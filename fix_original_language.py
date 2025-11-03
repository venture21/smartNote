"""
기존 세그먼트의 원본 언어를 자동 감지하여 업데이트

text 컬럼의 실제 내용을 분석하여 original_language를 올바르게 설정합니다.
"""

import sqlite3
import os
import logging
from modules.sqlite_db import DB_PATH, get_db_connection
from modules.translation import detect_language

logging.basicConfig(level=logging.INFO)

def detect_and_update_languages():
    """모든 세그먼트의 언어를 감지하고 업데이트"""

    with get_db_connection() as conn:
        cursor = conn.cursor()

        # YouTube 세그먼트 처리
        logging.info("=" * 60)
        logging.info("YouTube 세그먼트 언어 감지 시작...")
        logging.info("=" * 60)

        cursor.execute("SELECT DISTINCT video_id FROM youtube_segments")
        video_ids = [row['video_id'] for row in cursor.fetchall()]

        for video_id in video_ids:
            logging.info(f"\n처리 중: {video_id}")

            # 첫 번째 세그먼트의 텍스트로 언어 감지
            cursor.execute("""
                SELECT text FROM youtube_segments
                WHERE video_id = ? AND text IS NOT NULL AND text != ''
                ORDER BY segment_id LIMIT 1
            """, (video_id,))

            row = cursor.fetchone()
            if not row:
                logging.warning(f"  ⚠️  텍스트가 없는 영상: {video_id}")
                continue

            sample_text = row['text']
            detected_lang = detect_language(sample_text)

            logging.info(f"  감지된 언어: {detected_lang}")
            logging.info(f"  샘플 텍스트: {sample_text[:100]}...")

            # 해당 영상의 모든 세그먼트 업데이트
            cursor.execute("""
                UPDATE youtube_segments
                SET original_language = ?
                WHERE video_id = ?
            """, (detected_lang, video_id))

            updated_count = cursor.rowcount
            logging.info(f"  ✅ {updated_count}개 세그먼트 업데이트 완료")

        # 오디오 세그먼트 처리
        logging.info("\n" + "=" * 60)
        logging.info("오디오 세그먼트 언어 감지 시작...")
        logging.info("=" * 60)

        cursor.execute("SELECT DISTINCT file_hash FROM audio_segments")
        file_hashes = [row['file_hash'] for row in cursor.fetchall()]

        for file_hash in file_hashes:
            logging.info(f"\n처리 중: {file_hash}")

            # 첫 번째 세그먼트의 텍스트로 언어 감지
            cursor.execute("""
                SELECT text FROM audio_segments
                WHERE file_hash = ? AND text IS NOT NULL AND text != ''
                ORDER BY segment_id LIMIT 1
            """, (file_hash,))

            row = cursor.fetchone()
            if not row:
                logging.warning(f"  ⚠️  텍스트가 없는 오디오: {file_hash}")
                continue

            sample_text = row['text']
            detected_lang = detect_language(sample_text)

            logging.info(f"  감지된 언어: {detected_lang}")
            logging.info(f"  샘플 텍스트: {sample_text[:100]}...")

            # 해당 오디오의 모든 세그먼트 업데이트
            cursor.execute("""
                UPDATE audio_segments
                SET original_language = ?
                WHERE file_hash = ?
            """, (detected_lang, file_hash))

            updated_count = cursor.rowcount
            logging.info(f"  ✅ {updated_count}개 세그먼트 업데이트 완료")

        logging.info("\n" + "=" * 60)
        logging.info("🎉 모든 세그먼트의 언어 감지 및 업데이트 완료!")
        logging.info("=" * 60)

if __name__ == "__main__":
    if os.path.exists(DB_PATH):
        logging.info(f"📁 데이터베이스 경로: {DB_PATH}\n")
        detect_and_update_languages()
    else:
        logging.error(f"❌ 데이터베이스 파일을 찾을 수 없습니다: {DB_PATH}")
