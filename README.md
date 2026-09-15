# Duragen

Duragen is a reference implementation for crash-resilient, tool-using agent workflows built with Temporal. See the [project one-pager](docs/DurableAgent_Project_OnePager.md) and [failure-semantics ADR](docs/ADR-001-Durable-Workflow-Failure-Semantics.md) for scope and design decisions.

## Local Development

The local setup deliberately uses two boundaries:

- Temporal runs in Docker with its development SQLite database in a named volume.
- The Python worker and clients run in the local `.venv` for fast editing and debugging.

The development server is not a production deployment. Production Temporal requires an external persistence database, security, backups, and independently managed services.

### First-time setup

1. Start Docker Desktop.
2. Install and synchronize the Python environment:

	```bash
	uv sync --all-groups
	```

3. Start Temporal:

	```bash
	docker compose up -d
	```

4. Verify the service and open the Temporal UI at [http://localhost:8233](http://localhost:8233):

	```bash
	docker compose ps
	```

### Run the smoke workflow

Start the worker in one terminal:

```bash
uv run duragen-worker
```

Run the workflow from another terminal:

```bash
uv run duragen-smoke
```

Expected result:

```text
Duragen environment ready for local development
```

Stop the worker with `Ctrl+C`. Stop Temporal without deleting its state using:

```bash
docker compose down
```

To intentionally delete all local Temporal workflow state:

```bash
docker compose down --volumes
```

### Validate changes

```bash
uv run ruff check src tests
uv run pytest
docker compose config --quiet
```

See [Local Environment Setup](docs/LOCAL_SETUP.md) for the prerequisite inventory, current machine status, troubleshooting, and the container decision.
