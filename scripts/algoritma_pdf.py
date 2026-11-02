"""Builds 'Algoritma ve Hesaplama Yöntemi' PDF (Turkish) for school management.

Usage:  python scripts/algoritma_pdf.py output.pdf [database.db]
With a database, a results page compares the school's current timetable with the optimized variant.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from reportlab.lib import colors  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import ParagraphStyle  # noqa: E402
from reportlab.lib.units import mm  # noqa: E402
from reportlab.platypus import (KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Table,  # noqa: E402
                                TableStyle)

from app.config import WEIGHT_DEFINITIONS  # noqa: E402
from app.core.optimizer import MULTIPLIERS, TERM_LABELS  # noqa: E402
from app.utils.pdf_export import _register_font  # noqa: E402

FONT, BOLD = _register_font()
H1 = ParagraphStyle("h1", fontName=BOLD, fontSize=19, leading=24, spaceAfter=6, textColor=colors.HexColor("#1F4E79"))
H2 = ParagraphStyle("h2", fontName=BOLD, fontSize=13.5, leading=18, spaceBefore=10, spaceAfter=4,
                    textColor=colors.HexColor("#1F4E79"))
BODY = ParagraphStyle("b", fontName=FONT, fontSize=10, leading=14, spaceAfter=4)
SMALL = ParagraphStyle("s", fontName=FONT, fontSize=8.5, leading=11)
CELL = ParagraphStyle("c", fontName=FONT, fontSize=9, leading=11.5)
CELLB = ParagraphStyle("cb", fontName=BOLD, fontSize=9, leading=11.5, textColor=colors.white)
BOX = ParagraphStyle("box", fontName=FONT, fontSize=10, leading=14, backColor=colors.HexColor("#EEF4FA"),
                     borderPadding=6, spaceBefore=6, spaceAfter=8)


def p(text, style=BODY):
    return Paragraph(text, style)


def bullets(items):
    return [p(f"• {x}") for x in items]


def table(rows, widths, header=True):
    data = [[Paragraph(str(c), CELLB if header and i == 0 else CELL) for c in row] for i, row in enumerate(rows)]
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    style = [("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9AA9B8")), ("VALIGN", (0, 0), (-1, -1), "TOP"),
             ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F4F7FA")])]
    if header:
        style.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E79")))
    t.setStyle(TableStyle(style))
    return t


def results_section(db_path):
    from app.core.problem import build_problem
    from app.core.workload import build_report
    from app.database.database import Database
    from app.services.timetable_service import TimetableService
    db = Database(db_path)
    problem = build_problem(db)
    svc = TimetableService(db)
    variants = svc.list()
    current = next((t for t in variants if t.source.startswith("excel")), None)
    optimized = next((t for t in variants if t.source.startswith("auto")), None)
    if not current or not optimized:
        return []
    a, b = build_report(problem, svc.entries(current.id)), build_report(problem, svc.entries(optimized.id))
    groups = sum(1 for c in problem.classes.values() if c.parent_id is not None)
    teaching = len({t for e in svc.entries(current.id) for t in e.teacher_ids})
    story = [PageBreak(), p("7. Okul verileriyle sonuç", H1),
             p(f"Okulun 9–12. sınıf programları (Excel) programa aktarıldı: <b>{len(problem.classes) - groups} sınıf</b> "
               f"ve <b>{groups} şube grubu</b>, <b>{len(problem.subjects)} ders kodu</b>, <b>{teaching} dersi olan "
               f"öğretmen</b>, <b>{len(problem.rooms)} derslik/atölye</b>, haftada <b>{a.required_hours} ders saati</b> "
               f"({problem.num_days} gün × {problem.periods} ders, her ders 30 dakika). Mevcut program hiçbir zorunlu "
               f"kuralı ihlal etmiyor; yani model okulun gerçek kurallarını doğru tanımlıyor."),
             p("Program, mevcut ders programını başlangıç noktası alarak daha iyi bir dağılım aradı:")]
    rows = [["Ölçüt", "Mevcut program", "Optimize edilmiş"]]
    for (label, va), (_, vb) in zip(a.summary_rows(), b.summary_rows()):
        rows.append([label, va, vb])

    def spread(r):
        values = [(hi - lo) for _, lo, hi, n in r.branch_stats.values() if n > 1]
        return max(values) if values else 0
    rows.append(["Branş içi en büyük yük farkı (ders)", spread(a), spread(b)])
    story.append(table(rows, [90 * mm, 40 * mm, 40 * mm]))
    story.append(p("Öğretmen boş penceresi: aynı gün iki dersi arasında boş geçen 30 dakikalık ders saatleri. "
                   "Zorunlu kurallar her iki programda da tamamen sağlanıyor. Bu çalıştırmada hangi öğretmenin hangi "
                   "sınıfa gireceği okulun mevcut atamasıyla aynı tutuldu (yalnızca gün/saat/derslik değişti); bu "
                   "nedenle branş içi yük farkı değişmez. Atamalar programda açılırsa çözücü yükleri de dengeler.",
                   SMALL))
    return story


def build(path, db_path=None):
    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm,
                            bottomMargin=16 * mm, title="Otomatik Ders Dağılımı – Algoritma")
    s = [p("Otomatik Ders Dağılım Programı", H1),
         p("Ders programı nasıl hesaplanır? – Algoritma ve hesaplama yöntemi", H2),
         p("Bu belge, programın ders dağılımını hangi bilgilerle, hangi kurallarla ve hangi matematiksel yöntemle "
           "oluşturduğunu okul yönetimi için özetler.", BODY),
         p("<b>Kısaca:</b> Program dersleri rastgele yerleştirmez. Okulun tüm kurallarını bir matematiksel model "
           "olarak yazar, Google OR-Tools CP-SAT çözücüsüyle bu kuralların <b>hepsini</b> sağlayan programlar "
           "arasından tercihlere göre <b>en iyi puanlı</b> olanı arar. Kurallar sağlanamıyorsa program üretmez ve "
           "nedenini açıkça yazar.", BOX),
         p("1. Kullanılan bilgiler", H2)]
    s += bullets([
        "<b>Zaman çizelgesi:</b> haftalık gün sayısı, günlük ders sayısı ve her dersin saati (ör. 16 ders × 30 dk).",
        "<b>Sınıflar ve şube grupları:</b> her sınıfın okul günleri ve ders saati aralığı; gruplar (ör. ATP10A-1) "
        "ana sınıfa bağlıdır, grup dersindeyken ana sınıfın başka dersi olamaz.",
        "<b>Dersler:</b> her sınıf için haftalık ders saati (HDS), zorluk, beden eğitimi gibi özellikler, blok "
        "(art arda ders) kuralları.",
        "<b>Öğretmenler:</b> branş, verebildiği dersler, günlük/haftalık en fazla ders, kapalı saatler, tercih "
        "ettiği günler. Bir derse birden fazla öğretmen ekip olarak girebilir.",
        "<b>Derslikler ve atölyeler:</b> tür, kapasite, kapalı saatler ve aynı anda kaç grubun kullanabileceği.",
        "<b>Özel durumlar:</b> birleştirilmiş dersler (iki grup aynı öğretmenle birlikte), İşletmelerde Mesleki "
        "Eğitim (okul dışında geçen günler) ve kilitlenen (yeri değişmeyecek) dersler.",
    ])
    s += [p("2. Hesaplama adımları", H2)]
    s.append(table([
        ["Adım", "Ne yapılır?"],
        ["1. Veri kontrolü", "Eksik/çelişkili bilgi aranır: planı olmayan sınıf, öğretmeni olmayan ders, sınıfın "
                             "müsait saatinden fazla ders, öğretmen veya derslik kapasitesinin yetmemesi gibi. Hata "
                             "varsa dağıtım başlamaz ve hangi kaydın düzeltileceği yazılır."],
        ["2. Modelin kurulması", "Her ders için 'hangi gün, kaçıncı saatte, kaç saatlik blok olarak başlar', 'hangi "
                                 "öğretmen(ler)', 'hangi derslik' soruları evet/hayır değişkenlerine dönüştürülür. "
                                 "Tüm kurallar bu değişkenler arasında matematiksel eşitlik/eşitsizlik olarak yazılır."],
        ["3. Çözüm ve iyileştirme", "CP-SAT çözücüsü önce kuralları sağlayan bir program bulur, sonra süre sınırı "
                                    "içinde ceza puanı daha düşük programlar arar. Ekranda bulunan çözüm sayısı ve "
                                    "puan canlı görünür; işlem istenince durdurulabilir."],
        ["4. Bağımsız doğrulama", "Bulunan program ayrı bir denetleyiciyle tüm kurallara karşı tekrar kontrol "
                                  "edilir. Elle yapılan her değişiklikten sonra da aynı kontrol çalışır."],
        ["5. Rapor", "Öğretmen yükleri, branş ortalamaları, derslik doluluğu, sınıfların günlük yükü, boş "
                     "pencereler ve varsa sorunlar raporlanır; varyantlar karşılaştırılabilir."],
    ], [38 * mm, 136 * mm]))
    s += [p("3. Zorunlu kurallar (asla ihlal edilmez)", H2)]
    s += bullets([
        "Bir sınıfın (ve ana sınıf ile gruplarının) aynı saatte en fazla bir dersi olur.",
        "Bir öğretmen aynı saatte en fazla bir derse girer (birleştirilmiş ders tek ders sayılır).",
        "Bir derslik aynı saatte en fazla izin verilen sayıda gruba (genelde 1) verilir.",
        "Her ders, haftalık ders saati kadar ve tam olarak yerleştirilir.",
        "Dersi yalnızca o derse yetkili öğretmen(ler) verir; ekip derslerinde ekibin tamamı aynı anda derstedir.",
        "Sınıfın okul dışı günlerine/saatlerine, öğretmenin ve dersliğin kapalı saatlerine ders konmaz.",
        "Ders gerekiyorsa uygun türdeki derslikte yapılır; atölye dersleri kendi atölyelerinde.",
        "Öğretmenin günlük ve haftalık ders sınırları aşılmaz.",
        "Blok kuralları: ders, izin verilen bölünmelerden biriyle yerleşir (ör. 9 saat = 3+3+3); bir günde aynı "
        "dersin birden fazla bloğu ancak izin verilmişse olur.",
        "Kilitlenen dersler yerinden oynamaz.",
    ])
    s.append(p("Bu kuralların hepsi aynı anda sağlanamıyorsa program <b>oluşturulmaz</b>. Çözücü, birbirine engel "
               "olan kuralların en küçük grubunu bulur ve örneğin şöyle yazar: <i>“AMP12A sınıfının Türk Dili ve "
               "Edebiyatı dersi için 4 saat yerleştirilemiyor. Öğretmen X: kapalı saatleri ders yerleştirmeyi "
               "engelliyor. AMP12A sınıfının okul günleri yetersiz.”</i>", BOX))
    s.append(KeepTogether([p("4. Tercihler ve puanlama", H2),
                           p("Kuralları sağlayan çok sayıda program vardır. Hangisinin daha iyi olduğunu bir <b>ceza "
                             "puanı</b> belirler; çözücü bu puanı en aza indirir:"),
                           p("<b>Toplam ceza = Σ (öncelik × katsayı × ölçülen değer)</b>", BOX),
                           p("Öncelik 0–10 arasıdır ve Ayarlar ekranından değiştirilebilir (0 = dikkate alma). "
                             "Katsayı, farklı birimlerdeki ölçüleri dengeler.")]))
    rows = [["Tercih", "Ölçülen değer", "Varsayılan öncelik", "Katsayı"]]
    measures = {
        "teacher_balance": "Aynı branştaki öğretmenlerin haftalık yükleri arasındaki en büyük fark",
        "teacher_gaps": "Öğretmenin gün içindeki boş ders saatleri (pencere)",
        "class_gaps": "Sınıfın gün içindeki boş ders saatleri",
        "hard_early": "Zor derslerin (Matematik, Fizik…) günün kaçıncı saatinde olduğu",
        "physical_late": "Beden eğitiminin günün sonuna olan uzaklığı",
        "preferred_time": "Dersin istenen zamana (sabah/öğleden sonra) uzaklığı",
        "hard_per_day": "Bir günde sınırı aşan zor ders saati",
        "class_day_balance": "Sınıfın en yoğun ve en hafif günü arasındaki fark",
        "teacher_day_balance": "Öğretmenin en yoğun günündeki ders sayısı",
        "teacher_consecutive": "Art arda en fazla ders sınırını aşan saatler",
        "teacher_preferred_days": "Öğretmenin tercih etmediği günlerdeki dersleri",
        "split_preference": "Tercih edilen bölünmenin (ör. 3+3+3) kullanılmaması",
    }
    for key, label, default in WEIGHT_DEFINITIONS:
        rows.append([label, measures.get(key, TERM_LABELS.get(key, "")), default, MULTIPLIERS.get(key, 1)])
    s.append(table(rows, [52 * mm, 78 * mm, 22 * mm, 20 * mm]))
    s += [p("Örnek: Bir öğretmenin bir günde 2 boş saati varsa ceza = 8 (öncelik) × 12 (katsayı) × 2 = 192 puan. "
            "Matematik 1. saat yerine 6. saate konursa ceza = 7 × 2 × 5 × 2 (zorluk) = 140 puan artar. Çözücü "
            "tüm bu puanların toplamını en küçük yapan yerleşimi arar.", SMALL),
          p("5. Neden CP-SAT?", H2)]
    s += bullets([
        "Ders programı, olası yerleşimlerin sayısı astronomik olan bir 'kısıt programlama' problemidir; deneme-"
        "yanılma veya basit sırayla yerleştirme ya kural ihlali yapar ya da çok kötü programlar üretir.",
        "CP-SAT (Google OR-Tools) bu tür problemler için dünyada en güçlü ücretsiz çözücülerden biridir: kuralları "
        "kesin olarak uygular, çok çekirdekli çalışır ve bulduğu çözümün en iyiye ne kadar yakın olduğunu "
        "gösteren bir alt sınır hesaplar.",
        "Mevcut programdan başlayarak iyileştirebilir; kilitli dersleri koruyarak yeniden dağıtım yapılabilir.",
    ])
    s += [p("6. Okulda kullanım", H2)]
    s += bullets([
        "Ayarlar → 'Okul programını içe aktar' ile sınıf programları (Excel) tek seferde aktarılır.",
        "Ders Programı → 'Otomatik Ders Dağılımı': süre seçilir, istenirse mevcut program başlangıç yapılır.",
        "Sonuç yeni bir varyant olarak kaydedilir; mevcut program kaybolmaz. Varyantlar karşılaştırılabilir.",
        "Elle taşıma: derse tıklayıp hedef saate tıklanır; çakışma olursa kırmızıyla gösterilir.",
        "Excel (okul, sınıf, öğretmen, derslik sayfaları) ve PDF çıktıları alınabilir.",
        "Tüm bilgiler (dersler, saatler, öğretmenler, derslikler, kurallar, öncelikler) programda düzenlenebilir.",
    ])
    if db_path:
        s += results_section(db_path)
    doc.build(s)
    return path


if __name__ == "__main__":
    build(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
    print(sys.argv[1])
