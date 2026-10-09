"""Integration tests using real FFmpeg processes."""

import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from tests.helpers import CLI, checked, inspect, invoke, packet_hashes


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg is required")
class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "测试 video.mp4"
        self.output = self.source.with_suffix(".m4a")
        checked(
            "ffmpeg", "-v", "error", "-nostdin", "-f", "lavfi", "-i",
            "color=c=black:s=32x32:r=10", "-f", "lavfi", "-i", "sine=frequency=440:duration=0.5",
            "-t", "0.5", "-c:v", "mpeg4", "-c:a", "aac",
            "-metadata", "title=旧标题", "-metadata", "album=旧专辑", str(self.source),
        )

    def cli(self, *args):
        return invoke(*CLI, *map(str, args))

    def success(self, *args):
        result = self.cli(*args)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def test_copy_and_unicode_metadata(self):
        self.success("convert", self.source, "--title", "中文 新标题", "--artist", "歌手", "--album-artist", "专辑艺术家", "--track", "3/12")
        data = inspect(self.output)
        self.assertEqual([s["codec_type"] for s in data["streams"]], ["audio"])
        self.assertEqual(data["format"]["tags"]["title"], "中文 新标题")
        self.assertEqual(data["format"]["tags"]["album"], "旧专辑")
        self.assertEqual(data["format"]["tags"]["album_artist"], "专辑艺术家")
        self.assertEqual(packet_hashes(self.source), packet_hashes(self.output))

    def test_cover_edit_preservation_and_removal(self):
        cover = self.root / "封面.png"
        checked("ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=red:s=32x32", "-frames:v", "1", str(cover))
        self.success("convert", self.source, "--cover", cover)
        self.success("edit", self.output, "--title", "编辑后", "--comment", "测试")
        data = inspect(self.output)
        self.assertTrue(any(s.get("disposition", {}).get("attached_pic") for s in data["streams"]))
        self.assertEqual(data["format"]["tags"]["title"], "编辑后")
        self.assertEqual(packet_hashes(self.source), packet_hashes(self.output))
        self.success("edit", self.output, "--remove-cover", "--remove-tag", "comment")
        data = inspect(self.output)
        self.assertEqual(len(data["streams"]), 1)
        self.assertNotIn("comment", data["format"]["tags"])

    def test_clear_metadata_and_save_as(self):
        self.success("convert", self.source)
        original = self.output.read_bytes()
        other = self.root / "另存.m4a"
        self.success("edit", self.output, "-o", other, "--clear-metadata", "--title", "新标题")
        tags = inspect(other)["format"]["tags"]
        self.assertEqual(tags["title"], "新标题")
        self.assertNotIn("album", tags)
        self.assertEqual(self.output.read_bytes(), original)
        self.assertEqual(packet_hashes(self.source), packet_hashes(other))

    def test_overwrite_and_failed_edit_protect_output(self):
        self.success("convert", self.source)
        before = hashlib.sha256(self.output.read_bytes()).digest()
        self.assertNotEqual(self.cli("convert", self.source).returncode, 0)
        self.assertNotEqual(self.cli("edit", self.output, "--cover", self.root / "不存在.png").returncode, 0)
        self.assertEqual(hashlib.sha256(self.output.read_bytes()).digest(), before)
        self.success("convert", self.source, "--overwrite", "--title", "覆盖后")
        self.assertEqual(inspect(self.output)["format"]["tags"]["title"], "覆盖后")
        self.assertEqual(list(self.root.glob(".mp4_to_m4a-*")), [])

    def test_encode_auto_and_alac(self):
        pcm_source = self.root / "PCM.mp4"
        checked("ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=duration=0.5", "-c:a", "pcm_s16le", "-f", "mov", str(pcm_source))
        self.assertNotEqual(self.cli("convert", pcm_source, "--codec", "copy").returncode, 0)
        self.success("convert", pcm_source)
        output = pcm_source.with_suffix(".m4a")
        self.assertEqual(inspect(output)["streams"][0]["codec_name"], "aac")
        self.success("convert", pcm_source, "--codec", "alac", "--overwrite")
        self.assertEqual(inspect(output)["streams"][0]["codec_name"], "alac")

    def test_no_audio_and_show(self):
        silent = self.root / "silent.mp4"
        checked("ffmpeg", "-v", "error", "-i", str(self.source), "-an", "-c:v", "copy", str(silent))
        self.assertNotEqual(self.cli("convert", silent).returncode, 0)
        self.assertFalse(silent.with_suffix(".m4a").exists())
        result = self.success("show", self.source)
        self.assertEqual(json.loads(result.stdout)["format"]["tags"]["title"], "旧标题")


if __name__ == "__main__":
    unittest.main()
