"""
영상/오디오 검색 엔진

두 가지 모드 제공:
1. 영상 검색 엔진: YouTube 링크 입력 → 다운로드 → STT → 회의록
2. 오디오 검색 엔진: 오디오 파일 업로드 → STT → 회의록

기능:
- YouTube 영상 다운로드 및 MP3 변환
- 오디오 파일 업로드 지원 (mp3, wav, m4a, flac, ogg)
- STT (Gemini)
- VectorStore 기반 회의록 저장 및 검색 (ChromaDB + Gemini Embedding)
- 회의록 요약 및 AI 채팅 (RAG 기반)
- CSV로 작업 이력 관리 (캐싱)
"""

from flask import Flask, render_template, request, jsonify, send_from_directory
import os
import pandas as pd
import json
import subprocess
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from google import genai
from google.genai import types
import secrets
import yt_dlp
import logging
from datetime import datetime
import threading
import time
import hashlib
from mutagen import File as MutagenFile
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings
from langchain_core.documents import Document
from langchain_community.vectorstores.utils import filter_complex_metadata
from langchain_text_splitters import RecursiveCharacterTextSplitter

# 환경 변수 로드
load_dotenv()

# Flask 앱 생성 (main.py에서 재사용)
app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')

# 설정
MP4_FOLDER = "mp4"
MP3_FOLDER = "mp3"
CSV_FOLDER = "csv"
UPLOADS_FOLDER = "uploads"
CHROMA_DB_FOLDER = "chroma_db"
YOUTUBE_HISTORY_CSV = os.path.join(CSV_FOLDER, "youtube_history.csv")
AUDIO_HISTORY_CSV = os.path.join(CSV_FOLDER, "audio_history.csv")
STT_PROCESSING_LOG = os.path.join(CSV_FOLDER, "stt_processing_log.json")

app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500MB max

# 허용된 오디오 파일 확장자
ALLOWED_AUDIO_EXTENSIONS = {
    "mp3",
    "wav",
    "m4a",
    "flac",
    "ogg",
    "mp4",
    "avi",
    "mov",
    "mkv",
}

# 폴더 생성
for folder in [MP4_FOLDER, MP3_FOLDER, CSV_FOLDER, UPLOADS_FOLDER, CHROMA_DB_FOLDER]:
    os.makedirs(folder, exist_ok=True)

# 세션별 데이터 저장
session_data = {}

# 진행 상황 저장
progress_data = {}

# LangChain Embeddings 초기화
embeddings = None

# LangChain VectorStore (YouTube, Audio, Summary 분리)
youtube_vectorstore = None
audio_vectorstore = None
summary_vectorstore = None


def allowed_file(filename):
    """허용된 파일 확장자인지 확인"""
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_AUDIO_EXTENSIONS
    )


def calculate_file_hash(file_path):
    """파일의 MD5 해시를 계산하여 고유 ID 생성"""
    hasher = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def get_audio_duration(file_path):
    """오디오 파일의 길이를 초 단위로 반환"""
    try:
        audio = MutagenFile(file_path)
        if audio is not None and hasattr(audio.info, "length"):
            duration = audio.info.length
            logging.info(f"🎵 오디오 파일 길이: {duration:.2f}초 ({duration/60:.2f}분)")
            return duration
        else:
            logging.warning(f"⚠️ 오디오 길이를 읽을 수 없습니다: {file_path}")
            return 0.0
    except Exception as e:
        logging.error(f"❌ 오디오 길이 추출 오류: {e}")
        return 0.0


def update_progress(task_id, step, progress, message, estimated_time=None, elapsed_time=None):
    """
    진행 상황 업데이트 (시간 정보 포함)

    Args:
        task_id: 작업 ID
        step: 단계 (예: 'stt', 'download', 'vectorstore')
        progress: 진행률 (0-100)
        message: 메시지
        estimated_time: 예상 소요 시간 (초)
        elapsed_time: 실제 경과 시간 (초)
    """
    if task_id not in progress_data:
        progress_data[task_id] = {}

    progress_data[task_id][step] = {
        "progress": progress,
        "message": message,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    # 시간 정보 추가
    if estimated_time is not None:
        progress_data[task_id][step]["estimated_time"] = estimated_time

    if elapsed_time is not None:
        progress_data[task_id][step]["elapsed_time"] = elapsed_time

        # 남은 예상 시간 계산
        if estimated_time is not None:
            remaining_time = max(0, estimated_time - elapsed_time)
            progress_data[task_id][step]["remaining_time"] = remaining_time

    # 로깅 (시간 정보 포함)
    log_msg = f"[{task_id}] {step}: {progress}% - {message}"
    if estimated_time is not None and elapsed_time is not None:
        remaining = max(0, estimated_time - elapsed_time)
        log_msg += f" (예상: {estimated_time:.1f}초, 경과: {elapsed_time:.1f}초, 남음: {remaining:.1f}초)"
    logging.info(log_msg)


# YouTube 이력 로드
def load_youtube_history():
    """SQLite에서 YouTube 다운로드 이력을 로드합니다 (modules/database.py 사용)"""
    from modules.database import load_youtube_history as db_load_youtube
    return db_load_youtube()


def save_youtube_history(df):
    """YouTube 이력을 SQLite에 저장합니다 (modules/database.py 사용)"""
    from modules.database import save_youtube_history as db_save_youtube
    db_save_youtube(df)


# 오디오 이력 로드
def load_audio_history():
    """SQLite에서 오디오 파일 처리 이력을 로드합니다 (modules/database.py 사용)"""
    from modules.database import load_audio_history as db_load_audio
    return db_load_audio()


def save_audio_history(df):
    """오디오 이력을 SQLite에 저장합니다 (modules/database.py 사용)"""
    from modules.database import save_audio_history as db_save_audio
    db_save_audio(df)


def load_stt_processing_log():
    """STT 처리 시간 로그를 로드합니다."""
    if os.path.exists(STT_PROCESSING_LOG):
        try:
            with open(STT_PROCESSING_LOG, 'r', encoding='utf-8') as f:
                logs = json.load(f)
            return logs
        except Exception as e:
            logging.error(f"STT 로그 로드 오류: {e}")
            return []
    else:
        return []


def save_stt_processing_log(logs):
    """STT 처리 시간 로그를 저장합니다."""
    try:
        with open(STT_PROCESSING_LOG, 'w', encoding='utf-8') as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error(f"STT 로그 저장 오류: {e}")


def add_stt_processing_record(audio_duration, processing_time, source_type="audio"):
    """
    STT 처리 기록을 로그에 추가합니다.

    Args:
        audio_duration: 오디오 길이 (초)
        processing_time: 실제 처리 시간 (초)
        source_type: 소스 타입 ("audio" 또는 "youtube")
    """
    logs = load_stt_processing_log()

    # 처리 비율 계산
    ratio = processing_time / audio_duration if audio_duration > 0 else 0

    # 새 기록 추가 (더 많은 메타데이터)
    logs.append({
        "audio_duration": float(audio_duration),
        "processing_time": float(processing_time),
        "ratio": float(ratio),
        "source_type": source_type,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })

    # 최근 200개만 유지 (더 많은 데이터로 정확도 향상)
    if len(logs) > 200:
        logs = logs[-200:]

    save_stt_processing_log(logs)
    logging.info(f"📊 STT 처리 기록 추가: {audio_duration:.2f}초 → {processing_time:.2f}초 (비율: {ratio:.3f})")


def estimate_stt_processing_time(audio_duration):
    """
    과거 로그를 기반으로 STT 처리 시간을 정확히 예측합니다.

    개선 사항:
    - 가중 평균: 최근 데이터에 더 높은 가중치 부여
    - 이상치 제거: 표준편차 기반 필터링
    - 구간별 분석: 오디오 길이별로 다른 비율 적용

    Args:
        audio_duration: 오디오 길이 (초)

    Returns:
        예상 처리 시간 (초)
    """
    logs = load_stt_processing_log()

    if not logs:
        # 로그가 없으면 기본값: 오디오 길이의 20% (경험적 추정)
        estimated = audio_duration * 0.2
        logging.info(f"⏱️ STT 예상 시간 (기본값): {estimated:.2f}초")
        return estimated

    # 1. 오디오 길이별 구간 분류
    # - 짧은 오디오: 0~300초 (5분)
    # - 중간 오디오: 300~900초 (5~15분)
    # - 긴 오디오: 900초 이상 (15분 이상)
    if audio_duration < 300:
        duration_range = "short"
        target_logs = [log for log in logs if log.get("audio_duration", 0) < 300]
    elif audio_duration < 900:
        duration_range = "medium"
        target_logs = [log for log in logs if 300 <= log.get("audio_duration", 0) < 900]
    else:
        duration_range = "long"
        target_logs = [log for log in logs if log.get("audio_duration", 0) >= 900]

    # 구간별 데이터가 부족하면 전체 데이터 사용
    if len(target_logs) < 5:
        target_logs = logs
        logging.info(f"⏱️ 구간별 데이터 부족, 전체 로그 사용 ({len(logs)}개)")

    # 2. 최근 데이터만 선택 (최대 50개)
    recent_logs = target_logs[-50:]

    # 3. 비율 추출 및 이상치 제거
    ratios = []
    for log in recent_logs:
        audio_dur = log.get("audio_duration", 0)
        proc_time = log.get("processing_time", 0)

        if audio_dur > 0:
            # 기존 ratio 필드가 있으면 사용, 없으면 계산
            ratio = log.get("ratio", proc_time / audio_dur)
            ratios.append(ratio)

    if not ratios:
        # 비율 계산 실패 시 기본값
        estimated = audio_duration * 0.2
        logging.info(f"⏱️ STT 예상 시간 (기본값): {estimated:.2f}초")
        return estimated

    # 4. 이상치(outlier) 제거 (표준편차 기반)
    import statistics

    if len(ratios) >= 3:
        mean_ratio = statistics.mean(ratios)
        stdev_ratio = statistics.stdev(ratios)

        # 평균 ± 2 표준편차 범위 내의 값만 사용
        filtered_ratios = [
            r for r in ratios
            if abs(r - mean_ratio) <= 2 * stdev_ratio
        ]

        if filtered_ratios:
            ratios = filtered_ratios
            logging.info(f"📊 이상치 제거: {len(recent_logs)}개 → {len(ratios)}개")

    # 5. 가중 평균 계산 (최근 데이터에 더 높은 가중치)
    weights = []
    weighted_sum = 0
    weight_total = 0

    for i, ratio in enumerate(ratios):
        # 지수 가중치: 최근 데이터일수록 높은 가중치 (1.0 ~ 2.0)
        weight = 1.0 + (i / len(ratios))  # 첫 번째: 1.0, 마지막: 2.0
        weighted_sum += ratio * weight
        weight_total += weight
        weights.append(weight)

    weighted_avg_ratio = weighted_sum / weight_total if weight_total > 0 else 0.2

    # 6. 예상 시간 계산
    estimated = audio_duration * weighted_avg_ratio

    # 7. 예측 신뢰도 계산
    if len(ratios) >= 3:
        stdev = statistics.stdev(ratios)
        confidence = max(0, 100 - (stdev * 100))  # 표준편차가 낮을수록 신뢰도 높음
    else:
        confidence = 50  # 데이터 부족 시 중간 신뢰도

    logging.info(
        f"⏱️ STT 예상 시간: {estimated:.2f}초 "
        f"(구간: {duration_range}, 샘플: {len(ratios)}개, "
        f"가중평균 비율: {weighted_avg_ratio:.3f}, 신뢰도: {confidence:.0f}%)"
    )

    return estimated


def analyze_stt_prediction_accuracy():
    """
    STT 예측 정확도를 분석합니다.

    Returns:
        dict: 통계 정보 (평균 오차율, 표준편차 등)
    """
    logs = load_stt_processing_log()

    if len(logs) < 5:
        return {
            "total_records": len(logs),
            "message": "데이터가 부족합니다 (최소 5개 필요)"
        }

    import statistics

    # 각 구간별 통계
    stats_by_range = {
        "short": {"ratios": [], "errors": []},   # 0~5분
        "medium": {"ratios": [], "errors": []},  # 5~15분
        "long": {"ratios": [], "errors": []}     # 15분 이상
    }

    all_ratios = []

    for log in logs:
        audio_dur = log.get("audio_duration", 0)
        proc_time = log.get("processing_time", 0)

        if audio_dur > 0:
            ratio = log.get("ratio", proc_time / audio_dur)
            all_ratios.append(ratio)

            # 구간 분류
            if audio_dur < 300:
                duration_range = "short"
            elif audio_dur < 900:
                duration_range = "medium"
            else:
                duration_range = "long"

            stats_by_range[duration_range]["ratios"].append(ratio)

    # 전체 통계
    if all_ratios:
        mean_ratio = statistics.mean(all_ratios)
        median_ratio = statistics.median(all_ratios)
        stdev_ratio = statistics.stdev(all_ratios) if len(all_ratios) >= 2 else 0

        result = {
            "total_records": len(logs),
            "overall": {
                "mean_ratio": round(mean_ratio, 4),
                "median_ratio": round(median_ratio, 4),
                "stdev_ratio": round(stdev_ratio, 4),
                "min_ratio": round(min(all_ratios), 4),
                "max_ratio": round(max(all_ratios), 4),
            },
            "by_duration": {}
        }

        # 구간별 통계
        for duration_range, data in stats_by_range.items():
            ratios = data["ratios"]
            if len(ratios) >= 2:
                result["by_duration"][duration_range] = {
                    "count": len(ratios),
                    "mean_ratio": round(statistics.mean(ratios), 4),
                    "median_ratio": round(statistics.median(ratios), 4),
                    "stdev_ratio": round(statistics.stdev(ratios), 4),
                }
            elif len(ratios) == 1:
                result["by_duration"][duration_range] = {
                    "count": 1,
                    "mean_ratio": round(ratios[0], 4),
                    "median_ratio": round(ratios[0], 4),
                    "stdev_ratio": 0,
                }

        return result
    else:
        return {
            "total_records": len(logs),
            "message": "유효한 데이터가 없습니다"
        }


def get_gemini_client():
    """Gemini 클라이언트 생성"""
    api_key = os.environ.get("GOOGLE_API_KEY")
    if api_key:
        return genai.Client(api_key=api_key)
    else:
        return genai.Client()


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
            persist_directory=CHROMA_DB_FOLDER,
        )

        # Audio VectorStore
        audio_vectorstore = Chroma(
            collection_name="audio_transcripts",
            embedding_function=embeddings,
            persist_directory=CHROMA_DB_FOLDER,
        )

        # Summary VectorStore (별도 저장소)
        summary_vectorstore = Chroma(
            collection_name="summaries",
            embedding_function=embeddings,
            persist_directory=CHROMA_DB_FOLDER,
        )

        logging.info(f"✅ LangChain VectorStore 초기화 완료")
        logging.info(f"   - YouTube VectorStore 초기화됨")
        logging.info(f"   - Audio VectorStore 초기화됨")
        logging.info(f"   - Summary VectorStore 초기화됨")
    except Exception as e:
        logging.error(f"❌ LangChain VectorStore 초기화 오류: {e}")
        import traceback

        traceback.print_exc()


