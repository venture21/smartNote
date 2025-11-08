// ========== 영상 검색 탭 전역 변수 ==========
let videoSessionId = null;
let videoId = null;
let videoSegments = [];
let videoChatHistory = [];
let youtubePlayer = null;
let videoAutoScrollEnabled = true;
let videoTaskId = null;
let videoTitle = null;  // 저장된 제목
let videoProgressInterval = null;

// ========== 오디오 검색 탭 전역 변수 ==========
let audioSessionId = null;
let audioFileHash = null;  // 오디오 파일 해시 (source_id로 사용)
let audioSegments = [];
let audioChatHistory = [];
let audioElement = null;
let audioAutoScrollEnabled = true;
let audioTaskId = null;
let audioProgressInterval = null;
let selectedAudioFile = null;
let audioTitle = null;  // 저장된 제목
let audioFilename = null;  // 백엔드에서 반환된 실제 파일명
let audioTimeUpdateHandler = null;  // 이벤트 핸들러 참조 저장

// ========== Retriever 탭 전역 변수 ==========
let retrieverYoutubePlayer = null;
let retrieverAudioPlayer = null;

// ========== 공통 함수 ==========
function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
}

// ========== 탭 전환 ==========
document.querySelectorAll('.tab-button').forEach(button => {
    button.addEventListener('click', () => {
        const tabId = button.dataset.tab;

        // 모든 탭 버튼 비활성화
        document.querySelectorAll('.tab-button').forEach(btn => {
            btn.classList.remove('active');
        });

        // 모든 탭 컨텐츠 숨김
        document.querySelectorAll('.tab-content').forEach(content => {
            content.classList.remove('active');
        });

        // 선택된 탭 활성화
        button.classList.add('active');
        document.getElementById(tabId).classList.add('active');
    });
});

// ========================================
// 영상 검색 탭 로직
// ========================================

// YouTube 폼 제출
document.getElementById('youtubeForm').addEventListener('submit', async (e) => {
    e.preventDefault();

    const youtubeUrl = document.getElementById('youtubeUrl').value.trim();
    const sttApi = document.getElementById('videoSttApi').value;
    const chunkDuration = parseInt(document.getElementById('videoChunkDuration').value);

    if (!youtubeUrl) {
        alert('YouTube URL을 입력해주세요.');
        return;
    }

    // 버튼 비활성화 및 텍스트 변경
    const submitBtn = document.getElementById('videoSubmitBtn');
    const submitBtnText = document.getElementById('videoSubmitBtnText');
    submitBtn.disabled = true;
    submitBtnText.textContent = '오디오 다운로드 및 텍스트 생성중';

    // 프로그레스 바 초기화 (0%로 리셋)
    document.getElementById('videoDownloadProgress').textContent = '0%';
    document.getElementById('videoDownloadProgressBar').style.width = '0%';
    document.getElementById('videoDownloadMessage').textContent = '대기 중...';
    document.getElementById('videoSttProgress').textContent = '0%';
    document.getElementById('videoSttProgressBar').style.width = '0%';
    document.getElementById('videoSttMessage').textContent = '대기 중...';

    // UI 상태 변경
    document.getElementById('videoUploadStatus').innerHTML = '<p style="color: #666;">처리 중...</p>';
    document.getElementById('videoProgressSection').style.display = 'block';

    try {
        const response = await fetch('/api/process-youtube', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                youtube_url: youtubeUrl,
                stt_api: sttApi,
                chunk_duration: chunkDuration
            })
        });

        const data = await response.json();

        if (data.success) {
            if (data.cached) {
                displayVideoResult(data);
            } else if (data.processing) {
                videoTaskId = data.task_id;
                startVideoProgressPolling();
            }
        } else {
            alert('오류: ' + data.error);
            document.getElementById('videoProgressSection').style.display = 'none';
            // 버튼 재활성화
            submitBtn.disabled = false;
            submitBtnText.textContent = '영상 처리 시작';
        }
    } catch (error) {
        console.error('오류:', error);
        alert('처리 중 오류가 발생했습니다.');
        document.getElementById('videoProgressSection').style.display = 'none';
        // 버튼 재활성화
        const submitBtn = document.getElementById('videoSubmitBtn');
        const submitBtnText = document.getElementById('videoSubmitBtnText');
        submitBtn.disabled = false;
        submitBtnText.textContent = '영상 처리 시작';
    }
});

// 영상 진행 상황 폴링
function startVideoProgressPolling() {
    if (videoProgressInterval) {
        clearInterval(videoProgressInterval);
    }

    videoProgressInterval = setInterval(async () => {
        try {
            const response = await fetch(`/api/progress/${videoTaskId}`);
            const data = await response.json();

            if (data.success) {
                const progress = data.progress;

                if (progress.download) {
                    updateVideoProgress('download', progress.download.progress, progress.download.message, progress.download);
                }

                if (progress.stt) {
                    updateVideoProgress('stt', progress.stt.progress, progress.stt.message, progress.stt);
                }

                if (progress.vectorstore) {
                    updateVideoProgress('vectorstore', progress.vectorstore.progress, progress.vectorstore.message, progress.vectorstore);
                }

                if (progress.completed && progress.result) {
                    clearInterval(videoProgressInterval);
                    // 최종 시간 정보 표시
                    if (progress.stt) {
                        updateVideoProgress('stt', 100, progress.stt.message, progress.stt);
                    }
                    displayVideoResult(progress.result);
                }

                if (progress.error) {
                    clearInterval(videoProgressInterval);
                    alert('오류: ' + progress.error.message);
                    document.getElementById('videoProgressSection').style.display = 'none';
                    // 버튼 재활성화
                    const submitBtn = document.getElementById('videoSubmitBtn');
                    const submitBtnText = document.getElementById('videoSubmitBtnText');
                    submitBtn.disabled = false;
                    submitBtnText.textContent = '영상 처리 시작';
                }
            }
        } catch (error) {
            console.error('진행 상황 조회 오류:', error);
        }
    }, 1000);
}

function updateVideoProgress(type, percent, message, progressData = null) {
    const progressSpan = document.getElementById(`video${type.charAt(0).toUpperCase() + type.slice(1)}Progress`);
    const progressBar = document.getElementById(`video${type.charAt(0).toUpperCase() + type.slice(1)}ProgressBar`);
    const messageDiv = document.getElementById(`video${type.charAt(0).toUpperCase() + type.slice(1)}Message`);

    if (progressSpan) progressSpan.textContent = `${percent}%`;
    if (progressBar) progressBar.style.width = `${percent}%`;

    // 시간 정보 포함 메시지 생성
    if (messageDiv) {
        let fullMessage = message;

        if (progressData && (progressData.estimated_time || progressData.elapsed_time)) {
            const timeInfo = [];

            if (progressData.estimated_time !== undefined) {
                timeInfo.push(`예상: ${Math.round(progressData.estimated_time)}초`);
            }

            if (progressData.elapsed_time !== undefined) {
                timeInfo.push(`경과: ${Math.round(progressData.elapsed_time)}초`);
            }

            if (progressData.remaining_time !== undefined) {
                timeInfo.push(`남음: ${Math.round(progressData.remaining_time)}초`);
            }

            if (timeInfo.length > 0) {
                fullMessage += ` (${timeInfo.join(', ')})`;
            }
        }

        messageDiv.textContent = fullMessage;
    }
}

// 영상 결과 표시
function displayVideoResult(data) {
    videoSessionId = data.session_id;
    videoId = data.video_id;
    videoSegments = data.segments;

    // 버튼 재활성화
    const submitBtn = document.getElementById('videoSubmitBtn');
    const submitBtnText = document.getElementById('videoSubmitBtnText');
    submitBtn.disabled = false;
    submitBtnText.textContent = '영상 처리 시작';

    // 업로드 섹션 숨기기
    document.getElementById('videoUploadSection').style.display = 'none';
    document.getElementById('videoViewerSection').style.display = 'block';

    // 영상 정보 표시
    document.getElementById('videoInfo').innerHTML = `
        <div class="info-row">
            <div class="info-item">
                <strong>제목:</strong> <span>${data.title}</span>
            </div>
        </div>
        <div class="info-row">
            <div class="info-item">
                <strong>채널:</strong> <span>${data.channel}</span>
            </div>
            <div class="info-item">
                <strong>조회수:</strong> <span>${data.view_count.toLocaleString()}</span>
            </div>
            <div class="info-item">
                <strong>업로드 날짜:</strong> <span>${data.upload_date}</span>
            </div>
            <div class="info-item">
                <strong>처리 일시:</strong> <span>${data.created_at}</span>
            </div>
        </div>
    `;

    // YouTube Player 초기화
    if (!youtubePlayer) {
        youtubePlayer = new YT.Player('youtubePlayer', {
            videoId: data.video_id,
            width: '100%',
            height: '400',
            playerVars: {
                'autoplay': 0,
                'controls': 1
            },
            events: {
                'onReady': onYouTubePlayerReady,
                'onStateChange': onYouTubePlayerStateChange
            }
        });
    } else {
        youtubePlayer.loadVideoById(data.video_id);
    }

    // 회의록 표시
    displayVideoTranscript(data.segments);

    // TTS 오디오 초기화 (audio_path가 있는 세그먼트에 대해)
    if (typeof initializeTtsAudio === 'function') {
        initializeTtsAudio('video');
    }

    // 요약 먼저 초기화 (무조건)
    videoRawSummary = '';  // 원본 마크다운 초기화
    document.getElementById('videoSummaryContent').innerHTML = '<p class="summary-placeholder">요약 생성 버튼을 클릭하세요</p>';

    // 요약이 있고 비어있지 않으면 표시
    if (data.summary && data.summary.trim() !== '') {
        videoRawSummary = data.summary;  // 캐시된 원본 마크다운 저장
        document.getElementById('videoSummaryContent').innerHTML = marked.parse(data.summary);
        console.log('[Video] Loaded cached summary and raw markdown.');
    }

    // 채팅 초기화 (새로운 영상이므로)
    document.getElementById('videoChatMessages').innerHTML = `
        <div class="chat-welcome">
            회의록 내용에 대해 질문해보세요!
        </div>
    `;
    videoChatHistory = [];

    // 진행 상황 숨기기
    document.getElementById('videoProgressSection').style.display = 'none';

    console.log('[Video] New video loaded. Summary and chat initialized.');
}

// 영상 회의록 표시
// 영상 세그먼트 자동 정지용
let videoSegmentStopInterval = null;

