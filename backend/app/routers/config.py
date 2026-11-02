from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
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
    if data.platform!='bilibili':raise HTTPException(422,'仅支持 B 站')
    CookieConfigManager().set(data.platform,data.cookie)
    return R.success()

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
