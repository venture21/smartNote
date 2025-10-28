"""
영상 검색 엔진 v0.1

YouTube 링크를 입력받아:
1. 영상을 다운로드 (mp4 폴더에 저장)
2. MP3로 변환 (mp3 폴더에 저장)
3. STT로 회의록 생성
4. CSV로 작업 이력 관리 (캐싱)
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
HISTORY_CSV = os.path.join(CSV_FOLDER, "youtube_history.csv")

app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500MB max

# 폴더 생성
for folder in [MP4_FOLDER, MP3_FOLDER, CSV_FOLDER]:
    os.makedirs(folder, exist_ok=True)

# 세션별 데이터 저장
session_data = {}

# 진행 상황 저장
progress_data = {}


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
def load_history():
    """CSV 파일에서 YouTube 다운로드 이력을 로드합니다."""
    if os.path.exists(HISTORY_CSV):
        try:
            df = pd.read_csv(HISTORY_CSV, encoding='utf-8-sig')
            # summary 컬럼이 없으면 추가
            if 'summary' not in df.columns:
                df['summary'] = ''
            # stt_processing_time 컬럼이 없으면 추가
            if 'stt_processing_time' not in df.columns:
                df['stt_processing_time'] = 0.0

            # NaN 값 처리
            df['summary'] = df['summary'].fillna('')
            df['stt_processing_time'] = df['stt_processing_time'].fillna(0.0)
            df['view_count'] = df['view_count'].fillna(0)
            df['channel'] = df['channel'].fillna('Unknown')
            df['upload_date'] = df['upload_date'].fillna('')

            logging.info(f"📋 이력 로드 완료: {len(df)}개 항목")
            return df
        except Exception as e:
            logging.error(f"이력 로드 오류: {e}")
            return pd.DataFrame(columns=['youtube_url', 'video_id', 'title', 'channel', 'view_count', 'upload_date', 'mp3_path', 'segments_json', 'stt_service', 'stt_processing_time', 'created_at', 'summary'])
    else:
        return pd.DataFrame(columns=['youtube_url', 'video_id', 'title', 'channel', 'view_count', 'upload_date', 'mp3_path', 'segments_json', 'stt_service', 'stt_processing_time', 'created_at', 'summary'])


def save_history(df):
    """이력을 CSV 파일에 저장합니다."""
    try:
        df.to_csv(HISTORY_CSV, index=False, encoding='utf-8-sig')
        logging.info(f"💾 이력 저장 완료: {len(df)}개 항목")
    except Exception as e:
        logging.error(f"이력 저장 오류: {e}")


def get_gemini_client():
    """Gemini 클라이언트 생성"""
    api_key = os.environ.get("GOOGLE_API_KEY")
    if api_key:
        return genai.Client(api_key=api_key)
    else:
        return genai.Client()


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


def extract_audio_to_mp3(video_path, audio_format="mp3", bitrate="192k", task_id=None):
    """
    비디오 파일에서 오디오를 추출합니다.

    Args:
        video_path: 입력 비디오 파일 경로
        audio_format: 오디오 포맷 (기본값: 'mp3')
        bitrate: 비트레이트 (기본값: '192k')
        task_id: 작업 ID (진행 상황 추적용)

    Returns:
        dict: {
            'success': bool,
            'mp3_path': str,
            'error': str (optional)
        }
    """
    try:
        if task_id:
            update_progress(task_id, 'mp3_conversion', 0, 'MP3 변환 시작')
        # 출력 파일 경로 생성
        base_name = os.path.basename(video_path)
        name_without_ext = os.path.splitext(base_name)[0]
        audio_path = os.path.join(MP3_FOLDER, f"{name_without_ext}.{audio_format}")

        # 포맷별 코덱 설정
        codec_map = {"mp3": "libmp3lame", "wav": "pcm_s16le", "aac": "aac", "m4a": "aac"}
        codec = codec_map.get(audio_format, "libmp3lame")

        # FFmpeg 명령어
        command = [
            "ffmpeg",
            "-i", video_path,
            "-vn",  # 비디오 제거
            "-acodec", codec,
            "-ab", bitrate,
            audio_path,
            "-y",  # 덮어쓰기
        ]

        logging.info(f'🎵 MP3 변환 시작: {video_path} -> {audio_path}')

        result = subprocess.run(command, check=True, capture_output=True, text=True)

        logging.info(f"✅ MP3 변환 완료: {audio_path}")

        if task_id:
            update_progress(task_id, 'mp3_conversion', 100, 'MP3 변환 완료')

        return {
            'success': True,
            'mp3_path': audio_path
        }

    except subprocess.CalledProcessError as e:
        logging.error(f"❌ FFmpeg 오류: {e.stderr}")
        if task_id:
            update_progress(task_id, 'mp3_conversion', 0, 'MP3 변환 실패')
        return {
            'success': False,
            'error': f'FFmpeg 오류: {e.stderr}'
        }
    except FileNotFoundError:
        logging.error("❌ ffmpeg가 설치되어 있지 않습니다.")
        if task_id:
            update_progress(task_id, 'mp3_conversion', 0, 'MP3 변환 실패 - ffmpeg 미설치')
        return {
            'success': False,
            'error': 'ffmpeg가 설치되어 있지 않습니다.'
        }
    except Exception as e:
        logging.error(f"❌ MP3 변환 오류: {e}")
        if task_id:
            update_progress(task_id, 'mp3_conversion', 0, 'MP3 변환 실패')
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
                start_time = start_time_ms / 1000.0

                speaker_segments.append(
                    {
                        "speaker": speaker_label,
                        "start_time": start_time,
                        "confidence": confidence,
                        "text": text,
                    }
                )

            merged_segments = merge_consecutive_speaker_segments(speaker_segments)

            for idx, seg in enumerate(merged_segments):
                seg["id"] = idx

            if task_id:
                update_progress(task_id, 'stt', 100, 'Clova STT 완료')

            return merged_segments
        else:
            logging.error(f"❌ Clova 음성 인식 실패: {res.status_code}")
            if task_id:
                update_progress(task_id, 'stt', 0, 'Clova STT 실패')
            return None

    except Exception as e:
        logging.error(f"❌ Clova 오류 발생: {e}")
        if task_id:
            update_progress(task_id, 'stt', 0, 'Clova STT 오류')
        return None


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
    return render_template("youtube_viewer_v0.1.html")


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
        history_df = load_history()

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
                "video_id": row['video_id']  # 요약 저장 시 사용
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
                "summary": row.get('summary', '')  # 캐시된 요약 반환
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
                if stt_service == "gemini":
                    result = recognize_with_gemini(mp3_path, task_id)
                    if result and isinstance(result, dict):
                        segments = result.get('segments')
                        stt_processing_time = result.get('processing_time', 0.0)
                    else:
                        segments = None
                else:
                    segments = recognize_with_clova(mp3_path, task_id)

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
                    'summary': ''  # 초기값은 빈 문자열
                }

                history_df = load_history()
                history_df = pd.concat([history_df, pd.DataFrame([new_row])], ignore_index=True)
                save_history(history_df)

                # 5. 세션에 저장
                session_id = remote_addr + "_" + secrets.token_hex(8)
                session_data[session_id] = {
                    "segments": segments,
                    "chat_history": [],
                    "video_id": video_id  # 요약 저장 시 사용
                }

                # 완료 상태 저장
                progress_data[task_id]['completed'] = True
                progress_data[task_id]['result'] = {
                    "success": True,
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
            video_id = session_data[session_id].get("video_id")
            if video_id:
                try:
                    history_df = load_history()
                    # video_id로 찾아서 summary 업데이트
                    mask = history_df['video_id'] == video_id
                    if mask.any():
                        history_df.loc[mask, 'summary'] = summary
                        save_history(history_df)
                        logging.info(f"💾 요약이 CSV에 저장되었습니다 (video_id: {video_id})")
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
    """회의록 기반 채팅 API"""
    try:
        data = request.get_json()
        user_message = data.get("message", "").strip()

        if not user_message:
            return jsonify({
                "success": False,
                "error": "메시지를 입력해주세요."
            }), 400

        segments = data.get("segments")
        session_id = data.get("session_id")
        chat_history = data.get("chat_history", [])

        if not segments and session_id and session_id in session_data:
            segments = session_data[session_id]["segments"]
            chat_history = session_data[session_id].get("chat_history", [])

        if not segments:
            return jsonify({
                "success": False,
                "error": "회의록 데이터가 없습니다."
            }), 400

        transcript_text = "\n\n".join([
            f"화자 {seg['speaker']} ({seg['start_time']:.1f}초): {seg['text']}"
            for seg in segments
        ])

        history_text = ""
        if chat_history:
            history_text = "\n\n이전 대화 내역:\n"
            for hist in chat_history[-5:]:
                history_text += f"사용자: {hist['user']}\n"
                history_text += f"AI: {hist['assistant']}\n\n"

        client = get_gemini_client()

        prompt = f"""당신은 회의록 분석 전문 AI 어시스턴트입니다. 다음 회의록 내용을 바탕으로 사용자의 질문에 답변해 주세요.

