from typing import Optional
from pydantic import BaseModel, Field


class Step(BaseModel):
    method: str                      # GET / POST
    path: str                        # may contain {var} placeholders, e.g. /payments/{p1}/refund
    body: Optional[dict] = None
    headers: dict = Field(default_factory=dict)
    save_as: Optional[str] = None    # save response["id"] under this variable name
    repeat: int = Field(default=1, ge=1, le=20)  # >1 => send that many requests CONCURRENTLY


class Scenario(BaseModel):
    name: str
    description: str = ""
    steps: list[Step] = Field(min_length=1, max_length=12)


class Violation(BaseModel):
    invariant: str
    detail: str
