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
    """
    시간 문자열을 초 단위로 변환합니다.
    지원 형식:
    - '시:분:초' (예: "0:05:30" -> 330초, "1:05:30" -> 3930초) - 기본 형식
    - '시:분:초.밀리초' (예: "0:05:30.200" -> 330.2초) - 하위 호환성
    - '시:분:초:밀리초' (예: "0:05:30:200" -> 330.2초) - 하위 호환성
    - '분:초' (예: "5:30" -> 330초)
    """
    try:
        # 점(.)으로 밀리초 분리
        if '.' in time_str:
            main_parts = time_str.split('.')
            time_parts = main_parts[0]
            milliseconds = int(main_parts[1]) if len(main_parts) > 1 else 0

            parts = time_parts.split(":")
            if len(parts) == 3:
                # 시:분:초.밀리초
                hours = int(parts[0])
                minutes = int(parts[1])
                seconds = int(parts[2])
                return hours * 3600 + minutes * 60 + seconds + milliseconds / 1000.0
            elif len(parts) == 2:
                # 분:초.밀리초
                minutes = int(parts[0])
                seconds = int(parts[1])
                return minutes * 60 + seconds + milliseconds / 1000.0
        else:
            # 밀리초 없는 형식
            parts = time_str.split(":")
            if len(parts) == 4:
                # 시:분:초:밀리초 (하위 호환성)
                hours = int(parts[0])
                minutes = int(parts[1])
                seconds = int(parts[2])
                milliseconds = int(parts[3])
                return hours * 3600 + minutes * 60 + seconds + milliseconds / 1000.0
            elif len(parts) == 3:
                # 시:분:초 (기본 형식)
                hours = int(parts[0])
                minutes = int(parts[1])
                seconds = int(parts[2])
                return hours * 3600 + minutes * 60 + seconds
            elif len(parts) == 2:
                # 분:초
                minutes = int(parts[0])
                seconds = int(parts[1])
                return minutes * 60 + seconds

        return 0.0
    except:
        return 0.0
