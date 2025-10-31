"""
SQLite 데이터베이스 쿼리 테스트 및 예제

다양한 고급 쿼리 기능을 시연합니다.
"""

import logging
from modules.sqlite_db import (
    get_database_stats,
    load_audio_data,
    get_audio_segments_by_speaker,
    get_audio_segments_by_time_range,
    get_db_connection
)

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(message)s')


def test_basic_queries():
    """기본 쿼리 테스트"""
    print("=" * 60)
    print("📊 1. 데이터베이스 통계")
    print("=" * 60)

    stats = get_database_stats()
    print(f"YouTube 영상: {stats['youtube_videos']}개")
    print(f"YouTube 세그먼트: {stats['youtube_segments']}개")
    print(f"오디오 파일: {stats['audio_files']}개")
    print(f"오디오 세그먼트: {stats['audio_segments']}개")
    print(f"전체: {stats['total_items']}개 항목, {stats['total_segments']}개 세그먼트")


def test_audio_data_load():
    """오디오 데이터 로드 테스트"""
    print("\n" + "=" * 60)
    print("📂 2. 오디오 데이터 로드")
    print("=" * 60)

    audio_data = load_audio_data()
    if audio_data:
        for audio in audio_data:
            print(f"\nFilename: {audio['filename']}")
            print(f"Duration: {audio['audio_duration']:.2f}초")
            print(f"STT Service: {audio['stt_service']}")
            print(f"Processing Time: {audio['stt_processing_time']:.2f}초")
            print(f"Segments: {len(audio['segments'])}개")
            if audio['summary']:
                print(f"Summary: {audio['summary'][:100]}...")
    else:
        print("데이터가 없습니다.")


def test_speaker_queries(file_hash: str):
    """화자별 쿼리 테스트"""
    print("\n" + "=" * 60)
    print("🎤 3. 화자별 발화 분석")
    print("=" * 60)

    with get_db_connection() as conn:
        cursor = conn.cursor()

        # 화자별 통계
        cursor.execute('''
        SELECT
            speaker_id,
            COUNT(*) as segment_count,
            SUM(end_time - start_time) as total_duration,
            AVG(confidence) as avg_confidence
        FROM audio_segments
        WHERE file_hash = ?
        GROUP BY speaker_id
        ORDER BY total_duration DESC
        ''', (file_hash,))

        print("\n화자별 통계:")
        for row in cursor.fetchall():
            print(f"  화자 {row['speaker_id']}: "
                  f"{row['segment_count']}개 발화, "
                  f"{row['total_duration']:.1f}초, "
                  f"평균 신뢰도 {row['avg_confidence']:.2f}")


def test_time_based_queries(file_hash: str):
    """시간 기반 쿼리 테스트"""
    print("\n" + "=" * 60)
    print("⏱️ 4. 시간 기반 쿼리")
    print("=" * 60)

    # 첫 1분간의 발화 조회
    segments = get_audio_segments_by_time_range(file_hash, 0.0, 60.0)
    print(f"\n첫 1분간 발화: {len(segments)}개")
    for seg in segments[:3]:
        print(f"  [{seg['start_time']:.1f}s] 화자 {seg['speaker_id']}: {seg['text'][:50]}...")


def test_long_segments_query(file_hash: str):
    """가장 긴 발화 찾기"""
    print("\n" + "=" * 60)
    print("📏 5. 가장 긴 발화 Top 5")
    print("=" * 60)

    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute('''
        SELECT speaker_id, text, (end_time - start_time) as duration, start_time
        FROM audio_segments
        WHERE file_hash = ?
        ORDER BY duration DESC
        LIMIT 5
        ''', (file_hash,))

        for idx, row in enumerate(cursor.fetchall(), 1):
            print(f"\n{idx}. 화자 {row['speaker_id']} ({row['duration']:.1f}초, {row['start_time']:.1f}s)")
            print(f"   {row['text'][:100]}...")


def test_keyword_search(file_hash: str, keyword: str):
    """키워드 검색 테스트"""
    print("\n" + "=" * 60)
    print(f"🔍 6. 키워드 검색: '{keyword}'")
    print("=" * 60)

    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute('''
        SELECT speaker_id, start_time, text
        FROM audio_segments
        WHERE file_hash = ? AND text LIKE ?
        ORDER BY start_time
        ''', (file_hash, f'%{keyword}%'))

        results = cursor.fetchall()
        print(f"\n'{keyword}' 포함 발화: {len(results)}개")

        for row in results[:5]:
            print(f"\n  [{row['start_time']:.1f}s] 화자 {row['speaker_id']}:")
            # 키워드 하이라이트
            text = row['text']
            highlighted = text.replace(keyword, f"**{keyword}**")
            print(f"  {highlighted}")


def test_confidence_analysis(file_hash: str):
    """신뢰도 분석"""
    print("\n" + "=" * 60)
    print("📈 7. STT 신뢰도 분석")
    print("=" * 60)

    with get_db_connection() as conn:
        cursor = conn.cursor()

        # 전체 평균 신뢰도
        cursor.execute('''
        SELECT
            AVG(confidence) as avg_conf,
            MIN(confidence) as min_conf,
            MAX(confidence) as max_conf
        FROM audio_segments
        WHERE file_hash = ?
        ''', (file_hash,))

        row = cursor.fetchone()
        print(f"\n전체 신뢰도:")
        print(f"  평균: {row['avg_conf']:.2%}")
        print(f"  최소: {row['min_conf']:.2%}")
        print(f"  최대: {row['max_conf']:.2%}")

        # 낮은 신뢰도 세그먼트 찾기
        cursor.execute('''
        SELECT speaker_id, start_time, confidence, text
        FROM audio_segments
        WHERE file_hash = ? AND confidence < 0.95
        ORDER BY confidence ASC
        LIMIT 3
        ''', (file_hash,))

        low_conf = cursor.fetchall()
        if low_conf:
            print(f"\n신뢰도 낮은 발화 Top 3:")
            for row in low_conf:
                print(f"\n  화자 {row['speaker_id']} ({row['confidence']:.2%}, {row['start_time']:.1f}s)")
                print(f"  {row['text'][:80]}...")


def main():
    """메인 테스트 실행"""
    print("\n🚀 SQLite 데이터베이스 쿼리 테스트 시작\n")

    # 1. 기본 통계
    test_basic_queries()

    # 2. 오디오 데이터 로드
    test_audio_data_load()

    # 오디오 데이터가 있으면 추가 테스트 실행
    audio_data = load_audio_data()
    if audio_data and len(audio_data) > 0:
        file_hash = audio_data[0]['file_hash']

        # 3. 화자별 분석
        test_speaker_queries(file_hash)

        # 4. 시간 기반 쿼리
        test_time_based_queries(file_hash)

        # 5. 긴 발화 찾기
        test_long_segments_query(file_hash)

        # 6. 키워드 검색
        test_keyword_search(file_hash, "경복궁")

        # 7. 신뢰도 분석
        test_confidence_analysis(file_hash)

    print("\n" + "=" * 60)
    print("✨ 테스트 완료!")
    print("=" * 60)


if __name__ == "__main__":
    main()
