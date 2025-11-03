"""
번역 슬롯 추가 마이그레이션

youtube_segments와 audio_segments 테이블에 2개의 추가 번역 슬롯을 추가합니다.
- 기존: translated_text, translated_language (슬롯 1)
- 추가: translated_text_2, translated_language_2 (슬롯 2)
- 추가: translated_text_3, translated_language_3 (슬롯 3)

총 3개 언어까지 저장 가능
"""

import sqlite3
import logging

logging.basicConfig(level=logging.INFO)

DB_PATH = "csv/smartnote.db"


def migrate_add_translation_slots():
    """번역 슬롯 추가 마이그레이션"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # 1. youtube_segments에 슬롯 2, 3 추가
        logging.info("📝 youtube_segments 테이블에 번역 슬롯 추가 중...")

        columns_to_add = [
            ("translated_text_2", "TEXT"),
            ("translated_language_2", "TEXT"),
            ("translated_text_3", "TEXT"),
            ("translated_language_3", "TEXT"),
        ]

        for col_name, col_type in columns_to_add:
            try:
                cursor.execute(f"""
                    ALTER TABLE youtube_segments
                    ADD COLUMN {col_name} {col_type}
                """)
                logging.info(f"  ✅ {col_name} 컬럼 추가 완료")
            except sqlite3.OperationalError as e:
                if "duplicate column name" in str(e).lower():
                    logging.info(f"  ⏭️  {col_name} 컬럼이 이미 존재함")
                else:
                    raise

        # 2. audio_segments에 슬롯 2, 3 추가
        logging.info("\n📝 audio_segments 테이블에 번역 슬롯 추가 중...")

        for col_name, col_type in columns_to_add:
            try:
                cursor.execute(f"""
                    ALTER TABLE audio_segments
                    ADD COLUMN {col_name} {col_type}
                """)
                logging.info(f"  ✅ {col_name} 컬럼 추가 완료")
            except sqlite3.OperationalError as e:
                if "duplicate column name" in str(e).lower():
                    logging.info(f"  ⏭️  {col_name} 컬럼이 이미 존재함")
                else:
                    raise

        conn.commit()

        # 3. 현재 상태 확인
        logging.info("\n📊 마이그레이션 결과:")

        cursor.execute("PRAGMA table_info(youtube_segments)")
        youtube_cols = cursor.fetchall()
        translation_cols = [col for col in youtube_cols if 'translated' in col[1]]
        logging.info(f"  YouTube Segments 번역 컬럼: {len(translation_cols)}개")
        for col in translation_cols:
            logging.info(f"    - {col[1]} ({col[2]})")

        cursor.execute("PRAGMA table_info(audio_segments)")
        audio_cols = cursor.fetchall()
        translation_cols = [col for col in audio_cols if 'translated' in col[1]]
        logging.info(f"  Audio Segments 번역 컬럼: {len(translation_cols)}개")
        for col in translation_cols:
            logging.info(f"    - {col[1]} ({col[2]})")

        logging.info("\n✅ 마이그레이션 완료! 이제 세그먼트당 최대 3개 언어 저장 가능")

    except Exception as e:
        logging.error(f"❌ 마이그레이션 오류: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    migrate_add_translation_slots()
