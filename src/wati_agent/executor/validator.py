"""Pre-execution validation for action steps."""

from __future__ import annotations

from dataclasses import dataclass

from wati_agent.agent.tools import WATI_TOOLS
from wati_agent.executor.plan import ActionStep


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str]


# Build required params map from tool definitions
_REQUIRED_PARAMS: dict[str, list[str]] = {}
for tool in WATI_TOOLS:
    fn = tool["function"]
    _REQUIRED_PARAMS[fn["name"]] = fn["parameters"].get("required", [])


def validate_step(step: ActionStep) -> ValidationResult:
    """Validate that a step has all required parameters."""
    errors: list[str] = []

    required = _REQUIRED_PARAMS.get(step.tool_name)
    if required is None:
        errors.append(f"Unknown tool: {step.tool_name}")
        return ValidationResult(valid=False, errors=errors)

    for param in required:
        if param not in step.params or step.params[param] is None:
            errors.append(f"Missing required parameter: {param}")

    return ValidationResult(valid=len(errors) == 0, errors=errors)


def validate_steps(steps: list[ActionStep]) -> ValidationResult:
    """Validate all steps in a plan."""
    all_errors: list[str] = []
    for i, step in enumerate(steps):
        result = validate_step(step)
        if not result.valid:
            for err in result.errors:
                all_errors.append(f"Step {i + 1} ({step.tool_name}): {err}")
    return ValidationResult(valid=len(all_errors) == 0, errors=all_errors)
