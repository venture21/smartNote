"""
SQLite 데이터베이스 관리 모듈

CSV 기반 저장 방식을 SQLite로 전환하여:
- 화자별, 시간별 쿼리 성능 향상
- 관계형 데이터 모델로 정규화
- 트랜잭션 지원으로 데이터 무결성 보장
"""

import sqlite3
import json
import logging
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from contextlib import contextmanager
from config import CSV_FOLDER
import os


# 데이터베이스 파일 경로
DB_PATH = os.path.join(CSV_FOLDER, "smartnote.db")


@contextmanager
def get_db_connection():
    """데이터베이스 연결 컨텍스트 매니저"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # 딕셔너리 형태로 결과 반환
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        logging.error(f"Database error: {e}")
        raise
    finally:
        conn.close()


def init_database():
    """데이터베이스 초기화 및 테이블 생성"""
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # YouTube 메타데이터 테이블
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS youtube_metadata (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            youtube_url TEXT NOT NULL,
            video_id TEXT UNIQUE NOT NULL,
            title TEXT,
            channel TEXT,
            view_count INTEGER,
            upload_date TEXT,
            mp3_path TEXT,
            stt_service TEXT,
            stt_processing_time REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            summary TEXT
        )''')

        # 오디오 메타데이터 테이블
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS audio_metadata (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_hash TEXT UNIQUE NOT NULL,
            filename TEXT NOT NULL,
            file_path TEXT,
            file_size INTEGER,
            audio_duration REAL,
            stt_service TEXT,
            stt_processing_time REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            summary TEXT
        )''')

        # 화자 분리 세그먼트 테이블 (YouTube용)
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS youtube_segments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id TEXT NOT NULL,
            segment_id INTEGER NOT NULL,
            speaker_id INTEGER,
            start_time REAL,
            end_time REAL,
            confidence REAL,
            text TEXT,
            FOREIGN KEY (video_id) REFERENCES youtube_metadata (video_id) ON DELETE CASCADE
        )''')

        # 화자 분리 세그먼트 테이블 (오디오용)
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS audio_segments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_hash TEXT NOT NULL,
            segment_id INTEGER NOT NULL,
            speaker_id INTEGER,
            start_time REAL,
            end_time REAL,
            confidence REAL,
            text TEXT,
            FOREIGN KEY (file_hash) REFERENCES audio_metadata (file_hash) ON DELETE CASCADE
        )''')

        # 인덱스 생성 (쿼리 최적화)
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_youtube_video_id ON youtube_metadata(video_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_audio_file_hash ON audio_metadata(file_hash)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_youtube_seg_video ON youtube_segments(video_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_youtube_seg_speaker ON youtube_segments(speaker_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_youtube_seg_time ON youtube_segments(start_time)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_audio_seg_hash ON audio_segments(file_hash)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_audio_seg_speaker ON audio_segments(speaker_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_audio_seg_time ON audio_segments(start_time)')

        logging.info(f"✅ SQLite 데이터베이스 초기화 완료: {DB_PATH}")


# ==================== YouTube 관련 함수 ====================

def save_youtube_data(
    youtube_url: str,
    video_id: str,
    title: str,
    channel: str,
    view_count: int,
    upload_date: str,
    mp3_path: str,
    segments: List[Dict],
    stt_service: str,
    stt_processing_time: float,
    summary: str = ""
) -> int:
    """YouTube 데이터 저장"""
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # 메타데이터 저장
        cursor.execute('''
        INSERT OR REPLACE INTO youtube_metadata
        (youtube_url, video_id, title, channel, view_count, upload_date,
         mp3_path, stt_service, stt_processing_time, summary, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (youtube_url, video_id, title, channel, view_count, upload_date,
              mp3_path, stt_service, stt_processing_time, summary, datetime.now()))

        # 기존 세그먼트 삭제 (재처리 시)
        cursor.execute('DELETE FROM youtube_segments WHERE video_id = ?', (video_id,))

        # 세그먼트 저장
        for seg in segments:
            # end_time 계산 (없는 경우)
            end_time = seg.get('end_time')
            if end_time is None and 'start_time' in seg:
                # 다음 세그먼트의 start_time 또는 현재 + 추정 시간
                next_idx = segments.index(seg) + 1
                if next_idx < len(segments):
                    end_time = segments[next_idx].get('start_time', seg['start_time'] + 5.0)
                else:
                    end_time = seg['start_time'] + 5.0

            cursor.execute('''
            INSERT INTO youtube_segments
            (video_id, segment_id, speaker_id, start_time, end_time, confidence, text)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (video_id, seg.get('id', seg.get('segment_id', 0)),
                  seg.get('speaker'), seg.get('start_time'), end_time,
                  seg.get('confidence'), seg.get('text')))

        logging.info(f"💾 YouTube 데이터 저장 완료: {video_id} ({len(segments)}개 세그먼트)")
        return cursor.lastrowid


def load_youtube_data(video_id: str = None) -> List[Dict]:
    """YouTube 데이터 로드"""
    with get_db_connection() as conn:
        cursor = conn.cursor()

        if video_id:
            # 특정 영상 조회
            cursor.execute('SELECT * FROM youtube_metadata WHERE video_id = ?', (video_id,))
        else:
            # 전체 조회
            cursor.execute('SELECT * FROM youtube_metadata ORDER BY created_at DESC')

        rows = cursor.fetchall()
        results = []

        for row in rows:
            data = dict(row)
            # 세그먼트 조회
            cursor.execute('''
            SELECT segment_id, speaker_id, start_time, end_time, confidence, text
            FROM youtube_segments
            WHERE video_id = ?
            ORDER BY segment_id
            ''', (data['video_id'],))

            segments = []
            for seg_row in cursor.fetchall():
                segments.append({
                    'id': seg_row['segment_id'],
                    'speaker': seg_row['speaker_id'],
                    'start_time': seg_row['start_time'],
                    'end_time': seg_row['end_time'],
                    'confidence': seg_row['confidence'],
                    'text': seg_row['text']
                })

            data['segments'] = segments
            data['segments_json'] = json.dumps(segments, ensure_ascii=False)  # 하위 호환성
            results.append(data)

        logging.info(f"📋 YouTube 데이터 로드 완료: {len(results)}개 항목")
        return results


def get_youtube_segments_by_speaker(video_id: str, speaker_id: int) -> List[Dict]:
    """특정 화자의 발화만 조회"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
        SELECT segment_id, start_time, end_time, confidence, text
        FROM youtube_segments
        WHERE video_id = ? AND speaker_id = ?
        ORDER BY start_time
        ''', (video_id, speaker_id))

        return [dict(row) for row in cursor.fetchall()]


def get_youtube_segments_by_time_range(video_id: str, start: float, end: float) -> List[Dict]:
    """특정 시간대의 발화 조회"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
        SELECT segment_id, speaker_id, start_time, end_time, confidence, text
        FROM youtube_segments
        WHERE video_id = ? AND start_time BETWEEN ? AND ?
        ORDER BY start_time
        ''', (video_id, start, end))

        return [dict(row) for row in cursor.fetchall()]


