# Development

Python 3.12+ and FFmpeg/ffprobe with AAC, ALAC, FLAC, and libmp3lame support are
required. The application uses Python's standard library and system WebKit.

```sh
git clone https://github.com/tsuikaii/Audio_Forge.git
cd Audio_Forge
make run
make test
```

`make run` opens the browser interface. Use its Quit button to stop the local
service. `make test` runs the conversion, metadata, artwork, localization, and
desktop service tests using synthetic files in temporary directories.

## Layout

```text
src/audio_forge/   Python package and web interface
native/           macOS window and icon
scripts/          Build tools and launcher
tests/            Integration tests and shared helpers
docs/             Usage, build notes, licenses, and screenshots
```

`media.py` handles conversion and the optional CLI; `server.py` serves the
interface; `i18n.py` shares translations. UI assets live in `src/audio_forge/web`.
Project metadata and the package version live in `pyproject.toml`.

## Native macOS build

On macOS 15+, install Xcode command-line tools and the build dependencies:

```sh
xcode-select --install
brew install python@3.14 pkgconf
make media
make app
```

The media builder verifies pinned FFmpeg 9.0.2 and LAME 4.0 source archives and
builds shared LGPL libraries. GPL/nonfree code, networking, unused codecs, and
external dependency autodetection are disabled. Configure options are recorded
in `build/deps/build-info.json`. Delete `build/deps` before changing dependency
versions or architecture.

The app builder copies the package and a reduced Python runtime, relocates
non-system libraries, verifies signatures, and runs the tests with the bundled
runtime. Editable source retains the repository layout inside the application.

Outputs: **Audio Forge.app**, plus the DMG, third-party source archive, and
**SHA256SUMS.txt** in `dist/`. The architecture suffix follows the build machine;
only Apple Silicon is validated by v1.0.0. For an app without release archives,
run `python3 -B scripts/build_app.py --app-only`.

Builds are ad-hoc signed, not Apple-notarized. Developer ID signing requires
Apple credentials. Toolchains and timestamps can change output hashes.

## Optional Python install and CLI

You can install the package in a virtual environment with `python3 -m pip install -e .`.
This exposes `audio-forge` and `audio-forge-cli`; FFmpeg remains a separate
runtime requirement. To use the CLI directly from the checkout:

```sh
PYTHONPATH=src python3 -m audio_forge.media convert "video.mp4" -o "song.mp3"
PYTHONPATH=src python3 -m audio_forge.media edit "song.m4a" --title "New title"
```

Use `convert --help` or `edit --help` for codec, bitrate, and metadata options.
For contributions and release history, see [Contributing](../.github/CONTRIBUTING.md)
and [Changelog](CHANGELOG.md).
