import os
from flask import Flask, jsonify, after_this_request, request, send_file, render_template
from downloader import download_mp3, download_mp4

app = Flask(__name__)

@app.route("/")
def home():
  return render_template("index.html")

@app.route("/api/info/", methods=["POST"])
def api_info():
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()

    if not url:
        return jsonify({"error": "URL wajib diisi."}), 400
    
    try:
        info = get_media_info(url)
        return jsonify(info)
    except Exception as exc:
        return jsonify({"error": f"Gagal mengambil informasi : {exc}"}), 500

@app.route("/api/download/", methods=["POST"])
def api_download():
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or request.form.get("url") or "").strip()
    fmt = (data.get("format") or request.form.get("format") or "mp4").strip().lower()
    quality = str(data.get("quality") or ("max" if fmt == "mp4" else "192")).strip()

    if not url:
        return jsonify({"error" : "URL wajib diisi."}), 400

    if fmt not in ("mp4", "mp3"):
        return jsonify({"error": "Format harus mp4 atau mp3."}), 400
    
    try:
        if fmt == "mp3":
            file_path, download_name = download_mp3(url)
        else:
            file_path, download_name = download_mp4(url)
    except Exception as exc:
        return jsonify({"error": f"Gagal memproses unduhan: {exc}"}), 500

    @after_this_request
    def cleanup_file(response):
        try:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
        except OSError:
            pass
        return response
    
    return send_file(
        file_path,
        as_attachment=True,
        download_name=download_name,
    )

if __name__ == "__main__":
  app.run(host="0.0.0.0", port=5000, debug=True)