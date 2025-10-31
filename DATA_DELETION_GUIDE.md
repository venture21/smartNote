# 데이터 완전 삭제 가이드

## 개요

SmartNote의 데이터 관리 기능은 **완전 삭제**를 지원합니다.

데이터 삭제 시 다음 항목들이 모두 제거됩니다:
- ✅ SQLite 데이터베이스 (메타데이터 + 세그먼트)
- ✅ VectorStore (세그먼트 임베딩 + 요약 임베딩)
- ✅ 실제 파일 (uploads 또는 mp3 폴더의 원본 파일)

---

## 🗂️ 삭제 범위

### 1. **SQLite 데이터베이스**

#### YouTube 영상
- `youtube_metadata` 테이블에서 메타데이터 삭제
- `youtube_segments` 테이블에서 모든 세그먼트 자동 삭제 (CASCADE)

#### 오디오 파일
- `audio_metadata` 테이블에서 메타데이터 삭제
- `audio_segments` 테이블에서 모든 세그먼트 자동 삭제 (CASCADE)

### 2. **VectorStore (ChromaDB)**

#### 세그먼트 임베딩
- YouTube: `youtube_transcripts` 컬렉션에서 해당 video_id의 모든 문서 삭제
- Audio: `audio_transcripts` 컬렉션에서 해당 file_hash의 모든 문서 삭제

#### 요약 임베딩
- `summaries` 컬렉션에서 해당 source_id의 요약 문서 삭제

### 3. **실제 파일**

#### YouTube 영상
- `mp3/` 폴더에서 변환된 MP3 파일 삭제
- 예: `mp3/{video_id}.mp3`

#### 오디오 파일
- `uploads/` 폴더에서 원본 오디오 파일 삭제
- 예: `uploads/meeting.mp3`

---

## 🚀 사용 방법

### 1. 웹 UI에서 삭제

1. `http://localhost:5002` 접속
2. **🗂️ 데이터 관리** 탭 클릭
3. 삭제할 항목 찾기
4. **🗑️ 삭제** 버튼 클릭
5. 확인 다이얼로그에서 **확인** 클릭

### 2. API로 직접 삭제

#### 오디오 파일 삭제
```bash
curl -X POST http://localhost:5002/api/data-management/delete \
     -H 'Content-Type: application/json' \
     -d '{"type": "audio", "id": "<file_hash>"}'
```

#### YouTube 영상 삭제
```bash
curl -X POST http://localhost:5002/api/data-management/delete \
     -H 'Content-Type: application/json' \
     -d '{"type": "youtube", "id": "<video_id>"}'
```

---

## 📊 삭제 전후 확인

### 삭제 전 상태 확인
```bash
python test_complete_deletion.py
```

출력 예시:
```
🔍 삭제 전 상태 확인
============================================================

📊 데이터베이스:
   - 오디오 파일: 1개
   - 오디오 세그먼트: 72개

📁 오디오 파일:
   파일명: meeting.mp3
   Hash: 95d4d88b7a28e859...
   경로: uploads/meeting.mp3
   실제 파일: ✅ 존재
   세그먼트: 72개

🔍 VectorStore:
   - Audio 세그먼트: 10개
   - Summary: 5개
   - 전체: 15개
```

### 삭제 후 상태 확인
```bash
python test_complete_deletion.py after
```

출력 예시:
```
🔍 삭제 후 상태 확인
============================================================

📊 데이터베이스:
   - 오디오 파일: 0개
   - 오디오 세그먼트: 0개

✅ 모든 오디오 파일 삭제됨

📂 uploads 폴더:
   ✅ 모든 오디오 파일 삭제됨

🔍 VectorStore:
   - Audio 세그먼트: 0개
   - Summary: 0개
   ✅ 모든 VectorStore 데이터 삭제됨
```

---

## 📝 삭제 로그 예시

```
🗑️ 오디오 파일 삭제 완료: 95d4d88b7a28e859fff5783f80fb88d1
🗑️ audio VectorStore에서 10개 세그먼트 삭제
🗑️ Summary VectorStore에서 5개 요약 삭제
✅ VectorStore 삭제 완료: 총 15개 문서 삭제됨
🗑️ 실제 파일 삭제 완료: uploads/meeting.mp3
```

---

## 🔒 안전 기능

### 1. **확인 다이얼로그**
웹 UI에서 삭제 버튼 클릭 시 확인 메시지 표시:
```
정말로 이 오디오 파일을(를) 삭제하시겠습니까?

삭제된 데이터는 복구할 수 없습니다.
```

### 2. **단계별 삭제**
삭제는 다음 순서로 진행됩니다:
1. SQLite 데이터베이스 삭제
   - 실패 시: 삭제 중단, 오류 반환
2. VectorStore 삭제
   - 실패 시: 경고 로그, 계속 진행
3. 실제 파일 삭제
   - 실패 시: 경고 로그, 계속 진행

이렇게 하면 최소한 데이터베이스에서는 삭제가 보장됩니다.

### 3. **경로 정규화**
Windows 경로(`\`) → Unix 경로(`/`) 자동 변환:
- WSL 환경 호환
- 크로스 플랫폼 지원

### 4. **트랜잭션 보장**
SQLite는 트랜잭션으로 보호되어 원자성 보장:
- 삭제 중 오류 발생 시 롤백
- 데이터 무결성 유지

### 5. **CASCADE 삭제**
외래키 CASCADE 설정으로 세그먼트 자동 삭제:
- 메타데이터 삭제 시 관련 세그먼트도 함께 삭제
- 고아 데이터 방지

---

## ⚠️ 주의사항

### 1. **복구 불가능**
삭제된 데이터는 복구할 수 없습니다. 삭제 전 반드시 백업하세요:
```bash
# 데이터베이스 백업
cp csv/smartnote.db backup/smartnote_$(date +%Y%m%d).db

# 파일 백업
cp -r uploads backup/uploads_$(date +%Y%m%d)
cp -r mp3 backup/mp3_$(date +%Y%m%d)
```

### 2. **VectorStore 삭제 실패**
VectorStore 삭제가 실패해도 DB와 파일은 삭제됩니다:
- 수동으로 ChromaDB를 정리해야 할 수 있음
- 로그를 확인하여 오류 원인 파악

### 3. **파일 권한 오류**
파일 삭제 시 권한 문제 발생 가능:
- 로그에서 오류 확인
- 수동으로 파일 삭제 필요

---

## 🛠️ 문제 해결

### VectorStore만 정리하기
```python
from legacy.youtube_search_viewer import delete_from_vectorstore

# 특정 항목 삭제
delete_from_vectorstore("95d4d88b...", "audio")
```

### 파일만 수동 삭제
```bash
# 오디오 파일
rm uploads/meeting.mp3

# YouTube MP3
rm mp3/{video_id}.mp3
```

### 데이터 일관성 확인
```bash
python test_complete_deletion.py
```

---

## 📌 관련 파일

- **SQLite 삭제**: `modules/sqlite_db.py` (429-496줄)
- **VectorStore 삭제**: `legacy/youtube_search_viewer.py` (857-904줄)
- **API 엔드포인트**: `legacy/youtube_search_viewer.py` (2910-2975줄)
- **테스트 스크립트**: `test_complete_deletion.py`

---

**업데이트 날짜**: 2025-10-31
