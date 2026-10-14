#!/usr/bin/env python3
"""Generate every per-tool reference page from the offline input store.

Inputs (offline store, produced by the batch-fetch step):
  store/manifest-tools.yaml      - the manifest rows (source of truth)
  store/nvfetcher-sources.json   - pinned revs/dates for bespoke tools
  store/derivation-headers/*.nix - per-tool derivation (version attr)
  store/tools/<id>.md            - upstream README (when upstream has one)
  store/meta.json                - manifest git sha + fetch date

Outputs: reference/tools/<id>.qmd (one per non-module row) + a
generation report printed to stdout. Fully offline. Pages carry the
compact version-lock line: `ref: [pin](url) - verified <date>` per
KA-WS-6.10 (user 2026-10-14).

Row-shaped exceptions (ADR-0001): module rows are NOT per-tool pages
(their category anchor in the directory covers them); data-pack rows
render as data-bundle pages without synopsis/options; stale rows get
a staleness banner.
"""
from pathlib import Path
import os
import re
import json
import argparse
import datetime
from collections import OrderedDict

try:
    import yaml
except ImportError:
    raise SystemExit('PyYAML required at generation time')

STORE_DEFAULT = (Path(__file__).resolve().parent.parent / 'inputs' / 'store')
if not STORE_DEFAULT.is_dir():
    raise SystemExit(
        '%s: input store not found — pass --store explicitly '
        '(generation inputs live outside the repo by design; see README)' % STORE_DEFAULT)

LAYER_ORDER = ['CLASSIC', 'ATTACK', 'DEFENCE', 'OPS']


def sanitize_links(text, upstream_url):
    """Upstream READMEs often link relative files (demo/README.md,
    CONTRIBUTORS.md) that do not exist in this repo. Rewrite any
    relative link target against the upstream repo so nothing dangles."""
    if not text or not upstream_url:
        return text
    base = upstream_url.rstrip('/')
    def repl(m):
        target = m.group(1)
        stripped = target.strip()
        if (stripped.startswith(('http://', 'https://', 'mailto:', '#'))
                or stripped.endswith(('.html', '.qmd'))
                or stripped.startswith('../tools/')):
            return m.group(0)
        # link to the file on the upstream default branch view of the repo tree
        return f']({base}/tree/HEAD/{stripped.lstrip("./")})'
    return re.sub(r']\(((?!http)[^)#\s]+\.md)\)', lambda m: repl(m) if '/' in m.group(1) or m.group(1).endswith('.md') else m.group(0), text)


def md_paragraphs(markdown_text, limit_paragraphs=2, max_chars=700):
    """First meaningful paragraphs of a README: strip badges/images/html."""
    lines = []
    for line in markdown_text.splitlines():
        s = line.strip()
        if (not s
                or s.startswith(('#', '[!', '<', '|', '---', '```', '!['))
                or re.match(r'^\[\!+', s)
                or re.match(r'^\[!\[', s)
                or (s.startswith('[') and '](' in s and s.endswith(')') and len(s) < 120)):
            continue
        lines.append(line)
    paras, cur = [], []
    for line in lines:
        if line.strip() == '':
            if cur:
                paras.append(' '.join(p.strip() for p in cur))
                cur = []
                if len(paras) >= limit_paragraphs:
                    break
        else:
            cur.append(line)
    if cur and len(paras) < limit_paragraphs:
        paras.append(' '.join(p.strip() for p in cur))
    out = []
    total = 0
    for p in paras:
        if len(p) < 40:
            continue
        out.append(p)
        total += len(p)
        if total >= max_chars:
            break
    return ' '.join(out)[:max_chars]


def md_code_blocks(markdown_text, max_blocks=2, max_lines=12):
    blocks = []
    in_block = False
    cur = []
    for line in markdown_text.splitlines():
        if line.strip().startswith('```'):
            if in_block:
                if 1 <= len(cur) <= max_lines and len(cur) >= 1:
                    joined = '\n'.join(cur)
                    # usage-shaped blocks only (mentions the tool or looks commandy)
                    if ('--' in joined or 'usage' in joined.lower()
                            or '$' in joined or len(cur) >= 1):
                        blocks.append(joined)
                cur = []
                in_block = False
                if len(blocks) >= max_blocks:
                    break
            else:
                in_block = True
        elif in_block:
            cur.append(line)
    return blocks


def md_option_lines(markdown_text, max_items=15):
    """Detect option-style bullets: '  - --flag ...' or '- `--flag` ...'."""
    opts = []
    for line in markdown_text.splitlines():
        m = re.match(r'\s*-+\s+`?(--[a-zA-Z][\w-]*(?:,?\s+-[a-zA-Z])?)`?\s*[:\-]+?\s*(.+)',
                     line)
        if not m:
            m = re.match(r'\s*-\s+`(--[a-zA-Z][\w-]*)`?\s*[-:]?\s*(.*)', line)
        if m:
            flag, desc = m.group(1).strip(), (m.group(2) or '').strip()[:110]
            if desc and flag.startswith('--'):
                opts.append((flag, desc))
        if len(opts) >= max_items:
            break
    return opts if len(opts) >= 3 else []


