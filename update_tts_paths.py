#!/usr/bin/env python3
"""
기존 TTS 오디오 파일의 경로를 데이터베이스에 업데이트하는 스크립트
"""
import sqlite3
import os
from pathlib import Path

DB_PATH = "csv/smartnote.db"
TTS_DIR = "tts_audio"

def update_tts_paths():
    """TTS 오디오 파일 경로를 데이터베이스에 업데이트"""

    if not os.path.exists(TTS_DIR):
        print(f"❌ {TTS_DIR} 폴더가 없습니다.")
        return

    # TTS 파일 목록 가져오기
    tts_files = [f for f in os.listdir(TTS_DIR) if f.endswith('.wav')]

    if not tts_files:
        print(f"❌ {TTS_DIR} 폴더에 TTS 파일이 없습니다.")
        return

    print(f"📂 {len(tts_files)}개의 TTS 파일 발견")

    # 데이터베이스 연결
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    youtube_updated = 0
    audio_updated = 0
    errors = 0

    for filename in tts_files:
        try:
            # 파일명 파싱: {data_id}_{language}_seg{segment_id:04d}_spk{speaker_id}.wav
            # 예: _gdtY2V3Zx8_ko_seg0001_spk1.wav

            parts = filename.replace('.wav', '').split('_')

            # data_id 추출 (언어 코드 이전까지)
            # 파일명이 _로 시작하는 경우를 고려
            if filename.startswith('_'):
                # _gdtY2V3Zx8_ko_seg0001_spk1.wav -> ['', 'gdtY2V3Zx8', 'ko', 'seg0001', 'spk1']
                data_id = '_' + parts[1]  # '_gdtY2V3Zx8'
                language = parts[2]  # 'ko'
                seg_part = parts[3]  # 'seg0001'
                spk_part = parts[4]  # 'spk1'
            else:
                # 일반적인 경우
                data_id = parts[0]
                language = parts[1]
                seg_part = parts[2]
                spk_part = parts[3]

            # segment_id 추출 (seg0001 -> 1)
            segment_id = int(seg_part.replace('seg', ''))

            audio_path = os.path.join(TTS_DIR, filename)

            # YouTube 세그먼트 업데이트 시도
            cursor.execute("""
                UPDATE youtube_segments
                SET audio_path = ?
                WHERE video_id = ? AND segment_id = ?
            """, (audio_path, data_id, segment_id))

            if cursor.rowcount > 0:
                youtube_updated += cursor.rowcount
                print(f"✅ YouTube 세그먼트 업데이트: {filename} -> video_id={data_id}, seg={segment_id}")
            else:
                # Audio 세그먼트 업데이트 시도
                cursor.execute("""
                    UPDATE audio_segments
                    SET audio_path = ?
                    WHERE file_hash = ? AND segment_id = ?
                """, (audio_path, data_id, segment_id))

                if cursor.rowcount > 0:
                    audio_updated += cursor.rowcount
                    print(f"✅ Audio 세그먼트 업데이트: {filename} -> file_hash={data_id}, seg={segment_id}")
                else:
                    print(f"⚠️  매칭되는 세그먼트 없음: {filename}")

        except Exception as e:
            print(f"❌ {filename} 처리 오류: {e}")
            errors += 1

    conn.commit()
    conn.close()

    print("\n" + "="*60)
    print("📊 업데이트 결과:")
    print(f"  - YouTube 세그먼트: {youtube_updated}개")
    print(f"  - Audio 세그먼트: {audio_updated}개")
    print(f"  - 오류: {errors}개")
    print("="*60)

if __name__ == "__main__":
    print("🔄 TTS 오디오 경로 업데이트 시작...\n")
    update_tts_paths()
    print("\n✅ 완료!")
