"""Small helpers for real FFmpeg integration tests."""
import json
import subprocess
import sys

CLI = (sys.executable, "-m", "audio_forge.media")


def invoke(*args):
    return subprocess.run(args, capture_output=True, text=True)


def checked(*args):
    result = invoke(*args)
    if result.returncode:
        raise AssertionError(result.stderr)
    return result.stdout


def inspect(path):
    return json.loads(checked("ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)))


def packet_hashes(path):
    data = json.loads(checked(
        "ffprobe", "-v", "error", "-select_streams", "a:0", "-show_packets",
        "-show_data_hash", "sha256", "-of", "json", str(path),
    ))
    return [p["data_hash"] for p in data["packets"]]
