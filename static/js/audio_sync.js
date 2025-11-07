// 전역 변수
let segments = [];
let currentSegmentIndex = -1;
let autoScroll = true;
let sessionId = null;
let chatHistory = [];

// DOM 요소
const uploadForm = document.getElementById('uploadForm');
const uploadSection = document.getElementById('uploadSection');
const viewerSection = document.getElementById('viewerSection');
const audioPlayer = document.getElementById('audioPlayer');
const transcriptContent = document.getElementById('transcriptContent');
const currentTimeSpan = document.getElementById('currentTime');
const durationSpan = document.getElementById('duration');
const segmentInfo = document.getElementById('segmentInfo');
const autoScrollToggle = document.getElementById('autoScrollToggle');
const changeFileBtn = document.getElementById('changeFileBtn');
const uploadStatus = document.getElementById('uploadStatus');

// 파일 업로드 처리
uploadForm.addEventListener('submit', async (e) => {
    e.preventDefault();

    const formData = new FormData(uploadForm);

    // 제출 버튼 찾기
    const submitButton = uploadForm.querySelector('button[type="submit"]');
    const originalButtonText = submitButton.innerHTML;

    // 버튼 비활성화
    submitButton.disabled = true;
    submitButton.innerHTML = '<span class="btn-icon">⏳</span>처리 중...';
    submitButton.style.opacity = '0.6';
    submitButton.style.cursor = 'not-allowed';

    // 업로드 상태 표시
    showStatus(`🎤 ${sttServiceName}로 음성 인식 중...\n이 작업은 몇 분 정도 소요될 수 있습니다.`, 'info');

    try {
        const response = await fetch('/upload', {
            method: 'POST',
            body: formData
        });

        const result = await response.json();

        if (result.success) {
            showStatus(`✅ 음성 인식 완료! ${result.total_segments}개 세그먼트를 로드했습니다. (${sttServiceName})`, 'success');

            // 데이터 저장
            segments = result.segments;
            sessionId = result.session_id;

            // 오디오 설정
            audioPlayer.src = result.audio_url;

            // 회의록 렌더링
            renderTranscript();

            // 뷰어 표시
            setTimeout(() => {
                uploadSection.style.display = 'none';
                viewerSection.style.display = 'block';
            }, 1500);

        } else {
            showStatus(`❌ 오류: ${result.error}`, 'error');

            // 버튼 다시 활성화 (오류 시)
            submitButton.disabled = false;
            submitButton.innerHTML = originalButtonText;
            submitButton.style.opacity = '1';
            submitButton.style.cursor = 'pointer';
        }

    } catch (error) {
        showStatus(`❌ 업로드 실패: ${error.message}`, 'error');
        console.error('Upload error:', error);

        // 버튼 다시 활성화 (오류 시)
        submitButton.disabled = false;
        submitButton.innerHTML = originalButtonText;
        submitButton.style.opacity = '1';
        submitButton.style.cursor = 'pointer';
    }
});

// 상태 메시지 표시
function showStatus(message, type) {
    uploadStatus.textContent = message;
    uploadStatus.className = 'upload-status';

    if (type === 'success') {
        uploadStatus.classList.add('success');
    } else if (type === 'error') {
        uploadStatus.classList.add('error');
    }
}

// 회의록 렌더링
function renderTranscript() {
    transcriptContent.innerHTML = '';

    segments.forEach((segment, index) => {
        const segmentDiv = document.createElement('div');
        segmentDiv.className = 'transcript-segment future';
        segmentDiv.dataset.segmentId = index;
        segmentDiv.dataset.startTime = segment.start_time;

        segmentDiv.innerHTML = `
            <div class="segment-header">
                <span class="speaker-label speaker-${segment.speaker}">
                    🗣️ Speaker ${segment.speaker}
                </span>
                <div class="segment-meta">
                    <span class="time-stamp">${formatTime(segment.start_time)}</span>
                    ${segment.confidence > 0 ? `<span class="confidence-badge">신뢰도: ${(segment.confidence * 100).toFixed(0)}%</span>` : ''}
                </div>
            </div>
            <div class="segment-text">${segment.text}</div>
        `;

        // 클릭하면 해당 시간으로 이동
        segmentDiv.addEventListener('click', () => {
            audioPlayer.currentTime = segment.start_time;
            audioPlayer.play();
        });

        transcriptContent.appendChild(segmentDiv);
    });

    // 세그먼트 정보 업데이트
    segmentInfo.textContent = `총 ${segments.length}개 세그먼트`;
}