def store_segments_in_vectordb(
    segments, source_id, source_type="youtube", filename=None, title=None, use_chunking=True, chunk_size=500, chunk_overlap=100
):
    """
    세그먼트를 VectorDB에 저장 (LangChain 방식)

    Args:
        segments: STT로 추출된 세그먼트 리스트
        source_id: YouTube video_id 또는 audio file_hash
        source_type: "youtube" 또는 "audio"
        filename: 오디오 파일명 (오디오일 경우)
        title: 제목 (사용자 입력 또는 자동 추출)
        use_chunking: True이면 토큰 기반 청킹 사용, False이면 원본 세그먼트 저장 (기본값: True)
        chunk_size: 청킹 시 chunk당 최대 문자 수 (기본값: 500)
        chunk_overlap: 청킹 시 chunk 간 중복 문자 수 (기본값: 100)
    """
    try:
        vectorstore = (
            youtube_vectorstore if source_type == "youtube" else audio_vectorstore
        )

        if not vectorstore:
            logging.error("❌ LangChain VectorStore가 초기화되지 않았습니다.")
            return False

        # 기존 데이터 삭제 (같은 source_id)
        try:
            # LangChain Chroma에서 기존 데이터 삭제
            existing_docs = vectorstore.get(where={"source_id": source_id})
            if existing_docs and existing_docs["ids"]:
                vectorstore.delete(ids=existing_docs["ids"])
                logging.info(
                    f"🗑️ 기존 데이터 삭제: {len(existing_docs['ids'])}개 문서"
                )
        except Exception as e:
            logging.warning(f"기존 데이터 삭제 중 오류 (무시): {e}")

        # 청킹 여부에 따라 처리
        if use_chunking:
            logging.info(f"📦 토큰 기반 청킹 시작 (chunk_size={chunk_size}, overlap={chunk_overlap})...")
            chunks = create_token_based_chunks(segments, chunk_size=chunk_size, chunk_overlap=chunk_overlap)

            if not chunks:
                logging.warning("⚠️ 청킹 결과가 비어있음, 원본 세그먼트로 저장합니다.")
                use_chunking = False  # 폴백: 원본 세그먼트 저장
            else:
                # LangChain Document 객체 생성 (청크 기반)
                documents = []
                doc_ids = []

                for chunk in chunks:
                    # Document (content)
                    text = chunk["text"]

                    # Metadata
                    metadata = {
                        "source_id": source_id,
                        "source_type": source_type,
                        "document_type": "chunk",  # 청크임을 표시
                        "chunk_id": int(chunk["chunk_id"]),
                        "segment_ids": chunk["segment_ids"],  # 원본 세그먼트 ID 리스트 (복잡한 메타데이터)
                        "speakers": chunk["speakers"],  # 화자 리스트 (복잡한 메타데이터)
                        "start_time": float(chunk["start_time"]),
                        "end_time": float(chunk["end_time"]) if chunk["end_time"] is not None else None,
                        "confidence": float(chunk["confidence"]),
                    }

                    # 제목 추가
                    if title:
                        metadata["title"] = title

                    if source_type == "audio" and filename:
                        metadata["filename"] = filename

                    # ID: source_id + chunk_id
                    doc_id = f"{source_id}_chunk_{chunk['chunk_id']}"
                    doc_ids.append(doc_id)

                    # LangChain Document 생성
                    doc = Document(page_content=text, metadata=metadata)
                    documents.append(doc)

                # 복잡한 메타데이터 필터링 (segment_ids, speakers는 리스트)
                logging.info(f"🔧 복잡한 메타데이터 필터링 중... (Document 수: {len(documents)})")
                filtered_documents = filter_complex_metadata(documents)

                # LangChain VectorStore에 저장 (자동으로 임베딩 생성됨)
                vectorstore.add_documents(
                    documents=filtered_documents,
                    ids=doc_ids,
                )

                logging.info(
                    f"✅ VectorDB 저장 완료: {len(chunks)}개 청크 (원본 {len(segments)}개 세그먼트, source: {source_id})"
                )
                return True

        # 청킹 미사용 또는 폴백: 원본 세그먼트 저장
        if not use_chunking:
            documents = []

            for idx, segment in enumerate(segments):
                # Document (content)
                text = segment["text"]

                # end_time 계산 (다음 세그먼트의 start_time 또는 None)
                if idx < len(segments) - 1:
                    end_time = float(segments[idx + 1]["start_time"])
                else:
                    # 마지막 세그먼트는 end_time이 없음 (None)
                    end_time = None

                # Metadata
                metadata = {
                    "source_id": source_id,
                    "source_type": source_type,
                    "document_type": "segment",  # 명시적으로 세그먼트임을 표시
                    "speaker": str(segment["speaker"]),
                    "start_time": float(segment["start_time"]),
                    "end_time": end_time,
                    "confidence": float(segment.get("confidence", 0.0)),
                    "segment_id": int(segment["id"]),
                }

                # 제목 추가
                if title:
                    metadata["title"] = title

                if source_type == "audio" and filename:
                    metadata["filename"] = filename

                # ID: source_id + segment_id
                doc_id = f"{source_id}_seg_{segment['id']}"

                # LangChain Document 생성
                doc = Document(page_content=text, metadata=metadata)
                documents.append(doc)

            # LangChain VectorStore에 저장 (자동으로 임베딩 생성됨)
            vectorstore.add_documents(
                documents=documents,
                ids=[f"{source_id}_seg_{seg['id']}" for seg in segments],
            )

            logging.info(
                f"✅ VectorDB 저장 완료: {len(segments)}개 세그먼트 (source: {source_id})"
            )
            return True

    except Exception as e:
        logging.error(f"❌ VectorDB 저장 오류: {e}")
        import traceback

        traceback.print_exc()
        return False


