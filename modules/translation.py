"""
번역 모듈 - Gemini API를 사용한 다국어 번역

지원 언어:
- 한국어 (ko)
- 영어 (en)
- 일본어 (ja)
- 독일어 (de)
"""

import logging
from google import genai
from google.genai import types
import os
import time
from typing import List, Dict, Optional
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

# 언어 코드와 이름 매핑
LANGUAGE_MAP = {
    "ko": "한국어",
    "en": "English",
    "ja": "日本語",
    "de": "Deutsch",
    "unknown": "Unknown",
}


def get_gemini_client():
    """Gemini API 클라이언트 초기화"""
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY 환경 변수가 설정되지 않았습니다")

    client = genai.Client(api_key=api_key)
    return client


def translate_text(
    text: str, target_language: str, source_language: str = "ko", max_retries: int = 3
) -> Optional[str]:
    """
    텍스트를 지정된 언어로 번역 (재시도 및 긴 텍스트 처리 지원)

    Args:
        text: 번역할 텍스트
        target_language: 목표 언어 코드 (en, ja, de, ko)
        source_language: 원본 언어 코드 (기본값: ko)
        max_retries: 최대 재시도 횟수 (기본값: 3)

    Returns:
        번역된 텍스트 또는 None (오류 시)
    """
    if not text or not text.strip():
        return text

    if source_language == target_language:
        return text

    # 텍스트 길이 체크 (5000자 이상이면 분할)
    MAX_CHUNK_LENGTH = 5000
    if len(text) > MAX_CHUNK_LENGTH:
        logging.info(f"📏 긴 텍스트 감지 ({len(text)}자), 분할 번역 수행")

        # 문장 단위로 분할 (마침표, 느낌표, 물음표 기준)
        sentences = []
        current_chunk = ""

        for sentence in (
            text.replace("! ", "!|").replace("? ", "?|").replace(". ", ".|").split("|")
        ):
            if len(current_chunk) + len(sentence) <= MAX_CHUNK_LENGTH:
                current_chunk += sentence
            else:
                if current_chunk:
                    sentences.append(current_chunk)
                current_chunk = sentence

        if current_chunk:
            sentences.append(current_chunk)

        # 각 청크 번역
        translated_chunks = []
        for i, chunk in enumerate(sentences, 1):
            logging.info(f"  📝 청크 {i}/{len(sentences)} 번역 중 ({len(chunk)}자)")
            translated_chunk = translate_text(
                chunk, target_language, source_language, max_retries
            )
            if translated_chunk is None:
                logging.error(f"  ❌ 청크 {i} 번역 실패")
                return None
            translated_chunks.append(translated_chunk)
            time.sleep(0.5)  # 청크 간 딜레이

        return " ".join(translated_chunks)

    # 재시도 로직
    for attempt in range(1, max_retries + 1):
        try:
            client = get_gemini_client()

            # 언어 이름 가져오기
            target_lang_name = LANGUAGE_MAP.get(target_language, target_language)
            source_lang_name = LANGUAGE_MAP.get(source_language, source_language)

            # 번역 프롬프트 생성
            prompt = f"""Translate the following text from {source_lang_name} to {target_lang_name}.
Only provide the translation without any explanations or additional text.

Text to translate:
{text}

Translation:"""

            # Gemini API 호출
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.3,
                    max_output_tokens=4096,  # 긴 텍스트 처리를 위해 증가
                ),
            )

            # 응답 확인
            if not response or not hasattr(response, "text") or response.text is None:
                error_msg = f"API 응답이 비어있음 (텍스트 길이: {len(text)})"
                if hasattr(response, "candidates") and response.candidates:
                    error_msg += (
                        f", finish_reason: {response.candidates[0].finish_reason}"
                    )

                if attempt < max_retries:
                    wait_time = 2 ** (attempt - 1)  # exponential backoff: 1초, 2초, 4초
                    logging.warning(
                        f"⚠️  번역 실패 (시도 {attempt}/{max_retries}): {error_msg}"
                    )
                    logging.info(f"   🔄 {wait_time}초 후 재시도...")
                    time.sleep(wait_time)
                    continue
                else:
                    logging.error(f"❌ 번역 오류 (최종 실패): {error_msg}")
                    return None

            translated_text = response.text.strip()

            if attempt > 1:
                logging.info(f"✅ 재시도 성공 (시도 {attempt}/{max_retries})")

            return translated_text

        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}"

            if attempt < max_retries:
                wait_time = 2 ** (attempt - 1)  # exponential backoff
                logging.warning(
                    f"⚠️  번역 오류 (시도 {attempt}/{max_retries}): {error_msg}"
                )
                logging.info(f"   🔄 {wait_time}초 후 재시도...")
                time.sleep(wait_time)
                continue
            else:
                logging.error(f"❌ 번역 오류 (최종 실패): {error_msg}")
                import traceback

                logging.error(f"   스택 트레이스: {traceback.format_exc()}")
                return None

    return None


