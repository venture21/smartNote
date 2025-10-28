document.addEventListener('DOMContentLoaded', () => {
    const urlInput = document.getElementById('youtube-url');
    const downloadBtn = document.getElementById('download-btn');
    const loadingDiv = document.getElementById('loading');
    const resultDiv = document.getElementById('result');
    const videoTitle = document.getElementById('video-title');
    const downloadLink = document.getElementById('download-link');
    const errorDiv = document.getElementById('error');
    const errorMessage = document.getElementById('error-message');

    downloadBtn.addEventListener('click', async () => {
        const url = urlInput.value.trim();
        if (!url) {
            showError('유튜브 URL을 입력해주세요.');
            return;
        }

        // 이전 상태 초기화
        hideAllMessages();
        loadingDiv.classList.remove('hidden');

        try {
            const response = await fetch('/download', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ url }),
            });

            loadingDiv.classList.add('hidden');

            if (response.ok) {
                const data = await response.json();
                videoTitle.textContent = data.title;
                downloadLink.href = data.file_path;
                downloadLink.download = data.title.replace(/[^a-zA-Z0-9]/g, '_') + '.mp4'; // 파일명 설정
                resultDiv.classList.remove('hidden');
            } else {
                const errorData = await response.json();
                showError(errorData.error || '다운로드에 실패했습니다.');
            }
        } catch (error) {
            loadingDiv.classList.add('hidden');
            showError('서버와 통신 중 오류가 발생했습니다.');
            console.error('Error:', error);
        }
    });

    function showError(message) {
        errorMessage.textContent = message;
        errorDiv.classList.remove('hidden');
    }

    function hideAllMessages() {
        loadingDiv.classList.add('hidden');
        resultDiv.classList.add('hidden');
        errorDiv.classList.add('hidden');
    }
});
