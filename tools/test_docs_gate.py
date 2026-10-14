#!/usr/bin/env python3
"""Self-test for docs_gate.py — RED fixture + GREEN assertion, no network.

Org TDD standard (failing test first): the test builds a toy repo-tree
(two manifest rows, one complete page, one stub, one stale-pin page,
one missing page) and asserts the gate's verdicts. Run on the lane box:
    python3 tools/test_docs_gate.py
"""
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import docs_gate  # noqa: E402

FIXTURE_MANIFEST = """\
schema_version: 1
tools:
  - id: alpha
    layer: CLASSIC
    category: c-01-information-gathering
    name: alpha
    description: "Test tool alpha."
    license: MIT
    packaging:
      status: bespoke
    safety:
      level: safe
  - id: beta
    layer: CLASSIC
    category: c-01-information-gathering
    name: beta
    description: "Test tool beta."
    license: MIT
    packaging:
      status: native
    safety:
      level: safe
  - id: gamma
    layer: OPS
    category: o-02-compute-serving-infrastructure
    name: gamma
    description: "Test data row."
    license: MIT
    packaging:
      status: data
    safety:
      level: safe
  - id: carrier
    layer: OPS
    category: o-02-compute-serving-infrastructure
    name: carrier
    description: "Module carrier row."
    license: MIT
    packaging:
      status: module
    safety:
      level: safe
"""

FIXTURE_PINS = json.dumps({
    "alpha": {"version": "1.2.3"},
    "beta": {"version": "2.0.0"},
    "gamma": {"version": "0.1.0"},
})

COMPLETE_PAGE = """---
title: "alpha(1) - Kailash Tool Reference"
---

## alpha

> **alpha** - Test tool alpha.

| | |
|---|---|
| Layer | CLASSIC |

### NAME

`alpha` - Test tool alpha.

---

ref: [v1.2.3](https://github.com/kailash-os/kailash-packages/blob/main/nvfetcher/_sources/generated.nix) - verified 2026-10-14
"""

STUB_PAGE = """---
title: "gamma(1) - Kailash Tool Reference"
---

## gamma

> **gamma** - Test data row.

### SYNOPSIS

Not derived automatically - see upstream documentation. This page does
not hand-copy flags (generation contract, ADR-0001).

---

ref: [pin](https://github.com/kailash-os/kailash-packages/blob/main/manifest/tools.yaml) - verified 2026-10-14
"""

STALE_PAGE = """---
title: "beta(1) - Kailash Tool Reference"
---

## beta

> **beta** - Test tool beta.

---

ref: [v1.0.0](https://github.com/kailash-os/kailash-packages/blob/main/nvfetcher/_sources/generated.nix) - verified 2026-10-13
"""

NOFOOT_PAGE = """---
title: "orphan(1)"
---

## orphan

A page with no ref footnote at all.
"""


def build_tree(stale: bool) -> Path:
    root = Path(tempfile.mkdtemp(prefix="gate-fixture-"))
    (root / "reference" / "tools").mkdir(parents=True)
    (root / "reference" / "config").mkdir(parents=True)
    (root / "reference" / "tools" / "alpha.qmd").write_text(COMPLETE_PAGE)
    (root / "reference" / "tools" / "gamma.qmd").write_text(STUB_PAGE)
    if stale:
        (root / "reference" / "tools" / "beta.qmd").write_text(STALE_PAGE)
    else:
        (root / "reference" / "tools" / "beta.qmd").write_text(
            STALE_PAGE.replace("v1.0.0", "v2.0.0").replace(
                "2026-10-13", "2026-10-14"))
    (root / "reference" / "tools" / "orphan.qmd").write_text(NOFOOT_PAGE)
    mf = root / "manifest-fixture.yaml"
    mf.write_text(FIXTURE_MANIFEST)
    pf = root / "pins-fixture.json"
    pf.write_text(FIXTURE_PINS)
    return root


def main() -> int:
    ok = True

    # RED case: stale page must turn the gate RED + list the stale pin
    root = build_tree(stale=True)
    rep = docs_gate.check(root, str(root / "manifest-fixture.yaml"),
                          str(root / "pins-fixture.json"))
    if rep["verdict"] != "RED":
        print("FAIL: expected RED verdict with a stale page, got %s"
              % rep["verdict"]); ok = False
    if not any(s["id"] == "beta" for s in rep["stale_pins"]):
        print("FAIL: stale_pins should name beta: %s" % rep["stale_pins"]); ok = False
    if rep["coverage_missing_pages"]:
        # every non-module row has a page in the fixture -> must be empty
        print("FAIL: coverage missing should be empty: %s"
              % rep["coverage_missing_pages"]); ok = False
    # orphan page: inventoried, NOT in the row-backed RED set
    if "orphan" in rep["provenance_bad_footnote"]:
        print("FAIL: orphan must not turn the gate RED via provenance: %s"
              % rep["provenance_bad_footnote"]); ok = False
    if set(rep["module_rows_reported"]) != {"carrier"}:
        print("FAIL: module row reporting: %s" % rep["module_rows_reported"]); ok = False
    if set(rep["data_rows"]) != {"gamma"}:
        print("FAIL: data row reporting: %s" % rep["data_rows"]); ok = False
    if "orphan" not in rep["orphan_pages"]:
        print("FAIL: orphan page must be listed (no manifest row): %s"
              % rep["orphan_pages"]); ok = False
    if "orphan" not in rep["orphan_without_footnote"]:
        print("FAIL: orphan page owes a footnote record in orphan_without_footnote: %s"
              % rep["orphan_without_footnote"]); ok = False
    # orphan bad-footnote must NOT leak into the row-backed RED set
    if "orphan" in rep["provenance_bad_footnote"]:
        print("FAIL: orphan must not turn the gate RED via provenance: %s"
              % rep["provenance_bad_footnote"]); ok = False

    # GREEN case: after 'regen' (stale pin corrected), the gate is GREEN
    root = build_tree(stale=False)
    rep2 = docs_gate.check(root, str(root / "manifest-fixture.yaml"),
                           str(root / "pins-fixture.json"))
    if rep2["verdict"] != "GREEN":
        print("FAIL: expected GREEN after regen, got %s (stale=%s bad=%s)"
              % (rep2["verdict"], rep2["stale_pins"],
                 rep2["provenance_bad_footnote"])); ok = False
    if "orphan" in rep2["orphan_pages"]:
        # the orphan page has no manifest row; it stays an inventory item
        pass

    shutil.rmtree(root, ignore_errors=True)
    print("SELF-TEST: %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
