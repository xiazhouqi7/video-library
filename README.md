# VideoLibrary · Windows 本地视频保存工具

一个用于保存**自己制作、获得授权、或平台允许保存**的视频素材的本地网页工具。当前仅作为个人原型，不用于批量抓取、绕过付费/登录限制、DRM 或去除创作者水印。

> **版本：v1.2.0（2026-11-08，Windows 实测通过）**
> 本仓库只含源码，不含 `.venv/`、下载的视频、Cookies、日志和本地设置（见 `.gitignore`）。
> 仅在本地 `127.0.0.1:8765` 运行，不要把端口暴露到公网。

## v1.2 更新

- 后台启动管理：`manage.ps1`（Start / Open / Status / Stop / EnableStartup / DisableStartup / Shortcut），`start.bat` 为可见控制台诊断入口；`open.vbs` 用于桌面快捷方式无窗口启动。
- 保存目录可在网页「保存位置与服务」里改，写入本地 `settings.json`（不进仓库），重启保留；默认目录见 `app.py` 的 `SAVE_DIR`。
- 剪贴板读取只在操作时进行；自动读取需勾选同意，仅页面打开/重新聚焦尝试一次。
- 安全加固：只绑定 `127.0.0.1`，API 校验 Host / Origin / 跨站 Fetch 标记和每次进程随机令牌；不启用 CORS。
- 详细验收记录见 `docs/V1.2-acceptance-notes.md`，启动修复记录见 `docs/startup-fix-notes.txt`。
- 回滚：停止新版服务并关闭自启后，用 v1.1 备份文件覆盖同名源码即可，保留 `.venv` 和所有视频。

## 运行方式（Windows 10/11）

### 1. 安装基础工具

