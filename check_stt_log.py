"""
STT 처리 로그 확인 및 정리 스크립트
"""
import json
import os
from config import CSV_FOLDER

STT_PROCESSING_LOG = os.path.join(CSV_FOLDER, "stt_processing_log.json")

def check_and_clean_stt_log():
    """STT 로그 확인 및 이상 데이터 제거"""

    if not os.path.exists(STT_PROCESSING_LOG):
        print("❌ STT 로그 파일이 없습니다.")
        return

    with open(STT_PROCESSING_LOG, 'r', encoding='utf-8') as f:
        logs = json.load(f)

    print(f"📊 총 로그 개수: {len(logs)}개")
    print()

    # 통계 분석
    ratios = []
    abnormal_logs = []

    for idx, log in enumerate(logs):
        audio_dur = log.get("audio_duration", 0)
        proc_time = log.get("processing_time", 0)
        ratio = log.get("ratio", proc_time / audio_dur if audio_dur > 0 else 0)

        ratios.append(ratio)

        # 비정상적인 비율 체크 (1.5 초과)
        if ratio > 1.5:
            abnormal_logs.append({
                "index": idx,
                "audio_duration": audio_dur,
                "processing_time": proc_time,
                "ratio": ratio,
                "timestamp": log.get("timestamp", "Unknown")
            })

    # 통계 출력
    if ratios:
        import statistics
        print(f"⏱️ 비율 통계:")
        print(f"   - 평균: {statistics.mean(ratios):.3f}")
        print(f"   - 중앙값: {statistics.median(ratios):.3f}")
        print(f"   - 최소: {min(ratios):.3f}")
        print(f"   - 최대: {max(ratios):.3f}")
        if len(ratios) >= 2:
            print(f"   - 표준편차: {statistics.stdev(ratios):.3f}")
        print()

    # 비정상 데이터 출력
    if abnormal_logs:
        print(f"⚠️ 비정상 데이터 발견: {len(abnormal_logs)}개")
        print()
        for item in abnormal_logs[:10]:  # 최대 10개만 출력
            print(f"   [{item['index']}] 오디오: {item['audio_duration']:.1f}초, "
                  f"처리: {item['processing_time']:.1f}초, "
                  f"비율: {item['ratio']:.3f}, "
                  f"시간: {item['timestamp']}")

        if len(abnormal_logs) > 10:
            print(f"   ... 외 {len(abnormal_logs) - 10}개")
        print()

        # 자동 정리
        print("🧹 비정상 데이터를 자동으로 정리합니다...")

        # 비정상 데이터 제거 (비율이 1.5 초과인 것)
        cleaned_logs = [
            log for log in logs
            if (log.get("ratio",
                log.get("processing_time", 0) / log.get("audio_duration", 1)
                if log.get("audio_duration", 0) > 0 else 0)) <= 1.5
        ]

        # 저장
        with open(STT_PROCESSING_LOG, 'w', encoding='utf-8') as f:
            json.dump(cleaned_logs, f, indent=2, ensure_ascii=False)

        print(f"✅ 정리 완료: {len(logs)}개 → {len(cleaned_logs)}개")
        print(f"   삭제된 데이터: {len(logs) - len(cleaned_logs)}개")
    else:
        print("✅ 모든 데이터가 정상 범위 내에 있습니다.")

if __name__ == "__main__":
    check_and_clean_stt_log()
