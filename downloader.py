import json
import os
import re
import threading
import time
import uuid
import yt_dlp

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

_STATE_LOCK = threading.Lock()
_JOBS: dict[str, dict] = {}
_LAST_WRITE_TIME: dict[str, float] = {}

try:
  MAX_DURATION_SECONDS = int(os.getenv("MAX_DURATION_SECONDS", "1200"))
except (ValueError, TypeError):
  MAX_DURATION_SECONDS = 1200


# Periksa Durasi Video
def _format_duration_limit(seconds: int) -> str:
  mins, secs = divmod(max(0, int(seconds)), 60)
  if secs == 0:
    return f"{mins} menit"
  return f"{mins} menit {secs} detik"


def _check_duration_limit(info: dict):
  raw_duration = info.get("duration")
  if raw_duration is not None:
    try:
      duration = float(raw_duration)
      if duration > MAX_DURATION_SECONDS:
        limit_text = _format_duration_limit(MAX_DURATION_SECONDS)
        raise ValueError(
            f"Durasi media melebihi batas maksimal ({limit_text})."
        )
    except (ValueError, TypeError) as exc:
      if "Durasi media melebihi batas maksimal" in str(exc):
        raise

def _job_file_path(job_id: str) -> str:
  safe_id = re.sub(r"[^a-zA-Z0-9_-]", "", job_id)
  return os.path.join(DOWNLOAD_DIR, f".job_{safe_id}.json")

# Atur status download
def _set_job(job_id: str, **updates):
  path = _job_file_path(job_id)
  with _STATE_LOCK:
    current = _JOBS.get(job_id)
    if current is None:
      current = {}
      if os.path.exists(path):
        for _ in range(3):
          try:
            with open(path, "r", encoding="utf-8") as f:
              loaded = json.load(f)
              if isinstance(loaded, dict):
                current = loaded
                break
          except (OSError, json.JSONDecodeError):
            time.sleep(0.01)
    current.update(updates)
    _JOBS[job_id] = current

    # Tulis atomik ke disk menggunakan nama file unik
    tmp_path = f"{path}.tmp.{os.getpid()}_{uuid.uuid4().hex[:6]}"
    try:
      with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(current, f)
        f.flush()
        os.fsync(f.fileno())
      os.replace(tmp_path, path)
    except OSError:
      try:
        time.sleep(0.02)
        os.replace(tmp_path, path)
      except OSError:
        pass
    finally:
      if os.path.exists(tmp_path):
        try:
          os.remove(tmp_path)
        except OSError:
          pass

# Dapatkan status download
def get_job(job_id: str) -> dict | None:
  path = _job_file_path(job_id)

  with _STATE_LOCK:
    mem_job = _JOBS.get(job_id)

  for attempt in range(5):
    if not os.path.exists(path):
      if mem_job is not None:
        return dict(mem_job)
      if attempt < 4:
        time.sleep(0.025)
        continue
      return None

    try:
      with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
        if isinstance(data, dict) and data:
          with _STATE_LOCK:
            _JOBS[job_id] = data
          return data
    except (OSError, json.JSONDecodeError):
      time.sleep(0.025)

  with _STATE_LOCK:
    return dict(_JOBS[job_id]) if job_id in _JOBS else None

# Hapus File
def delete_job(job_id: str):
  path = _job_file_path(job_id)
  with _STATE_LOCK:
    _JOBS.pop(job_id, None)
    _LAST_WRITE_TIME.pop(job_id, None)
    for p in (path,):
      try:
        if os.path.exists(p):
          os.remove(p)
      except OSError:
        pass

    safe_id = re.sub(r"[^a-zA-Z0-9_-]", "", job_id)
    prefix = f".job_{safe_id}.json.tmp"
    try:
      for fname in os.listdir(DOWNLOAD_DIR):
        if fname.startswith(prefix):
          try:
            os.remove(os.path.join(DOWNLOAD_DIR, fname))
          except OSError:
            pass
    except OSError:
      pass

# Menghapus cache download lama
def clean_stale_downloads(max_age_seconds: int = 3600):
  now = time.time()
  try:
    for fname in os.listdir(DOWNLOAD_DIR):
      if fname == ".gitkeep":
        continue
      fpath = os.path.join(DOWNLOAD_DIR, fname)
      try:
        if os.path.isfile(fpath) and (now - os.path.getmtime(fpath) > max_age_seconds):
          os.remove(fpath)
      except OSError:
        pass
  except OSError:
    pass

# Kelola Persentase
def _parse_percent(raw_str: str | None) -> float:
  if not raw_str:
    return 0.0
  cleaned = re.sub(r"\x1b\[[0-9;]*m", "", raw_str).replace("%", "").strip()
  try:
    return max(0.0, min(100.0, float(cleaned)))
  except ValueError:
    return 0.0


# Bersihkan Nama File
def _sanitize_filename(name: str) -> str:
  cleaned = re.sub(r'[\\/*?:"<>|]', "", name).strip()
  return cleaned or "media"


