FROM python:3.11-slim

WORKDIR /app

# 시스템 패키지 업데이트
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Python 의존성 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 애플리케이션 코드 복사
COPY . .

# ChromaDB 데이터 디렉토리 생성
RUN mkdir -p /app/data/chromadb

# 환경변수 설정 (SSE 모드)
ENV MCP_MODE=sse
ENV HOST=0.0.0.0
ENV PORT=8000
ENV CHROMA_PERSIST_DIR=/app/data/chromadb
ENV COLLECTION_NAME=it_helpdesk_docs

# 포트 노출
EXPOSE 8000
EXPOSE 8001

# 서버 실행
CMD ["python", "mcp_server/server.py"]
