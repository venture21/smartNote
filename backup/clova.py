import os
import requests
import json
from dotenv import load_dotenv

load_dotenv()

CLOVASPEECH_API_KEY = os.getenv("CLOVASPEECH_API")
CLOVASPEECH_URL = os.getenv("CLOVASPEECH_INVOKE_URL")


# ClovaSpeechClient 클래스 정의


class ClovaSpeechClient:
    # Clova Speech invoke URL
    invoke_url = CLOVASPEECH_URL
    # Clova Speech secret key
    secret = CLOVASPEECH_API_KEY

    """
    req_url : 이 함수는 웹(Web) 상에 공개된 URL 주소에 있는 음성 파일을 인식할 때 사용.
              이미 서버나 클라우드 버킷 등에 업로드되어 외부에서 접근 가능한 URL(url 파라미터)을 API에 전달하여 음성 인식을 요청.
    """

    def req_url(  # 외부 파일 인식 (url)
        self,
        url,
        completion,
        callback=None,
        userdata=None,
        forbiddens=None,
        boostings=None,
        wordAlignment=True,
        fullText=True,
        diarization=True,
        sed=None,
    ):

        request_body = {
            "url": url,
            "language": "ko-KR",
            "completion": completion,
            "callback": callback,
            "userdata": userdata,
            "wordAlignment": wordAlignment,
            "fullText": fullText,
            "forbiddens": forbiddens,
            "boostings": boostings,
            "diarization": diarization,
            "sed": sed,
        }
        headers = {
            "Accept": "application/json;UTF-8",
            "Content-Type": "application/json;UTF-8",
            "X-CLOVASPEECH-API-KEY": self.secret,
        }
        return requests.post(
            headers=headers,
            url=self.invoke_url + "/recognizer/url",
            data=json.dumps(request_body).encode("UTF-8"),
        )

    """
    req_object_storage : 이 함수는 NAVER Cloud Platform (NCP)의 Object Storage(OBS)에 저장된 파일을 인식할 때 사용합니다.
                         NCP Object Storage 버킷 내의 파일 경로(data_key 파라미터)를 지정하여 음성 인식을 요청합니다.
    """

    def req_object_storage(  # Naver Cloud Object Storage에 저장된 파일 인식
        self,
        data_key,
        completion,
        callback=None,
        userdata=None,
        forbiddens=None,
        boostings=None,
        wordAlignment=True,
        fullText=True,
        diarization=None,
        sed=None,
    ):

        request_body = {
            "dataKey": data_key,
            "language": "ko-KR",
            "completion": completion,
            "callback": callback,
            "userdata": userdata,
            "wordAlignment": wordAlignment,
            "fullText": fullText,
            "forbiddens": forbiddens,
            "boostings": boostings,
            "diarization": diarization,
            "sed": sed,
        }
        headers = {
            "Accept": "application/json;UTF-8",
            "Content-Type": "application/json;UTF-8",
            "X-CLOVASPEECH-API-KEY": self.secret,
        }
        return requests.post(
            headers=headers,
            url=self.invoke_url + "/recognizer/object-storage",
            data=json.dumps(request_body).encode("UTF-8"),
        )

    """
    req_upload : 로컬 컴퓨터에 있는 파일을 직접 업로드하여 인식할 때 사용.
                 로컬 파일 경로(file 파라미터)를 받아, 해당 파일을 API 서버로 직접 전송(업로드)하면서 동시에 음성 인식을 요청.
    """

    def req_upload(  # 로컬 파일 직접 업로드
        self,
        file,
        completion,
        callback=None,
        userdata=None,
        forbiddens=None,
        boostings=None,
        wordAlignment=True,
        fullText=True,
        diarization=None,
        sed=None,
    ):

        request_body = {
            "language": "ko-KR",  ### 언어
            "completion": completion,  ### 응답방식 [동기 / 비동기]
            "callback": callback,  # 비동기 방식일 경우 callback, resultToObs 중 하나 필수 입력
            "userdata": userdata,  # 사용자 데이터 세부 정보
            "wordAlignment": wordAlignment,  # 인식 결과의 음성과 텍스트 정렬 출력 여부
            "fullText": fullText,  # 전체 인식 결과 텍스트 출력 기본 true
            "forbiddens": forbiddens,
            # noiseFiltering : 노이즈 필터링 여부 기본값 true
            "boostings": boostings,  ### 키워드 부스팅, 음성 인식률을 높일 수 있는 키워드 목록으로 사용
            "diarization": diarization,  ### 화자 인식
            "sed": sed,
        }
        headers = {
            "Accept": "application/json;UTF-8",
            "X-CLOVASPEECH-API-KEY": self.secret,
        }
        print(json.dumps(request_body, ensure_ascii=False).encode("UTF-8"))
        files = {
            "media": open(file, "rb"),
            "params": (
                None,
                json.dumps(request_body, ensure_ascii=False).encode("UTF-8"),
                "application/json",
            ),
        }
        response = requests.post(
            headers=headers, url=self.invoke_url + "/recognizer/upload", files=files
        )
        return response


