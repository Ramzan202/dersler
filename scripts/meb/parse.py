import re
CATS = {"ORTAK DERSLER", "MESLEK DERSLERİ", "DERS KATEGORİLERİ", "DERSLER", "SEÇMELİ DERSLER", "SINIF"}
def tokens(line):
    return [(m.start(), m.end(), m.group()) for m in re.finditer(r'\S+(?: \S+)*', line)]
def parse_file(path):
    lines = open(path, encoding='utf-8', errors='replace').read().split('\n')
    blocks = []; i = 0
    while i < len(lines):
        L = lines[i]
        if re.search(r'HAFTALIK DERS ÇİZELGES\w*\s*$', L) and not re.search(r'\.{3,}', L):
            head = [l.strip() for l in lines[max(0, i-8):i+1] if l.strip()]
            # column header
            cols = None; j = i + 1
            while j < min(len(lines), i + 8):
                ms = list(re.finditer(r'\b(9|10|11|12)\.', lines[j]))
                if len(ms) == 4:
                    cols = [(m.start() + m.end()) / 2 for m in ms]
                    hz = lines[j].find('HAZIRLIK')
                    text_end = hz - 2 if hz > 0 else int(cols[0]) - 6
                    break
                j += 1
            if cols is None: i += 1; continue
            rows = []; pending = []; extend_row = None
            j += 1
            while j < len(lines) and j < i + 90:
                l = lines[j]
                s = l.strip()
                if s.startswith('NOT') or 'HAFTALIK DERS ÇİZELGES' in l or 'ÇERÇEVE ÖĞRETIM PROGRAMI' in l and rows:
                    break
                if not s or re.fullmatch(r'\d+', s) and len(s) <= 3 and l.startswith(s):
                    j += 1; continue
                vals = {}; text_parts = []
                for a, b, t in re.finditer(r'\S+', l) and [(m.start(), m.end(), m.group()) for m in re.finditer(r'\S+', l)]:
                    c = (a + b) / 2
                    if re.fullmatch(r'\d+|-', t) and c > cols[0] - 6:
                        g = min(range(4), key=lambda k: abs(cols[k] - c)); vals[g] = t
                    else:
                        text_parts.append((a, t))
                text = ' '.join(t for _, t in text_parts)
                # split category prefix: category text begins at small indentation and separated by 2+ spaces
                segs = [x.strip() for x in re.split(r'\s{2,}', l[:text_end]) if x.strip()]
                segs = [x for x in segs if x not in CATS and x not in ("TOPLAM",) or x == "TOPLAM"]
                name = segs[-1] if segs else ""
                for cat in ("ORTAK DERSLER ", "MESLEK DERSLERİ ", "SEÇMELİ DERSLER "):
                    if name.startswith(cat): name = name[len(cat):]
                if name in CATS: name = ""
                if vals and name:
                    rows.append([name, vals]); pending = []; extend_row = rows[-1]
                elif vals and not name:
                    if rows and len(rows[-1][1]) < 4 and not (set(vals) & set(rows[-1][1])):
                        rows[-1][1].update(vals)
                    else:
                        rows.append([' '.join(pending), vals]); extend_row = rows[-1]; pending = []
                        extend_row.append("wrapped")
                elif name and not vals:
                    if extend_row is not None and len(extend_row) == 3 and extend_row[2] == "wrapped":
                        extend_row[0] = (extend_row[0] + ' ' + name).strip(); extend_row[2] = "done"
                    else:
                        pending.append(name)
                j += 1
            out = []
            for r in rows:
                v = [r[1].get(g, '-') for g in range(4)]
                out.append((r[0], v, []))
            blocks.append({"head": head, "rows": out, "line": i})
            i = j
        else:
            i += 1
    return blocks
