# Google Custom Search Secret Storage

Updated: 2026-04-03 (Asia/Tokyo)

## Purpose

This document records the public storage format for the Google Custom Search API key used by `OpenClaw`.

The plaintext key is not stored in the repository.

## Repository Artifact

- Encrypted file:
  - `secrets/google-custom-search-api.enc.json`

## Encryption Method

- Algorithm:
  - `AES-256-GCM`
- KDF:
  - `PBKDF2-HMAC-SHA256`
- Iterations:
  - `200000`
- Stored fields:
  - `salt`
  - `nonce`
  - `ciphertext`
  - `tag`

## Password Handling

- The encryption password is intentionally not stored in the repository.
- The password must be supplied separately by an operator when decryption is required.

## Operational Use

- Runtime configuration for `OpenClaw` uses a root-managed environment file on the host.
- The repository copy is for escrow and recovery only.
- The encrypted repository artifact does not replace host-side secret management.

## Decryption Reference

Decryption should recreate the same key derivation and AES-GCM parameters:

1. Base64-decode `salt`, `nonce`, `ciphertext`, and `tag`
2. Derive a 32-byte key with `PBKDF2-HMAC-SHA256(password, salt, 200000)`
3. Decrypt with `AES-256-GCM`

## Boundary

- The password is not to be committed.
- The plaintext API key is not to be committed.
- Only the encrypted artifact and the public method description belong in Git.
