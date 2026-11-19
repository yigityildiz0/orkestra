# Toplu koşucu (`ork suru`)

Dış işçileri (bedava API, otomatik agy, Codex) **tek Bash çağrısıyla** paralel yürütür. Lider yalnız ≤ 4 KB özet JSON'u ve gerekli çıktı dosyalarını okur. Dış işçi bir Claude alt ajanına sarılmaz: her sarmalayıcı kendi bağlamıyla (~15-25K sistem + araç + keşif) Claude 5s penceresini yakar. Platform ve model adı kodda yoktur; sınırlar, şablonlar ve kardeşler kişisel `platformlar.json` içindeki `suru` bloklarındadır.

## 0. İnce lider akışı (SKILL.md "Çok ajanlı iş")

Lider planlar ve doğrular; ağır okuma/yazma dış işçide. Uçtan uca örnek: `references/playbook.md` 54.

1. **Böl:** bağımsız parçalar; bağımlılar zincir.
2. **Sınıfla:** parça başına `sinif, alan, alt_alan, veri, boyut, duzenle, dis_kanit`; kişisel parçayı kamu parçadan ayır.
3. **Seç (tek çağrı):** `ORK sec --plan parcalar.json --suru-plani suru.json --claude 5s=..,hafta=.. [--sef rol:efor]` → parça seçimleri (brief boyutundan token tahmini, kota rezervasyonu, şef tavanı), `CLAUDE` satırları, birleşik `SOR`, tasarruf. Plan düzeyi `sef` koşucu planına (`suru.json`) taşınır.
4. **Yürüt:** tek Bash `ORK suru calistir --plan suru.json`; aynı turda yalnız Claude seçilen parçalar Agent ile paralel ("çıktıyı <dosya>'ya yaz, ≤ 10 satır özet dön").
5. **Doğrula:** dış kanıt koşucuda ya da liderde; lider yalnız özet JSON'u (≤ 4 KB) ve başarısız öğelerin çıktısını okur.
6. **Bildir:** mevcut biçim + "Claude tasarrufu ≈ X USD-e (%Y)"; delege edilen kısımda Claude maliyeti ~%75-98 düşer.

## 1. Komutlar

```
ork sec --plan parcalar.json --suru-plani suru.json --claude 5s=..,hafta=..     # seçim + plan (tek çağrı)
ork suru calistir --plan suru.json [--paralel N] [--kuru] [--dusus izinli|yok] [--sef rol:efor] [--tavan-yok] [--json]
ork suru durum --is <is_id>
ork suru temizle --agy [--gun 7] [--uygula]       # agy konuşma DB'si; --uygula: Geri Dönüşüm Kutusu
```

- `--kuru`: tarama + çözüm, sıfır istek, kota/durum dosyası yazılmaz. `--dusus yok`: kardeşe düşüş kapalı (kardeş tanımlı olsa da; hata olarak döner). Varsayılan `izinli`.
- Şemalar: girdi `data/sema/sec-plan.schema.json`, koşucu planı `suru-plan.schema.json`, özet `suru-ozet.schema.json`, agy toplu yanıt `agy-toplu.schema.json`.

## 2. Plan öğesi

`{id, brief, cikti, hedef: {yol, platform, havuz, model, kimlik, efor, kip} | {sec: {...istek}}, veri, desen?, bagimli?, max_tokens?, zaman_asimi_sn?, dogrulama?: {tur: test|sema|yok, komut?}, boyut?, k?, cevap_deseni?, turkce?}`

