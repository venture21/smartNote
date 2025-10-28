from flask import Flask, request, send_file, jsonify
import yt_dlp
import os
import logging

app = Flask(__name__, static_folder='static', static_url_path='')
logging.basicConfig(level=logging.INFO)

# 다운로드 폴더 설정
DOWNLOAD_FOLDER = 'downloads'
if not os.path.exists(DOWNLOAD_FOLDER):
    os.makedirs(DOWNLOAD_FOLDER)

@app.route('/')
def index():
    """
    메인 페이지를 렌더링합니다.
    """
    return app.send_static_file('index.html')

@app.route('/download', methods=['POST'])
def download_video():
    """
    유튜브 URL을 받아 동영상을 다운로드하고 파일 경로를 반환합니다.
    """
    data = request.get_json()
    url = data.get('url')

    if not url:
        return jsonify({'error': 'URL is required'}), 400

    try:
        logging.info(f'Downloading video from: {url}')
        
        ydl_opts = {
            'format': 'best[ext=mp4]/best',
            'outtmpl': os.path.join(DOWNLOAD_FOLDER, '%(title).20s-%(id)s.%(ext)s'),
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            video_title = info_dict.get('title', None)
            downloaded_filepath = info_dict.get('_filename', None)
            
        if downloaded_filepath:
            filename = os.path.basename(downloaded_filepath)
            output_path = downloaded_filepath
        else:
            # Fallback if _filename is not available (should not happen with download=True)
            video_id = info_dict.get('id', None)
            file_ext = info_dict.get('ext', 'mp4')
            filename = f'{video_id}.{file_ext}'
            output_path = os.path.join(DOWNLOAD_FOLDER, filename)

        logging.info(f'Video downloaded to: {output_path}')
        
        # 다운로드된 파일 경로를 클라이언트에게 전달
        return jsonify({
            'file_path': f'/get-video/{filename}',
            'title': video_title
        })

    except Exception as e:
        logging.error(f"Error downloading video: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/get-video/<filename>')
def get_video(filename):
    """
    다운로드된 비디오 파일을 클라이언트에게 전송합니다.
    """
    file_path = os.path.join(DOWNLOAD_FOLDER, filename)
    if os.path.exists(file_path):
        return send_file(file_path, as_attachment=True)
    else:
        return "File not found.", 404

if __name__ == '__main__':
    app.run(debug=True, port=5000)