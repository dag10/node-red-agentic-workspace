#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: summarize-nodered-flows.sh <flows.json>" >&2
  exit 1
fi

FLOWS_FILE="$1"

if [[ ! -f "$FLOWS_FILE" ]]; then
  echo "Error: file not found: $FLOWS_FILE" >&2
  exit 1
fi

python3 -c "
import json, sys

with open(sys.argv[1]) as f:
    data = json.load(f)

from collections import Counter
nodes_per_z = Counter(e.get('z') for e in data if 'z' in e)

tabs = sorted(
    [e for e in data if e.get('type') == 'tab'],
    key=lambda e: e.get('label', ''),
)
subflows = sorted(
    [e for e in data if e.get('type') == 'subflow'],
    key=lambda e: e.get('name', ''),
)

print(f'Flows ({len(tabs)}):')
for t in tabs:
    label = t.get('label', '(unnamed)')
    nid = t['id']
    count = nodes_per_z.get(nid, 0)
    disabled = ' [disabled]' if t.get('disabled') else ''
    print(f'  {label} ({count} nodes){disabled}  id={nid}')

print()
print(f'Subflows ({len(subflows)}):')
for s in subflows:
    name = s.get('name', '(unnamed)')
    nid = s['id']
    count = nodes_per_z.get(nid, 0)
    ins = len(s.get('in', []))
    outs = len(s.get('out', []))
    print(f'  {name} ({count} nodes, {ins} in, {outs} out)  id={nid}')
" "$FLOWS_FILE"
