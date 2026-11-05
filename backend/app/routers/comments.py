from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from app.services import comments
from app.utils.response import ResponseWrapper as R
router=APIRouter()
class Crawl(BaseModel):
    limit:int=Field(500,ge=20,le=5000)
    replies:bool=True
    sort:int=Field(2,ge=0,le=2)
class Analyze(BaseModel):
    provider_id:str
    model_name:str
    sample:int=Field(300,ge=20,le=1000)
@router.get('/comments/{bvid}')
def read(bvid:str):
    try:
        data=comments.load(bvid)
        if data.get('state')=='RUNNING' and bvid not in comments.active:
            data.update(state='FAILED',error='服务曾中断，已保存部分结果，请重新采集或分析')
        return R.success(data=data)
    except ValueError as exc:raise HTTPException(422,str(exc))
@router.post('/comments/{bvid}/crawl')
def crawl(bvid:str,data:Crawl):
    try:return R.success(data=comments.start(bvid,'crawl',data.model_dump()))
    except ValueError as exc:raise HTTPException(409,str(exc))
@router.post('/comments/{bvid}/analyze')
def analyze(bvid:str,data:Analyze):
    try:return R.success(data=comments.start(bvid,'analyze',data.model_dump()))
    except ValueError as exc:raise HTTPException(409,str(exc))