- `hedef.sec` verilirse koşucu öğeyi kendisi seçtirir; öğeler sırayla ve kota rezervasyonuyla çözülür (N öğe aynı anlığı N kez saymaz, `plan_sec` kuralı).
- Açık `hedef` (ör. elle yazılmış plan) de, kardeş, oy adayı ve yargıç da aynı sert denetimden geçer: yasak aile, şef tavanı (plan `sef`; yoksa `--sef` > oturum kaydı > algılama; efor verilmemiş hedefte en yüksek Z'li varyant varsayılır), havuz bitişi/kapalı, soğuma, taban (CLI her koşuda kotayı taze okur), agy kapısı. Geçmeyen öğe `engel` ya da `bekle`, sıfır istek.
- Claude hedefli öğe **çalıştırılmaz**: özetin `claude_isleri[]` listesinde hazır Agent satırıyla döner; lider aynı turda Agent ile paralel başlatır.
- `bagimli`: önce bağımlılar biter; başarısız bağımlılık öğeyi `bekle` yazar (yürütülmez).

## 3. Güvenceler

- **İnşa ≠ eleştiri:** eleştirmen, inşa eden ajandan ayrı bir ajandır (ayrı bağlam, yalnız hata bulma görevi; model aynı olabilir). Gerekçe: hata bulmakla görevli ajan, kendi işini savunan inşacıdan daha çok hata yakalar (öz-düzeltme sınırı; ayrı doğrulayıcı üstünlüğü). Düzeltme mümkünse üçüncü bir ajanda yapılır: inşa → bağımsız eleştiri → düzeltme.

| Ne | Kural |
|---|---|
| Gizlilik | Her öğe gönderimden önce `araclar.tara()` + `kisi_saglik_tara()`. `kamu`/`dis` hedefte tam kişisel tarama + yalnız `veri=genel`; `ozel` dış hedefte sırlar (`SIR_DESENLERI`, yüksek entropi, ortam anahtar değerleri), kimlik/finans (TCKN/IBAN), `yasak_yol` ve kişi-düzeyi sağlık kaydı her zaman engellenir (`saglik`/`gizli` veri `--dis-onay` olmadan geçmez). Bulgu → `engel`, sıfır istek |
| Eşzamanlılık | Platform (`hesap_eszamanli_kullan`) ve model (`model_eszamanli`) semaforları |
| Bedava 5 dk penceresi | Token penceresi `pencere_5dk_tampon` altına inince HOLD (en çok 10 dk); boşalmazsa öğe `bekle` (rezervasyonsuz gönderim yok). Ağ hatası/zaman aşımı yeniden deneme dalına girer |
| 503 | `Retry-After` + jitter, geri çekilme listesi; `ardisik_503_kardese` kez üst üste → `kardes` listesindeki eş sınıf model (`kardes_kosul`: ör. Türkçe öğede İngilizce-only modele düşmez). Daha zayıf sınıfa asla |
| 429 adil pay | Model semaforu beklenir; deneme sayılmaz |
| agy | Kapı her çağrıda yeniden denetlenir (fail-closed: kapalıysa açık hedef de `engel`). Tavan ve eşzamanlılık semafor içinde, süreçler arası kilitle (`agy.lock`) ve BAŞLANGIÇ kaydıyla sayılır: tek koşu da paralel iki koşu da tavanı aşamaz. Başlatma aralığı, teyitsiz profilde daha sıkı tavan. Askı işareti (403, forbidden, suspend, PERMISSION_DENIED, restricted, banned) stderr'de her zaman, stdout/yanıtta yalnız başarısız çağrıda aranır; ilkinde `durum.agy_otomatik_kapali`. 2 ardışık kalıcı/kota hatasında (RESOURCE_EXHAUSTED dahil) bu koşuda agy durur. Değişmemiş ikili: ilk kullanımda sha256 kaydı, sonra karşılaştırma. Yalın profil dosyası `doğrulandı` iken yoksa `engel`. `--model` ve `--effort` her çağrıda zorunlu |
| Codex | `service_tier="default"`, efor açık, `--ignore-user-config` (401'de bir kez bayraksız; sonraki koşular doğrudan yedekle ve özette NOT: kullanıcı yapılandırması ve AGENTS.md yüklendi), brief stdin'den |
| Test yargıcı | Komut listesi, `shell=False`, Python `-I`, zaman aşımı; model çıktısının geçici klasördeki KOPYASI üzerinde, o klasör çalışma dizini ve sırsız ortamla (anahtar/token değişkenleri düşer). Ağ kapatılamaz: test komutu çıktıyı o klasör dışında içe aktarmamalı |
| Alt süreç ortamı | agy, Codex ve test süreçlerine kayıtlı anahtar/taban değişkenleri ve `*_KEY`, `*_TOKEN`, `*_SECRET`, `*_PASSWORD` gibi adlar geçmez |

## 4. agy otomatik yol

- Kapı: kişisel `agy_otomatik.acik` + `durum.agy_otomatik_kapali` yok + (`isci_profili.dogrulandi` ya da `kisisel_baglam_kabul` ya da bu oturumdaki SOR T4 yanıtı `agy_kabul`). Kapalıysa seçici `agy-elle` (hazır komut) döner; seçim Claude'a düşecekse SOR T4 kabul/ret sorar (yanıt oturumda saklanır). Koşucu da kapıyı her çağrıda denetler.
- İstem argv ile gider (≤ 28 000 karakter; `-p -` stdin okumaz). Başarı ölçütü: `response` dolu. `SUCCESS` + boş yanıt ya da `denied_actions` → hata, bir kez "Araç kullanma; yalnız metin yanıt ver." önekiyle yeniden.
- Mikro öğeler aynı (model, efor) grubunda en çok 8'li tek çağrıda toplanır (`### ÖĞE <id>` başlıkları, yanıt `agy-toplu` şeması); çağrı sabit yükü (~26-40K token) öğelere bölünür.

## 5. Desenler (yalnız kalite kattığı yerde)

| Desen | Ne | Ne zaman |
|---|---|---|
| `oy` | `oy_adaylari` ile k yanıt; ilk iki uyuşursa üçüncü çağrı yok | Kapalı cevaplı, zor olmayan iş |
| `aday_yargic` | k aday + yargıç (test yargıcı varsa önce o) | Dış kanıtı olan kod/dönüşüm |
| `harita_indirgeme` | Parçalar ayrı öğeler (bedava işçi), indirgeme `bagimli` öğe olarak Q'yu karşılayan modelde (koşucuda ayrı yürütücü yok, plan biçimidir) | Uzun belge, çok dosya |
| `toplu` | Mikro öğe paketleme (agy-oto + `boyut: mikro` + bağımsız öğede kendiliğinden) | agy mikro iş |

## 6. Özet ve kayıt

- Özet (stdout, ≤ 4 KB, aşarsa `kirpildi: true`): `is_id, sure_sn, sayac{ok,kismi,engel,hata,bekle}, isler[{id, durum, model, havuz, cikti, ozet (işçinin "ÖZET:" satırı, ≤ 200 karakter), tok, deneme, dusus, dogrulama}], claude_isleri, kota_farki_tahmini, claude_tasarruf_usd_e, notlar`.
- Her çağrı `olc` kaydı yazar (yol `suru`, token, süre, durum, hata sınıfı, deneme, kardeş düşüşü, `yukseltme`). İş özeti `~/.orkestra/suru/<is_id>-ozet.json` (`ork suru durum`).
- Brief'in ilk satırı işçiye `ÖZET:` satırı yazdırır (`references/brief-rehberi.md`).

## 7. Kontrol noktaları ve sürekli yeniden değerlendirme (R17)

- **Lider kontrol noktaları:** iş başladıktan sonra seçim donmaz. Lider **işin ortasında**, **sonunda** ve **her yeni alt ajan/parça gönderiminden önce** kota anlığını, işçi dönüş kalitesini, hata/boş yanıt/yeniden deneme oranını ve kalan işi kontrol eder; gerekirse kalan parçalarda model, efor ya da platform değiştirir.
- **Dalga arası yeniden değerlendirme (`ork suru`):** her dalga (`wave`) arasında:
  1. Kota anlığını tazeler (`kota_okuyucu` ya da önbelleksiz canlı okuma `kota.oku(..., onbellek=False)`).
  2. Tamamlanan dalgadaki işçi dönüşlerini değerlendirir: başarısızlık, boş yanıt ya da yüksek yeniden deneme oranında (`>= 1 - histerezis` veya `deneme >= en_cok_deneme`) kalan parçalarda bir üst efora ya da bir üst modele (`delta.aa_z` anlamlı farkla) çıkar.
  3. Kullanılan havuz tabana yaklaşır (`kalan - taban <= esitlik_bandi`) ya da kapasite/kota hatası alırsa eşdeğer, anlamlı derecede daha rahat (`kova_adim`/`esitlik_bandi`) başka bir havuza geçirir.
  4. Otomatik `sec` parçalarında sağlıklı dalgada kota/katman anlamlı değişmişse (`P_yeni < histerezis * P_eski`) seçimi tazeler.
- **Histerezis ve değişmezler:** aynı parça için ardışık iki dalgada tersine geçiş (ör. yukarı→aşağı ya da A→B→A havuz zıplaması) yapılmaz; gürültü bandı içinde geçiş yok. Şef tavanı (R16) ve kalite tabanı (`Q`) her zaman korunur; açık yeni dalga kontrolünde hedef tabana inmişse `bekle` işaretlenir.
- **Kayıt:** her değişiklik gerekçesiyle `olc` kaydının `yukseltme` (`{"var": true, "neden": ...}`) alanına ve koşu özetindeki `notlar` listesine yazılır.

## İşçi dökümü (zorunlu kapanış raporu)

Alt ajan ya da dış işçi çalıştıysa lider, iş sonunda kullanıcıya bu dökümü verir. Kısa yanıt istense de kısaltılır, kaldırılamaz. İşçi çalışmadıysa tek satır: "işçi çalıştırılmadı, lider yaptı".

| Platform | Model (rol + kesin sürüm) | Efor | Adet | Ne için | Sonuç |
|---|---|---|---|---|---|

- Her işçi grubu bir satır; aynı model ve eforla aynı işi yapanlar tek satırda, adetle.
- Sonuç: tamam / yarım / hata. Kota ya da hata yüzünden başka modele aktarıldıysa "X'ten Y'ye aktarıldı" yaz.
- Altına toplam: kaç işçi, kaç platform.
