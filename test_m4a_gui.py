"""Integration tests from GUI requests to the conversion engine."""
import hashlib
from pathlib import Path
import tempfile
import unittest

import m4a_gui as gui
from test_mp4_to_m4a import checked, inspect, packet_hashes


class GuiIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "视频.mp4"
        checked("ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=duration=0.3", "-c:a", "aac", "-metadata", "title=旧标题", "-metadata", "artist=旧歌手", str(self.source))

    def test_gui_convert_and_edit_empty_field(self):
        args = gui.prepare_args({"input": str(self.source), "tags": {"title": "新标题", "artist": ""}})
        gui.worker(args)
        self.assertEqual(gui.JOB["state"], "done", gui.JOB)
        output = self.source.with_suffix(".m4a")
        tags = inspect(output)["format"]["tags"]
        self.assertEqual(tags["title"], "新标题")
        self.assertNotIn("artist", tags)
        self.assertEqual(packet_hashes(self.source), packet_hashes(output))
        gui.worker(gui.prepare_args({"input": str(output), "tags": {"title": "再次编辑"}}))
        self.assertEqual(gui.JOB["state"], "done", gui.JOB)
        self.assertEqual(inspect(output)["format"]["tags"]["title"], "再次编辑")
        self.assertEqual(packet_hashes(self.source), packet_hashes(output))

    def test_gui_failed_job_preserves_file(self):
        args = gui.prepare_args({"input": str(self.source)})
        gui.worker(args)
        before = hashlib.sha256(args.output.read_bytes()).digest()
        args = gui.prepare_args({"input": str(args.output), "cover_action": "replace", "cover": str(self.root / "missing.png")})
        gui.worker(args)
        self.assertEqual(gui.JOB["state"], "error")
        self.assertEqual(hashlib.sha256(args.output.read_bytes()).digest(), before)

    def test_gui_rejects_invalid_options(self):
        with self.assertRaises(ValueError):
            gui.prepare_args({"input": str(self.source), "codec": "wrong"})
        with self.assertRaises(ValueError):
            gui.prepare_args({"input": str(self.source), "tags": {"title": []}})

    def test_file_picker_filter_and_select(self):
        (self.root / "子目录").mkdir()
        (self.root / "忽略.txt").write_text("无关文件")
        data = gui.list_files({"kind": "input", "directory": str(self.root)})
        self.assertEqual([entry["name"] for entry in data["entries"]], ["子目录", "视频.mp4"])
        selected = gui.select_file({"kind": "input", "path": str(self.source)})
        self.assertEqual(selected["mode"], "convert")
        self.assertEqual(selected["tags"]["title"], "旧标题")
        with self.assertRaises(ValueError):
            gui.select_file({"kind": "input", "path": str(self.root / "忽略.txt")})

    def test_clearing_visible_fields_preserves_removed_fields(self):
        source = self.root / "legacy.mp4"
        checked("ffmpeg", "-v", "error", "-i", str(self.source), "-c:a", "copy",
                "-metadata", "album_artist=Original album artist", "-metadata", "track=2/8", str(source))
        args = gui.prepare_args({"input": str(source), "tags": {
            "title": "", "artist": "", "album": "", "date": "",
            "album_artist": "Ignored", "track": "",
        }})
        gui.worker(args)
        self.assertEqual(gui.JOB["state"], "done", gui.JOB)
        tags = inspect(args.output)["format"]["tags"]
        self.assertNotIn("title", tags)
        self.assertNotIn("artist", tags)
        self.assertEqual(tags["album_artist"], "Original album artist")
        self.assertEqual(tags["track"], "2/8")


if __name__ == "__main__":
    unittest.main()
