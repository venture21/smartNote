"""
누락된 파일 찾기 및 재처리 안내

uploads 폴더에는 있지만 DB에 없는 파일들을 찾습니다.
"""

import os
import glob
import sys

sys.path.insert(0, os.path.dirname(__file__))

from modules.database import load_audio_history

def find_missing_files():
    """DB에 없는 파일 찾기"""
    print("=" * 60)
    print("🔍 누락된 파일 찾기")
    print("=" * 60)

    # uploads 폴더의 모든 오디오 파일
    audio_files = glob.glob('uploads/*.mp3') + glob.glob('uploads/*.wav') + \
                  glob.glob('uploads/*.m4a') + glob.glob('uploads/*.flac') + \
                  glob.glob('uploads/*.ogg')

    upload_filenames = {os.path.basename(f): f for f in audio_files}
    print(f"\n📁 uploads 폴더: {len(upload_filenames)}개 파일")

    # DB의 파일들
    df = load_audio_history()
    db_filenames = set(df['filename'].tolist()) if not df.empty else set()
    print(f"💾 DB: {len(db_filenames)}개 파일")

    # 누락된 파일
    missing = set(upload_filenames.keys()) - db_filenames

    if missing:
        print(f"\n❌ DB에 없는 파일 ({len(missing)}개):")
        print("-" * 60)

        missing_files = []
        for filename in sorted(missing):
            filepath = upload_filenames[filename]
            mtime = os.path.getmtime(filepath)
            from datetime import datetime
            mtime_str = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
            size_mb = os.path.getsize(filepath) / (1024 * 1024)

            print(f"\n  📄 {filename}")
            print(f"     경로: {filepath}")
            print(f"     수정: {mtime_str}")
            print(f"     크기: {size_mb:.2f} MB")

            missing_files.append(filepath)

        print("\n" + "=" * 60)
        print("💡 재처리 방법:")
        print("=" * 60)
        print("\n1. 웹 UI 사용:")
        print("   - http://localhost:5002 접속")
        print("   - 오디오 검색 탭에서 해당 파일 재업로드")
        print("\n2. 파일 삭제 후 재업로드:")
        print("   - 처리 실패한 파일들을 삭제하고 다시 업로드")

        print("\n⚠️ 주의:")
        print("   - STT 처리 실패 원인을 먼저 확인하세요")
        print("   - Gemini API 키 확인")
        print("   - 네트워크 연결 확인")
        print("   - API quota 확인")

        return missing_files
    else:
        print("\n✅ 모든 파일이 DB에 저장되어 있습니다")
        return []


if __name__ == "__main__":
    find_missing_files()
