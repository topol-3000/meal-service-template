"""Errors the domain and application raise on purpose.

Feature errors subclass one of these (`class RecipeNotFoundError(NotFoundError)`);
`api/errors.py` maps each base class to an HTTP status. Adapters convert library
exceptions (httpx2, SQLAlchemy, LLM client) into these at the boundary.
"""


class DomainError(Exception):
    """Base class: a business rule was broken. Maps to 400."""


class NotFoundError(DomainError):
    """The requested entity does not exist. Maps to 404."""


class ConflictError(DomainError):
    """The operation clashes with the current state (duplicate, stale version). Maps to 409."""


class ValidationError(DomainError):
    """Input is well-formed but breaks a business rule. Maps to 422.

    Schema errors (missing field, wrong type) are caught earlier by the API's Pydantic models.
    """


class ExternalServiceError(DomainError):
    """A service we depend on (HTTP API, LLM, database) failed. Maps to 502."""
