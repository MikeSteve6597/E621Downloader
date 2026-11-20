# GitHub 发布指南

本文件夹已按可直接上传 GitHub 的结构整理完成。按照下面的步骤即可完成首次发布。

## 1. 文件夹内容

```
E6dlGithub/
├─ README.md                 # 仓库首页说明（已写好）
├─ LICENSE                   # MIT 许可证
├─ .gitignore                # 排除缓存、日志、本地配置
├─ requirements.txt          # 运行依赖
├─ requirements-build.txt    # 打包依赖
├─ build.bat                 # 一键打包脚本
├─ E6dl.spec                 # PyInstaller 配置
├─ e6core.py / gui.py / gui_theme.py / gui_widgets.py / script.py
├─ icon.ico / icon.png
└─ release/
   ├─ E621Downloader.exe     # 已打包的单文件程序
   └─ RELEASE_NOTES.md       # Release 页面文案
```

## 2. 发布前检查

- [ ] 双击 `release\E621Downloader.exe` 能正常启动
- [ ] 不要上传 `%USERPROFILE%\E6Dler\userdata.json`（内含 API Key，明文保存）
- [ ] 不要上传下载目录中的图片或 `downloaded_md5.txt`
- [ ] 如需修改作者名：编辑 `LICENSE` 中的版权署名
- [ ] 如需修改仓库地址：在 `README.md` 中补充仓库链接

## 3. 创建 GitHub 仓库

1. 登录 GitHub，点击右上角 **+ → New repository**。
2. Repository name 填 `E621Downloader`。
3. 选择 **Public**。
4. **不要**勾选 Add a README file、Add .gitignore、Choose a license（本文件夹已经包含）。
5. 点击 **Create repository**。

## 4. 上传文件

### 方式 A：网页上传（无需安装 Git）

> 注意：GitHub 网页上传单个文件上限 25 MB，`release\E621Downloader.exe`（约 39 MB）无法通过网页上传。请先上传其余全部文件（含 `release\RELEASE_NOTES.md`），exe 留到第 5 步作为 Release 附件上传（附件上限 2 GB）。

1. 在新建的仓库页面点击 **uploading an existing file**。
2. 把 `E6dlGithub` 文件夹内的所有内容拖入页面，**但暂时不要拖 `release\E621Downloader.exe`**。
3. 确认 `.gitignore`、`README.md`、`release/RELEASE_NOTES.md` 等文件都在列表中。
4. 在提交说明中填写 `Initial commit`，点击 **Commit changes**。

### 方式 B：Git 命令行

本机当前未检测到 Git。可先安装 [Git for Windows](https://git-scm.com/download/win) 或使用 GitHub Desktop，然后执行：

```powershell
cd "$env:USERPROFILE\Desktop\E6dlGithub"
git init
git add .
git commit -m "Initial commit: E621Downloader 1.5.1"
git branch -M main
git remote add origin https://github.com/MikeSteve6597/E621Downloader.git
git push -u origin main
```

> 首次提交前建议执行 `git config --global user.name "你的名字"` 与 `git config --global user.email "你的邮箱"`。

## 5. 创建 Release 并上传 exe

1. 进入仓库页面，点击右侧 **Releases → Draft a new release**。
2. **Choose a tag** 填 `v1.5.1`，点击 **Create new tag**。
3. Release title 填 `E621Downloader v1.5.1`。
4. 描述部分粘贴 `release/RELEASE_NOTES.md` 的内容。
5. 在 **Attach binaries** 处上传 `release/E621Downloader.exe`（保持原文件名，不要压缩）。
6. 点击 **Publish release**。

发布完成后，README 中的 Releases 链接与下载都可使用。

## 6. 仓库信息建议

- **Description**：`e621 图片浏览与批量下载工具，Windows Fluent Design 桌面客户端`
- **Topics**：`e621`、`downloader`、`pyside6`、`fluent-design`、`windows`、`gui`、`python`
- 建议在仓库设置中关闭 Wiki 与 Projects（如不需要）。

## 7. 安全与合规

- 仓库中不得包含任何个人 API Key、Cookie 或下载的内容。
- `.gitignore` 已排除 `userdata.json`、`*.log`、`build/`、`dist/`。
- README 已包含成人内容警告与非官方声明，请保留。
- 若未来加入 CI 自动打包，请使用 GitHub Actions 的 Windows runner，并注意 exe 体积。

## 8. 后续版本发布流程

1. 修改 `e6core.py` 中的 `APP_VERSION`。
2. 双击 `build.bat` 重新打包，替换 `release\E621Downloader.exe`。
3. 更新 `release/RELEASE_NOTES.md`。
4. 提交代码，创建新的 tag（如 `v1.5.2`）并发布 Release，上传新的 exe。
