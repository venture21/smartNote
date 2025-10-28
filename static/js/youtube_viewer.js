// 전역 변수
let segments = [];
let sessionId = null;
let chatHistory = [];
let youtubePlayer = null;
let currentVideoId = null;
let autoScroll = true;
let syncInterval = null;

// DOM 요소
const youtubeForm = document.getElementById('youtubeForm');
const uploadSection = document.getElementById('uploadSection');
const viewerSection = document.getElementById('viewerSection');
const transcriptContent = document.getElementById('transcriptContent');
const segmentInfo = document.getElementById('segmentInfo');
const changeUrlBtn = document.getElementById('changeUrlBtn');
const uploadStatus = document.getElementById('uploadStatus');

// 진행 상황 요소
const progressSection = document.getElementById('progressSection');
const downloadProgress = document.getElementById('downloadProgress');
const downloadProgressBar = document.getElementById('downloadProgressBar');
const downloadMessage = document.getElementById('downloadMessage');
const sttProgress = document.getElementById('sttProgress');
const sttProgressBar = document.getElementById('sttProgressBar');
const sttMessage = document.getElementById('sttMessage');

// 영상 정보 요소
const videoTitle = document.getElementById('videoTitle');
const videoChannel = document.getElementById('videoChannel');
const viewCount = document.getElementById('viewCount');
const uploadDate = document.getElementById('uploadDate');
const processedAt = document.getElementById('processedAt');

// 진행 상황 폴링
let pollingInterval = null;

function startPolling(taskId) {
    // 초기화
    progressSection.style.display = 'block';
    downloadProgress.textContent = '0%';
    downloadProgressBar.style.width = '0%';
    downloadMessage.textContent = '대기 중...';
    sttProgress.textContent = '0%';
    sttProgressBar.style.width = '0%';
    sttMessage.textContent = '대기 중...';

    // 폴링 시작 (500ms마다)
    pollingInterval = setInterval(async () => {
        try {
            const response = await fetch(`/api/progress/${taskId}`);
            const result = await response.json();

            if (result.success && result.progress) {
                const progress = result.progress;

                // 다운로드 & MP3 변환 진행 상황
                if (progress.download) {
                    const downloadProg = progress.download.progress;
                    downloadProgress.textContent = `${downloadProg}%`;
                    downloadProgressBar.style.width = `${downloadProg}%`;
                    downloadMessage.textContent = progress.download.message;
                }

                // STT 진행 상황
                if (progress.stt) {
                    const sttProg = progress.stt.progress;
                    sttProgress.textContent = `${sttProg}%`;
                    sttProgressBar.style.width = `${sttProg}%`;
                    sttMessage.textContent = progress.stt.message;
                }
            }
        } catch (error) {
            console.error('Progress polling error:', error);
        }
    }, 500);
}

function stopPolling() {
    if (pollingInterval) {
        clearInterval(pollingInterval);
        pollingInterval = null;
    }
}

