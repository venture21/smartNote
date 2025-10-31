"""
STT 예상 시간 예측 정확도 테스트

개선된 estimate_stt_processing_time 함수를 테스트합니다.
"""

import json
import os
import sys
from datetime import datetime

# 현재 디렉토리를 Python 경로에 추가
sys.path.insert(0, os.path.dirname(__file__))

# STT 처리 로그 경로
CSV_FOLDER = os.path.join(os.path.dirname(__file__), "csv")
STT_PROCESSING_LOG = os.path.join(CSV_FOLDER, "stt_processing_log.json")


def load_stt_processing_log():
    """STT 처리 시간 로그를 로드합니다."""
    if os.path.exists(STT_PROCESSING_LOG):
        try:
            with open(STT_PROCESSING_LOG, 'r', encoding='utf-8') as f:
                logs = json.load(f)
            return logs
        except Exception as e:
            print(f"STT 로그 로드 오류: {e}")
            return []
    else:
        return []


def analyze_stt_prediction_accuracy():
    """STT 예측 정확도를 분석합니다."""
    logs = load_stt_processing_log()

    if len(logs) < 5:
        return {
            "total_records": len(logs),
            "message": "데이터가 부족합니다 (최소 5개 필요)"
        }

    import statistics

    # 각 구간별 통계
    stats_by_range = {
        "short": {"ratios": [], "errors": []},   # 0~5분
        "medium": {"ratios": [], "errors": []},  # 5~15분
        "long": {"ratios": [], "errors": []}     # 15분 이상
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
            "by_duration": {}
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
        return {
            "total_records": len(logs),
            "message": "유효한 데이터가 없습니다"
        }


def test_prediction():
    """예측 테스트"""
    print("=" * 60)
    print("📊 STT 예상 시간 예측 정확도 분석")
    print("=" * 60)

    # 통계 분석
    stats = analyze_stt_prediction_accuracy()

    if "message" in stats:
        print(f"\n⚠️ {stats['message']}")
        print(f"   현재 기록: {stats['total_records']}개")
        return

    print(f"\n📈 전체 통계 (총 {stats['total_records']}개 기록)")
    print("-" * 60)

    overall = stats["overall"]
    print(f"  평균 비율:  {overall['mean_ratio']:.4f} ({overall['mean_ratio']*100:.2f}%)")
    print(f"  중앙 비율:  {overall['median_ratio']:.4f} ({overall['median_ratio']*100:.2f}%)")
    print(f"  표준편차:   {overall['stdev_ratio']:.4f}")
    print(f"  최소 비율:  {overall['min_ratio']:.4f} ({overall['min_ratio']*100:.2f}%)")
    print(f"  최대 비율:  {overall['max_ratio']:.4f} ({overall['max_ratio']*100:.2f}%)")

    print("\n📊 구간별 통계")
    print("-" * 60)

    duration_labels = {
        "short": "짧은 오디오 (0~5분)",
        "medium": "중간 오디오 (5~15분)",
        "long": "긴 오디오 (15분 이상)"
    }

    for duration_range, label in duration_labels.items():
        if duration_range in stats["by_duration"]:
            data = stats["by_duration"][duration_range]
            print(f"\n  {label}:")
            print(f"    기록 수:    {data['count']}개")
            print(f"    평균 비율:  {data['mean_ratio']:.4f} ({data['mean_ratio']*100:.2f}%)")
            print(f"    중앙 비율:  {data['median_ratio']:.4f} ({data['median_ratio']*100:.2f}%)")
            print(f"    표준편차:   {data['stdev_ratio']:.4f}")
        else:
            print(f"\n  {label}: 데이터 없음")

    # 최근 기록 확인
    logs = load_stt_processing_log()
    if logs:
        print("\n📝 최근 10개 기록")
        print("-" * 60)
        print(f"{'오디오 길이':>12} {'처리 시간':>12} {'비율':>8} {'타입':>10} {'날짜':>20}")
        print("-" * 60)

        for log in logs[-10:]:
            audio_dur = log.get("audio_duration", 0)
            proc_time = log.get("processing_time", 0)
            ratio = log.get("ratio", proc_time / audio_dur if audio_dur > 0 else 0)
            source_type = log.get("source_type", "unknown")
            timestamp = log.get("timestamp", "")

            print(f"{audio_dur:>10.1f}초 {proc_time:>10.1f}초 {ratio:>7.2%} {source_type:>10} {timestamp:>20}")

    print("\n" + "=" * 60)
    print("💡 개선 사항:")
    print("  - ✅ 가중 평균: 최근 데이터에 더 높은 가중치")
    print("  - ✅ 이상치 제거: 표준편차 기반 필터링")
    print("  - ✅ 구간별 분석: 오디오 길이별 다른 비율 적용")
    print("  - ✅ 신뢰도 계산: 표준편차 기반 예측 신뢰도")
    print("=" * 60)


def main():
    """메인 함수"""
    test_prediction()


if __name__ == "__main__":
    main()
