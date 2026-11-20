# E621Downloader 交接文档（AI / 开发者）

> 生成时间：2026-11-20　适用版本：1.5.1（`e6core.APP_VERSION = "1.5.1"`）
> 本文基于实际代码与文件核对写成。凡未能核实的内容都明确标注「未知 / 待确认」，请勿当作事实使用。

---

## 0. 现状判定：哪一份是权威源码

工作区根目录 `d:\Files\E621Downloader` 下有三个目录：

| 目录 | 角色 | 实际情况 |
| --- | --- | --- |
| `E621Downloader_GitHub\E6dlGithub\` | **等待上传 GitHub 的版本（只保留一个版本）** | 源码 + `build.bat` + `requirements*.txt` + `README.md` + `LICENSE` + `.gitignore` + `GITHUB发布指南.md`，是交给 GitHub 的完整树；新版本开发完成后直接覆盖旧版，直到下一个版本开发完毕再覆盖 |
| `E621Downloader_snapshot\E6Dler\` | **仅开发中使用的源码工作区** | 版本开发完成后不要把成品留在该目录；已完成的版本统一归档到 release |
| `E621Downloader_release\` | **各版本备份与开发完成版本的归档** | `v1.5.0_2026-11-16\`、`v1.5.1_2026-11-20\`（exe + icon.ico/png + README.md + LICENSE + RELEASE_NOTES.md）及同名 zip |

判定依据（已实测，SHA256 前 12 位比对）：

| 文件 | snapshot | GitHub | 结论 |
| --- | --- | --- | --- |
| e6core.py | B17FA969DB4C | B17FA969DB4C | 相同 |
| gui.py | 50413B9FAD67 | 50413B9FAD67 | 相同 |
| gui_theme.py | E45A7331D876 | E45A7331D876 | 相同 |
| gui_widgets.py | 25121C3173F8 | 25121C3173F8 | 相同 |
| script.py | B4847830812E | B4847830812E | 相同 |
| E6dl.spec | 0E965A8D2852 | 0E965A8D2852 | 相同 |
| icon.ico / icon.png | E9B360236AED / 97F653F373E1 | 同 | 相同 |

**两个目录都没有 `.git`**，本地无版本历史，唯一的提交历史在远端 <https://github.com/MikeSteve6597/E621Downloader>（是否需要 `git init` 由你决定；建议以 GitHub 目录为准 clone/init）。

**结论**：源码以 `E621Downloader_GitHub\E6dlGithub` 为唯一真源；`snapshot` 视为等价副本 + 构建产物；`release` 只放已验证的发布物。三者不要各自演化。

---

## 1. 项目定位与功能概览

e621（成年向图片站）的第三方 Windows 桌面客户端：浏览作品、按标签搜索并批量下载、管理收藏与黑名单。单文件 exe 发布，目标机无需 Python。与 e621 官方无关联。

### 1.1 三种运行状态（这是最容易改错的地方）

| 状态 | 判定依据（代码） | 行为 |
| --- | --- | --- |
| **单机模式（默认）** | `e6core.DEFAULT_MODE = "offline"`；`_MODE` 全局开关 | 所有网络函数先调 `require_online()`，抛 `OfflineModeError`。发现页显示「单机模式 · 已停用联网」，图片加载器直接回调失败（`ImageLoader.load` 检查 `e6core.is_online()`）。登录入口提示先切在线模式 |
| **在线 + 未登录（游客）** | `MainWindow._anon_session = e6core.make_session(guest=True)` | 可浏览发现页、搜索、以匿名身份下载；不写搜索历史、不写 `downloaded_md5.txt`；发现页黑名单**不生效**（`gui.py` 发现页按 `self.main.logged_in` 决定是否带黑名单） |
| **在线 + 已登录** | `config["username"]` 与 `config["api_key"]` 均非空 | 请求带 `Basic base64(username:api_key)`；可收藏/取消收藏、拉黑、批量操作；搜索历史与去重记录按设置落盘 |

### 1.2 主要用户流程

1. 启动 → 默认单机模式 → 用户到「设置 › 运行模式」切在线（会弹二次确认 `confirm(...)`）。
2. 发现页 `DiscoverPage`（`PAGE_LIMIT = 24`）滚动加载推荐作品，点击进入 `DetailPage` 大图，支持「在浏览器中打开」。
3. 「搜索下载」`SearchPage`：多标签（逗号分隔）、临时黑名单、画质、页数 1–50、每页 1–320、最低评分 → 点下载时若未登录，弹 `MainWindow.ask_download_mode()` 选择「登录下载 / 不登录下载」。
4. 下载由 `DownloadWorker` 执行：逐页 `fetch_posts`，按 `target_filename()` 命名，`.part` 临时文件 + `replace` 落盘，`downloaded_md5.txt` 去重，翻页间 `DELAY_BETWEEN_REQUESTS = 1.1` 秒，可取消。
5. 「我的收藏」`FavoritesPage`：登录后 `fetch_favorites(session, 200)`（一次 200 条，无分页），支持多选批量收藏/拉黑/下载。
6. 「黑名单」`BlacklistPage`：标签写入 `config["blacklist"]`，发现/搜索/收藏统一过滤（搜索时以 `-tag` 形式拼进查询）。
7. 「设置」`SettingsPage`：运行模式、主题、默认画质、下载目录、关键词记忆条数、账号信息、清空历史 / 清空图片缓存 / 打开配置目录。

---

## 2. 技术栈

| 项 | 实际值 | 来源 |
| --- | --- | --- |
| 语言 | Python 3.14.0 | `C:\Users\MikeSteve\AppData\Local\Programs\Python\Python314\python.exe -V` |
| GUI | PySide6（`PySide6_Essentials`）6.12.0 | `pip list` |
| HTTP | requests 2.34.2 | `pip list` |
| 打包 | PyInstaller 6.22.3，`pyinstaller-hooks-contrib` 2026.10 | `pip list` |
| 声明依赖 | `requirements.txt`：`requests>=2.31`、`PySide6>=6.6`；`requirements-build.txt`：`-r requirements.txt` + `pyinstaller>=6.0` | 文件内容 |
| 目标平台 | Windows 10 / 11 64 位；Mica 需 build ≥ 22000 | `gui_theme.mica_supported()` |
| 外部服务 | `https://e621.net`（`e6core.API_ROOT`） | 代码 |
| 认证 | HTTP Basic：`base64("username:api_key")`，校验接口 `GET /users/me.json`（超时 12s） | `e6core.make_auth_header` / `validate_login` |
| 请求约束 | 所有请求带 `User-Agent: E621Downloader/1.5 (by <user> on e621)` 或 `(anonymous)`；普通接口超时 20s，下载 30s；翻页间隔 1.1s；429 有专门错误提示 | `e6core`、`gui.friendly_error` |
| 已用到的 e621 接口 | `/posts.json`、`/posts/{id}.json`、`/favorites.json`（GET/POST）、`/favorites/{id}.json`（DELETE）、`/users/me.json` | `e6core` |
| 未使用/未确认 | 官方 API 最新条款（UA 格式、限流细则）**待确认**；仓库未见 CI 配置（`.github/` 是否存在**待确认**） | — |

