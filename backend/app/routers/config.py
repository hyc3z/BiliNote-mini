from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import requests

from app.services.cookie_manager import CookieConfigManager
from app.services.transcriber_config_manager import TranscriberConfigManager
from app.services.mini_preferences import get_preferences, save_preferences
from app.utils.response import ResponseWrapper as R

router=APIRouter()

class CookieRequest(BaseModel):
    platform:str
    cookie:str

@router.get('/get_downloader_cookie/{platform}')
def get_cookie(platform:str):
    return R.success(data={'platform':platform,'cookie':CookieConfigManager().get(platform) or ''})

@router.post('/update_downloader_cookie')
def save_cookie(data:CookieRequest):
    if data.platform not in ('bilibili','youtube'):
        raise HTTPException(422,'仅支持 B 站 / YouTube')
    CookieConfigManager().set(data.platform,data.cookie)
    return R.success()

def _bilibili_login_status(cookie: str) -> dict:
    if not cookie:
        return {'configured': False, 'isLogin': False}
    try:
        response = requests.get(
            'https://api.bilibili.com/x/web-interface/nav',
            headers={
                'User-Agent': (
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                    '(KHTML, like Gecko) Chrome/131.0 Safari/537.36'
                ),
                'Referer': 'https://www.bilibili.com',
                'Cookie': cookie,
            },
            timeout=10,
        )
        payload = response.json()
    except Exception as exc:
        return {'configured': True, 'isLogin': False, 'error': str(exc)}
    data = payload.get('data') or {}
    return {
        'configured': True,
        'isLogin': bool(data.get('isLogin')),
        'code': payload.get('code'),
        'message': payload.get('message'),
    }

@router.get('/account_status')
def account_status(platform: str):
    """按平台返回 Cookie 配置/登录状态；不返回 Cookie 或账号名。"""
    cookie = CookieConfigManager().get(platform) or ''
    if platform == 'bilibili':
        return R.success(data=_bilibili_login_status(cookie))
    if platform == 'youtube':
        return R.success(data={
            'configured': bool(cookie),
            'isLogin': None,
            'message': '已保存 YouTube Cookie' if cookie else '',
        })
    raise HTTPException(422, '仅支持 B 站 / YouTube')

@router.get('/bilibili_login_status')
def bilibili_login_status():
    """兼容旧调用方；新代码使用 /account_status。"""
    return R.success(data=_bilibili_login_status(CookieConfigManager().get('bilibili') or ''))

@router.get('/transcriber_config')
def transcriber_config():
    return R.success(data=TranscriberConfigManager().get_config())

class TranscriberRequest(BaseModel):
    transcriber_type:str='fast-whisper'
    whisper_model_size:str='small'

@router.post('/transcriber_config')
def update_transcriber(data:TranscriberRequest):
    if data.transcriber_type!='fast-whisper':raise HTTPException(422,'仅支持 faster-whisper')
    return R.success(data=TranscriberConfigManager().update_config(data.transcriber_type,data.whisper_model_size))

@router.get('/sys_check')
def sys_check():return R.success()

@router.get('/mini_preferences')
def mini_preferences():return R.success(data=get_preferences())

class PreferencesRequest(BaseModel):
    device:str

@router.post('/mini_preferences')
def update_preferences(data:PreferencesRequest):
    if data.device not in ('cpu','cuda'):raise HTTPException(422,'设备仅支持 cpu 或 cuda')
    save_preferences(data.device)
    return R.success()

class TermsRequest(BaseModel):
    terms:list[str]

@router.get('/terminology')
def get_terms():
    from app.services.terminology import terms
    return R.success(data={'terms':terms()})

@router.post('/terminology')
def update_terms(data:TermsRequest):
    from app.services.terminology import save_terms
    try:save_terms(data.terms)
    except ValueError as exc:raise HTTPException(422,str(exc))
    return R.success()

class TagTermsRequest(BaseModel):
    tag:str
    terms:list[str]

class VideoTagsRequest(BaseModel):
    bvid:str
    tags:list[str]

@router.get('/tag_terms')
def get_tag_terms():
    from app.services.terminology import tag_config
    return R.success(data=tag_config())

@router.post('/tag_terms')
def put_tag_terms(data:TagTermsRequest):
    from app.services.terminology import update_tag_config
    try:return R.success(data=update_tag_config(tag=data.tag,items=data.terms))
    except ValueError as exc:raise HTTPException(422,str(exc))

@router.post('/video_tags')
def put_video_tags(data:VideoTagsRequest):
    from app.services.terminology import update_tag_config
    try:return R.success(data=update_tag_config(bvid=data.bvid,tags=data.tags))
    except ValueError as exc:raise HTTPException(422,str(exc))
