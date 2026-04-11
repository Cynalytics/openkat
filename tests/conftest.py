from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined


@pytest.fixture(scope="session")
def role_root() -> Path:
    return Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def role_defaults(role_root: Path) -> dict:
    return yaml.safe_load((role_root / "defaults" / "main.yml").read_text())


@pytest.fixture(scope="session")
def render_context(role_defaults: dict) -> dict:
    context = dict(role_defaults)
    context.update(
        {
            "ansible_managed": "managed by pytest",
            "docker_binary": "/usr/bin/docker",
            "inventory_hostname": "openkat.example.test",
            "openkat_postgres_password": "postgres-password",
            "openkat_rocky_password": "rocky-password",
            "openkat_katalogus_password": "katalogus-password",
            "openkat_bytes_password": "bytes-password",
            "openkat_mula_password": "mula-password",
            "openkat_rabbitmq_password": "rabbitmq-password",
            "openkat_bytes_secret": "bytes-secret",
            "openkat_rocky_secret": "rocky-secret",
            "openkat_rocky_superuser_password": "superuser-password",
            "openkat_superuser_fullname": "OpenKAT Admin",
            "openkat_superuser_email": "admin@example.test",
            "openkat_traefik_letsencrypt_admin_email": "letsencrypt@example.test",
        }
    )
    return context


@pytest.fixture(scope="session")
def jinja_env(role_root: Path) -> Environment:
    return Environment(
        loader=FileSystemLoader(str(role_root / "templates")),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )