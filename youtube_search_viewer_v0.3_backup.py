"""
영상/오디오 검색 엔진 v0.3

두 가지 모드 제공:
1. 영상 검색 엔진: YouTube 링크 입력 → 다운로드 → STT → 회의록
2. 오디오 검색 엔진: 오디오 파일 업로드 → STT → 회의록

기능:
- YouTube 영상 다운로드 및 MP3 변환
- 오디오 파일 업로드 지원 (mp3, wav, m4a, flac, ogg)
- STT (Gemini / Clova)
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
import chromadb
from chromadb.config import Settings

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
CHROMA_DB_FOLDER = "chroma_db_v0.3"
YOUTUBE_HISTORY_CSV = os.path.join(CSV_FOLDER, "youtube_history_v0.3.csv")
AUDIO_HISTORY_CSV = os.path.join(CSV_FOLDER, "audio_history_v0.3.csv")

app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500MB max

# 허용된 오디오 파일 확장자
ALLOWED_AUDIO_EXTENSIONS = {'mp3', 'wav', 'm4a', 'flac', 'ogg', 'mp4', 'avi', 'mov', 'mkv'}

# 폴더 생성
for folder in [MP4_FOLDER, MP3_FOLDER, CSV_FOLDER, UPLOADS_FOLDER, CHROMA_DB_FOLDER]:
    os.makedirs(folder, exist_ok=True)

# 세션별 데이터 저장
session_data = {}

# 진행 상황 저장
progress_data = {}

# ChromaDB 클라이언트 초기화
chroma_client = chromadb.PersistentClient(path=CHROMA_DB_FOLDER)

# ChromaDB 컬렉션 (YouTube와 Audio 분리)
youtube_collection = None
audio_collection = None


def allowed_file(filename):
    """허용된 파일 확장자인지 확인"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_AUDIO_EXTENSIONS


def calculate_file_hash(file_path):
    """파일의 MD5 해시를 계산하여 고유 ID 생성"""
    hasher = hashlib.md5()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def get_audio_duration(file_path):
    """오디오 파일의 길이를 초 단위로 반환"""
    try:
        audio = MutagenFile(file_path)
        if audio is not None and hasattr(audio.info, 'length'):
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
        'progress': progress,
        'message': message,
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    logging.info(f"[{task_id}] {step}: {progress}% - {message}")


# YouTube 이력 로드
def load_youtube_history():
    """CSV 파일에서 YouTube 다운로드 이력을 로드합니다."""
    if os.path.exists(YOUTUBE_HISTORY_CSV):
        try:
            df = pd.read_csv(YOUTUBE_HISTORY_CSV, encoding='utf-8-sig')
            # 필수 컬럼 확인 및 추가
            if 'summary' not in df.columns:
                df['summary'] = ''
            if 'stt_processing_time' not in df.columns:
                df['stt_processing_time'] = 0.0

            # NaN 값 처리
            df['summary'] = df['summary'].fillna('')
            df['stt_processing_time'] = df['stt_processing_time'].fillna(0.0)
            df['view_count'] = df['view_count'].fillna(0)
            df['channel'] = df['channel'].fillna('Unknown')
            df['upload_date'] = df['upload_date'].fillna('')

            logging.info(f"📋 YouTube 이력 로드 완료: {len(df)}개 항목")
            return df
        except Exception as e:
            logging.error(f"YouTube 이력 로드 오류: {e}")
            return pd.DataFrame(columns=['youtube_url', 'video_id', 'title', 'channel', 'view_count', 'upload_date', 'mp3_path', 'segments_json', 'stt_service', 'stt_processing_time', 'created_at', 'summary'])
    else:
        return pd.DataFrame(columns=['youtube_url', 'video_id', 'title', 'channel', 'view_count', 'upload_date', 'mp3_path', 'segments_json', 'stt_service', 'stt_processing_time', 'created_at', 'summary'])


def save_youtube_history(df):
    """YouTube 이력을 CSV 파일에 저장합니다."""
    try:
        df.to_csv(YOUTUBE_HISTORY_CSV, index=False, encoding='utf-8-sig')
        logging.info(f"💾 YouTube 이력 저장 완료: {len(df)}개 항목")
    except Exception as e:
        logging.error(f"YouTube 이력 저장 오류: {e}")


