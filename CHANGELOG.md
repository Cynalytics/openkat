# Changelog

All notable functional changes for this role are documented in this file.
## 1.22.1-1 (compared to 1.22.0-3)

### Changed

- Upgraded OpenKAT to v1.22.1: `openkat_version` now defaults to `v1.22.1`, which sets the
  image tag for all OpenKAT components (rocky, octopoes, bytes, mula, boefjes/katalogus/normalizer).

### Upstream changes in OpenKAT v1.22.1

- Added `octopoes_api_scanprofiles` to the upstream example compose. This role already ships
  the equivalent `octopoes_scanprofiles` service (since 1.22.0-1), so no role change is required.
- Added compound database indexes for task-list and stats queries (scheduler). This is applied
  as a database migration on container start; no role change is required.
- Scheduler can return bounded/unpartial counts.
- Fixed `get_tree(search_types)` dropping findings on descendant OOIs (octopoes).

### Compatibility and upgrade notes

- Patch release relative to 1.22.0: image-only changes plus an automatic scheduler database
  index migration. No new services, environment variables, or compose changes are introduced.
- Before deploying, make sure the configured registry (`openkat_docker_repository`) provides the
  `v1.22.1` tag for all OpenKAT images.

## 1.22.0-2 (compared to 1.22.0-1)

### Changed

- The manage_openkat.py commandline script has a new option `disable-2fa` facilitating resetting 2fa for users that have lost access to 2fa devices


## 1.22.0-1 (compared to 1.21.0-1)

### Added

- Added a new OpenKAT service: octopoes_scanprofiles.
- The new service is deployed as its own Docker Compose stack and systemd unit:
  - Compose path: ${openkat_service_root}/octopoesscanprofiles/docker-compose.yml
  - Unit path: /etc/systemd/system/openkat_octopoes_scanprofiles.service
- The service uses the same OpenKAT Octopoes image family and runs with command scanprofiles.
- Added a dedicated version variable: openkat_octopoes_scanprofiles_version (default: openkat_version).

### Changed

- use the 1.22.0 version of the docker images
- Integrated octopoes_scanprofiles into the main role task flow so it is deployed with the rest of the application services.
- Added a restart handler for openkat_octopoes_scanprofiles.service.
- Updated Molecule default verification to check:
  - openkat_octopoes_scanprofiles.service is active
  - The octopoes_scanprofiles Compose file and systemd unit are generated
- Updated documentation to include the new service and its version variable.

### Compatibility and upgrade notes

- This release is additive for runtime behavior and introduces no known breaking changes relative to 1.21.0-1
- After upgrade, one additional service is expected to be present and active on the target host: openkat_octopoes_scanprofiles.service.
