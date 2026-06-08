# retention_cron.py
"""
로그 보관주기 자동화 스크립트
- Hot (0~7일): 전체 상세 데이터
- Warm (7~30일): result_summary 압축
- Cold (30~90일): 일별 집계만 보관
- Archive (90일+): 삭제 또는 GCS 이동

실행: crontab에 등록
0 2 * * * /usr/bin/python3 /path/to/retention_cron.py
"""
import sqlite3
import gzip
import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 경로 설정
PROJECT_ROOT = Path(__file__).parent
LOGS_DIR = PROJECT_ROOT / "logs"
JSONL_PATH = LOGS_DIR / "mcp_tools.jsonl"
ARCHIVE_DIR = LOGS_DIR / "archive"
ARCHIVE_DIR.mkdir(exist_ok=True)

# DB는 영구 저장 폴더에 위치
DB_DIR = Path("/app/data/db") if Path("/app/data/db").exists() else PROJECT_ROOT / "data" / "db"
DB_PATH = DB_DIR / "mcp_logs.db"


def get_connection():
    """SQLite 연결"""
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def warm_phase():
    """
    Warm 단계 (7~30일)
    - result_summary 압축 (200자 이상 → 100자로 자르기)
    """
    logger.info("🟠 Warm 단계 처리 중...")
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # 7일 전 날짜
    cutoff = (datetime.utcnow() - timedelta(days=7)).isoformat() + "Z"
    
    # result_summary가 긴 레코드 압축
    cursor.execute("""
        UPDATE tool_logs
        SET result_summary = SUBSTR(result_summary, 1, 100) || '...[truncated]'
        WHERE timestamp < ?
        AND LENGTH(result_summary) > 100
        AND result_summary NOT LIKE '%[truncated]'
    """, (cutoff,))
    
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    
    logger.info(f"   ✅ {affected}개 레코드 압축")
    
    # JSONL 파일 압축 (7일 이상 된 파일)
    compress_old_jsonl()


def compress_old_jsonl():
    """오래된 JSONL 파일 gzip 압축"""
    if not JSONL_PATH.exists():
        return
    
    # 파일 크기가 10MB 이상이면 압축
    file_size = JSONL_PATH.stat().st_size
    if file_size > 10 * 1024 * 1024:  # 10MB
        archive_name = f"mcp_tools_{datetime.utcnow().strftime('%Y%m%d')}.jsonl.gz"
        archive_path = ARCHIVE_DIR / archive_name
        
        logger.info(f"   📦 JSONL 압축 중: {file_size / 1024 / 1024:.1f}MB → {archive_path}")
        
        with open(JSONL_PATH, 'rb') as f_in:
            with gzip.open(archive_path, 'wb') as f_out:
                f_out.writelines(f_in)
        
        # 원본 파일 비우기 (새로 시작)
        open(JSONL_PATH, 'w').close()
        
        logger.info(f"   ✅ 압축 완료")


def cold_phase():
    """
    Cold 단계 (30~90일)
    - 일별 집계 테이블로 이동
    - 상세 로그 삭제
    """
    logger.info("🔵 Cold 단계 처리 중...")
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # 30일 전 날짜
    cutoff = (datetime.utcnow() - timedelta(days=30)).isoformat() + "Z"
    
    # 일별 집계 생성
    cursor.execute("""
        INSERT OR REPLACE INTO daily_stats 
        (date, source, tool_name, total_calls, success_count, error_count, avg_duration_ms, min_duration_ms, max_duration_ms)
        SELECT 
            DATE(timestamp) as date,
            source,
            tool_name,
            COUNT(*) as total_calls,
            SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as success_count,
            SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as error_count,
            AVG(duration_ms) as avg_duration_ms,
            MIN(duration_ms) as min_duration_ms,
            MAX(duration_ms) as max_duration_ms
        FROM tool_logs
        WHERE timestamp < ?
        AND DATE(timestamp) NOT IN (SELECT DISTINCT date FROM daily_stats)
        GROUP BY DATE(timestamp), source, tool_name
    """, (cutoff,))
    
    aggregated = cursor.rowcount
    
    # 상세 로그 삭제
    cursor.execute("""
        DELETE FROM tool_logs
        WHERE timestamp < ?
    """, (cutoff,))
    
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    
    logger.info(f"   ✅ {aggregated}개 집계 생성, {deleted}개 상세 로그 삭제")


def archive_phase():
    """
    Archive 단계 (90일+)
    - 일별 집계도 삭제 (또는 GCS로 이동)
    """
    logger.info("⚫ Archive 단계 처리 중...")
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # 90일 전 날짜
    cutoff = (datetime.utcnow() - timedelta(days=90)).strftime('%Y-%m-%d')
    
    # 오래된 일별 집계 삭제
    cursor.execute("""
        DELETE FROM daily_stats
        WHERE date < ?
    """, (cutoff,))
    
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    
    logger.info(f"   ✅ {deleted}개 집계 삭제")
    
    # 오래된 압축 파일 정리 (90일 이상)
    cleanup_old_archives()


def cleanup_old_archives():
    """오래된 아카이브 파일 삭제"""
    cutoff = datetime.utcnow() - timedelta(days=90)
    
    for archive_file in ARCHIVE_DIR.glob("*.gz"):
        file_time = datetime.fromtimestamp(archive_file.stat().st_mtime)
        if file_time < cutoff:
            archive_file.unlink()
            logger.info(f"   🗑️ 아카이브 삭제: {archive_file.name}")


def vacuum_db():
    """DB 최적화"""
    logger.info("🧹 DB 최적화 중...")
    
    conn = get_connection()
    conn.execute("VACUUM")
    conn.close()
    
    # DB 파일 크기 확인
    db_size = DB_PATH.stat().st_size / 1024 / 1024
    logger.info(f"   ✅ DB 크기: {db_size:.2f}MB")


def main():
    """메인 함수"""
    logger.info("=" * 60)
    logger.info("🗂️ MCP 로그 보관주기 관리 시작")
    logger.info("=" * 60)
    
    if not DB_PATH.exists():
        logger.warning("❌ DB 파일이 없습니다. 종료합니다.")
        return
    
    try:
        warm_phase()
        cold_phase()
        archive_phase()
        vacuum_db()
        
        logger.info("=" * 60)
        logger.info("✅ 보관주기 관리 완료!")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"❌ 오류 발생: {e}", exc_info=True)


if __name__ == "__main__":
    main()
