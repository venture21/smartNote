import gradio as gr
import importlib.util
from pathlib import Path
import tempfile
import os
import shutil
import webbrowser
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

# ClovaSpeech-API.py 모듈 동적 로드
spec = importlib.util.spec_from_file_location("clova_speech", "C:/Users/park0/github/smartNote/ClovaSpeech-API.py")
clova_speech = importlib.util.module_from_spec(spec)
spec.loader.exec_module(clova_speech)
ClovaSpeechClient = clova_speech.ClovaSpeechClient


class SpeechTranscriber:
    """음성 인식 처리 클래스"""

    def __init__(self):
        self.segments = []
        self.audio_file = None
        self.temp_dir = tempfile.mkdtemp()
        self.html_file_path = None

    def transcribe_audio(self, audio_file_path, progress=gr.Progress()):
        """오디오 파일을 음성 인식하여 화자별 세그먼트 반환"""
        if audio_file_path is None:
            return "파일을 먼저 업로드해주세요.", ""

        try:
            progress(0, desc="음성 인식 시작...")

            client = ClovaSpeechClient()

            # diarization 옵션 활성화하여 화자 분리
            progress(0.3, desc="Clova Speech API 호출 중...")
            response = client.req_upload(
                file=audio_file_path,
                completion="sync",
                diarization={"enable": True}
            )

            progress(0.7, desc="결과 처리 중...")
            result = response.json()

            # 화자별 세그먼트 추출
            segments = result.get("segments", [])
            speaker_segments = []

            for segment in segments:
                speaker_label = segment.get("speaker", {}).get("label", "Unknown")
                text = segment.get("text", "")
                start_time = segment.get("start", 0)
                end_time = segment.get("end", 0)

                speaker_segments.append({
                    "speaker": speaker_label,
                    "text": text,
                    "start": start_time,
                    "end": end_time
                })

            self.segments = speaker_segments
            self.audio_file = audio_file_path

            progress(1.0, desc="음성 인식 완료!")

            # 독립 HTML 파일 생성
            html_path = self.create_standalone_html(audio_file_path, speaker_segments, font_size=14)
            self.html_file_path = html_path

            # 브라우저에서 자동으로 열기
            webbrowser.open('file://' + html_path.replace('\\', '/'))

            status = f"✓ 음성 인식 완료: {len(speaker_segments)}개 세그먼트\n📂 HTML 파일: {html_path}\n🌐 브라우저에서 열림"

            # Gradio UI에는 요약 정보와 안내 표시
            summary_html = f'''
            <div style="padding: 30px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                        border-radius: 15px; color: white; text-align: center;">
                <h2 style="margin-top: 0;">✅ 음성 인식 완료!</h2>
                <p style="font-size: 18px; margin: 20px 0;">
                    {len(speaker_segments)}개의 대화 세그먼트가 인식되었습니다
                </p>
                <div style="background: rgba(255,255,255,0.2); padding: 20px; border-radius: 10px; margin: 20px 0;">
                    <p style="font-size: 16px; margin: 10px 0;">
                        🎵 <strong>체크박스 표시 플레이어</strong>가<br/>
                        브라우저 새 탭에서 자동으로 열렸습니다!
                    </p>
                    <p style="font-size: 14px; margin: 10px 0; opacity: 0.9;">
                        오디오를 재생하면 현재 발화 중인 대화 왼쪽에<br/>
                        <strong>✓ 체크박스가 표시</strong>됩니다
                    </p>
                </div>
                <p style="font-size: 12px; opacity: 0.8; margin: 10px 0;">
                    브라우저가 열리지 않았다면 아래 경로의 파일을 직접 여세요:
                </p>
                <code style="background: rgba(0,0,0,0.3); padding: 8px 15px; border-radius: 5px;
                            font-size: 11px; display: inline-block; word-break: break-all;">
                    {html_path}
                </code>
            </div>
            '''

            return status, summary_html

        except Exception as e:
            error_msg = f"오류 발생: {str(e)}"
            error_html = f"<p style='color: red; padding: 20px;'>{error_msg}</p>"
            return error_msg, error_html

    def create_standalone_html(self, audio_file_path, segments, font_size=14):
        """독립적인 HTML 파일 생성 (완전한 JavaScript 지원 + Gemini 챗 기능)"""

        # 오디오 파일을 temp 디렉토리에 복사
        import os, shutil, json
        audio_filename = os.path.basename(audio_file_path)
        temp_audio_path = os.path.join(self.temp_dir, audio_filename)
        shutil.copy2(audio_file_path, temp_audio_path)

        # .env 파일에서 Gemini API 키 읽기
        gemini_api_key = os.getenv('GEMINI_API_KEY', '')

        # 전체 대화 내용을 JavaScript로 전달하기 위해 JSON으로 변환
        transcript_text = ""
        for segment in segments:
            speaker = segment["speaker"]
            text = segment["text"]
            transcript_text += f"[화자 {speaker}] {text}\n"

        # JSON 문자열로 변환 (JavaScript에서 사용)
        transcript_json = json.dumps(transcript_text)
        api_key_json = json.dumps(gemini_api_key)

        # 화자별 색상
        speaker_colors = {
            "0": "#E3F2FD",
            "1": "#FFE0B2",
            "2": "#C8E6C9",
            "3": "#E1BEE7",
        }

        speaker_text_colors = {
            "0": "#1565C0",
            "1": "#E65100",
            "2": "#2E7D32",
            "3": "#6A1B9A",
        }

        # 세그먼트 HTML 생성
        segments_html = ""
        for idx, segment in enumerate(segments):
            speaker = segment["speaker"]
            text = segment["text"]
            start_time = segment["start"]
            end_time = segment["end"]

            bg_color = speaker_colors.get(speaker, "#F5F5F5")
            text_color = speaker_text_colors.get(speaker, "#333333")
            time_str = self.format_time(start_time)

            segments_html += f'''
                <div id="segment-{idx}" class="chat-segment"
                     data-start="{start_time}" data-end="{end_time}"
                     style="margin: 8px 0; padding: 12px 12px 12px 55px;
                            background-color: {bg_color};
                            border-left: 4px solid {text_color};
                            border-radius: 5px;
                            transition: all 0.3s ease;
                            position: relative;">
                    <!-- 체크박스 아이콘 (기본 숨김) -->
                    <div class="checkbox-indicator" style="position: absolute;
                                                           left: 8px;
                                                           top: 50%;
                                                           transform: translateY(-50%);
                                                           width: 35px;
                                                           height: 35px;
                                                           background-color: #4CAF50;
                                                           border-radius: 50%;
                                                           display: none;
                                                           align-items: center;
                                                           justify-content: center;
                                                           font-size: 22px;
                                                           font-weight: bold;
                                                           color: white;
                                                           box-shadow: 0 2px 8px rgba(0,0,0,0.3);
                                                           animation: fadeIn 0.3s ease;">
                        ✓
                    </div>
                    <div style="font-size: {int(font_size * 0.8)}px; color: #666; margin-bottom: 5px;">
                        <b style="color: {text_color};">화자 {speaker}</b> · {time_str}
                    </div>
                    <div class="segment-text" data-base-size="{font_size}"
                         style="font-size: {font_size}px;
                                color: {text_color};
                                line-height: 1.5;">
                        {text}
                    </div>
                </div>
            '''

        # 완전한 HTML 생성 (Gemini 챗 기능 포함)
        html_content = f'''
<!DOCTYPE html>
<html lang="ko">
<head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Smart Note - 화자 분리 음성 인식 + Gemini Chat</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                margin: 0;
                padding: 20px;
                background-color: #f9f9f9;
            }}
            .container {{
                max-width: 1600px;
                margin: 0 auto;
                display: grid;
                grid-template-columns: 1fr 400px;
                gap: 20px;
            }}
            .left-panel {{
                display: flex;
                flex-direction: column;
                gap: 20px;
            }}
            .audio-player-container {{
                padding: 20px;
                background-color: #fff;
                border-radius: 10px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            }}
            audio {{
                width: 100%;
            }}
            .debug-info {{
                font-size: 11px;
                color: #999;
                margin-top: 10px;
                padding: 8px;
                background-color: #f5f5f5;
                border-radius: 5px;
            }}
            .chat-container {{
                background-color: #f5f5f5;
                padding: 20px;
                border-radius: 10px;
                max-height: 600px;
                overflow-y: auto;
            }}
            .gemini-panel {{
                background-color: #fff;
                border-radius: 10px;
                padding: 20px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                display: flex;
                flex-direction: column;
                height: calc(100vh - 40px);
            }}
            .gemini-header {{
                margin-bottom: 15px;
            }}
            .gemini-header h3 {{
                margin: 0 0 10px 0;
                color: #333;
            }}
            .api-key-container {{
                display: flex;
                gap: 10px;
                margin-bottom: 15px;
            }}
            .api-key-input {{
                flex: 1;
                padding: 8px 12px;
                border: 1px solid #ddd;
                border-radius: 5px;
                font-size: 14px;
            }}
            .connect-btn {{
                padding: 8px 20px;
                background-color: #667eea;
                color: white;
                border: none;
                border-radius: 5px;
                cursor: pointer;
                font-size: 14px;
                font-weight: 500;
            }}
            .connect-btn:hover {{
                background-color: #5568d3;
            }}
            .connect-btn:disabled {{
                background-color: #ccc;
                cursor: not-allowed;
            }}
            .status-message {{
                font-size: 12px;
                padding: 8px;
                border-radius: 5px;
                margin-bottom: 15px;
            }}
            .status-success {{
                background-color: #d4edda;
                color: #155724;
            }}
            .status-error {{
                background-color: #f8d7da;
                color: #721c24;
            }}
            .status-info {{
                background-color: #d1ecf1;
                color: #0c5460;
            }}
            .gemini-messages {{
                flex: 1;
                overflow-y: auto;
                margin-bottom: 15px;
                border: 1px solid #e0e0e0;
                border-radius: 5px;
                padding: 10px;
                background-color: #fafafa;
            }}
            .message {{
                margin-bottom: 15px;
                padding: 10px 15px;
                border-radius: 8px;
                max-width: 85%;
            }}
            .message-user {{
                background-color: #667eea;
                color: white;
                margin-left: auto;
                text-align: right;
            }}
            .message-ai {{
                background-color: #fff;
                color: #333;
                border: 1px solid #e0e0e0;
            }}
            .message-content {{
                font-size: 14px;
                line-height: 1.5;
                white-space: pre-wrap;
            }}
            .input-container {{
                display: flex;
                gap: 10px;
            }}
            .message-input {{
                flex: 1;
                padding: 10px 12px;
                border: 1px solid #ddd;
                border-radius: 5px;
                font-size: 14px;
                resize: none;
            }}
            .send-btn {{
                padding: 10px 20px;
                background-color: #667eea;
                color: white;
                border: none;
                border-radius: 5px;
                cursor: pointer;
                font-size: 14px;
                font-weight: 500;
            }}
            .send-btn:hover {{
                background-color: #5568d3;
            }}
            .send-btn:disabled {{
                background-color: #ccc;
                cursor: not-allowed;
            }}
            @keyframes fadeIn {{
                from {{
                    opacity: 0;
                    transform: translateY(-50%) scale(0.5);
                }}
                to {{
                    opacity: 1;
                    transform: translateY(-50%) scale(1);
                }}
            }}
            .checkbox-indicator {{
                animation: fadeIn 0.3s ease !important;
            }}
        </style>
</head>
<body>
        <div class="container">
            <div class="left-panel">
                <div class="audio-player-container">
                    <h3 style="margin-top: 0;">🎵 오디오 플레이어</h3>
                    <audio id="audio-player" controls preload="auto">
                        <source src="{audio_filename}" type="audio/wav">
                        Your browser does not support the audio element.
                    </audio>
                    <div id="debug-info" class="debug-info">로딩 중...</div>
                </div>

                <div class="chat-container" id="chat-container">
                    {segments_html}
                </div>
            </div>

            <div class="gemini-panel">
                <div class="gemini-header">
                    <h3>🤖 Gemini Chat</h3>
                    <div class="api-key-container">
                        <input type="password" id="api-key-input" class="api-key-input" placeholder="Gemini API 키를 입력하세요">
                        <button id="connect-btn" class="connect-btn">연결</button>
                    </div>
                    <div id="status-message" class="status-message status-info" style="display: none;">
                        API 키를 입력하고 연결하세요.
                    </div>
                </div>

                <div id="gemini-messages" class="gemini-messages">
                    <div class="message message-ai">
                        <div class="message-content">👋 안녕하세요! Gemini AI입니다.<br><br>API 키를 입력하고 연결 버튼을 클릭하면, 음성 인식된 대화 내용에 대해 질문하실 수 있습니다.</div>
                    </div>
                </div>

                <div class="input-container">
                    <textarea id="message-input" class="message-input" placeholder="질문을 입력하세요..." rows="3" disabled></textarea>
                    <button id="send-btn" class="send-btn" disabled>전송</button>
                </div>
            </div>
        </div>

        <script>
            console.log('🎯 Standalone HTML loaded with Gemini Chat!');

            // 전체 대화 내용 (컨텍스트로 사용)
            const TRANSCRIPT_TEXT = {transcript_json};

            // .env 파일에서 로드된 API 키
            const ENV_API_KEY = {api_key_json};

            // Gemini API 관련 변수
            let geminiApiKey = null;
            let geminiConnected = false;
            let chatHistory = [];

            // DOM 요소
            const apiKeyInput = document.getElementById('api-key-input');
            const connectBtn = document.getElementById('connect-btn');
            const statusMessage = document.getElementById('status-message');
            const messagesContainer = document.getElementById('gemini-messages');
            const messageInput = document.getElementById('message-input');
            const sendBtn = document.getElementById('send-btn');

            // 상태 메시지 표시
            function showStatus(message, type = 'info') {{
                statusMessage.textContent = message;
                statusMessage.className = `status-message status-${{type}}`;
                statusMessage.style.display = 'block';
            }}

            // 메시지 추가
            function addMessage(content, isUser = false) {{
                const messageDiv = document.createElement('div');
                messageDiv.className = `message ${{isUser ? 'message-user' : 'message-ai'}}`;

                const contentDiv = document.createElement('div');
                contentDiv.className = 'message-content';
                contentDiv.textContent = content;

                messageDiv.appendChild(contentDiv);
                messagesContainer.appendChild(messageDiv);
                messagesContainer.scrollTop = messagesContainer.scrollHeight;
            }}

            // Gemini API 연결
            connectBtn.addEventListener('click', async function() {{
                const apiKey = apiKeyInput.value.trim();
                if (!apiKey) {{
                    showStatus('❌ API 키를 입력해주세요.', 'error');
                    return;
                }}

                connectBtn.disabled = true;
                connectBtn.textContent = '연결 중...';
                showStatus('🔄 Gemini API에 연결 중...', 'info');

                try {{
                    // Gemini API 테스트 호출
                    const response = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent?key=${{apiKey}}`, {{
                        method: 'POST',
                        headers: {{
                            'Content-Type': 'application/json',
                        }},
                        body: JSON.stringify({{
                            contents: [
                                {{
                                    parts: [
                                        {{text: `다음은 음성으로 변환된 대화 내용입니다. 이 내용을 바탕으로 질문에 답변해주세요:\\n\\n${{TRANSCRIPT_TEXT}}`}}
                                    ]
                                }}
                            ]
                        }})
                    }});

                    if (!response.ok) {{
                        throw new Error(`API 오류: ${{response.status}} ${{response.statusText}}`);
                    }}

                    const data = await response.json();
                    geminiApiKey = apiKey;
                    geminiConnected = true;

                    // 대화 히스토리 초기화 (컨텍스트 포함)
                    chatHistory = [
                        {{
                            role: 'user',
                            parts: [{{text: `다음은 음성으로 변환된 대화 내용입니다. 이 내용을 바탕으로 질문에 답변해주세요:\\n\\n${{TRANSCRIPT_TEXT}}`}}]
                        }},
                        {{
                            role: 'model',
                            parts: data.candidates[0].content.parts
                        }}
                    ];

                    showStatus(`✅ Gemini API 연결 성공! (${{TRANSCRIPT_TEXT.length}}자의 대화 내용 로드됨)`, 'success');
                    messageInput.disabled = false;
                    sendBtn.disabled = false;
                    apiKeyInput.disabled = true;
                    connectBtn.textContent = '연결됨';

                    // 초기 메시지 추가
                    messagesContainer.innerHTML = '';
                    addMessage('👋 안녕하세요! Gemini AI입니다.\\n\\n음성 인식된 대화 내용을 분석했습니다. 무엇을 도와드릴까요?', false);

                }} catch (error) {{
                    console.error('Gemini API 연결 오류:', error);
                    showStatus(`❌ 연결 실패: ${{error.message}}`, 'error');
                    connectBtn.disabled = false;
                    connectBtn.textContent = '연결';
                }}
            }});

            // 메시지 전송
            async function sendMessage() {{
                if (!geminiConnected) {{
                    showStatus('❌ 먼저 API에 연결해주세요.', 'error');
                    return;
                }}

                const message = messageInput.value.trim();
                if (!message) return;

                // 사용자 메시지 추가
                addMessage(message, true);
                messageInput.value = '';
                sendBtn.disabled = true;
                sendBtn.textContent = '전송 중...';

                // 대화 히스토리에 추가
                chatHistory.push({{
                    role: 'user',
                    parts: [{{text: message}}]
                }});

                try {{
                    const response = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent?key=${{geminiApiKey}}`, {{
                        method: 'POST',
                        headers: {{
                            'Content-Type': 'application/json',
                        }},
                        body: JSON.stringify({{
                            contents: chatHistory
                        }})
                    }});

                    if (!response.ok) {{
                        throw new Error(`API 오류: ${{response.status}} ${{response.statusText}}`);
                    }}

                    const data = await response.json();
                    const aiResponse = data.candidates[0].content.parts[0].text;

                    // AI 응답 추가
                    addMessage(aiResponse, false);

                    // 대화 히스토리에 추가
                    chatHistory.push({{
                        role: 'model',
                        parts: data.candidates[0].content.parts
                    }});

                }} catch (error) {{
                    console.error('메시지 전송 오류:', error);
                    addMessage(`❌ 오류: ${{error.message}}`, false);
                }} finally {{
                    sendBtn.disabled = false;
                    sendBtn.textContent = '전송';
                }}
            }}

            // 전송 버튼 클릭
            sendBtn.addEventListener('click', sendMessage);

        // Enter 키로 전송 (Shift+Enter는 줄바꿈)
        messageInput.addEventListener('keydown', function(e) {{
            if (e.key === 'Enter' && !e.shiftKey) {{
                e.preventDefault();
                sendMessage();
            }}
        }});

        // .env 파일에서 API 키가 있으면 자동으로 연결
        if (ENV_API_KEY && ENV_API_KEY.trim() !== '') {{
            console.log('✅ .env 파일에서 API 키를 찾았습니다. 자동 연결을 시작합니다.');
            apiKeyInput.value = '••••••••••••••••••••';
            apiKeyInput.disabled = true;

            // 자동 연결 시도
            setTimeout(() => {{
                connectBtn.disabled = true;
                connectBtn.textContent = '연결 중...';
                showStatus('🔄 Gemini API에 자동 연결 중...', 'info');

                // Gemini API 테스트 호출
                fetch(`https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent?key=${{ENV_API_KEY}}`, {{
                    method: 'POST',
                    headers: {{
                        'Content-Type': 'application/json',
                    }},
                    body: JSON.stringify({{
                        contents: [
                            {{
                                parts: [
                                    {{text: `다음은 음성으로 변환된 대화 내용입니다. 이 내용을 바탕으로 질문에 답변해주세요:\\n\\n${{TRANSCRIPT_TEXT}}`}}
                                ]
                            }}
                        ]
                    }})
                }})
                .then(response => {{
                    if (!response.ok) {{
                        throw new Error(`API 오류: ${{response.status}} ${{response.statusText}}`);
                    }}
                    return response.json();
                }})
                .then(data => {{
                    geminiApiKey = ENV_API_KEY;
                    geminiConnected = true;

                    // 대화 히스토리 초기화 (컨텍스트 포함)
                    chatHistory = [
                        {{
                            role: 'user',
                            parts: [{{text: `다음은 음성으로 변환된 대화 내용입니다. 이 내용을 바탕으로 질문에 답변해주세요:\\n\\n${{TRANSCRIPT_TEXT}}`}}]
                        }},
                        {{
                            role: 'model',
                            parts: data.candidates[0].content.parts
                        }}
                    ];

                    showStatus(`✅ Gemini API 자동 연결 성공! (${{TRANSCRIPT_TEXT.length}}자의 대화 내용 로드됨)`, 'success');
                    messageInput.disabled = false;
                    sendBtn.disabled = false;
                    connectBtn.textContent = '연결됨';

                    // 초기 메시지 추가
                    messagesContainer.innerHTML = '';
                    addMessage('👋 안녕하세요! Gemini AI입니다.\\n\\n음성 인식된 대화 내용을 분석했습니다. 무엇을 도와드릴까요?', false);
                }})
                .catch(error => {{
                    console.error('Gemini API 자동 연결 오류:', error);
                    showStatus(`❌ 자동 연결 실패: ${{error.message}}. API 키를 확인해주세요.`, 'error');
                    connectBtn.disabled = false;
                    connectBtn.textContent = '재연결';
                    apiKeyInput.disabled = false;
                    apiKeyInput.value = '';
                }});
            }}, 500);
        }} else {{
            console.log('ℹ️ .env 파일에 API 키가 없습니다. 수동으로 입력해주세요.');
            showStatus('API 키를 입력하고 연결하세요.', 'info');
            statusMessage.style.display = 'block';
        }}

        // ===========================================
        // 오디오 플레이어 기능
        // ===========================================
        const audioPlayer = document.getElementById('audio-player');
        const segments = document.querySelectorAll('.chat-segment');
        const debugInfo = document.getElementById('debug-info');
        let currentHighlighted = null;

        console.log('Audio player:', audioPlayer);
        console.log('Segments count:', segments.length);

        if (debugInfo) {{
            debugInfo.textContent = 'Audio player: ' + (audioPlayer ? '✓' : '✗') + ' | Segments: ' + segments.length;
        }}

        if (audioPlayer && segments.length > 0) {{
            console.log('✅ Setting up event listeners');

            audioPlayer.addEventListener('loadedmetadata', function() {{
                console.log('📢 Audio loaded! Duration:', this.duration, 'seconds');
                if (debugInfo) {{
                    debugInfo.textContent += ' | Duration: ' + this.duration.toFixed(2) + 's | Status: Ready';
                }}
            }});

            audioPlayer.addEventListener('error', function(e) {{
                console.error('❌ Audio error:', e);
                if (debugInfo) {{
                    debugInfo.textContent = '❌ Error loading audio file';
                    debugInfo.style.color = 'red';
                    debugInfo.style.backgroundColor = '#ffe6e6';
                }}
            }});

            audioPlayer.addEventListener('timeupdate', function() {{
                const currentTime = this.currentTime * 1000;

                segments.forEach(function(segment) {{
                    const start = parseFloat(segment.getAttribute('data-start'));
                    const end = parseFloat(segment.getAttribute('data-end'));
                    const checkboxIndicator = segment.querySelector('.checkbox-indicator');

                    if (currentTime >= start && currentTime <= end) {{
                        if (currentHighlighted !== segment) {{
                            console.log('✓ Active segment:', segment.id, 'at', currentTime.toFixed(0), 'ms');

                            checkboxIndicator.style.display = 'flex';
                            segment.scrollIntoView({{ behavior: 'smooth', block: 'nearest' }});

                            currentHighlighted = segment;

                            if (debugInfo) {{
                                debugInfo.textContent = '▶️ Playing: Segment ' + segment.id + ' | Time: ' +
                                    this.currentTime.toFixed(2) + 's / ' + this.duration.toFixed(2) + 's';
                            }}
                        }}
                    }} else {{
                        checkboxIndicator.style.display = 'none';
                    }}
                }});
            }});

            audioPlayer.addEventListener('pause', function() {{
                console.log('⏸️ Audio paused');
                segments.forEach(function(segment) {{
                    const checkboxIndicator = segment.querySelector('.checkbox-indicator');
                    checkboxIndicator.style.display = 'none';
                }});
                currentHighlighted = null;
                if (debugInfo) {{
                    debugInfo.textContent = '⏸️ Paused at ' + this.currentTime.toFixed(2) + 's';
                }}
            }});

            audioPlayer.addEventListener('play', function() {{
                console.log('▶️ Audio playing');
                if (debugInfo) {{
                    debugInfo.textContent = '▶️ Playing...';
                }}
            }});

            audioPlayer.addEventListener('ended', function() {{
                console.log('⏹️ Audio ended');
                segments.forEach(function(segment) {{
                    const checkboxIndicator = segment.querySelector('.checkbox-indicator');
                    checkboxIndicator.style.display = 'none';
                }});
                currentHighlighted = null;
                if (debugInfo) {{
                    debugInfo.textContent = '⏹️ Playback completed';
                }}
            }});
        }} else {{
            console.error('❌ Missing audio player or segments');
            if (debugInfo) {{
                debugInfo.textContent = '❌ Setup failed';
                debugInfo.style.color = 'red';
            }}
        }}
    </script>
</body>
</html>
        '''

        # HTML 파일 저장
        html_file_path = os.path.join(self.temp_dir, 'player.html')
        with open(html_file_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

        return html_file_path

    def format_time(self, ms):
        """밀리초를 MM:SS 형식으로 변환"""
        seconds = ms // 1000
        minutes = seconds // 60
        seconds = seconds % 60
        return f"{minutes:02d}:{seconds:02d}"

    def update_font_size(self, font_size):
        """폰트 크기 변경 시 HTML 재생성 및 브라우저에서 열기"""
        if not self.segments:
            return "<p style='color: #666; padding: 20px; text-align: center;'>음성 인식 결과가 없습니다.</p>"

        if hasattr(self, 'audio_file') and self.audio_file:
            # 독립 HTML 파일 재생성
            html_path = self.create_standalone_html(self.audio_file, self.segments, font_size)
            self.html_file_path = html_path

            # 브라우저에서 열기
            webbrowser.open('file://' + html_path.replace('\\', '/'))

            # 안내 메시지
            summary_html = f'''
            <div style="padding: 30px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                        border-radius: 15px; color: white; text-align: center;">
                <h2 style="margin-top: 0;">🔄 폰트 크기 업데이트됨</h2>
                <p style="font-size: 18px; margin: 20px 0;">
                    폰트 크기: <strong>{font_size}px</strong>
                </p>
                <div style="background: rgba(255,255,255,0.2); padding: 20px; border-radius: 10px; margin: 20px 0;">
                    <p style="font-size: 16px; margin: 10px 0;">
                        🌐 업데이트된 플레이어가<br/>
                        브라우저 새 탭에서 열렸습니다!
                    </p>
                    <p style="font-size: 14px; margin: 10px 0; opacity: 0.9;">
                        재생 시 현재 대화 왼쪽에<br/>
                        <strong>✓ 체크박스가 표시</strong>됩니다
                    </p>
                </div>
                <p style="font-size: 12px; opacity: 0.8; margin: 10px 0;">
                    파일 경로:
                </p>
                <code style="background: rgba(0,0,0,0.3); padding: 8px 15px; border-radius: 5px;
                            font-size: 11px; display: inline-block; word-break: break-all;">
                    {html_path}
                </code>
            </div>
            '''
            return summary_html
        else:
            return "<p style='color: #666; padding: 20px; text-align: center;'>먼저 음성 인식을 실행하세요.</p>"


def create_interface():
    """Gradio 인터페이스 생성"""
    transcriber = SpeechTranscriber()

    with gr.Blocks(title="Smart Note - 화자 분리 음성 인식", theme=gr.themes.Soft()) as app:
        gr.Markdown("""
        # 🎙️ Smart Note - 화자 분리 음성 인식
        WAV 파일을 업로드하고 음성 인식을 실행하여 화자별 대화를 확인하세요.
        """)

        with gr.Row():
            # 왼쪽: 업로드 및 설정
            with gr.Column(scale=1):
                audio_input = gr.File(
                    label="📁 WAV 파일 업로드",
                    file_types=[".wav"],
                    type="filepath"
                )

                transcribe_btn = gr.Button(
                    "🎯 음성 인식 시작",
                    variant="primary",
                    size="lg"
                )

                status_text = gr.Textbox(
                    label="상태",
                    value="파일을 업로드하고 음성 인식을 시작하세요.",
                    interactive=False
                )

                font_size_slider = gr.Slider(
                    minimum=10,
                    maximum=30,
                    value=14,
                    step=1,
                    label="폰트 크기",
                    interactive=True
                )

                gr.Markdown("""
                ### 💡 사용 방법
                1. WAV 파일 업로드
                2. 음성 인식 시작 버튼 클릭
                3. 브라우저에서 플레이어 확인
                4. 폰트 크기 조절하여 재생성
                """)

            # 오른쪽: 처리 결과
            with gr.Column(scale=1):
                combined_display = gr.HTML(
                    value="""
                    <div style='padding: 50px; text-align: center; color: #999;'>
                        <h3 style='color: #666;'>🎙️ 음성 인식을 시작하세요</h3>
                        <p style='margin-top: 20px; color: #888;'>
                            WAV 파일을 업로드하고 음성 인식을 시작하면<br/>
                            브라우저에서 체크박스 플레이어가 자동으로 열립니다.
                        </p>
                    </div>
                    """,
                    label="📊 처리 결과"
                )

        # 이벤트 핸들러
        def handle_transcription(audio_file):
            status, html = transcriber.transcribe_audio(audio_file)
            return status, html

        # 음성 인식
        transcribe_btn.click(
            fn=handle_transcription,
            inputs=[audio_input],
            outputs=[status_text, combined_display]
        )

        # 폰트 크기 변경
        font_size_slider.change(
            fn=transcriber.update_font_size,
            inputs=[font_size_slider],
            outputs=[combined_display]
        )

    return app


if __name__ == "__main__":
    app = create_interface()
    app.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        show_error=True
    )
