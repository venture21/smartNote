# YouTube Video Downloader

This is a simple web application that allows you to download YouTube videos by providing a URL.

## How to Use

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/your-username/youtube-downloader.git
    cd youtube-downloader
    ```

2.  **Create a virtual environment and activate it:**
    ```bash
    # For Windows
    python -m venv venv
    venv\Scripts\activate

    # For macOS/Linux
    python3 -m venv venv
    source venv/bin/activate
    ```

3.  **Install the required packages:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Run the application:**
    ```bash
    python app.py
    ```

5.  **Open your web browser and go to:**
    [http://127.0.0.1:5000](http://127.0.0.1:5000)

## How It Works

*   **Backend:** The backend is built with Flask. It takes a YouTube URL from the user, uses the `pytube` library to download the highest resolution video, and provides a download link.
*   **Frontend:** The frontend is a simple HTML page with CSS and JavaScript. It allows the user to enter the YouTube URL and handles the communication with the backend to display the download link.
