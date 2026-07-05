import { describe, expect, it } from "vitest";

import type { Category } from "@/types/registry";

import {
  SUBMISSION_SPEC,
  buildSubmissionPacket,
  preflight,
  slugify,
} from "@/lib/submission-spec-lib";

const RISK_BEARING_CATEGORIES: Category[] = [
  "mcp",
  "skills",
  "hooks",
  "commands",
  "statuslines",
];

const NON_RISK_CATEGORIES: Category[] = [
  "agents",
  "rules",
  "guides",
  "collections",
];

function baseCommonFields(overrides: Record<string, string> = {}) {
  return {
    name: "Example Entry",
    slug: "example-entry",
    description:
      "A useful registry submission used to exercise preflight validation in the HeyClaude submit flow.",
    card_description: "Short browse-card preview for the example submission.",
    github_url: "https://github.com/example/repo",
    ...overrides,
  };
}

function validMcpFields(overrides: Record<string, string> = {}) {
  return {
    ...baseCommonFields({ slug: "example-mcp" }),
    install_command: "npx -y @example/mcp",
    usage_snippet: "Add the server to your MCP client config.",
    safety_notes: "Review install scripts before running.",
    privacy_notes: "May send prompts to configured APIs.",
    ...overrides,
  };
}

function validAgentsFields(overrides: Record<string, string> = {}) {
  return {
    ...baseCommonFields({ slug: "example-agent" }),
    full_copyable_content: "You are a helpful coding agent.",
    ...overrides,
  };
}

function validSkillsFields(overrides: Record<string, string> = {}) {
  return {
    ...baseCommonFields({ slug: "example-skill" }),
    usage_snippet: "Install the skill package into your client directory.",
    skill_type: "general",
    skill_level: "advanced",
    verification_status: "validated",
    full_copyable_content: "---\nname: Example\n---\n",
    safety_notes: "Review scripts before installing.",
    privacy_notes: "No third-party telemetry in the sample package.",
    ...overrides,
  };
}

function fieldsForRiskCategory(category: Category): Record<string, string> {
  switch (category) {
    case "mcp":
      return validMcpFields();
    case "skills":
      return validSkillsFields();
    case "hooks":
      return {
        ...baseCommonFields({ slug: "example-hook" }),
        trigger: "PreToolUse",
        usage_snippet: "Attach to PreToolUse lifecycle.",
        full_copyable_content: "hook script",
        safety_notes: "Review hook actions.",
        privacy_notes: "Runs locally.",
      };
    case "commands":
      return {
        ...baseCommonFields({ slug: "example-command" }),
        command_syntax: "/example <path>",
        usage_snippet: "Run in Claude Code.",
        full_copyable_content: "slash command body",
        safety_notes: "May modify files.",
        privacy_notes: "Runs locally.",
      };
    case "statuslines":
      return {
        ...baseCommonFields({ slug: "example-statusline" }),
        script_language: "bash",
        full_copyable_content: "statusline script",
        safety_notes: "Runs shell commands.",
        privacy_notes: "Reads local git state.",
      };
    default:
      return baseCommonFields();
  }
}

describe("submission-spec-lib slugify", () => {
  it("normalizes titles into lowercase kebab-case slugs", () => {
    expect(slugify("Claude's Helpful MCP!")).toBe("claudes-helpful-mcp");
    expect(slugify('  Foo   "Bar"  ')).toBe("foo-bar");
    expect(slugify("")).toBe("");
  });
});

