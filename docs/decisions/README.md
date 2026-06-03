---
title: Architecture Decision Records (ADRs)
description: Registro permanente de decisiones técnicas con consecuencias.
last_updated: 2026-05-04
---

# Architecture Decision Records

We follow [MADR](https://adr.github.io/madr/) (Markdown Any Decision Record) format. Every irreversible or hard-to-reverse architectural decision lives here as a numbered file.

## Index

| ID | Title | Status | Date |
|---|---|---|---|
| [0001](0001-stack-django-react.md) | Stack: Django + DRF + React + Vite | Accepted | 2026-05-04 |
| [0002](0002-staging-deploy-contract.md) | Staging deploy contract & merging foundational high-risk infra during ramp-up | Accepted | 2026-06-03 |

## Rules

- **Numbering is permanent.** Never renumber, never reuse. A retired ADR keeps its number with `Status: superseded by NNNN`.
- **An ADR is created when:** an answer to a `Question` ticket commits us to a path that's hard to reverse, OR the Architect agent makes an architectural choice that affects more than one bounded context.
- **An ADR is NOT created for:** library version bumps, code style decisions (those go to `golden-principles.md`), or revisable choices.
- **The Consultant Resolver writes ADRs** automatically when a `Question` is closed with a strategic decision. Drafts are reviewed by Sebas before merge.

## When to read an ADR

The Architect and Spec Writer agents read ADRs newer than 90 days as part of their always-read set. Older ADRs are read only when a ticket explicitly proposes to revisit them.
