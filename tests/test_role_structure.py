from __future__ import annotations

from pathlib import Path

import yaml


EXPECTED_TASK_ORDER = [
    "preflight_checks.yml",
    "set_variables.yml",
    "directories.yml",
    "passwords.yml",
    "docker_compose_networks.yml",
    "traefik.yml",
    "postgres.yml",
    "rabbitmq.yml",
    "bytes.yml",
    "boefje.yml",
    "crux.yml",
    "katalogus.yml",
    "normalizer.yml",
    "octopoes_api.yml",
    "octopoes_api_worker.yml",
    "mula.yml",
    "rocky.yml",
    "rocky_worker.yml",
]


def load_yaml(path: Path):
    return yaml.safe_load(path.read_text())


def iter_task_files(role_root: Path):
    yield role_root / "tasks" / "main.yml"
    yield from sorted((role_root / "tasks").glob("*.yml"))


def test_main_task_order_is_explicit_and_complete(role_root):
    tasks = load_yaml(role_root / "tasks" / "main.yml")
    includes = [task["ansible.builtin.include_tasks"] for task in tasks]

    assert includes == EXPECTED_TASK_ORDER


def test_included_task_files_exist(role_root):
    for task_name in EXPECTED_TASK_ORDER:
        assert (role_root / "tasks" / task_name).is_file()


def test_required_variables_are_empty_by_default(role_defaults):
    for variable_name in role_defaults["openkat_required_vars"]:
        assert role_defaults[variable_name] == ""


def test_required_variable_list_matches_expected_contract(role_defaults):
    assert role_defaults["openkat_required_vars"] == [
        "openkat_superuser_fullname",
        "openkat_superuser_email",
        "openkat_traefik_letsencrypt_admin_email",
    ]


def test_preflight_asserts_required_variables(role_root):
    tasks = load_yaml(role_root / "tasks" / "preflight_checks.yml")
    required_var_assert = tasks[-1]

    assert required_var_assert["name"] == "Check For Variables That Are Required But Do Not Have Defaults"
    assert required_var_assert["loop"] == "{{ openkat_required_vars }}"
    assert required_var_assert["ansible.builtin.assert"]["that"] == [
        "(lookup('vars', item, default='') | string | trim | length) > 0"
    ]
    assert "required but not defined" in required_var_assert["ansible.builtin.assert"]["fail_msg"]


def test_static_template_and_copy_sources_exist(role_root):
    for task_file in iter_task_files(role_root):
        tasks = load_yaml(task_file) or []
        for task in tasks:
            template_call = task.get("ansible.builtin.template")
            if template_call:
                src = template_call["src"]
                if "{{" not in src:
                    assert (role_root / "templates" / src).is_file()

            copy_call = task.get("ansible.builtin.copy")
            if copy_call:
                src = copy_call["src"]
                if "{{" not in src:
                    assert (role_root / "files" / src).is_file()