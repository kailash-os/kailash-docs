# kailash-docs

Kailash OS documentation — a Quarto book (user & administrator guide sections + per-tool reference) published at
**docs.kailash.tools** via GitHub Pages.

- Prose parts: what Kailash is, security & governance of the build,
  administrator operations.
- Per-tool reference: man-style pages for every tool in the catalogue,
  generated from the tool manifest with a version-lock note pinning
  each page to the exact tool version it documents. Each page is titled
  `tool - reference`; the 53 tools with config surfaces also carry a
  `tool - configuration` page nested under the tool in the sidebar
  (ADR-0002).

Content is tracked on the issue tracker (KA-WS-6 and children); the
manifest in `kailash-packages` stays the single source of truth.

Deploy: `.github/workflows/pages.yml` renders the book and publishes
on merges to `main`. Custom domain persisted via the root `CNAME` and
repo Pages settings.

Licensed BSD-3-Clause (see `LICENSE`).
