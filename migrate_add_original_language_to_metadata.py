"""
메타데이터 테이블에 original_language 컬럼 추가 마이그레이션

youtube_metadata와 audio_metadata 테이블에 original_language 컬럼을 추가하고,
기존 데이터는 segments 테이블의 첫 번째 세그먼트에서 언어를 가져옵니다.
"""

import sqlite3
import logging

logging.basicConfig(level=logging.INFO)

DB_PATH = "csv/smartnote.db"


def migrate_add_original_language_to_metadata():
    """메타데이터 테이블에 original_language 컬럼 추가"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # 1. youtube_metadata에 original_language 컬럼 추가
        logging.info("📝 youtube_metadata 테이블에 original_language 컬럼 추가 중...")
        try:
            cursor.execute(
                """
                ALTER TABLE youtube_metadata
                ADD COLUMN original_language TEXT DEFAULT 'unknown'
                """
            )
            logging.info("✅ youtube_metadata에 컬럼 추가 완료")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                logging.info("⏭️  youtube_metadata에 이미 컬럼이 존재함")
            else:
                raise

        # 2. audio_metadata에 original_language 컬럼 추가
        logging.info("📝 audio_metadata 테이블에 original_language 컬럼 추가 중...")
        try:
            cursor.execute(
                """
                ALTER TABLE audio_metadata
                ADD COLUMN original_language TEXT DEFAULT 'unknown'
                """
            )
            logging.info("✅ audio_metadata에 컬럼 추가 완료")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                logging.info("⏭️  audio_metadata에 이미 컬럼이 존재함")
            else:
                raise

        conn.commit()

        # 3. youtube_metadata의 기존 데이터 업데이트
        logging.info("🔄 youtube_metadata의 기존 데이터 업데이트 중...")
        cursor.execute(
            """
            UPDATE youtube_metadata
            SET original_language = (
                SELECT original_language
                FROM youtube_segments
                WHERE youtube_segments.video_id = youtube_metadata.video_id
                LIMIT 1
            )
            WHERE EXISTS (
                SELECT 1
                FROM youtube_segments
                WHERE youtube_segments.video_id = youtube_metadata.video_id
            )
            """
        )
        youtube_updated = cursor.rowcount
        logging.info(f"✅ youtube_metadata {youtube_updated}개 행 업데이트 완료")

        # 4. audio_metadata의 기존 데이터 업데이트
        logging.info("🔄 audio_metadata의 기존 데이터 업데이트 중...")
        cursor.execute(
            """
            UPDATE audio_metadata
            SET original_language = (
                SELECT original_language
                FROM audio_segments
                WHERE audio_segments.file_hash = audio_metadata.file_hash
                LIMIT 1
            )
            WHERE EXISTS (
                SELECT 1
                FROM audio_segments
                WHERE audio_segments.file_hash = audio_metadata.file_hash
            )
            """
        )
        audio_updated = cursor.rowcount
        logging.info(f"✅ audio_metadata {audio_updated}개 행 업데이트 완료")

        conn.commit()

        # 5. 결과 확인
        logging.info("\n📊 마이그레이션 결과:")
        cursor.execute(
            "SELECT original_language, COUNT(*) FROM youtube_metadata GROUP BY original_language"
        )
        youtube_langs = cursor.fetchall()
        logging.info("  YouTube 언어 분포:")
        for lang, count in youtube_langs:
            logging.info(f"    - {lang}: {count}개")

        cursor.execute(
            "SELECT original_language, COUNT(*) FROM audio_metadata GROUP BY original_language"
        )
        audio_langs = cursor.fetchall()
        if audio_langs:
            logging.info("  Audio 언어 분포:")
            for lang, count in audio_langs:
                logging.info(f"    - {lang}: {count}개")
        else:
            logging.info("  Audio: 데이터 없음")

        logging.info("\n✅ 마이그레이션 완료!")

    except Exception as e:
        logging.error(f"❌ 마이그레이션 오류: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    migrate_add_original_language_to_metadata()
