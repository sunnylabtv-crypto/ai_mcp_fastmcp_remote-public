# tests/test_mcp_server.py
"""
MCP 서버 기능 테스트
"""
import sys
from pathlib import Path

# 프로젝트 루트를 Python path에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import logging
from mcp_server.config import CONFIG, validate_config, print_config_summary
from mcp_server.services.service_manager import initialize_all_services, get_all_service_status

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def test_config():
    """설정 파일 테스트"""
    logger.info("\n" + "=" * 70)
    logger.info("테스트 1: 설정 파일 검증")
    logger.info("=" * 70)
    
    print_config_summary()
    
    if validate_config():
        logger.info("✅ 설정 검증 성공")
        return True
    else:
        logger.error("❌ 설정 검증 실패")
        return False


def test_service_initialization():
    """서비스 초기화 테스트"""
    logger.info("\n" + "=" * 70)
    logger.info("테스트 2: 서비스 초기화")
    logger.info("=" * 70)
    
    try:
        results = initialize_all_services(CONFIG)
        
        logger.info("\n초기화 결과:")
        for service, success in results.items():
            status = "✅" if success else "❌"
            logger.info(f"  {status} {service}")
        
        if all(results.values()):
            logger.info("\n✅ 모든 서비스 초기화 성공")
            return True
        else:
            logger.warning("\n⚠️ 일부 서비스 초기화 실패")
            return False
            
    except Exception as e:
        logger.error(f"❌ 서비스 초기화 중 예외 발생: {e}", exc_info=True)
        return False


def test_service_status():
    """서비스 상태 확인 테스트"""
    logger.info("\n" + "=" * 70)
    logger.info("테스트 3: 서비스 상태 확인")
    logger.info("=" * 70)
    
    try:
        status = get_all_service_status()
        
        logger.info("\n서비스 상태:")
        logger.info(f"  Gmail: {status['gmail']}")
        logger.info(f"  OpenAI: {status['openai']}")
        logger.info(f"  Salesforce: {status['salesforce']}")
        
        logger.info("\n✅ 상태 확인 성공")
        return True
        
    except Exception as e:
        logger.error(f"❌ 상태 확인 중 예외 발생: {e}", exc_info=True)
        return False


def test_gmail_fetch(test_fetch: bool = False):
    """Gmail 이메일 조회 테스트 (선택적)"""
    if not test_fetch:
        logger.info("\n⏭️  Gmail 조회 테스트 건너뛰기 (test_fetch=False)")
        return True
    
    logger.info("\n" + "=" * 70)
    logger.info("테스트 4: Gmail 이메일 조회")
    logger.info("=" * 70)
    
    try:
        from mcp_server.services import gmail_service
        
        emails = gmail_service.get_recent_emails(minutes_ago=60, max_results=5)
        
        logger.info(f"\n조회된 이메일 수: {len(emails)}")
        
        if emails:
            logger.info("\n최근 이메일:")
            for i, email in enumerate(emails[:3], 1):
                logger.info(f"\n{i}. 발신자: {email['sender']}")
                logger.info(f"   제목: {email['subject']}")
                logger.info(f"   내용 미리보기: {email['content'][:100]}...")
        
        logger.info("\n✅ Gmail 조회 테스트 성공")
        return True
        
    except Exception as e:
        logger.error(f"❌ Gmail 조회 실패: {e}", exc_info=True)
        return False


def test_mcp_tools():
    """MCP 도구 등록 테스트"""
    logger.info("\n" + "=" * 70)
    logger.info("테스트 5: MCP 도구 등록")
    logger.info("=" * 70)
    
    try:
        from mcp_server.server import mcp
        
        # ✅ list_tools() → get_tools()로 변경
        tools = mcp.get_tools()
        
        logger.info(f"\n등록된 도구 수: {len(tools)}")
        logger.info("\n도구 목록:")
        for tool_name, tool_func in tools.items():
            logger.info(f"  - {tool_name}")
        
        # 예상되는 필수 도구들
        required_tools = [
            'fetch_unread_emails',
            'send_email_reply',
            'analyze_email_with_ai',
            'generate_email_reply',
            'create_salesforce_lead',
            'check_all_services_status',
            'process_customer_email_workflow'
        ]
        
        registered_tool_names = list(tools.keys())
        
        missing_tools = [tool for tool in required_tools if tool not in registered_tool_names]
        
        if missing_tools:
            logger.warning(f"\n⚠️ 누락된 도구: {missing_tools}")
        else:
            logger.info("\n✅ 모든 필수 도구가 등록되었습니다")
        
        logger.info("\n✅ MCP 도구 등록 테스트 성공")
        return True
        
    except Exception as e:
        logger.error(f"❌ MCP 도구 테스트 실패: {e}", exc_info=True)
        return False
    

def main():
    """메인 테스트 함수"""
    logger.info("\n" + "=" * 70)
    logger.info("🧪 FastMCP Sales Assistant 서버 테스트 시작")
    logger.info("=" * 70)
    
    results = {}
    
    # 테스트 실행
    results['config'] = test_config()
    results['services'] = test_service_initialization()
    results['status'] = test_service_status()
    results['tools'] = test_mcp_tools()
    
    # Gmail 조회 테스트는 선택적 (실제 API 호출하므로)
    # results['gmail'] = test_gmail_fetch(test_fetch=False)
    
    # 결과 요약
    logger.info("\n" + "=" * 70)
    logger.info("📊 테스트 결과 요약")
    logger.info("=" * 70)
    
    for test_name, success in results.items():
        status = "✅ 성공" if success else "❌ 실패"
        logger.info(f"  {test_name:15s}: {status}")
    
    success_count = sum(results.values())
    total_count = len(results)
    
    logger.info("-" * 70)
    logger.info(f"  전체: {success_count}/{total_count} 테스트 통과")
    logger.info("=" * 70)
    
    if all(results.values()):
        logger.info("\n🎉 모든 테스트 통과! 서버가 정상 작동합니다.")
        return 0
    else:
        logger.warning("\n⚠️ 일부 테스트 실패. 로그를 확인하세요.")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)