from typing import Callable
from astrbot.api import logger
from datetime import datetime, timedelta
import random
import asyncio
async def start_repeat_with_interval(
    interval: int,
    func: Callable,
    name: str,
    every_output=False, 
    error_output=True, 
    error_limit=5, 
    start_offset=10
):
    """
    开始重复执行某个异步任务
    """
    try:
        await asyncio.sleep(start_offset)
        error_count = 0
        logger.info(f'开始循环执行 {name} 任务', flush=True)
        next_time = datetime.now() + timedelta(seconds=1)
        while True:
            now_time = datetime.now()
            if next_time > now_time:
                try:
                    await asyncio.sleep((next_time - now_time).total_seconds())
                except asyncio.exceptions.CancelledError:
                    return
                except Exception as e:
                    logger.error(f'循环执行 {name} sleep失败')
            next_time = next_time + timedelta(seconds=interval)
            try:
                if every_output:
                    logger.debug(f'开始执行 {name}')
                await func()
                if every_output:
                    logger.info(f'执行 {name} 成功')
                if error_output and error_count > 0:
                    logger.info(f'循环执行 {name} 从错误中恢复, 累计错误次数: {error_count}')
                error_count = 0
            except Exception as e:
                if error_output and error_count < error_limit - 1:
                    logger.warning(f'循环执行 {name} 失败: {e} (失败次数 {error_count + 1})')
                elif error_output and error_count == error_limit - 1:
                    logger.error(f'循环执行 {name} 失败 (达到错误次数输出上限)')
                error_count += 1

    except Exception as e:
        logger.error(f'循环执行 {name} 任务失败')

def repeat_with_interval(
    interval_secs: int, 
    name: str, 
    every_output=False, 
    error_output=True, 
    error_limit=5, 
    start_offset=None
):
    """
    重复执行某个任务的装饰器
    """
    if start_offset is None:
        start_offset = 5 + random.randint(0, 10)
    def wrapper(func):
        start_repeat_with_interval(interval_secs, func, name, every_output, error_output, error_limit, start_offset)
        return func
    return wrapper