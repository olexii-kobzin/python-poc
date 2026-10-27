import asyncio
from pathlib import Path

import pytest

from statement.infra.heartbeat import run_heartbeat, start_heartbeat, stop_heartbeat


async def wait_until(condition: object, timeout: float = 1) -> bool:
    async with asyncio.timeout(timeout):
        while not condition():  # type: ignore[operator]
            await asyncio.sleep(0.005)
    return True


@pytest.mark.anyio
async def test_touches_file_while_check_passes(tmp_path: Path) -> None:
    path = tmp_path / "alive"

    async def check() -> None:
        return None

    task = asyncio.create_task(run_heartbeat(path, check, interval=0.01))
    try:
        await wait_until(path.exists)
        first = path.stat().st_mtime_ns
        await wait_until(lambda: path.stat().st_mtime_ns > first)
    finally:
        await stop_heartbeat(task)


@pytest.mark.anyio
async def test_does_not_touch_file_when_check_fails(tmp_path: Path) -> None:
    path = tmp_path / "alive"
    calls = 0

    async def check() -> None:
        nonlocal calls
        calls += 1
        raise RuntimeError("amqp unavailable")

    task = asyncio.create_task(run_heartbeat(path, check, interval=0.01))
    try:
        await wait_until(lambda: calls >= 3)
    finally:
        await stop_heartbeat(task)

    assert not path.exists()


@pytest.mark.anyio
async def test_keeps_running_after_failed_check(tmp_path: Path) -> None:
    path = tmp_path / "alive"
    calls = 0

    async def check() -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("blip")

    task = asyncio.create_task(run_heartbeat(path, check, interval=0.01))
    try:
        await wait_until(path.exists)
    finally:
        await stop_heartbeat(task)

    assert calls >= 2


@pytest.mark.anyio
async def test_stop_heartbeat_ends_the_task(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_check(broker: object) -> None:
        return None

    monkeypatch.setattr("statement.infra.heartbeat.check_dependencies", fake_check)

    task = start_heartbeat(tmp_path / "alive", broker=object(), interval=0.01)  # type: ignore[arg-type]
    await stop_heartbeat(task)

    assert task.cancelled()
