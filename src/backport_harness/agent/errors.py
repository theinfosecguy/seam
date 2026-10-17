"""Failures that stop adaptation without exposing provider responses."""


class AgentError(RuntimeError):
    """Stop adaptation without exposing provider error bodies or credentials."""


class BudgetExceeded(AgentError):
    """Refuse a request that cannot fit within the remaining dollar budget."""