function displayVideoTranscript(segments, useTranslation = false) {
    const transcriptContent = document.getElementById('videoTranscriptContent');
    transcriptContent.innerHTML = '';

    segments.forEach((segment, idx) => {
        const segmentDiv = document.createElement('div');
        segmentDiv.className = 'transcript-segment';
        segmentDiv.dataset.time = segment.start_time;
        segmentDiv.dataset.id = segment.id;

        // end_time 계산 (다음 세그먼트의 start_time)
        const endTime = idx < segments.length - 1 ? segments[idx + 1].start_time : null;
        if (endTime) {
            segmentDiv.dataset.endTime = endTime;
        }

        const minutes = Math.floor(segment.start_time / 60);
        const seconds = Math.floor(segment.start_time % 60);
        const timeStr = `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;

        // end_time 표시
        let timeRangeStr = timeStr;
        if (endTime) {
            const endMinutes = Math.floor(endTime / 60);
            const endSeconds = Math.floor(endTime % 60);
            const endTimeStr = `${String(endMinutes).padStart(2, '0')}:${String(endSeconds).padStart(2, '0')}`;
            timeRangeStr = `${timeStr} ~ ${endTimeStr}`;
        }

        // 번역된 텍스트가 있으면 사용, 없으면 원본 사용
        const displayText = (useTranslation && segment.translated_text) ? segment.translated_text : segment.text;

        segmentDiv.innerHTML = `
            <div class="segment-header">
                <span class="segment-speaker">화자 ${segment.speaker}</span>
                <span class="segment-time">${timeRangeStr}</span>
            </div>
            <div class="segment-text">${displayText}</div>
        `;

        segmentDiv.addEventListener('click', () => {
            if (youtubePlayer) {
                // 기존 interval 제거
                if (videoSegmentStopInterval) {
                    clearInterval(videoSegmentStopInterval);
                }

                console.log(`[Video] 자동 스크롤 상태: ${videoAutoScrollEnabled ? 'ON' : 'OFF'}, endTime: ${endTime}`);

                // 시작 위치로 이동 후 재생
                youtubePlayer.seekTo(segment.start_time, true);
                youtubePlayer.playVideo();

                // 자동 스크롤 OFF이고 end_time이 있으면 자동 정지 설정
                if (!videoAutoScrollEnabled && endTime) {
                    console.log(`[Video] 자동 정지 설정: ${segment.start_time}s ~ ${endTime}s`);
                    videoSegmentStopInterval = setInterval(() => {
                        const currentTime = youtubePlayer.getCurrentTime();
                        if (currentTime >= endTime) {
                            youtubePlayer.pauseVideo();
                            clearInterval(videoSegmentStopInterval);
                            console.log(`[Video] Auto-stopped at ${endTime}s`);
                        }
                    }, 100);
                } else {
                    console.log(`[Video] 연속 재생 모드 (자동 정지 안 함)`);
                }
            }
        });

        transcriptContent.appendChild(segmentDiv);
    });

    document.getElementById('videoSegmentInfo').textContent = `총 ${segments.length}개 세그먼트`;

    // 원본 언어 표시 및 드랍다운 업데이트
    if (segments.length > 0) {
        const originalLanguage = segments[0].original_language || 'unknown';
        updateVideoLanguageDisplay(originalLanguage);
    }
}

// 언어 표시 및 드랍다운 업데이트
function updateVideoLanguageDisplay(originalLanguage) {
    const languageNames = {
        'ko': '🇰🇷 한국어',
        'en': '🇺🇸 English',
        'ja': '🇯🇵 日本語',
        'de': '🇩🇪 Deutsch',
        'unknown': '❓ Unknown'
    };

    // 원본 언어 표시 (undefined 처리)
    const lang = originalLanguage || 'unknown';
    const languageLabel = document.getElementById('videoOriginalLanguage');
    languageLabel.textContent = `원본:${lang.toUpperCase()}`;

    // 드랍다운에서 현재 언어 옵션 숨기기
    const select = document.getElementById('videoLanguageSelect');
    Array.from(select.options).forEach(option => {
        if (option.value === originalLanguage) {
            option.style.display = 'none';
        } else if (option.value !== 'original') {
            option.style.display = 'block';
        }
    });
}

// 영상 요약 생성
let videoRawSummary = '';  // 원본 마크다운 텍스트 저장용
document.getElementById('videoGenerateSummaryBtn').addEventListener('click', async () => {
    document.getElementById('videoSummaryLoading').style.display = 'block';
    document.getElementById('videoSummaryContent').innerHTML = '';

    try {
        const response = await fetch('/api/summarize', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                segments: videoSegments,
                session_id: videoSessionId,
                title: videoTitle  // 저장된 제목을 요약 생성 시 참조
            })
        });

        const data = await response.json();

        if (data.success) {
            videoRawSummary = data.summary;  // 원본 마크다운 저장 (citation 포함)
            document.getElementById('videoSummaryContent').innerHTML = marked.parse(data.summary);
            console.log('[Video] Raw summary saved for VectorStore');
        } else {
            alert('오류: ' + data.error);
        }
    } catch (error) {
        console.error('오류:', error);
        alert('요약 생성 중 오류가 발생했습니다.');
    } finally {
        document.getElementById('videoSummaryLoading').style.display = 'none';
    }
});

// 영상 채팅 전송
document.getElementById('videoSendChatBtn').addEventListener('click', () => sendVideoChatMessage());
document.getElementById('videoChatInput').addEventListener('keypress', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendVideoChatMessage();
    }
});

async function sendVideoChatMessage() {
    const chatInput = document.getElementById('videoChatInput');
    const message = chatInput.value.trim();

    if (!message) return;

    const chatMessages = document.getElementById('videoChatMessages');
    const userMessageDiv = document.createElement('div');
    userMessageDiv.className = 'chat-message user-message';
    userMessageDiv.innerHTML = `<div class="message-content">${message}</div>`;
    chatMessages.appendChild(userMessageDiv);

    chatInput.value = '';
    chatMessages.scrollTop = chatMessages.scrollHeight;

    document.getElementById('videoChatLoading').style.display = 'block';

    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                message: message,
                segments: videoSegments,
                session_id: videoSessionId,
                chat_history: videoChatHistory
            })
        });

        const data = await response.json();

        if (data.success) {
            const aiMessageDiv = document.createElement('div');
            aiMessageDiv.className = 'chat-message ai-message';
            aiMessageDiv.innerHTML = `<div class="message-content">${marked.parse(data.response)}</div>`;
            chatMessages.appendChild(aiMessageDiv);

            videoChatHistory = data.chat_history;
            chatMessages.scrollTop = chatMessages.scrollHeight;
        } else {
            alert('오류: ' + data.error);
        }
    } catch (error) {
        console.error('오류:', error);
        alert('채팅 중 오류가 발생했습니다.');
    } finally {
        document.getElementById('videoChatLoading').style.display = 'none';
    }
}

// 영상 채팅 초기화
document.getElementById('videoClearChatBtn').addEventListener('click', () => {
    if (confirm('대화 내역을 모두 삭제하시겠습니까?')) {
        document.getElementById('videoChatMessages').innerHTML = `
            <div class="chat-welcome">
                회의록 내용에 대해 질문해보세요!
            </div>
        `;
        videoChatHistory = [];
    }
});

// 영상 제목 저장
document.getElementById('saveVideoTitleBtn').addEventListener('click', () => {
    const title = document.getElementById('videoTitleInput').value.trim();
    const statusDiv = document.getElementById('videoTitleStatus');

    if (!title) {
        statusDiv.innerHTML = '<span style="color: #dc2626;">❌ 제목을 입력해주세요.</span>';
        return;
    }

    // 제목을 변수에 저장
    videoTitle = title;
    statusDiv.innerHTML = '<span style="color: #10b981;">✅ 제목이 저장되었습니다. 요약 생성 및 VectorStore 저장 시 사용됩니다.</span>';

    setTimeout(() => {
        statusDiv.innerHTML = '';
    }, 3000);

    console.log('[Video] 제목 저장됨:', videoTitle);
});

// YouTube VectorStore 저장
document.getElementById('saveVideoToVectorstoreBtn').addEventListener('click', async () => {
    const statusDiv = document.getElementById('videoVectorstoreSaveStatus');
    const saveBtn = document.getElementById('saveVideoToVectorstoreBtn');

    // 유효성 검사
    if (!videoId) {
        statusDiv.innerHTML = '<span style="color: #dc2626;">❌ video_id를 찾을 수 없습니다.</span>';
        return;
    }

    if (videoSegments.length === 0) {
        statusDiv.innerHTML = '<span style="color: #dc2626;">❌ 저장할 세그먼트가 없습니다.</span>';
        return;
    }

    if (!videoTitle) {
        statusDiv.innerHTML = '<span style="color: #dc2626;">❌ 제목을 먼저 저장해주세요.</span>';
        return;
    }

    if (!videoRawSummary || videoRawSummary.trim() === '') {
        statusDiv.innerHTML = '<span style="color: #dc2626;">❌ 요약을 먼저 생성해주세요.</span>';
        return;
    }

    // 버튼 비활성화 및 저장 중 메시지 표시
    saveBtn.disabled = true;
    saveBtn.style.opacity = '0.6';
    saveBtn.style.cursor = 'not-allowed';
    statusDiv.innerHTML = '<span style="color: #666;">💾 VectorStore에 저장중입니다...</span>';
    console.log('[Video] Saving to VectorStore with raw summary (citations preserved)');
    console.log('[Video] Summary length:', videoRawSummary ? videoRawSummary.length : 0);
    console.log('[Video] Summary preview:', videoRawSummary ? videoRawSummary.substring(0, 200) : 'EMPTY');

    try {
        const payload = {
            source_id: videoId,
            source_type: 'youtube',
            segments: videoSegments,
            title: videoTitle,
            summary: videoRawSummary  // 원본 마크다운 사용 (citation 포함)
        };
        console.log('[Video] Payload summary included:', !!payload.summary);

        const response = await fetch('/api/save-to-vectorstore', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(payload)
        });

        const data = await response.json();

        if (data.success) {
            statusDiv.innerHTML = `<span style="color: #10b981;">✅ ${data.message}</span>`;
            setTimeout(() => {
                statusDiv.innerHTML = '';
            }, 5000);
        } else {
            statusDiv.innerHTML = `<span style="color: #dc2626;">❌ ${data.error}</span>`;
        }
    } catch (error) {
        console.error('VectorStore 저장 오류:', error);
        statusDiv.innerHTML = '<span style="color: #dc2626;">❌ VectorStore 저장 중 오류가 발생했습니다.</span>';
    } finally {
        // 버튼 재활성화
        saveBtn.disabled = false;
        saveBtn.style.opacity = '1';
        saveBtn.style.cursor = 'pointer';
    }
});

// 영상 변경
document.getElementById('changeVideoBtn').addEventListener('click', () => {
    if (confirm('현재 작업을 종료하고 새로운 영상을 처리하시겠습니까?')) {
        // 뷰어 섹션 숨기고 업로드 섹션 표시
        document.getElementById('videoViewerSection').style.display = 'none';
        document.getElementById('videoUploadSection').style.display = 'block';
        document.getElementById('youtubeUrl').value = '';

        // 요약 초기화
        document.getElementById('videoSummaryContent').innerHTML = '<p class="summary-placeholder">요약 생성 버튼을 클릭하세요</p>';

        // 채팅 초기화
        document.getElementById('videoChatMessages').innerHTML = `
            <div class="chat-welcome">
                회의록 내용에 대해 질문해보세요!
            </div>
        `;
        videoChatHistory = [];

        // 회의록 초기화
        document.getElementById('videoTranscriptContent').innerHTML = '';
        videoSegments = [];
        videoSessionId = null;
        videoId = null;

        // YouTube Player 정리
        if (videoHighlightInterval) {
            clearInterval(videoHighlightInterval);
            videoHighlightInterval = null;
        }

        console.log('[Video] Session cleared. Ready for new video.');
    }
});

// 영상 자동 스크롤 토글
document.getElementById('videoAutoScrollToggle').addEventListener('click', function() {
    videoAutoScrollEnabled = !videoAutoScrollEnabled;
    this.classList.toggle('active');
    this.textContent = videoAutoScrollEnabled ? '자동 스크롤: ON' : '자동 스크롤: OFF';
    console.log(`[Video] 자동 스크롤 토글: ${videoAutoScrollEnabled ? 'ON' : 'OFF'}`);
});

// 영상 언어 선택 - 원본 선택 시 즉시 복원
document.getElementById('videoLanguageSelect').addEventListener('change', function() {
    const selectedLanguage = this.value;

    // 원본 언어 선택 시
    if (selectedLanguage === 'original') {
        // 원본 세그먼트로 복원
        displayVideoTranscript(videoSegments);
        // 언어 표시도 원본으로 복원
        if (videoSegments.length > 0) {
            updateVideoLanguageDisplay(videoSegments[0].original_language || 'unknown');
        }
    }
});

// 영상 번역 버튼 클릭
document.getElementById('videoTranslateBtn').addEventListener('click', async function() {
    const selectElement = document.getElementById('videoLanguageSelect');
    const selectedLanguage = selectElement.value;

    console.log(`[Video] 번역 버튼 클릭 - 선택된 언어: ${selectedLanguage}`);
    console.log(`[Video] videoId: ${videoId}, segments: ${videoSegments ? videoSegments.length : 0}`);

    if (!videoId || !videoSegments || videoSegments.length === 0) {
        console.warn('[Video] 번역할 세그먼트가 없습니다.');
        alert('번역할 영상이 없습니다. 먼저 영상을 처리해주세요.');
        return;
    }

    // 원본 언어 선택 시
    if (selectedLanguage === 'original') {
        alert('번역할 언어를 선택해주세요.');
        return;
    }

    // 버튼 비활성화 및 텍스트 변경
    const originalBtnText = this.textContent;
    this.textContent = '번역 중...';
    this.disabled = true;
    this.style.opacity = '0.6';
    this.style.cursor = 'not-allowed';

    // 번역 요청
    try {
        const requestBody = {
            data_type: 'youtube',
            data_id: videoId,
            target_language: selectedLanguage,
            source_language: videoSegments[0]?.original_language || 'unknown'
        };
        console.log('[Video] 번역 요청:', requestBody);

        const response = await fetch('/api/translate', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(requestBody)
        });

        console.log('[Video] 응답 상태:', response.status);
        const data = await response.json();
        console.log('[Video] 응답 데이터:', data);

        if (data.success) {
            console.log(`[Video] 번역 완료: ${data.segments.length}개 세그먼트`);

            // 번역 통계 확인
            if (data.stats) {
                console.log(`[Video] 번역 통계: 성공 ${data.stats.success}개, 실패 ${data.stats.failed}개`);

                // 실패한 세그먼트가 있으면 경고 표시
                if (data.stats.failed > 0) {
                    alert(`⚠️ 번역이 부분적으로 완료되었습니다.\n\n` +
                          `성공: ${data.stats.success}개\n` +
                          `실패: ${data.stats.failed}개\n\n` +
                          `실패한 세그먼트는 원본 텍스트로 표시됩니다.`);
                }
            }

            // 번역된 세그먼트로 videoSegments 배열 업데이트
            videoSegments = data.segments;

            // 번역된 세그먼트로 화면 업데이트
            displayVideoTranscript(data.segments, true);

            // 언어 표시 업데이트 (번역된 언어 표시)
            const languageNames = {
                'ko': '🇰🇷 한국어',
                'en': '🇺🇸 English',
                'ja': '🇯🇵 日本語',
                'de': '🇩🇪 Deutsch',
                'unknown': '❓ Unknown'
            };
            const originalLang = data.segments[0]?.original_language || 'unknown';
            document.getElementById('videoOriginalLanguage').textContent =
                `원본:${originalLang.toUpperCase()} → 번역:${selectedLanguage.toUpperCase()}`;

            // 번역 완료 후 세그먼트를 다시 로드하여 번역 데이터와 audio_path 포함
            console.log('[Video] 번역 완료 후 세그먼트 재로드 (번역 데이터 및 audio_path 포함)');
            try {
                const segmentResponse = await fetch(`/api/get-segments?data_type=youtube&data_id=${videoId}&language=${selectedLanguage}`);
                const segmentData = await segmentResponse.json();

                if (segmentData.success) {
                    videoSegments = segmentData.segments;
                    console.log('[Video] 세그먼트 재로드 완료:', videoSegments.length);
                    console.log('[Video] 번역 데이터 있는 세그먼트:', videoSegments.filter(s => s.translated_text).length);
                    console.log('[Video] audio_path 있는 세그먼트:', videoSegments.filter(s => s.audio_path).length);

                    // TTS 오디오 초기화
                    if (typeof initializeTtsAudio === 'function') {
                        initializeTtsAudio('video');
                    }
                } else {
                    console.error('[Video] 세그먼트 재로드 실패:', segmentData.error);
                }
            } catch (reloadError) {
                console.error('[Video] 세그먼트 재로드 오류:', reloadError);
            }
        } else {
            console.error('[Video] 번역 오류:', data.error);
            alert('번역 중 오류가 발생했습니다: ' + data.error);
        }
    } catch (error) {
        console.error('[Video] 번역 API 오류:', error);
        console.error('[Video] 에러 스택:', error.stack);
        alert('번역 API 호출 중 오류가 발생했습니다: ' + error.message);
    } finally {
        // 버튼 다시 활성화
        this.textContent = originalBtnText;
        this.disabled = false;
        this.style.opacity = '1';
        this.style.cursor = 'pointer';
    }
});

// ========== TTS 생성 버튼 (Video) ==========
document.getElementById('videoGenerateTtsBtn').addEventListener('click', async function() {
    console.log(`[Video] TTS 생성 버튼 클릭`);
    console.log(`[Video] videoId: ${videoId}, segments: ${videoSegments ? videoSegments.length : 0}`);

    if (!videoId || !videoSegments || videoSegments.length === 0) {
        console.warn('[Video] TTS 생성할 세그먼트가 없습니다.');
        alert('TTS 생성할 영상이 없습니다. 먼저 영상을 처리해주세요.');
        return;
    }

    // 현재 선택된 언어 가져오기 (먼저 선언)
    const selectElement = document.getElementById('videoLanguageSelect');
    const selectedLanguage = selectElement.value;

    // 현재 선택된 언어의 번역이 있는지 확인
    const hasTranslationForSelectedLanguage = videoSegments.some(seg => {
        // 선택된 언어와 translated_language가 일치하고, translated_text가 있는지 확인
        return seg.translated_language === selectedLanguage &&
               seg.translated_text &&
               seg.translated_text.trim() !== '';
    });

    if (!hasTranslationForSelectedLanguage) {
        alert(`번역된 텍스트가 없습니다.\n\n현재 선택된 언어: ${selectedLanguage}\n\n먼저 해당 언어로 번역을 수행해주세요.`);
        return;
    }

    // 버튼 비활성화 및 텍스트 변경
    const originalBtnText = this.textContent;
    this.textContent = 'TTS 생성 중...';
    this.disabled = true;
    this.style.opacity = '0.6';
    this.style.cursor = 'not-allowed';

    if (!selectedLanguage || selectedLanguage === 'original') {
        alert('번역된 언어를 선택해주세요. 원본 언어로는 TTS를 생성할 수 없습니다.');
        this.textContent = originalBtnText;
        this.disabled = false;
        this.style.opacity = '1';
        this.style.cursor = 'pointer';
        return;
    }

    // TTS 생성 요청
    try {
        const requestBody = {
            data_type: 'youtube',
            data_id: videoId,
            target_language: selectedLanguage
        };
        console.log('[Video] TTS 생성 요청:', requestBody);

        const response = await fetch('/api/generate-tts', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(requestBody)
        });

        console.log('[Video] 응답 상태:', response.status);
        const data = await response.json();
        console.log('[Video] 응답 데이터:', data);

        if (data.success) {
            console.log(`[Video] TTS 생성 시작: task_id=${data.task_id}`);
            alert('TTS 오디오 생성이 시작되었습니다. 진행 상황은 콘솔에서 확인하세요.');

            // 진행 상황 폴링 시작
            pollTtsProgress(data.task_id, 'video', this, originalBtnText);
        } else {
            console.error('[Video] TTS 생성 오류:', data.error);
            alert('TTS 생성 중 오류가 발생했습니다: ' + data.error);
            this.textContent = originalBtnText;
            this.disabled = false;
            this.style.opacity = '1';
            this.style.cursor = 'pointer';
        }
    } catch (error) {
        console.error('[Video] TTS 생성 API 오류:', error);
        alert('TTS 생성 API 호출 중 오류가 발생했습니다: ' + error.message);
        this.textContent = originalBtnText;
        this.disabled = false;
        this.style.opacity = '1';
        this.style.cursor = 'pointer';
    }
});

// TTS 생성 진행 상황 폴링
function pollTtsProgress(taskId, dataType, button, originalBtnText) {
    const pollInterval = setInterval(async () => {
        try {
            const response = await fetch(`/api/progress/${taskId}`);
            const data = await response.json();

            if (data.success && data.progress && data.progress.tts) {
                const tts = data.progress.tts;
                console.log(`[TTS Progress] ${tts.progress}% - ${tts.message}`);
                button.textContent = `TTS 생성 중... ${tts.progress}%`;

                // 완료 확인
                if (data.progress.completed) {
                    clearInterval(pollInterval);

                    if (data.progress.result && data.progress.result.success) {
                        console.log(`[TTS] 생성 완료!`, data.progress.result);
                        alert(`TTS 오디오 생성 완료!\n\n` +
                              `성공: ${data.progress.result.success_count}개\n` +
                              `건너뜀: ${data.progress.result.skip_count}개\n` +
                              `실패: ${data.progress.result.fail_count}개`);

                        // 세그먼트 다시 로드 (audio_path 포함)
                        if (dataType === 'video') {
                            reloadVideoSegments();
                        } else {
                            reloadAudioSegments();
                        }
                    } else {
                        console.error('[TTS] 생성 실패:', data.progress.result);
                        alert('TTS 생성 중 오류가 발생했습니다.');
                    }

                    button.textContent = originalBtnText;
                    button.disabled = false;
                    button.style.opacity = '1';
                    button.style.cursor = 'pointer';
                }
            }
        } catch (error) {
            console.error('[TTS Progress] 폴링 오류:', error);
            clearInterval(pollInterval);
            button.textContent = originalBtnText;
            button.disabled = false;
            button.style.opacity = '1';
            button.style.cursor = 'pointer';
        }
    }, 1000); // 1초마다 폴링
}

// 세그먼트 다시 로드 (audio_path 포함)
async function reloadVideoSegments() {
    try {
        const response = await fetch(`/api/get-segments?data_type=youtube&data_id=${videoId}`);
        const data = await response.json();

        if (data.success) {
            videoSegments = data.segments;
            console.log('[Video] 세그먼트 다시 로드 완료:', videoSegments.length);

            // TTS 오디오 초기화
            initializeTtsAudio('video');
        }
    } catch (error) {
        console.error('[Video] 세그먼트 다시 로드 오류:', error);
    }
}

async function reloadAudioSegments() {
    try {
        const response = await fetch(`/api/get-segments?data_type=audio&data_id=${audioFileHash}`);
        const data = await response.json();

        if (data.success) {
            audioSegments = data.segments;
            console.log('[Audio] 세그먼트 다시 로드 완료:', audioSegments.length);

            // TTS 오디오 초기화
            initializeTtsAudio('audio');
        }
    } catch (error) {
        console.error('[Audio] 세그먼트 다시 로드 오류:', error);
    }
}

// YouTube 플레이어 이벤트 핸들러
let videoHighlightInterval = null;

function onYouTubePlayerReady(event) {
    // 플레이어가 준비되었을 때 재생 속도를 1.0으로 설정
    event.target.setPlaybackRate(1.0);
    console.log('[Video] YouTube 플레이어 재생 속도: 1.0x');
}

function onYouTubePlayerStateChange(event) {
    // 재생 중일 때만 하이라이트 업데이트
    if (event.data === YT.PlayerState.PLAYING) {
        console.log('[Video] Player started playing. Starting highlight updates.');
        if (videoHighlightInterval) {
            clearInterval(videoHighlightInterval);
        }
        videoHighlightInterval = setInterval(() => {
            if (youtubePlayer && youtubePlayer.getCurrentTime) {
                const currentTime = youtubePlayer.getCurrentTime();
                console.log('[Video] Current time:', currentTime.toFixed(2), 's');
                highlightCurrentVideoSegment(currentTime);
            }
        }, 100); // 100ms마다 업데이트
    } else {
        // 일시정지, 정지 등
        console.log('[Video] Player paused/stopped. Stopping highlight updates.');
        if (videoHighlightInterval) {
            clearInterval(videoHighlightInterval);
            videoHighlightInterval = null;
        }
    }
}

// 영상 재생 시간에 따라 현재 세그먼트 하이라이트
function highlightCurrentVideoSegment(currentTime) {
    if (!videoSegments || videoSegments.length === 0) {
        console.warn('[Video Highlight] No video segments available');
        return;
    }

    // 현재 시간에 해당하는 세그먼트 찾기
    let currentSegment = null;
    for (let i = 0; i < videoSegments.length; i++) {
        const segment = videoSegments[i];
        const nextSegment = videoSegments[i + 1];

        if (nextSegment) {
            if (currentTime >= segment.start_time && currentTime < nextSegment.start_time) {
                currentSegment = segment;
                break;
            }
        } else {
            if (currentTime >= segment.start_time) {
                currentSegment = segment;
                break;
            }
        }
    }

    if (currentSegment) {
        console.log('[Video Highlight] Found segment:', {
            id: currentSegment.id,
            speaker: currentSegment.speaker,
            start_time: currentSegment.start_time
        });

        // 모든 세그먼트에서 active-audio 클래스 제거
        const allSegments = document.querySelectorAll('#videoTranscriptContent .transcript-segment');
        allSegments.forEach(seg => seg.classList.remove('active-audio'));

        // 현재 세그먼트에 active-audio 클래스 추가
        const currentSegmentElement = document.querySelector(
            `#videoTranscriptContent .transcript-segment[data-id="${currentSegment.id}"]`
        );

        if (currentSegmentElement) {
            console.log('[Video Highlight] ✅ Adding active-audio to segment ID:', currentSegment.id);
            currentSegmentElement.classList.add('active-audio');

            // 자동 스크롤이 활성화되어 있으면 회의록 컨테이너 내부에서만 스크롤
            if (videoAutoScrollEnabled) {
                const transcriptContainer = document.getElementById('videoTranscriptContent');

                // 더 정확한 위치 계산을 위해 getBoundingClientRect 사용
                const containerRect = transcriptContainer.getBoundingClientRect();
                const elementRect = currentSegmentElement.getBoundingClientRect();

                // 컨테이너 기준 상대 위치 계산
                const relativeTop = elementRect.top - containerRect.top + transcriptContainer.scrollTop;
                const containerHeight = transcriptContainer.clientHeight;
                const elementHeight = currentSegmentElement.offsetHeight;

                // 요소를 컨테이너 중앙에 위치시키기
                const scrollTo = relativeTop - (containerHeight / 2) + (elementHeight / 2);

                transcriptContainer.scrollTo({
                    top: scrollTo,
                    behavior: 'smooth'
                });

                console.log('[Video Highlight] Container height:', containerHeight, 'Element relative top:', relativeTop, 'Scrolling to:', scrollTo);
            }
        } else {
            console.error('[Video Highlight] ❌ Could not find segment element with data-id:', currentSegment.id);
        }
    }
}

