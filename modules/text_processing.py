"""
텍스트 처리 및 청킹 모듈
"""
import re
import json
import logging
from langchain_text_splitters import RecursiveCharacterTextSplitter


def merge_consecutive_speaker_segments(segments):
    """연속적으로 동일한 화자의 세그먼트를 하나의 텍스트로 합칩니다."""
    if not segments:
        return []

    merged_segments = []
    current_segment = segments[0].copy()

    for next_segment in segments[1:]:
        if current_segment["speaker"] == next_segment["speaker"]:
            current_segment["text"] += " " + next_segment["text"]
        else:
            merged_segments.append(current_segment)
            current_segment = next_segment.copy()

    merged_segments.append(current_segment)
    return merged_segments


def get_segment_from_csv(source_id, source_type, segment_id):
    """
    CSV에서 특정 세그먼트를 segment_id로 조회

    Args:
        source_id: YouTube video_id 또는 audio file_hash
        source_type: "youtube" 또는 "audio"
        segment_id: 세그먼트 ID

    Returns:
        segment dict 또는 None
    """
    try:
        # 순환 import 방지를 위해 함수 내에서 import
        from modules.database import load_youtube_history, load_audio_history

        if source_type == "youtube":
            history_df = load_youtube_history()
            row = history_df[history_df["video_id"] == source_id]
        else:  # audio
            history_df = load_audio_history()
            row = history_df[history_df["file_hash"] == source_id]

        if row.empty:
            logging.warning(f"⚠️ CSV에서 source_id={source_id} 찾을 수 없음")
            return None

        # segments_json 파싱
        segments_json_str = row.iloc[0].get("segments_json", "[]")
        segments = json.loads(segments_json_str)

        # segment_id로 검색
        for seg in segments:
            if seg.get("id") == segment_id:
                return seg

        logging.warning(f"⚠️ CSV에서 segment_id={segment_id} 찾을 수 없음")
        return None

    except Exception as e:
        logging.error(f"❌ CSV에서 세그먼트 조회 실패 (source_id={source_id}, segment_id={segment_id}): {e}")
        return None


def create_token_based_chunks(segments, chunk_size=500, chunk_overlap=100):
    """
    토큰 기반 청킹: 화자 분리된 세그먼트를 고정 크기의 chunk로 재구성

    Args:
        segments: 세그먼트 리스트 [{"id": 1, "speaker": "1", "start_time": 0.0, "text": "...", "confidence": 0.95}, ...]
        chunk_size: chunk당 최대 문자 수 (토큰 근사치)
        chunk_overlap: chunk 간 중복 문자 수

    Returns:
        chunks: [{"chunk_id": 0, "text": "...", "segment_ids": [1, 2, 3], "start_time": 0.0, "end_time": 30.5, "speakers": ["1", "2"]}, ...]
    """
    try:
        if not segments:
            logging.warning("⚠️ create_token_based_chunks: 빈 세그먼트 리스트")
            return []

        # 세그먼트를 마커와 함께 텍스트로 결합
        full_text_with_markers = ""
        segment_map = {}  # 마커 위치 → 세그먼트 정보 매핑

        for seg in segments:
            marker = f"[SEG_{seg['id']}]"
            full_text_with_markers += marker + seg["text"] + " "
            segment_map[seg['id']] = seg

        # RecursiveCharacterTextSplitter로 청킹
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", ". ", "。 ", "! ", "? ", ", ", " ", ""],  # 한국어/영어 문장 구분자
            length_function=len,
        )

        chunks_text = splitter.split_text(full_text_with_markers)
        logging.info(f"📦 청킹 완료: {len(chunks_text)}개 chunk 생성 (chunk_size={chunk_size}, overlap={chunk_overlap})")

        # chunk에서 세그먼트 ID 추출 및 메타데이터 구성
        chunks = []

        for chunk_idx, chunk_text in enumerate(chunks_text):
            # [SEG_X] 마커에서 세그먼트 ID 추출
            seg_ids = [int(x) for x in re.findall(r'\[SEG_(\d+)\]', chunk_text)]

            if not seg_ids:
                # 마커가 없는 경우 (드물지만 처리)
                logging.warning(f"⚠️ Chunk {chunk_idx}: 세그먼트 ID 없음")
                continue

            # 마커 제거하여 순수 텍스트 추출
            clean_text = re.sub(r'\[SEG_\d+\]', '', chunk_text).strip()

            # chunk 시작 부분의 불완전한 문장 제거 (첫 번째 chunk 제외)
            if chunk_idx > 0:
                # 문장 끝 패턴 찾기: ". ", "。 ", "! ", "? " 다음부터 시작
                sentence_end_match = re.search(r'[.。!?]\s+', clean_text)
                if sentence_end_match:
                    # 문장 끝 다음부터 시작 (overlap으로 포함된 이전 문장 제거)
                    clean_text = clean_text[sentence_end_match.end():].strip()

            # 세그먼트 정보에서 메타데이터 추출
            cited_segments = [segment_map[sid] for sid in seg_ids if sid in segment_map]

            if not cited_segments:
                logging.warning(f"⚠️ Chunk {chunk_idx}: 유효한 세그먼트 없음")
                continue

            # 시작/종료 시간 계산
            start_time = min(seg["start_time"] for seg in cited_segments)

            # end_time 계산: 마지막 세그먼트의 end_time (없으면 다음 세그먼트의 start_time)
            last_seg = cited_segments[-1]
            last_seg_id = last_seg["id"]

            # 원본 segments에서 last_seg_id 다음 세그먼트 찾기
            last_seg_idx = next((i for i, s in enumerate(segments) if s["id"] == last_seg_id), None)
            if last_seg_idx is not None and last_seg_idx + 1 < len(segments):
                end_time = segments[last_seg_idx + 1]["start_time"]
            else:
                # 마지막 세그먼트인 경우 end_time은 None
                end_time = None

            # 화자 목록 추출 (중복 제거)
            speakers = sorted(list(set(seg["speaker"] for seg in cited_segments)))

            # 평균 신뢰도 계산
            avg_confidence = sum(seg.get("confidence", 0.0) for seg in cited_segments) / len(cited_segments)

            chunks.append({
                "chunk_id": chunk_idx,
                "text": clean_text,
                "segment_ids": seg_ids,  # 인용된 원본 세그먼트 ID 리스트
                "start_time": float(start_time),
                "end_time": float(end_time) if end_time is not None else None,
                "speakers": speakers,  # 복수 화자 가능
                "confidence": float(avg_confidence),
            })

        logging.info(f"✅ 청킹 결과: {len(chunks)}개 chunk, 평균 길이: {sum(len(c['text']) for c in chunks) / len(chunks):.0f}자")
        return chunks

    except Exception as e:
        logging.error(f"❌ create_token_based_chunks 오류: {e}")
        import traceback
        traceback.print_exc()
        return []


