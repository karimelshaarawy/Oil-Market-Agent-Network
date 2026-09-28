from __future__ import annotations

import asyncio
import uuid


class AsyncSafeDict:

    def __init__(self) -> None:
        self.dict: dict = {}
        self.lock = asyncio.Lock()

    async def put(self, key: str, value) -> None:
        async with self.lock:
            self.dict[key] = value

    async def get(self, key: str, default=None):
        async with self.lock:
            return self.dict.get(key, default)

    async def pop(self, key: str, default=None):
        async with self.lock:
            return self.dict.pop(key, default)

    async def keys(self) -> list[str]:
        async with self.lock:
            return list(self.dict.keys())


class Channel:
    """Async message bus that decouples agents from EconomicPlatform.

    Agents write action requests to ``receive_queue``.
    EconomicPlatform reads from ``receive_queue``, processes the action, and
    writes the result to ``send_dict`` keyed by the original message UUID.
    Agents poll ``send_dict`` until their result is ready.
    """

    def __init__(self) -> None:
        self.receive_queue: asyncio.Queue = asyncio.Queue()
        self.send_dict: AsyncSafeDict = AsyncSafeDict()

    async def receive_from(self):
        return await self.receive_queue.get()

    async def send_to(self, message) -> None:
        message_id = message[0]
        await self.send_dict.put(message_id, message)

    async def write_to_receive_queue(self, action_info) -> str:
        message_id = str(uuid.uuid4())
        await self.receive_queue.put((message_id, action_info))
        return message_id

    async def read_from_send_queue(self, message_id: str):
        while True:
            if message_id in await self.send_dict.keys():
                message = await self.send_dict.pop(message_id, None)
                if message:
                    return message
            await asyncio.sleep(0.1)
