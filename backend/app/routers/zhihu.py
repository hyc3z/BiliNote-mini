from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.zhihu_judge import judge
from app.utils.response import ResponseWrapper as R

router = APIRouter()


class ZhihuJudgeRequest(BaseModel):
    mode: str = "answer"
    question: Optional[str] = ""
    question_detail: Optional[str] = ""
    selection: Optional[str] = ""
    answer: Optional[str] = ""
    context: Optional[str] = ""
    author: Optional[str] = ""
    voteup: Optional[str] = ""
    url: Optional[str] = ""
    model_name: Optional[str] = ""
    provider_id: Optional[str] = ""


@router.post('/zhihu/judge')
def zhihu_judge(data: ZhihuJudgeRequest):
    try:
        return R.success(data=judge(data.model_dump()))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f'判断失败：{exc}')
