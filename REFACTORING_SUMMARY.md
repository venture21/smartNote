# SmartNote 리팩토링 요약

## 📋 리팩토링 개요

`legacy/youtube_search_viewer.py` 파일의 기능들을 모듈화하여 분리했습니다.

### ✅ 완료된 작업

#### 1. 새로 생성된 모듈들

- **`modules/vectorstore.py`** (새로 생성)
  - VectorStore 초기화: `initialize_collections()`
  - 데이터 저장: `store_segments_in_vectordb()`, `store_summary_in_vectordb()`
  - 데이터 조회: `get_summary_from_vectordb()`, `search_vectordb()`
  - 데이터 삭제: `delete_from_vectorstore()`
  - 제목 업데이트: `update_title_in_vectorstore()`

- **`modules/stt_prediction.py`** (새로 생성)
  - STT 로그 관리: `load_stt_processing_log()`, `save_stt_processing_log()`
  - 처리 기록 추가: `add_stt_processing_record()`
  - 시간 예측: `estimate_stt_processing_time()`
  - 정확도 분석: `analyze_stt_prediction_accuracy()`

#### 2. 업데이트된 파일들

- **`main.py`** (리팩토링)
  - legacy 의존성 최소화
  - `modules.vectorstore`에서 직접 VectorStore 초기화
  - legacy routes를 import하되, 모듈화된 함수 사용
  - 더 명확한 구조와 주석

- **`legacy/youtube_search_viewer.py`** (업데이트)
  - 새로 분리된 modules import 추가:
    ```python
    from modules.vectorstore import (...)
    from modules.stt_prediction import (...)
    ```
  - 기존 함수들은 유지 (하위 호환성)
  - import된 함수들이 우선 사용됨

### 📂 프로젝트 구조

```
smartNote/
├── main.py                          # ✅ 리팩토링됨 (legacy import만 사용)
├── app.py                           # 기존 파일 (변경 없음)
├── config.py                        # 설정 파일
├── modules/
│   ├── __init__.py
│   ├── utils.py                     # 유틸리티 함수들
│   ├── database.py                  # CSV 데이터베이스 관리
│   ├── sqlite_db.py                 # SQLite 데이터베이스 관리
│   ├── text_processing.py          # 텍스트 처리 및 청킹
│   ├── stt.py                       # Gemini STT
│   ├── youtube.py                   # YouTube 다운로드
│   ├── translation.py               # 번역
│   ├── vectorstore.py               # ✅ 새로 생성 (VectorStore 관리)
│   └── stt_prediction.py            # ✅ 새로 생성 (STT 예측)
├── legacy/
│   └── youtube_search_viewer.py     # ✅ 업데이트됨 (새 modules import)
├── templates/
│   └── youtube_viewer.html          # HTML (분할 권장 - 아직 미완료)
└── static/
    ├── css/
    └── js/
```

## 🔍 주요 변경사항

### 1. VectorStore 관련 기능 분리

**이전:**
```python
# legacy/youtube_search_viewer.py 내부에 모든 함수 정의
def initialize_collections():
    # 3400+ 줄의 파일 안에 포함됨
    ...
```

**이후:**
```python
# modules/vectorstore.py - 독립된 모듈
def initialize_collections():
    """LangChain VectorStore 초기화"""
    global embeddings, youtube_vectorstore, audio_vectorstore, summary_vectorstore
    ...

# main.py
from modules.vectorstore import initialize_collections
initialize_collections()
```

### 2. STT 예측 기능 분리

**이전:**
```python
# legacy 파일 내부에 모두 포함
def estimate_stt_processing_time(audio_duration):
    ...
```

**이후:**
```python
# modules/stt_prediction.py
def estimate_stt_processing_time(audio_duration):
    """과거 로그 기반 STT 처리 시간 예측"""
    ...
```

### 3. main.py 리팩토링

**이전:**
```python
# legacy 모듈의 app을 그대로 사용
from legacy import youtube_search_viewer as legacy_module
app = legacy_module.app
```

**이후:**
```python
# 독자적인 Flask app 생성
app = Flask(__name__)

# VectorStore 직접 초기화
from modules.vectorstore import initialize_collections
initialize_collections()

# legacy routes는 import만 (함수는 modules 사용)
from legacy import youtube_search_viewer as legacy_routes
legacy_routes.youtube_vectorstore = youtube_vectorstore  # 업데이트된 것으로 교체
```

## ✅ 테스트 방법

### 1. 기본 동작 테스트

```bash
# 애플리케이션 실행
python main.py
```

**기대 출력:**
```
============================================================
🎬 SmartNote - 영상/오디오 검색 엔진 (리팩토링 버전)
============================================================
URL: http://127.0.0.1:5000
============================================================
모듈 구조:
  ✅ config.py - 설정
  ✅ modules/utils.py - 유틸리티
  ✅ modules/database.py - 데이터베이스 관리
  ✅ modules/sqlite_db.py - SQLite 관리
  ✅ modules/text_processing.py - 텍스트 처리 및 청킹
  ✅ modules/stt.py - Gemini STT
  ✅ modules/stt_prediction.py - STT 처리 시간 예측
  ✅ modules/youtube.py - YouTube 다운로드
  ✅ modules/vectorstore.py - VectorStore 관리
  ✅ modules/translation.py - 번역
============================================================
주의: legacy 폴더는 하위 호환성을 위해 유지됩니다.
      모든 핵심 기능은 modules로 분리되었습니다.
============================================================
INFO:werkzeug: * Running on http://127.0.0.1:5000
✅ OpenAI Embeddings 사용
✅ LangChain VectorStore 초기화 완료
   - YouTube VectorStore 초기화됨
   - Audio VectorStore 초기화됨
   - Summary VectorStore 초기화됨
✅ Routes import 완료
```