function startPollingWithCompletion(taskId, submitButton, originalButtonText) {
    // 초기화
    progressSection.style.display = 'block';
    downloadProgress.textContent = '0%';
    downloadProgressBar.style.width = '0%';
    downloadMessage.textContent = '대기 중...';
    sttProgress.textContent = '0%';
    sttProgressBar.style.width = '0%';
    sttMessage.textContent = '대기 중...';

    // 폴링 시작 (500ms마다)
    pollingInterval = setInterval(async () => {
        try {
            const response = await fetch(`/api/progress/${taskId}`);
            const result = await response.json();

            if (result.success && result.progress) {
                const progress = result.progress;

                // 다운로드 & MP3 변환 진행 상황
                if (progress.download) {
                    const downloadProg = progress.download.progress;
                    downloadProgress.textContent = `${downloadProg}%`;
                    downloadProgressBar.style.width = `${downloadProg}%`;
                    downloadMessage.textContent = progress.download.message;
                }

                // STT 진행 상황
                if (progress.stt) {
                    const sttProg = progress.stt.progress;
                    sttProgress.textContent = `${sttProg}%`;
                    sttProgressBar.style.width = `${sttProg}%`;
                    sttMessage.textContent = progress.stt.message;
                }

                // 에러 체크
                if (progress.error) {
                    stopPolling();
                    showStatus(`❌ 오류: ${progress.error.message}`, 'error');
                    submitButton.disabled = false;
                    submitButton.innerHTML = originalButtonText;
                    submitButton.style.opacity = '1';
                    submitButton.style.cursor = 'pointer';
                    progressSection.style.display = 'none';
                    return;
                }

                // 완료 체크
                if (progress.completed && progress.result) {
                    stopPolling();
                    const finalResult = progress.result;

                    // 진행 상황을 100%로 설정
                    downloadProgress.textContent = '100%';
                    downloadProgressBar.style.width = '100%';
                    downloadMessage.textContent = '오디오 다운로드 & MP3 변환 완료';
                    sttProgress.textContent = '100%';
                    sttProgressBar.style.width = '100%';
                    sttMessage.textContent = '회의록 생성 완료';

                    // 데이터 저장
                    segments = finalResult.segments;
                    sessionId = finalResult.session_id;

                    // 영상 정보 표시
                    videoTitle.textContent = finalResult.title || '-';
                    videoChannel.textContent = finalResult.channel || '-';
                    viewCount.textContent = finalResult.view_count ? finalResult.view_count.toLocaleString() + ' 회' : '-';
                    uploadDate.textContent = finalResult.upload_date || '-';
                    processedAt.textContent = finalResult.created_at || '-';

                    // 완료 메시지
                    showStatus(`✅ 영상 처리 완료! ${finalResult.total_segments}개 세그먼트를 생성했습니다.`, 'success');

                    // 회의록 렌더링
                    renderTranscript();

                    // YouTube 플레이어 초기화
                    if (finalResult.video_id) {
                        setTimeout(() => {
                            initYouTubePlayer(finalResult.video_id);
                        }, 500);
                    }

                    // 캐시된 요약이 있으면 표시
                    if (finalResult.summary && finalResult.summary.trim()) {
                        const htmlContent = convertMarkdownToHtml(finalResult.summary);
                        summaryContent.innerHTML = htmlContent;
                    } else {
                        summaryContent.innerHTML = '<p class="summary-placeholder">요약 생성 버튼을 클릭하세요</p>';
                    }

                    // 뷰어 표시
                    setTimeout(() => {
                        progressSection.style.display = 'none';
                        uploadSection.style.display = 'none';
                        viewerSection.style.display = 'block';
                    }, 1500);

                    return;
                }
            }
        } catch (error) {
            console.error('Progress polling error:', error);
        }
    }, 500);
}

// YouTube URL 처리
youtubeForm.addEventListener('submit', async (e) => {
    e.preventDefault();

    const formData = new FormData(youtubeForm);
    const youtubeUrl = formData.get('youtube_url');
    const sttService = formData.get('stt_service');
    const sttServiceName = sttService === 'gemini' ? 'Gemini STT' : 'Clova STT';

    // 제출 버튼 찾기
    const submitButton = youtubeForm.querySelector('button[type="submit"]');
    const originalButtonText = submitButton.innerHTML;

    // 버튼 비활성화
    submitButton.disabled = true;
    submitButton.innerHTML = '<span class="btn-icon">⏳</span>처리 중...';
    submitButton.style.opacity = '0.6';
    submitButton.style.cursor = 'not-allowed';

    // 상태 메시지 숨김
    uploadStatus.textContent = '';
    uploadStatus.className = 'upload-status';

    try {
        const response = await fetch('/api/process-youtube', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                youtube_url: youtubeUrl,
                stt_service: sttService
            })
        });

        const result = await response.json();

        if (result.success) {
            // 캐시된 데이터인 경우
            if (result.cached) {
                const statusMessage = `✅ ${result.message}\n총 ${result.total_segments}개 세그먼트`;
                showStatus(statusMessage, 'success');

                // 데이터 저장
                segments = result.segments;
                sessionId = result.session_id;

                // 영상 정보 표시
                videoTitle.textContent = result.title || '-';
                videoChannel.textContent = result.channel || '-';
                viewCount.textContent = result.view_count ? result.view_count.toLocaleString() + ' 회' : '-';
                uploadDate.textContent = result.upload_date || '-';
                processedAt.textContent = result.created_at || '-';

                // 회의록 렌더링
                renderTranscript();

                // YouTube 플레이어 초기화
                if (result.video_id) {
                    setTimeout(() => {
                        initYouTubePlayer(result.video_id);
                    }, 500);
                }

                // 캐시된 요약이 있으면 표시
                if (result.summary && result.summary.trim()) {
                    const htmlContent = convertMarkdownToHtml(result.summary);
                    summaryContent.innerHTML = htmlContent;
                } else {
                    summaryContent.innerHTML = '<p class="summary-placeholder">요약 생성 버튼을 클릭하세요</p>';
                }

                // 뷰어 표시
                setTimeout(() => {
                    uploadSection.style.display = 'none';
                    viewerSection.style.display = 'block';
                }, 1500);
            }
            // 새로운 처리인 경우 - 폴링 시작
            else if (result.processing && result.task_id) {
                startPollingWithCompletion(result.task_id, submitButton, originalButtonText);
            }

        } else {
            showStatus(`❌ 오류: ${result.error}`, 'error');

            // 버튼 다시 활성화 (오류 시)
            submitButton.disabled = false;
            submitButton.innerHTML = originalButtonText;
            submitButton.style.opacity = '1';
            submitButton.style.cursor = 'pointer';
        }

    } catch (error) {
        showStatus(`❌ 처리 실패: ${error.message}`, 'error');
        console.error('Processing error:', error);

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
    } else if (type === 'info') {
        uploadStatus.classList.add('info');
    }
}

