#!/usr/bin/env python3
"""
데이터베이스 저장 상태 확인 스크립트
"""
import sqlite3
import json
from pathlib import Path

DB_PATH = "csv/smartnote.db"

def check_database():
    """데이터베이스 상태 확인"""

    if not Path(DB_PATH).exists():
        print(f"❌ 데이터베이스 파일이 없습니다: {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print("="*60)
    print("📊 데이터베이스 상태 확인")
    print("="*60)

    # 1. YouTube 메타데이터
    cursor.execute("SELECT COUNT(*) as count FROM youtube_metadata")
    youtube_count = cursor.fetchone()['count']
    print(f"\n📹 YouTube 메타데이터: {youtube_count}개")

    if youtube_count > 0:
        cursor.execute("""
            SELECT video_id, title, created_at, stt_service, original_language
            FROM youtube_metadata
            ORDER BY created_at DESC
            LIMIT 3
        """)
        for row in cursor.fetchall():
            print(f"  - {row['video_id']}: {row['title']}")
            print(f"    STT: {row['stt_service']}, 언어: {row['original_language']}")
            print(f"    생성: {row['created_at']}")

    # 2. YouTube 세그먼트
    cursor.execute("SELECT COUNT(*) as count FROM youtube_segments")
    segment_count = cursor.fetchone()['count']
    print(f"\n📝 YouTube 세그먼트: {segment_count}개")

    if segment_count > 0:
        cursor.execute("""
            SELECT video_id, COUNT(*) as seg_count
            FROM youtube_segments
            GROUP BY video_id
        """)
        for row in cursor.fetchall():
            print(f"  - {row['video_id']}: {row['seg_count']}개 세그먼트")

            # 첫 3개 세그먼트 텍스트 미리보기
            cursor.execute("""
                SELECT segment_id, text, original_language
                FROM youtube_segments
                WHERE video_id = ?
                ORDER BY segment_id
                LIMIT 3
            """, (row['video_id'],))

            for seg in cursor.fetchall():
                text_preview = seg['text'][:60] if seg['text'] else "(빈 텍스트)"
                print(f"    [{seg['segment_id']}] {text_preview}...")
                print(f"        언어: {seg['original_language']}")

    # 3. 오디오 메타데이터
    cursor.execute("SELECT COUNT(*) as count FROM audio_metadata")
    audio_count = cursor.fetchone()['count']
    print(f"\n🎵 오디오 메타데이터: {audio_count}개")

    # 4. 오디오 세그먼트
    cursor.execute("SELECT COUNT(*) as count FROM audio_segments")
    audio_seg_count = cursor.fetchone()['count']
    print(f"\n🎤 오디오 세그먼트: {audio_seg_count}개")

    conn.close()

    print("\n" + "="*60)

    if youtube_count == 0 and audio_count == 0:
        print("⚠️  데이터베이스가 비어있습니다.")
        print("\n💡 해결 방법:")
        print("1. YouTube 영상 처리하기")
        print("2. STT 처리 완료 후 자동으로 저장됨")
        print("3. 다시 이 스크립트 실행")
    else:
        print("✅ 데이터가 정상적으로 저장되어 있습니다!")

if __name__ == "__main__":
    check_database()
