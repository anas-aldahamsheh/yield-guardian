"""What every agent tool is: a name, a validated argument model and one read call.

The science tools (:mod:`yield_guardian.agent.tools`) and the run tools
(:mod:`yield_guardian.agent.run_tools`) are both built from :class:`Tool`.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, cast

from pydantic import BaseModel, ConfigDict

from yield_guardian.contracts.investigation import ToolName
from yield_guardian.contracts.services import ScienceServices
from yield_guardian.llm.messages import FunctionSpec, ToolSpec


class ToolArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


@dataclass(frozen=True, slots=True)
class Tool[A: ToolArgs, R: BaseModel]:
    name: ToolName
    description: str
    args: type[A]
    call: Callable[[ScienceServices, A], Awaitable[R]]
    title: Callable[[A], str]
    summary: Callable[[A, R], str]
    hidden: tuple[str, ...] = ()
    """JSON Pointer patterns left out of the model's view (``*`` matches any key or index)."""
    caps: tuple[tuple[str, int], ...] = ()
    """Lists the model's view cuts to their first items: (JSON Pointer pattern, how many)."""

    def spec(self) -> ToolSpec:
        return ToolSpec(
            function=FunctionSpec(
                name=self.name, description=self.description, parameters=argument_schema(self.args)
            )
        )


def _clean_schema(node: Any) -> Any:
    if isinstance(node, dict):
        return {k: _clean_schema(v) for k, v in node.items() if k != "title"}
    if isinstance(node, list):
        return [_clean_schema(v) for v in node]
    return node


def argument_schema(args: type[ToolArgs]) -> dict[str, Any]:
    schema = _clean_schema(args.model_json_schema())
    schema.pop("$defs", None)
    schema["additionalProperties"] = False
    return cast(dict[str, Any], schema)
