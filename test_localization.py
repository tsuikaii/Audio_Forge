"""Validate complete translations and their real CLI behavior."""
import re
import unittest

import messages
from test_mp4_to_m4a import SCRIPT, checked
import sys


class LocalizationTests(unittest.TestCase):
    def test_complete_dictionaries_and_format_parameters(self):
        reference = messages.TRANSLATIONS["en"]
        for locale in messages.LANGUAGES:
            translated = messages.TRANSLATIONS[locale]
            self.assertEqual(set(reference), set(translated))
            for key, english in reference.items():
                with self.subTest(locale=locale, key=key):
                    self.assertTrue(translated[key])
                    self.assertEqual(set(re.findall(r"\{(\w+)\}", english)), set(re.findall(r"\{(\w+)\}", translated[key])))

    def test_default_and_localized_cli_help(self):
        default = checked(sys.executable, str(SCRIPT), "--help")
        self.assertIn("Convert MP4, MP3, FLAC", default)
        self.assertNotRegex(default, r"[\u4e00-\u9fff]")
        chinese = checked(sys.executable, str(SCRIPT), "--language", "zh-CN", "convert", "--help")
        japanese = checked(sys.executable, str(SCRIPT), "--language", "ja", "edit", "--help")
        self.assertIn("目标格式", chinese)
        self.assertIn("メタデータ", japanese)

    def test_error_language_and_english_fallback(self):
        error = messages.UserError("err_no_audio")
        self.assertEqual(str(error), "This file has no audio track.")
        self.assertEqual(messages.error_message(error, "zh-CN"), "这个文件没有音轨。")
        self.assertEqual(messages.error_message(error, "ja"), "このファイルに音声トラックはありません。")
        self.assertEqual(messages.error_message(error, "invalid"), str(error))
