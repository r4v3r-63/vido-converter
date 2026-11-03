"""Local batch video converter. Requires Python 3.10+ and FFmpeg."""
import argparse
import email.policy
import json
import mimetypes
import shutil
import subprocess
import tempfile
import threading
import uuid
import zipfile
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).parent
JOBS = {}
LOCK = threading.Lock()
SIZES = {"original": None, "2160": (3840, 2160), "1080": (1920, 1080), "720": (1280, 720), "480": (854, 480)}
FORMATS = {"mp4": ["-c:v", "libx264", "-preset", "fast", "-crf", "23", "-c:a", "aac", "-movflags", "+faststart"], "mkv": ["-c:v", "libx264", "-preset", "fast", "-crf", "23", "-c:a", "aac"], "webm": ["-c:v", "libvpx-vp9", "-crf", "32", "-b:v", "0", "-c:a", "libopus"]}


def command(source, target, size, fps, mute):
    filters = []
    if SIZES[size]:
        w, h = SIZES[size]
        filters.append(f"scale={w}:{h}:force_original_aspect_ratio=decrease:force_divisible_by=2,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1")
    else:
        filters.append("scale=trunc(iw/2)*2:trunc(ih/2)*2")
    if fps != "original":
        filters.append(f"fps={fps}")
    args = ["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", str(source), "-map", "0:v:0", "-map", "0:a:0?", "-vf", ",".join(filters), *FORMATS[target.suffix[1:]], "-pix_fmt", "yuv420p", "-threads", "2"]
    if mute:
        args.append("-an")
    return args + [str(target)]


def convert(job_id, directory, inputs, settings):
    job = JOBS[job_id]
    for index, (source, name) in enumerate(inputs):
        item = job["files"][index]
        item["status"] = "processing"
        target = directory / f"{index + 1:03d}_{Path(name).stem}.{settings['format']}"
        try:
            result = subprocess.run(command(source, target, settings["size"], settings["fps"], settings["mute"]), capture_output=True, text=True)
            if result.returncode:
                raise ValueError(result.stderr[-1500:] or "FFmpeg не смог обработать файл")
            item.update(status="done", url=f"/download/{job_id}/{target.name}")
        except Exception as exc:
            target.unlink(missing_ok=True)
            item.update(status="error", error=str(exc))
        finally:
            source.unlink(missing_ok=True)
    outputs = [directory / Path(f["url"]).name for f in job["files"] if f["status"] == "done"]
    if outputs:
        with zipfile.ZipFile(directory / "videos.zip", "w", compression=zipfile.ZIP_STORED) as archive:
            for output in outputs:
                archive.write(output, output.name)
        job["archive"] = f"/download/{job_id}/videos.zip"
    job["status"] = "done"


class Handler(BaseHTTPRequestHandler):
    def json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parts = urlparse(self.path).path.split("/")
        if self.path == "/":
            path = ROOT / "index.html"
        elif len(parts) == 3 and parts[1] == "jobs" and parts[2] in JOBS:
            job = JOBS[parts[2]]
            return self.json({k: v for k, v in job.items() if k != "directory"})
        elif len(parts) == 4 and parts[1] == "download" and parts[2] in JOBS:
            from urllib.parse import unquote
            name = unquote(parts[3])
            if Path(name).name != name:
                return self.send_error(404)
            job = JOBS[parts[2]]
            allowed = [Path(f["url"]).name for f in job["files"] if f.get("url")]
            if job.get("archive"):
                allowed.append("videos.zip")
            if name not in allowed:
                return self.send_error(404)
            path = Path(job["directory"]) / name
        else:
            return self.send_error(404)
        if not path.is_file():
            return self.send_error(404)
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(path.stat().st_size))
        if parts[1:2] == ["download"]:
            from urllib.parse import quote
            self.send_header("Content-Disposition", "attachment; filename*=UTF-8''" + quote(path.name))
        self.end_headers()
        with path.open("rb") as file:
            shutil.copyfileobj(file, self.wfile)

    def do_POST(self):
        if self.path != "/convert":
            return self.send_error(404)
        directory = None
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 512 * 1024 * 1024:
                return self.json({"error": "Размер пакета должен быть от 1 байта до 512 МБ."}, 413)
            content_type = self.headers.get("Content-Type", "")
            if not content_type.startswith("multipart/form-data;") or "\r" in content_type or "\n" in content_type:
                raise ValueError("Ожидается загрузка файлов multipart/form-data")
            message = BytesParser(policy=email.policy.default).parsebytes(("Content-Type: " + content_type + "\r\nMIME-Version: 1.0\r\n\r\n").encode() + self.rfile.read(length))
            fields, files = {}, []
            for part in message.iter_parts():
                name = part.get_param("name", header="content-disposition")
                if part.get_filename():
                    files.append((Path(part.get_filename().replace("\\", "/")).name, part.get_payload(decode=True)))
                else:
                    fields[name] = part.get_content().strip()
            settings = {"format": fields.get("format", "mp4"), "size": fields.get("size", "original"), "fps": fields.get("fps", "original"), "mute": fields.get("mute") == "true"}
            if settings["format"] not in FORMATS or settings["size"] not in SIZES or settings["fps"] not in {"original", "24", "25", "30", "50", "60"}:
                raise ValueError("Неверные настройки конвертации")
            if not files or len(files) > 100:
                raise ValueError("Выберите от 1 до 100 видеофайлов")
            with LOCK:
                if any(j["status"] == "processing" for j in JOBS.values()):
                    return self.json({"error": "Уже выполняется конвертация. Дождитесь завершения."}, 409)
                directory = Path(tempfile.mkdtemp(prefix="video-converter-"))
                inputs = []
                for index, (name, data) in enumerate(files):
                    source = directory / f"input_{index}"
                    source.write_bytes(data)
                    inputs.append((source, name))
                job_id = uuid.uuid4().hex
                JOBS[job_id] = {"status": "processing", "directory": str(directory), "files": [{"name": name, "status": "waiting"} for name, _ in files]}
                threading.Thread(target=convert, args=(job_id, directory, inputs, settings), daemon=True).start()
            self.json({"id": job_id}, 202)
        except (ValueError, TypeError) as exc:
            if directory:
                shutil.rmtree(directory, ignore_errors=True)
            self.json({"error": str(exc)}, 400)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if not shutil.which("ffmpeg"):
        parser.error("Установите FFmpeg и добавьте его в PATH")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Конвертер запущен: http://127.0.0.1:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
