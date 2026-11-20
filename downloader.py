import os
import re
import uuid
import yt_dlp

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Bersihkan Nama File
def _sanitize_filename(name: str) -> str:
    cleaned = re.sub(r'[\\/*?:"<>|]', "", name).strip()
    return cleaned or "media"

def get_media_info(url: str) -> dict:
    """ 
        Dapatkan informasi YouTube Video
    """

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }

    # Eksekusi Info 
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    return {
        "title": info.get("title", "Media Tanpa Judul"),
        "thumbnail": info.get("thumbnail", ""),
        "duration": info.get("duration_string", ""),
        "uploader": info.get("uploader", ""),
    }
    

# Setup YouTube to MP4
def download_mp4(url: str, quality: str = "max") -> tuple[str, str]:

    # Format nama file
    job_id = str(uuid.uuid4())[:6]
    outtmpl = os.path.join(DOWNLOAD_DIR, f"streamgrab_%(title)s_{job_id}.%(ext)s")

    # Dapatkan kualitas tertinggi
    clean_quality = (quality or "max").strip().lower()

    if clean_quality.isdigit():
        height = clean_quality
        fmt_selector = (
            f"bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]/"
            f"best[height<={height}][ext=mp4]/"
            f"best[height<={height}]"
        )
        label_suffix = f"{height}p"
    else:
        fmt_selector = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
        label_suffix = "max"

    ydl_opts = {
        "outtmpl": outtmpl,
        "noplaylist": True,
        "format": fmt_selector,
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
    }

    # Eksekusi Download
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        prepared = ydl.prepare_filename(info)

    base_no_ext, _ = os.path.splitext(prepared)
    final_path = f"{base_no_ext}.mp4"

    if not os.path.exists(final_path):
        suffix = f"_{job_id}.mp4"
        for filename in os.listdir(DOWNLOAD_DIR):
            if filename.startswith("streamgrab_") and filename.endswith(suffix):
                final_path = os.path.join(DOWNLOAD_DIR, filename)
                break
    if not os.path.exists(final_path):
        raise FileNotFoundError("File MP4 tidak ditemukan.")

    # Mengembalikan Hasil
    title = info.get("title", "video")
    download_name = f"{_sanitize_filename(title)}.mp4"
    return final_path, download_name    

# Setup YouTube to MP3    
def download_mp3(url: str, quality: str = "max") -> tuple[str, str]:

    # Format nama file
    job_id = str(uuid.uuid4())[:6]
    outtmpl = os.path.join(DOWNLOAD_DIR, f"streamgrab_%(title)s_{job_id}.%(ext)s")

    # Dapatkan kualitas tertinggi
    clean_quality = (quality or "max").strip().lower()

    if clean_quality in ("320", "192", "128"):
        bitrate = clean_quality
        label_tag = f"{bitrate}kbps"
    else:
        bitrate = "320"
        label_tag = "max"

    ydl_opts = {
        "outtmpl": outtmpl,
        "noplaylist": True,
        "format": "bestaudio/best",
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }],
        "quiet": True,
        "no_warnings": True,
    }

    # Eksekusi Download
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        prepared = ydl.prepare_filename(info)

    base_no_ext, _ = os.path.splitext(prepared)
    final_path = f"{base_no_ext}.mp3"

    if not os.path.exists(final_path):
        suffix = f"_{job_id}.mp3"
        for filename in os.listdir(DOWNLOAD_DIR):
            if filename.startswith("streamgrab_") and filename.endswith(suffix):
                final_path = os.path.join(DOWNLOAD_DIR, filename)
                break

    if not os.path.exists(final_path):
        raise FileNotFoundError("File MP3 tidak ditemukan.")

    title = info.get("title", "audio")
    download_name = f"{_sanitize_filename(title)}.mp3"
    return final_path, download_name