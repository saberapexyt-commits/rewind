# Rewind

Instant replay for your PC, a sibling app to AutoClip. Rewind quietly keeps the last 30 seconds of your screen and sound. When something great happens, press **Alt + F8** and that moment is saved as a clip, named after the game you were playing.

## Publish it (exe + website), one time

1. Install Python from python.org (tick "Add python.exe to PATH").
2. Double-click **`publish.bat`**.
3. A GitHub page opens with the right boxes already ticked. Press **Generate token**, copy it, and paste it into the window.

That's it. The script:
- creates a public `rewind` repo on your GitHub and uploads this folder,
- turns on the website at `https://<your-name>.github.io/rewind/`,
- tags `v1.0.0`, which builds **Rewind.exe** in the cloud and publishes it as a Release,
- waits about 5 minutes, then opens the website. Its **Download** button gives a single `Rewind.exe`. On first run it downloads ffmpeg by itself, so there's nothing to unzip.

**Shipping an update:** change `VERSION` in `app.py` (for example to `"1.0.1"`) and run `publish.bat` again. Anyone on an older version gets the new `Rewind.exe` downloaded in the background and sees **Restart to update** in the app (one click, and it relaunches on the new version).

The token is saved in `%APPDATA%\Rewind\publish.json` only if you say yes. Delete that file to forget it.

## Run it without building

Put `ffmpeg.exe` and `ffprobe.exe` in this folder (or on PATH), then double-click `run_rewind.bat`.

## Using it

- Rewind starts buffering as soon as it opens. The Home tape shows the last 30 seconds filling up, with your audio level.
- Press the shortcut in any game (default **Alt + F8**). You'll hear a short chime, and the clip lands in `Videos\Rewind`.
- Closing the window keeps Rewind running in the tray, so the buffer keeps going. Right-click the tray icon to save, pause, or quit.
- Clips: watch, rename, show in folder, or delete (to the Recycle Bin).
- Settings: replay length (15s to 5m), shortcut, encoder, display, frame rate, quality, game sound, mic, and clips folder.

## 1.5.3

- **Your edit is saved automatically.** The editor keeps your project (clips, tracks, effects, text, sounds and the name) on your PC after every change, so it's still there after closing Rewind or installing an update. Open **Editor** in the sidebar to carry on.

## 1.5.2

- **Right click moves the playhead in the editor.** Right click anywhere on the timeline to jump to that spot, or hold and drag to scrub.

## 1.5.1

- **Add as many video layers as you like.** Press **+ Video** under the timeline for each one. A new video layer fills the whole screen until you resize or move it.
- **You choose your tracks.** Tracks no longer appear on their own: press **+ Video**, **+ Text**, **+ Effect**, **+ Filter** or **+ Audio** to add one, and the bin button on a track removes it.
- **Grabbing a clip no longer moves the playhead.** Only the ruler at the top moves it.
- **Effects and filters: click to preview, drag to add.** Click one to see it on the player, drag it down onto its track to add it, then drag the bar left or right to move it or pull its edges to change how long it lasts.

## 1.5.0

- **The video editor is rebuilt like CapCut.** Real tracks: Effect, Filter, Text, Layer, Main and Audio, each with its own show/hide and mute button, and extra tracks appear when items overlap. Drag things between tracks, trim them from either edge, and zoom or fit the timeline.
- **Effects and filters are now clips on the timeline.** Drop Glitch, Shake, Blur and more (or a colour look like Noir or Cinematic) on their own track and drag the edges to set exactly how long they last. They no longer cover the whole clip. Each has an intensity slider.
- **Transitions now work and are easy to find.** Click the small button between two clips, pick a transition from animated tiles (or drag one onto the join), and it plays right away. A Transition panel sets the length or applies it to every join.
- **Transform every clip:** scale, move, rotate and opacity, plus layers you can drag in the preview.
- A new **Editor** item in the sidebar, an editor that keeps your edit when you go back Home, window buttons in the editor, and a Ratio menu for 16:9, 9:16, 1:1 and 4:5.

## 1.4.3

- **Real fix for "Capture stopped: Error opening input files: Invalid argument".** The cause was a newer ffmpeg that Rewind had downloaded: it no longer accepts one option Rewind used for game sound. Rewind now checks what the ffmpeg in use accepts, so it works with old and new builds.
- **Rewind now uses one pinned, tested ffmpeg** and checks it with a SHA-256 before using it, instead of always downloading the newest. A newer ffmpeg can no longer break an install. PCs that already downloaded one switch to the pinned build the next time Rewind starts.

