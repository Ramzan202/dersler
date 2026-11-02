import json, re, os
from parse import parse_file
idx = [l.split('\t') for l in open('index.tsv', encoding='utf-8').read().split('\n') if l]
VOW = set("AEIİOÖUÜaeıioöuü")
SMALL = {"ve", "ile", "veya", "için", "de", "da"}
def low(s): return s.replace("I", "ı").replace("İ", "i").lower()
def cap(w):
    if not w: return w
    f = w[0]; f = "İ" if f == "i" else ("I" if f == "ı" else f.upper())
    return f + w[1:]
def tr_title(text):
    text = re.sub(r'\s*/\s*', ' / ', ' '.join(text.split()))
    out = []
    for i, word in enumerate(text.split(' ')):
        if word in ("T.C.", "/"): out.append(word); continue
        core = re.sub(r'[^\wÇĞİÖŞÜçğıöşü]', '', word)
        if core and (not (set(core) & VOW) or any(ch.isdigit() for ch in core)) and core.isupper():
            out.append(word); continue
        lw = low(word)
        if i > 0 and lw in SMALL: out.append(lw); continue
        out.append('-'.join(cap(p) if not p.startswith('(') else '(' + cap(p[1:]) for p in lw.split('-')))
    return ' '.join(out)
def clean(name): return ' '.join(re.sub(r'\(\*+\)', '', name).split()).strip(' .')
def v(x): return 0 if x == '-' else int(x)
PROGRAM = {"AMP": "Anadolu Meslek Programı", "ATP": "Anadolu Teknik Programı"}
plans = []; kinds = {}; warn_count = 0
for url, label in idx:
    alan_label = label.split(" MTAL")[0].strip()
    if alan_label.startswith("Mesleki Gelişim"): continue
    for blk in parse_file('txt/' + os.path.basename(url).replace('.pdf', '.txt')):
        head = blk["head"]; hj = ' | '.join(head)
        hj2 = ' '.join(head).replace("ANADOLU MESLEK VE ANADOLU TEKNİK PROGRAMI", "")
        dms = re.findall(r'\(([^()]+?)\s+DALI\)', hj2)
        dal = ' '.join(dms[-1].split()) if dms else ""
        prog = "ATP" if hj2.rfind("ANADOLU TEKNİK PROGRAMI") > hj2.rfind("ANADOLU MESLEK PROGRAMI") else "AMP"
        variant = ""
        if re.search(r"11\.\s*SINIFTA\s+BAŞLAYAN", hj): variant = "İME 11. sınıfta başlar"
        elif "PROTOKOL" in hj.upper() or "Protokol" in alan_label: variant = "Protokol"
        subjects = []; total = None; sec_m = sec = None; seen_total = False
        for name, vals, _ in blk["rows"]:
            n = clean(name)
            if not n: continue
            if n.startswith("TOPLAM DERS SAATİ"): total = [v(x) for x in vals]; continue
            if n.startswith("SEÇMELİ MESLEK DERS SAATİ"): sec_m = [v(x) for x in vals]; continue
            if n.startswith("SEÇMELİ DERS SAATİ"): sec = [v(x) for x in vals]; continue
            if n == "TOPLAM": seen_total = True; continue
            if n.endswith("TOPLAMI") or "TOPLAM" == n.split()[0]: continue
            if n.startswith("HAZIRLIK SINIFI"): continue
            kind = "rehberlik" if n.startswith("REHBERLİK") else ("meslek" if seen_total else "ortak")
            subjects.append((n, kind, [v(x) for x in vals]))
        if not subjects or total is None or not any(total): continue
        grades = {}; ime = {}; warnings = []
        for g in range(4):
            items = []
            for n, kind, hrs in subjects:
                h = hrs[g]
                if not h: continue
                if n.startswith("İŞLETMELERDE MESLEKİ EĞİTİM"): ime[str(g + 9)] = h; continue
                t = tr_title(n); kinds.setdefault(t, kind); items.append([t, h])
            sm = sec_m[g] if sec_m else 0; sg = sec[g] if sec else 0
            explicit = sum(h for _, h in items) + ime.get(str(g + 9), 0)
            rest = total[g] - explicit - sm - sg
            if rest > 0: sg += rest
            if sm: items.append(["Seçmeli Meslek Dersleri", sm]); kinds["Seçmeli Meslek Dersleri"] = "secmeli_meslek"
            if sg: items.append(["Seçmeli Dersler", sg]); kinds["Seçmeli Dersler"] = "secmeli"
            school_total = sum(h for _, h in items)
            expected = total[g] - ime.get(str(g + 9), 0)
            if rest < 0 and not (variant == "Protokol" and rest == -ime.get(str(g + 9), 0)):
                warnings.append(f"{g+9}. sınıf: PDF toplamı {total[g]} saat, tablodan okunan {explicit + sm + sg} saat – PDF ile karşılaştırın")
            if items: grades[str(g + 9)] = items
        warn_count += bool(warnings)
        plans.append(dict(alan=tr_title(alan_label.replace(" - Protokol", "")), dal=tr_title(dal) if dal else "",
                          program=PROGRAM[prog], variant=variant, pdf="https://meslek.meb.gov.tr/" + url,
                          grades=grades, ime=ime, total=total, warnings=warnings))
# dedupe identical plans
uniq = {}; 
for p in plans:
    key = (p["alan"], p["dal"], p["program"], p["variant"], json.dumps(p["grades"], ensure_ascii=False))
    uniq.setdefault(key, p)
plans = list(uniq.values())
data = dict(source="https://meslek.meb.gov.tr/cercevelistele.aspx?sinif_kodu=9&kurum_id=1",
            title="MTAL Çerçeve Öğretim Programları – Haftalık Ders Çizelgeleri (2026)",
            retrieved="2026-11-02", plans=plans, subject_kinds=dict(sorted(kinds.items())))
json.dump(data, open('meb_cerceve.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print("plans", len(plans), "alans", len({p['alan'] for p in plans}), "subjects", len(kinds), "with warnings", warn_count)
print(sorted(kinds)[:400:12])
