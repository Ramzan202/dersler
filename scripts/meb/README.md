# MEB çerçeve programlarının çıkarılması

`app/data/meb_cerceve_2026.json` dosyası şu adımlarla üretildi:

1. https://meslek.meb.gov.tr/cercevelistele.aspx?sinif_kodu=9&kurum_id=1 sayfasındaki tüm alan PDF'leri indirildi (`upload/cop9/*.pdf`), sayfa `index.tsv` olarak kaydedildi (`dosya<TAB>alan adı`).
2. Her PDF `pdftotext -layout` ile metne çevrildi (`txt/` klasörü).
3. `parse.py` her "HAFTALIK DERS ÇİZELGESİ" tablosunu sütun konumlarına göre (9., 10., 11., 12. sınıf) okur; iki satıra bölünmüş ders adlarını birleştirir.
4. `build.py` dersleri sınıflandırır (ortak / meslek / seçmeli), "İşletmelerde Mesleki Eğitim" saatlerini ayrı tutar ve her sınıf için toplamı PDF'deki "TOPLAM DERS SAATİ" ile karşılaştırır. Toplamı tutmayan 5 tablo-sınıf içe aktarılmaz (`skipped_grades`).

Çalıştırma: `python build.py` (aynı klasörde `index.tsv` ve `txt/` olmalı).
