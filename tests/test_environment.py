from duragen.activities import verify_environment
from duragen.settings import Settings


async def test_verify_environment() -> None:
    assert await verify_environment("tests") == "Duragen environment ready for tests"


def test_default_settings(monkeypatch) -> None:
    monkeypatch.delenv("TEMPORAL_ADDRESS", raising=False)
    monkeypatch.delenv("TEMPORAL_NAMESPACE", raising=False)
    monkeypatch.delenv("TEMPORAL_TASK_QUEUE", raising=False)

    assert Settings.from_environment() == Settings(
        temporal_address="localhost:7233",
        temporal_namespace="default",
        temporal_task_queue="duragen-investigations",
    )