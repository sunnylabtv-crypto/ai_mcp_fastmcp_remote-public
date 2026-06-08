# generate_token.py
"""
Gmail OAuth Token 생성 스크립트
사용법: python generate_token.py --user finance

예시:
    python generate_token.py --user finance    # finance@example.com용
    python generate_token.py --user sales      # 다른 계정용
"""
import os
import argparse
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials

# credentials 폴더 경로
CREDENTIALS_DIR = 'credentials'

SCOPES = [
    'https://www.googleapis.com/auth/gmail.modify',
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/calendar.events'
]

def generate_token(user_name: str, credentials_file: str = None):
    """새 사용자용 OAuth Token 생성"""
    
    # 기본 경로 설정
    if credentials_file is None:
        credentials_file = os.path.join(CREDENTIALS_DIR, 'credentials_new.json')
    
    output_file = os.path.join(CREDENTIALS_DIR, f'token_{user_name}.json')
    
    print(f"\n{'='*50}")
    print(f"🔐 Gmail OAuth Token 생성")
    print(f"{'='*50}")
    print(f"사용자: {user_name}")
    print(f"Credentials: {credentials_file}")
    print(f"출력 파일: {output_file}")
    print(f"{'='*50}\n")
    
    if not os.path.exists(credentials_file):
        print(f"❌ credentials 파일을 찾을 수 없습니다: {credentials_file}")
        print(f"   현재 디렉토리: {os.getcwd()}")
        return False
    
    if os.path.exists(output_file):
        response = input(f"⚠️  {output_file} 파일이 이미 존재합니다. 덮어쓸까요? (y/n): ")
        if response.lower() != 'y':
            print("취소되었습니다.")
            return False
    
    print("🌐 브라우저가 열립니다. 원하는 Gmail 계정으로 로그인하세요...")
    print(f"   (이 Token은 '{user_name}' 사용자용입니다)\n")
    
    try:
        flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)
        creds = flow.run_local_server(port=0)
        
        # Token 저장
        with open(output_file, 'w') as f:
            f.write(creds.to_json())
        
        print(f"\n✅ Token 생성 완료: {output_file}")
        
        # Base64 인코딩 안내
        print(f"\n{'='*50}")
        print(f"📋 GitHub Secrets 등록 방법")
        print(f"{'='*50}")
        print(f"\n1. PowerShell에서 base64 인코딩:")
        print(f'   [Convert]::ToBase64String([IO.File]::ReadAllBytes("{output_file}"))')
        print(f"\n2. GitHub Secrets에 추가:")
        print(f"   Name: GMAIL_TOKEN_{user_name.upper()}")
        print(f"   Value: (위에서 복사한 base64 문자열)")
        print(f"{'='*50}\n")
        
        return True
        
    except Exception as e:
        print(f"❌ Token 생성 실패: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Gmail OAuth Token 생성')
    parser.add_argument('--user', required=True, 
                        help='사용자 이름 (예: finance, sales, admin)')
    parser.add_argument('--credentials', default=None, 
                        help='OAuth Client ID 파일 (기본: credentials/credentials_new.json)')
    
    args = parser.parse_args()
    generate_token(args.user, args.credentials)