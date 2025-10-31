"""
유틸리티 함수 모듈
"""
import hashlib
import logging
from datetime import datetime
from mutagen import File as MutagenFile
from config import ALLOWED_AUDIO_EXTENSIONS

# 진행 상황 저장용 딕셔너리
progress_data = {}


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
