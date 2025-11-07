"""
데이터베이스 관리 모듈

SQLite 기반 데이터베이스로 전환 (CSV 하위 호환성 유지)
"""
import os
import pandas as pd
import logging
from config import YOUTUBE_HISTORY_CSV, AUDIO_HISTORY_CSV
from modules.sqlite_db import (
    init_database,
    load_youtube_data as sqlite_load_youtube,
    load_audio_data as sqlite_load_audio,
    save_youtube_data as sqlite_save_youtube,
    save_audio_data as sqlite_save_audio,
    check_youtube_exists,
    check_audio_exists
)

# SQLite 데이터베이스 초기화
init_database()


def load_youtube_history():
    """SQLite 데이터베이스에서 YouTube 다운로드 이력을 로드합니다."""
    try:
        # SQLite에서 데이터 로드
        data = sqlite_load_youtube()

        if not data:
            # 빈 DataFrame 반환
            return pd.DataFrame(
                columns=[
                    "youtube_url",
                    "video_id",
                    "title",
                    "channel",
                    "view_count",
                    "upload_date",
                    "mp3_path",
                    "segments_json",
                    "stt_service",
                    "stt_processing_time",
                    "created_at",
                    "summary",
                    "original_language",
                ]
            )

        # DataFrame으로 변환 (하위 호환성)
        df = pd.DataFrame(data)

        # 필수 컬럼 확인 및 추가
        if "summary" not in df.columns:
            df["summary"] = ""
        if "stt_processing_time" not in df.columns:
            df["stt_processing_time"] = 0.0
        if "original_language" not in df.columns:
            df["original_language"] = "unknown"

        # NaN 값 처리
        df["summary"] = df["summary"].fillna("")
        df["stt_processing_time"] = df["stt_processing_time"].fillna(0.0)
        df["view_count"] = df["view_count"].fillna(0)
        df["channel"] = df["channel"].fillna("Unknown")
        df["upload_date"] = df["upload_date"].fillna("")
        df["original_language"] = df["original_language"].fillna("unknown")

        logging.info(f"📋 YouTube 이력 로드 완료: {len(df)}개 항목")
        return df
    except Exception as e:
        logging.error(f"YouTube 이력 로드 오류: {e}")
        return pd.DataFrame(
            columns=[
                "youtube_url",
                "video_id",
                "title",
                "channel",
                "view_count",
                "upload_date",
                "mp3_path",
                "segments_json",
                "stt_service",
                "stt_processing_time",
                "created_at",
                "summary",
                "original_language",
            ]
        )


def save_youtube_history(df):
    """YouTube 이력을 SQLite 데이터베이스에 저장합니다."""
    try:
        import json

        for idx, row in df.iterrows():
            # segments_json 파싱
            segments_json_str = row.get('segments_json', '[]')
            if pd.isna(segments_json_str) or segments_json_str == '':
                segments_json_str = '[]'

            segments = json.loads(segments_json_str) if isinstance(segments_json_str, str) else segments_json_str

            logging.info(f"📝 YouTube 저장 시도 (행 {idx}): video_id={row.get('video_id', 'N/A')}, segments={len(segments)}개")

            # SQLite에 저장
            sqlite_save_youtube(
                youtube_url=row.get('youtube_url', ''),
                video_id=row.get('video_id', ''),
                title=row.get('title', ''),
                channel=row.get('channel', 'Unknown'),
                view_count=int(row.get('view_count', 0)) if not pd.isna(row.get('view_count')) else 0,
                upload_date=row.get('upload_date', ''),
                mp3_path=row.get('mp3_path', ''),
                segments=segments,
                stt_service=row.get('stt_service', 'gemini'),
                stt_processing_time=float(row.get('stt_processing_time', 0.0)) if not pd.isna(row.get('stt_processing_time')) else 0.0,
                detected_language=row.get('original_language', 'unknown'),
                summary=row.get('summary', '')
            )

        logging.info(f"💾 YouTube 이력 저장 완료: {len(df)}개 항목")
    except Exception as e:
        import traceback
        logging.error(f"YouTube 이력 저장 오류: {e}")
        logging.error(f"스택 트레이스:\n{traceback.format_exc()}")


def load_audio_history():
    """SQLite 데이터베이스에서 오디오 파일 처리 이력을 로드합니다."""
    try:
        # SQLite에서 데이터 로드
        data = sqlite_load_audio()

        if not data:
            # 빈 DataFrame 반환
            return pd.DataFrame(
                columns=[
                    "file_hash",
                    "filename",
                    "file_path",
                    "file_size",
                    "audio_duration",
                    "segments_json",
                    "stt_service",
                    "stt_processing_time",
                    "created_at",
                    "summary",
                    "original_language",
                ]
            )

        # DataFrame으로 변환 (하위 호환성)
        df = pd.DataFrame(data)

        # 필수 컬럼 확인 및 추가
        if "summary" not in df.columns:
            df["summary"] = ""
        if "stt_processing_time" not in df.columns:
            df["stt_processing_time"] = 0.0
        if "audio_duration" not in df.columns:
            df["audio_duration"] = 0.0
        if "original_language" not in df.columns:
            df["original_language"] = "unknown"

        # NaN 값 처리
        df["summary"] = df["summary"].fillna("")
        df["stt_processing_time"] = df["stt_processing_time"].fillna(0.0)
        df["audio_duration"] = df["audio_duration"].fillna(0.0)
        df["original_language"] = df["original_language"].fillna("unknown")

        logging.info(f"📋 오디오 이력 로드 완료: {len(df)}개 항목")
        return df
    except Exception as e:
        logging.error(f"오디오 이력 로드 오류: {e}")
        return pd.DataFrame(
            columns=[
                "file_hash",
                "filename",
                "file_path",
                "file_size",
                "audio_duration",
                "segments_json",
                "stt_service",
                "stt_processing_time",
                "created_at",
                "summary",
                "original_language",
            ]
        )


def save_audio_history(df):
    """오디오 이력을 SQLite 데이터베이스에 저장합니다."""
    try:
        import json

        for _, row in df.iterrows():
            # segments_json 파싱
            segments_json_str = row.get('segments_json', '[]')
            if pd.isna(segments_json_str) or segments_json_str == '':
                segments_json_str = '[]'

            segments = json.loads(segments_json_str) if isinstance(segments_json_str, str) else segments_json_str

            # SQLite에 저장
            sqlite_save_audio(
                file_hash=row.get('file_hash', ''),
                filename=row.get('filename', ''),
                file_path=row.get('file_path', ''),
                file_size=int(row.get('file_size', 0)) if not pd.isna(row.get('file_size')) else 0,
                audio_duration=float(row.get('audio_duration', 0.0)) if not pd.isna(row.get('audio_duration')) else 0.0,
                segments=segments,
                stt_service=row.get('stt_service', 'gemini'),
                stt_processing_time=float(row.get('stt_processing_time', 0.0)) if not pd.isna(row.get('stt_processing_time')) else 0.0,
                detected_language=row.get('original_language', 'unknown'),
                summary=row.get('summary', '')
            )

        logging.info(f"💾 오디오 이력 저장 완료: {len(df)}개 항목")
    except Exception as e:
        logging.error(f"오디오 이력 저장 오류: {e}")
