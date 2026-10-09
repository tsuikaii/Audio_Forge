# Audio Forge

A small, local music converter with a Windows 98 soul.

[Download for macOS](https://github.com/tsuikaii/Audio_Forge/releases/latest) · [Development](docs/BUILDING.md) · [MIT License](LICENSE)

![Audio Forge](docs/images/conversion.png)

- Convert between **MP4, MP3, FLAC, and M4A**.
- Edit **title, artist, album, date**, and **cover artwork**.
- Copy compatible audio without re-encoding and validate every save.
- Work locally, in **English**, **Simplified Chinese**, or **Japanese**.

## Install

Requires **Apple Silicon** and **macOS 15+**. Open the DMG, drag **Audio Forge**
into **Applications**, and launch it. Python and FFmpeg are included.

The app is ad-hoc signed, not Apple-notarized. If macOS blocks the first launch,
follow [Apple's Open Anyway instructions](https://support.apple.com/en-us/102445).

## Use

Open a file, choose the output format, adjust **Tags & artwork**, then convert.
Choosing the same format edits tags without re-encoding. The tool processes
one file at a time and preserves existing MP4 video.

[Usage](docs/USAGE.md) · [Build instructions](docs/BUILDING.md) · [Contributing](.github/CONTRIBUTING.md)

Audio Forge is **MIT-licensed**. FFmpeg, LAME, and Python retain their own
licenses; see [third-party notices and sources](docs/THIRD_PARTY.md).
