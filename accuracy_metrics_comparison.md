# 정확도 측정 지표 비교: avg_text_similarity vs overall_similarity

## 1. avg_text_similarity (평균 텍스트 유사도)

### 계산 방식
- 각 세그먼트를 **개별적으로 1:1 비교**
- 각 세그먼트의 유사도를 계산한 후 **평균**

### 코드
```python
for i in range(min_len):
    original_text = original_df.iloc[i]['transcript']
    recognized_text = recognized_df.iloc[i]['text']
    similarity = SequenceMatcher(None, original_text, recognized_text).ratio() * 100
    text_similarities.append(similarity)

avg_text_similarity = sum(text_similarities) / len(text_similarities)
```

### 특징
- 세그먼트 단위의 정확성 측정
- 각 발언이 얼마나 정확하게 인식되었는지 파악
- 세그먼트 순서가 틀려도 개별 정확도는 높을 수 있음

---

## 2. overall_similarity (전체 텍스트 유사도)

### 계산 방식
- 모든 텍스트를 **하나로 합쳐서** 한 번에 비교
- 전체 회의록을 하나의 긴 문자열로 취급

### 코드
```python
original_full_text = " ".join(original_df['transcript'].tolist())
recognized_full_text = " ".join(recognized_df['text'].tolist())
overall_similarity = SequenceMatcher(None, original_full_text, recognized_full_text).ratio() * 100
```

### 특징
- 전체적인 흐름과 순서 포함
- 세그먼트 경계를 무시하고 전체 내용 비교
- 순서나 구조가 틀리면 점수가 낮아짐

---

## 실제 예시

### 원본
```
세그먼트 1: "안녕하세요 회의를 시작하겠습니다"
세그먼트 2: "오늘 주제는 AI입니다"
```

### 케이스 1: 세그먼트 순서 정확

**인식 결과:**
```
세그먼트 1: "안녕하세요 회의를 시작합니다"    (유사도: 90%)
세그먼트 2: "오늘 주제는 AI예요"           (유사도: 85%)
```

**결과:**
- **avg_text_similarity**: (90 + 85) / 2 = **87.5%**
- **overall_similarity**: 전체 문자열이 거의 일치하므로 **~88%**

### 케이스 2: 세그먼트 순서 뒤바뀜

**인식 결과:**
```
세그먼트 1: "오늘 주제는 AI예요"           (원본의 세그먼트2와 비교 → 낮음)
세그먼트 2: "안녕하세요 회의를 시작합니다"  (원본의 세그먼트1과 비교 → 낮음)
```

**결과:**
- **avg_text_similarity**: **낮음** (1:1 비교 시 순서가 안 맞음)
- **overall_similarity**: 전체 내용은 비슷하므로 **상대적으로 높음**

### 케이스 3: 세그먼트 분할이 다름

**인식 결과:**
```
세그먼트 1: "안녕하세요"
세그먼트 2: "회의를 시작하겠습니다 오늘 주제는"
세그먼트 3: "AI입니다"
```

**결과:**
- **avg_text_similarity**: **낮음** (세그먼트 개수와 내용이 안 맞음)
- **overall_similarity**: **높음** (전체 내용은 거의 일치)

---

## 어떤 지표를 신뢰해야 하나?

| 상황 | 더 중요한 지표 |
|------|----------------|
| 세그먼트(발언) 단위로 정확한 인식이 중요할 때 | **avg_text_similarity** |
| 전체 회의 내용이 빠짐없이 인식되었는지 확인할 때 | **overall_similarity** |
| 화자 구분이 정확한지 확인할 때 | **avg_text_similarity** |
| 회의록 요약용으로 사용할 때 | **overall_similarity** |

---

## 종합 평가 가이드

두 지표를 함께 보는 것이 가장 좋습니다:

| avg_text_similarity | overall_similarity | 해석 |
|--------------------|--------------------|------|
| 높음 | 높음 | ✅ 완벽한 인식 |
| 높음 | 낮음 | ⚠️ 거의 발생하지 않음 (이론적으로 불가능에 가까움) |
| 낮음 | 높음 | ⚠️ 세그먼트 분할이나 순서는 틀렸지만 내용은 정확 |
| 낮음 | 낮음 | ❌ 인식 실패 |

---

## 결론

- **avg_text_similarity**: 세그먼트별 정밀도 측정에 유용
- **overall_similarity**: 전체 내용의 완전성 측정에 유용
- 두 지표를 **함께 고려**하여 음성 인식 품질을 종합적으로 평가하는 것이 권장됨
