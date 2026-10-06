- **Fixes Rewind getting stuck on slow "compatibility capture".** The fast screen capture can say no for a moment, for example right after an update restart. Rewind used to give up after two tries and then remember compatibility capture forever. It now waits and retries longer, only uses compatibility capture as a temporary fallback, and tries the fast capture again whenever a game starts or stops.
- PCs that were locked into compatibility capture by this are put back on Automatic.

Download **Rewind.exe** and run it. Installed copies update themselves.