def store_summary_in_vectordb(summary, source_id, source_type="youtube", filename=None):
    """
    요약을 소주제별로 분할하여 Summary VectorDB에 저장

    Args:
        summary: 생성된 요약 텍스트 (마크다운 형식)
        source_id: YouTube video_id 또는 audio file_hash
        source_type: "youtube" 또는 "audio"
        filename: 오디오 파일명 (오디오일 경우)
    """
    try:
        # 디버깅: 입력 파라미터 확인
        logging.info(f"📥 store_summary_in_vectordb 호출됨 - source_id: {source_id}, source_type: {source_type}")
        logging.debug(f"요약 타입: {type(summary)}, 길이: {len(summary) if summary else 0}")
        logging.debug(f"요약 미리보기: {summary[:200] if summary else 'None'}...")

        if not summary_vectorstore:
            logging.error("❌ Summary VectorStore가 초기화되지 않았습니다.")
            return False

        # 기존 요약 데이터 삭제 (같은 source_id의 summary)
        try:
            existing_docs = summary_vectorstore.get(where={"source_id": source_id})
            if existing_docs and existing_docs["ids"]:
                summary_vectorstore.delete(ids=existing_docs["ids"])
                logging.info(f"🗑️ 기존 요약 삭제: {len(existing_docs['ids'])}개")
        except Exception as e:
            logging.warning(f"기존 요약 삭제 중 오류 (무시): {e}")

        # 요약을 소주제별로 분할
        logging.info("🔍 소주제 파싱 시작...")
        subtopics = parse_summary_by_subtopics(summary)
        logging.info(f"🔍 소주제 파싱 결과: {len(subtopics) if subtopics else 0}개")

        if not subtopics:
            # 파싱 실패 시 전체를 하나의 문서로 저장 (fallback)
            logging.warning("⚠️ 소주제 파싱 실패, 전체 요약을 하나의 문서로 저장합니다.")
            metadata = {
                "source_id": source_id,
                "source_type": source_type,
                "document_type": "summary",
                "subtopic": "전체",
                "subtopic_index": 0,
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            if source_type == "audio" and filename:
                metadata["filename"] = filename

            doc = Document(page_content=summary, metadata=metadata)
            doc_id = f"{source_id}_summary_0"

            # 복잡한 메타데이터 필터링 (일관성을 위해)
            filtered_docs = filter_complex_metadata([doc])
            summary_vectorstore.add_documents(documents=filtered_docs, ids=[doc_id])
            logging.info(
                f"✅ 요약 Summary VectorDB 저장 완료 (전체, source: {source_id})"
            )
            return True

        # 각 소주제를 별도의 Document로 저장
        documents = []
        doc_ids = []

        for idx, subtopic in enumerate(subtopics):
            # cited_chunk_ids 추출
            cited_chunk_ids = subtopic.get("cited_chunk_ids", [])

            metadata = {
                "source_id": source_id,
                "source_type": source_type,
                "document_type": "summary",
                "subtopic": subtopic["title"],
                "subtopic_index": idx,
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "cited_chunk_ids": cited_chunk_ids,  # citation 정보 저장 (청크 번호)
            }

            if source_type == "audio" and filename:
                metadata["filename"] = filename

            # 소주제 제목 + 내용을 함께 저장 (검색 시 컨텍스트 유지)
            content = f"**{subtopic['title']}**\n\n{subtopic['content']}"
            doc = Document(page_content=content, metadata=metadata)
            documents.append(doc)

            doc_id = f"{source_id}_summary_{idx}"
            doc_ids.append(doc_id)

            logging.debug(f"📌 소주제 '{subtopic['title']}' - cited_chunk_ids: {cited_chunk_ids}")

        # 복잡한 메타데이터 필터링 (리스트, 딕셔너리 등을 문자열로 변환)
        logging.info(f"🔧 복잡한 메타데이터 필터링 중... (Document 수: {len(documents)})")
        filtered_documents = filter_complex_metadata(documents)
        logging.info(f"✅ 메타데이터 필터링 완료")

        # Summary VectorStore에 일괄 저장
        summary_vectorstore.add_documents(documents=filtered_documents, ids=doc_ids)

        logging.info(
            f"✅ 요약 Summary VectorDB 저장 완료 ({len(subtopics)}개 소주제, source: {source_id})"
        )
        return True

    except Exception as e:
        logging.error(f"❌ 요약 VectorDB 저장 오류: {e}")
        import traceback

        traceback.print_exc()
        return False


def parse_summary_by_subtopics(summary):
    """
    마크다운 형식의 요약을 소주제별로 파싱하고 citation 정보 추출

    다양한 형식을 지원:
    1. ### 제목 (마크다운 헤딩)
    2. **제목** (볼드)
    3. 빈 줄로 둘러싸인 짧은 텍스트 (일반 텍스트 제목)

    Args:
        summary: 마크다운 형식의 요약 텍스트

    Returns:
        list: [{"title": "소주제 제목", "content": "소주제 내용", "cited_segment_ids": [1, 2, 3]}, ...]
    """
    import re

    if not summary or not summary.strip():
        logging.warning("⚠️ 요약 내용이 비어있습니다.")
        return []

    lines = summary.split("\n")
    subtopics = []
    current_title = None
    current_content = []

    logging.info(f"📝 요약 파싱 시작 (총 {len(lines)}줄)")

    for idx, line in enumerate(lines):
        stripped = line.strip()

        # 다양한 헤더 형식 지원
        # 1. **제목** 패턴 (마크다운 볼드)
        bold_match = re.match(r"^\*\*(.+?)\*\*\s*$", stripped)
        # 2. ### 제목 패턴 (마크다운 헤딩 3)
        h3_match = re.match(r"^###[\s]+(.+?)[\s]*$", stripped)
        # 3. ## 제목 패턴 (마크다운 헤딩 2)
        h2_match = re.match(r"^##[\s]+(.+?)[\s]*$", stripped)
        # 4. # 제목 패턴 (마크다운 헤딩 1)
        h1_match = re.match(r"^#[\s]+(.+?)[\s]*$", stripped) if len(subtopics) > 0 else None

        # 5. 일반 텍스트 제목 감지 (휴리스틱)
        # - 빈 줄로 둘러싸여 있음
        # - 짧은 텍스트 (100자 이하)
        # - 글머리 기호나 [cite:로 시작하지 않음
        # - 문장 부호로 끝나지 않음 (또는 물음표로만 끝남)
        is_potential_title = False
        if stripped and len(stripped) < 100 and not stripped.startswith('*') and not stripped.startswith('[cite'):
            # 이전 줄과 다음 줄이 비어있는지 확인
            prev_line_empty = (idx == 0) or (idx > 0 and not lines[idx-1].strip())
            next_line_empty = (idx == len(lines)-1) or (idx < len(lines)-1 and not lines[idx+1].strip())

            # 문장 부호 체크 (마침표, 쉼표, [cite: 등으로 끝나지 않음)
            ends_with_punct = stripped.endswith(('.', ',', '!', ':', ';')) or '[cite:' in stripped[-20:]

            if prev_line_empty and next_line_empty and not ends_with_punct:
                is_potential_title = True
                logging.debug(f"🔍 일반 텍스트 제목 후보 (줄 {idx+1}): '{stripped}'")

        # 헤더 매칭 우선순위: h3 > h2 > bold > h1 > 일반 텍스트
        title_match = h3_match or h2_match or bold_match or h1_match

        if title_match or is_potential_title:
            # 이전 소주제 저장
            if current_title is not None:
                content_str = "\n".join(current_content).strip()
                if content_str:  # 내용이 있을 때만 저장
                    # Citation 추출 ([cite: 0, 1, 2] 형식 - 청크 번호)
                    cited_chunk_ids = extract_citations(content_str)

                    subtopics.append(
                        {
                            "title": current_title,
                            "content": content_str,
                            "cited_chunk_ids": cited_chunk_ids,
                        }
                    )
                    logging.debug(
                        f"✅ 소주제 저장: '{current_title}' (내용 길이: {len(content_str)}, citations: {cited_chunk_ids})"
                    )
                else:
                    logging.warning(f"⚠️ 소주제 '{current_title}'에 내용이 없어 제외됨")

            # 새 소주제 시작
            if title_match:
                current_title = title_match.group(1).strip()
            else:
                current_title = stripped
            current_content = []
            logging.debug(f"📌 새 소주제 발견 (줄 {idx+1}): '{current_title}'")

        elif current_title is not None and stripped:
            # 현재 소주제의 내용 추가 (빈 줄이 아닌 경우만)
            current_content.append(line)

    # 마지막 소주제 저장
    if current_title is not None:
        content_str = "\n".join(current_content).strip()
        if content_str:
            cited_chunk_ids = extract_citations(content_str)
            subtopics.append({
                "title": current_title,
                "content": content_str,
                "cited_chunk_ids": cited_chunk_ids,
            })
            logging.debug(
                f"✅ 마지막 소주제 저장: '{current_title}' (내용 길이: {len(content_str)}, citations: {cited_chunk_ids})"
            )
        else:
            logging.warning(f"⚠️ 마지막 소주제 '{current_title}'에 내용이 없어 제외됨")

    logging.info(f"✅ 파싱 완료: {len(subtopics)}개의 소주제 발견")

    if len(subtopics) == 0:
        logging.warning(
            f"⚠️ 소주제를 찾을 수 없습니다. 요약 내용 미리보기:\n{summary[:500]}"
        )

    return subtopics


def extract_citations(text):
    """
    텍스트에서 [cite: X, Y, Z] 형식의 citation을 추출하여 chunk_id 리스트 반환

    Args:
        text: citation이 포함된 텍스트

    Returns:
        list: 추출된 chunk_id 리스트 (정수)
    """
    import re

    # [cite: 0, 1, 2] 또는 [cite: 0] 형식의 citation 찾기 (청크 번호)
    citations = re.findall(r'\[cite:\s*(\d+(?:\s*,\s*\d+)*)\]', text)

    chunk_ids = []
    for citation in citations:
        # 쉼표로 구분된 chunk_id들을 추출
        ids = [int(cid.strip()) for cid in citation.split(',')]
        chunk_ids.extend(ids)

    # 중복 제거 및 정렬
    chunk_ids = sorted(list(set(chunk_ids)))

    return chunk_ids


def get_summary_from_vectordb(source_id, source_type="youtube"):
    """
    별도의 Summary VectorDB에서 저장된 요약 가져오기 (모든 소주제 포함)

    Args:
        source_id: YouTube video_id 또는 audio file_hash
        source_type: "youtube" 또는 "audio"

    Returns:
        요약 텍스트 (모든 소주제 합쳐진 것) 또는 None (없으면)
    """
    try:
        if not summary_vectorstore:
            logging.error("❌ Summary VectorStore가 초기화되지 않았습니다.")
            return None

        # 요약 문서 검색 (source_id 일치)
        results = summary_vectorstore.get(where={"source_id": source_id})

        if results and results["documents"] and len(results["documents"]) > 0:
            # 모든 소주제를 순서대로 정렬하여 합치기
            documents = results["documents"]
            metadatas = results["metadatas"]

            # subtopic_index로 정렬 (저장 순서 유지)
            sorted_chunks = []
            for doc, meta in zip(documents, metadatas):
                subtopic_index = meta.get("subtopic_index", 0)
                sorted_chunks.append((subtopic_index, doc))

            sorted_chunks.sort(key=lambda x: x[0])

            # 모든 소주제를 합쳐서 반환
            summary = "\n\n".join([doc for _, doc in sorted_chunks])

            logging.info(
                f"✅ Summary VectorDB에서 요약 로드 완료 (source: {source_id}, {len(documents)}개 소주제)"
            )
            return summary
        else:
            logging.info(
                f"ℹ️ Summary VectorDB에 저장된 요약이 없습니다 (source: {source_id})"
            )
            return None

    except Exception as e:
        logging.error(f"❌ Summary VectorDB 요약 로드 오류: {e}")
        import traceback

        traceback.print_exc()
        return None


def delete_from_vectorstore(source_id, source_type="youtube"):
    """
    VectorStore에서 특정 source_id의 모든 데이터 삭제 (세그먼트 + 요약)

    Args:
        source_id: YouTube video_id 또는 audio file_hash
        source_type: "youtube" 또는 "audio"

    Returns:
        (성공 여부, 삭제된 문서 수)
    """
    try:
        total_deleted = 0

        # 1. 세그먼트 삭제 (youtube_vectorstore 또는 audio_vectorstore)
        vectorstore = youtube_vectorstore if source_type == "youtube" else audio_vectorstore

        if vectorstore:
            try:
                existing_docs = vectorstore.get(where={"source_id": source_id})
                if existing_docs and existing_docs["ids"]:
                    vectorstore.delete(ids=existing_docs["ids"])
                    deleted_count = len(existing_docs["ids"])
                    total_deleted += deleted_count
                    logging.info(f"🗑️ {source_type} VectorStore에서 {deleted_count}개 세그먼트 삭제")
            except Exception as e:
                logging.warning(f"⚠️ {source_type} VectorStore 삭제 중 오류: {e}")

        # 2. 요약 삭제 (summary_vectorstore)
        if summary_vectorstore:
            try:
                existing_summary = summary_vectorstore.get(where={"source_id": source_id})
                if existing_summary and existing_summary["ids"]:
                    summary_vectorstore.delete(ids=existing_summary["ids"])
                    summary_count = len(existing_summary["ids"])
                    total_deleted += summary_count
                    logging.info(f"🗑️ Summary VectorStore에서 {summary_count}개 요약 삭제")
            except Exception as e:
                logging.warning(f"⚠️ Summary VectorStore 삭제 중 오류: {e}")

        logging.info(f"✅ VectorStore 삭제 완료: 총 {total_deleted}개 문서 삭제됨")
        return True, total_deleted

    except Exception as e:
        logging.error(f"❌ VectorStore 삭제 오류: {e}")
        import traceback
        traceback.print_exc()
        return False, 0


def search_vectordb(query, source_id=None, source_type=None, n_results=5, document_type=None):
    """
    VectorDB에서 검색 (LangChain Retriever 사용)

    Args:
        query: 검색 쿼리
        source_id: 특정 source로 제한 (선택)
        source_type: "youtube", "audio", "summary" 또는 None (선택)
        n_results: 반환할 결과 수
        document_type: "chunk", "segment" 또는 None (선택, chunk만 검색하려면 "chunk" 지정)

    Returns:
        검색 결과 리스트
    """
    try:
        # 검색할 VectorStore 결정
        vectorstores_to_search = []
        if source_type == "youtube":
            vectorstores_to_search = [youtube_vectorstore]
            logging.info(f"🔍 검색 대상: YouTube VectorStore만")
        elif source_type == "audio":
            vectorstores_to_search = [audio_vectorstore]
            logging.info(f"🔍 검색 대상: Audio VectorStore만")
        elif source_type == "summary":
            vectorstores_to_search = [summary_vectorstore]
            logging.info(f"🔍 검색 대상: Summary VectorStore만")
        else:
            vectorstores_to_search = [youtube_vectorstore, audio_vectorstore]
            logging.info(f"🔍 검색 대상: YouTube + Audio VectorStore (전체 검색)")

        all_results = []

        for idx, vectorstore in enumerate(vectorstores_to_search):
            if not vectorstore:
                logging.warning(f"⚠️ VectorStore #{idx}가 초기화되지 않았습니다.")
                continue

            # VectorStore에 저장된 문서 수 확인
            try:
                collection = vectorstore._collection
                total_docs = collection.count()
                logging.info(f"📊 VectorStore #{idx} 문서 수: {total_docs}개")
            except Exception as e:
                logging.warning(f"⚠️ VectorStore #{idx} 문서 수 확인 실패: {e}")

            # where 필터 구성
            search_kwargs = {"k": n_results}
            filter_dict = {}

            if source_id:
                filter_dict["source_id"] = source_id

            if document_type:
                filter_dict["document_type"] = document_type
                logging.info(f"📋 document_type 필터: {document_type}")

            if filter_dict:
                search_kwargs["filter"] = filter_dict

            # LangChain Retriever 생성 및 검색
            retriever = vectorstore.as_retriever(
                search_type="similarity", search_kwargs=search_kwargs
            )

            # 검색 수행 (similarity_search_with_score 사용)
            logging.info(f"🔎 검색 쿼리: '{query}', k={n_results}, 필터: {filter_dict if filter_dict else 'None'}")
            docs_with_scores = vectorstore.similarity_search_with_score(
                query=query, k=n_results, filter=search_kwargs.get("filter")
            )
            logging.info(
                f"✅ VectorStore #{idx}에서 {len(docs_with_scores)}개 결과 발견"
            )

            # 결과 파싱
            for doc, score in docs_with_scores:
                all_results.append(
                    {
                        "id": doc.metadata.get("segment_id", ""),
                        "document": doc.page_content,
                        "metadata": doc.metadata,
                        "distance": score,  # LangChain은 거리(낮을수록 유사)를 반환
                    }
                )

        # 거리 기준으로 정렬 (낮을수록 유사)
        all_results.sort(key=lambda x: x.get("distance", float("inf")))

        # 상위 n_results개만 반환
        return all_results[:n_results]

    except Exception as e:
        logging.error(f"❌ VectorDB 검색 오류: {e}")
        import traceback

        traceback.print_exc()
        return []


def download_youtube_audio_as_mp3(url, task_id=None):
    """
    YouTube에서 오디오만 다운로드하여 mp3로 변환합니다.

    Returns:
        dict: {
            'video_id': str,
            'title': str,
            'channel': str,
            'view_count': int,
            'upload_date': str,
            'mp3_path': str,
            'success': bool,
            'error': str (optional)
        }
    """
    try:
        if task_id:
            update_progress(task_id, "download", 0, "YouTube 오디오 다운로드 시작")

        logging.info(f"🎵 YouTube 오디오 다운로드 시작: {url}")

        # 진행률 콜백 함수
        def progress_hook(d):
            if task_id and d["status"] == "downloading":
                downloaded = d.get("downloaded_bytes", 0)
                total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)

                if total > 0:
                    percent = int((downloaded / total) * 100)
                    speed = d.get("speed", 0)
                    eta = d.get("eta", 0)

                    # 속도 포맷팅
                    if speed:
                        speed_mb = speed / (1024 * 1024)
                        speed_str = f"{speed_mb:.1f} MB/s"
                    else:
                        speed_str = "계산 중..."

                    # ETA 포맷팅
                    if eta:
                        eta_min = eta // 60
                        eta_sec = eta % 60
                        eta_str = f"{int(eta_min)}:{int(eta_sec):02d}"
                    else:
                        eta_str = "계산 중..."

                    message = (
                        f"오디오 다운로드 중... {speed_str} (남은 시간: {eta_str})"
                    )
                    update_progress(task_id, "download", percent, message)
            elif task_id and d["status"] == "finished":
                update_progress(
                    task_id, "download", 90, "오디오 다운로드 완료, MP3 변환 중..."
                )
            elif task_id and d["status"] == "processing":
                update_progress(task_id, "download", 95, "MP3 변환 중...")

        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": os.path.join(MP3_FOLDER, "%(title).50s-%(id)s.%(ext)s"),
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ],
            "progress_hooks": [progress_hook],
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            video_id = info_dict.get("id", None)
            video_title = info_dict.get("title", None)
            channel = info_dict.get("channel", info_dict.get("uploader", "Unknown"))
            view_count = info_dict.get("view_count", 0)
            upload_date = info_dict.get("upload_date", "")

            # upload_date 포맷 변환 (YYYYMMDD -> YYYY-MM-DD)
            if upload_date and len(upload_date) == 8:
                upload_date = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}"

            # MP3 파일 경로 생성 (yt-dlp가 생성한 파일명 기반)
            # prepare_filename은 원본 확장자를 반환하므로 .mp3로 교체
            original_path = ydl.prepare_filename(info_dict)
            mp3_path = os.path.splitext(original_path)[0] + ".mp3"

        if not os.path.exists(mp3_path):
            if task_id:
                update_progress(task_id, "download", 0, "MP3 파일을 찾을 수 없습니다")
            return {"success": False, "error": "MP3 파일을 찾을 수 없습니다."}

        logging.info(f"✅ YouTube 오디오 다운로드 완료: {mp3_path}")

        if task_id:
            update_progress(task_id, "download", 100, "YouTube 오디오 다운로드 완료")

        return {
            "success": True,
            "video_id": video_id,
            "title": video_title,
            "channel": channel,
            "view_count": view_count,
            "upload_date": upload_date,
            "mp3_path": mp3_path,
        }

    except Exception as e:
        logging.error(f"❌ YouTube 오디오 다운로드 오류: {e}")
        if task_id:
            update_progress(task_id, "download", 0, f"다운로드 오류: {str(e)}")
        return {"success": False, "error": str(e)}


