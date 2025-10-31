"""
Gemini 2.5 Pro를 사용한 오디오 화자 분리 및 텍스트 변환
google-genai 패키지 사용
"""

from google import genai
from google.genai import types
import os
import json
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv()


def transcribe_diarize_gemini_ai_studio(local_audio_path: str, api_key: str = None) -> dict:
    """
    Gemini 2.5 Pro 모델 (Google AI Studio)을 사용하여
    로컬 오디오 파일을 변환하고 화자를 분리합니다.

    Args:
        local_audio_path: 로컬 오디오 파일 경로
        api_key: Google API 키 (None인 경우 환경변수에서 로드)

    Returns:
        화자 분리된 텍스트 결과 (JSON 형식)
    """

    # 1. 클라이언트 생성
    if api_key:
        client = genai.Client(api_key=api_key)
    else:
        # 환경변수나 gcloud auth를 통한 인증 사용
        client = genai.Client()

    # 2. 로컬 오디오 파일 업로드
    print(f"📤 '{local_audio_path}' 파일을 업로드 중입니다...")

    try:
        # 파일을 바이너리 모드로 읽기
        with open(local_audio_path, "rb") as f:
            file_bytes = f.read()

        # 파일 확장자에 따른 MIME 타입 결정
        file_ext = os.path.splitext(local_audio_path)[1].lower()
        mime_type_map = {
            ".wav": "audio/wav",
            ".mp3": "audio/mp3",
            ".m4a": "audio/mp4",
            ".flac": "audio/flac",
            ".ogg": "audio/ogg",
        }
        mime_type = mime_type_map.get(file_ext, "audio/wav")

        print(f"✅ 파일 업로드 완료 (타입: {mime_type})")

        # 3. 프롬프트 준비
        prompt = """
당신은 전문적인 회의록 작성자입니다. 제공된 오디오 파일을 듣고 다음 작업을 수행해 주십시오:

1. 전체 대화를 정확하게 텍스트로 변환합니다.
2. 각 발화에 대해 화자를 숫자로 구분합니다. 발화자의 등장 순서대로 번호를 할당합니다. 참고로, 현재 오디오의 화자수는 총 4명입니다. 화자의 숫자는 4를 넘지 않습니다.
3. 최종 결과는 아래의 JSON 형식과 정확히 일치해야 합니다. 각 JSON 객체는 'speaker', 'start_time_seconds', 'transcript' 키를 포함해야 합니다.
4. speaker가 동일한 경우 하나의 행으로 만듭니다. 하나의 행으로 만드는 경우 'start_time_seconds' 값은 제일 앞의 행의 시간을 사용합니다.

출력 형식 예시:
[
    {
        "speaker": 1,
        "start_time_seconds": 0.0,
        "transcript": "안녕하세요. 회의를 시작하겠습니다."
    },
    {
        "speaker": 2,
        "start_time_seconds": 5.2,
        "transcript": "네, 좋습니다."
    }
]

JSON 배열만 출력하고, 추가 설명이나 마크다운 코드 블록은 포함하지 마세요.
"""

        # 4. 모델에 멀티모달 프롬프트 전송
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

        print("✅ 음성 인식 완료")

        # 5. 결과 정리 및 반환
        cleaned_response = response.text.strip()

        # 마크다운 코드 블록 제거
        cleaned_response = cleaned_response.replace("```json", "").replace("```", "").strip()

        # JSON 파싱 시도
        try:
            result_json = json.loads(cleaned_response)
            return result_json
        except json.JSONDecodeError as e:
            print(f"⚠️ JSON 파싱 오류: {e}")
            print("원본 응답을 문자열로 반환합니다.")
            return {"raw_response": cleaned_response}

    except FileNotFoundError:
        print(f"❌ 오류: 파일을 찾을 수 없습니다 - {local_audio_path}")
        return None
    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        return None


def save_result_to_json(result: dict, output_file: str):
    """
    결과를 JSON 파일로 저장합니다.

    Args:
        result: 결과 데이터
        output_file: 출력 파일 경로
    """
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"💾 결과 저장 완료: {output_file}")


def convert_to_simple_format(result: list) -> str:
    """
    JSON 결과를 간단한 텍스트 형식으로 변환합니다.

    Args:
        result: JSON 결과 리스트

    Returns:
        "Speaker 1: 안녕하세요" 형식의 텍스트
    """
    if not isinstance(result, list):
        return str(result)

    lines = []
    for item in result:
        speaker = item.get("speaker", "Unknown")
        transcript = item.get("transcript", "")
        lines.append(f"Speaker {speaker}: {transcript}")

    return "\n".join(lines)


def main():
    """메인 실행 함수"""
    import argparse

    parser = argparse.ArgumentParser(description="Gemini 2.5 Pro를 사용한 오디오 화자 분리")
    parser.add_argument("audio_file", help="입력 오디오 파일 경로")
    parser.add_argument("--output-json", help="출력 JSON 파일 경로 (선택)")
    parser.add_argument("--output-txt", help="출력 TXT 파일 경로 (선택)")
    parser.add_argument("--api-key", help="Google API 키 (환경변수 우선)", default=None)

    args = parser.parse_args()

    # API 키 설정 (우선순위: 명령줄 인자 > 환경변수)
    api_key = args.api_key or os.environ.get("GOOGLE_API_KEY")

    if not api_key:
        print("⚠️ 경고: API 키가 설정되지 않았습니다.")
        print("환경변수 GOOGLE_API_KEY를 설정하거나 --api-key 옵션을 사용하세요.")
        print("gcloud auth application-default login으로 인증한 경우 이 경고를 무시할 수 있습니다.")

    # 파일 존재 확인
    if not os.path.exists(args.audio_file):
        print(f"❌ 오류: 파일이 존재하지 않습니다 - {args.audio_file}")
        return

    print("="*60)
    print("🎯 Gemini 2.5 Pro 오디오 화자 분리 시작")
    print("="*60)
    print(f"입력 파일: {args.audio_file}")
    print("="*60)

    # 음성 인식 실행
    result = transcribe_diarize_gemini_ai_studio(args.audio_file, api_key)

    if result:
        # JSON 파일로 저장
        if args.output_json:
            save_result_to_json(result, args.output_json)

        # TXT 파일로 저장
        if args.output_txt:
            simple_text = convert_to_simple_format(result)
            with open(args.output_txt, "w", encoding="utf-8") as f:
                f.write(simple_text)
            print(f"💾 텍스트 저장 완료: {args.output_txt}")

        # 결과 출력
        print("\n" + "="*60)
        print("📊 변환 결과")
        print("="*60)

        if isinstance(result, list):
            simple_text = convert_to_simple_format(result)
            print(simple_text)
            print("\n" + "="*60)
            print(f"총 {len(result)}개 세그먼트 인식됨")
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))

        print("="*60)
        print("✅ 작업 완료!")
    else:
        print("❌ 음성 인식 실패")


if __name__ == "__main__":
    main()
