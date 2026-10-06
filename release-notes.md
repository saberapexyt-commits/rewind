- **Fixes clips with hours of sound and a broken timeline.** If the PC went to sleep (or Rewind was frozen for a while), the sound pipe could write the whole gap into the buffer, so the next clip came out hundreds of MB with a 140 minute timeline and a black strip. Rewind now skips that gap and keeps recording in real time.
- **No damaged clip is ever kept.** Every saved clip, long recording, cut and edit export is checked before it appears in your library: it has to open, have a picture, and its sound has to match its picture. A clip that fails is repaired if possible and otherwise thrown away, never saved half-broken.
- **Old damaged clips repair themselves.** When Rewind starts it fixes clips whose sound runs past the picture and clears out half-written files.

Download **Rewind.exe** and run it. Installed copies update themselves.
