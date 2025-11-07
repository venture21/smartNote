# TTS 재생 멈춤 문제 디버깅 가이드

## 1단계: 브라우저 개발자 도구 열기

1. **Chrome/Edge**: `F12` 또는 `Ctrl + Shift + I`
2. **Firefox**: `F12` 또는 `Ctrl + Shift + K`
3. **Console 탭**으로 이동

---

## 2단계: TTS 재생 이력 확인

콘솔에서 다음 명령어 실행:

```javascript
showTtsHistory()
```

### 정상 재생 예시:
```
[0] 세그먼트 6: play_start {needsVideoPause: false}
[1] 세그먼트 6: ended {needsVideoPause: false}
[2] 세그먼트 7: play_start {needsVideoPause: true}
[3] 세그먼트 7: ended {needsVideoPause: true}
[4] 세그먼트 7: youtube_resume
[5] 세그먼트 8: play_start {needsVideoPause: false}
```

### 문제 발생 예시:
```
[0] 세그먼트 7: play_start {needsVideoPause: true}
[1] 세그먼트 7: play_error {error: "NotAllowedError"}
```
👆 이 경우 세그먼트 7에서 재생 오류 발생

---

## 3단계: 콘솔 로그 확인

콘솔에서 다음 메시지를 찾으세요:

### 찾아야 할 로그:
- ✅ `[TTS] 재생 시작: 세그먼트 X` - TTS 재생 시작
- ✅ `[TTS] TTS 재생 완료` - TTS 재생 완료
- ✅ `[TTS] YouTube 다시 재생` - YouTube 재생 복구
- ❌ `[TTS] 재생 오류` - 재생 오류
- ❌ `[TTS] 오디오 로드 오류` - 파일 로드 오류

### 에러 메시지 유형:
1. **NotAllowedError**: 브라우저가 자동 재생 차단
2. **NotSupportedError**: 오디오 형식 미지원
3. **AbortError**: 재생 중단됨
4. **NetworkError**: 파일 로드 실패

---

## 4단계: Network 탭 확인

1. 개발자 도구에서 **Network** 탭 클릭
2. 필터를 **Media** 또는 **All**로 설정
3. TTS 파일 로드 상태 확인

### 확인 사항:
- 파일 경로: `tts_audio/[video_id]_[language]_seg[번호]_spk[화자].wav`
- Status: **200 OK**가 정상
- Status: **404 Not Found** - 파일이 없음
- Status: **ERR_FILE_NOT_FOUND** - 경로 오류

---

## 5단계: 현재 상태 확인

콘솔에서 다음 명령어로 현재 상태 확인:

```javascript
// 현재 TTS 세그먼트 확인
console.log('현재 TTS 세그먼트:', currentTtsSegment)

// TTS 활성화 상태 확인
console.log('TTS 활성화:', ttsEnabled)

// YouTube 플레이어 상태 확인 (영상인 경우)
if (youtubePlayer) {
    console.log('YouTube 상태:', youtubePlayer.getPlayerState())
    // -1: 시작되지 않음, 0: 종료, 1: 재생 중, 2: 일시정지, 3: 버퍼링, 5: 동영상 신호
}
```

---

## 6단계: 특정 세그먼트 TTS 파일 확인

콘솔에서 문제 세그먼트의 오디오 객체 확인:

```javascript
// 7번째 세그먼트 TTS 확인 (인덱스는 0부터 시작하므로 6)
const tts7 = ttsAudioElements[6]
if (tts7) {
    console.log('세그먼트 7 TTS:', {
        src: tts7.src,
        duration: tts7.duration,
        paused: tts7.paused,
        ended: tts7.ended,
        error: tts7.error,
        readyState: tts7.readyState,
        needsVideoPause: tts7.needsVideoPause
    })
}
```

### readyState 값:
- 0: HAVE_NOTHING - 데이터 없음
- 1: HAVE_METADATA - 메타데이터만 로드
- 2: HAVE_CURRENT_DATA - 현재 위치 데이터만
- 3: HAVE_FUTURE_DATA - 약간의 버퍼링
- 4: HAVE_ENOUGH_DATA - 충분한 데이터 (재생 가능)

---

## 7단계: 수동으로 YouTube 재생 복구

YouTube가 멈춘 경우 수동으로 재생:

```javascript
// YouTube 재생
if (youtubePlayer) {
    youtubePlayer.playVideo()
    console.log('YouTube 수동 재생')
}
```

---

## 일반적인 문제와 해결책

### 문제 1: 브라우저 자동 재생 차단
**증상**: `NotAllowedError` 발생
**해결**:
- 브라우저 설정에서 자동 재생 허용
- Chrome: `chrome://settings/content/sound`
- 페이지를 먼저 클릭한 후 재생

### 문제 2: TTS 파일이 없음
**증상**: 404 에러 또는 `NetworkError`
**해결**:
- "오디오 생성" 버튼으로 TTS 파일 생성
- 파일 경로 확인

### 문제 3: YouTube가 일시정지된 채로 멈춤
**증상**: TTS는 끝났지만 YouTube가 멈춤
**해결**:
```javascript
// 수동으로 YouTube 재생
youtubePlayer.playVideo()
```

### 문제 4: 특정 세그먼트에서 반복적으로 멈춤
**증상**: 항상 같은 세그먼트에서 멈춤
**확인**:
```javascript
// 해당 세그먼트 TTS 파일 확인
const segment = videoSegments[6] // 7번째 세그먼트
console.log('세그먼트 정보:', segment)
console.log('TTS 파일:', segment.audio_path)
```

---

## 8단계: 디버그 정보 수집 및 보고

문제가 지속되면 다음 정보를 수집하세요:

```javascript
// 종합 디버그 정보
console.log('=== TTS 디버그 정보 ===')
console.log('1. TTS 재생 이력:', showTtsHistory())
console.log('2. 현재 세그먼트:', currentTtsSegment)
console.log('3. TTS 활성화:', ttsEnabled)
console.log('4. YouTube 상태:', youtubePlayer ? youtubePlayer.getPlayerState() : 'N/A')
console.log('5. 전체 세그먼트 수:', videoSegments ? videoSegments.length : audioSegments.length)
console.log('6. TTS 오디오 개수:', Object.keys(ttsAudioElements).length)
```

이 정보를 복사해서 문제를 보고할 때 함께 제공하세요.

---

## 문제 해결이 안 되면

1. **페이지 새로고침**: `F5` 또는 `Ctrl + R`
2. **캐시 삭제 후 새로고침**: `Ctrl + Shift + R`
3. **브라우저 재시작**
4. **다른 브라우저에서 테스트**

---

## 추가 도움말

- TTS 재생 이력 초기화: `clearTtsHistory()`
- 모든 TTS 정지: 페이지 새로고침
