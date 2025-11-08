# STT API 선택 가이드
Google AI Studio와 Vertex AI 중 선택하여 사용

## 개요

이제 STT 처리 시 두 가지 Google Gemini API 중에서 선택할 수 있습니다:
- **Google AI Studio** (기본값, 권장)
- **Vertex AI**

## API 비교

### Google AI Studio
**장점:**
- ✅ 무료 API 키로 간단하게 사용
- ✅ 설정이 간단 (API 키만 필요)
- ✅ 개인 프로젝트 및 개발/테스트에 적합
- ✅ 더 큰 출력 토큰 제한 (250,000 토큰)

**단점:**
- ⚠️ 사용량 제한이 있음
- ⚠️ 프로덕션 환경에는 부적합할 수 있음

**권장 상황:**
- 개인 프로젝트
- 개발 및 테스트
- 소규모 사용
- 빠른 프로토타이핑

### Vertex AI
**장점:**
- ✅ 프로덕션 환경에 적합
- ✅ 더 높은 사용량 제한
- ✅ 기업용 SLA 및 지원
- ✅ GCP 서비스와 통합 가능

**단점:**
- ⚠️ GCP 프로젝트 설정 필요
- ⚠️ 비용 발생 (사용량 기반)
- ⚠️ 더 복잡한 설정
- ⚠️ 출력 토큰 제한이 작음 (65,536 토큰 vs Google AI Studio 250,000)

**권장 상황:**
- 프로덕션 환경
- 대규모 사용
- 기업 프로젝트
- GCP 인프라를 이미 사용 중인 경우

## 설정 방법

### 1. Google AI Studio 설정 (기본값)

