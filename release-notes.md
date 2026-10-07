- **Fixes "certificate verify failed: certificate has expired" when sharing a link.** Some PCs have a Windows that's missing newer root certificates, so it can't verify the sharing site. Rewind now falls back to the trusted list built into it, for sharing and for updates, downloads and the free sound search.
- **Fixes "The process cannot access the file" when renaming a clip.** The player still held the file open. Rewind now lets go of it first, waits a moment if something else is still using it, and says so plainly if it can't.

Download **Rewind.exe** and run it. Installed copies update themselves.
