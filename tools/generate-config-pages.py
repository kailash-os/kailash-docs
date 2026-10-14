#!/usr/bin/env python3
"""Generate per-tool config reference pages from the offline store.

Delivers the second page required by the ADR-0001 config-page policy:
tools whose upstream docs show real config surfaces (>= 3 markers:
config file paths, yaml/conf files, env vars, --config flags) get
reference/config/<id>.qmd — full env-var table, config-file paths with
context, and README-derived sample blocks. The man page stays
invocation-only and links here (the tool-pages generator emits that
link when the config page exists).

Page yml registration is owned by generate-tool-pages.py
register_chapters() (single-writer); per ADR-0002 the config page
nests under its tool page — "tool - reference" opens a sub-section
with "tool - configuration" inside.
"""
import os
import re
import json
import argparse
import datetime

try:
    import yaml
except ImportError:
    raise SystemExit('PyYAML required at generation time')

STORE_DEFAULT = os.path.expanduser(
    '~/.hermes/profiles/satyayuga-cloud/cache/scratch/kailash-guide-inputs')

CFG_RE = (r'(/etc/[\w./-]+|[\w.-]+\.ya?ml|[\w.-]+\.conf\b|'
          r'environment variables?|--config\b)')
ENV_RE = re.compile(r'\b([A-Z][A-Z0-9_]{3,})\b')


def uniq(seq, keep_first=12):
    out = []
    for x in seq:
        if x not in out:
            out.append(x)
        if len(out) >= keep_first:
            break
    return out


def env_vars_with_context(md, max_vars=10):
    """Env-var-looking tokens (KEY/TOKEN/URL/PATH suffix shape) with context."""
    seen, rows = set(), []
    for m in ENV_RE.finditer(md):
        var = m.group(1)
        if var in seen or var in {'README', 'LICENSE', 'WARNING', 'NOTE',
                                  'TODO', 'HTTP', 'HTTPS', 'JSON', 'UTF',
                                  'URL', 'API', 'GPU', 'CPU', 'SDR', 'CSV',
                                  'JSONL', 'XML', 'HTML', 'YAML', 'PATH'}:
            continue
        # require a config-ish suffix or an immediately preceding `export`
        before = md[max(0, m.start() - 8):m.start()]
        if not (re.search(r'_(KEY|TOKEN|URL|HOST|PATH|DIR|HOME|NAME|TYPE|MODE|ENDPOINT|KEYS)$', var)
                or before.strip().endswith('export')):
            continue
        ctx = md[max(0, m.start() - 60):m.end() + 60].replace('\n', ' ').strip()
        seen.add(var)
        rows.append((var, ctx[:130]))
        if len(rows) >= max_vars:
            break
    return rows


def config_paths(md, max_paths=10):
    """Real config-file paths only: never URL fragments."""
    rows = []
    for m in re.finditer(r'(?<![\w/])((?:/etc/[\w./-]+)|(?<![:/\w])~?/?[\w][\w./-]*\.ya?ml|(?<![:/\w])~?/?[\w][\w./-]*\.conf)\b',
                         md):
        p = m.group(1)
        # part of a URL? (preceded by '/' from a scheme, or contains a domain)
        pre = md[max(0, m.start() - 10):m.start()]
        if '//' in p or '://' in pre[-6:] or 'github' in p or 'workflows' in p:
            continue
        if p in [r[0] for r in rows]:
            continue
        rows.append((p, md[max(0, m.start() - 50):m.end() + 70].replace('\n', ' ').strip()[:120]))
        if len(rows) >= max_paths:
            break
    return rows


def sample_blocks(md, max_blocks=2):
    blocks, in_block, cur = [], False, []
    for line in md.splitlines():
        if line.strip().startswith('```'):
            if in_block:
                joined = '\n'.join(cur).strip()
                if joined and re.search(r'config|yaml|conf|env|key\s*:', joined, re.I) \
                        and 1 <= len(cur) <= 20:
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