// ========================================
// 오디오 검색 탭 로직
// ========================================

// 파일 업로드 영역
const fileUploadArea = document.getElementById('fileUploadArea');
const audioFileInput = document.getElementById('audioFileInput');
const fileInfo = document.getElementById('fileInfo');
const audioSubmitBtn = document.getElementById('audioSubmitBtn');

fileUploadArea.addEventListener('click', () => {
    audioFileInput.click();
});

fileUploadArea.addEventListener('dragover', (e) => {
    e.preventDefault();
    fileUploadArea.classList.add('drag-over');
});

fileUploadArea.addEventListener('dragleave', () => {
    fileUploadArea.classList.remove('drag-over');
});

fileUploadArea.addEventListener('drop', (e) => {
    e.preventDefault();
    fileUploadArea.classList.remove('drag-over');

    const files = e.dataTransfer.files;
    if (files.length > 0) {
        handleFileSelect(files[0]);
    }
});

audioFileInput.addEventListener('change', (e) => {
    const files = e.target.files;
    if (files.length > 0) {
        handleFileSelect(files[0]);
    }
});

function handleFileSelect(file) {
    selectedAudioFile = file;

    document.getElementById('fileName').textContent = file.name;
    document.getElementById('fileSize').textContent = formatFileSize(file.size);
    document.getElementById('fileType').textContent = file.type || '알 수 없음';
    fileInfo.classList.add('show');

    audioSubmitBtn.disabled = false;
}

