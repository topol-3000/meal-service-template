from pydantic import BaseModel, ConfigDict


class ApiModel(BaseModel):
    """Base for every request and response schema.

    Unknown fields are rejected instead of silently dropped, and instances are immutable.
    Keep separate request and response models; map to and from domain objects with
    `to_domain()` / `from_domain()` on the schema.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
