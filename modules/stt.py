"""
STT (Speech-to-Text) 모듈 - Gemini API 사용
"""
import os
import logging
import time
import json
from google import genai
from google.genai import types


def get_gemini_client():
    """Gemini 클라이언트 생성"""
    api_key = os.environ.get("GOOGLE_API_KEY")
    if api_key:
        return genai.Client(api_key=api_key)
    else:
        return genai.Client()


def recognize_with_gemini(audio_path, task_id=None):
    """
    Google Gemini STT API로 음성 인식

    Args:
        audio_path: 오디오 파일 경로
        task_id: 진행 상황 추적용 ID (optional)

    Returns:
        tuple: (segments, processing_time) 또는 (None, 0.0) on error
    """
    from modules.utils import update_progress, parse_mmss_to_seconds

    start_time = time.time()

    try:
        if task_id:
            update_progress(task_id, "stt", 0, "Gemini STT 시작")

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

        if task_id:
            update_progress(task_id, "stt", 50, "Gemini 응답 파싱 중")

        # 응답 파싱
        text = response.text.strip()

        # 마크다운 코드 블록 제거
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]

        if text.endswith("```"):
            text = text[:-3]

        text = text.strip()

        try:
            result = json.loads(text)
        except json.JSONDecodeError as e:
            logging.error(f"❌ JSON 파싱 오류: {e}")
            logging.error(f"응답 텍스트: {text[:500]}...")
            if task_id:
                update_progress(task_id, "stt", 100, f"JSON 파싱 오류: {str(e)}")
            return None, 0.0

        # 세그먼트 변환
        segments = []
        for idx, item in enumerate(result):
            start_time_str = item.get("start_time_mmss", "0:00:000")
            start_time = parse_mmss_to_seconds(start_time_str)

            segments.append({
                "id": idx + 1,
                "speaker": str(item.get("speaker", "Unknown")),
                "start_time": start_time,
                "confidence": float(item.get("confidence", 0.0)),
                "text": item.get("text", ""),
            })

        processing_time = time.time() - start_time

        logging.info(f"✅ Gemini STT 완료: {len(segments)}개 세그먼트 ({processing_time:.2f}초)")

        if task_id:
            update_progress(task_id, "stt", 100, f"STT 완료: {len(segments)}개 세그먼트")

        return segments, processing_time

    except Exception as e:
        logging.error(f"❌ Gemini STT 오류: {e}")
        import traceback
        traceback.print_exc()

        if task_id:
            update_progress(task_id, "stt", 100, f"STT 오류: {str(e)}")

        return None, 0.0
