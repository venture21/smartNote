"""
Flask 기반 오디오-회의록 동기화 뷰어 v0.2

오디오 재생 시간에 맞춰 회의록 텍스트를 하이라이트하는 웹 애플리케이션
WAV 파일을 업로드하면 자동으로 STT를 수행합니다.

v0.2 추가 기능:
- 회의록 요약 기능
- AI 채팅 기능 (회의록 내용에 대한 질의응답)
"""

from flask import Flask, render_template, request, jsonify, send_from_directory, session
import os
import pandas as pd
import json
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from myClovaSpeech import ClovaSpeechClient
from google import genai
from google.genai import types
import secrets

# 환경 변수 로드
load_dotenv()

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)  # 세션을 위한 시크릿 키

# 설정
UPLOAD_FOLDER = "uploads"
ALLOWED_AUDIO_EXTENSIONS = {"wav", "mp3", "m4a", "flac"}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # 100MB max

# 업로드 폴더 생성
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# 세션별 데이터 저장 (간단한 인메모리 저장소)
session_data = {}


def get_gemini_client():
    """Gemini 클라이언트 생성"""
    api_key = os.environ.get("GOOGLE_API_KEY")
    if api_key:
        return genai.Client(api_key=api_key)
    else:
        return genai.Client()


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
        client = get_gemini_client()

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
    return render_template("index_v0.2.html")


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

        # 세션에 segments 저장 (요약 및 채팅 기능에서 사용)
        session_id = request.remote_addr + "_" + secrets.token_hex(8)
        session_data[session_id] = {
            "segments": segments,
            "chat_history": []
        }

        return jsonify(
            {
                "success": True,
                "audio_url": f"/uploads/{audio_filename}",
                "segments": segments,
                "total_segments": len(segments),
                "stt_service": stt_service,
                "csv_file": csv_filename,
                "csv_url": f"/uploads/{csv_filename}",
                "session_id": session_id,
            }
        )

    except Exception as e:
        import traceback

        traceback.print_exc()
        return (
            jsonify({"success": False, "error": f"파일 업로드 중 오류 발생: {str(e)}"}),
            500,
        )


@app.route("/api/summarize", methods=["POST"])
def summarize_transcript():
    """
    회의록 요약 API

    Request Body:
    {
        "segments": [...],  # 요약할 세그먼트 데이터 (선택사항, session_id가 있으면 불필요)
        "session_id": "..."  # 세션 ID (선택사항)
    }

    Response:
    {
        "success": true,
        "summary": "요약 내용..."
    }
    """
    try:
        data = request.get_json()

        # segments 가져오기 (request body 또는 session에서)
        segments = data.get("segments")
        session_id = data.get("session_id")

        if not segments and session_id and session_id in session_data:
            segments = session_data[session_id]["segments"]

        if not segments:
            return jsonify({
                "success": False,
                "error": "요약할 데이터가 없습니다."
            }), 400

        # 회의록 텍스트 생성
        transcript_text = "\n\n".join([
            f"화자 {seg['speaker']}: {seg['text']}"
            for seg in segments
        ])

        # Gemini로 요약 생성
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

        print("🤖 Gemini로 요약 생성 중...")

        response = client.models.generate_content(
            model="gemini-2.5-pro",
            contents=prompt,
        )

        summary = response.text.strip()

        print("✅ 요약 생성 완료")

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
    """
    회의록 기반 채팅 API

    Request Body:
    {
        "message": "질문 내용",
        "segments": [...],  # 대화 컨텍스트 (선택사항, session_id가 있으면 불필요)
        "session_id": "...",  # 세션 ID (선택사항)
        "chat_history": [...]  # 이전 대화 히스토리 (선택사항)
    }

    Response:
    {
        "success": true,
        "response": "AI 응답...",
        "chat_history": [...]  # 업데이트된 대화 히스토리
    }
    """
    try:
        data = request.get_json()

        user_message = data.get("message", "").strip()
        if not user_message:
            return jsonify({
                "success": False,
                "error": "메시지를 입력해주세요."
            }), 400

        # segments와 chat_history 가져오기
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

        # 회의록 텍스트 생성
        transcript_text = "\n\n".join([
            f"화자 {seg['speaker']} ({seg['start_time']:.1f}초): {seg['text']}"
            for seg in segments
        ])

        # 대화 히스토리 텍스트 생성
        history_text = ""
        if chat_history:
            history_text = "\n\n이전 대화 내역:\n"
            for hist in chat_history[-5:]:  # 최근 5개만
                history_text += f"사용자: {hist['user']}\n"
                history_text += f"AI: {hist['assistant']}\n\n"

        # Gemini로 응답 생성
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

        print(f"🤖 사용자 질문: {user_message}")

        response = client.models.generate_content(
            model="gemini-2.5-pro",
            contents=prompt,
        )

        assistant_response = response.text.strip()

        print(f"✅ AI 응답 생성 완료")

        # 대화 히스토리 업데이트
        chat_history.append({
            "user": user_message,
            "assistant": assistant_response
        })

        # 세션에 대화 히스토리 저장
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
    print("🎵 오디오-회의록 동기화 뷰어 v0.2 시작")
    print("=" * 60)
    print("URL: http://localhost:5000")
    print("=" * 60)
    print("새로운 기능:")
    print("  - 회의록 자동 요약")
    print("  - AI 채팅 (회의록 질의응답)")
    print("=" * 60)

    app.run(host="0.0.0.0", port=5000, debug=True)
