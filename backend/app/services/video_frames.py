"""On-demand timestamp frames, cached locally; no complete video download."""
import os
from pathlib import Path
import uuid
import av
import yt_dlp
from filelock import FileLock
from app.services import library


def frame(task_id, seconds):
    uuid.UUID(task_id)
    note=library.get(task_id)
    if not note:
        raise ValueError('笔记尚未保存')
    audio=note.get('audio_meta', {})
    duration=audio.get('duration') or 0
    if seconds<0 or seconds>86400 or (duration and seconds>duration):
        raise ValueError('时间戳超出视频范围')
    folder=Path(os.getenv('NOTE_OUTPUT_DIR','note_results'))/'frames'/task_id
    folder.mkdir(parents=True,exist_ok=True)
    target=folder/f'{seconds}.jpg'
    with FileLock(str(target)+'.lock',timeout=90):
        if target.is_file():return target
        from app.downloaders.bilibili_downloader import BilibiliDownloader
        downloader=BilibiliDownloader() if audio.get('platform','bilibili')=='bilibili' else None
        options={'quiet':True,'no_warnings':True,'noplaylist':True,'format':'worstvideo[ext=mp4]/worst[ext=mp4]/worst','socket_timeout':15}
        if downloader and downloader._cookiefile:options['cookiefile']=downloader._cookiefile
        source=(audio.get('raw_info') or {}).get('webpage_url') if audio.get('platform') in ('youtube','instagram') else 'https://www.bilibili.com/video/'+audio['video_id'].replace('_p','?p=')
        with yt_dlp.YoutubeDL(options) as ydl:
            info=ydl.extract_info(source,download=False)
        headers={**info.get('http_headers',{}),'Referer':'https://www.bilibili.com/'}
        with av.open(info['url'],options={'headers':''.join(f'{k}: {v}\r\n' for k,v in headers.items())},timeout=20) as container:
            stream=container.streams.video[0]
            container.seek(int(seconds/stream.time_base),stream=stream,backward=True)
            chosen=None
            for decoded in container.decode(stream):
                chosen=decoded
                if decoded.time is not None and decoded.time>=seconds:break
            if chosen is None:raise ValueError('未能读取对应画面')
            width=min(960,chosen.width);height=max(2,int(chosen.height*width/chosen.width)//2*2)
            image=chosen.reformat(width=width,height=height,format='yuvj420p')
            encoder=av.CodecContext.create('mjpeg','w');encoder.width=width;encoder.height=height;encoder.pix_fmt='yuvj420p'
            content=b''.join(bytes(p) for p in encoder.encode(image))+b''.join(bytes(p) for p in encoder.encode(None))
            temp=target.with_suffix('.tmp');temp.write_bytes(content);temp.replace(target)
        return target
