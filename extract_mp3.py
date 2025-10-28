import subprocess
import os


def extract_audio(video_path, audio_path=None, audio_format="mp3", bitrate="192k"):
    """
    비디오 파일에서 오디오를 추출합니다.

    Args:
        video_path: 입력 비디오 파일 경로
        audio_path: 출력 오디오 파일 경로 (None이면 자동 생성)
        audio_format: 오디오 포맷 ('mp3', 'wav', 'aac', 'm4a')
        bitrate: 비트레이트 (기본값: '192k')
    """
    # 출력 파일 경로 자동 생성
    if audio_path is None:
        base_name = os.path.splitext(video_path)[0]
        audio_path = f"{base_name}.{audio_format}"

    # 포맷별 코덱 설정
    codec_map = {"mp3": "libmp3lame", "wav": "pcm_s16le", "aac": "aac", "m4a": "aac"}

    codec = codec_map.get(audio_format, "libmp3lame")

    # FFmpeg 명령어
    command = [
        "ffmpeg",
        "-i",
        video_path,
        "-vn",  # 비디오 제거
        "-acodec",
        codec,
        "-ab",
        bitrate,
        audio_path,
        "-y",
    ]

    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        print(f"✓ 오디오 추출 완료: {audio_path}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ 오류 발생: {e.stderr}")
        return False
    except FileNotFoundError:
        print("✗ ffmpeg가 설치되어 있지 않습니다.")
        return False


# 사용 예시
filePath = "data/퍼플렉시티부터 삼성까지-AWS먹통.mp4"
extract_audio(filePath, bitrate="128k")  # video.mp3로 저장
# extract_audio("video.mp4", "output.wav", audio_format='wav')  # WAV로 저장
# extract_audio("video.mp4", "output.m4a", audio_format='m4a', bitrate='256k')  # 고음질 M4A
