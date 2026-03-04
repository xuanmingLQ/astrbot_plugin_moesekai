import asyncio
import os
from datetime import datetime, timedelta
from os.path import join as pjoin

from astrbot.api import logger

from ..utils.webdriver import PlaywrightPage
from ..config import get_global_config, Config
from ..utils.lifecycle import on_initialize
from ..handlers import HandlerContext, SekaiCmdHandler

sekairanking_lock: asyncio.Lock = asyncio.Lock()
config: Config | None = None
@on_initialize(102)
def initialize_sekai_ranking():
    logger.debug("init ranking")
    global config
    config = get_global_config()
    
    logger.debug("注册skp指令")
    pjsk_skp = SekaiCmdHandler(
        [
            "/pjsk sk predict",
            "/pjsk board predict",
            "/sk预测",
            "/榜线预测",
            "/skp",
            "/prediction",
            "/预测",
        ],
        prefix_args=["", "wl"],
        parse_uid_arg=False,
    )
    @pjsk_skp.handle()
    async def _(ctx):
        refresh = False
        args = []
        logger.debug(ctx.get_args())
        for token in ctx.get_args().split():
            if token.casefold() == "refresh":
                refresh = True
                continue
            args.append(token)
        ctx.arg_text = " ".join(args)

        async for result in get_sekairanking_img(ctx=ctx, refresh=refresh):
            yield result

def _get_screenshot_path(ctx: HandlerContext) -> str:
    return pjoin(config.data_path, f"sekairanking/screenshots/{ctx.region}.png")


def _is_cache_valid(ctx: HandlerContext, screenshot_path: str) -> bool:
    if not os.path.exists(screenshot_path):
        return False
    cache_duration = int(config.sekairanking.cache_duration or 0)
    if cache_duration <= 0:
        return True
    mtime = datetime.fromtimestamp(os.path.getmtime(screenshot_path))
    return datetime.now() - mtime <= timedelta(seconds=cache_duration)


async def get_sekairanking_img(ctx: HandlerContext, refresh: bool = False):
    """获取榜线截图结果。"""
    screenshot_path = _get_screenshot_path(ctx)
    os.makedirs(os.path.dirname(screenshot_path), exist_ok=True)

    async with sekairanking_lock:
        if not refresh and _is_cache_valid(ctx, screenshot_path):
            yield ctx.event.image_result(os.path.abspath(screenshot_path))
            return
        try:
            yield ctx.event.plain_result(f"正在下载 {ctx.region} 的榜线预测截图")
            await screenshot_sekairanking_page(ctx, screenshot_path)
            logger.info(f"下载 {ctx.region} 的榜线预测截图成功")
        except Exception as e:
            logger.error(f"下载图片失败: {e}，尝试返回缓存图片")

    if os.path.exists(screenshot_path):
        yield ctx.event.image_result(os.path.abspath(screenshot_path))
    else:
        raise Exception(f"下载 {ctx.region} 的榜线预测截图失败")


async def screenshot_sekairanking_page(ctx: HandlerContext, screenshot_path: str):
    url: str = config.sekairanking.base_url
    if not url.endswith("/"):
        url += "/"
    if ctx.region == "cn":
        url = f"{url}simple"
    else:
        url = f"{url}{ctx.region}/simple"

    async with PlaywrightPage() as page:
        await page.goto(url, wait_until="domcontentloaded", timeout=config.sekairanking.timeout * 1000)
        await page.set_viewport_size(
            {
                "width": config.sekairanking.page_size[0],
                "height": config.sekairanking.page_size[1],
            },
        )
        await page.screenshot(path=screenshot_path, full_page=True)

