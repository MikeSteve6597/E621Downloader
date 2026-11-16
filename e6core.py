"""E6Dler 共享核心：配置、登录鉴权、e621 API 与下载。

配置保存在用户目录：C:\\Users\\<用户名>\\E6Dler\\userdata.json
不向程序目录或 exe 写入任何账号信息。
"""

from __future__ import annotations

import base64
import hashlib
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable, Optional

import requests

APP_NAME = "E6Dler"
APP_VERSION = "1.5"
API_ROOT = "https://e621.net"

DOWNLOAD_DIR = Path.home() / "Downloads" / "E6dl"
CONFIG_FILE = Path.home() / "E6Dler" / "userdata.json"

DEFAULT_MIN_SCORE = 10
DEFAULT_LIMIT = 50
DEFAULT_MAX_PAGES = 5
DELAY_BETWEEN_REQUESTS = 1.1
MAX_HISTORY = 10

QUALITY_LABELS = {"1": "原图", "2": "采样图", "3": "预览图"}
VIDEO_EXTS = {"webm", "mp4", "swf"}
REQUEST_TIMEOUT = 20

# --------------------------------------------------------------------------- #
# 单机模式 / 在线模式：全局运行开关与网络门禁
# --------------------------------------------------------------------------- #

MODE_OFFLINE = "offline"
MODE_ONLINE = "online"
DEFAULT_MODE = MODE_OFFLINE
_MODE = DEFAULT_MODE


class OfflineModeError(RuntimeError):
    """单机模式下尝试发起网络请求时抛出。"""


def current_mode() -> str:
    return _MODE


def is_online() -> bool:
    return _MODE == MODE_ONLINE


def set_mode(mode: str) -> str:
    """设置全局运行模式，非法值一律归为单机模式。"""
    global _MODE
    _MODE = MODE_ONLINE if str(mode or "").strip().lower() == MODE_ONLINE else MODE_OFFLINE
    return _MODE


def sync_mode_from_config(config: Optional[dict] = None) -> str:
    cfg = config or {}
    return set_mode(cfg.get("mode", DEFAULT_MODE))


def set_mode_in_config(config: dict, mode: str) -> str:
    """仅写入配置字典，不落盘。"""
    value = MODE_ONLINE if str(mode or "").strip().lower() == MODE_ONLINE else MODE_OFFLINE
    if isinstance(config, dict):
        config["mode"] = value
    return value


def save_mode(config: dict, mode: str) -> str:
    value = set_mode_in_config(config, mode)
    set_mode(value)
    save_config(config)
    return value


def require_online() -> None:
    if not _MODE == MODE_ONLINE:
        raise OfflineModeError("当前为单机模式，已禁止联网请求")


def load_config() -> dict:
    try:
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if not isinstance(data, dict):
                    return {}
                if data.get("mode") not in (MODE_OFFLINE, MODE_ONLINE):
                    data["mode"] = DEFAULT_MODE
                sync_mode_from_config(data)
                return data
    except Exception:
        pass
    return {}


def save_config(data: dict) -> None:
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def add_to_history(config: dict, tags: list, blacklist: list) -> None:
    history = config.setdefault("history", [])
    record = {
        "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "tags": list(tags),
        "blacklist": list(blacklist),
    }
    for old in list(history):
        if old.get("tags") == record["tags"] and old.get("blacklist") == record["blacklist"]:
            history.remove(old)
    history.insert(0, record)
    del history[MAX_HISTORY:]
    save_config(config)


# --------------------------------------------------------------------------- #
# 搜索关键词记忆
# --------------------------------------------------------------------------- #

DEFAULT_KEYWORD_MEMORY = 10
MAX_KEYWORD_MEMORY = 50
KEYWORD_HISTORY_KEY = "recent_keywords"


def keywords_limit(config: Optional[dict] = None) -> int:
    """关键词记忆条数上限：缺失默认 10，取值裁剪到 0-50，0 表示不记忆。"""
    cfg = config or {}
    ui = cfg.get("ui")
    raw = ui.get("keyword_memory") if isinstance(ui, dict) else None
    try:
        value = int(raw) if raw is not None else DEFAULT_KEYWORD_MEMORY
    except (TypeError, ValueError):
        value = DEFAULT_KEYWORD_MEMORY
    return max(0, min(MAX_KEYWORD_MEMORY, value))


