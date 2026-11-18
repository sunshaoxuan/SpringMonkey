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

The runtime enables the store and publisher toolsets and uses the upstream
read-only flag. Hermes adds a seven-tool allowlist from
[`steam-mcp-config.json`](../../scripts/hermes-pilot/steam-mcp-config.json).
The working Steam MCP has no Steam account, Publisher Key, or browser session.

Verification passed for HTTP MCP initialization and listing, a live public
Steam player-count lookup, rejection of an unexpected Host header, and the
missing-key response for private build history. Both Hermes containers passed
native MCP discovery. An actual Hermes conversation called the Steam tool for
public App ID 570 and returned the live result.

## Use

Restart discovery in an existing Hermes conversation with `/reload-mcp`, or
start a new conversation. Ask it to use Steam MCP for a public Steam title,
such as querying the current player count for App ID 570. Steamworks build
history and beta branch reads are registered. Both require the publisher
group's key for the relevant App ID.

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
