#!/usr/bin/env python3
"""Build pinned, shared LGPL media tools for Audio Forge (macOS only)."""
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
DEPS = ROOT / "build/deps"
PACKAGES = {
    "ffmpeg": {
        "version": "9.0.2", "archive": "ffmpeg-9.0.2.tar.xz",
        "url": "https://ffmpeg.org/releases/ffmpeg-9.0.2.tar.xz",
        "sha256": "8c3850283eb25fa026482078a04051e0be17347b09ef81a0849bec15a96e002e",
    },
    "lame": {
        "version": "4.0", "archive": "lame-4.0.tar.gz",
        "url": "https://downloads.sourceforge.net/project/lame/lame/4.0/lame-4.0.tar.gz",
        "sha256": "3df5124d5ad3a98312ffd7ba6a9b36230e4f8a3e66d3ce0f425e336c32d216eb",
    },
}


def run(*args, cwd, env):
    subprocess.run([str(arg) for arg in args], cwd=cwd, env=env, check=True)


def main():
    if platform.system() != "Darwin":
        raise SystemExit("Build the release media tools on macOS.")
    archives = DEPS / "archives"
    sources = DEPS / "source"
    prefix = DEPS / "prefix"
    archives.mkdir(parents=True, exist_ok=True)
    sources.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, MACOSX_DEPLOYMENT_TARGET="15.0")
    env["CFLAGS"] = "-Os -mmacosx-version-min=15.0 -Wno-implicit-function-declaration"
    env["LDFLAGS"] = "-mmacosx-version-min=15.0 -Wl,-headerpad_max_install_names"
    env["ac_cv_prog_cc_c23"] = "no"
    for name, package in PACKAGES.items():
        archive = archives / package["archive"]
        if not archive.exists():
            temporary = archive.with_suffix(archive.suffix + ".partial")
            with urllib.request.urlopen(package["url"], timeout=120) as response, temporary.open("wb") as file:
                shutil.copyfileobj(response, file)
            temporary.replace(archive)
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        if digest != package["sha256"]:
            raise SystemExit(f"Source checksum mismatch: {archive.name}; delete it and retry.")
        source = sources / f"{name}-{package['version']}"
        if not source.exists():
            with tarfile.open(archive) as file:
                file.extractall(sources, filter="data")
    lame = sources / f"lame-{PACKAGES['lame']['version']}"
    lame_args = ["--prefix=/", "--enable-shared", "--disable-static", "--disable-frontend", "--disable-decoder", "--disable-debug", "--disable-dependency-tracking"]
    if (lame / "Makefile").exists():
        run("make", "clean", cwd=lame, env=env)
    run("./configure", *lame_args, cwd=lame, env=env)
    jobs = str(min(os.cpu_count() or 2, 8))
    run("make", "-j", jobs, cwd=lame, env=env)
    run("make", "install", f"DESTDIR={prefix}", cwd=lame, env=env)
    ffmpeg = sources / f"ffmpeg-{PACKAGES['ffmpeg']['version']}"
    ffmpeg_args = [
        "--prefix=/", "--enable-shared", "--disable-static", "--disable-gpl", "--disable-nonfree",
        "--disable-autodetect", "--disable-doc", "--disable-debug", "--disable-ffplay", "--disable-network",
        "--disable-everything", "--enable-ffmpeg", "--enable-ffprobe", "--enable-small", "--enable-pthreads",
        "--enable-libmp3lame", "--enable-zlib", "--enable-protocol=file,pipe", "--enable-indev=lavfi",
        "--enable-demuxer=mov,mp3,flac,image2,png_pipe,jpeg_pipe,wav",
        "--enable-muxer=mov,mp4,ipod,mp3,flac,image2,image2pipe,wav,null",
        "--enable-decoder=aac,alac,mp3,mp3float,flac,ac3,eac3,opus,vorbis,pcm_s16le,pcm_s24le,pcm_s32le,pcm_f32le,pcm_f64le,pcm_s16be,pcm_s24be,pcm_s32be,png,mjpeg,mpeg4,wrapped_avframe",
        "--enable-encoder=aac,alac,flac,libmp3lame,png,mpeg4,pcm_s16le",
        "--enable-parser=aac,aac_latm,mpegaudio,flac,ac3,opus,vorbis,h264,hevc,mpeg4video,png,mjpeg",
        "--enable-bsf=aac_adtstoasc,extract_extradata,h264_mp4toannexb,hevc_mp4toannexb",
        "--enable-filter=aresample,aformat,anull,atrim,format,null,scale,trim,sine,color",
        "--extra-cflags=-Os -mmacosx-version-min=15.0 -I../../prefix/include",
        "--extra-ldflags=-mmacosx-version-min=15.0 -Wl,-headerpad_max_install_names -L../../prefix/lib",
        "--install-name-dir=@rpath",
    ]
    if platform.machine() == "x86_64":
        ffmpeg_args.append("--disable-x86asm")
    if (ffmpeg / "Makefile").exists():
        run("make", "clean", cwd=ffmpeg, env=env)
    run("./configure", *ffmpeg_args, cwd=ffmpeg, env=env)
    run("make", "-j", jobs, cwd=ffmpeg, env=env)
    run("make", "install", f"DESTDIR={prefix}", cwd=ffmpeg, env=env)
    # Make the build tools usable from PATH before packaging, without DYLD vars.
    # No source is changed; only these installed build outputs are relocated.
    for file in [*(prefix / "lib").glob("*.dylib"), *(prefix / "bin").iterdir()]:
        if file.is_symlink():
            continue
        listing = subprocess.check_output(["otool", "-L", str(file)], text=True).splitlines()[1:]
        identifiers = subprocess.check_output(["otool", "-D", str(file)], text=True).splitlines()[1:]
        identifier = identifiers[0].strip() if identifiers else None
        for line in listing:
            dependency = line.strip().split(" (compatibility", 1)[0]
            if dependency == identifier or dependency.startswith(("/usr/lib/", "/System/Library/")):
                continue
            library = prefix / "lib" / Path(dependency).name
            if not library.is_file():
                raise RuntimeError(f"Unexpected media dependency: {dependency}")
            relative = os.path.relpath(library, file.parent)
            run("install_name_tool", "-change", dependency, "@loader_path/" + relative, file, cwd=ROOT, env=env)
        if identifier:
            run("install_name_tool", "-id", "@rpath/" + file.name, file, cwd=ROOT, env=env)
        run("codesign", "--force", "--sign", "-", file, cwd=ROOT, env=env)
    info = {"packages": PACKAGES, "lame_configure": lame_args, "ffmpeg_configure": ffmpeg_args, "architecture": platform.machine(), "minimum_macos": "15.0", "source_modifications": "None. Only installed Mach-O library paths are relocated."}
    (DEPS / "build-info.json").write_text(json.dumps(info, indent=2) + "\n")
    print(f"Built LGPL media tools: {prefix}")


if __name__ == "__main__":
    main()
