"""Bundle a standalone CPython distribution and pinned application dependencies."""
import argparse
import json
import pathlib
import shutil
import subprocess
import sys

parser = argparse.ArgumentParser()
parser.add_argument('--base', required=True, help='Relocatable CPython distribution, not a venv')
parser.add_argument('--site-packages', required=True)
args = parser.parse_args()
base = pathlib.Path(args.base).resolve()
site = pathlib.Path(args.site_packages).resolve()
root = pathlib.Path(__file__).resolve().parents[1]
target = root / 'runtime/macos-arm64/python'
if (base / 'pyvenv.cfg').exists() or not (base / 'lib/python3.12/os.py').exists():
    raise SystemExit('Requires a standalone Python 3.12 distribution, not a system Python or venv')
staging = target.with_name('python-staging')
if staging.exists():
    shutil.rmtree(staging)
shutil.copytree(base, staging, symlinks=True, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
for source in site.iterdir():
    if source.name in ('__pycache__',) or source.name.endswith('.pyc'):
        continue
    dest = staging / 'lib/python3.12/site-packages' / source.name
    if source.is_dir():
        shutil.copytree(source, dest, dirs_exist_ok=True, symlinks=True,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    else:
        shutil.copy2(source, dest)
for link in staging.rglob('*'):
    if link.is_symlink() and not link.resolve().is_relative_to(staging.resolve()):
        raise SystemExit(f'Nonportable symlink: {link}')
subprocess.run([str(staging / 'bin/python3'), '-I', '-c',
    'import platform,sys,openpyxl,playwright,pypdf; assert platform.machine()=="arm64"; assert sys.version_info[:2]==(3,12)'], check=True)
# No customer credentials, profiles or task files enter this directory.
if target.exists():
    shutil.rmtree(target)
staging.rename(target)
(root / 'runtime/macos-arm64/runtime-manifest.json').write_text(json.dumps({
    'python': '3.12.13', 'architecture': 'arm64', 'selfContained': True,
    'dependencies': (root / 'requirements-macos.txt').read_text().splitlines()
}, indent=2))
print('Standalone runtime bundled and import checks passed')
