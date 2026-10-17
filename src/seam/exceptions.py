"""Failures raised at repository, runner, and model boundaries."""


class AgentError(RuntimeError):
    """Stop adaptation without exposing provider error bodies or credentials."""


class BudgetExceeded(AgentError):
    """Refuse a request that cannot fit within the remaining dollar budget."""


class RepositoryError(RuntimeError):
    """Describe an invalid repository operation without changing the caller's tree."""


class RunnerError(RuntimeError):
    """Explain an execution environment that could not be prepared."""