// 시간 포맷팅 (초 -> H:MM:SS)
function formatTime(seconds) {
    const hours = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    return `${hours}:${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
}

// 오디오 시간 업데이트 이벤트
audioPlayer.addEventListener('timeupdate', () => {
    const currentTime = audioPlayer.currentTime;

    // 현재 시간 표시
    currentTimeSpan.textContent = formatTime(currentTime);

    // 현재 재생 중인 세그먼트 찾기
    updateCurrentSegment(currentTime);
});

// 오디오 메타데이터 로드 (길이 표시)
audioPlayer.addEventListener('loadedmetadata', () => {
    durationSpan.textContent = formatTime(audioPlayer.duration);
});

// 현재 세그먼트 업데이트
function updateCurrentSegment(currentTime) {
    // 현재 시간에 해당하는 세그먼트 찾기
    let newSegmentIndex = -1;

    for (let i = 0; i < segments.length; i++) {
        const segment = segments[i];
        const nextSegment = segments[i + 1];

        const startTime = segment.start_time;
        const endTime = nextSegment ? nextSegment.start_time : audioPlayer.duration;

        if (currentTime >= startTime && currentTime < endTime) {
            newSegmentIndex = i;
            break;
        }
    }

    // 세그먼트가 변경되었을 때만 업데이트
    if (newSegmentIndex !== currentSegmentIndex) {
        currentSegmentIndex = newSegmentIndex;
        highlightSegment(currentSegmentIndex);
    }
}

// 세그먼트 하이라이트
function highlightSegment(index) {
    const segmentDivs = document.querySelectorAll('.transcript-segment');

    segmentDivs.forEach((div, i) => {
        div.classList.remove('current', 'past', 'future');

        if (i === index) {
            // 현재 재생 중
            div.classList.add('current');

            // 자동 스크롤
            if (autoScroll) {
                div.scrollIntoView({
                    behavior: 'smooth',
                    block: 'center'
                });
            }
        } else if (i < index) {
            // 지나간 세그먼트
            div.classList.add('past');
        } else {
            // 아직 재생되지 않은 세그먼트
            div.classList.add('future');
        }
    });
}

// 자동 스크롤 토글
autoScrollToggle.addEventListener('click', () => {
    autoScroll = !autoScroll;

    if (autoScroll) {
        autoScrollToggle.textContent = '자동 스크롤: ON';
        autoScrollToggle.classList.add('active');
    } else {
        autoScrollToggle.textContent = '자동 스크롤: OFF';
        autoScrollToggle.classList.remove('active');
    }
});

// 파일 변경 버튼
changeFileBtn.addEventListener('click', () => {
    // 오디오 정지
    audioPlayer.pause();
    audioPlayer.src = '';

    // 데이터 초기화
    segments = [];
    currentSegmentIndex = -1;

    // UI 초기화
    uploadSection.style.display = 'block';
    viewerSection.style.display = 'none';
    uploadForm.reset();
    uploadStatus.textContent = '';
    uploadStatus.className = 'upload-status';

    // 제출 버튼 초기화
    const submitButton = uploadForm.querySelector('button[type="submit"]');
    submitButton.disabled = false;
    submitButton.innerHTML = '<span class="btn-icon">🎤</span>음성 인식 시작';
    submitButton.style.opacity = '1';
    submitButton.style.cursor = 'pointer';
});

// 키보드 단축키
document.addEventListener('keydown', (e) => {
    // 입력 요소에 포커스가 있으면 단축키 무시
    const activeElement = document.activeElement;
    const isInputFocused = activeElement.tagName === 'INPUT' ||
                          activeElement.tagName === 'TEXTAREA' ||
                          activeElement.isContentEditable;

    if (isInputFocused) {
        return;
    }

    // 스페이스바: 재생/일시정지
    if (e.code === 'Space' && viewerSection.style.display !== 'none') {
        e.preventDefault();
        if (audioPlayer.paused) {
            audioPlayer.play();
        } else {
            audioPlayer.pause();
        }
    }

    // 화살표 좌: 5초 뒤로
    if (e.code === 'ArrowLeft' && viewerSection.style.display !== 'none') {
        e.preventDefault();
        audioPlayer.currentTime = Math.max(0, audioPlayer.currentTime - 5);
    }

    // 화살표 우: 5초 앞으로
    if (e.code === 'ArrowRight' && viewerSection.style.display !== 'none') {
        e.preventDefault();
        audioPlayer.currentTime = Math.min(audioPlayer.duration, audioPlayer.currentTime + 5);
    }
});

// 페이지 로드 완료 메시지
console.log('🎵 오디오-회의록 동기화 뷰어 v0.2가 준비되었습니다.');
console.log('키보드 단축키:');
console.log('  - 스페이스바: 재생/일시정지');
console.log('  - 화살표 좌: 5초 뒤로');
console.log('  - 화살표 우: 5초 앞으로');

// ===== v0.2 새로운 기능: 요약 및 채팅 =====

// DOM 요소 (요약 및 채팅)
const generateSummaryBtn = document.getElementById('generateSummaryBtn');
const summaryContent = document.getElementById('summaryContent');
const summaryLoading = document.getElementById('summaryLoading');
const chatMessages = document.getElementById('chatMessages');
const chatInput = document.getElementById('chatInput');
const sendChatBtn = document.getElementById('sendChatBtn');
const clearChatBtn = document.getElementById('clearChatBtn');
const chatLoading = document.getElementById('chatLoading');

// 요약 생성
generateSummaryBtn.addEventListener('click', async () => {
    if (!segments || segments.length === 0) {
        alert('회의록 데이터가 없습니다.');
        return;
    }

    // 로딩 표시
    summaryLoading.style.display = 'block';
    summaryContent.innerHTML = '<p class="summary-placeholder">요약 생성 중...</p>';
    generateSummaryBtn.disabled = true;

    try {
        const response = await fetch('/api/summarize', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                segments: segments,
                session_id: sessionId
            })
        });

        const result = await response.json();

        if (result.success) {
            // 마크다운을 HTML로 간단 변환
            const htmlContent = convertMarkdownToHtml(result.summary);
            summaryContent.innerHTML = htmlContent;
        } else {
            summaryContent.innerHTML = `<p class="error-message">❌ ${result.error}</p>`;
        }

    } catch (error) {
        console.error('Summary error:', error);
        summaryContent.innerHTML = `<p class="error-message">❌ 요약 생성 실패: ${error.message}</p>`;
    } finally {
        summaryLoading.style.display = 'none';
        generateSummaryBtn.disabled = false;
    }
});

// 간단한 마크다운 -> HTML 변환
function convertMarkdownToHtml(markdown) {
    let html = markdown;

    // 헤더
    html = html.replace(/^### (.*$)/gim, '<h3>$1</h3>');
    html = html.replace(/^## (.*$)/gim, '<h2>$1</h2>');
    html = html.replace(/^# (.*$)/gim, '<h1>$1</h1>');

    // 볼드
    html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');

    // 이탤릭
    html = html.replace(/\*(.*?)\*/g, '<em>$1</em>');

    // 리스트
    html = html.replace(/^\- (.*$)/gim, '<li>$1</li>');
    html = html.replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>');

    // 줄바꿈
    html = html.replace(/\n\n/g, '</p><p>');
    html = '<p>' + html + '</p>';

    // 빈 p 태그 제거
    html = html.replace(/<p><\/p>/g, '');

    return html;
}

// 채팅 전송
async function sendChatMessage() {
    const message = chatInput.value.trim();

    if (!message) {
        return;
    }

    if (!segments || segments.length === 0) {
        alert('회의록 데이터가 없습니다.');
        return;
    }

    // 사용자 메시지 표시
    addChatMessage(message, 'user');

    // 입력창 초기화
    chatInput.value = '';
    chatInput.style.height = 'auto';

    // 로딩 표시
    chatLoading.style.display = 'block';
    sendChatBtn.disabled = true;
    chatInput.disabled = true;

    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                message: message,
                segments: segments,
                session_id: sessionId,
                chat_history: chatHistory
            })
        });

        const result = await response.json();

        if (result.success) {
            // AI 응답 표시
            addChatMessage(result.response, 'assistant');

            // 대화 히스토리 업데이트
            chatHistory = result.chat_history;
        } else {
            addChatMessage(`❌ ${result.error}`, 'error');
        }

    } catch (error) {
        console.error('Chat error:', error);
        addChatMessage(`❌ 채팅 오류: ${error.message}`, 'error');
    } finally {
        chatLoading.style.display = 'none';
        sendChatBtn.disabled = false;
        chatInput.disabled = false;
        chatInput.focus();
    }
}

// 채팅 메시지 추가
function addChatMessage(message, role) {
    // welcome 메시지 제거
    const welcomeMsg = chatMessages.querySelector('.chat-welcome');
    if (welcomeMsg) {
        welcomeMsg.remove();
    }

    const messageDiv = document.createElement('div');
    messageDiv.className = `chat-message chat-${role}`;

    if (role === 'user') {
        messageDiv.innerHTML = `
            <div class="message-header">
                <span class="message-sender">👤 나</span>
            </div>
            <div class="message-content">${escapeHtml(message)}</div>
        `;
    } else if (role === 'assistant') {
        messageDiv.innerHTML = `
            <div class="message-header">
                <span class="message-sender">🤖 AI</span>
            </div>
            <div class="message-content">${convertMarkdownToHtml(message)}</div>
        `;
    } else if (role === 'error') {
        messageDiv.className = 'chat-message chat-error';
        messageDiv.innerHTML = `
            <div class="message-content">${escapeHtml(message)}</div>
        `;
    }

    chatMessages.appendChild(messageDiv);

    // 스크롤을 최하단으로
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// HTML 이스케이프
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// 채팅 전송 버튼 클릭
sendChatBtn.addEventListener('click', sendChatMessage);

// 채팅 입력창에서 Enter 키 (Shift+Enter는 줄바꿈)
chatInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendChatMessage();
    }
});

// 채팅 입력창 자동 높이 조절
chatInput.addEventListener('input', () => {
    chatInput.style.height = 'auto';
    chatInput.style.height = chatInput.scrollHeight + 'px';
});

// 채팅 초기화
clearChatBtn.addEventListener('click', () => {
    if (confirm('대화 내역을 모두 삭제하시겠습니까?')) {
        chatMessages.innerHTML = '<div class="chat-welcome">회의록 내용에 대해 질문해보세요!</div>';
        chatHistory = [];

        // 세션 데이터도 초기화
        if (sessionId) {
            // 서버에 알릴 필요가 있다면 여기에 추가
        }
    }
});

// 오디오 볼륨 컨트롤
const audioVolumeSlider = document.getElementById('audioVolume');
const audioVolumeValue = document.getElementById('audioVolumeValue');

if (audioVolumeSlider && audioVolumeValue && audioPlayer) {
    // 슬라이더 배경 업데이트 함수
    function updateAudioVolumeBackground(value) {
        const percentage = value;
        audioVolumeSlider.style.background = `linear-gradient(to right, var(--primary-color) 0%, var(--primary-color) ${percentage}%, #e5e7eb ${percentage}%, #e5e7eb 100%)`;
    }

    // 초기 볼륨 설정 (80%)
    const initialVolume = 80;
    audioPlayer.volume = initialVolume / 100;
    updateAudioVolumeBackground(initialVolume);

    // 볼륨 변경 이벤트
    audioVolumeSlider.addEventListener('input', (e) => {
        const volume = e.target.value;
        audioVolumeValue.textContent = `${volume}%`;
        updateAudioVolumeBackground(volume);

        // 오디오 플레이어 볼륨 설정 (0.0 ~ 1.0 범위)
        audioPlayer.volume = volume / 100;
    });
}
