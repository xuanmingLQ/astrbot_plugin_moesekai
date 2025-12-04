from ..utils.webdriver import PlaywrightPage
import asyncio, os, re
from datetime import datetime, timedelta
from astrbot.api import logger, AstrBotConfig
from typing import Optional, Dict, Tuple



EVNET_ID_PATTERN = r'event(\d+)'
RANK_PATTERN = r't?(\d+)'
def extract_event_id_rank_from_args(args: str)->Tuple[Optional[None], Optional[None], str]:
    if event_id := re.search(EVNET_ID_PATTERN, args):
        args = args.replace(event_id.group(), '')
        event_id = int(event_id.groups()[0])
    if rank := re.search(RANK_PATTERN, args):
        args = args.replace(rank.group(), '')
        rank = int(rank.groups()[0])
    return event_id, rank, args

locks:Dict[int, asyncio.Lock] = {}
locks_lock: asyncio.Lock = asyncio.Lock()

async def get_lock(lock_id: int) -> asyncio.Lock:
    global locks, locks_lock
    async with locks_lock:
        if lock_id not in locks:
            locks[lock_id] = asyncio.Lock()
        return locks[lock_id]

async def get_sekairanking_img(config: AstrBotConfig, event_id: Optional[int] = None, rank: Optional[int] = None, refresh: bool = False) -> str:
    lock = await get_lock( event_id if event_id is not None else -1 )
    r"""获取截图的路径"""
    screenshot_path = "data/sekairanking/screenshots/"
    if event_id is None:
        screenshot_path = f"{screenshot_path}current/"
    else:
        screenshot_path = f"{screenshot_path}{event_id}/"
    if rank is None:
        screenshot_path = f"{screenshot_path}overview.png"
    else:
        if rank not in config.all_ranks:
            raise Exception(f"排名 {rank} 无效，支持的排名：{config.all_ranks}")
        screenshot_path = f"{screenshot_path}chart-{rank}.png"
    async with lock:
        if not refresh and os.path.exists(screenshot_path): # 图片存在且不强制刷新
            if event_id is None: # 如果是查看当前活动，不超时就不重新下载
                file_mtime = datetime.fromtimestamp(os.path.getmtime(screenshot_path))
                if  datetime.now() < file_mtime + timedelta(seconds=config.cache_duration):
                    return os.path.abspath(screenshot_path)
            else: # 如果是查看历史活动，不强制刷新就不重新下载
                return os.path.abspath(screenshot_path)
        logger.info(f"event {event_id if event_id is not None else '当前'} 的截图不存在或已过期或刷新，重新下载")
        try:
            await screenshot_sekairanking_page(config, event_id)
            logger.info(f"下载 event {event_id if event_id is not None else '当前'} 的截图成功")
        except Exception as e:
            logger.error(f"下载图片失败 {e} 尝试返回缓存图片")
    # 下载截图成功或失败，都返回缓存图片路径
    if os.path.exists(screenshot_path):
        return os.path.abspath(screenshot_path)
    else:
        raise Exception(f"获取 event {event_id if event_id is not None else '当前'} 的截图失败")

async def screenshot_sekairanking_page(config: AstrBotConfig, event_id: Optional[int] = None):
    url:str = config.base_url
    screenshot_path = "data/sekairanking/screenshots/"
    if event_id is None:
        screenshot_path = f"{screenshot_path}current/"
    else:
        screenshot_path = f"{screenshot_path}{event_id}/"
        if not url.endswith('/'):
            url += '/'
        url = f"{url}event/{event_id}"
    async with PlaywrightPage() as page:
        await page.goto(url, wait_until='domcontentloaded', timeout=config.timeout*1000)
        # 等待加载遮罩消失
        await page.wait_for_selector(
            "#loadingOverlay.hidden",
            state="attached",  
            timeout=config.timeout*1000 
        )
        # 设置窗口大小
        await page.set_viewport_size({"width": config.page_size[0], "height": config.page_size[1]})
        # 截图总览
        await page.screenshot(path=f"{screenshot_path}overview.png", full_page=True)
        # 截图单个rank
        for rank in config.all_ranks:
            card_id = f"chart-{rank}"
            try:
                card_locator = page.locator(f"xpath=//*[@id='{card_id}']/..")
                await card_locator.screenshot(path=f"{screenshot_path}{card_id}.png")
            except Exception as e: 
                logger.error(f"获取截图失败：{e}")
                continue

