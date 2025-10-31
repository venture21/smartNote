"""
SmartNote - 영상/오디오 검색 엔진 (모듈화 버전)

두 가지 모드 제공:
1. 영상 검색 엔진: YouTube 링크 입력 → 다운로드 → STT → 회의록
2. 오디오 검색 엔진: 오디오 파일 업로드 → STT → 회의록

기능:
- YouTube 영상 다운로드 및 MP3 변환
- 오디오 파일 업로드 지원 (mp3, wav, m4a, flac, ogg)
- STT (Gemini)
- VectorStore 기반 회의록 저장 및 검색 (ChromaDB + OpenAI Embedding)
- 회의록 요약 및 AI 채팅 (RAG 기반)
- CSV로 작업 이력 관리 (캐싱)
"""

# =============================================================================
# Import: 표준 라이브러리
# =============================================================================
from flask import Flask, render_template, request, jsonify, send_from_directory
import os
import pandas as pd
import json
import subprocess
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
import secrets
import logging
from datetime import datetime
import threading
import time

# =============================================================================
# Import: 외부 라이브러리
# =============================================================================
from google import genai
from google.genai import types
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings
from langchain_core.documents import Document
from langchain_community.vectorstores.utils import filter_complex_metadata

# =============================================================================
# Import: 프로젝트 모듈
# =============================================================================
import config
from modules.utils import (
    allowed_file,
    calculate_file_hash,
    get_audio_duration,
    update_progress,
    parse_mmss_to_seconds,
    progress_data,
)
from modules.database import (
    load_youtube_history,
    save_youtube_history,
    load_audio_history,
    save_audio_history,
)
from modules.text_processing import (
    merge_consecutive_speaker_segments,
    get_segment_from_csv,
    create_token_based_chunks,
    extract_citations,
    parse_summary_by_subtopics,
)
from modules.stt import get_gemini_client, recognize_with_gemini
from modules.youtube import download_youtube_audio_as_mp3

# =============================================================================
# Flask 앱 초기화 - legacy 파일에서 import
# =============================================================================
load_dotenv()

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')

# legacy 모듈을 먼저 import (Flask app이 여기서 생성됨)
from legacy import youtube_search_viewer as legacy_module

# legacy 모듈의 app 사용
app = legacy_module.app

# templates와 static 경로 설정
import os
app.template_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
app.static_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')

# =============================================================================
# 전역 변수
# =============================================================================
session_data = {}

# LangChain Embeddings 및 VectorStore
embeddings = None
youtube_vectorstore = None
audio_vectorstore = None
summary_vectorstore = None

# =============================================================================
# VectorStore 초기화
# =============================================================================
def initialize_collections():
    """LangChain VectorStore 초기화 (OpenAI Embeddings 사용)"""
    global embeddings, youtube_vectorstore, audio_vectorstore, summary_vectorstore

    try:
        # OpenAI Embeddings 초기화
        openai_api_key = os.environ.get("OPENAI_API_KEY")
        embeddings = OpenAIEmbeddings(
            model="text-embedding-3-small", openai_api_key=openai_api_key
        )
        logging.info("✅ OpenAI Embeddings 사용")

        # YouTube VectorStore
        youtube_vectorstore = Chroma(
            collection_name="youtube_transcripts",
            embedding_function=embeddings,
            persist_directory=config.CHROMA_DB_FOLDER,
        )

        # Audio VectorStore
        audio_vectorstore = Chroma(
            collection_name="audio_transcripts",
            embedding_function=embeddings,
            persist_directory=config.CHROMA_DB_FOLDER,
        )

        # Summary VectorStore
        summary_vectorstore = Chroma(
            collection_name="summaries",
            embedding_function=embeddings,
            persist_directory=config.CHROMA_DB_FOLDER,
        )

        logging.info("✅ LangChain VectorStore 초기화 완료")
        logging.info("   - YouTube VectorStore 초기화됨")
        logging.info("   - Audio VectorStore 초기화됨")
        logging.info("   - Summary VectorStore 초기화됨")
    except Exception as e:
        logging.error(f"❌ LangChain VectorStore 초기화 오류: {e}")
        import traceback
        traceback.print_exc()


# VectorStore 초기화 실행
initialize_collections()

# VectorStore를 legacy 모듈에 전달
legacy_module.youtube_vectorstore = youtube_vectorstore
legacy_module.audio_vectorstore = audio_vectorstore
legacy_module.summary_vectorstore = summary_vectorstore
legacy_module.embeddings = embeddings

# =============================================================================
# 메인 실행
# =============================================================================
if __name__ == "__main__":
    print("=" * 60)
    print("🎬 SmartNote - 영상/오디오 검색 엔진 (모듈화 버전)")
    print("=" * 60)
    print("URL: http://localhost:5000")
    print("=" * 60)
    print("모듈 구조:")
    print("  ✅ config.py - 설정")
    print("  ✅ modules/utils.py - 유틸리티")
    print("  ✅ modules/database.py - CSV 관리")
    print("  ✅ modules/text_processing.py - 텍스트 처리 및 청킹")
    print("  ✅ modules/stt.py - Gemini STT")
    print("  ✅ modules/youtube.py - YouTube 다운로드")
    print("=" * 60)

    app.run(host="127.0.0.1", port=5000, debug=True, threaded=True)
