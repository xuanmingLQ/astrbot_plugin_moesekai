from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig
from .src.snowy.sekairanking import get_sekairanking_img, extract_event_id_rank_from_args
from .src.snowy.sekaiprofile import get_sekaiprofile_img
from .src.utils.webdriver import PlaywrightPage


@register("sekairanking", "xmlq", "访问sekairanking并截图", "0.0.1")
class MyPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config

    async def initialize(self):
        """可选择实现异步的插件初始化方法，当实例化该插件类之后会自动调用该方法。"""
        await get_sekairanking_img(self.config.sekairanking) # 初始化后立刻初始化浏览器并截图一次
   
    @filter.command("cnskp")
    async def _sekairanking(self, event: AstrMessageEvent):
        r"""获取截图，返回图片"""
        message = event.get_message_str()
        logger.debug(message)
        refresh = False
        if 'refresh' in message:
            refresh = True
            message = message.replace('refresh', '')
        event_id, rank, _ = extract_event_id_rank_from_args(message)
        if rank is not None and rank <= 0:
            rank = None
        logger.debug(f"event_id={event_id} rank={rank}")
        try:
            img_path = await get_sekairanking_img(self.config.sekairanking, event_id, rank, refresh)
            yield event.image_result(img_path)
        except Exception as e:
            logger.error(f"获取截图失败：{e}")
            yield event.plain_result(f"获取截图失败：{e}")
    async def _sekaiprofile(self, event: AstrMessageEvent):
        r""""""
        pass
    async def terminate(self):
        """可选择实现异步的插件销毁方法，当插件被卸载/停用时会调用。"""
        await PlaywrightPage.stop() # 关闭时确保playwright被关闭