# ------------------------------------------------------------
# ① 출력 파일이 저장될 경로 및 폴더 세팅
# ------------------------------------------------------------
def setup_output_paths(audio_path: str):
    # 오디오 경로를 받아서 해당 오디오의 파일명(확장자 제외)를 사용해서 만들어질 파일명을 정함.
    # 이것도 json이랑 txt로 나눠서 폴더를 만들 수 있게 하는게 좋아보임.
    # 오디오파일명
    audio_basename = os.path.splitext(os.path.basename(audio_path))[0]
    # output을 넣을 폴더 경로와 폴더명 정의
    output_dir = os.path.join("../result", audio_basename)
    # 실제 폴더 생성.
    os.makedirs(output_dir, exist_ok=True)

    # 생성된 폴더에 생성할 파일명 정의
    txt_path = os.path.join(output_dir, f"{audio_basename}.txt")
    json_path = os.path.join(output_dir, f"{audio_basename}_result.json")

    print(f"출력 디렉토리: {output_dir}")
    # 파일명 return
    return txt_path, json_path


# ------------------------------------------------------------
# ② CLOVA Speech API 호출
# ------------------------------------------------------------
def call_clova_api(audio_path: str, diarization: bool = True):
    # 단순히 Clova Speech API를 호출하는 코드
    # file: 오디오 경로 필요 (필수)
    # diarization: 화자 분리 기능
    # completion(sync/async) 동기 비동기 방식인데 오디오 길이가 클수록 들어가는 시간이 많아져 비동기 방식을 권장. 단 테스트에는 동기방식으로 통일
    print("클로바 스피치 API 요청 중...")
    # HTTP 통신의 상태 코드, 헤더, 본문(JSON 등)을 모두 포함하는 구조를 반환.
    res = ClovaSpeechClient().req_upload(
        file=audio_path, completion="sync", diarization={"enable": diarization}
    )
    # 실행중 에러 발생시
    if res.status_code != 200:
        print(f"❌ API 실패 ({res.status_code})")
        print(res.text)
        return None
    # 정상 동작시
    else:
        print("✅ API 응답 수신 완료")
        return res.json()


# ------------------------------------------------------------
# ③ 세그먼트 병합 : Clova Speech API가 반환한 원본(raw) JSON 결과에서
# 'segments' 목록을 가져와, '동일한 화자'의 연속된 발화(segment)를 하나로 병합하는 역할
#
# "segments": [
#  {"speaker": {"label": "1"}, "text": "안녕하세요.", ...},
#  {"speaker": {"label": "1"}, "text": "반갑습니다.", ...},
# ]
# ------------------------------------------------------------
def process_segments(result_json: dict):

    segments = result_json.get("segments", [])
    merged = []
    current = None

    for seg in segments:
        speaker = seg.get("speaker", {}).get("label", "Unknown")
        text = seg.get("text", "").strip()
        start = seg.get("start")
        conf = seg.get("confidence")

        # 🔹 새로운 화자면 이전 구간 저장
        if current and speaker != current["speaker"]:
            merged.append(format_segment(current))
            current = None

        # 🔹 현재 화자 구간 갱신
        if not current:
            current = {"speaker": speaker, "start": start, "texts": [], "confs": []}

        current["texts"].append(text)
        if conf is not None:
            current["confs"].append(conf)

    # 🔹 마지막 화자 구간 처리
    if current:
        merged.append(format_segment(current))

    return merged


def format_segment(seg):
    avg_conf = sum(seg["confs"]) / len(seg["confs"]) if seg["confs"] else None
    conf_str = f"{avg_conf:.2f}" if avg_conf is not None else "N/A"
    start_str = f"{int(seg['start']):08d}" if seg["start"] else "00000000"
    text = " ".join(seg["texts"]).strip()
    idx = len(text)  # (선택사항) or global counter
    return f"{start_str}:{conf_str}:speaker{seg['speaker']}:{text}\n"


# ------------------------------------------------------------
# ④ 결과 저장 (TXT + JSON)
# ------------------------------------------------------------
# def save_results(txt_lines, txt_path, json_path, json_data):  #
#     with open(txt_path, "w", encoding="utf-8") as f:
#         f.writelines(txt_lines)
#     print(f"✅ 텍스트 저장 완료 → {txt_path}")

#     with open(json_path, "w", encoding="utf-8") as jf:
#         json.dump(json_data, jf, ensure_ascii=False, indent=2)
#     print(f"✅ JSON 저장 완료 → {json_path}")


def save_text_result(txt_lines, path):
    """
    텍스트 라인 리스트를 지정된 경로의 텍스트 파일로 저장합니다.
    """
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(txt_lines)
    print(f"✅ 텍스트 저장 완료 → {path}")


def save_json_result(path, data):
    """
    파이썬 딕셔너리(JSON 데이터)를 지정된 경로의 JSON 파일로 저장합니다.
    """
    with open(path, "w", encoding="utf-8") as jf:
        json.dump(data, jf, ensure_ascii=False, indent=2)
    print(f"✅ JSON 저장 완료 → {path}")


# ------------------------------------------------------------
# ⑤ 메인 실행 함수
# ------------------------------------------------------------
def main(audio_path, diarization=True):
    # 경로에 실제 오디오 파일이 있는지 확인(메소드화)
    if not os.path.exists(audio_path):
        print(f"❌ 파일 없음: {audio_path}")
        return

    txt_path, json_path = setup_output_paths(audio_path)
    result_json = call_clova_api(audio_path, diarization)

    if not result_json:
        print("❌ API 결과 없음. 종료합니다.")
        return

    txt_lines = process_segments(result_json)
    save_text_result(txt_lines, txt_path)
    save_json_result(json_path, result_json)
    print("🎉 모든 과정 완료!")


# ------------------------------------------------------------
# 실행
# ------------------------------------------------------------
if __name__ == "__main__":
    AUDIO_FILE_PATH = input("🎧 변환할 오디오 파일 경로를 입력하세요: ").strip()
    DIARIZATION = True
    main(AUDIO_FILE_PATH, DIARIZATION)
