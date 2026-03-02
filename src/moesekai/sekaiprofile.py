from astrbot.api import logger
from ..config import get_global_config, Config
from ..utils.webdriver import PlaywrightPage
from ..utils.tempfile import TempFilePath
from datetime import timedelta
from ..utils.lifecycle import on_initialize
from ..handlers import HandlerContext, SekaiCmdHandler, assert_and_reply, ReplyException
from ..utils.bind import get_player_bind_id
import os

config: Config | None = None
@on_initialize()
def initialize_sekai_ranking():
    global config
    config = get_global_config()
# 获取个人信息截图
async def get_sekaiprofile_img(ctx: HandlerContext, uid: str):
    allow_regions:list[str] = config.sekaiprofile.bind_limit.keys()
    assert_and_reply(ctx.region in allow_regions, f"不支持的服务器 {ctx.region}，当前支持的服务器：{allow_regions}")
    base_url:str = config.sekaiprofile.base_url
    assert_and_reply(base_url, "没有配置sekaiprofile.base_url")
    token: str = config.sekaiprofile.token
    assert_and_reply(token, "没有配置sekaiprofile.token")
    url = base_url.format(region=ctx.region, user_id=uid, token=token)
    async with PlaywrightPage() as page:
        try:
            await page.goto(url, wait_until='networkidle', timeout=60000)
            await page.set_viewport_size({"width": 1000, "height": 1000})
            main_container_locator = page.locator(".pjsk-container").nth(0)
            # 使用临时文件返回
            with TempFilePath('png') as path:
                await main_container_locator.screenshot(path=path)
                yield ctx.event.image_result(os.path.abspath(path))
        except TimeoutError as e:
            raise ReplyException("下载个人信息页面失败：连接超时")
        except Exception as e:
            raise Exception("下载个人信息页面失败")
    pass
_profile_handle = SekaiCmdHandler(
    ["个人信息", "grxx", "profile"]
)
@_profile_handle.handle()
async def _(ctx):
    uid = get_player_bind_id(ctx)
    async for result in get_sekaiprofile_img(ctx=ctx, uid=uid):
        yield result