### 2. 기능 테스트 체크리스트

브라우저에서 `http://127.0.0.1:5000` 접속 후:

- [ ] **영상 검색 탭**
  - [ ] YouTube URL 입력 및 처리
  - [ ] STT 처리 시간 예측 표시
  - [ ] 회의록 생성
  - [ ] 요약 생성
  - [ ] VectorStore 저장

- [ ] **오디오 검색 탭**
  - [ ] 오디오 파일 업로드
  - [ ] STT 처리
  - [ ] 회의록 생성

- [ ] **Retriever 검색 탭**
  - [ ] VectorStore 검색 (새 모듈 사용)

- [ ] **내용 질문 탭**
  - [ ] RAG 기반 질문 응답

- [ ] **데이터 관리 탭**
  - [ ] 데이터 목록 조회
  - [ ] 데이터 삭제 (VectorStore 포함)

### 3. 모듈별 테스트

#### VectorStore 모듈 테스트
```python
from modules.vectorstore import initialize_collections, search_vectordb

# 초기화
initialize_collections()

# 검색 테스트
results = search_vectordb(
    query="테스트 질문",
    source_type=None,
    n_results=5
)
print(f"검색 결과: {len(results)}개")
```

#### STT 예측 모듈 테스트
```python
from modules.stt_prediction import estimate_stt_processing_time

# 5분(300초) 오디오 예상 시간 계산
estimated = estimate_stt_processing_time(300)
print(f"예상 처리 시간: {estimated:.2f}초")
```

## 🔄 다음 단계 (선택사항)

### 1. legacy 파일 정리 (권장)

현재는 `legacy/youtube_search_viewer.py`에 중복된 함수 정의가 남아있습니다.
다음 명령으로 중복 제거:

```python
# legacy/youtube_search_viewer.py 에서 다음 함수들을 주석 처리하거나 삭제:
# - initialize_collections (라인 ~480)
# - store_segments_in_vectordb (라인 ~501)
# - store_summary_in_vectordb (라인 ~658)
# - get_summary_from_vectordb (라인 ~917)
# - delete_from_vectorstore (라인 ~970)
# - search_vectordb (라인 ~1020)
# - load_stt_processing_log (라인 ~194)
# - save_stt_processing_log (라인 ~208)
# - add_stt_processing_record (라인 ~217)
# - estimate_stt_processing_time (라인 ~248)
# - analyze_stt_prediction_accuracy (라인 ~360)
```

**주의:** 위 작업은 테스트 후에 진행하세요!

### 2. HTML/JavaScript 분할 (대규모 작업)

`templates/youtube_viewer.html` 파일이 2000+ 줄로 매우 큽니다.
다음과 같이 분할 권장:

```
templates/
├── base.html                    # 기본 레이아웃
├── tabs/
│   ├── video_tab.html          # 영상 검색 탭
│   ├── audio_tab.html          # 오디오 검색 탭
│   ├── retriever_tab.html      # Retriever 탭
│   ├── ask_content_tab.html    # 질문 탭
│   └── data_management_tab.html # 데이터 관리 탭
└── components/
    ├── header.html             # 헤더
    └── progress_bar.html       # 진행률 바

static/js/
├── main.js                     # 공통 JavaScript
├── video_tab.js                # 영상 탭 로직
├── audio_tab.js                # 오디오 탭 로직
└── utils.js                    # 유틸리티 함수
```

### 3. Flask Blueprint 사용 (고급)

routes를 Blueprint로 분리하면 더 깔끔합니다:

```python
# modules/routes/video_routes.py
from flask import Blueprint
video_bp = Blueprint('video', __name__)

@video_bp.route('/api/process-youtube', methods=['POST'])
def process_youtube():
    ...

# main.py
from modules.routes.video_routes import video_bp
app.register_blueprint(video_bp)
```

## 📝 롤백 방법

만약 문제가 발생하면:

1. **main.py 이전 버전 사용:**
   ```bash
   git checkout HEAD~1 main.py
   ```

2. **legacy 파일만 사용:**
   ```bash
   python legacy/youtube_search_viewer.py
   ```
   (포트 5002에서 실행됨)

## 🎯 요약

### 장점
- ✅ 코드 모듈화로 유지보수 용이
- ✅ 각 기능별 독립적인 테스트 가능
- ✅ legacy 파일 유지로 하위 호환성 보장
- ✅ 점진적 마이그레이션 가능

### 주의사항
- ⚠️ legacy 파일에 중복 함수가 남아있음 (테스트 후 제거 권장)
- ⚠️ HTML/JS 분할은 아직 미완료 (대규모 작업)
- ⚠️ import 순서 중요 (modules → legacy 순서 유지)

### 다음 작업 권장 순서
1. 기능 테스트 (모든 탭 동작 확인)
2. legacy 파일 정리 (중복 함수 제거)
3. HTML/JS 분할 (선택사항, 큰 작업)
4. Flask Blueprint 적용 (선택사항)

## 🆘 문제 해결

### Import 오류
```
ModuleNotFoundError: No module named 'modules.vectorstore'
```
**해결:** modules 폴더에 `__init__.py` 파일이 있는지 확인

### VectorStore 초기화 오류
```
❌ LangChain VectorStore 초기화 오류
```
**해결:**
- `OPENAI_API_KEY` 환경 변수 확인
- `chroma_db` 폴더 권한 확인

### 중복 함수 실행
**증상:** 같은 함수가 두 번 정의되어 있다는 경고
**해결:** legacy 파일의 중복 함수를 주석 처리

---

**작성일:** 2025-10-31
**버전:** v0.3 (리팩토링 버전)
