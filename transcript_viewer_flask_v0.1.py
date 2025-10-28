"""
Flask 기반 오디오-회의록 동기화 뷰어

오디오 재생 시간에 맞춰 회의록 텍스트를 하이라이트하는 웹 애플리케이션
WAV 파일을 업로드하면 자동으로 STT를 수행합니다.
"""

from flask import Flask, render_template, request, jsonify, send_from_directory
import os
import pandas as pd
import json
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from myClovaSpeech import ClovaSpeechClient
from google import genai
from google.genai import types

# 환경 변수 로드
load_dotenv()

app = Flask(__name__)

# 설정
UPLOAD_FOLDER = "uploads"
ALLOWED_AUDIO_EXTENSIONS = {"wav", "mp3", "m4a", "flac"}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # 100MB max

# 업로드 폴더 생성
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def allowed_file(filename, allowed_extensions):
    """파일 확장자 검증"""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed_extensions


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


def save_segments_to_csv(segments, audio_filename, stt_service):
    """
    STT 결과를 CSV 파일로 저장합니다.

    Args:
        segments: STT 결과 세그먼트 리스트
        audio_filename: 원본 오디오 파일명
        stt_service: 사용한 STT 서비스 (clova 또는 gemini)

    Returns:
        str: 저장된 CSV 파일 경로
    """
    # CSV 파일명 생성 (오디오 파일명 기반)
    base_name = os.path.splitext(audio_filename)[0]
    csv_filename = f"{base_name}_{stt_service}_transcript.csv"
    csv_path = os.path.join(app.config["UPLOAD_FOLDER"], csv_filename)

    # DataFrame 생성
    df_data = []
    for segment in segments:
        df_data.append(
            {
                "speaker": segment.get("speaker", 1),
                "start_time": segment.get("start_time", 0.0),
                "text": segment.get("text", ""),
                "confidence": segment.get("confidence", 0.0),
            }
        )

    df = pd.DataFrame(df_data)

    # CSV 저장
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")

    print(f"📄 CSV 파일 저장 완료: {csv_path}")

    return csv_path


def recognize_with_clova(audio_path):
    """Clova Speech API로 음성 인식"""
    try:
        print(f"🎧 Clova Speech API로 음성 인식 중: {audio_path}")

        res = ClovaSpeechClient().req_upload(
            file=audio_path, completion="sync", diarization={"enable": True}
        )

        if res.status_code == 200:
            result = res.json()
            print("✅ Clova 음성 인식 완료")

            # 화자별 인식 결과 추출
            segments = result.get("segments", [])
            speaker_segments = []

            for segment in segments:
                speaker_label = segment["speaker"]["label"]
                text = segment["text"]
                confidence = segment.get("confidence", 0)
                start_time_ms = segment.get("start", 0)

                # Clova는 밀리초(ms) 단위이므로 초(s)로 변환
                start_time = start_time_ms / 1000.0

                speaker_segments.append(
                    {
                        "speaker": speaker_label,
                        "start_time": start_time,
                        "confidence": confidence,
                        "text": text,
                    }
                )

            # 연속된 동일 화자 세그먼트 병합
            merged_segments = merge_consecutive_speaker_segments(speaker_segments)

            # ID 추가
            for idx, seg in enumerate(merged_segments):
                seg["id"] = idx

            return merged_segments
        else:
            print(f"❌ Clova 음성 인식 실패: {res.status_code}")
            return None

    except Exception as e:
        print(f"❌ Clova 오류 발생: {e}")
        return None


def parse_mmss_to_seconds(time_str):
    """
    '분:초:밀리초' 형태의 문자열을 초 단위로 변환합니다.

    Args:
        time_str: "0:05:200" 또는 "1:23:450" 형태의 문자열

    Returns:
        float: 초 단위 시간 (예: 5.2, 83.45)
    """
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


def recognize_with_gemini(audio_path):
    """Google Gemini STT API로 음성 인식"""
    try:
        print(f"🎧 Gemini STT API로 음성 인식 중: {audio_path}")

        # Client 생성
        api_key = os.environ.get("GOOGLE_API_KEY")
        if api_key:
            client = genai.Client(api_key=api_key)
        else:
            client = genai.Client()

        # 로컬 파일을 바이너리로 읽기
        with open(audio_path, "rb") as f:
            file_bytes = f.read()

        # MIME 타입 결정
        file_ext = os.path.splitext(audio_path)[1].lower()
        mime_type_map = {
            ".wav": "audio/wav",
            ".mp3": "audio/mp3",
            ".m4a": "audio/mp4",
            ".flac": "audio/flac",
            ".ogg": "audio/ogg",
        }
        mime_type = mime_type_map.get(file_ext, "audio/wav")

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

        print("🤖 Gemini 2.5 Pro로 음성 인식 중...")

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

        print("✅ Gemini 음성 인식 완료")

        # 결과 정리
        cleaned_response = response.text.strip()
        cleaned_response = (
            cleaned_response.replace("```json", "").replace("```", "").strip()
        )

        # JSON 파싱
        result_list = json.loads(cleaned_response)

        # 필드명 정규화 및 ID 추가
        normalized_segments = []
        for idx, segment in enumerate(result_list):
            # start_time_mmss를 초 단위로 변환
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

        return normalized_segments

    except Exception as e:
        print(f"❌ Gemini 오류 발생: {e}")
        import traceback

        traceback.print_exc()
        return None