describe("submission-spec-lib SUBMISSION_SPEC", () => {
  it("defines every registry category with core metadata", () => {
    const categories = Object.keys(SUBMISSION_SPEC).sort();
    expect(categories).toEqual(
      [
        "agents",
        "collections",
        "commands",
        "guides",
        "hooks",
        "mcp",
        "rules",
        "skills",
        "statuslines",
        "tools",
      ].sort(),
    );

    for (const category of categories as Category[]) {
      const spec = SUBMISSION_SPEC[category];
      expect(spec.category).toBe(category);
      expect(spec.blurb.length).toBeGreaterThan(10);
      expect(spec.fields.map((field) => field.key)).toEqual(
        expect.arrayContaining([
          "name",
          "slug",
          "description",
          "card_description",
        ]),
      );
    }
  });

  it("marks risk-bearing categories and exposes safety or privacy examples", () => {
    for (const category of RISK_BEARING_CATEGORIES) {
      const spec = SUBMISSION_SPEC[category];
      expect(spec.riskBearing).toBe(true);
      expect(spec.exampleSafety?.length).toBeGreaterThan(0);
      expect(spec.examplePrivacy?.length).toBeGreaterThan(0);
    }

    for (const category of NON_RISK_CATEGORIES) {
      expect(SUBMISSION_SPEC[category].riskBearing).toBe(false);
    }
  });

  it("routes commercial tools through a web-only maintainer lane", () => {
    expect(SUBMISSION_SPEC.tools.webOnly).toBe(true);
    expect(
      SUBMISSION_SPEC.tools.fields.map((field) => field.key),
    ).not.toContain("full_copyable_content");
  });

  it("includes category-specific required fields", () => {
    expect(
      SUBMISSION_SPEC.mcp.fields.find(
        (field) => field.key === "install_command",
      )?.required,
    ).toBe(true);
    expect(
      SUBMISSION_SPEC.skills.fields.find((field) => field.key === "skill_type")
        ?.options,
    ).toEqual(["general", "capability-pack"]);
    expect(
      SUBMISSION_SPEC.hooks.fields.find((field) => field.key === "trigger")
        ?.options,
    ).toContain("PreToolUse");
    expect(
      SUBMISSION_SPEC.commands.fields.find(
        (field) => field.key === "command_syntax",
      )?.required,
    ).toBe(true);
    expect(
      SUBMISSION_SPEC.guides.fields.find(
        (field) => field.key === "guide_content",
      )?.required,
    ).toBe(true);
    expect(
      SUBMISSION_SPEC.collections.fields.find((field) => field.key === "items")
        ?.required,
    ).toBe(true);
  });
});

describe("submission-spec-lib preflight", () => {
  it("blocks submissions without a category", () => {
    expect(preflight("", {})).toEqual([
      { kind: "blocker", message: "Pick a category." },
    ]);
  });

  it("warns when a web-only category is selected", () => {
    expect(
      preflight("tools", { github_url: "https://example.com" }),
    ).toContainEqual({
      kind: "warning",
      message:
        "This category needs maintainer routing before website import is enabled.",
    });
  });

  it("flags invalid slugs and non-HTTPS source URLs for MCP submissions", () => {
    expect(
      preflight("mcp", {
        title: "Example",
        slug: "Bad Slug",
        github_url: "http://example.com/repo",
      }).map((issue) => issue.message),
    ).toEqual(
      expect.arrayContaining([
        "Slug must be lowercase kebab-case.",
        "github url must be HTTPS.",
        "Safety notes are required for this category.",
        "Privacy notes are required for this category.",
      ]),
    );
  });

  it("requires HTTPS docs and download URLs when present", () => {
    const issues = preflight("skills", {
      ...validSkillsFields(),
      docs_url: "http://docs.example.com",
      download_url: "ftp://files.example.com/pkg.zip",
    }).map((issue) => issue.message);

    expect(issues).toEqual(
      expect.arrayContaining([
        "docs url must be HTTPS.",
        "download url must be HTTPS.",
      ]),
    );
  });

  it("requires at least one source or docs URL", () => {
    const issues = preflight(
      "agents",
      validAgentsFields({
        github_url: "",
        docs_url: "",
      }),
    ).map((issue) => issue.message);

    expect(issues).toContain("Add at least one source or docs URL.");
  });

  it("requires safety and privacy notes for risk-bearing categories", () => {
    for (const category of RISK_BEARING_CATEGORIES) {
      const fields = { ...fieldsForRiskCategory(category) };
      delete fields.safety_notes;
      delete fields.privacy_notes;

      const messages = preflight(category, fields).map(
        (issue) => issue.message,
      );
      expect(messages).toEqual(
        expect.arrayContaining([
          "Safety notes are required for this category.",
          "Privacy notes are required for this category.",
        ]),
      );
    }
  });

  it("reports missing required fields by label", () => {
    const issues = preflight("mcp", {
      slug: "example-mcp",
      github_url: "https://github.com/example/mcp",
      safety_notes: "Review scripts.",
      privacy_notes: "No telemetry.",
    }).map((issue) => issue.message);

    expect(issues).toEqual(
      expect.arrayContaining([
        "Missing required field: Name",
        "Missing required field: Description",
        "Missing required field: Card description",
        "Missing required field: Install command",
        "Missing required field: Usage snippet",
      ]),
    );
  });

  it("accepts a complete MCP payload without blockers", () => {
    const issues = preflight("mcp", validMcpFields());
    expect(issues.filter((issue) => issue.kind === "blocker")).toEqual([]);
  });

  it("accepts a complete agents payload without blockers", () => {
    const issues = preflight("agents", validAgentsFields());
    expect(issues.filter((issue) => issue.kind === "blocker")).toEqual([]);
  });

  it("accepts docs_url as the sole source URL", () => {
    const issues = preflight(
      "agents",
      validAgentsFields({
        github_url: "",
        docs_url: "https://docs.example.com/agents/example",
      }),
    );

    expect(issues.map((issue) => issue.message)).not.toContain(
      "Add at least one source or docs URL.",
    );
  });

  it("allows blank optional URLs", () => {
    const issues = preflight(
      "agents",
      validAgentsFields({
        docs_url: "",
        download_url: "",
      }),
    ).map((issue) => issue.message);

    expect(issues).not.toContain("docs url must be HTTPS.");
    expect(issues).not.toContain("download url must be HTTPS.");
  });
});

