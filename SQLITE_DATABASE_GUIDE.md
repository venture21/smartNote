# SQLite 데이터베이스 사용 가이드

## 개요

SmartNote는 이제 CSV 기반 저장 방식에서 **SQLite 데이터베이스**로 전환되었습니다.

### 변경 사항
- ✅ **CSV → SQLite 마이그레이션 완료**
- ✅ **화자 분리 세그먼트 별도 테이블 저장**
- ✅ **고급 쿼리 기능 지원** (화자별, 시간별 검색)
- ✅ **데이터 무결성 보장** (트랜잭션, 외래키)
- ✅ **하위 호환성 유지** (기존 코드 그대로 사용 가능)

---

## 데이터베이스 구조

### 테이블 구조

```
📦 youtube_metadata (YouTube 영상 메타데이터)
├── id (PK)
├── youtube_url
├── video_id (Unique)
├── title
├── channel
├── view_count
├── upload_date
├── mp3_path
├── stt_service
├── stt_processing_time
├── created_at
└── summary

📦 youtube_segments (YouTube 화자 분리 세그먼트)
├── id (PK)
├── video_id (FK → youtube_metadata.video_id)
├── segment_id
├── speaker_id
├── start_time
├── end_time
├── confidence
└── text

📦 audio_metadata (오디오 파일 메타데이터)
├── id (PK)
├── file_hash (Unique)
├── filename
├── file_path
├── file_size
├── audio_duration
├── stt_service
├── stt_processing_time
├── created_at
└── summary

📦 audio_segments (오디오 화자 분리 세그먼트)
├── id (PK)
├── file_hash (FK → audio_metadata.file_hash)
├── segment_id
├── speaker_id
├── start_time
├── end_time
├── confidence
└── text
```

---

## 사용 방법

### 1. 기본 사용 (기존 코드 호환)

기존 `modules/database.py`의 함수들은 그대로 사용 가능합니다:

```python
from modules.database import (
    load_youtube_history,
    save_youtube_history,
    load_audio_history,
    save_audio_history
)

# YouTube 이력 로드 (DataFrame 형태)
youtube_df = load_youtube_history()

# 오디오 이력 로드 (DataFrame 형태)
audio_df = load_audio_history()

# 저장도 동일하게 사용
save_youtube_history(youtube_df)
save_audio_history(audio_df)
```

### 2. 고급 쿼리 (SQLite 직접 사용)

`modules/sqlite_db.py`에서 제공하는 고급 함수들:

```python
from modules.sqlite_db import (
    get_audio_segments_by_speaker,
    get_audio_segments_by_time_range,
    get_youtube_segments_by_speaker,
    get_youtube_segments_by_time_range,
    update_summary,
    check_audio_exists,
    check_youtube_exists
)

# 특정 화자의 발화만 조회
speaker_1_segments = get_audio_segments_by_speaker(
    file_hash="95d4d88b...",
    speaker_id=1
)

# 특정 시간대의 발화 조회
segments = get_audio_segments_by_time_range(
    file_hash="95d4d88b...",
    start=100.0,
    end=200.0
)

# YouTube 영상 존재 여부 확인
if check_youtube_exists(video_id="abc123"):
    print("이미 처리된 영상입니다")

# 요약 업데이트
update_summary(file_hash="95d4d88b...", summary="회의 요약...")
```

### 3. 데이터 저장

```python
from modules.sqlite_db import save_audio_data, save_youtube_data

# 오디오 데이터 저장
save_audio_data(
    file_hash="abc123...",
    filename="meeting.mp3",
    file_path="/path/to/meeting.mp3",
    file_size=1024000,
    audio_duration=567.24,
    segments=[
        {
            "id": 0,
            "speaker": 1,
            "start_time": 0.1,
            "end_time": 5.5,
            "confidence": 0.98,
            "text": "안녕하세요"
        },
        # ...
    ],
    stt_service="gemini",
    stt_processing_time=97.3,
    summary="회의 요약..."
)
```

### 4. 통계 조회

```python
from modules.sqlite_db import get_database_stats

stats = get_database_stats()
print(f"YouTube 영상: {stats['youtube_videos']}개")
print(f"오디오 파일: {stats['audio_files']}개")
print(f"전체 세그먼트: {stats['total_segments']}개")
```

---

## 마이그레이션

### CSV → SQLite 마이그레이션

기존 CSV 데이터를 SQLite로 마이그레이션하려면:

```bash
python migrate_csv_to_sqlite.py
```

마이그레이션 후:
- ✅ 기존 CSV 파일은 `backup/csv/`에 백업됨
- ✅ SQLite DB는 `csv/smartnote.db`에 생성됨

### 수동 마이그레이션

```python
from migrate_csv_to_sqlite import main

main()  # 전체 마이그레이션 실행
```

---

## 장점

### 1. 성능 향상
- ✅ 화자별, 시간별 검색 속도 대폭 향상
- ✅ 인덱스를 통한 빠른 조회
- ✅ 대용량 데이터 처리 최적화

### 2. 고급 쿼리
```python
# 화자 1번이 100초~200초 사이에 말한 내용 찾기
SELECT text FROM audio_segments
WHERE file_hash = ?
  AND speaker_id = 1
  AND start_time BETWEEN 100 AND 200
ORDER BY start_time
```

### 3. 데이터 무결성
- ✅ 외래키 제약으로 데이터 일관성 보장
- ✅ 트랜잭션으로 원자성 보장
- ✅ UNIQUE 제약으로 중복 방지

