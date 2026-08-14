import os
import datetime

def is_excluded(path):
    parts = path.split(os.sep)
    return any(p in ['node_modules', '.venv', 'dist', 'build', '.git', '__pycache__', '.next', 'coverage'] for p in parts)

files = []
for root, dirs, filenames in os.walk('.'):
    # prune excluded dirs
    dirs[:] = [d for d in dirs if not is_excluded(os.path.join(root, d))]
    
    for f in filenames:
        path = os.path.join(root, f)
        if not is_excluded(path):
            try:
                stat = os.stat(path)
                files.append({
                    'path': path,
                    'size': stat.st_size,
                    'mtime': stat.st_mtime
                })
            except Exception as e:
                pass

files_by_size = sorted(files, key=lambda x: x['size'], reverse=True)[:20]
files_by_mtime = sorted(files, key=lambda x: x['mtime'], reverse=True)[:20]

print('=== 20 LARGEST FILES ===')
for f in files_by_size:
    print(f"{f['size']} bytes - {f['path']}")

print('\n=== 20 MOST RECENTLY MODIFIED FILES ===')
for f in files_by_mtime:
    print(f"{datetime.datetime.fromtimestamp(f['mtime']).isoformat()} - {f['path']}")
