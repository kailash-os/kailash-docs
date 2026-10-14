# ADR-0002 — reference-page naming: "tool - reference" nesting the config page

*Status:* accepted · *Date:* 2026-10-14 · *Deciders:* kailash-docs
maintainers · *Supersedes:* the naming/layout parts of ADR-0001 (its
generation contract, version-lock footnote and coverage invariant carry
forward unchanged)

## Context

ADR-0001 titled every tool page as a man section — `nmap(1) - Kailash
Tool Reference` — and gave tools with config surfaces a second page
filed under a separate flat "Config references" book part. Reviewed
on 2026-10-14, that shape has three defects:

1. The `(1)` suffix is section-number noise: the book numberer already
   prefixes every sidebar entry (`94  nmap(1) — ...`), and section `(1)`
   on a URL-flavoured web page reads as a duplicate numbering system.
2. A separate config part orphans the config pages from their tool:
   a reader lands on `subfinder` and must know to look three parts
   lower for its configuration surfaces.
3. The flat config part also breaks the sidebar ordering contract: a
   config page renders far from the tool it documents.

## Decision

**Every tool page is titled `tool - reference`** (plain name, no `(1)`,
no suffix banner). **The config reference is titled `tool -
configuration` and nests UNDER its tool page** — the tool page is
declared as the part (`- part: reference/tools/<id>.qmd` with the
config page as its single chapter), which the Quarto book renderer
renders as the tool's own sidebar sub-section, collapsible, with the
configuration page inside it. Tools without a config page stay flat
chapters; there is no separate config-references part. Chapter
numbering is off book-wide (`format.html.number-sections: false`).
Layer headers stay as title-only parts ("Layer CLASSIC — tools"), so
the sidebar grouping is headers only, not numbered sections.

## Consequences

- One navigation path per tool: reference first, configuration one
  chevron away under it; the man page's CONFIGURATION section and SEE
  ALSO both link to the nested page.
- The section-number noise disappears from sidebar, breadcrumbs, page
  titles and search results (numbering is renderer-level, so no
  per-page edits were needed for it).
- Layout is a generator invariant: `register_chapters` owns the whole
  region and regenerating converges to this shape from any prior state.
- Cross-links in prose may name the pages; nothing on the live site
  links to the retired flat config part, so no redirects arise.
