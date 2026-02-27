import flet as ft
from flet import (
    Page, Container, Row, Column, Text, TextField, ElevatedButton,
    OutlinedButton, IconButton, Card, Dropdown, 
    FilledButton, ButtonStyle, Divider, SnackBar, Switch, TextButton,
    alignment, padding, FontWeight, CrossAxisAlignment, MainAxisAlignment,
    ScrollMode, Colors, RoundedRectangleBorder, ProgressBar, Image, Icon, margin
)
from flet import icons as icons_module
from flet import Icons
import sys
import threading
import time
import os
import subprocess
import json
import asyncio
import urllib.request

APP_VERSION = "1.0.0"
UPDATE_URL = "https://raw.githubusercontent.com/ibr3himkhaled/Vortex/main/update.json"


def check_for_updates():
    try:
        with urllib.request.urlopen(UPDATE_URL, timeout=5) as response:
            data = json.loads(response.read().decode())
            latest = data.get("version", APP_VERSION)
            return {
                "available": latest != APP_VERSION,
                "latest": latest,
                "message": data.get("message", ""),
                "download_url": data.get("download_url", ""),
            }
    except Exception:
        return None


# ============== MODELS ==============
class JobState:
    CREATED = "created"
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class FormatType:
    VIDEO = "video"
    AUDIO = "audio"


class DownloadJob:
    def __init__(self, id, url, title, is_playlist=False, thumbnail_url=None,
                 output_path=None, format_type=FormatType.VIDEO, 
                 quality="best", output_folder="", 
                 state=JobState.CREATED, progress=0.0, speed_bytes=None,
                 eta_seconds=None, error_message=None, video_format="mp4", audio_format="mp3",
                 retry_count=0, scheduled_time=None, playlist_range=None):
        self.id = id
        self.url = url
        self.title = title
        self.is_playlist = is_playlist
        self.thumbnail_url = thumbnail_url
        self.output_path = output_path
        self.format_type = format_type
        self.quality = quality
        self.video_format = video_format
        self.audio_format = audio_format
        self.output_folder = output_folder
        self.state = state
        self.progress = progress
        self.speed_bytes = speed_bytes
        self.eta_seconds = eta_seconds
        self.error_message = error_message
        self.retry_count = retry_count
        self.scheduled_time = scheduled_time
        self.playlist_range = playlist_range