def merge_consecutive_speaker_segments(segments):
    """연속적으로 동일한 화자의 세그먼트를 하나의 텍스트로 합칩니다."""
    if not segments:
        return []

    merged_segments = []
    current_segment = segments[0].copy()

    for next_segment in segments[1:]:
        if current_segment["speaker"] == next_segment["speaker"]:
            current_segment["text"] += " " + next_segment["text"]
        else:
            merged_segments.append(current_segment)
            current_segment = next_segment.copy()

    merged_segments.append(current_segment)
    return merged_segments


def get_segment_from_csv(source_id, source_type, segment_id):
    """
    CSV에서 특정 세그먼트를 segment_id로 조회

    Args:
        source_id: YouTube video_id 또는 audio file_hash
        source_type: "youtube" 또는 "audio"
        segment_id: 세그먼트 ID

    Returns:
        segment dict 또는 None
    """
    try:
        if source_type == "youtube":
            history_df = load_youtube_history()
            row = history_df[history_df["video_id"] == source_id]
        else:  # audio
            history_df = load_audio_history()
            row = history_df[history_df["file_hash"] == source_id]

        if row.empty:
            logging.warning(f"⚠️ CSV에서 source_id={source_id} 찾을 수 없음")
            return None

        # segments_json 파싱
        segments_json_str = row.iloc[0].get("segments_json", "[]")
        segments = json.loads(segments_json_str)

        # segment_id로 검색
        for seg in segments:
            if seg.get("id") == segment_id:
                return seg

        logging.warning(f"⚠️ CSV에서 segment_id={segment_id} 찾을 수 없음")
        return None

    except Exception as e:
        logging.error(f"❌ CSV에서 세그먼트 조회 실패 (source_id={source_id}, segment_id={segment_id}): {e}")
        return None


def create_token_based_chunks(segments, chunk_size=500, chunk_overlap=100):
    """
    토큰 기반 청킹: 화자 분리된 세그먼트를 고정 크기의 chunk로 재구성

    Args:
        segments: 세그먼트 리스트 [{"id": 1, "speaker": "1", "start_time": 0.0, "text": "...", "confidence": 0.95}, ...]
        chunk_size: chunk당 최대 문자 수 (토큰 근사치)
        chunk_overlap: chunk 간 중복 문자 수

    Returns:
        chunks: [{"chunk_id": 0, "text": "...", "segment_ids": [1, 2, 3], "start_time": 0.0, "end_time": 30.5, "speakers": ["1", "2"]}, ...]
    """
    try:
        if not segments:
            logging.warning("⚠️ create_token_based_chunks: 빈 세그먼트 리스트")
            return []

        # 세그먼트를 마커와 함께 텍스트로 결합
        full_text_with_markers = ""
        segment_map = {}  # 마커 위치 → 세그먼트 정보 매핑

        for seg in segments:
            marker = f"[SEG_{seg['id']}]"
            full_text_with_markers += marker + seg["text"] + " "
            segment_map[seg['id']] = seg

        # RecursiveCharacterTextSplitter로 청킹
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", ". ", "。 ", "! ", "? ", ", ", " ", ""],  # 한국어/영어 문장 구분자
            length_function=len,
        )

        chunks_text = splitter.split_text(full_text_with_markers)
        logging.info(f"📦 청킹 완료: {len(chunks_text)}개 chunk 생성 (chunk_size={chunk_size}, overlap={chunk_overlap})")

        # chunk에서 세그먼트 ID 추출 및 메타데이터 구성
        chunks = []
        import re

        for chunk_idx, chunk_text in enumerate(chunks_text):
            # [SEG_X] 마커에서 세그먼트 ID 추출
            seg_ids = [int(x) for x in re.findall(r'\[SEG_(\d+)\]', chunk_text)]

            if not seg_ids:
                # 마커가 없는 경우 (드물지만 처리)
                logging.warning(f"⚠️ Chunk {chunk_idx}: 세그먼트 ID 없음")
                continue

            # 마커 제거하여 순수 텍스트 추출
            clean_text = re.sub(r'\[SEG_\d+\]', '', chunk_text).strip()

            # 세그먼트 정보에서 메타데이터 추출
            cited_segments = [segment_map[sid] for sid in seg_ids if sid in segment_map]

            if not cited_segments:
                logging.warning(f"⚠️ Chunk {chunk_idx}: 유효한 세그먼트 없음")
                continue

            # 시작/종료 시간 계산
            start_time = min(seg["start_time"] for seg in cited_segments)

            # end_time 계산: 마지막 세그먼트의 end_time (없으면 다음 세그먼트의 start_time)
            last_seg = cited_segments[-1]
            last_seg_id = last_seg["id"]

            # 원본 segments에서 last_seg_id 다음 세그먼트 찾기
            last_seg_idx = next((i for i, s in enumerate(segments) if s["id"] == last_seg_id), None)
            if last_seg_idx is not None and last_seg_idx + 1 < len(segments):
                end_time = segments[last_seg_idx + 1]["start_time"]
            else:
                # 마지막 세그먼트인 경우 end_time은 None
                end_time = None

            # 화자 목록 추출 (중복 제거)
            speakers = sorted(list(set(seg["speaker"] for seg in cited_segments)))

            # 평균 신뢰도 계산
            avg_confidence = sum(seg.get("confidence", 0.0) for seg in cited_segments) / len(cited_segments)

            chunks.append({
                "chunk_id": chunk_idx,
                "text": clean_text,
                "segment_ids": seg_ids,  # 인용된 원본 세그먼트 ID 리스트
                "start_time": float(start_time),
                "end_time": float(end_time) if end_time is not None else None,
                "speakers": speakers,  # 복수 화자 가능
                "confidence": float(avg_confidence),
            })

        logging.info(f"✅ 청킹 결과: {len(chunks)}개 chunk, 평균 길이: {sum(len(c['text']) for c in chunks) / len(chunks):.0f}자")
        return chunks

    except Exception as e:
        logging.error(f"❌ create_token_based_chunks 오류: {e}")
        import traceback
        traceback.print_exc()
        return []


def parse_mmss_to_seconds(time_str):
    """'분:초:밀리초' 형태의 문자열을 초 단위로 변환합니다."""
    try:
        parts = time_str.split(":")
        if len(parts) == 3:
            minutes = int(parts[0])
            seconds = int(parts[1])
            milliseconds = int(parts[2])
            return minutes * 60 + seconds + milliseconds / 1000.0
        else:
            return 0.0
    except:
        return 0.0


def recognize_with_gemini(audio_path, task_id=None, audio_duration=None):
    """
    Google Gemini STT API로 음성 인식

    Args:
        audio_path: 오디오 파일 경로
        task_id: 작업 ID (프로그레스 업데이트용)
        audio_duration: 오디오 길이 (초) - 예상 시간 계산용
    """
    start_time = time.time()

    # 예상 처리 시간 계산
    estimated_time = None
    if audio_duration:
        estimated_time = estimate_stt_processing_time(audio_duration)
        logging.info(f"⏱️ 예상 STT 처리 시간: {estimated_time:.1f}초 (오디오 길이: {audio_duration:.1f}초)")

    try:
        if task_id:
            update_progress(
                task_id,
                "stt",
                0,
                "Gemini STT 시작",
                estimated_time=estimated_time,
                elapsed_time=0
            )

        logging.info(f"🎧 Gemini STT API로 음성 인식 중: {audio_path}")

        # 별도 스레드로 경과 시간 업데이트 (시뮬레이션)
        stop_progress_update = threading.Event()

        def update_elapsed_time():
            """경과 시간을 주기적으로 업데이트"""
            while not stop_progress_update.is_set():
                elapsed = time.time() - start_time

                if task_id and estimated_time:
                    # 진행률 계산 (최대 95%까지만)
                    progress_percent = min(95, int((elapsed / estimated_time) * 100))

                    update_progress(
                        task_id,
                        "stt",
                        progress_percent,
                        "오디오에서 텍스트 추출 중...",
                        estimated_time=estimated_time,
                        elapsed_time=elapsed
                    )

                time.sleep(1)  # 1초마다 업데이트

        # 진행 상황 업데이트 스레드 시작
        if task_id and estimated_time:
            progress_thread = threading.Thread(target=update_elapsed_time, daemon=True)
            progress_thread.start()

        client = get_gemini_client()

        with open(audio_path, "rb") as f:
            file_bytes = f.read()

        file_ext = os.path.splitext(audio_path)[1].lower()
        mime_type_map = {
            ".wav": "audio/wav",
            ".mp3": "audio/mp3",
            ".m4a": "audio/mp4",
            ".flac": "audio/flac",
            ".ogg": "audio/ogg",
        }
        mime_type = mime_type_map.get(file_ext, "audio/mp3")

        prompt = """
당신은 전문적인 회의록 작성자입니다. 제공된 오디오 파일을 듣고 다음 작업을 수행해 주십시오:
1. 전체 대화를 정확하게 텍스트로 변환합니다.
2. 각 발화에 대해 화자를 숫자로 구분합니다. 발화자의 등장 순서대로 번호를 할당합니다.
3. 각 발화에 대해 음성 인식의 신뢰도를 0.0~1.0 사이의 값으로 평가합니다.
4. 최종 결과는 아래의 JSON 형식과 정확히 일치해야 합니다. 각 JSON 객체는 'speaker', 'start_time_mmss', 'confidence', 'text' 키를 포함해야 합니다.
5. start_time_mmss는 "분:초:밀리초" 형태로 출력합니다. (예: "0:05:200", "1:23:450")
6. 배경음악과 발화자의 목소리가 섞인 경우 목소리만 잘 구별하여 가져온다.
7. speaker가 동일한 경우 하나의 행으로 만듭니다. 단, 문장이 5개를 넘어갈 경우 다음 대화로 분리한다.


출력 형식:
[
    {
        "speaker": 1,
        "start_time_mmss": "0:00:000",
        "confidence": 0.95,
        "text": "안녕하세요. 회의를 시작하겠습니다."
    },
    {
        "speaker": 2,
        "start_time_mmss": "0:05:200",
        "confidence": 0.92,
        "text": "네, 좋습니다."
    }
]

JSON 배열만 출력하고, 추가 설명이나 마크다운 코드 블록은 포함하지 마세요.
"""

        logging.info("🤖 Gemini 2.5 Pro로 음성 인식 중...")

        response = client.models.generate_content(
            model="gemini-2.5-pro",
            contents=[
                prompt,
                types.Part.from_bytes(
                    data=file_bytes,
                    mime_type=mime_type,
                ),
            ],
        )

        logging.info("✅ Gemini 음성 인식 완료")

        cleaned_response = response.text.strip()
        cleaned_response = (
            cleaned_response.replace("```json", "").replace("```", "").strip()
        )

        result_list = json.loads(cleaned_response)

        normalized_segments = []
        for idx, segment in enumerate(result_list):
            time_mmss = segment.get("start_time_mmss", "0:00:000")
            start_time_seconds = parse_mmss_to_seconds(time_mmss)

            normalized_segments.append(
                {
                    "id": idx,
                    "speaker": segment.get("speaker", 1),
                    "start_time": start_time_seconds,
                    "confidence": segment.get("confidence", 0.0),
                    "text": segment.get("text", ""),
                }
            )

        end_time = time.time()
        processing_time = end_time - start_time

        # 진행 상황 업데이트 스레드 중지
        if task_id and estimated_time:
            stop_progress_update.set()
            if 'progress_thread' in locals():
                progress_thread.join(timeout=1)

        if task_id:
            update_progress(
                task_id,
                "stt",
                100,
                f"Gemini STT 완료",
                estimated_time=estimated_time,
                elapsed_time=processing_time
            )

        logging.info(f"⏱️ Gemini STT 처리 시간: {processing_time:.2f}초")

        return {"segments": normalized_segments, "processing_time": processing_time}

    except Exception as e:
        end_time = time.time()
        processing_time = end_time - start_time

        # 진행 상황 업데이트 스레드 중지
        if task_id and estimated_time:
            stop_progress_update.set()
            if 'progress_thread' in locals():
                progress_thread.join(timeout=1)

        logging.error(f"❌ Gemini 오류 발생: {e}")
        if task_id:
            update_progress(
                task_id,
                "stt",
                0,
                "Gemini STT 오류",
                estimated_time=estimated_time,
                elapsed_time=processing_time
            )
        import traceback

        traceback.print_exc()
        return {"segments": None, "processing_time": processing_time}


@app.route("/")
def index():
    """메인 페이지"""
    return render_template("youtube_viewer.html")


