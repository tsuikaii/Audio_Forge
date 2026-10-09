#!/usr/bin/env python3
"""Audio Forge: a local browser interface using only the Python standard library."""

import argparse
import base64
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import subprocess
import sys
import threading
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
import webbrowser

from . import media
from .i18n import error_data, language, translate

WEB = Path(__file__).resolve().parent / "web"
BROWSE_ROOT = WEB.parents[2]
if os.environ.get("AUDIO_FORGE_DESKTOP") == "1":
    BROWSE_ROOT = Path.home() / "Music"
    if not BROWSE_ROOT.is_dir():
        BROWSE_ROOT = Path.home()
TOKEN = secrets.token_urlsafe(32)
LOCK = threading.Lock()
JOB = {"state": "idle", "message_key": "ready", "output": ""}
GUI_TAGS = ("title", "artist", "album", "date")


def prepare_args(payload):
    source = Path(payload["input"]).expanduser().resolve()
    source_format = source.suffix.lower().lstrip(".")
    if source_format not in media.FORMATS or not source.is_file():
        raise media.MediaError("err_input_format")
    target_format = payload.get("target_format")
    if target_format is None:
        target_format = Path(payload["output"]).suffix.lower().lstrip(".") if payload.get("output") else ("m4a" if source_format == "mp4" else source_format)
    if target_format not in media.FORMATS:
        raise media.MediaError("err_output_format")
    action = "edit" if source_format == target_format else "convert"
    output = Path(os.path.abspath(payload.get("output") or str(source.with_suffix("." + target_format))))
    if output.suffix.lower() != "." + target_format:
        raise media.MediaError("err_format_mismatch")
    tags = payload.get("tags", {})
    original = media.normalized_tags(media.probe(source))
    values = {}
    removed = []
    for key in media.TAGS:
        if key not in tags or key not in GUI_TAGS:
            values[key] = None
            continue
        value = tags[key]
        if not isinstance(value, str):
            raise media.MediaError("err_tag_text")
        values[key] = value if value else None
        if not value and original.get(key):
            removed.append(key)
    cover_action = payload.get("cover_action", "keep")
    if cover_action not in ("keep", "remove", "replace"):
        raise media.MediaError("err_cover_action")
    cover = Path(payload["cover"]) if cover_action == "replace" and payload.get("cover") else None
    if cover_action == "replace" and cover is None:
        raise media.MediaError("err_cover")
    codec = payload.get("codec", "auto")
    bitrate = payload.get("bitrate", "256k")
    if codec not in ("auto", "aac", "alac") or bitrate not in ("128k", "192k", "256k", "320k"):
        raise media.MediaError("err_encoding")
    if target_format in ("mp3", "flac"):
        codec = "auto"
    return argparse.Namespace(
        language=language(payload.get("language")), action=action, input=source, output=output, codec=codec if action == "convert" else "copy",
        bitrate=bitrate, overwrite=bool(payload.get("overwrite", False)),
        cover=cover, remove_cover=cover_action == "remove",
        clear_metadata=bool(payload.get("clear_metadata", False)), remove_tag=removed, **values,
    )


def list_files(payload):
    kind = payload.get("kind", "input")
    if kind not in ("input", "cover", "output"):
        raise media.MediaError("err_picker_kind")
    directory = Path(payload.get("directory") or BROWSE_ROOT).expanduser().resolve()
    if not directory.is_dir():
        raise media.MediaError("err_directory")
    suffixes = {"input": {"." + f for f in media.FORMATS}, "cover": {".jpg", ".jpeg", ".png"}, "output": {"." + payload.get("target_format", "m4a")}}[kind]
    entries = []
    for entry in directory.iterdir():
        if entry.name.startswith("."):
            continue
        try:
            is_dir = entry.is_dir()
            if is_dir or (entry.is_file() and entry.suffix.lower() in suffixes):
                entries.append({"name": entry.name, "path": str(entry), "is_dir": is_dir})
        except OSError:
            continue
    entries.sort(key=lambda e: (not e["is_dir"], e["name"].casefold()))
    return {"directory": str(directory), "parent": str(directory.parent), "entries": entries,
            "shortcuts": {"folder_music" if os.environ.get("AUDIO_FORGE_DESKTOP") == "1" else "folder_app": str(BROWSE_ROOT), "folder_downloads": str(Path.home() / "Downloads"), "folder_home": str(Path.home())}}


