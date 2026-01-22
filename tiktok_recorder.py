#!/usr/bin/env python3
"""
TikTok Live Recorder
====================
Record TikTok live streams easily with a beautiful, modern interface.

Features:
- Record TikTok live streams to MP4
- Quality selection (Best/High/Medium/Low)
- Real-time duration and file size display
- Live preview while recording
- Dark/Light theme support
- Telegram notifications
- Recording history
- Watchlist for monitoring multiple users

GitHub: https://github.com/adenoviardian/tiktok-live-recorder
Author: adenoviardian
License: MIT
"""

import os
import sys
import json
import time
import re
import threading
import subprocess
import queue
import tempfile
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field, asdict
from io import BytesIO
import shutil

# ============================================================================
# DEPENDENCY INSTALLER
# ============================================================================

def install_packages():
    packages = {
        "yt-dlp": "yt_dlp",
        "customtkinter": "customtkinter", 
        "pillow": "PIL",
        "requests": "requests",
        "pystray": "pystray",
    }
    
    for pkg_name, import_name in packages.items():
        try:
            __import__(import_name)
        except ImportError:
            print(f"Installing {pkg_name}...")
            try:
                # Try with --break-system-packages first (for externally managed environments)
                subprocess.check_call([
                    sys.executable, "-m", "pip", "install", pkg_name,
                    "--break-system-packages", "-q"
                ], stderr=subprocess.DEVNULL)
            except subprocess.CalledProcessError:
                # Fallback without the flag
                subprocess.check_call([
                    sys.executable, "-m", "pip", "install", pkg_name, "-q"
                ])

install_packages()

import customtkinter as ctk
from PIL import Image, ImageDraw
import yt_dlp
import requests

# System tray
try:
    import pystray
    from pystray import MenuItem as TrayItem
    TRAY_AVAILABLE = True
except ImportError:
    TRAY_AVAILABLE = False

# Sound (Windows)
try:
    import winsound
    SOUND_AVAILABLE = True
except ImportError:
    SOUND_AVAILABLE = False


# ============================================================================
# THEME COLORS
# ============================================================================

class ThemeColors:
    """Color schemes for light and dark themes"""
    
    DARK = {
        "bg_primary": "#000000",
        "bg_secondary": "#0f0f0f",
        "bg_tertiary": "#1a1a1a",
        "bg_elevated": "#252525",
        "text_primary": "#FFFFFF",
        "text_secondary": "#ABABAB",
        "text_muted": "#6a6a6a",
        "accent": "#FE2C55",
        "accent_hover": "#FF4466",
        "cyan": "#25F4EE",
        "success": "#00D26A",
        "border": "#2a2a2a",
    }
    
    LIGHT = {
        "bg_primary": "#FFFFFF",
        "bg_secondary": "#F5F5F5",
        "bg_tertiary": "#EBEBEB",
        "bg_elevated": "#E0E0E0",
        "text_primary": "#000000",
        "text_secondary": "#444444",
        "text_muted": "#666666",  # Darker for better visibility
        "accent": "#FE2C55",
        "accent_hover": "#E02850",
        "cyan": "#00C4CC",
        "success": "#00A855",
        "border": "#D0D0D0",
    }


class Theme:
    """Dynamic theme manager"""
    current = "dark"
    colors = ThemeColors.DARK
    
    @classmethod
    def set_theme(cls, theme: str):
        cls.current = theme
        cls.colors = ThemeColors.DARK if theme == "dark" else ThemeColors.LIGHT
    
    @classmethod
    def get(cls, key: str) -> str:
        return cls.colors.get(key, "#000000")


# ============================================================================
# CONFIGURATION
# ============================================================================

@dataclass
class TelegramConfig:
    enabled: bool = False
    bot_token: str = ""
    chat_id: str = ""
    notify_on_live: bool = True
    notify_on_record_start: bool = True
    notify_on_record_end: bool = True


@dataclass
class SoundConfig:
    enabled: bool = True
    on_live: bool = True
    on_record_start: bool = True
    on_record_end: bool = True


@dataclass
class AppConfig:
    output_dir: str = "./recordings"
    cookies_file: str = ""
    check_interval: int = 60
    quality: str = "best"  # best, high, medium, low
    filename_pattern: str = "{username}_{datetime}"
    theme: str = "dark"
    minimize_to_tray: bool = False
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    sound: SoundConfig = field(default_factory=SoundConfig)
    
    # Statistics
    total_recordings: int = 0
    total_size_bytes: int = 0
    total_duration_seconds: int = 0
    
    def to_dict(self) -> dict:
        return {
            "output_dir": self.output_dir,
            "cookies_file": self.cookies_file,
            "check_interval": self.check_interval,
            "quality": self.quality,
            "filename_pattern": self.filename_pattern,
            "theme": self.theme,
            "minimize_to_tray": self.minimize_to_tray,
            "telegram": asdict(self.telegram),
            "sound": asdict(self.sound),
            "total_recordings": self.total_recordings,
            "total_size_bytes": self.total_size_bytes,
            "total_duration_seconds": self.total_duration_seconds,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'AppConfig':
        config = cls()
        for key, value in data.items():
            if key == "telegram":
                config.telegram = TelegramConfig(**value)
            elif key == "sound":
                config.sound = SoundConfig(**value)
            elif hasattr(config, key):
                setattr(config, key, value)
        return config
    
    def save(self, filepath: str = "config.json"):
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
        except Exception:
            pass
    
    @classmethod
    def load(cls, filepath: str = "config.json") -> 'AppConfig':
        try:
            if os.path.exists(filepath):
                with open(filepath, 'r', encoding='utf-8') as f:
                    return cls.from_dict(json.load(f))
        except Exception:
            pass
        return cls()


# ============================================================================
# SOUND MANAGER
# ============================================================================

class SoundManager:
    """Play notification sounds"""
    
    @staticmethod
    def play_notification():
        if not SOUND_AVAILABLE:
            return
        try:
            # Windows notification sound
            winsound.MessageBeep(winsound.MB_OK)
        except Exception:
            pass
    
    @staticmethod
    def play_success():
        if not SOUND_AVAILABLE:
            return
        try:
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
        except Exception:
            pass
    
    @staticmethod
    def play_alert():
        if not SOUND_AVAILABLE:
            return
        try:
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        except Exception:
            pass


# ============================================================================
# TELEGRAM NOTIFIER
# ============================================================================

class TelegramNotifier:
    def __init__(self, config: TelegramConfig):
        self.config = config
    
    def update_config(self, config: TelegramConfig):
        self.config = config
    
    def _send(self, message: str):
        if not self.config.enabled or not self.config.bot_token or not self.config.chat_id:
            return
        
        def send_async():
            try:
                url = f"https://api.telegram.org/bot{self.config.bot_token}/sendMessage"
                data = {"chat_id": self.config.chat_id, "text": message, "parse_mode": "HTML"}
                requests.post(url, data=data, timeout=10)
            except Exception:
                pass
        
        threading.Thread(target=send_async, daemon=True).start()
    
    def notify_live(self, username: str, title: str, viewers: int):
        if self.config.notify_on_live:
            self._send(f"🔴 <b>@{username}</b> is LIVE!\n\n📝 {title}\n👥 {viewers:,}")
    
    def notify_record_start(self, username: str):
        if self.config.notify_on_record_start:
            self._send(f"⏺️ Recording: <b>@{username}</b>")
    
    def notify_record_end(self, username: str, duration: str, file_size: str):
        if self.config.notify_on_record_end:
            self._send(f"✅ Finished: <b>@{username}</b>\n⏱️ {duration}\n📁 {file_size}")


# ============================================================================
# THUMBNAIL GENERATOR
# ============================================================================

class ThumbnailGenerator:
    """Generate thumbnails from video files"""
    
    CACHE_DIR = ".thumbnails"
    
    @classmethod
    def ensure_cache_dir(cls):
        os.makedirs(cls.CACHE_DIR, exist_ok=True)
    
    @classmethod
    def get_cache_path(cls, video_path: str) -> str:
        cls.ensure_cache_dir()
        # Create hash of video path for unique filename
        hash_name = hashlib.md5(video_path.encode()).hexdigest()
        return os.path.join(cls.CACHE_DIR, f"{hash_name}.jpg")
    
    @classmethod
    def generate(cls, video_path: str, size: tuple = (120, 160)) -> Optional[Image.Image]:
        """Generate thumbnail from video using FFmpeg"""
        if not os.path.exists(video_path):
            return None
        
        cache_path = cls.get_cache_path(video_path)
        
        # Check cache
        if os.path.exists(cache_path):
            try:
                return Image.open(cache_path)
            except:
                pass
        
        # Find FFmpeg
        ffmpeg = cls._find_ffmpeg()
        if not ffmpeg:
            return cls._create_placeholder(size)
        
        try:
            cmd = [
                ffmpeg, "-y", "-loglevel", "error",
                "-i", video_path,
                "-ss", "00:00:05",  # 5 seconds in
                "-vframes", "1",
                "-vf", f"scale={size[0]}:{size[1]}:force_original_aspect_ratio=increase,crop={size[0]}:{size[1]}",
                "-q:v", "5",
                cache_path
            ]
            
            kwargs = {"capture_output": True, "timeout": 15}
            if sys.platform == "win32":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            
            subprocess.run(cmd, **kwargs)
            
            if os.path.exists(cache_path):
                return Image.open(cache_path)
        except:
            pass
        
        return cls._create_placeholder(size)
    
    @classmethod
    def _find_ffmpeg(cls) -> Optional[str]:
        try:
            result = subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5,
                                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
            if result.returncode == 0:
                return "ffmpeg"
        except:
            pass
        return None
    
    @classmethod
    def _create_placeholder(cls, size: tuple) -> Image.Image:
        """Create placeholder thumbnail"""
        img = Image.new('RGB', size, '#1a1a1a')
        draw = ImageDraw.Draw(img)
        # Draw play icon
        cx, cy = size[0] // 2, size[1] // 2
        draw.polygon([(cx - 15, cy - 20), (cx - 15, cy + 20), (cx + 20, cy)], fill='#444444')
        return img


# ============================================================================
# LIVE PREVIEW
# ============================================================================

class LivePreview:
    def __init__(self):
        self.is_running = False
        self._stop_event = threading.Event()
        self._temp_dir: Optional[str] = None
    
    def start(self, stream_url: str, callback: Callable[[Image.Image], None], 
              width: int = 180, height: int = 320) -> bool:
        if self.is_running or not stream_url:
            return False
        
        ffmpeg = self._find_ffmpeg()
        if not ffmpeg:
            return False
        
        self._stop_event.clear()
        self.is_running = True
        self._temp_dir = tempfile.mkdtemp(prefix="preview_")
        
        def capture():
            count = 0
            fails = 0
            
            while not self._stop_event.is_set() and fails < 5:
                path = os.path.join(self._temp_dir, f"f{count % 2}.jpg")
                
                try:
                    cmd = [ffmpeg, "-y", "-loglevel", "error", "-i", stream_url,
                           "-vframes", "1", "-q:v", "5",
                           "-vf", f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}",
                           path]
                    
                    kwargs = {"capture_output": True, "timeout": 10}
                    if sys.platform == "win32":
                        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
                    
                    subprocess.run(cmd, **kwargs)
                    
                    if os.path.exists(path) and os.path.getsize(path) > 1000:
                        img = Image.open(path)
                        img.load()
                        callback(img.copy())
                        fails = 0
                        count += 1
                    else:
                        fails += 1
                except:
                    fails += 1
                
                for _ in range(4):
                    if self._stop_event.is_set():
                        break
                    time.sleep(0.1)
            
            self._cleanup()
            self.is_running = False
        
        threading.Thread(target=capture, daemon=True).start()
        return True
    
    def _find_ffmpeg(self) -> Optional[str]:
        try:
            subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5,
                          creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
            return "ffmpeg"
        except:
            return None
    
    def _cleanup(self):
        if self._temp_dir:
            shutil.rmtree(self._temp_dir, ignore_errors=True)
            self._temp_dir = None
    
    def stop(self):
        self._stop_event.set()
        self.is_running = False


# ============================================================================
# TIKTOK API
# ============================================================================

