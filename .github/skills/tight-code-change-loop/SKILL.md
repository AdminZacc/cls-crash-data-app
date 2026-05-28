---
name: tight-code-change-loop
description: "Use when making small, safe code changes in an existing repository: gather minimal local context, form one falsifiable hypothesis, make the smallest grounded edit, and validate immediately."
---

# Tight Code Change Loop

Use this skill when you need to change code in an existing repository without broad exploration.

## Goal

Make a targeted edit based on nearby evidence, prove it with the cheapest useful validation, and iterate only if the validation changes the hypothesis.

## Workflow

1. Start from the nearest concrete anchor: a failing test, error, file, symbol, or call site.
2. Read only enough nearby code to state one falsifiable local hypothesis.
3. Identify one cheap check that could disconfirm the hypothesis.
4. Make the smallest edit that tests the hypothesis.
5. Run the narrowest validation that exercises the touched behavior.
6. If validation fails, repair the same slice immediately and rerun the same check.
7. If validation succeeds, make only the smallest adjacent follow-up edit needed, then validate again.

## Decision Rules

- Prefer the owning implementation over wiring, wrappers, or registration code.
- If the first candidate path only forwards data, step to the code that actually computes or mutates the behavior.
- If more than one nearby path looks plausible, choose the one that gives the sharpest discriminating check.
- Do not keep exploring once you can name a falsifiable hypothesis, the dependent code path, a cheap check, and a small edit.
- After the first substantive edit, do a focused executable validation before any broader searching or refactoring.

## Quality Checks

- The change is minimal and local to the behavior being fixed.
- The validation directly exercises the touched slice.
- The final result is explainable as a change in control flow, data flow, or validation, not a speculative rewrite.
- Any remaining risk is explicit and narrow.

## Good Prompts

- Fix this bug with the smallest safe change.
- Investigate this failure from the nearest code path.
- Patch the behavior and validate it locally.
- Reduce the search to one falsifiable hypothesis and one cheap check.

## When Not to Use

- Large redesigns that need broader planning.
- Pure brainstorming without a code change goal.
- Tasks that are mostly documentation, product copy, or architecture discussion.
