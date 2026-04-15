import sys
import os
from types import ModuleType
import ssl
import logging
from typing import Any, Callable, Optional, List, Dict, Tuple, Union
import threading
import json
import time
import re

import platform
import shutil
from datetime import datetime, timedelta
import urllib.request

import flet as ft # type: ignore

# --- V2.3.0 Changelog (Simplified UI Update) ---
# - Removed 40+ unused/niche settings to reduce cognitive load
# - Redesigned Simple/Advanced mode logic
# - Streamlined Settings menu
# - Enforced safe defaults for hidden options
# ------------------------

APP_TITLE = "Vortex"
APP_VERSION = "1.5.0"
REMOTE_VERSION_URL = "https://raw.githubusercontent.com/ibr3himkhaled/Vortex/refs/heads/main/update.json"
CONFIG_FILE = "vortex_config.json"
HISTORY_FILE = "vortex_history.json"
QUEUE_FILE = "vortex_queue.json"
DEFAULT_DOWNLOAD_PATH = os.path.join(os.path.expanduser("~"), "Downloads", "Vortex")

DOWNLOAD_STATE = {
    "IDLE": "idle",
    "READY": "ready",
    "FETCHING": "fetching",
    "DOWNLOADING": "downloading",
    "PAUSED": "paused",
    "CANCELLED": "cancelled",
    "FINISHED": "finished",
    "QUEUE_RUNNING": "queue_running",
    "ERROR": "error"
}

app_state = {
    "state": DOWNLOAD_STATE["IDLE"],
    "active_thread": None
}

# --- SSL Patching ---
try:
    import certifi # type: ignore
except ImportError:
    m = ModuleType("certifi")
    setattr(m, "where", lambda: "")
    sys.modules["certifi"] = m

try:
    _create_unverified_https_context = ssl._create_unverified_context
except AttributeError:
    pass
else:
    ssl._create_default_https_context = _create_unverified_https_context

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)

# --- Utility Functions ---

def is_valid_url(url: str) -> bool:
    """Check if the URL is valid using basic checks."""
    if not url:
        return False
    url = url.strip()
    if url.startswith("debug:"): # Allow diagnostic command
        return True
    if not re.match(r'^(https?://|www\.)', url):
        return False
    # Prevent command injection
    if any(c in url for c in [';', '|', '&', '$', '`']):
        return False
    return True

def sanitize_path(path: str) -> str:
    """Sanitize file paths to prevent injection and invalid characters."""
    if not path:
        return ""
    return re.sub(r'[<>:"/\\|?*]', '_', path)

def parse_time_seconds(time_str: Optional[str]) -> Optional[int]:
    """Convert time string to seconds."""
    if not time_str:
        return None
    try:
        parts = [int(x) for x in time_str.split(':')]
        if len(parts) == 3:
            return parts[0]*3600 + parts[1]*60 + parts[2]
        if len(parts) == 2:
            return parts[0]*60 + parts[1]
        return int(time_str)
    except Exception as ex:
        logging.warning(f"Failed to parse time: {ex}")
        return None

def format_duration(seconds: Optional[int]) -> str:
    """Format video duration as string."""
    if not seconds:
        return "00:00"
    try:
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        return f"{h}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"
    except Exception as ex:
        logging.warning(f"Failed to format duration: {ex}")
        return "00:00"

def get_ffmpeg_path() -> Optional[str]:
    """Get the path to ffmpeg executable."""
    path = shutil.which("ffmpeg")
    if path:
        return path
    # Check common locations on Windows
    common_paths = [
        "C:\\ffmpeg\\bin\\ffmpeg.exe",
        "C:\\Program Files\\ffmpeg\\bin\\ffmpeg.exe",
        "C:\\Program Files (x86)\\ffmpeg\\bin\\ffmpeg.exe",
        os.path.join(os.path.expanduser("~"), "ffmpeg\\bin\\ffmpeg.exe"),
    ]
    for p in common_paths:
        if os.path.exists(p):
            return p
    return None

def check_ffmpeg() -> bool:
    """Check if ffmpeg is available in the system."""
    return get_ffmpeg_path() is not None

def map_error_message(error_text: str) -> Optional[str]:
    error_text = str(error_text).lower()
    if "sign in" in error_text or "not a bot" in error_text:
        return "🔐 Login required. Please enable cookies in settings."
    if "private video" in error_text:
        return "🔒 Private video. Cannot access."
    if "video is unavailable" in error_text:
        return "❌ Video unavailable or removed."
    if "429" in error_text or "too many requests" in error_text:
        return "⏳ Too many requests. Please wait a moment."
    if "cancelledbyuser" in error_text:
        return "⛔ Download stopped by user."
    if "network is unreachable" in error_text:
        return "📡 Network unreachable. Check internet."
    if "copyright" in error_text:
        return "© Copyright restriction."
    # Return None for unimportant/generic errors to avoid cluttering logs
    return None

def map_warning_message(warning_text: str) -> Optional[str]:
    text = warning_text.lower()
    if "no title found" in text:
        return "⚠️ Metadata limited."
    if "falling back" in text:
        return "⚠️ Using fallback format."
    # Filter out unimportant warnings like JavaScript runtime
    return None

def version_greater(v1: str, v2: str) -> bool:
    """Compare two version strings."""
    try:
        def parse_version(v):
            return [int(x) for x in v.split('.') if x.isdigit()]
        return parse_version(v1) > parse_version(v2)
    except:
        return False

def execute_post_action(action: str, page: Any):
    """Execute a post-download action."""
    if action == "Do Nothing":
        return
    time.sleep(5)
    try:
        if action == "Exit App":
            page.window_close()
        elif action == "Shutdown PC":
            os.system("shutdown /s /t 1" if platform.system() == "Windows" else "shutdown -h now")
        elif action == "Sleep PC":
            os.system("rundll32.exe powrprof.dll,SetSuspendState 0,1,0" if platform.system() == "Windows" else "systemctl suspend")
    except Exception as ex:
        logging.error(f"Failed to execute post action: {ex}")

def run_bg(target: Callable, name: Optional[str] = None, daemon: bool = True) -> threading.Thread:
    """Unified helper for running background tasks with error isolation."""
    def wrapped_target():
        try:
            target()
        except Exception as ex:
            logging.error(f"Background task '{name}' failed: {ex}")
    thread = threading.Thread(target=wrapped_target, daemon=daemon, name=name)
    thread.start()
    return thread

def check_for_updates(page: Any, dm: Any, notify: Callable):
    """Check for application updates."""
    try:
        with urllib.request.urlopen(REMOTE_VERSION_URL, timeout=3) as response:
            data = json.loads(response.read().decode('utf-8'))
        remote_version = data.get('latest_version', '')
        if remote_version and version_greater(remote_version, APP_VERSION):
            changelog = data.get('changelog', '')
            windows_url = data.get('windows_url', 'the repository')
            message = f"Update {remote_version} available!\n{changelog}\nVisit {windows_url}"
            notify(message, "info")
        else:
            notify("You are on the latest version!", "success")
    except Exception as ex:
        logging.error(f"Update check failed: {ex}")
        notify("Failed to check for updates. Please check your internet connection.", "error")

# --- Logger Class ---

class MyLogger:
    """Log download messages and format them."""
    def __init__(self, log_func: Callable):
        self.log_func = log_func
    def debug(self, msg: str):
        pass 
    def info(self, msg: str):
        if not msg.startswith('[download] '): 
            self.log_func(msg, color="white")
    def warning(self, msg: str):
        user_msg = map_warning_message(msg)
        if user_msg:
            self.log_func(user_msg, color="orange")
    def error(self, msg: str):
        user_msg = map_error_message(msg)
        if user_msg:
            self.log_func(user_msg, color="red")

def get_theme_colors(theme_mode: str) -> Dict[str, str]:
    if theme_mode == "light":
        return {
            "bg": "#F9FAFB", "card": "#FFFFFF", "accent": "#6366F1", "input": "#F3F4F6",
            "text_main": "#111827", "text_dim": "#6B7280", "icon": "#6366F1", "shadow": "#cbd5e1",
            "border": "#E5E7EB", "primary": "#6366F1", "success": "#10B981", "error": "#EF4444",
            "sidebar_bg": "#F9FAFB", "divider": "#E5E7EB", "input_bg": "#FFFFFF", "surface": "#FFFFFF", "secondary_text": "#6B7280",
            "actions_bg": "#FFFFFF", "gradient_1": "#8B5CF6", "gradient_2": "#6366F1"
        }
    else:
        return {
            "bg": "#09090B", "card": "#18181B", "accent": "#8B5CF6", "input": "#27272A",
            "text_main": "#FAFAFA", "text_dim": "#A1A1AA", "icon": "#8B5CF6", "shadow": "#000000",
            "border": "#27272A", "primary": "#8B5CF6", "success": "#10B981", "error": "#EF4444",
            "sidebar_bg": "#09090B", "divider": "#27272A", "input_bg": "#18181B", "surface": "#18181B", "secondary_text": "#A1A1AA",
            "actions_bg": "#09090B", "gradient_1": "#8B5CF6", "gradient_2": "#3B82F6"
        }

