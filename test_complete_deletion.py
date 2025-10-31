"""
완전 삭제 기능 테스트

SQLite + VectorStore + 실제 파일 삭제를 테스트합니다.
"""

import logging
import os
from modules.sqlite_db import (
    load_audio_data,
    get_database_stats
)

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(message)s')


def check_before_deletion():
    """삭제 전 상태 확인"""
    print("=" * 60)
    print("🔍 삭제 전 상태 확인")
    print("=" * 60)

    # 데이터베이스 통계
    stats = get_database_stats()
    print(f"\n📊 데이터베이스:")
    print(f"   - 오디오 파일: {stats['audio_files']}개")
    print(f"   - 오디오 세그먼트: {stats['audio_segments']}개")

    # 오디오 목록
    audio_data = load_audio_data()
    if audio_data:
        print(f"\n📁 오디오 파일:")
        for item in audio_data:
            file_path = item['file_path'].replace('\\', '/')
            exists = os.path.exists(file_path)

            print(f"\n   파일명: {item['filename']}")
            print(f"   Hash: {item['file_hash'][:16]}...")
            print(f"   경로: {file_path}")
            print(f"   실제 파일: {'✅ 존재' if exists else '❌ 없음'}")
            print(f"   세그먼트: {len(item['segments'])}개")

    # VectorStore 확인
    try:
        from langchain_chroma import Chroma
        from langchain_openai import OpenAIEmbeddings
        from config import CHROMA_DB_FOLDER

        openai_api_key = os.environ.get("OPENAI_API_KEY")
        embeddings = OpenAIEmbeddings(
            model="text-embedding-3-small",
            openai_api_key=openai_api_key
        )

        audio_vs = Chroma(
            collection_name="audio_transcripts",
            embedding_function=embeddings,
            persist_directory=CHROMA_DB_FOLDER
        )
        audio_count = audio_vs._collection.count()

        summary_vs = Chroma(
            collection_name="summaries",
            embedding_function=embeddings,
            persist_directory=CHROMA_DB_FOLDER
        )
        summary_count = summary_vs._collection.count()

        print(f"\n🔍 VectorStore:")
        print(f"   - Audio 세그먼트: {audio_count}개")
        print(f"   - Summary: {summary_count}개")
        print(f"   - 전체: {audio_count + summary_count}개")

    except Exception as e:
        print(f"\n⚠️ VectorStore 확인 오류: {e}")

    print("\n" + "=" * 60)


def check_after_deletion():
    """삭제 후 상태 확인"""
    print("\n" + "=" * 60)
    print("🔍 삭제 후 상태 확인")
    print("=" * 60)

    # 데이터베이스 통계
    stats = get_database_stats()
    print(f"\n📊 데이터베이스:")
    print(f"   - 오디오 파일: {stats['audio_files']}개")
    print(f"   - 오디오 세그먼트: {stats['audio_segments']}개")

    # 오디오 목록
    audio_data = load_audio_data()
    if audio_data:
        print(f"\n📁 남은 오디오 파일: {len(audio_data)}개")
    else:
        print(f"\n✅ 모든 오디오 파일 삭제됨")

    # 실제 파일 확인
    uploads_files = []
    if os.path.exists('uploads'):
        uploads_files = [f for f in os.listdir('uploads') if f.endswith(('.mp3', '.wav', '.m4a', '.flac', '.ogg'))]

    print(f"\n📂 uploads 폴더:")
    if uploads_files:
        print(f"   - 남은 파일: {len(uploads_files)}개")
        for f in uploads_files[:5]:
            print(f"     • {f}")
    else:
        print(f"   ✅ 모든 오디오 파일 삭제됨")

    # VectorStore 확인
    try:
        from langchain_chroma import Chroma
        from langchain_openai import OpenAIEmbeddings
        from config import CHROMA_DB_FOLDER

        openai_api_key = os.environ.get("OPENAI_API_KEY")
        embeddings = OpenAIEmbeddings(
            model="text-embedding-3-small",
            openai_api_key=openai_api_key
        )

        audio_vs = Chroma(
            collection_name="audio_transcripts",
            embedding_function=embeddings,
            persist_directory=CHROMA_DB_FOLDER
        )
        audio_count = audio_vs._collection.count()

        summary_vs = Chroma(
            collection_name="summaries",
            embedding_function=embeddings,
            persist_directory=CHROMA_DB_FOLDER
        )
        summary_count = summary_vs._collection.count()

        print(f"\n🔍 VectorStore:")
        print(f"   - Audio 세그먼트: {audio_count}개")
        print(f"   - Summary: {summary_count}개")
        if audio_count == 0 and summary_count == 0:
            print(f"   ✅ 모든 VectorStore 데이터 삭제됨")

    except Exception as e:
        print(f"\n⚠️ VectorStore 확인 오류: {e}")

    print("\n" + "=" * 60)


def main():
    """메인 함수"""
    print("\n🚀 완전 삭제 기능 테스트\n")

    # 삭제 전 상태
    check_before_deletion()

    print("\n" + "=" * 60)
    print("💡 테스트 방법")
    print("=" * 60)
    print("\n1. 웹 UI 사용:")
    print("   - http://localhost:5002 접속")
    print("   - '🗂️ 데이터 관리' 탭 클릭")
    print("   - '🗑️ 삭제' 버튼 클릭")
    print("\n2. API 직접 호출:")
    print("   curl -X POST http://localhost:5002/api/data-management/delete \\")
    print("        -H 'Content-Type: application/json' \\")
    print("        -d '{\"type\": \"audio\", \"id\": \"95d4d88b7a28e859fff5783f80fb88d1\"}'")
    print("\n3. 삭제 후 이 스크립트 다시 실행:")
    print("   python test_complete_deletion.py")
    print("\n" + "=" * 60)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "after":
        # 삭제 후 확인
        check_after_deletion()
    else:
        # 일반 테스트
        main()
