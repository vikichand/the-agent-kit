<!-- Optional. Drop this into a project's PROJECT-CONFIG block, or into ~/.claude/rules/, when the
     project does browser work and both MCPs are installed. It is not part of the kit's universal
     rules: a project with no browser has no use for it, and AGENTS.md stays lean. -->

# Choosing between Playwright MCP and Chrome DevTools MCP

Both are browser MCPs, so an agent with both installed will pick one arbitrarily unless told how to
choose. This is the rule that makes the choice deliberate.

**Neither subsumes the other, so running both is correct.** But the popular shorthand ("Playwright
drives, DevTools inspects") is out of date and will send you to the wrong tool. Chrome DevTools MCP
ships 52 tools including 10 input-automation tools (`click`, `hover`, `fill`, `fill_form`, `drag`,
`press_key`, `type_text`, `upload_file`), a `wait_for` tool, and `take_snapshot`, which is explicitly
built from the accessibility tree. It drives a page perfectly well.

## What each one can do that the other genuinely cannot

| Only Chrome DevTools MCP | Only Playwright MCP |
|---|---|
| **Performance traces with Core Web Vitals** (`performance_start_trace`, `performance_analyze_insight`) covering LCP, INP, CLS | **Non-Chromium engines**: `--browser firefox`, `--browser webkit` |
| `lighthouse_audit` | `browser_generate_locator`, for emitting real test code (`--caps=testing`) |
| 12 heap-snapshot / memory tools | |
| Chrome extension install and inspection | |
| Per-request network detail (`get_network_request`) | |

Playwright MCP does have `browser_start_tracing` (behind `--caps=devtools`), but that records a
Playwright debug trace, not a Chrome performance profile. It will not give you Core Web Vitals.

## Pick by the question

| The question | Tool |
|---|---|
| Did my change work? Does this interaction still behave? | **Playwright** |
| Does it work in Firefox or Safari? | **Playwright** (only option) |
| I need this as a repeatable test in CI | **Playwright** |
| Is this slower than before? What is blocking render? | **DevTools** (only option) |
| What computed styles does this element actually have? | **DevTools** |
| Why did that request fail, redirect, or return the wrong body? | **DevTools** |
| What is the console emitting? | **DevTools** |
| Is something leaking memory? | **DevTools** (only option) |

## Sequencing

Many tasks need both, in this order: **act with Playwright, then inspect with DevTools.** Playwright
proves *that* something changed; DevTools explains *why* it looks wrong. Switch tools when the
question changes, never mid-question. Ping-ponging inside one question burns context and produces
fragmented evidence that is hard to trust.

**When you have no hypothesis yet** ("something is wrong here"), start with DevTools: console and
network are the cheapest broad signal. **When you are checking your own change**, start with
Playwright: behaviour is the acceptance test.

## Boundaries

- **One primary tool per finding.** One tool, plus at most one confirming check. Not parallel
  investigations in both.
- **A screenshot is not a measurement.** Do not eyeball two renderings through either MCP and report
  a similarity judgement. If the project has a scoring script, the score is the evidence (Section 5).
- **A skill that prescribes its own browser tooling wins inside that skill.** This rule governs
  everything outside one.
- **Build and compile questions do not go to a browser at all.** They go to the build command or the
  framework's own tooling.

---

*Verified against the Chrome DevTools MCP tool reference and the Playwright MCP CLI reference,
2026-08-06. Both move quickly: re-check the tool lists before relying on a "only X can do this" claim.*