def parse_csv_transcript(csv_path):
    """
    CSV 파일을 읽어서 회의록 데이터를 파싱합니다.

    Returns:
        List[Dict]: [
            {
                "speaker": 1,
                "start_time": 0.0,
                "text": "안녕하세요",
                "confidence": 0.95
            },
            ...
        ]
    """
    try:
        df = pd.read_csv(csv_path)

        # 필요한 컬럼 확인
        required_cols = ["speaker", "start_time"]

        # 컬럼명 변환 (여러 형식 지원)
        column_mapping = {}

        for col in df.columns:
            col_lower = col.lower()
            if "speaker" in col_lower:
                column_mapping[col] = "speaker"
            elif "start" in col_lower and "time" in col_lower:
                column_mapping[col] = "start_time"
            elif col_lower in ["text", "transcript", "recognized_text"]:
                column_mapping[col] = "text"
            elif "confidence" in col_lower:
                column_mapping[col] = "confidence"

        df = df.rename(columns=column_mapping)

        # text 컬럼이 없으면 recognized_text 사용
        if "text" not in df.columns and "recognized_text" in df.columns:
            df["text"] = df["recognized_text"]

        # 기본값 설정
        if "confidence" not in df.columns:
            df["confidence"] = 0.0

        # 데이터 변환
        segments = []
        for idx, row in df.iterrows():
            segment = {
                "id": idx,
                "speaker": int(row.get("speaker", 1)),
                "start_time": float(row.get("start_time", 0.0)),
                "text": str(row.get("text", "")),
                "confidence": float(row.get("confidence", 0.0)),
            }
            segments.append(segment)

        return segments

    except Exception as e:
        print(f"CSV 파싱 오류: {e}")
        return []


@app.route("/")
def index():
    """메인 페이지"""
    return render_template("index_v0.1.html")


@app.route("/upload", methods=["POST"])
def upload_files():
    """오디오 파일 업로드 및 STT 처리"""

    # 파일 검증
    if "audio_file" not in request.files:
        return (
            jsonify({"success": False, "error": "오디오 파일을 업로드해주세요."}),
            400,
        )

    audio_file = request.files["audio_file"]
    stt_service = request.form.get("stt_service", "clova")  # clova 또는 gemini

    if audio_file.filename == "":
        return jsonify({"success": False, "error": "파일을 선택해주세요."}), 400

    if not allowed_file(audio_file.filename, ALLOWED_AUDIO_EXTENSIONS):
        return (
            jsonify(
                {
                    "success": False,
                    "error": "지원하지 않는 오디오 형식입니다. (wav, mp3, m4a, flac만 가능)",
                }
            ),
            400,
        )

    try:
        # 파일 저장
        audio_filename = secure_filename(audio_file.filename)
        audio_path = os.path.join(app.config["UPLOAD_FOLDER"], audio_filename)
        audio_file.save(audio_path)

        print(f"📁 파일 저장 완료: {audio_path}")
        print(f"🔧 STT 서비스: {stt_service}")

        # STT 처리
        if stt_service == "gemini":
            segments = recognize_with_gemini(audio_path)
        else:  # clova (default)
            segments = recognize_with_clova(audio_path)

        if not segments:
            return (
                jsonify(
                    {
                        "success": False,
                        "error": f"{stt_service.upper()} STT 처리 중 오류가 발생했습니다.",
                    }
                ),
                500,
            )

        # CSV 파일로 저장
        csv_path = save_segments_to_csv(segments, audio_filename, stt_service)
        csv_filename = os.path.basename(csv_path)

        return jsonify(
            {
                "success": True,
                "audio_url": f"/uploads/{audio_filename}",
                "segments": segments,
                "total_segments": len(segments),
                "stt_service": stt_service,
                "csv_file": csv_filename,
                "csv_url": f"/uploads/{csv_filename}",
            }
        )

    except Exception as e:
        import traceback

        traceback.print_exc()
        return (
            jsonify({"success": False, "error": f"파일 업로드 중 오류 발생: {str(e)}"}),
            500,
        )


@app.route("/uploads/<filename>")
def uploaded_file(filename):
    """업로드된 파일 제공"""
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


@app.route("/api/transcript/<int:segment_id>")
def get_segment(segment_id):
    """특정 세그먼트 정보 반환 (선택사항)"""
    # 필요시 구현
    return jsonify({"segment_id": segment_id})


if __name__ == "__main__":
    print("=" * 60)
    print("🎵 오디오-회의록 동기화 뷰어 시작")
    print("=" * 60)
    print("URL: http://localhost:5000")
    print("=" * 60)

    app.run(host="0.0.0.0", port=5000, debug=True)
