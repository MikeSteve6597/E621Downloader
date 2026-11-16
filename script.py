"""
e621 图片下载工具（命令行界面）
支持：登录保存、画质选择、黑名单、自定义页数、进度条、搜索历史

GUI 版本请运行 gui.py；本文件保留原有的控制台交互行为。
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import sys
import time

from pathlib import Path

import requests

try:
    from tqdm import tqdm
except ImportError:
    # 未安装 tqdm 时退回无进度条的空实现。
    # 开发阶段禁止联网，故不再尝试 pip install（旧逻辑会在离线环境发起网络请求）。
    def tqdm(*_args, **_kwargs):  # type: ignore
        class _Dummy:
            def __enter__(self):
                return self

            def __exit__(self, *_exc):
                return False

            def update(self, _n=1):
                return None

        return _Dummy()

from e6core import (  # noqa: E402
    DEFAULT_LIMIT,
    DEFAULT_MAX_PAGES,
    DEFAULT_MIN_SCORE,
    DELAY_BETWEEN_REQUESTS,
    DOWNLOAD_DIR,
    MAX_HISTORY,
    MODE_OFFLINE,
    OfflineModeError,
    add_to_history,
    current_mode,
    get_image_url,
    load_config,
    make_auth_header,
    require_online,
    save_config,
    sync_mode_from_config,
)

CONFIG_FILE = Path.home() / "E6Dler" / "userdata.json"


def _enable_vt() -> bool:
    """开启 Windows 控制台的 ANSI 转义支持（用于原地重绘菜单）"""
    if os.name != "nt":
        return True
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        return bool(kernel32.SetConsoleMode(handle, mode.value | 0x0004))
    except Exception:
        return False


INTERACTIVE = sys.stdin.isatty()
VT_OK = _enable_vt()


def clear_screen() -> None:
    if INTERACTIVE and VT_OK:
        sys.stdout.write("\x1b[2J\x1b[H")
        sys.stdout.flush()
    else:
        os.system("cls" if os.name == "nt" else "clear")


def select_menu(title: str, options: list[tuple[str, str]], header: list[str] | None = None) -> str:
    """实时交互菜单：↑/↓ 切换、回车确认，也可直接按对应按键；非交互环境退回数字输入。

    options: [(key, label), ...]，返回被选中的 key。
    """
    try:
        import msvcrt
    except ImportError:
        msvcrt = None

    if not INTERACTIVE or msvcrt is None:
        if header:
            for line in header:
                print(line)
        print(title)
        for key, label in options:
            print(f"  {key}. {label}")
        while True:
            answer = input("请选择 (" + "/".join(k for k, _ in options) + "): ").strip().upper()
            for key, _label in options:
                if answer == key.upper():
                    return key
            print("无效选项，请重新输入。")

    index = 0

    def draw(redraw: bool) -> None:
        lines: list[str] = []
        if header:
            lines.extend(header)
        lines.append(title)
        for i, (_key, label) in enumerate(options):
            marker = "▶" if i == index else " "
            lines.append(f"  {marker} {label}")
        if redraw and VT_OK:
            sys.stdout.write("\x1b[" + str(len(lines)) + "A")
        for line in lines:
            sys.stdout.write("\r\x1b[K" + line + "\n")
        sys.stdout.flush()

    clear_screen()
    draw(False)
    while True:
        try:
            ch = msvcrt.getwch()
        except KeyboardInterrupt:
            raise
        if ch in ("\r", "\n"):
            return options[index][0]
        if ch in ("\x00", "\xe0"):
            code = msvcrt.getwch()
            if code == "H":
                index = (index - 1) % len(options)
                draw(True)
            elif code == "P":
                index = (index + 1) % len(options)
                draw(True)
            continue
        for key, _label in options:
            if ch.upper() == key.upper():
                return key


def download_image(session: requests.Session, url: str, save_path: Path) -> bool:
    require_online()
    try:
        r = session.get(url, timeout=30)
        r.raise_for_status()
        content = r.content
        if not content:
            raise ValueError("空文件")
        with open(save_path, "wb") as f:
            f.write(content)
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"\n  [下载失败] {exc}")
        return False


def search_and_download(
    session: requests.Session,
    tags: list[str],
    blacklist: list[str],
    quality: str,
    max_pages: int,
    limit_per_page: int,
    min_score: int,
    remember: bool,
) -> None:
    require_online()
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    seen_md5: set[str] = set()
    history_file = DOWNLOAD_DIR / "downloaded_md5.txt"
    if remember and history_file.exists():
        try:
            with open(history_file, "r", encoding="utf-8") as f:
                seen_md5.update(line.strip() for line in f if line.strip())
        except Exception:
            pass

    search_tags = tags.copy()
    for b in blacklist:
        search_tags.append(f"-{b}")
    tag_str = " ".join(search_tags)
    quality_name = {"1": "原图", "2": "采样图", "3": "预览图"}.get(quality, "采样图")

    print(f"\n搜索标签 : {tag_str}")
    print(f"画质选择 : {quality_name}")
    print(
        f"下载页数 : {max_pages}  |  每页数量 : {limit_per_page}"
        f"  |  最低评分 : {min_score}"
    )
    print(f"下载目录 : {DOWNLOAD_DIR}")
    print("-" * 60)

    total_downloaded = 0
    total_skipped = 0

    for page in range(1, max_pages + 1):
        params = {
            "tags": f"{tag_str} score:>={min_score}",
            "limit": limit_per_page,
            "page": page,
        }
        print(f"\n正在请求第 {page}/{max_pages} 页...")
        try:
            resp = session.get("https://e621.net/posts.json", params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:  # noqa: BLE001
            print(f"请求失败 (page {page}): {exc}")
            break

        posts = data.get("posts", [])
        if not posts:
            print(f"第 {page} 页没有更多结果，结束。")
            break

        print(f"第 {page} 页找到 {len(posts)} 张图片，开始下载...")
        with tqdm(total=len(posts), desc=f"第{page}页", unit="张", ncols=80) as pbar:
            for post in posts:
                img_url = get_image_url(post, quality)
                if not img_url:
                    pbar.update(1)
                    total_skipped += 1
                    continue

                file_info = post.get("file") or {}
                ext = (file_info.get("ext") or "jpg").lower()
                if ext in ("webm", "mp4", "swf"):
                    pbar.update(1)
                    total_skipped += 1
                    continue

                md5 = post.get("md5") or hashlib.md5(img_url.encode()).hexdigest()
                if md5 in seen_md5:
                    pbar.update(1)
                    total_skipped += 1
                    continue

                post_id = post.get("id", "unknown")
                filename = f"{post_id}_{md5[:8]}.{ext}"
                save_path = DOWNLOAD_DIR / filename

                if save_path.exists():
                    seen_md5.add(md5)
                    pbar.update(1)
                    total_skipped += 1
                    continue

                if download_image(session, img_url, save_path):
                    seen_md5.add(md5)
                    total_downloaded += 1
                    if remember:
                        with open(history_file, "a", encoding="utf-8") as f:
                            f.write(md5 + "\n")
                else:
                    total_skipped += 1
                pbar.update(1)

        time.sleep(DELAY_BETWEEN_REQUESTS)

    print("\n" + "-" * 60)
    print(f"下载完成！成功下载 {total_downloaded} 张，跳过 {total_skipped} 张")
    print(f"保存目录: {DOWNLOAD_DIR}")


def create_login_session(config: dict):
    """按原流程录入/校验登录信息并创建带认证的 Session；中途取消返回 None"""
    require_online()
    username = config.get("username", "")
    api_key = config.get("api_key", "")

    if username and api_key:
        print(f"检测到已保存账号: {username}")
        use_saved = input("是否使用已保存的登录信息？(Y/n): ").strip().lower()
        if use_saved in ("n", "no"):
            username = ""

    if not username:
        username = input("请输入 e621 用户名: ").strip()
        if not username:
            print("用户名不能为空，退出。")
            return None
        api_key = input("请输入 API Key（直接粘贴后回车）:").strip()
        if not api_key:
            print("API Key 不能为空，退出。")
            return None

    save_choice = input("是否保存登录信息？(y/N): ").strip().lower()
    if save_choice in ("y", "yes"):
        config["username"] = username
        config["api_key"] = api_key
        save_config(config)

    print("\n正在创建登录信息...")
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": f"E6dl/1.4 (by {username} on e621)",
            "Authorization": make_auth_header(username, api_key),
            "Accept": "application/json",
        }
    )

    try:
        test = session.get("https://e621.net/users/me.json", timeout=12)
        if test.status_code == 401:
            print("登录失败：用户名或 API Key 错误。")
            if CONFIG_FILE.exists():
                if input("是否删除错误配置？(y/N): ").strip().lower() in ("y", "yes"):
                    save_config({})
            return None
        if test.status_code == 200:
            print(f"登录成功！欢迎 {username}")
        else:
            print(f"验证状态码 {test.status_code}，继续尝试...")
    except Exception as exc:  # noqa: BLE001
        print(f"验证出现问题: {exc}，继续尝试...")

    return session


def download_flow(guest: bool = False) -> None:
    """完整下载流程；guest=True 为不登录模式，不读写任何本地记录"""
    config = load_config() if not guest else {}

    if guest:
        print("开始搜索并下载")
        print("模式：不登录下载（不保存登录信息、搜索历史与下载记录）")
        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": "E6dl/1.4 (anonymous)",
                "Accept": "application/json",
            }
        )
    else:
        print("开始搜索并下载")
        try:
            session = create_login_session(config)
        except OfflineModeError:
            print("当前为单机模式，操作已中止。")
            return
        if session is None:
            return

    tags: list[str] = []
    blacklist: list[str] = []

    if not guest:
        history = config.get("history", [])
        if history:
            print("\n===== 搜索历史（最近10条）=====")
            for i, record in enumerate(history, 1):
                tags_str = ", ".join(record.get("tags", []))
                black_str = ", ".join(record.get("blacklist", [])) or "无"
                print(f"  {i}. [{record.get('time', '')}] 关键词: {tags_str}")
                print(f"     黑名单: {black_str}")
            print("  0. 不使用历史，手动输入新搜索")
            choice = input("\n请选择历史记录编号（直接回车跳过）: ").strip()
            if choice.isdigit():
                idx = int(choice)
                if 1 <= idx <= len(history):
                    selected = history[idx - 1]
                    tags = selected.get("tags", [])
                    blacklist = selected.get("blacklist", [])
                    print(f"\n已选择历史记录：关键词 = {', '.join(tags)}")
                    if blacklist:
                        print(f"黑名单 = {', '.join(blacklist)}")
                elif idx == 0:
                    print("将手动输入新搜索内容")

    print("\n请选择图片画质：")
    print("  1. 原图（最大体积，画质最高）")
    print("  2. 采样图（推荐，体积与画质平衡）")
    print("  3. 预览图（最小，加载最快）")
    quality = input("请输入选项 (1/2/3，默认2): ").strip() or "2"
    if quality not in ("1", "2", "3"):
        quality = "2"

    try:
        max_pages = int(
            input(f"请输入要下载的页数（默认 {DEFAULT_MAX_PAGES}）: ").strip() or DEFAULT_MAX_PAGES
        )
    except ValueError:
        max_pages = DEFAULT_MAX_PAGES
    max_pages = max(1, min(max_pages, 50))

    try:
        limit_per_page = int(
            input(f"请输入每页数量（1-320，默认 {DEFAULT_LIMIT}）: ").strip() or DEFAULT_LIMIT
        )
    except ValueError:
        limit_per_page = DEFAULT_LIMIT
    limit_per_page = max(1, min(limit_per_page, 320))

    try:
        min_score = int(
            input(f"请输入最低评分（默认 {DEFAULT_MIN_SCORE}）: ").strip() or DEFAULT_MIN_SCORE
        )
    except ValueError:
        min_score = DEFAULT_MIN_SCORE

    if not tags:
        raw = input("\n请输入关键词（多个用英文逗号分隔）: ").strip()
        if not raw:
            print("未输入关键词，退出。")
            return
        tags = [t.strip().replace(" ", "_") for t in raw.split(",") if t.strip()]

        black_raw = input(
            "请输入黑名单标签（要排除的，多个用逗号分隔，可直接回车跳过）: "
        ).strip()
        if black_raw:
            blacklist = [t.strip().replace(" ", "_") for t in black_raw.split(",") if t.strip()]
    else:
        modify = input("\n是否修改本次关键词/黑名单？(y/N): ").strip().lower()
        if modify in ("y", "yes"):
            raw = input(f"关键词（当前: {', '.join(tags)}）: ").strip()
            if raw:
                tags = [t.strip().replace(" ", "_") for t in raw.split(",") if t.strip()]
            black_raw = input(
                f"黑名单（当前: {', '.join(blacklist) or '无'}）: "
            ).strip()
            if black_raw:
                blacklist = [
                    t.strip().replace(" ", "_") for t in black_raw.split(",") if t.strip()
                ]

    if blacklist:
        print(f"已设置黑名单: {', '.join(blacklist)}")

    if not guest:
        add_to_history(config, tags, blacklist)

    try:
        search_and_download(
            session,
            tags,
            blacklist,
            quality,
            max_pages,
            limit_per_page,
            min_score,
            remember=not guest,
        )
    except OfflineModeError:
        print("当前为单机模式，操作已中止。")


def manage_history() -> None:
    """搜索历史管理：查看 / 清空"""
    notice = ""
    while True:
        config = load_config()
        history = config.get("history", [])

        header = []
        if notice:
            header.append(notice)
        if history:
            for i, record in enumerate(history, 1):
                tags_str = ", ".join(record.get("tags", []))
                black_str = ", ".join(record.get("blacklist", []))
                header.append(f"  {i}. [{record.get('time', '')}] 关键词: {tags_str}")
                if black_str:
                    header.append(f"     黑名单: {black_str}")
        else:
            header.append("暂无搜索历史。")

        options = [("C", "清空全部搜索历史")] if history else []
        options.append(("0", "返回主菜单"))
        key = select_menu("===== 搜索历史管理 =====", options, header)

        if key == "C":
            if input("确认清空全部搜索历史？(y/N): ").strip().lower() in ("y", "yes"):
                config["history"] = []
                save_config(config)
                notice = "搜索历史已清空。"
                clear_screen()
                continue
            clear_screen()
            continue
        clear_screen()
        return


def manage_login() -> None:
    """登录信息管理：查看 / 修改 / 删除"""
    notice = ""
    while True:
        config = load_config()
        username = config.get("username", "")
        api_key = config.get("api_key", "")

        header = []
        if notice:
            header.append(notice)
        if username and api_key:
            masked = "*" * len(api_key)
            header.append(f"当前账号: {username}")
            header.append(f"API Key : {masked}")
        else:
            header.append("当前尚未保存登录信息。")

        options = [
            ("1", "修改登录信息"),
            ("2", "删除登录信息"),
            ("0", "返回主菜单"),
        ]
        key = select_menu("===== 登录信息管理 =====", options, header)

        if key == "1":
            new_user = input("请输入 e621 用户名（直接回车取消）: ").strip()
            if not new_user:
                notice = "已取消修改。"
                clear_screen()
                continue
            new_key = input("请输入 API Key（直接粘贴后回车）:").strip()
            if not new_key:
                notice = "API Key 为空，已取消修改。"
                clear_screen()
                continue
            config["username"] = new_user
            config["api_key"] = new_key
            save_config(config)
            notice = "登录信息已保存。"
            clear_screen()
            continue

        if key == "2":
            if not username:
                notice = "当前尚未保存登录信息。"
                clear_screen()
                continue
            if input("确认删除已保存的登录信息？(y/N): ").strip().lower() in ("y", "yes"):
                config.pop("username", None)
                config.pop("api_key", None)
                save_config(config)
                notice = "登录信息已删除。"
            else:
                notice = "已取消删除。"
            clear_screen()
            continue

        clear_screen()
        return


def main() -> None:
    cfg = load_config()
    sync_mode_from_config(cfg)
    if current_mode() == MODE_OFFLINE:
        print("当前为单机模式（离线），CLI 下载需要联网。")
        print("请在 GUI「设置 › 运行模式」切换为在线模式后重试。")
        print("或先运行 GUI（gui.py）在其中切换运行模式，再回到命令行使用。")
        return
    try:
        while True:
            key = select_menu(
                "===== 主菜单 =====",
                [
                    ("1", "开始搜索并下载"),
                    ("2", "搜索历史管理"),
                    ("3", "登录信息管理"),
                    ("0", "退出"),
                ],
                ["=" * 60, "e621 图片下载工具", "=" * 60],
            )

            if key == "1":
                mode = select_menu(
                    "===== 请选择下载方式 =====",
                    [
                        ("1", "登录下载（使用账号，保存搜索历史）"),
                        ("2", "不登录下载（不保存任何数据）"),
                        ("0", "返回主菜单"),
                    ],
                )
                if mode == "1":
                    download_flow()
                    input("\n按回车返回主菜单...")
                elif mode == "2":
                    download_flow(guest=True)
                    input("\n按回车返回主菜单...")
            elif key == "2":
                manage_history()
            elif key == "3":
                manage_login()
            else:
                clear_screen()
                print("再见！")
                return
    except (KeyboardInterrupt, EOFError):
        print("\n已退出。")


if __name__ == "__main__":
    main()
