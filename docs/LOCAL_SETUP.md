# Local Environment Setup

Status verified on September 14, 2026, on this macOS x86_64 workstation.

## Action Checklist

| Action or dependency | Required now | Local status | Action taken or remaining |
|---|---:|---|---|
| Git | Yes | Available: 2.39.5 | None |
| Python 3.13 | Yes | Available: 3.13.5 through `uv` | Selected with `.python-version` |
| Project virtual environment | Yes | Ready | Created at `.venv` by `uv sync` |
| Python dependencies | Yes | Ready | Locked in `uv.lock` and installed |
| `uv` package manager | Yes | Available: 0.12.9 | None |
| Docker CLI/Desktop | Yes | Ready: Desktop 4.91.0, Engine 29.8.0 | Intel/x86_64 installation verified |
| Docker daemon | Yes | Ready | Running through the `desktop-linux` context |
| Docker Compose | Yes | Ready: 5.5.1 | Compose configuration validated |
| Ports 7233 and 8233 | Yes | Ready | Temporal gRPC and UI are reachable |
| Temporal Service | Yes | Ready | `default` namespace is registered |
| Temporal CLI on the host | No | Not installed | Supplied by the pinned Temporal container |
| Homebrew | No | Not installed | Not needed because `uv` and Docker are available |
| Foundry credentials | No, later task | Not configured by this scaffold | Add when implementing LLM activities |
| Langfuse credentials | No, later task | Not configured by this scaffold | Add when implementing observability |
| SQLite idempotency store | No, later task | Not implemented by this scaffold | Add with protected side effects |

The project currently resolves Temporal SDK 1.32.0, Pydantic 2.13.5, pytest 9.1.1, pytest-asyncio 1.4.0, and Ruff 0.16.7. `uv.lock` is the authoritative dependency resolution.

## Container Decision

Use a container for Temporal, but not for the Python development loop yet.

This split gives the infrastructure a reproducible lifecycle and persistent isolated state while keeping breakpoints, tests, dependency inspection, and code reloads direct in VS Code. A worker container becomes useful when packaging the demo or validating deployment parity; it adds little value during the first implementation tasks.

The Compose service uses `temporalio/temporal:1.8.3`, exposes gRPC on port 7233 and the UI on port 8233, and persists the development SQLite database in the `temporal-data` volume. This is intentionally lighter than running PostgreSQL and Elasticsearch locally.

The local development container runs as root so the Temporal CLI image can initialize its SQLite database in the Docker-managed volume. This exception is limited to the disposable local infrastructure service and is not an appropriate production security configuration.

Do not use this development server design for production. It skips production security checks and does not provide the operational topology, external persistence, backup, or disaster-recovery configuration required for a production Temporal deployment.

## Setup

From the repository root:

```bash
uv sync --all-groups
docker compose up -d
docker compose ps
```

Run `uv run duragen-worker` in one terminal and `uv run duragen-smoke` in another. The Temporal UI is available at [http://localhost:8233](http://localhost:8233).

The verified smoke result is `Duragen environment ready for local development`. Temporal recorded the execution as `COMPLETED`, and the local test and lint checks pass.

Environment variables are optional for the defaults. Copy values from `.env.example` into your shell or secret manager only when overriding the local Temporal address, namespace, or task queue. The application does not automatically load `.env` files.

## Troubleshooting

If `docker compose up` reports that it cannot connect to the daemon, start Docker Desktop and retry. If port 7233 or 8233 is occupied, stop the conflicting service or change both the host port in `compose.yaml` and `TEMPORAL_ADDRESS` where applicable.

Inspect services and logs with:

```bash
docker compose ps
docker compose logs temporal
```

Preserve workflow history when stopping:

```bash
docker compose down
```

Delete the local Temporal database only when a clean reset is intentional:

```bash
docker compose down --volumes
```