// 오디오 폼 제출
document.getElementById('audioForm').addEventListener('submit', async (e) => {
    e.preventDefault();

    if (!selectedAudioFile) {
        alert('오디오 파일을 선택해주세요.');
        return;
    }

    const sttApi = document.getElementById('audioSttApi').value;
    const chunkDuration = parseInt(document.getElementById('audioChunkDuration').value);

    const formData = new FormData();
    formData.append('audio_file', selectedAudioFile);
    formData.append('stt_api', sttApi);
    formData.append('chunk_duration', chunkDuration);

    document.getElementById('audioUploadStatus').innerHTML = '<p style="color: #666;">처리 중...</p>';
    document.getElementById('audioProgressSection').style.display = 'block';
    audioSubmitBtn.disabled = true;
    audioSubmitBtn.innerHTML = '<span class="btn-icon">⏳</span>오디오에서 텍스트 추출중';

    try {
        const response = await fetch('/api/process-audio', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        if (data.success) {
            if (data.cached) {
                displayAudioResult(data);
            } else if (data.processing) {
                audioTaskId = data.task_id;
                const estimatedTime = data.estimated_time || 60; // 기본값 60초
                startAudioProgressPolling(estimatedTime);
            }
        } else {
            alert('오류: ' + data.error);
            document.getElementById('audioProgressSection').style.display = 'none';
            audioSubmitBtn.disabled = false;
            audioSubmitBtn.innerHTML = '<span class="btn-icon">🎤</span>오디오 처리 시작';
        }
    } catch (error) {
        console.error('오류:', error);
        alert('처리 중 오류가 발생했습니다.');
        document.getElementById('audioProgressSection').style.display = 'none';
        audioSubmitBtn.disabled = false;
        audioSubmitBtn.innerHTML = '<span class="btn-icon">🎤</span>오디오 처리 시작';
    }
});

// 오디오 진행 상황 폴링 (예상 시간 기반 프로그레스 바)
function startAudioProgressPolling(estimatedTime) {
    if (audioProgressInterval) {
        clearInterval(audioProgressInterval);
    }

    // 예상 시간 기반 프로그레스 바 업데이트
    const startTime = Date.now();
    const updateInterval = 200; // 200ms마다 업데이트
    let simulatedProgress = 0;

    // 시뮬레이션 타이머 (프로그레스 바를 부드럽게 증가)
    const simulationInterval = setInterval(() => {
        const elapsed = (Date.now() - startTime) / 1000; // 경과 시간 (초)
        simulatedProgress = Math.min(95, (elapsed / estimatedTime) * 100); // 최대 95%까지만

        updateAudioProgress('stt', Math.round(simulatedProgress), '오디오에서 텍스트 추출중...');
    }, updateInterval);

    // 실제 진행 상황 폴링 (서버에서 완료 신호 확인)
    audioProgressInterval = setInterval(async () => {
        try {
            const response = await fetch(`/api/progress/${audioTaskId}`);
            const data = await response.json();

            if (data.success) {
                const progress = data.progress;

                // 실제 서버에서 진행 상황이 오면 해당 값 사용
                if (progress.stt && progress.stt.progress > 0) {
                    clearInterval(simulationInterval); // 시뮬레이션 중지
                    updateAudioProgress('stt', progress.stt.progress, progress.stt.message, progress.stt);
                }

                if (progress.vectorstore) {
                    updateAudioProgress('vectorstore', progress.vectorstore.progress, progress.vectorstore.message, progress.vectorstore);
                }

                if (progress.completed && progress.result) {
                    clearInterval(audioProgressInterval);
                    clearInterval(simulationInterval);
                    // 최종 시간 정보 표시
                    const finalMessage = progress.stt ? progress.stt.message : 'STT 완료';
                    updateAudioProgress('stt', 100, finalMessage, progress.stt);
                    displayAudioResult(progress.result);
                }

                if (progress.error) {
                    clearInterval(audioProgressInterval);
                    clearInterval(simulationInterval);
                    alert('오류: ' + progress.error.message);
                    document.getElementById('audioProgressSection').style.display = 'none';
                    audioSubmitBtn.disabled = false;
                    audioSubmitBtn.innerHTML = '<span class="btn-icon">🎤</span>오디오 처리 시작';
                }
            }
        } catch (error) {
            console.error('진행 상황 조회 오류:', error);
        }
    }, 1000);
}

function updateAudioProgress(type, percent, message, progressData = null) {
    const progressSpan = document.getElementById(`audio${type.charAt(0).toUpperCase() + type.slice(1)}Progress`);
    const progressBar = document.getElementById(`audio${type.charAt(0).toUpperCase() + type.slice(1)}ProgressBar`);
    const messageDiv = document.getElementById(`audio${type.charAt(0).toUpperCase() + type.slice(1)}Message`);

    if (progressSpan) progressSpan.textContent = `${percent}%`;
    if (progressBar) progressBar.style.width = `${percent}%`;

    // 시간 정보 포함 메시지 생성
    if (messageDiv) {
        let fullMessage = message;

        if (progressData && (progressData.estimated_time || progressData.elapsed_time)) {
            const timeInfo = [];

            if (progressData.estimated_time !== undefined) {
                timeInfo.push(`예상: ${Math.round(progressData.estimated_time)}초`);
            }

            if (progressData.elapsed_time !== undefined) {
                timeInfo.push(`경과: ${Math.round(progressData.elapsed_time)}초`);
            }

            if (progressData.remaining_time !== undefined) {
                timeInfo.push(`남음: ${Math.round(progressData.remaining_time)}초`);
            }

            if (timeInfo.length > 0) {
                fullMessage += ` (${timeInfo.join(', ')})`;
            }
        }

        messageDiv.textContent = fullMessage;
    }
}

// 오디오 결과 표시
function displayAudioResult(data) {
    audioSessionId = data.session_id;
    audioFileHash = data.file_hash;  // 파일 해시 저장
    audioFilename = data.filename;  // 백엔드에서 반환된 실제 파일명 저장
    audioSegments = data.segments;

    // 업로드 섹션 숨기기
    document.getElementById('audioUploadSection').style.display = 'none';
    document.getElementById('audioViewerSection').style.display = 'block';

    // 오디오 정보 표시
    const audioDurationMin = Math.floor(data.audio_duration / 60);
    const audioDurationSec = Math.floor(data.audio_duration % 60);
    const audioDurationStr = `${audioDurationMin}분 ${audioDurationSec}초`;

    document.getElementById('audioContentInfo').innerHTML = `
        <div class="info-row">
            <div class="info-item">
                <strong>파일명:</strong> <span>${data.filename}</span>
            </div>
        </div>
        <div class="info-row">
            <div class="info-item">
                <strong>파일 크기:</strong> <span>${formatFileSize(data.file_size)}</span>
            </div>
            <div class="info-item">
                <strong>오디오 길이:</strong> <span>${audioDurationStr}</span>
            </div>
            <div class="info-item">
                <strong>처리 일시:</strong> <span>${data.created_at}</span>
            </div>
            <div class="info-item">
                <strong>STT 처리 시간:</strong> <span>${data.stt_processing_time.toFixed(2)}초</span>
            </div>
        </div>
    `;

    // 오디오 플레이어 설정
    const audioPath = data.file_path.replace(/\\/g, '/');
    const audioUrl = `/uploads/${audioPath.split('/').pop()}`;

    audioElement = document.getElementById('audioPlayer');
    audioElement.src = audioUrl;

    // 기존 이벤트 리스너 제거 (중복 방지)
    if (audioTimeUpdateHandler) {
        audioElement.removeEventListener('timeupdate', audioTimeUpdateHandler);
    }

    // 새로운 이벤트 핸들러 정의
    audioTimeUpdateHandler = () => {
        const currentTime = audioElement.currentTime;
        console.log('[Audio] Current time:', currentTime.toFixed(2), 's');
        highlightCurrentAudioSegment(currentTime);
    };

    // 오디오 재생 시간에 따라 대화 하이라이트
    audioElement.addEventListener('timeupdate', audioTimeUpdateHandler);
    console.log('[Audio] Event listener attached. Total segments:', audioSegments.length);

    // 회의록 표시
    displayAudioTranscript(data.segments);

    // TTS 오디오 초기화 (audio_path가 있는 세그먼트에 대해)
    if (typeof initializeTtsAudio === 'function') {
        initializeTtsAudio('audio');
    }

    // 요약 먼저 초기화 (무조건)
    audioRawSummary = '';  // 원본 마크다운 초기화
    document.getElementById('audioSummaryContent').innerHTML = '<p class="summary-placeholder">요약 생성 버튼을 클릭하세요</p>';

    // 요약이 있고 비어있지 않으면 표시
    if (data.summary && data.summary.trim() !== '') {
        audioRawSummary = data.summary;  // 캐시된 원본 마크다운 저장
        document.getElementById('audioSummaryContent').innerHTML = marked.parse(data.summary);
        console.log('[Audio] Loaded cached summary and raw markdown.');
    }

    // 채팅 초기화 (새로운 오디오이므로)
    document.getElementById('audioChatMessages').innerHTML = `
        <div class="chat-welcome">
            회의록 내용에 대해 질문해보세요!
        </div>
    `;
    audioChatHistory = [];

    // 진행 상황 숨기기
    document.getElementById('audioProgressSection').style.display = 'none';
    audioSubmitBtn.disabled = false;
    audioSubmitBtn.innerHTML = '<span class="btn-icon">🎤</span>오디오 처리 시작';

    console.log('[Audio] New audio loaded. Summary and chat initialized.');
}

// 오디오 회의록 표시
// 오디오 세그먼트 자동 정지용
let audioSegmentStopListener = null;

function displayAudioTranscript(segments, useTranslation = false) {
    const transcriptContent = document.getElementById('audioTranscriptContent');
    transcriptContent.innerHTML = '';

    segments.forEach((segment, idx) => {
        const segmentDiv = document.createElement('div');
        segmentDiv.className = 'transcript-segment';
        segmentDiv.dataset.time = segment.start_time;
        segmentDiv.dataset.id = segment.id;

        // end_time 계산 (다음 세그먼트의 start_time)
        const endTime = idx < segments.length - 1 ? segments[idx + 1].start_time : null;
        if (endTime) {
            segmentDiv.dataset.endTime = endTime;
        }

        const minutes = Math.floor(segment.start_time / 60);
        const seconds = Math.floor(segment.start_time % 60);
        const timeStr = `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;

        // end_time 표시
        let timeRangeStr = timeStr;
        if (endTime) {
            const endMinutes = Math.floor(endTime / 60);
            const endSeconds = Math.floor(endTime % 60);
            const endTimeStr = `${String(endMinutes).padStart(2, '0')}:${String(endSeconds).padStart(2, '0')}`;
            timeRangeStr = `${timeStr} ~ ${endTimeStr}`;
        }

        // 번역된 텍스트가 있으면 사용, 없으면 원본 사용
        const displayText = (useTranslation && segment.translated_text) ? segment.translated_text : segment.text;

        segmentDiv.innerHTML = `
            <div class="segment-header">
                <span class="segment-speaker">화자 ${segment.speaker}</span>
                <span class="segment-time">${timeRangeStr}</span>
            </div>
            <div class="segment-text">${displayText}</div>
        `;

        segmentDiv.addEventListener('click', () => {
            if (audioElement) {
                // 기존 listener 제거
                if (audioSegmentStopListener) {
                    audioElement.removeEventListener('timeupdate', audioSegmentStopListener);
                }

                console.log(`[Audio] 자동 스크롤 상태: ${audioAutoScrollEnabled ? 'ON' : 'OFF'}, endTime: ${endTime}`);

                // 시작 위치로 이동 후 재생
                audioElement.currentTime = segment.start_time;
                audioElement.play();

                // 자동 스크롤 OFF이고 end_time이 있으면 자동 정지 설정
                if (!audioAutoScrollEnabled && endTime) {
                    console.log(`[Audio] 자동 정지 설정: ${segment.start_time}s ~ ${endTime}s`);
                    audioSegmentStopListener = function() {
                        if (audioElement.currentTime >= endTime) {
                            audioElement.pause();
                            console.log(`[Audio] Auto-stopped at ${endTime}s`);
                        }
                    };
                    audioElement.addEventListener('timeupdate', audioSegmentStopListener);
                } else {
                    console.log(`[Audio] 연속 재생 모드 (자동 정지 안 함)`);
                }
            }
        });

        transcriptContent.appendChild(segmentDiv);
    });

    document.getElementById('audioSegmentInfo').textContent = `총 ${segments.length}개 세그먼트`;

    // 원본 언어 표시 및 드랍다운 업데이트
    if (segments.length > 0) {
        const originalLanguage = segments[0].original_language || 'unknown';
        updateAudioLanguageDisplay(originalLanguage);
    }
}

// 언어 표시 및 드랍다운 업데이트
function updateAudioLanguageDisplay(originalLanguage) {
    const languageNames = {
        'ko': '🇰🇷 한국어',
        'en': '🇺🇸 English',
        'ja': '🇯🇵 日本語',
        'de': '🇩🇪 Deutsch',
        'unknown': '❓ Unknown'
    };

    // 원본 언어 표시 (undefined 처리)
    const lang = originalLanguage || 'unknown';
    const languageLabel = document.getElementById('audioOriginalLanguage');
    languageLabel.textContent = `원본:${lang.toUpperCase()}`;

    // 드랍다운에서 현재 언어 옵션 숨기기
    const select = document.getElementById('audioLanguageSelect');
    Array.from(select.options).forEach(option => {
        if (option.value === originalLanguage) {
            option.style.display = 'none';
        } else if (option.value !== 'original') {
            option.style.display = 'block';
        }
    });
}

// 오디오 요약 생성
let audioRawSummary = '';  // 원본 마크다운 텍스트 저장용
document.getElementById('audioGenerateSummaryBtn').addEventListener('click', async () => {
    document.getElementById('audioSummaryLoading').style.display = 'block';
    document.getElementById('audioSummaryContent').innerHTML = '';

    try {
        const response = await fetch('/api/summarize', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                segments: audioSegments,
                session_id: audioSessionId,
                title: audioTitle  // 저장된 제목을 요약 생성 시 참조
            })
        });

        const data = await response.json();

        if (data.success) {
            audioRawSummary = data.summary;  // 원본 마크다운 저장 (citation 포함)
            document.getElementById('audioSummaryContent').innerHTML = marked.parse(data.summary);
            console.log('[Audio] Raw summary saved for VectorStore');
        } else {
            alert('오류: ' + data.error);
        }
    } catch (error) {
        console.error('오류:', error);
        alert('요약 생성 중 오류가 발생했습니다.');
    } finally {
        document.getElementById('audioSummaryLoading').style.display = 'none';
    }
});

// 오디오 채팅 전송
document.getElementById('audioSendChatBtn').addEventListener('click', () => sendAudioChatMessage());
document.getElementById('audioChatInput').addEventListener('keypress', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendAudioChatMessage();
    }
});

async function sendAudioChatMessage() {
    const chatInput = document.getElementById('audioChatInput');
    const message = chatInput.value.trim();

    if (!message) return;

    const chatMessages = document.getElementById('audioChatMessages');
    const userMessageDiv = document.createElement('div');
    userMessageDiv.className = 'chat-message user-message';
    userMessageDiv.innerHTML = `<div class="message-content">${message}</div>`;
    chatMessages.appendChild(userMessageDiv);

    chatInput.value = '';
    chatMessages.scrollTop = chatMessages.scrollHeight;

    document.getElementById('audioChatLoading').style.display = 'block';

    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                message: message,
                segments: audioSegments,
                session_id: audioSessionId,
                chat_history: audioChatHistory
            })
        });

        const data = await response.json();

        if (data.success) {
            const aiMessageDiv = document.createElement('div');
            aiMessageDiv.className = 'chat-message ai-message';
            aiMessageDiv.innerHTML = `<div class="message-content">${marked.parse(data.response)}</div>`;
            chatMessages.appendChild(aiMessageDiv);

            audioChatHistory = data.chat_history;
            chatMessages.scrollTop = chatMessages.scrollHeight;
        } else {
            alert('오류: ' + data.error);
        }
    } catch (error) {
        console.error('오류:', error);
        alert('채팅 중 오류가 발생했습니다.');
    } finally {
        document.getElementById('audioChatLoading').style.display = 'none';
    }
}

// 오디오 채팅 초기화
document.getElementById('audioClearChatBtn').addEventListener('click', () => {
    if (confirm('대화 내역을 모두 삭제하시겠습니까?')) {
        document.getElementById('audioChatMessages').innerHTML = `
            <div class="chat-welcome">
                회의록 내용에 대해 질문해보세요!
            </div>
        `;
        audioChatHistory = [];
    }
});

// 오디오 제목 저장
document.getElementById('saveAudioTitleBtn').addEventListener('click', () => {
    const title = document.getElementById('audioTitleInput').value.trim();
    const statusDiv = document.getElementById('audioTitleStatus');

    if (!title) {
        statusDiv.innerHTML = '<span style="color: #dc2626;">❌ 제목을 입력해주세요.</span>';
        return;
    }

    // 제목을 변수에 저장
    audioTitle = title;
    statusDiv.innerHTML = '<span style="color: #10b981;">✅ 제목이 저장되었습니다. 요약 생성 및 VectorStore 저장 시 사용됩니다.</span>';

    setTimeout(() => {
        statusDiv.innerHTML = '';
    }, 3000);

    console.log('[Audio] 제목 저장됨:', audioTitle);
});

// Audio VectorStore 저장
document.getElementById('saveAudioToVectorstoreBtn').addEventListener('click', async () => {
    const statusDiv = document.getElementById('audioVectorstoreSaveStatus');
    const saveBtn = document.getElementById('saveAudioToVectorstoreBtn');

    // 유효성 검사
    if (!audioFileHash) {
        statusDiv.innerHTML = '<span style="color: #dc2626;">❌ file_hash를 찾을 수 없습니다.</span>';
        return;
    }

    if (audioSegments.length === 0) {
        statusDiv.innerHTML = '<span style="color: #dc2626;">❌ 저장할 세그먼트가 없습니다.</span>';
        return;
    }

    if (!audioTitle) {
        statusDiv.innerHTML = '<span style="color: #dc2626;">❌ 제목을 먼저 저장해주세요.</span>';
        return;
    }

    if (!audioRawSummary || audioRawSummary.trim() === '') {
        statusDiv.innerHTML = '<span style="color: #dc2626;">❌ 요약을 먼저 생성해주세요.</span>';
        return;
    }

    // 버튼 비활성화 및 저장 중 메시지 표시
    saveBtn.disabled = true;
    saveBtn.style.opacity = '0.6';
    saveBtn.style.cursor = 'not-allowed';
    statusDiv.innerHTML = '<span style="color: #666;">💾 VectorStore에 저장중입니다...</span>';
    console.log('[Audio] Saving to VectorStore with raw summary (citations preserved)');
    console.log('[Audio] Summary length:', audioRawSummary ? audioRawSummary.length : 0);
    console.log('[Audio] Summary preview:', audioRawSummary ? audioRawSummary.substring(0, 200) : 'EMPTY');

    try {
        const payload = {
            source_id: audioFileHash,
            source_type: 'audio',
            segments: audioSegments,
            title: audioTitle,
            summary: audioRawSummary,  // 원본 마크다운 사용 (citation 포함)
            filename: audioFilename  // 백엔드에서 반환된 실제 파일명 사용
        };
        console.log('[Audio] Payload summary included:', !!payload.summary);

        const response = await fetch('/api/save-to-vectorstore', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(payload)
        });

        const data = await response.json();

        if (data.success) {
            statusDiv.innerHTML = `<span style="color: #10b981;">✅ ${data.message}</span>`;
            setTimeout(() => {
                statusDiv.innerHTML = '';
            }, 5000);
        } else {
            statusDiv.innerHTML = `<span style="color: #dc2626;">❌ ${data.error}</span>`;
        }
    } catch (error) {
        console.error('VectorStore 저장 오류:', error);
        statusDiv.innerHTML = '<span style="color: #dc2626;">❌ VectorStore 저장 중 오류가 발생했습니다.</span>';
    } finally {
        // 버튼 재활성화
        saveBtn.disabled = false;
        saveBtn.style.opacity = '1';
        saveBtn.style.cursor = 'pointer';
    }
});

// 오디오 변경
document.getElementById('changeAudioBtn').addEventListener('click', () => {
    if (confirm('현재 작업을 종료하고 새로운 오디오를 처리하시겠습니까?')) {
        // 뷰어 섹션 숨기고 업로드 섹션 표시
        document.getElementById('audioViewerSection').style.display = 'none';
        document.getElementById('audioUploadSection').style.display = 'block';
        selectedAudioFile = null;
        fileInfo.classList.remove('show');
        audioSubmitBtn.disabled = true;

        // 요약 초기화
        document.getElementById('audioSummaryContent').innerHTML = '<p class="summary-placeholder">요약 생성 버튼을 클릭하세요</p>';

        // 채팅 초기화
        document.getElementById('audioChatMessages').innerHTML = `
            <div class="chat-welcome">
                회의록 내용에 대해 질문해보세요!
            </div>
        `;
        audioChatHistory = [];

        // 회의록 초기화
        document.getElementById('audioTranscriptContent').innerHTML = '';
        audioSegments = [];
        audioSessionId = null;
        audioFileHash = null;
        audioFilename = null;

        // 오디오 플레이어 정리
        if (audioElement) {
            audioElement.pause();
            audioElement.src = '';
        }

        // 이벤트 리스너 정리
        if (audioTimeUpdateHandler) {
            audioElement.removeEventListener('timeupdate', audioTimeUpdateHandler);
            audioTimeUpdateHandler = null;
        }

        console.log('[Audio] Session cleared. Ready for new audio.');
    }
});

// 오디오 자동 스크롤 토글
document.getElementById('audioAutoScrollToggle').addEventListener('click', function() {
    audioAutoScrollEnabled = !audioAutoScrollEnabled;
    this.classList.toggle('active');
    this.textContent = audioAutoScrollEnabled ? '자동 스크롤: ON' : '자동 스크롤: OFF';
    console.log(`[Audio] 자동 스크롤 토글: ${audioAutoScrollEnabled ? 'ON' : 'OFF'}`);
});

// 오디오 언어 선택 - 원본 선택 시 즉시 복원
document.getElementById('audioLanguageSelect').addEventListener('change', function() {
    const selectedLanguage = this.value;

    // 원본 언어 선택 시
    if (selectedLanguage === 'original') {
        // 원본 세그먼트로 복원
        displayAudioTranscript(audioSegments);
        // 언어 표시도 원본으로 복원
        if (audioSegments.length > 0) {
            updateAudioLanguageDisplay(audioSegments[0].original_language || 'unknown');
        }
    }
});

// 오디오 번역 버튼 클릭
document.getElementById('audioTranslateBtn').addEventListener('click', async function() {
    const selectElement = document.getElementById('audioLanguageSelect');
    const selectedLanguage = selectElement.value;

    console.log(`[Audio] 번역 버튼 클릭 - 선택된 언어: ${selectedLanguage}`);
    console.log(`[Audio] fileHash: ${audioFileHash}, segments: ${audioSegments ? audioSegments.length : 0}`);

    if (!audioFileHash || !audioSegments || audioSegments.length === 0) {
        console.warn('[Audio] 번역할 세그먼트가 없습니다.');
        alert('번역할 오디오가 없습니다. 먼저 오디오를 처리해주세요.');
        return;
    }

    // 원본 언어 선택 시
    if (selectedLanguage === 'original') {
        alert('번역할 언어를 선택해주세요.');
        return;
    }

    // 버튼 비활성화 및 텍스트 변경
    const originalBtnText = this.textContent;
    this.textContent = '번역 중...';
    this.disabled = true;
    this.style.opacity = '0.6';
    this.style.cursor = 'not-allowed';

    // 번역 요청
    try {
        const requestBody = {
            data_type: 'audio',
            data_id: audioFileHash,
            target_language: selectedLanguage,
            source_language: audioSegments[0]?.original_language || 'unknown'
        };
        console.log('[Audio] 번역 요청:', requestBody);

        const response = await fetch('/api/translate', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(requestBody)
        });

        console.log('[Audio] 응답 상태:', response.status);
        const data = await response.json();
        console.log('[Audio] 응답 데이터:', data);

        if (data.success) {
            console.log(`[Audio] 번역 완료: ${data.segments.length}개 세그먼트`);

            // 번역 통계 확인
            if (data.stats) {
                console.log(`[Audio] 번역 통계: 성공 ${data.stats.success}개, 실패 ${data.stats.failed}개`);

                // 실패한 세그먼트가 있으면 경고 표시
                if (data.stats.failed > 0) {
                    alert(`⚠️ 번역이 부분적으로 완료되었습니다.\n\n` +
                          `성공: ${data.stats.success}개\n` +
                          `실패: ${data.stats.failed}개\n\n` +
                          `실패한 세그먼트는 원본 텍스트로 표시됩니다.`);
                }
            }

            // 번역된 세그먼트로 audioSegments 배열 업데이트
            audioSegments = data.segments;

            // 번역된 세그먼트로 화면 업데이트
            displayAudioTranscript(data.segments, true);

            // 언어 표시 업데이트 (번역된 언어 표시)
            const languageNames = {
                'ko': '🇰🇷 한국어',
                'en': '🇺🇸 English',
                'ja': '🇯🇵 日本語',
                'de': '🇩🇪 Deutsch',
                'unknown': '❓ Unknown'
            };
            const originalLang = data.segments[0]?.original_language || 'unknown';
            document.getElementById('audioOriginalLanguage').textContent =
                `원본:${originalLang.toUpperCase()} → 번역:${selectedLanguage.toUpperCase()}`;

            // 번역 완료 후 세그먼트를 다시 로드하여 번역 데이터와 audio_path 포함
            console.log('[Audio] 번역 완료 후 세그먼트 재로드 (번역 데이터 및 audio_path 포함)');
            try {
                const segmentResponse = await fetch(`/api/get-segments?data_type=audio&data_id=${audioFileHash}&language=${selectedLanguage}`);
                const segmentData = await segmentResponse.json();

                if (segmentData.success) {
                    audioSegments = segmentData.segments;
                    console.log('[Audio] 세그먼트 재로드 완료:', audioSegments.length);
                    console.log('[Audio] 번역 데이터 있는 세그먼트:', audioSegments.filter(s => s.translated_text).length);
                    console.log('[Audio] audio_path 있는 세그먼트:', audioSegments.filter(s => s.audio_path).length);

                    // TTS 오디오 초기화
                    if (typeof initializeTtsAudio === 'function') {
                        initializeTtsAudio('audio');
                    }
                } else {
                    console.error('[Audio] 세그먼트 재로드 실패:', segmentData.error);
                }
            } catch (reloadError) {
                console.error('[Audio] 세그먼트 재로드 오류:', reloadError);
            }
        } else {
            console.error('[Audio] 번역 오류:', data.error);
            alert('번역 중 오류가 발생했습니다: ' + data.error);
        }
    } catch (error) {
        console.error('[Audio] 번역 API 오류:', error);
        console.error('[Audio] 에러 스택:', error.stack);
        alert('번역 API 호출 중 오류가 발생했습니다: ' + error.message);
    } finally {
        // 버튼 다시 활성화
        this.textContent = originalBtnText;
        this.disabled = false;
        this.style.opacity = '1';
        this.style.cursor = 'pointer';
    }
});

// ========== TTS 생성 버튼 (Audio) ==========
document.getElementById('audioGenerateTtsBtn').addEventListener('click', async function() {
    console.log(`[Audio] TTS 생성 버튼 클릭`);
    console.log(`[Audio] fileHash: ${audioFileHash}, segments: ${audioSegments ? audioSegments.length : 0}`);

    if (!audioFileHash || !audioSegments || audioSegments.length === 0) {
        console.warn('[Audio] TTS 생성할 세그먼트가 없습니다.');
        alert('TTS 생성할 오디오가 없습니다. 먼저 오디오를 처리해주세요.');
        return;
    }

    // 현재 선택된 언어 가져오기 (먼저 선언)
    const selectElement = document.getElementById('audioLanguageSelect');
    const selectedLanguage = selectElement.value;

    // 현재 선택된 언어의 번역이 있는지 확인
    const hasTranslationForSelectedLanguage = audioSegments.some(seg => {
        // 선택된 언어와 translated_language가 일치하고, translated_text가 있는지 확인
        return seg.translated_language === selectedLanguage &&
               seg.translated_text &&
               seg.translated_text.trim() !== '';
    });

    if (!hasTranslationForSelectedLanguage) {
        alert(`번역된 텍스트가 없습니다.\n\n현재 선택된 언어: ${selectedLanguage}\n\n먼저 해당 언어로 번역을 수행해주세요.`);
        return;
    }

    // 버튼 비활성화 및 텍스트 변경
    const originalBtnText = this.textContent;
    this.textContent = 'TTS 생성 중...';
    this.disabled = true;
    this.style.opacity = '0.6';
    this.style.cursor = 'not-allowed';

    if (!selectedLanguage || selectedLanguage === 'original') {
        alert('번역된 언어를 선택해주세요. 원본 언어로는 TTS를 생성할 수 없습니다.');
        this.textContent = originalBtnText;
        this.disabled = false;
        this.style.opacity = '1';
        this.style.cursor = 'pointer';
        return;
    }

    // TTS 생성 요청
    try {
        const requestBody = {
            data_type: 'audio',
            data_id: audioFileHash,
            target_language: selectedLanguage
        };
        console.log('[Audio] TTS 생성 요청:', requestBody);

        const response = await fetch('/api/generate-tts', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(requestBody)
        });

        console.log('[Audio] 응답 상태:', response.status);
        const data = await response.json();
        console.log('[Audio] 응답 데이터:', data);

        if (data.success) {
            console.log(`[Audio] TTS 생성 시작: task_id=${data.task_id}`);
            alert('TTS 오디오 생성이 시작되었습니다. 진행 상황은 콘솔에서 확인하세요.');

            // 진행 상황 폴링 시작
            pollTtsProgress(data.task_id, 'audio', this, originalBtnText);
        } else {
            console.error('[Audio] TTS 생성 오류:', data.error);
            alert('TTS 생성 중 오류가 발생했습니다: ' + data.error);
            this.textContent = originalBtnText;
            this.disabled = false;
            this.style.opacity = '1';
            this.style.cursor = 'pointer';
        }
    } catch (error) {
        console.error('[Audio] TTS 생성 API 오류:', error);
        alert('TTS 생성 API 호출 중 오류가 발생했습니다: ' + error.message);
        this.textContent = originalBtnText;
        this.disabled = false;
        this.style.opacity = '1';
        this.style.cursor = 'pointer';
    }
});

// 오디오 재생 시간에 따라 현재 세그먼트 하이라이트
function highlightCurrentAudioSegment(currentTime) {
    if (!audioSegments || audioSegments.length === 0) {
        console.warn('[Audio Highlight] No audio segments available');
        return;
    }

    // 현재 시간에 해당하는 세그먼트 찾기
    let currentSegment = null;
    for (let i = 0; i < audioSegments.length; i++) {
        const segment = audioSegments[i];
        const nextSegment = audioSegments[i + 1];

        if (nextSegment) {
            // 현재 시간이 이 세그먼트와 다음 세그먼트 사이에 있는지 확인
            if (currentTime >= segment.start_time && currentTime < nextSegment.start_time) {
                currentSegment = segment;
                break;
            }
        } else {
            // 마지막 세그먼트
            if (currentTime >= segment.start_time) {
                currentSegment = segment;
                break;
            }
        }
    }

    if (currentSegment) {
        console.log('[Audio Highlight] Found segment:', {
            id: currentSegment.id,
            speaker: currentSegment.speaker,
            start_time: currentSegment.start_time,
            text: currentSegment.text.substring(0, 50) + '...'
        });

        // 모든 세그먼트에서 active-audio 클래스 제거
        const allSegments = document.querySelectorAll('#audioTranscriptContent .transcript-segment');
        console.log('[Audio Highlight] Removing active-audio from', allSegments.length, 'segments');
        allSegments.forEach(seg => seg.classList.remove('active-audio'));

        // 현재 세그먼트에 active-audio 클래스 추가
        const currentSegmentElement = document.querySelector(
            `#audioTranscriptContent .transcript-segment[data-id="${currentSegment.id}"]`
        );

        if (currentSegmentElement) {
            console.log('[Audio Highlight] ✅ Adding active-audio to segment ID:', currentSegment.id);
            currentSegmentElement.classList.add('active-audio');

            // 클래스가 실제로 추가되었는지 확인
            const hasClass = currentSegmentElement.classList.contains('active-audio');
            console.log('[Audio Highlight] Class added successfully:', hasClass);

            // 현재 적용된 스타일 확인
            const styles = window.getComputedStyle(currentSegmentElement);
            console.log('[Audio Highlight] Background:', styles.background);
            console.log('[Audio Highlight] Border-left:', styles.borderLeft);

            // 자동 스크롤이 활성화되어 있으면 회의록 컨테이너 내부에서만 스크롤
            if (audioAutoScrollEnabled) {
                const transcriptContainer = document.getElementById('audioTranscriptContent');

                // 더 정확한 위치 계산을 위해 getBoundingClientRect 사용
                const containerRect = transcriptContainer.getBoundingClientRect();
                const elementRect = currentSegmentElement.getBoundingClientRect();

                // 컨테이너 기준 상대 위치 계산
                const relativeTop = elementRect.top - containerRect.top + transcriptContainer.scrollTop;
                const containerHeight = transcriptContainer.clientHeight;
                const elementHeight = currentSegmentElement.offsetHeight;

                // 요소를 컨테이너 중앙에 위치시키기
                const scrollTo = relativeTop - (containerHeight / 2) + (elementHeight / 2);

                transcriptContainer.scrollTo({
                    top: scrollTo,
                    behavior: 'smooth'
                });

                console.log('[Audio Highlight] Container height:', containerHeight, 'Element relative top:', relativeTop, 'Scrolling to:', scrollTo);
            }
        } else {
            console.error('[Audio Highlight] ❌ Could not find segment element with data-id:', currentSegment.id);
            // 모든 세그먼트의 data-id 출력하여 디버깅
            const allIds = Array.from(allSegments).map(seg => seg.dataset.id);
            console.log('[Audio Highlight] Available segment IDs:', allIds);
        }
    }
}

// ========================================
// Retriever 검색 탭 로직
// ========================================

// Retriever 폼 제출
document.getElementById('retrieverForm').addEventListener('submit', async (e) => {
    e.preventDefault();

    const query = document.getElementById('retrieverQuery').value.trim();
    const sourceType = document.querySelector('input[name="source_type"]:checked').value;
    const nResults = parseInt(document.getElementById('retrieverResults').value);

    if (!query) {
        alert('검색어를 입력해주세요.');
        return;
    }

    // UI 상태 변경
    document.getElementById('retrieverStatus').innerHTML = '<p style="color: #666;">검색 중...</p>';
    document.getElementById('retrieverResultsSection').style.display = 'none';

    try {
        const requestBody = {
            query: query,
            n_results: nResults
        };

        // source_type이 'all'이 아닌 경우에만 추가
        if (sourceType !== 'all') {
            requestBody.source_type = sourceType;
        }

        const response = await fetch('/api/retriever-search', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(requestBody)
        });

        const data = await response.json();

        if (data.success) {
            displayRetrieverResults(data.results, query);
            document.getElementById('retrieverStatus').innerHTML = '';
        } else {
            document.getElementById('retrieverStatus').innerHTML = `<p style="color: #dc2626;">오류: ${data.error}</p>`;
        }
    } catch (error) {
        console.error('오류:', error);
        document.getElementById('retrieverStatus').innerHTML = '<p style="color: #dc2626;">검색 중 오류가 발생했습니다.</p>';
    }
});