def select_file(payload):
    kind = payload.get("kind")
    path = Path(payload["path"]).expanduser().resolve()
    if not path.is_file():
        raise media.MediaError("err_input_missing", path=str(path))
    if kind == "cover":
        if path.suffix.lower() not in (".jpg", ".jpeg", ".png"):
            raise media.MediaError("err_cover")
        info = media.probe(path)
        if not info.get("streams") or info["streams"][0].get("codec_name") not in ("mjpeg", "png"):
            raise media.MediaError("err_cover_content")
        return {"path": str(path), "artwork_data": artwork_data(path, 0)}
    if kind != "input" or path.suffix.lower().lstrip(".") not in media.FORMATS:
        raise media.MediaError("err_input_format")
    info = media.probe(path)
    audio = next((s for s in info.get("streams", []) if s.get("codec_type") == "audio"), None)
    if audio is None:
        raise media.MediaError("err_no_audio")
    source_format = path.suffix.lower().lstrip(".")
    target_format = "m4a" if source_format == "mp4" else source_format
    artwork = next((s for s in info.get("streams", []) if s.get("disposition", {}).get("attached_pic")), None)
    return {"path": str(path), "tags": media.normalized_tags(info),
            "codec": audio.get("codec_name", "unknown"),
            "duration": float(info.get("format", {}).get("duration", 0)),
            "has_cover": any(s.get("disposition", {}).get("attached_pic") for s in info.get("streams", [])),
            "artwork_data": artwork_data(path, artwork["index"]) if artwork else "",
            "mode": "edit" if source_format == target_format else "convert",
            "source_format": source_format, "target_format": target_format,
            "output": str(path.with_suffix("." + target_format))}


def artwork_data(path, stream_index):
    """Return a small in-memory thumbnail; never create preview files."""
    try:
        result = subprocess.run([
            "ffmpeg", "-v", "error", "-nostdin", "-i", str(path), "-map", f"0:{stream_index}",
            "-frames:v", "1", "-vf", "scale=256:256:force_original_aspect_ratio=decrease",
            "-f", "image2pipe", "-c:v", "png", "pipe:1",
        ], capture_output=True, timeout=10)
        if result.returncode == 0 and result.stdout:
            return "data:image/png;base64," + base64.b64encode(result.stdout).decode("ascii")
    except (OSError, subprocess.TimeoutExpired):
        pass
    return ""


