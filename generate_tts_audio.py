"""
TTS 오디오 생성 스크립트
youtube_segments 테이블의 translated_text를 사용하여 Gemini TTS로 오디오 생성
"""

import os
import sqlite3
import logging
import mimetypes
import struct
from pathlib import Path
from google import genai
from google.genai import types
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv()

# 로깅 설정
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

DB_PATH = "csv/smartnote.db"
TTS_OUTPUT_DIR = "tts_audio"

# Speaker별 Voice 매핑 (최대 10명의 화자 지원)
SPEAKER_VOICES = {
    1: "Zephyr",  # Speaker 1
    2: "Puck",  # Speaker 2
    3: "Charon",  # Speaker 3
    4: "Kore",  # Speaker 4
    5: "Fenrir",  # Speaker 5
    6: "Leda",  # Speaker 6
    7: "Orus",  # Speaker 7
    8: "Aoede",  # Speaker 8
    9: "Autonoe",  # Speaker 9
    10: "Enceladus",  # Speaker 10
}


def convert_to_wav(audio_data: bytes, mime_type: str) -> bytes:
    """
    오디오 데이터를 WAV 형식으로 변환

    Args:
        audio_data: 원본 오디오 데이터
        mime_type: MIME 타입

    Returns:
        WAV 형식의 바이트 데이터
    """
    parameters = parse_audio_mime_type(mime_type)
    bits_per_sample = parameters["bits_per_sample"]
    sample_rate = parameters["rate"]
    num_channels = 1
    data_size = len(audio_data)
    bytes_per_sample = bits_per_sample // 8
    block_align = num_channels * bytes_per_sample
    byte_rate = sample_rate * block_align
    chunk_size = 36 + data_size

    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        chunk_size,
        b"WAVE",
        b"fmt ",
        16,
        1,
        num_channels,
        sample_rate,
        byte_rate,
        block_align,
        bits_per_sample,
        b"data",
        data_size,
    )
    return header + audio_data


def parse_audio_mime_type(mime_type: str) -> dict:
    """
    MIME 타입에서 오디오 파라미터 추출

    Args:
        mime_type: MIME 타입 문자열

    Returns:
        bits_per_sample과 rate를 포함한 딕셔너리
    """
    bits_per_sample = 16
    rate = 24000

    parts = mime_type.split(";")
    for param in parts:
        param = param.strip()
        if param.lower().startswith("rate="):
            try:
                rate_str = param.split("=", 1)[1]
                rate = int(rate_str)
            except (ValueError, IndexError):
                pass
        elif param.startswith("audio/L"):
            try:
                bits_per_sample = int(param.split("L", 1)[1])
            except (ValueError, IndexError):
                pass

    return {"bits_per_sample": bits_per_sample, "rate": rate}


def get_voice_for_speaker(speaker_id: int) -> str:
    """
    Speaker ID에 맞는 Voice 이름 반환

    Args:
        speaker_id: 화자 ID

    Returns:
        Voice 이름
    """
    # speaker_id를 1-10 범위로 순환
    voice_id = ((speaker_id - 1) % 10) + 1
    return SPEAKER_VOICES.get(voice_id, "Zephyr")


def add_audio_path_column():
    """youtube_segments 테이블에 audio_path 컬럼 추가"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            ALTER TABLE youtube_segments
            ADD COLUMN audio_path TEXT
        """
        )
        conn.commit()
        logging.info("✅ audio_path 컬럼 추가 완료")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            logging.info("⏭️  audio_path 컬럼이 이미 존재함")
        else:
            raise
    finally:
        conn.close()


def generate_tts_for_segment(
    client, text: str, speaker_id: int, output_path: str
) -> bool:
    """
    단일 세그먼트에 대한 TTS 오디오 생성

    Args:
        client: Gemini API 클라이언트
        text: 변환할 텍스트
        speaker_id: 화자 ID
        output_path: 출력 파일 경로

    Returns:
        성공 여부
    """
    try:
        voice_name = get_voice_for_speaker(speaker_id)

        contents = [
            types.Content(
                role="user",
                parts=[
                    types.Part.from_text(text=text),
                ],
            ),
        ]

        generate_content_config = types.GenerateContentConfig(
            temperature=1,
            response_modalities=["audio"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=voice_name
                    )
                )
            ),
        )

        audio_data = b""
        mime_type = None

        for chunk in client.models.generate_content_stream(
            model="gemini-2.5-flash-preview-tts",
            contents=contents,
            config=generate_content_config,
        ):
            if (
                chunk.candidates is None
                or chunk.candidates[0].content is None
                or chunk.candidates[0].content.parts is None
            ):
                continue

            if (
                chunk.candidates[0].content.parts[0].inline_data
                and chunk.candidates[0].content.parts[0].inline_data.data
            ):
                inline_data = chunk.candidates[0].content.parts[0].inline_data
                audio_data += inline_data.data
                if mime_type is None:
                    mime_type = inline_data.mime_type

        if not audio_data:
            logging.error(f"❌ 오디오 데이터가 생성되지 않음")
            return False

        # WAV 변환
        file_extension = mimetypes.guess_extension(mime_type)
        if file_extension is None or file_extension != ".wav":
            audio_data = convert_to_wav(audio_data, mime_type)
            output_path = output_path.replace(file_extension or "", ".wav")

        # 파일 저장
        with open(output_path, "wb") as f:
            f.write(audio_data)

        logging.info(f"✅ TTS 생성 완료: {output_path} (Voice: {voice_name})")
        return True

    except Exception as e:
        logging.error(f"❌ TTS 생성 오류: {e}")
        import traceback

        traceback.print_exc()
        return False