# Mendapatkan informasi media
def get_media_info(url: str) -> dict:
  ydl_opts = {
      "quiet": True,
      "no_warnings": True,
      "noplaylist": True,
  }

  with yt_dlp.YoutubeDL(ydl_opts) as ydl:
    info = ydl.extract_info(url, download=False)

  _check_duration_limit(info)

  return {
      "title": info.get("title", "Media Tanpa Judul"),
      "thumbnail": info.get("thumbnail", ""),
      "duration": info.get("duration_string", ""),
      "uploader": info.get("uploader", ""),
  }


# Mulai Download
def start_download_job(
    url: str, fmt: str = "mp4", quality: str = "max"
) -> str:
  threading.Thread(target=clean_stale_downloads, daemon=True).start()
  job_id = str(uuid.uuid4())[:8]
  _set_job(
      job_id,
      status="downloading",
      percent=0.0,
      stage="Menyiapkan unduhan...",
      speed="",
      eta="",
      file_path=None,
      download_name=None,
      error=None,
  )

  thread = threading.Thread(
      target=_run_download_worker,
      args=(job_id, url, fmt, quality),
      daemon=True,
  )
  thread.start()
  return job_id


# Jalankan Download
def _run_download_worker(job_id: str, url: str, fmt: str, quality: str):
  outtmpl = os.path.join(DOWNLOAD_DIR, f"streamgrab_%(title)s_{job_id}.%(ext)s")
  clean_quality = (quality or "max").strip().lower()

  last_pct = [-1.0]

  def progress_hook(d):
    status = d.get("status")
    if status == "downloading":
      pct = _parse_percent(d.get("_percent_str"))
      now = time.time()
      last_write = _LAST_WRITE_TIME.get(job_id, 0.0)

      # Throttle penulisan status progress agar tidak terjadi tabrakan disk I/O
      if (now - last_write < 0.4) and (abs(pct - last_pct[0]) < 1.0) and (pct < 99.0):
        return

      _LAST_WRITE_TIME[job_id] = now
      last_pct[0] = pct

      speed = re.sub(
          r"\x1b\[[0-9;]*m", "", (d.get("_speed_str") or "")
      ).strip()
      eta = re.sub(r"\x1b\[[0-9;]*m", "", (d.get("_eta_str") or "")).strip()
      _set_job(
          job_id,
          status="downloading",
          percent=pct,
          stage="Mengunduh media...",
          speed=speed,
          eta=eta,
      )
    elif status == "finished":
      _LAST_WRITE_TIME[job_id] = time.time()
      _set_job(
          job_id,
          status="processing",
          percent=99.0,
          stage="Mengonversi & menggabungkan file...",
          speed="",
          eta="",
      )

  try:
    if fmt == "mp3":
      bitrate = (
          clean_quality if clean_quality in ("320", "192", "128") else "320"
      )
      label_tag = (
          f"{bitrate}kbps" if clean_quality in ("320", "192", "128") else "max"
      )
      ydl_opts = {
          "outtmpl": outtmpl,
          "noplaylist": True,
          "format": "bestaudio/best",
          "progress_hooks": [progress_hook],
          "postprocessors": [{
              "key": "FFmpegExtractAudio",
              "preferredcodec": "mp3",
              "preferredquality": bitrate,
          }],
          "quiet": True,
          "no_warnings": True,
      }
      ext = "mp3"
    else:
      if clean_quality.isdigit():
        height = clean_quality
        fmt_selector = (
            f"bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]/"
            f"best[height<={height}][ext=mp4]/"
            f"best[height<={height}]"
        )
        preset_tag = f"{height}p"
      else:
        fmt_selector = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
        preset_tag = "max"

      ydl_opts = {
          "outtmpl": outtmpl,
          "noplaylist": True,
          "format": fmt_selector,
          "merge_output_format": "mp4",
          "progress_hooks": [progress_hook],
          "quiet": True,
          "no_warnings": True,
      }
      ext = "mp4"

    # Proses Download
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
      info = ydl.extract_info(url, download=False)
      _check_duration_limit(info)
      info = ydl.extract_info(url, download=True)
      prepared = ydl.prepare_filename(info)

    base_no_ext, _ = os.path.splitext(prepared)
    final_path = f"{base_no_ext}.{ext}"

    if not os.path.exists(final_path):
      suffix = f"_{job_id}.{ext}"
      for filename in os.listdir(DOWNLOAD_DIR):
        if filename.startswith("streamgrab_") and filename.endswith(suffix):
          final_path = os.path.join(DOWNLOAD_DIR, filename)
          break

    if not os.path.exists(final_path):
      raise FileNotFoundError(
          f"File {ext.upper()} tidak ditemukan setelah diproses."
      )

    title = info.get("title", "media")
    if fmt == "mp3":
      actual_abr = info.get("abr")
      final_tag = f"{int(actual_abr)}kbps" if actual_abr else label_tag
    else:
      if clean_quality.isdigit():
        final_tag = preset_tag
      else:
        actual_height = info.get("height")
        final_tag = f"{actual_height}p" if actual_height else "max"

    download_name = f"{_sanitize_filename(title)}_{final_tag}.{ext}"

    _set_job(
        job_id,
        status="ready",
        percent=100.0,
        stage="Siap diunduh!",
        speed="",
        eta="",
        file_path=final_path,
        download_name=download_name,
    )
  except Exception as exc:
    _set_job(
        job_id,
        status="error",
        stage="Gagal memproses",
        error=str(exc),
    )