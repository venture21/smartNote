"""
STT 처리 시간 예측 기능

과거 STT 처리 이력을 기반으로 처리 시간을 예측합니다.
"""

import json
import logging
import os
from datetime import datetime

import config


# =============================================================================
# STT 처리 로그 관리
# =============================================================================
def load_stt_processing_log():
    """STT 처리 시간 로그를 로드합니다."""
    if os.path.exists(config.STT_PROCESSING_LOG):
        try:
            with open(config.STT_PROCESSING_LOG, "r", encoding="utf-8") as f:
                logs = json.load(f)
            return logs
        except Exception as e:
            logging.error(f"STT 로그 로드 오류: {e}")
            return []
    else:
        return []


def save_stt_processing_log(logs):
    """STT 처리 시간 로그를 저장합니다."""
    try:
        with open(config.STT_PROCESSING_LOG, "w", encoding="utf-8") as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error(f"STT 로그 저장 오류: {e}")


def add_stt_processing_record(audio_duration, processing_time, source_type="audio"):
    """
    STT 처리 기록을 로그에 추가합니다.

    Args:
        audio_duration: 오디오 길이 (초)
        processing_time: 실제 처리 시간 (초)
        source_type: 소스 타입 ("audio" 또는 "youtube")
    """
    import traceback
    import inspect

    # 검증 1: processing_time이 비정상적으로 큰 경우 (Unix timestamp 오류 등)
    if processing_time > 10000:
        # 호출 스택 정보 출력
        caller_frame = inspect.currentframe().f_back
        caller_info = inspect.getframeinfo(caller_frame)

        logging.error(
            f"❌ STT 처리 시간({processing_time:.2f}초)이 비정상적으로 큽니다. "
            f"Unix timestamp를 잘못 전달했을 가능성이 있습니다. "
            f"(오디오: {audio_duration:.2f}초, 타입: {source_type})"
        )
        logging.error(
            f"   호출 위치: {caller_info.filename}:{caller_info.lineno} in {caller_info.function}"
        )
        logging.error("   호출 스택:")
        for line in traceback.format_stack()[:-1]:
            logging.error(f"   {line.strip()}")
        return

    # 검증 2: processing_time이 1000초를 넘으면 로그에 저장하지 않음
    if processing_time > 1000:
        logging.warning(
            f"⚠️ STT 처리 시간({processing_time:.2f}초)이 1000초를 초과하여 로그에 저장하지 않습니다. "
            f"(오디오: {audio_duration:.2f}초, 타입: {source_type})"
        )
        return

    # 검증 3: processing_time이 audio_duration의 10배를 초과하는 경우
    if audio_duration > 0 and processing_time > audio_duration * 10:
        logging.warning(
            f"⚠️ STT 처리 시간({processing_time:.2f}초)이 오디오 길이({audio_duration:.2f}초)의 10배를 초과하여 로그에 저장하지 않습니다. "
            f"(비율: {processing_time/audio_duration:.2f}x, 타입: {source_type})"
        )
        return

    logs = load_stt_processing_log()

    # 처리 비율 계산
    ratio = processing_time / audio_duration if audio_duration > 0 else 0

    # 새 기록 추가 (더 많은 메타데이터)
    logs.append(
        {
            "audio_duration": float(audio_duration),
            "processing_time": float(processing_time),
            "ratio": float(ratio),
            "source_type": source_type,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    )

    # 최근 200개만 유지 (더 많은 데이터로 정확도 향상)
    if len(logs) > 200:
        logs = logs[-200:]

    save_stt_processing_log(logs)
    logging.info(
        f"📊 STT 처리 기록 추가: {audio_duration:.2f}초 → {processing_time:.2f}초 (비율: {ratio:.3f})"
    )


# =============================================================================
# STT 처리 시간 예측
# =============================================================================
def estimate_stt_processing_time(audio_duration):
    """
    과거 로그를 기반으로 STT 처리 시간을 정확히 예측합니다.

    개선 사항:
    - 가중 평균: 최근 데이터에 더 높은 가중치 부여
    - 이상치 제거: 표준편차 기반 필터링
    - 구간별 분석: 오디오 길이별로 다른 비율 적용

    Args:
        audio_duration: 오디오 길이 (초)

    Returns:
        예상 처리 시간 (초)
    """
    logs = load_stt_processing_log()

    if not logs:
        # 로그가 없으면 기본값: 오디오 길이의 20% (경험적 추정)
        estimated = audio_duration * 0.2
        logging.info(f"⏱️ STT 예상 시간 (기본값): {estimated:.2f}초")
        return estimated

    # 1. 오디오 길이별 구간 분류
    # - 짧은 오디오: 0~300초 (5분)
    # - 중간 오디오: 300~900초 (5~15분)
    # - 긴 오디오: 900초 이상 (15분 이상)
    if audio_duration < 300:
        duration_range = "short"
        target_logs = [log for log in logs if log.get("audio_duration", 0) < 300]
    elif audio_duration < 900:
        duration_range = "medium"
        target_logs = [log for log in logs if 300 <= log.get("audio_duration", 0) < 900]
    else:
        duration_range = "long"
        target_logs = [log for log in logs if log.get("audio_duration", 0) >= 900]

    # 구간별 데이터가 부족하면 전체 데이터 사용
    if len(target_logs) < 5:
        target_logs = logs
        logging.info(f"⏱️ 구간별 데이터 부족, 전체 로그 사용 ({len(logs)}개)")

    # 2. 최근 데이터만 선택 (최대 50개)
    recent_logs = target_logs[-50:]

    # 3. 비율 추출 및 이상치 제거
    ratios = []
    for log in recent_logs:
        audio_dur = log.get("audio_duration", 0)
        proc_time = log.get("processing_time", 0)

        if audio_dur > 0:
            # 기존 ratio 필드가 있으면 사용, 없으면 계산
            ratio = log.get("ratio", proc_time / audio_dur)
            ratios.append(ratio)

    if not ratios:
        # 비율 계산 실패 시 기본값
        estimated = audio_duration * 0.2
        logging.info(f"⏱️ STT 예상 시간 (기본값): {estimated:.2f}초")
        return estimated

    # 4. 이상치(outlier) 제거 (표준편차 기반)
    import statistics

    if len(ratios) >= 3:
        mean_ratio = statistics.mean(ratios)
        stdev_ratio = statistics.stdev(ratios)

        # 평균 ± 2 표준편차 범위 내의 값만 사용
        filtered_ratios = [r for r in ratios if abs(r - mean_ratio) <= 2 * stdev_ratio]

        if filtered_ratios:
            ratios = filtered_ratios
            logging.info(f"📊 이상치 제거: {len(recent_logs)}개 → {len(ratios)}개")

    # 5. 가중 평균 계산 (최근 데이터에 더 높은 가중치)
    weights = []
    weighted_sum = 0
    weight_total = 0

    for i, ratio in enumerate(ratios):
        # 지수 가중치: 최근 데이터일수록 높은 가중치 (1.0 ~ 2.0)
        weight = 1.0 + (i / len(ratios))  # 첫 번째: 1.0, 마지막: 2.0
        weighted_sum += ratio * weight
        weight_total += weight
        weights.append(weight)

    weighted_avg_ratio = weighted_sum / weight_total if weight_total > 0 else 0.2

    # 6. 예상 시간 계산
    estimated = audio_duration * weighted_avg_ratio

    # 7. 예상 시간을 오디오 길이로 제한
    # STT 처리는 실시간보다 빨라야 하므로, 최대 오디오 길이의 1.5배로 제한
    max_estimated_time = audio_duration * 1.5
    if estimated > max_estimated_time:
        logging.warning(
            f"⚠️ 예상 시간({estimated:.2f}초)이 오디오 길이({audio_duration:.2f}초)의 1.5배를 초과하여 "
            f"{max_estimated_time:.2f}초로 제한합니다."
        )
        estimated = max_estimated_time

    # 최소값 제한 (너무 짧으면 비현실적)
    min_estimated_time = min(
        5.0, audio_duration * 0.05
    )  # 최소 5초 또는 오디오 길이의 5%
    if estimated < min_estimated_time:
        estimated = min_estimated_time

    # 8. 예측 신뢰도 계산
    if len(ratios) >= 3:
        stdev = statistics.stdev(ratios)
        confidence = max(0, 100 - (stdev * 100))  # 표준편차가 낮을수록 신뢰도 높음
    else:
        confidence = 50  # 데이터 부족 시 중간 신뢰도

    logging.info(
        f"⏱️ STT 예상 시간: {estimated:.2f}초 "
        f"(오디오: {audio_duration:.2f}초, 구간: {duration_range}, 샘플: {len(ratios)}개, "
        f"가중평균 비율: {weighted_avg_ratio:.3f}, 신뢰도: {confidence:.0f}%)"
    )

    return estimated


# =============================================================================
# STT 예측 정확도 분석
# =============================================================================
def analyze_stt_prediction_accuracy():
    """
    STT 예측 정확도를 분석합니다.

    Returns:
        dict: 통계 정보 (평균 오차율, 표준편차 등)
    """
    logs = load_stt_processing_log()

    if len(logs) < 5:
        return {
            "total_records": len(logs),
            "message": "데이터가 부족합니다 (최소 5개 필요)",
        }

    import statistics

    # 각 구간별 통계
    stats_by_range = {
        "short": {"ratios": [], "errors": []},  # 0~5분
        "medium": {"ratios": [], "errors": []},  # 5~15분
        "long": {"ratios": [], "errors": []},  # 15분 이상
    }

    all_ratios = []

    for log in logs:
        audio_dur = log.get("audio_duration", 0)
        proc_time = log.get("processing_time", 0)

        if audio_dur > 0:
            ratio = log.get("ratio", proc_time / audio_dur)
            all_ratios.append(ratio)

            # 구간 분류
            if audio_dur < 300:
                duration_range = "short"
            elif audio_dur < 900:
                duration_range = "medium"
            else:
                duration_range = "long"

            stats_by_range[duration_range]["ratios"].append(ratio)

    # 전체 통계
    if all_ratios:
        mean_ratio = statistics.mean(all_ratios)
        median_ratio = statistics.median(all_ratios)
        stdev_ratio = statistics.stdev(all_ratios) if len(all_ratios) >= 2 else 0

        result = {
            "total_records": len(logs),
            "overall": {
                "mean_ratio": round(mean_ratio, 4),
                "median_ratio": round(median_ratio, 4),
                "stdev_ratio": round(stdev_ratio, 4),
                "min_ratio": round(min(all_ratios), 4),
                "max_ratio": round(max(all_ratios), 4),
            },
            "by_duration": {},
        }

        # 구간별 통계
        for duration_range, data in stats_by_range.items():
            ratios = data["ratios"]
            if len(ratios) >= 2:
                result["by_duration"][duration_range] = {
                    "count": len(ratios),
                    "mean_ratio": round(statistics.mean(ratios), 4),
                    "median_ratio": round(statistics.median(ratios), 4),
                    "stdev_ratio": round(statistics.stdev(ratios), 4),
                }
            elif len(ratios) == 1:
                result["by_duration"][duration_range] = {
                    "count": 1,
                    "mean_ratio": round(ratios[0], 4),
                    "median_ratio": round(ratios[0], 4),
                    "stdev_ratio": 0,
                }

        return result
    else:
        return {"total_records": len(logs), "message": "유효한 데이터가 없습니다"}