# 오디오 이력 로드
def load_audio_history():
    """CSV 파일에서 오디오 파일 처리 이력을 로드합니다."""
    if os.path.exists(AUDIO_HISTORY_CSV):
        try:
            df = pd.read_csv(AUDIO_HISTORY_CSV, encoding='utf-8-sig')
            # 필수 컬럼 확인 및 추가
            if 'summary' not in df.columns:
                df['summary'] = ''
            if 'stt_processing_time' not in df.columns:
                df['stt_processing_time'] = 0.0
            if 'audio_duration' not in df.columns:
                df['audio_duration'] = 0.0

            # NaN 값 처리
            df['summary'] = df['summary'].fillna('')
            df['stt_processing_time'] = df['stt_processing_time'].fillna(0.0)
            df['audio_duration'] = df['audio_duration'].fillna(0.0)

            logging.info(f"📋 오디오 이력 로드 완료: {len(df)}개 항목")
            return df
        except Exception as e:
            logging.error(f"오디오 이력 로드 오류: {e}")
            return pd.DataFrame(columns=['file_hash', 'filename', 'file_path', 'file_size', 'audio_duration', 'segments_json', 'stt_service', 'stt_processing_time', 'created_at', 'summary'])
    else:
        return pd.DataFrame(columns=['file_hash', 'filename', 'file_path', 'file_size', 'audio_duration', 'segments_json', 'stt_service', 'stt_processing_time', 'created_at', 'summary'])


def save_audio_history(df):
    """오디오 이력을 CSV 파일에 저장합니다."""
    try:
        df.to_csv(AUDIO_HISTORY_CSV, index=False, encoding='utf-8-sig')
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


def initialize_collections():
    """ChromaDB 컬렉션 초기화"""
    global youtube_collection, audio_collection

    try:
        # YouTube 컬렉션
        youtube_collection = chroma_client.get_or_create_collection(
            name="youtube_transcripts_v0.3",
            metadata={"description": "YouTube video transcripts with embeddings"}
        )

        # Audio 컬렉션
        audio_collection = chroma_client.get_or_create_collection(
            name="audio_transcripts_v0.3",
            metadata={"description": "Audio file transcripts with embeddings"}
        )

        logging.info(f"✅ ChromaDB 컬렉션 초기화 완료")
        logging.info(f"   - YouTube 컬렉션: {youtube_collection.count()} documents")
        logging.info(f"   - Audio 컬렉션: {audio_collection.count()} documents")
    except Exception as e:
        logging.error(f"❌ ChromaDB 컬렉션 초기화 오류: {e}")


def get_gemini_embedding(text):
    """Gemini를 사용하여 텍스트 임베딩 생성"""
    try:
        client = get_gemini_client()

        # Gemini embedding API 사용
        result = client.models.embed_content(
            model="models/text-embedding-004",
            content=text
        )

        embedding = result['embedding']
        return embedding
    except Exception as e:
        logging.error(f"❌ Gemini 임베딩 생성 오류: {e}")
        return None


def store_segments_in_vectordb(segments, source_id, source_type="youtube", filename=None):
    """
    세그먼트를 VectorDB에 저장

    Args:
        segments: STT로 추출된 세그먼트 리스트
        source_id: YouTube video_id 또는 audio file_hash
        source_type: "youtube" 또는 "audio"
        filename: 오디오 파일명 (오디오일 경우)
    """
    try:
        collection = youtube_collection if source_type == "youtube" else audio_collection

        if not collection:
            logging.error("❌ ChromaDB 컬렉션이 초기화되지 않았습니다.")
            return False

        # 기존 데이터 삭제 (같은 source_id)
        try:
            existing_ids = collection.get(
                where={"source_id": source_id}
            )
            if existing_ids and existing_ids['ids']:
                collection.delete(ids=existing_ids['ids'])
                logging.info(f"🗑️ 기존 데이터 삭제: {len(existing_ids['ids'])}개 세그먼트")
        except Exception as e:
            logging.warning(f"기존 데이터 삭제 중 오류 (무시): {e}")

        documents = []
        metadatas = []
        ids = []
        embeddings = []

        for segment in segments:
            # Document (content)
            text = segment['text']
            documents.append(text)

            # Metadata
            metadata = {
                "source_id": source_id,
                "source_type": source_type,
                "speaker": str(segment['speaker']),
                "start_time": float(segment['start_time']),
                "confidence": float(segment.get('confidence', 0.0)),
                "segment_id": int(segment['id'])
            }

            if source_type == "audio" and filename:
                metadata["filename"] = filename

            metadatas.append(metadata)

            # ID: source_id + segment_id
            doc_id = f"{source_id}_seg_{segment['id']}"
            ids.append(doc_id)

            # Embedding 생성
            embedding = get_gemini_embedding(text)
            if embedding:
                embeddings.append(embedding)
            else:
                logging.error(f"❌ 세그먼트 {segment['id']} 임베딩 생성 실패")
                return False

        # ChromaDB에 저장
        collection.add(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
            embeddings=embeddings
        )

        logging.info(f"✅ VectorDB 저장 완료: {len(segments)}개 세그먼트 (source: {source_id})")
        return True

    except Exception as e:
        logging.error(f"❌ VectorDB 저장 오류: {e}")
        import traceback
        traceback.print_exc()
        return False