// Retriever 검색 결과 표시
function displayRetrieverResults(results, query) {
    const resultsContent = document.getElementById('retrieverResultsContent');
    const resultInfo = document.getElementById('retrieverResultInfo');

    if (!results || results.length === 0) {
        resultsContent.innerHTML = '<div style="padding: 40px; text-align: center; color: var(--text-muted);"><p>검색 결과가 없습니다.</p></div>';
        document.getElementById('retrieverResultsSection').style.display = 'block';
        resultInfo.textContent = '검색 결과: 0개';
        return;
    }

    resultsContent.innerHTML = '';

    results.forEach((result, index) => {
        const resultDiv = document.createElement('div');
        resultDiv.className = 'transcript-segment';
        resultDiv.style.marginBottom = '20px';
        resultDiv.style.borderLeft = '4px solid var(--primary-color)';

        const metadata = result.metadata;
        const sourceType = metadata.source_type;
        const distance = result.distance ? result.distance.toFixed(4) : 'N/A';

        // 요약 검색 결과인 경우 (document_type으로 명시적 구분)
        if (metadata.document_type === 'summary') {
            const sourceIcon = sourceType === 'youtube' ? '🎬' : '🎵';
            const sourceName = sourceType === 'youtube' ? 'YouTube' : 'Audio';
            const sourceId = metadata.source_id;
            const createdAt = metadata.created_at || 'N/A';
            const filename = metadata.filename || '';

            resultDiv.innerHTML = `
                <div class="segment-header" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                    <div>
                        <span class="segment-speaker" style="background: var(--accent-color, #f59e0b); color: white; padding: 4px 12px; border-radius: 6px; font-weight: 600;">
                            📝 ${sourceIcon} ${sourceName} 요약
                        </span>
                    </div>
                    <div style="font-size: 0.85rem; color: var(--text-muted);">
                        <span style="padding: 4px 8px; background: rgba(var(--primary-rgb), 0.1); border-radius: 4px;">
                            유사도: ${distance}
                        </span>
                    </div>
                </div>
                <div class="segment-text" style="margin-bottom: 12px; padding: 12px; background: var(--bg-secondary); border-radius: 8px; line-height: 1.6; max-height: 400px; overflow-y: auto;">
                    ${marked.parse(result.document)}
                </div>
                <div style="font-size: 0.85rem; color: var(--text-muted); padding: 8px 12px; background: rgba(var(--primary-rgb), 0.05); border-radius: 6px;">
                    <div style="display: flex; gap: 20px; flex-wrap: wrap;">
                        <span><strong>Source ID:</strong> ${sourceId}</span>
                        <span><strong>생성일시:</strong> ${createdAt}</span>
                        ${filename ? `<span><strong>파일명:</strong> ${filename}</span>` : ''}
                    </div>
                </div>
            `;
        } else {
            // 세그먼트 검색 결과인 경우 (기존 로직)
            const sourceIcon = sourceType === 'youtube' ? '🎬' : '🎵';
            const sourceName = sourceType === 'youtube' ? 'YouTube' : 'Audio';
            const sourceId = metadata.source_id;
            const speaker = metadata.speaker;
            const startTime = metadata.start_time;
            const confidence = (metadata.confidence * 100).toFixed(1);
            const filename = metadata.filename || '';

            const minutes = Math.floor(startTime / 60);
            const seconds = Math.floor(startTime % 60);
            const timeStr = `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;

            // end_time 포맷팅
            let timeRangeStr = timeStr;
            if (metadata.end_time) {
                const endMinutes = Math.floor(metadata.end_time / 60);
                const endSeconds = Math.floor(metadata.end_time % 60);
                const endTimeStr = `${String(endMinutes).padStart(2, '0')}:${String(endSeconds).padStart(2, '0')}`;
                timeRangeStr = `${timeStr} ~ ${endTimeStr}`;
            }

            resultDiv.innerHTML = `
                <div class="segment-header" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                    <div>
                        <span class="segment-speaker" style="background: var(--primary-color); color: white; padding: 4px 12px; border-radius: 6px; font-weight: 600;">
                            ${sourceIcon} ${sourceName} - 화자 ${speaker}
                        </span>
                        <span class="segment-time" style="margin-left: 12px; padding: 4px 12px; background: var(--bg-secondary); border-radius: 6px;">
                            ${timeRangeStr}
                        </span>
                    </div>
                    <div style="font-size: 0.85rem; color: var(--text-muted);">
                        <span style="padding: 4px 8px; background: rgba(var(--primary-rgb), 0.1); border-radius: 4px;">
                            유사도: ${distance}
                        </span>
                    </div>
                </div>
                <div class="segment-text" style="margin-bottom: 12px; padding: 12px; background: var(--bg-secondary); border-radius: 8px; line-height: 1.6;">
                    ${result.document}
                </div>
                <div style="font-size: 0.85rem; color: var(--text-muted); padding: 8px 12px; background: rgba(var(--primary-rgb), 0.05); border-radius: 6px;">
                    <div style="display: flex; gap: 20px; flex-wrap: wrap;">
                        <span><strong>Source ID:</strong> ${sourceId}</span>
                        <span><strong>Segment ID:</strong> ${metadata.segment_id}</span>
                        <span><strong>Start Time:</strong> ${timeStr}</span>
                        <span><strong>Confidence:</strong> ${confidence}%</span>
                        ${filename ? `<span><strong>파일명:</strong> ${filename}</span>` : ''}
                    </div>
                </div>
                <div style="margin-top: 8px; padding: 8px 12px; background: rgba(var(--primary-rgb), 0.1); border-radius: 6px; text-align: center; font-size: 0.9rem; color: var(--primary-color); font-weight: 600;">
                    🎧 클릭하여 재생하기
                </div>
            `;

            // 클릭 이벤트: 오디오/비디오 재생 (세그먼트만)
            resultDiv.style.cursor = 'pointer';
            const endTime = metadata.end_time || null;
            resultDiv.addEventListener('click', () => {
                playFromRetrieverResult(sourceType, sourceId, startTime, endTime, filename);
            });
        }

        resultsContent.appendChild(resultDiv);
    });

    document.getElementById('retrieverResultsSection').style.display = 'block';
    resultInfo.textContent = `검색 결과: ${results.length}개`;
}

// Retriever 결과에서 재생하기 (현재 탭에서)
let retrieverAudioStopListener = null;
let retrieverYoutubeStopInterval = null;

async function playFromRetrieverResult(sourceType, sourceId, startTime, endTime, filename) {
    // 플레이어 섹션 표시
    document.getElementById('retrieverPlayerSection').style.display = 'block';

    if (sourceType === 'audio') {
        // 오디오 파일 재생
        console.log(`[Retriever] Playing audio: ${filename} from ${startTime}s to ${endTime || 'end'}s`);

        // YouTube 플레이어 숨기고 오디오 플레이어 표시
        document.getElementById('retrieverYoutubePlayerWrapper').style.display = 'none';
        document.getElementById('retrieverAudioPlayerWrapper').style.display = 'block';
        document.getElementById('retrieverPlayerTitle').innerHTML = '🎵 오디오 플레이어 (세그먼트 재생)';

        // 오디오 플레이어 가져오기
        if (!retrieverAudioPlayer) {
            retrieverAudioPlayer = document.getElementById('retrieverAudioPlayer');
        }

        // 기존 stop listener 제거
        if (retrieverAudioStopListener) {
            retrieverAudioPlayer.removeEventListener('timeupdate', retrieverAudioStopListener);
        }

        // 오디오 파일 경로 구성 (filename 기반)
        const audioUrl = `/uploads/${filename}`;

        // 오디오 소스 설정
        retrieverAudioPlayer.src = audioUrl;
        retrieverAudioPlayer.currentTime = startTime;

        // end_time이 있으면 자동 정지 설정
        if (endTime) {
            retrieverAudioStopListener = function() {
                if (retrieverAudioPlayer.currentTime >= endTime) {
                    retrieverAudioPlayer.pause();
                    console.log(`[Retriever] Auto-stopped at ${endTime}s`);
                }
            };
            retrieverAudioPlayer.addEventListener('timeupdate', retrieverAudioStopListener);
        }

        // 로드 후 재생
        retrieverAudioPlayer.addEventListener('loadedmetadata', function onLoaded() {
            retrieverAudioPlayer.currentTime = startTime;
            retrieverAudioPlayer.play();
            retrieverAudioPlayer.removeEventListener('loadedmetadata', onLoaded);
        }, { once: true });

        retrieverAudioPlayer.load();

    } else if (sourceType === 'youtube') {
        // YouTube 영상 재생
        console.log(`[Retriever] Playing YouTube: ${sourceId} from ${startTime}s to ${endTime || 'end'}s`);

        // 오디오 플레이어 숨기고 YouTube 플레이어 표시
        document.getElementById('retrieverAudioPlayerWrapper').style.display = 'none';
        document.getElementById('retrieverYoutubePlayerWrapper').style.display = 'block';
        document.getElementById('retrieverPlayerTitle').innerHTML = '🎬 YouTube 플레이어 (세그먼트 재생)';

        // 기존 stop interval 제거
        if (retrieverYoutubeStopInterval) {
            clearInterval(retrieverYoutubeStopInterval);
        }

        // YouTube Player 초기화 또는 비디오 로드
        if (!retrieverYoutubePlayer) {
            retrieverYoutubePlayer = new YT.Player('retrieverYoutubePlayer', {
                videoId: sourceId,
                width: '100%',
                height: '400',
                playerVars: {
                    'autoplay': 1,
                    'controls': 1,
                    'start': Math.floor(startTime)
                },
                events: {
                    'onReady': (event) => {
                        event.target.seekTo(startTime, true);
                        event.target.playVideo();

                        // end_time이 있으면 자동 정지 설정
                        if (endTime) {
                            retrieverYoutubeStopInterval = setInterval(() => {
                                const currentTime = event.target.getCurrentTime();
                                if (currentTime >= endTime) {
                                    event.target.pauseVideo();
                                    clearInterval(retrieverYoutubeStopInterval);
                                    console.log(`[Retriever] Auto-stopped at ${endTime}s`);
                                }
                            }, 100);
                        }
                    }
                }
            });
        } else {
            retrieverYoutubePlayer.loadVideoById({
                videoId: sourceId,
                startSeconds: startTime
            });
            retrieverYoutubePlayer.playVideo();

            // end_time이 있으면 자동 정지 설정
            if (endTime) {
                retrieverYoutubeStopInterval = setInterval(() => {
                    const currentTime = retrieverYoutubePlayer.getCurrentTime();
                    if (currentTime >= endTime) {
                        retrieverYoutubePlayer.pauseVideo();
                        clearInterval(retrieverYoutubeStopInterval);
                        console.log(`[Retriever] Auto-stopped at ${endTime}s`);
                    }
                }, 100);
            }
        }
    }

    // 플레이어 영역으로 스크롤
    document.getElementById('retrieverPlayerSection').scrollIntoView({
        behavior: 'smooth',
        block: 'start'
    });
}

// Retriever 플레이어 닫기
document.getElementById('retrieverClosePlayerBtn').addEventListener('click', () => {
    document.getElementById('retrieverPlayerSection').style.display = 'none';

    // 오디오 정지 및 리스너 제거
    if (retrieverAudioPlayer) {
        retrieverAudioPlayer.pause();
        if (retrieverAudioStopListener) {
            retrieverAudioPlayer.removeEventListener('timeupdate', retrieverAudioStopListener);
            retrieverAudioStopListener = null;
        }
    }

    // YouTube 정지 및 interval 제거
    if (retrieverYoutubePlayer && retrieverYoutubePlayer.pauseVideo) {
        retrieverYoutubePlayer.pauseVideo();
    }
    if (retrieverYoutubeStopInterval) {
        clearInterval(retrieverYoutubeStopInterval);
        retrieverYoutubeStopInterval = null;
    }
});

// ========================================
// 내용 질문 탭 로직
// ========================================

// 내용 질문 폼 제출
document.getElementById('askContentForm').addEventListener('submit', async (e) => {
    e.preventDefault();

    const question = document.getElementById('contentQuestion').value.trim();
    const transcriptN = parseInt(document.getElementById('transcriptCount').value);
    const summaryN = parseInt(document.getElementById('summaryCount').value);

    if (!question) {
        alert('질문을 입력해주세요.');
        return;
    }

    // 버튼 비활성화 및 텍스트 변경
    const askContentBtn = document.getElementById('askContentBtn');
    const askContentBtnText = document.getElementById('askContentBtnText');
    const originalBtnText = askContentBtnText.textContent;

    askContentBtn.disabled = true;
    askContentBtnText.textContent = '질문에 대한 답변을 준비중입니다...';
    askContentBtn.style.opacity = '0.6';
    askContentBtn.style.cursor = 'not-allowed';

    // UI 상태 변경
    document.getElementById('askContentStatus').innerHTML = '<p style="color: #666;">🤔 생각 중... (검색 및 답변 생성)</p>';
    document.getElementById('askContentAnswerSection').style.display = 'none';

    try {
        const response = await fetch('/api/ask_content', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                question: question,
                transcript_n: transcriptN,
                summary_n: summaryN
            })
        });

        const data = await response.json();

        if (data.success) {
            displayAskContentAnswer(data);
            document.getElementById('askContentStatus').innerHTML = '';
        } else {
            document.getElementById('askContentStatus').innerHTML = `<p style="color: #dc2626;">오류: ${data.error}</p>`;
        }
    } catch (error) {
        console.error('오류:', error);
        document.getElementById('askContentStatus').innerHTML = '<p style="color: #dc2626;">질문 처리 중 오류가 발생했습니다.</p>';
    } finally {
        // 버튼 다시 활성화
        askContentBtn.disabled = false;
        askContentBtnText.textContent = originalBtnText;
        askContentBtn.style.opacity = '1';
        askContentBtn.style.cursor = 'pointer';
    }
});

// 답변 표시 함수
function displayAskContentAnswer(data) {
    const answerSection = document.getElementById('askContentAnswerSection');
    const answerContent = document.getElementById('askContentAnswer');
    const resultInfo = document.getElementById('askContentResultInfo');
    const transcriptResults = document.getElementById('askContentTranscriptResults');
    const summaryResults = document.getElementById('askContentSummaryResults');

    // 답변 표시 (마크다운 렌더링)
    answerContent.innerHTML = marked.parse(data.answer);

    // 검색 결과 개수 표시
    resultInfo.textContent = `검색: 요약 ${data.summary_results_count}개, Chunk ${data.direct_chunk_results_count || 0}개`;

    // 요약 검색 결과 먼저 표시 (Retriever 스타일)
    if (data.summary_results && data.summary_results.length > 0) {
        summaryResults.innerHTML = data.summary_results.map((result, index) => {
            const metadata = result.metadata || {};
            const subtopic = metadata.subtopic || '전체';
            const sourceType = metadata.source_type || 'unknown';
            const sourceIcon = sourceType === 'youtube' ? '🎬' : '🎵';
            const sourceName = sourceType === 'youtube' ? 'YouTube' : 'Audio';
            const sourceId = metadata.source_id || 'Unknown';
            const createdAt = metadata.created_at || 'N/A';
            const distance = result.distance ? result.distance.toFixed(4) : 'N/A';
            const filename = metadata.filename || '';

            return `
                <div class="transcript-segment" style="margin-bottom: 20px; border-left: 4px solid var(--primary-color); padding-left: 0;">
                    <div class="segment-header" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                        <div>
                            <span class="segment-speaker" style="background: var(--accent-color, #f59e0b); color: white; padding: 4px 12px; border-radius: 6px; font-weight: 600;">
                                📝 ${sourceIcon} ${sourceName} 요약
                            </span>
                        </div>
                        <div style="font-size: 0.85rem; color: var(--text-muted);">
                            <span style="padding: 4px 8px; background: rgba(var(--primary-rgb), 0.1); border-radius: 4px;">
                                유사도: ${distance}
                            </span>
                        </div>
                    </div>
                    <div class="segment-text" style="margin-bottom: 12px; padding: 12px; background: var(--bg-secondary); border-radius: 8px; line-height: 1.6; max-height: 400px; overflow-y: auto;">
                        ${marked.parse(result.document || '')}
                    </div>
                    <div style="font-size: 0.85rem; color: var(--text-muted); padding: 8px 12px; background: rgba(var(--primary-rgb), 0.05); border-radius: 6px;">
                        <div style="display: flex; gap: 20px; flex-wrap: wrap;">
                            <span><strong>Source ID:</strong> ${sourceId}</span>
                            <span><strong>소주제:</strong> ${subtopic}</span>
                            <span><strong>생성일시:</strong> ${createdAt}</span>
                            ${filename ? `<span><strong>파일명:</strong> ${filename}</span>` : ''}
                        </div>
                    </div>
                </div>
            `;
        }).join('');
    } else {
        summaryResults.innerHTML = '<p style="padding: 15px; color: var(--text-secondary);">검색 결과가 없습니다.</p>';
    }

    // Chunk 검색 결과 표시 (회의록 전체에서 검색)
    if (data.direct_chunk_results && data.direct_chunk_results.length > 0) {
        transcriptResults.innerHTML = data.direct_chunk_results.map((result, index) => {
            const metadata = result.metadata || {};
            const sourceType = metadata.source_type || 'unknown';
            const sourceIcon = sourceType === 'youtube' ? '🎬' : '🎵';
            const sourceName = sourceType === 'youtube' ? 'YouTube' : 'Audio';
            const sourceId = metadata.source_id || 'Unknown';
            const speaker = metadata.speaker || 'Unknown';
            const startTime = metadata.start_time || 0;
            const confidence = metadata.confidence ? (metadata.confidence * 100).toFixed(1) : 'N/A';
            const distance = result.distance ? result.distance.toFixed(4) : 'N/A';
            const filename = metadata.filename || '';
            const segmentId = metadata.segment_id || 'N/A';

            const minutes = Math.floor(startTime / 60);
            const seconds = Math.floor(startTime % 60);
            const timeStr = `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;

            // end_time 포맷팅
            let timeRangeStr = timeStr;
            if (metadata.end_time) {
                const endMinutes = Math.floor(metadata.end_time / 60);
                const endSeconds = Math.floor(metadata.end_time % 60);
                const endTimeStr = `${String(endMinutes).padStart(2, '0')}:${String(endSeconds).padStart(2, '0')}`;
                timeRangeStr = `${timeStr} ~ ${endTimeStr}`;
            }

            return `
                <div class="transcript-segment" style="margin-bottom: 20px; border-left: 4px solid var(--primary-color); padding-left: 0;">
                    <div class="segment-header" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                        <div>
                            <span class="segment-speaker" style="background: var(--primary-color); color: white; padding: 4px 12px; border-radius: 6px; font-weight: 600;">
                                ${sourceIcon} ${sourceName} - 화자 ${speaker}
                            </span>
                            <span class="segment-time" style="margin-left: 12px; padding: 4px 12px; background: var(--bg-secondary); border-radius: 6px;">
                                ${timeRangeStr}
                            </span>
                        </div>
                        <div style="font-size: 0.85rem; color: var(--text-muted);">
                            <span style="padding: 4px 8px; background: rgba(var(--primary-rgb), 0.1); border-radius: 4px;">
                                유사도: ${distance}
                            </span>
                        </div>
                    </div>
                    <div class="segment-text" style="margin-bottom: 12px; padding: 12px; background: var(--bg-secondary); border-radius: 8px; line-height: 1.6;">
                        ${result.document || ''}
                    </div>
                    <div style="font-size: 0.85rem; color: var(--text-muted); padding: 8px 12px; background: rgba(var(--primary-rgb), 0.05); border-radius: 6px;">
                        <div style="display: flex; gap: 20px; flex-wrap: wrap;">
                            <span><strong>Source ID:</strong> ${sourceId}</span>
                            <span><strong>Segment ID:</strong> ${segmentId}</span>
                            <span><strong>Start Time:</strong> ${timeStr}</span>
                            <span><strong>Confidence:</strong> ${confidence}%</span>
                            ${filename ? `<span><strong>파일명:</strong> ${filename}</span>` : ''}
                        </div>
                    </div>
                </div>
            `;
        }).join('');
    } else {
        transcriptResults.innerHTML = '<p style="padding: 15px; color: var(--text-secondary);">Chunk 검색 결과가 없습니다.</p>';
    }

    // 답변 섹션 표시
    answerSection.style.display = 'block';

    // 스크롤 이동
    answerSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// ========== 데이터 관리 함수 ==========

// 데이터 목록 로드
async function loadDataList() {
    try {
        const response = await fetch('/api/data-management/list');
        const data = await response.json();

        if (data.success) {
            // 통계 표시
            displayStats(data.stats);

            // YouTube 목록 표시
            displayYoutubeList(data.youtube);

            // 오디오 목록 표시
            displayAudioList(data.audio);
        } else {
            alert('데이터 로드 실패: ' + data.error);
        }
    } catch (error) {
        console.error('데이터 로드 오류:', error);
        alert('데이터 로드 중 오류가 발생했습니다.');
    }
}

// 통계 표시
function displayStats(stats) {
    const statsDiv = document.getElementById('dbStats');
    statsDiv.innerHTML = `
        <div style="padding: 15px; background: var(--bg-secondary); border-radius: 8px; border-left: 4px solid #4CAF50;">
            <div style="font-size: 0.9rem; color: var(--text-muted); margin-bottom: 5px;">YouTube 영상</div>
            <div style="font-size: 1.5rem; font-weight: bold; color: var(--text-primary);">${stats.youtube_videos}개</div>
            <div style="font-size: 0.85rem; color: var(--text-muted); margin-top: 5px;">세그먼트: ${stats.youtube_segments.toLocaleString()}개</div>
        </div>
        <div style="padding: 15px; background: var(--bg-secondary); border-radius: 8px; border-left: 4px solid #2196F3;">
            <div style="font-size: 0.9rem; color: var(--text-muted); margin-bottom: 5px;">오디오 파일</div>
            <div style="font-size: 1.5rem; font-weight: bold; color: var(--text-primary);">${stats.audio_files}개</div>
            <div style="font-size: 0.85rem; color: var(--text-muted); margin-top: 5px;">세그먼트: ${stats.audio_segments.toLocaleString()}개</div>
        </div>
    `;
}

// YouTube 목록 표시
function displayYoutubeList(youtubeList) {
    const listDiv = document.getElementById('youtubeList');

    if (youtubeList.length === 0) {
        listDiv.innerHTML = '<p style="text-align: center; color: var(--text-muted); padding: 20px;">저장된 YouTube 영상이 없습니다.</p>';
        return;
    }

    listDiv.innerHTML = youtubeList.map(item => `
        <div style="padding: 15px; margin-bottom: 10px; background: var(--bg-secondary); border-radius: 8px; border-left: 4px solid #FF0000;">
            <div style="display: flex; justify-content: space-between; align-items: start;">
                <div style="flex: 1;">
                    <div style="font-weight: bold; font-size: 1.1rem; margin-bottom: 5px;">${item.title}</div>
                    <div style="font-size: 0.9rem; color: var(--text-muted); margin-bottom: 8px;">
                        📺 ${item.channel} | 조회수: ${item.view_count.toLocaleString()}회 | 업로드: ${item.upload_date}
                    </div>
                    <div style="font-size: 0.85rem; color: var(--text-muted);">
                        🎤 세그먼트: ${item.segments_count}개 |
                        ⏱️ STT: ${item.stt_time.toFixed(1)}초 (${item.stt_service}) |
                        📅 처리일: ${item.created_at}
                        ${item.has_summary ? ' | ✅ 요약 있음' : ''}
                    </div>
                </div>
                <button onclick="deleteData('youtube', '${item.id}')"
                        style="padding: 8px 16px; background: #f44336; color: white; border: none; border-radius: 6px; cursor: pointer; margin-left: 10px;">
                    🗑️ 삭제
                </button>
            </div>
        </div>
    `).join('');
}

// 오디오 목록 표시
function displayAudioList(audioList) {
    const listDiv = document.getElementById('audioList');

    if (audioList.length === 0) {
        listDiv.innerHTML = '<p style="text-align: center; color: var(--text-muted); padding: 20px;">저장된 오디오 파일이 없습니다.</p>';
        return;
    }

    listDiv.innerHTML = audioList.map(item => `
        <div style="padding: 15px; margin-bottom: 10px; background: var(--bg-secondary); border-radius: 8px; border-left: 4px solid #2196F3;">
            <div style="display: flex; justify-content: space-between; align-items: start;">
                <div style="flex: 1;">
                    <div style="font-weight: bold; font-size: 1.1rem; margin-bottom: 5px;">${item.filename}</div>
                    <div style="font-size: 0.9rem; color: var(--text-muted); margin-bottom: 8px;">
                        📁 ${item.file_path} | 크기: ${formatFileSize(item.file_size)} | 길이: ${(item.duration / 60).toFixed(1)}분
                    </div>
                    <div style="font-size: 0.85rem; color: var(--text-muted);">
                        🎤 세그먼트: ${item.segments_count}개 |
                        ⏱️ STT: ${item.stt_time.toFixed(1)}초 (${item.stt_service}) |
                        📅 처리일: ${item.created_at}
                        ${item.has_summary ? ' | ✅ 요약 있음' : ''}
                    </div>
                </div>
                <button onclick="deleteData('audio', '${item.id}')"
                        style="padding: 8px 16px; background: #f44336; color: white; border: none; border-radius: 6px; cursor: pointer; margin-left: 10px;">
                    🗑️ 삭제
                </button>
            </div>
        </div>
    `).join('');
}

// 데이터 삭제
async function deleteData(type, id) {
    const typeName = type === 'youtube' ? 'YouTube 영상' : '오디오 파일';

    if (!confirm(`정말로 이 ${typeName}을(를) 삭제하시겠습니까?\n\n삭제된 데이터는 복구할 수 없습니다.`)) {
        return;
    }

    try {
        const response = await fetch('/api/data-management/delete', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ type, id })
        });

        const data = await response.json();

        if (data.success) {
            alert('삭제되었습니다.');
            loadDataList(); // 목록 새로고침
        } else {
            alert('삭제 실패: ' + data.error);
        }
    } catch (error) {
        console.error('삭제 오류:', error);
        alert('삭제 중 오류가 발생했습니다.');
    }
}

