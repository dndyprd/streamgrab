import mimetypes
import os
from flask import Flask, Response, jsonify, render_template, request
from downloader import DOWNLOAD_DIR, delete_job, get_job, get_media_info, start_download_job

app = Flask(__name__)

# Route Home
@app.route("/")
def home():
  return render_template("index.html")

# Route Informasi Media
@app.route("/api/info", methods=["POST"])
def api_info():
  data = request.get_json(silent=True) or {}
  url = (data.get("url") or "").strip()

  if not url:
    return jsonify({"error": "URL wajib diisi."}), 400

  try:
    info = get_media_info(url)
    return jsonify(info)
  except ValueError as exc:
    return jsonify({"error": str(exc)}), 400
  except Exception as exc:
    return jsonify({"error": f"Gagal mengambil informasi: {exc}"}), 500

# Route Download
@app.route("/api/download", methods=["POST"])
def api_download():
  data = request.get_json(silent=True) or {}
  url = (data.get("url") or "").strip()
  fmt = (data.get("format") or "mp4").strip().lower()
  quality = str(data.get("quality") or "max").strip()

  if not url:
    return jsonify({"error": "URL wajib diisi."}), 400

  if fmt not in ("mp4", "mp3"):
    return jsonify({"error": "Format harus 'mp4' atau 'mp3'."}), 400

  try:
    job_id = start_download_job(url=url, fmt=fmt, quality=quality)
    return jsonify({"job_id": job_id}), 202
  except ValueError as exc:
    return jsonify({"error": str(exc)}), 400
  except Exception as exc:
    return jsonify({"error": f"Gagal memulai unduhan: {exc}"}), 500

# Route Progress Download
@app.route("/api/progress/<job_id>", methods=["GET"])
def api_progress(job_id: str):
  job = get_job(job_id)
  if not job:
    return jsonify({"error": "Job tidak ditemukan."}), 404

  return jsonify({
      "status": job.get("status"),
      "percent": job.get("percent", 0),
      "stage": job.get("stage", ""),
      "speed": job.get("speed", ""),
      "eta": job.get("eta", ""),
      "error": job.get("error"),
  })

# Route File
@app.route("/api/file/<job_id>", methods=["GET"])
def api_file(job_id: str):
  job = get_job(job_id)
  if not job or job.get("status") != "ready":
    return jsonify({"error": "File belum siap atau sudah kedaluwarsa."}), 404

  file_path = job.get("file_path")
  download_name = job.get("download_name") or "download"

  if not file_path or not os.path.exists(file_path):
    return jsonify({"error": "File tidak ditemukan."}), 404

  try:
    file_size = os.path.getsize(file_path)
  except OSError:
    file_size = None

  content_type, _ = mimetypes.guess_type(download_name)
  if not content_type:
    content_type = "application/octet-stream"

  def generate():
    try:
      with open(file_path, "rb") as fp:
        while chunk := fp.read(1024 * 64):
          yield chunk
    finally:
      try:
        if os.path.exists(file_path):
          os.remove(file_path)
      except OSError:
        pass
      delete_job(job_id)

  headers = {
      "Content-Disposition": f'attachment; filename="{download_name}"',
  }
  if file_size is not None:
    headers["Content-Length"] = str(file_size)

  return Response(
      generate(),
      mimetype=content_type,
      headers=headers,
  )

if __name__ == "__main__":
  app.run(host="0.0.0.0", port=5000, debug=True)