from app.downloaders.bilibili_downloader import BilibiliDownloader

SUPPORT_PLATFORM_MAP = {'bilibili': BilibiliDownloader}

from app.downloaders.external_downloader import ExternalDownloader
SUPPORT_PLATFORM_MAP.update(youtube=ExternalDownloader,instagram=ExternalDownloader)
