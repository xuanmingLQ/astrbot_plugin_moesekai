from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent

class NoReplyException(Exception):
    """
    触发特定消息回复并且不会折叠的Exception，用于退出当前消息处理
    """
    pass
class ReplyException(Exception):
    """
    触发特定消息回复并且不会折叠的Exception，用于退出当前消息处理
    """
    pass

def assert_and_reply(condition, msg: str):
    """
    检查条件，如果不满足则抛出ReplyException
    """
    if not condition:
        raise ReplyException(msg)

class HandlerContext:
    event: AstrMessageEvent

    def __init__(self, event: AstrMessageEvent):
        self.event = event
        self.region: str | None = None
        self.trigger_cmd: str = ""
        self.original_trigger_cmd: str = ""
        self.arg_text: str = ""
        self.prefix_arg: str = ""

    def get_args(self) -> str:
        return self.arg_text
    
class CmdHandler:
    """基础命令处理器。"""

    _handlers: list["CmdHandler"] = []

    def __init__(self, commands: list[str]):
        self.commands = self._normalize_commands(commands)
        self.handler_func: Callable[[HandlerContext], Any] | None = None
        CmdHandler._handlers.append(self)
        print(f"注册指令 {commands[0]}")

    @staticmethod
    def _normalize_spaces(text: str) -> str:
        return " ".join(str(text).strip().split())

    @classmethod
    def _normalize_commands(cls, commands: list[str]) -> list[str]:
        normalized = []
        for command in commands:
            cmd = cls._normalize_spaces(command)
            if cmd.startswith("/"):
                cmd = cmd[1:].lstrip()
            if cmd:
                normalized.append(cmd)
        normalized = list(dict.fromkeys(normalized))
        normalized.sort(key=len, reverse=True)
        return normalized

    def handle(self):
        def decorator(func: Callable[[HandlerContext], Any]):
            self.handler_func = func
            return func

        return decorator

    def check_cdrate(self, *_args, **_kwargs):
        # 兼容 refer 中的链式写法，后续再接入实际逻辑。
        return self

    def check_wblist(self, *_args, **_kwargs):
        # 兼容 refer 中的链式写法，后续再接入实际逻辑。
        return self

    def parse_context(self, event: AstrMessageEvent) -> HandlerContext | None:
        raise NotImplementedError

    def get_prefix_hint(self, event: AstrMessageEvent) -> str | None:
        return None


async def _iter_results(result: Any):
    if result is None:
        return

    if inspect.isawaitable(result) and not inspect.isasyncgen(result):
        awaited = await result
        async for item in _iter_results(awaited):
            if item is not None:
                yield item
        return

    if inspect.isasyncgen(result) or hasattr(result, "__aiter__"):
        async for item in result:
            if item is not None:
                yield item
        return

    if isinstance(result, (list, tuple)):
        for item in result:
            if item is not None:
                yield item
        return

    yield result


async def dispatch_event(event: AstrMessageEvent):
    """在已注册处理器中分发事件。"""
    logger.debug(event.get_message_str())
    message = event.get_message_str().strip()
    logger.debug(message)
    if not message.startswith("/"):
        return

    missing_prefix_hint: str | None = None
    logger.debug(CmdHandler._handlers)
    for handler in list(CmdHandler._handlers):
        logger.debug(handler.commands)
        ctx = handler.parse_context(event)
        if ctx is None:
            if missing_prefix_hint is None:
                missing_prefix_hint = handler.get_prefix_hint(event)
            continue
        if handler.handler_func is None:
            return

        try:
            result = handler.handler_func(ctx)
            async for item in _iter_results(result):
                yield item
        except NoReplyException:
            return
        except ReplyException as e:
            yield event.plain_result(str(e))
        except Exception as e:
            logger.error(f"指令处理失败: {e}", exc_info=True)
            yield event.plain_result(f"指令处理失败: {e}")
        return
    logger.debug(missing_prefix_hint)
    if missing_prefix_hint:
        yield event.plain_result(missing_prefix_hint)
