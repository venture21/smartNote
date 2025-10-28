"""
영상/오디오 검색 엔진 v0.3 (LangChain 버전)

두 가지 모드 제공:
1. 영상 검색 엔진: YouTube 링크 입력 → 다운로드 → STT → 회의록
2. 오디오 검색 엔진: 오디오 파일 업로드 → STT → 회의록

기능:
- YouTube 영상 다운로드 및 MP3 변환
- 오디오 파일 업로드 지원 (mp3, wav, m4a, flac, ogg)
- STT (Gemini / Clova)
- VectorStore 기반 회의록 저장 및 검색 (LangChain + ChromaDB + Gemini Embedding)
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
from myClovaSpeech import ClovaSpeechClient
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

# LangChain imports
from langchain_community.vectorstores import Chroma
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

# 환경 변수 로드
load_dotenv()

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

# 로깅 설정
logging.basicConfig(level=logging.INFO)

# 설정
MP4_FOLDER = "mp4"
MP3_FOLDER = "mp3"
CSV_FOLDER = "csv"
UPLOADS_FOLDER = "uploads"
CHROMA_DB_FOLDER = "chroma_db_langchain_v0.3"
YOUTUBE_HISTORY_CSV = os.path.join(CSV_FOLDER, "youtube_history_v0.3.csv")
AUDIO_HISTORY_CSV = os.path.join(CSV_FOLDER, "audio_history_v0.3.csv")

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
embeddings = GoogleGenerativeAIEmbeddings(
    model="models/text-embedding-004", google_api_key=os.environ.get("GOOGLE_API_KEY")
)

# LangChain VectorStore (YouTube와 Audio 분리)
youtube_vectorstore = None
audio_vectorstore = None


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


def update_progress(task_id, step, progress, message):
    """진행 상황 업데이트"""
    if task_id not in progress_data:
        progress_data[task_id] = {}

    progress_data[task_id][step] = {
        "progress": progress,
        "message": message,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    logging.info(f"[{task_id}] {step}: {progress}% - {message}")


# YouTube 이력 로드
def load_youtube_history():
    """CSV 파일에서 YouTube 다운로드 이력을 로드합니다."""
    if os.path.exists(YOUTUBE_HISTORY_CSV):
        try:
            df = pd.read_csv(YOUTUBE_HISTORY_CSV, encoding="utf-8-sig")
            # 필수 컬럼 확인 및 추가
            if "summary" not in df.columns:
                df["summary"] = ""
            if "stt_processing_time" not in df.columns:
                df["stt_processing_time"] = 0.0

            # NaN 값 처리
            df["summary"] = df["summary"].fillna("")
            df["stt_processing_time"] = df["stt_processing_time"].fillna(0.0)
            df["view_count"] = df["view_count"].fillna(0)
            df["channel"] = df["channel"].fillna("Unknown")
            df["upload_date"] = df["upload_date"].fillna("")

            logging.info(f"📋 YouTube 이력 로드 완료: {len(df)}개 항목")
            return df
        except Exception as e:
            logging.error(f"YouTube 이력 로드 오류: {e}")
            return pd.DataFrame(
                columns=[
                    "youtube_url",
                    "video_id",
                    "title",
                    "channel",
                    "view_count",
                    "upload_date",
                    "mp3_path",
                    "segments_json",
                    "stt_service",
                    "stt_processing_time",
                    "created_at",
                    "summary",
                ]
            )
    else:
        return pd.DataFrame(
            columns=[
                "youtube_url",
                "video_id",
                "title",
                "channel",
                "view_count",
                "upload_date",
                "mp3_path",
                "segments_json",
                "stt_service",
                "stt_processing_time",
                "created_at",
                "summary",
            ]
        )


def save_youtube_history(df):
    """YouTube 이력을 CSV 파일에 저장합니다."""
    try:
        df.to_csv(YOUTUBE_HISTORY_CSV, index=False, encoding="utf-8-sig")
        logging.info(f"💾 YouTube 이력 저장 완료: {len(df)}개 항목")
    except Exception as e:
        logging.error(f"YouTube 이력 저장 오류: {e}")


# 오디오 이력 로드
def load_audio_history():
    """CSV 파일에서 오디오 파일 처리 이력을 로드합니다."""
    if os.path.exists(AUDIO_HISTORY_CSV):
        try:
            df = pd.read_csv(AUDIO_HISTORY_CSV, encoding="utf-8-sig")
            # 필수 컬럼 확인 및 추가
            if "summary" not in df.columns:
                df["summary"] = ""
            if "stt_processing_time" not in df.columns:
                df["stt_processing_time"] = 0.0
            if "audio_duration" not in df.columns:
                df["audio_duration"] = 0.0

            # NaN 값 처리
            df["summary"] = df["summary"].fillna("")
            df["stt_processing_time"] = df["stt_processing_time"].fillna(0.0)
            df["audio_duration"] = df["audio_duration"].fillna(0.0)

            logging.info(f"📋 오디오 이력 로드 완료: {len(df)}개 항목")
            return df
        except Exception as e:
            logging.error(f"오디오 이력 로드 오류: {e}")
            return pd.DataFrame(
                columns=[
                    "file_hash",
                    "filename",
                    "file_path",
                    "file_size",
                    "audio_duration",
                    "segments_json",
                    "stt_service",
                    "stt_processing_time",
                    "created_at",
                    "summary",
                ]
            )
    else:
        return pd.DataFrame(
            columns=[
                "file_hash",
                "filename",
                "file_path",
                "file_size",
                "audio_duration",
                "segments_json",
                "stt_service",
                "stt_processing_time",
                "created_at",
                "summary",
            ]
        )


def save_audio_history(df):
    """오디오 이력을 CSV 파일에 저장합니다."""
    try:
        df.to_csv(AUDIO_HISTORY_CSV, index=False, encoding="utf-8-sig")
        logging.info(f"💾 오디오 이력 저장 완료: {len(df)}개 항목")
    except Exception as e:
        logging.error(f"오디오 이력 저장 오류: {e}")


def get_gemini_client():
    """Gemini 클라이언트 생성"""
    api_key = os.environ.get("GOOGLE_API_KEY")
    if api_key:
        return genai.Client(api_key=api_key)
    else:
        return genai.Client()


def initialize_vectorstores():
    """LangChain VectorStore 초기화"""
    global youtube_vectorstore, audio_vectorstore

    try:
        # YouTube VectorStore
        youtube_vectorstore = Chroma(
            collection_name="youtube_transcripts_langchain_v0.3",
            embedding_function=embeddings,
            persist_directory=os.path.join(CHROMA_DB_FOLDER, "youtube"),
        )

        # Audio VectorStore
        audio_vectorstore = Chroma(
            collection_name="audio_transcripts_langchain_v0.3",
            embedding_function=embeddings,
            persist_directory=os.path.join(CHROMA_DB_FOLDER, "audio"),
        )

        logging.info(f"✅ LangChain VectorStore 초기화 완료")

        # 문서 개수 확인
        try:
            youtube_count = len(youtube_vectorstore.get()["ids"])
            audio_count = len(audio_vectorstore.get()["ids"])
            logging.info(f"   - YouTube VectorStore: {youtube_count} documents")
            logging.info(f"   - Audio VectorStore: {audio_count} documents")
        except:
            logging.info(f"   - VectorStore 문서 개수 확인 불가 (빈 컬렉션일 수 있음)")

    except Exception as e:
        logging.error(f"❌ LangChain VectorStore 초기화 오류: {e}")


def store_segments_in_vectordb(
    segments, source_id, source_type="youtube", filename=None
):
    """
    세그먼트를 LangChain VectorDB에 저장

    Args:
        segments: STT로 추출된 세그먼트 리스트
        source_id: YouTube video_id 또는 audio file_hash
        source_type: "youtube" 또는 "audio"
        filename: 오디오 파일 이름 (오디오 타입인 경우)
    """
    try:
        if not segments:
            logging.warning("⚠️ 저장할 세그먼트가 없습니다.")
            return False

        # VectorStore 선택
        vectorstore = (
            youtube_vectorstore if source_type == "youtube" else audio_vectorstore
        )

        # LangChain Document 객체 생성
        documents = []
        for idx, segment in enumerate(segments):
            text = segment.get("text", "").strip()
            if not text:
                continue

            # 메타데이터 구성
            metadata = {
                "source_id": source_id,
                "source_type": source_type,
                "segment_index": idx,
                "speaker": segment.get("speaker", "Unknown"),
                "start_time": segment.get("start", 0.0),
                "end_time": segment.get("end", 0.0),
            }

            if filename:
                metadata["filename"] = filename

            # Document 생성
            doc = Document(page_content=text, metadata=metadata)
            documents.append(doc)

        if not documents:
            logging.warning("⚠️ 유효한 문서가 없습니다.")
            return False

        # VectorStore에 추가
        logging.info(f"📥 LangChain VectorStore에 {len(documents)}개 문서 저장 중...")
        vectorstore.add_documents(documents)

        logging.info(f"✅ VectorStore 저장 완료 ({source_type}: {source_id})")
        return True

    except Exception as e:
        logging.error(f"❌ VectorStore 저장 오류: {e}")
        import traceback

        traceback.print_exc()
        return False


def search_vectordb(query, source_id, source_type="youtube", n_results=5):
    """
    LangChain VectorDB에서 검색 (Retriever 사용)

    Args:
        query: 검색 쿼리
        source_id: YouTube video_id 또는 audio file_hash
        source_type: "youtube" 또는 "audio"
        n_results: 반환할 결과 개수

    Returns:
        검색 결과 리스트
    """
    try:
        # VectorStore 선택
        vectorstore = (
            youtube_vectorstore if source_type == "youtube" else audio_vectorstore
        )

        # Retriever 생성 (특정 source_id로 필터링)
        retriever = vectorstore.as_retriever(
            search_type="similarity",
            search_kwargs={"k": n_results, "filter": {"source_id": source_id}},
        )

        # 검색 실행
        docs = retriever.get_relevant_documents(query)

        # 결과 포맷팅
        results = []
        for doc in docs:
            results.append(
                {
                    "document": doc.page_content,
                    "metadata": doc.metadata,
                    "score": None,  # LangChain의 기본 retriever는 score를 반환하지 않음
                }
            )

        logging.info(f"🔍 검색 완료: {len(results)}개 결과 (query: {query[:50]}...)")
        return results

    except Exception as e:
        logging.error(f"❌ VectorDB 검색 오류: {e}")
        import traceback

        traceback.print_exc()
        return []


def search_vectordb_with_score(query, source_id, source_type="youtube", n_results=5):
    """
    LangChain VectorDB에서 유사도 점수와 함께 검색

    Args:
        query: 검색 쿼리
        source_id: YouTube video_id 또는 audio file_hash
        source_type: "youtube" 또는 "audio"
        n_results: 반환할 결과 개수

    Returns:
        검색 결과 리스트 (점수 포함)
    """
    try:
        # VectorStore 선택
        vectorstore = (
            youtube_vectorstore if source_type == "youtube" else audio_vectorstore
        )

        # 유사도 검색 (점수 포함)
        docs_with_scores = vectorstore.similarity_search_with_score(
            query, k=n_results, filter={"source_id": source_id}
        )

        # 결과 포맷팅
        results = []
        for doc, score in docs_with_scores:
            results.append(
                {
                    "document": doc.page_content,
                    "metadata": doc.metadata,
                    "score": float(score),  # 거리 점수 (낮을수록 유사)
                }
            )

        logging.info(
            f"🔍 검색 완료 (점수 포함): {len(results)}개 결과 (query: {query[:50]}...)"
        )
        return results

    except Exception as e:
        logging.error(f"❌ VectorDB 검색 오류: {e}")
        import traceback

        traceback.print_exc()
        return []


# STT 처리 함수들은 원본 파일과 동일하게 유지
def process_stt_gemini(mp3_path):
    """Gemini STT 처리"""
    try:
        logging.info("🎤 Gemini STT 시작...")
        start_time = time.time()

        client = get_gemini_client()

        # 오디오 파일 업로드
        logging.info("📤 오디오 파일 업로드 중...")
        audio_file = client.files.upload(path=mp3_path)
        logging.info(f"✅ 업로드 완료: {audio_file.name}")

        # STT 실행
        logging.info("🔄 STT 처리 중...")
        prompt = """이 오디오를 한국어로 정확하게 전사해 주세요. 
        다음 형식으로 작성해 주세요:
        - 화자 구분이 가능하면 "화자1:", "화자2:" 등으로 표시
        - 타임스탬프 포함
        - 문장 단위로 구분
        """

        response = client.models.generate_content(
            model="gemini-2.0-flash-exp", contents=[prompt, audio_file]
        )

        transcript_text = response.text
        elapsed_time = time.time() - start_time

        logging.info(f"✅ Gemini STT 완료 (소요 시간: {elapsed_time:.2f}초)")

        # 세그먼트 파싱 (간단한 버전)
        segments = []
        lines = transcript_text.split("\n")
        for i, line in enumerate(lines):
            line = line.strip()
            if line:
                segments.append(
                    {
                        "speaker": "Speaker",
                        "start": i * 5.0,  # 임시 타임스탬프
                        "end": (i + 1) * 5.0,
                        "text": line,
                    }
                )

        return segments, elapsed_time

    except Exception as e:
        logging.error(f"❌ Gemini STT 오류: {e}")
        import traceback

        traceback.print_exc()
        return [], 0.0


def process_stt_clova(mp3_path):
    """Clova STT 처리"""
    try:
        logging.info("🎤 Clova STT 시작...")
        start_time = time.time()

        invoke_url = os.environ.get("CLOVA_INVOKE_URL")
        secret_key = os.environ.get("CLOVA_SECRET_KEY")

        if not invoke_url or not secret_key:
            raise ValueError("Clova API 설정이 없습니다.")

        clova_client = ClovaSpeechClient(invoke_url, secret_key)

        # Clova STT 실행 (diarization 활성화)
        res = clova_client.req_upload(
            file=mp3_path, completion="sync", diarization={"enable": True}
        )

        elapsed_time = time.time() - start_time

        if "segments" not in res:
            raise ValueError("Clova STT 응답에 segments가 없습니다.")

        segments = res["segments"]
        logging.info(
            f"✅ Clova STT 완료: {len(segments)}개 세그먼트 (소요 시간: {elapsed_time:.2f}초)"
        )

        return segments, elapsed_time

    except Exception as e:
        logging.error(f"❌ Clova STT 오류: {e}")
        import traceback

        traceback.print_exc()
        return [], 0.0


# YouTube 다운로드 함수
def download_youtube_video(youtube_url, task_id):
    """YouTube 영상 다운로드 및 MP3 변환"""
    try:
        update_progress(task_id, "download", 10, "YouTube 영상 정보 확인 중...")

        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": os.path.join(MP4_FOLDER, "%(id)s.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(youtube_url, download=False)
            video_id = info["id"]
            title = info.get("title", "Unknown")
            channel = info.get("uploader", "Unknown")
            view_count = info.get("view_count", 0)
            upload_date = info.get("upload_date", "")

            update_progress(task_id, "download", 30, f"'{title}' 다운로드 중...")

            # 다운로드
            ydl.download([youtube_url])

        # MP3 변환
        update_progress(task_id, "download", 70, "MP3 변환 중...")

        downloaded_file = None
        for ext in ["webm", "m4a", "mp3", "opus"]:
            potential_file = os.path.join(MP4_FOLDER, f"{video_id}.{ext}")
            if os.path.exists(potential_file):
                downloaded_file = potential_file
                break

        if not downloaded_file:
            raise FileNotFoundError(f"다운로드된 파일을 찾을 수 없습니다: {video_id}")

        mp3_path = os.path.join(MP3_FOLDER, f"{video_id}.mp3")

        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                downloaded_file,
                "-vn",
                "-ar",
                "16000",
                "-ac",
                "1",
                "-b:a",
                "128k",
                mp3_path,
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        update_progress(task_id, "download", 100, "다운로드 완료")

        return {
            "video_id": video_id,
            "title": title,
            "channel": channel,
            "view_count": view_count,
            "upload_date": upload_date,
            "mp3_path": mp3_path,
        }

    except Exception as e:
        logging.error(f"YouTube 다운로드 오류: {e}")
        update_progress(task_id, "download", 0, f"오류 발생: {str(e)}")
        raise


# Flask 라우트들
@app.route("/")
def index():
    """메인 페이지"""
    return render_template("index.html")


@app.route("/api/youtube/process", methods=["POST"])
def process_youtube():
    """YouTube 영상 처리 API"""
    try:
        data = request.get_json()
        youtube_url = data.get("youtube_url", "").strip()
        stt_service = data.get("stt_service", "gemini")

        if not youtube_url:
            return (
                jsonify({"success": False, "error": "YouTube URL을 입력해주세요."}),
                400,
            )

        # Task ID 생성
        task_id = secrets.token_hex(8)
        session_id = secrets.token_hex(16)

        # 백그라운드에서 처리
        thread = threading.Thread(
            target=process_youtube_background,
            args=(youtube_url, stt_service, task_id, session_id),
        )
        thread.start()

        return jsonify(
            {
                "success": True,
                "task_id": task_id,
                "session_id": session_id,
                "message": "처리가 시작되었습니다.",
            }
        )

    except Exception as e:
        import traceback

        traceback.print_exc()
        return jsonify({"success": False, "error": f"처리 중 오류 발생: {str(e)}"}), 500


def process_youtube_background(youtube_url, stt_service, task_id, session_id):
    """YouTube 영상 백그라운드 처리"""
    try:
        # 1. 이력 확인
        history_df = load_youtube_history()

        # video_id 추출
        import re

        video_id_match = re.search(r"(?:v=|/)([0-9A-Za-z_-]{11}).*", youtube_url)
        if not video_id_match:
            update_progress(task_id, "error", 0, "유효하지 않은 YouTube URL입니다.")
            return

        video_id = video_id_match.group(1)

        # 기존 데이터 확인
        existing = history_df[history_df["video_id"] == video_id]

        if not existing.empty:
            # 캐시된 데이터 사용
            update_progress(task_id, "cache", 100, "캐시된 데이터 사용")

            row = existing.iloc[0]
            segments = json.loads(row["segments_json"])

            session_data[session_id] = {
                "source_type": "youtube",
                "video_id": video_id,
                "title": row["title"],
                "segments": segments,
                "summary": row.get("summary", ""),
                "chat_history": [],
            }

            update_progress(task_id, "complete", 100, "처리 완료 (캐시 사용)")
            return

        # 2. 다운로드
        download_result = download_youtube_video(youtube_url, task_id)

        # 3. STT 처리
        update_progress(task_id, "stt", 10, f"{stt_service.upper()} STT 처리 중...")

        if stt_service == "gemini":
            segments, stt_time = process_stt_gemini(download_result["mp3_path"])
        else:
            segments, stt_time = process_stt_clova(download_result["mp3_path"])

        update_progress(task_id, "stt", 100, "STT 처리 완료")

        # 4. VectorDB 저장
        update_progress(task_id, "vectordb", 50, "VectorDB 저장 중...")
        store_segments_in_vectordb(segments, source_id=video_id, source_type="youtube")
        update_progress(task_id, "vectordb", 100, "VectorDB 저장 완료")

        # 5. 이력 저장
        new_row = {
            "youtube_url": youtube_url,
            "video_id": video_id,
            "title": download_result["title"],
            "channel": download_result["channel"],
            "view_count": download_result["view_count"],
            "upload_date": download_result["upload_date"],
            "mp3_path": download_result["mp3_path"],
            "segments_json": json.dumps(segments, ensure_ascii=False),
            "stt_service": stt_service,
            "stt_processing_time": stt_time,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "summary": "",
        }

        history_df = pd.concat([history_df, pd.DataFrame([new_row])], ignore_index=True)
        save_youtube_history(history_df)

        # 6. 세션 데이터 저장
        session_data[session_id] = {
            "source_type": "youtube",
            "video_id": video_id,
            "title": download_result["title"],
            "segments": segments,
            "summary": "",
            "chat_history": [],
        }

        update_progress(task_id, "complete", 100, "모든 처리 완료")

    except Exception as e:
        import traceback

        traceback.print_exc()
        update_progress(task_id, "error", 0, f"오류 발생: {str(e)}")


@app.route("/api/audio/process", methods=["POST"])
def process_audio():
    """오디오 파일 처리 API"""
    try:
        if "audio_file" not in request.files:
            return jsonify({"success": False, "error": "오디오 파일이 없습니다."}), 400

        audio_file = request.files["audio_file"]
        stt_service = request.form.get("stt_service", "gemini")

        if audio_file.filename == "":
            return (
                jsonify({"success": False, "error": "파일이 선택되지 않았습니다."}),
                400,
            )

        if not allowed_file(audio_file.filename):
            return (
                jsonify(
                    {
                        "success": False,
                        "error": f"허용되지 않는 파일 형식입니다. 허용 형식: {', '.join(ALLOWED_AUDIO_EXTENSIONS)}",
                    }
                ),
                400,
            )

        # 파일 저장
        filename = secure_filename(audio_file.filename)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_filename = f"{timestamp}_{filename}"
        file_path = os.path.join(UPLOADS_FOLDER, unique_filename)
        audio_file.save(file_path)

        # MP3 변환 (필요한 경우)
        if not filename.lower().endswith(".mp3"):
            mp3_path = os.path.join(
                UPLOADS_FOLDER, f"{timestamp}_{os.path.splitext(filename)[0]}.mp3"
            )
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    file_path,
                    "-vn",
                    "-ar",
                    "16000",
                    "-ac",
                    "1",
                    "-b:a",
                    "128k",
                    mp3_path,
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            file_path = mp3_path

        # Task ID 생성
        task_id = secrets.token_hex(8)
        session_id = secrets.token_hex(16)

        # 백그라운드에서 처리
        thread = threading.Thread(
            target=process_audio_background,
            args=(file_path, filename, stt_service, task_id, session_id),
        )
        thread.start()

        return jsonify(
            {
                "success": True,
                "task_id": task_id,
                "session_id": session_id,
                "message": "처리가 시작되었습니다.",
            }
        )

    except Exception as e:
        import traceback

        traceback.print_exc()
        return jsonify({"success": False, "error": f"처리 중 오류 발생: {str(e)}"}), 500


def process_audio_background(file_path, filename, stt_service, task_id, session_id):
    """오디오 파일 백그라운드 처리"""
    try:
        # 1. 파일 해시 계산
        update_progress(task_id, "hash", 10, "파일 해시 계산 중...")
        file_hash = calculate_file_hash(file_path)

        # 2. 이력 확인
        history_df = load_audio_history()
        existing = history_df[history_df["file_hash"] == file_hash]

        if not existing.empty:
            # 캐시된 데이터 사용
            update_progress(task_id, "cache", 100, "캐시된 데이터 사용")

            row = existing.iloc[0]
            segments = json.loads(row["segments_json"])

            session_data[session_id] = {
                "source_type": "audio",
                "file_hash": file_hash,
                "filename": filename,
                "segments": segments,
                "summary": row.get("summary", ""),
                "chat_history": [],
            }

            update_progress(task_id, "complete", 100, "처리 완료 (캐시 사용)")
            return

        # 3. 오디오 정보 추출
        update_progress(task_id, "info", 30, "오디오 정보 추출 중...")
        file_size = os.path.getsize(file_path)
        audio_duration = get_audio_duration(file_path)

        # 4. STT 처리
        update_progress(task_id, "stt", 40, f"{stt_service.upper()} STT 처리 중...")

        if stt_service == "gemini":
            segments, stt_time = process_stt_gemini(file_path)
        else:
            segments, stt_time = process_stt_clova(file_path)

        update_progress(task_id, "stt", 80, "STT 처리 완료")

        # 5. VectorDB 저장
        update_progress(task_id, "vectordb", 85, "VectorDB 저장 중...")
        store_segments_in_vectordb(
            segments, source_id=file_hash, source_type="audio", filename=filename
        )
        update_progress(task_id, "vectordb", 95, "VectorDB 저장 완료")

        # 6. 이력 저장
        new_row = {
            "file_hash": file_hash,
            "filename": filename,
            "file_path": file_path,
            "file_size": file_size,
            "audio_duration": audio_duration,
            "segments_json": json.dumps(segments, ensure_ascii=False),
            "stt_service": stt_service,
            "stt_processing_time": stt_time,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "summary": "",
        }

        history_df = pd.concat([history_df, pd.DataFrame([new_row])], ignore_index=True)
        save_audio_history(history_df)

        # 7. 세션 데이터 저장
        session_data[session_id] = {
            "source_type": "audio",
            "file_hash": file_hash,
            "filename": filename,
            "segments": segments,
            "summary": "",
            "chat_history": [],
        }

        update_progress(task_id, "complete", 100, "모든 처리 완료")

    except Exception as e:
        import traceback

        traceback.print_exc()
        update_progress(task_id, "error", 0, f"오류 발생: {str(e)}")


@app.route("/api/transcript", methods=["POST"])
def get_transcript():
    """회의록 조회 API"""
    try:
        data = request.get_json()
        session_id = data.get("session_id")

        if not session_id or session_id not in session_data:
            return jsonify({"success": False, "error": "세션 데이터가 없습니다."}), 400

        session_info = session_data[session_id]
        segments = session_info.get("segments", [])

        return jsonify(
            {
                "success": True,
                "segments": segments,
                "title": session_info.get("title") or session_info.get("filename"),
                "summary": session_info.get("summary", ""),
            }
        )

    except Exception as e:
        import traceback

        traceback.print_exc()
        return (
            jsonify({"success": False, "error": f"회의록 조회 중 오류 발생: {str(e)}"}),
            500,
        )


@app.route("/api/summarize", methods=["POST"])
def summarize_transcript():
    """회의록 요약 API"""
    try:
        data = request.get_json()
        session_id = data.get("session_id")

        if not session_id or session_id not in session_data:
            return jsonify({"success": False, "error": "세션 데이터가 없습니다."}), 400

        session_info = session_data[session_id]
        segments = session_info.get("segments", [])

        if not segments:
            return jsonify({"success": False, "error": "회의록이 없습니다."}), 400

        # 전체 회의록 텍스트 생성
        transcript_text = "\n\n".join(
            [
                f"화자 {seg.get('speaker', 'Unknown')} ({seg.get('start', 0):.1f}초): {seg.get('text', '')}"
                for seg in segments
            ]
        )

        client = get_gemini_client()

        prompt = f"""다음 회의록을 요약해 주세요. 다음 항목을 포함해 주세요:

