from astrbot.api import logger, AstrBotConfig
from ..utils.webdriver import PlaywrightPage
from ..utils.tempfile import TempFilePath
from datetime import timedelta
# 获取个人信息截图
async def get_sekaiprofile_img(config: AstrBotConfig, region: str, uid: str) -> str:
    allow_regions:list[str] = config.allow_regions
    if region not in allow_regions:
        raise Exception(f"不支持的服务器 {region}，当前支持的服务器：{allow_regions}")
    base_url:str = config.base_url
    if not base_url:
        raise Exception("没有配置sekaiprofile.base_url")
    token: str = config.token
    if not token:
        raise Exception("没有配置sekaiprofile.token")
    url = base_url.format(user_id=uid, token=token)
    async with PlaywrightPage() as page:
        try:
            await page.goto(url, wait_until='networkidle', timeout=60000)
            # 等待加载遮罩消失
            await page.wait_for_selector(
                "#loadingOverlay.hidden",
                state="attached",  
                timeout=60000 
            )
            await page.set_viewport_size({"width": 1000, "height": 1000})
            main_container_locator = page.locator("#mainContainer")
            # 使用临时文件返回
            with TempFilePath('png', timedelta(minutes=5)) as path:
                await main_container_locator.screenshot(path=path)
                return path
        except TimeoutError as e:
            raise Exception(f"下载个人信息页面失败：连接超时")
        except Exception as e:
            logger.error(f"下载个人信息页面失败: {e}")
            raise Exception(f"下载个人信息页面失败")
    pass