def parse_version_from_nix(nix_text):
    m = re.search(r'version\s*=\s*"([^"]+)"', nix_text)
    return m.group(1) if m else None


def compact_ref(version, pin_url, verified_at):
    label = f'v{version}' if version and not version.startswith('v') else (version or 'pin')
    return f'ref: [{label}]({pin_url}) - verified {verified_at}'


def build(store):
    meta = json.load(open(os.path.join(store, 'meta.json')))
    tools = yaml.safe_load(open(os.path.join(store, 'manifest-tools.yaml')))['tools']
    nv = json.load(open(os.path.join(store, 'nvfetcher-sources.json')))
    verified_at = meta.get('fetched_at_utc', '')[:10]
    manifest_sha = meta.get('manifest_git_sha', '')
    MANIFEST_ROW_URL = ('https://github.com/kailash-os/kailash-packages/blob/main/'
                        'manifest/tools.yaml')
    PKG_URL_T = 'https://github.com/kailash-os/kailash-packages/blob/main/nvfetcher/_sources/generated.nix'

    versions = {}
    for tid, e in nv.items():
        versions[tid] = (e.get('version') or e.get('src', {}).get('rev') or '').strip()
    dh_dir = os.path.join(store, 'derivation-headers')
    if os.path.isdir(dh_dir):
        for fname in os.listdir(dh_dir):
            if not fname.endswith('.nix'):
                continue
            tid = fname[:-4]
            v = parse_version_from_nix(open(os.path.join(dh_dir, fname)).read())
            if v:
                # human-readable derivation version wins over the bare rev
                versions[tid] = v

    out_dir_page = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                '..', 'reference', 'tools')
    os.makedirs(out_dir_page, exist_ok=True)

    written, skipped_module, stale_rows, data_rows, readme_used = [], [], [], [], []
    layer_groups = OrderedDict((l, []) for l in LAYER_ORDER)

    for t in tools:
        tid = t['id']
        layer = t['layer']
        status = (t.get('packaging') or {}).get('status', '')
        if status == 'module':
            skipped_module.append(tid)
            continue
        safety = (t.get('safety') or {}).get('level', '?')
        cat = t['category']
        src = t.get('source') or {}
        vcs_owner, repo = src.get('vcs_owner'), src.get('repo')
        upstream = src.get('vcs_url') or (f'https://github.com/{vcs_owner}/{repo}'
                                          if vcs_owner and repo else None)
        licence = t.get('license') or ''
        desc = t.get('description') or t.get('name') or tid

        readme_read = ''
        rp = os.path.join(store, 'tools', tid + '.md')
        if os.path.exists(rp):
            try:
                readme_read = open(rp, encoding='utf-8', errors='replace').read()
                readme_read = sanitize_links(readme_read, upstream)
                readme_used.append(tid)
            except Exception:
                readme_read = ''

        is_data = (status == 'data')
        if is_data:
            data_rows.append(tid)
        if 'stale' in (status or ''):
            stale_rows.append(tid)

        pin_url = PKG_URL_T if status == 'bespoke' else MANIFEST_ROW_URL
        version = versions.get(tid) or None

        lines = []
        lines.append('---')
        lines.append(f'title: "{tid}(1) - Kailash Tool Reference"')
        lines.append('listing: tools') if False else None
        lines.append('---')
        lines.append('')
        lines.append(f'## {tid}')
        lines.append('')
        lines.append(f'> **{tid}** - {desc}')
        lines.append('')
        lines.append('| | |')
        lines.append('|---|---|')
        lines.append(f'| Layer | {layer} |')
        lines.append(f'| Category | [{cat}](../directory.qmd#cat-{cat}) |')
        lines.append(f'| Safety class | {safety} |')
        if licence:
            lines.append(f'| Licence | {licence} |')
        if upstream:
            lines.append(f'| Upstream | [{upstream.replace("https://", "")}]({upstream}) |')
        if is_data:
            lines.append('| Row kind | data pack (bundle description, not an invocation surface) |')
        lines.append('')

        if 'stale' in (status or ''):
            lines.append('::: {.callout-warning}')
            lines.append('## Stale classification')
            lines.append('This row is classed stale in the manifest at generation')
            lines.append('time - check upstream status before relying on it.')
            lines.append(':::')
            lines.append('')

        lines.append('### NAME')
        lines.append('')
        lines.append(f'`{tid}` - {desc}')
        lines.append('')

        if not is_data:
            blocks = md_code_blocks(readme_read) if readme_read else []
            if blocks:
                lines.append('### SYNOPSIS & usage')
                lines.append('')
                lines.append('*Derived from the upstream README at generation')
                lines.append('time; verify against `--help` where the tool is')
                lines.append('installed.*')
                lines.append('')
                for b in blocks:
                    lines.append('```')
                    lines.append(b)
                    lines.append('```')
                    lines.append('')
            elif upstream:
                lines.append('### SYNOPSIS')
                lines.append('')
                lines.append(f'Not derived automatically - see [upstream '
                             f'documentation]({upstream}). This page does not')
                lines.append('hand-copy flags (generation contract, ADR-0001).')
                lines.append('')

            if readme_read:
                dsc = md_paragraphs(readme_read)
                if dsc:
                    lines.append('### DESCRIPTION (upstream)')
                    lines.append('')
                    lines.append(dsc)
                    lines.append('')

            opts = md_option_lines(readme_read) if readme_read else []
            if opts:
                lines.append('### OPTIONS (upstream README)')
                lines.append('')
                lines.append('| Flag | Meaning |')
                lines.append('|---|---|')
                for flag, meaning in opts:
                    lines.append(f'| `{flag}` | {meaning} |')
                lines.append('')

            # config-surface detection (ADR-0001 config-page policy, first pass)
            if readme_read:
                cfg_hits = re.findall(
                    r'(/etc/[\w./-]+|[\w.-]+\.ya?ml|[\w.-]+\.conf\b|'
                    r'environment variables?|--config\b)',
                    readme_read)
                if len(cfg_hits) >= 2:
                    lines.append('### CONFIGURATION (detected)')
                    lines.append('')
                    lines.append(f'Config-surface markers detected in the upstream')
                    lines.append(f'README ({len(cfg_hits)} matches, e.g. '
                                 f'`{cfg_hits[0]}`, `{cfg_hits[1] if len(cfg_hits) > 1 else ""}`).')
                    lines.append('A full config reference page for this tool is')
                    lines.append('queued under the config-page policy — this line')
                    lines.append('is the detection record, not the page.')
                    lines.append('')

        lines.append('### SEE ALSO')
        lines.append('')
        lines.append(f'- Category: [{cat}](../directory.qmd#cat-{cat}) in the')
        lines.append('  category directory (sister tools listed there).')
        cfg_page = os.path.join(os.path.dirname(out_dir_page), 'config',
                                tid + '.qmd')
        if os.path.exists(cfg_page):
            lines.append(f'- [Configuration reference]({'../config/' + tid + ".qmd"}) '
                         '— files, environment variables, samples.')
        lines.append('')

        lines.append('---')
        lines.append('')
        lines.append(compact_ref(version, pin_url, verified_at))
        lines.append('')

        page = '\n'.join(lines)
        with open(os.path.join(out_dir_page, tid + '.qmd'), 'w',
                  encoding='utf-8') as fh:
            fh.write(page)
        written.append(tid)
        layer_groups[layer].append(tid)

    report = {
        'generated_pages': len(written),
        'module_rows_skipped': len(skipped_module),
        'data_rows': len(data_rows),
        'stale_rows': len(stale_rows),
        'readme_used': len(readme_used),
        'manifest_only': len(written) - len(readme_used),
        'manifest_sha': manifest_sha,
        'verified_at': verified_at,
    }
    return report, layer_groups, out_dir_page, skipped_module


