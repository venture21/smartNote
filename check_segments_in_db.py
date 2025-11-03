"""
DB에 저장된 세그먼트 데이터를 확인하는 스크립트
"""
import json
from modules.sqlite_db import get_youtube_data, get_audio_data

def check_youtube_segments(video_id=None):
    """YouTube 데이터의 세그먼트 확인"""
    youtube_data = get_youtube_data(video_id)

    if not youtube_data:
        print("❌ YouTube 데이터를 찾을 수 없습니다.")
        return

    print(f"\n{'='*80}")
    print(f"YouTube 데이터 확인 (총 {len(youtube_data)}개)")
    print(f"{'='*80}\n")

    for idx, data in enumerate(youtube_data, 1):
        video_id = data.get('video_id', 'Unknown')
        title = data.get('title', 'Unknown')
        segments_json = data.get('segments', '[]')

        try:
            segments = json.loads(segments_json) if isinstance(segments_json, str) else segments_json
            segment_count = len(segments)

            print(f"{idx}. Video ID: {video_id}")
            print(f"   제목: {title}")
            print(f"   세그먼트 수: {segment_count}개")

            if segment_count == 0:
                print(f"   ⚠️ 세그먼트가 비어있습니다!")
            elif segment_count < 10:
                print(f"   ⚠️ 세그먼트가 적습니다 ({segment_count}개). STT 실패 가능성 있음")
            else:
                print(f"   ✅ 정상")
                # 첫 번째 세그먼트 샘플 출력
                if segments:
                    first_seg = segments[0]
                    print(f"   샘플: {first_seg.get('text', '')[:50]}...")

            print()

        except json.JSONDecodeError as e:
            print(f"   ❌ JSON 파싱 오류: {e}")
            print(f"   원본 데이터: {segments_json[:100]}...")
            print()


def check_audio_segments(file_hash=None):
    """오디오 데이터의 세그먼트 확인"""
    audio_data = get_audio_data(file_hash)

    if not audio_data:
        print("❌ 오디오 데이터를 찾을 수 없습니다.")
        return

    print(f"\n{'='*80}")
    print(f"오디오 데이터 확인 (총 {len(audio_data)}개)")
    print(f"{'='*80}\n")

    for idx, data in enumerate(audio_data, 1):
        file_hash = data.get('file_hash', 'Unknown')
        filename = data.get('filename', 'Unknown')
        segments_json = data.get('segments', '[]')

        try:
            segments = json.loads(segments_json) if isinstance(segments_json, str) else segments_json
            segment_count = len(segments)

            print(f"{idx}. File Hash: {file_hash[:16]}...")
            print(f"   파일명: {filename}")
            print(f"   세그먼트 수: {segment_count}개")

            if segment_count == 0:
                print(f"   ⚠️ 세그먼트가 비어있습니다!")
            elif segment_count < 10:
                print(f"   ⚠️ 세그먼트가 적습니다 ({segment_count}개). STT 실패 가능성 있음")
            else:
                print(f"   ✅ 정상")
                # 첫 번째 세그먼트 샘플 출력
                if segments:
                    first_seg = segments[0]
                    print(f"   샘플: {first_seg.get('text', '')[:50]}...")

            print()

        except json.JSONDecodeError as e:
            print(f"   ❌ JSON 파싱 오류: {e}")
            print(f"   원본 데이터: {segments_json[:100]}...")
            print()


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        data_type = sys.argv[1]
        data_id = sys.argv[2] if len(sys.argv) > 2 else None

        if data_type == "youtube":
            check_youtube_segments(data_id)
        elif data_type == "audio":
            check_audio_segments(data_id)
        else:
            print("사용법: python check_segments_in_db.py [youtube|audio] [video_id|file_hash]")
    else:
        # 인자가 없으면 모두 확인
        check_youtube_segments()
        check_audio_segments()
