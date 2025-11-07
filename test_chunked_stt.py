"""
긴 오디오 파일에 대한 청크 처리 STT 테스트 스크립트
"""

import os
import logging
from modules.stt import recognize_with_gemini_chunked, recognize_with_gemini

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


def test_chunked_stt(audio_path, chunk_duration_minutes=30, overlap_seconds=25):
    """
    청크 처리 STT 테스트

    Args:
        audio_path: 오디오 파일 경로
        chunk_duration_minutes: 각 청크 길이 (분)
        overlap_seconds: 청크 간 중복 시간 (초)
    """
    if not os.path.exists(audio_path):
        logging.error(f"파일이 존재하지 않습니다: {audio_path}")
        return

    logging.info(f"=" * 80)
    logging.info(f"청크 처리 STT 테스트 시작")
    logging.info(f"파일: {audio_path}")
    logging.info(f"청크 길이: {chunk_duration_minutes}분")
    logging.info(f"중복 구간: {overlap_seconds}초")
    logging.info(f"=" * 80)

    # 청크 처리 STT 실행
    segments, processing_time, language = recognize_with_gemini_chunked(
        audio_path,
        task_id=None,
        audio_duration=None,
        chunk_duration_minutes=chunk_duration_minutes,
        overlap_seconds=overlap_seconds
    )

    if segments:
        logging.info(f"\n{'=' * 80}")
        logging.info(f"✅ STT 처리 완료!")
        logging.info(f"총 처리 시간: {processing_time:.2f}초")
        logging.info(f"감지된 언어: {language}")
        logging.info(f"세그먼트 수: {len(segments)}개")
        logging.info(f"=" * 80)

        # 처음 5개 세그먼트 출력
        logging.info(f"\n처음 5개 세그먼트:")
        for seg in segments[:5]:
            logging.info(
                f"[{seg['id']}] 화자 {seg['speaker']} "
                f"({seg.get('start_time', 0):.2f}s): {seg['text'][:100]}..."
            )

        # 마지막 5개 세그먼트 출력
        if len(segments) > 5:
            logging.info(f"\n마지막 5개 세그먼트:")
            for seg in segments[-5:]:
                logging.info(
                    f"[{seg['id']}] 화자 {seg['speaker']} "
                    f"({seg.get('start_time', 0):.2f}s): {seg['text'][:100]}..."
                )

        return segments, processing_time, language
    else:
        logging.error(f"❌ STT 처리 실패")
        return None, 0.0, "unknown"


def compare_with_regular_stt(audio_path):
    """
    청크 처리 STT와 일반 STT 비교
    (주의: 일반 STT는 긴 파일에서 실패할 수 있음)

    Args:
        audio_path: 오디오 파일 경로
    """
    logging.info(f"\n{'=' * 80}")
    logging.info(f"일반 STT vs 청크 처리 STT 비교")
    logging.info(f"=" * 80)

    # 청크 처리 STT
    logging.info(f"\n1. 청크 처리 STT 실행...")
    chunks_segments, chunks_time, chunks_lang = recognize_with_gemini_chunked(
        audio_path,
        chunk_duration_minutes=30,
        overlap_seconds=25
    )

    # 일반 STT
    logging.info(f"\n2. 일반 STT 실행... (긴 파일의 경우 실패할 수 있음)")
    try:
        regular_segments, regular_time, regular_lang = recognize_with_gemini(
            audio_path,
            task_id=None,
            audio_duration=None
        )
    except Exception as e:
        logging.error(f"일반 STT 실패: {e}")
        regular_segments = None
        regular_time = 0.0
        regular_lang = "unknown"

    # 결과 비교
    logging.info(f"\n{'=' * 80}")
    logging.info(f"결과 비교:")
    logging.info(f"=" * 80)

    logging.info(f"\n청크 처리 STT:")
    logging.info(f"  - 세그먼트 수: {len(chunks_segments) if chunks_segments else 0}")
    logging.info(f"  - 처리 시간: {chunks_time:.2f}초")
    logging.info(f"  - 감지 언어: {chunks_lang}")

    logging.info(f"\n일반 STT:")
    logging.info(f"  - 세그먼트 수: {len(regular_segments) if regular_segments else 0}")
    logging.info(f"  - 처리 시간: {regular_time:.2f}초")
    logging.info(f"  - 감지 언어: {regular_lang}")


if __name__ == "__main__":
    import sys

    # 사용법 출력
    if len(sys.argv) < 2:
        print("사용법: python test_chunked_stt.py <audio_file> [chunk_minutes] [overlap_seconds]")
        print("")
        print("예시:")
        print("  python test_chunked_stt.py mp3/long_meeting.mp3")
        print("  python test_chunked_stt.py mp3/long_meeting.mp3 20 30")
        print("")
        print("기본값:")
        print("  - chunk_minutes: 30분")
        print("  - overlap_seconds: 25초")
        sys.exit(1)

    audio_file = sys.argv[1]
    chunk_minutes = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    overlap_secs = int(sys.argv[3]) if len(sys.argv) > 3 else 25

    # 테스트 실행
    test_chunked_stt(audio_file, chunk_minutes, overlap_secs)

    # 비교 테스트 (선택사항)
    # compare_with_regular_stt(audio_file)