def search_vectordb(query, source_id=None, source_type=None, n_results=5):
    """
    VectorDB에서 검색

    Args:
        query: 검색 쿼리
        source_id: 특정 source로 제한 (선택)
        source_type: "youtube" 또는 "audio" (선택)
        n_results: 반환할 결과 수

    Returns:
        검색 결과 리스트
    """
    try:
        # 쿼리 임베딩 생성
        query_embedding = get_gemini_embedding(query)
        if not query_embedding:
            logging.error("❌ 쿼리 임베딩 생성 실패")
            return []

        # 검색할 컬렉션 결정
        collections_to_search = []
        if source_type == "youtube":
            collections_to_search = [youtube_collection]
        elif source_type == "audio":
            collections_to_search = [audio_collection]
        else:
            collections_to_search = [youtube_collection, audio_collection]

        all_results = []

        for collection in collections_to_search:
            if not collection:
                continue

            # where 필터 구성
            where_filter = None
            if source_id:
                where_filter = {"source_id": source_id}

            # 검색 수행
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=n_results,
                where=where_filter
            )

            # 결과 파싱
            if results and results['ids'] and len(results['ids']) > 0:
                for i in range(len(results['ids'][0])):
                    all_results.append({
                        'id': results['ids'][0][i],
                        'document': results['documents'][0][i],
                        'metadata': results['metadatas'][0][i],
                        'distance': results['distances'][0][i] if 'distances' in results else None
                    })

        # 거리 기준으로 정렬
        all_results.sort(key=lambda x: x.get('distance', float('inf')))

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
            update_progress(task_id, 'download', 0, 'YouTube 오디오 다운로드 시작')

        logging.info(f'🎵 YouTube 오디오 다운로드 시작: {url}')

        # 진행률 콜백 함수
        def progress_hook(d):
            if task_id and d['status'] == 'downloading':
                downloaded = d.get('downloaded_bytes', 0)
                total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)

                if total > 0:
                    percent = int((downloaded / total) * 100)
                    speed = d.get('speed', 0)
                    eta = d.get('eta', 0)

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

                    message = f"오디오 다운로드 중... {speed_str} (남은 시간: {eta_str})"
                    update_progress(task_id, 'download', percent, message)
            elif task_id and d['status'] == 'finished':
                update_progress(task_id, 'download', 90, '오디오 다운로드 완료, MP3 변환 중...')
            elif task_id and d['status'] == 'processing':
                update_progress(task_id, 'download', 95, 'MP3 변환 중...')

        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': os.path.join(MP3_FOLDER, '%(title).50s-%(id)s.%(ext)s'),
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'progress_hooks': [progress_hook],
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            video_id = info_dict.get('id', None)
            video_title = info_dict.get('title', None)
            channel = info_dict.get('channel', info_dict.get('uploader', 'Unknown'))
            view_count = info_dict.get('view_count', 0)
            upload_date = info_dict.get('upload_date', '')

            # upload_date 포맷 변환 (YYYYMMDD -> YYYY-MM-DD)
            if upload_date and len(upload_date) == 8:
                upload_date = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}"

            # MP3 파일 경로 생성 (yt-dlp가 생성한 파일명 기반)
            # prepare_filename은 원본 확장자를 반환하므로 .mp3로 교체
            original_path = ydl.prepare_filename(info_dict)
            mp3_path = os.path.splitext(original_path)[0] + '.mp3'

        if not os.path.exists(mp3_path):
            if task_id:
                update_progress(task_id, 'download', 0, 'MP3 파일을 찾을 수 없습니다')
            return {
                'success': False,
                'error': 'MP3 파일을 찾을 수 없습니다.'
            }

        logging.info(f'✅ YouTube 오디오 다운로드 완료: {mp3_path}')

        if task_id:
            update_progress(task_id, 'download', 100, 'YouTube 오디오 다운로드 완료')

        return {
            'success': True,
            'video_id': video_id,
            'title': video_title,
            'channel': channel,
            'view_count': view_count,
            'upload_date': upload_date,
            'mp3_path': mp3_path
        }

    except Exception as e:
        logging.error(f"❌ YouTube 오디오 다운로드 오류: {e}")
        if task_id:
            update_progress(task_id, 'download', 0, f'다운로드 오류: {str(e)}')
        return {
            'success': False,
            'error': str(e)
        }


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


