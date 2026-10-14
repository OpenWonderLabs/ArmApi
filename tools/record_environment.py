#!/usr/bin/env python3
"""Record the actual offline execution environment, including system packages."""
import importlib.metadata
import json
import platform
import subprocess
import sys
from pathlib import Path

conda = Path(sys.prefix) / 'conda-meta'
if conda.is_dir():
    source = 'Conda'
    packages = []
    for path in sorted(conda.glob('*.json')):
        meta = json.loads(path.read_text())
        packages.append({k:meta.get(k) for k in ('name','version','build','sha256')})
elif platform.system() == 'Linux':
    source = 'dpkg'
    text = subprocess.check_output(['dpkg-query','-W','-f=${binary:Package}\t${Version}\n'], text=True)
    packages = [{'name':line.split('\t')[0], 'version':line.split('\t')[1]}
                for line in text.splitlines()]
else:
    source = 'pip'
    packages = sorted(({'name':d.metadata['Name'], 'version':d.version}
                       for d in importlib.metadata.distributions()), key=lambda d:d['name'].lower())
os_name = platform.system()+' '+platform.release()
if platform.system() == 'Linux':
    os_name = platform.freedesktop_os_release().get('PRETTY_NAME', os_name)
print(json.dumps({'check':'SDK execution environment', 'os':os_name,
                  'python':platform.python_version(), 'numpy':importlib.metadata.version('numpy'),
                  'loguru':importlib.metadata.version('loguru'), 'inventory_source':source,
                  'packages':packages}, sort_keys=True), flush=True)
