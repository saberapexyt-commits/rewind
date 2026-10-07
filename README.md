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

## 1.6.11

- **Pick the clip size.** New **Clip size** in Settings → Video: Original, 1440p, 1080p, 720p or 480p. Smaller sizes make smaller files and are easier on your PC. Sizes bigger than your screen are greyed out. In a test on a 1080p screen, 720p came out at 1280×720 and 480p at 854×480. Intel graphics use the card's own scaler, which I couldn't test here.
- **Clips folder you can type.** The Change button now tells you if nothing was picked, and a new box lets you type or paste a folder. Rewind creates it and checks it can save there before switching, and says why if it can't.
- **Clearer graphics info.** The Video card now lists only your real graphics cards (not virtual monitors like "Meta Virtual Monitor") and explains in plain words when an encoder isn't available, instead of showing raw ffmpeg text.
- **Settings saving is sturdier.** Two settings changes at the same moment, or a virus scanner touching the file, could make a save fail. Saves now take turns and retry briefly.

## 1.6.10

- **A frozen capture now fixes itself.** If the picture froze while ffmpeg stayed running (the sound carried on), only closing Rewind used to help. Rewind now notices after about 12 seconds without new video, restarts the capture, and carries on. A long recording continues through it. The restart used to be able to hang itself, because it closed the audio pipe while a write was still waiting on it, so it now ends the recorder first.

## 1.6.9

- **Smoother clips and long recordings.** Rewind records in 2 second pieces and joins them when you save. The joiner added a tiny extra pause (up to 65 ms) at every join, so the picture hitched every two seconds and the sound steps were uneven, which could look like the video freezing while the sound kept going. Pieces are now joined at their true length: in a test, the hitches at the joins dropped from 32 to a handful of single-frame gaps, and the sound steps became perfectly even. This applies to replay clips and long recordings, including recovered ones.
- **Freeze detection.** If the screen capture itself stalls for a few seconds (a heavy game, a busy GPU), Rewind now writes a "video capture stalled" line with how long it lasted to `rewind.log`, so a real stall can be told apart from a joining problem.

## 1.6.8

- **Starting a long recording is gentler.** The crash-protection helper now starts a few seconds later and at low priority, so starting a recording can't compete with a game or a stream. There is a new switch in Settings, **Protect long recordings**, to turn the helper off entirely. Rewind also logs each step of starting a recording, to help track down anything that still gets in the way of a screenshare.

## 1.6.7

- **Fixes "certificate verify failed: certificate has expired" when sharing a link.** Some PCs have a Windows that's missing newer root certificates, so it can't verify the sharing site. Rewind now falls back to the trusted list built into it, for sharing and for updates, downloads and the free sound search.
- **Fixes "The process cannot access the file" when renaming a clip.** The player still held the file open. Rewind now lets go of it first, waits a moment if something else is still using it, and says so plainly if it can't.

## 1.6.6

- **Full screen really fills the screen.** When the window fills the screen (or half of it), Windows 11's rounded corners and thin border are turned off, so nothing of what's behind shows at the sides, top or corners. The taskbar stays visible. Going back to a normal window brings the rounded corners back.

## 1.6.5

