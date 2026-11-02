"""Expand a BV into selectable pages or its UGC collection; metadata only."""
import re
from app.services.replay_chat import api
from app.utils.url_parser import extract_video_id


def rows(bvid, data, title=None):
    pages = data.get('pages') or [{'cid': data.get('cid'), 'page': 1,
        'part': data.get('title', title or ''), 'duration': data.get('duration', 0)}]
    result=[]
    for index, page in enumerate(pages, 1):
        if not page.get('cid'):
            raise ValueError('B 站未返回完整分 P 信息，请稍后重试')
        number=int(page.get('page', index))
        label=page.get('part') or title or data.get('title', '')
        result.append({'key': f"{bvid}:{page['cid']}", 'bvid': bvid, 'cid': str(page['cid']),
            'part': number, 'title': label, 'duration': page.get('duration', 0),
            'source': f'https://www.bilibili.com/video/{bvid}?p={number}'})
    return result


def inspect(video_url):
    bvid=extract_video_id(video_url.strip(), 'bilibili')
    if not bvid or not re.fullmatch(r'BV[0-9A-Za-z]{10}', bvid):
        raise ValueError('请输入有效的 B 站 BV 号或视频链接')
    data=api('x/web-interface/view', {'bvid': bvid})
    season=data.get('ugc_season') or {}
    episodes=[episode for section in season.get('sections', []) for episode in section.get('episodes', [])]
    parts=[]
    # Multiple pages are the selection displayed by the player for this BV.
    # A single-page BV may instead belong to a multi-BV collection.
    kind='pages'
    if len(data.get('pages') or [])>1 or not episodes:
        parts=rows(bvid, data)
    else:
        kind='collection'
        seen=set()
        for episode in episodes:
            bv=episode.get('bvid')
            if not bv or bv in seen:
                continue
            seen.add(bv)
            if bv==bvid:
                detail=data
            elif episode.get('pages'):
                detail=episode
            else:
                detail=api('x/web-interface/view', {'bvid': bv})
            parts.extend(rows(bv, detail, episode.get('title')))
    parts=list({p['key']: p for p in parts}.values())
    if not parts:
        raise ValueError('没有找到可处理的选集')
    return {'title': season.get('title') if kind=='collection' else data.get('title', ''),
        'kind': kind, 'parts': parts, 'count': len(parts)}


def prepare(video_url, keys, model, start=True):
    if not keys or len(keys)>60:
        raise ValueError('请选择 1–60 个视频分 P')
    selection=inspect(video_url)
    chosen=set(keys)
    available={p['key'] for p in selection['parts']}
    if not chosen.issubset(available):
        raise ValueError('选集信息已变化，请重新解析后选择')
    from app.services.replay_chat import enqueue_parts
    return enqueue_parts([p for p in selection['parts'] if p['key'] in chosen], model=model, start=start)