# ==================== 오디오 관련 함수 ====================

def save_audio_data(
    file_hash: str,
    filename: str,
    file_path: str,
    file_size: int,
    audio_duration: float,
    segments: List[Dict],
    stt_service: str,
    stt_processing_time: float,
    summary: str = ""
) -> int:
    """오디오 데이터 저장"""
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # 메타데이터 저장
        cursor.execute('''
        INSERT OR REPLACE INTO audio_metadata
        (file_hash, filename, file_path, file_size, audio_duration,
         stt_service, stt_processing_time, summary, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (file_hash, filename, file_path, file_size, audio_duration,
              stt_service, stt_processing_time, summary, datetime.now()))

        # 기존 세그먼트 삭제 (재처리 시)
        cursor.execute('DELETE FROM audio_segments WHERE file_hash = ?', (file_hash,))

        # 세그먼트 저장
        for seg in segments:
            # end_time 계산 (없는 경우)
            end_time = seg.get('end_time')
            if end_time is None and 'start_time' in seg:
                next_idx = segments.index(seg) + 1
                if next_idx < len(segments):
                    end_time = segments[next_idx].get('start_time', seg['start_time'] + 5.0)
                else:
                    end_time = seg['start_time'] + 5.0

            cursor.execute('''
            INSERT INTO audio_segments
            (file_hash, segment_id, speaker_id, start_time, end_time, confidence, text)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (file_hash, seg.get('id', seg.get('segment_id', 0)),
                  seg.get('speaker'), seg.get('start_time'), end_time,
                  seg.get('confidence'), seg.get('text')))

        logging.info(f"💾 오디오 데이터 저장 완료: {file_hash} ({len(segments)}개 세그먼트)")
        return cursor.lastrowid