@app.route("/api/process-youtube", methods=["POST"])
def process_youtube():
    """
    YouTube URL을 처리하여 회의록을 생성합니다.
    캐싱 기능 포함.
    """
    try:
        data = request.get_json()
        youtube_url = data.get("youtube_url", "").strip()

        if not youtube_url:
            return (
                jsonify({"success": False, "error": "YouTube URL을 입력해주세요."}),
                400,
            )

        # 먼저 video_id 추출 (다운로드 없이 정보만)
        try:
            with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
                info = ydl.extract_info(youtube_url, download=False)
                video_id = info.get("id", None)

                if not video_id:
                    return (
                        jsonify(
                            {
                                "success": False,
                                "error": "유효하지 않은 YouTube URL입니다.",
                            }
                        ),
                        400,
                    )
        except Exception as e:
            logging.error(f"URL 파싱 오류: {e}")
            return (
                jsonify(
                    {"success": False, "error": f"YouTube URL 파싱 실패: {str(e)}"}
                ),
                400,
            )

        # 이력에서 확인
        history_df = load_youtube_history()

        # video_id로 캐시 확인 (URL 형식과 무관)
        existing = history_df[history_df["video_id"] == video_id]

        if not existing.empty:
            # 캐시된 데이터 로드
            row = existing.iloc[0]

            logging.info(f"📂 캐시된 데이터 로드: {row['title']}")

            # segments JSON 파싱
            segments = json.loads(row["segments_json"])

            # 세션에 저장
            session_id = request.remote_addr + "_" + secrets.token_hex(8)
            session_data[session_id] = {
                "segments": segments,
                "chat_history": [],
                "video_id": row["video_id"],  # 요약 저장 시 사용
                "source_type": "youtube",
            }

            # NaN 값 안전 처리
            view_count = row.get("view_count", 0)
            if pd.isna(view_count):
                view_count = 0
            else:
                view_count = int(view_count)

            stt_processing_time = row.get("stt_processing_time", 0.0)
            if pd.isna(stt_processing_time):
                stt_processing_time = 0.0
            else:
                stt_processing_time = float(stt_processing_time)

            # 요약 로드 (CSV → VectorStore 순서로 확인)
            summary = row.get("summary", "")
            if not summary or pd.isna(summary) or summary.strip() == "":
                # CSV에 요약이 없으면 VectorStore에서 가져오기
                vectordb_summary = get_summary_from_vectordb(
                    source_id=row["video_id"], source_type="youtube"
                )
                if vectordb_summary:
                    summary = vectordb_summary
                    logging.info(f"📦 VectorDB에서 요약 로드: {row['video_id']}")

            return jsonify(
                {
                    "success": True,
                    "cached": True,
                    "source_type": "youtube",
                    "message": f"✅ 저장된 데이터를 불러왔습니다: {row['title']}",
                    "video_id": row["video_id"],
                    "title": row["title"],
                    "channel": row.get("channel", "Unknown"),
                    "view_count": view_count,
                    "upload_date": row.get("upload_date", ""),
                    "mp3_path": row.get("mp3_path", ""),
                    "segments": segments,
                    "total_segments": len(segments),
                    "stt_service": row["stt_service"],
                    "stt_processing_time": stt_processing_time,
                    "session_id": session_id,
                    "created_at": row["created_at"],
                    "summary": summary,
                }
            )

        # 새로운 처리
        logging.info(f"🆕 새로운 YouTube URL 처리: {youtube_url}")

        # task_id 및 remote_addr 생성 (request context에서 미리 추출)
        task_id = secrets.token_hex(16)
        remote_addr = request.remote_addr

        # progress_data 초기화 (프로그레스 바 100% 버그 방지)
        progress_data[task_id] = {}

        # 백그라운드에서 처리할 함수
        def process_in_background():
            try:
                # 1. YouTube 오디오 다운로드 (mp3로 직접 변환)
                download_result = download_youtube_audio_as_mp3(youtube_url, task_id)
                if not download_result["success"]:
                    update_progress(
                        task_id,
                        "error",
                        0,
                        f"다운로드 실패: {download_result.get('error', '알 수 없는 오류')}",
                    )
                    return

                video_id = download_result["video_id"]
                title = download_result["title"]
                channel = download_result["channel"]
                view_count = download_result["view_count"]
                upload_date = download_result["upload_date"]
                mp3_path = download_result["mp3_path"]

                # MP3 오디오 길이 추출 (예상 시간 계산용)
                audio_duration = get_audio_duration(mp3_path)

                # 2. STT 처리 (Gemini)
                stt_processing_time = 0.0
                segments = None

                result = recognize_with_gemini(mp3_path, task_id, audio_duration)
                if result and isinstance(result, dict):
                    segments = result.get("segments")
                    stt_processing_time = result.get("processing_time", 0.0)

                if not segments:
                    # STT 실패 시에도 영상 정보는 DB에 저장 (빈 세그먼트로)
                    logging.warning(f"⚠️ STT 처리 실패, 영상 정보만 DB에 저장: {title}")

                    new_row = {
                        "youtube_url": youtube_url,
                        "video_id": video_id,
                        "title": title,
                        "channel": channel,
                        "view_count": view_count,
                        "upload_date": upload_date,
                        "mp3_path": mp3_path,
                        "segments_json": json.dumps([], ensure_ascii=False),  # 빈 세그먼트
                        "stt_service": "gemini",
                        "stt_processing_time": 0.0,
                        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "summary": "STT 처리 실패",
                    }

                    history_df = load_youtube_history()
                    history_df = pd.concat(
                        [history_df, pd.DataFrame([new_row])], ignore_index=True
                    )
                    save_youtube_history(history_df)

                    update_progress(
                        task_id,
                        "error",
                        0,
                        "Gemini STT 처리 중 오류가 발생했습니다.",
                    )
                    return

                # 3. 이력에 저장
                new_row = {
                    "youtube_url": youtube_url,
                    "video_id": video_id,
                    "title": title,
                    "channel": channel,
                    "view_count": view_count,
                    "upload_date": upload_date,
                    "mp3_path": mp3_path,
                    "segments_json": json.dumps(segments, ensure_ascii=False),
                    "stt_service": "gemini",
                    "stt_processing_time": stt_processing_time,
                    "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "summary": "",
                }

                history_df = load_youtube_history()
                history_df = pd.concat(
                    [history_df, pd.DataFrame([new_row])], ignore_index=True
                )
                save_youtube_history(history_df)

                # STT 처리 시간 로그에 기록
                add_stt_processing_record(audio_duration, stt_processing_time, source_type="youtube")

                # 세션에 저장
                session_id = remote_addr + "_" + secrets.token_hex(8)
                session_data[session_id] = {
                    "segments": segments,
                    "chat_history": [],
                    "video_id": video_id,
                    "source_type": "youtube",
                }

                # 완료 상태 저장
                progress_data[task_id]["completed"] = True
                progress_data[task_id]["result"] = {
                    "success": True,
                    "source_type": "youtube",
                    "video_id": video_id,
                    "title": title,
                    "channel": channel,
                    "view_count": view_count,
                    "upload_date": upload_date,
                    "mp3_path": mp3_path,
                    "segments": segments,
                    "total_segments": len(segments),
                    "stt_service": "gemini",
                    "stt_processing_time": stt_processing_time,
                    "session_id": session_id,
                    "created_at": new_row["created_at"],
                }

                logging.info(f"✅ 백그라운드 처리 완료: {title}")

            except Exception as e:
                import traceback

                traceback.print_exc()
                update_progress(task_id, "error", 0, f"처리 중 오류 발생: {str(e)}")

        # 백그라운드 스레드 시작
        thread = threading.Thread(target=process_in_background)
        thread.daemon = True
        thread.start()

        # 즉시 task_id 반환
        return jsonify(
            {
                "success": True,
                "processing": True,
                "task_id": task_id,
                "message": "처리를 시작했습니다. 진행 상황을 확인하세요.",
            }
        )

    except Exception as e:
        import traceback

        traceback.print_exc()
        return jsonify({"success": False, "error": f"처리 중 오류 발생: {str(e)}"}), 500


@app.route("/api/process-audio", methods=["POST"])
def process_audio():
    """
    오디오 파일을 업로드하여 회의록을 생성합니다.
    캐싱 기능 포함.
    """
    try:
        # 파일 확인
        if "audio_file" not in request.files:
            return jsonify({"success": False, "error": "오디오 파일이 없습니다."}), 400

        file = request.files["audio_file"]

        if file.filename == "":
            return (
                jsonify({"success": False, "error": "파일이 선택되지 않았습니다."}),
                400,
            )

        if not allowed_file(file.filename):
            return (
                jsonify(
                    {
                        "success": False,
                        "error": f"지원하지 않는 파일 형식입니다. 허용된 형식: {', '.join(ALLOWED_AUDIO_EXTENSIONS)}",
                    }
                ),
                400,
            )

        # 파일명 준비
        filename = secure_filename(file.filename)
        final_file_path = os.path.join(UPLOADS_FOLDER, filename)

        # 임시 파일로 먼저 저장 (덮어쓰기 방지)
        temp_filename = f"temp_{secrets.token_hex(8)}_{filename}"
        temp_file_path = os.path.join(UPLOADS_FOLDER, temp_filename)
        file.save(temp_file_path)

        logging.info(f"📁 임시 파일 저장 완료: {temp_file_path}")

        # 파일 해시 계산
        file_hash = calculate_file_hash(temp_file_path)
        file_size = os.path.getsize(temp_file_path)

        # 최종 파일명 중복 체크
        if os.path.exists(final_file_path):
            # 기존 파일의 해시 계산
            existing_file_hash = calculate_file_hash(final_file_path)

            if existing_file_hash != file_hash:
                # 다른 파일인데 이름이 같음 → 에러
                os.remove(temp_file_path)  # 임시 파일 삭제
                return (
                    jsonify(
                        {
                            "success": False,
                            "error": f"같은 이름의 다른 파일이 이미 존재합니다: {filename}\n다른 파일명으로 업로드해주세요.",
                        }
                    ),
                    400,
                )
            else:
                # 같은 파일임 → 임시 파일 삭제하고 기존 파일 사용
                os.remove(temp_file_path)
                file_path = final_file_path
                logging.info(f"✅ 기존 파일 재사용: {filename}")
        else:
            # 파일이 없음 → 임시 파일을 최종 위치로 이동
            os.rename(temp_file_path, final_file_path)
            file_path = final_file_path
            logging.info(f"✅ 파일 저장 완료: {file_path}")

        # 오디오 길이 추출
        audio_duration = get_audio_duration(file_path)

        # 이력에서 확인 (파일 해시로 캐시 확인)
        history_df = load_audio_history()
        existing = history_df[history_df["file_hash"] == file_hash]

        if not existing.empty:
            # 캐시된 데이터 로드
            row = existing.iloc[0]

            logging.info(f"📂 캐시된 오디오 데이터 로드: {row['filename']}")

            # segments JSON 파싱
            segments = json.loads(row["segments_json"])

            # 세션에 저장
            session_id = request.remote_addr + "_" + secrets.token_hex(8)
            session_data[session_id] = {
                "segments": segments,
                "chat_history": [],
                "file_hash": row["file_hash"],
                "filename": row["filename"],
                "source_type": "audio",
            }

            stt_processing_time = row.get("stt_processing_time", 0.0)
            if pd.isna(stt_processing_time):
                stt_processing_time = 0.0
            else:
                stt_processing_time = float(stt_processing_time)

            audio_duration = row.get("audio_duration", 0.0)
            if pd.isna(audio_duration):
                audio_duration = 0.0
            else:
                audio_duration = float(audio_duration)

            # 요약 로드 (CSV → VectorStore 순서로 확인)
            summary = row.get("summary", "")
            if not summary or pd.isna(summary) or summary.strip() == "":
                # CSV에 요약이 없으면 VectorStore에서 가져오기
                vectordb_summary = get_summary_from_vectordb(
                    source_id=row["file_hash"], source_type="audio"
                )
                if vectordb_summary:
                    summary = vectordb_summary
                    logging.info(f"📦 VectorDB에서 요약 로드: {row['filename']}")

            return jsonify(
                {
                    "success": True,
                    "cached": True,
                    "source_type": "audio",
                    "message": f"✅ 저장된 데이터를 불러왔습니다: {row['filename']}",
                    "file_hash": row["file_hash"],
                    "filename": row["filename"],
                    "file_path": row["file_path"],
                    "file_size": int(row["file_size"]),
                    "audio_duration": audio_duration,
                    "segments": segments,
                    "total_segments": len(segments),
                    "stt_service": row["stt_service"],
                    "stt_processing_time": stt_processing_time,
                    "session_id": session_id,
                    "created_at": row["created_at"],
                    "summary": summary,
                }
            )

        # 새로운 처리
        logging.info(f"🆕 새로운 오디오 파일 처리: {filename}")

        # task_id 및 remote_addr 생성
        task_id = secrets.token_hex(16)
        remote_addr = request.remote_addr

        # progress_data 초기화 (프로그레스 바 100% 버그 방지)
        progress_data[task_id] = {}

        # 백그라운드에서 처리할 함수
        def process_in_background():
            try:
                # STT 처리 (Gemini)
                stt_processing_time = 0.0
                segments = None

                result = recognize_with_gemini(file_path, task_id, audio_duration)
                if result and isinstance(result, tuple) and len(result) == 2:
                    segments, stt_processing_time = result
                elif result and isinstance(result, dict):
                    segments = result.get("segments")
                    stt_processing_time = result.get("processing_time", 0.0)

                if not segments:
                    # STT 실패 시에도 파일 정보는 DB에 저장 (빈 세그먼트로)
                    logging.warning(f"⚠️ STT 처리 실패, 파일 정보만 DB에 저장: {filename}")

                    new_row = {
                        "file_hash": file_hash,
                        "filename": filename,
                        "file_path": file_path,
                        "file_size": file_size,
                        "audio_duration": audio_duration,
                        "segments_json": json.dumps([], ensure_ascii=False),  # 빈 세그먼트
                        "stt_service": "gemini",
                        "stt_processing_time": 0.0,
                        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "summary": "STT 처리 실패",
                    }

                    history_df = load_audio_history()
                    history_df = pd.concat(
                        [history_df, pd.DataFrame([new_row])], ignore_index=True
                    )
                    save_audio_history(history_df)

                    update_progress(
                        task_id,
                        "error",
                        0,
                        "Gemini STT 처리 중 오류가 발생했습니다.",
                    )
                    return

                # 이력에 저장
                new_row = {
                    "file_hash": file_hash,
                    "filename": filename,
                    "file_path": file_path,
                    "file_size": file_size,
                    "audio_duration": audio_duration,
                    "segments_json": json.dumps(segments, ensure_ascii=False),
                    "stt_service": "gemini",
                    "stt_processing_time": stt_processing_time,
                    "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "summary": "",
                }

                history_df = load_audio_history()
                history_df = pd.concat(
                    [history_df, pd.DataFrame([new_row])], ignore_index=True
                )
                save_audio_history(history_df)

                # STT 처리 시간 로그에 기록
                add_stt_processing_record(audio_duration, stt_processing_time, source_type="audio")

                # 세션에 저장
                session_id = remote_addr + "_" + secrets.token_hex(8)
                session_data[session_id] = {
                    "segments": segments,
                    "chat_history": [],
                    "file_hash": file_hash,
                    "filename": filename,
                    "source_type": "audio",
                }

                # 완료 상태 저장
                progress_data[task_id]["completed"] = True
                progress_data[task_id]["result"] = {
                    "success": True,
                    "source_type": "audio",
                    "file_hash": file_hash,
                    "filename": filename,
                    "file_path": file_path,
                    "file_size": file_size,
                    "audio_duration": audio_duration,
                    "segments": segments,
                    "total_segments": len(segments),
                    "stt_service": "gemini",
                    "stt_processing_time": stt_processing_time,
                    "session_id": session_id,
                    "created_at": new_row["created_at"],
                }

                logging.info(f"✅ 백그라운드 오디오 처리 완료: {filename}")

            except Exception as e:
                import traceback

                traceback.print_exc()
                update_progress(task_id, "error", 0, f"처리 중 오류 발생: {str(e)}")

        # STT 예상 처리 시간 계산
        estimated_time = estimate_stt_processing_time(audio_duration)

        # 백그라운드 스레드 시작
        thread = threading.Thread(target=process_in_background)
        thread.daemon = True
        thread.start()

        # 즉시 task_id와 예상 시간 반환
        return jsonify(
            {
                "success": True,
                "processing": True,
                "task_id": task_id,
                "estimated_time": estimated_time,  # 예상 처리 시간 (초)
                "audio_duration": audio_duration,  # 오디오 길이 (초)
                "message": "오디오 파일 처리를 시작했습니다. 진행 상황을 확인하세요.",
            }
        )

    except Exception as e:
        import traceback

        traceback.print_exc()
        return jsonify({"success": False, "error": f"처리 중 오류 발생: {str(e)}"}), 500


