from typing import Callable
from astrbot.api import logger
from datetime import datetime, timedelta
import random
import asyncio, inspect
from .lifecycle import on_initialize, on_terminate

_pending_startup_tasks: list = []
_running_tasks: list[asyncio.Task] = []
async def call_common_or_async(func: Callable, *args, **kwargs):
    """
    调用一个可能是异步的函数
    """
    if inspect.iscoroutinefunction(func):
        return await func(*args, **kwargs)
    else:
        return func(*args, **kwargs)
    
def start_repeat_with_interval(
    interval: int,
    func: Callable,
    name: str,
    every_output=False, 
    error_output=True, 
    error_limit=5, 
    delay=2
):
    """
    开始重复执行某个异步任务
    """
    async def task():
        await asyncio.sleep(delay)
        try:
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
                        logger.error(f'循环执行 {name} sleep失败',exc_info=True)
                next_time = next_time + timedelta(seconds=interval)
                try:
                    if every_output:
                        logger.debug(f'开始执行 {name}')
                    await call_common_or_async(func)
                    if every_output:
                        logger.info(f'执行 {name} 成功')
                    if error_output and error_count > 0:
                        logger.info(f'循环执行 {name} 从错误中恢复, 累计错误次数: {error_count}')
                    error_count = 0
                except asyncio.CancelledError:
                    # 关键：捕获取消异常，这是 asyncio 停止任务的正常流程
                    logger.info(f"循环任务 {name} 已停止。")
                    raise # 向上抛出以完成协程的取消
                except Exception as e:
                    if error_output and error_count < error_limit - 1:
                        logger.warning(f'循环执行 {name} 失败: {e} (失败次数 {error_count + 1})')
                    elif error_output and error_count == error_limit - 1:
                        logger.error(f'循环执行 {name} 失败 (达到错误次数输出上限)', exc_info=True)
                    error_count += 1

        except Exception as e:
            logger.error(f'循环执行 {name} 任务失败', exc_info=True)
    _pending_startup_tasks.append(task)

def repeat_with_interval(
    interval_secs: int, 
    name: str, 
    every_output=False, 
    error_output=True, 
    error_limit=5, 
    delay=2
):
    """
    重复执行某个任务的装饰器
    """
    def wrapper(func):
        start_repeat_with_interval(interval_secs, func, name, every_output, error_output, error_limit, delay)
        return func
    return wrapper

@on_initialize(order=100)
async def initialize_task():
    for task in _pending_startup_tasks:
        _running_tasks.append(asyncio.create_task(task()))
    _pending_startup_tasks.clear()

@on_terminate(order=100)
async def terminate_task():
    for task in _running_tasks:
        if task and not task.done():
            task.cancel()
    if _running_tasks:
        # 等待所有任务完成取消流程
        await asyncio.gather(*_running_tasks, return_exceptions=True)
        _running_tasks.clear()
        logger.info("已停止所有后台定时任务")