def translate_segments(
    segments: List[Dict], target_language: str, source_language: str = "ko"
) -> List[Dict]:
    """
    여러 세그먼트를 한 번에 일괄 번역 (전체를 하나로 합쳐서 번역)

    Args:
        segments: 번역할 세그먼트 리스트
        target_language: 목표 언어 코드
        source_language: 원본 언어 코드 (기본값: ko)

    Returns:
        번역된 세그먼트 리스트 (translated_text 필드 추가)
    """
    total = len(segments)

    logging.info(
        f"🔄 일괄 번역 시작: {total}개 세그먼트 ({source_language} → {target_language})"
    )

    # 1. 모든 세그먼트의 텍스트를 하나로 합치기 (공백행으로 구분)
    combined_text = "\n\n".join([segment.get("text", "") for segment in segments])

    logging.info(f"  📝 전체 텍스트 길이: {len(combined_text)}자")
    logging.info(f"  🔄 Gemini로 한 번에 번역 중...")

    # 2. 전체 텍스트를 한 번에 번역
    try:
        client = get_gemini_client()

        # 언어 이름 가져오기
        target_lang_name = LANGUAGE_MAP.get(target_language, target_language)
        source_lang_name = LANGUAGE_MAP.get(source_language, source_language)

        # 번역 프롬프트 생성
        prompt = f"""Translate the following text from {source_lang_name} to {target_lang_name}.
The text contains multiple segments separated by blank lines.
Preserve the blank line separations in your translation.
Only provide the translation without any explanations or additional text.

Text to translate:
{combined_text}

Translation:"""

        # Gemini API 호출 (충분한 타임아웃과 토큰 설정)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.3,
                max_output_tokens=8192,  # 긴 텍스트 처리
            ),
        )

        # 응답 확인
        if not response or not hasattr(response, "text") or response.text is None:
            error_msg = f"API 응답이 비어있음"
            if hasattr(response, "candidates") and response.candidates:
                error_msg += f", finish_reason: {response.candidates[0].finish_reason}"

            logging.error(f"❌ 번역 오류: {error_msg}")
            # 실패 시 원본 반환
            return [
                {
                    **segment,
                    "translated_text": segment.get("text", ""),
                    "translated_language": target_language,
                    "original_language": source_language,
                    "translation_failed": True,
                }
                for segment in segments
            ]

        translated_combined = response.text.strip()
        logging.info(f"  ✅ 번역 완료 ({len(translated_combined)}자)")

        # 3. 번역된 텍스트를 다시 공백행으로 분리
        translated_texts = translated_combined.split("\n\n")

        logging.info(f"  📊 분리된 세그먼트: {len(translated_texts)}개")

        # 4. 각 세그먼트에 번역 결과 저장
        translated_segments = []
        for idx, segment in enumerate(segments):
            # 번역된 텍스트가 있으면 사용, 없으면 원본 사용
            if idx < len(translated_texts):
                translated_text = translated_texts[idx].strip()
                translation_failed = False
            else:
                translated_text = segment.get("text", "")
                translation_failed = True
                logging.warning(f"  ⚠️  세그먼트 {idx + 1}: 번역 결과 부족, 원본 사용")

            # 세그먼트에 번역 정보 추가
            translated_segment = segment.copy()
            translated_segment["translated_text"] = translated_text
            translated_segment["translated_language"] = target_language
            translated_segment["original_language"] = source_language
            translated_segment["translation_failed"] = translation_failed

            translated_segments.append(translated_segment)

        # 최종 결과 로그
        failed_count = sum(1 for seg in translated_segments if seg.get("translation_failed", False))
        success_count = total - failed_count

        logging.info(
            f"✅ 일괄 번역 완료: 성공 {success_count}개, 실패 {failed_count}개 (총 {total}개)"
        )

        if failed_count > 0:
            logging.warning(f"⚠️  {failed_count}개 세그먼트는 원본 텍스트로 표시됩니다")

        return translated_segments

    except Exception as e:
        logging.error(f"❌ 일괄 번역 오류: {e}")
        import traceback
        logging.error(f"   스택 트레이스: {traceback.format_exc()}")

        # 오류 발생 시 모든 세그먼트를 원본으로 반환
        return [
            {
                **segment,
                "translated_text": segment.get("text", ""),
                "translated_language": target_language,
                "original_language": source_language,
                "translation_failed": True,
            }
            for segment in segments
        ]