def generate_tts_for_all_segments(video_id: str = None, skip_existing: bool = True):
    """
    모든 세그먼트에 대한 TTS 오디오 생성

    Args:
        video_id: 특정 비디오 ID (None이면 모든 비디오)
        skip_existing: 이미 생성된 파일 건너뛰기
    """
    # TTS 출력 디렉토리 생성
    Path(TTS_OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

    # Gemini 클라이언트 초기화
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY 환경 변수가 설정되지 않았습니다")

    client = genai.Client(api_key=api_key)

    # DB 연결
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        # 세그먼트 조회
        if video_id:
            cursor.execute(
                """
                SELECT id, video_id, segment_id, speaker_id, text,
                       translated_text, translated_language, audio_path
                FROM youtube_segments
                WHERE video_id = ?
                ORDER BY segment_id
            """,
                (video_id,),
            )
        else:
            cursor.execute(
                """
                SELECT id, video_id, segment_id, speaker_id, text,
                       translated_text, translated_language, audio_path
                FROM youtube_segments
                ORDER BY video_id, segment_id
            """
            )

        segments = cursor.fetchall()
        total = len(segments)
        success_count = 0
        skip_count = 0
        fail_count = 0

        logging.info(f"🔄 TTS 생성 시작: {total}개 세그먼트")

        for idx, segment in enumerate(segments, 1):
            segment_id = segment["segment_id"]
            db_id = segment["id"]
            vid = segment["video_id"]
            speaker_id = segment["speaker_id"] or 1

            # 변환할 텍스트 선택 (translated_text 우선, 없으면 text)
            tts_text = segment["translated_text"] or segment["text"]
            if not tts_text or not tts_text.strip():
                logging.warning(f"⏭️  세그먼트 {idx}/{total} 건너뛰기: 텍스트 없음")
                skip_count += 1
                continue

            # 출력 파일 경로
            output_filename = f"{vid}_seg{segment_id:04d}_spk{speaker_id}.wav"
            output_path = os.path.join(TTS_OUTPUT_DIR, output_filename)

            # 이미 생성된 파일 확인
            if (
                skip_existing
                and segment["audio_path"]
                and os.path.exists(segment["audio_path"])
            ):
                logging.info(
                    f"⏭️  세그먼트 {idx}/{total} 건너뛰기: 이미 생성됨 ({segment['audio_path']})"
                )
                skip_count += 1
                continue

            # 진행 상황 로그
            if idx % max(1, total // 10) == 0 or idx == total:
                logging.info(f"📊 진행 중: {idx}/{total} ({100*idx//total}%)")

            # TTS 생성
            logging.info(f"🎙️  세그먼트 {idx}/{total}: {tts_text[:50]}...")
            success = generate_tts_for_segment(
                client, tts_text, speaker_id, output_path
            )

            if success:
                # DB 업데이트
                cursor.execute(
                    """
                    UPDATE youtube_segments
                    SET audio_path = ?
                    WHERE id = ?
                """,
                    (output_path, db_id),
                )
                conn.commit()
                success_count += 1
            else:
                fail_count += 1

        # 최종 결과
        logging.info(
            f"""
✅ TTS 생성 완료!
  총 세그먼트: {total}개
  성공: {success_count}개
  건너뜀: {skip_count}개
  실패: {fail_count}개
"""
        )

    except Exception as e:
        logging.error(f"❌ 오류 발생: {e}")
        import traceback

        traceback.print_exc()
    finally:
        conn.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="YouTube 세그먼트 TTS 오디오 생성")
    parser.add_argument("--video-id", type=str, help="특정 비디오 ID만 처리")
    parser.add_argument(
        "--no-skip", action="store_true", help="이미 생성된 파일도 다시 생성"
    )

    args = parser.parse_args()

    # audio_path 컬럼 추가
    add_audio_path_column()

    # TTS 생성
    generate_tts_for_all_segments(
        video_id=args.video_id, skip_existing=not args.no_skip
    )
