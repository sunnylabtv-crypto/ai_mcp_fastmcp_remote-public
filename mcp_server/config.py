# mcp_server/config.py
"""
FastMCP 서버 설정 (멀티유저 지원)
"""
import os
import sys
import base64
from pathlib import Path
from dotenv import load_dotenv

# 프로젝트 루트 경로
PROJECT_ROOT = Path(__file__).parent.parent

# .env 파일 로드 (루트 디렉토리에 있음)
env_path = PROJECT_ROOT / '.env'
load_dotenv(dotenv_path=env_path)

print(f"[INFO] .env file path: {env_path}", file=sys.stderr)
print(f"[INFO] .env file exists: {env_path.exists()}", file=sys.stderr)

# ============================================================
# 사용자 설정 (멀티유저 지원)
# ============================================================

# 지원하는 사용자 목록
SUPPORTED_USERS = ['admin', 'sales', 'finance']

# 사용자별 설정 매핑
USER_CONFIG_MAP = {
    'admin': {
        'gmail_token_env': 'GMAIL_TOKEN',  # 기존 토큰 사용 (admin@example.com)
        'gmail_account': 'admin@example.com',
        'sfdc_enabled': True,
        'sfdc_client_id_env': 'SF_CLIENT_ID',
        'sfdc_username_env': 'SF_USERNAME',
        'sfdc_key_env': 'SF_PRIVATE_KEY',
    },
    'sales': {
        'gmail_token_env': 'GMAIL_TOKEN',  # Admin과 동일 (admin@example.com)
        'gmail_account': 'admin@example.com',
        'sfdc_enabled': True,
        'sfdc_client_id_env': 'SF_CLIENT_ID',
        'sfdc_username_env': 'SF_USERNAME',
        'sfdc_key_env': 'SF_PRIVATE_KEY',
    },
    'finance': {
        'gmail_token_env': 'GMAIL_TOKEN_FINANCE',  # 별도 토큰 (finance@example.com)
        'gmail_account': 'finance@example.com',
        'sfdc_enabled': False,
        'sfdc_client_id_env': None,
        'sfdc_username_env': None,
        'sfdc_key_env': None,
    },
}

# ============================================================
# 환경변수에서 파일 생성 (Docker/Cloud 환경용)
# ============================================================

def create_file_from_env(env_var: str, file_path: str, is_base64: bool = False) -> bool:
    """환경변수 내용을 파일로 저장 (base64 디코딩 지원)"""
    content = os.getenv(env_var)
    if content:
        try:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            if is_base64:
                decoded_content = base64.b64decode(content).decode('utf-8')
                with open(file_path, 'w') as f:
                    f.write(decoded_content)
                print(f"[INFO] Created {file_path} from {env_var} (base64 decoded)", file=sys.stderr)
            else:
                with open(file_path, 'w') as f:
                    f.write(content)
                print(f"[INFO] Created {file_path} from {env_var}", file=sys.stderr)
            return True
        except Exception as e:
            print(f"[ERROR] Failed to create {file_path}: {e}", file=sys.stderr)
    return False


def setup_user_credentials():
    """모든 사용자의 credentials 파일 생성 (Cloud 환경)"""
    
    # Gmail Credentials (공통)
    gmail_creds_path = '/app/credentials/credentials_new.json'
    if os.getenv('GMAIL_CREDENTIALS'):
        create_file_from_env('GMAIL_CREDENTIALS', gmail_creds_path, is_base64=True)
    
    # 사용자별 Gmail Token 생성
    for user_id, user_config in USER_CONFIG_MAP.items():
        token_env = user_config['gmail_token_env']
        token_path = f'/app/credentials/token_{user_id}.json'
        
        if os.getenv(token_env):
            create_file_from_env(token_env, token_path, is_base64=True)
            print(f"[INFO] Created Gmail token for user: {user_id} from {token_env}", file=sys.stderr)
    
    # Salesforce JWT Key (공통)
    sf_key_path = '/app/credentials/salesforce.key'
    if os.getenv('SF_PRIVATE_KEY'):
        create_file_from_env('SF_PRIVATE_KEY', sf_key_path)


# Cloud 환경에서 credentials 설정
if os.getenv('MCP_MODE') == 'sse':
    setup_user_credentials()


# ============================================================
# UserConfig 클래스 (사용자별 설정 관리)
# ============================================================

