#!/usr/bin/env python3
"""Build a relocatable native macOS application and drag-to-install disk image.

Requires the local Xcode tools, Python and FFmpeg only at build time. The output
contains its own Python standard library, FFmpeg, and non-system dynamic libraries.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import plistlib
import re
import shutil
import subprocess
import sys
import sysconfig
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parent
VERSION = "1.0.0"
MINIMUM_MACOS = "15.0"
ASSETS = ("m4a_gui.py", "mp4_to_m4a.py", "messages.py", "m4a_gui.html", "ui.css", "ui.js", "locales.json", "app-icon.png")
SYSTEM_PREFIXES = ("/usr/lib/", "/System/Library/")
MACH_MAGICS = {b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe", b"\xfe\xed\xfa\xcf", b"\xfe\xed\xfa\xce", b"\xca\xfe\xba\xbe", b"\xca\xfe\xba\xbf"}
# This private local-service runtime does not need TLS, databases, or a REPL.
UNUSED_EXTENSIONS = ("_ssl", "_hashlib", "_sqlite3", "_lzma", "_bz2", "_zstd", "_decimal", "_ctypes", "_curses", "_curses_panel", "_dbm", "_gdbm", "readline", "_tkinter")


def media_tool(name):
    tool = ROOT / "build/deps/prefix/bin" / name
    if tool.is_file():
        return str(tool)
    raise RuntimeError("Missing release media tools. Run python3 -B scripts/build_media.py first.")


def run(*args, **kwargs):
    return subprocess.run([str(arg) for arg in args], check=True, **kwargs)


def output(*args):
    return subprocess.check_output([str(arg) for arg in args], text=True)


def is_macho(path):
    if not path.is_file():
        return False
    with path.open("rb") as file:
        return file.read(4) in MACH_MAGICS


def dependencies(path):
    lines = output("/usr/bin/otool", "-L", path).splitlines()[1:]
    identifier = None
    result = subprocess.run(["/usr/bin/otool", "-D", str(path)], capture_output=True, text=True, check=True)
    if len(result.stdout.splitlines()) > 1:
        identifier = result.stdout.splitlines()[1].strip()
    return [line.strip().split(" (compatibility", 1)[0] for line in lines if line.strip().split(" (compatibility", 1)[0] != identifier]


class RuntimeBundler:
    """Copy and rewrite each Mach-O dependency once; never modify the source tools."""
    def __init__(self, runtime):
        self.runtime = runtime
        self.lib = runtime / "lib"
        self.lib.mkdir(parents=True)
        self.files = {}
        self.origins = []
        self.minimum = tuple(map(int, MINIMUM_MACOS.split(".")))

    def resolve(self, value, source):
        if value.startswith("/"):
            return Path(value).resolve(strict=True)
        if value.startswith("@loader_path/"):
            return (source.parent / value.removeprefix("@loader_path/")).resolve(strict=True)
        if value.startswith("@executable_path/"):
            return (source.parent / value.removeprefix("@executable_path/")).resolve(strict=True)
        if value.startswith("@rpath/"):
            suffix = value.removeprefix("@rpath/")
            commands = output("/usr/bin/otool", "-l", source)
            paths = re.findall(r"cmd LC_RPATH\s+cmdsize \d+\s+path (.+?) \(offset", commands)
            candidates = []
            for path in paths:
                path = path.replace("@loader_path", str(source.parent)).replace("@executable_path", str(source.parent))
                candidates.append(Path(path) / suffix)
            candidates.extend([source.parent / suffix, source.parent.parent / "lib" / suffix, Path(sys.prefix) / "lib" / suffix])
            for candidate in candidates:
                if candidate.is_file():
                    return candidate.resolve()
        raise RuntimeError(f"Cannot resolve {value} required by {source}")

    def add(self, source, destination=None, copied=False):
        source = Path(source).resolve(strict=True)
        if source in self.files:
            return self.files[source]
        destination = destination or (self.lib / source.name)
        if destination.exists() and not copied:
            raise RuntimeError(f"Dependency filename collision: {destination}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not copied:
            shutil.copy2(source, destination)
        destination.chmod(destination.stat().st_mode | 0o200)
        self.files[source] = destination
        self.origins.append({"component": source.name, "bundled": str(destination.relative_to(self.runtime))})
        load_commands = output("/usr/bin/otool", "-l", source)
        for version in re.findall(r"\bminos (\d+\.\d+(?:\.\d+)?)", load_commands):
            self.minimum = max(self.minimum, tuple(map(int, version.split("."))))
        for value in dependencies(source):
            if value.startswith(SYSTEM_PREFIXES):
                continue
            dependency = self.resolve(value, source)
            bundled = self.add(dependency)
            relative = os.path.relpath(bundled, destination.parent)
            run("/usr/bin/install_name_tool", "-change", value, "@loader_path/" + relative, destination, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if destination.parent == self.lib and not destination.name.endswith(".so"):
            run("/usr/bin/install_name_tool", "-id", "@rpath/" + destination.name, destination, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return destination

    def validate(self):
        for path in self.files.values():
            arches = output("/usr/bin/lipo", "-archs", path).split()
            if platform.machine() not in arches:
                raise RuntimeError(f"Wrong architecture in {path}: {arches}")
            for value in dependencies(path):
                if value.startswith(SYSTEM_PREFIXES):
                    continue
                if not value.startswith("@loader_path/"):
                    raise RuntimeError(f"Non-relocatable library reference: {path}: {value}")
                resolved = (path.parent / value.removeprefix("@loader_path/")).resolve(strict=True)
                if not resolved.is_relative_to(self.runtime.resolve()):
                    raise RuntimeError(f"Library dependency escapes bundle: {resolved}")


def copy_licenses(bundler, destination):
    destination.mkdir(parents=True)
    packages = set()
    for source in bundler.files:
        parts = source.parts
        if "Cellar" in parts:
            index = parts.index("Cellar")
            packages.add(Path(*parts[:index + 3]))
    for package in packages:
        for path in package.iterdir():
            if path.is_file() and path.name.upper().startswith(("LICENSE", "COPYING", "COPYRIGHT", "AUTHORS")):
                target = destination / package.parent.name / path.name
                target.parent.mkdir(exist_ok=True)
                shutil.copy2(path, target)
    for component, version in (("ffmpeg", "9.0.2"), ("lame", "4.0")):
        source = ROOT / "build/deps/source" / f"{component}-{version}"
        target = destination / component
        target.mkdir(exist_ok=True)
        for path in source.iterdir():
            if path.is_file() and path.name.upper().startswith(("LICENSE", "COPYING", "COPYRIGHT", "AUTHORS")):
                shutil.copy2(path, target / path.name)
    shutil.copy2(ROOT / "build/deps/build-info.json", destination / "media-build.json")
    shutil.copy2(ROOT / "THIRD_PARTY_NOTICES.md", destination / "README.md")
    manifest = {"python":sys.version, "ffmpeg_version":output(media_tool("ffmpeg"), "-version"), "libraries":bundler.origins, "omitted_python_extensions":list(UNUSED_EXTENSIONS)}
    (destination / "components.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")


def runtime_environment(runtime):
    env = {k:v for k,v in os.environ.items() if not k.startswith(("PYTHON", "DYLD_")) and k != "__PYVENV_LAUNCHER__"}
    env.update(PYTHONHOME=str(runtime), PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1", PATH=str(runtime / "bin") + ":/usr/bin:/bin", AUDIO_FORGE_DESKTOP="1")
    return env


def smoke_test(app):
    runtime = app / "Contents/Resources/runtime"
    env = runtime_environment(runtime)
    python = runtime / "bin/python3"
    with tempfile.TemporaryDirectory(prefix="audio-forge-smoke-") as temporary:
        folder = Path(temporary)
        # Run the bundled application modules from a foreign working directory.
        shutil.copy2(ROOT / "test_mp4_to_m4a.py", folder / "test_mp4_to_m4a.py")
        for name in ("test_audio_formats.py", "test_m4a_gui.py", "test_localization.py", "test_desktop.py"):
            shutil.copy2(ROOT / name, folder / name)
        for name in ASSETS:
            shutil.copy2(app / "Contents/Resources/backend" / name, folder / name)
        env["AUDIO_FORGE_DESKTOP"] = "0"
        run(python, "-B", "-s", "-S", "-m", "unittest", "-q", "test_mp4_to_m4a.py", "test_m4a_gui.py", "test_audio_formats.py", "test_localization.py", "test_desktop.py", cwd=folder, env=env)
    for name in ("ffmpeg", "ffprobe"):
        run(runtime / "bin" / name, "-version", env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("Verified: bundled Python and FFmpeg; all conversion tests pass with Homebrew absent from PATH.", flush=True)


def build_app(app, cache):
    resources = app / "Contents/Resources"
    scripts = resources / "backend"
    scripts.mkdir(parents=True)
    executable = app / "Contents/MacOS/AudioForge"
    executable.parent.mkdir(parents=True)
    for name in ASSETS:
        if name != "app-icon.png":  # Generated with the Dock icon below.
            shutil.copy2(ROOT / name, scripts / name)
    runtime = resources / "runtime"
    bundler = RuntimeBundler(runtime)
    print("Bundling Python standard library…", flush=True)
    stdlib = Path(sysconfig.get_path("stdlib"))
    library = runtime / "lib" / stdlib.name
    shutil.copytree(stdlib, library, ignore=shutil.ignore_patterns("site-packages", "__pycache__", "*.pyc", "test", "tests", "idlelib", "tkinter", "ensurepip", "pydoc_data", "_test*", "config-3*", *(name + ".*" for name in UNUSED_EXTENSIONS)))
    # Framework bin/python3 is a launcher stub that re-execs Python.app. Bundle
    # the actual interpreter so it does not depend on a Frameworks directory.
    interpreter = Path(sys.prefix) / "Resources/Python.app/Contents/MacOS/Python"
    if not interpreter.is_file():
        interpreter = Path(sys.executable)
    bundler.add(interpreter, runtime / "bin/python3")
    for source in stdlib.rglob("*.so"):
        destination = library / source.relative_to(stdlib)
        if destination.is_file():
            bundler.add(source, destination, copied=True)
    print("Bundling FFmpeg and its libraries…", flush=True)
    for tool in ("ffmpeg", "ffprobe"):
        source = media_tool(tool)
        bundler.add(source, runtime / "bin" / tool)
    bundler.validate()
    minimum = ".".join(map(str, bundler.minimum))
    print(f"Compiling native {platform.machine()} client (macOS {minimum}+)…", flush=True)
    run("/usr/bin/xcrun", "swiftc", "-O", "-target", f"{platform.machine()}-apple-macos{minimum}", "-module-cache-path", cache, ROOT / "native/AudioForge.swift", "-framework", "AppKit", "-framework", "WebKit", "-o", executable)
    iconset = Path(cache).parent / "AudioForge.iconset"; iconset.mkdir()
    generator = Path(cache).parent / "make-icon"
    run("/usr/bin/xcrun", "swiftc", "-module-cache-path", cache, ROOT / "native/Icon.swift", "-o", generator)
    run(generator, iconset)
    run("/usr/bin/iconutil", "-c", "icns", iconset, "-o", resources / "AudioForge.icns")
    shutil.copy2(iconset / "icon_512x512.png", ROOT / "app-icon.png")
    shutil.copy2(ROOT / "app-icon.png", scripts / "app-icon.png")
    plist = dict(CFBundleIdentifier="io.github.tsuikaii.AudioForge", CFBundleName="Audio Forge", CFBundleDisplayName="Audio Forge", CFBundleExecutable="AudioForge", CFBundlePackageType="APPL", CFBundleShortVersionString=VERSION, CFBundleVersion=VERSION, CFBundleDevelopmentRegion="en", CFBundleLocalizations=["en", "zh-Hans", "ja"], CFBundleIconFile="AudioForge", LSMinimumSystemVersion=minimum, NSHighResolutionCapable=True, NSAppTransportSecurity={"NSExceptionDomains":{"127.0.0.1":{"NSExceptionAllowsInsecureHTTPLoads":True}}}, NSDownloadsFolderUsageDescription="Audio Forge opens and saves the audio files you select in Downloads.", NSDocumentsFolderUsageDescription="Audio Forge opens and saves the audio files you select in Documents.", NSDesktopFolderUsageDescription="Audio Forge opens and saves the audio files you select on Desktop.", CFBundleDocumentTypes=[{"CFBundleTypeName":"Audio and video", "CFBundleTypeRole":"Editor", "LSHandlerRank":"Alternate", "CFBundleTypeExtensions":["mp4","mp3","flac","m4a"]}])
    (app / "Contents/Info.plist").write_bytes(plistlib.dumps(plist))
    copy_licenses(bundler, resources / "ThirdParty")
    shutil.copy2(ROOT / "LICENSE", resources / "LICENSE")
    # Include the application's editable sources alongside bundled runtime assets.
    source_dir = resources / "Source"; source_dir.mkdir()
    for name in ("build_gui_app.py", "README.md", "LICENSE", "THIRD_PARTY_NOTICES.md", "test_mp4_to_m4a.py", "test_audio_formats.py", "test_m4a_gui.py", "test_localization.py", "test_desktop.py"):
        shutil.copy2(ROOT / name, source_dir / name)
    for name in ASSETS:
        shutil.copy2(ROOT / name, source_dir / name)
    shutil.copytree(ROOT / "native", source_dir / "native")
    shutil.copytree(ROOT / "scripts", source_dir / "scripts", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(ROOT / "docs", source_dir / "docs")
    print(f"Signing {len(bundler.files)} bundled binaries…", flush=True)
    for binary in [*bundler.files.values(), executable]:
        run("/usr/bin/codesign", "--force", "--sign", "-", binary, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    run("/usr/bin/codesign", "--force", "--sign", "-", app)
    run("/usr/bin/codesign", "--verify", "--deep", "--strict", app)
    smoke_test(app)
    return minimum


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-only", action="store_true", help="Build the client without generating a disk image")
    args = parser.parse_args()
    if platform.system() != "Darwin":
        parser.error("Build this package on macOS.")
    dist = ROOT / "dist"; dist.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="audio-forge-build-", dir=dist) as temporary:
        stage = Path(temporary)
        app = stage / "Audio Forge.app"
        minimum = build_app(app, stage / "swift-cache")
        dmg = stage / f"Audio-Forge-{VERSION}-{platform.machine()}.dmg"
        if not args.app_only:
            print("Creating drag-to-install disk image…", flush=True)
            image = stage / "image"; image.mkdir()
            shutil.copytree(app, image / app.name)
            (image / "Applications").symlink_to("/Applications", target_is_directory=True)
            (image / "Install.txt").write_text(f"Audio Forge {VERSION}\n\nDrag Audio Forge.app onto Applications. Eject this disk image, then open Audio Forge from Applications.\n\nRequires an {platform.machine()} Mac running macOS {minimum} or later. Python and FFmpeg are included.\n\nThis build is ad-hoc signed, not Apple-notarized. If macOS blocks it, use System Settings > Privacy & Security > Open Anyway after attempting to open the application.\n\nAudio Forge source: MIT. Third-party components retain their licenses.\nhttps://github.com/tsuikaii/Audio_Forge\n")
            run("/usr/bin/hdiutil", "create", "-volname", "Audio Forge", "-srcfolder", image, "-format", "UDZO", "-ov", dmg)
            run("/usr/bin/hdiutil", "verify", dmg)
            os.replace(dmg, dist / dmg.name)
        target = ROOT / app.name
        if target.exists():
            target.rename(stage / "previous.app")
        try:
            app.rename(target)
        except Exception:
            previous = stage / "previous.app"
            if previous.exists():
                previous.rename(target)
            raise
    print(f"Client: {target}", flush=True)
    if not args.app_only:
        print(f"Installer: {dist / dmg.name}", flush=True)
        write_release_sources(dist)


def write_release_sources(dist):
    """Ship the exact LGPL source archives and recipe alongside the installer."""
    source_archive = dist / f"Audio-Forge-{VERSION}-third-party-sources.tar.gz"
    with tarfile.open(source_archive, "w:gz") as archive:
        for path in sorted((ROOT / "build/deps/archives").iterdir()):
            if path.suffix in (".xz", ".gz"):
                archive.add(path, arcname=path.name)
        for path in (ROOT / "scripts/build_media.py", ROOT / "build/deps/build-info.json", ROOT / "THIRD_PARTY_NOTICES.md", ROOT / "docs/BUILDING.md"):
            archive.add(path, arcname=str(path.relative_to(ROOT)) if path.is_relative_to(ROOT / "scripts") or path.is_relative_to(ROOT / "docs") else path.name)
    artifacts = [dist / f"Audio-Forge-{VERSION}-{platform.machine()}.dmg", source_archive]
    checksums = "".join(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n" for path in artifacts)
    (dist / "SHA256SUMS.txt").write_text(checksums)
    (dist / (artifacts[0].name + ".sha256")).write_text(checksums.splitlines()[0] + "\n")


if __name__ == "__main__":
    main()
