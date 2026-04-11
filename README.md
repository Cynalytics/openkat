# OpenKAT Role

This role deploys [OpenKAT](https://openkat.nl), the opensource security scanner, as a set of Docker Compose projects, each managed by its own systemd unit.

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

## Variables in defaults/main.yml

Defaults are defined in `defaults/main.yml`. Override them in inventory (`group_vars`, `host_vars`) or play vars.

### Core image and install path

- `openkat_version`: base OpenKAT version anchor used by component versions
- `openkat_docker_repository`: Docker registry/repository prefix
- `openkat_crux_version`: explicit version for Crux
- `openkat_service_root`: root path for service Compose directories (default `/srv`)
- `openkat_data_directory`: persistent data root (default `/data`)

### Backup control

- `openkat_backupninja_enabled`: enables BackupNinja setup for PostgreSQL (`true` by default)

### Per-component image versions

- `openkat_boefje_version`
- `openkat_bytes_version`
- `openkat_katalogus_version`
- `openkat_mula_version`
- `openkat_normalizer_version`
- `openkat_octopoes_api_version`
- `openkat_octopoes_api_worker_version`
- `openkat_rocky_version`
- `openkat_rocky_worker_version`

These default to `openkat_version` unless explicitly overridden.

### Database and service account names

- `openkat_rocky_database`, `openkat_rocky_user`
- `openkat_katalogus_database`, `openkat_katalogus_user`
- `openkat_bytes_database`, `openkat_bytes_user`
- `openkat_mula_database`, `openkat_mula_user`
- `openkat_rabbitmq_user`, `openkat_rabbitmq_vhost`

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

### Required user-supplied values

These are intentionally empty by default and validated in preflight checks:

- `openkat_superuser_fullname`
- `openkat_superuser_email`
- `openkat_traefik_letsencrypt_admin_email`

`openkat_required_vars` lists these required names and is looped by an assert task.

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