class UserConfig:
    """사용자별 설정 관리 클래스"""
    
    _configs = {}
    
    @classmethod
    def get_supported_users(cls) -> list:
        return SUPPORTED_USERS
    
    @classmethod
    def is_valid_user(cls, user_id: str) -> bool:
        return user_id in SUPPORTED_USERS
    
    @classmethod
    def get_config(cls, user_id: str) -> dict:
        if user_id not in cls._configs:
            cls._configs[user_id] = cls._load_user_config(user_id)
        return cls._configs[user_id]
    
    @classmethod
    def _load_user_config(cls, user_id: str) -> dict:
        if user_id not in USER_CONFIG_MAP:
            raise ValueError(f"Unknown user: {user_id}. Supported users: {SUPPORTED_USERS}")
        
        user_map = USER_CONFIG_MAP[user_id]
        
        # Gmail 설정
        gmail_config = {
            'SCOPES': [
                'https://www.googleapis.com/auth/gmail.modify',
                'https://www.googleapis.com/auth/calendar',
                'https://www.googleapis.com/auth/calendar.events'
            ],
            'TOKEN_FILE': cls._get_token_path(user_id),
            'CREDENTIALS_FILE': cls._get_credentials_path(),
        }
        
        # OpenAI 설정 (공통)
        openai_config = {
            'API_KEY': os.getenv('OPENAI_API_KEY'),
            'MODEL': 'gpt-4o-mini',
            'BASE_URL': 'https://api.openai.com/v1',
        }
        
        # VectorDB 설정 (공통)
        vectordb_config = {
            'CHROMA_PERSIST_DIR': os.getenv('CHROMA_PERSIST_DIR', '/app/data/chromadb'),
            'COLLECTION_NAME': os.getenv('COLLECTION_NAME', 'it_helpdesk_docs'),
        }
        
        # Salesforce 설정 (사용자별)
        salesforce_config = None
        if user_map['sfdc_enabled']:
            salesforce_config = {
                'CONSUMER_KEY': os.getenv(user_map['sfdc_client_id_env']) if user_map['sfdc_client_id_env'] else None,
                'USERNAME': os.getenv(user_map['sfdc_username_env']) if user_map['sfdc_username_env'] else None,
                'LOGIN_URL': os.getenv('SF_LOGIN_URL', 'https://login.salesforce.com'),
                'JWT_KEY_PATH': cls._get_sfdc_key_path(),
            }
        
        return {
            'user_id': user_id,
            'gmail_account': user_map['gmail_account'],
            'sfdc_enabled': user_map['sfdc_enabled'],
            'GMAIL_CONFIG': gmail_config,
            'OPENAI_CONFIG': openai_config,
            'SALESFORCE_CONFIG': salesforce_config,
            'VECTORDB_CONFIG': vectordb_config,
        }
    
    @classmethod
    def _get_token_path(cls, user_id: str) -> str:
        cloud_path = f'/app/credentials/token_{user_id}.json'
        local_path = str(PROJECT_ROOT / 'credentials' / f'token_{user_id}.json')
        
        # 기존 token_new.json 호환 (admin용)
        if user_id == 'admin':
            old_cloud_path = '/app/token_new.json'
            old_local_path = str(PROJECT_ROOT / 'credentials' / 'token_new.json')
            if os.path.exists(old_cloud_path):
                return old_cloud_path
            if os.path.exists(old_local_path):
                return old_local_path
        
        if os.path.exists(cloud_path):
            return cloud_path
        if os.path.exists(local_path):
            return local_path
        return cloud_path
    
    @classmethod
    def _get_credentials_path(cls) -> str:
        cloud_path = '/app/credentials/credentials_new.json'
        local_path = str(PROJECT_ROOT / 'credentials' / 'credentials_new.json')
        old_cloud_path = '/app/credentials_new.json'
        old_local_path = str(PROJECT_ROOT / 'credentials_new.json')
        
        for path in [cloud_path, local_path, old_cloud_path, old_local_path]:
            if os.path.exists(path):
                return path
        return cloud_path
    
    @classmethod
    def _get_sfdc_key_path(cls) -> str:
        cloud_path = '/app/credentials/salesforce.key'
        local_path = str(PROJECT_ROOT / 'credentials' / 'sf_new.key')
        old_cloud_path = '/app/salesforce_jwt.key'
        
        for path in [cloud_path, local_path, old_cloud_path]:
            if os.path.exists(path):
                return path
        return cloud_path


# ============================================================
# 기존 단일 사용자 설정 (하위 호환성)
# ============================================================

DEFAULT_USER = 'admin'

# 기존 경로 호환
GMAIL_CREDENTIALS_PATH = '/app/credentials_new.json'
GMAIL_TOKEN_PATH = '/app/token_new.json'
SF_JWT_KEY_PATH = '/app/salesforce_jwt.key'

