import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    temporal_address: str
    temporal_namespace: str
    temporal_task_queue: str

    @classmethod
    def from_environment(cls) -> "Settings":
        return cls(
            temporal_address=os.getenv("TEMPORAL_ADDRESS", "localhost:7233"),
            temporal_namespace=os.getenv("TEMPORAL_NAMESPACE", "default"),
            temporal_task_queue=os.getenv(
                "TEMPORAL_TASK_QUEUE", "duragen-investigations"
            ),
        )