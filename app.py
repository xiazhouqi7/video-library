"""VideoLibrary: local-only personal video archiver for authorized content."""
from __future__ import annotations

import os
import shutil
import threading
import uuid
import json
import secrets
import tempfile
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, jsonify, render_template, request
from yt_dlp import YoutubeDL

APP = Flask(__name__)
SETTINGS = Path(__file__).with_name('settings.json')
TOKEN = secrets.token_urlsafe(32)
SERVER = None
try:
    SAVED = json.loads(SETTINGS.read_text(encoding='utf-8'))
except (OSError, ValueError):
    SAVED = {}
SAVE_DIR = Path(SAVED.get('save_dir') or r'D:\Creator\视频下载\下载成品').expanduser().resolve()
APP.config['MAX_CONTENT_LENGTH'] = 16384


class QuietLogger:
    # yt-dlp diagnostics can contain private URLs or browser data.
    def debug(self, message): pass
    def warning(self, message): pass
    def error(self, message): pass


@APP.before_request
def local_guard():
    if request.host not in ('127.0.0.1:8765', 'localhost:8765'):
        return jsonify(error='无效的本地主机。'), 403
    if request.path.startswith('/api/'):
        origin = request.headers.get('Origin')
        if origin and origin not in ('http://127.0.0.1:8765', 'http://localhost:8765'):
            return jsonify(error='来源校验失败。'), 403
        if request.headers.get('Sec-Fetch-Site') == 'cross-site':
            return jsonify(error='来源校验失败。'), 403
        if not secrets.compare_digest(request.headers.get('X-Local-Token', ''), TOKEN):
            return jsonify(error='请刷新本地页面后重试。'), 403
        if request.method == 'POST' and not request.is_json:
            return jsonify(error='请求必须为 JSON。'), 415


@APP.after_request
def security_headers(response):
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    return response


def check_directory(path):
    path.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryFile(dir=path):
        pass
    if shutil.disk_usage(path).free < 1024 ** 3:
        raise ValueError('保存目录可用空间不足 1 GB，请释放空间或更换目录。')


@APP.post('/api/settings')
def settings():
    global SAVE_DIR
    try:
        with LOCK:
            if ACTIVE_JOB:
                raise ValueError('下载期间不能修改保存位置。')
            raw = (request.get_json(silent=True) or {}).get('save_dir')
            if not isinstance(raw, str) or not raw.strip() or not Path(raw).is_absolute():
                raise ValueError('请输入完整的绝对目录路径。')
            target = Path(raw).resolve()
            check_directory(target)
            temp = SETTINGS.with_suffix('.tmp')
            temp.write_text(json.dumps({'save_dir': str(target)}, ensure_ascii=False), encoding='utf-8')
            temp.replace(SETTINGS)
            SAVE_DIR = target
        return jsonify(save_dir=str(SAVE_DIR))
    except Exception as exc:
        return jsonify(error=friendly_error(exc)), 400


@APP.post('/api/open-folder')
def open_folder():
    try:
        SAVE_DIR.mkdir(parents=True, exist_ok=True)
        os.startfile(str(SAVE_DIR))
        return jsonify(ok=True)
    except OSError:
        return jsonify(error='无法打开保存目录，请在资源管理器中手动打开。'), 400


@APP.post('/api/stop')
def stop():
    global STOPPING
    with LOCK:
        if ACTIVE_JOB:
            return jsonify(error='请等待当前下载完成再退出。'), 409
        STOPPING = True
    if SERVER:
        threading.Thread(target=SERVER.shutdown, daemon=True).start()
    return jsonify(ok=True)


STOPPING = False
ALLOWED_DOMAINS = ('youtube.com', 'youtu.be', 'bilibili.com', 'b23.tv', 'douyin.com', 'iesdouyin.com')
JOBS: dict[str, dict] = {}
LOCK = threading.RLock()
ACTIVE_JOB: str | None = None


def validate_url(raw: object) -> str:
    if not isinstance(raw, str):
        raise ValueError('请粘贴完整的视频链接。')
    url = raw.strip()
    if not url or len(url) > 2048:
        raise ValueError('请输入长度合理的视频链接。')
    parsed = urlparse(url)
    host = (parsed.hostname or '').lower()
    if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port:
        raise ValueError('目前仅支持 HTTPS 视频链接。')
    if not any(host == domain or host.endswith('.' + domain) for domain in ALLOWED_DOMAINS):
        raise ValueError('第一版仅支持抖音、B站和 YouTube 的链接。')
    return url


