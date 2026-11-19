"""Synthetic read-only fixture; count a supplied UTF-8 local list."""
import hashlib
import json
from pathlib import Path
import sys

if len(sys.argv) != 2:
    print('input_required: supply one local input path', file=sys.stderr)
    raise SystemExit(2)
try:
    data = Path(sys.argv[1]).read_bytes()
    items = [line.strip() for line in data.decode('utf-8').splitlines() if line.strip()]
except (OSError, UnicodeError) as error:
    print('input_unavailable: ' + str(error), file=sys.stderr)
    raise SystemExit(2)
print(json.dumps({'count': len(set(items)), 'input_sha256': hashlib.sha256(data).hexdigest(),
                  'fixture_version': 'v2'}, sort_keys=True))