def get_recent_keywords(config: Optional[dict] = None) -> list[str]:
    cfg = config or {}
    raw = cfg.get(KEYWORD_HISTORY_KEY)
    if not isinstance(raw, list):
        return []
    limit = keywords_limit(cfg)
    if limit == 0:
        return []
    items = [item for item in raw if isinstance(item, str) and item.strip()]
    return items[:limit]


def add_recent_keyword(config: dict, keyword: str) -> list[str]:
    """记录一条搜索关键词：去重、插到最前、按上限裁剪；limit 为 0 时清空。仅写回配置字典，不落盘。"""
    if not isinstance(config, dict):
        return []
    limit = keywords_limit(config)
    if limit == 0:
        config[KEYWORD_HISTORY_KEY] = []
        return []
    text = (keyword or "").strip()
    if not text:
        return get_recent_keywords(config)
    lowered = text.lower()
    items = [item for item in get_recent_keywords(config) if item.lower() != lowered]
    items.insert(0, text)
    del items[limit:]
    config[KEYWORD_HISTORY_KEY] = items
    return items


def make_auth_header(username: str, api_key: str) -> str:
    token = base64.b64encode(f"{username}:{api_key}".encode()).decode()
    return "Basic " + token


def user_agent(username: Optional[str] = None) -> str:
    if username:
        return f"E6dl/{APP_VERSION} (by {username} on e621)"
    return f"E6dl/{APP_VERSION} (anonymous)"


def make_session(config: Optional[dict] = None, guest: bool = False) -> requests.Session:
    require_online()
    cfg = config or {}
    session = requests.Session()
    headers = {"Accept": "application/json"}
    if not guest and cfg.get("username") and cfg.get("api_key"):
        headers["User-Agent"] = user_agent(cfg["username"])
        headers["Authorization"] = make_auth_header(cfg["username"], cfg["api_key"])
    else:
        headers["User-Agent"] = user_agent()
    session.headers.update(headers)
    return session


def session_for(username: str, api_key: str) -> requests.Session:
    require_online()
    session = requests.Session()
    session.headers.update(
        {
            "Accept": "application/json",
            "User-Agent": user_agent(username),
            "Authorization": make_auth_header(username, api_key),
        }
    )
    return session


def validate_login(username: str, api_key: str) -> tuple[bool, int, str]:
    """返回 (是否成功, HTTP 状态码, 提示文本)。网络异常时状态码为 0。"""
    require_online()
    try:
        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": user_agent(username),
                "Authorization": make_auth_header(username, api_key),
                "Accept": "application/json",
            }
        )
        resp = session.get(f"{API_ROOT}/users/me.json", timeout=12)
        if resp.status_code == 200:
            return True, 200, "登录成功"
        if resp.status_code == 401:
            return False, 401, "用户名或 API Key 错误"
        return False, resp.status_code, f"验证失败（HTTP {resp.status_code}）"
    except Exception as exc:  # noqa: BLE001
        return False, 0, f"网络错误：{exc}"


def get_image_url(post: dict, quality: str) -> Optional[str]:
    file_info = post.get("file") or {}
    sample_info = post.get("sample") or {}
    preview_info = post.get("preview") or {}
    if quality == "1":
        return file_info.get("url") or sample_info.get("url") or preview_info.get("url")
    if quality == "2":
        return sample_info.get("url") or file_info.get("url") or preview_info.get("url")
    return preview_info.get("url") or sample_info.get("url") or file_info.get("url")


def build_search_tags(tags: Iterable[str], blacklist: Iterable[str], min_score: int) -> str:
    search_tags = list(tags)
    for tag in blacklist:
        search_tags.append(f"-{tag}")
    tag_str = " ".join(search_tags)
    if min_score is not None:
        tag_str = f"{tag_str} score:>={min_score}"
    return tag_str.strip()