@app.route("/uploads/<path:filename>")
def serve_audio(filename):
    """업로드된 오디오 파일 제공"""
    uploads_path = os.path.abspath(UPLOADS_FOLDER)
    return send_from_directory(uploads_path, filename)


@app.route("/mp3/<path:filename>")
def serve_mp3(filename):
    """MP3 파일 제공"""
    mp3_path = os.path.abspath(MP3_FOLDER)
    return send_from_directory(mp3_path, filename)


@app.route("/api/summarize", methods=["POST"])
def summarize_transcript():
    """회의록 요약 API"""
    try:
        data = request.get_json()
        segments = data.get("segments")
        session_id = data.get("session_id")
        title = data.get("title")  # 제목 받기

        if not segments and session_id and session_id in session_data:
            segments = session_data[session_id]["segments"]

        if not segments:
            return (
                jsonify({"success": False, "error": "요약할 데이터가 없습니다."}),
                400,
            )

        # 기존 요약이 있는지 확인 (중복 생성 방지)
        if session_id and session_id in session_data:
            source_type = session_data[session_id].get("source_type")
            source_id = None

            if source_type == "youtube":
                source_id = session_data[session_id].get("video_id")
            elif source_type == "audio":
                source_id = session_data[session_id].get("file_hash")

            if source_id:
                # VectorStore에서 기존 요약 확인
                existing_summary = get_summary_from_vectordb(source_id, source_type)
                if existing_summary:
                    logging.info(
                        f"✅ 기존 요약 발견 (source: {source_id}), 새로 생성하지 않음"
                    )
                    return jsonify(
                        {
                            "success": True,
                            "summary": existing_summary,
                            "from_cache": True,
                        }
                    )

        # segments를 token-based chunks로 변환
        logging.info("📦 Token-based chunks 생성 중...")
        chunks = create_token_based_chunks(segments, chunk_size=500, chunk_overlap=100)
        logging.info(f"✅ {len(chunks)}개 chunks 생성 완료")

        # chunks를 텍스트로 변환 (chunk_id 표시)
        chunk_texts = []
        for chunk in chunks:
            # chunk_id를 사용하여 청크 번호 표시
            chunk_id = chunk["chunk_id"]
            chunk_text = f"[청크 {chunk_id}]\n{chunk['text']}"
            chunk_texts.append(chunk_text)

        transcript_text = "\n\n".join(chunk_texts)

        client = get_gemini_client()

        # 제목이 있으면 프롬프트에 포함
        title_context = f"\n회의 제목: {title}\n" if title else ""

        prompt = f"""당신은 제공된 대화 스크립트 내용을 분석하여, 구조화된 주제별 요약본으로 변환하는 AI 어시스턴트입니다.

**입력 파일 형식:**
입력 내용은 의미 단위로 묶인 청크(chunk) 형태입니다. 각 청크는 [청크 X] 형식으로 청크 번호를 표시합니다.
예시: [청크 0], [청크 1], [청크 2] 등

**출력 요구사항:**
당신은 입력 파일을 다음과 같은 규칙에 따라 요약본으로 변환해야 합니다.

1.  회의 제목 : {title_context}
2.  주제별 그룹화 : 스크립트 전체 내용을 분석하여 주요 논의 주제를 파악합니다.
3.  소주제 제목 형식 (중요): 각 주요 주제별로 핵심 내용을 요약하는 제목을 **반드시 "### 제목" 형식**으로 생성합니다. (예: `### 대주주 주식 양도세 기준 논란`)
4.  내용 요약: 각 주제 제목 아래에 관련된 핵심 주장, 사실, 의견을 글머리 기호(`*`)를 사용하여 요약합니다.
5.  문체 변환: 원본의 구어체(대화체)를 간결하고 공식적인 서술형 문어체(요약문 스타일)로 변경합니다.
6.  화자 및 군더더기 제거: 'A:', 'B:'와 같은 화자 표시와 '그러니까', '어,', '자,', '[웃음]' 등 대화의 군더더기를 모두 제거하고 내용만 정제하여 요약합니다.
7.  제목과 내용 간격: 소주제 제목(### 제목)과 첫 번째 글머리 기호(*) 사이에는 공백 줄을 두지 않습니다. 제목 바로 다음 줄에 내용을 작성합니다.
8.  문단 간격: 서로 다른 소주제 사이에는 줄바꿈을 2개 넣어 가독성을 높입니다.
9.  정확한 인용 (필수):
    * 요약된 모든 문장이나 구절 끝에는 반드시 [청크 X]에 표시된 청크 번호를 [cite: X] 형식으로 인용해야 합니다.
    * 하나의 글머리 기호가 여러 청크의 내용을 종합한 경우, 모든 관련 청크 번호를 인용해야 합니다. (예: `[cite: 0, 1, 2]`)
    * 인용은 요약된 내용과 원본 소스 간의 사실 관계가 정확히 일치해야 합니다.
    * [청크 0]의 내용을 요약할 때는 반드시 [cite: 0]으로 인용합니다.
    * [청크 1]과 [청크 2]의 내용을 종합할 때는 [cite: 1, 2]로 인용합니다.

**출력 예시:**
### 첫 번째 주요 주제
* 첫 번째 논의 내용 요약 [cite: 0]
* 두 번째 논의 내용 요약 [cite: 1, 2]

### 두 번째 주요 주제
* 관련 논의 내용 요약 [cite: 3, 4]

작업 수행:
이제 다음 [스크립트 내용]을 분석하여 위의 요구사항을 모두 준수하는 주제별 요약본을 생성해 주십시오.

[스크립트 내용]
{transcript_text}"""

        logging.info("🤖 Gemini로 요약 생성 중...")

        response = client.models.generate_content(
            model="gemini-2.5-pro",
            contents=prompt,
        )

        summary = response.text.strip()

        # 디버깅: 요약 내용 출력 및 파일 저장
        print("\n" + "=" * 80)
        print("생성된 요약 내용:")
        print("=" * 80)
        print(summary)
        print("=" * 80 + "\n")

        # 요약 내용을 파일로 저장 (디버깅용)
        try:
            debug_file = (
                f"data/summary_debug_{session_id[:8] if session_id else 'unknown'}.txt"
            )
            with open(debug_file, "w", encoding="utf-8") as f:
                f.write(summary)
            logging.info(f"📄 요약 내용이 디버그 파일에 저장됨: {debug_file}")
        except Exception as e:
            logging.debug(f"디버그 파일 저장 실패 (무시): {e}")

        logging.info("✅ 요약 생성 완료")

        # CSV 및 VectorStore에 요약 저장
        if session_id and session_id in session_data:
            source_type = session_data[session_id].get("source_type")

            if source_type == "youtube":
                video_id = session_data[session_id].get("video_id")
                if video_id:
                    try:
                        # CSV에 저장
                        history_df = load_youtube_history()
                        mask = history_df["video_id"] == video_id
                        if mask.any():
                            history_df.loc[mask, "summary"] = summary
                            save_youtube_history(history_df)
                            logging.info(
                                f"💾 요약이 YouTube CSV에 저장되었습니다 (video_id: {video_id})"
                            )
                            logging.info(
                                f"ℹ️ VectorStore 저장을 원하시면 'VectorStore에 저장' 버튼을 클릭하세요."
                            )

                        # VectorStore 자동 저장 제거: 사용자가 명시적으로 저장 버튼을 클릭해야 함
                        # vectordb_success = store_summary_in_vectordb(
                        #     summary=summary,
                        #     source_id=video_id,
                        #     source_type="youtube",
                        #     filename=None,
                        # )
                    except Exception as e:
                        logging.error(f"요약 저장 오류: {e}")

            elif source_type == "audio":
                file_hash = session_data[session_id].get("file_hash")
                filename = session_data[session_id].get("filename")
                if file_hash:
                    try:
                        # CSV에 저장
                        history_df = load_audio_history()
                        mask = history_df["file_hash"] == file_hash
                        if mask.any():
                            history_df.loc[mask, "summary"] = summary
                            save_audio_history(history_df)
                            logging.info(
                                f"💾 요약이 오디오 CSV에 저장되었습니다 (file_hash: {file_hash})"
                            )
                            logging.info(
                                f"ℹ️ VectorStore 저장을 원하시면 'VectorStore에 저장' 버튼을 클릭하세요."
                            )

                        # VectorStore 자동 저장 제거: 사용자가 명시적으로 저장 버튼을 클릭해야 함
                        # vectordb_success = store_summary_in_vectordb(
                        #     summary=summary,
                        #     source_id=file_hash,
                        #     source_type="audio",
                        #     filename=filename,
                        # )
                    except Exception as e:
                        logging.error(f"요약 저장 오류: {e}")

        return jsonify({"success": True, "summary": summary})

    except Exception as e:
        import traceback

        traceback.print_exc()
        return (
            jsonify({"success": False, "error": f"요약 생성 중 오류 발생: {str(e)}"}),
            500,
        )