## 1.4.2

- **Fixes "Couldn't open audio: Invalid number of channels".** Rewind now tries the channel counts and sample rates a sound device will really accept, so game sound and the mic open on headsets, virtual mixers and spatial-audio setups that report more channels than Windows allows. If audio still can't open, Rewind records video only and says so, without hiding capture errors.
- **Recording that starts but never fills the buffer** is now spotted after 14 seconds and retried with the next capture method.
- **Better AMD and Intel detection.** Rewind tries more ways to start each graphics encoder, and Settings now shows which graphics cards Windows found and why an encoder isn't available.
- Compatibility capture now uses real screen pixels on scaled displays (125%, 150%).
- New **Copy report** button in Settings: copies your graphics card, what Rewind tried and the recent errors, ready to paste to whoever is helping you.

## 1.4.1

- **Fixes "Capture stopped: Error opening input files: Invalid argument".** If the fast screen capture can't start on a PC (some laptops, hybrid graphics, drivers that refuse it), Rewind now switches by itself to compatibility capture and remembers it. You can pick the method in Settings, under Video, Screen capture.
- If a graphics encoder keeps failing, Rewind falls back to the processor after the capture method has been tried, instead of before.
- Settings has a Show log file button to help work out problems.

## 1.4.0

- **Editor: multiple tracks.** Put clips on top of the main video as picture-in-picture layers (move, resize, fade, set opacity), stack text on its own lanes, and run several sound tracks at once.
- **Editor: transitions.** Twelve free transitions between clips (fade, dissolve, dip to black, wipes, slides, circle open and close, zoom), with adjustable length.
- **Editor: effects.** Thirteen free effects you can stack on any clip or layer: black and white, sepia, vivid, cool, warm, faded film, blur, sharpen, negative, vignette, film grain, mirror and flip.
- **Editor: free sounds.** Twelve built-in sound effects, plus a search of free music and sound effects online (public domain and CC0, no credit needed).
- The editor now has the minimise, maximise and close buttons and can be dragged by its top bar.

## 1.3.0

- **Video editor.** Open any clip and press Open in editor: a multi-clip timeline with split, trim, reorder, speed (0.25x to 4x), volume, fades, brightness / contrast / saturation, text with fonts, colours and outlines, music and sound tracks, 16:9 / 9:16 / 1:1 / 4:5 canvases with Fit, Fill or Fit + blur, undo and redo, and an export to a normal mp4.

## 1.2.1

- Links and Discord-sized copies are limited to clips of 10 minutes or less. Longer ones can be trimmed and saved as a copy first. Copying the file has no limit.

## 1.2.0

- Every hotkey can be Tap or Long press (hold the key for 2 seconds), so a stray press won't clip or bookmark by accident.
- Forever links now work for any clip length: a clip over 200 MB is shrunk to fit just for the link, and your original stays untouched.

## 1.1.1

- Share links can now last forever: pick Forever (up to 200 MB) in the Share menu, or keep the 1 hour to 3 day options.

## 1.1.0

- Hotkeys: Clip (with its length next to it), Start / stop long recording, and Bookmark. Set any of them in Settings.
- Long recordings: record a whole session, drop bookmarks as you go, and see them as flags on the timeline when you watch it back.
- Share without sending the mp4: copy the file, shrink it to fit Discord (10, 50 or 500 MB), or get a temporary link.

## 1.0.9

- Vertical clips: open any clip and pick a format (Fill, Fit + blur or Vertical zoom) to see a live 9:16 preview and save a 1080 x 1920 copy. Drag the preview to choose the part of the picture, and trim at the same time.

## 1.0.8

- Saving a replay is much faster, even for 2 and 5 minute clips. The clip is written in a single pass and the sound plays the moment you press the key.
- Four new save sounds: Clip, Rewind, Ping and Chime. Clip is the new default.
- Updates work like AutoClip's now: a banner offers Update now, Later or Skip, shows the download progress, and restarts Rewind for you.

## 1.0.7

- Removed the "shortcut already in use" warning from Home. Rewind now retries quietly at startup, which fixes it after an update.
- Website: full changelog and a clip editor section.

## 1.0.6

- New clips show up in the library right away, without switching pages.
- Select several clips (tick the box on a clip, or Ctrl+click) and delete them all at once.

## 1.0.5

- Fixed the player: the video no longer spills over the timeline.
- The shortcut can be any single key (like F8 or a letter), not just a combo.
- The left sidebar is back to labelled items with a teal active pill and the app card at the bottom.

