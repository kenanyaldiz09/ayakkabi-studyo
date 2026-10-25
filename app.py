import io
import os
import zipfile
from pathlib import Path
from flask import Flask, render_template, request, send_file, jsonify
import requests
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 250 * 30 * 1024 * 1024  # upload cap: approx. 250 images, each up to 30 MB
ALLOWED = {".jpg", ".jpeg", ".png", ".webp", ".avif"}
PHOTOROOM_ENDPOINT = "https://image-api.photoroom.com/v2/edit"

@app.get("/")
def home():
    return render_template("index.html")

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/process")
def process_images():
    api_key = os.getenv("PHOTOROOM_API_KEY", "").strip()
    if not api_key:
        return jsonify(error="Photoroom API anahtarı sunucuda ayarlanmamış. Kurulum dosyasındaki README adımlarını izleyin."), 400

    files = request.files.getlist("photos")
    style = request.form.get("style", "classic")
    if not files or not any(f.filename for f in files):
        return jsonify(error="Lütfen önce fotoğraf seçin."), 400
    if len(files) > 250:
        return jsonify(error="Bir seferde en fazla 250 fotoğraf seçebilirsiniz."), 400

    output = io.BytesIO()
    completed = 0
    failed = []
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for idx, file in enumerate(files, start=1):
            if not file.filename:
                continue
            original_name = secure_filename(file.filename)
            suffix = Path(original_name).suffix.lower()
            if suffix not in ALLOWED:
                failed.append(f"{original_name}: desteklenmeyen dosya türü")
                continue

            try:
                file_bytes = file.read()
                if not file_bytes:
                    failed.append(f"{original_name}: dosya boş")
                    continue

                form_data = {
                    "removeBackground": "true",
                    "padding": "0.12",
                    "export.format": "png",
                }
                headers = {"x-api-key": api_key}
                if style == "classic":
                    form_data.update({
                        "background.color": "FFFFFF",
                        "shadow.mode": "ai.soft",
                        "lighting.mode": "ai.preserve-hue-and-saturation",
                    })
                else:
                    form_data.update({
                        "background.prompt": (
                            "A premium commercial shoe product photograph in a refined light grey studio, "
                            "subtle sculptural platform, elegant directional studio lighting, realistic soft "
                            "contact shadow, clean luxury e-commerce photography, neutral background, "
                            "no text, no logo additions, no extra shoes"
                        ),
                        "pr-ai-background-model-version": "background-studio-beta-2025-03-17",
                    })

                response = requests.post(
                    PHOTOROOM_ENDPOINT,
                    headers=headers,
                    data=form_data,
                    files={"imageFile": (original_name, io.BytesIO(file_bytes), file.mimetype or "application/octet-stream")},
                    timeout=180,
                )
                if response.status_code >= 400:
                    # Do not expose the API key or full upstream response in the error.
                    failed.append(f"{original_name}: Photoroom hatası ({response.status_code})")
                    continue

                stem = Path(original_name).stem or f"ayakkabi_{idx}"
                archive.writestr(f"{stem}_{style}.png", response.content)
                completed += 1
            except requests.Timeout:
                failed.append(f"{original_name}: işlem zaman aşımına uğradı")
            except Exception:
                failed.append(f"{original_name}: işlem sırasında hata oluştu")

    if completed == 0:
        return jsonify(error="Hiçbir fotoğraf düzenlenemedi.", details=failed[:10]), 502

    output.seek(0)
    response = send_file(
        output,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"ayakkabi_studyo_{style}.zip",
    )
    response.headers["X-Processed-Images"] = str(completed)
    response.headers["X-Failed-Images"] = str(len(failed))
    return response

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=False)
