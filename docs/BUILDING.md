# Development and release builds

## Run from source

Python 3.12 or later and FFmpeg/ffprobe with AAC, ALAC, FLAC, and libmp3lame
support are required. There are no pip or npm dependencies.

```sh
git clone https://github.com/tsuikaii/Audio_Forge.git
cd Audio_Forge
python3 -B m4a_gui.py
```

On macOS, development dependencies can be installed with
`brew install python@3.14 ffmpeg`. The browser UI opens automatically; use its
Quit button to stop the local service. Opening `m4a_gui.html` directly does not
start the backend. Browser development and the CLI can run on other systems
with Python and FFmpeg, but the packaged desktop client is macOS-only.

Run all tests with actual FFmpeg binaries available on PATH:

```sh
python3 -B -m unittest -v test_mp4_to_m4a test_m4a_gui test_audio_formats test_localization test_desktop
```

Tests create synthetic signals and images in temporary directories. They cover
all 12 conversion directions, audio packet preservation, metadata and artwork,
failure/overwrite protection, localization, and the private desktop service.

## Build the native macOS release

Build on macOS 15 or later with Xcode command-line tools, Python 3.14, pkgconf,
make, and a C compiler. The current public binary is for Apple Silicon.
The Python framework supplied by Homebrew is the reference build runtime.

```sh
xcode-select --install
brew install python@3.14 pkgconf
python3 -B scripts/build_media.py
python3 -B build_gui_app.py
```

The media builder downloads pinned FFmpeg 9.0.2 and LAME 4.0 archives, verifies
their SHA-256 hashes, and builds shared LGPL libraries. It disables GPL/nonfree
code, network protocols, external dependency autodetection, ffplay, and codecs
unrelated to this workflow. LAME's frontend and MP3 decoder are omitted.
Small synthetic-source filters and the MPEG-4 encoder remain for the real
integration tests. Configure arguments are recorded in `build/deps/build-info.json`.
Sources are unmodified. Run this script again after changing its configuration;
delete `build/deps` first when changing dependency versions or architecture.

The app builder copies Python's standard library, excluding pip, Tk/IDLE, test
packages, and optional TLS, database, decimal, compression, curses, and REPL
extensions that the private local service does not use. The resulting runtime
is for Audio Forge, not a replacement for a full Python installation. Browser
development uses your full local Python installation.

Every non-system Mach-O dependency is copied once and rewritten to a bundle
relative path. The builder checks architecture and library references, compiles
the AppKit/WebKit client, generates the icon, signs the application locally, and
runs all tests using the bundled runtime with Homebrew absent from PATH.
An existing application is replaced only after the staged build succeeds.

Outputs:

- `Audio Forge.app` — standalone native client.
- `dist/Audio-Forge-1.0.0-arm64.dmg` — drag-to-Applications installer.
- `dist/Audio-Forge-1.0.0-third-party-sources.tar.gz` — exact LGPL source archives and recipe.
- `dist/SHA256SUMS.txt` — checksums for both release downloads.

`python3 -B build_gui_app.py --app-only` skips the installer and source archive.
The architecture suffix follows the build machine. Intel packaging is not
validated by this release. Do not describe output as bit-for-bit reproducible:
toolchain versions, code signatures, timestamps, and disk images can differ.

## Project layout

| Path | Purpose |
| --- | --- |
| `native/AudioForge.swift` | Native window, WebKit, menus, subprocess lifecycle, and safe quit |
| `native/Icon.swift` | Original pixel artwork inside a continuous rounded app tile |
| `m4a_gui.py` | Authenticated local backend, file selection, thumbnails, and conversion jobs |
| `mp4_to_m4a.py` | Format conversion, metadata editing, probing, and optional CLI |
| `m4a_gui.html`, `ui.css`, `ui.js` | Classic desktop interface |
| `messages.py`, `locales.json` | Shared translations and localized errors |
| `test_*.py` | Standard-library integration tests |
| `scripts/build_media.py`, `build_gui_app.py` | Dependency and macOS package builders |

The legacy converter filename is retained for compatibility. Editable app
sources, MIT license, and dependency notices are also included inside the app.

## Publish a release

Update the version in `build_gui_app.py`, the UI footer, and all `about_version`
translations. Update the changelog, rebuild, and exercise the installed native
client: select a file, convert, edit artwork, minimize/restore, switch languages,
and quit. Verify the DMG and checksums, then tag the tested commit and attach the
installer, third-party source archive, and checksum file to the GitHub release.
GitHub provides the corresponding application source archive for the tag.

Current packages are ad-hoc signed, not Apple-notarized. Developer ID signing
and notarization require the maintainer's Apple credentials and are not part of
this repository. Never commit signing certificates or credentials.
