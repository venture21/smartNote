# Retriever 탭 내 플레이어 재생 기능

## 변경 사항 요약

사용자가 Retriever 검색 탭에서 검색 결과를 클릭했을 때, **다른 탭으로 이동하지 않고 현재 탭 내에서 바로 재생**되도록 개선했습니다.

### 1. Retriever 탭에 플레이어 추가
**파일**: `youtube_viewer_v0.3.html:718-743`

**추가된 요소:**
- 🎬 YouTube iframe 플레이어
- 🎵 HTML5 audio 플레이어
- ✕ 닫기 버튼
- 플레이어 타이틀 (동적 변경)

```html
<div id="retrieverPlayerSection" style="display: none;">
    <div class="audio-player-container">
        <div class="audio-header">
            <h2 id="retrieverPlayerTitle">🎵 플레이어</h2>
            <button id="retrieverClosePlayerBtn">✕ 닫기</button>
        </div>
        
        <!-- YouTube 플레이어 -->
        <div id="retrieverYoutubePlayerWrapper" style="display: none;">
            <div id="retrieverYoutubePlayer"></div>
        </div>
        
        <!-- 오디오 플레이어 -->
        <div id="retrieverAudioPlayerWrapper" style="display: none;">
            <audio id="retrieverAudioPlayer" controls></audio>
        </div>
    </div>
</div>
```

### 2. 전역 변수 추가
**파일**: `youtube_viewer_v0.3.html:782-784`

```javascript
let retrieverYoutubePlayer = null;  // Retriever용 YouTube 플레이어
let retrieverAudioPlayer = null;    // Retriever용 Audio 플레이어
```

### 3. 재생 로직 변경
**파일**: `youtube_viewer_v0.3.html:1929-2005`

#### 변경 전: 다른 탭으로 이동
```javascript
// 오디오 탭으로 전환
document.querySelector('[data-tab="audio-tab"]').classList.add('active');

// 영상 탭으로 전환
document.querySelector('[data-tab="video-tab"]').classList.add('active');
```

#### 변경 후: 현재 탭에서 재생
```javascript
// 플레이어 섹션 표시
document.getElementById('retrieverPlayerSection').style.display = 'block';

// Audio인 경우
if (sourceType === 'audio') {
    // 오디오 플레이어만 표시
    document.getElementById('retrieverYoutubePlayerWrapper').style.display = 'none';
    document.getElementById('retrieverAudioPlayerWrapper').style.display = 'block';
    
    // 오디오 파일 로드 및 재생
    retrieverAudioPlayer.src = `/uploads/${filename}`;
    retrieverAudioPlayer.currentTime = startTime;
    retrieverAudioPlayer.play();
}

// YouTube인 경우
else if (sourceType === 'youtube') {
    // YouTube 플레이어만 표시
    document.getElementById('retrieverAudioPlayerWrapper').style.display = 'none';
    document.getElementById('retrieverYoutubePlayerWrapper').style.display = 'block';
    
    // YouTube 플레이어 초기화 또는 비디오 로드
    if (!retrieverYoutubePlayer) {
        retrieverYoutubePlayer = new YT.Player('retrieverYoutubePlayer', {
            videoId: sourceId,
            startSeconds: startTime
        });
    } else {
        retrieverYoutubePlayer.loadVideoById({
            videoId: sourceId,
            startSeconds: startTime
        });
    }
}
```

### 4. 플레이어 닫기 기능
**파일**: `youtube_viewer_v0.3.html:2007-2020`

```javascript
document.getElementById('retrieverClosePlayerBtn').addEventListener('click', () => {
    // 플레이어 섹션 숨김
    document.getElementById('retrieverPlayerSection').style.display = 'none';
    
    // 오디오 정지
    if (retrieverAudioPlayer) {
        retrieverAudioPlayer.pause();
    }
    
    // YouTube 정지
    if (retrieverYoutubePlayer && retrieverYoutubePlayer.pauseVideo) {
        retrieverYoutubePlayer.pauseVideo();
    }
});
```

## 사용 흐름

### 검색 및 재생
1. **🔍 Retriever 검색** 탭에서 검색어 입력
2. 검색 결과 표시
3. 원하는 결과 클릭
4. ✨ **현재 탭에서** 플레이어가 나타나며 자동 재생
5. 플레이어 영역으로 자동 스크롤

### Audio 검색 결과 클릭 시
```
검색 결과 클릭
    ↓
플레이어 섹션 표시
    ↓
🎵 오디오 플레이어 활성화
    ↓
파일 로드: /uploads/{filename}
    ↓
시작 시간 설정: startTime
    ↓
자동 재생 시작
```

### YouTube 검색 결과 클릭 시
```
검색 결과 클릭
    ↓
플레이어 섹션 표시
    ↓
🎬 YouTube 플레이어 활성화
    ↓
비디오 로드: videoId
    ↓
시작 시간 설정: startSeconds
    ↓
자동 재생 시작
```

## 주요 기능

### ✅ 탭 이동 없음
- 검색 결과를 클릭해도 Retriever 탭 유지
- 사용자 컨텍스트 유지

### ✅ 동적 플레이어 전환
- Audio 결과: 오디오 플레이어만 표시
- YouTube 결과: YouTube 플레이어만 표시

### ✅ 파일 자동 로드
- Audio: filename 기반 경로 자동 구성
- YouTube: videoId 기반 자동 로드

### ✅ 정확한 시간 탐색
- `startTime`으로 정확한 위치에서 재생
- YouTube: `startSeconds` 파라미터 사용
- Audio: `currentTime` 속성 사용

### ✅ 플레이어 제어
- 닫기 버튼으로 플레이어 숨김
- 자동으로 재생 중지

## 개선 효과

### 사용자 경험
✅ **원클릭 재생**: 검색 → 클릭 → 재생 (탭 이동 없음)
✅ **컨텍스트 유지**: 검색 결과를 보면서 재생 가능
✅ **빠른 비교**: 여러 결과를 빠르게 들어보고 비교 가능

### 기술적 이점
✅ **독립적인 플레이어**: 다른 탭의 플레이어와 충돌 없음
✅ **효율적인 리소스**: 필요할 때만 플레이어 초기화
✅ **깔끔한 UI**: 사용하지 않을 때는 숨김 처리

## 비교: 이전 vs 현재

| 항목 | 이전 (탭 이동) | 현재 (현재 탭 재생) |
|------|----------------|---------------------|
| 탭 이동 | ✓ 필요 | ✗ 불필요 |
| 검색 결과 유지 | ✗ 사라짐 | ✓ 유지됨 |
| 빠른 비교 | ✗ 어려움 | ✓ 쉬움 |
| 사용 단계 | 3단계 (클릭→이동→확인) | 1단계 (클릭) |
| 플레이어 | 공유 | 독립적 |

