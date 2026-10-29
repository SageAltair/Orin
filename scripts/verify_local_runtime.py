"""Read-only guard against serving Orin from a stale Docker Compose checkout.

This script never restarts containers, reads database rows, or prints secret values.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import ntpath
from pathlib import Path
import subprocess
import sys


def normalized(path: str) -> str:
    """Compare Windows bind paths case-insensitively, including on Linux CI."""
    return ntpath.normcase(ntpath.normpath(path.replace("/", "\\")))


def inspect_environment(entries: list[str]) -> dict[str, str]:
    return dict(item.split("=", 1) for item in entries if "=" in item)


def assess_runtime(root: str, compose: dict, containers: list[dict]) -> list[str]:
    """Return actionable errors without revealing credentials or their values."""
    errors: list[str] = []
    services = {}
    for item in containers:
        name = item["Name"].strip("/")
        labels = item.get("Config", {}).get("Labels") or {}
        service = labels.get("com.docker.compose.service")
        if service is None:
            service = next((candidate for candidate in ("web", "api")
                            if name.endswith(f"-{candidate}-1")), None)
        if service:
            services[service] = item
    expected = {
        "web": {"/app/apps/web": str(Path(root) / "apps" / "web"),
                "/app/packages": str(Path(root) / "packages")},
        "api": {"/app/src": str(Path(root) / "apps" / "api" / "src")},
    }
    for service, mounts in expected.items():
        container = services.get(service)
        if container is None:
            errors.append(f"{service}: container not found")
            continue
        actual = {m["Destination"]: m["Source"] for m in container.get("Mounts", [])
                  if m.get("Type") == "bind"}
        for target, source in mounts.items():
            if target not in actual:
                errors.append(f"{service}: expected bind mount {target} is missing")
            elif normalized(actual[target]) != normalized(source):
                errors.append(f"{service}: {target} is mounted from a noncanonical checkout: {actual[target]}")
        planned = compose["services"][service]
        live_env = inspect_environment(container.get("Config", {}).get("Env", []))
        for key, value in planned.get("environment", {}).items():
            if key not in live_env:
                errors.append(f"{service}: runtime environment is missing {key}")
            elif live_env[key] != str(value):
                errors.append(f"{service}: runtime environment differs for {key} (values hidden)")
        if service == "api":
            command = " ".join(container.get("Config", {}).get("Cmd") or []).lower()
            if "alembic" in command and "upgrade" in command:
                errors.append("api: startup command runs migrations; use the local-recovery override")
    return errors


def run(args: list[str], *, cwd: Path) -> str:
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=False)
    if result.returncode:
        raise RuntimeError(f"Command failed ({args[0]} {args[1]}), exit {result.returncode}; output suppressed")
    return result.stdout


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, help="Existing local env file; never copied or printed")
    parser.add_argument("--project", default="orin")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    compose_args = ["docker", "compose", "-p", args.project]
    if args.env_file:
        compose_args.extend(["--env-file", str(args.env_file.resolve())])
    compose_args.extend(["-f", str(root / "docker-compose.yml"),
                         "-f", str(root / "docker-compose.local-recovery.yml")])
    try:
        config = json.loads(run(compose_args + ["config", "--format", "json"], cwd=root))
        names = [f"{args.project}-web-1", f"{args.project}-api-1"]
        containers = json.loads(run(["docker", "inspect", *names], cwd=root))
        errors = assess_runtime(str(root), config, containers)
        installed_hash = run(["docker", "exec", names[0], "cat",
                              "/app/apps/web/node_modules/.orin-package-lock-hash"], cwd=root).strip()
        lock_hash = hashlib.sha256((root / "apps/web/package-lock.json").read_bytes()).hexdigest()
        if installed_hash != lock_hash:
            errors.append("web: installed node_modules do not match the canonical package-lock.json")
    except (OSError, RuntimeError, ValueError, KeyError) as exc:
        print(f"Runtime verification unavailable: {exc}", file=sys.stderr)
        return 2
    for error in errors:
        print(f"FAIL: {error}")
    if errors:
        print(f"{len(errors)} runtime drift finding(s). No services changed.")
        return 1
    print("PASS: web/API bind mounts, runtime environment, safe API command and web lock hash match.")
    print("Read-only check. No worker, database, or phone actions performed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
