"""
설정 파일
"""
import os
import secrets
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv()

# Flask 설정
SECRET_KEY = secrets.token_hex(16)
MAX_CONTENT_LENGTH = 500 * 1024 * 1024  # 500MB max

# 디렉토리 설정
MP4_FOLDER = "mp4"
MP3_FOLDER = "mp3"
CSV_FOLDER = "csv"
UPLOADS_FOLDER = "uploads"
CHROMA_DB_FOLDER = "chroma_db"

# CSV 파일 경로
YOUTUBE_HISTORY_CSV = os.path.join(CSV_FOLDER, "youtube_history.csv")
AUDIO_HISTORY_CSV = os.path.join(CSV_FOLDER, "audio_history.csv")
STT_PROCESSING_LOG = os.path.join(CSV_FOLDER, "stt_processing_log.json")

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

# API 키
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
