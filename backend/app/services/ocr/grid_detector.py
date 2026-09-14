import fitz
import cv2
import numpy as np
import pytesserac

def extract_tables_by_grid_page(page, page_num, zoom=300/72, debug_dir="backend/data/debug"):

    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    if pix.n == 4:
        img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


    thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 15, -2)

    h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (img.shape[1] // 40, 1))
    h_lines = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, h_kernel)

    v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, img.shape[0] // 40))
    v_lines = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, v_kernel)

    grid = cv2.add(h_lines, v_lines)

    inv_grid = cv2.bitwise_not(grid)
    contours, _ = cv2.findContours(inv_grid, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    cells = []
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        if w >= 10 and h >= 10 and (w * h) < 0.95 * (img.shape[0] * img.shape[1]):
            cells.append({'x': x, 'y': y, 'w': w, 'h': h})


    if not cells:
        return []

    # Sort cells into rows
    cells.sort(key=lambda c: c['y'])
    rows = []
    for c in cells:
        if not rows:
            rows.append([c])
        else:
            last_row = rows[-1]
            avg_y = sum(cc['y'] for cc in last_row) / len(last_row)
            if abs(c['y'] - avg_y) < 15:
                rows[-1].append(c)
            else:
                rows.append([c])

    for r in rows:
        r.sort(key=lambda c: c['x'])

    # Filter rows to build tables
    tables = []
    current_table = []
    for r in rows:
        if len(r) >= 2: # At least 2 columns
            if not current_table:
                current_table.append(r)
            else:
                last_r = current_table[-1]
                last_y_bottom = max(cc['y'] + cc['h'] for cc in last_r)
                r_y_top = min(cc['y'] for cc in r)
                if (r_y_top - last_y_bottom) < 50:
                    current_table.append(r)
                else:
                    tables.append(current_table)
                    current_table = [r]
    if current_table:
        tables.append(current_table)

    # Process OCR and mapping
    words = page.get_text("words")
    page_tables = []
    for table_rows in tables:
        out_table = []
        for r in table_rows:
            out_row = []
            for c in r:
                x, y, w, h = c['x'], c['y'], c['w'], c['h']
                cell_img = gray[y:y+h, x:x+w]
                mean_val = np.mean(cell_img)
                header_text = None

                # Expand slightly to not cut off tex
                cx = x + 2
                cy = y + 2
                cw = w - 4
                ch = h - 4
                if cw < 5 or ch < 5:
                    cx, cy, cw, ch = x, y, w, h

                if mean_val < 100:
                    inv_cell = cv2.bitwise_not(gray[cy:cy+ch, cx:cx+cw])
                    header_text = pytesseract.image_to_string(inv_cell, config='-l spa --psm 7').strip()

                c['words'] = []
                for w_tup in words:
                    wx0, wy0, wx1, wy1, wtext = w_tup[0], w_tup[1], w_tup[2], w_tup[3], w_tup[4]
                    w_cx = ((wx0 + wx1) / 2) * zoom
                    w_cy = ((wy0 + wy1) / 2) * zoom
                    if x <= w_cx <= x+w and y <= w_cy <= y+h:
                        c['words'].append({'x': w_cx, 'y': w_cy, 'text': wtext})

                if header_text:
                    final_text = header_tex
                else:
                    c['words'].sort(key=lambda ww: (ww['y'] // 15, ww['x']))
                    final_text = " ".join(ww['text'] for ww in c['words'])

                out_row.append(final_text)
            out_table.append(out_row)

        class MockCell:
            def __init__(self, text):
                self.text = tex
            def __str__(self):
                return str(self.text)
            def __repr__(self):
                return str(self.text)

        class MockRow:
            def __init__(self, texts):
                self.cells = [MockCell(t) for t in texts]
                self.bbox = (0, 0, 100, 10)

        class MockTable:
            def __init__(self, rows):
                self.rows = [MockRow(r) for r in rows]
                self.bbox = (0, 0, 100, 100)
            def extract(self):
                return [[c.text for c in r.cells] for r in self.rows]

        page_tables.append(MockTable(out_table))

    return page_tables
import cv2
import numpy as np
import fitz
import pytesserac
from pytesseract import Outpu

class MockCell:
    def __init__(self, text):
        self.text = tex
    def __str__(self):
        return str(self.text)
    def __repr__(self):
        return str(self.text)

class MockRow:
    def __init__(self, texts, bbox=(0,0,100,10)):
        self.cells = [MockCell(t) for t in texts]
        self.bbox = bbox

class MockTable:
    def __init__(self, rows, bbox=(0,0,100,100)):
        self.rows = [MockRow(r[0], r[1]) for r in rows]
        self.bbox = bbox
    def extract(self):
        return [[c.text for c in r.cells] for r in self.rows]

def extract_tables_by_dark_header(page, page_num_0):
    zoom = 300 / 72
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)

    if pix.n == 4:
        gray = cv2.cvtColor(img, cv2.COLOR_RGBA2GRAY)
        bgr = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
    else:
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        bgr = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

    pdf_w, pdf_h = page.rect.width, page.rect.heigh
    img_w, img_h = pix.w, pix.h
    scale_x = pdf_w / img_w
    scale_y = pdf_h / img_h

    _, thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY_INV)
    close_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (50, 15))
    closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, close_kernel)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (int(img_w * 0.6), 15))
    band_mask = cv2.morphologyEx(closed, cv2.MORPH_OPEN, kernel)

    contours, _ = cv2.findContours(band_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    bands = []
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        if w > img_w * 0.6 and 15 <= h <= 150:
            mean_val = np.mean(gray[y:y+h, x:x+w])
            if mean_val < 100:
                bands.append({'x': x, 'y': y, 'w': w, 'h': h, 'mean': mean_val})

    bands.sort(key=lambda b: b['y'])


    if not bands:
        return []

    out_tables = []
    for band in bands:
        bx, by, bw, bh = band['x'], band['y'], band['w'], band['h']

        roi = gray[by:by+bh, bx:bx+bw]
        roi_inv = cv2.bitwise_not(roi)
        roi_inv_2x = cv2.resize(roi_inv, (0,0), fx=2, fy=2, interpolation=cv2.INTER_CUBIC)

        data = pytesseract.image_to_data(roi_inv_2x, lang="spa", config="--psm 6", output_type=Output.DICT)

        words = []
        n = len(data['level'])
        for i in range(n):
            text = data['text'][i].strip()
            if text:
                x2 = data['left'][i]
                y2 = data['top'][i]
                w2 = data['width'][i]
                h2 = data['height'][i]

                wx = bx + x2 / 2
                wy = by + y2 / 2
                ww = w2 / 2
                wh = h2 / 2
                words.append({
                    'text': text,
                    'x0': wx,
                    'y0': wy,
                    'x1': wx + ww,
                    'y1': wy + wh,
                    'w': ww
                })

        words.sort(key=lambda w: w['x0'])

        titles = []
        if words:
            global_avg_char_w = sum(w['w'] for w in words) / max(1, sum(len(w['text']) for w in words))
            current_title = [words[0]]
            for i in range(1, len(words)):
                curr = words[i]
                gap = curr['x0'] - max(w['x1'] for w in current_title)
                # Strict rule requested by user
                if gap < 2.0 * global_avg_char_w:
                    current_title.append(curr)
                else:
                    titles.append(current_title)
                    current_title = [curr]
            titles.append(current_title)




        pdf_titles = []
        for t in titles:
            pdf_titles.append({
                'text': t[0].get("text_override", " ".join(w["text"] for w in t)),
                'x0': min(w['x0'] for w in t) * scale_x,
                'x1': max(w['x1'] for w in t) * scale_x
            })

        if not pdf_titles:
            continue

        table_x0 = bx * scale_x
        table_x1 = (bx + bw) * scale_x


        col_ranges = []
        table_x0 = bx * scale_x
        table_x1 = (bx + bw) * scale_x

        for i in range(len(pdf_titles)):
            c_start = table_x0 if i == 0 else (pdf_titles[i-1]['x1'] + pdf_titles[i]['x0']) / 2
            c_end = table_x1 if i == len(pdf_titles)-1 else (pdf_titles[i]['x1'] + pdf_titles[i+1]['x0']) / 2
            col_ranges.append((c_start, c_end))



        band_pdf_y1 = (by + bh) * scale_y
        all_words = page.get_text("words")
        body_words = [w for w in all_words if w[1] >= band_pdf_y1 and w[0] >= table_x0 - 10 and w[2] <= table_x1 + 10]
        body_words.sort(key=lambda w: w[1])

        # El hueco de 25px a 300 DPI equivale a unos 6 puntos en la escala PDF
        gap_threshold_pdf = 25 * scale_y
        # También el hueco puede ser si hay demasiada distancia


        filtered_body_words = []

        if body_words:
            prev_y1_pdf = band_pdf_y1
            # Sort words roughly line by line
            lines = []
            for w in body_words:
                placed = False
                for l in lines:
                    if abs(w[1] - l['y0']) < 5:
                        l['words'].append(w)
                        l['y1'] = max(l['y1'], w[3])
                        placed = True
                        break
                if not placed:
                    lines.append({'y0': w[1], 'y1': w[3], 'words': [w]})

            lines.sort(key=lambda l: l['y0'])

            for l in lines:
                gap = l['y0'] - prev_y1_pdf
                if gap > gap_threshold_pdf:
                    break
                filtered_body_words.extend(l['words'])
                prev_y1_pdf = l['y1']

        rows_dict = []
        for w in filtered_body_words:
            wx0, wy0, wx1, wy1, wtext = w[0], w[1], w[2], w[3], w[4]
            wcenter = (wx0 + wx1) / 2
            wmidy = (wy0 + wy1) / 2
            placed = False
            for r in rows_dict:
                r_midy = r['midy']
                if abs(wmidy - r_midy) < (wy1 - wy0) * 0.5:
                    r['words'].append(w)
                    r['midy'] = sum((ww[1]+ww[3])/2 for ww in r['words']) / len(r['words'])
                    placed = True
                    break
            if not placed:
                rows_dict.append({'midy': wmidy, 'words': [w]})

        rows_dict.sort(key=lambda r: r['midy'])

        out_rows = []
        header_texts = [t['text'] for t in pdf_titles]
        header_bbox = (table_x0, by * scale_y, table_x1, band_pdf_y1)
        out_rows.append((header_texts, (0,0,0,0)))

        for r in rows_dict:
            r['words'].sort(key=lambda w: w[0])
            cols_text = [""] * len(col_ranges)
            r_y0 = min(w[1] for w in r['words'])
            r_y1 = max(w[3] for w in r['words'])
            for w in r['words']:
                wcenter = (w[0] + w[2]) / 2
                for i, (cs, ce) in enumerate(col_ranges):
                    if cs <= wcenter <= ce:
                        cols_text[i] = (cols_text[i] + " " + w[4]).strip()
                        break
            out_rows.append((cols_text, (0,0,0,0)))

        table_bbox = (table_x0, by * scale_y, table_x1, out_rows[-1][1][3] if len(out_rows) > 0 else band_pdf_y1)
        out_tables.append(MockTable(out_rows, table_bbox))


    return out_tables
