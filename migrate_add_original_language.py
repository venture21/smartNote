#!/usr/bin/env python3
"""
데이터베이스 마이그레이션: original_language 및 audio_path 컬럼 추가

이 스크립트는 다음 컬럼들을 추가합니다:
1. youtube_metadata.original_language - STT에서 감지한 언어
2. audio_metadata.original_language - STT에서 감지한 언어
3. youtube_segments.audio_path - TTS 생성 오디오 파일 경로
4. audio_segments.audio_path - TTS 생성 오디오 파일 경로

실행 날짜: 2025-11-01
이유: STT 언어 감지 및 TTS 오디오 경로 저장
"""
import sqlite3
import logging
from pathlib import Path

DB_PATH = "csv/smartnote.db"

logging.basicConfig(level=logging.INFO)

def add_original_language_columns():
    """모든 테이블에 original_language와 audio_path 컬럼 추가"""

    if not Path(DB_PATH).exists():
        logging.error(f"❌ 데이터베이스 파일이 없습니다: {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # 1. youtube_metadata 테이블에 original_language 추가
        try:
            cursor.execute("""
                ALTER TABLE youtube_metadata
                ADD COLUMN original_language TEXT DEFAULT 'ko'
            """)
            logging.info("✅ youtube_metadata 테이블에 original_language 컬럼 추가")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e):
                logging.info("ℹ️ youtube_metadata.original_language 컬럼이 이미 존재합니다")
            else:
                raise

        # 2. audio_metadata 테이블에 original_language 추가
        try:
            cursor.execute("""
                ALTER TABLE audio_metadata
                ADD COLUMN original_language TEXT DEFAULT 'ko'
            """)
            logging.info("✅ audio_metadata 테이블에 original_language 컬럼 추가")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e):
                logging.info("ℹ️ audio_metadata.original_language 컬럼이 이미 존재합니다")
            else:
                raise

        # 3. youtube_segments 테이블에 audio_path 추가
        try:
            cursor.execute("""
                ALTER TABLE youtube_segments
                ADD COLUMN audio_path TEXT
            """)
            logging.info("✅ youtube_segments 테이블에 audio_path 컬럼 추가")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e):
                logging.info("ℹ️ youtube_segments.audio_path 컬럼이 이미 존재합니다")
            else:
                raise

        # 4. audio_segments 테이블에 audio_path 추가
        try:
            cursor.execute("""
                ALTER TABLE audio_segments
                ADD COLUMN audio_path TEXT
            """)
            logging.info("✅ audio_segments 테이블에 audio_path 컬럼 추가")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e):
                logging.info("ℹ️ audio_segments.audio_path 컬럼이 이미 존재합니다")
            else:
                raise

        conn.commit()
        logging.info("💾 데이터베이스 변경사항 저장 완료")

        # 5. 변경 확인
        cursor.execute("PRAGMA table_info(youtube_metadata)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'original_language' in columns:
            logging.info("✅ 검증 완료: youtube_metadata.original_language")

        cursor.execute("PRAGMA table_info(audio_metadata)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'original_language' in columns:
            logging.info("✅ 검증 완료: audio_metadata.original_language")

        cursor.execute("PRAGMA table_info(youtube_segments)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'audio_path' in columns:
            logging.info("✅ 검증 완료: youtube_segments.audio_path")

        cursor.execute("PRAGMA table_info(audio_segments)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'audio_path' in columns:
            logging.info("✅ 검증 완료: audio_segments.audio_path")

    except Exception as e:
        logging.error(f"❌ 마이그레이션 실패: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    print("="*60)
    print("🔄 데이터베이스 마이그레이션 시작")
    print("="*60)
    add_original_language_columns()
    print("="*60)
    print("✅ 마이그레이션 완료!")
    print("="*60)
