# Frozen Contracts (1.0)

TouchPilot's 1.0 release depends on a stable surface between the app runtime,
bundled assets, and anything a maintainer or third-party author writes by hand
(tools, skills, workflows, model manifests). This document is the audit result
for issue #389: it lists every contract that ships with the app, its frozen
version, its status, and what changed since Milestone 14.

Freezing a contract means:

- Its current shape is documented and versioned here.
- Future changes must be additive (new optional fields, new enum values) or
  must bump the version and update this changelog.
- Removing or repurposing a field is a breaking change and requires a new
  major/contract version plus a migration note.

Contracts marked **Experimental** are explicitly excluded from that guarantee:
they may change or be removed without a version bump before 1.0 ships and
after, until they are promoted here.

## Contract Audit Checklist

Run this checklist before every release that touches a contract:

1. For each contract below, confirm the code's version constant matches the
   version recorded here.
2. Confirm every field in the spec doc has a corresponding field in the code
   model, and vice versa (no undocumented fields, no dead doc fields).
3. Confirm any field added since the last audit is either versioned (bumped
   the contract version) or additive-and-optional (safe without a bump).
4. Confirm experimental contracts are still labeled experimental in both the
   doc and the code, or have been promoted here with a version.
5. Update the "Since M14" changelog entry for anything that changed.
6. Update this table's "Last audited" column.

## Contract Registry