class DataManager:
    """Manage settings, history, and queue."""
    def __init__(self):
        self.default_config = {
            "save_path": DEFAULT_DOWNLOAD_PATH,
            "theme_mode": "dark",
            "ui_mode": "simple",
            "preset": "Custom",
            "smart_organize": True,
            "clipboard_monitor": False,  # Disabled by default for performance
            "notifications": True,
            "filename_template": "%(title)s.%(ext)s",
            "ffmpeg_path": "",
            "subtitles": False,
            "embed_subs": False,
            "thumbnail": False,
            "sponsorblock": False,
            "cookies_path": "",
            "proxy": "",
            "speed_limit": "",
            "playlist_items": "",
            "post_action": "Do Nothing",
            "download_retries": 10,
            "concurrent_downloads": 1,
            "auto_check_updates": False,
            "embed_metadata": False,
            "custom_user_agent": "",
            "download_delay": 0,
            "log_verbosity": "Standard"
        }
        self.config = self.default_config.copy()
        self.load_config()
        self.history: List[Dict[str, Any]] = []
        self.batch_urls: List[str] = []
        self.queue: List[str] = []
        # Defer loading to load_async()
        self.is_cancelled = False
        self.is_paused = False
        self.total_files = 0
        self.current_file_index = 0
        self.has_download_started = False
        self.last_downloaded_file = ""

    def load_async(self):
        """Load config, history, and queue asynchronously."""
        def load_task():
            self.load_history()
            self.load_queue()
        run_bg(load_task, name="Vortex-DataLoadThread")

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    saved = json.load(f)
                    # Filter out obsolete keys
                    filtered: dict[str, Any] = {str(k): v for k, v in saved.items() if k in self.default_config}
                    self.config.update(filtered)
            except Exception as ex:
                logging.error(f"Failed to load config: {ex}")

    def save_config(self):
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2)
        except Exception as ex:
            logging.error(f"Failed to save config: {ex}")

    def reset_config(self):
        self.config = self.default_config.copy()
        self.save_config()

    def load_history(self):
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                    self.history = json.load(f)
            except Exception as ex:
                self.history = []

    def add_history(self, item: Dict[str, Any]):
        self.history.insert(0, item)
        if len(self.history) > 50:
            self.history.pop()
        try:
            with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.history, f, indent=2)
        except Exception as ex:
            logging.error(f"Failed to save history: {ex}")

    def clear_history(self):
        self.history = []
        if os.path.exists(HISTORY_FILE):
            try: os.remove(HISTORY_FILE)
            except: pass

    def load_queue(self):
        if os.path.exists(QUEUE_FILE):
            try:
                with open(QUEUE_FILE, 'r', encoding='utf-8') as f:
                    self.queue = json.load(f)
            except Exception as ex:
                self.queue = []

    def save_queue(self):
        try:
            with open(QUEUE_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.queue, f, indent=2)
        except Exception as ex:
            logging.error(f"Failed to save queue: {ex}")

    def add_to_queue(self, item: str):
        if item not in self.queue:
            self.queue.append(item)
            self.save_queue()

    def remove_from_queue(self, item: str):
        if item in self.queue:
            self.queue.remove(item)
            self.save_queue()

    def clear_queue(self):
        self.queue = []
        if os.path.exists(QUEUE_FILE):
            try: os.remove(QUEUE_FILE)
            except: pass

class NotificationManager:
    def __init__(self):
        self.history: List[Dict[str, Any]] = []
        self.max_history = 100
    def add_notification(self, title: str, message: str, level: str = "info"):
        history_len = len(self.history)
        start_idx = max(0, history_len - 5)
        for i in range(start_idx, history_len):
            item = self.history[i]
            if item["title"] == title and item["message"] == message and item["level"] == level:
                item["count"] = item.get("count", 1) + 1
                item["timestamp"] = str(datetime.now())
                return
        notification = {
            "title": title, "message": message, "level": level,
            "timestamp": str(datetime.now()), "count": 1
        }
        self.history.append(notification)
        if len(self.history) > self.max_history:
            self.history.pop(0)

class UIUpdateManager:
    def __init__(self, page: Any):
        self.page = page
        self.log_buffer: List[Tuple[str, str, Optional[Callable]]] = []
        self.notification_queue: List[Tuple[str, str, str, Optional[str], Optional[Callable]]] = []
        self.last_progress_update: float = 0.0
        self.progress_update_interval = 0.3  # Throttle progress updates
        self.last_ui_update: float = 0.0
        self.ui_update_interval = 0.05  # General UI update interval
        self._running = True
        self.lock = threading.Lock()
        
        self.log_view: Any = None
        self.notify_func: Any = None

        # Expanded state caching for UI elements
        self.cached_states: Dict[str, Dict[str, Any]] = {
            "progress_bar": {"value": 0.0, "indeterminate": False},
            "prog_label": {"value": "Ready"},
            "log_view": {"controls": []},
            "queue_display": {"controls": []},
            "queue_stats": {"value": "Queue: 0 items"},
            "btn_fetch": {"disabled": False},
            "btn_download": {"disabled": True, "visible": True},
            "btn_cancel": {"disabled": True, "visible": False},
            "btn_pause": {"disabled": False, "visible": False},
            "btn_start_queue": {"visible": True},
            "url_input": {"value": "", "read_only": False, "prefix_icon": "link"},
            "img_preview": {"src": "https://placehold.co/600x400/2d2d2d/999999/png?text=Vortex"},
            "title_txt": {"value": "Paste a video link Here"},
            "txt_uploader": {"value": "Unknown"},
            "txt_duration": {"value": "00:00"},
            "txt_views": {"value": "0"},
            "meta_row": {"visible": False}
        }
        self.thread = threading.Thread(target=self._update_loop, daemon=True, name="Vortex-UIThread")
        self.thread.start()

    def _update_loop(self):
        while self._running:
            current_time = time.time()
            if current_time - self.last_ui_update >= self.ui_update_interval:
                self._flush_updates()
                self.last_ui_update = current_time
            time.sleep(0.05)

    def add_log_message(self, msg: str, color: str = "white", retry_callback: Optional[Callable] = None):
        timestamp = datetime.now().strftime('%H:%M:%S')
        with self.lock:
            self.log_buffer.append((f"[{timestamp}] {msg}", color, retry_callback))

    def queue_notification(self, title: str, message: str, level: str = "info", action_text: Optional[str] = None, on_action: Optional[Callable] = None):
        with self.lock:
            self.notification_queue.append((title, message, level, action_text, on_action))

    def update_progress(self, progress_bar: Any, value: float, prog_label: Any, text: str):
        current_time = time.time()
        if current_time - self.last_progress_update >= self.progress_update_interval:
            value = max(0.0, min(value, 1.0))
            if self.cached_states["progress_bar"]["value"] != value:
                progress_bar.value = value
                self.cached_states["progress_bar"]["value"] = value
            if self.cached_states["prog_label"]["value"] != text:
                prog_label.value = text
                self.cached_states["prog_label"]["value"] = text
            self.last_progress_update = current_time

    def update_ui_element(self, element_name: str, element: Any, **kwargs):
        """Update UI element only if state has changed."""
        if element_name not in self.cached_states:
            return
        changed = False
        for key, value in kwargs.items():
            if self.cached_states[element_name].get(key) != value:
                setattr(element, key, value)
                self.cached_states[element_name][key] = value
                changed = True
        if changed:
            self.page.update()

    def stop(self):
        """Gracefully stop the UI update loop."""
        self._running = False

    def _flush_updates(self):
        with self.lock:
            logs_to_process = list(self.log_buffer)
            self.log_buffer.clear()
            notifs_to_process = list(self.notification_queue)
            self.notification_queue.clear()

        if hasattr(self, 'log_view') and logs_to_process:
            for msg, color, retry_cb in logs_to_process:
                if retry_cb:
                    control = ft.Row([
                        ft.Text(msg, color=color, size=12, font_family="Consolas", expand=True),
                        ft.IconButton(
                            icon="refresh",
                            icon_size=14,
                            tooltip="Retry this item",
                            on_click=lambda e, cb=retry_cb: cb()
                        )
                    ], alignment="spaceBetween", spacing=5)
                else:
                    control = ft.Text(msg, color=color, size=12, font_family="Consolas")

                if self.log_view is not None:
                    self.log_view.controls.append(control) # type: ignore
                    if len(self.log_view.controls) > 100:  # type: ignore
                        self.log_view.controls.pop(0)      # type: ignore
            
        if self.notify_func is not None and notifs_to_process:
            for title, message, level, action_text, on_action in notifs_to_process:
                self.notify_func(message, level, action_text, on_action)
        try:
            self.page.update()
        except:
            pass

# --- yt-dlp Options Builder ---

