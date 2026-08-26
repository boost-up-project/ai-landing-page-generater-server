# AI Landing Page Generator Server

## Architecture

- Organize application code by domain: `brand`, `campaign`, and `persona`.
- Keep routers, schemas, services, prompts, and output templates inside their owning
  domain.
- Put only genuinely domain-independent behavior in `app/common`. PDF parsing is the
  current shared capability.
- Put cross-domain sequencing in `app/workflows`; domains must not orchestrate one
  another directly.
- Put application configuration and infrastructure-wide concerns in `app/core`.

## AI and Markdown contracts

- Prefer Gemini structured output validated by Pydantic over free-form Markdown.
- Runtime prompts belong in `<domain>/prompts`, not in `.gemini`.
- Runtime Markdown layouts belong in `<domain>/templates`, not in `.gemini`.
- Product-facing output specifications belong in `docs/output-specs`.
- When an output contract changes, update its schema, prompt, template, specification,
  and tests together.

## Verification

- Run `uv run pytest` after behavior or structure changes.
- Run `uv run ruff check .` after Python changes.
