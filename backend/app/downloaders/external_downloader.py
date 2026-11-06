from pathlib import Path
import yt_dlp
from app.downloaders.base import Downloader, YDL_RETRY_OPTS
from app.models.audio_model import AudioDownloadResult
from app.utils.video_source import detect

class ExternalDownloader(Downloader):
    def download(self,video_url,output_dir=None,quality='medium',need_video=False,skip_download=False):
        platform=detect(video_url)
        folder=Path(output_dir or 'data');folder.mkdir(parents=True,exist_ok=True)
        options={**YDL_RETRY_OPTS,'format':'bestaudio/best','outtmpl':str(folder/(platform+'-%(id)s.%(ext)s')),'noplaylist':True,'quiet':True,'postprocessors':[]}
        def progress(event):
            callback=getattr(self,'progress_callback',None)
            if callback:
                total=event.get('total_bytes') or event.get('total_bytes_estimate')
                done=event.get('downloaded_bytes',0)
                callback(message='正在获取 '+platform+' 媒体',downloaded_bytes=done,total_bytes=total,percent=done/total*100 if total else None)
        options['progress_hooks']=[progress]
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
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

