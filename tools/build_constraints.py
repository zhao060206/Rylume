"""Pin the Windows build environment to the versions recorded in licenses/python-packages.json.

The license record lists the packages whose notices (and, where required, corresponding sources)
ship with a release, so the build interpreter must contain exactly those versions.

  python tools/build_constraints.py --write build-constraints.txt   # constraints for pip install -c
  python tools/build_constraints.py --check                         # run with the build interpreter
"""
import argparse
import json
import re
import sys
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _norm(name):
    return re.sub(r'[-_.]+', '-', name).lower()


def recorded():
    items = json.loads((ROOT / 'licenses' / 'python-packages.json').read_text(encoding='utf-8-sig'))
    return {item['name']: item['version'] for item in items}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--write', type=Path, help='write pip constraints to this file')
    group.add_argument('--check', action='store_true', help='compare this interpreter with the record')
    args = parser.parse_args()
    packages = recorded()
    if args.write:
        lines = [f'{name}=={version}\n' for name, version in sorted(packages.items(), key=lambda p: p[0].lower())]
        args.write.write_text(''.join(lines), encoding='utf-8')
        print(f'{len(lines)} constraints written to {args.write}')
        return 0
    installed = {_norm(d.metadata['Name']): d.version for d in metadata.distributions() if d.metadata['Name']}
    differ = [(name, version, installed.get(_norm(name), 'not installed'))
              for name, version in sorted(packages.items(), key=lambda p: p[0].lower())
              if installed.get(_norm(name)) != version]
    for row in differ:
        print('%s: recorded %s, installed %s' % row)
    print(f'{len(packages)} recorded packages; {len(differ)} differ in {sys.executable}')
    return 1 if differ else 0


if __name__ == '__main__':
    sys.exit(main())