def build_ydl_opts(
    dm: DataManager,
    format_type: str,
    quality: str,
    audio_ext: str,
    video_ext: str = "mp4",
    progress_hook: Optional[Callable] = None,
    logger: Optional[MyLogger] = None,
    is_metadata: bool = False
) -> Dict[str, Any]:
    """Build yt-dlp options based on settings."""
    # Local import to improve startup performance
    import yt_dlp # type: ignore
    
    opts: Dict[str, Any] = {
        'ignoreerrors': True,
        'nocheckcertificate': True,
        'retries': dm.config.get("download_retries", 10),
        'fragment_retries': dm.config.get("download_retries", 10),
        'skip_unavailable_fragments': True,
        'concurrent_fragment_downloads': dm.config.get("concurrent_downloads", 1),
    }
    if is_metadata:
        opts.update({
            'quiet': True,
            'noplaylist': True,
            'skip_download': True,
        })
    else:
        base_template = sanitize_path(str(dm.config.get("filename_template", "%(title)s.%(ext)s")))
        if dm.config.get("smart_organize", False):
            template = f"%(uploader)s/{base_template}"
        else:
            template = base_template
        opts['outtmpl'] = os.path.join(str(dm.config["save_path"]), template)
        if progress_hook:
            opts['progress_hooks'] = [progress_hook]
        if logger:
            opts['logger'] = logger
        ffmpeg_path = dm.config["ffmpeg_path"] or get_ffmpeg_path()
        if ffmpeg_path:
            opts['use_ffmpeg'] = True
            opts['ffmpeg_location'] = ffmpeg_path
            opts['ffmpeg_args'] = ['-preset', 'ultrafast', '-threads', '0']
        else:
            opts['use_ffmpeg'] = False
        if format_type == "audio":
            opts['format'] = 'bestaudio/best'
            if opts.get('use_ffmpeg'):
                opts['postprocessors'] = [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': audio_ext,
                    'preferredquality': quality
                }]
        elif format_type == "video":
            height = quality.replace("p", "")
            opts['format'] = f"bestvideo[height<={height}]+bestaudio/best"
            opts['merge_output_format'] = video_ext
        else:
            opts['format'] = 'bestvideo+bestaudio/best'
            if opts.get('use_ffmpeg'):
                opts['postprocessors'] = [{
                    'key': 'FFmpegVideoConvertor',
                    'preferedformat': video_ext
                }]
    if dm.config["cookies_path"]:
        opts['cookiefile'] = dm.config["cookies_path"]
    if dm.config["proxy"]:
        opts['proxy'] = dm.config["proxy"]
    if dm.config.get("sponsorblock", False):
        opts['sponsorblock_remove'] = ['all']
    if dm.config.get("speed_limit"):
        try:
            opts['ratelimit'] = float(dm.config["speed_limit"]) * 1024 * 1024
        except:
            pass
    if dm.config.get("custom_user_agent"):
        opts['user_agent'] = dm.config["custom_user_agent"]
    else:
        opts['user_agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    if dm.config.get("embed_metadata", False):
        opts['addmetadata'] = True
    delay_val = dm.config.get("download_delay", 0)
    if delay_val and int(delay_val) > 0:
        opts['sleep_interval'] = int(delay_val)
    verbosity = dm.config.get("log_verbosity", "Standard")
    if verbosity == "Quiet":
        opts['quiet'] = True
    elif verbosity == "Verbose":
        opts['verbose'] = True
    
    return opts

def download_media(
    url: str,
    opts: Dict[str, Any],
    dm: DataManager,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    playlist_items: Optional[str] = None,
    is_playlist: bool = False
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Download media using yt-dlp."""
    import yt_dlp # type: ignore
    from yt_dlp.utils import download_range_func # type: ignore

    try:
        if playlist_items:
            opts['playlist_items'] = playlist_items
            opts['noplaylist'] = False
        elif is_playlist:
            opts['noplaylist'] = False
        else:
            opts['noplaylist'] = True
        s, e = parse_time_seconds(start_time), parse_time_seconds(end_time)
        if s is not None and e is not None:
            opts['download_ranges'] = download_range_func(None, [(s, e)])
            opts['force_keyframes_at_cuts'] = True
        if dm.config.get("subtitles", False):
            opts['writesubtitles'] = True
            opts['subtitleslangs'] = ['en', 'ar']
        if dm.config.get("embed_subs", False):
            opts['embedsub'] = True
        if dm.config.get("thumbnail", True):
            opts['writethumbnail'] = True

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get('title', 'Video')
            if 'entries' in info:
                title = "Playlist Download"
            
            # Robust filepath extraction
            filepath = info.get('_filename') or info.get('requested_downloads', [{}])[0].get('filepath')
            
            return title, None, filepath
    except Exception as ex:
        return None, str(ex), None

# --- UI Functions ---

ui_manager: Any = None

def main(page: Any):
    """Main UI entry point."""
    global ui_manager
    dm = DataManager()
    nm = NotificationManager()
    ui_manager = UIUpdateManager(page)
    colors = get_theme_colors(str(dm.config["theme_mode"]))
    download_state = {
        "progress": 0.0,
        "text": "Ready",
        "active": False
    }

    # Flags for task guards
    session_ytdlp_checked = False

    def notify(message, level="info", action_text=None, on_action=None):
        if not dm.config.get("notifications", True):
            return
        nm.add_notification("Vortex", message, level)
        show_notification(page, "Vortex", message, level, action_text, on_action)

    page.title = f"{APP_TITLE} {APP_VERSION}"
    page.window_width = 1200
    page.window_height = 850
    page.window_min_width = 900
    page.window_min_height = 600
    page.padding = 0
    page.theme_mode = "dark" if dm.config["theme_mode"] == "dark" else "light"
    page.bgcolor = colors["bg"]

    content_area = ft.Container(expand=True, padding=20, bgcolor=colors["bg"])

    def show_notification(page: ft.Page, title: str, message: str, level="info", action_text=None, on_action=None):
        if level == "info":
            icon_name, bg_color = "notifications_active", colors["primary"]
        elif level == "success":
            icon_name, bg_color = "check_circle", colors["success"]
        elif level == "warning":
            icon_name, bg_color = "warning", colors["accent"]
        elif level == "error":
            icon_name, bg_color = "error_outline", colors["error"]
        else:
            icon_name, bg_color = "info", colors["primary"]

        snack = ft.SnackBar(
            content=ft.Row([
                ft.Icon(icon_name, color="white"),
                ft.Column([
                    ft.Text(title, weight="bold", color="white"),
                    ft.Text(message, color="white", size=12, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)
                ], spacing=2, expand=True)
            ], alignment="start"),
            bgcolor=bg_color,
            behavior=ft.SnackBarBehavior.FLOATING,
            margin=10,
            duration=4000 if level != "error" else 5000,
            show_close_icon=True,
            elevation=10,
            action=action_text if action_text else None,
            on_action=on_action if on_action else None,
            action_color="white"
        )
        page.overlay.append(snack)
        snack.open = True
        page.update()

    if ui_manager is not None:
        ui_manager.notify_func = notify

    # Set up graceful shutdown on app close
    page.on_close = lambda e: ui_manager.stop()

    # Start background loading of config, history, queue
    dm.load_async()

    # Background FFmpeg check
    def background_ffmpeg_check():
        time.sleep(1)  # Small delay to allow UI to load
        ffmpeg_path = get_ffmpeg_path()
        # Removed FFmpeg path logging to reduce clutter
        if not ffmpeg_path and not dm.config["ffmpeg_path"]:
            notify("FFmpeg Not Found! Features limited.", "warning")

    run_bg(background_ffmpeg_check, name="Vortex-FFmpegCheck")

    # Background update check
    def background_update_check():
        time.sleep(5)  # Delay to allow UI to load
        if dm.config.get("auto_check_updates", True):
            check_for_updates(page, dm, notify)

    run_bg(background_update_check, name="Vortex-UpdateCheck")

    def clear_input_click(e):
        url_input.value = ""
        url_input.read_only = False
        url_input.prefix_icon = "link"
        dm.batch_urls = []
        validate_buttons()
        page.update()

    def open_folder_click(e):
        import subprocess
        save_path = str(dm.config["save_path"])
        if os.path.exists(save_path):
            if sys.platform == 'win32' and hasattr(os, 'startfile'):
                os.startfile(save_path) # type: ignore
            else:
                subprocess.Popen(['open' if sys.platform == 'darwin' else 'xdg-open', save_path])
        else:
            notify("Folder not found", "error")

    def validate_buttons(e=None):
        """Enable or disable buttons based on input state."""
        url_valid = bool(url_input.value and (is_valid_url(url_input.value) or dm.batch_urls))
        path_valid = bool(dm.config["save_path"])
        
        btn_download.disabled = not (url_valid and path_valid)
        btn_add_queue.disabled = not url_valid
        
        if btn_download.disabled:
            btn_download.tooltip = "Enter valid URL and check Save Path"
        else:
            btn_download.tooltip = "Start Download"
            
        page.update()

    url_input = ft.TextField(
        label="Paste Any Link Here", prefix_icon=ft.icons.LINK_ROUNDED, border_radius=20, 
        bgcolor=colors["input_bg"], border_color="transparent", focused_border_color=colors["primary"],
        focused_bgcolor=colors["surface"], content_padding=ft.padding.all(20), expand=True, text_size=16,
        suffix=ft.Row([
            ft.IconButton(icon=ft.icons.FOLDER_OPEN_ROUNDED, tooltip="Open Downloads", icon_size=20, icon_color=colors["text_dim"], on_click=open_folder_click),
            ft.IconButton(icon=ft.icons.CLOSE_ROUNDED, tooltip="Clear", icon_size=20, icon_color=colors["text_dim"], on_click=clear_input_click)
        ], spacing=0, tight=True),
        on_change=validate_buttons
    )

    batch_picker = ft.FilePicker(on_result=lambda e: load_batch_files(e))
    page.overlay.append(batch_picker)
    btn_import = ft.IconButton(icon="file_upload", tooltip="Import TXT", on_click=lambda _: batch_picker.pick_files(allowed_extensions=["txt"]))

    # --- Presets and Config UI ---
    
    def apply_preset(e):
        """Apply preset configurations."""
        val = preset_dd.value
        dm.config["preset"] = val # Persistence
        dm.save_config()

        if val == "Best Video (MP4)":
            format_dd.value = "video"
            quality_dd.value = "2160p"
            video_ext_dd.value = "mp4"
            update_dynamic_options()
            notify("Applied: Best Video Settings", "info")
        elif val == "Best Audio (MP3)":
            format_dd.value = "audio"
            quality_dd.value = "320"
            audio_ext_dd.value = "mp3"
            update_dynamic_options()
            notify("Applied: Best Audio Settings", "info")
        recalculate_size()
        page.update()

    preset_dd = ft.Dropdown(
        label="Quick Preset", width=200, border_radius=10, 
        options=[
            ft.dropdown.Option("Custom", "Custom Settings"),
            ft.dropdown.Option("Best Video (MP4)", "Best Video (MP4)"),
            ft.dropdown.Option("Best Audio (MP3)", "Best Audio (MP3)")
        ],
        value=dm.config.get("preset", "Custom"),
        on_change=apply_preset,
        text_size=12
    )

    format_dd = ft.Dropdown(label="Format", width=140, border_radius=10, value="video", options=[ft.dropdown.Option("video", "Video"), ft.dropdown.Option("audio", "Audio")])
    quality_dd = ft.Dropdown(label="Quality", width=140, border_radius=10, value="1080p", on_change=lambda e: recalculate_size())
    est_size_label = ft.Container(
        content=ft.Row([
            ft.Icon("storage", size=16, color=colors["accent"]),
            ft.Text("Est. Size: --", size=12, color=colors["secondary_text"], weight="bold")
        ], spacing=5),
        bgcolor=colors["surface"],
        padding=ft.padding.symmetric(horizontal=10, vertical=5),
        border_radius=8,
        border=ft.border.all(1, colors["border"])
    )
    video_ext_dd = ft.Dropdown(label="Ext", width=100, border_radius=10, value="mp4", options=[ft.dropdown.Option("mp4"), ft.dropdown.Option("mkv"), ft.dropdown.Option("webm")], visible=False)
    audio_ext_dd = ft.Dropdown(label="Ext", width=100, border_radius=10, value="mp3", options=[ft.dropdown.Option("mp3"), ft.dropdown.Option("m4a"), ft.dropdown.Option("wav"), ft.dropdown.Option("flac")], visible=False)
    
    start_time = ft.TextField(label="Start", hint_text="00:00:00", width=100, height=40, content_padding=10, text_size=12)
    end_time = ft.TextField(label="End", hint_text="00:00:00", width=100, height=40, content_padding=10, text_size=12)
    speed_input = ft.TextField(label="Limit MB/s", value=dm.config["speed_limit"], width=100, height=40, content_padding=10, text_size=12)
    playlist_input = ft.TextField(label="Playlist Items", hint_text="e.g. 1,2,5-10", value=dm.config.get("playlist_items", ""), width=150, height=40, content_padding=10, text_size=12, icon="list")
    post_action_dd = ft.Dropdown(label="When Done", value=dm.config.get("post_action", "Do Nothing"), width=150, content_padding=10, text_size=12, options=[ft.dropdown.Option("Do Nothing"), ft.dropdown.Option("Shutdown PC"), ft.dropdown.Option("Sleep PC"), ft.dropdown.Option("Exit App")])
    
    cb_organize = ft.Switch(label="Smart Organize", value=dm.config["smart_organize"], active_color=colors["primary"])
    cb_subs = ft.Switch(label="Subtitles", value=dm.config["subtitles"], active_color=colors["primary"])
    cb_embed = ft.Switch(label="Embed Subs", value=dm.config["embed_subs"], active_color=colors["primary"])
    cb_thumb = ft.Switch(label="Save Thumbnail", value=dm.config.get("thumbnail", True), active_color=colors["primary"])
    cb_sponsor = ft.Switch(label="SponsorBlock", value=dm.config["sponsorblock"], active_color=colors["primary"])

    img_preview = ft.Image(src="https://placehold.co/600x400/27272A/A1A1AA/png?text=Vortex", width=420, height=235, border_radius=20, fit="cover", animate_opacity=300)
    title_txt = ft.Text("Paste a video link Here", size=22, weight="w800", color=colors["text_main"], text_align="center", max_lines=2, overflow=ft.TextOverflow.ELLIPSIS)
    txt_uploader = ft.Text("Unknown", size=13, color=colors["secondary_text"], weight="w500")
    txt_duration = ft.Text("00:00", size=13, color=colors["secondary_text"], weight="w500")
    txt_views = ft.Text("0", size=13, color=colors["secondary_text"], weight="w500")
    
    def meta_tag(icon_name, text_control):
        return ft.Container(
            content=ft.Row([ft.Icon(icon_name, size=16, color=colors["accent"]), text_control], spacing=6),
            padding=ft.padding.symmetric(horizontal=12, vertical=6),
            bgcolor=colors["input_bg"], border_radius=15,
        )

    meta_row = ft.Row([
        meta_tag(ft.icons.PERSON_ROUNDED, txt_uploader),
        meta_tag(ft.icons.ACCESS_TIME_ROUNDED, txt_duration),
        meta_tag(ft.icons.VISIBILITY_ROUNDED, txt_views),
    ], alignment="center", visible=False, spacing=15)
    
    # Styled progress bar
    progress_bar = ft.ProgressBar(width=600, value=0.0, bgcolor="#E0E0E0", color=colors["primary"])
    # Dynamic label color - initialized with theme color
    prog_label = ft.Text("Idle", size=12, weight="bold", color=colors["text_main"])
    
    log_view = ft.ListView(height=150, spacing=2, padding=10, auto_scroll=True)
    ui_manager.log_view = log_view # bind for updates
    log_container = ft.Container(content=log_view, bgcolor=colors["surface"], border_radius=12, border=ft.border.all(1, colors["border"]))
    queue_display = ft.ListView(height=150, spacing=2, auto_scroll=True)
    queue_container = ft.Container(content=queue_display, bgcolor=colors["surface"], border_radius=12, border=ft.border.all(1, colors["border"]))
    queue_stats = ft.Text("Queue: 0 items", size=12, color=colors["text_dim"])

    def log(msg: str, color: str = "white", retry_callback: Optional[Callable] = None):
        logging.info(msg)
        # Delegate to UI manager for thread safety
        ui_manager.add_log_message(msg, color, retry_callback)

    my_logger = MyLogger(log)

    def load_batch_files(e: ft.FilePickerResultEvent):
        if e.files:
            try:
                with open(e.files[0].path, "r", encoding="utf-8") as f:
                    links = [line.strip() for line in f.read().splitlines() if is_valid_url(line.strip())]
                if links:
                    dm.batch_urls = links
                    url_input.value = f"📂 {len(links)} Links Loaded"
                    url_input.read_only = True
                    url_input.prefix_icon = "folder_special"
                    notify(f"Queue loaded: {len(links)} videos", "success")
                    validate_buttons()
                    page.update()
            except Exception as ex:
                logging.error(f"Failed to load batch file: {ex}")
                notify("File Error", "error")

    def update_dynamic_options(e=None):
        fmt = format_dd.value
        quality_dd.options = []
        is_advanced = dm.config.get("ui_mode", "simple") == "advanced"
        
        if fmt == "video":
            quality_dd.label = "Resolution"
            opts = ["4320p", "2160p", "1440p", "1080p", "720p", "480p", "360p", "240p", "144p"]
            quality_dd.options = [ft.dropdown.Option(o) for o in opts]
            if not quality_dd.value or quality_dd.value not in opts:
                quality_dd.value = "1080p"
            video_ext_dd.visible = True if is_advanced else False
            audio_ext_dd.visible = False
        else:
            quality_dd.label = "Bitrate"
            opts = [("320", "High"), ("192", "Medium"), ("128", "Low")]
            quality_dd.options = [ft.dropdown.Option(k, v) for k, v in opts]
            quality_dd.value = "192"
            video_ext_dd.visible = False
            audio_ext_dd.visible = True if is_advanced else False
        page.update()

    format_dd.on_change = lambda e: [update_dynamic_options(), recalculate_size()]

    def calculate_estimated_size(formats, mode, quality):
        """Calculate estimated download size based on formats and settings."""
        if not formats:
            return "--"
        total_size = 0
        for fmt in formats:
            if mode == "video":
                height = quality.replace("p", "")
                if fmt.get('height') and fmt.get('height') <= int(height):
                    size = fmt.get('filesize') or fmt.get('filesize_approx')
                    if size is not None and size > total_size:
                        total_size = size
            elif mode == "audio":
                if fmt.get('abr') and fmt.get('abr') <= int(quality):
                    size = fmt.get('filesize') or fmt.get('filesize_approx')
                    if size is not None and size > total_size:
                        total_size = size
        if total_size > 0:
            if total_size >= 1024**3:
                return f"{float(total_size) / (1024**3):.2f} GB"
            elif total_size >= 1024**2:
                return f"{float(total_size) / (1024**2):.2f} MB"
            else:
                return f"{float(total_size) / 1024:.2f} KB"
        return "--"

    def recalculate_size():
        """Recalculate and update estimated size label."""
        url = url_input.value.strip()
        if not url or url not in metadata_cache:
            est_size_label.content.controls[1].value = "Est. Size: --"
            page.update()
            return
        _, info = metadata_cache[url]
        mode = format_dd.value
        quality = quality_dd.value
        if 'entries' in info:
            # Playlist: aggregate sizes
            total_size = 0
            for entry in info['entries']:
                formats = entry.get('formats', [])
                size_str = calculate_estimated_size(formats, mode, quality)
                if size_str != "--":
                    # Convert back to bytes for aggregation
                    if "GB" in size_str:
                        total_size += float(size_str.split()[0]) * (1024**3)
                    elif "MB" in size_str:
                        total_size += float(size_str.split()[0]) * (1024**2)
                    elif "KB" in size_str:
                        total_size += float(size_str.split()[0]) * 1024
            if total_size > 0:
                if total_size >= 1024**3:
                    est_size_label.content.controls[1].value = f"Est. Size: {float(total_size) / (1024**3):.2f} GB"
                elif total_size >= 1024**2:
                    est_size_label.content.controls[1].value = f"Est. Size: {float(total_size) / (1024**2):.2f} MB"
                else:
                    est_size_label.content.controls[1].value = f"Est. Size: {float(total_size) / 1024:.2f} KB"
            else:
                est_size_label.content.controls[1].value = "Est. Size: --"
        else:
            formats = info.get('formats', [])
            size_str = calculate_estimated_size(formats, mode, quality)
            est_size_label.content.controls[1].value = f"Est. Size: {size_str}"
        page.update()

    # Store tuples (timestamp, info)
    metadata_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}

    def fetch_info_click(e):
        if dm.batch_urls:
            notify("Batch mode active.", "info")
            return
        url = url_input.value
        if not url:
            return

        # Diagnostic Mode Trigger
        if url == "debug:vortex":
            log("--- DIAGNOSTIC REPORT ---", "cyan")
            log(f"OS: {platform.system()} {platform.release()}", "cyan")
            log(f"App Version: {APP_VERSION}", "cyan")
            log(f"FFmpeg: {'Available' if check_ffmpeg() else 'Missing'}", "cyan")
            log(f"Save Path: {dm.config['save_path']}", "cyan")
            log("--- END REPORT ---", "cyan")
            notify("Diagnostic report logged.", "success")
            return

        set_state(DOWNLOAD_STATE["FETCHING"])

        def metadata_fetch_task():
            import yt_dlp # type: ignore # Delayed import
            try:
                # Metadata Cache Cleanup (TTL ~15 min)
                current_time = time.time()
                expired = [k for k, v in metadata_cache.items() if current_time - v[0] > 900]
                for k in expired:
                    metadata_cache.pop(k, None)

                if url in metadata_cache:
                    info = metadata_cache[url][1]
                else:
                    is_playlist = bool(playlist_input.value.strip())
                    ydl_opts = build_ydl_opts(dm, "video", "1080p", "mp3", is_metadata=True)
                    if is_playlist:
                        ydl_opts['noplaylist'] = False
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(url, download=False)
                        if not info:
                            log("Could not analyze link", "red")
                            set_state(DOWNLOAD_STATE["IDLE"])
                            return
                        metadata_cache[url] = (current_time, info)
                    # For display, use first entry if playlist
                    display_info = list(info['entries'])[0] if 'entries' in info else info

                if info.get('thumbnail'): img_preview.src = info.get('thumbnail')
                meta_row.visible = True
                title_txt.value = info.get('title', 'Unknown')
                txt_uploader.value = info.get('uploader', 'Unknown')[:20]
                txt_duration.value = format_duration(info.get('duration'))
                txt_views.value = f"{info.get('view_count', 0):,}"

                recalculate_size()

                log(f"Analyzed: {info.get('title')}", "green")
                notify("Link analyzed successfully!", "success")
                evaluate_ready_state()
            except Exception as ex:
                error_str = str(ex)
                if 'UrllibResponseAdapter' in error_str and '_http_error' in error_str:
                    log("yt-dlp compatibility issue detected. Updating core...", "orange")
                    try:
                        import subprocess
                        subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"])
                        log("Core updated. Please try again.", "green")
                        notify("Core updated successfully!", "success")
                    except Exception as update_ex:
                        log(f"Failed to update core: {update_ex}", "red")
                        notify("Failed to update core", "error")
                else:
                    user_error = map_error_message(error_str)
                    logging.error(f"Metadata fetch failed: {ex}")
                    if user_error:
                        log(user_error, "red")
                set_state(DOWNLOAD_STATE["IDLE"])
        run_bg(metadata_fetch_task, name="Vortex-MetadataThread")

    def cancel_download_click(e):
        dm.is_cancelled = True
        set_state(DOWNLOAD_STATE["CANCELLED"])
        evaluate_ready_state()

    def pause_resume_click(e):
        if dm.is_paused:
            resume_download()
            log("Resumed download", "green")
            notify("Download resumed", "info")
        else:
            pause_download()
            log("Paused download", "orange")
            notify("Download paused", "warning")
    
    def retry_download_wrapper(url):
        """Helper to retry a specific URL with current settings."""
        if not url: return
        log(f"Retrying: {url}", "cyan")

        def retry_task():
            import yt_dlp # type: ignore
            try:
                 safe_fmt = format_dd.value if format_dd.value else "video"
                 safe_qual = quality_dd.value if quality_dd.value else "1080p"
                 audio_ext = audio_ext_dd.value if safe_fmt == "audio" else "mp3"
                 video_ext = video_ext_dd.value if safe_fmt == "video" else "mp4"
                 opts = build_ydl_opts(dm, safe_fmt, safe_qual, audio_ext, video_ext, progress_hook, my_logger)

                 is_playlist = bool(playlist_input.value.strip()) or "list=" in url
                 title, error, filepath = download_media(url, opts, dm, start_time.value, end_time.value, playlist_input.value, is_playlist)
                 if error:
                     err_msg = map_error_message(error) or str(error)
                     log(err_msg, "red", lambda: retry_download_wrapper(url))
                 else:
                     dm.add_history({'title': title, 'date': datetime.now().strftime("%Y-%m-%d %H:%M")})
                     log(f"Retry Success: {title}", "green")
                     notify("Retry Successful", "success")
            except Exception as ex:
                log(f"Retry failed: {ex}", "red")

        run_bg(retry_task, name="Vortex-RetryThread")

    def open_file_click(e):
        """Open the last downloaded file using cross-platform commands."""
        if dm.last_downloaded_file and os.path.exists(dm.last_downloaded_file):
            try:
                if sys.platform == 'win32':
                    getattr(os, "startfile")(dm.last_downloaded_file)
                else:  # macOS/Linux
                    import subprocess
                    subprocess.Popen(['open' if sys.platform == 'darwin' else 'xdg-open', dm.last_downloaded_file])
                notify("File opened successfully!", "success")
            except Exception as ex:
                log(f"Failed to open file: {ex}", "red")
                notify("Failed to open file", "error")
        else:
            notify("No file to open", "warning")

    def download_click(e):
        # Disable button immediately for faster response
        btn_download.disabled = True
        page.update()

        # Start download in background thread
        threading.Thread(target=do_download, daemon=True, name="Vortex-DownloadThread").start()

    def do_download():
        nonlocal session_ytdlp_checked

        # Thread Guard
        for t in threading.enumerate():
            if t.name == "Vortex-DownloadThread" and t.is_alive() and t != threading.current_thread():
                ui_manager.queue_notification("Vortex", "A download is already active!", "warning")
                ui_manager.update_ui_element("btn_download", btn_download, disabled=False)
                return

        # Save Path Validation
        try:
            os.makedirs(str(dm.config["save_path"]), exist_ok=True)
        except Exception as os_ex:
            ui_manager.add_log_message(f"Cannot access save path: {os_ex}", "red")
            ui_manager.queue_notification("Vortex", f"Invalid Save Path: {os_ex}", "error")
            ui_manager.update_ui_element("btn_download", btn_download, disabled=False)
            return

        import yt_dlp # type: ignore # Ensure module is available
        targets = dm.batch_urls if dm.batch_urls else ([url_input.value.strip()] if url_input.value else [])
        if not targets:
            ui_manager.queue_notification("Vortex", "No URL loaded!", "warning")
            ui_manager.update_ui_element("btn_download", btn_download, disabled=False)
            return

        # Playlist Detection
        url = targets[0] if targets else ""
        if url and not dm.batch_urls:
            try:
                meta_opts = build_ydl_opts(dm, "video", "1080p", "mp3", is_metadata=True)
                with yt_dlp.YoutubeDL(meta_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    if 'entries' in info:
                        video_count = len(info['entries'])
                        # For faster response, assume download all without dialog
                        pass  # Proceed with download
            except Exception as ex:
                ui_manager.add_log_message(f"Playlist check failed: {ex}", "orange")

        set_state(DOWNLOAD_STATE["DOWNLOADING"])
        proceed_with_download(targets)

    def proceed_with_download(targets):
        nonlocal session_ytdlp_checked

        dm.config.update({
            "smart_organize": cb_organize.value, "subtitles": cb_subs.value, "embed_subs": cb_embed.value,
            "sponsorblock": cb_sponsor.value, "speed_limit": speed_input.value,
            "playlist_items": playlist_input.value, "thumbnail": cb_thumb.value, "post_action": post_action_dd.value
        })
        dm.save_config()

        safe_fmt = format_dd.value if format_dd.value else "video"
        safe_qual = quality_dd.value if quality_dd.value else "1080p"

        btn_download.visible = False
        btn_cancel.visible = True
        btn_pause.visible = True
        btn_cancel.disabled = False
        btn_fetch.disabled = True
        dm.is_cancelled = False
        dm.total_files = len(targets)
        dm.current_file_index = 0
        dm.has_download_started = False
        progress_bar.value = 0.0
        prog_label.value = f"Preparing {dm.total_files} items..."
        notify("Download initialized...", "info")
        page.update()
        download_state.update({"progress": 0, "text": "Starting...", "active": True})

        def single_download_task():
            nonlocal session_ytdlp_checked
            try:
                # Core Health Check (Once per session)
                if not session_ytdlp_checked:
                    try:
                        import yt_dlp # type: ignore
                        with yt_dlp.YoutubeDL({'quiet':True}) as ydl: # type: ignore
                            pass
                        session_ytdlp_checked = True
                    except Exception as ydl_ex:
                        log(f"Core engine check failed: {ydl_ex}", "red")
                        notify("Core Engine Error", "error")
                        return

                for index, url in enumerate(targets):
                    if dm.is_cancelled: break
                    dm.current_file_index = index + 1

                    if len(targets) == 1 and url not in metadata_cache:
                        log("Analyzing link before download...", "cyan")
                        try:
                             meta_opts = build_ydl_opts(dm, "video", "1080p", "mp3", is_metadata=True)
                             with yt_dlp.YoutubeDL(meta_opts) as ydl: # type: ignore
                                 info = ydl.extract_info(url, download=False)
                                 # Store with timestamp
                                 metadata_cache[url] = (time.time(), info)
                        except Exception as fetch_ex:
                            log(f"Verification failed: {map_error_message(str(fetch_ex))}", "red", lambda: retry_download_wrapper(url))
                            continue

                    prog_label.value = f"Downloading {dm.current_file_index}/{dm.total_files}..."

                    try:
                        audio_ext = audio_ext_dd.value if safe_fmt == "audio" else "mp3"
                        video_ext = video_ext_dd.value if safe_fmt == "video" else "mp4"
                        opts = build_ydl_opts(dm, safe_fmt, safe_qual, audio_ext, video_ext, progress_hook, my_logger)
                        is_playlist = bool(playlist_input.value.strip()) or "list=" in url
                        title, error, filepath = download_media(url, opts, dm, start_time.value, end_time.value, playlist_input.value, is_playlist)

                        if error:
                            err_msg = map_error_message(error) or str(error)
                            log(err_msg, "red", lambda: retry_download_wrapper(url))
                            continue
                        if dm.is_cancelled:
                            log("⛔ Download cancelled.", "red")
                            break

                        dm.add_history({'title': title, 'date': datetime.now().strftime("%Y-%m-%d %H:%M")})
                        # Track last downloaded file path
                        if filepath:
                            dm.last_downloaded_file = filepath
                        log(f"Finished: {title}", "green")
                    except Exception as ex:
                        err_msg = map_error_message(str(ex))
                        log(err_msg if err_msg is not None else str(ex), "red", lambda: retry_download_wrapper(url))
                        continue

                btn_download.visible = True
                btn_cancel.visible = False
                validate_buttons()
                btn_fetch.disabled = False
                progress_bar.value = 1.0 if not dm.is_cancelled else 0.0
                prog_label.value = "Completed successfully" if not dm.is_cancelled else "Cancelled"
                page.update()

                if not dm.is_cancelled:
                    notify("All Tasks Finished!", "success")
                    execute_post_action(post_action_dd.value, page)
            except Exception as e_glob:
                logging.critical(f"Critical error: {e_glob}")
                notify("Critical Error Occurred", "error")
                btn_download.visible = True
                validate_buttons()
                btn_fetch.disabled = False
                page.update()
        threading.Thread(target=single_download_task, daemon=True, name="Vortex-DownloadThread").start()

    def progress_hook(d):
        from yt_dlp.utils import DownloadCancelled # type: ignore # Local import
        if dm.is_cancelled: raise DownloadCancelled()
        if dm.is_paused:
            raise DownloadCancelled("Paused by user")

        if d["status"] == "downloading":
            dm.has_download_started = True
            downloaded = d.get("downloaded_bytes", 0)
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            percent = (downloaded / total) if total > 0 else 0
            percent = max(0.0, min(percent, 1.0))

            overall = 0.0
            if dm.total_files > 0:
                overall = (dm.current_file_index - 1 + percent) / dm.total_files
                overall = max(0.0, min(overall, 1.0))

            speed = d.get("speed")
            speed_text = f"{speed/1024/1024:.2f} MB/s" if speed else ""
            ui_manager.update_progress(progress_bar, overall, prog_label, f"Downloading... {int(percent * 100)}% {speed_text}")

        elif d["status"] == "postprocessing":
            progress_bar.indeterminate = True
            prog_label.value = "Finalizing file..."
            page.update()

        elif d["status"] == "finished":
            progress_bar.indeterminate = False
            prog_label.value = "Download completed"
            page.update()

    def toggle_theme_click(e):
        new_mode = "light" if dm.config["theme_mode"] == "dark" else "dark"
        dm.config["theme_mode"] = new_mode
        dm.save_config()
        colors = get_theme_colors(new_mode)
        page.theme_mode = new_mode
        page.bgcolor = colors["bg"]
        content_area.bgcolor = colors["bg"]
        nav_rail.bgcolor = colors["sidebar_bg"]
        url_input.bgcolor = colors["input_bg"]
        config_card.bgcolor = colors["surface"]
        log_container.bgcolor = colors["surface"]
        queue_container.bgcolor = colors["surface"]
        preview_container.bgcolor = colors["surface"]
        for control in about_list.controls:
            if isinstance(control, ft.Container): 
                control.bgcolor = colors["surface"] # type: ignore
        txt_uploader.color = colors["secondary_text"]
        txt_duration.color = colors["secondary_text"]
        txt_views.color = colors["secondary_text"]
        log_title.color = colors["text_dim"]
        queue_title.color = colors["text_dim"]
        queue_stats.color = colors["text_dim"]
        divider.color = colors["divider"]
        developed_by.color = colors["text_dim"]
        ibrahim.color = colors["text_dim"]
        basic_settings_text.color = colors["text_main"]
        
        # Dynamic update of action/progress section
        prog_label.color = colors["text_main"] # Updates to Black in Light, White in Dark
        progress_container.bgcolor = colors["input_bg"]
        progress_container.border = ft.border.all(1, colors["border"])
        actions_container.bgcolor = colors["actions_bg"]
        actions_container.border = ft.border.all(1, colors["border"])
        
        title_txt.color = colors["text_main"]
        adv_expansion_tile.subtitle.color = colors["text_dim"]
        est_size_label.bgcolor = colors["surface"]
        est_size_label.border = ft.border.all(1, colors["border"])
        est_size_label.content.controls[0].color = colors["accent"]
        est_size_label.content.controls[1].color = colors["text_main"] if new_mode == "light" else colors["secondary_text"]
        btn_theme.icon = "dark_mode" if new_mode == "light" else "light_mode"
    page.update()
    
    adv_expansion_tile = ft.ExpansionTile(title=ft.Text("Advanced Features", size=14, color=colors["text_main"]), subtitle=ft.Text("Cut, Speed, Playlist, Auto-Action", size=10, color=colors["text_dim"]), controls=[
                ft.Container(padding=10, content=ft.Column([
                    ft.Row([ft.Text("Playlist Items:", size=12, color=colors["text_main"]), playlist_input]),
                    ft.Row([ft.Text("Time Cut:", size=12, color=colors["text_main"]), start_time, end_time]),
                    ft.Row([ft.Text("Speed Limit:", size=12, color=colors["text_main"]), speed_input]),
                    ft.Row([ft.Text("When Done:", size=12, color=colors["text_main"]), post_action_dd]),
                ]))
            ])

    def update_ui_visibility():
        mode = dm.config.get("ui_mode", "simple")
        is_adv = mode == "advanced"
        
        # Simple/Advanced Visibilty Logic
        adv_expansion_tile.visible = is_adv
        cb_organize.visible = is_adv
        cb_thumb.visible = is_adv
        cb_subs.visible = is_adv
        cb_embed.visible = is_adv
        cb_sponsor.visible = is_adv
        
        btn_ui_mode.selected = is_adv
        btn_ui_mode.icon = "settings" if is_adv else "tune"
        btn_ui_mode.tooltip = "Switch to Simple Mode" if is_adv else "Switch to Advanced Mode"
        
        update_dynamic_options()
        page.update()

    def toggle_ui_mode_click(e):
        current = dm.config.get("ui_mode", "simple")
        new_mode = "advanced" if current == "simple" else "simple"
        dm.config["ui_mode"] = new_mode
        dm.save_config()
        update_ui_visibility()
        notify(f"Switched to {new_mode.capitalize()} Mode", "info")

    btn_ui_mode = ft.IconButton(icon="tune", tooltip="Toggle Simple/Advanced Mode", on_click=toggle_ui_mode_click)

    btn_fetch = ft.IconButton(icon=ft.icons.ARROW_FORWARD_ROUNDED, on_click=fetch_info_click, bgcolor=colors["primary"], icon_color="white", width=60, height=60, style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=20)))
    btn_download = ft.ElevatedButton("Start Download", icon=ft.icons.DOWNLOAD_ROUNDED, width=160, height=50, style=ft.ButtonStyle(bgcolor=colors["primary"], color="white", shape=ft.RoundedRectangleBorder(radius=25), elevation=5), on_click=download_click, disabled=True)
    btn_cancel = ft.ElevatedButton("Stop", icon=ft.icons.STOP_ROUNDED, width=160, height=50, visible=False, style=ft.ButtonStyle(bgcolor=colors["error"], color="white", shape=ft.RoundedRectangleBorder(radius=25)), on_click=cancel_download_click)
    btn_pause = ft.ElevatedButton("Pause", icon=ft.icons.PAUSE_ROUNDED, width=160, height=50, visible=False, style=ft.ButtonStyle(bgcolor="#F59E0B", color="white", shape=ft.RoundedRectangleBorder(radius=25)), on_click=pause_resume_click)
    btn_open_file = ft.ElevatedButton("Open File", icon=ft.icons.OPEN_IN_NEW_ROUNDED, width=160, height=50, style=ft.ButtonStyle(bgcolor=colors["surface"], color=colors["primary"], shape=ft.RoundedRectangleBorder(radius=25), side=ft.BorderSide(1, colors["primary"])), on_click=open_file_click)
    
    config_card = ft.Container(
        bgcolor=colors["surface"], padding=25, border_radius=20, border=ft.border.all(1, colors["border"]),
        shadow=ft.BoxShadow(spread_radius=1, blur_radius=15, color=colors["shadow"], offset=ft.Offset(0, 4)),
        content=ft.Column([
            ft.Row([preset_dd], alignment="start"),
            ft.Row([format_dd, quality_dd, video_ext_dd, audio_ext_dd]),
            ft.Row([est_size_label], alignment="start"),
            ft.Divider(height=20, color="transparent"),
            adv_expansion_tile,
            ft.Divider(color="transparent", height=10),
            ft.Row([cb_organize, cb_thumb], wrap=True),
            ft.Row([cb_subs, cb_embed, cb_sponsor], wrap=True)
        ])
    )

    preview_container = ft.Container(
        content=ft.Column([img_preview, ft.Divider(height=15, color="transparent"), title_txt, meta_row], horizontal_alignment="center"), 
        bgcolor=colors["surface"], padding=25, border_radius=24, border=ft.border.all(1, colors["border"]), alignment=ft.alignment.top_center,
        shadow=ft.BoxShadow(spread_radius=1, blur_radius=20, color=colors["shadow"], offset=ft.Offset(0, 8))
    )
    
    # --- Enhanced Queue Logic ---
    def update_queue_display():
        queue_display.controls.clear()
        for item in dm.queue:
             queue_display.controls.append(
                ft.Row([
                    ft.Text(item, size=12, expand=True, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                    ft.IconButton(icon="close", icon_size=16, tooltip="Remove", on_click=lambda e, url=item: remove_queue_item(url))
                ], alignment="spaceBetween")
             )
        queue_stats.value = f"Queue: {len(dm.queue)} items"
        recalculate_size()
        page.update()

    def remove_queue_item(url):
        dm.remove_from_queue(url)
        update_queue_display()

    def add_to_queue_click(e):
        url = url_input.value.strip()
        if not url: return
        dm.add_to_queue(url)
        update_queue_display()
        notify("Added to queue!", "success")

    def start_queue_click(e):
        if not dm.queue:
            notify("Queue is empty!", "warning")
            return

        # Thread Guard
        for t in threading.enumerate():
            if t.name == "Vortex-DownloadThread" and t.is_alive():
                notify("A download is already active!", "warning")
                return

        # Save Path Validation
        try:
            os.makedirs(str(dm.config["save_path"]), exist_ok=True)
        except Exception as os_ex:
            notify(f"Invalid Save Path: {os_ex}", "error")
            return

        dm.config.update({
            "smart_organize": cb_organize.value, "subtitles": cb_subs.value, "embed_subs": cb_embed.value,
            "sponsorblock": cb_sponsor.value, "speed_limit": speed_input.value,
            "playlist_items": playlist_input.value, "thumbnail": cb_thumb.value, "post_action": post_action_dd.value
        })
        dm.save_config()

        safe_fmt = format_dd.value if format_dd.value else "video"
        safe_qual = quality_dd.value if quality_dd.value else "1080p"

        set_state(DOWNLOAD_STATE["QUEUE_RUNNING"])
        dm.is_cancelled = False
        dm.total_files = len(dm.queue)
        dm.current_file_index = 0

        progress_bar.value = 0.0
        prog_label.value = f"Queue: 0/{dm.total_files}"
        notify("Queue Download Started...", "info")
        page.update()

        def queue_download_task():
            import yt_dlp # type: ignore
            try:
                # Clone queue to iterate safely
                queue_items = list(dm.queue)
                processed_count: int = 0

                for url in queue_items:
                    if dm.is_cancelled: break
                    dm.current_file_index = int(processed_count) + 1
                    # Get title for display
                    try:
                        meta_opts = build_ydl_opts(dm, "video", "1080p", "mp3", is_metadata=True)
                        with yt_dlp.YoutubeDL(meta_opts) as ydl:
                            info = ydl.extract_info(url, download=False)
                            current_title = info.get('title', url)[:30] if 'entries' not in info else "Playlist"
                    except:
                        current_title = "%.30s" % (str(url),)
                    prog_label.value = f"Queue: {dm.current_file_index}/{dm.total_files} - {current_title}"

                    try:
                        audio_ext = audio_ext_dd.value if safe_fmt == "audio" else "mp3"
                        video_ext = video_ext_dd.value if safe_fmt == "video" else "mp4"
                        opts = build_ydl_opts(dm, safe_fmt, safe_qual, audio_ext, video_ext, progress_hook, my_logger)
                        is_playlist = bool(playlist_input.value.strip()) or "list=" in url

                        title, error, filepath = download_media(url, opts, dm, start_time.value, end_time.value, playlist_input.value, is_playlist)

                        if error:
                            err_msg = map_error_message(error) or str(error)
                            log(err_msg, "red", lambda: retry_download_wrapper(url))
                            continue # Failed items remain in queue

                        if dm.is_cancelled:
                            log("⛔ Download cancelled.", "red")
                            break

                        dm.add_history({'title': title, 'date': datetime.now().strftime("%Y-%m-%d %H:%M")})
                        log(f"Finished: {title}", "green")

                        # Remove successful item from queue
                        dm.remove_from_queue(url)

                    except Exception as ex:
                        err_msg = map_error_message(str(ex))
                        log(err_msg if err_msg is not None else str(ex), "red", lambda: retry_download_wrapper(url))
                        continue

                    processed_count = int(str(processed_count)) + 1
                # Refresh queue display at end
                dm.load_queue()
                update_queue_display()

                if not dm.is_cancelled:
                    set_state(DOWNLOAD_STATE["FINISHED"])
                    notify("Queue Processing Finished!", "success")
                    execute_post_action(post_action_dd.value, page)
                else:
                    set_state(DOWNLOAD_STATE["CANCELLED"])
                    evaluate_ready_state()

            except Exception as e_glob:
                set_state(DOWNLOAD_STATE["ERROR"])
                notify("Critical Error in Queue", "error")
        threading.Thread(target=queue_download_task, daemon=True, name="Vortex-DownloadThread").start()

    btn_add_queue = ft.ElevatedButton("Add to Queue", icon=ft.icons.ADD_ROUNDED, width=160, height=50, style=ft.ButtonStyle(bgcolor=colors["surface"], color=colors["primary"], shape=ft.RoundedRectangleBorder(radius=25), side=ft.BorderSide(1, colors["border"])), on_click=add_to_queue_click, disabled=True)
    btn_start_queue = ft.ElevatedButton("Start Queue", icon=ft.icons.PLAY_ARROW_ROUNDED, width=160, height=50, style=ft.ButtonStyle(bgcolor=colors["accent"], color="white", shape=ft.RoundedRectangleBorder(radius=25), elevation=5), on_click=start_queue_click)

    def set_state(new_state: str):
        app_state["state"] = new_state
        sync_ui_with_state()

    def sync_ui_with_state():
        state = app_state["state"]
        btn_download.visible = state in ["idle", "ready", "finished", "cancelled"]
        btn_download.disabled = state not in ["ready"]
        btn_fetch.disabled = state in ["downloading", "queue_running"]
        btn_cancel.visible = state in ["downloading", "queue_running"]
        btn_cancel.disabled = False
        btn_pause.visible = state == "downloading"
        btn_add_queue.disabled = state not in ["ready"]
        btn_start_queue.disabled = state != "ready"
        progress_bar.visible = state in ["downloading", "queue_running", "paused"]
        
        is_active = state in ["downloading", "queue_running", "paused"]
        try:
            progress_container.visible = is_active
            progress_container.opacity = 1 if is_active else 0
            progress_container.height = 80 if is_active else 0
        except NameError:
            pass
            
        if state == "idle":
            prog_label.value = "Idle"
        elif state == "ready":
            prog_label.value = "Ready"
        elif state == "fetching":
            prog_label.value = "Analyzing link..."
        elif state == "downloading":
            prog_label.value = "Downloading..."
        elif state == "paused":
            prog_label.value = "Paused"
        elif state == "finished":
            prog_label.value = "Completed"
        elif state == "cancelled":
            prog_label.value = "Cancelled"
        elif state == "error":
            prog_label.value = "Error"
        page.update()

    def evaluate_ready_state():
        if (
            url_input.value
            and is_valid_url(url_input.value)
            and dm.config["save_path"]
        ):
            set_state(DOWNLOAD_STATE["READY"])
        else:
            set_state(DOWNLOAD_STATE["IDLE"])

    def pause_download():
        dm.is_paused = True
        set_state(DOWNLOAD_STATE["PAUSED"])

    def resume_download():
        dm.is_paused = False
        set_state(DOWNLOAD_STATE["DOWNLOADING"])

    log_title = ft.Text("Log (Real Output)", size=12, weight="bold", color=colors["text_dim"])
    queue_title = ft.Text("Download Queue", size=12, weight="bold", color=colors["text_dim"])
    basic_settings_text = ft.Text("Basic Settings", weight="bold", color=colors["text_main"])
    divider = ft.VerticalDivider(width=1, color=colors["divider"])
    developed_by = ft.Text("Developed by", size=10, color=colors["text_dim"])
    ibrahim = ft.Text("Ibrahim Khaled", size=12, weight="bold", color=colors["text_dim"])

    # Define inner progress container separately to allow updates
    progress_container = ft.Container(
        content=ft.Column([
            ft.Row([prog_label], alignment="center"),
            ft.Container(content=progress_bar, padding=ft.padding.symmetric(horizontal=20), alignment=ft.alignment.center)
        ], alignment="center"),
        bgcolor=colors["input_bg"], border_radius=15,
        animate_opacity=300, animate_size=300,
        opacity=0, height=0, visible=False
    )

    # Define outer actions container separately to allow updates
    actions_container = ft.Container(
        content=ft.Column([
            ft.Container(
                content=ft.Row([btn_download, btn_add_queue, btn_start_queue, btn_open_file, btn_cancel, btn_pause], alignment="center", spacing=15, wrap=True),
                padding=ft.padding.symmetric(vertical=10),
                alignment=ft.alignment.center
            ),
            progress_container
        ]),
        padding=ft.padding.all(25),
        bgcolor=colors["actions_bg"], border_radius=20,
        shadow=ft.BoxShadow(spread_radius=1, blur_radius=15, color=colors["shadow"], offset=ft.Offset(0, 4))
    )

    home_view = ft.Container(
        content=ft.Column([
            # Hero layout
            preview_container,
            ft.Container(
                content=ft.Row([url_input, btn_fetch, btn_import, btn_ui_mode], alignment="center"),
                padding=ft.padding.symmetric(vertical=10)
            ),
            actions_container,
            config_card,
            ft.ResponsiveRow([
                ft.Column([log_title, log_container], col={"sm": 12, "md": 6}),
                ft.Column([queue_title, queue_container], col={"sm": 12, "md": 6})
            ])
        ], expand=True, scroll="auto", spacing=20),
        padding=20
    )

    def path_change(e):
        if os.path.isabs(path_txt.value):
            dm.config["save_path"] = path_txt.value
        else:
            dm.config["save_path"] = os.path.join(os.path.expanduser("~"), path_txt.value)
        dm.save_config()
        validate_buttons()
    path_txt = ft.TextField(label="Save Path", value=dm.config["save_path"], read_only=False, expand=True, on_change=path_change)
    
    def on_picker_result(e):
        if e.path:
            dm.config.update({"save_path": e.path})
            dm.save_config()
            path_txt.value = e.path
            validate_buttons()
            page.update()
    picker = ft.FilePicker(on_result=on_picker_result)
    
    cookies_in = ft.TextField(label="Cookies.txt Path", value=dm.config["cookies_path"], icon="cookie", suffix=ft.IconButton(icon="folder_open", on_click=lambda _: cookie_picker.pick_files(allowed_extensions=["txt"])))
    cookie_picker = ft.FilePicker(on_result=lambda e: [setattr(cookies_in, "value", e.files[0].path), dm.config.update({"cookies_path": e.files[0].path}), dm.save_config(), page.update()] if e.files else None)
    
    ffmpeg_in = ft.TextField(label="FFmpeg Path (Optional)", value=dm.config.get("ffmpeg_path",""), icon="settings_applications", suffix=ft.IconButton(icon="folder_open", on_click=lambda _: ffmpeg_picker.pick_files()))
    ffmpeg_picker = ft.FilePicker(on_result=lambda e: [setattr(ffmpeg_in, "value", e.files[0].path), dm.config.update({"ffmpeg_path": e.files[0].path}), dm.save_config(), page.update()] if e.files else None)
    
    page.overlay.extend([picker, cookie_picker, ffmpeg_picker])
    
    proxy_settings_in = ft.TextField(label="Proxy URL", value=dm.config["proxy"], icon="security", hint_text="http://user:pass@ip:port")
    filename_dd = ft.Dropdown(label="File Naming Style", value=dm.config.get("filename_template", "%(title)s.%(ext)s"), prefix_icon="text_fields", options=[
        ft.dropdown.Option(key="%(title)s.%(ext)s", text="Video Title (Default)"),
        ft.dropdown.Option(key="%(uploader)s - %(title)s.%(ext)s", text="Channel - Video Title"),
        ft.dropdown.Option(key="%(title)s [%(id)s].%(ext)s", text="Title [Video ID]"),
        ft.dropdown.Option(key="%(upload_date)s - %(title)s.%(ext)s", text="Date - Title"),
    ])
    
    sw_monitor = ft.Switch(label="Clipboard Monitor", value=dm.config["clipboard_monitor"])
    sw_notifications = ft.Switch(label="Show Notifications", value=dm.config.get("notifications", True))
    
    custom_user_agent_in = ft.TextField(label="Custom User Agent", value=dm.config.get("custom_user_agent", ""), hint_text="Leave empty for default")
    embed_metadata_cb = ft.Checkbox(label="Embed Metadata", value=dm.config.get("embed_metadata", False))
    download_delay_in = ft.TextField(label="Download Delay (seconds)", value=str(dm.config.get("download_delay", 0)), hint_text="0 for no delay")
    log_verbosity_dd = ft.Dropdown(label="Log Verbosity", value=dm.config.get("log_verbosity", "Standard"), options=[ft.dropdown.Option("Quiet"), ft.dropdown.Option("Standard"), ft.dropdown.Option("Verbose")])
    
    def save_settings_click(e):
        dm.config.update({
            "proxy": proxy_settings_in.value,
            "filename_template": filename_dd.value,
            "clipboard_monitor": sw_monitor.value,
            "notifications": sw_notifications.value,
            "cookies_path": cookies_in.value,
            "ffmpeg_path": ffmpeg_in.value,
            "custom_user_agent": custom_user_agent_in.value,
            "embed_metadata": embed_metadata_cb.value,
            "download_delay": int(download_delay_in.value) if download_delay_in.value.isdigit() else 0,
            "log_verbosity": log_verbosity_dd.value,
        })
        dm.save_config()
        notify("Settings Saved Successfully!", "success")

    def reset_app(e):
        dm.reset_config()
        path_txt.value = dm.config["save_path"]
        # Reset simple fields to defaults
        cookies_in.value = ""
        proxy_settings_in.value = ""
        ffmpeg_in.value = ""
        filename_dd.value = "%(title)s.%(ext)s"
        sw_monitor.value = True
        sw_notifications.value = True
        custom_user_agent_in.value = ""
        embed_metadata_cb.value = False
        download_delay_in.value = "0"
        log_verbosity_dd.value = "Standard"
        # Reset UI
        validate_buttons()
        page.update()
        notify("App Reset to Defaults!", "success")

    def update_core(e):
        import subprocess
        log("Updating Core...", "orange"); notify("Checking for updates...", "info")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"])
            log("Core Updated!", "green"); notify("Core Updated Successfully!", "success")
        except Exception as ex:
            log(f"Update failed: {ex}", "red"); notify("Update Failed!", "error")

    def check_updates_click(e):
        check_for_updates(page, dm, notify)

    basic_tab = ft.Tab(
        tab_content=ft.Text("Basic Settings"),
        content=ft.ListView(controls=[
            ft.Text("General", size=20, weight="bold", color=colors["primary"]), ft.Row([path_txt, ft.IconButton("folder", on_click=lambda _: picker.get_directory_path())]), 
            ft.Row([sw_monitor, sw_notifications], spacing=20),
            ft.Divider(),
            ft.Text("Maintenance", size=20, weight="bold", color=colors["primary"]), 
            ft.Row([ft.ElevatedButton("Update Core", icon="update", on_click=update_core), ft.ElevatedButton("Check for Updates", icon="system_update", on_click=check_updates_click), ft.ElevatedButton("Save All", icon="save", on_click=save_settings_click), ft.ElevatedButton("Reset App", icon="restore", color="white", bgcolor="red", on_click=reset_app)], spacing=10)
        ], padding=30, spacing=15, expand=True)
    )

    advanced_tab = ft.Tab(
        tab_content=ft.Text("Advanced Settings"),
        content=ft.ListView(controls=[
            ft.Text("Authentication & Network", size=18, weight="bold", color=colors["primary"]),
            cookies_in, proxy_settings_in, custom_user_agent_in,
            ft.Divider(),
            ft.Text("System & File", size=18, weight="bold", color=colors["primary"]),
            ffmpeg_in, filename_dd,
            ft.Divider(),
            ft.Text("Download Behavior", size=18, weight="bold", color=colors["primary"]),
            ft.Row([download_delay_in, log_verbosity_dd]),
            embed_metadata_cb,
            ft.ElevatedButton("Save Advanced Settings", icon="save", on_click=save_settings_click)
        ], padding=30, spacing=10, expand=True)
    )

    history_list = ft.ListView(expand=True, spacing=10)
    def refresh_history():
        history_list.controls.clear()
        if not dm.history:
            history_list.controls.append(
                ft.Container(
                    content=ft.Column([
                        ft.Icon(ft.icons.HISTORY_ROUNDED, size=64, color=colors["text_dim"]),
                        ft.Text("No Download History Yet", size=18, weight="w600", color=colors["text_main"]),
                        ft.Text("Complete a download and it will show up here.", size=14, color=colors["text_dim"])
                    ], alignment="center", horizontal_alignment="center"),
                    padding=50, alignment=ft.alignment.center
                )
            )
        else:
            for item in dm.history: 
                history_list.controls.append(
                    ft.Container(
                        content=ft.ListTile(
                            leading=ft.Icon(ft.icons.CHECK_CIRCLE_ROUNDED, color=colors["success"], size=32),
                            title=ft.Text("%.60s" % str(item.get('title', '')), weight="w600"),
                            subtitle=ft.Text(str(item.get('date', '')), color=colors["text_dim"]),
                            on_click=lambda e: getattr(os, 'startfile')(str(dm.config["save_path"])) if sys.platform == 'win32' and hasattr(os, 'startfile') else None
                        ),
                        bgcolor=colors["surface"],
                        border_radius=15,
                        border=ft.border.all(1, colors["border"]),
                        on_hover=lambda e: setattr(e.control, 'bgcolor', colors["input_bg"] if e.data == "true" else colors["surface"]) or page.update()
                    )
                ) # type: ignore
        page.update()
    
    history_view = ft.Container(
        content=ft.Column([
            ft.Row([
                ft.Text("Download History", size=28, weight="w800", color=colors["text_main"]), 
                ft.ElevatedButton("Clear All", icon=ft.icons.DELETE_ROUNDED, color="white", bgcolor=colors["error"], on_click=lambda e: [dm.clear_history(), refresh_history()], style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=20)))
            ], alignment="spaceBetween"), 
            ft.Divider(height=20, color="transparent"), 
            history_list
        ], expand=True),
        padding=20, expand=True
    )

    about_list = ft.ListView(expand=True, spacing=10)
    features_data = [("4K/8K Support", "Download videos in 2160p, 1440p."), ("Audio Conversion", "Convert to MP3, M4A, WAV."), ("Smart Organize", "Auto-folder by channel name."), ("Playlist Control", "Download specific items."), ("Time Trimming", "Cut specific parts."), ("SponsorBlock", "Auto-skip segments."), ("Subtitles", "Embed subtitles."), ("Bulk Download", "Import links via TXT file."), ("Clipboard Monitor", "Automatically detect and load links from clipboard.")]
    about_container = ft.Column([
        ft.Container(
            content=ft.Icon(ft.icons.BOLT_ROUNDED, size=80, color=colors["primary"]),
            padding=20, bgcolor=colors["surface"], border_radius=50, shadow=ft.BoxShadow(spread_radius=1, blur_radius=20, color=colors["accent"], offset=ft.Offset(0,0))
        ),
        ft.Text(f"{APP_TITLE} {APP_VERSION}", size=36, weight="w900", color=colors["text_main"]),
        ft.Container(content=ft.Text("Professional Media Downloader", size=16, color=colors["text_dim"]), bgcolor=colors["surface"], padding=ft.padding.symmetric(horizontal=15, vertical=5), border_radius=20),
        ft.Divider(height=40, color="transparent"),
        ft.Text("Key Features", size=24, weight="w800", color=colors["text_main"]), 
        about_list
    ], horizontal_alignment="center", scroll="auto")
    for title, desc in features_data: 
        about_list.controls.append(ft.Container(content=ft.Row([ft.Icon(ft.icons.CHECK_CIRCLE_ROUNDED, color=colors["accent"]), ft.Column([ft.Text(title, weight="w600", color=colors["text_main"]), ft.Text(desc, size=12, color=colors["text_dim"])])]), padding=15, bgcolor=colors["surface"], border_radius=15, border=ft.border.all(1, colors["border"])))
    about_view = ft.Container(content=about_container, padding=40)

    def settings_card(title, icon_name, controls):
        return ft.Container(
            content=ft.Column([
                ft.Row([ft.Icon(icon_name, color=colors["primary"]), ft.Text(title, size=20, weight="w800", color=colors["text_main"])]),
                ft.Divider(height=10, color="transparent"),
                *controls
            ]),
            padding=25, margin=ft.margin.only(bottom=20),
            bgcolor=colors["surface"], border_radius=20, border=ft.border.all(1, colors["border"]),
            shadow=ft.BoxShadow(spread_radius=1, blur_radius=10, color=colors["shadow"], offset=ft.Offset(0, 4))
        )

    settings_view = ft.Container(
        content=ft.ListView(controls=[
            ft.Text("Settings", size=28, weight="w800", color=colors["text_main"]),
            ft.Divider(height=20, color="transparent"),
            settings_card("General", ft.icons.TUNE_ROUNDED, [
                ft.Row([path_txt, ft.IconButton(ft.icons.FOLDER_ROUNDED, on_click=lambda _: picker.get_directory_path(), icon_color=colors["text_dim"])]),
                ft.Row([sw_monitor, sw_notifications], spacing=20),
            ]),
            settings_card("Authentication & Network", ft.icons.SECURITY_ROUNDED, [
                cookies_in, proxy_settings_in, custom_user_agent_in,
            ]),
            settings_card("System & File", ft.icons.COMPUTER_ROUNDED, [
                ffmpeg_in, filename_dd,
            ]),
            settings_card("Download Behavior", ft.icons.DOWNLOAD_ROUNDED, [
                ft.Row([download_delay_in, log_verbosity_dd]),
                embed_metadata_cb,
            ]),
            settings_card("Maintenance", ft.icons.BUILD_ROUNDED, [
                ft.Row([
                    ft.ElevatedButton("Update Core", icon=ft.icons.UPDATE_ROUNDED, on_click=update_core, style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=20))),
                    ft.ElevatedButton("Check for Updates", icon=ft.icons.SYSTEM_UPDATE_ROUNDED, on_click=check_updates_click, style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=20))),
                    ft.ElevatedButton("Save All", icon=ft.icons.SAVE_ROUNDED, on_click=save_settings_click, style=ft.ButtonStyle(bgcolor=colors["primary"], color="white", shape=ft.RoundedRectangleBorder(radius=20))),
                    ft.ElevatedButton("Reset App", icon=ft.icons.RESTORE_ROUNDED, color="white", bgcolor=colors["error"], on_click=reset_app, style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=20)))
                ], spacing=10, wrap=True),
            ])
        ], padding=20, spacing=0, expand=True),
        expand=True
    )

    def nav_change(e):
        idx = e.control.selected_index
        if idx == 0: content_area.content = home_view
        elif idx == 1: content_area.content = settings_view
        elif idx == 2: refresh_history(); content_area.content = history_view
        elif idx == 3: content_area.content = about_view
        page.update()

    btn_theme = ft.IconButton(icon="light_mode" if dm.config["theme_mode"] == "dark" else "dark_mode", on_click=toggle_theme_click)
    if os.path.exists("icon.png"): leading_content = ft.Row([ft.Image(src="icon.png", width=40, height=40, fit="contain"), ft.Text("Vortex", size=20, weight="bold")], alignment="center", spacing=10)
    else: leading_content = ft.Row([ft.Icon("bolt", size=30, color=colors["primary"]), ft.Text("Vortex", size=20, weight="bold")], alignment="center", spacing=10)
    
    nav_rail = ft.NavigationRail(
        selected_index=0, label_type="all", min_width=100, min_extended_width=200, group_alignment=-0.9,
        leading=ft.Container(content=leading_content, padding=30),
        trailing=ft.Container(content=ft.Column([ft.Divider(), btn_theme, ft.Container(height=10), developed_by, ibrahim], horizontal_alignment="center", spacing=0), padding=ft.padding.only(bottom=20)),
        destinations=[ft.NavigationRailDestination(icon="home", selected_icon="home", label="Home"), ft.NavigationRailDestination(icon="settings", selected_icon="settings", label="Settings"), ft.NavigationRailDestination(icon="history", selected_icon="history", label="History"), ft.NavigationRailDestination(icon="info_outline", selected_icon="info", label="About")],
        on_change=nav_change, bgcolor=colors["sidebar_bg"]
    )

    page.add(ft.Row([nav_rail, divider, content_area], expand=True))
    update_dynamic_options()
    update_ui_visibility()
    update_queue_display()
    validate_buttons()
    
    content_area.content = home_view
    page.update()

    def paste_link(url_to_paste):
        url_input.value = url_to_paste
        validate_buttons()
        page.update()
        fetch_info_click(None)

    def monitor():
        last = ""
        while ui_manager._running:
            if dm.config["clipboard_monitor"]:
                try:
                    curr = page.get_clipboard()
                    if curr and curr != last and is_valid_url(curr):
                        last = curr
                        # Automatically paste and fetch the video info
                        paste_link(curr)
                        ui_manager.queue_notification(
                            "Link Detected",
                            "Video link loaded and analyzed automatically!",
                            "success"
                        )
                except Exception as ex:
                    pass
            time.sleep(1)

    threading.Thread(target=monitor, daemon=True, name="Vortex-ClipboardMonitor").start()

if __name__ == "__main__":
    try:
        ft.app(target=main)
    except Exception as ex:
        logging.critical(f"Application crashed: {ex}")
    finally:
        # Graceful shutdown: stop UI manager
        if ui_manager is not None:
            ui_manager.stop()