import asyncio

from temporalio.client import Client
from temporalio.worker import Worker

from duragen.activities import (
    export_report,
    generate_diagnosis,
    plan_remediation,
    retrieve_evidence,
    retry_pipeline,
    verify_environment,
)
from duragen.settings import Settings
from duragen.workflows import EnvironmentSmokeWorkflow, InvestigationWorkflow


async def run_worker() -> None:
    settings = Settings.from_environment()
    client = await Client.connect(
        settings.temporal_address,
        namespace=settings.temporal_namespace,
    )
    worker = Worker(
        client,
        task_queue=settings.temporal_task_queue,
        workflows=[EnvironmentSmokeWorkflow, InvestigationWorkflow],
        activities=[
            verify_environment,
            retrieve_evidence,
            generate_diagnosis,
            plan_remediation,
            retry_pipeline,
            export_report,
        ],
    )
    await worker.run()


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()