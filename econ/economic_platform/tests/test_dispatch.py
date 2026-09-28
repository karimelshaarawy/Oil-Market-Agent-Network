"""Tests pinning the Channel/ActionType reflection-dispatch contract.

``EconomicPlatform.running()`` resolves handlers with
``getattr(self, action.value)`` and inspects ``co_argcount`` — these tests
guarantee the contract survives any internal restructuring.
"""
from __future__ import annotations

import asyncio
import inspect

from econ.economic_platform.tests.helpers import make_platform
from econ.economic_platform.typing import ActionType


def test_every_action_type_has_a_conforming_handler():
    platform, _ = make_platform()
    for action in ActionType:
        if action == ActionType.EXIT:
            continue
        handler = getattr(platform, action.value, None)
        assert handler is not None, f"no handler for {action.value!r}"
        assert inspect.iscoroutinefunction(handler), f"{action.value!r} not async"
        argcount = handler.__code__.co_argcount
        assert argcount <= 3, f"{action.value!r} takes too many parameters"
        param_names = handler.__code__.co_varnames[:argcount]
        assert param_names[0] == "self"
        if argcount >= 2:
            assert param_names[1] == "agent_id"


async def test_channel_roundtrip_register_produce_list_bid_clear_check_exit():
    platform, _ = make_platform()
    channel = platform.channel
    task = asyncio.create_task(platform.running())

    async def call(agent_id, message, action: ActionType):
        mid = await channel.write_to_receive_queue((agent_id, message, action.value))
        response = await channel.read_from_send_queue(mid)
        assert response[0] == mid
        return response[2]

    reg = await call(1, ("seller", "firm", "energy", 1000.0, "NA", ["crude_oil"]),
                     ActionType.REGISTER)
    assert reg == {"success": True, "agent_id": 1}
    await call(2, ("buyer", "consumer", "households", 500.0, "NA", []),
               ActionType.REGISTER)

    produced = await call(1, ("crude_oil", 10, 5.0), ActionType.PRODUCE)
    assert produced["success"] is True

    listed = await call(1, (produced["good_id"], 10.0, 10), ActionType.LIST_GOOD)
    assert listed["success"] is True

    bid = await call(2, ("crude_oil", 10.0, 3), ActionType.PLACE_BID)
    assert bid["success"] is True
    assert bid["quantity_submitted"] == 3
    assert bid["escrow"] == 30.0

    # Clearing is driven by the env loop, not the channel — invoke it directly
    # (the running task is idle, waiting on the next channel message).
    await platform.clear_market()

    seller = await call(1, None, ActionType.CHECK_BALANCE)
    assert seller["balance"] == 980.0  # 1000 - 50 production + 30 cleared sale
    buyer = await call(2, None, ActionType.CHECK_BALANCE)
    assert buyer["balance"] == 470.0   # 500 - 30 (escrow == clearing cost)

    await channel.write_to_receive_queue((0, None, ActionType.EXIT.value))
    await asyncio.wait_for(task, timeout=5.0)
