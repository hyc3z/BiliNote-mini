from urllib.parse import urlparse
import re

def detect(url):
    if re.fullmatch(r'BV[0-9A-Za-z]{10}',url.strip()):return 'bilibili'
    parsed=urlparse(url.strip());host=(parsed.hostname or '').lower()
    if parsed.scheme not in ('http','https'):raise ValueError('请输入视频链接')
    if host in ('www.bilibili.com','bilibili.com','m.bilibili.com','b23.tv'):return 'bilibili'
    if host in ('youtube.com','www.youtube.com','m.youtube.com','youtu.be','www.youtube-nocookie.com') and (host=='youtu.be' or parsed.path in ('/watch',) or parsed.path.startswith(('/shorts/','/live/','/embed/'))):return 'youtube'
    if host in ('instagram.com','www.instagram.com') and re.match(r'^/(p|reel|reels|tv)/[^/]+',parsed.path):return 'instagram'
    raise ValueError('仅支持 B 站、YouTube 视频及 Instagram 视频帖/Reels 链接')
