import inspect
from typing import Callable

_initialize_hooks: list[tuple[int, Callable]] = []
_terminate_hooks: list[tuple[int, Callable]] = []


def _register(hooks: list[tuple[int, Callable]], func: Callable, order: int) -> Callable:
    # 防止模块被重复导入时重复注册
    if not any(registered is func for _, registered in hooks):
        hooks.append((order, func))
        hooks.sort(key=lambda item: item[0])
    return func


def on_initialize(order: int = 100):
    def decorator(func: Callable) -> Callable:
        return _register(_initialize_hooks, func, order)

    return decorator


def on_terminate(order: int = 100):
    def decorator(func: Callable) -> Callable:
        return _register(_terminate_hooks, func, order)

    return decorator


async def _call_hook(func: Callable) -> None:
    result = func()
    if inspect.isawaitable(result):
        await result


async def run_initialize_hooks() -> None:
    for _, hook in _initialize_hooks:
        await _call_hook(hook)


async def run_terminate_hooks() -> None:
    for _, hook in _terminate_hooks:
        await _call_hook(hook)
