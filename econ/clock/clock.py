from __future__ import annotations


class Clock:
    """Simulation time abstraction.

    Tracks discrete time steps. Each call to ``env.step()`` advances
    ``time_step`` by one.  The integer value is embedded in every DB record
    so all events have a consistent simulation timestamp.
    """

    def __init__(self) -> None:
        self.time_step: int = 0

    def tick(self) -> None:
        self.time_step += 1

    def now(self) -> int:
        return self.time_step
