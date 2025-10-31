# VectorStore seg_idx 메타데이터 추가

## 변경 사항

### 1. Backend 수정 (youtube_search_viewer_v0.3.py:273-285)

**store_segments_in_vectordb 함수 업데이트**

```python
# 변경 전
for segment in segments:
    metadata = {
        "source_id": source_id,
        "source_type": source_type,
        "speaker": str(segment['speaker']),
        "start_time": float(segment['start_time']),
        "confidence": float(segment.get('confidence', 0.0)),
        "segment_id": int(segment['id'])
    }

# 변경 후
for seg_idx, segment in enumerate(segments):
    metadata = {
        "source_id": source_id,
        "source_type": source_type,
        "speaker": str(segment['speaker']),
        "start_time": float(segment['start_time']),
        "confidence": float(segment.get('confidence', 0.0)),
        "segment_id": int(segment['id']),
        "seg_idx": int(seg_idx)  # 세그먼트 인덱스 추가
    }
```

### 2. Frontend 수정 (youtube_viewer_v0.3.html:1870-1878)

**Retriever 검색 결과 표시 업데이트**

```javascript
// seg_idx 정보 추가 표시
<span><strong>Seg Index:</strong> ${metadata.seg_idx}</span>
<span><strong>Segment ID:</strong> ${metadata.segment_id}</span>
```

## 메타데이터 구조

이제 VectorStore에 저장되는 각 Document의 metadata는 다음 정보를 포함합니다:

### YouTube 세그먼트
```json
{
  "source_id": "video_id",
  "source_type": "youtube",
  "speaker": "1",
  "start_time": 12.5,
  "confidence": 0.95,
  "segment_id": 0,
  "seg_idx": 0
}
```

### Audio 세그먼트
```json
{
  "source_id": "file_hash",
  "source_type": "audio",
  "speaker": "2",
  "start_time": 45.3,
  "confidence": 0.92,
  "segment_id": 5,
  "seg_idx": 5,
  "filename": "meeting_audio.mp3"
}
```

## 필드 설명

| 필드 | 타입 | 설명 |
|------|------|------|
| `source_id` | string | YouTube video_id 또는 Audio file_hash |
| `source_type` | string | "youtube" 또는 "audio" |
| `speaker` | string | 화자 번호 |
| `start_time` | float | 세그먼트 시작 시간 (초) |
| `confidence` | float | STT 신뢰도 (0.0 ~ 1.0) |
| `segment_id` | int | 세그먼트의 고유 ID |
| **`seg_idx`** | **int** | **세그먼트의 배열 인덱스 (0부터 시작)** ⭐ NEW |
| `filename` | string | 오디오 파일명 (audio만 해당) |

## 활용 방안

### 1. 순서 정렬
seg_idx를 사용하여 검색 결과를 원래 순서대로 정렬:
```python
results.sort(key=lambda x: x['metadata']['seg_idx'])
```

### 2. 이전/다음 세그먼트 찾기
```python
# 현재 seg_idx가 5인 경우
prev_segment = search_by_seg_idx(seg_idx=4)
next_segment = search_by_seg_idx(seg_idx=6)
```

### 3. 범위 검색
```python
# seg_idx 10~20 범위의 세그먼트만 검색
results = vectorstore.similarity_search(
    query=query,
    filter={"seg_idx": {"$gte": 10, "$lte": 20}}
)
```

## 호환성

- ✅ 기존 VectorStore 데이터와 호환됨
- ✅ 새로 추가되는 세그먼트부터 seg_idx 포함
- ✅ 검색 결과 화면에 자동으로 표시됨

## 테스트

새로운 YouTube 영상 또는 오디오 파일 처리 후:
1. Retriever 검색 탭 이동
2. 검색어 입력 및 검색
3. 검색 결과에서 "Seg Index" 필드 확인