- 安装 [Python 3.11 或更新版本](https://www.python.org/downloads/windows/)；Windows 命令行运行 `python --version` 确认。
- 安装 FFmpeg（音视频处理工具）。在 PowerShell 运行：

  ```powershell
  winget install -e --id Gyan.FFmpeg
  ```

  安装完成后，**关掉旧 PowerShell 窗口，重新打开**，运行 `ffmpeg -version` 验证。若本机 `winget` 不可用，参见 [FFmpeg 官方下载](https://ffmpeg.org/download.html)。
- YouTube 的完整支持在部分情况下还需要 JavaScript 运行环境（例如 Deno）及 `yt-dlp-ejs`。本项目通过 `yt-dlp[default]` 安装 Python 依赖。详见 [yt-dlp 官方依赖说明](https://github.com/yt-dlp/yt-dlp#dependencies)。

### 2. 初始化和启动

1. 解压整个文件夹，**不要单独移动 HTML**。
2. 双击 `setup.bat` 安装 Python 虚拟环境和依赖（只需首次安装，或手动更新时运行）。Python 3.11+ 即可；微软商店版 Python 3.13 也可用，在 PowerShell 里用 `python --version` 确认。
3. 双击 `start.bat` 启动服务。浏览器自动打开 `http://127.0.0.1:8765`。`start.bat` 现在是诊断入口，成功时自动结束，失败时保留窗口并提示看 `logs\startup.log`。
4. 也可以在项目目录打开 PowerShell（无需管理员）：
   ```powershell
   powershell -NoProfile -File .\manage.ps1 -Action Shortcut  # 创建桌面快捷方式
   powershell -NoProfile -File .\manage.ps1 -Action Open      # 后台启动并打开网页
   powershell -NoProfile -File .\manage.ps1 -Action Status    # 查看运行状态
   powershell -NoProfile -File .\manage.ps1 -Action Stop      # 退出服务（下载期间会拒绝）
   ```
   只有显式运行 `EnableStartup` 才会注册登录自启，`DisableStartup` 可关闭。
5. 粘贴平台允许下载、或你获得授权的视频链接；点击「识别视频」，选择真实可用的画质，再点击「保存到电脑」。
6. 处理结束后，视频会保存在本地保存目录（默认见 `app.py` 的 `SAVE_DIR`，可在网页里改）。

**提示**：下载过程中不要直接关闭服务。关闭服务窗口就停止本地服务，未完成任务可能中断。

### 3. 自定义文件夹（可选）

用文本编辑器打开 `start.bat`，在运行 Python 那行之前增加：

```bat
set "VIDEO_SAVE_DIR=D:\VideoLibrary"
```

前提是电脑确实存在 `D:` 盘。下次启动后网页底部会显示保存路径。

## v1.1 更新

- 新增 YouTube 可选「Firefox 登录会话」：仅当用户勾选时，从本地 Firefox 读取 Cookie 用于视频解析与保存；不创建 Cookie 导出文件，也不会发送给用户界面。
- 需要先安装 Firefox、正常登录并完成平台验证；使用时完全退出 Firefox。Chrome 目前可能遇到 DPAPI 加密问题，因此不提供 Chrome 选项。
- YouTube 视频格式解析需要兼容的 Deno 和 yt-dlp EJS，参考 https://github.com/yt-dlp/yt-dlp/wiki/EJS 。
- 修复识别新链接、识别失败时仍展示旧任务「100% 完成」的混淆。
- 画质选项尽可能展示实际像素尺寸。
- **更新旧项目**：关闭 `start.bat`，将更新包的 `app.py`、`static`、`templates` 和 `README.md` 覆盖到原来的 `video-library-mvp` 文件夹。**不要删除 `.venv` 文件夹**；已有环境无需重新执行 `setup.bat`。

## 第一版实现的功能

- 本机浏览器网页，限制只监听 `127.0.0.1`，不向局域网或互联网提供服务。
- 识别抖音、B站、YouTube 的单个 HTTPS 链接（平台支持与访问权限会变化）。
- 显示视频标题、作者和来源报告的可用分辨率，不凭空列出 4K。
- 优先选取视频与音频并通过 FFmpeg 合并，尽可能保留来源质量；合并容器优先 MP4，必要时 MKV。
- 单任务下载、进度反馈、失败原因、本地文件夹保存。

## 第一版限制

- 不支持播放列表、批量任务、取消任务或历史记录；允许主动使用 Firefox 的现有 YouTube 登录会话。
- 不支持破解 DRM、绕过付费墙或自动绕过访问验证；仅在用户明确勾选时读取本机 Firefox Cookie。
- 「可用格式」只是解析结果；页面显示成功不保证下载环节一定成功。
- 若平台只提供带水印的视频流，此工具不会通过画面擦除/裁切去除水印。
- FFmpeg 的合并与视频转码不同：一般不会重新编码视频；部分组合会使用 MKV 容器。
- 默认最高画质不等于一定是 4K，具体取决于内容源和权限。
- 启动在本地开发服务器，仅供个人 Windows 本机使用；**不要把 Flask 开发服务器端口直接暴露到公网**。
- 没有进行真实网络平台视频的端到端测试（测试环境无法联网）。部署使用前请用自己制作或获得授权的测试视频确认。

## 项目结构

```text
video-library-mvp/
  app.py             # Flask 后端
  requirements.txt   # Python 依赖
  setup.bat          # 首次安装
  start.bat          # 日常启动
  templates/
    index.html       # 页面结构
  static/
    style.css        # 页面样式
    app.js           # 交互和进度查询
```

## 常见问题

- **提示找不到 FFmpeg**：安装 FFmpeg 后关闭终端和本工具，重新启动。确认 `ffmpeg -version` 可执行。
- **无法识别某个平台**：先更新 yt-dlp，检查视频是否公开、是否获得授权、链接是否完整，再看具体报错。可重新运行 `setup.bat` 更新依赖。
- **YouTube 有 JavaScript 相关错误**：按 yt-dlp 官方文档安装兼容的 Deno 或其他受支持运行时，之后重试。
- **视频没有 4K 选项**：可能源视频本来没有 4K、平台未向当前会话提供，或解析器暂时无法识别。
- **失败后是否会继续下载**：同名未完成文件可能可续传；本项目没有实现任务持久化或恢复队列。

## 迭代计划

1. 完善失败日志、画质与音轨匹配验证、停止任务和任务历史。
2. 如需手机提交任务，再使用受认证、私有网络方案让 iPhone 将链接发送到 Windows。不要直接在路由器上映射本地端口。
3. 之后再考虑桌面应用打包，减少日常启动和 Python 环境依赖。
