"""
회의록 TTS-STT 정확도 테스트 스크립트 (Google Gemini STT 사용)

이 스크립트는 다음을 수행합니다:
1. txt 파일에서 회의록 스크립트 읽기
2. OpenAI TTS API로 오디오 파일 생성
3. Google Gemini STT API로 오디오 인식하여 텍스트로 변환 (신뢰도 포함)
4. 원본 스크립트와 인식된 스크립트 비교하여 정확도 측정
"""

import os
import re
import io
import json
import pandas as pd
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
from openai import OpenAI
from pydub import AudioSegment
from google import genai
from google.genai import types
import argparse
from difflib import SequenceMatcher


# 환경 변수 로드
load_dotenv()


# OpenAI TTS 설정
TTS_MODEL = "tts-1-hd"  # 또는 "tts-1"
SPEAKER_VOICES = {
    "Speaker 1": "alloy",  # 중성적인 음성
    "Speaker 2": "echo",   # 남성적인 음성
    "Speaker 3": "fable",  # 영국식 억양
    "Speaker 4": "onyx",   # 깊은 남성 음성
}


def parse_meeting_text(text_content: str) -> List[Dict[str, str]]:
    """
    회의록 텍스트를 파싱하여 화자와 대화 내용을 추출합니다.

    Args:
        text_content: 회의록 텍스트 (형식: "Speaker 1: 안녕하세요")

    Returns:
        파싱된 데이터 리스트 [{"speaker": "Speaker 1", "transcript": "안녕하세요"}, ...]
    """
    parsed_data = []
    file_like_object = io.StringIO(text_content)

    for line in file_like_object:
        clean_line = line.strip()

        # 빈 줄은 건너뜀
        if not clean_line:
            continue

        # "Speaker X: " 형식 파싱
        parts = clean_line.split(": ", 1)

        if len(parts) == 2:
            speaker = parts[0].strip()
            transcript = parts[1].strip()
            parsed_data.append({"speaker": speaker, "transcript": transcript})

    return parsed_data