def fetch_posts(
    session: requests.Session,
    tags: str | Iterable[str],
    limit: int = 24,
    page: int = 1,
    min_score: Optional[int] = None,
    blacklist: Iterable[str] = (),
) -> list[dict]:
    require_online()
    if isinstance(tags, str):
        tag_str = tags
        if blacklist:
            tag_str = build_search_tags([tags], blacklist, min_score if min_score is not None else 0)
        elif min_score is not None:
            tag_str = f"{tags} score:>={min_score}"
    else:
        tag_str = build_search_tags(tags, blacklist, min_score if min_score is not None else 0)
    resp = session.get(
        f"{API_ROOT}/posts.json",
        params={"tags": tag_str, "limit": limit, "page": page},
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json().get("posts", [])


def fetch_post(session: requests.Session, post_id: int) -> Optional[dict]:
    require_online()
    resp = session.get(f"{API_ROOT}/posts/{post_id}.json", timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp.json().get("post")


def fetch_favorites(session: requests.Session, limit: int = 100) -> list[dict]:
    require_online()
    resp = session.get(
        f"{API_ROOT}/favorites.json", params={"limit": limit}, timeout=REQUEST_TIMEOUT
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("posts", data.get("favorites", []))


def add_favorite(session: requests.Session, post_id: int) -> bool:
    require_online()
    resp = session.post(f"{API_ROOT}/favorites.json", data={"post_id": post_id}, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return True


def remove_favorite(session: requests.Session, post_id: int) -> bool:
    require_online()
    resp = session.delete(f"{API_ROOT}/favorites/{post_id}.json", timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return True


def download_image(
    session: requests.Session,
    url: str,
    save_path: Path,
    on_progress: Optional[Callable[[int, int], None]] = None,
    cancelled: Optional[Callable[[], bool]] = None,
) -> bool:
    require_online()
    try:
        with session.get(url, stream=True, timeout=30) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("Content-Length") or 0)
            done = 0
            tmp = save_path.with_suffix(save_path.suffix + ".part")
            with open(tmp, "wb") as f:
                for chunk in resp.iter_content(64 * 1024):
                    if cancelled and cancelled():
                        f.close()
                        tmp.unlink(missing_ok=True)
                        return False
                    if not chunk:
                        continue
                    f.write(chunk)
                    done += len(chunk)
                    if on_progress:
                        on_progress(done, total)
            tmp.replace(save_path)
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"\n  [下载失败] {exc}")
        return False


def guess_ext(post: dict) -> str:
    file_info = post.get("file") or {}
    return (file_info.get("ext") or "jpg").lower()


def post_md5(post: dict) -> str:
    value = post.get("md5")
    if not value:
        value = hashlib.md5((get_image_url(post, "1") or "").encode()).hexdigest()
    return value


def target_filename(post: dict) -> str:
    return f"{post.get('id', 'unknown')}_{post_md5(post)[:8]}.{guess_ext(post)}"


def read_seen_md5(directory: Path) -> set[str]:
    seen: set[str] = set()
    history_file = directory / "downloaded_md5.txt"
    if history_file.exists():
        try:
            with open(history_file, "r", encoding="utf-8") as f:
                seen.update(line.strip() for line in f if line.strip())
        except Exception:
            pass
    return seen


def append_seen_md5(directory: Path, md5: str) -> None:
    try:
        with open(directory / "downloaded_md5.txt", "a", encoding="utf-8") as f:
            f.write(md5 + "\n")
    except Exception:
        pass


def human_size(num: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if abs(num) < 1024 or unit == "GB":
            return f"{num:.0f} {unit}" if unit == "B" else f"{num:.1f} {unit}"
        num /= 1024
    return f"{num:.1f} GB"


def rating_label(rating: str) -> str:
    return {"s": "安全", "q": "待定", "e": "明确"}.get(rating or "", "未知")


def score_total(post: dict) -> int:
    score = post.get("score") or {}
    if isinstance(score, dict):
        total = score.get("total")
        if total is not None:
            return int(total)
        return int(score.get("up", 0)) + int(score.get("down", 0))
    return int(score)


def post_tags(post: dict, limit: int = 0) -> list[str]:
    tags = post.get("tags") or {}
    flat: list[str] = []
    for value in tags.values():
        if isinstance(value, list):
            flat.extend(value)
    return flat[:limit] if limit else flat


def is_blocked(post: dict, blacklist: Iterable[str]) -> bool:
    if not blacklist:
        return False
    tags = set(post_tags(post))
    return any(tag in tags for tag in blacklist)


def wait_cancel(cancel_event, seconds: float) -> None:
    end = time.time() + seconds
    while time.time() < end:
        if cancel_event is not None and cancel_event.is_set():
            return
        time.sleep(0.1)