def detect_language(text: str) -> str:
    """
    텍스트의 언어를 자동 감지 (개선된 버전)

    Args:
        text: 언어를 감지할 텍스트

    Returns:
        언어 코드 (ko, en, ja, de 중 하나, 기본값: ko)
    """
    if not text or not text.strip():
        return "unknown"

    try:
        client = get_gemini_client()

        # 더 많은 텍스트 샘플 사용 (최대 500자)
        sample_text = text[:500].strip()

        # 매우 간결한 프롬프트 사용
        prompt = f"""Detect language. Reply with ONLY: ko, en, ja, or de

Text: {sample_text}

Code:"""

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.0,
                max_output_tokens=8192,
            ),
        )

        # 응답 텍스트 추출
        if hasattr(response, "text") and response.text:
            detected_lang = response.text.strip().lower()
        elif hasattr(response, "candidates") and response.candidates:
            detected_lang = response.candidates[0].content.parts[0].text.strip().lower()
        else:
            logging.warning("⚠️ API 응답이 비어있습니다. 기본값(unknown) 사용")
            return "unknown"

        # 응답이 여러 줄이거나 추가 텍스트가 있는 경우 첫 단어만 추출
        detected_lang = detected_lang.split()[0] if detected_lang else "unknown"

        # 유효한 언어 코드인지 확인
        if detected_lang in LANGUAGE_MAP:
            logging.info(
                f"✅ 언어 감지 완료: {detected_lang} (샘플: {sample_text[:50]}...)"
            )
            return detected_lang
        else:
            logging.warning(
                f"⚠️ 알 수 없는 언어 코드: {detected_lang}, 기본값(unknown) 사용"
            )
            return "unknown"

    except Exception as e:
        logging.error(f"❌ 언어 감지 오류: {e}")
        return "unknown"


if __name__ == "__main__":
    # 테스트 코드
    logging.basicConfig(level=logging.INFO)

    test_text = "안녕하세요, 이것은 테스트입니다."

    print("=== 번역 테스트 ===")
    print(f"원본 (한국어): {test_text}\n")

    # 영어로 번역
    en_text = translate_text(test_text, "en", "ko")
    print(f"영어: {en_text}\n")

    # 일본어로 번역
    ja_text = translate_text(test_text, "ja", "ko")
    print(f"일본어: {ja_text}\n")

    # 독일어로 번역
    de_text = translate_text(test_text, "de", "ko")
    print(f"독일어: {de_text}\n")

    # 언어 감지 테스트
    print("=== 언어 감지 테스트 ===")
    print(f"감지된 언어: {detect_language(test_text)}")
