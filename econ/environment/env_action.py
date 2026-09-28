from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from econ.economic_platform.typing import ActionType


@dataclass
class ManualAction:
    """A scripted action injected by the researcher — no LLM involved.

    Use this to:
    - Seed initial goods inventory at the start of a run.
    - Inject supply/demand shocks mid-simulation.
    - Force a specific agent to take a particular action.

    Example::

        ManualAction(
            action_type=ActionType.PRODUCE,
            action_args={"good_name": "wheat", "quantity": 200, "unit_cost": 1.5},
        )
    """
    action_type: ActionType
    action_args: dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMAction:
    """Signal that the agent should decide its own action via LLM.

    Pass an ``LLMAction`` instance in the ``step()`` dict for any agent you
    want to act autonomously this step.
    """
    pass
