"""FFmpeg integration tests for conversion, artwork, and video preservation."""
import base64
from pathlib import Path
import tempfile
import unittest

from audio_forge import server as gui
from audio_forge import media
from tests.helpers import checked, inspect, packet_hashes


class FormatIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        for extension, codec in [("mp3", "libmp3lame"), ("flac", "flac"), ("m4a", "aac")]:
            checked("ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=duration=0.4", "-c:a", codec,
                    "-metadata", "title=原标题", "-metadata", "genre=原风格", str(cls.root / ("输入." + extension)))
        checked("ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=blue:s=32x32:r=10",
                "-f", "lavfi", "-i", "sine=duration=0.4", "-t", "0.4", "-c:v", "mpeg4", "-c:a", "aac",
                "-metadata", "title=原标题", "-metadata", "genre=原风格", str(cls.root / "输入.mp4"))
        cls.cover = cls.root / "封面.png"
        checked("ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=red:s=32x32", "-frames:v", "1", str(cls.cover))

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_all_twelve_conversion_directions_with_cover_and_tags(self):
        for source_format in media.FORMATS:
            for target_format in media.FORMATS:
                if source_format == target_format:
                    continue
                with self.subTest(source=source_format, target=target_format):
                    source = self.root / ("输入." + source_format)
                    output = self.root / (source_format + "_to_" + target_format + "." + target_format)
                    args = gui.prepare_args({
                        "input": str(source), "output": str(output), "target_format": target_format,
                        "tags": {"title": "新标题", "artist": "测试歌手", "album": "测试专辑", "date": "2026"},
                        "cover_action": "replace", "cover": str(self.cover),
                    })
                    media.process(args)
                    info = inspect(output)
                    audio = next(s for s in info["streams"] if s["codec_type"] == "audio")
                    self.assertIn(audio["codec_name"], media.FORMATS[target_format]["copy"])
                    self.assertAlmostEqual(float(info["format"]["duration"]), 0.4, delta=0.15)
                    tags = media.normalized_tags(info)
                    self.assertEqual(tags["title"], "新标题")
                    self.assertEqual(tags["artist"], "测试歌手")
                    self.assertEqual(tags["album"], "测试专辑")
                    self.assertEqual(tags["date"], "2026")
                    self.assertEqual(tags["genre"], "原风格")
                    self.assertTrue(any(s.get("disposition", {}).get("attached_pic") for s in info["streams"]))

    def test_edit_all_formats_preserves_audio_and_mp4_video(self):
        for extension in media.FORMATS:
            with self.subTest(format=extension):
                source = self.root / ("输入." + extension)
                output = self.root / ("编辑." + extension)
                args = gui.prepare_args({"input": str(source), "output": str(output), "target_format": extension,
                                         "tags": {"title": "编辑后", "artist": ""}, "cover_action": "replace", "cover": str(self.cover)})
                media.process(args)
                self.assertEqual(packet_hashes(source), packet_hashes(output))
                self.assertEqual(media.normalized_tags(inspect(output))["title"], "编辑后")
                if extension == "mp4":
                    ordinary_video = [s for s in inspect(output)["streams"] if s["codec_type"] == "video" and not s.get("disposition", {}).get("attached_pic")]
                    self.assertEqual(len(ordinary_video), 1)
                    self.assertEqual(ordinary_video[0]["codec_name"], "mpeg4")
                removed = self.root / ("无封面." + extension)
                media.process(gui.prepare_args({"input": str(output), "output": str(removed), "target_format": extension, "cover_action": "remove"}))
                self.assertFalse(any(s.get("disposition", {}).get("attached_pic") for s in inspect(removed)["streams"]))

    def test_jpeg_artwork_and_thumbnail_in_all_formats(self):
        cover = self.root / "cover.jpg"
        cover.write_bytes(base64.b64decode("/9j/4AAQSkZJRgABAgAAAQABAAD//gAPTGF2YzYzLjEuMTAyAP/bAEMACAQEBAQEBQUFBQUFBgYGBgYGBgYGBgYGBgcHBwgICAcHBwYGBwcICAgICQkJCAgICAkJCgoKDAwLCw4ODhERFP/EAE0AAQEAAAAAAAAAAAAAAAAAAAAHAQEBAQAAAAAAAAAAAAAAAAAABQgQAQAAAAAAAAAAAAAAAAAAAAARAQAAAAAAAAAAAAAAAAAAAAD/wAARCAAgADADASIAAhEAAxEA/9oADAMBAAIRAxEAPwCxAM/qgAAAAAAAAAD/2Q=="))
        selected = gui.select_file({"kind": "cover", "path": str(cover)})
        self.assertTrue(selected["artwork_data"].startswith("data:image/png;base64,"))
        for extension in media.FORMATS:
            with self.subTest(format=extension):
                source = self.root / ("输入." + extension)
                destination = self.root / ("jpeg-cover." + extension)
                args = gui.prepare_args({"input": str(source), "output": str(destination), "target_format": extension,
                                         "cover_action": "replace", "cover": str(cover)})
                media.process(args)
                self.assertEqual(packet_hashes(source), packet_hashes(destination))
                selected = gui.select_file({"kind": "input", "path": str(destination)})
                self.assertTrue(selected["artwork_data"].startswith("data:image/png;base64,"))
                artwork = [s for s in inspect(destination)["streams"] if s.get("disposition", {}).get("attached_pic")]
                self.assertEqual(artwork[0]["codec_name"], "mjpeg")

    def test_gui_picker_supports_four_formats(self):
        entries = gui.list_files({"kind": "input", "directory": str(self.root)})["entries"]
        self.assertTrue(all(any(e["name"] == "输入." + f for e in entries) for f in media.FORMATS))
        for f in media.FORMATS:
            selected = gui.select_file({"kind": "input", "path": str(self.root / ("输入." + f))})
            self.assertEqual(selected["source_format"], f)

    def test_flac_aliases_are_replaced_and_removed(self):
        source = self.root / "别名.flac"
        checked("ffmpeg", "-v", "error", "-i", str(self.root / "输入.flac"), "-c:a", "copy",
                "-metadata", "ALBUMARTIST=旧歌手", "-metadata", "TRACKNUMBER=1", str(source))
        self.assertEqual(gui.select_file({"kind": "input", "path": str(source)})["tags"]["album_artist"], "旧歌手")
        args = media.make_parser().parse_args(["edit", str(source), "--album-artist", "新歌手", "--remove-tag", "track"])
        media.process(args)
        tags = media.normalized_tags(inspect(source))
        self.assertEqual(tags["album_artist"], "新歌手")
        self.assertNotIn("track", tags)


if __name__ == "__main__":
    unittest.main()
