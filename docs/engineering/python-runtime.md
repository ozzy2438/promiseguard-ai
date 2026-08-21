# Python 3.12 runtime baseline

PromiseGuard AI supports **Python 3.12 only** for local development, CI and Docker.

| Surface | Pin |
|---|---|
| Packaging | `requires-python = ">=3.12"` in `pyproject.toml` |
| Local toolchain | `.python-version` → `3.12` |
| Type checker | `python_version = "3.12"` |
| Linter | `target-version = "py312"` |
| CI | `actions/setup-python` `python-version: "3.12"` |
| API image | `FROM python:3.12-slim` |
| Console image | `FROM python:3.12-slim` |

Dependencies were not upgraded as part of this standardisation. Compatibility is the existing
3.12-tested set in `pyproject.toml`.

## Local setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
make install
make python-version
pytest -m "not live_openai"
```

`make` prefers `python3.12` when it is on `PATH`. A generic `python3` that is not 3.12 fails
`make python-version` rather than silently drifting to 3.13 or 3.14.

Historical milestone-2 evidence was produced on Python 3.13.5 in one local environment. That is
recorded as historical fact; it is not the supported baseline going forward.
