# Ubuntu 26.10 unattended recovery preparation

Scope: prepare an unarmed package, preserve remote connectivity, validate in isolation, and execute a real reset only after its separate live-environment checks succeed. The current host is ubuntu-2625; this name is unrelated to the Ubuntu release number.

## Package contents

`prepare.py` serializes installer user-data, independent target networking, a key-only administrative SSH account, FRP service/configuration, exact-disk preflight, and first-boot network/SSH/firewall checks. `guard.py` contains no disk writes. `bootstrap.sh` is exclusively for a live installer and requires an explicitly armed, checksum-bound payload. It exposes a temporary key-only installer SSH endpoint through FRP and waits for an authenticated controller acknowledgment before storage installation proceeds.

Real SSIDs, PSKs, tokens and private keys remain inside a Windows DPAPI archive or a root-protected remote staging directory. **FRP binaries must never be downloaded, copied, executed or hidden in an archive on the managed Windows workstation, WSL or its Docker environment.** Preparation records the binary hash; remote staging obtains and validates the executable. The current live FRP remains separate from the staged latest version.

Local preparation is limited to configuration, scripts, ordinary Ubuntu packages and evidence:

```text
python prepare.py --output <protected-directory> --debs <offline-debs> --host <existing-host> --password-file <existing-local-secret-file>
python prepare.py --refresh --output <protected-directory> --debs <offline-debs> --remote-frp-manifest <verified-remote-manifest>
python -m unittest discover -s scripts/reinstall -p test_contracts.py
```

The password file is read into the SSH client, never printed. Existing known_hosts is mandatory. Fixture generation accepts a remote binary hash, never a local FRP executable. Fixtures use disposable credentials and Ethernet DHCP, so they cannot prove physical Wi-Fi association.

## Preservation and activation boundaries

Keep the existing system, authenticated Tailscale state, Wi-Fi settings, FRP access, and Discord company/private connection configuration until reset preconditions pass. Never start a copied production Tailscale identity alongside the original machine. Discord material is a later Harness migration input; this package does not activate Discord or send messages.

The prepared production package has no ARMED.json. There is no automatic host boot editing or reboot entry point in these preparation commands. Real execution additionally needs a validated signed boot path, enough RAM for any installer/media residing on the disk to be erased, independent access to installation sources throughout formatting, and actual live-environment Wi-Fi, Tailscale/FRP SSH confirmation. Copying an ISO onto the root partition is insufficient for safely formatting that partition.

## Validation

`validate_bundle.py` checks the official installer schema, payload hashes, actual Netplan generation, key pairing, and shell syntax. Real secrets are validated in a Linux tmpfs and never logged. FRP execution is marked remote-only unless the validator runs on the remote host with its staged binary. Safety tests reject the wrong disk, altered payloads, path traversal and non-SSH proxy additions.

The isolated VM workflow tests installation, key-based SSH through FRP, a subsequent reboot, and then the latest client, first-boot firewall and access checks in the same installed fixture. Physical radio/firmware behavior, the production identity restore and actual host reset retain their own acceptance evidence.

Current progress and results: [preparation report](../../docs/reports/AUTOINSTALL_PREPARATION_2026-11-16.md).