// 데이터 관리 탭 진입 시 자동 로드
document.querySelectorAll('.tab-button').forEach(button => {
    button.addEventListener('click', () => {
        const tabId = button.dataset.tab;
        if (tabId === 'data-management-tab') {
            loadDataList();
        }
    });
});

// Marked.js 라이브러리 로드
const script = document.createElement('script');
script.src = 'https://cdn.jsdelivr.net/npm/marked/marked.min.js';
document.head.appendChild(script);

// ========== TTS 오디오 동기화 ==========
let ttsAudioElements = {}; // 세그먼트별 TTS 오디오 엘리먼트
let currentTtsSegment = null; // 현재 재생 중인 TTS 세그먼트
let ttsEnabled = false; // TTS 재생 활성화 여부
let ttsPlaybackHistory = []; // TTS 재생 이력 (디버깅용)
let ttsHasVideoPaused = false; // TTS가 의도적으로 YouTube를 일시정지시켰는지 여부
let ttsResumeTimer = null; // YouTube 재개 타이머

// TTS 오디오 초기화
function initializeTtsAudio(dataType) {
    console.log(`[TTS] 오디오 초기화: ${dataType}`);

    const segments = dataType === 'video' ? videoSegments : audioSegments;

    if (!segments || segments.length === 0) {
        console.warn('[TTS] 세그먼트가 없습니다.');
        return;
    }

    // 기존 오디오 엘리먼트 정리
    Object.values(ttsAudioElements).forEach(audio => {
        audio.pause();
        audio.src = '';
    });
    ttsAudioElements = {};
    currentTtsSegment = null;

    // TTS 오디오 파일이 있는 세그먼트에 대해 Audio 엘리먼트 생성
    let ttsCount = 0;
    segments.forEach((segment, idx) => {
        if (segment.audio_path) {
            const audio = new Audio();
            audio.src = `/${segment.audio_path}`;
            audio.preload = 'auto';

            // 재생 속도는 메타데이터 로드 후 세그먼트 길이에 맞춰 동적으로 설정
            audio.addEventListener('loadedmetadata', () => {
                console.log(`[TTS 타이밍] 세그먼트 ${idx} 메타데이터 로드 완료, readyState: ${audio.readyState}, duration: ${audio.duration}s`);
                if (segment.end_time && segment.start_time) {
                    const segmentDuration = segment.end_time - segment.start_time;
                    const ttsDuration = audio.duration;

                    if (ttsDuration > 0 && segmentDuration > 0) {
                        // TTS 길이를 세그먼트 길이에 맞추기 위한 재생 속도 계산
                        const idealRate = ttsDuration / segmentDuration;

                        // 배속을 0.85x ~ 1.3x 범위로 제한
                        const clampedRate = Math.max(0.85, Math.min(1.3, idealRate));
                        audio.playbackRate = clampedRate;

                        // 1.3x를 초과하는 경우 YouTube 일시정지가 필요함을 표시
                        if (idealRate > 1.3 && dataType === 'video') {
                            audio.needsVideoPause = true;
                            console.log(`[TTS] 세그먼트 ${idx} 재생 속도: ${clampedRate.toFixed(2)}x (YouTube 일시정지 필요, 원래 계산값: ${idealRate.toFixed(2)}x, TTS: ${ttsDuration.toFixed(2)}s, 세그먼트: ${segmentDuration.toFixed(2)}s)`);
                        } else if (idealRate !== clampedRate) {
                            audio.needsVideoPause = false;
                            console.log(`[TTS] 세그먼트 ${idx} 재생 속도: ${clampedRate.toFixed(2)}x (제한됨, 원래 계산값: ${idealRate.toFixed(2)}x, TTS: ${ttsDuration.toFixed(2)}s, 세그먼트: ${segmentDuration.toFixed(2)}s)`);
                        } else {
                            audio.needsVideoPause = false;
                            console.log(`[TTS] 세그먼트 ${idx} 재생 속도: ${clampedRate.toFixed(2)}x (TTS: ${ttsDuration.toFixed(2)}s, 세그먼트: ${segmentDuration.toFixed(2)}s)`);
                        }
                    } else {
                        audio.playbackRate = 1.0;
                        audio.needsVideoPause = false;
                    }
                } else {
                    audio.playbackRate = 1.0;
                    audio.needsVideoPause = false;
                }
            });

            // TTS 재생 완료 시 처리 (안전장치)
            audio.addEventListener('ended', () => {
                console.log(`[TTS] 세그먼트 ${idx} TTS 재생 완료 (ended 이벤트)`);
                // 재생 이력 기록
                ttsPlaybackHistory.push({
                    segment: idx,
                    action: 'ended',
                    needsVideoPause: audio.needsVideoPause,
                    time: new Date().toISOString()
                });

                // TTS가 일찍 끝난 경우 타이머 취소 및 YouTube 재개
                if (ttsResumeTimer) {
                    clearTimeout(ttsResumeTimer);
                    ttsResumeTimer = null;
                    console.log(`[TTS] TTS 조기 종료, 타이머 취소`);
                }

                // YouTube가 일시정지된 상태라면 재개
                if (ttsHasVideoPaused && dataType === 'video' && youtubePlayer) {
                    console.log(`[TTS] TTS 종료로 인한 YouTube 재개 (세그먼트 ${idx})`);
                    try {
                        ttsHasVideoPaused = false;
                        youtubePlayer.playVideo();
                        ttsPlaybackHistory.push({
                            segment: idx,
                            action: 'youtube_resume_on_ended',
                            time: new Date().toISOString()
                        });
                    } catch (err) {
                        console.error(`[TTS] YouTube 재생 오류:`, err);
                    }
                }
            });

            // 오디오 로드 오류 처리 - YouTube도 복구
            audio.addEventListener('error', (e) => {
                console.error(`[TTS] 세그먼트 ${idx} 오디오 로드 오류:`, segment.audio_path, e);
                // TTS 오류 시에도 YouTube 재생 복구
                if (audio.needsVideoPause && dataType === 'video' && youtubePlayer) {
                    console.log(`[TTS] 오류 발생, YouTube 다시 재생 (세그먼트 ${idx})`);
                    try {
                        ttsHasVideoPaused = false; // 플래그 해제
                        youtubePlayer.playVideo();
                    } catch (err) {
                        console.error(`[TTS] YouTube 재생 복구 오류:`, err);
                    }
                }
            });

            // 볼륨 설정 (audioVolume 슬라이더에서 가져옴)
            const volumeSlider = dataType === 'video' ?
                document.getElementById('youtubeVolume') :
                document.getElementById('audioVolume');
            if (volumeSlider) {
                audio.volume = volumeSlider.value / 100;
            } else {
                audio.volume = 0.8; // 기본값
            }

            ttsAudioElements[idx] = audio;
            ttsCount++;

            console.log(`[TTS 타이밍] 세그먼트 ${idx} Audio 객체 생성 완료: ${segment.audio_path}, readyState: ${audio.readyState}`);
        }
    });

    if (ttsCount > 0) {
        console.log(`[TTS] ${ttsCount}개의 TTS 오디오 준비 완료`);
        ttsEnabled = true;

        // YouTube 플레이어 또는 오디오 플레이어 동기화 시작
        if (dataType === 'video') {
            startVideoTtsSync();
        } else {
            startAudioTtsSync();
        }
    } else {
        console.warn('[TTS] TTS 오디오 파일이 없습니다.');
        ttsEnabled = false;
    }
}

