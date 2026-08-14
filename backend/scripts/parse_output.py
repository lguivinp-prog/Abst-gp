import json

try:
    with open('scripts/output.txt', 'r', encoding='utf-8') as f:
        text = f.read()
except FileNotFoundError:
    print('File not found')
    exit(1)

parts = text.split('=== ANCHOR ')
for part in parts[1:]:
    name = part.split('===')[0].strip()
    json_text = part.split('===', 1)[1].strip()
    decoder = json.JSONDecoder()
    idx = 0
    while idx < len(json_text):
        # find next [
        idx = json_text.find('[', idx)
        if idx == -1:
            break
        try:
            blocks, next_idx = decoder.raw_decode(json_text[idx:])
            print(f'\nANCHOR {name}: {len(blocks)} blocks')
            for b in blocks:
                if b.get('type') == 'TABLE':
                    print(f"  [TABLE] cols: {b.get('col_count')}, rows: {b.get('row_count')}")
                    if b.get('table_data'):
                        print(f"    table_data has {b['table_data'].get('row_count', 0)} rows and {b['table_data'].get('col_count', 0)} cols")
                elif b.get('type') == 'LIST_ITEM':
                    print('  [LIST_ITEM]', repr(b.get('text'))[:60])
                else:
                    print(f"  [{b.get('type')}]", repr(b.get('text'))[:60])
            idx += next_idx
        except Exception as e:
            idx += 1
