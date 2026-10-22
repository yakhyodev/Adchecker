"""Own long operations per user; navigation waits for cancellation to finish."""

import asyncio
from weakref import WeakValueDictionary

running: dict[tuple[int, int], asyncio.Task] = {}
_transition_locks: WeakValueDictionary[tuple[int, int], asyncio.Lock] = WeakValueDictionary()


def _owner_lock(owner):
    lock = _transition_locks.get(owner)
    if lock is None:
        lock = asyncio.Lock()
        _transition_locks[owner] = lock
    return lock


async def _cancel_running(owner):
    task = running.get(owner)
    if task and task is not asyncio.current_task():
        # A second navigation must not interrupt the old operation's cleanup.
        if not task.done() and not task.cancelling():
            task.cancel()
        await asyncio.shield(asyncio.gather(task, return_exceptions=True))
        if task.done() and running.get(owner) is task:
            running.pop(owner, None)


async def cancel_operation(chat_id: int, user_id: int) -> None:
    owner = (chat_id, user_id)
    async with _owner_lock(owner):
        # Cleanup/rollback must complete before a new FSM conversation starts.
        await _cancel_running(owner)


async def begin_operation(chat_id: int, user_id: int) -> asyncio.Task:
    owner = (chat_id, user_id)
    async with _owner_lock(owner):
        await _cancel_running(owner)
        task = asyncio.current_task()
        running[owner] = task
        return task


def owns_operation(owner: tuple[int, int], task: asyncio.Task) -> bool:
    return running.get(owner) is task


def finish_operation(owner: tuple[int, int], task: asyncio.Task) -> bool:
    if not owns_operation(owner, task):
        return False
    running.pop(owner, None)
    return True
