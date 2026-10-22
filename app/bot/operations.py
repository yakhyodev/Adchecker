"""Own long operations per user; navigation waits for cancellation to finish."""

import asyncio

running: dict[tuple[int, int], asyncio.Task] = {}


async def cancel_operation(chat_id: int, user_id: int) -> None:
    owner = (chat_id, user_id)
    task = running.get(owner)
    if task and task is not asyncio.current_task():
        task.cancel()
        # Cleanup/rollback must complete before a new FSM conversation starts.
        await asyncio.gather(task, return_exceptions=True)


async def begin_operation(chat_id: int, user_id: int) -> asyncio.Task:
    await cancel_operation(chat_id, user_id)
    task = asyncio.current_task()
    running[(chat_id, user_id)] = task
    return task


def owns_operation(owner: tuple[int, int], task: asyncio.Task) -> bool:
    return running.get(owner) is task


def finish_operation(owner: tuple[int, int], task: asyncio.Task) -> bool:
    if not owns_operation(owner, task):
        return False
    running.pop(owner, None)
    return True