def main():
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--store', default=STORE_DEFAULT)
    a = ap.parse_args()
    store = os.path.abspath(a.store)

    meta = json.load(open(os.path.join(store, 'meta.json')))
    tools = yaml.safe_load(open(os.path.join(store, 'manifest-tools.yaml')))['tools']
    nv = json.load(open(os.path.join(store, 'nvfetcher-sources.json')))
    verified_at = meta.get('fetched_at_utc', '')[:10]
    MANIFEST_ROW_URL = ('https://github.com/kailash-os/kailash-packages/blob/main/'
                        'manifest/tools.yaml')
    PKG_URL_T = ('https://github.com/kailash-os/kailash-packages/blob/main/'
                 'nvfetcher/_sources/generated.nix')

    versions = {}
    for tid, e in nv.items():
        versions[tid] = (e.get('version') or e.get('src', {}).get('rev') or '').strip()
    dh_dir = os.path.join(store, 'derivation-headers')
    if os.path.isdir(dh_dir):
        for fname in os.listdir(dh_dir):
            if fname.endswith('.nix'):
                m = re.search(r'version\s*=\s*"([^"]+)"',
                              open(os.path.join(dh_dir, fname)).read())
                if m:
                    versions[fname[:-4]] = m.group(1)

    out_dir = os.path.join('..', 'reference', 'config')
    os.makedirs(out_dir, exist_ok=True)

    made, layer_counts = [], {}
    for t in tools:
        tid = t['id']
        status = (t.get('packaging') or {}).get('status', '')
        if status == 'module':
            continue
        rp = os.path.join(store, 'tools', tid + '.md')
        if not os.path.exists(rp):
            continue
        md = open(rp, encoding='utf-8', errors='replace').read()
        markers = len(re.findall(CFG_RE, md))
        if markers < 3:
            continue

        env_rows = env_vars_with_context(md)
        path_rows = config_paths(md)
        blocks = sample_blocks(md)
        safety = (t.get('safety') or {}).get('level', '?')
        cat = t['category']
        src = t.get('source') or {}
        upstream = src.get('vcs_url') or (
            f"https://github.com/{src.get('vcs_owner')}/{src.get('repo')}"
            if src.get('vcs_owner') and src.get('repo') else None)
        pin_url = PKG_URL_T if status == 'bespoke' else MANIFEST_ROW_URL
        version = versions.get(tid)

        lines = ['---', f'title: "{tid} - configuration"', '---', '']
        lines.append(f'Configuration surfaces for [{tid}](../tools/{tid}.qmd)')
        lines.append(f'(safety class: {safety}; category: [{cat}](../directory.qmd#cat-{cat})) —')
        lines.append(f'detected from the upstream documentation at generation')
        lines.append(f'time ({markers} config-surface markers). The invocation')
        lines.append('reference stays on the main tool page.')
        lines.append('')

        lines.append('## Configuration files')
        lines.append('')
        if path_rows:
            lines.append('| Path | Context |')
            lines.append('|---|---|')
            for p, ctx in path_rows:
                lines.append(f'| `{p}` | {ctx} |')
        else:
            lines.append('No config-file paths surfaced in the upstream README')
            lines.append('at generation time — the tool likely takes options')
            lines.append('through flags or environment instead; see upstream.')
        lines.append('')

        lines.append('## Environment variables')
        lines.append('')
        if env_rows:
            lines.append('| Variable | Upstream context |')
            lines.append('|---|---|')
            for var, ctx in env_rows:
                lines.append(f'| `{var}` | {ctx} |')
            lines.append('')
            lines.append('*Names extracted heuristically from upstream docs —')
            lines.append('verify each against the tool\'s own docs before use.*')
        else:
            lines.append('None surfaced in the upstream README at generation time.')
        lines.append('')

        if blocks:
            lines.append('## Sample configuration (upstream)')
            lines.append('')
            for b in blocks:
                lines.append('```')
                lines.append(b)
                lines.append('```')
                lines.append('')

        lines.append('---')
        lines.append('')
        label = (f'v{version}' if version and not str(version).startswith('v')
                 else (version or 'pin'))
        lines.append(f'ref: [{label}]({pin_url}) - verified {verified_at}')
        lines.append('')

        with open(os.path.join(out_dir, tid + '.qmd'), 'w', encoding='utf-8') as fh:
            fh.write('\n'.join(lines))
        made.append(tid)
        layer_counts[t['layer']] = layer_counts.get(t['layer'], 0) + 1

    # yml registration is SOLELY owned by generate-tool-pages.py
    # register_chapters() — it discovers reference/config/*.qmd and
    # writes the same "Tools — Config references" part. This script
    # never touches _quarto.yml (single-writer = no order dependence).

    # man-page cross-links are owned by generate-tool-pages.py
    # (it annotates a tool page iff reference/config/<id>.qmd exists).
    # Run order for a full regen: generate-config-pages.py FIRST, then
    # generate-tool-pages.py, then generate-category-directory.py —
    # all idempotent; regenerating tool pages alone keeps the links.

    print(json.dumps({
        'config_pages': len(made),
        'per_layer': layer_counts,
        'verified_at': verified_at,
    }, indent=1))


if __name__ == '__main__':
    main()