def register_chapters(out_dir, layer_groups):
    """Register generated pages in _quarto.yml as top-level parts:
    Part III (directory/coverage/exemplar), tool layer parts, and a
    config-references part for any existing reference/config pages.
    This function is the SOLE writer of the reference region — run it
    last in any regen (or alone); order converges."""
    yml_p = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         '..', '_quarto.yml')
    yml = open(yml_p).read()
    start = yml.index('    - part: "Part III')
    end = yml.index('    - part: "Part IV')
    head = yml[:start]
    head += '    - part: "Part III — Tool reference"\n'
    head += '      chapters:\n'
    head += '        - reference/directory.qmd\n'
    head += '        - reference/coverage.qmd\n'
    head += '        - reference/garak.qmd\n'
    n = 0
    for layer, tids in layer_groups.items():
        if not tids:
            continue
        head += f'    - part: "Tools — Layer {layer}"\n'
        head += '      chapters:\n'
        for tid in sorted(tids):
            head += f'        - reference/tools/{tid}.qmd\n'
            n += 1
    # config pages: discovered, machine-owned, idempotent
    ref_root = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            '..', 'reference')
    cfg_pages = sorted(f[:-4] for f in os.listdir(os.path.join(ref_root, 'config'))
                       if f.endswith('.qmd')) if os.path.isdir(os.path.join(ref_root, 'config')) else []
    if cfg_pages:
        head += '    - part: "Tools — Config references"\n'
        head += '      chapters:\n'
        for tid in cfg_pages:
            head += f'        - reference/config/{tid}.qmd\n'
    new_yml = head + yml[end:]
    open(yml_p, 'w').write(new_yml)
    print(f'registered {n} tool chapters + {len(cfg_pages)} config chapters in _quarto.yml')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--store', default=STORE_DEFAULT)
    a = ap.parse_args()
    report, layer_groups, out_dir, skipped = build(os.path.abspath(a.store))
    register_chapters(out_dir, layer_groups)
    print(json.dumps(report, indent=1))
    for layer, tids in layer_groups.items():
        print(f'  {layer}: {len(tids)} pages')
    json.dump({'skipped_module_rows': skipped},
              open('/tmp/gen-skip-report.json', 'w'))


if __name__ == '__main__':
    main()
