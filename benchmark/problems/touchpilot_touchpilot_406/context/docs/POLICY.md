# Policy Rule Format

TouchPilot's safety policy decides whether a tool call, workflow step, or
skill action runs silently, needs approval, or is blocked outright. Unlike the
[Tool Spec](TOOL_SPEC.md), [Skills](SKILLS.md), and [Workflows](WORKFLOWS.md)
contracts, the policy contract is **not a file format** — there is no
`policy.json` a maintainer or third party authors by hand. It is a fixed
vocabulary of enums and a decision precedence rule, implemented in
`app/src/main/java/dev/touchpilot/app/security/PolicyV2Model.kt` and evaluated
by `PolicyEngine`.

The wire-visible part of this vocabulary is `PolicyWorkflowClass`, which
appears in the [Workflow schema](WORKFLOWS.md#per-step-policy)'s
`policy.workflow_class` field (lowercase, e.g. `security_settings`).

## Contract Status

`POLICY_CONTRACT_VERSION = 1` (`PolicyV2Defaults.POLICY_CONTRACT_VERSION`).
Frozen for 1.0: the four enum vocabularies and the decision precedence rule
below are additive-only going forward. `PolicyRule` itself stays an in-memory,
code-constructed model — it is not serialized to or parsed from a file today,
so there is nothing to version beyond the enums it references.

## Vocabulary

`PolicySubject`
: What kind of thing a rule evaluates: `TOOL`, `APP`, `WORKFLOW`, `SKILL`,
  `SOURCE`.

`PolicyWorkflowClass`
: The sensitivity category a workflow step belongs to: `GENERAL`,
  `MESSAGE_SEND`, `PAYMENT`, `PURCHASE`, `DELETION`, `ACCOUNT_CHANGE`,
  `ACCOUNT_RECOVERY`, `PERMISSION_CHANGE`, `SECURITY_SETTINGS`,
  `SENSITIVE_TEXT_ENTRY`, `EXTERNAL_MCP`, `UNKNOWN_SENSITIVE`. This is the one
  value from the vocabulary that round-trips through a file: it is the wire
  value for `workflow_class` in a workflow step's `policy` block (serialized
  lowercase; see [WORKFLOWS.md](WORKFLOWS.md#per-step-policy)).

`PolicyRiskBand`
: `LOW`, `MEDIUM`, `HIGH`, `BLOCKED`. Derived from `ToolRisk` via
  `PolicyRiskBand.fromToolRisk`, so it stays in lockstep with the
  [Tool API](TOOL_SPEC.md)'s own risk enum.

`PolicyDecisionKind`
: The outcome of evaluating a rule, in strictest-wins precedence order:
  `ALLOW` (0) < `ASK` (1) < `DENY` (2) < `BLOCK` (3). When multiple rules
  match, `PolicyDecisionKind.strictest` picks the highest-precedence decision.

## Models

`PolicyRule`
: `id`, `subject`, `decision`, `reason`, `workflowClass` (default `GENERAL`),
  `riskBand` (default `LOW`). Built in code by `PolicyEngine.rulesFor()` and
  the default tables in `PolicyV2Defaults` — never loaded from a file.

`PolicyEvaluation`
: The result of evaluating a set of `PolicyRule`s for one action: the
  strictest `decision`, the full `rules` list that matched, and a
  human-readable `userMessage` built from the reasons behind the strictest
  decision.

## Default Decision Tables

`PolicyV2Defaults.decisionForToolRisk` and `.decisionForWorkflow` define the
1.0 baseline decisions:

| `ToolRisk` | Decision |
| --- | --- |
| `LOW` | `ALLOW` |
| `MEDIUM` | `ASK` |
| `HIGH` | `ASK` |
| `BLOCKED` | `BLOCK` |

| `PolicyWorkflowClass` | Decision |
| --- | --- |
| `GENERAL` | `ALLOW` |
| `MESSAGE_SEND` | `ASK` |
| `PAYMENT`, `PURCHASE`, `DELETION`, `ACCOUNT_CHANGE`, `ACCOUNT_RECOVERY`, `PERMISSION_CHANGE`, `SECURITY_SETTINGS`, `SENSITIVE_TEXT_ENTRY`, `EXTERNAL_MCP`, `UNKNOWN_SENSITIVE` | `BLOCK` |

Freezing this contract means these mappings cannot get *less* strict (a value
moving from `ASK`/`BLOCK` toward `ALLOW`) without a contract version bump and
an explicit changelog entry, per [CONTRACTS.md](CONTRACTS.md#widening-permissions).
Adding a new, more permissive path for an existing `PolicyWorkflowClass` is
exactly the kind of change that needs one; adding a new enum value at the
strictest default (`BLOCK`/`ASK`) does not.

## Out of Scope for 1.0

- Loading policy rules from an external file or remote source. Today's
  code-only model is the frozen contract.
- Per-user or per-device policy overrides.

## Related Code

```text
app/src/main/java/dev/touchpilot/app/security/
  PolicyV2Model.kt          vocabulary + PolicyRule/PolicyEvaluation + defaults
  PolicyEngine.kt           rule construction and evaluation
  WorkflowRiskClassifier.kt workflow risk classification helpers
  AppContextClassifier.kt   app-context classification helpers
  ApprovalCopyBuilder.kt    approval prompt copy built from PolicyEvaluation
```