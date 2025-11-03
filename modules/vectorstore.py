"""
VectorStore 관련 기능

LangChain ChromaDB를 사용한 벡터 저장 및 검색 기능을 제공합니다.
"""

import logging
import os
from datetime import datetime

from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings
from langchain_core.documents import Document
from langchain_community.vectorstores.utils import filter_complex_metadata

import config
from modules.text_processing import parse_summary_by_subtopics


# =============================================================================
# 전역 변수
# =============================================================================
embeddings = None
youtube_vectorstore = None
audio_vectorstore = None
summary_vectorstore = None


# =============================================================================
# VectorStore 초기화
# =============================================================================
def initialize_collections():
    """LangChain VectorStore 초기화 (OpenAI Embeddings 사용)"""
    global embeddings, youtube_vectorstore, audio_vectorstore, summary_vectorstore

    try:
        # OpenAI Embeddings 초기화
        openai_api_key = os.environ.get("OPENAI_API_KEY")
        embeddings = OpenAIEmbeddings(
            model="text-embedding-3-small", openai_api_key=openai_api_key
        )
        logging.info("✅ OpenAI Embeddings 사용")

        # YouTube VectorStore
        youtube_vectorstore = Chroma(
            collection_name="youtube_transcripts",
            embedding_function=embeddings,
            persist_directory=config.CHROMA_DB_FOLDER,
        )

        # Audio VectorStore
        audio_vectorstore = Chroma(
            collection_name="audio_transcripts",
            embedding_function=embeddings,
            persist_directory=config.CHROMA_DB_FOLDER,
        )

        # Summary VectorStore
        summary_vectorstore = Chroma(
            collection_name="summaries",
            embedding_function=embeddings,
            persist_directory=config.CHROMA_DB_FOLDER,
        )

        logging.info("✅ LangChain VectorStore 초기화 완료")
        logging.info("   - YouTube VectorStore 초기화됨")
        logging.info("   - Audio VectorStore 초기화됨")
        logging.info("   - Summary VectorStore 초기화됨")
    except Exception as e:
        logging.error(f"❌ LangChain VectorStore 초기화 오류: {e}")
        import traceback
        traceback.print_exc()