describe("submission-spec-lib buildSubmissionPacket", () => {
  it("renders labeled markdown sections for populated fields", () => {
    const packet = buildSubmissionPacket("mcp", {
      name: "Example MCP",
      slug: "example-mcp",
      github_url: "https://github.com/example/mcp",
      usage_snippet: "Configure the MCP client with the install command.",
    });

    expect(packet).toContain("### Name");
    expect(packet).toContain("Example MCP");
    expect(packet).toContain("### GitHub URL");
    expect(packet).toContain("https://github.com/example/mcp");
    expect(packet).toContain("### Usage snippet");
  });

  it("omits empty optional fields from the packet", () => {
    const packet = buildSubmissionPacket("agents", {
      name: "Example Agent",
      slug: "example-agent",
      description: "Agent description.",
      card_description: "Card preview.",
      full_copyable_content: "System prompt body.",
      docs_url: "",
      author: "",
    });

    expect(packet).not.toContain("### Docs URL");
    expect(packet).not.toContain("### Author or organization");
    expect(packet).toContain("### Full copyable content");
  });

  it("falls back to common fields when category is empty", () => {
    const packet = buildSubmissionPacket("", {
      name: "Untyped Entry",
      slug: "untyped-entry",
    });

    expect(packet).toContain("### Name");
    expect(packet).toContain("Untyped Entry");
    expect(packet).not.toContain("### Install command");
  });

  it("includes skills-specific metadata fields when provided", () => {
    const packet = buildSubmissionPacket("skills", {
      ...validSkillsFields(),
      retrieval_sources: "https://docs.example.com/skills/example",
      tested_platforms: "Claude, Cursor",
    });

    expect(packet).toContain("### Skill type");
    expect(packet).toContain("general");
    expect(packet).toContain("### Retrieval sources");
    expect(packet).toContain("https://docs.example.com/skills/example");
    expect(packet).toContain("### Tested platforms");
    expect(packet).toContain("Claude, Cursor");
  });

  it("preserves multiline code and textarea values", () => {
    const packet = buildSubmissionPacket("commands", {
      ...baseCommonFields({ slug: "refactor-command" }),
      command_syntax: "/refactor <path>",
      usage_snippet: "Run inside Claude Code:\n/refactor src/",
      full_copyable_content: "Command body\nwith multiple lines",
      safety_notes: "May modify files.",
      privacy_notes: "Runs locally.",
    });

    expect(packet).toContain("/refactor <path>");
    expect(packet).toContain("Run inside Claude Code:\n/refactor src/");
    expect(packet).toContain("Command body\nwith multiple lines");
  });
});