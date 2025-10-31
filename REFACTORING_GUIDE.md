# SmartNote 리팩토링 가이드

## 📦 현재 구조

```
smartNote/
├── youtube_search_viewer.py        (메인, 2617줄)
├── config.py                       (✅ 완료)
├── modules/
│   ├── __init__.py                 (✅ 완료)
│   ├── utils.py                    (✅ 완료)
│   ├── database.py                 (✅ 완료)
│   └── text_processing.py          (✅ 완료)
├── app.py                          (✅ 메인 진입점)
└── templates/
    └── youtube_viewer.html
```

## ✅ 완료된 모듈

### 1. `config.py`
- 설정 상수 (디렉토리, API 키 등)
- 환경 변수 로드
- 폴더 자동 생성

### 2. `modules/utils.py`
- `allowed_file()`: 파일 확장자 검증
- `calculate_file_hash()`: 파일 해시 계산
- `get_audio_duration()`: 오디오 길이 추출
- `update_progress()`: 진행 상황 업데이트
- `parse_mmss_to_seconds()`: 시간 변환

### 3. `modules/database.py`
- `load_youtube_history()`: YouTube 이력 로드
- `save_youtube_history()`: YouTube 이력 저장
- `load_audio_history()`: 오디오 이력 로드
- `save_audio_history()`: 오디오 이력 저장

### 4. `modules/text_processing.py`
- `create_token_based_chunks()`: 토큰 기반 청킹 ⭐
- `merge_consecutive_speaker_segments()`: 화자 병합
- `get_segment_from_csv()`: CSV에서 세그먼트 조회
- `extract_citations()`: Citation 추출
- `parse_summary_by_subtopics()`: 요약 파싱

## 🔄 점진적 마이그레이션 전략

### 단계 1: 현재 상태 (완료)
- 핵심 유틸리티 모듈 분리
- 원본 파일은 그대로 유지
- `app.py`에서 원본 import

### 단계 2: VectorStore 모듈 분리 (다음)
```python
# modules/vectorstore.py
- initialize_collections()
- store_segments_in_vectordb()
- store_summary_in_vectordb()
- search_vectordb()
- get_summary_from_vectordb()
```

### 단계 3: STT 및 YouTube 모듈 분리
```python
# modules/stt.py
- get_gemini_client()
- recognize_with_gemini()

# modules/youtube.py
- download_youtube_audio_as_mp3()
```

### 단계 4: API 라우트 분리
```python
# modules/api_routes.py
- 모든 @app.route 함수들을 Blueprint로 변환
- process_youtube(), process_audio(), summarize_transcript() 등
```

### 단계 5: 완전 마이그레이션
- 원본 파일 제거
- 모든 import 경로 수정
- 테스트 및 검증

## 🚀 현재 실행 방법

### 방법 1: app.py 사용 (권장)
```bash
python app.py
```

### 방법 2: 직접 실행
```bash
python youtube_search_viewer.py
```
*주의: 두 방법 모두 동일하게 작동합니다*

## 📝 다음 단계

1. **VectorStore 모듈 완성**
   - `initialize_collections()` 등 VectorStore 관련 함수 분리
   - LangChain 및 ChromaDB 초기화 로직 캡슐화

2. **API Blueprint 생성**
   - Flask Blueprint를 사용하여 라우트 그룹화
   - `/api/*` 엔드포인트들을 별도 모듈로 분리

3. **테스트 및 검증**
   - 각 모듈 단위 테스트
   - 통합 테스트
   - 성능 비교

## 💡 장점

### 현재 구조의 장점
- ✅ **모듈화**: 함수들이 논리적으로 그룹화됨
- ✅ **재사용성**: 다른 프로젝트에서 모듈 재사용 가능
- ✅ **유지보수**: 특정 기능 수정 시 해당 모듈만 수정
- ✅ **테스트 용이**: 각 모듈 독립적으로 테스트 가능
- ✅ **가독성**: 2617줄 → 여러 작은 파일로 분산

### 점진적 마이그레이션의 장점
- ✅ **안정성**: 원본 파일은 그대로 유지
- ✅ **호환성**: 기존 코드와 100% 호환
- ✅ **유연성**: 필요한 부분만 먼저 마이그레이션

## ⚠️ 주의사항

- 원본 `youtube_search_viewer_v0.3.py` 파일을 삭제하지 마세요
- 새로운 모듈들은 아직 원본 파일의 함수들을 참조합니다
- 완전한 분리를 위해서는 추가 작업이 필요합니다

## 🎯 최종 목표 구조

```
smartNote/
├── app.py                      # Flask 앱 초기화
├── config.py                   # 설정
├── modules/
│   ├── __init__.py
│   ├── utils.py                # 유틸리티
│   ├── database.py             # CSV 관리
│   ├── text_processing.py     # 텍스트 처리
│   ├── vectorstore.py          # VectorStore
│   ├── stt.py                  # STT
│   ├── youtube.py              # YouTube
│   └── api_routes.py           # API 엔드포인트
├── templates/
│   └── youtube_viewer_v0.3.html
└── tests/                      # 유닛 테스트 (추후)
    ├── test_utils.py
    ├── test_database.py
    └── test_text_processing.py
```