def browser_opts(url: str, use_firefox: bool) -> dict:
    """Opt-in; only for YouTube. Never persist/export browser login data."""
    host = (urlparse(url).hostname or '').lower()
    youtube = host in ('youtu.be', 'youtube.com') or host.endswith('.youtube.com')
    if use_firefox and not youtube:
        raise ValueError('Firefox 登录会话选项仅适用于 YouTube。')
    return {'cookiesfrombrowser': ('firefox',)} if use_firefox else {}


def friendly_error(exc: Exception) -> str:
    message = str(exc)
    if isinstance(exc, (ValueError, OSError)):
        return message[:250] if isinstance(exc, ValueError) else '本地文件操作失败，请检查目录权限、路径和磁盘空间。'
    if '403' in message:
        return '平台拒绝访问（HTTP 403），请稍后重试或使用其他有权访问的来源。'
    if 'Could not copy' in message and 'cookie' in message.lower():
        return '无法读取 Firefox 登录信息。请完全退出 Firefox 后重试。'
    if 'Failed to decrypt' in message or 'failed to load cookies' in message:
        return '读取浏览器登录信息失败，请检查 Firefox 登录状态，且不要禁用系统安全保护。'
    if 'Sign in to confirm' in message or 'not a bot' in message:
        return 'YouTube 要求登录验证。可在确认来源和使用权限后，勾选 Firefox 登录会话再识别。'
    if 'Requested format is not available' in message:
        return '当前会话没有提供所选视频画质，请重新识别或换一种画质。'
    return '解析或下载失败，请检查网络、链接有效性及平台访问权限后重试。'


def get_metadata(url: str, use_firefox: bool = False) -> dict:
    opts = {
        'quiet': True,
        'logger': QuietLogger(),
        'no_warnings': True,
        'noplaylist': True,
        'skip_download': True,
        'socket_timeout': 18,
        'retries': 1,
        'extractor_retries': 1,
        'ignoreerrors': False,
        **browser_opts(url, use_firefox),
    }
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    if not info or info.get('_type') == 'playlist' or info.get('entries'):
        raise ValueError('请使用单条视频链接，暂不支持合集或播放列表。')
    formats = info.get('formats') or []
    heights = sorted({int(f['height']) for f in formats
                     if f.get('vcodec') not in (None, 'none') and isinstance(f.get('height'), (int, float))
                     and 0 < f['height'] <= 8640}, reverse=True)
    # Some extractor results contain no separate formats; use their height if known.
    if not heights and isinstance(info.get('height'), (int, float)):
        heights = [int(info['height'])]
    choices = [{'value': 'best', 'label': '最高可用画质'}]
    for h in heights:
        fmt_candidates = [f for f in formats if f.get('vcodec') not in (None, 'none') and f.get('height') == h]
        width = max((int(f.get('width')) for f in fmt_candidates if isinstance(f.get('width'), (int, float))), default=None)
        label = f'{h}p · {width}×{h}' if width else f'{h}p'
        if width and width >= 3800 and h >= 1900:
            label += ' · 超高清'
        choices.append({'value': str(h), 'label': label})
    return {
        'title': str(info.get('title') or '未命名视频')[:180],
        'uploader': str(info.get('uploader') or info.get('channel') or '')[:80],
        'duration': info.get('duration'),
        'choices': choices,
        'id': str(info.get('id') or '')[:100],
    }


def update_job(job_id: str, **values: object) -> None:
    with LOCK:
        if job_id in JOBS:
            JOBS[job_id].update(values)


