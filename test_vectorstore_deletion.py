"""
VectorStore 삭제 기능 테스트

SQLite + VectorStore 통합 삭제를 테스트합니다.
"""

import logging
from modules.sqlite_db import (
    load_audio_data,
    load_youtube_data,
    get_database_stats
)

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(message)s')


def test_data_list():
    """현재 데이터 목록 확인"""
    print("=" * 60)
    print("📊 현재 데이터베이스 상태")
    print("=" * 60)

    stats = get_database_stats()
    print(f"\n📹 YouTube 영상: {stats['youtube_videos']}개")
    print(f"   - 세그먼트: {stats['youtube_segments']}개")
    print(f"\n🎵 오디오 파일: {stats['audio_files']}개")
    print(f"   - 세그먼트: {stats['audio_segments']}개")

    # YouTube 목록
    youtube_data = load_youtube_data()
    if youtube_data:
        print(f"\n📹 YouTube 영상 목록:")
        for item in youtube_data:
            print(f"   - {item['title']} (ID: {item['video_id']})")
            print(f"     세그먼트: {len(item['segments'])}개")

    # 오디오 목록
    audio_data = load_audio_data()
    if audio_data:
        print(f"\n🎵 오디오 파일 목록:")
        for item in audio_data:
            print(f"   - {item['filename']} (Hash: {item['file_hash'][:16]}...)")
            print(f"     세그먼트: {len(item['segments'])}개")

    print("\n" + "=" * 60)


def test_vectorstore_check():
    """VectorStore 상태 확인"""
    print("\n" + "=" * 60)
    print("🔍 VectorStore 상태 확인")
    print("=" * 60)

    try:
        from langchain_chroma import Chroma
        from langchain_openai import OpenAIEmbeddings
        import os
        from config import CHROMA_DB_FOLDER

        # OpenAI Embeddings 초기화
        openai_api_key = os.environ.get("OPENAI_API_KEY")
        embeddings = OpenAIEmbeddings(
            model="text-embedding-3-small",
            openai_api_key=openai_api_key
        )

        # YouTube VectorStore 확인
        youtube_vs = Chroma(
            collection_name="youtube_transcripts",
            embedding_function=embeddings,
            persist_directory=CHROMA_DB_FOLDER
        )
        youtube_count = youtube_vs._collection.count()
        print(f"\n📹 YouTube VectorStore: {youtube_count}개 문서")

        # Audio VectorStore 확인
        audio_vs = Chroma(
            collection_name="audio_transcripts",
            embedding_function=embeddings,
            persist_directory=CHROMA_DB_FOLDER
        )
        audio_count = audio_vs._collection.count()
        print(f"🎵 Audio VectorStore: {audio_count}개 문서")

        # Summary VectorStore 확인
        summary_vs = Chroma(
            collection_name="summaries",
            embedding_function=embeddings,
            persist_directory=CHROMA_DB_FOLDER
        )
        summary_count = summary_vs._collection.count()
        print(f"📝 Summary VectorStore: {summary_count}개 문서")

        print(f"\n📈 전체: {youtube_count + audio_count + summary_count}개 문서")

    except Exception as e:
        print(f"⚠️ VectorStore 확인 중 오류: {e}")

    print("=" * 60)


def main():
    """메인 함수"""
    print("\n🚀 VectorStore 삭제 기능 테스트\n")

    # 1. 현재 데이터 목록
    test_data_list()

    # 2. VectorStore 상태
    test_vectorstore_check()

    print("\n✅ 테스트 완료!")
    print("\n💡 삭제 테스트:")
    print("   1. 웹 UI에서 '🗂️ 데이터 관리' 탭 접속")
    print("   2. 삭제할 항목의 '🗑️ 삭제' 버튼 클릭")
    print("   3. 삭제 후 다시 이 스크립트 실행하여 확인")
    print("\n   또는 API 직접 호출:")
    print("   curl -X POST http://localhost:5002/api/data-management/delete \\")
    print("        -H 'Content-Type: application/json' \\")
    print("        -d '{\"type\": \"audio\", \"id\": \"<file_hash>\"}'")


if __name__ == "__main__":
    main()
