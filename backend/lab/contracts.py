from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Diagnosis(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cause: Literal[
        "db_latency", "worker_stopped", "dependency_config", "healthy", "unknown"
    ]
    explanation: str = Field(min_length=10, max_length=2500)
    evidence_ids: list[str] = Field(min_length=1, max_length=12)
    alternative: str = Field(min_length=5, max_length=1200)
    next_check: str = Field(min_length=5, max_length=1200)