#### 1.1 API 키 발급
1. [Google AI Studio](https://aistudio.google.com/app/apikey) 접속
2. "Get API key" 클릭
3. API 키 생성

#### 1.2 환경 변수 설정
`.env` 파일에 추가:
```bash
GOOGLE_API_KEY=your_api_key_here
```

#### 1.3 완료!
- 웹 UI에서 "Google AI Studio" 선택 (기본값)
- 바로 사용 가능

### 2. Vertex AI 설정

#### 2.1 GCP 프로젝트 생성
1. [Google Cloud Console](https://console.cloud.google.com/) 접속
2. 새 프로젝트 생성 또는 기존 프로젝트 선택
3. Vertex AI API 활성화

#### 2.2 인증 설정
**방법 1: Application Default Credentials (권장)**
```bash
gcloud auth application-default login
```

**방법 2: Service Account**
1. Service Account 생성
2. JSON 키 다운로드
3. 환경 변수 설정:
```bash
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/service-account-key.json"
```

#### 2.3 환경 변수 설정
`.env` 파일에 추가:
```bash
VERTEX_AI_PROJECT_ID=your-gcp-project-id
VERTEX_AI_LOCATION=us-central1  # 선택사항, 기본값: us-central1
VERTEX_AI_MAX_TOKENS=65536  # 선택사항, 기본값: 65536
```

#### 2.4 완료!
- 웹 UI에서 "Vertex AI" 선택
- 사용 시작

## 웹 UI에서 사용하기

### 1. 애플리케이션 시작
```bash
python main.py
```

### 2. API 선택
**영상 검색 탭** 또는 **오디오 검색 탭**에서:

1. **STT API 선택** 드롭다운 찾기
2. 원하는 API 선택:
   - **Google AI Studio (권장)** - 기본값
   - **Vertex AI** - 프로덕션용

3. 다른 설정 완료 (청크 시간 등)
4. 처리 시작!

## 코드에서 직접 사용하기

### Python 코드 예제

```python
from modules.stt import recognize_with_gemini_chunked

# Google AI Studio 사용 (기본값)
segments, time, lang = recognize_with_gemini_chunked(
    audio_path="audio.mp3",
    api_type="google_ai_studio"
)

# Vertex AI 사용
segments, time, lang = recognize_with_gemini_chunked(
    audio_path="audio.mp3",
    api_type="vertex_ai"
)
```

## 문제 해결

### Google AI Studio

**문제: "API key not found" 오류**
```
해결: .env 파일에 GOOGLE_API_KEY가 설정되었는지 확인
```

**문제: "Quota exceeded" 오류**
```
해결:
1. AI Studio 콘솔에서 사용량 확인
2. Vertex AI로 전환 고려
3. 나중에 다시 시도
```

### Vertex AI

**문제: "VERTEX_AI_PROJECT_ID 환경 변수가 필요합니다" 오류**
```
해결: .env 파일에 VERTEX_AI_PROJECT_ID 추가
VERTEX_AI_PROJECT_ID=your-project-id
```

**문제: start_time이 정확하지 않음 (타임스탬프 싱크 문제)** ⚠️ 중요!
```
원인 1: 잘못된 모델 사용
- gemini-2.0-flash-exp는 타임스탬프 정확도가 매우 낮음
- 오래된 모델(gemini-1.5) 사용 시 최신 모델보다 정확도 낮음

원인 2: 출력 토큰 제한이 너무 낮음
- VERTEX_AI_MAX_TOKENS를 65536으로 설정하지 않은 경우
- Google AI Studio: 250,000 토큰
- Vertex AI: 65,536 토큰 (약 4배 차이)

원인 3: Vertex AI 프롬프트 최적화 부족 (해결됨 ✅)
- 최신 버전에서는 Vertex AI 전용 프롬프트 사용
- 타임스탬프 정확도를 극대화하는 지침 추가
- 추정 금지, 검증 요구사항 강화

해결 방법 1: 최신 모델 + 최대 토큰 설정 (권장) ✅
.env 파일에 추가:
VERTEX_AI_MODEL=gemini-2.5-pro
VERTEX_AI_MAX_TOKENS=65536

주의: gemini-2.5-pro가 리전에서 사용 불가 시 자동으로 gemini-2.5-flash로 fallback

해결 방법 2: 청크 분할 사용 (매우 긴 오디오)
웹 UI에서 청크 시간 설정:
- 매우 긴 오디오(1시간+): 20분 또는 30분 청크
- 중간 길이(30~50분): 30분 청크로 충분

해결 방법 3: Google AI Studio 사용 (가장 안정적)
웹 UI에서 "Google AI Studio"로 변경
- gemini-2.5-pro 항상 사용 가능
- 250,000 토큰 출력 가능
- 가장 안정적이고 예측 가능

모델 비교 (타임스탬프 정확도):
- Google AI Studio: gemini-2.5-pro ✅✅ (최고, 항상 사용 가능)
- Vertex AI: gemini-2.5-pro ✅✅ (최고, 리전에 따라 제한)
- Vertex AI: gemini-2.5-flash ✅✅ (최고, 빠름, 최신)
- Vertex AI: gemini-1.5-pro ✅ (높은 정확도)
- Vertex AI: gemini-1.5-flash-002 ⚠️ (보통 정확도)
- Vertex AI: gemini-2.0-flash-exp ❌ (낮은 정확도 - 사용 금지)
```

**문제: "Authentication failed" 오류**
```
해결:
1. gcloud auth application-default login 실행
2. 또는 GOOGLE_APPLICATION_CREDENTIALS 설정 확인
3. Service Account에 Vertex AI User 권한 있는지 확인
```

**문제: "Permission denied" 오류**
```
해결:
1. GCP 프로젝트에서 Vertex AI API 활성화 확인
2. IAM에서 필요한 권한 확인:
   - Vertex AI User
   - Service Account User (Service Account 사용 시)
```

**문제: "Region not available" 오류**
```
해결:
1. .env의 VERTEX_AI_LOCATION 확인
2. 지원되는 리전 사용:
   - us-central1 (권장)
   - us-east1
   - europe-west1
   - asia-northeast1
```

## 비용 비교

### Google AI Studio
- **무료**: 매우 관대한 무료 할당량
- **제한**: 분당 요청 수 제한 있음

### Vertex AI
- **종량제**: 사용한 만큼 지불
- **가격**: 입력/출력 토큰 수에 따라 결정
- **예상 비용**:
  - 1시간 오디오: 약 $0.50 - $2.00 (모델 및 설정에 따라 다름)
  - 자세한 가격: [Vertex AI Pricing](https://cloud.google.com/vertex-ai/pricing)

## 성능 비교

| 특성 | Google AI Studio | Vertex AI |
|-----|-----------------|-----------|
| 응답 속도 | 빠름 | 빠름 |
| 신뢰성 | 높음 | 매우 높음 |
| 출력 제한 | 250K 토큰 | 8K 토큰 |
| 사용량 제한 | 중간 | 높음 |
| 설정 복잡도 | 낮음 | 높음 |

## 모델 정보

### Google AI Studio
- **모델**: gemini-2.5-pro (고정)
- **특징**:
  - 최신 Gemini 모델
  - 매우 긴 출력 지원 (250K 토큰)
  - 오디오 입력 직접 지원
  - **타임스탬프 정확도: 매우 높음** ✅

### Vertex AI
- **기본 모델**: gemini-2.5-pro (Google AI Studio와 동일)
- **설정 가능**: `VERTEX_AI_MODEL` 환경 변수로 변경 가능
- **⚠️ 중요**: gemini-2.5-pro는 일부 리전에서 사용 불가할 수 있음 (자동 fallback)
- **사용 가능한 모델**:

  | 모델 | 속도 | 정확도 | 타임스탬프 | 출력 토큰 | 권장 용도 |
  |-----|------|--------|-----------|----------|----------|
  | **gemini-2.5-pro** | 보통 | 최고 | ✅✅ 최고 | 65K | **최고 정확도** |
  | **gemini-2.5-flash** | 빠름 | 최고 | ✅✅ 최고 | 65K | **빠르고 정확** |
  | gemini-1.5-pro | 보통 | 매우 높음 | ✅ 정확 | 65K | 안정적 |
  | gemini-1.5-flash-002 | 빠름 | 높음 | ⚠️ 보통 | 65K | 빠른 처리 |
  | gemini-2.0-flash-exp | 매우 빠름 | 보통 | ❌ 부정확 | 65K | 사용 금지 |

- **오디오 입력 직접 지원**

**주요 제약사항:**
- **출력 토큰 제한**: 최대 65,536 (권장)
  - Vertex AI: 65,536 토큰 (실제 최대)
  - Google AI Studio: 250,000 토큰 (약 4배 차이)
  - ⚠️ 65,537 이상 설정 시 오류 발생
  - 공식 문서 8,192는 보수적 값, 65,536 사용 권장
- **긴 오디오 처리**: 매우 긴 오디오(1시간+)는 청크 분할 권장
  - 65,536 토큰으로 최대 30~40분 처리 가능
  - 더 긴 오디오: 20~30분 청크 사용

## 권장 사항

### 개인 사용자
- **추천**: Google AI Studio
- **이유**: 무료, 간단한 설정, 충분한 성능

### 개발자 (개발/테스트)
- **추천**: Google AI Studio
- **이유**: 빠른 반복 개발, 비용 절감

### 기업 사용자
- **추천**: Vertex AI
- **이유**: 프로덕션 SLA, 높은 사용량 제한, 기업 지원

### 대량 처리
- **추천**: Vertex AI
- **이유**: 높은 사용량 제한, 더 나은 확장성

## 환경 변수 요약

### 필수 설정

**Google AI Studio 사용 시:**
```bash
GOOGLE_API_KEY=your_api_key_here
```

**Vertex AI 사용 시:**
```bash
VERTEX_AI_PROJECT_ID=your-gcp-project-id
VERTEX_AI_LOCATION=us-central1  # 선택사항
```

### 추가 설정
```bash
# STT 기본 설정
DEFAULT_STT_API=google_ai_studio  # 또는 vertex_ai
DEFAULT_CHUNK_DURATION=30
CHUNK_OVERLAP_SECONDS=25
```

## 자주 묻는 질문 (FAQ)

**Q: 어느 API가 더 정확한가요?**
A: **이제 거의 동일합니다!**
- Google AI Studio: gemini-2.5-pro (항상 사용 가능)
- Vertex AI: gemini-2.5-pro → gemini-2.5-flash (자동 fallback)
- Gemini 2.5 모델 사용 시 타임스탬프 정확도 거의 동일
- Google AI Studio가 더 안정적 (항상 사용 가능 + 더 많은 토큰)

**Q: Vertex AI의 타임스탬프가 왜 부정확한가요?**
A: 여러 원인이 있습니다:
1. **모델 설정**: gemini-2.5 모델 대신 오래된 모델 사용
2. **출력 토큰 제한**: VERTEX_AI_MAX_TOKENS를 65536으로 설정하지 않음
3. **리전 제한**: gemini-2.5-pro가 해당 리전에서 사용 불가
→ 해결책:
  - .env에 VERTEX_AI_MODEL=gemini-2.5-pro 설정
  - .env에 VERTEX_AI_MAX_TOKENS=65536 설정
  - gemini-2.5-pro 사용 불가 시 자동으로 gemini-2.5-flash 사용
  - 매우 긴 오디오(1시간+)는 청크 분할 사용

**Q: gemini-2.5-pro가 Vertex AI에서 작동하나요?**
A: **리전에 따라 다릅니다.**
- 일부 리전(예: us-central1)에서는 사용 가능
- 사용 불가 리전에서는 자동으로 gemini-2.5-flash로 fallback
- gemini-2.5-flash도 최신 Gemini 2.5 모델로 매우 높은 정확도 제공
- 로그를 확인하여 어떤 모델이 실제 사용되는지 확인 가능

**Q: 프로젝트 중간에 API를 변경할 수 있나요?**
A: 네, 언제든지 웹 UI에서 선택하여 변경 가능합니다.

**Q: 두 API를 동시에 설정해야 하나요?**
A: 아니요, 사용하려는 API만 설정하면 됩니다.

**Q: Vertex AI 비용이 얼마나 나오나요?**
A: 사용량에 따라 다릅니다. GCP 콘솔에서 비용 예측 도구를 사용해보세요.

**Q: Google AI Studio 할당량이 초과되면 어떻게 하나요?**
A: Vertex AI로 전환하거나 다음 날까지 기다리면 됩니다.

## 프롬프트 최적화

### API별 프롬프트 분리

최신 버전에서는 각 API에 최적화된 프롬프트를 사용합니다:

#### Google AI Studio 프롬프트
- 표준 타임스탬프 정확도 지침
- 균형잡힌 성능과 정확도
- 250K 토큰 출력 활용

#### Vertex AI 전용 프롬프트 ✅ (대폭 강화됨!)
**30~50초 타임스탬프 오차 문제 해결을 위한 특별 최적화:**

1. **역할 변경 및 문제 명시**:
   - 역할: "타임스탬프 분석가" (회의록 작성자 → 변경)
   - ⚠️⚠️⚠️ 30~50초 오차 문제 직접 언급
   - "절대 용납될 수 없음" 명시로 경각심 극대화

2. **명확한 우선순위**:
   - ⭐⭐⭐⭐⭐ start_time (최우선! 절대적!)
   - ⭐⭐⭐ 텍스트 정확도
   - ⭐⭐ confidence 정확도
   - ⭐ speaker 구분 (대략적으로만) ← 화자 분리 우선순위 하향

3. **7단계 구조화된 타임스탬프 요구사항**:
   - a) 오디오 파일 내장 타임스탬프 활용
   - b) 형식 (시:분:초.백분의1초)
   - c) 정확도 검증 방법 (구체적 예시)
   - d) 절대 금지사항 (구체적 예시)
   - e) 필수 수행사항
   - f) 자가 검증
   - g) 오류 예시와 해결

