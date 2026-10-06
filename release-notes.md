- **Fixes "Couldn't open audio: Invalid number of channels".** Rewind now tries the channel counts and sample rates a sound device will really accept, so game sound and the mic open on headsets, virtual mixers and spatial-audio setups that report more channels than Windows allows. If audio still can't open, Rewind records video only and says so, without hiding capture errors.
- **Recording that starts but never fills the buffer** is now spotted after 14 seconds and retried with the next capture method.
- **Better AMD and Intel detection.** Rewind tries more ways to start each graphics encoder, and Settings now shows which graphics cards Windows found and why an encoder isn't available.
- Compatibility capture now uses real screen pixels on scaled displays (125%, 150%).
- New **Copy report** button in Settings: copies your graphics card, what Rewind tried and the recent errors, ready to paste to whoever is helping you.

Download **Rewind.exe** and run it. Installed copies update themselves.
