# Usage

1. Open an MP4, MP3, FLAC, or M4A file.
2. Select a format in **Conversion**. **Auto** copies compatible audio or chooses
   the format's default encoder.
3. Edit **Title**, **Artist**, **Album**, and **Year / date** in **Tags & artwork**.
   Clear a field to remove its tag; add, replace, or remove JPEG/PNG artwork.
4. Check the output path, then convert or save. Use **Show in Finder** for the result.

![Tags and artwork](images/tags-artwork.png)

Matching formats edit tags in place without re-encoding. Choose another output
path to keep a separate copy. Other formats create a file next to the source.
Existing destinations require overwrite confirmation. Quit is blocked during
conversion to protect the active save.

| Format | Auto audio behavior | Video |
| --- | --- | --- |
| M4A | Copy AAC/ALAC; otherwise encode AAC | Audio and compatible artwork |
| MP3 | Copy MP3; otherwise encode MP3 | Audio and compatible artwork |
| FLAC | Copy FLAC; otherwise encode FLAC | Audio and compatible artwork |
| MP4 | Copy AAC/ALAC/MP3; otherwise encode AAC | Preserve existing video |

AAC and MP3 default to 256 kbps. M4A/MP4 also offer ALAC. The first audio track
is used; lossless output cannot restore detail already lost in the source.
Unexposed tags are preserved where supported by the destination format.

**Cmd/Ctrl+O** opens a file; **Cmd/Ctrl+Enter** converts or saves. Drag the blue
title bar to move the window; double-click it to maximize/restore. Its three
buttons minimize, maximize/restore, and quit. Restore minimized windows from the Dock.

The client processes files locally and uploads nothing. Its authenticated
service listens only on `127.0.0.1`. For downloads and checksums, see
[Releases](https://github.com/tsuikaii/Audio_Forge/releases/latest).
