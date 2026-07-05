# MCP

Phase 4 adds a small MCP client to the Android app.

The client uses HTTP JSON-RPC and implements the core lifecycle needed to
interoperate with tool servers:

- initialize a session,
- list tools,
- call a selected tool with JSON arguments,
- preserve `Mcp-Session-Id` when a server returns one.

MCP tools are not yet merged into the main agent loop. The Android control layer
remains the source of truth for phone actions, approvals, and audit logs. This
keeps the first MCP integration low risk while establishing protocol plumbing
for later interoperability.

Running an MCP server from the phone is deferred. Before TouchPilot exposes
Android tools over MCP, it needs an explicit server permission model,
foreground-service lifecycle, local-network binding controls, and request
authentication.

References:

- https://modelcontextprotocol.io/docs/learn/architecture
- https://modelcontextprotocol.io/specification/2025-11-25/server/tools