def load_audio_data(file_hash: str = None) -> List[Dict]:
    """오디오 데이터 로드"""
    with get_db_connection() as conn:
        cursor = conn.cursor()

        if file_hash:
            # 특정 파일 조회
            cursor.execute('SELECT * FROM audio_metadata WHERE file_hash = ?', (file_hash,))
        else:
            # 전체 조회
            cursor.execute('SELECT * FROM audio_metadata ORDER BY created_at DESC')

        rows = cursor.fetchall()
        results = []

        for row in rows:
            data = dict(row)
            # 세그먼트 조회
            cursor.execute('''
            SELECT segment_id, speaker_id, start_time, end_time, confidence, text
            FROM audio_segments
            WHERE file_hash = ?
            ORDER BY segment_id
            ''', (data['file_hash'],))

            segments = []
            for seg_row in cursor.fetchall():
                segments.append({
                    'id': seg_row['segment_id'],
                    'speaker': seg_row['speaker_id'],
                    'start_time': seg_row['start_time'],
                    'end_time': seg_row['end_time'],
                    'confidence': seg_row['confidence'],
                    'text': seg_row['text']
                })

            data['segments'] = segments
            data['segments_json'] = json.dumps(segments, ensure_ascii=False)  # 하위 호환성
            results.append(data)

        logging.info(f"📋 오디오 데이터 로드 완료: {len(results)}개 항목")
        return results


