# Silica Skills Layer

Skills are discrete, composable reasoning modules that teach the model *how to think* about EDA tool output — not just how to call tools. They ship as plain Markdown files and are injected into the model's context as needed.

## Structure

```
skills/
├── base/
│   └── rtl_assistant.md      # Always loaded at server boot — core identity and tool awareness
└── workflows/
    └── debug_simulation_failure.md   # Loaded when triaging sim failures
    └── write_testbench.md            # Loaded when generating testbenches
    └── generate_assertions.md        # Loaded when writing SVA
    └── close_timing.md               # Loaded when working timing closure
    └── debug_formal_failure.md       # Loaded when triaging formal FAIL/UNKNOWN
    └── cdc_review.md                 # Loaded when reviewing clock domain crossings
```

## How loading works

- `base/rtl_assistant.md` is injected as the MCP server's `instructions` field — always visible.
- Workflow skills are exposed as MCP **prompts** (via `@mcp.prompt()`). The model requests them by name when the task context calls for it. Claude Desktop surfaces available prompts in the UI.

## Writing a new skill

A skill file should contain:

1. **Task description** — one sentence on what this skill covers
2. **When to use it** — trigger conditions
3. **Reasoning script** — numbered steps; be explicit, not vague
4. **Tool calls** — which MCP tools are called at each step and what to look for
5. **Few-shot examples** — minimum two complete examples with real (or realistic) tool output
6. **Edge cases** — common failure modes

The few-shot examples are the most important part. Use actual Verilator errors, actual Yosys output, actual waveform signal states — not placeholder text. Generic examples don't improve model behavior.
