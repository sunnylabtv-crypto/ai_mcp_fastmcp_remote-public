# mcp_server/server.py
"""
FastMCP 메인 서버 (멀티유저 지원 - URL 파라미터 방식)
"""
import sys
import os      
import logging
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from fastmcp import FastMCP, Context
from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.server.dependencies import get_http_request

# 프로젝트 루트를 Python path에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from mcp_server.config import (
    CONFIG, validate_config, print_config_summary,
    UserConfig, SUPPORTED_USERS
)
from mcp_server.services.service_manager import (
    initialize_all_services, get_all_service_status,
    initialize_user_services, get_user_service_status,
    set_current_user, get_current_user
)
from mcp_server.tools import (
    register_gmail_tools,
    register_openai_tools,
    register_salesforce_tools,
    register_company_helpdesk_tools,
    register_calendar_tools,
    register_logging_tools
)
from mcp_server.logging_middleware import LoggingMiddleware
from mcp_server.log_receiver import router as log_api_router

# 로깅 설정
log_handlers = [logging.StreamHandler()]

if os.getenv('MCP_MODE', 'stdio') == 'stdio':
    try:
        log_handlers.append(logging.FileHandler('mcp_server.log', encoding='utf-8'))
    except:
        pass

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=log_handlers
)

logger = logging.getLogger(__name__)

# ============================================================
# 사용자별 서비스 캐시
# ============================================================

_user_services_cache = {}


def get_or_create_user_services(user_id: str):
    """사용자별 서비스 인스턴스 생성/반환"""
    if user_id not in _user_services_cache:
        if not UserConfig.is_valid_user(user_id):
            logger.warning(f"⚠️ 알 수 없는 사용자: {user_id}, 기본값 'admin' 사용")
            user_id = 'admin'
        
        logger.info(f"🔄 사용자 '{user_id}' 서비스 초기화 중...")
        config = UserConfig.get_config(user_id)
        services = initialize_user_services(config)
        _user_services_cache[user_id] = {
            'config': config,
            'services': services
        }
        logger.info(f"✅ 사용자 '{user_id}' 서비스 초기화 완료")
    
    return _user_services_cache[user_id]


# ============================================================
# MCP 인스턴스
# ============================================================

mcp = FastMCP("Sales Assistant")


# ============================================================
# 유저 식별 미들웨어 (FastMCP 공식 Middleware)
# ============================================================

class UserIdentificationMiddleware(Middleware):
    """URL 파라미터에서 user_id를 추출하여 서비스 초기화"""
    
    async def _extract_and_set_user(self, context: MiddlewareContext):
        """HTTP request에서 user_id 추출 및 설정"""
        try:
            request = get_http_request()
            user_id = request.query_params.get("user_id", "admin")
            
            # 유효한 사용자인지 확인
            if user_id not in SUPPORTED_USERS:
                logger.warning(f"⚠️ 알 수 없는 사용자: {user_id}, 기본값 'admin' 사용")
                user_id = "admin"
            
            # 사용자 서비스 초기화 및 컨텍스트 설정
            get_or_create_user_services(user_id)
            set_current_user(user_id)
            
            # Context state에 저장
            context.fastmcp_context.set_state("user_id", user_id)
            context.fastmcp_context.set_state("user_config", _user_services_cache[user_id]['config'])
            
            logger.debug(f"🔗 요청 처리: user_id={user_id}")
            
        except Exception as e:
            logger.warning(f"⚠️ 사용자 식별 실패, 기본값 사용: {e}")
            set_current_user("admin")
            context.fastmcp_context.set_state("user_id", "admin")
    
    async def on_call_tool(self, context: MiddlewareContext, call_next):
        """Tool 호출 시 user_id 확인"""
        await self._extract_and_set_user(context)
        return await call_next(context)
    
    async def on_read_resource(self, context: MiddlewareContext, call_next):
        """Resource 읽기 시 user_id 확인"""
        await self._extract_and_set_user(context)
        return await call_next(context)
    
    async def on_list_tools(self, context: MiddlewareContext, call_next):
        """Tool 목록 조회 시 user_id 확인"""
        await self._extract_and_set_user(context)
        return await call_next(context)


# MCP에 미들웨어 등록 (새로운 방식)
# 순서 중요: UserIdentification → Logging (Logging이 user_id를 사용하기 위해)
mcp.add_middleware(UserIdentificationMiddleware())
mcp.add_middleware(LoggingMiddleware())


