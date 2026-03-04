from __future__ import annotations

from dataclasses import dataclass

from astrbot.api.event import AstrMessageEvent

from ..config import get_global_config, Config
from .base import CmdHandler, HandlerContext, assert_and_reply
from ..utils.lifecycle import on_initialize
from astrbot.api import logger

import re

config: Config | None = None
@on_initialize()
def initialize_sekai():
    global config
    config = get_global_config()

@dataclass
class _CommandMatch:
    prefix_arg: str
    matched_trigger: str
    args: str

@dataclass
class SekaiHandlerContext(HandlerContext):
    region: str = None
    original_trigger_cmd: str = None
    create_from_region: bool = False
    prefix_arg: str = None
    uid_arg: str = None

    @classmethod
    def from_region(cls, region: str) -> 'SekaiHandlerContext':
        ctx = SekaiHandlerContext()
        ctx.region = region
        ctx.create_from_region = True
        ctx.prefix_arg = None
        return ctx
    
    def block_region(self, key="", timeout=3*60, err_msg: str = None):
        if not self.create_from_region:
            return self.block(f"{self.region}_{key}", timeout=timeout, err_msg=err_msg)

class SekaiCmdHandler(CmdHandler):
    """支持sekai命令处理器。"""

    def __init__(
        self,
        commands: list[str],
        regions: list[str] | None = None,
        prefix_args: list[str] | None = None,
    ):
        logger.debug(f"注册 sekai 指令 {commands[0]}")
        self.available_regions = regions or config.regions
        self.prefix_args = sorted(prefix_args or [''], key=lambda x: len(x), reverse=True)
        all_region_commands = []
        for prefix in self.prefix_args:
            for region in self.available_regions:
                for cmd in commands:
                    assert not cmd.startswith(f"/{region}{prefix}")
                    all_region_commands.append(cmd)
                    all_region_commands.append(cmd.replace("/", f"/{prefix}"))
                    all_region_commands.append(cmd.replace("/", f"/{region}{prefix}"))
        self.original_commands = commands
        super().__init__(all_region_commands)

    async def additional_context_process(self, context: HandlerContext):
        cmd_region = None
        original_trigger_cmd = context.trigger_cmd
        for region in config.regions:
            if context.trigger_cmd.strip().startswith(f"/{region}"):
                cmd_region = region
                context.trigger_cmd = context.trigger_cmd.replace(f"/{region}", "/")
                break
        assert_and_reply(
            cmd_region in self.available_regions, 
            f"该指令不支持 {cmd_region} 服务器，可用的服务器有: {', '.join(self.available_regions)}"
        )
        prefix_arg = None
        for prefix in self.prefix_args:
            if context.trigger_cmd.startswith(f"/{prefix}"):
                prefix_arg = prefix
                context.trigger_cmd = context.trigger_cmd.replace(f"/{prefix}", "/")
                break
        # 处理账号指定参数
        args = context.get_args()
        uid_arg = None
        if self.parse_uid_arg:
            # 匹配 u数字 并且前一个字母不能是m
            index_match = re.search(r'(?<!m)u(\d{1,2})', args)
            if index_match:
                uid_arg = f"u{index_match.group(1)}"
                args = args.replace(index_match.group(0), '', 1).strip()
            # 匹配游戏id
            uid_match = re.search(r'(\d{14,20})', args)
            if uid_match:
                uid_arg = uid_match.group(1)
                args = args.replace(uid_match.group(0), '', 1).strip()
            # 匹配 @QQ号
            qq_match = re.search(r'@(\d{9,13})', args)
            if qq_match:
                uid_arg = f"@{qq_match.group(1)}"
                args = args.replace(qq_match.group(0), '', 1).strip()
            # 匹配 at用户
            for seg in context.get_msg():
                seg = seg.toDict()
                stype, sdata = seg['type'], seg.get('data', {})
                if stype == "at" and sdata.get('qq'):
                    uid_arg = f"@{sdata['qq']}"
                    break
        context.handler = self
        params = context.__dict__.copy()
        params['arg_text'] = args
        params['region'] = cmd_region
        params['original_trigger_cmd'] = original_trigger_cmd
        params['create_from_region'] = False
        params['prefix_arg'] = prefix_arg
        params['uid_arg'] = uid_arg
        params['handler'] = self
        return SekaiHandlerContext(**params)
    

    @staticmethod
    def _is_command_head(text: str, command: str) -> bool:
        if len(text) < len(command):
            return False
        if text[:len(command)].casefold() != command.casefold():
            return False
        return len(text) == len(command) or text[len(command)] == " "

    def _build_trigger_variants(self, prefix_arg: str, command: str) -> list[str]:
        variants = [f"{prefix_arg}{command}" if prefix_arg else command]
        if prefix_arg:
            variants.append(f"{prefix_arg} {command}")
        return list(dict.fromkeys(variants))

    def _match_command(self, body_without_region: str) -> _CommandMatch | None:
        for prefix_arg in self.prefix_args:
            for command in self.commands:
                for trigger in self._build_trigger_variants(prefix_arg, command):
                    if self._is_command_head(body_without_region, trigger):
                        args = body_without_region[len(trigger):].strip()
                        return _CommandMatch(prefix_arg=prefix_arg, matched_trigger=trigger, args=args)
        return None

    def parse_context(self, event: AstrMessageEvent) -> HandlerContext | None:
        super().parse_context(event)
        message = self._normalize_spaces(event.get_message_str())
        logger.debug(message)
        if not message.startswith("/"):
            return None
        
        body = message[1:].strip()
        if not body:
            return None

        regions = self._get_regions()
        if not regions:
            return None
        logger.debug(regions)
        region, rest = self._extract_region(body, regions)
        if not region:
            return None

        matched = self._match_command(rest)
        if not matched:
            return None

        ctx = HandlerContext(event)
        ctx.region = region
        ctx.prefix_arg = matched.prefix_arg
        ctx.arg_text = matched.args
        ctx.trigger_cmd = f"/{region}{matched.matched_trigger}"
        ctx.original_trigger_cmd = ctx.trigger_cmd
        return ctx

    def get_prefix_hint(self, event: AstrMessageEvent) -> str | None:
        message = self._normalize_spaces(event.get_message_str())
        if not message.startswith("/"):
            return None
        
        body = message[1:].strip()
        if not body:
            return None

        matched = self._match_command(body)
        if not matched:
            return None

        regions = self._get_regions()
        if not regions:
            return None
        example = f"/{regions[0]}{matched.matched_trigger}"
        return (
            f"必须显式指定区服前缀。示例 {example}\n"
            f"当前支持区服：{', '.join(regions)}"
        )
