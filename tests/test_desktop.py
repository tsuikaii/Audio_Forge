"""Exercise the native client's subprocess protocol, authentication and lifecycle."""
import json
import os
from pathlib import Path
import selectors
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request


class DesktopServiceTests(unittest.TestCase):
    def start_service(self, parent=None):
        env = dict(os.environ, AUDIO_FORGE_DESKTOP="1", PYTHONDONTWRITEBYTECODE="1")
        process = subprocess.Popen([sys.executable, "-B", "-s", "-S", "-m", "audio_forge", "--desktop", "--parent-pid", str(parent if parent is not None else os.getpid())], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.addCleanup(self.stop_service, process)
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            self.assertTrue(selector.select(10), "No native startup event")
        line = process.stdout.readline()
        self.assertTrue(line, "Backend exited before its ready event")
        event = json.loads(line)
        self.assertEqual(event["event"], "ready")
        self.assertTrue(event["url"].startswith("http://127.0.0.1:"))
        return process, event

    @staticmethod
    def stop_service(process):
        if process.poll() is None:
            process.terminate()
        try:
            process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()

    def request(self, event, path, payload=None, token=True):
        url = event["url"].split("?", 1)[0] + path.lstrip("/")
        headers = {"Content-Type":"application/json"}
        if token:
            headers["X-M4A-Token"] = event["token"]
        request = urllib.request.Request(url, data=json.dumps(payload).encode() if payload is not None else None, headers=headers)
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=5) as response:
            body = response.read()
            return json.loads(body) if path.startswith("api/") else body

    def test_ready_protocol_private_assets_and_graceful_quit(self):
        process, event = self.start_service()
        self.assertEqual(self.request(event, "api/status")["state"], "idle")
        self.assertIn(b"native-client", self.request(event, "app.js"))
        with self.assertRaises(urllib.error.HTTPError) as context:
            self.request(event, "api/status", token=False)
        self.assertEqual(context.exception.code, 403)
        context.exception.close()
        self.assertTrue(self.request(event, "api/quit", {})["ok"])
        self.assertEqual(process.wait(timeout=5), 0)

    def test_parent_exit_stops_the_service(self):
        process, _ = self.start_service(parent=os.getpid() + 1000000)
        self.assertEqual(process.wait(timeout=5), 0)

    def test_native_service_converts_and_reports_output(self):
        process, event = self.start_service()
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source.flac"
            destination = Path(temporary) / "result.mp3"
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=700:duration=0.3", "-c:a", "flac", str(source)], check=True)
            self.assertEqual(self.request(event, "api/select", {"kind":"input", "path":str(source)})["source_format"], "flac")
            self.assertTrue(self.request(event, "api/start", {"input":str(source), "output":str(destination), "target_format":"mp3", "tags":{"title":"Native / 原生 / ネイティブ"}})["started"])
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                job = self.request(event, "api/status")
                if job["state"] != "running":
                    break
                threading.Event().wait(0.05)
            self.assertEqual(job["state"], "done", job)
            self.assertEqual(job["output"], str(destination))
            info = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_format", "-of", "json", str(destination)]))
            self.assertEqual(info["format"]["tags"]["title"], "Native / 原生 / ネイティブ")
        process.terminate()
        self.assertEqual(process.wait(timeout=5), 0)


if __name__ == "__main__":
    unittest.main()
