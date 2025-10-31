"""
VectorStore에서 요약의 모든 소주제 chunk 로드 테스트

이전: 첫 번째 소주제만 로드됨
수정 후: 모든 소주제를 순서대로 합쳐서 로드
"""

import logging
import sys
import os

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

# 환경 변수 로드
from dotenv import load_dotenv
load_dotenv()

# ChromaDB 초기화
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings
from config import CHROMA_DB_FOLDER

# OpenAI Embeddings 초기화
openai_api_key = os.environ.get("OPENAI_API_KEY")
embeddings = OpenAIEmbeddings(
    model="text-embedding-3-small",
    openai_api_key=openai_api_key
)

# Summary VectorStore 초기화
summary_vectorstore = Chroma(
    collection_name="summaries",
    embedding_function=embeddings,
    persist_directory=CHROMA_DB_FOLDER
)


def test_get_all_summaries():
    """모든 요약 데이터 확인"""
    print("=" * 60)
    print("📊 Summary VectorStore 전체 확인")
    print("=" * 60)

    # 전체 데이터 가져오기
    all_results = summary_vectorstore.get()

    if not all_results or not all_results["documents"]:
        print("\n⚠️ Summary VectorStore에 저장된 데이터가 없습니다.")
        return

    total_count = len(all_results["documents"])
    print(f"\n전체 요약 문서: {total_count}개")

    # source_id별로 그룹화
    source_groups = {}
    for doc, meta in zip(all_results["documents"], all_results["metadatas"]):
        source_id = meta.get("source_id", "unknown")
        source_type = meta.get("source_type", "unknown")
        subtopic = meta.get("subtopic", "알 수 없음")
        subtopic_index = meta.get("subtopic_index", 0)

        if source_id not in source_groups:
            source_groups[source_id] = {
                "type": source_type,
                "chunks": []
            }

        source_groups[source_id]["chunks"].append({
            "index": subtopic_index,
            "subtopic": subtopic,
            "content_preview": doc[:100] + "..." if len(doc) > 100 else doc
        })

    # 출력
    for source_id, data in source_groups.items():
        source_type = data["type"]
        chunks = sorted(data["chunks"], key=lambda x: x["index"])

        print(f"\n{'='*60}")
        print(f"📁 Source: {source_id[:16]}... ({source_type})")
        print(f"   소주제 수: {len(chunks)}개")

        for chunk in chunks:
            print(f"\n   [{chunk['index']}] {chunk['subtopic']}")
            print(f"       {chunk['content_preview']}")

    print("\n" + "=" * 60)


def test_get_summary_function(source_id=None):
    """수정된 get_summary_from_vectordb 함수 테스트"""
    print("\n" + "=" * 60)
    print("🧪 get_summary_from_vectordb 함수 테스트")
    print("=" * 60)

    if not source_id:
        # 첫 번째 source_id 찾기
        all_results = summary_vectorstore.get()
        if all_results and all_results["metadatas"]:
            source_id = all_results["metadatas"][0].get("source_id")
        else:
            print("\n⚠️ 테스트할 source_id를 찾을 수 없습니다.")
            return

    print(f"\n테스트 대상 source_id: {source_id[:16]}...")

    # 수정 전: 첫 번째 chunk만 가져오기
    print("\n📌 수정 전 방식 (첫 번째 chunk만):")
    results = summary_vectorstore.get(where={"source_id": source_id})
    if results and results["documents"]:
        first_only = results["documents"][0]
        print(f"   반환 길이: {len(first_only)}자")
        print(f"   내용 미리보기: {first_only[:200]}...")

    # 수정 후: 모든 chunk 합치기
    print("\n✅ 수정 후 방식 (모든 chunk 합침):")
    if results and results["documents"]:
        documents = results["documents"]
        metadatas = results["metadatas"]

        # subtopic_index로 정렬
        sorted_chunks = []
        for doc, meta in zip(documents, metadatas):
            subtopic_index = meta.get("subtopic_index", 0)
            subtopic = meta.get("subtopic", "")
            sorted_chunks.append((subtopic_index, subtopic, doc))

        sorted_chunks.sort(key=lambda x: x[0])

        # 모든 소주제 표시
        print(f"   총 소주제 수: {len(sorted_chunks)}개")
        for idx, subtopic, doc in sorted_chunks:
            print(f"   [{idx}] {subtopic} ({len(doc)}자)")

        # 합친 결과
        combined = "\n\n".join([doc for _, _, doc in sorted_chunks])
        print(f"\n   ✅ 합친 후 총 길이: {len(combined)}자")
        print(f"   내용 미리보기:\n{combined[:500]}...")

    print("\n" + "=" * 60)


def main():
    """메인 함수"""
    print("\n🚀 요약 소주제 전체 로드 테스트\n")

    try:
        # 1. 전체 요약 확인
        test_get_all_summaries()

        # 2. 함수 테스트
        test_get_summary_function()

        print("\n✅ 테스트 완료!")
        print("\n💡 실제 사용:")
        print("   1. 웹 UI에서 중복 오디오 파일 업로드")
        print("   2. '요약' 섹션에서 모든 소주제가 표시되는지 확인")

    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