class TikTokAPI:
    QUALITY_MAP = {
        "best": ['origin', 'uhd', 'hd', 'sd'],
        "high": ['hd', 'sd'],
        "medium": ['sd'],
        "low": ['sd', 'ld'],
    }
    
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }
    
    def __init__(self, cookies_file: str = ""):
        self.cookies_file = cookies_file
    
    def set_cookies_file(self, path: str):
        self.cookies_file = path if path and os.path.exists(path) else ""
    
    def get_live_info(self, username: str, quality: str = "best") -> Dict[str, Any]:
        username = username.strip().lstrip("@").lower()
        
        result = {
            "success": False, "is_live": False, "username": username,
            "title": "", "viewer_count": 0, "thumbnail_url": None,
            "stream_url": None, "error": None,
        }
        
        if not username:
            result["error"] = "Username tidak boleh kosong"
            return result
        
        url = f"https://www.tiktok.com/@{username}/live"
        
        # Try yt-dlp first
        yt_result = self._try_ytdlp(url, username, quality)
        if yt_result["success"]:
            yt_result["username"] = username  # Ensure username is set
            return yt_result
        
        # If yt-dlp fails, try web scraping as fallback
        web_result = self._try_web_scrape(username, quality)
        if web_result["success"]:
            web_result["username"] = username  # Ensure username is set
            return web_result
        
        # Return error result with username preserved
        if yt_result.get("error"):
            result["error"] = yt_result["error"]
        elif web_result.get("error"):
            result["error"] = web_result["error"]
        else:
            result["error"] = "Tidak bisa mendapatkan info live"
        
        return result
    
    def _try_ytdlp(self, url: str, username: str, quality: str) -> Dict[str, Any]:
        """Try to get live info using yt-dlp"""
        result = {
            "success": False, "is_live": False, "username": username,
            "title": "", "viewer_count": 0, "thumbnail_url": None,
            "stream_url": None, "error": None,
        }
        
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
            'extract_flat': False,
            'ignoreerrors': False,
        }
        
        if self.cookies_file and os.path.exists(self.cookies_file):
            ydl_opts['cookiefile'] = self.cookies_file
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                if info:
                    result["is_live"] = True
                    result["success"] = True
                    result["title"] = info.get("title", "TikTok Live")
                    result["viewer_count"] = info.get("concurrent_view_count", 0) or 0
                    result["thumbnail_url"] = info.get("thumbnail", "")
                    
                    formats = info.get("formats", [])
                    preferred = self.QUALITY_MAP.get(quality, ['origin'])
                    
                    best_url = None
                    for pref in preferred:
                        for fmt in formats:
                            fmt_id = fmt.get("format_id", "").lower()
                            if pref.lower() in fmt_id and fmt.get("url"):
                                best_url = fmt["url"]
                                break
                        if best_url:
                            break
                    
                    if not best_url and formats:
                        # Get highest quality available
                        for fmt in formats:
                            if fmt.get("url"):
                                best_url = fmt["url"]
                                break
                    
                    result["stream_url"] = best_url
                
        except yt_dlp.utils.DownloadError as e:
            msg = str(e).lower()
            if "not currently live" in msg or "offline" in msg:
                result["error"] = "User tidak sedang live"
            elif "captcha" in msg or "verify" in msg:
                result["error"] = "Butuh cookies! Export cookies dari browser."
            elif "private" in msg:
                result["error"] = "Live bersifat private"
            elif "not exist" in msg or "404" in msg:
                result["error"] = "User tidak ditemukan"
            else:
                result["error"] = f"yt-dlp: {str(e)[:60]}"
        except Exception as e:
            result["error"] = f"Error: {str(e)[:60]}"
        
        return result
    
    def _try_web_scrape(self, username: str, quality: str) -> Dict[str, Any]:
        """Fallback: Try to get live info via web scraping"""
        result = {
            "success": False, "is_live": False, "username": username,
            "title": "", "viewer_count": 0, "thumbnail_url": None,
            "stream_url": None, "error": None,
        }
        
        url = f"https://www.tiktok.com/@{username}/live"
        
        try:
            # Load cookies if available
            session = requests.Session()
            session.headers.update(self.HEADERS)
            
            if self.cookies_file and os.path.exists(self.cookies_file):
                try:
                    import http.cookiejar
                    cj = http.cookiejar.MozillaCookieJar(self.cookies_file)
                    cj.load(ignore_discard=True, ignore_expires=True)
                    session.cookies.update(cj)
                except:
                    pass
            
            resp = session.get(url, timeout=15)
            html = resp.text
            
            # Check for signs of live stream
            if "captcha" in html.lower() or "verify" in html.lower():
                result["error"] = "Butuh cookies! Export cookies dari browser."
                return result
            
            # Try to find SIGI_STATE data
            sigi_match = re.search(r'<script id="SIGI_STATE"[^>]*>(.+?)</script>', html, re.DOTALL)
            if sigi_match:
                try:
                    data = json.loads(sigi_match.group(1))
                    live_room = data.get("LiveRoom", {})
                    live_room_info = live_room.get("liveRoomUserInfo", {})
                    
                    if live_room_info:
                        user = live_room_info.get("user", {})
                        room = live_room_info.get("liveRoom", {})
                        
                        if room:
                            result["is_live"] = True
                            result["success"] = True
                            result["title"] = room.get("title", "") or user.get("nickname", "TikTok Live")
                            result["viewer_count"] = room.get("liveRoomStats", {}).get("userCount", 0)
                            result["thumbnail_url"] = room.get("coverUrl", "")
                            
                            # Extract stream URL
                            stream_data = room.get("streamData", {})
                            stream_url = self._extract_stream_url(stream_data, quality)
                            result["stream_url"] = stream_url
                            
                            return result
                except:
                    pass
            
            # Try __NEXT_DATA__
            next_match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.+?)</script>', html, re.DOTALL)
            if next_match:
                try:
                    data = json.loads(next_match.group(1))
                    props = data.get("props", {}).get("pageProps", {})
                    live_room = props.get("liveRoom", {})
                    
                    if live_room:
                        result["is_live"] = True
                        result["success"] = True
                        result["title"] = live_room.get("title", "TikTok Live")
                        result["viewer_count"] = live_room.get("liveRoomStats", {}).get("userCount", 0)
                        result["thumbnail_url"] = live_room.get("coverUrl", "")
                        
                        stream_data = live_room.get("streamData", {})
                        stream_url = self._extract_stream_url(stream_data, quality)
                        result["stream_url"] = stream_url
                        
                        return result
                except:
                    pass
            
            # Check if page indicates user is not live
            if "isn't hosting a LIVE" in html or "currently not hosting" in html.lower():
                result["error"] = "User tidak sedang live"
            
        except requests.exceptions.RequestException as e:
            result["error"] = f"Network error: {str(e)[:40]}"
        except Exception as e:
            result["error"] = f"Scrape error: {str(e)[:40]}"
        
        return result
    
    def _extract_stream_url(self, stream_data: Dict, quality: str) -> Optional[str]:
        """Extract stream URL from stream data"""
        if not stream_data:
            return None
        
        urls = {}
        
        # Try pull_data format
        pull_data = stream_data.get("pull_data", {})
        if pull_data:
            # Try stream_data inside pull_data
            if "stream_data" in pull_data:
                try:
                    sd = json.loads(pull_data["stream_data"])
                    for key, val in sd.get("data", {}).items():
                        main = val.get("main", {})
                        if "flv" in main:
                            urls[key] = main["flv"]
                        elif "hls" in main:
                            urls[key + "_hls"] = main["hls"]
                except:
                    pass
            
            # Try options.qualities
            options = pull_data.get("options", {})
            for q in options.get("qualities", []):
                sdk_key = q.get("sdk_key", "")
                if q.get("url"):
                    urls[sdk_key] = q["url"]
        
        # Try flv_pull_url
        flv_urls = stream_data.get("flv_pull_url", {})
        if isinstance(flv_urls, dict):
            urls.update(flv_urls)
        elif isinstance(flv_urls, str):
            urls["flv"] = flv_urls
        
        # Try hls_pull_url
        hls_url = stream_data.get("hls_pull_url", "")
        if hls_url:
            urls["hls"] = hls_url
        
        if not urls:
            return None
        
        # Select based on quality preference
        preferred = self.QUALITY_MAP.get(quality, ['origin'])
        for pref in preferred:
            for key, url in urls.items():
                if pref.lower() in key.lower() and url:
                    return url
        
        # Return first available
        return list(urls.values())[0] if urls else None
    
    def download_thumbnail(self, url: str) -> Optional[Image.Image]:
        if not url:
            return None
        try:
            resp = requests.get(url, headers=self.HEADERS, timeout=10)
            return Image.open(BytesIO(resp.content))
        except:
            return None


# ============================================================================
# RECORDER
# ============================================================================

