- **A frozen capture now fixes itself.** If the picture froze while ffmpeg stayed running (the sound carried on), only closing Rewind used to help. Rewind now notices after about 12 seconds without new video, restarts the capture, and carries on. A long recording continues through it. The restart used to be able to hang itself, because it closed the audio pipe while a write was still waiting on it, so it now ends the recorder first.

Download **Rewind.exe** and run it. Installed copies update themselves.
