from dotenv import load_dotenv
import os
import requests
import json


# 환경 변수 불러오기
load_dotenv()

# 환경 변수값을 전역변수로 설정하기
CLOVASPEECH_API_KEY = os.getenv("CLOVASPEECH_API")
CLOVASPEECH_URL = os.getenv("CLOVASPEECH_INVOKE_URL")


class ClovaSpeechClient:
    # Clova Speech invoke URL
    invoke_url = CLOVASPEECH_URL
    # Clova Speech secret key
    secret = CLOVASPEECH_API_KEY

    def req_url(
        self,
        url,
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

    def req_object_storage(
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

    def req_upload(
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


if __name__ == "__main__":
    res = ClovaSpeechClient().req_upload(
        file="./data/project_4p_4m_1.wav", completion="sync"
    )
    result = res.json()
    print(result)

    # 화자별 인식 결과 segment 추출
    segments = result.get("segments", [])
    speaker_segments = []
    for segment in segments:
        speaker_label = segment["speaker"]["label"]
        text = segment["text"]
        speaker_segments.append({"speaker": speaker_label, "text": text})

    # 화자별 인식 결과 segment 출력
    for speaker_segment in speaker_segments:
        speaker_label = speaker_segment["speaker"]
        text = speaker_segment["text"]
        print(f"Speaker {speaker_label}: {text}")
