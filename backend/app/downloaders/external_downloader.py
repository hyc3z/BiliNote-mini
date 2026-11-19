import os
import tempfile
from pathlib import Path
import yt_dlp
from app.downloaders.base import Downloader, YDL_RETRY_OPTS
from app.downloaders.ffmpeg import get_ffmpeg_location
from app.models.audio_model import AudioDownloadResult
from app.services.cookie_manager import CookieConfigManager
from app.utils.video_source import detect

COOKIE_DOMAINS = {'youtube': '.youtube.com', 'instagram': '.instagram.com'}


def _write_cookie_file(platform: str) -> str | None:
    cookie = CookieConfigManager().get(platform)
    domain = COOKIE_DOMAINS.get(platform)
    if not cookie or not domain:
        return None
    tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8')
    try:
        tmp.write('# Netscape HTTP Cookie File\n')
        for pair in cookie.split('; '):
            if '=' in pair:
                key, value = pair.split('=', 1)
                tmp.write(f'{domain}\tTRUE\t/\tFALSE\t0\t{key}\t{value}\n')
    finally:
        tmp.close()
    return tmp.name


class ExternalDownloader(Downloader):
    def download(self,video_url,output_dir=None,quality='medium',need_video=False,skip_download=False):
        platform=detect(video_url)
        folder=Path(output_dir or 'data');folder.mkdir(parents=True,exist_ok=True)
        options={**YDL_RETRY_OPTS,'format':'bestaudio/best','outtmpl':str(folder/(platform+'-%(id)s.%(ext)s')),'noplaylist':True,'quiet':True,'postprocessors':[]}
        ffmpeg_location = get_ffmpeg_location()
        if ffmpeg_location:
            options['ffmpeg_location'] = ffmpeg_location
        cookie_file = _write_cookie_file(platform)
        if cookie_file:
            options['cookiefile'] = cookie_file
        def progress(event):
            callback=getattr(self,'progress_callback',None)
            if callback:
                total=event.get('total_bytes') or event.get('total_bytes_estimate')
                done=event.get('downloaded_bytes',0)
                callback(message='正在获取 '+platform+' 媒体',downloaded_bytes=done,total_bytes=total,percent=done/total*100 if total else None)
        options['progress_hooks']=[progress]
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                # 先做一次轻量探测，直播流会在 download=True 时一直录制，必须在下载前拦掉。
                if platform == 'youtube' and not skip_download:
                    probe = ydl.extract_info(video_url, download=False)
                    if probe and probe.get('is_live'):
                        raise ValueError('该 YouTube 视频正在直播，暂不支持；请等直播结束/回放后再试。')
                info=ydl.extract_info(video_url,download=not skip_download)
                if not info or info.get('_type') in ('playlist','multi_video'):raise ValueError('请提供单个视频链接，暂不支持播放列表')
                if info.get('is_live'):raise ValueError('暂不支持正在直播的视频，请等待回放')
                filename='' if skip_download else ydl.prepare_filename(info)
                if not skip_download and not Path(filename).is_file():raise ValueError('下载文件不存在')
                raw={k:info.get(k) for k in ('id','title','duration','tags','uploader','uploader_id','webpage_url')}
                raw['webpage_url']=video_url
                if platform=='instagram':
                    from urllib.parse import urlparse
                    info['id']=urlparse(video_url).path.strip('/').split('/')[1]
                return AudioDownloadResult(filename,info.get('title') or info['id'],info.get('duration') or 0,info.get('thumbnail'),platform,info['id'],raw)
        except yt_dlp.utils.DownloadError as exc:
            raise RuntimeError(platform+' 获取失败，可能受登录、地区或平台访问限制：'+str(exc)) from exc
        finally:
            if cookie_file:
                try:
                    os.unlink(cookie_file)
                except OSError:
                    pass