def recognize_with_clova(audio_path, task_id=None):
    """Clova Speech API로 음성 인식"""
    start_time = time.time()

    try:
        if task_id:
            update_progress(task_id, 'stt', 0, 'Clova STT 시작')

        logging.info(f"🎧 Clova Speech API로 음성 인식 중: {audio_path}")

        res = ClovaSpeechClient().req_upload(
            file=audio_path, completion="sync", diarization={"enable": True}
        )

        if res.status_code == 200:
            result = res.json()
            logging.info("✅ Clova 음성 인식 완료")

            segments = result.get("segments", [])
            speaker_segments = []

            for segment in segments:
                speaker_label = segment["speaker"]["label"]
                text = segment["text"]
                confidence = segment.get("confidence", 0)
                start_time_ms = segment.get("start", 0)
                start_time_sec = start_time_ms / 1000.0

                speaker_segments.append(
                    {
                        "speaker": speaker_label,
                        "start_time": start_time_sec,
                        "confidence": confidence,
                        "text": text,
                    }
                )

            merged_segments = merge_consecutive_speaker_segments(speaker_segments)

            for idx, seg in enumerate(merged_segments):
                seg["id"] = idx

            end_time = time.time()
            processing_time = end_time - start_time

            if task_id:
                update_progress(task_id, 'stt', 100, f'Clova STT 완료 (처리 시간: {processing_time:.2f}초)')

            logging.info(f"⏱️ Clova STT 처리 시간: {processing_time:.2f}초")

            return {
                'segments': merged_segments,
                'processing_time': processing_time
            }
        else:
            end_time = time.time()
            processing_time = end_time - start_time

            logging.error(f"❌ Clova 음성 인식 실패: {res.status_code}")
            if task_id:
                update_progress(task_id, 'stt', 0, 'Clova STT 실패')
            return {
                'segments': None,
                'processing_time': processing_time
            }

    except Exception as e:
        end_time = time.time()
        processing_time = end_time - start_time

        logging.error(f"❌ Clova 오류 발생: {e}")
        if task_id:
            update_progress(task_id, 'stt', 0, 'Clova STT 오류')
        return {
            'segments': None,
            'processing_time': processing_time
        }


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


def recognize_with_gemini(audio_path, task_id=None):
    """Google Gemini STT API로 음성 인식"""
    start_time = time.time()

    try:
        if task_id:
            update_progress(task_id, 'stt', 0, 'Gemini STT 시작')

        logging.info(f"🎧 Gemini STT API로 음성 인식 중: {audio_path}")

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

        if task_id:
            update_progress(task_id, 'stt', 100, f'Gemini STT 완료 (처리 시간: {processing_time:.2f}초)')

        logging.info(f"⏱️ Gemini STT 처리 시간: {processing_time:.2f}초")

        return {
            'segments': normalized_segments,
            'processing_time': processing_time
        }

    except Exception as e:
        end_time = time.time()
        processing_time = end_time - start_time

        logging.error(f"❌ Gemini 오류 발생: {e}")
        if task_id:
            update_progress(task_id, 'stt', 0, 'Gemini STT 오류')
        import traceback
        traceback.print_exc()
        return {
            'segments': None,
            'processing_time': processing_time
        }


@app.route("/")
def index():
    """메인 페이지"""
    return render_template("youtube_viewer_v0.3.html")


