"""
번역 기능을 위한 데이터베이스 마이그레이션

기존 segments 테이블에 번역 관련 컬럼 추가:
- original_language: 원본 언어 (기본값: 'ko')
- translated_text: 번역된 텍스트
- translated_language: 번역된 언어
"""

import sqlite3
import os
import logging
from modules.sqlite_db import DB_PATH

logging.basicConfig(level=logging.INFO)

def migrate_database():
    """데이터베이스에 번역 컬럼 추가"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # youtube_segments 테이블에 컬럼 추가
        logging.info("youtube_segments 테이블에 번역 컬럼 추가 중...")

        # 기존 컬럼 확인
        cursor.execute("PRAGMA table_info(youtube_segments)")
        columns = [col[1] for col in cursor.fetchall()]

        if 'original_language' not in columns:
            cursor.execute("ALTER TABLE youtube_segments ADD COLUMN original_language TEXT DEFAULT 'ko'")
            logging.info("✅ original_language 컬럼 추가 완료")
        else:
            logging.info("⏭️  original_language 컬럼이 이미 존재합니다")

        if 'translated_text' not in columns:
            cursor.execute("ALTER TABLE youtube_segments ADD COLUMN translated_text TEXT")
            logging.info("✅ translated_text 컬럼 추가 완료")
        else:
            logging.info("⏭️  translated_text 컬럼이 이미 존재합니다")

        if 'translated_language' not in columns:
            cursor.execute("ALTER TABLE youtube_segments ADD COLUMN translated_language TEXT")
            logging.info("✅ translated_language 컬럼 추가 완료")
        else:
            logging.info("⏭️  translated_language 컬럼이 이미 존재합니다")

        # audio_segments 테이블에 컬럼 추가
        logging.info("\naudio_segments 테이블에 번역 컬럼 추가 중...")

        cursor.execute("PRAGMA table_info(audio_segments)")
        columns = [col[1] for col in cursor.fetchall()]

        if 'original_language' not in columns:
            cursor.execute("ALTER TABLE audio_segments ADD COLUMN original_language TEXT DEFAULT 'ko'")
            logging.info("✅ original_language 컬럼 추가 완료")
        else:
            logging.info("⏭️  original_language 컬럼이 이미 존재합니다")

        if 'translated_text' not in columns:
            cursor.execute("ALTER TABLE audio_segments ADD COLUMN translated_text TEXT")
            logging.info("✅ translated_text 컬럼 추가 완료")
        else:
            logging.info("⏭️  translated_text 컬럼이 이미 존재합니다")

        if 'translated_language' not in columns:
            cursor.execute("ALTER TABLE audio_segments ADD COLUMN translated_language TEXT")
            logging.info("✅ translated_language 컬럼 추가 완료")
        else:
            logging.info("⏭️  translated_language 컬럼이 이미 존재합니다")

        conn.commit()
        logging.info("\n🎉 데이터베이스 마이그레이션 완료!")

    except Exception as e:
        conn.rollback()
        logging.error(f"❌ 마이그레이션 오류: {e}")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    if os.path.exists(DB_PATH):
        logging.info(f"📁 데이터베이스 경로: {DB_PATH}")
        migrate_database()
    else:
        logging.error(f"❌ 데이터베이스 파일을 찾을 수 없습니다: {DB_PATH}")
