# mcp_server/services/vectordb_service.py
"""
ChromaDB 기반 Vector Database 서비스
IT Helpdesk RAG 시스템용
"""

import os
import hashlib
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

import chromadb
from chromadb.config import Settings

logger = logging.getLogger(__name__)

# 전역 변수
_chroma_client = None
_collection = None

# 설정
CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "/app/data/chromadb")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "it_helpdesk_docs")


def initialize(config: dict = None) -> bool:
    """ChromaDB 초기화"""
    global _chroma_client, _collection
    
    try:
        persist_dir = config.get('CHROMA_PERSIST_DIR', CHROMA_PERSIST_DIR) if config else CHROMA_PERSIST_DIR
        
        # 디렉토리 생성
        os.makedirs(persist_dir, exist_ok=True)
        
        # ChromaDB 클라이언트 생성 (영구 저장)
        _chroma_client = chromadb.PersistentClient(
            path=persist_dir,
            settings=Settings(anonymized_telemetry=False)
        )
        
        # 컬렉션 생성/가져오기
        _collection = _chroma_client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"description": "IT Helpdesk Knowledge Base"}
        )
        
        logger.info(f"✅ ChromaDB 초기화 완료 (경로: {persist_dir})")
        logger.info(f"   현재 문서 청크 수: {_collection.count()}")
        return True
        
    except Exception as e:
        logger.error(f"❌ ChromaDB 초기화 실패: {e}")
        return False


def get_status() -> dict:
    """VectorDB 상태 확인"""
    if _chroma_client is None or _collection is None:
        return {
            "initialized": False,
            "chunk_count": 0
        }
    
    return {
        "initialized": True,
        "chunk_count": _collection.count(),
        "persist_dir": CHROMA_PERSIST_DIR,
        "collection_name": COLLECTION_NAME
    }


def generate_doc_id(file_name: str, chunk_id: int) -> str:
    """문서 ID 생성"""
    return hashlib.md5(f"{file_name}_{chunk_id}".encode()).hexdigest()


def split_text_into_chunks(text: str, chunk_size: int = 1000, overlap: int = 200) -> List[str]:
    """텍스트를 청크로 분할"""
    chunks = []
    start = 0
    
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        
        # 문장 경계에서 자르기
        if end < len(text):
            last_period = chunk.rfind('.')
            last_newline = chunk.rfind('\n')
            cut_point = max(last_period, last_newline)
            
            if cut_point > chunk_size // 2:
                chunk = text[start:start + cut_point + 1]
                end = start + cut_point + 1
        
        if chunk.strip():
            chunks.append(chunk.strip())
        start = end - overlap
        
    return chunks


def add_document(
    content: str, 
    file_name: str, 
    embeddings: List[List[float]],
    file_path: str = "direct_upload"
) -> Dict[str, Any]:
    """
    문서를 Vector DB에 추가
    
    Args:
        content: 문서 내용
        file_name: 파일명
        embeddings: 청크별 임베딩 벡터 리스트
        file_path: 파일 경로 (선택)
        
    Returns:
        추가 결과
    """
    global _collection
    
    if _collection is None:
        return {"status": "error", "message": "VectorDB가 초기화되지 않았습니다."}
    
    try:
        # 청크 분할
        chunks = split_text_into_chunks(content)
        
        if len(chunks) != len(embeddings):
            return {
                "status": "error", 
                "message": f"청크 수({len(chunks)})와 임베딩 수({len(embeddings)})가 일치하지 않습니다."
            }
        
        # 데이터 준비
        ids = []
        documents = []
        metadatas = []
        
        for i, chunk in enumerate(chunks):
            doc_id = generate_doc_id(file_name, i)
            ids.append(doc_id)
            documents.append(chunk)
            metadatas.append({
                "file_name": file_name,
                "file_path": file_path,
                "chunk_id": i,
                "total_chunks": len(chunks),
                "uploaded_at": datetime.now().isoformat()
            })
        
        # ChromaDB에 추가
        _collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas
        )
        
        logger.info(f"✅ 문서 추가 완료: {file_name} ({len(chunks)}개 청크)")
        
        return {
            "status": "success",
            "file_name": file_name,
            "chunks_created": len(chunks)
        }
        
    except Exception as e:
        logger.error(f"❌ 문서 추가 실패: {e}")
        return {"status": "error", "message": str(e)}