4. **구체적 금지사항 (예시 포함)**:
   - ❌ 이전 시간 + 30초 추정 방식
   - ❌ "대략 이 정도" 추측
   - ❌ 평균 발화 시간 가정
   - ❌ 텍스트 길이 기반 계산

5. **5단계 최종 점검 체크리스트**:
   - ✅ 실제 재생 시간과 일치?
   - ✅ 시간 순서대로 증가?
   - ✅ 첫/마지막 합리적?
   - ✅ 균일한 증가 패턴 아님? (계산 방지)
   - ✅ 30초 이상 차이 재확인?

6. **3회 반복 강조**:
   - 시작부, 중간부, 마지막에 30초 오차 경고

### 프롬프트 선택 방법

프롬프트는 자동으로 API 타입에 따라 선택됩니다:

```python
# modules/stt.py의 get_stt_prompt() 함수
if api_type == "vertex_ai":
    # Vertex AI 전용 프롬프트 (타임스탬프 정확도 극대화)
    return vertex_ai_optimized_prompt
else:
    # Google AI Studio 프롬프트 (기본)
    return standard_prompt
```

로그에서 확인:
```
📝 Vertex AI 전용 프롬프트 사용 (타임스탬프 정확도 강화)
```

## 관련 파일

- `config.py`: API 설정
- `modules/stt.py`: STT 구현 코드 (get_stt_prompt 함수 포함)
- `templates/youtube_viewer.html`: 웹 UI
- `static/js/app.js`: JavaScript 로직
- `legacy/youtube_search_viewer.py`: 백엔드 라우트

## 추가 지원

문제가 있으면:
1. 로그 확인 (터미널 출력)
2. 환경 변수 재확인
3. API 키/인증 재설정
4. 이 가이드의 문제 해결 섹션 참조

---

**마지막 업데이트**: 2025-01-08
