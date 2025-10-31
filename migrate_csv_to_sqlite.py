"""
CSV 데이터를 SQLite로 마이그레이션하는 스크립트

기존 CSV 파일의 데이터를 읽어 SQLite 데이터베이스로 이전합니다.
- youtube_history.csv → youtube_metadata + youtube_segments
- audio_history.csv → audio_metadata + audio_segments
"""

import os
import sys
import pandas as pd
import json
import logging
from datetime import datetime

# 모듈 임포트
from modules.sqlite_db import (
    init_database,
    save_youtube_data,
    save_audio_data,
    get_database_stats
)
from config import YOUTUBE_HISTORY_CSV, AUDIO_HISTORY_CSV

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


def migrate_youtube_history():
    """YouTube 이력 CSV를 SQLite로 마이그레이션"""
    if not os.path.exists(YOUTUBE_HISTORY_CSV):
        logging.warning(f"⚠️ YouTube CSV 파일이 없습니다: {YOUTUBE_HISTORY_CSV}")
        return 0

    try:
        df = pd.read_csv(YOUTUBE_HISTORY_CSV, encoding="utf-8-sig")
        logging.info(f"📂 YouTube CSV 로드 완료: {len(df)}개 항목")

        migrated_count = 0
        error_count = 0

        for idx, row in df.iterrows():
            try:
                # segments_json 파싱
                segments_json_str = row.get('segments_json', '[]')
                if pd.isna(segments_json_str) or segments_json_str == '':
                    segments_json_str = '[]'

                segments = json.loads(segments_json_str)

                # 데이터 저장
                save_youtube_data(
                    youtube_url=row.get('youtube_url', ''),
                    video_id=row.get('video_id', ''),
                    title=row.get('title', ''),
                    channel=row.get('channel', 'Unknown'),
                    view_count=int(row.get('view_count', 0)) if not pd.isna(row.get('view_count')) else 0,
                    upload_date=row.get('upload_date', ''),
                    mp3_path=row.get('mp3_path', ''),
                    segments=segments,
                    stt_service=row.get('stt_service', 'gemini'),
                    stt_processing_time=float(row.get('stt_processing_time', 0.0)) if not pd.isna(row.get('stt_processing_time')) else 0.0,
                    summary=row.get('summary', '')
                )

                migrated_count += 1
                logging.info(f"✅ [{migrated_count}/{len(df)}] {row.get('video_id', 'unknown')}")

            except Exception as e:
                error_count += 1
                logging.error(f"❌ 마이그레이션 오류 (row {idx}): {e}")
                continue

        logging.info(f"🎉 YouTube 마이그레이션 완료: {migrated_count}개 성공, {error_count}개 실패")
        return migrated_count

    except Exception as e:
        logging.error(f"❌ YouTube CSV 로드 오류: {e}")
        return 0


def migrate_audio_history():
    """오디오 이력 CSV를 SQLite로 마이그레이션"""
    if not os.path.exists(AUDIO_HISTORY_CSV):
        logging.warning(f"⚠️ 오디오 CSV 파일이 없습니다: {AUDIO_HISTORY_CSV}")
        return 0

    try:
        df = pd.read_csv(AUDIO_HISTORY_CSV, encoding="utf-8-sig")
        logging.info(f"📂 오디오 CSV 로드 완료: {len(df)}개 항목")

        migrated_count = 0
        error_count = 0

        for idx, row in df.iterrows():
            try:
                # segments_json 파싱
                segments_json_str = row.get('segments_json', '[]')
                if pd.isna(segments_json_str) or segments_json_str == '':
                    segments_json_str = '[]'

                segments = json.loads(segments_json_str)

                # 데이터 저장
                save_audio_data(
                    file_hash=row.get('file_hash', ''),
                    filename=row.get('filename', ''),
                    file_path=row.get('file_path', ''),
                    file_size=int(row.get('file_size', 0)) if not pd.isna(row.get('file_size')) else 0,
                    audio_duration=float(row.get('audio_duration', 0.0)) if not pd.isna(row.get('audio_duration')) else 0.0,
                    segments=segments,
                    stt_service=row.get('stt_service', 'gemini'),
                    stt_processing_time=float(row.get('stt_processing_time', 0.0)) if not pd.isna(row.get('stt_processing_time')) else 0.0,
                    summary=row.get('summary', '')
                )

                migrated_count += 1
                logging.info(f"✅ [{migrated_count}/{len(df)}] {row.get('filename', 'unknown')}")

            except Exception as e:
                error_count += 1
                logging.error(f"❌ 마이그레이션 오류 (row {idx}): {e}")
                continue

        logging.info(f"🎉 오디오 마이그레이션 완료: {migrated_count}개 성공, {error_count}개 실패")
        return migrated_count

    except Exception as e:
        logging.error(f"❌ 오디오 CSV 로드 오류: {e}")
        return 0


def main():
    """메인 마이그레이션 실행"""
    logging.info("=" * 60)
    logging.info("🚀 CSV → SQLite 마이그레이션 시작")
    logging.info("=" * 60)

    # 1. 데이터베이스 초기화
    logging.info("\n📦 1단계: 데이터베이스 초기화")
    init_database()

    # 2. YouTube 데이터 마이그레이션
    logging.info("\n📹 2단계: YouTube 데이터 마이그레이션")
    youtube_count = migrate_youtube_history()

    # 3. 오디오 데이터 마이그레이션
    logging.info("\n🎵 3단계: 오디오 데이터 마이그레이션")
    audio_count = migrate_audio_history()

    # 4. 결과 확인
    logging.info("\n📊 4단계: 마이그레이션 결과 확인")
    stats = get_database_stats()

    logging.info("=" * 60)
    logging.info("✨ 마이그레이션 완료!")
    logging.info("=" * 60)
    logging.info(f"📹 YouTube 영상: {stats['youtube_videos']}개")
    logging.info(f"   - 세그먼트: {stats['youtube_segments']}개")
    logging.info(f"🎵 오디오 파일: {stats['audio_files']}개")
    logging.info(f"   - 세그먼트: {stats['audio_segments']}개")
    logging.info(f"📈 전체: {stats['total_items']}개 항목, {stats['total_segments']}개 세그먼트")
    logging.info("=" * 60)

    # 5. 백업 권장 메시지
    if youtube_count > 0 or audio_count > 0:
        logging.info("\n💡 권장 사항:")
        logging.info("   - 마이그레이션이 성공적으로 완료되었습니다.")
        logging.info("   - 기존 CSV 파일은 백업 폴더로 이동하는 것을 권장합니다.")
        logging.info(f"   - 백업 명령어: mkdir -p backup/csv && mv {YOUTUBE_HISTORY_CSV} {AUDIO_HISTORY_CSV} backup/csv/")


if __name__ == "__main__":
    main()