# ============================================================
# 도구 등록
# ============================================================

def register_all_tools(mcp_instance):
    """MCP 도구 등록"""
    logger.info("\n" + "=" * 70)
    logger.info("🔧 MCP 도구 등록 중...")
    logger.info("=" * 70)

    register_gmail_tools(mcp_instance)
    register_openai_tools(mcp_instance)
    register_salesforce_tools(mcp_instance)
    register_company_helpdesk_tools(mcp_instance)
    register_calendar_tools(mcp_instance)
    register_logging_tools(mcp_instance)

    logger.info("\n✅ 모든 MCP 도구 등록 완료!")
    logger.info("=" * 70 + "\n")


def register_workflow_tools(mcp_instance):
    """워크플로우 도구 등록"""
    
    @mcp_instance.tool()
    def check_all_services_status():
        """모든 서비스의 현재 상태를 확인합니다."""
        current_user = get_current_user()
        logger.info(f"📊 서비스 상태 확인 요청 (user: {current_user})")
        
        try:
            # 멀티유저 모드: 현재 사용자의 서비스 상태 조회
            if current_user:
                status = get_user_service_status(current_user)
            else:
                status = get_all_service_status()
            
            summary = {
                "current_user": current_user,
                "gmail": "✅ 인증됨" if status['gmail']['authenticated'] else "❌ 미인증",
                "gmail_account": status['gmail'].get('user_email', 'unknown'),
                "openai": "✅ 설정됨" if (status['openai']['initialized'] and status['openai']['api_key_configured']) else "❌ 미설정",
                "salesforce": "✅ 인증됨" if status['salesforce']['authenticated'] else "❌ 미인증",
                "vectordb": "✅ 초기화됨" if status['vectordb']['initialized'] else "❌ 미초기화",
                "calendar": "✅ 인증됨" if status['calendar']['authenticated'] else "❌ 미인증",
                "calendar_account": status['calendar'].get('user_email', 'unknown')
            }
            
            return {"status": "success", "summary": summary, "details": status}
            
        except Exception as e:
            logger.error(f"❌ 상태 확인 실패: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}

    @mcp_instance.tool()
    def get_current_user_info():
        """현재 연결된 사용자 정보를 반환합니다."""
        current_user = get_current_user()
        if current_user and current_user in _user_services_cache:
            user_data = _user_services_cache[current_user]
            return {
                "user_id": current_user,
                "gmail_account": user_data['config'].get('gmail_account', 'unknown'),
                "sfdc_enabled": user_data['config'].get('sfdc_enabled', False)
            }
        return {"user_id": current_user or "unknown", "status": "not_initialized"}

    @mcp_instance.tool()
    def process_customer_email_workflow(
        email_id: str,
        email_sender: str,
        email_subject: str,
        email_content: str
    ) -> dict:
        """고객 이메일 처리 전체 워크플로우를 실행합니다."""
        current_user = get_current_user()
        logger.info(f"🔄 고객 이메일 워크플로우 시작: {email_sender} (user: {current_user})")
        
        workflow_result = {
            "status": "success",
            "steps": {},
            "email_id": email_id,
            "sender": email_sender,
            "processed_by": current_user
        }
        
        try:
            from mcp_server.services import openai_service, salesforce_service, gmail_service
            
            customer_info = openai_service.extract_customer_info(email_content, email_sender)
            workflow_result["steps"]["extract_info"] = {"status": "success", "data": customer_info}
            
            if customer_info['has_all_info']:
                lead_id = salesforce_service.create_lead(customer_info)
                if lead_id:
                    lead_url = salesforce_service.get_lead_url(lead_id)
                    workflow_result["steps"]["create_lead"] = {"status": "success", "lead_id": lead_id, "lead_url": lead_url}
                else:
                    workflow_result["steps"]["create_lead"] = {"status": "error", "message": "Lead 생성 실패"}
            else:
                workflow_result["steps"]["create_lead"] = {"status": "skipped", "message": f"정보 부족: {customer_info['missing_fields']}"}
            
            reply = openai_service.generate_reply(customer_info, email_subject)
            workflow_result["steps"]["generate_reply"] = {"status": "success", "data": reply}
            
            send_success = gmail_service.send_reply(
                to_email=email_sender,
                subject=reply['subject'],
                content=reply['body'],
                original_email_id=email_id
            )
            workflow_result["steps"]["send_reply"] = {"status": "success" if send_success else "error"}
            
            return workflow_result
            
        except Exception as e:
            logger.error(f"❌ 워크플로우 실패: {e}", exc_info=True)
            workflow_result["status"] = "error"
            workflow_result["error"] = str(e)
            return workflow_result


# 도구 등록
register_all_tools(mcp)
register_workflow_tools(mcp)


# ============================================================
# 서비스 초기화
# ============================================================

def initialize_default_services():
    """기본 서비스 초기화 (admin 사용자)"""
    logger.info("=" * 70)
    logger.info("🚀 FastMCP Sales Assistant 서버 시작")
    logger.info("=" * 70)
    
    print_config_summary()
    
    if not validate_config():
        logger.warning("⚠️ 설정 검증 실패! 일부 기능이 제한될 수 있습니다.")
    
    logger.info("\n" + "=" * 70)
    logger.info("📡 기본 서비스 초기화 중 (admin)...")
    logger.info("=" * 70 + "\n")
    
    try:
        # 기본 사용자(admin) 서비스 초기화
        get_or_create_user_services('admin')
        set_current_user('admin')
        logger.info("✅ 기본 서비스 초기화 완료!")
    except Exception as e:
        logger.warning(f"⚠️ 서비스 초기화 중 오류: {e}")


# ============================================================
# 메인 함수
# ============================================================

def main():
    """메인 함수 - 서버 시작"""
    mode = os.getenv('MCP_MODE', 'stdio').lower()
    
    # 서비스 초기화
    try:
        initialize_default_services()
    except Exception as e:
        logger.warning(f"⚠️ 서비스 초기화 중 오류: {e}")
    
    if mode == 'sse':
        # Streamable HTTP 모드 (MCP 2025-03-26 스펙)
        host = os.getenv('HOST', '0.0.0.0')
        port = int(os.getenv('PORT', '8000'))
        
        logger.info("\n" + "=" * 70)
        logger.info("✅ FastMCP Multi-User Server 준비 완료!")
        logger.info("=" * 70)
        logger.info("🌐 Streamable HTTP 모드로 서버 시작")
        logger.info(f"   Host: {host}")
        logger.info(f"   Port: {port}")
        logger.info("")
        logger.info("   📌 엔드포인트 (URL 파라미터로 유저 구분):")
        logger.info(f"      http://{host}:{port}/mcp?user_id=admin")
        logger.info(f"      http://{host}:{port}/mcp?user_id=sales")
        logger.info(f"      http://{host}:{port}/mcp?user_id=finance")
        logger.info("")
        logger.info(f"   지원 사용자: {', '.join(SUPPORTED_USERS)}")
        logger.info("=" * 70 + "\n")
        
        # 로그 API 서버를 별도 쓰레드로 실행 (8001번 포트)
        import threading
        
        def run_log_api():
            try:
                from fastapi import FastAPI
                from fastapi.middleware.cors import CORSMiddleware
                import uvicorn
                
                log_app = FastAPI(title="MCP Log API")
                log_app.include_router(log_api_router, prefix="/api")
                log_app.add_middleware(
                    CORSMiddleware,
                    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
                )
                
                @log_app.get("/")
                async def root():
                    return {"service": "MCP Log API", "status": "running"}
                
                logger.info("📡 로그 API 서버 시작 (port 8001)")
                uvicorn.run(log_app, host="0.0.0.0", port=8001, log_level="warning")
            except Exception as e:
                logger.error(f"❌ 로그 API 서버 실패: {e}")
        
        log_thread = threading.Thread(target=run_log_api, daemon=True)
        log_thread.start()
        logger.info("📡 로그 API: http://0.0.0.0:8001/api/logs/upload")
        
        # FastMCP 서버 실행 (8000번 포트)
        mcp.run(transport="http", host=host, port=port)
        
    else:
        # stdio 모드
        logger.info("\n" + "=" * 70)
        logger.info("✅ FastMCP Sales Assistant 서버가 준비되었습니다!")
        logger.info("📟 stdio 모드로 서버 시작")
        logger.info("=" * 70 + "\n")
        
        mcp.run()


if __name__ == "__main__":
    main()
