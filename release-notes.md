- **Fixes a crash ("The memory could not be read").** Following your headphones started and stopped the Windows audio library every few seconds, which is not safe next to the running recording and could corrupt memory. Rewind now asks Windows directly which output is the default (a safe call that doesn't touch the audio library) and only restarts the sound capture, without stopping the recording, when you actually switch. The audio library is also locked so two parts of Rewind can't use it at once.
- **A crash log.** If Rewind ever crashes again it now writes where it happened to `crash.log` next to the settings, so it can be found and fixed.

Download **Rewind.exe** and run it. Installed copies update themselves.
