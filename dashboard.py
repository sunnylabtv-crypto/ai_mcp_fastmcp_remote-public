# dashboard.py
"""
MCP 통합 로깅 대시보드 (Streamlit)
- Remote + Local 로그 통합 조회
- 실시간 모니터링, 검색, 통계

실행: streamlit run dashboard.py --server.port 8501
"""
import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
import json

# ============================================================
# 설정
# ============================================================

PROJECT_ROOT = Path(__file__).parent
# DB는 영구 저장 폴더에 위치 (배포 시에도 유지)
DB_DIR = Path("/app/data/db") if Path("/app/data/db").exists() else PROJECT_ROOT / "data" / "db"
DB_PATH = DB_DIR / "mcp_logs.db"

st.set_page_config(
    page_title="MCP 로그 대시보드",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================================
# 데이터베이스 함수
# ============================================================

@st.cache_resource
def get_connection():
    """SQLite 연결 (캐시)"""
    return sqlite3.connect(str(DB_PATH), check_same_thread=False)


def query_logs(conn, start_time=None, end_time=None, tool_name=None, 
               source=None, success=None, keyword=None, limit=100):
    """로그 검색"""
    query = "SELECT * FROM tool_logs WHERE 1=1"
    params = []
    
    if start_time:
        query += " AND timestamp >= ?"
        params.append(start_time)
    if end_time:
        query += " AND timestamp <= ?"
        params.append(end_time)
    if tool_name:
        query += " AND tool_name LIKE ?"
        params.append(f"%{tool_name}%")
    if source and source != "전체":
        query += " AND source = ?"
        params.append(source.lower())
    if success is not None and success != "전체":
        query += " AND success = ?"
        params.append(1 if success == "성공" else 0)
    if keyword:
        query += " AND (parameters LIKE ? OR error_message LIKE ?)"
        params.extend([f"%{keyword}%"] * 2)
    
    query += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)
    
    return pd.read_sql_query(query, conn, params=params)


def get_stats(conn, start_time=None, end_time=None, source=None):
    """통계 조회"""
    where_clause = "WHERE 1=1"
    params = []
    
    if start_time:
        where_clause += " AND timestamp >= ?"
        params.append(start_time)
    if end_time:
        where_clause += " AND timestamp <= ?"
        params.append(end_time)
    if source and source != "전체":
        where_clause += " AND source = ?"
        params.append(source.lower())
    
    # 전체 통계
    query = f"""
        SELECT 
            COUNT(*) as total_calls,
            SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as success_count,
            SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as error_count,
            AVG(duration_ms) as avg_duration_ms
        FROM tool_logs {where_clause}
    """
    overall = pd.read_sql_query(query, conn, params=params).iloc[0].to_dict()
    
    # 도구별 통계
    query = f"""
        SELECT 
            tool_name,
            COUNT(*) as calls,
            SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as success,
            AVG(duration_ms) as avg_duration
        FROM tool_logs {where_clause}
        GROUP BY tool_name
        ORDER BY calls DESC
    """
    by_tool = pd.read_sql_query(query, conn, params=params)
    
    return overall, by_tool


def get_hourly_calls(conn, start_time=None, end_time=None, source=None):
    """시간대별 호출 수"""
    where_clause = "WHERE 1=1"
    params = []
    
    if start_time:
        where_clause += " AND timestamp >= ?"
        params.append(start_time)
    if end_time:
        where_clause += " AND timestamp <= ?"
        params.append(end_time)
    if source and source != "전체":
        where_clause += " AND source = ?"
        params.append(source.lower())
    
    query = f"""
        SELECT 
            strftime('%Y-%m-%d %H:00', timestamp) as hour,
            source,
            COUNT(*) as calls
        FROM tool_logs {where_clause}
        GROUP BY hour, source
        ORDER BY hour
    """
    return pd.read_sql_query(query, conn, params=params)


# ============================================================
# UI 컴포넌트
# ============================================================

def render_summary_cards(overall):
    """상단 요약 카드"""
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            label="📞 총 호출",
            value=f"{int(overall['total_calls'] or 0):,}"
        )
    
    with col2:
        success_rate = 0
        if overall['total_calls'] and overall['total_calls'] > 0:
            success_rate = (overall['success_count'] or 0) / overall['total_calls'] * 100
        st.metric(
            label="✅ 성공률",
            value=f"{success_rate:.1f}%"
        )
    
    with col3:
        avg_duration = overall['avg_duration_ms'] or 0
        st.metric(
            label="⏱️ 평균 응답",
            value=f"{avg_duration:.0f}ms"
        )
    
    with col4:
        st.metric(
            label="❌ 에러 수",
            value=f"{int(overall['error_count'] or 0):,}"
        )


def render_chart(hourly_data):
    """시간대별 호출 차트"""
    if hourly_data.empty:
        st.info("데이터가 없습니다.")
        return
    
    # Pivot for stacked bar
    pivot = hourly_data.pivot(index='hour', columns='source', values='calls').fillna(0)
    st.bar_chart(pivot)


def render_log_table(logs):
    """로그 테이블"""
    if logs.empty:
        st.info("검색 결과가 없습니다.")
        return
    
    # 컬럼 포맷팅
    display_df = logs.copy()
    
    # 성공/실패 표시
    display_df['상태'] = display_df['success'].apply(lambda x: '✅' if x else '❌')
    
    # 소스 표시
    display_df['소스'] = display_df['source'].apply(
        lambda x: '☁️ Remote' if x == 'remote' else '💻 Local'
    )
    
    # 시간 포맷
    display_df['시간'] = pd.to_datetime(display_df['timestamp']).dt.strftime('%m-%d %H:%M:%S')
    
    # 응답시간 포맷
    display_df['응답시간'] = display_df['duration_ms'].apply(
        lambda x: f"{x:.0f}ms" if pd.notna(x) else "-"
    )
    
    # 표시할 컬럼
    columns = ['시간', '소스', 'tool_name', '상태', '응답시간', 'error_message']
    
    st.dataframe(
        display_df[columns],
        use_container_width=True,
        height=400
    )


