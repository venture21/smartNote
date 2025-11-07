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


def recognize_with_gemini(audio_path, task_id=None, audio_duration=None):
    """
    Google Gemini STT API로 음성 인식 및 언어 감지

    Args:
        audio_path: 오디오 파일 경로
        task_id: 진행 상황 추적용 ID (optional)
        audio_duration: 오디오 파일의 총 길이 (초) (optional)

    Returns:
        tuple: (segments, processing_time, detected_language) 또는 (None, 0.0, 'unknown') on error
    """
    from modules.utils import update_progress, parse_mmss_to_seconds

    start_time = time.time()

    try:
        if task_id:
            update_progress(task_id, "stt", 0, "Gemini STT 시작")

        logging.info(f"🎧 Gemini STT API로 음성 인식 중: {audio_path}")

        # 파일 존재 확인
        if not os.path.exists(audio_path):
            error_msg = f"오디오 파일이 존재하지 않습니다: {audio_path}"
            logging.error(f"❌ {error_msg}")
            if task_id:
                update_progress(task_id, "stt", 100, f"오류: {error_msg}")
            return None, 0.0, "unknown"

        # 파일 크기 확인
        file_size = os.path.getsize(audio_path)
        file_size_mb = file_size / (1024 * 1024)
        logging.info(f"📁 파일 크기: {file_size_mb:.2f} MB")

        if file_size == 0:
            error_msg = f"오디오 파일이 비어있습니다: {audio_path}"
            logging.error(f"❌ {error_msg}")
            if task_id:
                update_progress(task_id, "stt", 100, f"오류: {error_msg}")
            return None, 0.0, "unknown"

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
        logging.info(f"🎵 MIME 타입: {mime_type}, 확장자: {file_ext}")

        prompt = """
당신은 전문적인 회의록 작성자입니다. 제공된 오디오 파일을 듣고 다음 작업을 수행해 주십시오:

작업 요구사항:
1. 전체 대화를 정확하게 텍스트로 변환합니다.

2. **화자 분리 (매우 중요)**:
   - 각 발화에 대해 화자를 숫자로 구분합니다
   - 발화자의 등장 순서대로 번호를 할당합니다 (1, 2, 3, ...)
   - 음성의 톤, 피치, 말투의 차이를 주의깊게 분석하여 정확하게 화자를 구분하세요
   - 화자가 바뀌면 반드시 새로운 세그먼트로 분리하세요

3. 각 발화에 대해 음성 인식의 신뢰도를 0.0~1.0 사이의 값으로 평가합니다.

4. start_time_mmss는 반드시 "시:분:초" 형식으로 출력합니다.
   예시: "0:00:05", "0:01:23", "1:05:30"

5. 배경음악과 발화자의 목소리가 섞인 경우 목소리만 잘 구별하여 가져온다.

6. **세그먼트 길이 제한**:
   - 동일 화자의 연속 발화를 하나의 세그먼트로 그룹화합니다
   - 단, 하나의 세그먼트가 4개 문장을 초과하면 적절한 위치에서 분리합니다

7. 대화 내용에 대한 누락이 발생하지 않게 주의하세요.
8. 세그먼트의 시작 시간을 정확하게 기록해주세요.

중요: 반드시 아래의 JSON 배열 형식으로만 출력하세요. 각 객체는 speaker, start_time_mmss, confidence, text 키를 포함해야 합니다.

출력 형식 (정확히 이 구조를 따르세요):
[
    {
        "speaker": 1,
        "start_time_mmss": "0:00:00",
        "confidence": 0.95,
        "text": "안녕하세요. 회의를 시작하겠습니다."
    },
    {
        "speaker": 2,
        "start_time_mmss": "0:00:05",
        "confidence": 0.92,
        "text": "네, 좋습니다."
    }
]

주의사항:
- 반드시 유효한 JSON 배열 형식으로 출력
- 추가 설명, 주석, 마크다운 코드 블록 없이 순수 JSON만 출력
- 모든 문자열은 큰따옴표(")로 감싸기
- 마지막 항목 뒤에는 쉼표 없음
"""

        logging.info("🤖 Gemini 2.5 Pro로 음성 인식 중...")

        try:
            response = client.models.generate_content(
                model="gemini-2.5-pro",
                contents=[
                    prompt,
                    types.Part.from_bytes(
                        data=file_bytes,
                        mime_type=mime_type,
                    ),
                ],
                config=types.GenerateContentConfig(
                    max_output_tokens=250000,  # 긴 대화록을 위해 출력 길이 증가
                    temperature=0.1,  # 정확성을 위해 낮은 temperature 사용
                    response_mime_type="application/json",  # JSON 형식 강제
                ),
            )
        except Exception as api_error:
            error_type = type(api_error).__name__
            error_msg = str(api_error)
            logging.error(f"❌ Gemini API 호출 오류 [{error_type}]: {error_msg}")
            logging.error(f"   파일: {audio_path} ({file_size_mb:.2f} MB)")
            logging.error(f"   MIME 타입: {mime_type}")

            if task_id:
                update_progress(
                    task_id, "stt", 100, f"API 오류 [{error_type}]: {error_msg[:100]}"
                )

            import traceback

            traceback.print_exc()
            return None, 0.0, "unknown"

        if task_id:
            update_progress(task_id, "stt", 50, "Gemini 응답 파싱 중")

        # 응답 검증
        if not response or not hasattr(response, "text") or response.text is None:
            error_msg = "Gemini API가 빈 응답을 반환했습니다"
            logging.error(f"❌ {error_msg}")
            logging.error(f"   파일: {audio_path} ({file_size_mb:.2f} MB)")

            # response 객체 디버깅 정보
            if response:
                logging.error(f"   response type: {type(response)}")
                logging.error(f"   response attributes: {dir(response)}")
                if hasattr(response, "candidates"):
                    logging.error(f"   candidates: {response.candidates}")
                if hasattr(response, "prompt_feedback"):
                    logging.error(f"   prompt_feedback: {response.prompt_feedback}")

            if task_id:
                update_progress(task_id, "stt", 100, f"오류: {error_msg}")
            return None, 0.0, "unknown"

        # 응답 파싱
        text = response.text.strip()

        # 빈 응답 체크
        if not text:
            error_msg = "Gemini API가 빈 텍스트를 반환했습니다"
            logging.error(f"❌ {error_msg}")
            logging.error(f"   파일: {audio_path} ({file_size_mb:.2f} MB)")
            if task_id:
                update_progress(task_id, "stt", 100, f"오류: {error_msg}")
            return None, 0.0, "unknown"

        # 마크다운 코드 블록 제거
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]

        if text.endswith("```"):
            text = text[:-3]

        text = text.strip()

        # 정리 후에도 빈 텍스트 체크
        if not text:
            error_msg = "응답 정리 후 빈 텍스트가 되었습니다"
            logging.error(f"❌ {error_msg}")
            logging.error(f"   원본 응답 길이: {len(response.text)}")
            if task_id:
                update_progress(task_id, "stt", 100, f"오류: {error_msg}")
            return None, 0.0, "unknown"

        # 제어 문자 처리 (JSON 파싱 에러 방지)
        # JSON 문자열 내의 제어 문자를 이스케이프 처리
        import re

        def escape_control_chars(match):
            """JSON 문자열 내의 제어 문자를 이스케이프"""
            char = match.group(0)
            if char == "\n":
                return "\\n"
            elif char == "\r":
                return "\\r"
            elif char == "\t":
                return "\\t"
            elif char == "\b":
                return "\\b"
            elif char == "\f":
                return "\\f"
            else:
                # 기타 제어 문자는 유니코드 이스케이프
                return f"\\u{ord(char):04x}"

        # JSON 문자열 값 내부의 제어 문자만 이스케이프 (구조는 유지)
        try:
            # "text": "..." 패턴에서 문자열 값의 제어 문자만 처리
            def fix_text_field(match):
                field_name = match.group(1)
                field_value = match.group(2)
                # 제어 문자를 이스케이프
                fixed_value = re.sub(r"[\x00-\x1f]", escape_control_chars, field_value)
                return f'"{field_name}": "{fixed_value}"'

            # "필드명": "값" 형태의 문자열 필드를 찾아서 제어 문자 이스케이프
            text = re.sub(
                r'"(text|start_time_mmss)":\s*"([^"]*(?:\\.[^"]*)*)"',
                fix_text_field,
                text,
                flags=re.DOTALL,
            )

        except Exception as e:
            logging.warning(f"⚠️ 제어 문자 이스케이프 중 오류 (무시): {e}")

        # JSON 사전 처리: 객체 사이 누락된 쉼표 추가
        try:
            # } 다음에 바로 { 가 오는 경우 (쉼표 누락)
            # }\n{ 또는 }\n\n{ 또는 } { 패턴을 },\n{ 로 변경
            text = re.sub(r"}\s*\n\s*{", "},\n{", text)
            text = re.sub(r"}\s+{", "},\n{", text)
        except Exception as e:
            logging.warning(f"⚠️ JSON 사전 처리 중 오류 (무시): {e}")

        # JSON 파싱 시도
        result = None
        try:
            result = json.loads(text)
        except json.JSONDecodeError as e:
            logging.warning(f"⚠️ 초기 JSON 파싱 실패: {e}")
            logging.warning(f"응답 길이: {len(text)} 문자")

            # 에러 위치 정보 출력
            if hasattr(e, "lineno") and hasattr(e, "colno"):
                error_line = (
                    text.split("\n")[e.lineno - 1]
                    if e.lineno <= len(text.split("\n"))
                    else ""
                )
                logging.warning(f"에러 위치: line {e.lineno}, column {e.colno}")
                logging.warning(f"에러 라인: {error_line[:100]}...")

            # 복구 시도를 위한 헬퍼 함수
            def try_parse_json(json_text):
                """JSON 파싱 시도 (제어 문자 처리 포함)"""
                try:
                    return json.loads(json_text)
                except json.JSONDecodeError:
                    # 제어 문자 처리 재시도
                    try:
                        fixed = re.sub(
                            r'"(text|start_time_mmss)":\s*"([^"]*(?:\\.[^"]*)*)"',
                            fix_text_field,
                            json_text,
                            flags=re.DOTALL,
                        )
                        return json.loads(fixed)
                    except:
                        return None

            # 복구 시도 0: 누락된 쉼표 추가
            if result is None and (
                "Expecting ',' delimiter" in str(e) or "Expecting ','" in str(e)
            ):
                fixed_text = re.sub(r"}\s*\n\s*{", "},\n{", text)
                fixed_text = re.sub(r"}\s+{", "},\n{", fixed_text)
                result = try_parse_json(fixed_text)
                if result:
                    logging.info(
                        f"✅ JSON 복구 성공 (쉼표 추가): {len(result)}개 세그먼트"
                    )

            # 복구 시도 0.5: Unterminated string 에러 처리
            if result is None and "Unterminated string" in str(e):
                try:
                    # 에러 위치(char position)를 파악
                    if hasattr(e, "pos"):
                        error_pos = e.pos
                        # 에러 위치 이전의 마지막 완전한 객체까지만 사용
                        truncated_text = text[:error_pos]
                        # 마지막 완전한 객체를 찾기
                        last_complete_brace = truncated_text.rfind("}")
                        if last_complete_brace > 0:
                            fixed_text = (
                                truncated_text[: last_complete_brace + 1] + "\n]"
                            )
                            result = try_parse_json(fixed_text)
                            if result:
                                logging.info(
                                    f"✅ JSON 복구 성공 (Unterminated string 처리): {len(result)}개 세그먼트"
                                )
                except Exception:
                    pass

            # 복구 시도 1: 불완전한 배열 닫기
            if result is None and text.startswith("[") and not text.endswith("]"):
                # 마지막 완전한 객체를 찾기 위해 역순으로 검색
                last_complete_brace = text.rfind("}")
                if last_complete_brace > 0:
                    fixed_text = text[: last_complete_brace + 1] + "\n]"
                    result = try_parse_json(fixed_text)
                    if result:
                        logging.info(
                            f"✅ JSON 복구 성공 (불완전한 배열 닫기): {len(result)}개 세그먼트"
                        )

            # 복구 시도 2: 마지막 불완전한 항목 제거
            if result is None and "," in text:
                # 마지막 콤마 이후 내용 제거하고 배열 닫기
                parts = text.rsplit(",", 1)
                if len(parts) == 2:
                    fixed_text = parts[0] + "\n]"
                    result = try_parse_json(fixed_text)
                    if result:
                        logging.info(
                            f"✅ JSON 복구 성공 (마지막 항목 제거): {len(result)}개 세그먼트"
                        )

            # 복구 시도 3: 불완전한 객체 제거 후 배열 닫기
            if result is None and text.startswith("["):
                # { 와 } 의 균형을 맞추기 위해 마지막 완전한 객체 찾기
                depth = 0
                last_valid_pos = -1
                for i, char in enumerate(text):
                    if char == "{":
                        depth += 1
                    elif char == "}":
                        depth -= 1
                        if depth == 0:
                            last_valid_pos = i

                if last_valid_pos > 0:
                    fixed_text = text[: last_valid_pos + 1] + "\n]"
                    result = try_parse_json(fixed_text)
                    if result:
                        logging.info(
                            f"✅ JSON 복구 성공 (깊이 분석): {len(result)}개 세그먼트"
                        )

            # 복구 시도 4: 줄바꿈으로 분리하여 유효한 JSON 객체만 추출
            if result is None:
                try:
                    lines = text.split("\n")
                    recovered_items = []
                    current_obj = ""
                    depth = 0

                    for line in lines:
                        current_obj += line
                        for char in line:
                            if char == "{":
                                depth += 1
                            elif char == "}":
                                depth -= 1

                        if depth == 0 and current_obj.strip():
                            # 완전한 객체일 수 있음
                            obj_text = current_obj.strip().rstrip(",")
                            obj = try_parse_json(obj_text)
                            if obj and isinstance(obj, dict):
                                recovered_items.append(obj)
                            current_obj = ""

                    if recovered_items:
                        result = recovered_items
                        logging.info(
                            f"✅ JSON 복구 성공 (라인 분석): {len(result)}개 세그먼트"
                        )
                except Exception:
                    pass

            # 모든 복구 시도 실패
            if result is None:
                logging.error(f"❌ JSON 복구 실패")
                logging.error(f"응답 텍스트 (처음 500자): {text[:500]}")
                logging.error(f"응답 텍스트 (마지막 500자): {text[-500:]}")
                if task_id:
                    update_progress(task_id, "stt", 100, f"JSON 파싱 오류: {str(e)}")
                return None, 0.0, "unknown"
            else:
                # 복구 성공 - 진행 상황 업데이트
                if task_id:
                    update_progress(
                        task_id,
                        "stt",
                        60,
                        f"JSON 복구 완료, {len(result)}개 세그먼트 파싱 중...",
                    )

        # 세그먼트 변환
        segments = []
        for idx, item in enumerate(result):
            start_time_str = item.get("start_time_mmss", "0:00:000")
            segment_start = parse_mmss_to_seconds(start_time_str)

            # end_time 계산: 다음 세그먼트의 start_time 또는 audio_duration
            end_time = None
            if idx < len(result) - 1:
                # 다음 세그먼트가 있으면 다음 세그먼트의 start_time 사용
                next_start_time_str = result[idx + 1].get("start_time_mmss", "0:00:000")
                end_time = parse_mmss_to_seconds(next_start_time_str)
            elif audio_duration is not None:
                # 마지막 세그먼트면 오디오 총 길이 사용
                end_time = audio_duration

            segments.append(
                {
                    "id": idx + 1,
                    "speaker": str(item.get("speaker", "Unknown")),
                    "start_time": segment_start,
                    "end_time": end_time,
                    "confidence": float(item.get("confidence", 0.0)),
                    "text": item.get("text", ""),
                }
            )

        # 긴 세그먼트 분할 (5개 이상의 문장인 경우)
        if task_id:
            update_progress(task_id, "stt", 70, "긴 세그먼트 분할 처리 중...")

        def split_long_segment(segment):
            """5개 이상의 문장을 가진 세그먼트를 분할"""
            text = segment["text"]

            # 문장 구분자로 분리 (한국어와 영어 모두 지원)
            import re

            # 문장 끝 패턴: . ! ? 뒤에 공백이나 줄바꿈
            sentences = re.split(r"([.!?]+[\s\n]+)", text)

            # 구분자를 문장에 다시 붙이기
            full_sentences = []
            for i in range(0, len(sentences) - 1, 2):
                if i + 1 < len(sentences):
                    full_sentences.append(sentences[i] + sentences[i + 1])
                else:
                    full_sentences.append(sentences[i])

            # 마지막 요소가 구분자가 아닌 경우 추가
            if len(sentences) % 2 == 1:
                full_sentences.append(sentences[-1])

            # 빈 문장 제거
            full_sentences = [s.strip() for s in full_sentences if s.strip()]

            # 5개 미만이면 분할하지 않음
            if len(full_sentences) < 5:
                return [segment]

            # 세그먼트 분할 (4개 문장씩)
            split_segments = []
            chunk_size = 4
            total_duration = (segment["end_time"] or segment["start_time"]) - segment[
                "start_time"
            ]

            for i in range(0, len(full_sentences), chunk_size):
                chunk_sentences = full_sentences[i : i + chunk_size]
                chunk_text = " ".join(chunk_sentences)

                # 시간 비율로 계산
                sentence_ratio = len(chunk_sentences) / len(full_sentences)
                chunk_start = segment["start_time"] + (
                    total_duration * (i / len(full_sentences))
                )
                chunk_end = segment["start_time"] + (
                    total_duration * ((i + len(chunk_sentences)) / len(full_sentences))
                )

                split_segments.append(
                    {
                        "id": segment["id"],  # ID는 나중에 재할당
                        "speaker": segment["speaker"],
                        "start_time": chunk_start,
                        "end_time": chunk_end,
                        "confidence": segment["confidence"],
                        "text": chunk_text,
                    }
                )

            return split_segments

        # 모든 세그먼트에 대해 분할 적용
        original_count = len(segments)
        split_segments = []
        for seg in segments:
            split_segments.extend(split_long_segment(seg))

        # ID 재할당
        for idx, seg in enumerate(split_segments, 1):
            seg["id"] = idx

        segments = split_segments

        if len(segments) > original_count:
            logging.info(f"📝 긴 세그먼트 분할: {original_count}개 → {len(segments)}개")

        # 언어 감지 (첫 번째 세그먼트 텍스트 사용)
        detected_language = "unknown"
        if segments and len(segments) > 0:
            first_text = segments[0].get("text", "")
            if first_text and first_text.strip():
                try:
                    if task_id:
                        update_progress(task_id, "stt", 80, "언어 감지 중...")

                    from modules.translation import detect_language

                    detected_language = detect_language(first_text)
                    logging.info(f"🌐 감지된 언어: {detected_language}")
                except Exception as e:
                    logging.warning(f"⚠️ 언어 감지 실패, 기본값(unknown) 사용: {e}")
                    detected_language = "unknown"

        processing_time = time.time() - start_time
        logging.info(
            f"✅ Gemini STT 완료: {len(segments)}개 세그먼트, 언어: {detected_language} ({processing_time:.2f}초)"
        )

        if task_id:
            update_progress(
                task_id, "stt", 100, f"STT 완료: {len(segments)}개 세그먼트"
            )

        return segments, processing_time, detected_language

    except Exception as e:
        error_type = type(e).__name__
        error_msg = str(e)

        logging.error(f"❌ Gemini STT 오류 발생")
        logging.error(f"   오류 타입: {error_type}")
        logging.error(f"   오류 메시지: {error_msg}")
        logging.error(f"   파일 경로: {audio_path}")

        # 파일 정보 출력 (파일이 존재하는 경우)
        try:
            if os.path.exists(audio_path):
                file_size = os.path.getsize(audio_path)
                file_size_mb = file_size / (1024 * 1024)
                file_ext = os.path.splitext(audio_path)[1].lower()
                logging.error(f"   파일 크기: {file_size_mb:.2f} MB")
                logging.error(f"   파일 확장자: {file_ext}")
            else:
                logging.error(f"   파일이 존재하지 않음")
        except:
            pass

        import traceback

        logging.error("   스택 트레이스:")
        traceback.print_exc()

        if task_id:
            update_progress(
                task_id, "stt", 100, f"오류 [{error_type}]: {error_msg[:100]}"
            )

        return None, 0.0, "unknown"