# =============================================================================
# VectorStore 저장 기능
# =============================================================================
def store_segments_in_vectordb(
    segments, source_id, source_type="youtube", filename=None, title=None, use_chunking=True, chunk_size=500, chunk_overlap=100
):
    """
    세그먼트를 VectorDB에 저장 (LangChain 방식)

    Args:
        segments: STT로 추출된 세그먼트 리스트
        source_id: YouTube video_id 또는 audio file_hash
        source_type: "youtube" 또는 "audio"
        filename: 오디오 파일명 (오디오일 경우)
        title: 제목 (사용자 입력 또는 자동 추출)
        use_chunking: True이면 토큰 기반 청킹 사용, False이면 원본 세그먼트 저장 (기본값: True)
        chunk_size: 청킹 시 chunk당 최대 문자 수 (기본값: 500)
        chunk_overlap: 청킹 시 chunk 간 중복 문자 수 (기본값: 100)
    """
    try:
        from modules.text_processing import create_token_based_chunks

        vectorstore = (
            youtube_vectorstore if source_type == "youtube" else audio_vectorstore
        )

        if not vectorstore:
            logging.error("❌ LangChain VectorStore가 초기화되지 않았습니다.")
            return False

        # 기존 데이터 삭제 (같은 source_id)
        try:
            # LangChain Chroma에서 기존 데이터 삭제
            existing_docs = vectorstore.get(where={"source_id": source_id})
            if existing_docs and existing_docs["ids"]:
                vectorstore.delete(ids=existing_docs["ids"])
                logging.info(
                    f"🗑️ 기존 데이터 삭제: {len(existing_docs['ids'])}개 문서"
                )
        except Exception as e:
            logging.warning(f"기존 데이터 삭제 중 오류 (무시): {e}")

        # 청킹 여부에 따라 처리
        if use_chunking:
            logging.info(f"📦 토큰 기반 청킹 시작 (chunk_size={chunk_size}, overlap={chunk_overlap})...")
            chunks = create_token_based_chunks(segments, chunk_size=chunk_size, chunk_overlap=chunk_overlap)

            if not chunks:
                logging.warning("⚠️ 청킹 결과가 비어있음, 원본 세그먼트로 저장합니다.")
                use_chunking = False  # 폴백: 원본 세그먼트 저장
            else:
                # LangChain Document 객체 생성 (청크 기반)
                documents = []
                doc_ids = []

                for chunk in chunks:
                    # Document (content)
                    text = chunk["text"]

                    # Metadata
                    metadata = {
                        "source_id": source_id,
                        "source_type": source_type,
                        "document_type": "chunk",  # 청크임을 표시
                        "chunk_id": int(chunk["chunk_id"]),
                        "segment_ids": chunk["segment_ids"],  # 원본 세그먼트 ID 리스트 (복잡한 메타데이터)
                        "speakers": chunk["speakers"],  # 화자 리스트 (복잡한 메타데이터)
                        "start_time": float(chunk["start_time"]),
                        "end_time": float(chunk["end_time"]) if chunk["end_time"] is not None else None,
                        "confidence": float(chunk["confidence"]),
                    }

                    # 제목 추가
                    if title:
                        metadata["title"] = title

                    if source_type == "audio" and filename:
                        metadata["filename"] = filename

                    # ID: source_id + chunk_id
                    doc_id = f"{source_id}_chunk_{chunk['chunk_id']}"
                    doc_ids.append(doc_id)

                    # LangChain Document 생성
                    doc = Document(page_content=text, metadata=metadata)
                    documents.append(doc)

                # 복잡한 메타데이터 필터링 (segment_ids, speakers는 리스트)
                logging.info(f"🔧 복잡한 메타데이터 필터링 중... (Document 수: {len(documents)})")
                filtered_documents = filter_complex_metadata(documents)

                # LangChain VectorStore에 저장 (자동으로 임베딩 생성됨)
                vectorstore.add_documents(
                    documents=filtered_documents,
                    ids=doc_ids,
                )

                logging.info(
                    f"✅ VectorDB 저장 완료: {len(chunks)}개 청크 (원본 {len(segments)}개 세그먼트, source: {source_id})"
                )
                return True

        # 청킹 미사용 또는 폴백: 원본 세그먼트 저장
        if not use_chunking:
            documents = []

            for idx, segment in enumerate(segments):
                # Document (content)
                text = segment["text"]

                # end_time 계산 (다음 세그먼트의 start_time 또는 None)
                if idx < len(segments) - 1:
                    end_time = float(segments[idx + 1]["start_time"])
                else:
                    # 마지막 세그먼트는 end_time이 없음 (None)
                    end_time = None

                # Metadata
                metadata = {
                    "source_id": source_id,
                    "source_type": source_type,
                    "document_type": "segment",  # 명시적으로 세그먼트임을 표시
                    "speaker": str(segment["speaker"]),
                    "start_time": float(segment["start_time"]),
                    "end_time": end_time,
                    "confidence": float(segment.get("confidence", 0.0)),
                    "segment_id": int(segment["id"]),
                }

                # 제목 추가
                if title:
                    metadata["title"] = title

                if source_type == "audio" and filename:
                    metadata["filename"] = filename

                # ID: source_id + segment_id
                doc_id = f"{source_id}_seg_{segment['id']}"

                # LangChain Document 생성
                doc = Document(page_content=text, metadata=metadata)
                documents.append(doc)

            # LangChain VectorStore에 저장 (자동으로 임베딩 생성됨)
            vectorstore.add_documents(
                documents=documents,
                ids=[f"{source_id}_seg_{seg['id']}" for seg in segments],
            )

            logging.info(
                f"✅ VectorDB 저장 완료: {len(segments)}개 세그먼트 (source: {source_id})"
            )
            return True

    except Exception as e:
        logging.error(f"❌ VectorDB 저장 오류: {e}")
        import traceback

        traceback.print_exc()
        return False


