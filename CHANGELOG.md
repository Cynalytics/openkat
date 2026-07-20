# Changelog

All notable functional changes for this role are documented in this file.

## Unreleased

### Added

- Installs `openkat-report`, a host CLI to list reports and fetch full report JSON from the local octopoes/bytes APIs (`openkat-report list` / `get [selector]`).

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
