<p align="center"><img src="icon.png" width="112" alt="E621Downloader 图标"></p>

<h1 align="center">E621Downloader</h1>

<p align="center">
  e621 图片浏览与批量下载工具 · Windows Fluent Design 桌面客户端
  <br>
  <strong>版本 1.5</strong>
</p>

> [!WARNING]
> e621 是面向成年人的内容站点，部分内容可能包含成人向素材。本项目仅提供第三方客户端工具，与 e621 官方无任何关联。请确认你已年满 18 周岁，并遵守所在地法律法规及 e621 的使用条款。

## 简介

E621Downloader 是一个基于 Python + PySide6 构建的 Windows 桌面客户端，用于浏览 e621 作品、按标签批量搜索下载，并管理收藏与黑名单。界面遵循 Windows 11 Fluent Design 设计语言，支持 Mica 云母材质、深色/浅色主题与高 DPI 缩放。

程序以**单文件 exe** 形式发布，目标电脑无需安装 Python 或任何运行库，复制后双击即可启动。

## 功能特性

**浏览与发现**
- 发现页展示 e621 推荐内容，瀑布式预览，无需登录即可浏览
- 点击作品查看大图、评分、分级、标签与收藏数
- 支持「在浏览器中打开」原作品页

**搜索与批量下载**
- 多标签搜索，支持逗号分隔
- 持久化黑名单 + 单次搜索临时黑名单，自动从发现、搜索、收藏中隐藏
- 可设置最低评分、下载页数（1–50）、每页数量（1–320）
- 三种画质：原图 / 采样图 / 预览图
- 实时进度、下载取消、MD5 去重、自动跳过已下载文件
- 自定义下载目录，默认 `%USERPROFILE%\Downloads\E6dl`
- 游客模式下载，不保存任何搜索与下载记录

**账号与收藏**
- 使用 e621 用户名 + API Key 登录
- 收藏 / 取消收藏，收藏页统一浏览
- 多选模式：批量收藏、批量拉黑、批量下载

**本地数据与外观**
- 搜索历史与最近关键词（可配置保留条数）
- 深色 / 浅色 / 跟随系统主题，Windows 11 Mica 材质
- 一键清空搜索历史、清空图片缓存、打开配置目录
- 单机 / 在线模式开关，默认单机模式，所有联网请求受统一门禁控制

## 运行要求

| 项目 | 要求 |
| --- | --- |
| 操作系统 | Windows 10 / Windows 11 64 位（Windows 11 下启用 Mica 材质） |
| 运行环境 | 无需安装 Python，单文件 exe 直接运行 |
| 网络 | 在线模式需要访问 `e621.net` |
| 账号 | 登录与收藏功能需要 e621 账号及 API Key |

## 下载与运行

1. 前往 [Releases](https://github.com/MikeSteve6597/E621Downloader/releases/latest) 页面，在 Assets 中下载 `E621Downloader.exe`（约 39 MB）。
2. 双击 `E621Downloader.exe` 启动，无需安装。
3. 首次启动默认为「单机模式」，请前往 **设置 › 运行模式** 切换为「在线模式」。

## 快速上手

1. **浏览**：切换在线模式后，发现页会自动加载推荐作品；未登录也可浏览。
2. **登录（可选）**：点击左下角账户入口，输入 e621 用户名与 API Key。API Key 可在 [e621 API 文档](https://e621.net/help/api) 中获取。
3. **搜索下载**：进入「搜索下载」，填写关键词、黑名单、画质、页数、每页数量与最低评分，点击「开始下载」。
4. **收藏管理**：登录后可在作品详情页收藏，在「我的收藏」中批量管理。
5. **黑名单**：在「黑名单」页添加要屏蔽的标签，所有列表会自动过滤。

> 未登录时点击下载会询问「登录下载」或「游客下载」。游客模式不会保存登录信息、搜索历史与下载记录。

## 数据与隐私

| 内容 | 位置 |
| --- | --- |
| 配置、账号、黑名单、搜索历史 | `%USERPROFILE%\E6Dler\userdata.json` |
| 默认下载目录 | `%USERPROFILE%\Downloads\E6dl` |
| 下载去重记录 | 下载目录下的 `downloaded_md5.txt` |
| 错误日志 | `%LOCALAPPDATA%\E6Dler\e6dler-error.log` |

> 配置目录、缓存目录与日志文件名沿用内部代号 `E6Dler` / `e6dler`，仅用于兼容已有数据，不影响程序显示名称。

- 所有数据仅保存在本机，程序不包含遥测、统计或任何上传行为。
- **API Key 以明文形式保存在本机配置文件中**，请勿分享 `userdata.json`，也不要把该文件提交到 Git 仓库。
- 程序不会向自身目录或 exe 写入账号信息，可放在任意路径运行。

## 从源码运行

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 启动 GUI
python gui.py

# 启动命令行版本（可选）
python script.py
```

## 打包为单文件 exe

```powershell
pip install -r requirements-build.txt
python -m PyInstaller --noconfirm --clean E6dl.spec
```

或直接双击 `build.bat`。构建产物位于 `dist\E621Downloader.exe`。

## 项目结构

```
E621Downloader/
├─ gui.py            # GUI 入口与页面实现
├─ gui_theme.py      # Fluent Design 主题令牌、Mica 支持
├─ gui_widgets.py    # 自绘控件与图片加载器
├─ e6core.py         # e621 API、配置、下载核心
├─ script.py         # 命令行版本
├─ E6dl.spec         # PyInstaller 打包配置
├─ build.bat         # 一键打包脚本
├─ icon.ico / icon.png
├─ requirements.txt
└─ requirements-build.txt
```

## 常见问题

**发现页空白或提示单机模式？**
程序默认以单机模式启动，请到 **设置 › 运行模式** 切换为在线模式。

**提示登录状态失效（HTTP 401）？**
用户名或 API Key 不正确/已失效，请在账户入口重新登录。

**提示请求过于频繁（HTTP 429）？**
e621 对请求频率有限制，请稍后重试。程序在翻页之间内置了约 1.1 秒的请求间隔。

**下载目录中没有文件？**
请确认下载目录可写，且搜索条件（最低评分、黑名单）没有过滤掉所有结果。

**Windows 10 上没有 Mica 效果？**
Mica 是 Windows 11 的系统特性，Windows 10 下会自动回退为纯色背景，其余功能不受影响。

**旧版本下载的文件会被重复下载吗？**
不会。程序会读取下载目录中的 `downloaded_md5.txt` 并按 MD5 去重。

## 免责声明

- 本项目为第三方开源工具，与 e621 官方及其运营方无任何关联。
- 请自行确保使用行为符合 e621 的服务条款、API 使用规范以及你所在地的法律法规。
- 请勿使用本工具大量抓取内容或对 e621 服务器造成压力。
- 使用者需自行承担因使用本工具产生的一切后果。

## 许可证

本项目使用 [MIT License](LICENSE) 发布。

第三方依赖：PySide6（LGPL-3.0）、requests（Apache-2.0）。