// 회의록 렌더링
function renderTranscript() {
    transcriptContent.innerHTML = '';

    segments.forEach((segment, index) => {
        const segmentDiv = document.createElement('div');
        segmentDiv.className = 'transcript-segment';
        segmentDiv.dataset.segmentId = index;
        segmentDiv.style.cursor = 'pointer';

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

        // 세그먼트 클릭 시 해당 시간으로 이동
        segmentDiv.addEventListener('click', () => {
            seekToSegment(segment.start_time);
        });

        transcriptContent.appendChild(segmentDiv);
    });

    // 세그먼트 정보 업데이트
    segmentInfo.textContent = `총 ${segments.length}개 세그먼트`;
}

// 시간 포맷팅 (초 -> MM:SS)
function formatTime(seconds) {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
}

// URL 변경 버튼
changeUrlBtn.addEventListener('click', () => {
    // 데이터 초기화
    segments = [];
    sessionId = null;
    chatHistory = [];

    // YouTube 플레이어 정리
    if (youtubePlayer) {
        stopSync();
        youtubePlayer.destroy();
        youtubePlayer = null;
    }
    currentVideoId = null;

    // UI 초기화
    uploadSection.style.display = 'block';
    viewerSection.style.display = 'none';
    youtubeForm.reset();
    uploadStatus.textContent = '';
    uploadStatus.className = 'upload-status';

    // 제출 버튼 초기화
    const submitButton = youtubeForm.querySelector('button[type="submit"]');
    submitButton.disabled = false;
    submitButton.innerHTML = '<span class="btn-icon">🎤</span>영상 처리 시작';
    submitButton.style.opacity = '1';
    submitButton.style.cursor = 'pointer';

    // 채팅 초기화
    chatMessages.innerHTML = '<div class="chat-welcome">회의록 내용에 대해 질문해보세요!</div>';

    // 요약 초기화
    summaryContent.innerHTML = '<p class="summary-placeholder">요약 생성 버튼을 클릭하세요</p>';
});

// ===== 요약 및 채팅 기능 =====

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
    }
});

// ===== YouTube 플레이어 및 동기화 기능 =====

// YouTube IFrame API 준비 완료 콜백
function onYouTubeIframeAPIReady() {
    console.log('✅ YouTube IFrame API 준비 완료');
}

// YouTube 플레이어 생성
function initYouTubePlayer(videoId) {
    currentVideoId = videoId;

    // 기존 플레이어가 있으면 제거
    if (youtubePlayer) {
        youtubePlayer.destroy();
    }

    youtubePlayer = new YT.Player('youtubePlayer', {
        height: '480',
        width: '100%',
        videoId: videoId,
        playerVars: {
            'playsinline': 1,
            'rel': 0
        },
        events: {
            'onReady': onPlayerReady,
            'onStateChange': onPlayerStateChange
        }
    });
}

// 플레이어 준비 완료
function onPlayerReady(event) {
    console.log('✅ YouTube 플레이어 준비 완료');
    updateDuration();
}