- **Fixes a crash ("The memory could not be read").** Following your headphones started and stopped the Windows audio library every few seconds, which is not safe next to the running recording and could corrupt memory. Rewind now asks Windows directly which output is the default (a safe call that doesn't touch the audio library) and only restarts the sound capture, without stopping the recording, when you actually switch. The audio library is also locked so two parts of Rewind can't use it at once.
- **A crash log.** If Rewind ever crashes again it now writes where it happened to `crash.log` next to the settings, so it can be found and fixed.

## 1.6.4

- **Fixes dragging in the editor.** Once a clip, effect, text or sound was selected, you couldn't grab it again to move it or pull its edges, and pressing on it moved the playhead instead. A style meant for the clip player's trim box was also applying to selected timeline items. They're separate now.
- **Transitions rebuilt.** "Zoom in" came out as a flat solid colour in the exported video, so it's gone (old projects that used it get a fade). "Dip to black" and "Dissolve" in the preview now look like what the export makes. New: Dip to white, Soft wipe left and right, Slide up and down, and Pixelate. The animated previews on the tiles match each transition.

## 1.6.3

- **Start with Windows.** A new switch in Settings opens Rewind in the tray when you sign in, so you never miss a clip after a restart.
- **Sound waveforms in the editor.** Video and sound clips on the timeline now show their audio, so you can line a cut up with a loud moment.

## 1.6.2

- **Choose which sound to record.** Settings → Audio → Sound to record lets you pick your headphones or speakers (or any other output) instead of following Windows. Leave it on "Follow the Windows default" and Rewind switches by itself when you plug in headphones. If the one you picked isn't connected, Rewind uses the Windows default and tells you.

## 1.6.1

- **A crash or force close no longer loses a long recording.** A small helper watches over it: if Rewind stops unexpectedly, the helper saves what was recorded (marked "recovered") with your bookmarks. If you were only buffering and hadn't pressed the clip button, nothing is kept and nothing keeps running.
- **The recorder always closes with Rewind.** ffmpeg is tied to Rewind, so End Task or a crash can't leave it running in the background, and any stray one is cleared at startup.
- **Game sound follows your output device.** Plug in headphones or switch outputs and Rewind moves over within a few seconds, with no restart.
- **Low disk protection.** A warning on Home when under 5 GB is free, saves are refused with a clear message instead of failing halfway, and a long recording is saved safely before the drive fills up.
- **Updates are verified.** Each release publishes a SHA-256 checksum, and Rewind refuses to install a download that doesn't match.
- **Settings can't be corrupted** by a crash or power cut: they are written safely and a backup copy is kept.
- **Show older clips.** The Clips page loads 400 at a time and has a button for the rest.
- **Less disk activity.** The clips folder is no longer listed twice a second.
- **Clips are private to Rewind.** Viewing clips and thumbnails now needs a secret that other websites can't send.

## 1.6.0

- **Move, snap and resize the window properly.** Drag the top bar to the top of the screen to fill it, or to the left or right edge for half the screen. Pull a filled window down to bring it back to its old size. Grab any edge or corner to resize it, and double-click the top bar to fill or restore. It works on every monitor and on scaled displays.
- **Rewind remembers where its window was** and puts it back the next time you open it.
- Clean-up: leftover work folders from crashed saves or exports are removed, and the log no longer grows without limit.

## 1.5.8

- **Fixes the window not dragging after you clip something.** The "Clip captured" pop-up changed some shared Windows settings that the window dragging relies on. It now keeps its own, so dragging keeps working.
- **More minimal pop-up.** A small dark card with the rewind mark, "Clip captured" and the replay length.

## 1.5.7

- **New look for the "Clip captured" pop-up.** A slim capsule with a rewind icon inside a ring that counts down, the title, and the game. Cleaner and smaller than before.

## 1.5.6

- **"Clip captured" pop-up.** When a clip is saved, a card slides in at the top left of the screen you're recording, with the game name and how much was saved, then fades away. It doesn't take focus, you can click straight through it, and it is kept out of your recordings. Turn it off or preview it in Settings.

## 1.5.5

- **Fixes Rewind getting stuck on slow "compatibility capture".** The fast screen capture can say no for a moment, for example right after an update restart. Rewind used to give up after two tries and then remember compatibility capture forever. It now waits and retries longer, only uses compatibility capture as a temporary fallback, and tries the fast capture again whenever a game starts or stops.
- PCs that were locked into compatibility capture by this are put back on Automatic.

## 1.5.4

- **Fixes clips with hours of sound and a broken timeline.** If the PC went to sleep (or Rewind was frozen for a while), the sound pipe could write the whole gap into the buffer, so the next clip came out hundreds of MB with a 140 minute timeline and a black strip. Rewind now skips that gap and keeps recording in real time.
- **No damaged clip is ever kept.** Every saved clip, long recording, cut and edit export is checked before it appears in your library: it has to open, have a picture, and its sound has to match its picture. A clip that fails is repaired if possible and otherwise thrown away, never saved half-broken.
- **Old damaged clips repair themselves.** When Rewind starts it fixes clips whose sound runs past the picture and clears out half-written files.

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
