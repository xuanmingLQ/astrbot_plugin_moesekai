from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from dataclasses import dataclass, field
from datetime import datetime
import asyncio
from argparse import ArgumentParser

from astrbot.core.message.components import ComponentType

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
    


class MessageArgumentParser(ArgumentParser):
    """
    适用于HandlerContext的参数解析器
    """
    def __init__(self, ctx: 'HandlerContext', *args, **kwargs):
        super().__init__(*args, **kwargs, exit_on_error=False)
        self.ctx = ctx

    def error(self, message):
        raise Exception(message)

    async def parse_args(self, error_reply=None, *args, **kwargs):
        try:
            s = self.ctx.get_args().strip().split()
            return super().parse_args(s, *args, **kwargs)
        except Exception as e:
            self.ctx.logger.print_exc("参数解析失败")
            if error_reply is None:
                raise e
            else:
                await self.ctx.asend_msg(error_reply)
                raise NoReplyException()

@dataclass
class HandlerContext:
    handler: "CmdHandler" = None
    event: AstrMessageEvent = None
    trigger_cmd: str = None
    arg_text: str = None
    message_id: str = None
    user_id: str = None
    group_id: str = None
    block_ids: list[str] = field(default_factory=list)

    def get_args(self) -> str:
        return self.arg_text
    def get_argparser(self) -> MessageArgumentParser:
        return MessageArgumentParser(self)
    def get_msg(self):
        return self.event.get_messages()
    def get_sender_name(self)->str:
        return self.event.get_sender_name()
    def get_reply_msg(self)->str:
        for msg in self.event.message_obj.message:
            if msg.type == ComponentType.Reply:
                return msg.chain
        
    
    async def block(self, block_id: str = "", timeout: int = 3 * 60, err_msg: str = None):
        """
        遇到相同block_id调用时阻塞当前指令，超时timeout秒后抛出ReplyException
        """
        block_id = str(block_id)
        block_start_time = datetime.now()
        while True:
            if block_id not in self.handler.block_set:
                break
            if (datetime.now() - block_start_time).seconds > timeout:
                if err_msg is None:
                    err_msg = f'指令执行繁忙(block_id={block_id})，请稍后再试'
                raise ReplyException(err_msg)
            await asyncio.sleep(1)
        self.handler.block_set.add(block_id)
        self.block_ids.append(block_id)

SEG_COMMAND_SEPS = ['', ' ', '_']

class SegCmd:
    """
    由多段构成的指令，用于生成不同分隔符的指令
    """
    def __init__(self, *args, seps: list[str]=SEG_COMMAND_SEPS):
        self.commands = set()
        assert len(args) > 0, "至少需要一个参数"
        if len(args) == 1:
            args = args[0]
            for sep in SEG_COMMAND_SEPS:
                if sep:
                    args = args.replace(sep, ' ')
            args = args.split()
        for sep in seps:
            self.commands.add(''.join([sep.join(args)]))

    def get(self) -> list[str]:
        return list(self.commands)

_cmd_history: list[HandlerContext] = []
MAX_CMD_HISTORY = 100

class CmdHandler:
    """基础命令处理器。"""

    _handlers: list["CmdHandler"] = []

    def __init__(
            self, 
            commands: str | SegCmd | list[str | SegCmd], 
            use_seg_cmd=True
        ):
        if isinstance(commands, str) or isinstance(commands, SegCmd):
            commands = [commands]
        self.commands = []
        for cmd in commands:
            if isinstance(cmd, str):
                if use_seg_cmd:
                    self.commands.extend(SegCmd(cmd).get())
                else:
                    self.commands.append(cmd)
            elif isinstance(cmd, SegCmd):
                self.commands.extend(cmd.get())
            else:
                raise Exception(f'未知的指令类型 {type(cmd)}')

        self.commands = list(set(self.commands)) 
        self.commands.sort(key=lambda x: len(x), reverse=True)

        self.handler_func: Callable[[HandlerContext], Any] | None = None
        CmdHandler._handlers.append(self)
        logger.debug(f"注册指令 {commands[0]}")

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

    async def additional_context_process(self, context: HandlerContext):
        context.handler = self
        return context
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
    plain_text = event.get_message_str().strip()
    logger.debug(plain_text)
    if not plain_text.startswith("/"):
        return
    missing_prefix_hint: str | None = None
    context = HandlerContext()
    context.event = event
    context.message_id = event.message_obj.message_id
    context.user_id = event.get_sender_id()
    context.group_id = event.get_group_id()
    for handler in list(CmdHandler._handlers):
        logger.debug(handler.commands)
        cmd_starts = []
        # TODO 需要做更好的指令解析
        for cmd in sorted(handler.commands, key = len, reverse=True):
            start = plain_text.find(cmd)
            if start != -1:
                cmd_starts.append((cmd, start))
        logger.debug(cmd_starts)
        if len(cmd_starts)<=0:
            continue
        cmd_starts.sort(key=lambda x:x[1])
        context.trigger_cmd = cmd_starts[0][0]
        context.arg_text = plain_text[cmd_starts[0][1] + len(context.trigger_cmd):]
        ctx = await handler.additional_context_process(context)
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
