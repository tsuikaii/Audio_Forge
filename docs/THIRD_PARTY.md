# Third-party notices

Audio Forge's original source, pixel artwork, and documentation are licensed
under the [MIT License](../LICENSE). Bundled dependencies keep their own licenses;
the MIT license does not replace them.

| Component | Release version | License | Source |
| --- | --- | --- | --- |
| FFmpeg | 9.0.2 | LGPL-2.1-or-later; upstream notices also apply | [ffmpeg.org](https://ffmpeg.org/releases/ffmpeg-9.0.2.tar.xz) |
| LAME | 4.0 | LGPL-2.0-or-later | [LAME project](https://downloads.sourceforge.net/project/lame/lame/4.0/lame-4.0.tar.gz) |
| CPython | 3.14.7 | Python Software Foundation License and included notices | [python.org](https://www.python.org/ftp/python/3.14.7/Python-3.14.7.tar.xz) |

Audio Forge uses FFmpeg under LGPL version 2.1 or later and LAME under LGPL
version 2.0 or later. The release uses shared libraries with GPL, nonfree,
network, and automatic external-library detection disabled. FFmpeg is invoked
as a separate process. Audio Forge does not link its native client to FFmpeg.
No upstream FFmpeg or LAME source is modified. Installed library paths are
rewritten to make the application relocatable.

The exact FFmpeg and LAME source archives, verified SHA-256 checksums, configure
options, and build recipe are available in
[`Audio-Forge-1.0.0-third-party-sources.tar.gz`](https://github.com/tsuikaii/Audio_Forge/releases/download/v1.0.0/Audio-Forge-1.0.0-third-party-sources.tar.gz),
alongside the installer. The recipe also lives in
[`scripts/build_media.py`](../scripts/build_media.py). See
[`docs/BUILDING.md`](BUILDING.md) for build instructions.

Original dependency license texts and the actual binary inventory are included
inside `Audio Forge.app/Contents/Resources/ThirdParty`. CPython comes from the
Homebrew framework build; its included license covers additional stdlib
components. Unused optional extensions and their external libraries are omitted
from the private service runtime. Apple's system frameworks and system libraries
are used from macOS and are not copied into the application.

You may inspect, rebuild, and replace the bundled media libraries. No agreement
in this project prohibits reverse engineering for debugging modifications to
those libraries. After modifying a macOS bundle, re-sign your local copy with
`codesign --force --deep --sign - "Audio Forge.app"`.

FFmpeg is a trademark of Fabrice Bellard. Audio Forge is an independent project
and is not affiliated with FFmpeg, Apple, or Microsoft. The interface is inspired
by classic Windows controls; its pixel icons are drawn by this project.
