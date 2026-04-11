from __future__ import annotations

from pathlib import Path

import pytest
import yaml


def template_id(template_path: Path, role_root: Path) -> str:
    return str(template_path.relative_to(role_root / "templates"))


def collect_templates(role_root: Path):
    return sorted((role_root / "templates").rglob("*.j2"))


@pytest.mark.parametrize(
    "template_path",
    collect_templates(Path(__file__).resolve().parents[1]),
    ids=lambda path: template_id(path, Path(__file__).resolve().parents[1]),
)
def test_templates_render_with_reference_context(template_path, role_root, jinja_env, render_context):
    rendered = jinja_env.get_template(
        str(template_path.relative_to(role_root / "templates"))
    ).render(render_context)

    assert rendered.strip()

    template_name = template_path.name
    if template_name.endswith("docker-compose.yml.j2") or template_name == "traefik_dynamic.yml.j2":
        parsed = yaml.safe_load(rendered)
        assert isinstance(parsed, dict)

    if template_name.endswith(".service.j2"):
        assert "[Unit]" in rendered
        assert "[Service]" in rendered
        assert "[Install]" in rendered


def test_rocky_compose_contains_expected_runtime_settings(jinja_env, render_context):
    rendered = jinja_env.get_template("rocky_docker-compose.yml.j2").render(render_context)

    assert "DJANGO_SUPERUSER_EMAIL=admin@example.test" in rendered
    assert "SECRET_KEY=rocky-secret" in rendered
    assert "Host(`openkat.example.test`)" in rendered


def test_postgres_service_unit_uses_role_paths(jinja_env, render_context):
    rendered = jinja_env.get_template("postgres.service.j2").render(render_context)

    assert "WorkingDirectory=/srv/postgres" in rendered
    assert "ExecStartPre=/usr/bin/docker compose  -f /srv/postgres/docker-compose.yml pull" in rendered
    assert "Requires=docker-compose-networks.service" in rendered