### 4. 확장성
- ✅ PostgreSQL로 쉽게 마이그레이션 가능
- ✅ 새로운 컬럼 추가 용이
- ✅ 복잡한 관계형 쿼리 지원

---

## 쿼리 예제

### 화자별 발화 시간 통계
```python
import sqlite3

conn = sqlite3.connect('csv/smartnote.db')
cursor = conn.cursor()

cursor.execute('''
SELECT
    speaker_id,
    COUNT(*) as segment_count,
    SUM(end_time - start_time) as total_duration
FROM audio_segments
WHERE file_hash = ?
GROUP BY speaker_id
ORDER BY total_duration DESC
''', (file_hash,))

for row in cursor.fetchall():
    print(f"화자 {row[0]}: {row[1]}개 발화, {row[2]:.1f}초")
```

### 가장 긴 발화 찾기
```python
cursor.execute('''
SELECT speaker_id, text, (end_time - start_time) as duration
FROM audio_segments
WHERE file_hash = ?
ORDER BY duration DESC
LIMIT 5
''', (file_hash,))

for row in cursor.fetchall():
    print(f"화자 {row[0]} ({row[2]:.1f}초): {row[1][:50]}...")
```

### 특정 키워드 검색
```python
cursor.execute('''
SELECT speaker_id, start_time, text
FROM audio_segments
WHERE file_hash = ? AND text LIKE ?
ORDER BY start_time
''', (file_hash, '%경복궁%'))

for row in cursor.fetchall():
    print(f"[{row[1]:.1f}초] 화자 {row[0]}: {row[2]}")
```

---

## 백업 및 복원

### 백업
```bash
# SQLite DB 백업
cp csv/smartnote.db backup/smartnote_backup_$(date +%Y%m%d).db

# 또는 SQLite dump
sqlite3 csv/smartnote.db .dump > backup/smartnote_backup.sql
```

### 복원
```bash
# DB 파일 복원
cp backup/smartnote_backup_20251031.db csv/smartnote.db

# 또는 SQL dump 복원
sqlite3 csv/smartnote.db < backup/smartnote_backup.sql
```

---

## VectorStore 통합 관리

### 데이터 삭제 시 자동으로 처리됨

데이터 삭제 시 **SQLite + VectorStore(ChromaDB)** 모두에서 삭제됩니다:

```python
# API 호출 시 자동으로:
# 1. SQLite에서 메타데이터 + 세그먼트 삭제
# 2. ChromaDB에서 임베딩 벡터 삭제
#    - youtube_transcripts 또는 audio_transcripts 컬렉션
#    - summaries 컬렉션
```

### VectorStore 상태 확인

```bash
python test_vectorstore_deletion.py
```

출력 예시:
```
📊 현재 데이터베이스 상태
📹 YouTube 영상: 0개 (세그먼트: 0개)
🎵 오디오 파일: 1개 (세그먼트: 72개)

🔍 VectorStore 상태 확인
📹 YouTube VectorStore: 0개 문서
🎵 Audio VectorStore: 10개 문서
📝 Summary VectorStore: 5개 문서
```

### 삭제 함수

```python
# legacy/youtube_search_viewer.py에서 사용
def delete_from_vectorstore(source_id, source_type="youtube"):
    """
    VectorStore에서 데이터 삭제

    - 세그먼트 (youtube_transcripts 또는 audio_transcripts)
    - 요약 (summaries)

    Returns: (성공 여부, 삭제된 문서 수)
    """
```

## 문제 해결

### 1. 데이터베이스 잠금 오류
```python
# 연결을 Context Manager로 사용
from modules.sqlite_db import get_db_connection

with get_db_connection() as conn:
    cursor = conn.cursor()
    # 쿼리 실행
    cursor.execute('SELECT * FROM audio_metadata')
    # 자동으로 commit/rollback됨
```

### 2. 데이터 일관성 확인
```python
from modules.sqlite_db import get_database_stats

stats = get_database_stats()
print(stats)  # 예상 값과 비교

# VectorStore 상태 확인
python test_vectorstore_deletion.py
```

### 3. 데이터베이스 리셋
```bash
# 주의: 모든 데이터가 삭제됩니다
rm csv/smartnote.db
rm -rf chroma_db/*  # VectorStore도 함께 삭제
python migrate_csv_to_sqlite.py  # CSV에서 재마이그레이션
```

---

## 다음 단계

### VectorStore 통합
ChromaDB와 SQLite를 함께 사용:
- SQLite: 정확한 메타데이터 쿼리 (화자, 시간, 파일명 등)
- ChromaDB: 시맨틱 검색 (의미 기반 검색)

### PostgreSQL 마이그레이션 (선택)
다중 사용자 환경이나 대용량 데이터 처리 시:
```bash
# PostgreSQL + pgvector로 업그레이드
# modules/postgresql_db.py 작성 예정
```

---

## 참고 자료

- [SQLite 공식 문서](https://www.sqlite.org/docs.html)
- [Python sqlite3 모듈](https://docs.python.org/3/library/sqlite3.html)
- [REFACTORING_GUIDE.md](./REFACTORING_GUIDE.md) - 전체 리팩토링 계획

---

**마이그레이션 완료일**: 2025-10-31
**데이터베이스 위치**: `csv/smartnote.db`
**백업 위치**: `backup/csv/`
