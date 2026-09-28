from __future__ import annotations

import asyncio
import logging
import os
from typing import TYPE_CHECKING, Any, Callable, List, Optional, Union

from camel.agents import ChatAgent
from camel.messages import BaseMessage
from camel.models import BaseModelBackend, ModelManager
from camel.toolkits import FunctionTool
from camel.types import OpenAIBackendRole

# CAMEL ``ChatAgent`` memory / context budget (ScoreBasedContextCreator).
# Keep this separate from API ``max_tokens`` (completion cap) in ``ChatGPTConfig``.
from econ.core.config import DEFAULT_TOKEN_LIMIT
from econ.economic_agent.agent_action import EconomicAction
from econ.economic_agent.agent_environment import EconomicEnvironment
from econ.economic_agent.config.agent_info import AgentInfo
from econ.economic_platform.channel import Channel
from econ.economic_platform.typing import ActionType

if TYPE_CHECKING:
    from econ.economic_agent.agent_graph import AgentGraph

logger = logging.getLogger("econ.agent")

ALL_ECONOMIC_ACTIONS = [action.value for action in ActionType]
INTERVIEW_TIMEOUT_SECONDS = float(os.getenv("ECON_INTERVIEW_TIMEOUT_SECONDS", "60"))


class EconomicAgent(ChatAgent):
    """An autonomous LLM-powered economic agent:

    - Extends CAMEL's ``ChatAgent`` so the LLM drives behaviour.
    - Holds an ``EconomicEnvironment`` to build observations.
    - Holds an ``EconomicAction`` whose methods become OpenAI function tools.
    - ``perform_action_by_llm()`` observes → LLM decides → tool call executes.

    Args:
        agent_id:          Unique integer.
        agent_info:        ``AgentInfo`` profile (generates system prompt).
        channel:           Shared ``Channel`` connecting to ``EconomicPlatform``.
        model:             CAMEL model backend(s).
        agent_graph:       Reference to the full ``AgentGraph`` (for graph ops).
        available_actions:      Restrict which ``ActionType`` values the LLM can use.
        tools:                  Extra CAMEL tools beyond the economic action set.
        max_iteration:          LLM call budget per step (default 1).
        max_listings_per_good:  Max listings shown per good type in the market
                                observation.  Set to 0 to disable the cap.
                                (default 5).
        token_limit:            Max context tokens for CAMEL memory (``ChatAgent``).
                                Defaults to ``DEFAULT_TOKEN_LIMIT``; override to
                                cap truncation independently of API ``max_tokens``.
    """

    def __init__(
        self,
        agent_id: int,
        agent_info: AgentInfo,
        channel: Channel | None = None,
        model: Optional[Union[BaseModelBackend,
                               List[BaseModelBackend],
                               ModelManager]] = None,
        agent_graph: "AgentGraph | None" = None,
        available_actions: list[ActionType] | None = None,
        tools: Optional[List[Union[FunctionTool, Callable]]] = None,
        max_iteration: int = 1,
        max_listings_per_good: int = 5,
        token_limit: int | None = None,
    ) -> None:
        self.economic_agent_id = agent_id
        self.agent_info = agent_info
        self.channel = channel or Channel()
        self.agent_graph = agent_graph
        self.env = EconomicEnvironment(
            EconomicAction(agent_id, self.channel),
            agent_id=agent_id,
            agent_graph=agent_graph,
            max_listings_per_good=max_listings_per_good,
        )
        self.env.agent_info = agent_info

        system_message = BaseMessage.make_assistant_message(
            role_name="system",
            content=agent_info.to_system_message(),
        )

        all_action_tools = self.env.action.get_openai_function_list()
        if available_actions:
            allowed_names = {
                a.value if isinstance(a, ActionType) else a
                for a in available_actions
            }
            self.action_tools = [
                t for t in all_action_tools if t.func.__name__ in allowed_names
            ]
        else:
            self.action_tools = all_action_tools

        combined_tools = (tools or []) + (self.action_tools or [])
        super().__init__(
            system_message=system_message,
            model=model,
            scheduling_strategy="random_model",
            tools=combined_tools,
            token_limit=token_limit if token_limit is not None else DEFAULT_TOKEN_LIMIT,
        )
        # Must be set AFTER super().__init__() because CAMEL's ChatAgent also
        # owns a max_iteration attribute and its __init__ would overwrite ours
        # if we assigned it earlier.
        self.max_iteration = max_iteration if max_iteration is not None else 1

    # ── LLM-driven action ────────────────────────────────────────────────

    @staticmethod
    def _is_rate_limit(exc: Exception) -> bool:
        msg = str(exc).lower()
        return (
            "429" in msg
            or "rate limit" in msg
            or "too many requests" in msg
            or type(exc).__name__ in ("RateLimitError", "HTTPStatusError")
        )

    async def perform_action_by_llm(
        self,
        max_retries: int = 8,
        base_delay: float = 5.0,
    ):
        """Observe the environment → ask LLM → execute up to ``max_iteration``
        sequential tool calls within one simulation step.

        Each iteration the LLM sees the results of the previous tool call and
        can choose a dependent follow-up action (e.g. refine owned crude →
        list_good, or check_balance → place_bid).  The loop breaks early when
        the LLM returns no tool calls, meaning it has finished acting this step.

        With ``max_iteration=1`` (default) the behaviour is identical to the
        original single-call implementation.

        Retries up to ``max_retries`` times with exponential async backoff when
        the inference server returns a 429 rate-limit error.  Each wait uses
        ``asyncio.sleep`` so the event loop (and the platform) remain alive.
        """
        env_prompt = await self.env.to_text_prompt()
        # First message includes the full environment observation.
        user_msg = BaseMessage.make_user_message(
            role_name="User",
            content=(
                "Observe the current economic environment below and choose "
                "your next action using the available tools. Consider your "
                "balance, the market state, and your strategic objectives.\n\n"
                f"{env_prompt}"
            ),
        )
        logger.info(
            "Agent %d observing environment (max_iteration=%d) …",
            self.economic_agent_id,
            self.max_iteration,
        )

        response = None
        for iteration in range(self.max_iteration):
            for attempt in range(max_retries):
                try:
                    response = await self.astep(user_msg)
                    tool_calls = response.info.get("tool_calls", [])
                    for tool_call in tool_calls:
                        logger.info(
                            "Agent %d [iter %d/%d] → %s(%s)",
                            self.economic_agent_id,
                            iteration + 1,
                            self.max_iteration,
                            tool_call.tool_name,
                            tool_call.args,
                        )
                    # No tool calls means the LLM is done — stop early.
                    if not tool_calls:
                        logger.info(
                            "Agent %d finished early at iteration %d/%d "
                            "(no tool calls).",
                            self.economic_agent_id,
                            iteration + 1,
                            self.max_iteration,
                        )
                        return response
                    break  # successful astep — exit retry loop

                except Exception as exc:
                    if self._is_rate_limit(exc) and attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)
                        logger.warning(
                            "Agent %d: rate-limited (iter %d, attempt %d/%d). "
                            "Waiting %.0fs before retry …",
                            self.economic_agent_id,
                            iteration + 1,
                            attempt + 1,
                            max_retries,
                            delay,
                        )
                        await asyncio.sleep(delay)
                        self.memory.clear()
                    else:
                        logger.error(
                            "Agent %d error at iter %d: %s",
                            self.economic_agent_id, iteration + 1, exc,
                        )
                        return exc
            else:
                # All retries exhausted for this iteration.
                logger.error(
                    "Agent %d: exhausted %d retries at iteration %d.",
                    self.economic_agent_id, max_retries, iteration + 1,
                )
                return response

            # Subsequent iterations: ask the LLM to continue based on results.
            user_msg = BaseMessage.make_user_message(
                role_name="User",
                content=(
                    "Tool call(s) executed successfully. "
                    "If you have further dependent actions to take this step "
                    "(e.g. refine after buying crude, or list after refining), "
                    "call the next tool now. Otherwise do nothing."
                ),
            )

        return response

    async def _respond_from_memory(
        self,
        user_content: str,
        *,
        timeout: float | None = None,
        memory_note: Callable[[str], str] | None = None,
    ) -> str:
        """Answer from accumulated memory with tool schemas disabled.

        Shared by step reflection and post-simulation interviews — both ask
        the model to respond from what the agent has experienced without
        letting it take further market actions. ``memory_note`` formats how
        the answer is written back into the agent's memory (None to skip).
        """
        openai_messages, num_tokens = self.memory.get_context()
        openai_messages = list(openai_messages) + [
            {"role": "user", "content": user_content}
        ]
        coro = self._aget_model_response(
            openai_messages=openai_messages,
            num_tokens=num_tokens,
            tool_schemas=[],
        )
        response = await (
            asyncio.wait_for(coro, timeout=timeout) if timeout is not None else coro
        )
        content = (
            response.output_messages[0].content
            if response and response.output_messages
            else ""
        )
        if content and memory_note is not None:
            self.update_memory(
                message=BaseMessage.make_user_message(
                    role_name=OpenAIBackendRole.SYSTEM,
                    content=memory_note(content),
                ),
                role=OpenAIBackendRole.SYSTEM,
            )
        return content

    async def perform_step_reflection(self, step: int) -> str:
        """Generate an LLM-authored reflection about this agent's latest step.

        This intentionally bypasses tool schemas so the agent cannot take extra
        market actions during reflection.  The resulting text is stored in RAG
        memory and also appended to this agent's local memory.
        """
        reflection_prompt = (
            f"Reflect on simulation step {step} from your own perspective. "
            "Do not call tools. Write 3-5 concise sentences covering: "
            "what you remember from recent market events or retrieved memory, "
            "which actions you took this step, why you chose them, what outcome "
            "you observed, and what you plan to do next."
        )

        try:
            return await self._respond_from_memory(
                reflection_prompt,
                timeout=INTERVIEW_TIMEOUT_SECONDS,
                memory_note=lambda content: f"Step {step} self-reflection: {content}",
            )
        except Exception as exc:
            logger.warning(
                "Agent %d reflection failed at step %d: %s",
                self.economic_agent_id,
                step,
                exc,
            )
            return ""

    # ── Scripted action ──────────────────────────────────────────────────

    async def perform_action_by_data(self, func_name, *args, **kwargs) -> Any:
        """Execute a specific action by name (used by ``ManualAction``)."""
        func_name = func_name.value if isinstance(func_name, ActionType) else func_name
        for tool in self.env.action.get_openai_function_list():
            if tool.func.__name__ == func_name:
                result = await tool.func(*args, **kwargs)
                self.update_memory(
                    message=BaseMessage.make_user_message(
                        role_name=OpenAIBackendRole.SYSTEM,
                        content=(
                            f"Agent {self.economic_agent_id} performed "
                            f"{func_name}({args}, {kwargs}) → {result}"
                        ),
                    ),
                    role=OpenAIBackendRole.SYSTEM,
                )
                logger.info("Agent %d manual action %s → %s",
                            self.economic_agent_id, func_name, result)
                return result
        raise ValueError(f"Action {func_name!r} not found in tool list.")

    # ── Interview ────────────────────────────────────────────────────────

    async def perform_interview(self, prompt: str) -> dict:
        """Ask the agent a question.

        The LLM responds from its accumulated memory (what it has experienced
        in the simulation so far).  The interview prompt is appended to memory
        so the agent can reference it in future steps.
        """
        try:
            content = await self._respond_from_memory(
                (
                    "You are being interviewed after the simulation. "
                    "Answer as yourself, using your own memory, actions, "
                    "reasoning, and reflections. Do not call tools.\n\n"
                    f"Question: {prompt}"
                ),
                memory_note=lambda content: f"Interview question: {prompt}\nAnswer: {content}",
            )
            result = await self.env.action.interview(prompt, content)
            return {
                "agent_id": self.economic_agent_id,
                "prompt": prompt,
                "content": content,
                "success": result.get("success", False),
            }
        except Exception as exc:
            logger.warning(
                "Agent %d interview failed: %s",
                self.economic_agent_id,
                exc,
            )
            return {
                "agent_id": self.economic_agent_id,
                "prompt": prompt,
                "content": f"Interview failed: {exc}",
                "success": False,
            }

    def __str__(self) -> str:
        return (
            f"EconomicAgent(id={self.economic_agent_id}, "
            f"type={self.agent_info.agent_type}, "
            f"sector={self.agent_info.sector})"
        )