| Contract | Version | Status | Spec | Code |
| --- | --- | --- | --- | --- |
| Tool API | 1 | Frozen | [TOOL_SPEC.md](TOOL_SPEC.md) | `tools/ToolModels.kt` (`AndroidToolCatalog.CATALOG_VERSION`) |
| Skill `SKILL.md` schema | 2 | Frozen | [SKILLS.md](SKILLS.md) | `memory/SkillModels.kt`, `memory/SkillParser.kt` |
| Skill `SKILL.md` schema (legacy heading format) | 1 | Experimental — deprecated, slated for removal after 1.0 | [SKILLS.md](SKILLS.md#legacy-v1-format-deprecated) | `memory/SkillModels.kt` (`SkillFormat.LEGACY_V1`) |
| Workflow schema | 1 | Frozen | [WORKFLOWS.md](WORKFLOWS.md) | `workflow/WorkflowModels.kt` (`WorkflowDefinition.CURRENT_VERSION`) |
| Policy rule vocabulary | 1 | Frozen | [POLICY.md](POLICY.md) | `security/PolicyV2Model.kt` (`PolicyV2Defaults.POLICY_CONTRACT_VERSION`) |
| Model manifest (LiteRT command router) | 1 | Frozen | [LOCAL_INFERENCE.md](LOCAL_INFERENCE.md#litert-command-router-asset-contract) | `localinference/LocalCommandModelRuntime.kt` (`LocalModelManifest.SUPPORTED_CONTRACT_VERSION`) |
| Local model request/response shape | — | Experimental — not yet independently versioned | [LOCAL_INFERENCE.md](LOCAL_INFERENCE.md#runtime-boundary) | `localinference/LocalModelContracts.kt` |
| MCP tool-call contract | — | Experimental — not merged into the main agent loop | [MCP.md](MCP.md) | `mcp/McpModels.kt` |
| Local extension plugin API manifest | 1.0.0 (semver) | Experimental — no bundled extensions ship in 1.0 | [MCP.md](MCP.md#local-extension-plugin-api-manifest) | `mcp/PluginApiManifest.kt` |
| Memory entry schema | — | Deferred to Milestone 17 | not yet designed | not yet implemented |

Last audited: 2026-07-03 (issue #389).

## Memory Entry Schema: Explicitly Deferred

Milestone 17 ("Local Memory and Trace System") introduces on-device memory
entries for preferences, recurring apps, and task history. As of this audit
that milestone has not started: there is no `MemoryEntry` type, no storage
path, and no schema to freeze. `docs/ROADMAP.md`'s Milestone 24 deliverable
previously asked to "freeze and version the tool, skill, workflow, memory, and
policy contracts" as a single 2.0-scoped item; this audit pulls the four
contracts that already exist (tool, skill, workflow, policy) forward into the
1.0 freeze below and leaves the memory entry schema for Milestone 17, where it
will be versioned from its first commit using the same `contract_version` /
`schema_version` convention as the other contracts (see
[DemonstrationModels.kt](../app/src/main/java/dev/touchpilot/app/demonstration/DemonstrationModels.kt)
for the closest existing precedent). Freezing a schema that does not exist yet
would not give third-party authors anything real to build against, so calling
it "frozen" here would be misleading.

The `memory/` package that exists today (`SkillModels.kt`, `SkillParser.kt`,
`SkillRegistry.kt`, `SkillStore.kt`) only implements skill loading — it is
covered by the Skill contract above, not this deferred one.

## Experimental Contracts

These contracts are explicitly **not** frozen for 1.0. They may change shape,
gain a version field, or be removed without notice:

- **Legacy Skill v1 format** (`SkillFormat.LEGACY_V1`): the original heading +
  "Allowed initial tools:" parser. Every bundled skill has used v2 front
  matter since the Skills v2 migration, so this path only matters for
  hand-authored, unmigrated third-party `SKILL.md` files. It stays available
  through 1.0 for backward compatibility but does not get the freeze
  guarantee, is marked `@Deprecated` in code, and should be removed once
  third-party skill authors have had a release cycle to migrate.
- **Local model request/response shape** (`LocalModelContracts.kt`): the JSON
  passed to and from the LiteRT command router each turn. The manifest that
  points at the model asset is frozen (`contract_version`), but the shape of
  the request/response JSON itself has no version field yet. A future change
  here should add one before promoting it to frozen.
- **MCP tool-call contract** (`McpModels.kt`) and **local extension plugin API
  manifest** (`PluginApiManifest.kt`): MCP tools are not merged into the main
  agent loop (see [MCP.md](MCP.md)), and no extension ships bundled with the
  app. The plugin manifest already carries a semver `api_version` and
  compatibility gate, so it is closer to freeze-ready than the MCP tool-call
  shape, but both stay experimental until MCP is wired into the agent loop.

## Changes Since Milestone 14

Milestone 14 ("Advanced Local AI") is the last milestone completed before this
audit. Contract-relevant changes landed since then:

- Workflow schema (`version: 1`) reached its documented, enforced form —
  strict version gate, required/optional field set, and parser validation —
  and is frozen as-is with this audit.
- Policy vocabulary (`PolicySubject`, `PolicyWorkflowClass`, `PolicyRiskBand`,
  `PolicyDecisionKind`) moved from "Milestone 7 provisional, no runtime
  enforcement" (per the original header comment in `PolicyV2Model.kt`) to the
  vocabulary actually used by `PolicyEngine`, `WorkflowStepPolicy`, and replay.
  This audit freezes it as `POLICY_CONTRACT_VERSION = 1` and removes the
  "provisional" language from the code comment.
- Model manifest `contract_version: 1` and the plugin API manifest
  `api_version: 1.0.0` were both already versioned; this audit confirms both
  and freezes the model manifest for 1.0 while leaving the plugin manifest
  experimental (no bundled extensions).
- Tool API (`ToolSpec` / `AndroidToolCatalog`) had no version concept at all.
  This audit adds `AndroidToolCatalog.CATALOG_VERSION = 1` as the frozen
  starting point; the catalog's 23 tools and their argument contracts as of
  this audit are the 1.0 baseline.
- No breaking changes to any existing field shape were made by this audit —
  every change above is additive (a new version constant, a new doc, a
  deprecation marker) or a documentation-only freeze declaration.

## Widening Permissions

Per the issue's safety note, freezing the policy contract must not silently
widen permissions. This audit only *documents and versions* the existing
`PolicyV2Defaults` decision tables (`decisionForToolRisk`,
`decisionForWorkflow`) — no default decision (`ALLOW`/`ASK`/`DENY`/`BLOCK`)
for any existing `ToolRisk` or `PolicyWorkflowClass` value changed as part of
this work.