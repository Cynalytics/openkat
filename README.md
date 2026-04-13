# OpenKAT Role

[![CI](https://github.com/Cynalytics/openkat/actions/workflows/ci.yml/badge.svg)](https://github.com/Cynalytics/openkat/actions/workflows/ci.yml)

This Ansible role deploys [OpenKAT](https://openkat.nl), the opensource security scanner, as a set of Docker Compose projects, each managed by its own systemd unit.


## Overview

This role installs a production-grade setup of Openkat:
- all Openkat services run in their own Docker-Compose stack
- all Docker-compose stacks are controlled by their own systemd service
- dependecies are handles in systemd
- all backend services run in a local docker network
- all external exposed services use Traefik as a front proxy
- certificates are handled by Lets Encrypt

The role has been tested on Ubuntu 22.04 LTS.

## Example galaxy requirements

```yaml
---
roles:
  - name: geerlingguy.docker
  - name: cynalytics.openkat
    version: "1.21"
```

## Example playbook

```yaml
- hosts: all
  vars:
    openkat_superuser_fullname: John Doe
    openkat_superuser_email: john.doe@example.com
    openkat_traefik_letsencrypt_admin_email: certmaster@example.com
  roles:
    - geerlingguy.docker
    - cynalytics.openkat
```


## Versioning

This role uses the same version as the Openkat project, with a postfix indicating the role version: version 1.21.0-1 will install Openkat 1.21.0

## Traefik Proxying

Traefik is deployed as a dedicated Compose stack at:

- `/srv/traefik/docker-compose.yml` (or `${openkat_service_root}/traefik/docker-compose.yml`)
- systemd unit: `traefik.service`

How proxying works:

1. Traefik is started with Docker provider enabled (`--providers.docker=true`) and `--providers.docker.exposedbydefault=false`.
2. OpenKAT services that should be reachable externally add explicit Traefik labels in their Compose templates.
3. The Rocky web service defines a router rule:
   - `Host(`{{ inventory_hostname }}`)`
   - entrypoint `websecure`
   - Let's Encrypt resolver `letsencrypt`
4. HTTP (`:80`) is redirected to HTTPS (`:443`).
5. Dynamic middleware config is generated in `dynamic.yml` and currently includes:
   - `security-headers`
   - `rate-limit`
6. Traefik and services communicate over Docker networks, especially `openkatinternalnetwork`.

TLS certificates are managed by Traefik ACME and stored in:

- `${openkat_service_root}/traefik/letsencrypt/acme.json`

## General OpenKAT Setup

Role task flow (high level):

1. Preflight checks:
   - Docker must exist
   - `docker compose` must exist
   - required variables must be set
2. Runtime variable setup:
   - detects Docker binary path and stores it in `docker_binary`
3. Directory and secret preparation
4. Network bootstrap (`docker-compose-networks.service`)
5. Service deployment in dependency order:
   - `traefik`
   - `postgres`
   - `rabbitmq`
   - application services (`bytes`, `boefje`, `crux`, `katalogus`, `normalizer`, `octopoes_api`, `octopoes_api_worker`, `mula`, `rocky`, `rocky_worker`)

### systemd + Docker Compose model

Each component gets:

- a Compose file at `${openkat_service_root}/<service>/docker-compose.yml`
- a systemd unit at `/etc/systemd/system/openkat_<service>.service` (Traefik is `traefik.service`)

Typical unit behavior:

- `ExecStartPre`: `docker compose ... pull`
- `ExecStart`: `docker compose ... up`
- `ExecStop`: `docker compose ... stop`
- `Restart=always`
- explicit `Requires=` dependencies between units to enforce startup order

Most service tasks:

- template the Compose file
- template the systemd unit
- enable and start the unit
- wait until `ActiveState == active`

## Role variables

### Core image and install path

| variable | default | description |
|----------|---------|-------------|
| `openkat_superuser_fullname` | empty | REQUIRED full name for generated Superuser for Openkat application |
| `openkat_superuser_email` | empty | REQUIRED email address for superuser |
| `openkat_traefik_letsencrypt_admin_email` | empty | REQUIRED email address for Lets Encrypt ceritificates |
| `openkat_version` |  `v1.21.0` | OpenKAT version to install or upgrade to |
| `openkat_docker_repository`| `docker.underdark.nl/librekat` |  Docker registry/repository prefix |
| `openkat_crux_version`| `v1.1.0` | Version for Crux component |
| `openkat_service_root`| `/opt/openkat` |  root path for service Compose directories  |
| `openkat_data_directory` | `/data/openkat` | persistent data root directory |
| `openkat_backupninja_enabled`| `true` | enables BackupNinja setup for PostgreSQL |
| `openkat_boefje_version` | `openkat_version` | specific version for boefje service |
| `openkat_bytes_version` | `openkat_version` | specific version for bytes service |
| `openkat_katalogus_version` | `openkat_version` | specific version for katalogus service |
| `openkat_mula_version` | `openkat_version` | specific version for mula service |
| `openkat_normalizer_version` | `openkat_version` | specific version for normalizer service |
| `openkat_octopoes_api_version` | `openkat_version` | specific version for octpous_api service |
| `openkat_octopoes_api_worker_version` | `openkat_version` | specific version for octopus_api_worker service |
| `openkat_rocky_version` | `openkat_version` | specific version for rocky service |
| `openkat_rocky_worker_version` | `openkat_version` | specific version for rocky_worker service |
| `openkat_rocky_database`  | `openkat_rocky_user` | database for rocky service |
| `openkat_katalogus_database` | `openkat_katalogus_user` | database for rocky service |
| `openkat_bytes_database`| `openkat_bytes_user` | database for rocky service |
| `openkat_mula_database`| `openkat_mula_user` | database for rocky service |
| `openkat_rabbitmq_user`| `openkat_rabbitmq_vhost` | database for rocky service |

### PostgreSQL and RabbitMQ runtime

- `openkat_postgres_version`
- `openkat_postgres_run_options`
- `openkat_postgres_admin_user`
- `openkat_rabbitmq_version`

### Feature flags / behavior

- `openkat_rocky_debug`
- `openkat_rocky_2fa`
- `openkat_rocky_worker_debug`
- `openkat_rocky_worker_2fa`


## Persistent Password Generation and Rotation

This role uses the custom module `library/persist_password.py` to generate and persist passwords and secrets in files on the target host.

What the module does:

1. Checks whether a `VARIABLE=value` entry already exists in the configured file.
2. Reuses the existing value when present (persistent behavior).
3. Generates a new secure random value when missing.
4. Optionally rotates by age via `rotatedays`:
    - `0` means no automatic rotation.
    - `N > 0` rotates when the file age is at least `N` days.
5. Writes values atomically and sets owner/group/mode.
6. Exposes the value as an Ansible fact (`fact_name`) for subsequent tasks/templates.

In this role, password/secrets generation is handled in `tasks/passwords.yml`.

Current behavior:

- 30-day auto-rotation is enabled for:
   - `postgres`, `rocky`, `katalogus`, `bytes`, `mula` passwords
   - `openkat_bytes_secret`
   - `openkat_rocky_secret`
- rotation is intentionally disabled for:
   - `openkat_rabbitmq_password`
   - `openkat_rocky_superuser_password`

Disabling rotation for RabbitMQ and Rocky superuser is deliberate to avoid breaking existing credentials and login flows.

## BackupNinja Option

When `openkat_backupninja_enabled: true`, the role includes `tasks/postgres_backupninja.yml` and configures host-level PostgreSQL backups.

It does the following:

1. Ensures local `postgres` user exists.
2. Installs package `backupninja`.
3. Templates config files:
   - `/etc/backup.d/20.pgsql`
   - `/etc/backupninja.conf`
4. Creates PostgreSQL credentials file:
   - `/home/postgres/.pgpass` (owner `postgres`, mode `0600`)
5. Ensures backup directories exist:
   - `${openkat_data_directory}/backups/`
   - `${openkat_data_directory}/backups/postgres`

Current `20.pgsql` template uses:

- `backupdir = ${openkat_data_directory}/backups/postgres`
- `databases = all`
- `compress = no`

Set `openkat_backupninja_enabled: false` to skip all BackupNinja-related setup.

## Testing

This role includes a lightweight pytest suite under `tests/`.

The suite focuses on the parts of the role that are practical to validate without
booting a full nested Docker + systemd environment:

- helper logic in `library/persist_password.py`
- task wiring and required variable declarations
- rendering smoke tests for all Jinja templates with representative role variables

Install the test dependencies and run the suite with:

```bash
python -m pip install -r requirements-test.txt
pytest
```

### Molecule

A Molecule scenario is available under `molecule/default/` for Linux hosts that can
run privileged Docker containers with systemd enabled.

The scenario converges the full role inside a Debian 12 systemd container. It uses a
prepared fake `docker` binary inside that container so the role can exercise its
systemd and compose wiring without needing a nested Docker daemon.

Install the Molecule dependencies and run the scenario with:

```bash
python -m pip install -r requirements-molecule.txt
molecule test
```

The scenario disables BackupNinja to keep the test focused on the role's service and
template orchestration.

A second scenario under `molecule/missing-required-vars/` exercises the failure path
for missing required role variables and asserts that the role aborts with the expected
validation message.

Run a specific scenario with:

```bash
molecule test -s default
molecule test -s missing-required-vars
```

## CI

GitHub Actions CI is defined in `.github/workflows/ci.yml`.

It runs:

- the pytest suite
- `molecule test -s default`
- `molecule test -s missing-required-vars`


## Local Development

Create a virtual environment and install the local test dependencies:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-test.txt -r requirements-molecule.txt
ansible-galaxy collection install -r requirements.yml
```

Run the pytest suite:

```bash
pytest
```

Run the Molecule scenarios:

```bash
molecule test -s default
molecule test -s missing-required-vars
```

The Molecule scenarios require a working Docker daemon because they run privileged
systemd-enabled test containers.

### Troubleshooting

If `molecule test` fails with a Docker daemon error, confirm that Docker is installed,
running, and reachable from your shell:

```bash
docker version
docker info
```

If the scenario fails during container startup, verify that your Docker environment
allows privileged containers and the `/sys/fs/cgroup` bind mount required for systemd.

If `pytest` or `molecule` is not found, make sure the virtual environment is active:

```bash
. .venv/bin/activate
```

If dependency installation fails on a system-managed Python interpreter, use the local
virtual environment shown above instead of installing packages into the system Python.
