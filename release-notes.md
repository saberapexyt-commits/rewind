- **Real fix for "Capture stopped: Error opening input files: Invalid argument".** The cause was a newer ffmpeg that Rewind had downloaded: it no longer accepts one option Rewind used for game sound. Rewind now checks what the ffmpeg in use accepts, so it works with old and new builds.
- **Rewind now uses one pinned, tested ffmpeg** and checks it with a SHA-256 before using it, instead of always downloading the newest. A newer ffmpeg can no longer break an install. PCs that already downloaded one switch to the pinned build the next time Rewind starts.

Download **Rewind.exe** and run it. Installed copies update themselves.
