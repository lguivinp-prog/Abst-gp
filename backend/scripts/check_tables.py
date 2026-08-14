import json

with open('backend/scripts/output.txt', 'r', encoding='utf-8') as f:
    text = f.read()

sec5_text = text.split('=== ANCHOR D ===')[0]

decoder = json.JSONDecoder()
idx = 0
while idx < len(sec5_text):
    idx = sec5_text.find('[', idx)
    if idx == -1:
        break
    try:
        blocks, next_idx = decoder.raw_decode(sec5_text[idx:])
        for b in blocks:
            if b.get('type') == 'TABLE' and b.get('table_data'):
                td = b['table_data']
                print(f"Table: {td.get('row_count')} rows, {td.get('col_count')} cols")
                for i, r in enumerate(td.get('rows', [])[:15]):
                    print(f"  Row {i}: " + " | ".join([c.get('text', '') for c in r.get('cells', [])]))
        idx += next_idx
    except Exception as e:
        idx += 1