---

## 3. 代码结构与模块职责

### 3.1 文件级

| 文件 | 行数 | 职责 |
| --- | --- | --- |
| [gui.py](file:///D:/Files/E621Downloader/E621Downloader_GitHub/E6dlGithub/gui.py) | 2343 | 程序入口、无边框主窗口、5 个页面 + 详情页、后台线程、登录/主题/模式切换 |
| [gui_widgets.py](file:///D:/Files/E621Downloader/E621Downloader_GitHub/E6dlGithub/gui_widgets.py) | 911 | 自绘 Fluent 控件、异步图片加载器（QNetworkAccessManager + 磁盘缓存） |
| [gui_theme.py](file:///D:/Files/E621Downloader/E621Downloader_GitHub/E6dlGithub/gui_theme.py) | 761 | 主题令牌 `Tokens`、QSS 生成、DWM/Mica、QPainter 线性图标 |
| [e6core.py](file:///D:/Files/E621Downloader/E621Downloader_GitHub/E6dlGithub/e6core.py) | 428 | 配置读写、运行模式门禁、Session/鉴权、API 封装、下载、去重、格式化工具 |
| [script.py](file:///D:/Files/E621Downloader/E621Downloader_GitHub/E6dlGithub/script.py) | 528 | 独立命令行版本（ANSI 彩色菜单，与 GUI 共用 `e6core`） |
| [E6dl.spec](file:///D:/Files/E621Downloader/E621Downloader_GitHub/E6dlGithub/E6dl.spec) | 73 | PyInstaller onefile 打包配置 |
| build.bat | 29 | 一键装依赖 + 打包 |

### 3.2 关键符号（文件:行）

**gui.py**
- `TitleBar` :376 —— 48px 自绘标题栏；`mousePressEvent` 用 `windowHandle().startSystemMove()` 拖动；双击 `toggle_max()`；`sync_max()` 在 `changeEvent(WindowStateChange)` 时刷新最大化图标。
- `DiscoverPage` :479（`PAGE_LIMIT = 24` :480）—— 瀑布流 + 滚动触底加载；`SMOKE` 模式下不联网。
- `ImageView` :874 —— 大图查看。
- `DetailPage` :929 —— 作品详情、收藏切换（`add_favorite`/`remove_favorite`）、单张下载（`SingleDownloadWorker`）。
- `SearchPage` :1156 —— 搜索/下载表单、`start_download` :1384、`is_busy()` :1378、`worker`。
- `FavoritesPage` :1507 / `BlacklistPage` :1651 / `SettingsPage` :1768。
- `LoginDialog` :2063 —— 用户名 + API Key + 「在本机保存登录信息」`FluentCheckBox`；校验走 `ApiWorker(lambda: e6core.validate_login(...))` :2120。
- `MainWindow` :2146 —— 组装；`api_session()` :2275（未登录时退回匿名 session）；`set_run_mode()` :2293（切在线需 confirm）；`show_page()` :2342；`open_detail()/close_detail()` :2379/:2387；`ask_download_mode()` :2397；`_apply_login()` :2434；`logout()` :2452；`_apply_theme()` :2497；`nativeEvent` :2566 处理 `WM_NCHITTEST` 缩放；`closeEvent` :2605 下载中退出需确认。
- `install_excepthook()` :2628 —— 写日志 + `MessageBoxW` 弹窗。
- `main()` :2647 —— `AppUserModelID("E6Dler.App")`、`QStyleFactory.create("windows11")`、设置字体、显示窗口。

**gui_widgets.py**
- `ImageLoader` :74 —— 磁盘缓存 `%LOCALAPPDATA%\E6Dler\image_cache`，上限 256 MB，`PreferCache` + `NoLessSafeRedirectPolicy`；单机模式/`SMOKE` 直接失败回调。
- `FlowLayout` :142、`NavItem` :213、`CaptionButton` :309、`PostCard` :362、`FluentCheckBox` :551、`FluentComboBox` :583、`SegmentedControl` :601、`ToggleSwitch` :692、`InfoBar` :768、`EmptyState` :824、`ContentDialog` :884、`confirm()` :991。
- `set_icon()` :1025 / `refresh_icons()` :1033 —— 图标随主题重绘（改主题必须调用，否则图标颜色不更新）。

**gui_theme.py**
- `Tokens` :25 / `LIGHT` :56 / `DARK` :86 / `ACCENT = "#005FB8"` :117；`resolve_dark()` :142；`build_qss()` :181；`apply_theme()` :461。
- `mica_supported()` :522（`build >= 22000`，可用 `E6DL_NO_MICA=1` 关闭）；`apply_mica()` :597 —— 依次尝试 `DWMWA_SYSTEMBACKDROP_TYPE=2` → `DWMWA_MICA_EFFECT` → `SetWindowCompositionAttribute` 兜底，再 `DwmExtendFrameIntoClientArea(0,0,0,0)`；`mica_status_text()` :618 用于设置页显示。
- `paint_icon()` :655 / `make_icon()` :824 —— 全部图标用 QPainter 画，**不引入图标包或 emoji**。

**e6core.py**（行号见文件）
- 运行模式：`set_mode` / `sync_mode_from_config` / `save_mode` / `require_online` / `is_online`。
- 配置：`load_config` / `save_config`（`ensure_ascii=False, indent=2`）。
- 关键词记忆：`keywords_limit`（默认 10，裁剪 0–50，0 = 关闭）/ `add_recent_keyword`（仅改字典，不落盘）。
- 会话：`make_session(config, guest=False)` / `session_for(username, api_key)` / `validate_login`。
- 业务：`fetch_posts` / `fetch_post` / `fetch_favorites` / `add_favorite` / `remove_favorite` / `download_image`（支持 `on_progress`、`cancelled`）。
- 工具：`get_image_url(post, quality)`（"1" 原图 / "2" 采样 / "3" 预览，逐级回退）、`build_search_tags`（黑名单拼 `-tag`，追加 `score:>=N`）、`target_filename`（`<id>_<md5前8>.<ext>`）、`read_seen_md5` / `append_seen_md5`、`human_size`、`rating_label`、`score_total`、`post_tags`、`is_blocked`、`wait_cancel`。

### 3.3 调用关系

```
gui.main() → QApplication + MainWindow
MainWindow ──→ DiscoverPage / SearchPage / FavoritesPage / BlacklistPage / SettingsPage（QStackedWidget）
           ──→ DetailPage（临时加到 stack，关闭时 removeWidget + deleteLater）
           ──→ ImageLoader（QNetworkAccessManager，所有缩略图/大图）
SearchPage ──→ MainWindow.api_session() ──→ e6core.make_session()
           ──→ DownloadWorker(QThread) ──→ e6core.fetch_posts / download_image / *_seen_md5
DetailPage / FavoritesPage ──→ ApiWorker(QThread) ──→ e6core.fetch_post / add_favorite / remove_favorite
SettingsPage / LoginDialog ──→ e6core.save_mode / validate_login
script.py → 直接复用 e6core（无 GUI 依赖）
```

---

## 4. 配置与本地数据

| 内容 | 位置 | 说明 |
| --- | --- | --- |
| 主配置 | `%USERPROFILE%\E6Dler\userdata.json` | `e6core.CONFIG_FILE`；账号 API Key **明文** |
| 默认下载目录 | `%USERPROFILE%\Downloads\E6dl` | `e6core.DOWNLOAD_DIR`，可被 `download_dir` 覆盖 |
| 去重记录 | `<下载目录>\downloaded_md5.txt` | 每行一个 MD5 |
| 图片缓存 | `%LOCALAPPDATA%\E6Dler\image_cache` | 上限 256 MB，可在设置页清空 |
| 错误日志 | `%LOCALAPPDATA%\E6Dler\e6dler-error.log` | `install_excepthook()` 追加写 |

**配置键（代码中实际读写）**

| 键 | 类型 | 默认 | 作用 |
| --- | --- | --- | --- |
| `mode` | `"offline"` / `"online"` | `offline` | 运行模式 |
| `username` / `api_key` | str | 无 | 登录态；两者同时存在才算已登录 |
| `blacklist` | list[str] | `[]` | 持久黑名单标签 |
| `history` | list[dict] | `[]` | 搜索历史，最多 `MAX_HISTORY = 10` 条，含 `time`/`tags`/`blacklist` |
| `recent_keywords` | list[str] | `[]` | 最近关键词，上限由 `ui.keyword_memory` 控制 |
| `ui.theme` | `"system"` / `"light"` / `"dark"` | `system` | 主题 |
| `ui.keyword_memory` | int | 10 | 0 = 不记忆，最大 50 |
| `quality` | `"1"/"2"/"3"` | `"2"` | 默认画质 |
| `max_pages` | int | 5 | 下载页数 1–50 |
| `limit` | int | 50 | 每页数量 1–320 |
| `min_score` | int | 10 | 搜索附加 `score:>=N` |
| `download_dir` | str | 空 → 默认目录 | 下载路径 |
| `remember_history` | bool | `true` | 是否保存搜索历史/去重记录（仅登录时生效） |

**环境变量（代码读取）**

| 变量 | 作用 |
| --- | --- |
| `E6DL_SMOKE=1` | `gui_widgets.SMOKE`，跳过网络/图片加载，用于无网冒烟测试 |
| `E6DL_NO_MICA=1` | 强制关闭 Mica |
| `LOCALAPPDATA` | 缓存与日志根目录（缺省回退 `Path.home()`） |
| `QT_QPA_PLATFORM=offscreen` | 无界面运行 Qt（冒烟测试用） |

---

## 5. 开发流程

### 5.1 环境

```powershell
cd D:\Files\E621Downloader\E621Downloader_GitHub\E6dlGithub
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

本机已知可用的解释器：`C:\Users\MikeSteve\AppData\Local\Programs\Python\Python314\python.exe`（3.14.0）。若 PATH 里没有 `python`，直接用全路径。

### 5.2 运行与调试

```powershell
python gui.py      # GUI
python script.py   # 命令行版
```

- 首次运行是**单机模式**，需在设置里切在线，否则所有请求都会报「当前为单机模式」。
- 无网/无界面冒烟：

```powershell
$env:QT_QPA_PLATFORM="offscreen"; $env:E6DL_SMOKE="1"; python gui.py
```

（本仓库没有自动化测试用例；`SMOKE` 只是跳过网络与图片加载，**未知是否有正式 smoke 脚本**。）
- 异常统一走 `install_excepthook()`：写 `%LOCALAPPDATA%\E6Dler\e6dler-error.log` 并弹 MessageBox。
- 界面文案错误统一由 `gui.friendly_error()` 转成中文（401/403/404/429/5xx/超时/连接失败/单机模式）。

### 5.3 打包

```powershell
pip install -r requirements-build.txt
python -m PyInstaller --noconfirm --clean E6dl.spec
# 或双击 build.bat
```

产物：`dist\E621Downloader.exe`（当前 39,026,790 字节，SHA256 `3531AEAD5BE9ACCD37046C0F9ABC745EA927F3F663FB9B8720728BA64F6C1260`）。

**spec 字段要点**

| 字段 | 值 | 说明 |
| --- | --- | --- |
| `Analysis(['gui.py'])` | 入口 | 只分析 GUI；`script.py` 不打进 exe |
| `datas=[('icon.ico', '.')]` | 资源 | 图标打进包，运行时用 `resource_path()` 从 `sys._MEIPASS` 读取 |
| `hiddenimports` | `e6core` / `gui_theme` / `gui_widgets` | 确保同目录模块被收集 |
| `excludes` | QtQml、QtWebEngine、QtMultimedia、QtPdf、QtSql、QtTest 等 | 控制体积，**新增 Qt 模块时记得改这里** |
| `EXE(... name='E621Downloader', console=False, icon=['icon.ico'], upx=False, debug=False)` | 单文件无控制台 | 名字改了要同步 build.bat / README / Release 文案 |

**打包坑（已踩过）**

1. 只放 `icon.ico` 进 `datas`；`icon.png` 是给 README 用的，**不进 exe**，但归档发布物时必须带上，否则 Markdown Logo 失效。
2. `console=False` + 未捕获异常 → 只会弹 MessageBox 并写日志，看不到 traceback；排查时临时改 `console=True`。
3. 用 `E6DL_SMOKE=1` 验证启动时，`ImageLoader` 会直接失败回调，属正常现象。
4. 源码里用相对路径读图标，必须经 `resource_path()`，否则打包后找不到文件。
5. `optimize=0`、`upx=False`：开启 UPX 曾出现杀软误报/启动异常，**未知是否复现过，建议保持关闭**。

### 5.4 发布流程（现行约定）

1. 改版本：`e6core.APP_VERSION`；`gui_widgets.ImageLoader.user_agent` 里的版本串（当前硬编码 `E621Downloader/1.5`）与 `script.py` 的 UA 也要同步。
2. 打包 → 在本机双击验证（至少能开窗、切在线、搜一次）。
3. 归档：`E621Downloader_release\v<版本>_<YYYY-MM-DD>\` 放 `E621Downloader.exe`、`icon.ico`、`icon.png`、`README.md`、`LICENSE`、`RELEASE_NOTES.md`，再压同名 zip。
4. 更新 `E621Downloader_GitHub\E6dlGithub` 的 README / RELEASE_NOTES（含新 SHA256），把源码与 README 推到 GitHub，再在 Releases 页新建 tag 并上传 exe。
5. 对外名称统一用 `E621Downloader`；**内部代号 `E6Dler` / `E6dl` 只用于目录、配置、缓存、日志、AppUserModelID、spec 文件名**，属于兼容性硬约束，不要改。

---

## 6. 必须遵守的硬性约束

### 6.1 界面（已落地的 Fluent 实现）

| 规则 | 实现位置 | 破坏后果 |
| --- | --- | --- |
| 主窗口无系统边框：`FramelessWindowHint` + `WA_TranslucentBackground` | `MainWindow.__init__` :2171、:2183 | 出现双标题栏或黑边 |
| 自绘标题栏 48px，最小化/最大化/关闭用 `CaptionButton` | `TitleBar` :376 | 无法拖动/窗口按钮错位 |
| 拖动走 `startSystemMove()`，不要自己算 `--pos` 偏移 | `TitleBar.mousePressEvent` :404 | 高 DPI/多屏下窗口跳动 |
| 8 方向缩放靠 `nativeEvent` 拦截 `WM_NCHITTEST(0x0084)`，坐标需 `/ devicePixelRatioF()` | `MainWindow.nativeEvent` :2566 | 缩放热区错位（物理/逻辑像素混用） |
| 最大化/还原图标随窗口状态刷新 | `TitleBar.sync_max()` + `changeEvent` :2554 | 按钮状态与窗口不一致 |
| Mica 失败要能降级：`apply_mica()` 返回 False 时 `_mica = False`，背景回退 `bg_solid` | `MainWindow.showEvent` :2559、`RootWidget.paintEvent` :2616 | Win10 或旧 Win11 上黑屏/透明穿透 |
| 所有颜色/字体/圆角来自 `Tokens` + `build_qss()`，不写死颜色 | `gui_theme.py` | 深色模式局部失效 |
| 图标只能用 `make_icon`/`paint_icon` 绘制，`set_icon`/`refresh_icons` 负责随主题重绘 | `gui_theme.py` :655/:824、`gui_widgets.py` :1025/:1033 | 切主题后图标颜色不变 |
| 切换主题时先 `root.grab()` 快照再做 220ms 淡出遮罩 | `MainWindow._apply_theme` :2497 | 切换闪烁 |

### 6.2 逻辑硬约束

1. **网络门禁**：任何新增网络调用必须经过 `e6core.require_online()`（或用 `make_session`，它内部会检查），否则单机模式会被绕过。
2. **对外名称**：窗口标题、关于页、User-Agent、README、Release、exe 文件名 = `E621Downloader`。
3. **内部路径**：`%USERPROFILE%\E6Dler\userdata.json`、`%LOCALAPPDATA%\E6Dler\...`、`%USERPROFILE%\Downloads\E6dl`、`E6Dler.App`、`E6dl.spec` 保持不变，改了会丢失用户已有数据。
4. **API Key 明文**：只在 `userdata.json`，绝不写入程序目录、日志或提交 Git；`.gitignore` 已排除 `userdata.json`、`*.log`。
5. **请求节奏**：UI 侧 `DELAY_BETWEEN_REQUESTS = 1.1s`，改动前先确认 e621 的限流要求（官方细则**待确认**）。
6. **去重**：只有 `remember=True`（已登录且勾选保存历史）才读写 `downloaded_md5.txt`；游客模式必须完全不落盘。

---

## 7. 已知问题、待办与雷区

| 类别 | 内容 |
| --- | --- |
| 待办 | 无 `.git`，本地无版本历史；建议在 GitHub 目录 `git init` + 关联远端 |
| 已解决（2026-11-20） | UA 版本号已统一为 `e6core.user_agent()` / `e6core.APP_VERSION`（详见 §9） |
| 已解决（2026-11-20） | 收藏页已改为 `fetch_all_favorites()` 逐页拉取（详见 §9） |
| 待办 | 未做 CI（`.github/workflows` 是否存在**待确认**），打包全手动 |
| 待办 | Release 附件需手动上传（GitHub 的 `#releases-upload` 是隐藏 input，脚本化上传曾失败） |
| 已解决（2026-11-20） | `download_image` 现返回错误说明，GUI 逐条上报「其中 N 项下载失败」（详见 §9） |
| 已知缺陷 | 视频（`webm/mp4/swf`）直接跳过，不计入失败 |
| 雷区 | `MainWindow.nativeEvent` 里坐标换算、`border = 5` 与最大化判断，改动后务必在 125%/150% 缩放下实测 |
| 雷区 | `E6dl.spec` 的 `excludes` 很长，新增 Qt 子模块若被误排除，表现为运行时报 ImportError 且无控制台日志 |
| 雷区 | 单机模式是**默认值**，任何「启动即联网」的改动都会破坏这一设计意图 |
| 雷区 | 旧版 `E6dl.exe` 可能残留在 `dist`/release 目录，上传前确认文件名与 SHA256 |
| 未知 | 是否有代码签名计划、自动更新机制、多语言支持 —— 代码中均未发现 |

---

## 8. 接手 AI 的快速上手路径

1. **读代码顺序**（约 1 小时可通读关键路径）：
   `e6core.py`（全读，428 行）→ `gui.py` 的 `main()` :2647 → `MainWindow` :2146 → `TitleBar` :376 → `gui_widgets.ImageLoader` :74 → `gui_theme.apply_mica` :597 → `SearchPage.start_download` :1390 → `DownloadWorker` :222。
2. **第一步验证（源码）**：

```powershell
$env:QT_QPA_PLATFORM="offscreen"; $env:E6DL_SMOKE="1"
python gui.py
```

能开窗且无异常即环境正常（窗口标题应为 `E621Downloader`）；再切在线模式手动搜一次标签确认 API 通路。

3. **第二步验证（打包）**：跑 `build.bat`，确认 `dist\E621Downloader.exe` 生成、体积约 37 MB、双击能启动；用 `Get-FileHash dist\E621Downloader.exe -Algorithm SHA256` 记录新哈希。
4. **动 UI 前**：先在 100% 与 150% 缩放下拖动、贴边、最大化还原、切主题各做一遍，确认基线行为。
5. **改代码后必须自查**：单机模式是否仍然默认拦截联网；游客路径是否仍然不写盘；对外名称是否仍为 `E621Downloader`；`icon.ico`/`icon.png` 是否仍在发布物中。

---

## 9. 续开发记录（2026-11-20）

> 本节记录交接文档生成之后实际发生的改动，供后续开发者 / AI 直接对齐当前代码与产物状态。**以本节为准，覆盖上文对应旧描述。**

### 9.1 源码改动（仅 `E621Downloader_GitHub\E6dlGithub`）

| 文件 | 改动 |
| --- | --- |
| `e6core.py` | `download_image()` 返回值由 `bool` 改为 `Optional[str]`：成功 `None`、取消 `"已取消"`、失败返回可读错误（HTTP 状态码或异常文本），失败时清理 `.part`；`fetch_favorites()` 增加 `page` 参数；新增 `fetch_all_favorites()`（逐页拉取、按 id 去重、页间隔 1.1s、默认上限 25 页）。 |
| `gui.py` | `DownloadWorker` 新增 `item_failed = Signal(str, str)`；`SearchPage` 新增 `_on_item_failed()`，完成提示显示「其中 N 项下载失败」；`SingleDownloadWorker` 输出具体错误；收藏页改用 `fetch_all_favorites`；`MainWindow` 的 `WA_TranslucentBackground` 从 `self.root` 移到**顶层窗口**。 |
| `gui_widgets.py` | `ImageLoader.user_agent` 改用 `e6core.user_agent()`（不再硬编码版本串）。 |
| `script.py` | 两处硬编码 `E621Downloader/1.4` 改为 `user_agent(username)` / `user_agent()`，并补 `user_agent` 导入。 |
| `gui_theme.py` | `extend_frame()` 的 `_MARGINS(0,0,0,0)` 改为 `_MARGINS(-1,-1,-1,-1)`（云母铺满客户区的前提）。 |

### 9.2 云母材质移除与通知条修复

- **云母已全部移除**：删除 DWM/Mica 常量与函数、自绘壁纸底图、`Tokens.bg` 字段及设置页「当前材质」文案；窗口背景统一为纯色（深色 `#202020`、浅色 `#F3F3F3`）。
- **通知提示条**：`InfoBar` 样式选择器由 `QFrame` 改为 `#InfoBar`，避免图标/文字 `QLabel` 被套上外框；三个子控件统一垂直居中，修复排版错位。
- 已做冒烟测试：窗口正常启动，背景为纯色，通知条在深/浅色与窄窗口下均对齐。

### 9.3 版本与打包

- `e6core.APP_VERSION` 已升级为 `"1.5.1"`。
- 已用 `python -m PyInstaller --noconfirm --clean E6dl.spec` 重新打包；`build\`、`dist\`、`__pycache__` 已在打包后清理，保持上传目录干净。
- `release\E621Downloader.exe` 已更新：**39,025,502 字节**，SHA256：
  ```
  90AFF8BEC26364865998103F23721F1D2F83BA7D8202158C1BED3FB3316080DB
  ```
- `release\RELEASE_NOTES.md` 的 SHA256 已同步。
- 该 exe 包含 v1.5.1 全部改动：移除云母材质与设置项文案、修复通知提示条排版错位。

### 9.4 工作区与环境状态

- 权威源码仍为 `E621Downloader_GitHub\E6dlGithub`；本轮源码改动**只在此目录**。
- `E621Downloader_snapshot\E6Dler` 与 `E621Downloader_release` **未同步**（仍是旧代码 / 旧 exe）；如需发布请从 GitHub 树重新打包或复制。
- 本机会话曾因 `D:\Files\E621Downloader` 归 `Administrators` 所有、普通用户无写权限而无法运行 `pwsh`（`windows-acl workspace grant failed`）；切到完全权限后正常。换机器/换会话若再遇到，需管理员给该目录补当前用户「完全控制」，或把项目移到用户个人目录。
- 本仓库仍**无 `.git`**；`release\E621Downloader.exe` 与 `RELEASE_NOTES.md` 已被更新，但 Git 历史目前仍只在远端。
