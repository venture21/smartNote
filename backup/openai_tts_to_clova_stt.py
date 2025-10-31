"""
회의록 TTS-STT 정확도 테스트 스크립트

이 스크립트는 다음을 수행합니다:
1. txt 파일에서 회의록 스크립트 읽기
2. OpenAI TTS API로 오디오 파일 생성
3. Clova Speech API로 오디오 인식하여 텍스트로 변환
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
from myClovaSpeech import ClovaSpeechClient
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


def recognize_audio_with_clova(audio_file: str) -> Optional[Dict[str, Any]]:
    """
    Clova Speech API를 사용하여 오디오를 텍스트로 변환합니다.

    Args:
        audio_file: 인식할 오디오 파일명

    Returns:
        인식 결과 JSON 또는 None
    """
    print(f"\n🎧 Clova Speech API로 음성 인식 중: {audio_file}")

    try:
        res = ClovaSpeechClient().req_upload(
            file=audio_file,
            completion="sync",
            diarization={"enable": True}  # 화자 분리 활성화
        )

        if res.status_code == 200:
            result = res.json()
            print("✅ 음성 인식 완료")
            return result
        else:
            print(f"❌ 음성 인식 실패: {res.status_code}")
            return None

    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        return None


def merge_consecutive_speaker_segments(segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    연속적으로 동일한 화자의 세그먼트를 하나의 텍스트로 합칩니다.

    Args:
        segments: 인식된 세그먼트 리스트

    Returns:
        병합된 세그먼트 리스트
    """
    if not segments:
        return []

    merged_segments = []
    current_segment = segments[0].copy()

    for next_segment in segments[1:]:
        if current_segment['speaker'] == next_segment['speaker']:
            current_segment['text'] += ' ' + next_segment['text']
        else:
            merged_segments.append(current_segment)
            current_segment = next_segment.copy()

    merged_segments.append(current_segment)
    return merged_segments


def extract_recognized_segments(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Clova Speech API 결과에서 화자별 인식 결과를 추출합니다.

    Args:
        result: Clova Speech API 응답 JSON

    Returns:
        화자별 세그먼트 리스트
    """
    segments = result.get("segments", [])
    speaker_segments = []

    for segment in segments:
        speaker_label = segment["speaker"]["label"]
        text = segment["text"]
        confidence = segment.get("confidence", 0)
        start_time_ms = segment.get("start", 0)

        # Clova는 밀리초(ms) 단위이므로 초(s)로 변환
        start_time = start_time_ms / 1000.0

        speaker_segments.append({
            "start_time": start_time,
            "confidence": confidence,
            "speaker": speaker_label,
            "text": text
        })

    # 연속된 동일 화자 세그먼트 병합
    merged_segments = merge_consecutive_speaker_segments(speaker_segments)

    return merged_segments


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
        recognized_text = recognized_df.iloc[i]['text']

        # SequenceMatcher를 사용한 유사도 계산
        similarity = SequenceMatcher(None, original_text, recognized_text).ratio() * 100
        text_similarities.append(similarity)

    avg_text_similarity = sum(text_similarities) / len(text_similarities) if text_similarities else 0

    # 세그먼트 수 일치율
    segment_match_rate = min_len / max(len(original_df), len(recognized_df)) * 100

    # 전체 텍스트 비교
    original_full_text = " ".join(original_df['transcript'].tolist())
    recognized_full_text = " ".join(recognized_df['text'].tolist())
    overall_similarity = SequenceMatcher(None, original_full_text, recognized_full_text).ratio() * 100

    # 평균 신뢰도
    avg_confidence = recognized_df['confidence'].mean() if 'confidence' in recognized_df.columns else 0

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
        'text': 'recognized_text',
        'confidence': 'confidence',
        'start_time': 'start_time'
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
    print("📊 정확도 분석 결과")
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
    parser = argparse.ArgumentParser(description="회의록 TTS-STT 정확도 테스트")
    parser.add_argument("input_txt", help="입력 회의록 txt 파일 경로")
    parser.add_argument("--output-prefix", default="meeting", help="출력 파일명 접두사 (기본값: meeting)")

    args = parser.parse_args()

    # 파일 경로 설정
    input_txt = args.input_txt
    output_prefix = args.output_prefix
    csv_file = f"{output_prefix}.csv"
    audio_file = f"{output_prefix}.wav"
    comparison_file = f"{output_prefix}_comparison.csv"

    print("="*60)
    print("🎯 회의록 TTS-STT 정확도 테스트 시작")
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

    # 4. Clova Speech API로 음성 인식
    print("\n🎧 Step 4: Clova Speech API로 음성 인식")
    result = recognize_audio_with_clova(audio_file)
    if not result:
        print("❌ 음성 인식 실패")
        return

    # 5. 인식 결과 추출
    print("\n📊 Step 5: 인식 결과 추출 및 병합")
    recognized_segments = extract_recognized_segments(result)
    print(f"✅ 인식 완료: {len(recognized_segments)}개 세그먼트")

    # 6. 정확도 계산
    print("\n🔍 Step 6: 정확도 계산")
    accuracy_metrics = calculate_accuracy(original_df, recognized_segments)

    # 7. 비교 결과 저장
    print("\n💾 Step 7: 비교 결과 저장")
    save_comparison_csv(original_df, recognized_segments, comparison_file)

    # 8. 결과 출력
    print_accuracy_report(accuracy_metrics)

    print("\n✅ 모든 작업 완료!")


if __name__ == "__main__":
    main()
