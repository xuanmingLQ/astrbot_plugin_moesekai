from astrbot.api import AstrBotConfig
from astrbot.api.event import AstrMessageEvent, filter as event_filter
from astrbot.api.star import Context, Star, register

from .src.config import set_global_config
from .src.handlers import dispatch_event
from .src.utils.lifecycle import run_initialize_hooks, run_terminate_hooks
from .src.moesekai import handlers as _moesekai_handlers  # noqa: F401


@register("moesekai", "xmlq", "访问moesekai并截图", "0.0.1")
class MoesekaiPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        set_global_config(config)

    async def initialize(self):
        await run_initialize_hooks()

    @event_filter.event_message_type(event_filter.EventMessageType.ALL)
    async def _(self, event: AstrMessageEvent):
        async for result in dispatch_event(event):
            yield result

    async def terminate(self):
        await run_terminate_hooks()