// YouTube 플레이어와 TTS 동기화 시작
function startVideoTtsSync() {
    if (!youtubePlayer || !youtubePlayer.getCurrentTime) {
        console.warn('[TTS] YouTube 플레이어가 준비되지 않았습니다.');
        return;
    }

    // 기존 인터벌 정리
    if (window.videoTtsSyncInterval) {
        clearInterval(window.videoTtsSyncInterval);
    }

    // 100ms마다 현재 시간 확인하여 TTS 재생
    window.videoTtsSyncInterval = setInterval(() => {
        if (!ttsEnabled) {
            console.log('[TTS 이벤트] TTS 비활성화 상태 (video)');
            return;
        }
        if (!youtubePlayer) {
            console.log('[TTS 이벤트] YouTube 플레이어 없음');
            return;
        }

        try {
            const currentTime = youtubePlayer.getCurrentTime();
            const playerState = youtubePlayer.getPlayerState();

            // 재생 중일 때만 TTS 동기화
            if (playerState === 1) { // YT.PlayerState.PLAYING
                ttsHasVideoPaused = false; // 비디오가 재생 중이면 플래그 해제
                syncTtsWithTime(currentTime, 'video');
            } else {
                // TTS가 의도적으로 일시정지시킨 경우는 TTS를 멈추지 않음
                if (ttsHasVideoPaused) {
                    console.log(`[TTS 이벤트] YouTube 일시정지 상태지만 TTS가 의도적으로 멈춘 것이므로 TTS 계속 재생 (playerState: ${playerState})`);
                    // TTS는 계속 재생, 아무것도 하지 않음
                } else {
                    // 사용자가 일시정지/정지한 경우에만 TTS도 정지
                    console.log(`[TTS 이벤트] YouTube 일시정지/정지 (사용자 액션, playerState: ${playerState})`);
                    stopCurrentTts();
                }
            }
        } catch (error) {
            console.error('[TTS] YouTube 동기화 오류:', error);
        }
    }, 100);

    console.log('[TTS] YouTube 플레이어 동기화 시작');
}