## 1.0.4

- **New clip player** with a timeline, a thumbnail strip, volume, full screen and ← → to move between clips.
- **Trim clips.** Drag the handles, then **Save as copy** or **Replace original**.
- Only one Rewind can run at a time, so two copies can't write into the same buffer and garble clips.

## 1.0.3

- Redesigned the app: a flat, dark clip library (icon rail, status and shortcut chips up top, clips grouped by day with length, size and a Watch button) instead of the neon dashboard.

## 1.0.2

- **Microphone on by default.** Your voice is mixed into clips. If Windows' default mic is a silent virtual device (like Voicemeeter), Rewind picks a real microphone instead. A Mic on/off button sits on Home, and the mic can be chosen in Settings → Audio.

## 1.0.1

- New neon Home screen: a big Save replay button, game-art recent replays, no waveform.
- **Settings → Updates** has a Check for updates button, update status and an auto-download switch.

## Auto-update

- **Auto-update.** Like AutoClip: Rewind checks GitHub on startup, downloads the new `Rewind.exe` quietly, and swaps itself in when you press **Restart to update**. Each release now also attaches a standalone `Rewind.exe`.

## Highlights

- **No more black clips.** Rewind checks the picture every 4 seconds. If a game comes out black for about 12 seconds, it switches to recording that game's window (Windows Graphics Capture) and remembers the game. HDR screens are captured in 8-bit so they don't come out washed out or black. Settings → Games → *How to record games* lets you force screen or window capture.
- **Game detection.** Rewind spots the game in front from a built-in list of about 50 popular games, game library folders (Steam, Epic, Riot, Xbox, Battle.net, GOG, EA, Ubisoft), or any app that fills the screen and isn't a browser or video player. Clips are named after the game and saved in a folder per game. Optionally, the buffer runs only while a game is open. A wrongly detected app can be marked "not a game".
- **Better sound.** There are three new save sounds (chime, shutter, pop) at three volumes, with a preview, and a softer sound when a save fails. Clip audio is cleaner too: a seam-free resampler removes faint crackles, a soft limiter replaces hard clipping on loud moments, 5.1/7.1 headsets are folded down properly, and AAC is now 192k.

## How it works

- **Capture:** ffmpeg's `ddagrab` (Windows Desktop Duplication) grabs the screen straight from the GPU.
- **Encode:** NVENC on NVIDIA (your RTX 3060 Ti), AMF on AMD, Quick Sync on Intel, or x264 on the CPU as a fallback. Rewind tests which ones work at startup.
- **Buffer:** video is written to a ring of 2-second files in your temp folder that keep overwriting themselves, so disk use stays flat (roughly 100–250 MB at 30 seconds, 1080p60).
- **Audio:** game sound (WASAPI loopback) and the mic are mixed in Python and fed to ffmpeg as one steady stream, so it stays in sync even through silence.
- **Saving:** the newest pieces are joined and trimmed at a keyframe with no re-encode, which takes about a second.

Settings live in `%APPDATA%\Rewind\settings.json`, and errors go to `%APPDATA%\Rewind\rewind.log`.

## Tested vs. untested

Tested off Windows with a fake screen and audio track: the rolling buffer, saving (including trimming to the exact length), clip naming, thumbnails, the whole local API, video streaming, and every page of the UI.

Not tested yet, because they only exist on Windows:
- Real screen capture with `ddagrab` and the NVENC/AMF/QSV paths.
- Game and mic audio through PyAudioWPatch.
- The global shortcut, tray icon, frameless window, sounds, and the exe build.
- Real game detection and window capture (`gfxcapture`). The black-clip switch was tested with a fake black screen and a fake Valorant.
- `publish.py` against the real GitHub. It was tested end to end against a fake GitHub server.

Expect the first real run to need a fix or two. If something breaks, check `rewind.log` and paste the error.

## Good to know

- **Fullscreen games:** borderless or windowed fullscreen records most reliably. Some exclusive-fullscreen games show black frames.
- **Shortcut conflicts:** Alt + F10 is NVIDIA's own instant-replay key, which is why Rewind defaults to Alt + F8. If a shortcut is taken, Rewind says so and keeps the old one.
- **Switching headphones/speakers:** toggle game sound off and on in Settings so Rewind picks up the new device.

## Ideas for next

- A "Send to AutoClip" button on each clip.
- A second shortcut that bookmarks a moment without saving.
- Start with Windows.
- Per-game folders and a quick trim before saving.
