# ADR-0001 — reference-page template & the generation contract

*Status:* accepted · *Date:* 2026-10-14 · *Deciders:* kailash-docs
maintainers
*Acceptance sample:* the garak man-style page posted for review on
[kailash-website#30 (comment)](https://github.com/kailash-os/kailash-website/issues/30#issuecomment-6122448509)
(retired from the shipped site 2026-10-14 — the sample lives in the
review thread and the template; generated pages are the live form).
Page naming/layout was superseded by ADR-0002 on 2026-10-14
(`tool - reference` / `tool - configuration`, config nested under the
tool, no section numbering); the generation contract below stands.

## Context

`docs.kailash.tools` will carry one man-style reference page per tool
in the Kailash catalogue — 337 rows across 32 categories at the
2026-10 census. Hand-writing them is unmaintainable and untruthful at
that scale: upstream `--help` quality varies widely, flags drift, and
a hand-copied page lies the first time upstream moves. The catalogue
of record is the tool manifest (single source of truth; six consumer
views). The guide is one of those views, so page generation must obey
the same rules the other views already do.

Two further constraints decided at the 2026-10-14 window review:

1. **Version-lock footnote** — every page must state the exact pinned
   tool version it was written against (user decision), so a page is
   bound to a tool version; regeneration obligations then follow from
   lock movement, mechanically checkable.
2. **Per-tool config references** — tools that honour config files or
   environment variables get a second page; the man page itself must
   stay an invocation reference, not grow a config dump.

## Decision

**Generated, never hand-maintained.** Reference pages derive from the
tool's manifest row plus the packaged tool's own interface
(`--help`/CLI source). Upstream drift is answered by regeneration,
never by editing a page. Hand prose is confined to review-gated
sections.

**Fixed page template** (mirrors the acceptance sample):

1. Header block, entirely manifest-derived: name + one-line
   description, layer/category, **safety class**, licence, menu
   entry, upstream/doc links.
2. NAME — one line (manifest description extended only by reviewed
   prose).
3. SYNOPSIS / OPTIONS / COMMANDS — derived from the packaged tool's
   `--help` at generation time. Where parsing is unreliable the
   section degrades gracefully: link upstream docs, never hand-copy
   flags into source. Deprecation notes seen in upstream help carry
   through.
4. DESCRIPTION / EXAMPLES / SEE ALSO — curated, review-gated prose:
   never silently generated, never shipped unreviewed.
5. FILES / DIAGNOSTICS — derived-or-stubbed: render what the tool's
   own docs/interfaces state, else an explicit stub line.
6. **Version-lock footnote (required on every page)** — one compact
   line, hyperlink-first (KA-WS-6.10, user 2026-10-14):

   `ref: [v<pin>](<pin-url>) - verified <date>`

   The link targets the pin record that produced the page
   (nvfetcher `generated.nix` for bespoke tools, the manifest row
   otherwise). Gate-side data (pin source, smoke status) is tracked
   by the CI provenance check — the reader sees only the line.

7. **SEE ALSO** links sister tools in the same category and the
   category page.

**Config-page policy.** A tool gets a second page
(`reference/<tool>/config.qmd`) when its manifest row or interface
shows it honours config files or environment variables. The page
holds full sample configs, option-file formats and env-var tables;
the man page STAYS invocation-only and links to it. Tools without
config surfaces get no page (no empty stubs). Detection is automated
in the generator; policy disputes resolve on the exemplar's pattern.

**Regeneration contract (red-regenerate events).** A page is stale
when the pin its footnote links no longer matches the lock:
any `flake.lock` bump, lock-bump release, or per-tool renovate bump
that moves a tool's version is a red-regenerate event — the affected
pages regenerate **in the same change**, enforced by the coverage /
provenance CI gate. Per-release and per-bump obligations ledger on
the standing upkeep issue; the gate is the enforcement, the ledger
is the human-readable record.

**Coverage invariant.** "Every enabled tool on a profile has a
complete page" is checked at build time. Tools without complete
derived content render explicit `PENDING` stubs (blocking reason +
follow-up link) — never silent omissions. Row-shaped exceptions the
generator must handle: data-pack rows render as data-bundle
descriptions, category-module rows render as category overview
pages, stale-classified rows carry an explicit staleness banner
under a published rule.

**Part III publication rule.** The reference part publishes only
pages the contract guarantees. Until the generator + gate land, the
part carries the exemplar and the coverage page — not a partial
hand-written section.

## Consequences

- Trustworthy at scale: page count is a build fact, not an aspiration;
  the CI gate proves coverage and provenance every PR.
- Upstream `--help` quality bounds page quality; the degradation
  ladder (derive → link upstream → stub-with-reason) keeps pages
  honest rather than plausible-looking.
- Every lock-bump PR now carries a page-regen obligation — accepted
  as the standing cost of version-locked documentation
  (small: only version-moved tools regenerate).
- The exemplar (garak) defines the acceptance shape; template
  wording/layout tweaks resolve against it in review.