@app.route("/api/chat", methods=["POST"])
def chat_with_transcript():
    """회의록 기반 채팅 API (RAG)"""
    try:
        data = request.get_json()
        user_message = data.get("message", "").strip()

        if not user_message:
            return jsonify({"success": False, "error": "메시지를 입력해주세요."}), 400

        session_id = data.get("session_id")
        chat_history = data.get("chat_history", [])

        if not session_id or session_id not in session_data:
            return jsonify({"success": False, "error": "세션 데이터가 없습니다."}), 400

        session_info = session_data[session_id]
        source_type = session_info.get("source_type")
        chat_history = session_info.get("chat_history", [])

        # source_id 가져오기
        if source_type == "youtube":
            source_id = session_info.get("video_id")
        elif source_type == "audio":
            source_id = session_info.get("file_hash")
        else:
            return (
                jsonify({"success": False, "error": "알 수 없는 소스 타입입니다."}),
                400,
            )

        # VectorDB에서 관련 세그먼트 검색 (RAG)
        logging.info(f"🔍 VectorDB 검색: {user_message}")
        search_results = search_vectordb(
            query=user_message,
            source_id=source_id,
            source_type=source_type,
            n_results=5,
        )

        if not search_results:
            return (
                jsonify(
                    {"success": False, "error": "관련 회의록 내용을 찾을 수 없습니다."}
                ),
                400,
            )

        # 검색 결과를 컨텍스트로 구성
        context_text = "\n\n".join(
            [
                f"화자 {result['metadata']['speaker']} ({result['metadata']['start_time']:.1f}초): {result['document']}"
                for result in search_results
            ]
        )

        logging.info(f"📝 검색된 세그먼트 수: {len(search_results)}")

        # 이전 대화 내역
        history_text = ""
        if chat_history:
            history_text = "\n\n이전 대화 내역:\n"
            for hist in chat_history[-5:]:
                history_text += f"사용자: {hist['user']}\n"
                history_text += f"AI: {hist['assistant']}\n\n"

        client = get_gemini_client()

        prompt = f"""당신은 회의록 분석 전문 AI 어시스턴트입니다. 다음은 사용자 질문과 관련된 회의록 내용입니다. 이를 바탕으로 질문에 답변해 주세요.

관련 회의록 내용:
{context_text}
{history_text}
사용자 질문: {user_message}

답변 시 다음을 유의해 주세요:
1. 제공된 회의록 내용을 기반으로 정확하게 답변하세요.
2. 필요한 경우 화자와 시간 정보를 포함해 주세요.
3. 제공된 내용에 없는 것은 추측하지 말고 "제공된 회의록에 해당 내용이 없습니다"라고 답변하세요.
4. 간결하고 명확하게 답변하세요."""

        logging.info(f"🤖 사용자 질문: {user_message}")

        response = client.models.generate_content(
            model="gemini-2.5-pro",
            contents=prompt,
        )

        assistant_response = response.text.strip()
        logging.info(f"✅ AI 응답 생성 완료 (RAG 기반)")

        chat_history.append({"user": user_message, "assistant": assistant_response})

        session_data[session_id]["chat_history"] = chat_history

        return jsonify(
            {
                "success": True,
                "response": assistant_response,
                "chat_history": chat_history,
                "search_results": len(search_results),  # 디버깅용
            }
        )

    except Exception as e:
        import traceback

        traceback.print_exc()
        return (
            jsonify(
                {"success": False, "error": f"채팅 응답 생성 중 오류 발생: {str(e)}"}
            ),
            500,
        )


@app.route("/api/history", methods=["GET"])
def get_history():
    """처리 이력 조회 API"""
    try:
        youtube_history = load_youtube_history()
        audio_history = load_audio_history()

        # DataFrame을 dict 리스트로 변환
        youtube_list = youtube_history.to_dict("records")
        audio_list = audio_history.to_dict("records")

        return jsonify(
            {
                "success": True,
                "youtube_history": youtube_list,
                "audio_history": audio_list,
                "total_youtube": len(youtube_list),
                "total_audio": len(audio_list),
            }
        )
    except Exception as e:
        logging.error(f"이력 조회 오류: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/progress/<task_id>", methods=["GET"])
def get_progress(task_id):
    """진행 상황 조회 API"""
    try:
        if task_id not in progress_data:
            return jsonify({"success": False, "error": "작업을 찾을 수 없습니다."}), 404

        return jsonify(
            {"success": True, "task_id": task_id, "progress": progress_data[task_id]}
        )
    except Exception as e:
        logging.error(f"진행 상황 조회 오류: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/save-to-vectorstore", methods=["POST"])
def save_to_vectorstore():
    """세그먼트와 요약을 VectorStore에 저장"""
    try:
        data = request.get_json()
        source_id = data.get("source_id", "").strip()
        source_type = data.get("source_type", "").strip()
        segments = data.get("segments", [])
        title = data.get("title", "").strip()
        summary = data.get("summary", "")  # strip() 제거하여 원본 유지
        filename = data.get("filename", None)

        # 디버깅: 요약 수신 확인
        logging.info(f"📥 요약 수신 확인: type={type(summary)}, length={len(summary) if summary else 0}")
        if summary:
            logging.info(f"📝 요약 미리보기 (첫 200자): {summary[:200]}...")
        else:
            logging.warning("⚠️ 요약이 비어있거나 None입니다!")

        if not source_id or not source_type:
            return (
                jsonify(
                    {"success": False, "error": "source_id와 source_type이 필요합니다."}
                ),
                400,
            )

        if not segments:
            return (
                jsonify({"success": False, "error": "저장할 세그먼트가 없습니다."}),
                400,
            )

        logging.info(f"📦 VectorStore 저장 시작: source_id={source_id}, title={title}")

        # 1. 세그먼트를 VectorStore에 저장
        vectordb_success = store_segments_in_vectordb(
            segments=segments,
            source_id=source_id,
            source_type=source_type,
            filename=filename,
            title=title if title else None,
        )

        if not vectordb_success:
            return (
                jsonify({"success": False, "error": "세그먼트 저장에 실패했습니다."}),
                500,
            )

        # 2. 요약이 있으면 Summary VectorStore에도 저장
        summary_saved = False
        if summary and summary.strip():  # 빈 문자열 체크 강화
            logging.info(f"💾 요약 저장 시도: {len(summary)} 문자")
            summary_saved = store_summary_in_vectordb(
                summary=summary,
                source_id=source_id,
                source_type=source_type,
                filename=filename,
            )
            if summary_saved:
                logging.info(f"✅ 요약이 Summary VectorStore에 저장되었습니다.")
            else:
                logging.error(f"❌ 요약 저장 실패: store_summary_in_vectordb가 False 반환")
        else:
            logging.warning(f"⚠️ 요약이 비어있어 저장하지 않습니다 (summary={repr(summary)})")

        logging.info(
            f"✅ VectorStore 저장 완료: {len(segments)}개 세그먼트, 요약 저장={summary_saved}"
        )

        return jsonify(
            {
                "success": True,
                "message": f"VectorStore에 저장되었습니다 (세그먼트: {len(segments)}개)",
                "segments_saved": len(segments),
                "summary_saved": summary_saved,
            }
        )

    except Exception as e:
        import traceback

        traceback.print_exc()
        logging.error(f"❌ VectorStore 저장 오류: {e}")
        return (
            jsonify(
                {"success": False, "error": f"VectorStore 저장 중 오류 발생: {str(e)}"}
            ),
            500,
        )


@app.route("/api/update-title", methods=["POST"])
def update_title():
    """VectorStore의 세그먼트 메타데이터에 제목 업데이트"""
    try:
        data = request.get_json()
        source_id = data.get("source_id", "").strip()
        source_type = data.get("source_type", "").strip()
        title = data.get("title", "").strip()

        if not source_id or not source_type:
            return (
                jsonify(
                    {"success": False, "error": "source_id와 source_type이 필요합니다."}
                ),
                400,
            )

        if not title:
            return jsonify({"success": False, "error": "제목을 입력해주세요."}), 400

        # VectorStore 선택
        vectorstore = (
            youtube_vectorstore if source_type == "youtube" else audio_vectorstore
        )

        if not vectorstore:
            return (
                jsonify(
                    {"success": False, "error": "VectorStore가 초기화되지 않았습니다."}
                ),
                500,
            )

        # 해당 source_id의 모든 문서 가져오기
        existing_docs = vectorstore.get(where={"source_id": source_id})

        if not existing_docs or not existing_docs["ids"]:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": "해당 source_id의 데이터를 찾을 수 없습니다.",
                    }
                ),
                404,
            )

        # 각 문서의 메타데이터에 title 추가
        # LangChain Chroma는 직접적인 metadata 업데이트를 지원하지 않으므로
        # 내부 _collection을 사용하여 업데이트
        updated_metadatas = []
        for i in range(len(existing_docs["ids"])):
            metadata = existing_docs["metadatas"][i].copy()
            metadata["title"] = title
            updated_metadatas.append(metadata)

        # Chroma collection의 update 메서드 사용
        vectorstore._collection.update(
            ids=existing_docs["ids"], metadatas=updated_metadatas
        )
        updated_count = len(existing_docs["ids"])

        logging.info(
            f"✅ 제목 업데이트 완료: {updated_count}개 세그먼트 (source: {source_id}, title: {title})"
        )

        return jsonify(
            {
                "success": True,
                "message": f"제목이 업데이트되었습니다: {title}",
                "updated_count": updated_count,
            }
        )

    except Exception as e:
        import traceback

        traceback.print_exc()
        logging.error(f"❌ 제목 업데이트 오류: {e}")
        return (
            jsonify(
                {"success": False, "error": f"제목 업데이트 중 오류 발생: {str(e)}"}
            ),
            500,
        )


@app.route("/api/retriever-search", methods=["POST"])
def retriever_search():
    """VectorStore 검색 API (Retriever 사용) - 청크 반환"""
    try:
        data = request.get_json()
        query = data.get("query", "").strip()
        source_type = data.get("source_type", None)  # None이면 전체 검색
        n_results = data.get("n_results", 5)

        if not query:
            return jsonify({"success": False, "error": "검색어를 입력해주세요."}), 400

        # VectorDB 검색 수행 (chunk만 검색)
        logging.info(
            f"🔍 Retriever 검색: '{query}' (source_type: {source_type}, n_results: {n_results}, document_type: chunk)"
        )

        search_results = search_vectordb(
            query=query,
            source_id=None,  # 특정 source로 제한하지 않음
            source_type=source_type,  # youtube, audio 또는 None (전체)
            n_results=n_results,
            document_type="chunk",  # chunk만 검색
        )

        logging.info(f"✅ 청크 검색 완료: {len(search_results)}개 결과")

        # 청크 결과를 포맷팅
        chunk_results = []
        for result in search_results:
            metadata = result.get("metadata", {})
            chunk_id = metadata.get("chunk_id", 0)

            chunk_info = {
                "id": chunk_id,
                "document": result.get("document", ""),
                "metadata": metadata,
                "distance": result.get("distance", 0.0),
            }

            chunk_results.append(chunk_info)

        logging.info(f"✅ 청크 결과 포맷팅 완료: {len(chunk_results)}개")

        return jsonify(
            {
                "success": True,
                "results": chunk_results,
                "total": len(chunk_results),
                "query": query,
            }
        )

    except Exception as e:
        import traceback

        traceback.print_exc()
        logging.error(f"❌ Retriever 검색 오류: {e}")
        return jsonify({"success": False, "error": f"검색 중 오류 발생: {str(e)}"}), 500


