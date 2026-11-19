# Brief rehberi: lider ile işçi etkileşimi

Lider (üst model) işi böler, her işçiye (alt model) brief yazar, sonucu doğrular. Amaç: işçinin bu brief ile tek başına çalıştığından daha iyi iş çıkarması ve token'ın brief'e değil işe gitmesi. Brief biçimi hedef modelin ailesine göre `aile-promptlama.md` adaptörüyle son hâlini alır; `ork brief` şablonu doldurur.

Kanıt düzeyi: **A** bağımsız/akademik ölçüm, **B** satıcı iç testi, **C** yalnız tavsiye, **T** tasarım çıkarımı, **DY** doğrulanamadı.

## 1. Ne zaman bölünür

| Kural | Kanıt |
|---|---|
| Bağımsız, ayrıştırılabilir genişlik işi paralel; sıralı ya da bağımlı zincir bölünmez (aynı ölçümde etki büyük artıdan büyük eksiye kadar oynadı) | Kim 2025 (A) |
| Çok ajan kaliteyi token harcayarak alır (ajan ~4x, çok ajan ~15x sohbet token'ı); çoğu kodlama işinde bölme varsayılan değil | Anthropic 2025 (B) |
| Lider doğrular; işçi çıktısı doğrudan birleştirilmez (merkezi doğrulamasız mimari hatayı yayar) | Kim 2025 (A) |
| Paralel yazmada kilit değil sahiplik manifesti + ayrı çalışma ağacı; ortak dosyalar (kilit dosyası, yapılandırma, göç numaraları) yalnız liderde | Cursor 2026, CC belgeleri (B) |
| 3-5 işçiyle başla; büyük fan-out (`siniflar.json` `fan_out.sondaj_esigi` üstü) öncesi tek işçiyle sondaj, kalanı P90 × `p90_carpani` ile planla | literatür (A) |
| Yeni iş türünde önce güçlü modelle taban kur, ölç, sonra ucuza in | OpenAI ajan rehberi (C) |
| Planlayıcı yazmaz, işçi planlamaz, yargıç yazmaz; ayrı entegratör ajanı darboğazdır | Cursor 2026 (B) |

Küçük işi bölme: her işçi bir brief, bağlam yüklemesi ve doğrulama maliyeti getirir.

## 2. Brief şablonu (üç katman, önbellek dostu)

A katmanı kardeş işçilerde bayt bayt aynıdır (önbellek önek isabeti); hash'i `olc` kaydına yazılır. Kardeşleri aynı model, efor, araç kümesi, şema ve dizinle aç.

```
[A. SABİT ÖNEK: kardeşlerde aynı; zaman damgası, rastgele kimlik, sırasız küme YOK]
ROL: <tek cümle>
ORTAK KURALLAR: <en çok 7 madde; yalnız gerçek değişmezler>
KARAR SÖZLÜĞÜ: <ad, stil, arayüz, birim, dil kararları>
ÇIKTI ŞEMASI: <dönüş sözleşmesi, aşağıda>
ARAÇLAR / YASAKLAR: <izinli araçlar; yazma yasakları; ağ>
DURMA KURALLARI: <bitti ölçütü sağlanınca dur; ekstra inceleme ya da alt ajan açma; bütçe aşımında kısmi dön>

[B. PROJE BAĞLAMI: iş başına bir kez]
HEDEF ve NEDEN: <2-4 cümle>
MİMARİ ÖZETİ: <işaretçiler: yol + satır aralığı; içerik değil>
PROJE GRAFİĞİ: proje grafiği varsa graphify-out/GRAPH_REPORT.md ve grafik sorgusunu oku; yoksa yoksay
SAHİPLİK TABLOSU: <parça -> sahip -> yazılabilir glob>

[C. DEĞİŞKEN UÇ: en sonda]
PARÇA: <kimlik>
YAZILABİLİR / OKUNUR / YASAK YOLLAR: <glob listeleri>
GİRDİLER: <dosya yolları>
KAPSAM DIŞI: <"X diğer işçinin">
UÇ DURUMLAR: <"şu olursa şunu yap">
BİTTİ ÖLÇÜTÜ: <çalıştırılacak komut + beklenen kanıt>
BÜTÇE: <en çok N araç çağrısı / M dk; kalan bütçeyi raporla>
```

**Dönüş sözleşmesi** (şema `data/sema/brief-donus.schema.json`):

```
{durum: ok | kismi | bloke | dogrulanamadi, ozet (≤ 2.000 token), dosyalar[], kanit[{tur, ref}], acik_sorular[], sonraki}
```

Ağır çıktı (günlük, tam diff, tablo) dosyaya yazılır; yanıtta yalnız yol. Uzun işte devir dosyası `devir.json` (şema `data/sema/devir.schema.json`): hedef, bitti ölçütü, özellikler [{id, kabul_komutu, durum, sahip, son_commit}], kararlar, bilinen sorunlar, bütçe. İşçi yalnız kendi `durum` ve `son_commit` alanını yazar, kabul komutunu değiştiremez.

## 3. Lider kuralları

| Kural | Kanıt |
|---|---|
| Kapsam dışı satırı zorunlu (belirsiz brief iki ajana aynı işi yaptırır) | Anthropic 2025 (B) |
| Karar sözlüğü zorunlu (örtük kararlar paylaşılmazsa çıktılar çelişir) | Cognition 2025 (B) |
| Alt ajan konuşma geçmişini görmez (fork değilse): gereken her kural brief'e yazılır | CC belgeleri (R) |
| Ayrıntılı ve doğrulanabilir brief toplam token'ı düşürür | Smékal 2026 (A) |
| Zayıf yürütücüye **hedef düzeyinde kısa plan**; uzun, koşullu "nasıl" yönergesi zayıf modeli bozar | COPE 2025-26 (A-) |
| Güçlü planı zayıf işçiye enjekte etmek işçinin kendi planından iyidir; aynı ailede kazanç büyüktür | CUDA 2026 (A-) |
| Lider-uzman ayrımı aynı modelle bile kazanç verir | Meta-Prompting 2024 (A) |
| Planlayıcı-yürütücü ayrımı token verimini artırır | ReWOO 2023 (A) |
| İşçiye canlı kalan bütçeyi göstermek maliyet-başarı eğrisini iyileştirir | BATS 2025 (A) |
| Dikkat dağıtıcı bağlam akıl yürütmeyi bozar: brief'ten ayıkla | Gema 2025 (A) |
| Güçlü modele adım listesi değil hedef, ölçüt, kısıt, girdi ver | literatür (A/C) |
| İşçiye "bu parça zor" yazma (aşırı düşünmeyi tetikler); zorluk bilgisi lidere ait, efor parametreyle yönetilir | T |
| Belirsizliği lider çözer; işçiye seçenek değil karar ver | T |
| İçerik değil işaretçi ver (yol + satır aralığı); yapıştırma yalnız kısa kritik parça | T |

"Üst modelin brief'i alt modeli tekil performansının üstüne çıkarır" etkisinin büyüklüğü doğrudan ölçülmedi (DY); dolaylı kanıt yukarıdadır. Ölçüm planı: aynı parça için (a) işçinin kendi planı, (b) liderin hedef düzeyi planı, (c) ayrıntılı adım planı; başarı + token `olc` ile karşılaştırılır.

## 4. Doğrulama, kaskad, oy

| Kural | Kanıt |
|---|---|
| Doğrulayıcı sırası: deterministik dış kanıt (test, tip, linter, şema, DOI/PMID/bağlantı sorgusu) > farklı aile + farklı kanıt/kip > farklı aile LLM > aynı aile farklı model; öz-denetim doğrulama sayılmaz | Huang 2023, Kim 2025, Han 2026 (A) |
| Farklı aile gerekli ama yeterli değil: güçlü modeller birlikte yanıldığında çoğunlukla aynı yanlışı verir; çare kip ve kanıt kaynağını da ayırmak | Kim 2025 (A) |
| Hakem kendi üretimini kayırır | Panickssery 2024 (A) |
| Kaskad ve best-of-N yalnız dış doğrulayıcıyla; öz-güven, uzunluk, üslup yükseltme sinyali değil | AutoMix, Brown 2024 (A) |
| Ucuz doğrulayıcı ucuz modelin yanlışlarının önemli kısmını kabul eder: kabul edilenlerin bir kısmı bağımsız denetlenir (`siniflar.json` `kaskad`) | Rajput 2026 (A) |
| Kaskad yalnız `p_yukselt < 1 - (c_ucuz + c_dogrulama) / c_guclu` iken kazandırır; baştan zor belliyse atlanır | Dekoninck 2024 (A/T) |
| Best-of-N: küçük N, ardışık + erken durdurma, her denemede efor/aile/brief farkı; hiçbiri geçmezse N artmaz, model yükselir | Brown 2024 (A/T) |
| Oy yalnız kapalı cevaplı, zor olmayan işte; ilk iki uyuşursa üçüncü çağrılmaz; tartışma turu yok; oy birliği "doğrulandı" değil "çelişki yok" demektir | Chen 2024, Smit 2024 (A) |
| Üç değerli sonuç: doğrulandı / çürütüldü / doğrulanamadı (kota, 429, zaman aşımı = doğrulanamadı) | CC davranışı (R) |
| Üretim/sentez en güçlü yeterli modelde; zayıf aileyi üretime "çeşitlilik" diye katma | Self-MoA 2025 (A) |
| Lider iki defter tutar (olgu/plan, ilerleme); N adım ilerleme yoksa yeniden planla | Magentic-One (B) |

**Yeniden planlama tetikleri** (`siniflar.json` `fan_out.yeniden_planla`): kabul komutu çıktısı turlar boyunca değişmiyor, aynı dosya üst üste yeniden yazılıyor, bütçenin büyük kısmı ilerlemesiz harcandı, analiz felci (uzun düşünme, araç yok).

**Nöbetçi kontrol listesi:** analiz felci, erken bitirme, görev sapması, eksik doğrulama, işçiler arası çelişen karar, döngü, boş çıktı, kırmızı test, kapsam dışı dosya, gizli veri gönderimi, uydurma kaynak (MAST, A).

## 4b. Toplu koşucu ve Claude Agent briefleri

- **`ork suru` öğe briefi:** ilk satır işçiye "İlk satıra `ÖZET:` ile en çok 200 karakterlik sonuç yaz" der; tam çıktı `cikti` dosyasına. Koşucu yalnız bu satırı lidere taşır.
- **agy toplu mikro öğe:** her öğe `### ÖĞE <id>` başlığıyla; yanıt `data/sema/agy-toplu.schema.json` (`{"ogeler":[{"id","yanit"}]}`); en çok 8 öğe, aynı model ve efor.
- **Claude Agent briefi (ince lider):** "Çıktıyı `<dosya>`'ya yaz, bana ≤ 10 satır özet dön" sözleşmesi; ham dökümü geri yapıştırma.
- **Kamu/dış parça:** bağlamdan kopyalanmaz, yeniden yazılır (`brief_kaynagi: yeniden_yazildi`); proje adı, yol, anahtar, kişi adı yok (`gizlilik.md` 5).

## 5. Bütçe

Bütçe öngörü değil devre kesicidir: aynı görevin koşuları arasında token büyük oranda değişir ve modelin kendi tahmini güvenilmezdir (A). Kullan: `olc` P90 + sert tavan (alt ajan `maxTurns`, print modunda `--max-turns`, elle köprüde zaman aşımı = 3 × tahmin). Modele "kaç token harcarsın" sorulmaz; yükseltme için pay bırakılır.
