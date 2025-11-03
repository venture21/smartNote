"""
고아 YouTube 세그먼트 데이터 복구

youtube_segments 테이블에는 있지만 youtube_metadata에는 없는 데이터를 복구합니다.
"""
import sqlite3
import yt_dlp
import logging
from config import CSV_FOLDER
import os

logging.basicConfig(level=logging.INFO)

DB_PATH = os.path.join(CSV_FOLDER, "smartnote.db")


def get_orphaned_video_ids():
    """youtube_metadata에 없는 video_id 목록 조회"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT DISTINCT video_id
        FROM youtube_segments
        WHERE video_id NOT IN (SELECT video_id FROM youtube_metadata)
    """)

    orphaned_ids = [row[0] for row in cursor.fetchall()]
    conn.close()

    return orphaned_ids


def get_youtube_metadata(video_id):
    """YouTube API로 영상 메타데이터 가져오기"""
    try:
        url = f"https://www.youtube.com/watch?v={video_id}"

        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

            title = info.get('title', 'Unknown')
            channel = info.get('channel', info.get('uploader', 'Unknown'))
            view_count = info.get('view_count', 0)
            upload_date = info.get('upload_date', '')

            # upload_date 포맷 변환 (YYYYMMDD -> YYYY-MM-DD)
            if upload_date and len(upload_date) == 8:
                upload_date = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}"

            return {
                'youtube_url': url,
                'video_id': video_id,
                'title': title,
                'channel': channel,
                'view_count': view_count,
                'upload_date': upload_date,
            }
    except Exception as e:
        logging.error(f"YouTube 메타데이터 가져오기 실패 (video_id: {video_id}): {e}")
        return None


def insert_youtube_metadata(metadata):
    """youtube_metadata 테이블에 메타데이터 삽입"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO youtube_metadata
            (youtube_url, video_id, title, channel, view_count, upload_date,
             mp3_path, stt_service, stt_processing_time, summary)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            metadata['youtube_url'],
            metadata['video_id'],
            metadata['title'],
            metadata['channel'],
            metadata['view_count'],
            metadata['upload_date'],
            '',  # mp3_path (알 수 없음)
            'gemini',  # stt_service (기본값)
            0.0,  # stt_processing_time (알 수 없음)
            ''  # summary (비어있음)
        ))

        conn.commit()
        logging.info(f"✅ 메타데이터 추가 완료: {metadata['title']} ({metadata['video_id']})")
        return True
    except sqlite3.IntegrityError as e:
        logging.warning(f"⚠️ 이미 존재하는 video_id: {metadata['video_id']}")
        return False
    except Exception as e:
        logging.error(f"❌ 메타데이터 삽입 실패: {e}")
        return False
    finally:
        conn.close()


def main():
    """고아 데이터 복구 메인 함수"""
    print("=" * 80)
    print("고아 YouTube 세그먼트 데이터 복구")
    print("=" * 80)
    print()

    # 1. 고아 video_id 조회
    orphaned_ids = get_orphaned_video_ids()

    if not orphaned_ids:
        print("✅ 고아 데이터가 없습니다. 모든 데이터가 정상입니다.")
        return

    print(f"⚠️ 발견된 고아 video_id: {len(orphaned_ids)}개")
    for video_id in orphaned_ids:
        print(f"  - {video_id}")
    print()

    # 2. 각 video_id에 대해 메타데이터 복구
    success_count = 0
    fail_count = 0

    for video_id in orphaned_ids:
        print(f"🔄 처리 중: {video_id}")

        # YouTube 메타데이터 가져오기
        metadata = get_youtube_metadata(video_id)

        if metadata:
            # DB에 삽입
            if insert_youtube_metadata(metadata):
                success_count += 1
            else:
                fail_count += 1
        else:
            fail_count += 1
            print(f"❌ 메타데이터 가져오기 실패: {video_id}")

        print()

    # 3. 결과 요약
    print("=" * 80)
    print(f"복구 완료:")
    print(f"  ✅ 성공: {success_count}개")
    print(f"  ❌ 실패: {fail_count}개")
    print("=" * 80)


if __name__ == "__main__":
    main()
