import glob
import ast
import os

def find_models():
    models = {}
    for filepath in glob.glob("backend/app/models/**/*.py", recursive=True):
        if "__pycache__" in filepath: continue
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=filepath)
                
            for node in tree.body:
                if isinstance(node, ast.ClassDef):
                    tablename = None
                    for body_item in node.body:
                        if isinstance(body_item, ast.Assign):
                            for target in body_item.targets:
                                if isinstance(target, ast.Name) and target.id == "__tablename__":
                                    if isinstance(body_item.value, ast.Constant):
                                        tablename = body_item.value.value
                                    elif isinstance(body_item.value, ast.Str): # Python < 3.8 fallback
                                        tablename = body_item.value.s
                    if tablename:
                        if tablename not in models:
                            models[tablename] = []
                        models[tablename].append({"class": node.name, "file": filepath})
        except Exception as e:
            pass
            
    for table, defs in models.items():
        if len(defs) > 1:
            print(f"DUPLICATE TABLE: {table}")
            for d in defs:
                print(f"  - {d['class']} in {d['file']}")
        else:
            print(f"TABLE: {table} -> {defs[0]['class']} in {defs[0]['file']}")

if __name__ == "__main__":
    find_models()
