#!/usr/bin/env python3
"""Generate reference/directory.qmd - the category directory page.

Source of truth: manifest/tools.yaml from kailash-packages (fetch at
generation time, or pass --from FILE with --sha for a local copy).
Lists every category grouped by layer, each category an anchored
section with its tool inventory, hyperlinked to per-tool pages when
the linked page exists in the reference dir - auto-linking as more
pages land. Footer records manifest provenance. Generated, never
hand-edited.
"""
import os
import argparse
import datetime
from collections import OrderedDict

try:
    import yaml
except ImportError:
    raise SystemExit('PyYAML required at generation time')

LAYER_TITLES = OrderedDict([
    ('CLASSIC', 'Layer CLASSIC (c-01 .. c-10)'),
    ('ATTACK', 'Layer ATTACK (a-01 .. a-08)'),
    ('DEFENCE', 'Layer DEFENCE (d-01 .. d-07)'),
    ('OPS', 'Layer OPS (o-01 .. o-07)'),
])


def build(manifest_path, manifest_sha, out_path, tool_pages, sibling_pages):
    with open(manifest_path, encoding='utf-8') as fh:
        tools = yaml.safe_load(fh)['tools']

    cats = OrderedDict()
    for t in tools:
        cats.setdefault(t['category'], []).append(t)

    layer_counts = {}
    for cid, members in cats.items():
        layer = members[0]['layer']
        layer_counts[layer] = layer_counts.get(layer, 0) + len(members)

    lines = []
    lines.append('---')
    lines.append('title: "Category directory"')
    lines.append('---')
    lines.append('')
    lines.append('# Category directory')
    lines.append('')
    lines.append('Every category in the Kailash catalogue, grouped by layer,')
    lines.append('with the tools registered under it. Each category links into')
    lines.append('the per-tool pages of the reference section as they land;')
    lines.append('tools without a page yet are marked as pending.')
    lines.append('')
    lines.append('| Layer | Categories | Tools |')
    lines.append('|---|---|---|')
    for layer, title in LAYER_TITLES.items():
        n_cats = sum(1 for cid in cats if cats[cid][0]['layer'] == layer)
        lines.append(f'| {layer} | {n_cats} | {layer_counts.get(layer, 0)} |')
    lines.append('')

    for layer, title in LAYER_TITLES.items():
        lines.append(f'## {title}')
        lines.append('')
        for cid, members in cats.items():
            if members[0]['layer'] != layer:
                continue
            anchor = 'cat-' + cid
            lines.append(f'### {cid} {{#{anchor}}}')
            lines.append('')
            for t in sorted(members, key=lambda x: x['id']):
                tid = t['id']
                desc = t.get('description') or t.get('name') or tid
                safety = (t.get('safety') or {}).get('level', '?')
                href = None
                if tid in tool_pages:
                    href = f'tools/{tid}.qmd'
                elif tid in sibling_pages:
                    href = f'{tid}.qmd'
                if href:
                    lines.append(f'- [{tid}]({href}) - safety: {safety} - {desc}')
                else:
                    lines.append(f'- `{tid}` - safety: {safety} - {desc} *(reference page pending)*')
            lines.append('')

    now = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d')
    sha_short = manifest_sha[:8] if manifest_sha else 'local-copy'
    lines.append('---')
    lines.append('')
    lines.append('**Provenance.** Generated from `manifest/tools.yaml`'
                 f' (revision `{sha_short}`) on {now};'
                 f' {len(tools)} tool rows across {len(cats)} categories.'
                 ' The manifest remains the single source of truth -'
                 ' this page is regenerated, never hand-edited.')
    lines.append('')

    with open(out_path, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(lines))
    print(f'wrote {os.path.abspath(out_path)}: {len(tools)} tools / {len(cats)} categories')


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--from', dest='manifest', required=True,
                    help='path to tools.yaml (fetch fresh before calling for CI runs)')
    ap.add_argument('--sha', default='', help='manifest git sha for the provenance footer')
    ap.add_argument('--out', default=os.path.join(here, '..', 'reference', 'directory.qmd'))
    ap.add_argument('--ref-dir', default=os.path.join(here, '..', 'reference'))
    a = ap.parse_args()
    # detect generated tool pages (reference/tools/*.qmd) AND sibling pages
    tool_pages = set()
    tools_dir = os.path.join(os.path.dirname(a.out), 'tools')
    if os.path.isdir(tools_dir):
        tool_pages = {f[:-4] for f in os.listdir(tools_dir) if f.endswith('.qmd')}
    sibling_pages = set()
    if os.path.isdir(a.ref_dir):
        sibling_pages = {f[:-4] for f in os.listdir(a.ref_dir) if f.endswith('.qmd')}
    sibling_pages -= {'directory', 'coverage', os.path.splitext(os.path.basename(a.out))[0]}
    build(a.manifest, a.sha, a.out, tool_pages, sibling_pages)


if __name__ == '__main__':
    main()