def store_summary_in_vectordb(summary, source_id, source_type="youtube", filename=None):
    """
    요약을 소주제별로 분할하여 Summary VectorDB에 저장

    Args:
        summary: 생성된 요약 텍스트 (마크다운 형식)
        source_id: YouTube video_id 또는 audio file_hash
        source_type: "youtube" 또는 "audio"
        filename: 오디오 파일명 (오디오일 경우)
    """
    try:
        # 디버깅: 입력 파라미터 확인
        logging.info(f"📥 store_summary_in_vectordb 호출됨 - source_id: {source_id}, source_type: {source_type}")
        logging.debug(f"요약 타입: {type(summary)}, 길이: {len(summary) if summary else 0}")
        logging.debug(f"요약 미리보기: {summary[:200] if summary else 'None'}...")

        if not summary_vectorstore:
            logging.error("❌ Summary VectorStore가 초기화되지 않았습니다.")
            return False

        # 기존 요약 데이터 삭제 (같은 source_id의 summary)
        try:
            existing_docs = summary_vectorstore.get(where={"source_id": source_id})
            if existing_docs and existing_docs["ids"]:
                summary_vectorstore.delete(ids=existing_docs["ids"])
                logging.info(f"🗑️ 기존 요약 삭제: {len(existing_docs['ids'])}개")
        except Exception as e:
            logging.warning(f"기존 요약 삭제 중 오류 (무시): {e}")

        # 요약을 소주제별로 분할
        logging.info("🔍 소주제 파싱 시작...")
        subtopics = parse_summary_by_subtopics(summary)
        logging.info(f"🔍 소주제 파싱 결과: {len(subtopics) if subtopics else 0}개")

        if not subtopics:
            # 파싱 실패 시 전체를 하나의 문서로 저장 (fallback)
            logging.warning("⚠️ 소주제 파싱 실패, 전체 요약을 하나의 문서로 저장합니다.")
            metadata = {
                "source_id": source_id,
                "source_type": source_type,
                "document_type": "summary",
                "subtopic": "전체",
                "subtopic_index": 0,
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            if source_type == "audio" and filename:
                metadata["filename"] = filename

            doc = Document(page_content=summary, metadata=metadata)
            doc_id = f"{source_id}_summary_0"

            # 복잡한 메타데이터 필터링 (일관성을 위해)
            filtered_docs = filter_complex_metadata([doc])
            summary_vectorstore.add_documents(documents=filtered_docs, ids=[doc_id])
            logging.info(
                f"✅ 요약 Summary VectorDB 저장 완료 (전체, source: {source_id})"
            )
            return True

        # 각 소주제를 별도의 Document로 저장
        documents = []
        doc_ids = []

        for idx, subtopic in enumerate(subtopics):
            # cited_chunk_ids 추출
            cited_chunk_ids = subtopic.get("cited_chunk_ids", [])

            metadata = {
                "source_id": source_id,
                "source_type": source_type,
                "document_type": "summary",
                "subtopic": subtopic["title"],
                "subtopic_index": idx,
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "cited_chunk_ids": cited_chunk_ids,  # citation 정보 저장 (청크 번호)
            }

            if source_type == "audio" and filename:
                metadata["filename"] = filename

            # 소주제 제목 + 내용을 함께 저장 (검색 시 컨텍스트 유지)
            content = f"**{subtopic['title']}**\n\n{subtopic['content']}"
            doc = Document(page_content=content, metadata=metadata)
            documents.append(doc)

            doc_id = f"{source_id}_summary_{idx}"
            doc_ids.append(doc_id)

            logging.debug(f"📌 소주제 '{subtopic['title']}' - cited_chunk_ids: {cited_chunk_ids}")

        # 복잡한 메타데이터 필터링 (리스트, 딕셔너리 등을 문자열로 변환)
        logging.info(f"🔧 복잡한 메타데이터 필터링 중... (Document 수: {len(documents)})")
        filtered_documents = filter_complex_metadata(documents)
        logging.info(f"✅ 메타데이터 필터링 완료")

        # Summary VectorStore에 일괄 저장
        summary_vectorstore.add_documents(documents=filtered_documents, ids=doc_ids)

        logging.info(
            f"✅ 요약 Summary VectorDB 저장 완료 ({len(subtopics)}개 소주제, source: {source_id})"
        )
        return True

    except Exception as e:
        logging.error(f"❌ 요약 VectorDB 저장 오류: {e}")
        import traceback

        traceback.print_exc()
        return False


# =============================================================================
# VectorStore 조회 기능
# =============================================================================
def get_summary_from_vectordb(source_id, source_type="youtube"):
    """
    별도의 Summary VectorDB에서 저장된 요약 가져오기 (모든 소주제 포함)

    Args:
        source_id: YouTube video_id 또는 audio file_hash
        source_type: "youtube" 또는 "audio"

    Returns:
        요약 텍스트 (모든 소주제 합쳐진 것) 또는 None (없으면)
    """
    try:
        if not summary_vectorstore:
            logging.error("❌ Summary VectorStore가 초기화되지 않았습니다.")
            return None

        # 요약 문서 검색 (source_id 일치)
        results = summary_vectorstore.get(where={"source_id": source_id})

        if results and results["documents"] and len(results["documents"]) > 0:
            # 모든 소주제를 순서대로 정렬하여 합치기
            documents = results["documents"]
            metadatas = results["metadatas"]

            # subtopic_index로 정렬 (저장 순서 유지)
            sorted_chunks = []
            for doc, meta in zip(documents, metadatas):
                subtopic_index = meta.get("subtopic_index", 0)
                sorted_chunks.append((subtopic_index, doc))

            sorted_chunks.sort(key=lambda x: x[0])

            # 모든 소주제를 합쳐서 반환
            summary = "\n\n".join([doc for _, doc in sorted_chunks])

            logging.info(
                f"✅ Summary VectorDB에서 요약 로드 완료 (source: {source_id}, {len(documents)}개 소주제)"
            )
            return summary
        else:
            logging.info(
                f"ℹ️ Summary VectorDB에 저장된 요약이 없습니다 (source: {source_id})"
            )
            return None

    except Exception as e:
        logging.error(f"❌ Summary VectorDB 요약 로드 오류: {e}")
        import traceback

        traceback.print_exc()
        return None


def delete_from_vectorstore(source_id, source_type="youtube"):
    """
    VectorStore에서 특정 source_id의 모든 데이터 삭제 (세그먼트 + 요약)

    Args:
        source_id: YouTube video_id 또는 audio file_hash
        source_type: "youtube" 또는 "audio"

    Returns:
        (성공 여부, 삭제된 문서 수)
    """
    try:
        total_deleted = 0

        # 1. 세그먼트 삭제 (youtube_vectorstore 또는 audio_vectorstore)
        vectorstore = youtube_vectorstore if source_type == "youtube" else audio_vectorstore

        if vectorstore:
            try:
                existing_docs = vectorstore.get(where={"source_id": source_id})
                if existing_docs and existing_docs["ids"]:
                    vectorstore.delete(ids=existing_docs["ids"])
                    deleted_count = len(existing_docs["ids"])
                    total_deleted += deleted_count
                    logging.info(f"🗑️ {source_type} VectorStore에서 {deleted_count}개 세그먼트 삭제")
            except Exception as e:
                logging.warning(f"⚠️ {source_type} VectorStore 삭제 중 오류: {e}")

        # 2. 요약 삭제 (summary_vectorstore)
        if summary_vectorstore:
            try:
                existing_summary = summary_vectorstore.get(where={"source_id": source_id})
                if existing_summary and existing_summary["ids"]:
                    summary_vectorstore.delete(ids=existing_summary["ids"])
                    summary_count = len(existing_summary["ids"])
                    total_deleted += summary_count
                    logging.info(f"🗑️ Summary VectorStore에서 {summary_count}개 요약 삭제")
            except Exception as e:
                logging.warning(f"⚠️ Summary VectorStore 삭제 중 오류: {e}")

        logging.info(f"✅ VectorStore 삭제 완료: 총 {total_deleted}개 문서 삭제됨")
        return True, total_deleted

    except Exception as e:
        logging.error(f"❌ VectorStore 삭제 오류: {e}")
        import traceback
        traceback.print_exc()
        return False, 0


def search_vectordb(query, source_id=None, source_type=None, n_results=5, document_type=None):
    """
    VectorDB에서 검색 (LangChain Retriever 사용)

    Args:
        query: 검색 쿼리
        source_id: 특정 source로 제한 (선택)
        source_type: "youtube", "audio", "summary" 또는 None (선택)
        n_results: 반환할 결과 수
        document_type: "chunk", "segment" 또는 None (선택, chunk만 검색하려면 "chunk" 지정)

    Returns:
        검색 결과 리스트
    """
    try:
        # 검색할 VectorStore 결정
        vectorstores_to_search = []
        if source_type == "youtube":
            vectorstores_to_search = [youtube_vectorstore]
            logging.info(f"🔍 검색 대상: YouTube VectorStore만")
        elif source_type == "audio":
            vectorstores_to_search = [audio_vectorstore]
            logging.info(f"🔍 검색 대상: Audio VectorStore만")
        elif source_type == "summary":
            vectorstores_to_search = [summary_vectorstore]
            logging.info(f"🔍 검색 대상: Summary VectorStore만")
        else:
            vectorstores_to_search = [youtube_vectorstore, audio_vectorstore]
            logging.info(f"🔍 검색 대상: YouTube + Audio VectorStore (전체 검색)")

        all_results = []

        for idx, vectorstore in enumerate(vectorstores_to_search):
            if not vectorstore:
                logging.warning(f"⚠️ VectorStore #{idx}가 초기화되지 않았습니다.")
                continue

            # VectorStore에 저장된 문서 수 확인
            try:
                collection = vectorstore._collection
                total_docs = collection.count()
                logging.info(f"📊 VectorStore #{idx} 문서 수: {total_docs}개")
            except Exception as e:
                logging.warning(f"⚠️ VectorStore #{idx} 문서 수 확인 실패: {e}")

            # where 필터 구성
            search_kwargs = {"k": n_results}
            filter_dict = {}

            if source_id:
                filter_dict["source_id"] = source_id

            if document_type:
                filter_dict["document_type"] = document_type
                logging.info(f"📋 document_type 필터: {document_type}")

            if filter_dict:
                search_kwargs["filter"] = filter_dict

            # LangChain Retriever 생성 및 검색
            retriever = vectorstore.as_retriever(
                search_type="similarity", search_kwargs=search_kwargs
            )

            # 검색 수행 (similarity_search_with_score 사용)
            logging.info(f"🔎 검색 쿼리: '{query}', k={n_results}, 필터: {filter_dict if filter_dict else 'None'}")
            docs_with_scores = vectorstore.similarity_search_with_score(
                query=query, k=n_results, filter=search_kwargs.get("filter")
            )
            logging.info(
                f"✅ VectorStore #{idx}에서 {len(docs_with_scores)}개 결과 발견"
            )

            # 결과 파싱
            for doc, score in docs_with_scores:
                all_results.append(
                    {
                        "id": doc.metadata.get("segment_id", ""),
                        "document": doc.page_content,
                        "metadata": doc.metadata,
                        "distance": score,  # LangChain은 거리(낮을수록 유사)를 반환
                    }
                )

        # 거리 기준으로 정렬 (낮을수록 유사)
        all_results.sort(key=lambda x: x.get("distance", float("inf")))

        # 상위 n_results개만 반환
        return all_results[:n_results]

    except Exception as e:
        logging.error(f"❌ VectorDB 검색 오류: {e}")
        import traceback

        traceback.print_exc()
        return []


def update_title_in_vectorstore(source_id, source_type, title):
    """
    VectorStore의 세그먼트 메타데이터에 제목 업데이트

    Args:
        source_id: YouTube video_id 또는 audio file_hash
        source_type: "youtube" 또는 "audio"
        title: 업데이트할 제목

    Returns:
        (성공 여부, 업데이트된 문서 수)
    """
    try:
        # VectorStore 선택
        vectorstore = (
            youtube_vectorstore if source_type == "youtube" else audio_vectorstore
        )

        if not vectorstore:
            logging.error("❌ VectorStore가 초기화되지 않았습니다.")
            return False, 0

        # 해당 source_id의 모든 문서 가져오기
        existing_docs = vectorstore.get(where={"source_id": source_id})

        if not existing_docs or not existing_docs["ids"]:
            logging.warning(f"⚠️ 해당 source_id의 데이터를 찾을 수 없습니다: {source_id}")
            return False, 0

        # 각 문서의 메타데이터에 title 추가
        # LangChain Chroma는 직접적인 metadata 업데이트를 지원하지 않으므로
        # 내부 _collection을 사용하여 업데이트
        updated_metadatas = []
        for i in range(len(existing_docs["ids"])):
            metadata = existing_docs["metadatas"][i].copy()
            metadata["title"] = title
            updated_metadatas.append(metadata)

        # Chroma collection의 update 메서드 사용
        vectorstore._collection.update(
            ids=existing_docs["ids"], metadatas=updated_metadatas
        )
        updated_count = len(existing_docs["ids"])

        logging.info(
            f"✅ 제목 업데이트 완료: {updated_count}개 세그먼트 (source: {source_id}, title: {title})"
        )

        return True, updated_count

    except Exception as e:
        logging.error(f"❌ 제목 업데이트 오류: {e}")
        import traceback
        traceback.print_exc()
        return False, 0