def get_audio_segments_by_speaker(file_hash: str, speaker_id: int) -> List[Dict]:
    """특정 화자의 발화만 조회"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
        SELECT segment_id, start_time, end_time, confidence, text
        FROM audio_segments
        WHERE file_hash = ? AND speaker_id = ?
        ORDER BY start_time
        ''', (file_hash, speaker_id))

        return [dict(row) for row in cursor.fetchall()]


def get_audio_segments_by_time_range(file_hash: str, start: float, end: float) -> List[Dict]:
    """특정 시간대의 발화 조회"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
        SELECT segment_id, speaker_id, start_time, end_time, confidence, text
        FROM audio_segments
        WHERE file_hash = ? AND start_time BETWEEN ? AND ?
        ORDER BY start_time
        ''', (file_hash, start, end))

        return [dict(row) for row in cursor.fetchall()]


# ==================== 공통 유틸리티 함수 ====================

def update_summary(video_id: str = None, file_hash: str = None, summary: str = ""):
    """요약 업데이트"""
    with get_db_connection() as conn:
        cursor = conn.cursor()

        if video_id:
            cursor.execute('UPDATE youtube_metadata SET summary = ? WHERE video_id = ?',
                          (summary, video_id))
            logging.info(f"📝 YouTube 요약 업데이트: {video_id}")
        elif file_hash:
            cursor.execute('UPDATE audio_metadata SET summary = ? WHERE file_hash = ?',
                          (summary, file_hash))
            logging.info(f"📝 오디오 요약 업데이트: {file_hash}")


def check_youtube_exists(video_id: str) -> bool:
    """YouTube 영상 존재 여부 확인"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) as cnt FROM youtube_metadata WHERE video_id = ?', (video_id,))
        return cursor.fetchone()['cnt'] > 0


def check_audio_exists(file_hash: str) -> bool:
    """오디오 파일 존재 여부 확인"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) as cnt FROM audio_metadata WHERE file_hash = ?', (file_hash,))
        return cursor.fetchone()['cnt'] > 0


def get_database_stats() -> Dict:
    """데이터베이스 통계 정보"""
    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute('SELECT COUNT(*) as cnt FROM youtube_metadata')
        youtube_count = cursor.fetchone()['cnt']

        cursor.execute('SELECT COUNT(*) as cnt FROM audio_metadata')
        audio_count = cursor.fetchone()['cnt']

        cursor.execute('SELECT COUNT(*) as cnt FROM youtube_segments')
        youtube_seg_count = cursor.fetchone()['cnt']

        cursor.execute('SELECT COUNT(*) as cnt FROM audio_segments')
        audio_seg_count = cursor.fetchone()['cnt']

        return {
            'youtube_videos': youtube_count,
            'audio_files': audio_count,
            'youtube_segments': youtube_seg_count,
            'audio_segments': audio_seg_count,
            'total_items': youtube_count + audio_count,
            'total_segments': youtube_seg_count + audio_seg_count
        }


def delete_youtube_by_video_id(video_id: str) -> Tuple[bool, Optional[str]]:
    """
    YouTube 영상 삭제 (세그먼트 포함)

    Returns:
        (성공 여부, mp3_path 또는 None)
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            # 삭제 전에 파일 경로 조회
            cursor.execute('SELECT mp3_path FROM youtube_metadata WHERE video_id = ?', (video_id,))
            row = cursor.fetchone()

            if not row:
                logging.warning(f"⚠️ 삭제할 YouTube 영상을 찾을 수 없음: {video_id}")
                return False, None

            mp3_path = row['mp3_path']

            # 외래키로 CASCADE 설정되어 있어 자동으로 세그먼트도 삭제됨
            cursor.execute('DELETE FROM youtube_metadata WHERE video_id = ?', (video_id,))
            deleted = cursor.rowcount

            if deleted > 0:
                logging.info(f"🗑️ YouTube 영상 삭제 완료: {video_id}")
                return True, mp3_path
            else:
                return False, None
    except Exception as e:
        logging.error(f"YouTube 영상 삭제 오류: {e}")
        return False, None


def delete_audio_by_file_hash(file_hash: str) -> Tuple[bool, Optional[str]]:
    """
    오디오 파일 삭제 (세그먼트 포함)

    Returns:
        (성공 여부, file_path 또는 None)
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            # 삭제 전에 파일 경로 조회
            cursor.execute('SELECT file_path FROM audio_metadata WHERE file_hash = ?', (file_hash,))
            row = cursor.fetchone()

            if not row:
                logging.warning(f"⚠️ 삭제할 오디오 파일을 찾을 수 없음: {file_hash}")
                return False, None

            file_path = row['file_path']

            # 외래키로 CASCADE 설정되어 있어 자동으로 세그먼트도 삭제됨
            cursor.execute('DELETE FROM audio_metadata WHERE file_hash = ?', (file_hash,))
            deleted = cursor.rowcount

            if deleted > 0:
                logging.info(f"🗑️ 오디오 파일 삭제 완료: {file_hash}")
                return True, file_path
            else:
                return False, None
    except Exception as e:
        logging.error(f"오디오 파일 삭제 오류: {e}")
        return False, None


def delete_all_youtube() -> int:
    """모든 YouTube 영상 삭제"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            cursor.execute('SELECT COUNT(*) as cnt FROM youtube_metadata')
            count = cursor.fetchone()['cnt']

            cursor.execute('DELETE FROM youtube_metadata')

            logging.info(f"🗑️ 모든 YouTube 영상 삭제 완료: {count}개")
            return count
    except Exception as e:
        logging.error(f"모든 YouTube 영상 삭제 오류: {e}")
        return 0


def delete_all_audio() -> int:
    """모든 오디오 파일 삭제"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            cursor.execute('SELECT COUNT(*) as cnt FROM audio_metadata')
            count = cursor.fetchone()['cnt']

            cursor.execute('DELETE FROM audio_metadata')

            logging.info(f"🗑️ 모든 오디오 파일 삭제 완료: {count}개")
            return count
    except Exception as e:
        logging.error(f"모든 오디오 파일 삭제 오류: {e}")
        return 0


if __name__ == "__main__":
    # 데이터베이스 초기화 테스트
    logging.basicConfig(level=logging.INFO)
    init_database()
    stats = get_database_stats()
    print(f"📊 데이터베이스 통계: {stats}")
