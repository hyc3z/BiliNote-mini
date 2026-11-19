import os
import json
import logging
import tempfile
from abc import ABC
from typing import Union, Optional, List

import requests
import yt_dlp

from app.downloaders.base import Downloader, DownloadQuality, QUALITY_MAP, YDL_RETRY_OPTS
from app.downloaders.bilibili_dm_patch import apply_bilibili_dm_img_patch
from app.downloaders.bilibili_subtitle import BilibiliSubtitleFetcher
from app.downloaders.ffmpeg import get_ffmpeg_location
from app.models.notes_model import AudioDownloadResult
from app.models.transcriber_model import TranscriptResult, TranscriptSegment
from app.utils.path_helper import get_data_dir
from app.utils.url_parser import extract_video_id
from app.services.cookie_manager import CookieConfigManager

logger = logging.getLogger(__name__)

# Inject the dm_img_* / web_location risk-control params Bilibili's wbi/playurl
# gateway now requires; without them the API path returns HTTP 412. See
# app/downloaders/bilibili_dm_patch.py for details.
apply_bilibili_dm_img_patch()


class BilibiliDownloader(Downloader, ABC):
    def __init__(self):
        super().__init__()
        self._cookie_mgr = CookieConfigManager()
        self._cookie = self._cookie_mgr.get('bilibili')
        self._cookiefile = self._write_netscape_cookie_file()

    def _write_netscape_cookie_file(self) -> Optional[str]:
        """将 Cookie 写入 Netscape 格式临时文件，返回文件路径（供 yt-dlp cookiefile 使用）"""
        if not self._cookie:
            logger.warning("B站 Cookie 未配置，下载可能失败")
            return None
        lines = ["# Netscape HTTP Cookie File\n"]
        for pair in self._cookie.split("; "):
            if "=" in pair:
                key, value = pair.split("=", 1)
                lines.append(f".bilibili.com\tTRUE\t/\tFALSE\t0\t{key}\t{value}\n")
        tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8')
        tmp.writelines(lines)
        tmp.close()
        logger.info("已生成 B站 Netscape Cookie 文件: %s (条目: %d)", tmp.name, len(lines) - 1)
        return tmp.name

    def _report_progress(self, event):
        callback = getattr(self, "progress_callback", None)
        if not callback:
            return
        total = event.get("total_bytes") or event.get("total_bytes_estimate")
        done = event.get("downloaded_bytes", 0)
        callback(message="音轨下载完成" if event.get("status") == "finished" else "正在下载音轨",
            substage="downloading_audio", downloaded_bytes=done, total_bytes=total,
            percent=min(100.0, done / total * 100) if total else None,
            speed_bytes=event.get("speed"), eta_seconds=event.get("eta"))

    def download(
        self,
        video_url: str,
        output_dir: Union[str, None] = None,
        quality: DownloadQuality = "fast",
        need_video:Optional[bool]=False,
        skip_download: bool = False
    ) -> AudioDownloadResult:
        if output_dir is None:
            output_dir = get_data_dir()
        if not output_dir:
            output_dir=self.cache_data
        os.makedirs(output_dir, exist_ok=True)

        output_path = os.path.join(output_dir, "%(id)s.%(ext)s")

        ydl_opts = {
            **YDL_RETRY_OPTS,
            'format': 'bestaudio[ext=m4a]/bestaudio',
            'outtmpl': output_path,
            'http_headers': {'Referer': 'https://www.bilibili.com'},
            # Keep the original audio: faster-whisper decodes it through PyAV.
            'postprocessors': [],
            'progress_hooks': [self._report_progress],
            'noplaylist': True,
            'quiet': False,
        }
        if self._cookiefile:
            ydl_opts['cookiefile'] = self._cookiefile
        ffmpeg_location = get_ffmpeg_location()
        if ffmpeg_location:
            ydl_opts['ffmpeg_location'] = ffmpeg_location

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(video_url, download=not skip_download)
            except yt_dlp.utils.DownloadError as exc:
                message = str(exc)
                # 充电专属/会员内容在没有权限时只会返回预览格式（durl），
                # 没有独立音轨，bestaudio 选择器就会报这个很模糊的错误。
                if "Requested format is not available" in message:
                    raise RuntimeError(self._describe_format_failure(video_url)) from exc
                if "supporter-only video" in message:
                    raise RuntimeError(
                        "该视频为充电专属/会员内容，当前 B 站账号无权观看。"
                        "请在设置里更新 B 站 Cookie；若已登录仍失败，需要先开通对应 UP 的充电。\n"
                        + message
                    ) from exc
                raise
            video_id = info.get("id")
            title = info.get("title")
            duration = info.get("duration", 0)
            cover_url = info.get("thumbnail")
            audio_path = "" if skip_download else ydl.prepare_filename(info)
            if not skip_download and not os.path.isfile(audio_path):
                raise FileNotFoundError(f"音轨下载完成但文件不存在：{audio_path}")

        return AudioDownloadResult(
            file_path="" if skip_download else audio_path,
            title=title,
            duration=duration,
            cover_url=cover_url,
            platform="bilibili",
            video_id=video_id,
            raw_info=info,
            video_path=None  # ❗音频下载不包含视频路径
        )

    def _describe_format_failure(self, video_url: str) -> str:
        """把 yt-dlp 的 format 错误翻译成能指导用户下一步的中文提示。"""
        if not self._cookie:
            return "B 站没有返回可用音轨，且当前未配置 B 站 Cookie。请在设置里填写 B 站 Cookie 后重试。"

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
            ),
            "Referer": "https://www.bilibili.com",
            "Cookie": self._cookie,
        }

        # 先确认保存的 Cookie 是否还有登录态；过期后 B 站会降级成预览格式。
        try:
            nav = requests.get(
                "https://api.bilibili.com/x/web-interface/nav", headers=headers, timeout=10
            ).json()
            if not (nav.get("data") or {}).get("isLogin"):
                return (
                    "当前保存的 B 站 Cookie 未登录或已失效，B 站没有返回可用音轨。"
                    "请在设置里重新从已登录的浏览器复制 B 站 Cookie 后重试；"
                    "若视频是充电专属，更新 Cookie 后仍需账号本身有对应观看权限。"
                )
        except Exception as exc:
            logger.warning("查询 B 站登录状态失败：%s", exc)

        bvid = extract_video_id(video_url, "bilibili")
        if bvid:
            try:
                response = requests.get(
                    "https://api.bilibili.com/x/web-interface/view",
                    params={"bvid": bvid},
                    headers=headers,
                    timeout=10,
                )
                data = (response.json() or {}).get("data") or {}
                exclusive = bool(data.get("is_upower_exclusive"))
                playable = bool(data.get("is_upower_play"))
                if exclusive and not playable:
                    return (
                        "该视频是「UP 主充电专属」，当前 B 站账号没有观看权限，"
                        "B 站只返回了预览格式、没有完整音轨。"
                        "请确认账号已开通该 UP 的充电后重试；Cookie 失效时也会出现同样提示。"
                    )
                if exclusive and playable:
                    return (
                        "该视频是充电专属，账号有观看权限，但 B 站没有返回独立音轨（可能只给了预览格式）。"
                        "请更新 B 站 Cookie 或稍后重试。"
                    )
            except Exception as exc:
                logger.warning("查询视频可访问性失败（%s）：%s", bvid, exc)

        return (
            "B 站没有返回可用音轨（常见原因：视频为充电专属/会员内容、B 站 Cookie 已过期，或视频受限）。"
            "请在设置里更新 B 站 Cookie 后重试；充电专属视频需要账号本身有观看权限。"
        )

    def download_video(
        self,
        video_url: str,
        output_dir: Union[str, None] = None,
    ) -> str:
        """
        下载视频，返回视频文件路径
        """

        if output_dir is None:
            output_dir = get_data_dir()
        os.makedirs(output_dir, exist_ok=True)
        print("video_url",video_url)
        video_id=extract_video_id(video_url, "bilibili")
        video_path = os.path.join(output_dir, f"{video_id}.mp4")
        if os.path.exists(video_path):
            return video_path

        # 检查是否已经存在


        output_path = os.path.join(output_dir, "%(id)s.%(ext)s")

        ydl_opts = {
            **YDL_RETRY_OPTS,
            'format': 'bv*[ext=mp4]/bestvideo+bestaudio/best',
            'outtmpl': output_path,
            'http_headers': {'Referer': 'https://www.bilibili.com'},
            'noplaylist': True,
            'quiet': False,
            'merge_output_format': 'mp4',  # 确保合并成 mp4
        }
        if self._cookiefile:
            ydl_opts['cookiefile'] = self._cookiefile
        ffmpeg_location = get_ffmpeg_location()
        if ffmpeg_location:
            ydl_opts['ffmpeg_location'] = ffmpeg_location

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=True)
            video_id = info.get("id")
            video_path = os.path.join(output_dir, f"{video_id}.mp4")

        if not os.path.exists(video_path):
            raise FileNotFoundError(f"视频文件未找到: {video_path}")

        return video_path

    def delete_video(self, video_path: str) -> str:
        """
        删除视频文件
        """
        if os.path.exists(video_path):
            os.remove(video_path)
            return f"视频文件已删除: {video_path}"
        else:
            return f"视频文件未找到: {video_path}"

    def download_subtitles(self, video_url: str, output_dir: str = None,
                           langs: List[str] = None) -> Optional[TranscriptResult]:
        """
        尝试获取B站视频字幕

        :param video_url: 视频链接
        :param output_dir: 输出路径
        :param langs: 优先语言列表
        :return: TranscriptResult 或 None
        """
        # 1) 优先走 B 站官方 player API（直拉，无需下视频；AI 字幕需 SESSDATA cookie）
        try:
            result = BilibiliSubtitleFetcher().fetch_subtitles(video_url)
            if result and result.segments:
                return result
        except Exception as e:
            logger.warning(f"player API 直拉字幕异常，回退到 yt-dlp: {e}")

        # 2) Fallback：原 yt-dlp 路径（更脆弱，遇到签名/Cookie 问题失败概率较高）
        if output_dir is None:
            output_dir = get_data_dir()
        if not output_dir:
            output_dir = self.cache_data
        os.makedirs(output_dir, exist_ok=True)

        if langs is None:
            langs = ['zh-Hans', 'zh', 'zh-CN', 'ai-zh', 'en', 'en-US']

        video_id = extract_video_id(video_url, "bilibili")

        ydl_opts = {
            **YDL_RETRY_OPTS,
            'writesubtitles': True,
            'writeautomaticsub': True,
            'subtitleslangs': langs,
            'subtitlesformat': 'srt/json3/best',  # 支持多种格式
            'skip_download': True,
            'outtmpl': os.path.join(output_dir, f'{video_id}.%(ext)s'),
            'quiet': True,
        }

        # 通过 CookieConfigManager 注入 B站 Cookie（Netscape cookiefile）
        if self._cookiefile:
            ydl_opts['cookiefile'] = self._cookiefile
            ydl_opts['http_headers'] = {'Referer': 'https://www.bilibili.com'}

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=True)

                # 查找下载的字幕文件
                subtitles = info.get('requested_subtitles') or {}
                if not subtitles:
                    logger.info(f"B站视频 {video_id} 没有可用字幕")
                    return None

                # 按优先级查找字幕
                detected_lang = None
                sub_info = None
                for lang in langs:
                    if lang in subtitles:
                        detected_lang = lang
                        sub_info = subtitles[lang]
                        break

                # 如果按优先级没找到，取第一个可用的（排除弹幕）
                if not detected_lang:
                    for lang, info_item in subtitles.items():
                        if lang != 'danmaku':  # 排除弹幕
                            detected_lang = lang
                            sub_info = info_item
                            break

                if not sub_info:
                    logger.info(f"B站视频 {video_id} 没有可用字幕（排除弹幕）")
                    return None

                # 检查是否有内嵌数据（yt-dlp 有时直接返回字幕内容）
                if 'data' in sub_info and sub_info['data']:
                    logger.info(f"直接从返回数据解析字幕: {detected_lang}")
                    return self._parse_srt_content(sub_info['data'], detected_lang)

                # 查找字幕文件
                ext = sub_info.get('ext', 'srt')
                subtitle_file = os.path.join(output_dir, f"{video_id}.{detected_lang}.{ext}")

                if not os.path.exists(subtitle_file):
                    logger.info(f"字幕文件不存在: {subtitle_file}")
                    return None

                # 根据格式解析字幕文件
                if ext == 'json3':
                    return self._parse_json3_subtitle(subtitle_file, detected_lang)
                else:
                    with open(subtitle_file, 'r', encoding='utf-8') as f:
                        return self._parse_srt_content(f.read(), detected_lang)

        except Exception as e:
            logger.warning(f"获取B站字幕失败: {e}")
            return None

    def _parse_srt_content(self, srt_content: str, language: str) -> Optional[TranscriptResult]:
        """
        解析 SRT 格式字幕内容

        :param srt_content: SRT 字幕文本内容
        :param language: 语言代码
        :return: TranscriptResult
        """
        import re
        try:
            segments = []
            # SRT 格式: 序号\n时间戳\n文本\n\n
            pattern = r'(\d+)\n(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})\n(.*?)(?=\n\n|\n\d+\n|$)'
            matches = re.findall(pattern, srt_content, re.DOTALL)

            for match in matches:
                idx, start_time, end_time, text = match
                text = text.strip()
                if not text:
                    continue

                # 转换时间格式 00:00:00,000 -> 秒
                def time_to_seconds(t):
                    parts = t.replace(',', '.').split(':')
                    return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])

                segments.append(TranscriptSegment(
                    start=time_to_seconds(start_time),
                    end=time_to_seconds(end_time),
                    text=text
                ))

            if not segments:
                return None

            full_text = ' '.join(seg.text for seg in segments)
            logger.info(f"成功解析B站SRT字幕，共 {len(segments)} 段")
            return TranscriptResult(
                language=language,
                full_text=full_text,
                segments=segments,
                raw={'source': 'bilibili_subtitle', 'format': 'srt'}
            )

        except Exception as e:
            logger.warning(f"解析SRT字幕失败: {e}")
            return None

    def _parse_json3_subtitle(self, subtitle_file: str, language: str) -> Optional[TranscriptResult]:
        """
        解析 json3 格式字幕文件

        :param subtitle_file: 字幕文件路径
        :param language: 语言代码
        :return: TranscriptResult
        """
        try:
            with open(subtitle_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            segments = []
            events = data.get('events', [])

            for event in events:
                # json3 格式中时间单位是毫秒
                start_ms = event.get('tStartMs', 0)
                duration_ms = event.get('dDurationMs', 0)

                # 提取文本
                segs = event.get('segs', [])
                text = ''.join(seg.get('utf8', '') for seg in segs).strip()

                if text:  # 只添加非空文本
                    segments.append(TranscriptSegment(
                        start=start_ms / 1000.0,
                        end=(start_ms + duration_ms) / 1000.0,
                        text=text
                    ))

            if not segments:
                return None

            full_text = ' '.join(seg.text for seg in segments)

            logger.info(f"成功解析B站字幕，共 {len(segments)} 段")
            return TranscriptResult(
                language=language,
                full_text=full_text,
                segments=segments,
                raw={'source': 'bilibili_subtitle', 'file': subtitle_file}
            )

        except Exception as e:
            logger.warning(f"解析字幕文件失败: {e}")
            return None