def search_documents(
    query_embedding: List[float], 
    top_k: int = 5
) -> List[Dict[str, Any]]:
    """
    유사 문서 검색
    
    Args:
        query_embedding: 쿼리 임베딩 벡터
        top_k: 반환할 결과 수
        
    Returns:
        검색 결과 리스트
    """
    global _collection
    
    if _collection is None:
        return []
    
    try:
        if _collection.count() == 0:
            return []
        
        results = _collection.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k, _collection.count())
        )
        
        search_results = []
        if results['documents'] and results['documents'][0]:
            for i, doc in enumerate(results['documents'][0]):
                metadata = results['metadatas'][0][i] if results['metadatas'] else {}
                distance = results['distances'][0][i] if results['distances'] else 0
                
                # 거리를 유사도로 변환
                similarity = max(0, 1 - (distance / 2))
                
                search_results.append({
                    "content": doc,
                    "file_name": metadata.get("file_name", "Unknown"),
                    "similarity": round(similarity, 3),
                    "chunk_id": metadata.get("chunk_id", 0),
                    "metadata": metadata
                })
        
        return search_results
        
    except Exception as e:
        logger.error(f"❌ 검색 실패: {e}")
        return []


def list_documents() -> Dict[str, Any]:
    """업로드된 문서 목록 조회"""
    global _collection
    
    if _collection is None:
        return {"total_documents": 0, "total_chunks": 0, "documents": []}
    
    try:
        all_data = _collection.get()
        
        if not all_data['metadatas']:
            return {"total_documents": 0, "total_chunks": 0, "documents": []}
        
        # 파일별 그룹화
        file_stats = {}
        for metadata in all_data['metadatas']:
            file_name = metadata.get('file_name', 'Unknown')
            if file_name not in file_stats:
                file_stats[file_name] = {
                    "file_name": file_name,
                    "chunks": 0,
                    "uploaded_at": metadata.get('uploaded_at', 'Unknown')
                }
            file_stats[file_name]["chunks"] += 1
        
        return {
            "total_documents": len(file_stats),
            "total_chunks": len(all_data['metadatas']),
            "documents": list(file_stats.values())
        }
        
    except Exception as e:
        logger.error(f"❌ 문서 목록 조회 실패: {e}")
        return {"total_documents": 0, "total_chunks": 0, "documents": [], "error": str(e)}


def delete_document(file_name: str) -> Dict[str, Any]:
    """특정 문서 삭제"""
    global _collection
    
    if _collection is None:
        return {"status": "error", "message": "VectorDB가 초기화되지 않았습니다."}
    
    try:
        all_data = _collection.get()
        ids_to_delete = []
        
        for i, metadata in enumerate(all_data['metadatas']):
            if metadata.get('file_name') == file_name:
                ids_to_delete.append(all_data['ids'][i])
        
        if not ids_to_delete:
            return {"status": "warning", "message": f"'{file_name}' 문서를 찾을 수 없습니다."}
        
        _collection.delete(ids=ids_to_delete)
        
        logger.info(f"✅ 문서 삭제 완료: {file_name} ({len(ids_to_delete)}개 청크)")
        
        return {
            "status": "success",
            "file_name": file_name,
            "chunks_deleted": len(ids_to_delete)
        }
        
    except Exception as e:
        logger.error(f"❌ 문서 삭제 실패: {e}")
        return {"status": "error", "message": str(e)}