class ConfigManager:
    CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    
    @staticmethod
    def save_settings(settings, is_dark=True):
        try:
            data = {
                "default_output_folder": settings.default_output_folder,
                "clipboard_monitoring": settings.clipboard_monitoring,
                "auto_retry": settings.auto_retry,
                "max_retries": settings.max_retries,
                "auto_start": settings.auto_start,
                "default_video_format": settings.default_video_format,
                "default_audio_format": settings.default_audio_format,
                "quality_preset": settings.quality_preset,
                "theme": "dark" if is_dark else "light",
                "download_history": settings.download_history[-50:],
                "recent_urls": settings.recent_urls[-20:],
            }
            with open(ConfigManager.CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except:
            pass
    
    @staticmethod
    def load_settings():
        settings = Settings()
        theme = "dark"
        try:
            if os.path.exists(ConfigManager.CONFIG_FILE):
                with open(ConfigManager.CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    settings.default_output_folder = data.get("default_output_folder", settings.default_output_folder)
                    settings.clipboard_monitoring = data.get("clipboard_monitoring", True)
                    settings.auto_retry = data.get("auto_retry", True)
                    settings.max_retries = data.get("max_retries", 3)
                    settings.auto_start = data.get("auto_start", False)
                    settings.default_video_format = data.get("default_video_format", "mp4")
                    settings.default_audio_format = data.get("default_audio_format", "mp3")
                    settings.quality_preset = data.get("quality_preset", "best")
                    settings.download_history = data.get("download_history", [])
                    settings.recent_urls = data.get("recent_urls", [])
                    theme = data.get("theme", "dark")
        except:
            pass
        return settings, theme


class Settings:
    def __init__(self):
        self.max_concurrent_downloads = 3
        self.default_output_folder = os.path.join(os.path.expanduser("~"), "Downloads")
        self.clipboard_monitoring = True
        self.auto_retry = True
        self.max_retries = 3
        self.show_notifications = True
        self.minimize_to_tray = False
        self.filename_template = "%(title)s.%(ext)s"
        self.default_video_format = "mp4"
        self.default_audio_format = "mp3"
        self.last_clipboard = ""
        self.auto_start = False
        self.quality_preset = "best"
        self.download_history = []
        self.schedule_downloads = []
        self.recent_urls = []


# ============== THEME ==============
class Theme:
    @staticmethod
    def get():
        return ft.ThemeMode.DARK
    
    @staticmethod
    def get_colors(is_dark):
        if is_dark:
            return {
                "bg": "#0F0F14",
                "card": "#1C1C26",
                "text_primary": "#FFFFFF",
                "text_secondary": "#A0A0B0",
                "text_muted": "#606070",
                "accent": "#8B5CF6",
                "success": "#22C55E",
                "error": "#EF4444",
                "warning": "#F59E0B",
            }
        else:
            return {
                "bg": "#F8F9FA",
                "card": "#FFFFFF",
                "text_primary": "#1A1A2E",
                "text_secondary": "#4A4A5A",
                "text_muted": "#9090A0",
                "accent": "#8B5CF6",
                "success": "#22C55E",
                "error": "#EF4444",
                "warning": "#F59E0B",
            }


current_theme = {"is_dark": True}
ACCENT = "#8B5CF6"
SUCCESS = "#22C55E"
ERROR = "#EF4444"
WARNING = "#F59E0B"
TEXT_PRIMARY = "#FFFFFF"
TEXT_SECONDARY = "#A0A0B0"
TEXT_MUTED = "#606070"
BG_INPUT = "#1C1C26"
BG_CARD = "#1C1C26"


# ============== Video/Audio Quality ==============
class VideoQuality:
    QUALITIES = [
        ("best", "Best Quality (4K)"),
        ("2160p", "4K (2160p)"),
        ("1440p", "2K (1440p)"),
        ("1080p", "Full HD (1080p)"),
        ("720p", "HD (720p)"),
        ("480p", "SD (480p)"),
        ("360p", "Low (360p)"),
        ("240p", "Very Low (240p)"),
        ("144p", "Lowest (144p)"),
    ]
    AUDIO_QUALITIES = [
        ("bestaudio", "Best Audio"),
        ("320", "320 kbps"),
        ("256", "256 kbps"),
        ("192", "192 kbps"),
        ("128", "128 kbps"),
    ]


class VideoFormat:
    FORMATS = [
        ("mp4", "MP4"),
        ("mkv", "MKV"),
        ("webm", "WebM"),
    ]


class AudioFormat:
    FORMATS = [
        ("mp3", "MP3"),
        ("m4a", "M4A (AAC)"),
        ("wav", "WAV"),
        ("flac", "FLAC"),
        ("ogg", "OGG Vorbis"),
        ("aac", "AAC"),
    ]


# ============== FFmpeg Helper ==============
class FFmpegHelper:
    @staticmethod
    def is_available():
        local_ffmpeg = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ffmpeg", "bin", "ffmpeg.exe")
        if os.path.exists(local_ffmpeg):
            return True
        
        if getattr(sys, 'frozen', False):
            app_dir = os.path.dirname(sys.executable)
            local_ffmpeg = os.path.join(app_dir, "ffmpeg", "bin", "ffmpeg.exe")
            if os.path.exists(local_ffmpeg):
                return True
        
        try:
            subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
            return True
        except:
            return False
    
    @staticmethod
    def get_path():
        local_ffmpeg = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ffmpeg", "bin", "ffmpeg.exe")
        if os.path.exists(local_ffmpeg):
            return local_ffmpeg
        
        if getattr(sys, 'frozen', False):
            app_dir = os.path.dirname(sys.executable)
            local_ffmpeg = os.path.join(app_dir, "ffmpeg", "bin", "ffmpeg.exe")
            if os.path.exists(local_ffmpeg):
                return local_ffmpeg
        
        return "ffmpeg"


# ============== URL ANALYZER ==============
class UrlAnalyzer:
    @staticmethod
    def analyze(url: str) -> dict:
        url_lower = url.lower()
        is_playlist = "playlist" in url_lower or "list=" in url_lower or "start_radio" in url_lower
        
        if is_playlist:
            result = {
                "title": "Playlist",
                "is_playlist": True,
                "duration": 0,
                "thumbnail": None,
                "available_qualities": [q[0] for q in VideoQuality.QUALITIES],
                "available_formats": {
                    "video": [f[0] for f in VideoFormat.FORMATS],
                    "audio": [f[0] for f in AudioFormat.FORMATS],
                },
                "platform": UrlAnalyzer._detect_platform(url),
            }
            return result
        
        import yt_dlp
        
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'format': 'best',
            'socket_timeout': 15,
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                thumbnail = None
                if info.get("thumbnail"):
                    thumbnail = info.get("thumbnail")
                elif info.get("thumbnails"):
                    thumbnails = info.get("thumbnails")
                    if isinstance(thumbnails, list) and len(thumbnails) > 0:
                        thumbnail = thumbnails[-1].get("url") if thumbnails[-1].get("url") else None
                
                result = {
                    "title": info.get("title", "Video")[:100],
                    "is_playlist": False,
                    "duration": info.get("duration", 0),
                    "thumbnail": thumbnail,
                    "available_qualities": [q[0] for q in VideoQuality.QUALITIES],
                    "available_formats": {
                        "video": [f[0] for f in VideoFormat.FORMATS],
                        "audio": [f[0] for f in AudioFormat.FORMATS],
                    },
                    "platform": UrlAnalyzer._detect_platform(url),
                }
                return result
        except Exception as e:
            result = {
                "title": "Video Title",
                "is_playlist": False,
                "duration": 600,
                "thumbnail": None,
                "available_qualities": [q[0] for q in VideoQuality.QUALITIES],
                "available_formats": {
                    "video": [f[0] for f in VideoFormat.FORMATS],
                    "audio": [f[0] for f in AudioFormat.FORMATS],
                },
                "platform": UrlAnalyzer._detect_platform(url_lower),
            }
            return result
    
    @staticmethod
    def is_supported(url: str) -> bool:
        url = url.lower()
        supported_domains = [
            "youtube", "youtu.be",
            "tiktok",
            "instagram",
            "twitter", "x.com",
            "facebook",
            "reddit",
            "twitch",
            "soundcloud",
        ]
        for domain in supported_domains:
            if domain in url:
                return True
        return False
    
    @staticmethod
    def _detect_platform(url: str) -> str:
        platforms = {
            "youtube": "YouTube",
            "youtu.be": "YouTube",
            "tiktok": "TikTok",
            "instagram": "Instagram",
            "twitter": "X",
            "x.com": "X",
            "facebook": "Facebook",
            "reddit": "Reddit",
            "twitch": "Twitch",
            "soundcloud": "SoundCloud",
        }
        for domain, name in platforms.items():
            if domain in url:
                return name
        return "Website"
    
    @staticmethod
    def get_playlist_entries(url: str) -> list:
        import yt_dlp
        
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                entries = info.get("entries", [])
                result = []
                for i, entry in enumerate(entries):
                    thumbnail = entry.get("thumbnail")
                    if not thumbnail and entry.get("thumbnails"):
                        thumbnails = entry.get("thumbnails")
                        if isinstance(thumbnails, list) and len(thumbnails) > 0:
                            thumbnail = thumbnails[-1].get("url") if thumbnails[-1].get("url") else None
                    
                    duration = entry.get("duration", 0)
                    result.append({
                        "id": i,
                        "title": entry.get("title", f"Video {i+1}"),
                        "duration": f"{duration//60}:{duration%60:02d}" if duration else "Unknown",
                        "thumbnail": thumbnail,
                        "url": entry.get("webpage_url", url),
                    })
                return result
        except Exception as e:
            return []


# ============== MAIN APP ==============
class VortexApp:
    def __init__(self, page: Page):
        self.page = page
        self.page.title = "Vortex Downloader"
        self.page.window.width = 1000
        self.page.window.height = 750
        self.page.padding = 0
        self.page.spacing = 0
        
        self.settings, saved_theme = ConfigManager.load_settings()
        
        if saved_theme == "light":
            self.page.theme_mode = ft.ThemeMode.LIGHT
            current_theme["is_dark"] = False
        else:
            self.page.theme_mode = ft.ThemeMode.DARK
            current_theme["is_dark"] = True
        
        self.page.theme = ft.Theme(
            color_scheme_seed="#8B5CF6",
        )
        
        self.page.on_keyboard_event = self._handle_keyboard
        
        self.downloads = []
        self.current_url = ""
        self.current_analysis = None
        
        self.ffmpeg_available = FFmpegHelper.is_available()
        
        self._build_ui()
        
        if self.settings.clipboard_monitoring:
            self._start_clipboard_monitoring()
        
        self._check_yt_dlp_update()
    
    def _check_yt_dlp_update(self):
        def check():
            try:
                result = subprocess.run(["pip", "show", "yt-dlp"], capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    import re
                    current_match = re.search(r'Version:\s*([\d.]+)', result.stdout)
                    current_version = current_match.group(1) if current_match else None
                    
                    result2 = subprocess.run(["pip", "index", "versions", "yt-dlp"], capture_output=True, text=True, timeout=10)
                    if result2.returncode == 0:
                        latest_match = re.search(r'LATEST:\s*([\d.]+)', result2.stdout)
                        latest_version = latest_match.group(1) if latest_match else None
                        
                        if current_version and latest_version and current_version != latest_version:
                            def show_warning():
                                snack = ft.SnackBar(
                                    content=Row(
                                        [Text(f"⚠️ yt-dlp update needed! v{current_version} → v{latest_version}  ", expand=True),
                                         FilledButton("Update Now", height=32, on_click=lambda e: self._update_yt_dlp(latest_version))],
                                        spacing=10,
                                    ),
                                    duration=15,
                                )
                                self.page.add(snack)
                                snack.open = True
                                self.page.update()
                            try:
                                self.page.run_thread(show_warning)
                            except:
                                pass
            except:
                pass
        
        threading.Thread(target=check, daemon=True).start()
    
    def _update_yt_dlp(self, latest_version):
        def update():
            try:
                result = subprocess.run(["pip", "install", "--upgrade", "yt-dlp"], capture_output=True, text=True, timeout=120)
                def show_result():
                    if result.returncode == 0:
                        snack = ft.SnackBar(content=Text(f"✅ yt-dlp updated to v{latest_version}!"), duration=5)
                    else:
                        snack = ft.SnackBar(content=Text(f"❌ Update failed"), duration=8)
                    self.page.add(snack)
                    snack.open = True
                    self.page.update()
                self.page.run_thread(show_result)
            except:
                pass
        threading.Thread(target=update, daemon=True).start()
    
    def _set_auto_start(self, enable: bool):
        try:
            app_path = os.path.abspath(__file__)
            app_name = "Vortex"
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            
            if enable:
                cmd = f'Reg Add "HKCU\\{key_path}" /v "{app_name}" /t REG_SZ /d "\\"{app_path}\\"" /f'
            else:
                cmd = f'Reg Delete "HKCU\\{key_path}" /v "{app_name}" /f'
            
            subprocess.run(cmd, shell=True, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0)
        except:
            pass
    
    def _play_completion_sound(self):
        try:
            import winsound
            winsound.PlaySound("SystemExclamation", winsound.SND_ASYNC)
        except:
            pass
    
    def _show_notification(self, title: str, message: str):
        try:
            ps_script = f'''
            [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
            [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
            $template = @"
            <toast>
                <visual>
                    <binding template="ToastText02">
                        <text id="1">{title}</text>
                        <text id="2">{message}</text>
                    </binding>
                </visual>
            </toast>
"@
            $xml = New-Object Windows.Data.Xml.Dom.XmlDocument
            $xml.LoadXml($template)
            $toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
            [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("Vortex").Show($toast)
            '''
            subprocess.Popen(["powershell", "-WindowStyle", "Hidden", "-Command", ps_script], 
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                          creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0)
        except:
            pass
    
    def _start_clipboard_monitoring(self):
        def get_clipboard_text():
            try:
                result = subprocess.run(["powershell", "-Command", "Get-Clipboard"], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0)
                return result.stdout.strip()
            except:
                return ""
        
        def monitor_clipboard():
            while True:
                try:
                    if self.settings.clipboard_monitoring:
                        clipboard_text = get_clipboard_text()
                        if clipboard_text and clipboard_text != self.settings.last_clipboard:
                            self.settings.last_clipboard = clipboard_text
                            if UrlAnalyzer.is_supported(clipboard_text):
                                def update_input():
                                    self.url_input.value = clipboard_text
                                    self._show_error("")
                                    self.page.update()
                                self.page.run_thread(update_input)
                    time.sleep(1)
                except:
                    time.sleep(1)
        
        threading.Thread(target=monitor_clipboard, daemon=True).start()
    
    def _build_ui(self):
        colors = Theme.get_colors(current_theme["is_dark"])
        
        header = Container(
            content=Row(
                [
                    Row(
                        [
                            Container(
                                content=Icon(icon=Icons.PLAY_CIRCLE_FILLED, size=32, color=ACCENT),
                                width=40, height=40,
                                border_radius=8,
                                gradient=ft.LinearGradient(colors=["#8B5CF6", "#6366F1"], begin=ft.Alignment(-1, -1), end=ft.Alignment(1, 1)),
                            ),
                            Text("Vortex", size=24, weight=FontWeight.BOLD, color=colors["text_primary"]),
                        ],
                        spacing=12,
                    ),
                    Row(
                        [
                            Container(
                                content=IconButton(icon=Icons.SETTINGS, on_click=lambda e: self._open_settings(e), tooltip="Settings"),
                                bgcolor=colors["card"],
                                border_radius=12,
                            ),
                        ],
                        spacing=8,
                    ),
                ],
                alignment=MainAxisAlignment.SPACE_BETWEEN,
            ),
            padding=padding.only(left=32, right=32, top=20, bottom=20),
            bgcolor=colors["bg"],
        )
        
        hero_section = Container(
            content=Column(
                [
                    Text("Download Videos & Audio", size=32, weight=FontWeight.BOLD, color=colors["text_primary"], text_align=ft.TextAlign.CENTER),
                    Text("Paste a URL from any platform - YouTube, TikTok, Instagram & more", size=14, color=colors["text_secondary"], text_align=ft.TextAlign.CENTER),
                ],
                horizontal_alignment=CrossAxisAlignment.CENTER,
                spacing=8,
            ),
            alignment=ft.Alignment(0, 0),
            padding=padding.only(top=32),
            bgcolor=colors["bg"],
        )
        
        self.url_input = TextField(
            hint_text="Paste video or audio URL here...",
            expand=True,
            height=52,
            text_size=14,
            border_color=colors["text_muted"],
            filled=True,
            fill_color=colors["card"],
            cursor_color=ACCENT,
            prefix_icon=Icons.LINK,
            border_radius=16,
            on_submit=self._on_download_clicked,
            on_change=self._on_url_changed,
            suffix=Container(
                content=IconButton(
                    icon=Icons.SEARCH,
                    icon_size=22,
                    width=40, height=40,
                    on_click=self._on_download_clicked,
                ),
                margin=margin.only(right=4),
            ),
        )
        
        self.download_btn = self.url_input
        
        self.error_text = Text("", color=ERROR, size=11, visible=False)
        
        search_container = Container(
            content=Column(
                [
                    Row([self.url_input], spacing=8, vertical_alignment=CrossAxisAlignment.CENTER),
                    self.error_text,
                ],
                spacing=8,
                horizontal_alignment=CrossAxisAlignment.CENTER,
            ),
            padding=padding.symmetric(horizontal=48, vertical=24),
            bgcolor=colors["bg"],
        )
        
        self.clear_completed_btn = IconButton(
            icon=Icons.DELETE_SWEEP,
            icon_size=20,
            tooltip="Clear completed",
            on_click=self._clear_completed,
        )
        
        downloads_header = Row(
            [
                Row([Icon(icon=Icons.DOWNLOAD_FOR_OFFLINE, size=22, color=colors["text_primary"]), Text("Downloads", size=18, weight=FontWeight.W_600, color=colors["text_primary"])], spacing=8),
                Text("", size=12, color=colors["text_muted"], expand=True, key="count"),
                self.clear_completed_btn,
            ],
            alignment=MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=CrossAxisAlignment.CENTER,
        )
        
        self.downloads_search_expanded = False
        
        self.search_input = TextField(
            hint_text="Search downloads...",
            height=44,
            text_size=13,
            border_color=colors["text_muted"],
            filled=True,
            fill_color=colors["card"],
            border_radius=12,
            prefix_icon=Icons.SEARCH,
            cursor_color=ACCENT,
            on_change=self._on_search_changed,
            visible=False,
        )
        
        self.downloads_search_btn = IconButton(
            icon=Icons.SEARCH,
            icon_size=22,
            width=44, height=44,
            bgcolor=colors["card"],
            on_click=self._toggle_downloads_search,
        )
        
        self.downloads_list = Column(spacing=12, scroll=ScrollMode.AUTO)
        
        self.empty_state = Container(
            content=Column(
                [
                    Container(
                        content=Icon(icon=Icons.CLOUD_DOWNLOAD_OUTLINED, size=64, color=colors["text_muted"]),
                        padding=20,
                        bgcolor=colors["card"],
                        border_radius=50,
                    ),
                    Text("No downloads yet", size=16, weight=FontWeight.W_500, color=colors["text_primary"], margin=margin.only(top=16)),
                    Text("Paste a URL above to start downloading!", size=13, color=colors["text_secondary"]),
                ],
                horizontal_alignment=CrossAxisAlignment.CENTER,
            ),
            alignment=ft.Alignment(0, 0),
            padding=padding.only(top=48),
            visible=True,
        )
        
        downloads_container = Container(
            content=Column(
                [
                    Row([downloads_header, self.downloads_search_btn], alignment=MainAxisAlignment.SPACE_BETWEEN),
                    self.search_input,
                    Container(height=1, bgcolor=colors["card"], margin=margin.only(top=4, bottom=12)),
                    self.empty_state,
                    self.downloads_list,
                ],
                spacing=0,
                scroll=ScrollMode.AUTO,
            ),
            expand=True,
            padding=padding.only(left=48, right=48, top=24, bottom=32),
            bgcolor=colors["bg"],
        )
        
        self.page.add(Column([header, hero_section, search_container, downloads_container], expand=True, spacing=0))
    
    def _on_url_changed(self, e):
        url = e.control.value.strip()
        if url and not UrlAnalyzer.is_supported(url):
            e.control.value = ""
            self._show_error("Unsupported URL")
            return
        if url:
            self._show_error("")
    
    def _on_download_clicked(self, e):
        text = self.url_input.value.strip() if self.url_input.value else ""
        
        if not text:
            self._show_error("Please enter a URL")
            return
        
        urls = [u.strip() for u in text.split('\n') if u.strip()]
        
        if not urls:
            self._show_error("Please enter a valid URL")
            return
        
        valid_urls = [u for u in urls if UrlAnalyzer.is_supported(u)]
        
        if not valid_urls:
            self._show_error("No supported URLs found")
            return
        
        if len(valid_urls) == 1:
            self.current_url = valid_urls[0]
            self._analyze_and_download(valid_urls[0])
        else:
            self._process_batch_urls(valid_urls)
    
    def _analyze_and_download(self, url):
        if url not in self.settings.recent_urls:
            self.settings.recent_urls.insert(0, url)
            self.settings.recent_urls = self.settings.recent_urls[:20]
            ConfigManager.save_settings(self.settings, current_theme["is_dark"])
        
        self.download_btn.disabled = True
        self.download_btn.icon = Icons.HOURGLASS_TOP
        self.page.update()
        
        def analyze_and_show():
            analysis = None
            error_msg = None
            
            try:
                analysis = UrlAnalyzer.analyze(url)
            except Exception as ex:
                error_msg = str(ex)
            
            def show_result():
                if error_msg:
                    self._show_error(f"Error: {str(error_msg)}")
                    self.download_btn.disabled = False
                    self.download_btn.icon = Icons.SEARCH
                elif analysis:
                    self.current_analysis = analysis
                    self._show_download_options(analysis)
                    self.download_btn.disabled = False
                    self.download_btn.icon = Icons.SEARCH
                else:
                    self._show_error("Could not analyze URL")
                    self.download_btn.disabled = False
                    self.download_btn.icon = Icons.SEARCH
                self.page.update()
            
            self.page.run_thread(show_result)
        
        threading.Thread(target=analyze_and_show, daemon=True).start()
    
    def _process_batch_urls(self, urls):
        self.url_input.value = ""
        self._show_error("", visible=False)
        
        for url in urls:
            job = DownloadJob(
                id=str(hash(url) + int(time.time())),
                url=url,
                title=f"Batch: {url[:30]}...",
                format_type=FormatType.VIDEO,
                quality=self.settings.quality_preset,
                video_format=self.settings.default_video_format,
                audio_format=self.settings.default_audio_format,
                output_folder=self.settings.default_output_folder,
                state=JobState.QUEUED,
            )
            self.downloads.insert(0, job)
            threading.Thread(target=self._start_actual_download, args=(job,), daemon=True).start()
        
        self._refresh_list()
        self._show_notification("Vortex", f"Started downloading {len(urls)} videos")
    
    def _show_download_options(self, analysis: dict):
        colors = Theme.get_colors(current_theme["is_dark"])
        
        title = analysis.get("title", "Video")
        platform = analysis.get("platform", "Website")
        thumbnail = analysis.get("thumbnail")
        
        platform_colors = {"YouTube": "#FF0000", "TikTok": "#00F2EA", "Instagram": "#E4405F", "X": "#1DA1F2", "Facebook": "#1877F2"}
        platform_color = platform_colors.get(platform, TEXT_MUTED)
        
        self._format_btns = {"video": None, "audio": None}
        
        def make_video_btn(e):
            self._update_format_options("video")
            
        def make_audio_btn(e):
            self._update_format_options("audio")
        
        video_btn = Container(
            content=Row([Icon(icon=Icons.VIDEOCAM, size=18), Text("Video", size=14, weight=FontWeight.W_500)], spacing=8),
            padding=padding.symmetric(horizontal=20, vertical=12),
            bgcolor=ACCENT,
            border_radius=12,
            on_click=make_video_btn,
            expand=True,
            alignment=ft.Alignment(0, 0),
        )
        
        audio_btn = Container(
            content=Row([Icon(icon=Icons.AUDIOTRACK, size=18), Text("Audio", size=14, weight=FontWeight.W_500)], spacing=8),
            padding=padding.symmetric(horizontal=20, vertical=12),
            bgcolor=colors["card"],
            border_radius=12,
            on_click=make_audio_btn,
            expand=True,
            alignment=ft.Alignment(0, 0),
        )
        
        self._format_btns["video"] = video_btn
        self._format_btns["audio"] = audio_btn
        
        quality_dropdown = Dropdown(width=280, value="best", options=[ft.dropdown.Option(q[0], q[1]) for q in VideoQuality.QUALITIES], filled=True, fill_color=colors["card"])
        
        self.format_dropdown = Dropdown(width=140, value="mp4", options=[ft.dropdown.Option(f[0], f[1]) for f in VideoFormat.FORMATS], filled=True, fill_color=colors["card"])
        
        self.dialog_folder_input = TextField(
            value=self.settings.default_output_folder,
            expand=True,
            height=48,
            text_size=13,
            prefix_icon=Icons.FOLDER_OPEN,
            border_color=Colors.TRANSPARENT,
            filled=True,
            fill_color=colors["card"],
            read_only=True,
            on_click=self._pick_folder_dialog,
        )
        
        self._dialog_video_btn = video_btn
        self._dialog_audio_btn = audio_btn
        self._dialog_quality = quality_dropdown
        self._dialog_format_type = "video"
        
        thumbnail_preview = Container()
        if thumbnail:
            thumbnail_preview = Container(content=Image(src=thumbnail, width=120, height=68, border_radius=8), margin=margin.only(bottom=16))
        
        playlist_section = Container()
        if analysis.get("is_playlist"):
            self._is_playlist = True
            self.playlist_start = TextField(
                hint_text="1",
                width=70, height=40,
                text_size=14,
                border_color=colors["text_muted"],
                filled=True, fill_color=colors["bg"],
                border_radius=10,
                cursor_color=ACCENT,
            )
            self.playlist_end = TextField(
                hint_text="All",
                width=70, height=40,
                text_size=14,
                border_color=colors["text_muted"],
                filled=True, fill_color=colors["bg"],
                border_radius=10,
                cursor_color=ACCENT,
            )
            playlist_section = Container(
                content=Column([
                    Row([
                        Icon(icon=Icons.LIST, size=24, color=colors["text_secondary"]),
                        Column([
                            Text("Playlist Detected", size=14, weight=FontWeight.W_600, color=colors["text_primary"]),
                            Text("Select video range to download", size=11, color=colors["text_muted"]),
                        ], spacing=2, expand=True),
                    ], spacing=10),
                    Container(height=12),
                    Row([
                        Text("From", size=12, color=colors["text_secondary"]),
                        self.playlist_start,
                        Text("to", size=12, color=colors["text_secondary"]),
                        self.playlist_end,
                    ], spacing=6, vertical_alignment=CrossAxisAlignment.CENTER),
                ], spacing=0),
                bgcolor=colors["card"],
                padding=16,
                border_radius=14,
                margin=margin.only(top=16),
            )
        
        self.schedule_switch = Switch(value=False, on_change=self._on_schedule_toggled)
        self.schedule_time_picker = ft.TimePicker(confirm_text="OK", cancel_text="Cancel", on_change=self._on_time_selected)
        self.schedule_time_container = Container(visible=False, content=Row([
            Text("Download at: ", size=13, color=colors["text_secondary"]),
            TextButton("Pick Time", icon=Icons.ACCESS_TIME, on_click=lambda e: self._open_time_picker()),
        ], spacing=12), margin=margin.only(top=8))
        
        self.download_dialog = ft.AlertDialog(
            modal=True,
            bgcolor=colors["bg"],
            shape=ft.RoundedRectangleBorder(radius=24),
            content=Container(
                content=ft.Column(
                    [
                        Row(
                            [
                                thumbnail_preview,
                                Column(
                                    [
                                        Text(title[:60], size=16, weight=FontWeight.W_600, color=colors["text_primary"], max_lines=2),
                                        Row(
                                            [
                                                Container(content=Text(platform, size=10, color=platform_color, weight=FontWeight.W_500), bgcolor=platform_color + "22", padding=padding.symmetric(horizontal=8, vertical=4), border_radius=6),
                                                Text(f"Duration: {analysis.get('duration', 0)//60}:{analysis.get('duration', 0)%60:02d}", size=11, color=colors["text_muted"]) if analysis.get("duration") else Container(),
                                            ],
                                            spacing=8,
                                        ),
                                    ],
                                    spacing=4,
                                    expand=True,
                                ),
                            ],
                            spacing=16,
                        ),
                        Container(height=1, bgcolor=colors["card"], margin=margin.symmetric(vertical=16)),
                        Text("Download As", size=13, weight=FontWeight.W_600, color=colors["text_secondary"]),
                        Container(content=Row([video_btn, audio_btn], spacing=12), margin=margin.only(top=8, bottom=20)),
                        Row(
                            [
                                Column([Text("Quality", size=13, weight=FontWeight.W_600, color=colors["text_secondary"]), Container(content=quality_dropdown, margin=margin.only(top=4))], spacing=0),
                                Column([Text("Format", size=13, weight=FontWeight.W_600, color=colors["text_secondary"]), Container(content=self.format_dropdown, margin=margin.only(top=4))], spacing=0),
                            ],
                            spacing=24,
                        ),
                        Text("Save to", size=13, weight=FontWeight.W_600, color=colors["text_secondary"], margin=margin.only(top=16)),
                        Container(content=self.dialog_folder_input, margin=margin.only(top=4)),
                        playlist_section,
                        Container(
                            content=Row([
                                Icon(icon=Icons.SCHEDULE, size=20, color=colors["text_secondary"]),
                                Text("Schedule", size=14, weight=FontWeight.W_500, color=colors["text_primary"]),
                                self.schedule_switch,
                            ], spacing=12),
                            margin=margin.only(top=16),
                        ),
                        self.schedule_time_container,
                    ],
                    spacing=0,
                    tight=True,
                ),
                width=500,
                padding=padding.all(24),
            ),
            actions=[
                Row(
                    [TextButton("Cancel", on_click=self._close_download_dialog), FilledButton("Start Download", icon=Icons.DOWNLOAD, on_click=self._start_download_with_options)],
                    alignment=MainAxisAlignment.END,
                    spacing=12,
                )
            ],
            actions_padding=padding.only(left=24, right=24, bottom=20, top=8),
        )
        
        self._is_playlist = analysis.get("is_playlist", False)
        self._playlist_entries = []
        self._scheduled_time = None
        
        self.page.show_dialog(self.download_dialog)
        self.page.update()
    
    def _on_schedule_toggled(self, e):
        is_on = e.control.value
        self.schedule_time_container.visible = is_on
        self.page.update()
    
    def _open_time_picker(self, e=None):
        self.page.show_dialog(self.schedule_time_picker)
    
    def _on_time_selected(self, e):
        if e.control.value:
            self._scheduled_time = e.control.value
            self.page.pop_dialog()
            self.page.update()
    
    def _update_format_options(self, format_type: str):
        self._dialog_format_type = format_type
        colors = Theme.get_colors(current_theme["is_dark"])
        
        if format_type == "video":
            self._format_btns["video"].bgcolor = ACCENT
            self._format_btns["audio"].bgcolor = colors["card"]
            self._dialog_quality.options = [ft.dropdown.Option(q[0], q[1]) for q in VideoQuality.QUALITIES]
            self._dialog_quality.value = "best"
            self.format_dropdown.options = [ft.dropdown.Option(f[0], f[1]) for f in VideoFormat.FORMATS]
            self.format_dropdown.value = "mp4"
        else:
            self._format_btns["audio"].bgcolor = ACCENT
            self._format_btns["video"].bgcolor = colors["card"]
            self._dialog_quality.options = [ft.dropdown.Option(q[0], q[1]) for q in VideoQuality.AUDIO_QUALITIES]
            self._dialog_quality.value = "bestaudio"
            self.format_dropdown.options = [ft.dropdown.Option(f[0], f[1]) for f in AudioFormat.FORMATS]
            self.format_dropdown.value = "mp3"
        
        self.page.update()
    
    def _close_download_dialog(self, e):
        self.page.pop_dialog()
        self.download_btn.disabled = False
        self.download_btn.icon = Icons.SEARCH
        self.page.update()
    
    def _pick_folder_dialog(self, e):
        ps_script = '''Add-Type -AssemblyName System.Windows.Forms; $dialog = New-Object System.Windows.Forms.FolderBrowserDialog; $dialog.Description = "Select Download Folder"; $dialog.ShowNewFolderButton = $true; if ($dialog.ShowDialog() -eq "OK") { Write-Output $dialog.SelectedPath }'''
        try:
            result = subprocess.run(["powershell", "-Command", ps_script], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0)
            folder = result.stdout.strip()
            if folder:
                self.dialog_folder_input.value = folder
                self.settings.default_output_folder = folder
                self.page.update()
        except:
            pass
    
    def _start_download_with_options(self, e):
        self.page.pop_dialog()
        
        format_type = self._dialog_format_type
        quality = self._dialog_quality.value
        selected_format = self.format_dropdown.value
        
        is_scheduled = hasattr(self, 'schedule_switch') and self.schedule_switch.value
        scheduled_time = self._scheduled_time if is_scheduled else None
        
        playlist_range = None
        if hasattr(self, '_is_playlist') and self._is_playlist:
            try:
                start = int(self.playlist_start.value) if self.playlist_start.value else 1
                end = int(self.playlist_end.value) if self.playlist_end.value else None
                if start > 0:
                    playlist_range = (start, end)
            except:
                pass
        
        job = DownloadJob(
            id=str(hash(self.current_url) + int(time.time())),
            url=self.current_url,
            title=self.current_analysis.get("title", "Video") if self.current_analysis else "Video",
            thumbnail_url=self.current_analysis.get("thumbnail") if self.current_analysis else None,
            format_type=format_type,
            quality=quality,
            video_format=selected_format if format_type == "video" else "mp4",
            audio_format=selected_format if format_type == "audio" else "mp3",
            output_folder=self.settings.default_output_folder,
            state=JobState.QUEUED if is_scheduled else JobState.DOWNLOADING,
            playlist_range=playlist_range,
        )
        
        if is_scheduled and scheduled_time:
            job.scheduled_time = scheduled_time
            self.settings.schedule_downloads.append({"job": job, "scheduled_time": scheduled_time})
            self.downloads.insert(0, job)
            self._refresh_list()
            threading.Thread(target=self._schedule_download, args=(job, scheduled_time), daemon=True).start()
        else:
            existing_file = self._check_file_exists(job)
            if os.path.exists(existing_file):
                self._show_file_exists_dialog(job, existing_file)
            else:
                self._proceed_with_download(job)
        
        self.url_input.value = ""
        self._show_error("", visible=False)
        self.download_btn.disabled = False
        self.download_btn.icon = Icons.SEARCH
        self.page.update()
    
    def _schedule_download(self, job: DownloadJob, scheduled_time):
        from datetime import datetime, timedelta
        now = datetime.now()
        scheduled_dt = now.replace(hour=scheduled_time.hour, minute=scheduled_time.minute, second=0, microsecond=0)
        if scheduled_dt <= now:
            scheduled_dt += timedelta(days=1)
        wait_seconds = (scheduled_dt - now).total_seconds()
        time.sleep(wait_seconds)
        job.state = JobState.DOWNLOADING
        def update():
            self._refresh_list()
        self.page.run_thread(update)
        self._start_actual_download(job)
    
    def _get_potential_filename(self, job: DownloadJob) -> str:
        output_folder = job.output_folder or self.settings.default_output_folder
        ext = job.audio_format if job.format_type == "audio" else job.video_format
        title = job.title
        for c in r'<>:"/\|?*':
            title = title.replace(c, '_')
        return os.path.join(output_folder, f"{title}.{ext}")
    
    def _check_file_exists(self, job: DownloadJob) -> str:
        filename = self._get_potential_filename(job)
        if os.path.exists(filename):
            return filename
        base, ext = os.path.splitext(filename)
        counter = 1
        while os.path.exists(f"{base} ({counter}){ext}"):
            counter += 1
        return f"{base} ({counter}){ext}"
    
    def _show_file_exists_dialog(self, job: DownloadJob, existing_file: str):
        def handle_overwrite(e):
            self.page.pop_dialog()
            self._proceed_with_download(job, overwrite=True)
        
        def handle_skip(e):
            self.page.pop_dialog()
            job.state = JobState.CANCELLED
            self._refresh_list()
        
        def handle_rename(e):
            self.page.pop_dialog()
            self._proceed_with_download(job, overwrite=False)
        
        colors = Theme.get_colors(current_theme["is_dark"])
        filename = os.path.basename(existing_file)
        
        dialog = ft.AlertDialog(
            modal=True,
            bgcolor=colors["bg"],
            shape=ft.RoundedRectangleBorder(radius=20),
            content=Container(
                content=Column([
                    Row([Icon(icon=Icons.WARNING_AMBER_ROUNDED, size=40, color=WARNING)], alignment=MainAxisAlignment.CENTER),
                    Container(height=16),
                    Text("File Already Exists", size=18, weight=FontWeight.BOLD, color=colors["text_primary"], text_align=ft.TextAlign.CENTER),
                    Container(height=8),
                    Text(filename, size=13, color=colors["text_secondary"], text_align=ft.TextAlign.CENTER, max_lines=2),
                    Container(height=20),
                    Row([
                        OutlinedButton("Skip", on_click=handle_skip, expand=1),
                        FilledButton("Rename", on_click=handle_rename, expand=1),
                        FilledButton("Overwrite", bgcolor=ERROR, on_click=handle_overwrite, expand=1),
                    ], spacing=12, alignment=MainAxisAlignment.CENTER),
                ], spacing=0, horizontal_alignment=CrossAxisAlignment.CENTER),
                width=380,
                padding=padding.all(24),
            ),
        )
        self.page.show_dialog(dialog)
    
    def _proceed_with_download(self, job: DownloadJob, overwrite: bool = False):
        self.downloads.insert(0, job)
        self._refresh_list()
        
        threading.Thread(target=self._start_actual_download, args=(job, overwrite), daemon=True).start()
    
    def _start_actual_download(self, job: DownloadJob, overwrite: bool = False):
        try:
            output_folder = job.output_folder or self.settings.default_output_folder
            
            if job.format_type == "audio" and job.audio_format:
                output_template = os.path.join(output_folder, f"%(title)s.{job.audio_format}")
            else:
                output_template = os.path.join(output_folder, "%(title)s.%(ext)s")
            
            if job.format_type == "audio":
                if job.audio_format == "mp3":
                    format_selector = "bestaudio/best"
                    postprocessors = []
                elif job.audio_format == "wav":
                    format_selector = "bestaudio/best"
                    postprocessors = []
                elif job.audio_format == "flac":
                    format_selector = "bestaudio/best"
                    postprocessors = []
                elif job.audio_format == "m4a":
                    format_selector = "bestaudio[ext=m4a]/bestaudio/best"
                    postprocessors = []
                else:
                    format_selector = "bestaudio"
                    postprocessors = []
            else:
                quality = job.quality
                if quality == "best" or quality == "2160p":
                    format_selector = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
                elif quality == "1440p":
                    format_selector = "bestvideo[height<=1440][ext=mp4]+bestaudio[ext=m4a]/best[height<=1440][ext=mp4]/best"
                elif quality == "1080p":
                    format_selector = "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best"
                elif quality == "720p":
                    format_selector = "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best"
                elif quality == "480p":
                    format_selector = "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480][ext=mp4]/best"
                elif quality == "360p":
                    format_selector = "bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/best[height<=360][ext=mp4]/best"
                elif quality == "240p":
                    format_selector = "bestvideo[height<=240][ext=mp4]+bestaudio[ext=m4a]/best[height<=240][ext=mp4]/best"
                elif quality == "144p":
                    format_selector = "bestvideo[height<=144][ext=mp4]+bestaudio[ext=m4a]/best[height<=144][ext=mp4]/best"
                else:
                    format_selector = "best"
                postprocessors = []
            
            cmd = ["python", "-m", "yt_dlp", "-f", format_selector, "-o", output_template, "--newline", "--no-warnings"]
            if not overwrite:
                cmd.append("--no-overwrites")
            if job.format_type == "audio":
                if job.audio_format == "mp3":
                    cmd.extend(["--audio-format", "mp3", "--audio-quality", "0"])
                elif job.audio_format == "m4a":
                    cmd.extend(["--audio-format", "m4a"])
                elif job.audio_format == "wav":
                    cmd.extend(["--audio-format", "wav"])
                elif job.audio_format == "flac":
                    cmd.extend(["--audio-format", "flac"])
            if job.playlist_range:
                start, end = job.playlist_range
                cmd.extend(["--playlist-start", str(start)])
                if end:
                    cmd.extend(["--playlist-end", str(end)])
            cmd.append(job.url)
            
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
            
            import re
            percent_re = re.compile(r"(\d+(?:\.\d+)?)%")
            speed_re = re.compile(r"at\s+([\d.]+)([KMG]i?)?B/s")
            eta_re = re.compile(r"ETA\s+(\d+):(\d+)")
            
            for line in process.stdout:
                line = line.strip()
                if not line:
                    continue
                
                percent_match = percent_re.search(line)
                if percent_match:
                    job.progress = float(percent_match.group(1)) / 100
                
                speed_match = speed_re.search(line)
                if speed_match:
                    speed_val = float(speed_match.group(1))
                    unit = speed_match.group(2)
                    if unit and unit.startswith("K"):
                        job.speed_bytes = speed_val * 1024
                    elif unit and unit.startswith("M"):
                        job.speed_bytes = speed_val * 1024 * 1024
                    elif unit and unit.startswith("G"):
                        job.speed_bytes = speed_val * 1024 * 1024 * 1024
                    else:
                        job.speed_bytes = speed_val
                
                eta_match = eta_re.search(line)
                if eta_match:
                    minutes = int(eta_match.group(1))
                    seconds = int(eta_match.group(2))
                    job.eta_seconds = minutes * 60 + seconds
                
                def update():
                    self._refresh_list()
                self.page.run_thread(update)
            
            process.wait()
            
            if process.returncode == 0:
                job.state = JobState.COMPLETED
                job.progress = 1.0
                self.settings.download_history.append({"url": job.url, "title": job.title, "format": job.audio_format if job.format_type == "audio" else job.video_format, "quality": job.quality, "date": time.strftime("%Y-%m-%d %H:%M")})
                ConfigManager.save_settings(self.settings, current_theme["is_dark"])
                self._play_completion_sound()
                self._show_notification("Download Complete", f"{job.title[:30]} downloaded successfully")
            else:
                stderr = process.stderr.read() if process.stderr else ""
                job.state = JobState.FAILED
                job.error_message = stderr[:200] if stderr else "Download failed"
                self._show_notification("Download Failed", f"Failed to download {job.title[:30]}")
            
            if job.state == JobState.FAILED and self.settings.auto_retry:
                job.retry_count += 1
                if job.retry_count < self.settings.max_retries:
                    job.state = JobState.QUEUED
                    time.sleep(2 ** job.retry_count)
                    job.state = JobState.DOWNLOADING
                    self._start_actual_download(job)
        
        except Exception as e:
            job.state = JobState.FAILED
            job.error_message = str(e)
        
        def update():
            self._refresh_list()
        self.page.run_thread(update)
    
    def _refresh_list(self, search_query: str = ""):
        self.downloads_list.controls.clear()
        filtered = self.downloads
        if search_query:
            filtered = [j for j in self.downloads if search_query in j.title.lower() or search_query in j.url.lower()]
        for job in filtered:
            card = self._create_download_card(job)
            self.downloads_list.controls.append(card)
        self.empty_state.visible = len(filtered) == 0
        self.page.update()
    
    def _create_download_card(self, job: DownloadJob) -> Container:
        status_color = TEXT_SECONDARY
        if job.state == JobState.DOWNLOADING:
            status_color = ACCENT
        elif job.state == JobState.COMPLETED:
            status_color = SUCCESS
        elif job.state == JobState.FAILED:
            status_color = ERROR
        
        status_text = str(job.state).capitalize()
        if job.state == JobState.DOWNLOADING:
            speed = job.speed_bytes / 1024 / 1024 if job.speed_bytes else 0
            status_text = f"Downloading {int(job.progress * 100)}% - {speed:.1f} MB/s"
        elif job.state == JobState.COMPLETED:
            fmt = job.audio_format if job.format_type == "audio" else job.video_format
            status_text = f"Completed ({fmt.upper()})"
        
        platform = self._detect_platform(job.url)
        
        progress = None
        if job.state == JobState.DOWNLOADING:
            progress = Container(content=ft.ProgressBar(value=job.progress, color=ACCENT))
        
        thumbnail_content = None
        if job.thumbnail_url:
            thumbnail_content = Image(src=job.thumbnail_url, width=100, height=56, border_radius=8)
        else:
            thumbnail_content = IconButton(icon=Icons.VIDEOCAM, icon_color=TEXT_MUTED)
        
        return Container(
            content=Row(
                [
                    Container(width=100, height=56, bgcolor=BG_INPUT, border_radius=8, clip_behavior=ft.ClipBehavior.ANTI_ALIAS, content=thumbnail_content),
                    Column(
                        [
                            Row(
                                [
                                    Text(job.title[:40] + "..." if len(job.title) > 40 else job.title, size=14, weight=FontWeight.W_500, color=TEXT_PRIMARY),
                                    Container(Text(platform[0], size=10, color=platform[1]), bgcolor=platform[1] + "22", padding=padding.only(left=6, right=6, top=2, bottom=2), border_radius=4),
                                    Container(Text(job.quality.upper(), size=10, color=ACCENT), bgcolor=ACCENT + "22", padding=padding.only(left=6, right=6, top=2, bottom=2), border_radius=4),
                                ],
                                spacing=8,
                            ),
                            Text(status_text, size=12, color=status_color),
                            progress or Container(),
                        ],
                        spacing=4,
                        expand=True,
                    ),
                    Column(
                        [
                            Row(
                                [
                                    IconButton(icon=Icons.PAUSE if job.state == JobState.DOWNLOADING else Icons.PLAY_ARROW, icon_size=18, on_click=lambda e, j=job: self._toggle_pause(j)),
                                    IconButton(icon=Icons.CLOSE, icon_size=18, on_click=lambda e, j=job: self._cancel_download(j)),
                                    IconButton(icon=Icons.ARROW_UPWARD, icon_size=16, on_click=lambda e, j=job: self._move_job(j, -1)),
                                    IconButton(icon=Icons.ARROW_DOWNWARD, icon_size=16, on_click=lambda e, j=job: self._move_job(j, 1)),
                                ],
                                spacing=2,
                            ),
                            Row(
                                [
                                    IconButton(icon=Icons.FOLDER_OPEN, icon_size=16, tooltip="Open folder", on_click=lambda e, j=job: self._open_folder(j)) if job.state == JobState.COMPLETED else Container(),
                                    IconButton(icon=Icons.COPY, icon_size=16, tooltip="Copy URL", on_click=lambda e, j=job: self._copy_url(j)),
                                ],
                                spacing=2,
                            ),
                        ],
                        spacing=2,
                    ),
                ],
                spacing=12,
                vertical_alignment=CrossAxisAlignment.CENTER,
            ),
            padding=12,
            border_radius=12,
            bgcolor=BG_CARD,
        )
    
    def _detect_platform(self, url: str):
        url = url.lower()
        platforms = {"youtube": ("YouTube", "#FF0000"), "youtu.be": ("YouTube", "#FF0000"), "tiktok": ("TikTok", "#00F2EA"), "instagram": ("Instagram", "#E4405F"), "twitter": ("X", "#1DA1F2"), "x.com": ("X", "#1DA1F2"), "facebook": ("Facebook", "#1877F2"), "reddit": ("Reddit", "#FF4500"), "twitch": ("Twitch", "#9146FF"), "soundcloud": ("SoundCloud", "#FF5500")}
        for domain, info in platforms.items():
            if domain in url:
                return info
        return ("Website", TEXT_MUTED)
    
    def _toggle_pause(self, job: DownloadJob):
        if job.state == JobState.DOWNLOADING:
            job.state = JobState.PAUSED
        elif job.state == JobState.PAUSED:
            job.state = JobState.DOWNLOADING
        self._refresh_list()
    
    def _cancel_download(self, job: DownloadJob):
        job.state = JobState.CANCELLED
        if job in self.downloads:
            self.downloads.remove(job)
        self._refresh_list()
    
    def _move_job(self, job: DownloadJob, direction: int):
        if job not in self.downloads:
            return
        idx = self.downloads.index(job)
        new_idx = idx + direction
        if 0 <= new_idx < len(self.downloads):
            self.downloads.insert(new_idx, self.downloads.pop(idx))
            self._refresh_list()
    
    def _open_folder(self, job: DownloadJob):
        folder = job.output_folder or self.settings.default_output_folder
        try:
            os.startfile(folder)
        except:
            pass
    
    def _copy_url(self, job: DownloadJob):
        try:
            subprocess.run(["powershell", "-Command", f"Set-Clipboard -Value '{job.url}'"], 
                         capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0)
        except:
            pass
    
    def _toggle_downloads_search(self, e):
        self.downloads_search_expanded = not self.downloads_search_expanded
        self.search_input.visible = self.downloads_search_expanded
        self.downloads_search_btn.icon = Icons.CLOSE if self.downloads_search_expanded else Icons.SEARCH
        if not self.downloads_search_expanded:
            self.search_input.value = ""
            self._refresh_list("")
        self.page.update()
    
    def _clear_completed(self, e):
        self.downloads = [j for j in self.downloads if j.state != JobState.COMPLETED]
        self._refresh_list()
    
    def _on_search_changed(self, e):
        query = e.control.value.lower() if e.control.value else ""
        self._refresh_list(query)
    
    def _handle_keyboard(self, e: ft.KeyboardEvent):
        if e.ctrl and e.key == "v":
            try:
                import subprocess
                result = subprocess.run(["powershell", "-Command", "Get-Clipboard"], 
                                      capture_output=True, text=True, 
                                      creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0)
                clipboard_text = result.stdout.strip()
                if clipboard_text and UrlAnalyzer.is_supported(clipboard_text.split('\n')[0] if '\n' in clipboard_text else clipboard_text):
                    self.url_input.value = clipboard_text
                    self.page.update()
            except:
                pass
        elif e.key == "enter" and not self.download_btn.disabled:
            self._on_download_clicked(None)
    
    def _show_error(self, msg: str, visible: bool = True):
        self.error_text.value = msg
        self.error_text.visible = visible
        self.page.update()
    
    def _open_settings(self, e=None):
        colors = Theme.get_colors(current_theme["is_dark"])
        
        self.settings_clipboard = Switch(value=self.settings.clipboard_monitoring)
        self.settings_auto_retry = Switch(value=self.settings.auto_retry)
        self.settings_auto_start = Switch(value=self.settings.auto_start)
        self.dark_mode_switch = Switch(value=True if self.page.theme_mode == ft.ThemeMode.DARK else False)
        
        self.folder_input = TextField(
            value=self.settings.default_output_folder,
            expand=True,
            height=44,
            text_size=13,
            prefix_icon=Icons.FOLDER_OPEN,
            border_color=Colors.TRANSPARENT,
            filled=True,
            fill_color=colors["card"],
            border_radius=10,
            read_only=True,
            on_click=self._pick_folder,
        )
        
        self.update_btn_text = Text("Check", size=13, weight=FontWeight.W_500)
        self.update_btn = OutlinedButton(
            content=self.update_btn_text,
            height=36,
            on_click=self._check_for_updates
        )
        self.update_status = Text("", size=13, color=colors["text_muted"])
        
        self.settings_dialog = ft.AlertDialog(
            modal=True,
            bgcolor=colors["bg"],
            content=Container(
                content=Column(
                    [
                        Text("Settings", size=24, weight=FontWeight.BOLD, color=colors["text_primary"]),
                        Container(height=24),
                        Container(content=Row([Icon(icon=Icons.DARK_MODE, size=24), Text("Dark Mode", size=15, weight=FontWeight.W_500, color=colors["text_primary"], expand=True), self.dark_mode_switch], spacing=12), padding=14, bgcolor=colors["card"], border_radius=14),
                        Container(height=14),
                        Column([Text("Download Location", size=15, weight=FontWeight.W_500, color=colors["text_primary"]), Text("Choose where to save your files", size=12, color=colors["text_secondary"]), Container(height=8), self.folder_input], spacing=4, horizontal_alignment=CrossAxisAlignment.START),
                        Container(height=14),
                        Container(content=Row([Icon(icon=Icons.CONTENT_PASTE, size=22), Text("Auto-detect clipboard URLs", size=14, color=colors["text_primary"], expand=True), self.settings_clipboard], spacing=12), padding=14, bgcolor=colors["card"], border_radius=12),
                        Container(height=8),
                        Container(content=Row([Icon(icon=Icons.REPLAY, size=22), Text("Retry failed downloads", size=14, color=colors["text_primary"], expand=True), self.settings_auto_retry], spacing=12), padding=14, bgcolor=colors["card"], border_radius=12),
                        Container(height=8),
                        Container(content=Row([Icon(icon=Icons.POWER_SETTINGS_NEW, size=22), Text("Start with Windows", size=14, color=colors["text_primary"], expand=True), self.settings_auto_start], spacing=12), padding=14, bgcolor=colors["card"], border_radius=12),
                        Container(height=16),
                        Container(
                            content=Row([
                                Icon(icon=Icons.UPDATE, size=22),
                                Column([
                                    Text("Version", size=15, weight=FontWeight.W_500, color=colors["text_primary"]),
                                    Text(f"v{APP_VERSION}", size=12, color=colors["text_secondary"]),
                                ], spacing=2, expand=True),
                                self.update_btn,
                            ], spacing=12),
                            padding=16,
                            bgcolor=colors["card"],
                            border_radius=14,
                        ),
                        self.update_status,
                    ],
                    spacing=0,
                ),
                width=400,
                padding=padding.all(24),
            ),
            actions=[
                Row(
                    [TextButton("Cancel", on_click=lambda x: self.page.pop_dialog()), FilledButton("Done", height=42, style=ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10)), on_click=self._save_settings)],
                    alignment=MainAxisAlignment.END,
                    spacing=12,
                )
            ],
            actions_padding=padding.only(left=24, right=24, bottom=18, top=10),
        )
        
        self.page.show_dialog(self.settings_dialog)
    
    def _pick_folder(self, e):
        ps_script = '''Add-Type -AssemblyName System.Windows.Forms; $dialog = New-Object System.Windows.Forms.FolderBrowserDialog; $dialog.Description = "Select Download Folder"; $dialog.ShowNewFolderButton = $true; if ($dialog.ShowDialog() -eq "OK") { Write-Output $dialog.SelectedPath }'''
        try:
            result = subprocess.run(["powershell", "-Command", ps_script], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0)
            folder = result.stdout.strip()
            if folder:
                self.folder_input.value = folder
                self.settings.default_output_folder = folder
                self.page.update()
        except:
            pass
    
    def _save_settings(self, e):
        self.settings.clipboard_monitoring = self.settings_clipboard.value
        self.settings.auto_retry = self.settings_auto_retry.value
        self.settings.auto_start = self.settings_auto_start.value
        
        self._set_auto_start(self.settings.auto_start)
        
        was_dark = current_theme["is_dark"]
        is_dark = self.dark_mode_switch.value
        
        ConfigManager.save_settings(self.settings, is_dark)
        
        if is_dark:
            self.page.theme_mode = ft.ThemeMode.DARK
        else:
            self.page.theme_mode = ft.ThemeMode.LIGHT
        
        current_theme["is_dark"] = is_dark
        
        self.page.pop_dialog()
        
        if was_dark != is_dark:
            self.page.controls.clear()
            self._build_ui()
        else:
            self._refresh_list()
        self.page.update()
    
    def _check_for_updates(self, e):
        self.update_btn.disabled = True
        self.update_btn_text.value = "..."
        self.update_status.value = ""
        self.page.update()
        
        def check():
            result = check_for_updates()
            
            def show_result():
                self.update_btn.disabled = False
                
                if result is None:
                    self.update_status.value = "Unable to check"
                    self.update_status.color = ERROR
                    self.update_btn_text.value = "Retry"
                elif result["available"]:
                    self.update_status.value = f"New: {result['latest']}"
                    self.update_status.color = "#22C55E"
                    self.update_btn_text.value = "Update"
                else:
                    self.update_status.value = "Up to date!"
                    self.update_status.color = "#22C55E"
                    self.update_btn_text.value = "Up to Date"
                
                self.page.update()
            
            self.page.run_thread(show_result)
        
        threading.Thread(target=check, daemon=True).start()


def main(page: Page):
    VortexApp(page)


if __name__ == "__main__":
    ft.app(target=main)