@app.route("/api/ask_content", methods=["POST"])
def ask_content():
    """내용 질문 API (RAG 기반 - Citation 기반 세그먼트 조회)"""
    try:
        data = request.get_json()
        question = data.get("question", "").strip()
        summary_n = data.get("summary_n", 5)  # 요약 검색 개수

        if not question:
            return jsonify({"success": False, "error": "질문을 입력해주세요."}), 400

        logging.info(f"💬 내용 질문: '{question}' (요약: {summary_n}개)")

        # 1. 요약 검색만 수행
        logging.info("🔍 요약 검색 수행 중...")
        summary_results = search_vectordb(
            query=question,
            source_id=None,
            source_type="summary",
            n_results=summary_n,
        )
        logging.info(f"✅ 요약 검색 완료: {len(summary_results)}개")

        # 2. 요약에서 citation 추출 (청크 번호 기반)
        import re
        import json
        cited_segments = []
        segment_ids_to_fetch = set()  # 중복 제거를 위한 set

        for summary_result in summary_results:
            summary_text = summary_result.get("document", "")
            metadata = summary_result.get("metadata", {})
            source_id = metadata.get("source_id")
            source_type = metadata.get("source_type")

            # 1차: 메타데이터에서 cited_chunk_ids 가져오기
            cited_chunk_ids = metadata.get("cited_chunk_ids", [])

            # filter_complex_metadata는 리스트를 JSON 문자열로 변환하므로 파싱 필요
            if isinstance(cited_chunk_ids, str):
                try:
                    cited_chunk_ids = json.loads(cited_chunk_ids)
                    logging.debug(f"🔄 cited_chunk_ids를 문자열에서 리스트로 변환: {cited_chunk_ids}")
                except Exception as e:
                    logging.warning(f"⚠️ cited_chunk_ids 파싱 실패: {e}")
                    cited_chunk_ids = []

            if not cited_chunk_ids:
                # 2차: 텍스트에서 [cite: X] 정규식으로 파싱 (fallback)
                citations = re.findall(r'\[cite:\s*(\d+(?:\s*,\s*\d+)*)\]', summary_text)

                if citations:
                    for citation in citations:
                        ids = [int(cid.strip()) for cid in citation.split(',')]
                        cited_chunk_ids.extend(ids)

            if cited_chunk_ids:
                logging.info(f"📌 Citation 발견: source_id={source_id}, chunk_ids={cited_chunk_ids}")

                # 3. 각 청크에서 segment_ids 추출
                vectorstore = youtube_vectorstore if source_type == "youtube" else audio_vectorstore

                for chunk_id in cited_chunk_ids:
                    try:
                        # VectorStore에서 청크 조회
                        chunk_doc_id = f"{source_id}_chunk_{chunk_id}"
                        chunk_results = vectorstore.get(ids=[chunk_doc_id])

                        if chunk_results and chunk_results["documents"]:
                            chunk_metadata = chunk_results["metadatas"][0]
                            seg_ids = chunk_metadata.get("segment_ids", [])

                            # JSON 문자열인 경우 파싱
                            if isinstance(seg_ids, str):
                                try:
                                    seg_ids = json.loads(seg_ids)
                                except:
                                    seg_ids = []

                            # segment_ids를 조회 목록에 추가
                            for seg_id in seg_ids:
                                segment_ids_to_fetch.add((source_id, source_type, seg_id))

                            logging.debug(f"✅ 청크 {chunk_id}에서 segment_ids 추출: {seg_ids}")
                        else:
                            logging.warning(f"⚠️ 청크 {chunk_id}를 찾을 수 없음")
                    except Exception as e:
                        logging.warning(f"⚠️ 청크 {chunk_id} 조회 실패: {e}")

        # 중복 제거된 segment_id들을 조회
        logging.info(f"🔍 총 {len(segment_ids_to_fetch)}개의 고유한 세그먼트 조회 필요")

        # YouTube URL 조회를 위한 캐시 (video_id -> youtube_url)
        youtube_url_cache = {}

        for source_id, source_type, seg_id in segment_ids_to_fetch:
            vectorstore = youtube_vectorstore if source_type == "youtube" else audio_vectorstore

            segment_found = False

            # 1차 시도: VectorStore에서 세그먼트 조회 (기존 데이터 호환성)
            if vectorstore:
                try:
                    doc_id = f"{source_id}_seg_{seg_id}"
                    results = vectorstore.get(ids=[doc_id])

                    if results and results["documents"]:
                        metadata = results["metadatas"][0]
                        start_time = metadata.get("start_time", 0)

                        segment_info = {
                            "id": seg_id,
                            "document": results["documents"][0],
                            "metadata": metadata,
                            "distance": 0.0,  # citation이므로 거리 0
                        }

                        # 유튜브인 경우 타임스탬프 링크 생성
                        if source_type == "youtube":
                            # 캐시에서 URL 가져오기 (없으면 CSV에서 조회)
                            if source_id not in youtube_url_cache:
                                try:
                                    history_df = load_youtube_history()
                                    url_row = history_df[history_df["video_id"] == source_id]
                                    if not url_row.empty:
                                        youtube_url_cache[source_id] = url_row.iloc[0]["youtube_url"]
                                except Exception as e:
                                    logging.warning(f"⚠️ YouTube URL 조회 실패 (video_id: {source_id}): {e}")

                            youtube_url = youtube_url_cache.get(source_id)
                            if youtube_url:
                                # 타임스탬프 링크 생성 (초 단위로 변환)
                                timestamp_seconds = int(start_time)
                                timestamp_link = f"{youtube_url}&t={timestamp_seconds}s"
                                segment_info["timestamp_link"] = timestamp_link
                                logging.debug(f"🔗 타임스탬프 링크 생성: {timestamp_link}")

                        cited_segments.append(segment_info)
                        segment_found = True
                        logging.debug(f"✅ Segment {seg_id} VectorStore에서 조회 성공")
                except Exception as e:
                    logging.debug(f"VectorStore에서 Segment {seg_id} 조회 실패: {e}")

            # 2차 시도: CSV에서 세그먼트 조회 (청킹 사용 시)
            if not segment_found:
                try:
                    segment = get_segment_from_csv(source_id, source_type, seg_id)

                    if segment:
                        start_time = segment.get("start_time", 0)

                        segment_info = {
                            "id": seg_id,
                            "document": segment.get("text", ""),
                            "metadata": {
                                "source_id": source_id,
                                "source_type": source_type,
                                "speaker": str(segment.get("speaker", "")),
                                "start_time": float(start_time),
                                "confidence": float(segment.get("confidence", 0.0)),
                                "segment_id": seg_id,
                            },
                            "distance": 0.0,
                        }

                        # 유튜브인 경우 타임스탬프 링크 생성
                        if source_type == "youtube":
                            if source_id not in youtube_url_cache:
                                try:
                                    history_df = load_youtube_history()
                                    url_row = history_df[history_df["video_id"] == source_id]
                                    if not url_row.empty:
                                        youtube_url_cache[source_id] = url_row.iloc[0]["youtube_url"]
                                except Exception as e:
                                    logging.warning(f"⚠️ YouTube URL 조회 실패 (video_id: {source_id}): {e}")

                            youtube_url = youtube_url_cache.get(source_id)
                            if youtube_url:
                                timestamp_seconds = int(start_time)
                                timestamp_link = f"{youtube_url}&t={timestamp_seconds}s"
                                segment_info["timestamp_link"] = timestamp_link
                                logging.debug(f"🔗 타임스탬프 링크 생성: {timestamp_link}")

                        cited_segments.append(segment_info)
                        segment_found = True
                        logging.debug(f"✅ Segment {seg_id} CSV에서 조회 성공")
                except Exception as e:
                    logging.warning(f"⚠️ CSV에서 Segment {seg_id} 조회 실패: {e}")

            if not segment_found:
                logging.warning(f"⚠️ Segment {seg_id} 조회 실패 (VectorStore 및 CSV 모두)")

        # cited_segments를 시간순으로 정렬
        cited_segments.sort(key=lambda x: x["metadata"].get("start_time", 0))

        logging.info(f"✅ Citation 기반 세그먼트 조회 완료: {len(cited_segments)}개")

        # 3. 컨텍스트 구성 (요약만 사용)
        summary_context = "\n\n".join(
            [
                f"[요약 검색 결과 {i+1}]\n출처: {r.get('metadata', {}).get('source_id', 'Unknown')}\n제목: {r.get('metadata', {}).get('subtopic', '전체')}\n내용: {r.get('document', '')}"
                for i, r in enumerate(summary_results)
            ]
        )

        # 4. RAG 프롬프트 생성 (요약만 사용)
        rag_prompt = f"""아래 회의 요약을 바탕으로 질문에 답변해주세요.

**질문:**
{question}

**참고 자료: 회의 요약**
{summary_context if summary_context else "(검색 결과 없음)"}

**답변 작성 방법:**
1. 참고 자료의 내용을 기반으로 명확하고 간결하게 답변하세요.
2. 불필요한 인사말이나 "AI 어시스턴트입니다" 같은 자기소개는 생략하고, 질문에 대한 답변만 바로 시작하세요.
3. 일반인이 이해하기 쉽도록 쉬운 표현을 사용하세요.
4. 답변은 마크다운 형식으로 작성하세요 (제목, 리스트, 강조 등 활용).
5. 필요시 글머리 기호(-)나 번호 목록을 사용하여 구조화하세요.
6. 중요한 정보는 **굵게** 표시하세요.
7. 참고 자료에 관련 정보가 없으면, "제공된 자료에는 해당 내용이 없습니다"라고 간단히 답변하세요.

답변:"""

        # 5. Gemini API 호출
        logging.info("🤖 Gemini API 호출 중...")
        client = get_gemini_client()
        response = client.models.generate_content(
            model="gemini-2.5-pro", contents=rag_prompt
        )

        answer = response.text.strip()
        logging.info("✅ 답변 생성 완료")

        return jsonify(
            {
                "success": True,
                "answer": answer,
                "question": question,
                "transcript_results_count": len(cited_segments),
                "summary_results_count": len(summary_results),
                "transcript_results": cited_segments,  # citation 기반 세그먼트
                "summary_results": summary_results,
            }
        )

    except Exception as e:
        import traceback

        traceback.print_exc()
        logging.error(f"❌ 내용 질문 오류: {e}")
        return (
            jsonify({"success": False, "error": f"질문 처리 중 오류 발생: {str(e)}"}),
            500,
        )


# ==================== 데이터 관리 API ====================

@app.route("/api/data-management/list", methods=["GET"])
def api_data_management_list():
    """데이터베이스 목록 조회"""
    try:
        from modules.sqlite_db import load_youtube_data, load_audio_data, get_database_stats

        # YouTube 목록
        youtube_data = load_youtube_data()
        youtube_list = []
        for item in youtube_data:
            youtube_list.append({
                'id': item['video_id'],
                'type': 'youtube',
                'title': item['title'],
                'channel': item['channel'],
                'view_count': item['view_count'],
                'upload_date': item['upload_date'],
                'stt_service': item['stt_service'],
                'stt_time': item['stt_processing_time'],
                'segments_count': len(item['segments']),
                'created_at': item['created_at'],
                'has_summary': bool(item['summary'])
            })

        # 오디오 목록
        audio_data = load_audio_data()
        audio_list = []
        for item in audio_data:
            audio_list.append({
                'id': item['file_hash'],
                'type': 'audio',
                'filename': item['filename'],
                'file_path': item['file_path'],
                'file_size': item['file_size'],
                'duration': item['audio_duration'],
                'stt_service': item['stt_service'],
                'stt_time': item['stt_processing_time'],
                'segments_count': len(item['segments']),
                'created_at': item['created_at'],
                'has_summary': bool(item['summary'])
            })

        # 통계
        stats = get_database_stats()

        return jsonify({
            'success': True,
            'youtube': youtube_list,
            'audio': audio_list,
            'stats': stats
        })

    except Exception as e:
        logging.error(f"데이터 목록 조회 오류: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route("/api/data-management/detail/<data_type>/<data_id>", methods=["GET"])
def api_data_management_detail(data_type, data_id):
    """데이터 상세 조회"""
    try:
        from modules.sqlite_db import load_youtube_data, load_audio_data

        if data_type == 'youtube':
            data = load_youtube_data(video_id=data_id)
            if data and len(data) > 0:
                item = data[0]
                return jsonify({
                    'success': True,
                    'data': {
                        'type': 'youtube',
                        'video_id': item['video_id'],
                        'url': item['youtube_url'],
                        'title': item['title'],
                        'channel': item['channel'],
                        'view_count': item['view_count'],
                        'upload_date': item['upload_date'],
                        'mp3_path': item['mp3_path'],
                        'stt_service': item['stt_service'],
                        'stt_processing_time': item['stt_processing_time'],
                        'created_at': item['created_at'],
                        'summary': item['summary'],
                        'segments': item['segments']
                    }
                })
        elif data_type == 'audio':
            data = load_audio_data(file_hash=data_id)
            if data and len(data) > 0:
                item = data[0]
                return jsonify({
                    'success': True,
                    'data': {
                        'type': 'audio',
                        'file_hash': item['file_hash'],
                        'filename': item['filename'],
                        'file_path': item['file_path'],
                        'file_size': item['file_size'],
                        'audio_duration': item['audio_duration'],
                        'stt_service': item['stt_service'],
                        'stt_processing_time': item['stt_processing_time'],
                        'created_at': item['created_at'],
                        'summary': item['summary'],
                        'segments': item['segments']
                    }
                })

        return jsonify({'success': False, 'error': '데이터를 찾을 수 없습니다.'}), 404

    except Exception as e:
        logging.error(f"데이터 상세 조회 오류: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route("/api/data-management/delete", methods=["POST"])
def api_data_management_delete():
    """데이터 삭제 (SQLite + VectorStore + 실제 파일)"""
    try:
        from modules.sqlite_db import delete_youtube_by_video_id, delete_audio_by_file_hash

        data = request.get_json()
        data_type = data.get('type')
        data_id = data.get('id')

        if not data_type or not data_id:
            return jsonify({'success': False, 'error': '타입과 ID가 필요합니다.'}), 400

        file_path = None
        deleted_count = 0

        # 1. SQLite에서 삭제 (파일 경로 반환)
        if data_type == 'youtube':
            db_success, file_path = delete_youtube_by_video_id(data_id)
            source_type = 'youtube'
        elif data_type == 'audio':
            db_success, file_path = delete_audio_by_file_hash(data_id)
            source_type = 'audio'
        else:
            return jsonify({'success': False, 'error': '잘못된 타입입니다.'}), 400

        if not db_success:
            return jsonify({'success': False, 'error': '삭제할 데이터를 찾을 수 없습니다.'}), 404

        # 2. VectorStore에서 삭제
        try:
            vectorstore_success, deleted_count = delete_from_vectorstore(data_id, source_type)
            if vectorstore_success:
                logging.info(f"✅ VectorStore 삭제 완료: {deleted_count}개 문서")
            else:
                logging.warning(f"⚠️ VectorStore 삭제 실패 (DB는 삭제됨)")
        except Exception as vs_error:
            logging.error(f"⚠️ VectorStore 삭제 중 오류: {vs_error} (DB는 삭제됨)")

        # 3. 실제 파일 삭제
        file_deleted = False
        if file_path:
            # Windows 경로를 Unix 경로로 정규화 (WSL 호환)
            normalized_path = file_path.replace('\\', '/')

            if os.path.exists(normalized_path):
                try:
                    os.remove(normalized_path)
                    file_deleted = True
                    logging.info(f"🗑️ 실제 파일 삭제 완료: {normalized_path}")
                except Exception as file_error:
                    logging.error(f"⚠️ 파일 삭제 중 오류: {file_error} (경로: {normalized_path})")
            else:
                logging.warning(f"⚠️ 파일이 존재하지 않음: {normalized_path}")

        message = f'삭제되었습니다. (VectorStore: {deleted_count}개 문서'
        if file_deleted:
            message += ', 파일 삭제 완료'
        message += ')'

        return jsonify({
            'success': True,
            'message': message
        })

    except Exception as e:
        logging.error(f"데이터 삭제 오류: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


if __name__ == "__main__":
    print("=" * 60)
    print("🎬 영상/오디오 검색 엔진 시작")
    print("=" * 60)
    print("URL: http://localhost:5002")
    print("=" * 60)
    print("기능:")
    print("  [영상 검색 엔진]")
    print("  - YouTube 영상 다운로드 (mp4 폴더)")
    print("  - MP3 변환 (mp3 폴더)")
    print("  - STT 회의록 생성")
    print("")
    print("  [오디오 검색 엔진]")
    print("  - 오디오 파일 업로드 (uploads 폴더)")
    print("  - STT 회의록 생성")
    print("")
    print("  [Retriever 검색 엔진]")
    print("  - YouTube/Audio VectorStore 통합 검색")
    print("  - LangChain Retriever 기반 유사도 검색")
    print("  - 검색 결과 상세 정보 제공")
    print("")
    print("  [공통 기능]")
    print("  - 회의록 요약")
    print("  - AI 채팅 (RAG 기반)")
    print("  - VectorStore (LangChain + ChromaDB)")
    print("  - 처리 이력 캐싱 (SQLite)")
    print("=" * 60)

    # LangChain VectorStore 초기화
    initialize_collections()

    app.run(host="0.0.0.0", port=5002, debug=True)
