"""
특정 video_id 삭제 스크립트 (고아 데이터 포함)
"""
import sys
import os
import logging
import sqlite3
from config import CSV_FOLDER

logging.basicConfig(level=logging.INFO, format='%(message)s')

# 모듈 임포트
from modules.sqlite_db import delete_youtube_by_video_id
from modules.vectorstore import delete_from_vectorstore

DB_PATH = os.path.join(CSV_FOLDER, "smartnote.db")

def delete_orphaned_segments(video_id):
    """고아 세그먼트 직접 삭제 (metadata 없이 segments만 있는 경우)"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # 1. TTS 오디오 파일 경로 조회
        cursor.execute('SELECT audio_path FROM youtube_segments WHERE video_id = ? AND audio_path IS NOT NULL', (video_id,))
        tts_audio_paths = [row[0] for row in cursor.fetchall()]

        # 2. TTS 오디오 파일 삭제
        tts_deleted_count = 0
        for audio_path in tts_audio_paths:
            if audio_path and os.path.exists(audio_path):
                try:
                    os.remove(audio_path)
                    tts_deleted_count += 1
                    print(f"   🗑️ TTS 오디오 파일 삭제: {audio_path}")
                except Exception as e:
                    print(f"   ⚠️ TTS 오디오 파일 삭제 오류: {e}")

        if tts_deleted_count > 0:
            print(f"   ✅ TTS 오디오 파일 {tts_deleted_count}개 삭제 완료")

        # 3. 세그먼트 삭제
        cursor.execute('DELETE FROM youtube_segments WHERE video_id = ?', (video_id,))
        deleted_count = cursor.rowcount
        conn.commit()
        conn.close()

        return True, deleted_count

    except Exception as e:
        print(f"   ❌ 고아 세그먼트 삭제 오류: {e}")
        return False, 0

def delete_video(video_id):
    """YouTube 영상 완전 삭제 (고아 데이터 포함)"""
    print(f"=" * 80)
    print(f"YouTube 영상 삭제: {video_id}")
    print(f"=" * 80)
    print()

    # 1. metadata 존재 여부 확인
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM youtube_metadata WHERE video_id = ?', (video_id,))
    has_metadata = cursor.fetchone()[0] > 0

    cursor.execute('SELECT COUNT(*) FROM youtube_segments WHERE video_id = ?', (video_id,))
    segment_count = cursor.fetchone()[0]
    conn.close()

    print(f"📊 현황:")
    print(f"   - metadata 존재: {'예' if has_metadata else '아니오'}")
    print(f"   - segment 개수: {segment_count}개")
    print()

    # 2. SQLite에서 삭제
    print("1️⃣ smartnote.db에서 삭제 중...")

    if has_metadata:
        # 정상 삭제 (metadata + segments)
        db_success, mp3_path = delete_youtube_by_video_id(video_id)
        if db_success:
            print(f"   ✅ youtube_metadata 및 youtube_segments 삭제 완료")
        else:
            print(f"   ❌ 삭제 실패")
            return False
    else:
        # 고아 세그먼트 삭제
        print(f"   ⚠️ 고아 데이터 감지 (metadata 없음)")
        db_success, deleted_seg_count = delete_orphaned_segments(video_id)
        if db_success:
            print(f"   ✅ youtube_segments {deleted_seg_count}개 삭제 완료")
        else:
            print(f"   ❌ 삭제 실패")
            return False

    print()

    # 3. VectorStore에서 삭제
    print("2️⃣ chroma.sqlite3에서 삭제 중...")
    vs_success, deleted_count = delete_from_vectorstore(video_id, "youtube")

    if vs_success:
        print(f"   ✅ chroma.sqlite3 삭제 완료 ({deleted_count}개 임베딩)")
    else:
        print(f"   ⚠️ chroma.sqlite3 삭제 중 오류 발생")
    print()

    print("=" * 80)
    print(f"✅ video_id {video_id} 삭제 완료")
    print("=" * 80)

    return True

if __name__ == "__main__":
    video_id = "2EI1jDpDA0c"
    delete_video(video_id)
