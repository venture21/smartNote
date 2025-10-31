# Retriever 검색 결과 재생 기능 추가

## 변경 사항 요약

### 1. seg_idx 메타데이터 제거
**파일**: `youtube_search_viewer_v0.3.py:273-298`

```python
# 변경 전
for seg_idx, segment in enumerate(segments):
    metadata = {
        ...
        "seg_idx": int(seg_idx)  # 제거됨
    }

# 변경 후
for segment in segments:
    metadata = {
        "source_id": source_id,
        "source_type": source_type,
        "speaker": str(segment['speaker']),
        "start_time": float(segment['start_time']),  # ⭐ 오디오 시작시간 저장
        "confidence": float(segment.get('confidence', 0.0)),
        "segment_id": int(segment['id'])
    }
    if source_type == "audio" and filename:
        metadata["filename"] = filename  # ⭐ 파일명 저장
```

### 2. 검색 결과 화면 개선
**파일**: `youtube_viewer_v0.3.html:1817-1896`

**변경 사항:**
- ❌ seg_idx 표시 제거
- ✅ Start Time 표시 추가
- ✅ "🎧 클릭하여 재생하기" 버튼 추가
- ✅ cursor: pointer 스타일 추가

**표시 정보:**
```
- Source ID: video_id 또는 file_hash
- Segment ID: 세그먼트 고유 ID
- Start Time: 시작 시간 (MM:SS)
- Confidence: 신뢰도 (%)
- 파일명: (오디오인 경우)
```

### 3. 재생 기능 구현
**파일**: `youtube_viewer_v0.3.html:1898-1955`

**함수**: `playFromRetrieverResult(sourceType, sourceId, startTime, filename)`

#### Audio 재생
1. 오디오 탭으로 자동 전환
2. `audioPlayer.currentTime = startTime` 설정
3. 자동 재생 시작
4. 해당 세그먼트로 스크롤

#### YouTube 재생
1. 영상 탭으로 자동 전환
2. `youtubePlayer.seekTo(startTime)` 호출
3. 자동 재생 시작
4. 해당 세그먼트로 스크롤

## 메타데이터 최종 구조

### YouTube
```json
{
  "source_id": "video_id",
  "source_type": "youtube",
  "speaker": "1",
  "start_time": 12.5,
  "confidence": 0.95,
  "segment_id": 0
}
```

### Audio
```json
{
  "source_id": "file_hash",
  "source_type": "audio",
  "speaker": "2",
  "start_time": 45.3,
  "confidence": 0.92,
  "segment_id": 5,
  "filename": "meeting_audio.mp3"
}
```

## 사용 방법

### 1. 검색
1. **🔍 Retriever 검색** 탭 이동
2. 검색어 입력 (예: "예산 논의")
3. 검색 대상 선택 (전체/YouTube/Audio)
4. 검색 실행

### 2. 재생
1. 검색 결과 중 원하는 항목 클릭
2. 자동으로 해당 탭(영상/오디오)으로 이동
3. 해당 시간부터 자동 재생
4. 회의록에서 해당 세그먼트 하이라이트

## 주의사항

### Audio 재생 조건
- 오디오 파일이 이미 업로드되어 있어야 함
- 파일이 없으면 안내 메시지 표시

### YouTube 재생 조건
- YouTube 영상이 이미 로드되어 있어야 함
- 영상이 없으면 안내 메시지 표시

## 기술적 세부사항

### 탭 전환
```javascript
// 모든 탭 비활성화
document.querySelectorAll('.tab-button').forEach(btn => 
    btn.classList.remove('active')
);
document.querySelectorAll('.tab-content').forEach(content => 
    content.classList.remove('active')
);

// 대상 탭 활성화
document.querySelector('[data-tab="audio-tab"]').classList.add('active');
document.getElementById('audio-tab').classList.add('active');
```

### 오디오 재생
```javascript
const audioPlayer = document.getElementById('audioPlayer');
audioPlayer.currentTime = startTime;
audioPlayer.play();
```

### YouTube 재생
```javascript
youtubePlayer.seekTo(startTime, true);
youtubePlayer.playVideo();
```

### 스크롤 이동
```javascript
const targetSegment = document.querySelector(
    `#audioTranscriptContent .transcript-segment[data-time="${startTime}"]`
);
targetSegment.scrollIntoView({ behavior: 'smooth', block: 'center' });
```

## 개선 효과

✅ **사용자 경험 향상**
- 검색 결과를 클릭만으로 즉시 재생
- 탭 이동 자동화
- 해당 구간으로 정확히 이동

✅ **메타데이터 간소화**
- 불필요한 seg_idx 제거
- 필요한 정보만 유지 (start_time, filename)

✅ **통합 검색 경험**
- YouTube와 Audio를 동일한 인터페이스로 검색
- 클릭 한 번으로 원하는 부분 재생

