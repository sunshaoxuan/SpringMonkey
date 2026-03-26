# GitHub Access Setup For 汤猴

Purpose: give the remote `openclaw` runtime write access to this repository without exposing user credentials.

## Recommended Method

Use a repository deploy key with write access.

Why:

- isolated to this repository
- no personal GitHub password or PAT has to be stored on the host
- easy to revoke

## Public Key To Add

Add the following public key as a writable deploy key on `sunshaoxuan/SpringMonkey`:

```text
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIBVyzOZHa5HL0b9IUPdrxAuiTyfyGi32U/R6IDc/UrKu openclaw-springmonkey
```

## GitHub Side Steps

1. Open `https://github.com/sunshaoxuan/SpringMonkey/settings/keys`
2. Click `Add deploy key`
3. Title suggestion: `openclaw-springmonkey`
4. Paste the public key above
5. Enable `Allow write access`
6. Save

## Host Side Material Already Prepared

On the remote host, a dedicated SSH keypair now exists for the `openclaw` user:

- `/var/lib/openclaw/.ssh/id_ed25519_github_springmonkey`
- `/var/lib/openclaw/.ssh/id_ed25519_github_springmonkey.pub`

## Next Step After GitHub Key Is Added

Validate from the host with:

```bash
runuser -u openclaw -- ssh -i /var/lib/openclaw/.ssh/id_ed25519_github_springmonkey -T git@github.com
```

Then the repository can be cloned or attached with SSH for autonomous updates by `汤猴`.