1. 주요 논의 주제
2. 주요 결정 사항
3. 액션 아이템 (있는 경우)
4. 중요한 발언이나 의견

회의록:
{transcript_text}

요약을 마크다운 형식으로 작성해 주세요."""

        logging.info("🤖 Gemini로 요약 생성 중...")

        response = client.models.generate_content(
            model="gemini-2.5-pro",
            contents=prompt,
        )

        summary = response.text.strip()
        logging.info("✅ 요약 생성 완료")

        # CSV에 요약 저장
        if session_id and session_id in session_data:
            source_type = session_data[session_id].get("source_type")

            if source_type == "youtube":
                video_id = session_data[session_id].get("video_id")
                if video_id:
                    try:
                        history_df = load_youtube_history()
                        mask = history_df["video_id"] == video_id
                        if mask.any():
                            history_df.loc[mask, "summary"] = summary
                            save_youtube_history(history_df)
                            logging.info(
                                f"💾 요약이 YouTube CSV에 저장되었습니다 (video_id: {video_id})"
                            )
                    except Exception as e:
                        logging.error(f"요약 저장 오류: {e}")

            elif source_type == "audio":
                file_hash = session_data[session_id].get("file_hash")
                if file_hash:
                    try:
                        history_df = load_audio_history()
                        mask = history_df["file_hash"] == file_hash
                        if mask.any():
                            history_df.loc[mask, "summary"] = summary
                            save_audio_history(history_df)
                            logging.info(
                                f"💾 요약이 오디오 CSV에 저장되었습니다 (file_hash: {file_hash})"
                            )
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
    """회의록 기반 채팅 API (RAG with LangChain Retriever)"""
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

        # LangChain Retriever로 VectorDB 검색 (RAG)
        logging.info(f"🔍 LangChain Retriever 검색: {user_message}")
        search_results = search_vectordb_with_score(
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
        logging.info(f"✅ AI 응답 생성 완료 (LangChain RAG 기반)")

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


if __name__ == "__main__":
    print("=" * 60)
    print("🎬 영상/오디오 검색 엔진 v0.3 (LangChain) 시작")
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
    print("  [공통 기능]")
    print("  - LangChain VectorStore (ChromaDB + Gemini Embeddings)")
    print("  - LangChain Retriever로 RAG 검색")
    print("  - 회의록 요약")
    print("  - AI 채팅")
    print("  - 처리 이력 캐싱 (CSV)")
    print("=" * 60)

    # VectorStore 초기화
    initialize_vectorstores()

    app.run(host="0.0.0.0", port=5002, debug=True)