class Recorder:
    def __init__(self, config: AppConfig, notifier: TelegramNotifier):
        self.config = config
        self.notifier = notifier
        
        self.process: Optional[subprocess.Popen] = None
        self.is_recording = False
        self.is_stopping = False
        self.output_file: Optional[str] = None
        self.actual_recording_file: Optional[str] = None
        self._raw_recording_file: Optional[str] = None
        self.username: str = ""
        self.title: str = ""
        self.live_url: str = ""
        self.stream_url: str = ""
        
        self._first_write_time: Optional[float] = None
        self._stop_event = threading.Event()
        self._file_check_count = 0
        self._recording_method: str = ""
        self._last_error: Optional[str] = None
        
        self.on_complete: Optional[Callable] = None
        
        Path(config.output_dir).mkdir(parents=True, exist_ok=True)
    
    def _generate_filename(self) -> str:
        now = datetime.now()
        
        # Replace pattern placeholders
        safe_title = re.sub(r'[<>:"/\\|?*]', '', self.title)[:30].strip() or "live"
        
        filename = self.config.filename_pattern
        filename = filename.replace("{username}", self.username)
        filename = filename.replace("{date}", now.strftime("%Y%m%d"))
        filename = filename.replace("{time}", now.strftime("%H%M%S"))
        filename = filename.replace("{datetime}", now.strftime("%Y%m%d_%H%M%S"))
        filename = filename.replace("{title}", safe_title)
        
        # Clean filename
        filename = re.sub(r'[<>:"/\\|?*]', '', filename)
        
        # ALWAYS add milliseconds to ensure unique filename
        ms = int(now.microsecond / 1000)
        filename = f"{filename}_{ms:03d}"
        
        # Generate unique filename - avoid overwriting!
        base_path = os.path.join(self.config.output_dir, f"{filename}.mp4")
        
        if not os.path.exists(base_path):
            return base_path
        
        # File exists - add counter
        counter = 1
        while True:
            new_path = os.path.join(self.config.output_dir, f"{filename}_{counter:03d}.mp4")
            if not os.path.exists(new_path):
                return new_path
            counter += 1
            if counter > 999:  # Safety limit
                ts = int(time.time() * 1000)
                return os.path.join(self.config.output_dir, f"{filename}_{ts}.mp4")
    
    def start(self, username: str, stream_url: str, title: str, live_url: str) -> bool:
        if self.is_recording:
            return False
        
        self.username = username
        self.title = title
        self.live_url = live_url
        self.stream_url = stream_url
        self.is_stopping = False
        self._stop_event.clear()
        self._first_write_time = time.time()
        self._file_check_count = 0
        self.actual_recording_file = None
        self._raw_recording_file = None
        self._last_error = None
        
        self.output_file = self._generate_filename()
        
        # Try FFmpeg first if we have stream URL (more reliable for direct stream)
        if stream_url:
            success = self._start_ffmpeg(stream_url)
            if success:
                return True
        
        # Fallback to yt-dlp with live URL
        success = self._start_ytdlp(live_url)
        if success:
            return True
        
        self.is_recording = False
        return False
    
    def _start_ffmpeg(self, stream_url: str) -> bool:
        """Start recording using FFmpeg directly - record to FLV first (more reliable)"""
        ffmpeg = self._find_ffmpeg()
        if not ffmpeg:
            self._last_error = "FFmpeg not found"
            return False
        
        # Record to FLV format (more tolerant for live streams)
        # FLV handles incomplete writes better than MP4
        base_name = os.path.splitext(self.output_file)[0]
        self._raw_recording_file = base_name + ".flv"
        
        cmd = [
            ffmpeg,
            "-y",
            "-loglevel", "warning",
            "-reconnect", "1",
            "-reconnect_streamed", "1",
            "-reconnect_delay_max", "5",
            "-i", stream_url,
            "-c", "copy",
            "-f", "flv",
            self._raw_recording_file
        ]
        
        try:
            kwargs = {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE, "stdin": subprocess.PIPE}
            if sys.platform == "win32":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                kwargs["start_new_session"] = True
            
            self.process = subprocess.Popen(cmd, **kwargs)
            
            # Wait a moment to see if process starts successfully
            time.sleep(1.5)
            
            if self.process.poll() is not None:
                # Process already exited - failed
                stderr = self.process.stderr.read().decode('utf-8', errors='ignore')
                self._last_error = f"FFmpeg failed: {stderr[:100]}"
                return False
            
            self.is_recording = True
            self._recording_method = "ffmpeg"
            self.actual_recording_file = self._raw_recording_file
            
            self.notifier.notify_record_start(self.username)
            
            if self.config.sound.enabled and self.config.sound.on_record_start:
                SoundManager.play_notification()
            
            threading.Thread(target=self._monitor, daemon=True).start()
            return True
            
        except Exception as e:
            self._last_error = f"FFmpeg error: {str(e)}"
            return False
    
    def _start_ytdlp(self, live_url: str) -> bool:
        """Start recording using yt-dlp"""
        # Use FLV format for better live stream handling
        base_name = os.path.splitext(self.output_file)[0]
        self._raw_recording_file = base_name + ".flv"
        
        cmd = [
            sys.executable, "-m", "yt_dlp",
            "--no-part",
            "--no-mtime",
            "--no-warnings",
            "-o", self._raw_recording_file,
        ]
        
        # Add cookies if available
        if self.config.cookies_file and os.path.exists(self.config.cookies_file):
            cmd.extend(["--cookies", self.config.cookies_file])
        
        cmd.append(live_url)
        
        try:
            kwargs = {"stdout": subprocess.PIPE, "stderr": subprocess.STDOUT, "stdin": subprocess.PIPE}
            if sys.platform == "win32":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                kwargs["start_new_session"] = True
            
            self.process = subprocess.Popen(cmd, **kwargs)
            
            # Wait a moment to see if process starts successfully
            time.sleep(2)
            
            if self.process.poll() is not None:
                # Process already exited - failed
                stdout = self.process.stdout.read().decode('utf-8', errors='ignore')
                self._last_error = f"yt-dlp failed: {stdout[:100]}"
                return False
            
            self.is_recording = True
            self._recording_method = "yt-dlp"
            self.actual_recording_file = self._raw_recording_file
            
            self.notifier.notify_record_start(self.username)
            
            if self.config.sound.enabled and self.config.sound.on_record_start:
                SoundManager.play_notification()
            
            threading.Thread(target=self._monitor, daemon=True).start()
            return True
            
        except Exception as e:
            self._last_error = f"yt-dlp error: {str(e)}"
            return False
    
    def get_last_error(self) -> Optional[str]:
        """Get the last error message"""
        return getattr(self, '_last_error', None)
    
    def _monitor(self):
        """Monitor recording process and file growth"""
        last_size = 0
        stuck_count = 0
        
        while not self._stop_event.is_set() and self.is_recording:
            # Find and track actual file
            actual_file = self._find_actual_file()
            if actual_file:
                self.actual_recording_file = actual_file
                try:
                    current_size = os.path.getsize(actual_file)
                    
                    # Check if file is growing
                    if current_size > last_size:
                        stuck_count = 0
                        last_size = current_size
                    else:
                        stuck_count += 1
                    
                    # If file hasn't grown for 30 seconds, something might be wrong
                    # But don't stop - let user decide
                except:
                    pass
            
            # Check if process ended
            if self.process and self.process.poll() is not None:
                self._complete()
                break
            
            time.sleep(0.5)
    
    def _find_actual_file(self) -> Optional[str]:
        """Find the actual file being written"""
        # Check raw recording file first (FLV)
        if self._raw_recording_file and os.path.exists(self._raw_recording_file):
            return self._raw_recording_file
        
        # Return cached if we found it before
        if self.actual_recording_file and os.path.exists(self.actual_recording_file):
            return self.actual_recording_file
        
        if not self.output_file:
            return None
        
        base = os.path.splitext(self.output_file)[0]
        dir_path = os.path.dirname(self.output_file)
        base_name = os.path.basename(base)
        
        # Check the expected file first
        if os.path.exists(self.output_file):
            return self.output_file
        
        # Check common extensions
        for ext in ['.flv', '.mp4', '.ts', '.mkv', '.webm']:
            alt_file = base + ext
            if os.path.exists(alt_file):
                return alt_file
        
        # Search directory for any file starting with our base name
        try:
            for f in os.listdir(dir_path):
                if f.startswith(base_name) and not f.endswith('.txt'):
                    return os.path.join(dir_path, f)
        except:
            pass
        
        return None
    
    def _complete(self):
        """Called when recording ends naturally (stream ends)"""
        if not self.is_recording:
            return
        self.is_recording = False
        
        # Find actual recorded file
        actual_file = self._find_actual_file()
        if actual_file:
            self.output_file = actual_file
        
        # Convert to proper MP4
        self._convert_to_mp4()
        
        self._finalize_recording()
    
    def _complete_after_stop(self):
        """Called after manual stop"""
        # Find actual recorded file
        actual_file = self._find_actual_file()
        if actual_file:
            self.output_file = actual_file
        
        # Convert to proper MP4
        self._convert_to_mp4()
        
        self._finalize_recording()
    
    def _find_ffmpeg(self) -> Optional[str]:
        """Find FFmpeg executable"""
        try:
            kwargs = {"capture_output": True, "timeout": 5}
            if sys.platform == "win32":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            subprocess.run(["ffmpeg", "-version"], **kwargs)
            return "ffmpeg"
        except:
            return None
    
    def _convert_to_mp4(self):
        """Convert recorded FLV file to proper MP4 for universal playback"""
        # Find the actual recorded file (could be FLV or the original output path)
        input_file = getattr(self, '_raw_recording_file', None)
        if not input_file or not os.path.exists(input_file):
            input_file = self.actual_recording_file
        if not input_file or not os.path.exists(input_file):
            input_file = self.output_file
        if not input_file or not os.path.exists(input_file):
            return
        
        # Skip if file is too small (< 50KB)
        try:
            file_size = os.path.getsize(input_file)
            if file_size < 51200:
                return
        except:
            return
        
        ffmpeg = self._find_ffmpeg()
        if not ffmpeg:
            # No FFmpeg - just keep the raw file
            self.output_file = input_file
            return
        
        try:
            base_name = os.path.splitext(self.output_file)[0]
            mp4_output = base_name + ".mp4"
            
            # Don't overwrite if input is already the target
            if input_file == mp4_output:
                mp4_output = base_name + "_converted.mp4"
            
            # Track original FLV file for deletion
            original_flv = input_file if input_file.lower().endswith('.flv') else None
            
            # Method 1: Try simple remux (fastest, works if codec is compatible)
            cmd_remux = [
                ffmpeg, "-y", "-loglevel", "error",
                "-i", input_file,
                "-c", "copy",
                "-movflags", "+faststart",
                mp4_output
            ]
            
            kwargs = {"capture_output": True, "timeout": 1800}
            if sys.platform == "win32":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            
            result = subprocess.run(cmd_remux, **kwargs)
            
            # Check if output is valid
            if result.returncode == 0 and os.path.exists(mp4_output):
                output_size = os.path.getsize(mp4_output)
                if output_size > file_size * 0.5:  # Output should be at least 50% of input
                    # Success - DELETE ORIGINAL FLV and set output
                    self._cleanup_flv(original_flv, input_file)
                    self.output_file = mp4_output
                    return
            
            # Clean up failed attempt
            if os.path.exists(mp4_output):
                try:
                    os.remove(mp4_output)
                except:
                    pass
            
            # Method 2: Re-encode audio to AAC (if audio codec is incompatible)
            cmd_reencode = [
                ffmpeg, "-y", "-loglevel", "error",
                "-i", input_file,
                "-c:v", "copy",
                "-c:a", "aac", "-b:a", "128k",
                "-movflags", "+faststart",
                mp4_output
            ]
            
            result = subprocess.run(cmd_reencode, **kwargs)
            
            if result.returncode == 0 and os.path.exists(mp4_output):
                output_size = os.path.getsize(mp4_output)
                if output_size > file_size * 0.3:
                    # Success - DELETE ORIGINAL FLV
                    self._cleanup_flv(original_flv, input_file)
                    self.output_file = mp4_output
                    return
            
            # Clean up failed attempt
            if os.path.exists(mp4_output):
                try:
                    os.remove(mp4_output)
                except:
                    pass
            
            # Method 3: Full re-encode (slowest but most compatible)
            cmd_full = [
                ffmpeg, "-y", "-loglevel", "error",
                "-i", input_file,
                "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                "-c:a", "aac", "-b:a", "128k",
                "-movflags", "+faststart",
                mp4_output
            ]
            
            result = subprocess.run(cmd_full, **kwargs)
            
            if result.returncode == 0 and os.path.exists(mp4_output):
                output_size = os.path.getsize(mp4_output)
                if output_size > 10000:
                    # Success - DELETE ORIGINAL FLV
                    self._cleanup_flv(original_flv, input_file)
                    self.output_file = mp4_output
                    return
            
            # All methods failed - keep original file
            self.output_file = input_file
                        
        except Exception as e:
            # Keep original file
            if input_file and os.path.exists(input_file):
                self.output_file = input_file
    
    def _cleanup_flv(self, original_flv: Optional[str], input_file: str):
        """Delete original FLV file after successful MP4 conversion"""
        # Delete original FLV if it exists
        if original_flv and os.path.exists(original_flv):
            try:
                os.remove(original_flv)
            except:
                pass
        
        # Also delete input_file if it's different and is FLV
        if input_file and input_file != original_flv and os.path.exists(input_file):
            if input_file.lower().endswith('.flv'):
                try:
                    os.remove(input_file)
                except:
                    pass
    
    def _finalize_recording(self):
        """Finalize recording - save stats, notify"""
        duration = self.get_duration()
        file_size = self.get_file_size()
        
        # Update stats
        if self.output_file and os.path.exists(self.output_file):
            # Only count if file has actual content (> 10KB)
            actual_size = os.path.getsize(self.output_file)
            if actual_size > 10240:  # 10KB minimum
                self.config.total_recordings += 1
                self.config.total_size_bytes += actual_size
                if self._first_write_time:
                    self.config.total_duration_seconds += int(time.time() - self._first_write_time)
                self.config.save()
        
        self.notifier.notify_record_end(self.username, duration, file_size)
        
        if self.config.sound.enabled and self.config.sound.on_record_end:
            SoundManager.play_success()
        
        if self.on_complete:
            self.on_complete(self.username, duration, file_size, self.output_file)
    
    def stop(self):
        """Stop recording - use graceful shutdown to ensure file is valid"""
        if not self.is_recording or self.is_stopping:
            return
        
        self.is_stopping = True
        self._stop_event.set()
        
        if self.process:
            try:
                # First, try graceful shutdown (send 'q' to FFmpeg or SIGINT)
                # This allows FFmpeg to finalize the file properly
                if sys.platform == "win32":
                    # On Windows, send 'q' to FFmpeg stdin to quit gracefully
                    try:
                        if self.process.stdin:
                            self.process.stdin.write(b'q')
                            self.process.stdin.flush()
                    except:
                        pass
                    
                    # Wait for graceful exit
                    try:
                        self.process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        # Force kill if graceful shutdown failed
                        subprocess.run(
                            ["taskkill", "/F", "/T", "/PID", str(self.process.pid)],
                            capture_output=True,
                            timeout=10,
                            creationflags=subprocess.CREATE_NO_WINDOW
                        )
                else:
                    # On Unix, send SIGINT first (like Ctrl+C)
                    import signal
                    try:
                        os.killpg(os.getpgid(self.process.pid), signal.SIGINT)
                        # Wait for graceful exit
                        self.process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        # Force kill if needed
                        os.killpg(os.getpgid(self.process.pid), signal.SIGKILL)
                        self.process.wait(timeout=3)
                    except:
                        try:
                            self.process.kill()
                            self.process.wait(timeout=3)
                        except:
                            pass
                    
            except Exception as e:
                # Fallback: force kill
                try:
                    self.process.kill()
                    self.process.wait(timeout=3)
                except:
                    pass
            
            self.process = None
        
        # Mark as not recording
        self.is_recording = False
        self.is_stopping = False
        
        # Complete (convert to MP4, save stats, notify)
        self._complete_after_stop()
    
    def check_status(self) -> bool:
        return self.is_recording and not self.is_stopping
    
    def get_duration(self) -> str:
        if not self._first_write_time:
            return "00:00:00"
        elapsed = int(time.time() - self._first_write_time)
        h, r = divmod(elapsed, 3600)
        m, s = divmod(r, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"
    
    def get_file_size(self) -> str:
        try:
            # Use cached actual file first (more reliable during recording)
            file_to_check = self.actual_recording_file or self._find_actual_file()
            size = os.path.getsize(file_to_check) if file_to_check and os.path.exists(file_to_check) else 0
        except:
            size = 0
        
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        elif size < 1024 * 1024 * 1024:
            return f"{size / (1024 * 1024):.1f} MB"
        return f"{size / (1024 * 1024 * 1024):.2f} GB"


# ============================================================================
# MULTI-RECORDER
# ============================================================================

class MultiRecorder:
    def __init__(self, config: AppConfig, notifier: TelegramNotifier):
        self.config = config
        self.notifier = notifier
        self.recorders: Dict[str, Recorder] = {}
        self._lock = threading.Lock()
    
    def start(self, username: str, stream_url: str, title: str, live_url: str) -> bool:
        with self._lock:
            if username in self.recorders and self.recorders[username].is_recording:
                return False
            rec = Recorder(self.config, self.notifier)
            if rec.start(username, stream_url, title, live_url):
                self.recorders[username] = rec
                return True
            return False
    
    def is_recording(self, username: str) -> bool:
        with self._lock:
            return username in self.recorders and self.recorders[username].check_status()
    
    def get(self, username: str) -> Optional[Recorder]:
        with self._lock:
            return self.recorders.get(username)
    
    def get_all(self) -> List[str]:
        with self._lock:
            return [u for u, r in self.recorders.items() if r.check_status()]
    
    def stop_all(self):
        with self._lock:
            for r in self.recorders.values():
                r.stop()
            self.recorders.clear()


# ============================================================================
# HISTORY & WATCHLIST
# ============================================================================

class History:
    def __init__(self):
        self.file = "history.json"
        self.data = []
        self.load()
    
    def load(self):
        try:
            if os.path.exists(self.file):
                with open(self.file, 'r', encoding='utf-8') as f:
                    self.data = json.load(f)
        except Exception:
            self.data = []
    
    def save(self):
        try:
            with open(self.file, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, indent=2)
        except Exception:
            pass
    
    def add(self, username: str, title: str, duration: str, path: str, size: str):
        self.data.insert(0, {
            "username": username, "title": title, "duration": duration,
            "path": path, "size": size, "time": datetime.now().isoformat(),
        })
        self.data = self.data[:100]
        self.save()


class Watchlist:
    def __init__(self):
        self.file = "watchlist.json"
        self.users = []
        self.load()
    
    def load(self):
        try:
            if os.path.exists(self.file):
                with open(self.file, 'r', encoding='utf-8') as f:
                    self.users = json.load(f).get("users", [])
        except Exception:
            self.users = []
    
    def save(self):
        try:
            with open(self.file, 'w', encoding='utf-8') as f:
                json.dump({"users": self.users}, f)
        except Exception:
            pass
    
    def add(self, u: str) -> bool:
        u = u.strip().lstrip("@").lower()
        if u and u not in self.users:
            self.users.append(u)
            self.save()
            return True
        return False
    
    def remove(self, u: str) -> bool:
        u = u.strip().lstrip("@").lower()
        if u in self.users:
            self.users.remove(u)
            self.save()
            return True
        return False
    
    def get_all(self) -> List[str]:
        return self.users.copy()


# ============================================================================
# SYSTEM TRAY
# ============================================================================

class SystemTray:
    def __init__(self, app: 'TikTokApp'):
        self.app = app
        self.icon = None
        self.running = False
    
    def _create_image(self):
        img = Image.new('RGB', (64, 64), '#FE2C55')
        draw = ImageDraw.Draw(img)
        draw.ellipse([8, 8, 56, 56], fill='white')
        draw.ellipse([20, 20, 44, 44], fill='#FE2C55')
        return img
    
    def start(self):
        if not TRAY_AVAILABLE:
            return
        
        def on_show(icon, item):
            self.app.after(0, self.app.show_window)
        
        def on_quit(icon, item):
            self.running = False
            icon.stop()
            self.app.after(0, self.app.quit_app)
        
        menu = pystray.Menu(
            TrayItem('Show', on_show, default=True),
            TrayItem('Quit', on_quit)
        )
        
        self.icon = pystray.Icon("TikTok Recorder", self._create_image(), "TikTok Live Recorder", menu)
        self.running = True
        threading.Thread(target=self.icon.run, daemon=True).start()
    
    def stop(self):
        if self.icon:
            try:
                self.icon.stop()
            except:
                pass
        self.running = False


# ============================================================================
# MAIN APPLICATION
# ============================================================================

class TikTokApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        # Initialize
        self.config = AppConfig.load()
        Theme.set_theme(self.config.theme)
        
        self.notifier = TelegramNotifier(self.config.telegram)
        self.api = TikTokAPI(self.config.cookies_file)
        self.recorder = Recorder(self.config, self.notifier)
        self.multi = MultiRecorder(self.config, self.notifier)
        self.history = History()
        self.watchlist = Watchlist()
        self.preview = LivePreview()
        self.tray = SystemTray(self)
        
        self.current_info = {}
        self.monitoring = False
        self.user_status = {}
        self.queue = queue.Queue()
        self._stop = threading.Event()
        self.current_page = "home"
        
        self._setup_window()
        self._create_ui()
        self._start_updater()
        self._process_queue()
        
        if TRAY_AVAILABLE and self.config.minimize_to_tray:
            self.tray.start()
    
    def _setup_window(self):
        self.title("TikTok Live Recorder")
        # Sync CTkinter appearance mode with our theme
        ctk.set_appearance_mode(self.config.theme)
        self._apply_theme()
        
        self.geometry("1000x700")
        self.minsize(900, 650)
        self.after(10, self._maximize)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
    
    def _maximize(self):
        if sys.platform == "win32":
            self.state('zoomed')
        else:
            try:
                self.attributes('-zoomed', True)
            except:
                pass
    
    def _apply_theme(self):
        self.configure(fg_color=Theme.get("bg_primary"))
    
    def _create_ui(self):
        self.main = ctk.CTkFrame(self, fg_color=Theme.get("bg_primary"))
        self.main.pack(fill="both", expand=True)
        
        # Footer first
        self._create_footer()
        
        # Content
        self.content = ctk.CTkFrame(self.main, fg_color=Theme.get("bg_primary"))
        self.content.pack(fill="both", expand=True)
        
        # Pages
        self.pages = {}
        self._create_home_page()
        self._create_following_page()
        self._create_history_page()
        self._create_settings_page()
        
        self._show_page("home")
    
    def _create_footer(self):
        self.footer = ctk.CTkFrame(self.main, fg_color=Theme.get("bg_secondary"), height=90, corner_radius=0)
        self.footer.pack(fill="x", side="bottom")
        self.footer.pack_propagate(False)
        
        self.footer_inner = ctk.CTkFrame(self.footer, fg_color="transparent")
        self.footer_inner.pack(expand=True, fill="both", padx=30, pady=12)
        self.footer_inner.grid_columnconfigure((0, 1, 2, 3), weight=1)
        
        self.nav_btns = {}
        self.footer_frames = {}
        items = [("home", "🏠", "Home"), ("following", "👥", "Following"), ("history", "📥", "History"), ("settings", "⚙️", "Settings")]
        
        for i, (pid, icon, label) in enumerate(items):
            frame = ctk.CTkFrame(self.footer_inner, fg_color="transparent")
            frame.grid(row=0, column=i, sticky="nsew", padx=8)
            
            cont = ctk.CTkFrame(frame, fg_color="transparent")
            cont.pack(expand=True)
            
            icon_lbl = ctk.CTkLabel(cont, text=icon, font=ctk.CTkFont(size=28), text_color=Theme.get("text_muted"))
            icon_lbl.pack(pady=(0, 4))
            
            text_lbl = ctk.CTkLabel(cont, text=label, font=ctk.CTkFont(size=12), text_color=Theme.get("text_muted"))
            text_lbl.pack()
            
            for w in [cont, icon_lbl, text_lbl]:
                w.bind("<Button-1>", lambda e, p=pid: self._show_page(p))
            
            self.nav_btns[pid] = (icon_lbl, text_lbl)
    
    def _show_page(self, pid: str):
        for p, (i, t) in self.nav_btns.items():
            if p == pid:
                i.configure(text_color=Theme.get("text_primary"))
                t.configure(text_color=Theme.get("text_primary"))
            else:
                i.configure(text_color=Theme.get("text_muted"))
                t.configure(text_color=Theme.get("text_muted"))
        
        for page in self.pages.values():
            page.pack_forget()
        
        if pid in self.pages:
            self.pages[pid].pack(fill="both", expand=True)
        
        self.current_page = pid
    
    # ==================== HOME PAGE ====================
    
    def _create_home_page(self):
        page = ctk.CTkFrame(self.content, fg_color=Theme.get("bg_primary"))
        self.pages["home"] = page
        
        # Three columns
        left = ctk.CTkFrame(page, fg_color="transparent", width=300)
        left.pack(side="left", fill="y", padx=(25, 10), pady=25)
        left.pack_propagate(False)
        
        center = ctk.CTkFrame(page, fg_color="transparent")
        center.pack(side="left", fill="both", expand=True, padx=10, pady=25)
        
        right = ctk.CTkFrame(page, fg_color="transparent", width=320)
        right.pack(side="right", fill="y", padx=(10, 25), pady=25)
        right.pack_propagate(False)
        
        # === LEFT: Preview & Controls ===
        self.preview_card = ctk.CTkFrame(left, fg_color=Theme.get("bg_secondary"), corner_radius=16)
        self.preview_card.pack(fill="x")
        
        # Preview header
        ph = ctk.CTkFrame(self.preview_card, fg_color="transparent")
        ph.pack(fill="x", padx=16, pady=(16, 8))
        
        self.preview_title = ctk.CTkLabel(ph, text="Live Preview", font=ctk.CTkFont(size=14, weight="bold"),
                    text_color=Theme.get("text_primary"))
        self.preview_title.pack(side="left")
        
        self.preview_btn = ctk.CTkButton(ph, text="👁️", width=36, height=28, corner_radius=14,
                                        fg_color=Theme.get("bg_tertiary"), hover_color=Theme.get("bg_elevated"),
                                        command=self._toggle_preview)
        self.preview_btn.pack(side="right")
        
        # Preview display (compact)
        self.preview_frame = ctk.CTkFrame(self.preview_card, fg_color=Theme.get("bg_tertiary"), corner_radius=12,
                                         width=180, height=320)
        self.preview_frame.pack(padx=16, pady=(0, 16))
        self.preview_frame.pack_propagate(False)
        
        # Initialize preview image reference
        self._current_preview_image = None
        
        # Create initial blank preview - NO IMAGE, just frame with text
        self.preview_label = ctk.CTkFrame(
            self.preview_frame,
            width=180,
            height=320,
            fg_color=Theme.get("bg_tertiary"),
            corner_radius=0
        )
        self.preview_label.pack(expand=True, fill="both")
        self.preview_label.pack_propagate(False)
        
        self.preview_placeholder = ctk.CTkLabel(
            self.preview_label, 
            text="No Preview",
            font=ctk.CTkFont(size=14), 
            text_color=Theme.get("text_muted"),
            fg_color="transparent"
        )
        self.preview_placeholder.place(relx=0.5, rely=0.5, anchor="center")
        
        # Record buttons
        self.record_btn = ctk.CTkButton(left, text="🔴 Start Recording", height=48, corner_radius=24,
                                       fg_color=Theme.get("accent"), hover_color=Theme.get("accent_hover"),
                                       font=ctk.CTkFont(size=14, weight="bold"), state="disabled",
                                       command=self._start_recording)
        self.record_btn.pack(fill="x", pady=(15, 8))
        
        self.stop_btn = ctk.CTkButton(left, text="⏹️ Stop Recording", height=48, corner_radius=24,
                                     fg_color=Theme.get("bg_tertiary"), hover_color=Theme.get("bg_elevated"),
                                     text_color=Theme.get("text_primary"),
                                     font=ctk.CTkFont(size=14, weight="bold"), state="disabled",
                                     command=self._stop_recording)
        self.stop_btn.pack(fill="x")
        
        # === CENTER: Search & Info ===
        # Search
        self.search_card = ctk.CTkFrame(center, fg_color=Theme.get("bg_secondary"), corner_radius=16)
        self.search_card.pack(fill="x", pady=(0, 15))
        
        search_inner = ctk.CTkFrame(self.search_card, fg_color="transparent")
        search_inner.pack(fill="x", padx=20, pady=16)
        
        self.search_title = ctk.CTkLabel(search_inner, text="🔍 Search User", font=ctk.CTkFont(size=14, weight="bold"),
                    text_color=Theme.get("text_primary"))
        self.search_title.pack(anchor="w", pady=(0, 10))
        
        search_row = ctk.CTkFrame(search_inner, fg_color="transparent")
        search_row.pack(fill="x")
        
        self.username_entry = ctk.CTkEntry(search_row, placeholder_text="Enter TikTok username...",
                                          height=44, font=ctk.CTkFont(size=14),
                                          fg_color=Theme.get("bg_tertiary"), border_width=0,
                                          corner_radius=22, text_color=Theme.get("text_primary"))
        self.username_entry.pack(side="left", fill="x", expand=True, padx=(0, 12))
        self.username_entry.bind("<Return>", lambda e: self._check_user())
        
        self.check_btn = ctk.CTkButton(search_row, text="Check", width=90, height=44, corner_radius=22,
                                      fg_color=Theme.get("accent"), hover_color=Theme.get("accent_hover"),
                                      font=ctk.CTkFont(size=14, weight="bold"), command=self._check_user)
        self.check_btn.pack(side="right")
        
        # User info card
        self.info_card = ctk.CTkFrame(center, fg_color=Theme.get("bg_secondary"), corner_radius=16)
        self.info_card.pack(fill="both", expand=True)
        
        info_inner = ctk.CTkFrame(self.info_card, fg_color="transparent")
        info_inner.pack(fill="both", expand=True, padx=20, pady=20)
        
        # User header
        user_row = ctk.CTkFrame(info_inner, fg_color="transparent")
        user_row.pack(fill="x", pady=(0, 15))
        
        self.user_avatar = ctk.CTkFrame(user_row, width=56, height=56, corner_radius=28,
                                       fg_color=Theme.get("bg_tertiary"))
        self.user_avatar.pack(side="left", padx=(0, 15))
        self.user_avatar.pack_propagate(False)
        ctk.CTkLabel(self.user_avatar, text="👤", font=ctk.CTkFont(size=24)).place(relx=0.5, rely=0.5, anchor="center")
        
        user_info = ctk.CTkFrame(user_row, fg_color="transparent")
        user_info.pack(side="left", fill="x", expand=True)
        
        self.info_username = ctk.CTkLabel(user_info, text="@username", font=ctk.CTkFont(size=18, weight="bold"),
                                         text_color=Theme.get("text_primary"))
        self.info_username.pack(anchor="w")
        
        self.info_status = ctk.CTkLabel(user_info, text="⚫ Offline", font=ctk.CTkFont(size=13),
                                       text_color=Theme.get("text_muted"))
        self.info_status.pack(anchor="w")
        
        # Stream title
        self.stream_title_label = ctk.CTkLabel(info_inner, text="Stream Title", font=ctk.CTkFont(size=12),
                    text_color=Theme.get("text_muted"))
        self.stream_title_label.pack(anchor="w", pady=(10, 4))
        
        self.info_title = ctk.CTkLabel(info_inner, text="Check a user to see stream info",
                                      font=ctk.CTkFont(size=14), text_color=Theme.get("text_secondary"),
                                      wraplength=400, justify="left")
        self.info_title.pack(anchor="w")
        
        # Stats row - store references to stat boxes
        self.stats_frame = ctk.CTkFrame(info_inner, fg_color="transparent")
        self.stats_frame.pack(fill="x", pady=(20, 0))
        
        self.stat_boxes = []
        for icon, label, attr in [("👥", "Viewers", "stat_viewers"), ("⏱️", "Duration", "stat_duration"), ("📁", "Size", "stat_size")]:
            box = ctk.CTkFrame(self.stats_frame, fg_color=Theme.get("bg_tertiary"), corner_radius=12)
            box.pack(side="left", fill="x", expand=True, padx=(0, 10) if attr != "stat_size" else 0)
            self.stat_boxes.append(box)
            
            ctk.CTkLabel(box, text=icon, font=ctk.CTkFont(size=20)).pack(pady=(12, 2))
            lbl = ctk.CTkLabel(box, text="0" if attr == "stat_viewers" else ("00:00:00" if attr == "stat_duration" else "0 MB"),
                              font=ctk.CTkFont(size=16, weight="bold"), text_color=Theme.get("text_primary"))
            lbl.pack()
            ctk.CTkLabel(box, text=label, font=ctk.CTkFont(size=10), text_color=Theme.get("text_muted")).pack(pady=(0, 12))
            
            setattr(self, attr, lbl)
        
        # === RIGHT: Statistics ===
        self.stats_card = ctk.CTkFrame(right, fg_color=Theme.get("bg_secondary"), corner_radius=16)
        self.stats_card.pack(fill="x")
        
        stats_inner = ctk.CTkFrame(self.stats_card, fg_color="transparent")
        stats_inner.pack(fill="x", padx=20, pady=20)
        
        self.stats_title = ctk.CTkLabel(stats_inner, text="📊 Statistics", font=ctk.CTkFont(size=16, weight="bold"),
                    text_color=Theme.get("text_primary"))
        self.stats_title.pack(anchor="w", pady=(0, 15))
        
        # Total recordings
        self._create_stat_row(stats_inner, "Total Recordings", f"{self.config.total_recordings}", "total_rec_lbl")
        
        # Total size
        total_gb = self.config.total_size_bytes / (1024 * 1024 * 1024)
        self._create_stat_row(stats_inner, "Total Size", f"{total_gb:.2f} GB", "total_size_lbl")
        
        # Total duration
        hours = self.config.total_duration_seconds // 3600
        mins = (self.config.total_duration_seconds % 3600) // 60
        self._create_stat_row(stats_inner, "Total Duration", f"{hours}h {mins}m", "total_dur_lbl")
        
        # Quality card - Aesthetic segmented buttons
        self.quality_card = ctk.CTkFrame(right, fg_color=Theme.get("bg_secondary"), corner_radius=16)
        self.quality_card.pack(fill="x", pady=(15, 0))
        
        quality_inner = ctk.CTkFrame(self.quality_card, fg_color="transparent")
        quality_inner.pack(fill="x", padx=20, pady=20)
        
        self.quality_title = ctk.CTkLabel(quality_inner, text="🎬 Quality", font=ctk.CTkFont(size=14, weight="bold"),
                    text_color=Theme.get("text_primary"))
        self.quality_title.pack(anchor="w", pady=(0, 12))
        
        # Segmented quality buttons
        self.quality_frame = ctk.CTkFrame(quality_inner, fg_color=Theme.get("bg_tertiary"), corner_radius=12)
        self.quality_frame.pack(fill="x")
        
        quality_btn_frame = ctk.CTkFrame(self.quality_frame, fg_color="transparent")
        quality_btn_frame.pack(fill="x", padx=4, pady=4)
        quality_btn_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)
        
        self.quality_buttons = {}
        qualities = [
            ("best", "🔥", "Best"),
            ("high", "⭐", "High"),
            ("medium", "✨", "Med"),
            ("low", "💡", "Low"),
        ]
        
        for i, (qid, icon, label) in enumerate(qualities):
            is_selected = self.config.quality == qid
            btn = ctk.CTkButton(
                quality_btn_frame,
                text=f"{icon}\n{label}",
                width=65,
                height=50,
                corner_radius=10,
                fg_color=Theme.get("accent") if is_selected else "transparent",
                hover_color=Theme.get("accent_hover") if is_selected else Theme.get("bg_elevated"),
                text_color=Theme.get("text_primary") if is_selected else Theme.get("text_muted"),
                font=ctk.CTkFont(size=11),
                command=lambda q=qid: self._select_quality(q)
            )
            btn.grid(row=0, column=i, padx=2, pady=2, sticky="nsew")
            self.quality_buttons[qid] = btn
        
        # Theme selector - modern segmented buttons
        self.theme_card = ctk.CTkFrame(right, fg_color=Theme.get("bg_secondary"), corner_radius=16)
        self.theme_card.pack(fill="x", pady=(15, 0))
        
        theme_header = ctk.CTkFrame(self.theme_card, fg_color="transparent")
        theme_header.pack(fill="x", padx=20, pady=(16, 8))
        
        ctk.CTkLabel(theme_header, text="🎨 Appearance", 
                    font=ctk.CTkFont(size=14, weight="bold"),
                    text_color=Theme.get("text_primary")).pack(side="left")
        
        # Segmented theme buttons
        self.theme_btn_frame = ctk.CTkFrame(self.theme_card, fg_color=Theme.get("bg_tertiary"), corner_radius=12)
        self.theme_btn_frame.pack(fill="x", padx=16, pady=(0, 16))
        self.theme_btn_frame.grid_columnconfigure((0, 1), weight=1)
        
        self.theme_buttons = {}
        themes = [("dark", "🌙", "Dark"), ("light", "☀️", "Light")]
        
        for i, (tid, icon, label) in enumerate(themes):
            is_selected = self.config.theme == tid
            btn = ctk.CTkButton(
                self.theme_btn_frame,
                text=f"{icon} {label}",
                font=ctk.CTkFont(size=13, weight="bold" if is_selected else "normal"),
                fg_color=Theme.get("accent") if is_selected else "transparent",
                hover_color=Theme.get("accent_hover") if is_selected else Theme.get("bg_elevated"),
                text_color="#FFFFFF" if is_selected else Theme.get("text_muted"),
                height=40,
                corner_radius=10,
                command=lambda t=tid: self._set_theme(t)
            )
            btn.grid(row=0, column=i, padx=4, pady=4, sticky="nsew")
            self.theme_buttons[tid] = btn
        
        # Open folder button
        self.open_folder_btn = ctk.CTkButton(right, text="📂 Open Output Folder", height=42, corner_radius=21,
                     fg_color=Theme.get("bg_tertiary"), hover_color=Theme.get("bg_elevated"),
                     text_color=Theme.get("text_primary"),
                     font=ctk.CTkFont(size=13), command=self._open_folder)
        self.open_folder_btn.pack(fill="x", pady=(15, 0))
    
    def _create_stat_row(self, parent, label: str, value: str, attr: str):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=4)
        
        ctk.CTkLabel(row, text=label, font=ctk.CTkFont(size=13), text_color=Theme.get("text_secondary")).pack(side="left")
        lbl = ctk.CTkLabel(row, text=value, font=ctk.CTkFont(size=13, weight="bold"), text_color=Theme.get("text_primary"))
        lbl.pack(side="right")
        
        setattr(self, attr, lbl)
    
    def _reset_preview_display(self):
        """Reset preview to blank state - NO IMAGE, only text"""
        # Destroy ALL children of preview_frame
        for widget in self.preview_frame.winfo_children():
            try:
                widget.destroy()
            except:
                pass
        
        # Clear image reference
        self._current_preview_image = None
        
        # Create simple placeholder - NO IMAGE AT ALL
        self.preview_label = ctk.CTkFrame(
            self.preview_frame,
            width=180,
            height=320,
            fg_color=Theme.get("bg_tertiary"),
            corner_radius=0
        )
        self.preview_label.pack(expand=True, fill="both")
        self.preview_label.pack_propagate(False)
        
        # Center text only
        self.preview_placeholder = ctk.CTkLabel(
            self.preview_label,
            text="No Preview",
            font=ctk.CTkFont(size=14),
            text_color=Theme.get("text_muted"),
            fg_color="transparent"
        )
        self.preview_placeholder.place(relx=0.5, rely=0.5, anchor="center")
    
    def _show_preview_image(self, ctk_image):
        """Show preview image - replaces blank state with image"""
        # Destroy ALL children of preview_frame
        for widget in self.preview_frame.winfo_children():
            try:
                widget.destroy()
            except:
                pass
        
        # Create image label
        self.preview_label = ctk.CTkLabel(
            self.preview_frame,
            text="",
            width=180,
            height=320,
            image=ctk_image,
            fg_color=Theme.get("bg_tertiary")
        )
        self.preview_label.pack(expand=True, fill="both")
    
    def _check_user(self):
        username = self.username_entry.get().strip().lstrip("@")
        if not username:
            return
        
        self.check_btn.configure(state="disabled", text="...")
        self.info_username.configure(text=f"@{username}")
        self.info_status.configure(text="⏳ Checking...", text_color=Theme.get("text_secondary"))
        
        def check():
            info = self.api.get_live_info(username, self.config.quality)
            self.queue.put(("user_info", info))
        
        threading.Thread(target=check, daemon=True).start()
    
    def _update_user_info(self, info: Dict):
        self.current_info = info
        self.check_btn.configure(state="normal", text="Check")
        
        # Get username - fallback to entry field if not in info
        username = info.get('username', '').strip()
        if not username:
            username = self.username_entry.get().strip().lstrip("@").lower()
        
        if info["success"] and info["is_live"]:
            self.info_username.configure(text=f"@{username}")
            self.info_status.configure(text="🔴 LIVE", text_color=Theme.get("accent"))
            self.info_title.configure(text=info.get('title', 'TikTok Live')[:150] or "TikTok Live")
            self.stat_viewers.configure(text=f"{info.get('viewer_count', 0):,}")
            self.record_btn.configure(state="normal")
            
            self._show_toast(f"🔴 @{username} is LIVE! ({info.get('viewer_count', 0):,} viewers)", "success")
            
            if self.config.sound.enabled and self.config.sound.on_live:
                SoundManager.play_alert()
            
            # Preview is user-controlled via toggle button
            # Don't auto-show thumbnail
        else:
            self.info_username.configure(text=f"@{username}")
            self.info_status.configure(text="⚫ Offline", text_color=Theme.get("text_muted"))
            self.info_title.configure(text=info.get('error', 'User is not live'))
            self.stat_viewers.configure(text="0")
            self.record_btn.configure(state="disabled")
            
            error_msg = info.get('error', 'User is not live')
            if "captcha" in error_msg.lower() or "cookies" in error_msg.lower():
                self._show_toast("⚠️ Butuh cookies! Export dari browser.", "warning")
            else:
                self._show_toast(f"⚫ @{username} offline: {error_msg}", "info")
    
    def _toggle_preview(self):
        """Toggle live preview on/off - can be called anytime"""
        if self.preview.is_running:
            # === TURN OFF ===
            self.preview.stop()
            self.preview_btn.configure(fg_color=Theme.get("bg_tertiary"))
            # Reset to default state - NO IMAGE
            self._reset_preview_display()
            self._show_toast("Preview stopped", "info")
        else:
            # === TURN ON ===
            # Check if we have a valid stream
            if not self.current_info.get("stream_url"):
                # No stream URL yet
                username = self.username_entry.get().strip()
                if not username:
                    self._show_toast("⚠️ Please enter a username first", "warning")
                elif not self.current_info.get("success"):
                    self._show_toast("⚠️ Please check the user first", "warning")
                elif not self.current_info.get("is_live"):
                    self._show_toast("❌ User is not currently live", "error")
                else:
                    self._show_toast("❌ Could not get stream URL", "error")
                return
            
            # Show loading state
            self._show_preview_loading()
            
            # Start preview
            if self.preview.start(self.current_info["stream_url"],
                                 lambda f: self.queue.put(("preview", f)), 180, 320):
                self.preview_btn.configure(fg_color=Theme.get("accent"))
                self._show_toast("✅ Preview started", "success")
            else:
                # Failed - reset to default
                self._reset_preview_display()
                self._show_toast("❌ Failed to start preview. Is FFmpeg installed?", "error")
    
    def _show_preview_loading(self):
        """Show loading state in preview"""
        for widget in self.preview_frame.winfo_children():
            try:
                widget.destroy()
            except:
                pass
        
        self.preview_label = ctk.CTkFrame(
            self.preview_frame,
            width=180,
            height=320,
            fg_color=Theme.get("bg_tertiary"),
            corner_radius=0
        )
        self.preview_label.pack(expand=True, fill="both")
        self.preview_label.pack_propagate(False)
        
        self.preview_placeholder = ctk.CTkLabel(
            self.preview_label,
            text="Loading...",
            font=ctk.CTkFont(size=14),
            text_color=Theme.get("text_muted"),
            fg_color="transparent"
        )
        self.preview_placeholder.place(relx=0.5, rely=0.5, anchor="center")
    
    def _start_recording(self):
        if not self.current_info.get("success"):
            self._show_toast("❌ User not live or check failed", "error")
            return
        
        info = self.current_info
        
        # Get username - prefer from info, fallback to entry field
        username = info.get('username', '').strip()
        if not username:
            username = self.username_entry.get().strip().lstrip("@").lower()
        
        if not username:
            self._show_toast("❌ No username specified", "error")
            return
        
        # Get stream URL
        stream_url = info.get("stream_url", "")
        if not stream_url:
            self._show_toast("⚠️ No stream URL - will try yt-dlp", "warning")
        
        url = f"https://www.tiktok.com/@{username}/live"
        
        self.recorder.on_complete = lambda u, d, s, f: self.queue.put(("complete", u, d, s, f))
        
        # Show starting message
        self._show_toast(f"⏳ Starting recording for @{username}...", "info")
        self.record_btn.configure(state="disabled")
        self.update()
        
        if self.recorder.start(username, stream_url, info.get("title", "TikTok Live"), url):
            self.stop_btn.configure(state="normal")
            self.check_btn.configure(state="disabled")
            self._show_toast(f"🔴 Recording @{username}...", "success")
        else:
            self.record_btn.configure(state="normal")
            error = self.recorder.get_last_error() or "Unknown error"
            self._show_toast(f"❌ Failed: {error[:50]}", "error")
    
    def _stop_recording(self):
        if not self.recorder.check_status():
            return
        
        self.stop_btn.configure(state="disabled", text="⏳ Stopping...")
        self.update()  # Force UI update
        
        # Get info before stopping
        dur = self.recorder.get_duration()
        path = self.recorder.output_file
        
        # Get username - prefer from recorder, then from info, then from entry
        username = self.recorder.username
        if not username:
            username = self.current_info.get("username", "")
        if not username:
            username = self.username_entry.get().strip().lstrip("@").lower()
        if not username:
            username = "unknown"
        
        # Stop recording - this is now synchronous
        self.recorder.stop()
        
        # Stop preview
        self.preview.stop()
        self.preview_btn.configure(fg_color=Theme.get("bg_tertiary"))
        
        # Reset preview display
        self._reset_preview_display()
        
        # Get final file size after stop
        size = self.recorder.get_file_size()
        
        if path and os.path.exists(path):
            self.history.add(username, self.current_info.get("title", "TikTok Live"), dur, path, size)
        
        self._show_toast(f"✅ Recording stopped! {dur} • {size}", "success")
        
        # Reset UI
        self.queue.put(("stopped",))
    
    def _reset_record_ui(self):
        self.record_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled", text="⏹️ Stop Recording")
        self.check_btn.configure(state="normal")
        self.stat_duration.configure(text="00:00:00")
        self.stat_size.configure(text="0 MB")
        self._update_stats()
        
        # Reset preview if not running
        if not self.preview.is_running:
            self._reset_preview_display()
    
    def _select_quality(self, quality: str):
        """Select quality with visual feedback"""
        self.config.quality = quality
        self.config.save()
        
        # Update button states
        for qid, btn in self.quality_buttons.items():
            if qid == quality:
                btn.configure(
                    fg_color=Theme.get("accent"),
                    hover_color=Theme.get("accent_hover"),
                    text_color=Theme.get("text_primary")
                )
            else:
                btn.configure(
                    fg_color="transparent",
                    hover_color=Theme.get("bg_elevated"),
                    text_color=Theme.get("text_muted")
                )
        
        quality_names = {"best": "Best", "high": "High", "medium": "Medium", "low": "Low"}
        self._show_toast(f"✅ Quality set to {quality_names.get(quality, quality)}", "success")
    
    def _show_toast(self, message: str, toast_type: str = "info"):
        """Show a compact, minimalist toast notification - fixed height, auto-expand width"""
        # Remove existing toast if any
        if hasattr(self, '_toast_frame') and self._toast_frame:
            try:
                self._toast_frame.destroy()
            except:
                pass
        
        # Accent colors based on type
        accent_colors = {
            "success": "#00D26A",
            "error": "#FE2C55", 
            "warning": "#FF9500",
            "info": Theme.get("cyan")
        }
        accent_color = accent_colors.get(toast_type, accent_colors["info"])
        
        # Create compact toast container with FIXED HEIGHT
        self._toast_frame = ctk.CTkFrame(
            self,
            fg_color=Theme.get("bg_secondary"),
            corner_radius=6,
            height=28
        )
        self._toast_frame.place(relx=0.5, rely=0.04, anchor="center")
        
        # Left accent bar
        accent_bar = ctk.CTkFrame(
            self._toast_frame,
            width=3,
            fg_color=accent_color,
            corner_radius=0
        )
        accent_bar.place(x=0, y=0, relheight=1)
        
        # Message text - placed to allow width expansion
        label = ctk.CTkLabel(
            self._toast_frame,
            text=message,
            font=ctk.CTkFont(size=12),
            text_color=Theme.get("text_primary"),
            height=28
        )
        label.place(x=11, y=0)
        
        # Calculate and set frame width based on text
        self._toast_frame.update_idletasks()
        text_width = label.winfo_reqwidth()
        frame_width = text_width + 24  # 11px left padding + 13px right padding
        self._toast_frame.configure(width=frame_width)
        
        # Auto-dismiss after 2.5 seconds
        def dismiss():
            try:
                if self._toast_frame:
                    self._toast_frame.destroy()
                    self._toast_frame = None
            except:
                pass
        
        self.after(2500, dismiss)
    
    def _set_theme(self, theme: str):
        """Set theme to dark or light - applies immediately without restart"""
        if theme == Theme.current:
            return  # Already this theme
        
        # Set theme in our system
        Theme.current = theme
        Theme.colors = ThemeColors.DARK if theme == "dark" else ThemeColors.LIGHT
        self.config.theme = theme
        self.config.save()
        
        # IMPORTANT: Sync CTkinter appearance mode with our theme
        ctk.set_appearance_mode(theme)
        
        # Force update to apply appearance mode
        self.update()
        
        # Update theme buttons first
        self._update_theme_buttons()
        
        # Apply theme to all widgets
        self._apply_theme_to_all()
        
        # Force another update
        self.update()
        
        # Show confirmation
        theme_name = "Dark" if theme == "dark" else "Light"
        self._show_toast(f"{'🌙' if theme == 'dark' else '☀️'} {theme_name} mode applied!", "success")
    
    def _update_theme_buttons(self):
        """Update theme button visual states"""
        try:
            for tid, btn in self.theme_buttons.items():
                is_selected = self.config.theme == tid
                btn.configure(
                    fg_color=Theme.get("accent") if is_selected else "transparent",
                    hover_color=Theme.get("accent_hover") if is_selected else Theme.get("bg_elevated"),
                    text_color="#FFFFFF" if is_selected else Theme.get("text_muted"),
                    font=ctk.CTkFont(size=13, weight="bold" if is_selected else "normal")
                )
            # Update theme button frame background
            self.theme_btn_frame.configure(fg_color=Theme.get("bg_tertiary"))
            self.theme_card.configure(fg_color=Theme.get("bg_secondary"))
            
            # Update open folder button
            self.open_folder_btn.configure(
                fg_color=Theme.get("bg_tertiary"),
                hover_color=Theme.get("bg_elevated"),
                text_color=Theme.get("text_primary")
            )
        except:
            pass
    
    def _apply_theme_to_all(self):
        """Apply current theme to all widgets comprehensively"""
        # Main containers
        self.configure(fg_color=Theme.get("bg_primary"))
        self.main.configure(fg_color=Theme.get("bg_primary"))
        self.content.configure(fg_color=Theme.get("bg_primary"))
        
        # Update all pages background
        for page_name, page in self.pages.items():
            try:
                page.configure(fg_color=Theme.get("bg_primary"))
            except:
                pass
        
        # Apply recursively to all widgets in all pages
        for page in self.pages.values():
            self._apply_theme_recursive(page)
        
        # Also apply to footer
        self._apply_theme_recursive(self.footer)
        
        # Update footer
        self._update_footer_theme()
        
        # Update quality buttons
        self._update_quality_buttons_theme()
        
        # Update theme buttons
        self._update_theme_buttons()
        
        # Update preview frame
        self._update_preview_theme()
        
        # Update following page
        self._update_following_theme()
        
        # Update history page
        self._update_history_theme()
        
        # Update home page elements
        self._update_home_theme()
        
        # Update settings page
        self._update_settings_theme()
        
        # Force visual update
        self.update_idletasks()
    
    def _apply_theme_recursive(self, widget):
        """Recursively apply theme to widget and all children"""
        try:
            # Get widget class name
            class_name = widget.__class__.__name__
            
            # Update fg_color for frames
            if hasattr(widget, 'configure'):
                try:
                    current_fg = widget.cget('fg_color')
                    if current_fg != 'transparent':
                        # Determine which theme color to use based on current color
                        if current_fg in ['#000000', '#FFFFFF', ThemeColors.DARK['bg_primary'], ThemeColors.LIGHT['bg_primary']]:
                            widget.configure(fg_color=Theme.get("bg_primary"))
                        elif current_fg in ['#0f0f0f', '#F5F5F5', ThemeColors.DARK['bg_secondary'], ThemeColors.LIGHT['bg_secondary']]:
                            widget.configure(fg_color=Theme.get("bg_secondary"))
                        elif current_fg in ['#1a1a1a', '#EBEBEB', ThemeColors.DARK['bg_tertiary'], ThemeColors.LIGHT['bg_tertiary']]:
                            widget.configure(fg_color=Theme.get("bg_tertiary"))
                        elif current_fg in ['#252525', '#E0E0E0', ThemeColors.DARK['bg_elevated'], ThemeColors.LIGHT['bg_elevated']]:
                            widget.configure(fg_color=Theme.get("bg_elevated"))
                except:
                    pass
                
                # Update text_color for labels
                try:
                    current_text = widget.cget('text_color')
                    if current_text in ['#FFFFFF', '#000000', ThemeColors.DARK['text_primary'], ThemeColors.LIGHT['text_primary']]:
                        widget.configure(text_color=Theme.get("text_primary"))
                    elif current_text in ['#ABABAB', '#555555', ThemeColors.DARK['text_secondary'], ThemeColors.LIGHT['text_secondary']]:
                        widget.configure(text_color=Theme.get("text_secondary"))
                    elif current_text in ['#6a6a6a', '#888888', ThemeColors.DARK['text_muted'], ThemeColors.LIGHT['text_muted']]:
                        widget.configure(text_color=Theme.get("text_muted"))
                except:
                    pass
                
                # Update hover_color for buttons
                try:
                    current_hover = widget.cget('hover_color')
                    if current_hover in [ThemeColors.DARK['bg_elevated'], ThemeColors.LIGHT['bg_elevated']]:
                        widget.configure(hover_color=Theme.get("bg_elevated"))
                except:
                    pass
            
            # Recurse into children
            try:
                for child in widget.winfo_children():
                    self._apply_theme_recursive(child)
            except:
                pass
                
        except Exception:
            pass
    
    def _update_footer_theme(self):
        """Update footer navigation colors including background"""
        try:
            # Update footer background
            self.footer.configure(fg_color=Theme.get("bg_secondary"))
            
            # Update nav button colors based on current page
            for pid, (icon_lbl, text_lbl) in self.nav_btns.items():
                if pid == self.current_page:
                    icon_lbl.configure(text_color=Theme.get("text_primary"))
                    text_lbl.configure(text_color=Theme.get("text_primary"))
                else:
                    icon_lbl.configure(text_color=Theme.get("text_muted"))
                    text_lbl.configure(text_color=Theme.get("text_muted"))
        except Exception:
            pass
    
    def _update_quality_buttons_theme(self):
        """Update quality button colors"""
        try:
            for qid, btn in self.quality_buttons.items():
                if qid == self.config.quality:
                    btn.configure(
                        fg_color=Theme.get("accent"),
                        hover_color=Theme.get("accent_hover"),
                        text_color=Theme.get("text_primary")
                    )
                else:
                    btn.configure(
                        fg_color="transparent",
                        hover_color=Theme.get("bg_elevated"),
                        text_color=Theme.get("text_muted")
                    )
        except:
            pass
    
    def _update_preview_theme(self):
        """Update preview frame colors"""
        try:
            self.preview_frame.configure(fg_color=Theme.get("bg_tertiary"))
            if hasattr(self, 'preview_label') and self.preview_label:
                self.preview_label.configure(fg_color=Theme.get("bg_tertiary"))
            if hasattr(self, 'preview_placeholder') and self.preview_placeholder:
                self.preview_placeholder.configure(text_color=Theme.get("text_muted"))
        except:
            pass
    
    def _update_following_theme(self):
        """Update following page colors"""
        try:
            # Title
            self.following_title.configure(text_color=Theme.get("text_primary"))
            
            # Add card
            self.following_add_card.configure(fg_color=Theme.get("bg_secondary"))
            self.watchlist_entry.configure(fg_color=Theme.get("bg_tertiary"), text_color=Theme.get("text_primary"))
            
            # List card
            self.following_list_card.configure(fg_color=Theme.get("bg_secondary"))
            self.following_users_label.configure(text_color=Theme.get("text_primary"))
            self.watchlist_count.configure(text_color=Theme.get("text_muted"))
            
            # Scroll frame
            self.watchlist_scroll.configure(fg_color="transparent")
            
            # Monitor button
            self.monitor_btn.configure(text_color=Theme.get("bg_primary"))
            
            # Refresh watchlist items with new theme
            self._update_watchlist()
        except Exception as e:
            pass
    
    def _update_history_theme(self):
        """Update history page colors"""
        try:
            # Title
            self.history_title.configure(text_color=Theme.get("text_primary"))
            
            # List card
            self.history_list_card.configure(fg_color=Theme.get("bg_secondary"))
            
            # Scroll frame
            self.history_scroll.configure(fg_color="transparent")
            
            # Refresh history items with new theme
            self._update_history()
        except Exception as e:
            pass
    
    def _update_home_theme(self):
        """Update home page colors"""
        try:
            # Left column - Preview card
            self.preview_card.configure(fg_color=Theme.get("bg_secondary"))
            self.preview_title.configure(text_color=Theme.get("text_primary"))
            self.preview_btn.configure(fg_color=Theme.get("bg_tertiary"), hover_color=Theme.get("bg_elevated"))
            
            # Center column - Search card
            self.search_card.configure(fg_color=Theme.get("bg_secondary"))
            self.search_title.configure(text_color=Theme.get("text_primary"))
            self.username_entry.configure(fg_color=Theme.get("bg_tertiary"), text_color=Theme.get("text_primary"))
            
            # Center column - Info card
            self.info_card.configure(fg_color=Theme.get("bg_secondary"))
            self.user_avatar.configure(fg_color=Theme.get("bg_tertiary"))
            self.info_username.configure(text_color=Theme.get("text_primary"))
            self.stream_title_label.configure(text_color=Theme.get("text_muted"))
            self.info_title.configure(text_color=Theme.get("text_secondary"))
            
            # Stat boxes
            for box in self.stat_boxes:
                box.configure(fg_color=Theme.get("bg_tertiary"))
            
            # Right column - Stats card
            self.stats_card.configure(fg_color=Theme.get("bg_secondary"))
            self.stats_title.configure(text_color=Theme.get("text_primary"))
            
            # Right column - Quality card
            self.quality_card.configure(fg_color=Theme.get("bg_secondary"))
            self.quality_title.configure(text_color=Theme.get("text_primary"))
            self.quality_frame.configure(fg_color=Theme.get("bg_tertiary"))
            
            # Update buttons with text_color
            self.stop_btn.configure(
                fg_color=Theme.get("bg_tertiary"), 
                hover_color=Theme.get("bg_elevated"),
                text_color=Theme.get("text_primary")
            )
            self.open_folder_btn.configure(
                fg_color=Theme.get("bg_tertiary"),
                hover_color=Theme.get("bg_elevated"),
                text_color=Theme.get("text_primary")
            )
            
        except Exception as e:
            pass
    
    def _update_settings_theme(self):
        """Update settings page colors"""
        try:
            # Settings page is a scrollable frame
            self.pages["settings"].configure(fg_color=Theme.get("bg_primary"))
            
            # Container
            self.settings_container.configure(fg_color="transparent")
            
            # Title
            self.settings_title.configure(text_color=Theme.get("text_primary"))
            
            # All cards
            for card, title_label in self.settings_cards:
                card.configure(fg_color=Theme.get("bg_secondary"))
                title_label.configure(text_color=Theme.get("text_primary"))
            
            # Entry fields
            self.output_entry.configure(fg_color=Theme.get("bg_tertiary"), text_color=Theme.get("text_primary"))
            self.filename_entry.configure(fg_color=Theme.get("bg_tertiary"), text_color=Theme.get("text_primary"))
            self.cookies_entry.configure(fg_color=Theme.get("bg_tertiary"), text_color=Theme.get("text_primary"))
            
            # Browse buttons
            self.output_browse_btn.configure(fg_color=Theme.get("bg_tertiary"), hover_color=Theme.get("bg_elevated"))
            self.cookies_browse_btn.configure(fg_color=Theme.get("bg_tertiary"), hover_color=Theme.get("bg_elevated"))
            
            # Hint label
            self.filename_hint.configure(text_color=Theme.get("text_muted"))
            
            # Telegram
            self.tg_switch.configure(text_color=Theme.get("text_primary"))
            self.tg_token_label.configure(text_color=Theme.get("text_muted"))
            self.tg_chat_label.configure(text_color=Theme.get("text_muted"))
            self.tg_token.configure(fg_color=Theme.get("bg_tertiary"), text_color=Theme.get("text_primary"))
            self.tg_chat.configure(fg_color=Theme.get("bg_tertiary"), text_color=Theme.get("text_primary"))
            
            # Sound switch
            self.sound_switch.configure(text_color=Theme.get("text_primary"))
            
        except Exception as e:
            pass
    
    def _open_folder(self):
        path = os.path.abspath(self.config.output_dir)
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.run(["open", path])
        else:
            subprocess.run(["xdg-open", path])
    
    def _update_stats(self):
        self.total_rec_lbl.configure(text=f"{self.config.total_recordings}")
        total_gb = self.config.total_size_bytes / (1024 * 1024 * 1024)
        self.total_size_lbl.configure(text=f"{total_gb:.2f} GB")
        hours = self.config.total_duration_seconds // 3600
        mins = (self.config.total_duration_seconds % 3600) // 60
        self.total_dur_lbl.configure(text=f"{hours}h {mins}m")
    
    # ==================== FOLLOWING PAGE ====================
    
    def _create_following_page(self):
        page = ctk.CTkFrame(self.content, fg_color=Theme.get("bg_primary"))
        self.pages["following"] = page
        
        container = ctk.CTkFrame(page, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=30, pady=25)
        
        # Header
        header = ctk.CTkFrame(container, fg_color="transparent")
        header.pack(fill="x", pady=(0, 20))
        
        self.following_title = ctk.CTkLabel(header, text="Following", font=ctk.CTkFont(size=24, weight="bold"),
                    text_color=Theme.get("text_primary"))
        self.following_title.pack(side="left")
        
        self.monitor_status = ctk.CTkLabel(header, text="", font=ctk.CTkFont(size=12),
                                          text_color=Theme.get("accent"))
        self.monitor_status.pack(side="right")
        
        # Add user card
        self.following_add_card = ctk.CTkFrame(container, fg_color=Theme.get("bg_secondary"), corner_radius=16)
        self.following_add_card.pack(fill="x", pady=(0, 15))
        
        add_inner = ctk.CTkFrame(self.following_add_card, fg_color="transparent")
        add_inner.pack(fill="x", padx=20, pady=16)
        
        self.watchlist_entry = ctk.CTkEntry(add_inner, placeholder_text="Add username...", height=44,
                                           fg_color=Theme.get("bg_tertiary"), border_width=0, corner_radius=22,
                                           text_color=Theme.get("text_primary"))
        self.watchlist_entry.pack(side="left", fill="x", expand=True, padx=(0, 12))
        
        self.following_add_btn = ctk.CTkButton(add_inner, text="➕ Add", width=90, height=44, corner_radius=22,
                     fg_color=Theme.get("accent"), hover_color=Theme.get("accent_hover"),
                     command=self._add_watchlist)
        self.following_add_btn.pack(side="right")
        
        # Monitor button
        self.monitor_btn = ctk.CTkButton(container, text="▶️ Start Monitoring", height=48, corner_radius=24,
                                        fg_color=Theme.get("cyan"), hover_color="#20d4e0",
                                        text_color=Theme.get("bg_primary"), font=ctk.CTkFont(size=14, weight="bold"),
                                        command=self._toggle_monitor)
        self.monitor_btn.pack(fill="x", pady=(0, 15))
        
        # List card
        self.following_list_card = ctk.CTkFrame(container, fg_color=Theme.get("bg_secondary"), corner_radius=16)
        self.following_list_card.pack(fill="both", expand=True)
        
        list_header = ctk.CTkFrame(self.following_list_card, fg_color="transparent")
        list_header.pack(fill="x", padx=20, pady=(16, 8))
        
        self.following_users_label = ctk.CTkLabel(list_header, text="Users", font=ctk.CTkFont(size=14, weight="bold"),
                    text_color=Theme.get("text_primary"))
        self.following_users_label.pack(side="left")
        
        self.watchlist_count = ctk.CTkLabel(list_header, text="(0)", font=ctk.CTkFont(size=12),
                                           text_color=Theme.get("text_muted"))
        self.watchlist_count.pack(side="left", padx=8)
        
        self.watchlist_scroll = ctk.CTkScrollableFrame(self.following_list_card, fg_color="transparent")
        self.watchlist_scroll.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        
        self._update_watchlist()
    
    def _add_watchlist(self):
        u = self.watchlist_entry.get()
        if u and self.watchlist.add(u):
            self.watchlist_entry.delete(0, "end")
            self._update_watchlist()
    
    def _remove_watchlist(self, u: str):
        if self.watchlist.remove(u):
            self._update_watchlist()
    
    def _update_watchlist(self):
        # Ensure theme is synced
        Theme.colors = ThemeColors.DARK if Theme.current == "dark" else ThemeColors.LIGHT
        
        for w in self.watchlist_scroll.winfo_children():
            w.destroy()
        
        users = self.watchlist.get_all()
        self.watchlist_count.configure(text=f"({len(users)})")
        
        if not users:
            ctk.CTkLabel(self.watchlist_scroll, text="No users yet", font=ctk.CTkFont(size=13),
                        text_color=Theme.get("text_muted")).pack(pady=30)
            return
        
        for u in users:
            is_rec = self.multi.is_recording(u)
            is_live = self.user_status.get(u, {}).get("is_live", False)
            
            item = ctk.CTkFrame(self.watchlist_scroll, fg_color=Theme.get("bg_tertiary"), corner_radius=12)
            item.pack(fill="x", pady=3)
            
            inner = ctk.CTkFrame(item, fg_color="transparent")
            inner.pack(fill="x", padx=14, pady=10)
            
            status = "🔴" if is_rec else ("🟢" if is_live else "⚫")
            ctk.CTkLabel(inner, text=status, font=ctk.CTkFont(size=14)).pack(side="left", padx=(0, 10))
            
            ctk.CTkLabel(inner, text=f"@{u}", font=ctk.CTkFont(size=14, weight="bold"),
                        text_color=Theme.get("text_primary")).pack(side="left")
            
            if is_rec:
                rec = self.multi.get(u)
                if rec:
                    ctk.CTkLabel(inner, text=f" • {rec.get_duration()}", font=ctk.CTkFont(size=12),
                                text_color=Theme.get("text_secondary")).pack(side="left")
            
            ctk.CTkButton(inner, text="✕", width=30, height=30, corner_radius=15,
                         fg_color="transparent", hover_color=Theme.get("bg_elevated"),
                         text_color=Theme.get("text_muted"),
                         command=lambda x=u: self._remove_watchlist(x)).pack(side="right")
    
    def _toggle_monitor(self):
        if self.monitoring:
            self._stop_monitor()
        else:
            self._start_monitor()
    
    def _start_monitor(self):
        if not self.watchlist.get_all():
            return
        
        self.monitoring = True
        self.monitor_btn.configure(text="⏹️ Stop Monitoring", fg_color=Theme.get("accent"))
        self.monitor_status.configure(text="● Monitoring")
        
        threading.Thread(target=self._monitor_loop, daemon=True).start()
    
    def _stop_monitor(self):
        self.monitoring = False
        self.monitor_btn.configure(text="▶️ Start Monitoring", fg_color=Theme.get("cyan"))
        self.monitor_status.configure(text="")
    
    def _monitor_loop(self):
        while self.monitoring:
            for u in self.watchlist.get_all():
                if not self.monitoring:
                    break
                
                try:
                    info = self.api.get_live_info(u, self.config.quality)
                    self.user_status[u] = info
                    
                    if info["is_live"] and not self.multi.is_recording(u):
                        url = f"https://www.tiktok.com/@{u}/live"
                        if self.multi.start(u, info.get("stream_url", ""), info["title"], url):
                            self.notifier.notify_live(u, info["title"], info["viewer_count"])
                            if self.config.sound.enabled:
                                SoundManager.play_alert()
                    
                    self.queue.put(("monitor_update",))
                except:
                    pass
                
                time.sleep(3)
            
            for _ in range(self.config.check_interval):
                if not self.monitoring:
                    break
                time.sleep(1)
    
    # ==================== HISTORY PAGE ====================
    
    def _create_history_page(self):
        page = ctk.CTkFrame(self.content, fg_color=Theme.get("bg_primary"))
        self.pages["history"] = page
        
        container = ctk.CTkFrame(page, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=30, pady=25)
        
        # Header
        self.history_title = ctk.CTkLabel(container, text="Recordings", font=ctk.CTkFont(size=24, weight="bold"),
                    text_color=Theme.get("text_primary"))
        self.history_title.pack(anchor="w", pady=(0, 20))
        
        # List card
        self.history_list_card = ctk.CTkFrame(container, fg_color=Theme.get("bg_secondary"), corner_radius=16)
        self.history_list_card.pack(fill="both", expand=True)
        
        self.history_scroll = ctk.CTkScrollableFrame(self.history_list_card, fg_color="transparent")
        self.history_scroll.pack(fill="both", expand=True, padx=12, pady=12)
        
        self._update_history()
    
    def _update_history(self):
        # Ensure theme is synced
        Theme.colors = ThemeColors.DARK if Theme.current == "dark" else ThemeColors.LIGHT
        
        for w in self.history_scroll.winfo_children():
            w.destroy()
        
        if not self.history.data:
            ctk.CTkLabel(self.history_scroll, text="No recordings yet", font=ctk.CTkFont(size=13),
                        text_color=Theme.get("text_muted")).pack(pady=40)
            return
        
        for entry in self.history.data[:50]:
            item = ctk.CTkFrame(self.history_scroll, fg_color=Theme.get("bg_tertiary"), corner_radius=12)
            item.pack(fill="x", pady=4)
            
            inner = ctk.CTkFrame(item, fg_color="transparent")
            inner.pack(fill="x", padx=16, pady=12)
            
            # Thumbnail
            thumb_frame = ctk.CTkFrame(inner, width=90, height=120, corner_radius=8,
                                       fg_color=Theme.get("bg_elevated"))
            thumb_frame.pack(side="left", padx=(0, 16))
            thumb_frame.pack_propagate(False)
            
            # Load thumbnail async
            path = entry.get("path", "")
            if os.path.exists(path):
                def load_thumb(p, frame):
                    img = ThumbnailGenerator.generate(p, (90, 120))
                    if img:
                        self.queue.put(("history_thumb", frame, img))
                threading.Thread(target=load_thumb, args=(path, thumb_frame), daemon=True).start()
            else:
                ctk.CTkLabel(thumb_frame, text="🎬", font=ctk.CTkFont(size=28)).place(relx=0.5, rely=0.5, anchor="center")
            
            # Info
            info = ctk.CTkFrame(inner, fg_color="transparent")
            info.pack(side="left", fill="both", expand=True)
            
            ctk.CTkLabel(info, text=f"@{entry['username']}", font=ctk.CTkFont(size=14, weight="bold"),
                        text_color=Theme.get("text_primary")).pack(anchor="w")
            
            ctk.CTkLabel(info, text=entry.get('title', '')[:60] or "TikTok Live",
                        font=ctk.CTkFont(size=12), text_color=Theme.get("text_secondary"),
                        wraplength=350).pack(anchor="w", pady=(2, 0))
            
            ctk.CTkLabel(info, text=f"⏱️ {entry['duration']}  •  📁 {entry['size']}",
                        font=ctk.CTkFont(size=11), text_color=Theme.get("text_muted")).pack(anchor="w", pady=(6, 0))
            
            try:
                dt = datetime.fromisoformat(entry['time'])
                ctk.CTkLabel(info, text=dt.strftime("%d %b %Y, %H:%M"), font=ctk.CTkFont(size=10),
                            text_color=Theme.get("text_muted")).pack(anchor="w", pady=(2, 0))
            except:
                pass
            
            # Play button
            if os.path.exists(path):
                ctk.CTkButton(inner, text="▶️", width=44, height=44, corner_radius=22,
                             fg_color=Theme.get("accent"), hover_color=Theme.get("accent_hover"),
                             font=ctk.CTkFont(size=18),
                             command=lambda p=path: self._play_video(p)).pack(side="right")
    
    def _play_video(self, path: str):
        """Open video with default player"""
        if not os.path.exists(path):
            return
        
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.run(["open", path])
        else:
            subprocess.run(["xdg-open", path])
    
    # ==================== SETTINGS PAGE ====================
    
    def _create_settings_page(self):
        page = ctk.CTkScrollableFrame(self.content, fg_color=Theme.get("bg_primary"))
        self.pages["settings"] = page
        
        self.settings_container = ctk.CTkFrame(page, fg_color="transparent")
        self.settings_container.pack(fill="both", expand=True, padx=30, pady=25)
        
        self.settings_title = ctk.CTkLabel(self.settings_container, text="Settings", font=ctk.CTkFont(size=24, weight="bold"),
                    text_color=Theme.get("text_primary"))
        self.settings_title.pack(anchor="w", pady=(0, 20))
        
        # Store cards for theme updates
        self.settings_cards = []
        
        # Output
        self._create_settings_card(self.settings_container, "📁 Output Directory", self._build_output_settings)
        
        # Filename pattern
        self._create_settings_card(self.settings_container, "📝 Filename Pattern", self._build_filename_settings)
        
        # Cookies
        self._create_settings_card(self.settings_container, "🍪 Cookies", self._build_cookies_settings)
        
        # Sound
        self._create_settings_card(self.settings_container, "🔔 Sound Alerts", self._build_sound_settings)
        
        # Telegram
        self._create_settings_card(self.settings_container, "📱 Telegram", self._build_telegram_settings)
        
        # Save button
        self.settings_save_btn = ctk.CTkButton(self.settings_container, text="💾 Save Settings", height=48, corner_radius=24,
                     fg_color=Theme.get("accent"), hover_color=Theme.get("accent_hover"),
                     font=ctk.CTkFont(size=14, weight="bold"),
                     command=self._save_settings)
        self.settings_save_btn.pack(fill="x", pady=(15, 0))
    
    def _create_settings_card(self, parent, title: str, builder):
        card = ctk.CTkFrame(parent, fg_color=Theme.get("bg_secondary"), corner_radius=16)
        card.pack(fill="x", pady=(0, 12))
        
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=20, pady=16)
        
        title_label = ctk.CTkLabel(inner, text=title, font=ctk.CTkFont(size=14, weight="bold"),
                    text_color=Theme.get("text_primary"))
        title_label.pack(anchor="w", pady=(0, 10))
        
        builder(inner)
        
        # Store card and title for theme updates
        self.settings_cards.append((card, title_label))
    
    def _build_output_settings(self, parent):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x")
        
        self.output_entry = ctk.CTkEntry(row, height=40, fg_color=Theme.get("bg_tertiary"),
                                        border_width=0, corner_radius=10, text_color=Theme.get("text_primary"))
        self.output_entry.insert(0, self.config.output_dir)
        self.output_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        self.output_browse_btn = ctk.CTkButton(row, text="📂", width=40, height=40, corner_radius=10,
                     fg_color=Theme.get("bg_tertiary"), hover_color=Theme.get("bg_elevated"),
                     command=self._browse_output)
        self.output_browse_btn.pack(side="right")
    
    def _build_filename_settings(self, parent):
        self.filename_entry = ctk.CTkEntry(parent, height=40, fg_color=Theme.get("bg_tertiary"),
                                          border_width=0, corner_radius=10, text_color=Theme.get("text_primary"))
        self.filename_entry.insert(0, self.config.filename_pattern)
        self.filename_entry.pack(fill="x")
        
        self.filename_hint = ctk.CTkLabel(parent, text="Variables: {username}, {date}, {time}, {datetime}, {title}",
                    font=ctk.CTkFont(size=11), text_color=Theme.get("text_muted"))
        self.filename_hint.pack(anchor="w", pady=(6, 0))
    
    def _build_cookies_settings(self, parent):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x")
        
        self.cookies_entry = ctk.CTkEntry(row, placeholder_text="cookies.txt", height=40,
                                         fg_color=Theme.get("bg_tertiary"), border_width=0, corner_radius=10,
                                         text_color=Theme.get("text_primary"))
        self.cookies_entry.insert(0, self.config.cookies_file)
        self.cookies_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        self.cookies_browse_btn = ctk.CTkButton(row, text="📂", width=40, height=40, corner_radius=10,
                     fg_color=Theme.get("bg_tertiary"), hover_color=Theme.get("bg_elevated"),
                     command=self._browse_cookies)
        self.cookies_browse_btn.pack(side="right")
    
    def _build_sound_settings(self, parent):
        self.sound_switch = ctk.CTkSwitch(parent, text="Enable sound notifications",
                                         progress_color=Theme.get("accent"),
                                         font=ctk.CTkFont(size=13),
                                         text_color=Theme.get("text_primary"))
        if self.config.sound.enabled:
            self.sound_switch.select()
        self.sound_switch.pack(anchor="w")
        
        if not SOUND_AVAILABLE:
            self.sound_hint = ctk.CTkLabel(parent, text="(Sound only available on Windows)",
                        font=ctk.CTkFont(size=11), text_color=Theme.get("text_muted"))
            self.sound_hint.pack(anchor="w")
    
    def _build_telegram_settings(self, parent):
        self.tg_switch = ctk.CTkSwitch(parent, text="Enable Telegram notifications",
                                      progress_color=Theme.get("accent"), font=ctk.CTkFont(size=13),
                                      text_color=Theme.get("text_primary"))
        if self.config.telegram.enabled:
            self.tg_switch.select()
        self.tg_switch.pack(anchor="w", pady=(0, 10))
        
        self.tg_token_label = ctk.CTkLabel(parent, text="Bot Token", font=ctk.CTkFont(size=11),
                    text_color=Theme.get("text_muted"))
        self.tg_token_label.pack(anchor="w")
        self.tg_token = ctk.CTkEntry(parent, placeholder_text="123456:ABC...", height=36,
                                    fg_color=Theme.get("bg_tertiary"), border_width=0, corner_radius=8,
                                    text_color=Theme.get("text_primary"))
        self.tg_token.insert(0, self.config.telegram.bot_token)
        self.tg_token.pack(fill="x", pady=(2, 8))
        
        self.tg_chat_label = ctk.CTkLabel(parent, text="Chat ID", font=ctk.CTkFont(size=11),
                    text_color=Theme.get("text_muted"))
        self.tg_chat_label.pack(anchor="w")
        self.tg_chat = ctk.CTkEntry(parent, placeholder_text="987654321", height=36,
                                   fg_color=Theme.get("bg_tertiary"), border_width=0, corner_radius=8,
                                   text_color=Theme.get("text_primary"))
        self.tg_chat.insert(0, self.config.telegram.chat_id)
        self.tg_chat.pack(fill="x")
    
    def _browse_output(self):
        from tkinter import filedialog
        path = filedialog.askdirectory()
        if path:
            self.output_entry.delete(0, "end")
            self.output_entry.insert(0, path)
    
    def _browse_cookies(self):
        from tkinter import filedialog
        path = filedialog.askopenfilename(filetypes=[("Text", "*.txt")])
        if path:
            self.cookies_entry.delete(0, "end")
            self.cookies_entry.insert(0, path)
    
    def _save_settings(self):
        try:
            self.config.output_dir = self.output_entry.get() or "./recordings"
            Path(self.config.output_dir).mkdir(parents=True, exist_ok=True)
            
            self.config.filename_pattern = self.filename_entry.get() or "{username}_{datetime}_{title}"
            
            self.config.cookies_file = self.cookies_entry.get()
            self.api.set_cookies_file(self.config.cookies_file)
            
            self.config.sound.enabled = self.sound_switch.get()
            
            self.config.telegram.enabled = self.tg_switch.get()
            self.config.telegram.bot_token = self.tg_token.get()
            self.config.telegram.chat_id = self.tg_chat.get()
            self.notifier.update_config(self.config.telegram)
            
            self.config.save()
            
            # Show success confirmation
            self._show_toast("✅ Settings saved successfully!", "success")
            
        except Exception as e:
            self._show_toast(f"❌ Failed to save: {str(e)[:50]}", "error")
    
    # ==================== UTILITIES ====================
    
    def _start_updater(self):
        def loop():
            while not self._stop.is_set():
                if self.recorder.check_status():
                    self.queue.put(("update_stats",))
                time.sleep(1)
        threading.Thread(target=loop, daemon=True).start()
    
    def _process_queue(self):
        try:
            while True:
                msg = self.queue.get_nowait()
                
                if msg[0] == "user_info":
                    self._update_user_info(msg[1])
                
                elif msg[0] == "thumbnail":
                    # Thumbnail from check user - DON'T show automatically
                    # Only store for later use if user manually toggles preview
                    pass  # Ignore - user controls preview with toggle button
                
                elif msg[0] == "preview":
                    # Only update if preview is still running
                    if self.preview.is_running:
                        img = msg[1]
                        # Store reference to prevent garbage collection
                        self._current_preview_image = ctk.CTkImage(light_image=img, dark_image=img, size=(180, 320))
                        self._show_preview_image(self._current_preview_image)
                
                elif msg[0] == "update_stats":
                    self.stat_duration.configure(text=self.recorder.get_duration())
                    self.stat_size.configure(text=self.recorder.get_file_size())
                
                elif msg[0] == "complete" or msg[0] == "stopped":
                    self._reset_record_ui()
                    self._update_history()
                
                elif msg[0] == "monitor_update":
                    self._update_watchlist()
                
                elif msg[0] == "history_thumb":
                    frame, img = msg[1], msg[2]
                    try:
                        photo = ctk.CTkImage(light_image=img, dark_image=img, size=(90, 120))
                        lbl = ctk.CTkLabel(frame, image=photo, text="")
                        lbl.place(relx=0.5, rely=0.5, anchor="center")
                    except:
                        pass
                
                elif msg[0] == "theme_changed":
                    # Show message about restart
                    pass
                
                elif msg[0] == "exit_now":
                    # Recording finished, now exit
                    self._show_toast("✅ Recording complete! Exiting...", "success")
                    self.after(1000, self._force_exit)
                        
        except queue.Empty:
            pass
        
        self.after(100, self._process_queue)
    
    def show_window(self):
        self.deiconify()
        self.lift()
        self.focus_force()
    
    def quit_app(self):
        self._on_close(force=True)
    
    def _on_close(self, force: bool = False):
        """Handle window close - ALWAYS exits (no minimize to tray)"""
        from tkinter import messagebox
        
        # Check if recording is in progress
        is_recording = self.recorder.check_status()
        multi_recording = len(self.multi.get_all()) > 0
        
        if (is_recording or multi_recording) and not force:
            # Show confirmation dialog
            result = messagebox.askyesnocancel(
                "Recording in Progress",
                "Recording is still in progress!\n\n"
                "• Yes = Wait for recording to finish, then exit\n"
                "• No = Stop recording now and exit\n"
                "• Cancel = Don't exit, continue recording",
                icon="warning"
            )
            
            if result is None:
                # Cancel - don't exit
                return
            elif result:
                # Yes - wait for recording to finish
                self._show_toast("⏳ Waiting for recording to finish...", "info")
                self._wait_and_exit()
                return
            else:
                # No - stop recording immediately
                self._force_exit()
                return
        
        # No recording - just exit immediately
        self._force_exit()
    
    def _wait_and_exit(self):
        """Wait for current recording to finish, then exit"""
        def wait_loop():
            # Wait for recording to complete naturally
            while self.recorder.check_status() or len(self.multi.get_all()) > 0:
                time.sleep(1)
            
            # Recording finished, now cleanup and exit
            self.queue.put(("exit_now",))
        
        threading.Thread(target=wait_loop, daemon=True).start()
    
    def _force_exit(self):
        """Stop everything and exit immediately - GUARANTEED"""
        self._stop.set()
        self.monitoring = False
        
        # Stop all recordings synchronously
        try:
            if self.recorder.check_status():
                self.recorder.stop()
            self.multi.stop_all()
            self.preview.stop()
            self.tray.stop()
            self.config.save()
        except:
            pass
        
        # Destroy window
        try:
            self.quit()
            self.destroy()
        except:
            pass
        
        # FORCE KILL - os._exit() cannot be caught or ignored
        # This immediately terminates the process
        os._exit(0)
    
    def _final_destroy(self):
        """Final destruction of the window"""
        try:
            self.quit()
            self.destroy()
        except:
            pass
        
        # FORCE KILL
        os._exit(0)


# ============================================================================
# MAIN
# ============================================================================

def main():
    app = TikTokApp()
    app.mainloop()


if __name__ == "__main__":
    main()
