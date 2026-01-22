# TikTok Live Recorder

A simple desktop application to record TikTok live streams to MP4.

![Python](https://img.shields.io/badge/python-3.8+-blue)
![Platform](https://img.shields.io/badge/platform-Windows-blue)
![License](https://img.shields.io/badge/license-MIT-green)

---

## About

TikTok Live Recorder is a **GUI (Graphical User Interface) application** that makes recording TikTok live streams easy for everyone. No command line or technical knowledge required — just enter a username and click record!

### Why Use This?

- 🖥️ **User-Friendly GUI** — Beautiful interface
- 📊 **Real-Time Stats** — See recording duration and file size live
- 👁️ **Live Preview** — Watch the stream while recording
- 🎨 **Modern Design** — Dark and Light theme options
- 📱 **Telegram Alerts** — Get notified when your favorite creators go live
- 📋 **Watchlist** — Monitor multiple users at once

---

## Screenshots

<img width="654" height="535" alt="tlr" src="https://github.com/user-attachments/assets/68cfec12-2bd7-447d-b238-2999bd39c31f" />

## Requirements

Before running the app, make sure you have:

| Requirement | Description | How to Get |
|-------------|-------------|------------|
| **Windows** | Windows 10 or 11 | - |
| **Python 3.8+** | Programming language runtime | [Download Python](https://www.python.org/downloads/) |
| **FFmpeg** | Video processing tool | See installation below |

### Python Packages (Auto-Installed)

These will be installed automatically when you first run the app:
- `yt-dlp` — Stream extraction
- `customtkinter` — Modern GUI framework
- `pillow` — Image processing
- `requests` — HTTP requests
- `pystray` — System tray support

---

## Installation

### Step 1: Install Python

1. Download Python from [python.org](https://www.python.org/downloads/)
2. Run the installer
3. ⚠️ **IMPORTANT:** Check the box **"Add Python to PATH"** before clicking Install

### Step 2: Install FFmpeg

**Option A: Using winget (Recommended)**
```
winget install ffmpeg
```

**Option B: Using Chocolatey**
```
choco install ffmpeg
```

**Option C: Manual Installation**
1. Download FFmpeg from [ffmpeg.org](https://ffmpeg.org/download.html) or [gyan.dev](https://www.gyan.dev/ffmpeg/builds/)
2. Extract to `C:\ffmpeg`
3. Add `C:\ffmpeg\bin` to your System PATH:
   - Search "Environment Variables" in Windows
   - Click "Environment Variables"
   - Under "System Variables", find "Path" and click Edit
   - Click "New" and add `C:\ffmpeg\bin`
   - Click OK

**Verify FFmpeg Installation:**
```
ffmpeg -version
```

### Step 3: Download & Run

1. Download this repository (Code → Download ZIP)
2. Extract the ZIP file
3. Double-click `tiktok_recorder.py` or run:
```
python tiktok_recorder.py
```

> 💡 On first run, Python packages will be installed automatically. This may take a minute.

---

## How to Use

### Basic Recording

1. **Open the app** — Double-click `tiktok_recorder.py`
2. **Enter username** — Type TikTok username (without @)
3. **Click "Check"** — App will check if user is live
4. **Click "Start Recording"** — Recording begins
5. **Click "Stop Recording"** — Recording stops and saves
6. **Find your video** — Saved in `recordings/` folder

### Features Guide

| Feature | Location | Description |
|---------|----------|-------------|
| **Quality Selection** | Home page, left side | Choose Best/High/Medium/Low quality |
| **Live Preview** | Home page, left side | Click "Preview" to watch while recording |
| **Watchlist** | Following page | Add multiple users to monitor |
| **Recording History** | History page | View and play past recordings |
| **Theme** | Settings page | Switch between Dark/Light mode |
| **Telegram Alerts** | Settings page | Get notified when users go live |
| **Output Folder** | Settings page | Change where videos are saved |

---

## Cookies (For Restricted Streams)

Some TikTok streams require login to access. If you see "Need cookies" error:

1. Install browser extension: **"Get cookies.txt LOCALLY"**
   - [Chrome Extension](https://chrome.google.com/webstore/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)
   - [Firefox Extension](https://addons.mozilla.org/en-US/firefox/addon/cookies-txt/)

2. Go to [tiktok.com](https://www.tiktok.com) and **login to your account**

3. Click the extension icon → **Export** → Save as `cookies.txt`

4. In the app: **Settings** → **Cookies File** → Select your `cookies.txt`

---

## Troubleshooting

| Problem | Cause | Solution |
|---------|-------|----------|
| "FFmpeg not found" | FFmpeg not installed or not in PATH | Install FFmpeg and restart the app |
| "User is not live" | User is offline | Check if user is actually live on TikTok |
| "Need cookies" | Stream requires authentication | Export and load cookies (see above) |
| Video won't play | Recording was force-closed | Always use "Stop Recording" button |
| App won't start | Missing Python or dependencies | Reinstall Python with "Add to PATH" checked |
| Recording stops immediately | Stream URL expired | Click "Check" again before recording |

---

## FAQ

**Q: Is this free?**
> Yes, completely free and open source.

**Q: Is this safe?**
> Yes, the code is open source and you can review it yourself.

**Q: Can I record multiple streams at once?**
> Yes, use the Watchlist feature on the Following page.

**Q: Where are my recordings saved?**
> In the `recordings/` folder. You can change this in Settings.

**Q: Why is the quality low?**
> Quality depends on the streamer's broadcast settings. Try selecting "Best" quality.

**Q: Does this work on Mac/Linux?**
> Currently only tested and supported on Windows.

---

## License

MIT License — Feel free to use and modify.