회의록:
{transcript_text}
{history_text}
사용자 질문: {user_message}

답변 시 다음을 유의해 주세요:
1. 회의록의 내용을 기반으로 정확하게 답변하세요.
2. 필요한 경우 화자와 시간 정보를 포함해 주세요.
3. 회의록에 없는 내용은 추측하지 말고 "회의록에 해당 내용이 없습니다"라고 답변하세요.
4. 간결하고 명확하게 답변하세요."""

        logging.info(f"🤖 사용자 질문: {user_message}")

        response = client.models.generate_content(
            model="gemini-2.5-pro",
            contents=prompt,
        )

        assistant_response = response.text.strip()
        logging.info(f"✅ AI 응답 생성 완료")

        chat_history.append({
            "user": user_message,
            "assistant": assistant_response
        })

        if session_id and session_id in session_data:
            session_data[session_id]["chat_history"] = chat_history

        return jsonify({
            "success": True,
            "response": assistant_response,
            "chat_history": chat_history
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
        history_df = load_history()

        # DataFrame을 dict 리스트로 변환
        history_list = history_df.to_dict('records')

        return jsonify({
            "success": True,
            "history": history_list,
            "total": len(history_list)
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
    print("🎬 YouTube 영상 회의록 생성 뷰어 v0.1 시작")
    print("=" * 60)
    print("URL: http://localhost:5001")
    print("=" * 60)
    print("기능:")
    print("  - YouTube 영상 다운로드 (mp4 폴더)")
    print("  - MP3 변환 (mp3 폴더)")
    print("  - STT 회의록 생성")
    print("  - 회의록 요약")
    print("  - AI 채팅")
    print("  - 처리 이력 캐싱 (CSV)")
    print("=" * 60)

    app.run(host="0.0.0.0", port=5001, debug=True)