// 플레이어 상태 변경
function onPlayerStateChange(event) {
    if (event.data == YT.PlayerState.PLAYING) {
        // 재생 시작 - 동기화 시작
        startSync();
    } else if (event.data == YT.PlayerState.PAUSED || event.data == YT.PlayerState.ENDED) {
        // 일시정지/종료 - 동기화 중지
        stopSync();
    }
}

// 재생 시간 동기화 시작
function startSync() {
    if (syncInterval) return; // 이미 실행 중이면 무시

    syncInterval = setInterval(() => {
        if (youtubePlayer && youtubePlayer.getCurrentTime) {
            const currentTime = youtubePlayer.getCurrentTime();
            updateCurrentTime(currentTime);
            highlightCurrentSegment(currentTime);
        }
    }, 100); // 100ms마다 업데이트
}

// 동기화 중지
function stopSync() {
    if (syncInterval) {
        clearInterval(syncInterval);
        syncInterval = null;
    }
}

// 현재 시간 표시 업데이트
function updateCurrentTime(seconds) {
    const currentTimeEl = document.getElementById('currentTime');
    if (currentTimeEl) {
        currentTimeEl.textContent = formatTime(seconds);
    }
}

// 총 재생 시간 업데이트
function updateDuration() {
    if (youtubePlayer && youtubePlayer.getDuration) {
        const duration = youtubePlayer.getDuration();
        const durationEl = document.getElementById('duration');
        if (durationEl) {
            durationEl.textContent = formatTime(duration);
        }
    }
}

// 현재 재생 시간에 해당하는 세그먼트 하이라이트
function highlightCurrentSegment(currentTime) {
    if (!segments || segments.length === 0) return;

    // 현재 시간에 해당하는 세그먼트 찾기
    let activeSegmentIndex = -1;
    for (let i = 0; i < segments.length; i++) {
        const segment = segments[i];
        const nextSegment = segments[i + 1];

        if (nextSegment) {
            // 현재 세그먼트 시작 시간과 다음 세그먼트 시작 시간 사이
            if (currentTime >= segment.start_time && currentTime < nextSegment.start_time) {
                activeSegmentIndex = i;
                break;
            }
        } else {
            // 마지막 세그먼트
            if (currentTime >= segment.start_time) {
                activeSegmentIndex = i;
                break;
            }
        }
    }

    // 모든 세그먼트의 하이라이트 제거
    const allSegments = document.querySelectorAll('.transcript-segment');
    allSegments.forEach(seg => seg.classList.remove('active'));

    // 현재 세그먼트 하이라이트
    if (activeSegmentIndex >= 0) {
        const activeSegment = document.querySelector(`.transcript-segment[data-segment-id="${activeSegmentIndex}"]`);
        if (activeSegment) {
            activeSegment.classList.add('active');

            // 자동 스크롤 (회의록 창 내부에서만)
            if (autoScroll) {
                const container = transcriptContent;
                const segmentTop = activeSegment.offsetTop;
                const segmentHeight = activeSegment.offsetHeight;
                const containerHeight = container.clientHeight;

                // 세그먼트를 컨테이너 중앙에 위치시키기
                const scrollPosition = segmentTop - (containerHeight / 2) + (segmentHeight / 2);

                container.scrollTo({
                    top: scrollPosition,
                    behavior: 'smooth'
                });
            }
        }
    }
}

// 자동 스크롤 토글
const autoScrollToggle = document.getElementById('autoScrollToggle');
if (autoScrollToggle) {
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
}

// 세그먼트 클릭 시 해당 시간으로 이동
function seekToSegment(startTime) {
    if (youtubePlayer && youtubePlayer.seekTo) {
        youtubePlayer.seekTo(startTime, true);
        youtubePlayer.playVideo();
    }
}

// 페이지 로드 완료 메시지
console.log('🎬 영상 검색 엔진 v0.1이 준비되었습니다.');
console.log('기능:');
console.log('  - YouTube 영상 다운로드');
console.log('  - MP3 변환');
console.log('  - STT 회의록 생성');
console.log('  - 회의록 요약');
console.log('  - AI 채팅');
console.log('  - 처리 이력 캐싱');
console.log('  - YouTube 플레이어 동기화');
