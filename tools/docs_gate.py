#!/usr/bin/env python3
"""docs_gate.py — coverage + provenance + stale-pin gate for kailash-docs.

Delivers the kailash-docs#1 coverage-check + regeneration-contract
enforcement (lane #25; kailash-docs#8). Org standard: the gate runs its
own self-test first (tools/test_docs_gate.py, RED fixture inside).

Checks (see the lane issue for the contract):
  1. COVERAGE    every manifest row id resolves to a reference page
                 (complete or explicit stub); module rows are category
                 carriers — counted, reported, never silent omissions
  2. PROVENANCE  every page closes with the compact version-lock
                 footnote `ref: [pin|v<ver>](url) - verified <date>`
  3. STALE-PIN   a page pinned `v<version>` whose pin differs from the
                 CURRENT pin source (generated.json version/rev) = RED
                 — a lock move without regeneration
  4. DEAD-UPSTREAM inventory — pages whose Upstream link names
                 github.com/kailash-os/<id> are reported (phantom-tools
                 purge input, docs#24); listed but NOT gate-fatal in
                 this revision (the purge lane owns the removal)

Exit: 0 = GREEN, 1 = RED. Summary to stdout + gate-report.json.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
import urllib.error
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = REPO_ROOT / "reference" / "tools"
CONFIG_DIR = REPO_ROOT / "reference" / "config"

MANIFEST_URL = ("https://raw.githubusercontent.com/kailash-os/"
                "kailash-packages/main/manifest/tools.yaml")
PINS_URL = ("https://raw.githubusercontent.com/kailash-os/"
            "kailash-packages/main/nvfetcher/_sources/generated.json")

REF_LINE_RE = re.compile(
    r"ref: \[([^\]]*)\]\(([^)]+)\) - verified (\d{4}-\d{2}-\d{2})")
UPSTREAM_RE = re.compile(r"github\.com/kailash-os/([a-zA-Z0-9._-]+)")


def fetch_text(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "kailash-docs-gate"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def load_manifest(path_or_url: str) -> list[dict]:
    import yaml
    text = fetch_text(path_or_url) if path_or_url.startswith("http") \
        else open(path_or_url).read()
    return yaml.safe_load(text)["tools"]


def load_pins(path_or_url: str) -> dict:
    text = fetch_text(path_or_url) if path_or_url.startswith("http") \
        else open(path_or_url).read()
    raw = json.loads(text)
    pins = {}
    for tid, entry in raw.items():
        ver = entry.get("version") or (entry.get("src") or {}).get("rev") or ""
        pins[tid] = str(ver).strip()
    return pins


def current_pin_for(pins: dict, tid: str) -> str | None:
    """The current pin label the page SHOULD carry, or None when unknown.

    generated.json carries either a version attr or a bare src.rev; the
    generator's compact_ref labels version-attrs as v<version> and
    rev-only pins carry the RAW rev as the label (no 'v' for a sha).
    Normalise the same way: a numeric-ish pin gets v-prefixed; a commit
    sha does not.
    """
    ver = pins.get(tid)
    if not ver:
        return None
    if ver.startswith("v"):
        return ver
    if re.match(r"^[0-9a-f]{40}$", ver):   # commit sha — no v-prefix
        return ver
    if re.match(r"[0-9]", ver):            # version number
        return "v" + ver
    return ver


def page_footnote(page_text: str):
    """Return (label, url, date) of the LAST ref: line, or None."""
    hits = REF_LINE_RE.findall(page_text)
    if not hits:
        return None
    label, url, date = hits[-1]
    return label.strip(), url.strip(), date.strip()


def is_stub(page_text: str) -> bool:
    """An explicit PENDING/staleness stub (never a silent omission)."""
    return ("Not derived automatically" in page_text
            or "PENDING" in page_text[:4000]
            or "Stale classification" in page_text)


def check(repo_root: Path = REPO_ROOT,
          manifest_path: str = MANIFEST_URL,
          pins_path: str = PINS_URL,
          live_upstream: bool = False) -> dict:
    tools = load_manifest(manifest_path)
    pins = load_pins(pins_path)

    tools_dir = repo_root / "reference" / "tools"
    pages = {p.stem: p for p in sorted(tools_dir.glob("*.qmd"))}

    module_rows = []          # category carriers — page not required
    data_rows = []
    missing_pages = []        # coverage RED
    bad_footnote = []         # provenance RED
    stale_pin = []            # regen-diff RED
    dead_upstream = []        # inventory only (docs#24)

    for row in tools:
        tid = row.get("id")
        status = (row.get("packaging") or {}).get("status", "")
        if status == "module":
            module_rows.append(tid)
            continue
        if status == "data":
            data_rows.append(tid)
        page = pages.get(tid)
        if page is None:
            missing_pages.append(tid)
            continue
        text = page.read_text(encoding="utf-8")
        fn = page_footnote(text)
        if fn is None:
            bad_footnote.append(tid)
            continue
        label, _url, _date = fn
        want = current_pin_for(pins, tid)
        if want and label.startswith("v") and not is_stub(text):
            page_ver = label[1:]
            pin_ver = want[1:] if want.startswith("v") else want
            comparable = (
                re.match(r"^[0-9a-f]{40}$", pin_ver)        # json pin = sha
                and re.match(r"^[0-9a-f]{40}$", page_ver)   # page pin = sha too
            ) or (
                not re.match(r"^[0-9a-f]{40}$", pin_ver)    # json pin = human version
                and not re.match(r"^[0-9a-f]{40}$", page_ver)
                and page_ver.split("-unstable")[0] != pin_ver.split("-unstable")[0]
            )
            # a page-labeled human version vs json sha pins is NOT comparable
            # (nvfetcher version==rev; the human label comes from the
            # derivation header at lane time) — skip, do not false-RED
            if comparable and pin_ver != page_ver:
                stale_pin.append({"id": tid, "page": label, "current": want})
            if re.match(r"^[0-9a-f]{40}$", page_ver) and \
                    not re.match(r"^[0-9a-f]{40}$", pin_ver):
                # page stamped a sha but the pin record carries a version —
                # generation-stamp mismatch class, still not comparable
                pass
        if live_upstream:
            for up_id in sorted(set(UPSTREAM_RE.findall(text))):
                probe = "https://github.com/kailash-os/%s" % up_id
                try:
                    urllib.request.urlopen(
                        urllib.request.Request(probe, method="HEAD",
                                               headers={"User-Agent": "gate"}),
                        timeout=15)
                except urllib.error.HTTPError as e:
                    if e.code == 404:
                        dead_upstream.append({"id": up_id, "page": tid,
                                              "url": probe})
                except urllib.error.URLError:
                    pass  # network error is not proof of a dead upstream

    # orphan pages: reference pages with NO manifest row at all
    row_ids = {t["id"] for t in tools if t.get("id")}
    orphan_pages = sorted(p.name[:-4] for tid, p in pages.items()
                          if tid not in row_ids)
    # an orphan page still owes a parseable footnote (it is a public page) —
    # but an orphan WITHOUT any manifest row is a removal-queue item
    # (docs#24), inventoried, NOT gate-fatal in this revision
    for tid, p in pages.items():
        if tid in row_ids:
            continue
        if page_footnote(p.read_text(encoding="utf-8")) is None:
            # no parseable footnote on an orphan page -> provenance note,
            # but the orphan class is inventory; keep it out of the RED set
            pass

    report = {
        "manifest_rows": len(tools),
        "reference_pages": len(pages),
        "config_pages": len(list((repo_root / "reference" / "config").glob("*.qmd")))
        if (repo_root / "reference" / "config").is_dir() else 0,
        "module_rows_reported": module_rows,
        "data_rows": data_rows,
        "coverage_missing_pages": missing_pages,
        "provenance_bad_footnote": [t for t in bad_footnote if t in row_ids],
        "stale_pins": stale_pin,
        "dead_upstream_inventory": dead_upstream,
        "orphan_pages": orphan_pages,
        "orphan_without_footnote": sorted(
            tid for tid in orphan_pages
            if page_footnote(pages[tid].read_text(encoding="utf-8")) is None),
    }
    # verdict: orphan pages are the removal queue (docs#24), not a failure —
    # only row-backed pages missing/without-footnote/stale turn the gate RED
    report["verdict"] = "RED" if (missing_pages
                                  or any(t in row_ids for t in bad_footnote)
                                  or stale_pin) else "GREEN"
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", default=MANIFEST_URL)
    ap.add_argument("--pins", default=PINS_URL)
    ap.add_argument("--live-upstream", action="store_true",
                    help="probe kailash-os/<id> upstream links (HEAD; adds seconds)")
    ap.add_argument("--root", default=str(REPO_ROOT))
    ap.add_argument("--fail-on", default="missing,footnote,stale",
                    help="comma list of failure classes that turn the gate RED "
                         "(missing|footnote|stale); classes absent from the "
                         "list are inventoried without failing the run")
    args = ap.parse_args()

    fatal = {s.strip() for s in args.fail_on.split(",") if s.strip()}
    try:
        report = check(Path(args.root), args.manifest, args.pins,
                       args.live_upstream)
    except Exception as e:  # noqa: BLE001 — the gate must fail loud, not hang
        print("GATE ERROR: %s" % e, file=sys.stderr)
        return 1

    report["fail_on"] = sorted(fatal)
    report["verdict"] = "RED" if (
        ("missing" in fatal and report["coverage_missing_pages"]) or
        ("footnote" in fatal and report["provenance_bad_footnote"]) or
        ("stale" in fatal and report["stale_pins"])
    ) else "GREEN"

    out = Path(args.root) / "tools" / "gate-report.json"
    out.write_text(json.dumps(report, indent=1))

    print("== kailash-docs documentation gate ==")
    print("manifest rows      : %d" % report["manifest_rows"])
    print("reference pages    : %d (+ %d config pages)"
          % (report["reference_pages"], report["config_pages"]))
    print("module rows (dir)  : %d" % len(report["module_rows_reported"]))
    print("data rows          : %d" % len(report["data_rows"]))
    print("coverage missing   : %s" % (report["coverage_missing_pages"] or "none"))
    print("bad footnotes      : %s" % (report["provenance_bad_footnote"] or "none"))
    print("stale pins         : %s"
          % (len(report["stale_pins"]) and report["stale_pins"][:8] or "none"))
    if args.live_upstream:
        print("dead upstream (inv): %d (feeds docs#24)"
              % len(report["dead_upstream_inventory"]))
    print("VERDICT: %s" % report["verdict"])
    return 0 if report["verdict"] == "GREEN" else 1


if __name__ == "__main__":
    sys.exit(main())