def extract_citations(text):
    """
    텍스트에서 [cite: X, Y, Z] 형식의 citation을 추출하여 segment_id 리스트 반환

    Args:
        text: citation이 포함된 텍스트

    Returns:
        list: 추출된 segment_id 리스트 (정수)
    """
    # [cite: 1, 2, 3] 또는 [cite: 1] 형식의 citation 찾기
    citations = re.findall(r'\[cite:\s*(\d+(?:\s*,\s*\d+)*)\]', text)

    segment_ids = []
    for citation in citations:
        # 쉼표로 구분된 segment_id들을 추출
        ids = [int(sid.strip()) for sid in citation.split(',')]
        segment_ids.extend(ids)

    # 중복 제거 및 정렬
    segment_ids = sorted(list(set(segment_ids)))

    return segment_ids


def parse_summary_by_subtopics(summary):
    """
    마크다운 형식의 요약을 소주제별로 파싱하고 citation 정보 추출

    다양한 형식을 지원:
    1. ### 제목 (마크다운 헤딩)
    2. **제목** (볼드)
    3. 빈 줄로 둘러싸인 짧은 텍스트 (일반 텍스트 제목)

    Args:
        summary: 마크다운 형식의 요약 텍스트

    Returns:
        list: [{"title": "소주제 제목", "content": "소주제 내용", "cited_segment_ids": [1, 2, 3]}, ...]
    """
    if not summary or not summary.strip():
        logging.warning("⚠️ 요약 내용이 비어있습니다.")
        return []

    lines = summary.split("\n")
    subtopics = []
    current_title = None
    current_content = []

    logging.info(f"📝 요약 파싱 시작 (총 {len(lines)}줄)")

    for idx, line in enumerate(lines):
        stripped = line.strip()

        # 다양한 헤더 형식 지원
        # 1. **제목** 패턴 (마크다운 볼드)
        bold_match = re.match(r"^\*\*(.+?)\*\*\s*$", stripped)
        # 2. ### 제목 패턴 (마크다운 헤딩 3)
        h3_match = re.match(r"^###[\s]+(.+?)[\s]*$", stripped)
        # 3. ## 제목 패턴 (마크다운 헤딩 2)
        h2_match = re.match(r"^##[\s]+(.+?)[\s]*$", stripped)
        # 4. # 제목 패턴 (마크다운 헤딩 1)
        h1_match = re.match(r"^#[\s]+(.+?)[\s]*$", stripped) if len(subtopics) > 0 else None

        # 5. 일반 텍스트 제목 감지 (휴리스틱)
        is_potential_title = False
        if stripped and len(stripped) < 100 and not stripped.startswith('*') and not stripped.startswith('[cite'):
            # 이전 줄과 다음 줄이 비어있는지 확인
            prev_line_empty = (idx == 0) or (idx > 0 and not lines[idx-1].strip())
            next_line_empty = (idx == len(lines)-1) or (idx < len(lines)-1 and not lines[idx+1].strip())

            # 문장 부호 체크
            ends_with_punct = stripped.endswith(('.', ',', '!', ':', ';')) or '[cite:' in stripped[-20:]

            if prev_line_empty and next_line_empty and not ends_with_punct:
                is_potential_title = True

        # 헤더 매칭 우선순위: h3 > h2 > bold > h1 > 일반 텍스트
        title_match = h3_match or h2_match or bold_match or h1_match

        if title_match or is_potential_title:
            # 이전 소주제 저장
            if current_title is not None:
                content_str = "\n".join(current_content).strip()
                if content_str:  # 내용이 있을 때만 저장
                    # Citation 추출 ([cite: 1, 2, 3] 형식)
                    cited_segment_ids = extract_citations(content_str)

                    subtopics.append(
                        {
                            "title": current_title,
                            "content": content_str,
                            "cited_segment_ids": cited_segment_ids,
                        }
                    )

            # 새 소주제 시작
            if title_match:
                current_title = title_match.group(1).strip()
            else:
                current_title = stripped
            current_content = []

        elif current_title is not None and stripped:
            # 현재 소주제의 내용 추가 (빈 줄이 아닌 경우만)
            current_content.append(line)

    # 마지막 소주제 저장
    if current_title is not None:
        content_str = "\n".join(current_content).strip()
        if content_str:
            cited_segment_ids = extract_citations(content_str)
            subtopics.append({
                "title": current_title,
                "content": content_str,
                "cited_segment_ids": cited_segment_ids,
            })

    logging.info(f"✅ 파싱 완료: {len(subtopics)}개의 소주제 발견")

    return subtopics
