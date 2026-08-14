import ast
import glob

models = {}
for filepath in glob.glob('backend/app/**/*.py', recursive=True):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read())
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(item, ast.Assign):
                        for target in item.targets:
                            if isinstance(target, ast.Name) and target.id == '__tablename__':
                                tablename = ast.unparse(item.value).strip('\'"')
                                if tablename not in models:
                                    models[tablename] = []
                                models[tablename].append((node.name, filepath))
    except Exception:
        pass

for t, m in models.items():
    if len(m) > 1:
        print(f'DUPLICATE: {t} -> {m}')