# 기존 방식으로 파일 생성 (하위 호환)
if os.getenv('GMAIL_CREDENTIALS'):
    create_file_from_env('GMAIL_CREDENTIALS', GMAIL_CREDENTIALS_PATH, is_base64=True)
if os.getenv('GMAIL_TOKEN'):
    create_file_from_env('GMAIL_TOKEN', GMAIL_TOKEN_PATH, is_base64=True)
if os.getenv('SF_PRIVATE_KEY'):
    create_file_from_env('SF_PRIVATE_KEY', SF_JWT_KEY_PATH)

# 기존 CONFIG 객체
GMAIL_CONFIG = {
    'SCOPES': [
        'https://www.googleapis.com/auth/gmail.modify',
        'https://www.googleapis.com/auth/calendar',
        'https://www.googleapis.com/auth/calendar.events'
    ],
    'TOKEN_FILE': GMAIL_TOKEN_PATH if os.path.exists(GMAIL_TOKEN_PATH) else str(PROJECT_ROOT / 'credentials' / 'token_new.json'),
    'CREDENTIALS_FILE': GMAIL_CREDENTIALS_PATH if os.path.exists(GMAIL_CREDENTIALS_PATH) else str(PROJECT_ROOT / 'credentials' / 'credentials_new.json'),
}

OPENAI_CONFIG = {
    'API_KEY': os.getenv('OPENAI_API_KEY'),
    'MODEL': 'gpt-4o-mini',
    'BASE_URL': 'https://api.openai.com/v1',
}

VECTORDB_CONFIG = {
    'CHROMA_PERSIST_DIR': os.getenv('CHROMA_PERSIST_DIR', '/app/data/chromadb'),
    'COLLECTION_NAME': os.getenv('COLLECTION_NAME', 'it_helpdesk_docs'),
}

SALESFORCE_CONFIG = {
    'CONSUMER_KEY': os.getenv('SF_CLIENT_ID'),
    'USERNAME': os.getenv('SF_USERNAME'),
    'LOGIN_URL': os.getenv('SF_LOGIN_URL', 'https://login.salesforce.com'),
    'JWT_KEY_PATH': SF_JWT_KEY_PATH if os.path.exists(SF_JWT_KEY_PATH) else os.getenv('SF_JWT_KEY'),
}

CONFIG = {
    'GMAIL_CONFIG': GMAIL_CONFIG,
    'OPENAI_CONFIG': OPENAI_CONFIG,
    'SALESFORCE_CONFIG': SALESFORCE_CONFIG,
    'VECTORDB_CONFIG': VECTORDB_CONFIG,
}


# ============================================================
# 설정 검증 및 출력 함수
# ============================================================

def validate_config() -> bool:
    """필수 환경변수 확인"""
    errors = []
    
    if not OPENAI_CONFIG['API_KEY']:
        errors.append("[ERROR] OPENAI_API_KEY environment variable is not set")
    
    if not os.path.exists(GMAIL_CONFIG['CREDENTIALS_FILE']):
        errors.append(f"[ERROR] Gmail credentials file not found: {GMAIL_CONFIG['CREDENTIALS_FILE']}")
    
    if errors:
        print("\n[VALIDATION FAILED]", file=sys.stderr)
        for error in errors:
            print(f"  {error}", file=sys.stderr)
        return False
    
    print("[SUCCESS] All configuration validated", file=sys.stderr)
    return True


def print_config_summary():
    """설정 요약 출력"""
    print("\n" + "="*60, file=sys.stderr)
    print("FastMCP Server Configuration (Multi-User Support)", file=sys.stderr)
    print("="*60, file=sys.stderr)
    
    print(f"\n[Supported Users]: {SUPPORTED_USERS}", file=sys.stderr)
    
    for user_id in SUPPORTED_USERS:
        user_map = USER_CONFIG_MAP[user_id]
        print(f"\n[User: {user_id}]", file=sys.stderr)
        print(f"  Gmail: {user_map['gmail_account']}", file=sys.stderr)
        print(f"  Gmail Token Env: {user_map['gmail_token_env']}", file=sys.stderr)
        print(f"  SFDC: {'Enabled' if user_map['sfdc_enabled'] else 'Disabled'}", file=sys.stderr)
    
    print("\n[OpenAI]", file=sys.stderr)
    print(f"  API Key: {'SET' if OPENAI_CONFIG['API_KEY'] else 'NOT SET'}", file=sys.stderr)
    
    print("\n" + "="*60 + "\n", file=sys.stderr)


if __name__ == "__main__":
    print_config_summary()
    validate_config()
