"""
데이터베이스 저장 테스트

최근 파일이 DB에 저장되지 않는 문제 진단
"""

import os
import sys
import logging

# 로깅 설정
logging.basicConfig(level=logging.DEBUG, format='%(levelname)s: %(message)s')

# 현재 디렉토리를 Python 경로에 추가
sys.path.insert(0, os.path.dirname(__file__))

from modules.database import load_audio_history, save_audio_history
import pandas as pd
import json

def test_load():
    """데이터 로드 테스트"""
    print("=" * 60)
    print("📋 현재 DB 데이터 로드 테스트")
    print("=" * 60)

    df = load_audio_history()
    print(f"\n총 {len(df)}개 레코드")

    if not df.empty:
        print("\n최근 5개 레코드:")
        print(df[['filename', 'file_hash', 'created_at']].tail())

    return df


def test_save():
    """데이터 저장 테스트"""
    print("\n" + "=" * 60)
    print("💾 데이터 저장 테스트")
    print("=" * 60)

    # 기존 데이터 로드
    df = load_audio_history()
    print(f"\n기존 레코드 수: {len(df)}")

    # 테스트 데이터 추가
    test_row = {
        'file_hash': 'test_hash_12345',
        'filename': 'test_file.mp3',
        'file_path': 'uploads/test_file.mp3',
        'file_size': 1000000,
        'audio_duration': 100.0,
        'segments_json': json.dumps([
            {
                'id': 0,
                'speaker': 1,
                'start_time': 0.0,
                'end_time': 5.0,
                'confidence': 0.95,
                'text': '테스트 텍스트'
            }
        ]),
        'stt_service': 'gemini',
        'stt_processing_time': 20.0,
        'created_at': '2025-10-31 15:00:00',
        'summary': '테스트 요약'
    }

    print("\n테스트 데이터 추가:")
    print(f"  파일명: {test_row['filename']}")
    print(f"  해시: {test_row['file_hash']}")

    # DataFrame에 추가
    df = pd.concat([df, pd.DataFrame([test_row])], ignore_index=True)
    print(f"추가 후 레코드 수: {len(df)}")

    # 저장
    try:
        print("\n💾 저장 시도...")
        save_audio_history(df)
        print("✅ 저장 완료")
    except Exception as e:
        print(f"❌ 저장 실패: {e}")
        import traceback
        traceback.print_exc()
        return False

    # 다시 로드하여 확인
    print("\n📋 저장 후 재로드...")
    df_reloaded = load_audio_history()
    print(f"재로드 후 레코드 수: {len(df_reloaded)}")

    # 테스트 데이터 확인
    test_record = df_reloaded[df_reloaded['file_hash'] == 'test_hash_12345']
    if not test_record.empty:
        print("✅ 테스트 데이터 저장 성공!")
        return True
    else:
        print("❌ 테스트 데이터가 저장되지 않았습니다!")
        return False


def test_recent_files():
    """최근 파일 확인"""
    print("\n" + "=" * 60)
    print("📂 최근 업로드된 파일 vs DB 비교")
    print("=" * 60)

    # uploads 폴더의 파일들
    import glob
    audio_files = glob.glob('uploads/*.mp3')
    audio_files.sort(key=os.path.getmtime, reverse=True)

    print(f"\n📁 uploads 폴더 (최근 3개):")
    for f in audio_files[:3]:
        filename = os.path.basename(f)
        mtime = os.path.getmtime(f)
        from datetime import datetime
        mtime_str = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
        print(f"  - {filename}")
        print(f"    수정 시간: {mtime_str}")

    # DB의 파일들
    df = load_audio_history()
    print(f"\n💾 DB (최근 3개):")
    if not df.empty:
        for _, row in df.tail(3).iterrows():
            print(f"  - {row['filename']}")
            print(f"    생성 시간: {row['created_at']}")
    else:
        print("  (데이터 없음)")

    # 매칭 확인
    print(f"\n🔍 매칭 확인:")
    db_filenames = set(df['filename'].tolist()) if not df.empty else set()
    upload_filenames = set([os.path.basename(f) for f in audio_files])

    missing_in_db = upload_filenames - db_filenames
    if missing_in_db:
        print(f"❌ DB에 없는 파일 ({len(missing_in_db)}개):")
        for filename in missing_in_db:
            print(f"  - {filename}")
    else:
        print("✅ 모든 파일이 DB에 저장되어 있습니다")


def main():
    """메인 함수"""
    print("\n🚀 데이터베이스 저장 문제 진단\n")

    # 1. 현재 상태 확인
    test_load()

    # 2. 최근 파일 vs DB 비교
    test_recent_files()

    # 3. 저장 테스트
    success = test_save()

    if success:
        print("\n✅ 저장 기능은 정상 작동합니다")
        print("💡 문제 원인: save_audio_history()가 호출되지 않았을 가능성")
    else:
        print("\n❌ 저장 기능에 문제가 있습니다")
        print("💡 문제 원인: save_audio_history() 함수 내부 오류")


if __name__ == "__main__":
    main()
