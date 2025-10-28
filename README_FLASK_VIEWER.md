# 🎵 오디오-회의록 동기화 뷰어 (Flask)

오디오 재생 시간에 맞춰 회의록 텍스트를 실시간으로 하이라이트하는 웹 애플리케이션입니다.

**WAV 파일만 업로드하면 자동으로 STT를 수행하여 회의록을 생성합니다!**

## 주요 기능

✨ **주요 특징**
- 🎤 **자동 STT**: WAV 파일 업로드 시 Clova/Gemini STT 자동 실행
- 🎧 오디오 재생 시 자동 텍스트 하이라이트
- 🖱️ 텍스트 클릭 시 해당 시간으로 이동
- 📊 화자별 색상 구분
- ⏱️ 타임스탬프 표시
- 🎯 신뢰도 점수 표시
- 🔄 **STT 서비스 선택**: Clova 또는 Gemini 선택 가능
- 📱 반응형 디자인
- ⌨️ 키보드 단축키 지원

## 파일 구조

```
smartNote/
├── transcript_viewer_flask.py       # Flask 메인 애플리케이션
├── templates/
│   └── index.html                   # HTML 템플릿
├── static/
│   ├── css/
│   │   └── style.css               # 스타일시트
│   └── js/
│       └── audio_sync.js           # 오디오 동기화 JavaScript
└── uploads/                        # 업로드된 파일 저장 폴더 (자동 생성)
```

## 설치 및 실행

### 1. 필요한 패키지 설치

```bash
pip install flask pandas werkzeug
```

### 2. 애플리케이션 실행

```bash
python transcript_viewer_flask.py
```

### 3. 브라우저에서 접속

```
http://localhost:5000
```

## 사용 방법

### Step 1: 오디오 파일 업로드

1. **오디오 파일** 선택 (.wav, .mp3, .m4a, .flac)
2. **STT 서비스 선택**
   - **Clova STT**: 네이버 클로바 (한국어 특화, 빠른 처리)
   - **Gemini STT**: 구글 제미나이 (최신 AI, 컨텍스트 이해)
3. "🎤 음성 인식 시작" 버튼 클릭

### Step 2: 자동 음성 인식

- 선택한 STT 서비스가 자동으로 실행됩니다
- 화자 분리와 타임스탬프가 자동으로 생성됩니다
- 처리 시간: 1~3분 (오디오 길이에 따라 다름)

### Step 3: 오디오 재생 및 하이라이트

- ▶️ 재생 버튼을 클릭하면 자동으로 해당 시간의 텍스트가 하이라이트됩니다
- 💬 텍스트를 클릭하면 해당 시간으로 이동합니다
- 🔄 자동 스크롤을 ON/OFF 할 수 있습니다

## 키보드 단축키

| 키 | 동작 |
|----|------|
| `스페이스바` | 재생/일시정지 |
| `←` | 5초 뒤로 |
| `→` | 5초 앞으로 |

## 기능 상세

### 1. 오디오 동기화

- **실시간 동기화**: `timeupdate` 이벤트로 0.1초마다 업데이트
- **정확한 타이밍**: 현재 시간과 세그먼트 시작 시간을 비교하여 정확한 하이라이트
- **부드러운 전환**: CSS transition으로 자연스러운 애니메이션

### 2. 시각적 피드백

- **현재 세그먼트**: 노란색 배경 + 주황색 좌측 보더
- **지나간 세그먼트**: 투명도 70%
- **미래 세그먼트**: 기본 배경
- **호버 효과**: 마우스 오버 시 배경색 변경

### 3. 화자 구분

각 화자는 고유한 색상으로 구분됩니다:

- 🔵 Speaker 1: 파란색
- 🟢 Speaker 2: 초록색
- 🟡 Speaker 3: 주황색
- 🔴 Speaker 4: 빨간색

### 4. 자동 스크롤

- 현재 재생 중인 세그먼트가 항상 화면 중앙에 위치
- ON/OFF 토글 버튼으로 제어 가능
- `scrollIntoView()` API 사용으로 부드러운 스크롤

## 예시 워크플로우

### 방법 1: 직접 WAV 파일 업로드 (추천)

```bash
# 1. Flask 뷰어 실행
python transcript_viewer_flask.py

# 2. 브라우저에서 http://localhost:5000 접속

# 3. WAV 파일 선택 (예: meeting.wav)

# 4. STT 서비스 선택 (Clova 또는 Gemini)

# 5. "음성 인식 시작" 클릭

# 6. 자동으로 STT 수행 후 결과 표시!
```

### 방법 2: 기존 오디오 파일 사용

```bash
# OpenAI TTS로 생성한 오디오가 있다면
# 1. meeting2.wav 준비

# 2. Flask 뷰어 실행
python transcript_viewer_flask.py

# 3. meeting2.wav 업로드 + STT 서비스 선택
```

## 기술 스택

### Backend
- **Flask**: 웹 프레임워크
- **Pandas**: CSV 데이터 처리
- **Werkzeug**: 파일 업로드 보안

### Frontend
- **HTML5**: 구조
- **CSS3**: 스타일링 (CSS Variables, Flexbox, Animation)
- **Vanilla JavaScript**: 로직 (Web Audio API, DOM 조작)

### 주요 API
- **HTMLAudioElement**: 오디오 재생
- **timeupdate 이벤트**: 시간 동기화
- **scrollIntoView()**: 자동 스크롤
- **Fetch API**: 파일 업로드

## 개발 팁

### 디버깅

브라우저 콘솔에서 다음 정보를 확인할 수 있습니다:

```javascript
// 현재 세그먼트 정보
console.log('Current segment:', segments[currentSegmentIndex]);

// 현재 재생 시간
console.log('Current time:', audioPlayer.currentTime);

// 자동 스크롤 상태
console.log('Auto scroll:', autoScroll);
```

### 커스터마이징

**색상 변경** (`style.css`):
```css
:root {
    --primary-color: #4f46e5;  /* 메인 색상 */
    --highlight-bg: #fef3c7;   /* 하이라이트 배경 */
    --highlight-border: #f59e0b; /* 하이라이트 보더 */
}
```

**시간 업데이트 빈도** (`audio_sync.js`):
```javascript
// timeupdate는 기본적으로 0.1~0.25초마다 발생
// 더 정밀한 제어가 필요하면 requestAnimationFrame 사용
```

## 문제 해결

### Q: 오디오가 재생되지 않습니다
A: 브라우저의 자동 재생 정책 때문일 수 있습니다. 페이지와 상호작용 후 재생해보세요.

### Q: 텍스트 하이라이트가 정확하지 않습니다
A: CSV 파일의 `start_time`이 정확한지 확인하세요. 시간은 초 단위로 입력해야 합니다.

### Q: CSV 파일을 업로드할 수 없습니다
A: CSV 파일이 올바른 형식인지 확인하세요. 최소한 `speaker`, `start_time`, `text` 컬럼이 필요합니다.

### Q: 파일 크기 제한
A: 기본 100MB 제한. `transcript_viewer_flask.py`에서 `MAX_CONTENT_LENGTH` 수정 가능.

## 향후 개발 계획

- [ ] 재생 속도 조절
- [ ] 북마크 기능
- [ ] 세그먼트 편집 기능
- [ ] 다중 오디오 파일 지원
- [ ] 텍스트 검색 기능
- [ ] PDF/Word 내보내기

## 라이선스

MIT License

## 기여

이슈나 풀 리퀘스트는 언제나 환영합니다!

---

**제작**: Claude Code
**버전**: 1.0.0
**최종 업데이트**: 2025-01-23