@app.route("/api/process-youtube", methods=["POST"])
def process_youtube():
    """
    YouTube URL을 처리하여 회의록을 생성합니다.
    캐싱 기능 포함.
    """
    try:
        data = request.get_json()
        youtube_url = data.get("youtube_url", "").strip()
        stt_service = data.get("stt_service", "gemini")

        if not youtube_url:
            return jsonify({
                "success": False,
                "error": "YouTube URL을 입력해주세요."
            }), 400

        # 먼저 video_id 추출 (다운로드 없이 정보만)
        try:
            with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
                info = ydl.extract_info(youtube_url, download=False)
                video_id = info.get('id', None)

                if not video_id:
                    return jsonify({
                        "success": False,
                        "error": "유효하지 않은 YouTube URL입니다."
                    }), 400
        except Exception as e:
            logging.error(f"URL 파싱 오류: {e}")
            return jsonify({
                "success": False,
                "error": f"YouTube URL 파싱 실패: {str(e)}"
            }), 400

        # 이력에서 확인
        history_df = load_youtube_history()

        # video_id로 캐시 확인 (URL 형식과 무관)
        existing = history_df[history_df['video_id'] == video_id]

        if not existing.empty:
            # 캐시된 데이터 로드
            row = existing.iloc[0]

            logging.info(f"📂 캐시된 데이터 로드: {row['title']}")

            # segments JSON 파싱
            segments = json.loads(row['segments_json'])

            # 세션에 저장
            session_id = request.remote_addr + "_" + secrets.token_hex(8)
            session_data[session_id] = {
                "segments": segments,
                "chat_history": [],
                "video_id": row['video_id'],  # 요약 저장 시 사용
                "source_type": "youtube"
            }

            # NaN 값 안전 처리
            view_count = row.get('view_count', 0)
            if pd.isna(view_count):
                view_count = 0
            else:
                view_count = int(view_count)

            stt_processing_time = row.get('stt_processing_time', 0.0)
            if pd.isna(stt_processing_time):
                stt_processing_time = 0.0
            else:
                stt_processing_time = float(stt_processing_time)

            return jsonify({
                "success": True,
                "cached": True,
                "source_type": "youtube",
                "message": f"✅ 저장된 데이터를 불러왔습니다: {row['title']}",
                "video_id": row['video_id'],
                "title": row['title'],
                "channel": row.get('channel', 'Unknown'),
                "view_count": view_count,
                "upload_date": row.get('upload_date', ''),
                "mp3_path": row.get('mp3_path', ''),
                "segments": segments,
                "total_segments": len(segments),
                "stt_service": row['stt_service'],
                "stt_processing_time": stt_processing_time,
                "session_id": session_id,
                "created_at": row['created_at'],
                "summary": row.get('summary', '')
            })

        # 새로운 처리
        logging.info(f"🆕 새로운 YouTube URL 처리: {youtube_url}")

        # task_id 및 remote_addr 생성 (request context에서 미리 추출)
        task_id = secrets.token_hex(16)
        remote_addr = request.remote_addr

        # 백그라운드에서 처리할 함수
        def process_in_background():
            try:
                # 1. YouTube 오디오 다운로드 (mp3로 직접 변환)
                download_result = download_youtube_audio_as_mp3(youtube_url, task_id)
                if not download_result['success']:
                    update_progress(task_id, 'error', 0, f"다운로드 실패: {download_result.get('error', '알 수 없는 오류')}")
                    return

                video_id = download_result['video_id']
                title = download_result['title']
                channel = download_result['channel']
                view_count = download_result['view_count']
                upload_date = download_result['upload_date']
                mp3_path = download_result['mp3_path']

                # 2. STT 처리
                stt_processing_time = 0.0
                segments = None

                if stt_service == "gemini":
                    result = recognize_with_gemini(mp3_path, task_id)
                    if result and isinstance(result, dict):
                        segments = result.get('segments')
                        stt_processing_time = result.get('processing_time', 0.0)
                else:
                    result = recognize_with_clova(mp3_path, task_id)
                    if result and isinstance(result, dict):
                        segments = result.get('segments')
                        stt_processing_time = result.get('processing_time', 0.0)

                if not segments:
                    update_progress(task_id, 'error', 0, f"{stt_service.upper()} STT 처리 중 오류가 발생했습니다.")
                    return

                # 3. 이력에 저장
                new_row = {
                    'youtube_url': youtube_url,
                    'video_id': video_id,
                    'title': title,
                    'channel': channel,
                    'view_count': view_count,
                    'upload_date': upload_date,
                    'mp3_path': mp3_path,
                    'segments_json': json.dumps(segments, ensure_ascii=False),
                    'stt_service': stt_service,
                    'stt_processing_time': stt_processing_time,
                    'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'summary': ''
                }

                history_df = load_youtube_history()
                history_df = pd.concat([history_df, pd.DataFrame([new_row])], ignore_index=True)
                save_youtube_history(history_df)

                # 3-1. VectorDB에 저장
                logging.info(f"📦 VectorDB에 세그먼트 저장 중...")
                vectordb_success = store_segments_in_vectordb(
                    segments=segments,
                    source_id=video_id,
                    source_type="youtube",
                    filename=None
                )
                if vectordb_success:
                    logging.info(f"✅ VectorDB 저장 완료")
                else:
                    logging.warning(f"⚠️ VectorDB 저장 실패 (계속 진행)")

                # 4. 세션에 저장
                session_id = remote_addr + "_" + secrets.token_hex(8)
                session_data[session_id] = {
                    "segments": segments,
                    "chat_history": [],
                    "video_id": video_id,
                    "source_type": "youtube"
                }

                # 완료 상태 저장
                progress_data[task_id]['completed'] = True
                progress_data[task_id]['result'] = {
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
                    "stt_service": stt_service,
                    "stt_processing_time": stt_processing_time,
                    "session_id": session_id,
                    "created_at": new_row['created_at']
                }

                logging.info(f"✅ 백그라운드 처리 완료: {title}")

            except Exception as e:
                import traceback
                traceback.print_exc()
                update_progress(task_id, 'error', 0, f"처리 중 오류 발생: {str(e)}")

        # 백그라운드 스레드 시작
        thread = threading.Thread(target=process_in_background)
        thread.daemon = True
        thread.start()

        # 즉시 task_id 반환
        return jsonify({
            "success": True,
            "processing": True,
            "task_id": task_id,
            "message": "처리를 시작했습니다. 진행 상황을 확인하세요."
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": f"처리 중 오류 발생: {str(e)}"
        }), 500


