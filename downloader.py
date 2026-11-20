import os
import uuid
import yt_dlp

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Bersihkan Nama File
def _sanitize_filename(name: str) -> str:
    cleaned = "".join(
        c for c in name if c.isalnum() or c  in ("", "_", "-")
    ).strip()
    return cleaned or "video"

# Setup YouTube to MP4
def download_mp4(url: str) -> tuple[str, str]:
    """
        YouTube Video to MP4
    """

    # Format nama file
    job_id = str(uuid.uuid4())[:6]
    outtmpl = os.path.join(DOWNLOAD_DIR, f"streamgrab_%(title)s_{job_id}.%(ext)s")

    ydl_opts = {
        "outtmpl": outtmpl,
        "noplaylist": True,
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
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
        for filename in os.listdir(DOWNLOAD_DIR):
            if filename.startswith(job_id) and filename.endswith(".mp4"):
                final_path = os.path.join(DOWNLOAD_DIR, filename)
                break
    if not os.path.exists(final_path):
        raise FileNotFoundError("File unduhan tidak ditemukan.")

    # Mengembalikan Hasil
    title = info.get("title", "video")
    download_name = f"{_sanitize_filename(title)}.mp4"
    return final_path, download_name