import asyncio
from uuid import uuid4

from temporalio.client import Client

from duragen.settings import Settings
from duragen.workflows import EnvironmentSmokeWorkflow


async def run_smoke_workflow() -> str:
    settings = Settings.from_environment()
    client = await Client.connect(
        settings.temporal_address,
        namespace=settings.temporal_namespace,
    )
    return await client.execute_workflow(
        EnvironmentSmokeWorkflow.run,
        "local development",
        id=f"environment-smoke/{uuid4()}",
        task_queue=settings.temporal_task_queue,
    )


def main() -> None:
    print(asyncio.run(run_smoke_workflow()))


if __name__ == "__main__":
    main()