def merge_consecutive_speakers(parsed_data: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """
    연속적으로 동일한 화자의 발언을 하나로 합칩니다.

    Args:
        parsed_data: 파싱된 회의록 데이터 [{"speaker": "Speaker 1", "transcript": "안녕"}, ...]

    Returns:
        병합된 회의록 데이터
    """
    if not parsed_data:
        return []

    merged_data = []
    current_item = parsed_data[0].copy()

    for next_item in parsed_data[1:]:
        if current_item['speaker'] == next_item['speaker']:
            # 동일 화자면 transcript를 합침 (공백으로 구분)
            current_item['transcript'] += ' ' + next_item['transcript']
        else:
            # 화자가 다르면 현재 항목을 결과에 추가하고 다음 항목으로 이동
            merged_data.append(current_item)
            current_item = next_item.copy()

    # 마지막 항목 추가
    merged_data.append(current_item)

    print(f"✅ 연속 화자 병합: {len(parsed_data)}개 → {len(merged_data)}개 세그먼트")
    return merged_data


def save_to_csv(parsed_data: List[Dict[str, str]], filename: str) -> pd.DataFrame:
    """
    파싱된 회의록 데이터를 CSV 파일로 저장합니다.

    Args:
        parsed_data: 파싱된 회의록 데이터
        filename: 저장할 CSV 파일명

    Returns:
        저장된 DataFrame
    """
    df = pd.DataFrame(parsed_data)
    df.to_csv(filename, index=False, encoding="utf-8-sig")
    print(f"✅ CSV 파일 생성: {filename}")
    return df


def generate_audio_from_text(conversation: str, output_file: str) -> bool:
    """
    OpenAI TTS API를 사용하여 회의록 텍스트를 오디오로 변환합니다.

    Args:
        conversation: 회의록 텍스트
        output_file: 출력 오디오 파일명

    Returns:
        성공 여부
    """
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    # 대화 내용 파싱
    dialogue_blocks = conversation.strip().split("\n")
    dialogue_parts = []

    for block in dialogue_blocks:
        if block.strip():
            match = re.match(r"(Speaker \d+): (.*)", block, re.DOTALL)
            if match:
                speaker = match.group(1)
                dialogue = match.group(2)
                dialogue_parts.append({"speaker": speaker, "dialogue": dialogue})

    # 각 파트별 오디오 생성
    all_audio_segments = []

    for part in dialogue_parts:
        speaker = part["speaker"]
        dialogue = part["dialogue"]
        voice_name = SPEAKER_VOICES.get(speaker, "alloy")

        print(f"🎤 {speaker} 음성 생성 중 (voice: {voice_name})...")

        try:
            response = client.audio.speech.create(
                model=TTS_MODEL,
                voice=voice_name,
                input=dialogue,
                response_format="wav",
            )

            audio_data = response.content
            audio_segment = AudioSegment.from_file(io.BytesIO(audio_data), format="wav")
            all_audio_segments.append(audio_segment)
            print("  ✅ 성공")

        except Exception as e:
            print(f"  ❌ 실패: {e}")
            return False

    # 모든 오디오 세그먼트 결합
    if all_audio_segments:
        print("\n🔗 오디오 결합 중...")
        combined_audio = all_audio_segments[0]
        for segment in all_audio_segments[1:]:
            combined_audio += segment

        combined_audio.export(output_file, format="wav")
        print(f"✅ 오디오 파일 생성: {output_file}")
        return True
    else:
        print("❌ 오디오 생성 실패")
        return False


def recognize_audio_with_gemini(audio_file: str, api_key: str = None) -> Optional[List[Dict[str, Any]]]:
    """
    Google Gemini STT API를 사용하여 오디오를 텍스트로 변환합니다.

    Args:
        audio_file: 인식할 오디오 파일명
        api_key: Google API 키 (선택)

    Returns:
        인식 결과 리스트 또는 None
    """
    print(f"\n🎧 Gemini STT API로 음성 인식 중: {audio_file}")

    try:
        # Client 생성
        if api_key:
            client = genai.Client(api_key=api_key)
        else:
            client = genai.Client()

        print(f"📤 '{audio_file}' 파일을 업로드 중입니다...")

        # 로컬 파일을 바이너리로 읽기
        with open(audio_file, "rb") as f:
            file_bytes = f.read()

        # 파일 확장자에 따른 MIME 타입 결정
        file_ext = os.path.splitext(audio_file)[1].lower()
        mime_type_map = {
            ".wav": "audio/wav",
            ".mp3": "audio/mp3",
            ".m4a": "audio/mp4",
            ".flac": "audio/flac",
            ".ogg": "audio/ogg",
        }
        mime_type = mime_type_map.get(file_ext, "audio/wav")

        print(f"✅ 파일 업로드 완료 (타입: {mime_type})")

        prompt = """
당신은 전문적인 회의록 작성자입니다. 제공된 오디오 파일을 듣고 다음 작업을 수행해 주십시오:
1. 전체 대화를 정확하게 텍스트로 변환합니다.
2. 각 발화에 대해 화자를 숫자로 구분합니다. 발화자의 등장 순서대로 번호를 할당합니다. 참고로, 현재 오디오의 화자수는 총 4명입니다. 화자의 숫자는 4를 넘지 않습니다.
3. 각 발화에 대해 음성 인식의 신뢰도를 0.0~1.0 사이의 값으로 평가합니다. 음질, 발음 명확도, 배경 소음 등을 고려하여 추정합니다.
4. 최종 결과는 아래의 JSON 형식과 정확히 일치해야 합니다. 각 JSON 객체는 'speaker', 'start_time_seconds', 'confidence', 'transcript' 키를 포함해야 합니다.
5. speaker가 동일한 경우 하나의 행으로 만듭니다. 하나의 행으로 만드는 경우 'start_time_seconds' 값은 제일 앞의 행의 시간을 사용하고, confidence는 평균값을 사용합니다.

출력 형식 예시:
[
    {
        "speaker": 1,
        "start_time_seconds": 0.0,
        "confidence": 0.95,
        "transcript": "안녕하세요. 회의를 시작하겠습니다."
    },
    {
        "speaker": 2,
        "start_time_seconds": 5.2,
        "confidence": 0.92,
        "transcript": "네, 좋습니다."
    }
]

JSON 배열만 출력하고, 추가 설명이나 마크다운 코드 블록은 포함하지 마세요.
"""

        # 모델에 멀티모달 프롬프트 전송
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

        # 결과 정리
        cleaned_response = response.text.strip()
        cleaned_response = cleaned_response.replace("```json", "").replace("```", "").strip()

        # JSON 파싱
        try:
            result_list = json.loads(cleaned_response)
            return result_list
        except json.JSONDecodeError as e:
            print(f"⚠️ JSON 파싱 오류: {e}")
            print(f"원본 응답: {cleaned_response[:500]}")
            return None

    except FileNotFoundError:
        print(f"❌ 오류: 파일을 찾을 수 없습니다 - {audio_file}")
        return None
    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        return None


def calculate_accuracy(original_df: pd.DataFrame, recognized_segments: List[Dict[str, Any]]) -> Dict[str, float]:
    """
    원본 스크립트와 인식된 스크립트의 정확도를 계산합니다.

    Args:
        original_df: 원본 회의록 DataFrame
        recognized_segments: 인식된 세그먼트 리스트

    Returns:
        정확도 메트릭 딕셔너리
    """
    # 인식된 세그먼트를 DataFrame으로 변환
    recognized_df = pd.DataFrame(recognized_segments)

    # 화자 번호 정규화 (Speaker 제거)
    original_speakers = original_df['speaker'].str.replace("Speaker ", "", regex=False).astype(int)
    recognized_speakers = recognized_df['speaker'].astype(int)

    # 화자 인식 정확도 (길이가 다를 수 있으므로 최소 길이만큼만 비교)
    min_len = min(len(original_speakers), len(recognized_speakers))
    speaker_accuracy = (original_speakers[:min_len] == recognized_speakers[:min_len]).sum() / min_len * 100

    # 텍스트 유사도 계산
    text_similarities = []
    for i in range(min_len):
        original_text = original_df.iloc[i]['transcript']
        recognized_text = recognized_df.iloc[i]['transcript']

        # SequenceMatcher를 사용한 유사도 계산
        similarity = SequenceMatcher(None, original_text, recognized_text).ratio() * 100
        text_similarities.append(similarity)

    avg_text_similarity = sum(text_similarities) / len(text_similarities) if text_similarities else 0

    # 세그먼트 수 일치율
    segment_match_rate = min_len / max(len(original_df), len(recognized_df)) * 100

    # 전체 텍스트 비교
    original_full_text = " ".join(original_df['transcript'].tolist())
    recognized_full_text = " ".join(recognized_df['transcript'].tolist())
    overall_similarity = SequenceMatcher(None, original_full_text, recognized_full_text).ratio() * 100

    # 평균 신뢰도 계산
    avg_confidence = 0.0
    if 'confidence' in recognized_df.columns:
        avg_confidence = recognized_df['confidence'].mean()

    return {
        "화자_인식_정확도": round(speaker_accuracy, 2),
        "평균_텍스트_유사도": round(avg_text_similarity, 2),
        "전체_텍스트_유사도": round(overall_similarity, 2),
        "세그먼트_일치율": round(segment_match_rate, 2),
        "평균_신뢰도": round(avg_confidence, 2),
        "원본_세그먼트_수": len(original_df),
        "인식_세그먼트_수": len(recognized_df)
    }


def save_comparison_csv(original_df: pd.DataFrame, recognized_segments: List[Dict[str, Any]], output_file: str):
    """
    원본과 인식 결과를 비교한 CSV 파일을 생성합니다.

    Args:
        original_df: 원본 회의록 DataFrame
        recognized_segments: 인식된 세그먼트 리스트
        output_file: 출력 CSV 파일명
    """
    # 인식 결과를 DataFrame으로 변환
    recognized_df = pd.DataFrame(recognized_segments)

    # 컬럼명 변경
    recognized_df = recognized_df.rename(columns={
        'speaker': 'recognized_speaker',
        'transcript': 'recognized_text',
        'start_time_seconds': 'start_time'
    })

    # 원본과 인식 결과 병합
    comparison_df = pd.concat([
        original_df.reset_index(drop=True),
        recognized_df.reset_index(drop=True)
    ], axis=1)

    # 화자 번호 정규화
    comparison_df['speaker_num'] = comparison_df['speaker'].str.replace("Speaker ", "", regex=False).astype(int)

    # 저장
    comparison_df.to_csv(output_file, index=False, encoding="utf-8-sig")
    print(f"✅ 비교 결과 저장: {output_file}")


def print_accuracy_report(accuracy_metrics: Dict[str, float]):
    """
    정확도 보고서를 출력합니다.

    Args:
        accuracy_metrics: 정확도 메트릭 딕셔너리
    """
    print("\n" + "="*60)
    print("📊 정확도 분석 결과 (Gemini STT)")
    print("="*60)
    print(f"화자 인식 정확도:      {accuracy_metrics['화자_인식_정확도']:.2f}%")
    print(f"평균 텍스트 유사도:    {accuracy_metrics['평균_텍스트_유사도']:.2f}%")
    print(f"전체 텍스트 유사도:    {accuracy_metrics['전체_텍스트_유사도']:.2f}%")
    print(f"세그먼트 일치율:       {accuracy_metrics['세그먼트_일치율']:.2f}%")
    print(f"평균 신뢰도:           {accuracy_metrics['평균_신뢰도']:.2f}")
    print(f"원본 세그먼트 수:      {accuracy_metrics['원본_세그먼트_수']}")
    print(f"인식 세그먼트 수:      {accuracy_metrics['인식_세그먼트_수']}")
    print("="*60)


def main():
    """메인 실행 함수"""
    parser = argparse.ArgumentParser(description="회의록 TTS-STT 정확도 테스트 (Gemini STT)")
    parser.add_argument("input_txt", help="입력 회의록 txt 파일 경로")
    parser.add_argument("--output-prefix", default="meeting", help="출력 파일명 접두사 (기본값: meeting)")
    parser.add_argument("--api-key", help="Google API 키 (환경변수 우선)", default=None)

    args = parser.parse_args()

    # 파일 경로 설정
    input_txt = args.input_txt
    output_prefix = args.output_prefix
    csv_file = f"{output_prefix}.csv"
    audio_file = f"{output_prefix}.wav"
    comparison_file = f"{output_prefix}_comparison.csv"

    # API 키 설정
    api_key = args.api_key or os.environ.get("GOOGLE_API_KEY")

    print("="*60)
    print("🎯 회의록 TTS-STT 정확도 테스트 시작 (Gemini STT)")
    print("="*60)
    print(f"입력 파일: {input_txt}")
    print(f"출력 CSV: {csv_file}")
    print(f"출력 오디오: {audio_file}")
    print(f"비교 결과: {comparison_file}")
    print("="*60)

    # 1. txt 파일 읽기
    print("\n📖 Step 1: 회의록 텍스트 파일 읽기")
    if not os.path.exists(input_txt):
        print(f"❌ 오류: 파일을 찾을 수 없습니다 - {input_txt}")
        return

    with open(input_txt, "r", encoding="utf-8") as f:
        meeting_text = f.read()

    print(f"✅ 텍스트 파일 읽기 완료: {len(meeting_text)} 문자")

    # 2. 텍스트 파싱 및 CSV 저장
    print("\n📝 Step 2: 텍스트 파싱 및 연속 화자 병합")
    parsed_data = parse_meeting_text(meeting_text)
    print(f"✅ 파싱 완료: {len(parsed_data)}개 세그먼트")

    # 연속된 동일 화자 병합
    merged_data = merge_consecutive_speakers(parsed_data)

    # CSV 저장
    original_df = save_to_csv(merged_data, csv_file)

    # 3. OpenAI TTS로 오디오 생성
    print("\n🎵 Step 3: OpenAI TTS로 오디오 생성")
    success = generate_audio_from_text(meeting_text, audio_file)
    if not success:
        print("❌ 오디오 생성 실패")
        return

    # 4. Gemini STT API로 음성 인식
    print("\n🎧 Step 4: Gemini STT API로 음성 인식")
    result = recognize_audio_with_gemini(audio_file, api_key)
    if not result:
        print("❌ 음성 인식 실패")
        return

    print(f"✅ 인식 완료: {len(result)}개 세그먼트")

    # 5. 정확도 계산
    print("\n🔍 Step 5: 정확도 계산")
    accuracy_metrics = calculate_accuracy(original_df, result)

    # 6. 비교 결과 저장
    print("\n💾 Step 6: 비교 결과 저장")
    save_comparison_csv(original_df, result, comparison_file)

    # 7. 결과 출력
    print_accuracy_report(accuracy_metrics)

    print("\n✅ 모든 작업 완료!")


if __name__ == "__main__":
    main()