def render_tool_stats(by_tool):
    """도구별 통계"""
    if by_tool.empty:
        st.info("데이터가 없습니다.")
        return
    
    # 성공률 계산
    by_tool['success_rate'] = (by_tool['success'] / by_tool['calls'] * 100).round(1)
    by_tool['avg_duration'] = by_tool['avg_duration'].round(0)
    
    # 컬럼 이름 변경
    display_df = by_tool.rename(columns={
        'tool_name': '도구',
        'calls': '호출 수',
        'success': '성공',
        'success_rate': '성공률(%)',
        'avg_duration': '평균 응답(ms)'
    })
    
    st.dataframe(display_df, use_container_width=True)


# ============================================================
# 메인 앱
# ============================================================

def main():
    st.title("📊 MCP 통합 로그 대시보드")
    st.markdown("Remote MCP + Local MCP 로그 통합 모니터링")
    
    # DB 연결 확인
    if not DB_PATH.exists():
        st.error(f"❌ 로그 데이터베이스를 찾을 수 없습니다: {DB_PATH}")
        st.info("MCP 서버를 실행하여 로그를 생성해주세요.")
        return
    
    conn = get_connection()
    
    # ── 사이드바: 필터 ──
    st.sidebar.header("🔍 필터")
    
    # 시간 범위
    time_range = st.sidebar.selectbox(
        "시간 범위",
        ["최근 1시간", "오늘", "최근 7일", "최근 30일", "전체"]
    )
    
    now = datetime.utcnow()
    if time_range == "최근 1시간":
        start_time = (now - timedelta(hours=1)).isoformat() + "Z"
    elif time_range == "오늘":
        start_time = now.replace(hour=0, minute=0, second=0).isoformat() + "Z"
    elif time_range == "최근 7일":
        start_time = (now - timedelta(days=7)).isoformat() + "Z"
    elif time_range == "최근 30일":
        start_time = (now - timedelta(days=30)).isoformat() + "Z"
    else:
        start_time = None
    
    end_time = None
    
    # 소스 필터
    source = st.sidebar.selectbox(
        "소스",
        ["전체", "Remote", "Local"]
    )
    
    # 상태 필터
    success_filter = st.sidebar.selectbox(
        "상태",
        ["전체", "성공", "실패"]
    )
    
    # 도구 필터
    tool_name = st.sidebar.text_input("도구 이름 (부분 일치)")
    
    # 키워드 검색
    keyword = st.sidebar.text_input("키워드 검색")
    
    # 결과 수
    limit = st.sidebar.slider("표시 개수", 10, 500, 100)
    
    # ── 메인: 대시보드 ──
    
    # 통계 조회
    overall, by_tool = get_stats(conn, start_time, end_time, source)
    
    # 요약 카드
    st.subheader("📈 요약")
    render_summary_cards(overall)
    
    st.divider()
    
    # 차트
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("📊 시간대별 호출 수")
        hourly_data = get_hourly_calls(conn, start_time, end_time, source)
        render_chart(hourly_data)
    
    with col2:
        st.subheader("🔧 도구별 통계")
        render_tool_stats(by_tool)
    
    st.divider()
    
    # 로그 테이블
    st.subheader("📋 로그 목록")
    
    logs = query_logs(
        conn,
        start_time=start_time,
        end_time=end_time,
        tool_name=tool_name if tool_name else None,
        source=source,
        success=success_filter if success_filter != "전체" else None,
        keyword=keyword if keyword else None,
        limit=limit
    )
    
    render_log_table(logs)
    
    # 로그 상세 (선택 시)
    if not logs.empty:
        st.subheader("🔍 상세 보기")
        selected_id = st.selectbox(
            "로그 선택",
            logs['id'].tolist(),
            format_func=lambda x: f"#{x} - {logs[logs['id']==x]['tool_name'].values[0]} ({logs[logs['id']==x]['timestamp'].values[0][:19]})"
        )
        
        if selected_id:
            selected_log = logs[logs['id'] == selected_id].iloc[0]
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.json({
                    "id": int(selected_log['id']),
                    "timestamp": selected_log['timestamp'],
                    "source": selected_log['source'],
                    "user_id": selected_log['user_id'],
                    "tool_name": selected_log['tool_name'],
                    "success": bool(selected_log['success']),
                    "duration_ms": selected_log['duration_ms']
                })
            
            with col2:
                st.write("**파라미터:**")
                try:
                    params = json.loads(selected_log['parameters']) if selected_log['parameters'] else {}
                    st.json(params)
                except:
                    st.code(selected_log['parameters'])
                
                if selected_log['error_message']:
                    st.error(f"**에러:** {selected_log['error_message']}")
                
                if selected_log['result_summary']:
                    st.info(f"**결과:** {selected_log['result_summary']}")
    
    # Footer
    st.divider()
    st.caption(f"🕐 마지막 업데이트: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 자동 새로고침 (30초)
    if st.sidebar.checkbox("🔄 자동 새로고침 (30초)", value=False):
        import time
        time.sleep(30)
        st.rerun()


if __name__ == "__main__":
    main()