@app.route("/api/process-audio", methods=["POST"])
def process_audio():
    """
    오디오 파일을 업로드하여 회의록을 생성합니다.
    캐싱 기능 포함.
    """
    try:
        # 파일 확인
        if 'audio_file' not in request.files:
            return jsonify({
                "success": False,
                "error": "오디오 파일이 없습니다."
            }), 400

        file = request.files['audio_file']
        stt_service = request.form.get('stt_service', 'gemini')

        if file.filename == '':
            return jsonify({
                "success": False,
                "error": "파일이 선택되지 않았습니다."
            }), 400

        if not allowed_file(file.filename):
            return jsonify({
                "success": False,
                "error": f"지원하지 않는 파일 형식입니다. 허용된 형식: {', '.join(ALLOWED_AUDIO_EXTENSIONS)}"
            }), 400

        # 파일 저장
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        unique_filename = f"{timestamp}_{filename}"
        file_path = os.path.join(UPLOADS_FOLDER, unique_filename)
        file.save(file_path)

        logging.info(f"📁 파일 저장 완료: {file_path}")

        # 파일 해시 계산
        file_hash = calculate_file_hash(file_path)
        file_size = os.path.getsize(file_path)

        # 오디오 길이 추출
        audio_duration = get_audio_duration(file_path)

        # 이력에서 확인 (파일 해시로 캐시 확인)
        history_df = load_audio_history()
        existing = history_df[history_df['file_hash'] == file_hash]

        if not existing.empty:
            # 캐시된 데이터 로드
            row = existing.iloc[0]

            logging.info(f"📂 캐시된 오디오 데이터 로드: {row['filename']}")

            # segments JSON 파싱
            segments = json.loads(row['segments_json'])

            # 세션에 저장
            session_id = request.remote_addr + "_" + secrets.token_hex(8)
            session_data[session_id] = {
                "segments": segments,
                "chat_history": [],
                "file_hash": row['file_hash'],
                "source_type": "audio"
            }

            stt_processing_time = row.get('stt_processing_time', 0.0)
            if pd.isna(stt_processing_time):
                stt_processing_time = 0.0
            else:
                stt_processing_time = float(stt_processing_time)

            audio_duration = row.get('audio_duration', 0.0)
            if pd.isna(audio_duration):
                audio_duration = 0.0
            else:
                audio_duration = float(audio_duration)

            return jsonify({
                "success": True,
                "cached": True,
                "source_type": "audio",
                "message": f"✅ 저장된 데이터를 불러왔습니다: {row['filename']}",
                "file_hash": row['file_hash'],
                "filename": row['filename'],
                "file_path": row['file_path'],
                "file_size": int(row['file_size']),
                "audio_duration": audio_duration,
                "segments": segments,
                "total_segments": len(segments),
                "stt_service": row['stt_service'],
                "stt_processing_time": stt_processing_time,
                "session_id": session_id,
                "created_at": row['created_at'],
                "summary": row.get('summary', '')
            })

        # 새로운 처리
        logging.info(f"🆕 새로운 오디오 파일 처리: {filename}")

        # task_id 및 remote_addr 생성
        task_id = secrets.token_hex(16)
        remote_addr = request.remote_addr

        # 백그라운드에서 처리할 함수
        def process_in_background():
            try:
                # STT 처리
                stt_processing_time = 0.0
                segments = None

                if stt_service == "gemini":
                    result = recognize_with_gemini(file_path, task_id)
                    if result and isinstance(result, dict):
                        segments = result.get('segments')
                        stt_processing_time = result.get('processing_time', 0.0)
                else:
                    result = recognize_with_clova(file_path, task_id)
                    if result and isinstance(result, dict):
                        segments = result.get('segments')
                        stt_processing_time = result.get('processing_time', 0.0)

                if not segments:
                    update_progress(task_id, 'error', 0, f"{stt_service.upper()} STT 처리 중 오류가 발생했습니다.")
                    return

                # 이력에 저장
                new_row = {
                    'file_hash': file_hash,
                    'filename': filename,
                    'file_path': file_path,
                    'file_size': file_size,
                    'audio_duration': audio_duration,
                    'segments_json': json.dumps(segments, ensure_ascii=False),
                    'stt_service': stt_service,
                    'stt_processing_time': stt_processing_time,
                    'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'summary': ''
                }

                history_df = load_audio_history()
                history_df = pd.concat([history_df, pd.DataFrame([new_row])], ignore_index=True)
                save_audio_history(history_df)

                # VectorDB에 저장
                logging.info(f"📦 VectorDB에 세그먼트 저장 중...")
                vectordb_success = store_segments_in_vectordb(
                    segments=segments,
                    source_id=file_hash,
                    source_type="audio",
                    filename=filename
                )
                if vectordb_success:
                    logging.info(f"✅ VectorDB 저장 완료")
                else:
                    logging.warning(f"⚠️ VectorDB 저장 실패 (계속 진행)")

                # 세션에 저장
                session_id = remote_addr + "_" + secrets.token_hex(8)
                session_data[session_id] = {
                    "segments": segments,
                    "chat_history": [],
                    "file_hash": file_hash,
                    "source_type": "audio"
                }

                # 완료 상태 저장
                progress_data[task_id]['completed'] = True
                progress_data[task_id]['result'] = {
                    "success": True,
                    "source_type": "audio",
                    "file_hash": file_hash,
                    "filename": filename,
                    "file_path": file_path,
                    "file_size": file_size,
                    "audio_duration": audio_duration,
                    "segments": segments,
                    "total_segments": len(segments),
                    "stt_service": stt_service,
                    "stt_processing_time": stt_processing_time,
                    "session_id": session_id,
                    "created_at": new_row['created_at']
                }

                logging.info(f"✅ 백그라운드 오디오 처리 완료: {filename}")

            except Exception as e:
                import traceback
                traceback.print_exc()
                update_progress(task_id, 'error', 0, f"처리 중 오류 발생: {str(e)}")

        # 백그라운드 스레드 시작
        thread = threading.Thread(target=process_in_background)
        thread.daemon = True
        thread.start()

        # 즉시 task_id 반환
        return jsonify({
            "success": True,
            "processing": True,
            "task_id": task_id,
            "message": "오디오 파일 처리를 시작했습니다. 진행 상황을 확인하세요."
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": f"처리 중 오류 발생: {str(e)}"
        }), 500