def worker(args):
    try:
        media.process(args)
        result = {"state": "done", "message_key": "job_saved" if args.action == "edit" else "job_done", "error": None, "output": str(args.output)}
    except Exception as error:
        result = {"state": "error", "message_key": "job_failed", "error": error_data(error), "output": ""}
    with LOCK:
        JOB.update(result)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def authenticated(self):
        parsed = urlparse(self.path)
        cookies = SimpleCookie(self.headers.get("Cookie", ""))
        cookie = cookies.get(f"audio_forge_{self.server.server_port}")
        token = self.headers.get("X-M4A-Token", "") or parse_qs(parsed.query).get("token", [""])[0] or (cookie.value if cookie else "")
        if not secrets.compare_digest(token.encode("utf-8"), TOKEN.encode("utf-8")):
            self.reply({"error": self.text("err_auth")}, 403)
            return False
        # Reject cross-origin requests, even when a valid token is supplied.
        origin = self.headers.get("Origin")
        expected = f"http://127.0.0.1:{self.server.server_port}"
        if self.headers.get("Host") != f"127.0.0.1:{self.server.server_port}" or (origin and origin != expected):
            self.reply({"error": self.text("err_origin")}, 403)
            return False
        return True

    def text(self, key, **values):
        return translate(key, self.headers.get("X-Audio-Language", "en"), **values)

    def reply(self, data, status=200):
        raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if not self.authenticated():
            return
        route = urlparse(self.path).path
        assets = {"/": ("index.html", "text/html"), "/app.css": ("app.css", "text/css"),
                  "/app.js": ("app.js", "text/javascript"), "/locales.json": ("locales.json", "application/json"),
                  "/icon.png": ("icon.png", "image/png")}
        if route in assets:
            name, content_type = assets[route]
            raw = (WEB / name).read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type + ("; charset=utf-8" if content_type != "image/png" else ""))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            if route == "/":
                self.send_header("Set-Cookie", f"audio_forge_{self.server.server_port}={TOKEN}; HttpOnly; SameSite=Strict; Path=/")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        elif route == "/api/status":
            with LOCK:
                job = dict(JOB)
                error = job.get("error")
                job["message"] = self.text(error["key"], **error["values"]) if error else self.text(job["message_key"])
                self.reply(job)
        else:
            self.reply({"error": self.text("err_not_found")}, 404)

    def do_POST(self):
        if not self.authenticated():
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            if not 0 < length <= 1024 * 1024:
                raise media.MediaError("err_request_size")
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise media.MediaError("err_request")
            route = urlparse(self.path).path
            if route in ("/api/files", "/api/select"):
                with LOCK:
                    busy = JOB["state"] == "running"
                if busy:
                    raise media.MediaError("err_busy")
                self.reply(list_files(payload) if route == "/api/files" else select_file(payload))
            elif route == "/api/start":
                payload["language"] = language(self.headers.get("X-Audio-Language", payload.get("language")))
                args = prepare_args(payload)
                with LOCK:
                    if JOB["state"] == "running":
                        raise media.MediaError("err_busy")
                    if os.path.lexists(args.output) and args.output != args.input and not args.overwrite:
                        self.reply({"needs_overwrite": True, "path": str(args.output)}, 409)
                        return
                    JOB.update(state="running", message_key="running", error=None, output="")
                threading.Thread(target=worker, args=(args,), daemon=False).start()
                self.reply({"started": True})
            elif route == "/api/reveal":
                with LOCK:
                    output = JOB["output"] if JOB["state"] == "done" else ""
                if not output:
                    raise media.MediaError("err_no_output")
                subprocess.run(["/usr/bin/open", "-R", output], check=True)
                self.reply({"ok": True})
            elif route == "/api/quit":
                with LOCK:
                    if JOB["state"] == "running":
                        raise media.MediaError("err_busy")
                self.reply({"ok": True})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
            else:
                self.reply({"error": self.text("err_not_found")}, 404)
        except Exception as error:
            data = error_data(error)
            self.reply({"error": self.text(data["key"], **data["values"]), "error_key": data["key"], "error_values": data["values"]}, 400)


def main():
    parser = argparse.ArgumentParser(description="Audio Forge local service")
    parser.add_argument("--desktop", action="store_true", help="Serve the native client without opening a browser")
    parser.add_argument("--parent-pid", type=int, help="Stop when the owning native application exits")
    args = parser.parse_args()
    if not args.desktop:
        # Finder does not normally include Homebrew in PATH.
        os.environ["PATH"] = "/opt/homebrew/bin:/usr/local/bin:" + os.environ.get("PATH", "")
    missing = [tool for tool in ("ffmpeg", "ffprobe") if not shutil.which(tool)]
    if missing:
        message = translate("err_missing_tools", tools=", ".join(missing))
        if not args.desktop:
            subprocess.run(["/usr/bin/osascript", "-e", 'display alert "Audio Forge" message "' + message + '"'])
        raise SystemExit(message)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    url = f"http://127.0.0.1:{server.server_port}/?token={TOKEN}"
    if args.desktop:
        print(json.dumps({"event": "ready", "url": url, "token": TOKEN}), flush=True)
        signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=server.shutdown, daemon=True).start())
        if args.parent_pid:
            def watch_parent():
                while os.getppid() == args.parent_pid:
                    threading.Event().wait(1)
                server.shutdown()
            threading.Thread(target=watch_parent, daemon=True).start()
    else:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
