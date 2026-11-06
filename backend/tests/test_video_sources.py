import unittest
from unittest.mock import patch, MagicMock
from app.utils.video_source import detect
from app.downloaders.external_downloader import ExternalDownloader
from app.routers.note import VideoRequest
class Sources(unittest.TestCase):
    def test_supported_sources(self):
        for url,platform in [('https://youtu.be/BaW_jenozKc','youtube'),('https://www.youtube.com/watch?v=BaW_jenozKc','youtube'),('https://www.instagram.com/reel/ABC123/','instagram'),('BV1WHHy6pEqe','bilibili')]:
            self.assertEqual(detect(url),platform)
            request=VideoRequest(video_url=url,platform='bilibili',quality='medium',model_name='test',provider_id='1')
            self.assertEqual(request.platform,platform)
    def test_reject_fake_hosts_and_profiles(self):
        for url in ['https://youtube.com.evil.com/watch?v=x','http://localhost/watch?v=x','https://www.instagram.com/person/']:
            with self.assertRaises(ValueError):detect(url)
    def test_metadata_preserves_source_platform_without_downloading(self):
        url='https://youtu.be/BaW_jenozKc'
        with patch('app.downloaders.external_downloader.yt_dlp.YoutubeDL') as cls:
            ydl=cls.return_value.__enter__.return_value
            ydl.extract_info.return_value={'id':'BaW_jenozKc','title':'test','duration':10}
            result=ExternalDownloader().download(url,skip_download=True)
            ydl.extract_info.assert_called_once_with(url,download=False)
            self.assertEqual(result.platform,'youtube');self.assertEqual(result.raw_info['webpage_url'],url)
    def test_reject_live_stream(self):
        with patch('app.downloaders.external_downloader.yt_dlp.YoutubeDL') as cls:
            cls.return_value.__enter__.return_value.extract_info.return_value={'id':'x','is_live':True}
            with self.assertRaises(ValueError):ExternalDownloader().download('https://youtu.be/x',skip_download=True)
