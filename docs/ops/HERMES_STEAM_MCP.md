# SpringMonkey Steam MCP

This installation is for the owner's personal noncommercial Steamworks test.
TMHSDigital's Steam MCP is licensed CC BY-NC-ND 4.0. The running build uses the
unmodified upstream source at `fce291842eb162bc241f63228dc1c29b7202860c`.
The npm 0.9.0 release was checked separately and lacks the build and beta tools
needed here.

The source archive SHA256 is
`74fea31de4cc427b431ab6d3909f6d0c3b325741881af724e7ee40aac9fc8bc8`.
The Docker image uses the committed build recipe and upstream dependency lockfile.
The image ID on SpringMonkey is
`sha256:ce8ee20c0f448e6989250afd56e07a4f2bc75147c87e0aab00eee5984ee11fd9`.

The read-only container `hermes-steam-mcp` runs as UID 65534 with no host or
Hermes data mounts. Hermes connects over the dedicated Docker internal network
`hermes-steam-private` using the container DNS name. Steam MCP uses the default
bridge for outbound Steam API calls and publishes no host ports. The Hermes
startup scripts connect the application containers to the internal network when
it exists, with lower gateway priority than their existing route.

The public runtime enables the store and publisher toolsets and uses the upstream
read-only flag. Hermes exposes only the five public tools in
[`steam-mcp-config.json`](../../scripts/hermes-pilot/steam-mcp-config.json).
This container has no Steam account, Publisher Key, or browser session.

Verification passed for HTTP MCP initialization and listing, a live public
Steam player-count lookup, rejection of an unexpected Host header, and the
missing-key response for private build history. Both Hermes containers passed
native MCP discovery. An actual Hermes conversation called the Steam tool for
public App ID 570 and returned the live result.

## Use

Restart discovery in an existing Hermes conversation with `/reload-mcp`, or
start a new conversation. Ask it to use Steam MCP for a public Steam title,
such as querying the current player count for App ID 570. Steamworks build
history and beta branch reads use the separate `steamworks` entry for
`4417110` (英雄荣光医院).

## Private publisher queries

The owner's existing Valve publisher-group key is sealed with systemd
host credentials at `/etc/hermes-pilot/steam-publisher.cred` (root, 0600).
`hermes-steamworks-mcp.service` supplies the key at startup over stdin.
The key is absent from Docker configuration, Hermes YAML, and the public
connector. No Valve key, permissions, or Steamworks application settings were
created or changed.

The private MCP reuses the pinned upstream build and beta handlers, registers
only these two tools, and requires App ID `4417110` in both argument schemas.
Its listener binds only to the dedicated Docker internal network. It uses a
separate bridge for outbound Valve HTTPS and publishes no host ports. Use the
[`steamworks` MCP configuration](../../scripts/hermes-pilot/steamworks-mcp-config.json)
to discover the tools from Hermes. Other applications in the same Valve group
are outside this connector's scope.

Live verification passed for both Valve queries through the scoped MCP and
for rejection of the Demo App ID. Both Hermes containers passed native
discovery for the private and public connectors. No private build description
or credential was included in repository evidence.

To pause private access, disable `hermes-steamworks-mcp.service` and remove
only `mcp_servers.steamworks` from the managed configuration. The public
connector can continue serving public lookups.

Store-page edits, build uploads, and release actions are outside this
installation. Valve documents build uploads through SteamPipe and the required
Steamworks account permissions. Higher-risk partner-admin and mutation tools
are excluded.

To disable this connector, remove only `mcp_servers.steam` from the managed
Hermes YAML, then stop `hermes-steam-mcp`. A root-only pre-change policy backup
is under `/srv/hermes-pilot/b13-steam`. Use the single-entry removal if other
configuration changed after installation.

- [Pinned upstream source](https://github.com/TMHSDigital/steam-mcp/tree/fce291842eb162bc241f63228dc1c29b7202860c)
- [Upstream license](https://github.com/TMHSDigital/steam-mcp/blob/fce291842eb162bc241f63228dc1c29b7202860c/LICENSE)
- [Valve Publisher Keys](https://partner.steamgames.com/doc/webapi_overview/auth#publisher-keys)
- [Valve SteamPipe uploads](https://partner.steamgames.com/doc/sdk/uploading)

## Steam Guard email verification in WebApp

The WebApp image extends the reviewed Hermes v0.23.1 screen image with a pinned
classifier patch. Steamworks currently renders its emailed-code challenge as
five adjacent, unlabeled text fields. The patch recognizes this exact group on
the observed Valve partner origins (https://partner.steamgames.com and
https://partner.steampowered.com) when the surrounding challenge text matches.
The native vault handles the private prompt, origin check and field write. The
report workflow can continue after Steam accepts the verification.

`tests/steam_guard_browser_acceptance.py` covers the native prompt callback and
five-field fill in isolated Chromium, along with wrong-origin, unrelated fields,
wrong-length, and navigation cases. The candidate classifier also identified all
five fields on the real Steamworks challenge in a read-only probe. The production
image is selected through `/srv/hermes-pilot/screen-image.json`. The stopped
`hermes-dashboard-pre-steamguard` container and its original image are available
for rollback. The Steam MCP connector's tool scopes are independent of browser login.

The [Steamworks reports skill](../../scripts/hermes-pilot/steamworks-reports/SKILL.md)
covers routine read-only sales and financial report requests. It selects the
native Steam Guard prompt for either Valve portal when needed, then continues
the report lookup after successful verification.

For the application overview, the same skill runs the installed
`report-overview.js` through one `browser_exec` call. The extractor reads the
lifetime and currently selected period summaries together. It preserves the
visible period, currency, gross and net labels and leaves the report filters
as they are. The existing login and other report views use their own steps.
