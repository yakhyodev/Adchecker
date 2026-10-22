"""Concurrent navigation must wait for cleanup and leave only one operation."""

import asyncio

import pytest

from app.bot.operations import begin_operation, cancel_operation, finish_operation, running


@pytest.mark.asyncio
async def test_concurrent_replacements_do_not_double_cancel_old_cleanup():
    owner = (919, 919)
    ready, cleaning, release_cleanup = asyncio.Event(), asyncio.Event(), asyncio.Event()
    first_entered, second_entered = asyncio.Event(), asyncio.Event()

    async def original():
        task = await begin_operation(*owner)
        try:
            ready.set()
            await asyncio.Future()
        finally:
            cleaning.set()
            await release_cleanup.wait()
            finish_operation(owner, task)

    async def replacement(entered):
        task = await begin_operation(*owner)
        try:
            entered.set()
            await asyncio.Future()
        finally:
            finish_operation(owner, task)

    old = asyncio.create_task(original())
    first = second = None
    try:
        await asyncio.wait_for(ready.wait(), 2)
        first = asyncio.create_task(replacement(first_entered))
        await asyncio.wait_for(cleaning.wait(), 2)
        second = asyncio.create_task(replacement(second_entered))
        await asyncio.sleep(0)
        assert not first_entered.is_set() and not second_entered.is_set()
        release_cleanup.set()
        await asyncio.wait_for(second_entered.wait(), 2)
        assert old.done() and first.done()
        assert old.cancelling() == 1
        assert running[owner] is second
    finally:
        release_cleanup.set()
        await cancel_operation(*owner)
        for task in (old, first, second):
            if task is not None and not task.done():
                task.cancel()
        await asyncio.gather(*(task for task in (old, first, second) if task is not None), return_exceptions=True)
        assert owner not in running


@pytest.mark.asyncio
async def test_cancelling_a_waiting_navigation_does_not_cancel_cleanup_again():
    owner = (920, 920)
    ready, cleaning, release = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def operation():
        task = await begin_operation(*owner)
        try:
            ready.set()
            await asyncio.Future()
        finally:
            cleaning.set()
            await release.wait()
            finish_operation(owner, task)

    worker = asyncio.create_task(operation())
    waiter = None
    try:
        await asyncio.wait_for(ready.wait(), 2)
        waiter = asyncio.create_task(cancel_operation(*owner))
        await asyncio.wait_for(cleaning.wait(), 2)
        waiter.cancel()
        await asyncio.gather(waiter, return_exceptions=True)
        assert worker.cancelling() == 1 and not worker.done()
        release.set()
        await cancel_operation(*owner)
        assert worker.done() and owner not in running
    finally:
        release.set()
        if not worker.done():
            worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)