@app.route("/uploads/<path:filename>")
def serve_audio(filename):
    """업로드된 오디오 파일 제공"""
    return send_from_directory(UPLOADS_FOLDER, filename)


@app.route("/mp3/<path:filename>")
def serve_mp3(filename):
    """MP3 파일 제공"""
    return send_from_directory(MP3_FOLDER, filename)


@app.route("/api/summarize", methods=["POST"])
def summarize_transcript():
    """회의록 요약 API"""
    try:
        data = request.get_json()
        segments = data.get("segments")
        session_id = data.get("session_id")

        if not segments and session_id and session_id in session_data:
            segments = session_data[session_id]["segments"]

        if not segments:
            return jsonify({
                "success": False,
                "error": "요약할 데이터가 없습니다."
            }), 400

        transcript_text = "\n\n".join([
            f"화자 {seg['speaker']}: {seg['text']}"
            for seg in segments
        ])

        client = get_gemini_client()

        prompt = f"""다음은 회의록 내용입니다. 이 내용을 간결하고 명확하게 요약해 주세요.

요약 시 다음 사항을 포함해 주세요:
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
                        mask = history_df['video_id'] == video_id
                        if mask.any():
                            history_df.loc[mask, 'summary'] = summary
                            save_youtube_history(history_df)
                            logging.info(f"💾 요약이 YouTube CSV에 저장되었습니다 (video_id: {video_id})")
                    except Exception as e:
                        logging.error(f"요약 저장 오류: {e}")

            elif source_type == "audio":
                file_hash = session_data[session_id].get("file_hash")
                if file_hash:
                    try:
                        history_df = load_audio_history()
                        mask = history_df['file_hash'] == file_hash
                        if mask.any():
                            history_df.loc[mask, 'summary'] = summary
                            save_audio_history(history_df)
                            logging.info(f"💾 요약이 오디오 CSV에 저장되었습니다 (file_hash: {file_hash})")
                    except Exception as e:
                        logging.error(f"요약 저장 오류: {e}")

        return jsonify({
            "success": True,
            "summary": summary
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": f"요약 생성 중 오류 발생: {str(e)}"
        }), 500


@app.route("/api/chat", methods=["POST"])
def chat_with_transcript():
    """회의록 기반 채팅 API (RAG)"""
    try:
        data = request.get_json()
        user_message = data.get("message", "").strip()

        if not user_message:
            return jsonify({
                "success": False,
                "error": "메시지를 입력해주세요."
            }), 400

        session_id = data.get("session_id")
        chat_history = data.get("chat_history", [])

        if not session_id or session_id not in session_data:
            return jsonify({
                "success": False,
                "error": "세션 데이터가 없습니다."
            }), 400

        session_info = session_data[session_id]
        source_type = session_info.get("source_type")
        chat_history = session_info.get("chat_history", [])

        # source_id 가져오기
        if source_type == "youtube":
            source_id = session_info.get("video_id")
        elif source_type == "audio":
            source_id = session_info.get("file_hash")
        else:
            return jsonify({
                "success": False,
                "error": "알 수 없는 소스 타입입니다."
            }), 400

        # VectorDB에서 관련 세그먼트 검색 (RAG)
        logging.info(f"🔍 VectorDB 검색: {user_message}")
        search_results = search_vectordb(
            query=user_message,
            source_id=source_id,
            source_type=source_type,
            n_results=5
        )

        if not search_results:
            return jsonify({
                "success": False,
                "error": "관련 회의록 내용을 찾을 수 없습니다."
            }), 400

        # 검색 결과를 컨텍스트로 구성
        context_text = "\n\n".join([
            f"화자 {result['metadata']['speaker']} ({result['metadata']['start_time']:.1f}초): {result['document']}"
            for result in search_results
        ])

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

        chat_history.append({
            "user": user_message,
            "assistant": assistant_response
        })

        session_data[session_id]["chat_history"] = chat_history

        return jsonify({
            "success": True,
            "response": assistant_response,
            "chat_history": chat_history,
            "search_results": len(search_results)  # 디버깅용
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": f"채팅 응답 생성 중 오류 발생: {str(e)}"
        }), 500


@app.route("/api/history", methods=["GET"])
def get_history():
    """처리 이력 조회 API"""
    try:
        youtube_history = load_youtube_history()
        audio_history = load_audio_history()

        # DataFrame을 dict 리스트로 변환
        youtube_list = youtube_history.to_dict('records')
        audio_list = audio_history.to_dict('records')

        return jsonify({
            "success": True,
            "youtube_history": youtube_list,
            "audio_history": audio_list,
            "total_youtube": len(youtube_list),
            "total_audio": len(audio_list)
        })
    except Exception as e:
        logging.error(f"이력 조회 오류: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route("/api/progress/<task_id>", methods=["GET"])
def get_progress(task_id):
    """진행 상황 조회 API"""
    try:
        if task_id not in progress_data:
            return jsonify({
                "success": False,
                "error": "작업을 찾을 수 없습니다."
            }), 404

        return jsonify({
            "success": True,
            "task_id": task_id,
            "progress": progress_data[task_id]
        })
    except Exception as e:
        logging.error(f"진행 상황 조회 오류: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


if __name__ == "__main__":
    print("=" * 60)
    print("🎬 영상/오디오 검색 엔진 v0.2 시작")
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
    print("  - 회의록 요약")
    print("  - AI 채팅")
    print("  - 처리 이력 캐싱 (CSV)")
    print("=" * 60)

    app.run(host="0.0.0.0", port=5002, debug=True)