// 오디오 플레이어와 TTS 동기화 시작
function startAudioTtsSync() {
    const audioPlayer = document.getElementById('audioPlayer');
    if (!audioPlayer) {
        console.warn('[TTS] 오디오 플레이어를 찾을 수 없습니다.');
        return;
    }

    // 기존 이벤트 리스너 제거
    if (window.audioTtsTimeUpdateHandler) {
        audioPlayer.removeEventListener('timeupdate', window.audioTtsTimeUpdateHandler);
    }

    // timeupdate 이벤트로 TTS 동기화
    window.audioTtsTimeUpdateHandler = () => {
        if (!ttsEnabled) {
            console.log('[TTS 이벤트] TTS 비활성화 상태 (audio)');
            return;
        }
        console.log(`[TTS 이벤트] Audio timeupdate - 현재 시간: ${audioPlayer.currentTime.toFixed(2)}s`);
        syncTtsWithTime(audioPlayer.currentTime, 'audio');
    };
    audioPlayer.addEventListener('timeupdate', window.audioTtsTimeUpdateHandler);

    // pause 이벤트로 TTS 정지
    audioPlayer.addEventListener('pause', stopCurrentTts);

    console.log('[TTS] 오디오 플레이어 동기화 시작');
}

// 현재 시간에 맞는 TTS 재생
function syncTtsWithTime(currentTime, dataType) {
    const segments = dataType === 'video' ? videoSegments : audioSegments;

    // 현재 시간에 해당하는 세그먼트 찾기
    const currentSegmentIdx = segments.findIndex(seg =>
        currentTime >= seg.start_time && currentTime < seg.end_time
    );

    if (currentSegmentIdx === -1) {
        // 해당하는 세그먼트 없음
        console.log(`[TTS 이벤트] 현재 시간 ${currentTime.toFixed(2)}s에 해당하는 세그먼트 없음 (${dataType})`);
        if (currentTtsSegment !== null) {
            stopCurrentTts();
        }
        return;
    }

    const segment = segments[currentSegmentIdx];
    const ttsAudio = ttsAudioElements[currentSegmentIdx];

    if (!ttsAudio) {
        console.log(`[TTS 이벤트] 세그먼트 ${currentSegmentIdx}에 TTS 오디오 없음 (${dataType})`);
        return; // TTS 오디오가 없는 세그먼트
    }

    // 새로운 세그먼트로 변경
    if (currentTtsSegment !== currentSegmentIdx) {
        console.log(`[TTS 이벤트] 세그먼트 변경 감지: ${currentTtsSegment} → ${currentSegmentIdx} (시간: ${currentTime.toFixed(2)}s, ${dataType})`);
        // 이전 TTS 정지
        stopCurrentTts();

        try {
            // 세그먼트 시작 시 처음부터 재생
            ttsAudio.currentTime = 0;

            // TTS 오디오 준비 상태 확인
            console.log(`[TTS 타이밍] 세그먼트 ${currentSegmentIdx} 재생 시도 - readyState: ${ttsAudio.readyState}, paused: ${ttsAudio.paused}, duration: ${ttsAudio.duration}s, src: ${ttsAudio.src}`);

            // 기존 재개 타이머 취소
            if (ttsResumeTimer) {
                clearTimeout(ttsResumeTimer);
                ttsResumeTimer = null;
            }

            // TTS가 세그먼트보다 긴 경우, 세그먼트 end_time에 도달했을 때 YouTube 일시정지
            if (ttsAudio.needsVideoPause && dataType === 'video' && youtubePlayer) {
                const segmentDuration = segment.end_time - segment.start_time;
                const ttsActualDuration = ttsAudio.duration / ttsAudio.playbackRate; // 실제 재생 시간
                const overlapTime = ttsActualDuration - segmentDuration;

                console.log(`[TTS 타이밍] 세그먼트 ${currentSegmentIdx} - 세그먼트 길이: ${segmentDuration.toFixed(2)}s, TTS 실제 시간: ${ttsActualDuration.toFixed(2)}s, 초과: ${overlapTime.toFixed(2)}s`);

                // 세그먼트 end_time에 도달했을 때 YouTube 일시정지하도록 타이머 설정
                ttsResumeTimer = setTimeout(() => {
                    // 세그먼트가 끝났는데 TTS가 아직 재생 중이면 YouTube 일시정지
                    if (!ttsAudio.paused && !ttsAudio.ended && youtubePlayer) {
                        const remainingTtsTime = (ttsAudio.duration - ttsAudio.currentTime) / ttsAudio.playbackRate;
                        console.log(`[TTS] 세그먼트 end_time 도달, YouTube 일시정지 (남은 TTS: ${remainingTtsTime.toFixed(2)}s)`);
                        ttsHasVideoPaused = true;
                        youtubePlayer.pauseVideo();

                        // TTS 남은 시간만큼만 일시정지
                        setTimeout(() => {
                            if (ttsHasVideoPaused && youtubePlayer) {
                                console.log(`[TTS] TTS 재생 완료 예상 시점, YouTube 다시 재생`);
                                ttsHasVideoPaused = false;
                                try {
                                    youtubePlayer.playVideo();
                                } catch (err) {
                                    console.error(`[TTS] YouTube 재생 오류:`, err);
                                }
                            }
                        }, remainingTtsTime * 1000);
                    }
                }, segmentDuration * 1000); // 세그먼트 duration 후에 체크

                console.log(`[TTS] YouTube는 계속 재생, ${segmentDuration.toFixed(2)}s 후 TTS 남은 시간만큼 일시정지 예정`);
            }

            ttsHasVideoPaused = false; // TTS 시작 시점에는 일시정지하지 않음

            ttsAudio.play().then(() => {
                console.log(`[TTS 타이밍] 세그먼트 ${currentSegmentIdx} 재생 성공! readyState: ${ttsAudio.readyState}, currentTime: ${ttsAudio.currentTime}s`);
            }).catch(err => {
                console.error(`[TTS 타이밍] 재생 오류 (세그먼트 ${currentSegmentIdx}):`, err);
                // 재생 이력 기록
                ttsPlaybackHistory.push({
                    segment: currentSegmentIdx,
                    action: 'play_error',
                    error: err.toString(),
                    time: new Date().toISOString()
                });
                // TTS 재생 실패 시 YouTube 복구
                if (ttsAudio.needsVideoPause && dataType === 'video' && youtubePlayer) {
                    console.log(`[TTS] 재생 실패, YouTube 다시 재생 (세그먼트 ${currentSegmentIdx})`);
                    try {
                        ttsHasVideoPaused = false; // 플래그 해제
                        youtubePlayer.playVideo();
                    } catch (playErr) {
                        console.error(`[TTS] YouTube 재생 복구 오류:`, playErr);
                    }
                }
            });
            currentTtsSegment = currentSegmentIdx;
            console.log(`[TTS 이벤트] 재생 시작: 세그먼트 ${currentSegmentIdx}`);
            // 재생 이력 기록
            ttsPlaybackHistory.push({
                segment: currentSegmentIdx,
                action: 'play_start',
                needsVideoPause: ttsAudio.needsVideoPause,
                time: new Date().toISOString()
            });
        } catch (error) {
            console.error(`[TTS] 재생 오류 (세그먼트 ${currentSegmentIdx}):`, error);
        }
    }
    // 같은 세그먼트 내에서는 동기화 조정하지 않음 (겹침 재생 방지)
}

// 현재 재생 중인 TTS 정지
function stopCurrentTts() {
    if (currentTtsSegment !== null && ttsAudioElements[currentTtsSegment]) {
        const ttsAudio = ttsAudioElements[currentTtsSegment];
        ttsAudio.pause();
        ttsAudio.currentTime = 0;
        console.log(`[TTS] 정지: 세그먼트 ${currentTtsSegment}`);

        // 타이머 취소
        if (ttsResumeTimer) {
            clearTimeout(ttsResumeTimer);
            ttsResumeTimer = null;
            console.log(`[TTS] 정지 시 타이머 취소`);
        }

        // TTS가 YouTube를 일시정지시킨 상태였다면 YouTube 복구
        if (ttsHasVideoPaused && ttsAudio.needsVideoPause && youtubePlayer) {
            console.log(`[TTS] 정지 시 YouTube 복구 (세그먼트 ${currentTtsSegment})`);
            ttsHasVideoPaused = false; // 플래그 해제
            try {
                youtubePlayer.playVideo();
            } catch (err) {
                console.error(`[TTS] YouTube 복구 오류:`, err);
            }
        }

        currentTtsSegment = null;
    }
}

// 디버깅용: TTS 재생 이력 출력
window.showTtsHistory = function() {
    console.log('=== TTS 재생 이력 ===');
    console.log(`총 ${ttsPlaybackHistory.length}개 이벤트`);
    ttsPlaybackHistory.forEach((event, idx) => {
        console.log(`[${idx}] 세그먼트 ${event.segment}: ${event.action}`, event);
    });
    return ttsPlaybackHistory;
};

// 디버깅용: TTS 재생 이력 초기화
window.clearTtsHistory = function() {
    ttsPlaybackHistory = [];
    console.log('TTS 재생 이력이 초기화되었습니다.');
};

console.log('✅ TTS 오디오 동기화 로직 로드 완료');
console.log('💡 디버깅: showTtsHistory() - TTS 재생 이력 확인');