def do_download(job_id: str, url: str, quality: str, use_firefox: bool) -> None:
    global ACTIVE_JOB
    try:
        target_dir = Path(JOBS[job_id]['save_dir'])
        check_directory(target_dir)
        final_paths = []
        def finished_hook(payload):
            info = payload.get('info_dict') or {}
            if payload.get('status') == 'finished' and info.get('filepath'):
                final_paths.append(info['filepath'])
        update_job(job_id, status='running', message='正在获取视频数据…')
        def progress_hook(payload: dict) -> None:
            if payload.get('status') == 'downloading':
                done = payload.get('downloaded_bytes') or 0
                total = payload.get('total_bytes') or payload.get('total_bytes_estimate') or 0
                pct = min(99, round(100 * done / total)) if total else None
                update_job(job_id, message='正在下载视频…', percent=pct)
            elif payload.get('status') == 'finished':
                update_job(job_id, message='下载完成，正在整理音视频…', percent=99)

        fmt = 'bestvideo+bestaudio/best' if quality == 'best' else (
            f'bestvideo[height<={quality}]+bestaudio/best[height<={quality}]'
        )
        opts = {
            'format': fmt,
            'outtmpl': str(target_dir / ('%(title).150s [%(id)s] ' + job_id[:8] + '.%(ext)s')),
            'merge_output_format': 'mp4/mkv',
            'noplaylist': True,
            'windowsfilenames': True,
            'progress_hooks': [progress_hook],
            'postprocessor_hooks': [finished_hook],
            'quiet': True,
            'logger': QuietLogger(),
            'no_warnings': True,
            'overwrites': False,
            'continuedl': True,
            'socket_timeout': 25,
            'retries': 3,
            'fragment_retries': 3,
            **browser_opts(url, use_firefox),
        }
        with YoutubeDL(opts) as ydl:
            code = ydl.download([url])
        if code:
            raise RuntimeError('视频处理未成功完成。')
        candidates = [Path(p) for p in final_paths if Path(p).is_file()]
        if not candidates:
            candidates = [p for p in target_dir.glob('*' + job_id[:8] + '.*')
                          if p.suffix.lower() not in ('.part', '.ytdl', '.temp') and p.is_file()]
        details = {'save_dir': str(target_dir)}
        if candidates:
            output = max(candidates, key=lambda p: p.stat().st_size)
            details.update(path=str(output), size=output.stat().st_size, resolution='未能检测')
            ffprobe = shutil.which('ffprobe')
            if ffprobe:
                try:
                    result = subprocess.run([ffprobe, '-v', 'error', '-select_streams', 'v:0',
                                             '-show_entries', 'stream=width,height', '-of', 'json', str(output)],
                                            capture_output=True, text=True, timeout=30,
                                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                    streams = json.loads(result.stdout).get('streams', [])
                    if streams:
                        details['resolution'] = str(streams[0]['width']) + '×' + str(streams[0]['height'])
                except (OSError, ValueError, KeyError, subprocess.TimeoutExpired):
                    pass
        update_job(job_id, status='done', percent=100, message='已保存到电脑。', **details)
    except Exception as exc:
        update_job(job_id, status='error', percent=0, message=f'保存失败：{friendly_error(exc)}')
    finally:
        with LOCK:
            if ACTIVE_JOB == job_id:
                ACTIVE_JOB = None


@APP.get('/')
def index():
    return render_template('index.html', token=TOKEN)


@APP.get('/api/config')
def config():
    return jsonify(save_dir=str(SAVE_DIR), ffmpeg_ready=bool(shutil.which('ffmpeg')), version='1.2-preview', active_job=ACTIVE_JOB)


@APP.post('/api/probe')
def probe():
    try:
        payload = request.get_json(silent=True) or {}
        url = validate_url(payload.get('url'))
        use_firefox = payload.get('use_firefox') is True
        return jsonify(get_metadata(url, use_firefox))
    except Exception as exc:
        return jsonify(error=friendly_error(exc)), 400


@APP.post('/api/download')
def download():
    global ACTIVE_JOB
    try:
        payload = request.get_json(silent=True) or {}
        url = validate_url(payload.get('url'))
        use_firefox = payload.get('use_firefox') is True
        browser_opts(url, use_firefox)
        quality = payload.get('quality', 'best')
        if quality != 'best' and (not str(quality).isdigit() or not 1 <= int(quality) <= 8640):
            raise ValueError('画质参数不正确。')
        quality = str(quality)
        check_directory(SAVE_DIR)
        if not shutil.which('ffmpeg'):
            raise ValueError('找不到 FFmpeg。请安装后重新启动本工具。')
        with LOCK:
            if STOPPING:
                raise ValueError('服务正在退出，请重新启动。')
            if ACTIVE_JOB:
                return jsonify(error='正在处理另一条视频，请等本次完成后再试。'), 409
            job_id = uuid.uuid4().hex
            JOBS[job_id] = {'id': job_id, 'save_dir': str(SAVE_DIR), 'status': 'waiting', 'percent': 0, 'message': '正在准备下载…'}
            ACTIVE_JOB = job_id
        thread = threading.Thread(target=do_download, args=(job_id, url, quality, use_firefox), daemon=True)
        try:
            thread.start()
        except RuntimeError:
            with LOCK:
                ACTIVE_JOB = None
                JOBS.pop(job_id, None)
            raise
        return jsonify(job_id=job_id)
    except Exception as exc:
        return jsonify(error=friendly_error(exc)), 400


@APP.get('/api/jobs/<job_id>')
def job_status(job_id: str):
    with LOCK:
        result = JOBS.get(job_id)
        if not result:
            return jsonify(error='没有找到下载任务。'), 404
        return jsonify(result)


if __name__ == '__main__':
    from werkzeug.serving import make_server
    try:
        SERVER = make_server('127.0.0.1', 8765, APP, threaded=True)
    except (OSError, SystemExit):
        raise SystemExit(1)
    SERVER.serve_forever()
