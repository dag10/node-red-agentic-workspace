#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: normalize-json.sh <file.json> [output.json]" >&2
  echo "If no output file is given, the input file is modified in place." >&2
  exit 1
fi

INPUT_FILE="$1"
OUTPUT_FILE="${2:-$1}"

python3 -c "
import json, sys

with open(sys.argv[1]) as f:
    data = json.load(f)

def sort_keys_recursive(obj):
    if isinstance(obj, dict):
        return {k: sort_keys_recursive(v) for k, v in sorted(obj.items())}
    if isinstance(obj, list):
        return [sort_keys_recursive(item) for item in obj]
    return obj

data = sort_keys_recursive(data)

# If top-level is an array of objects with 'id' fields, sort by id for stable ordering.
if isinstance(data, list) and all(isinstance(e, dict) and 'id' in e for e in data):
    data.sort(key=lambda e: e['id'])

with open(sys.argv[2], 'w') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
    f.write('\n')
" "$INPUT_FILE" "$OUTPUT_FILE"
