"""
SmartNote - 영상/오디오 검색 엔진 (리팩토링 버전)

두 가지 모드 제공:
1. 영상 검색 엔진: YouTube 링크 입력 → 다운로드 → STT → 회의록
2. 오디오 검색 엔진: 오디오 파일 업로드 → STT → 회의록

기능:
- YouTube 영상 다운로드 및 MP3 변환
- 오디오 파일 업로드 지원 (mp3, wav, m4a, flac, ogg)
- STT (Gemini)
- VectorStore 기반 회의록 저장 및 검색 (ChromaDB + OpenAI Embedding)
- 회의록 요약 및 AI 채팅 (RAG 기반)
- SQLite로 작업 이력 관리
"""

# =============================================================================
# Import: 표준 라이브러리
# =============================================================================
from flask import Flask
import os
import logging
import secrets
from dotenv import load_dotenv

# =============================================================================
# Import: 프로젝트 모듈
# =============================================================================
import config
from modules.vectorstore import initialize_collections

# =============================================================================
# 환경 설정
# =============================================================================
load_dotenv()

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')

# =============================================================================
# VectorStore 초기화 (먼저 실행)
# =============================================================================
initialize_collections()

# =============================================================================
# Routes Import
# =============================================================================
# legacy 모듈의 routes와 app을 import하여 재사용
# (legacy 폴더는 있지만, 모듈화된 코드를 사용)
from legacy import youtube_search_viewer as legacy_routes

# legacy 모듈에서 필요한 전역 변수 가져오기
from modules.vectorstore import (
    youtube_vectorstore,
    audio_vectorstore,
    summary_vectorstore,
    embeddings
)

# legacy 모듈의 vectorstore를 업데이트된 것으로 교체
legacy_routes.youtube_vectorstore = youtube_vectorstore
legacy_routes.audio_vectorstore = audio_vectorstore
legacy_routes.summary_vectorstore = summary_vectorstore
legacy_routes.embeddings = embeddings

# legacy 모듈의 app을 사용 (routes가 이미 등록되어 있음)
app = legacy_routes.app

# templates와 static 경로 설정
app.template_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
app.static_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')

logging.info("✅ Routes import 완료")

# =============================================================================
# 메인 실행
# =============================================================================
if __name__ == "__main__":
    print("=" * 60)
    print("🎬 SmartNote - 영상/오디오 검색 엔진 (리팩토링 버전)")
    print("=" * 60)
    print("URL: http://127.0.0.1:5000")
    print("=" * 60)
    print("모듈 구조:")
    print("  ✅ config.py - 설정")
    print("  ✅ modules/utils.py - 유틸리티")
    print("  ✅ modules/database.py - 데이터베이스 관리")
    print("  ✅ modules/sqlite_db.py - SQLite 관리")
    print("  ✅ modules/text_processing.py - 텍스트 처리 및 청킹")
    print("  ✅ modules/stt.py - Gemini STT")
    print("  ✅ modules/stt_prediction.py - STT 처리 시간 예측")
    print("  ✅ modules/youtube.py - YouTube 다운로드")
    print("  ✅ modules/vectorstore.py - VectorStore 관리")
    print("  ✅ modules/translation.py - 번역")
    print("=" * 60)
    print("주의: legacy 폴더는 하위 호환성을 위해 유지됩니다.")
    print("      모든 핵심 기능은 modules로 분리되었습니다.")
    print("=" * 60)

    app.run(host="127.0.0.1", port=5000, debug=True, threaded=True)
