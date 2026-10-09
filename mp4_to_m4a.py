#!/usr/bin/env python3
"""Convert MP4, MP3, FLAC, and M4A, and edit metadata using FFmpeg."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from messages import LANGUAGES, UserError, error_message, translate


TAGS = {
    "title": "Title", "artist": "Artist", "album": "Album",
    "album_artist": "Album artist", "date": "Year / date", "genre": "Genre",
    "track": "Track number", "disc": "Disc number", "composer": "Composer",
    "comment": "Comment", "lyrics": "Lyrics", "copyright": "Copyright",
}

FORMATS = {
    "m4a": {"muxer": "ipod", "codec": "aac", "copy": {"aac", "alac"}},
    "mp4": {"muxer": "mp4", "codec": "aac", "copy": {"aac", "alac", "mp3"}},
    "mp3": {"muxer": "mp3", "codec": "mp3", "copy": {"mp3"}},
    "flac": {"muxer": "flac", "codec": "flac", "copy": {"flac"}},
}
TAG_ALIASES = {"albumartist": "album_artist", "tracknumber": "track", "discnumber": "disc", "year": "date"}


def normalized_tags(info):
    result = {}
    for key, value in info.get("format", {}).get("tags", {}).items():
        key = key.lower()
        result[TAG_ALIASES.get(key, key)] = value
    return result


class MediaError(UserError):
    pass


def run(command):
    result = subprocess.run(
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace",
    )
    if result.returncode:
        raise MediaError("err_ffmpeg", detail=result.stderr.strip()[-5000:])
    return result.stdout


def probe(path):
    return json.loads(run([
        "ffprobe", "-v", "error", "-show_format", "-show_streams",
        "-of", "json", str(path),
    ]))


def add_metadata_options(parser, locale="en"):
    for key, description in TAGS.items():
        flags = ["--" + key.replace("_", "-")]
        if key == "date":
            flags.append("--year")
        parser.add_argument(*flags, dest=key, help=translate(key, locale))
    parser.add_argument(
        "--remove-tag", action="append", choices=list(TAGS), default=[],
        metavar="TAG", help=translate("cli_remove_tag", locale),
    )
    parser.add_argument("--clear-metadata", action="store_true", help=translate("cli_clear", locale))
    cover = parser.add_mutually_exclusive_group()
    cover.add_argument("--cover", type=Path, help=translate("cli_cover", locale))
    cover.add_argument("--remove-cover", action="store_true", help=translate("cli_remove_cover", locale))


def make_parser(locale="en"):
    parser = argparse.ArgumentParser(description=translate("cli_description", locale))
    parser.add_argument("--language", choices=LANGUAGES, default=locale, help=translate("cli_language", locale))
    subs = parser.add_subparsers(dest="action", required=True)
    convert = subs.add_parser("convert", help=translate("cli_convert", locale))
    convert.add_argument("input", type=Path, help=translate("cli_input", locale))
    convert.add_argument("-o", "--output", type=Path, help=translate("cli_output", locale))
    convert.add_argument("--format", choices=list(FORMATS), default=None, help=translate("cli_format", locale))
    convert.add_argument(
        "--codec", choices=["auto", "copy", "aac", "alac", "mp3", "flac"], default="auto",
        help=translate("cli_codec", locale),
    )
    convert.add_argument("--bitrate", default="256k", help=translate("cli_bitrate", locale))
    convert.add_argument("--overwrite", action="store_true", help=translate("cli_overwrite", locale))
    add_metadata_options(convert, locale)
    edit = subs.add_parser("edit", help=translate("cli_edit", locale))
    edit.add_argument("input", type=Path, help=translate("cli_input", locale))
    edit.add_argument("-o", "--output", type=Path, help=translate("cli_output", locale))
    edit.add_argument("--overwrite", action="store_true", help=translate("cli_overwrite", locale))
    add_metadata_options(edit, locale)
    show = subs.add_parser("show", help=translate("cli_show", locale))
    show.add_argument("input", type=Path)
    return parser


def process(args):
    locale = getattr(args, "language", "en")
    source = args.input.expanduser().resolve()
    if not source.is_file():
        raise MediaError("err_input_missing", path=str(source))
    info = probe(source)
    if args.action == "show":
        print(json.dumps(info, ensure_ascii=False, indent=2))
        return
    source_format = source.suffix.lower().lstrip(".")
    if source_format not in FORMATS:
        raise MediaError("err_input_format")
    audio = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    if audio is None:
        raise MediaError("err_no_audio")
    source_codec = audio.get("codec_name")
    if args.output:
        # Preserve output symlinks as destinations instead of following them.
        destination = Path(os.path.abspath(args.output.expanduser()))
    elif args.action == "edit":
        destination = source
    else:
        destination = source.with_suffix("." + (getattr(args, "format", None) or "m4a"))
    target_format = destination.suffix.lower().lstrip(".")
    if target_format not in FORMATS:
        raise MediaError("err_output_format")
    if getattr(args, "format", None) and args.format != target_format:
        raise MediaError("err_format_mismatch")
    if args.action == "edit" and source_format != target_format:
        raise MediaError("err_edit_format")
    config = FORMATS[target_format]
    codec = "copy" if args.action == "edit" else getattr(args, "codec", "auto")
    if codec == "auto":
        codec = "copy" if source_codec in config["copy"] else config["codec"]
    if codec == "copy" and args.action != "edit" and source_codec not in config["copy"]:
        raise MediaError("err_copy_codec", codec=source_codec, format=target_format.upper())
    if codec != "copy" and codec not in config["copy"]:
        raise MediaError("err_codec_format", codec=codec, format=target_format.upper())
    inplace = destination == source
    if args.action == "convert" and inplace:
        raise MediaError("err_same_path")
    if not destination.parent.is_dir():
        raise MediaError("err_output_directory", path=str(destination.parent))
    if os.path.lexists(destination) and not (inplace or args.overwrite):
        raise MediaError("err_exists", path=str(destination))
    for key in args.remove_tag:
        if getattr(args, key) is not None:
            raise MediaError("err_tag_conflict", tag=key)

    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-i", str(source)]
    cover_map = None
    if args.cover:
        cover = args.cover.expanduser().resolve()
        if not cover.is_file() or cover.suffix.lower() not in (".jpg", ".jpeg", ".png"):
            raise MediaError("err_cover")
        cover_info = probe(cover)
        cover_streams = cover_info.get("streams", [])
        if not cover_streams or cover_streams[0].get("codec_name") not in ("mjpeg", "png"):
            raise MediaError("err_cover_content")
        command += ["-i", str(cover)]
        cover_map = "1:v:0"
    elif not args.remove_cover:
        cover_stream = next((
            s for s in info["streams"]
            if s.get("codec_type") == "video"
            and s.get("disposition", {}).get("attached_pic") == 1
            and s.get("codec_name") in ("mjpeg", "png")
        ), None)
        if cover_stream:
            cover_map = f"0:{cover_stream['index']}"
    command += ["-map", f"0:{audio['index']}", "-c:a", "libmp3lame" if codec == "mp3" else codec]
    if codec in ("aac", "mp3"):
        command += ["-b:a", args.bitrate]
    video_count = 0
    if target_format == "mp4":
        for stream in info["streams"]:
            if stream.get("codec_type") == "video" and not stream.get("disposition", {}).get("attached_pic"):
                command += ["-map", f"0:{stream['index']}"]
                video_count += 1
        if video_count:
            command += ["-c:v", "copy"]
    if cover_map:
        command += ["-map", cover_map, "-c:v", "copy", f"-disposition:v:{video_count}", "attached_pic"]
    command += ["-map_metadata", "-1" if args.clear_metadata else "0"]
    if args.clear_metadata:
        command += ["-map_metadata:s", "-1"]
    for key in args.remove_tag:
        for alias, canonical in TAG_ALIASES.items():
            if canonical == key:
                command += ["-metadata", f"{alias}="]
        command += ["-metadata", f"{key}="]
    for key in TAGS:
        value = getattr(args, key)
        if value is not None:
            for alias, canonical in TAG_ALIASES.items():
                if canonical == key:
                    command += ["-metadata", f"{alias}="]
            command += ["-metadata", f"{key}={value}"]
    if target_format in ("m4a", "mp4"):
        command += ["-movflags", "+faststart"]
    if target_format == "mp3":
        command += ["-id3v2_version", "3"]
    command += ["-f", config["muxer"]]

    fd, temporary = tempfile.mkstemp(prefix=".mp4_to_m4a-", suffix="." + target_format, dir=destination.parent)
    os.close(fd)
    temp_path = Path(temporary)
    try:
        print(translate("cli_processing", locale, source=source.name, output=destination.name, codec=translate("cli_copy", locale) if codec == "copy" else codec), file=sys.stderr)
        run(command + [str(temp_path)])
        output_info = probe(temp_path)
        if not any(s.get("codec_type") == "audio" for s in output_info.get("streams", [])):
            raise MediaError("err_output_audio")
        if inplace:
            os.chmod(temp_path, source.stat().st_mode & 0o777)
        if inplace or args.overwrite:
            os.replace(temp_path, destination)
        else:
            # Atomically create the output without overwriting a concurrent file.
            try:
                os.link(temp_path, destination)
            except FileExistsError:
                raise MediaError("err_exists", path=str(destination)) from None
        print(translate("cli_done", locale, path=str(destination)))
    finally:
        temp_path.unlink(missing_ok=True)


def main():
    bootstrap = argparse.ArgumentParser(add_help=False)
    bootstrap.add_argument("--language", choices=LANGUAGES, default="en")
    initial, _ = bootstrap.parse_known_args()
    args = make_parser(initial.language).parse_args()
    required = ["ffprobe"] if args.action == "show" else ["ffmpeg", "ffprobe"]
    missing = [name for name in required if not shutil.which(name)]
    if missing:
        print(translate("err_missing_tools", args.language, tools=", ".join(missing)), file=sys.stderr)
        return 1
    try:
        process(args)
    except (MediaError, OSError, ValueError, KeyError) as error:
        print(translate("cli_error", args.language, detail=error_message(error, args.language)), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n" + translate("cli_cancelled", args.language), file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
