"""
YouTube 다운로드 모듈
"""
import os
import logging
import yt_dlp
from config import MP3_FOLDER


def download_youtube_audio_as_mp3(url, task_id=None):
    """
    YouTube에서 오디오만 다운로드하여 mp3로 변환합니다.

    Args:
        url: YouTube URL
        task_id: 진행 상황 추적용 ID (optional)

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
    from modules.utils import update_progress

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
