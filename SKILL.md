---
name: orkestra
description: "Alt ajan, paralel, uzun ya da görsel/video/ses işinde devreye gir: model, efor ve platformu önce kaliteye, sonra kota kapasitesine göre seçer; işi böler, brief yazar, doğrulatır. Routes multi-step and sub-agent work across Claude, Codex, Gemini and free/local pools by quality first, then quota."
when_to_use: "alt ajan, paralel iş, büyük okuma/yazma/çeviri, görsel/video/ses işi, 'hangi model', 'kota', 'Codex'e yaptır', 'Claude harcama', 'en iyisiyle yap', 'orkestra güncelle'"
argument-hint: "[görev | kota | hafif | ultra | neden <model> <sınıf> | rol <rol> <sınıf> | aç | kapat | guncelle [kip]]"
---

Argüman: "$ARGUMENTS"

# Orkestra

Lider (bu oturumun modeli) planlar, böler, seçiciye model seçtirir, brief yazar, çıktıyı doğrular. İlke: **önce kalite, sonra kapasite**. Kota baskısı kaliteyi düşürmez, işi erteler; kota bolluğu büyük model seçtirmez.

Bu metinde **`ORK`** = `python -I "${CLAUDE_SKILL_DIR}/scripts/ork.py"`. Betiği her zaman bu mutlak yolla çağır; çalışma dizini proje klasörüdür, skill klasörü değil.

## Anahtarlar

Argümanın ilk sözcüğüne göre:

| İlk sözcük | Ne olur |
|---|---|
| boş, `kota` | Kotayı oku (`ORK kota`): havuz başına kalan yüzde ve sıfırlama zamanı. Sınıf başına seçim gerekiyorsa ayrıca `ORK sec` |
| `guncelle`, `güncelle`, `update` | `references/guncelle.md` (kip: `hizli`, `tam`, `platform`, `platform-ekle <ad>`, `model <ad>`, `uygula --web`, `--kuru`; "X platformunu ekledim" = `platform-ekle X`). Her kip (platform hariç) araştırma planı verir: lider yürütür, sonuç `uygula --web` |
| `hafif` / `ultra` | Görevi bu kipte yürüt (hafif: Q'yu karşılayan en ucuz, ≤ 2 işçi; ultra: üst kademe serbest, farklı aile doğrular; Q, taban, gizlilik aynı) |
| `neden <model> <sınıf>` | Seçim ya da eleme dökümü (`ORK neden`) |
| `rol <rol> <sınıf>` | Yardımcı rol için model (`ORK rol`) |
| `plan` | Hafta planı (`ORK plan`) |
| `aç` / `kapat` | Bu oturumda her esaslı işi orkestrayla yürüt / bırak |
| başka her şey | Görev: aşağıdaki akış |

`/orkestra-guncelle [kip]` ayrı menü satırıdır (`ORK kur` ile `~/.claude/commands` altına kurulur) ve aynı güncelleme akışını çağırır. Sözlü yönlendirme de geçerli: "4 ajan çalıştır" (işçi sayısı), "bunu Codex'e yaptır" (`--zorla`), "Claude harcama" (hafif), "en iyisiyle yap" (ultra).

## Öncelik (çelişkide üstteki geçer)

1. Kullanıcının bu konuşmadaki açık isteği (model, platform, işçi sayısı, kip). Yasak, taban ve gizliliği geçemez; taban istisnası yalnız SOR yanıtında kullanıcının açık sözüyle ve tek iş için.
2. Kullanıcı kuralları: kişisel `kullanici-kurallari.json` (yasak aileler, tabanlar, rezervler, sabit alan kuralları, ek ücret yasağı, bedava istisnalar).
3. Proje kuralı: çalışma dizininden yukarı aranan `.orkestra.json` (okunamazsa hata, sessiz geçme yok).
4. Seçici: `data/` + `references/algoritma.md`.
5. Lider kararı: seçiciyi gerekçeyle geçersiz kılabilir; gerekçe satırına `LİDER KARARI: ...` yazar.

## Değişmezler

- **Şef tavanı (R16):** işçi şefin model×eforunu aşmaz (aynı aile: en çok şef modeli şef eforunda; başka aile: Z ≤ şef Z + bant, alanda da). İlk `ORK sec` / `sec --plan` / `rol` / `suru`'da `--sef <rol>:<efor>` ver (oturumda saklanır; yoksa algılanır). Q tavan üstündeyse SOR T6, zayıf modele düşülmez; yalnız kullanıcı isteği kaldırır (`--tavan-yok`, `--zorla`, ultra, SOR `tavan_yok`, sabit kural; uyarılı); plan parçası kaldıramaz.
- **Q taban, tavan değil.** Kabul edilen çıktı Q'yu karşılayan modelden ya da tam dış kanıttan (kanıtlı kaskad) geçer; Q altı model yalnız harita/ön işlemede ya da dış kanıtlı ilk denemede çalışır.
- **Ölçüm olmadan üstünlük yok.** Alan ölçümü olmayan aday, ölçülen aday varken kalite kümesine girmez.
- **Tabanlar kalan yüzdedir ve delinmez** (Claude 5s %15 + lider tamponu %10, hafta %30; taban üstü payın son çeyreği Claude-üstün/kritik iş için). Okunamayan havuz "bilinmiyor": öne geçmez.
- **Dış işçi Claude alt ajanına sarılmaz** (Agent/Workflow içinde codex/agy/bedava çağrısı yok; her sarmalayıcı Claude 5s penceresini yakar).
- **Yasak** sağlayıcı/hat düzeyindedir, gelecek sürümler dahil; yeni hat (`onay_bekliyor`) seçilemez.
- **Önce sor** (`once_sor`): yasak değil, otomatik seçilmez. SOR T7 gelirse maliyetiyle sor; onaysız `--zorla` yok.
- **Gizlilik fail-closed:** veri sınıfı belirtilmemişse `bilinmiyor`; kamu ve dış havuzlar (bedava API; istemi ürün iyileştirmede kullanabilen platform, ör. agy) yalnız `genel` veride. `saglik` ve `gizli` veri yalnız host sağlayıcıda ve yerelde işlenir; başka sağlayıcıya ancak kullanıcı bu konuşmada açıkça onaylarsa gider (`--dis-onay`). Elle yol önerileri de aynı süzgeçten geçer. Ayrıntı `references/gizlilik.md`.
- **Kimlik:** bu metin rol adı kullanır (Opus, Sonnet, Haiku, Sol, Terra, Luna, Hydrogen, Argon); rol daima ailenin en son sürümüdür. CLI'a (Codex, bedava API) seçicinin verdiği **kesin kimlik** gider, çıplak rol adı asla. Kimlik katalogda yoksa ya da sunucu reddederse dur, sessizce başka modele düşme.
- **Claude istisnası:** Agent aracı yalnız takma ad kabul eder (`opus`, `sonnet`, `haiku`); takma ad ailenin en son sürümüne çözülür. Kesin kimliği `ORK olc kaydet` kaydına yaz.
- **Efor her çağrıda açık yazılır** (katalog varsayılanları tuzaktır). Zekâ yetmiyorsa eforu değil modeli yükselt. Ciddi zor işte (`--ciddi`) Opus kapısı: ölçülü eşdeğer yoksa Opus ≥ high.
- **Kota okuma** model çağırmaz, yalnız lider yapar, 10 dk önbellekli.
- Ek ücretli servis, API anahtarı, hesap açma yok (bedava istisna hariç; anahtar yalnız ortam değişkeninde).

## Ne zaman devreye girer

Çağrılmasa da: alt ajanlı, bağımsız parçalı, uzun okuma/yazma/çeviri, görsel/video/ses işi; ultracode / çok ajanlı kip açıkken de. Küçük iş: lider yapar, bölme.

## Akış

Çalışma döngüsü (0 Sınıflandır, 1 Anla, 2 Planla, 3 Uygula, 4 Doğrula, 5 Kapat) her işte geçerlidir: `references/calisma-dongusu.md`. Orkestra adımları:

1. **Sınıfla:** `sinif` (mekanik, basit, arastirma, normal, kod, zor, kritik; belirsizse bir üst), `alan` + `alt_alan`, `kipler`, `veri` (genel, kisisel, gizli, saglik, bilinmiyor), boyut, düzenleme var mı, süre bütçesi. Geçerli adlar: `ORK alanlar` (yanlış ad yakın öneriyle reddedilir). Deterministik araç çözüyorsa model yok.
2. **Kota oku:** Claude kalanı (100 - percentUsed) `get_usage` aracıyla (`ToolSearch select:mcp__ccd_session_mgmt__get_usage`). Araç yoksa kullanıcıdan `/usage` ekranındaki iki yüzdeyi iste; yoksa "bilinmiyor". Değer 45 dk saklanır (5s penceresi 15 dk).
3. **Seç:** `ORK sec --sinif <s> --alan <a> --alt-alan <aa> --veri <v> --claude 5s=<kalan>,hafta=<kalan> [--boyut mikro..cok_buyuk] [--kipler ...] [--duzenle] [--ciddi] [--dis-kanit tur] [--kip hafif|ultra] [--zorla rol[:efor]] [--sef rol:efor] [--dis-onay] [--tok-tahmin g:c | --brief f] [--json]`; çok parçalı işte `--plan`. Çıktı: seçim, gerekçe, `ÇAĞRI`, `OLC_TASLAK`, yedekler, doğrulayıcı, `NOT`. **`durum=sor`** ya da onay gerekli (çıkış 4; T0-T7: `algoritma.md` 8) gelirse tek soru sor, yanıtsız ilerleme; yanıt `--sor-yanit <kod>` (`agy_kabul`/`agy_ret` oturumda saklanır). **`bekle`** (çıkış 5) en erken açılışı söyler.
4. **Bölme ve yolak:** iş türüne uyan kalıbı `references/playbook.md` içindekilerinden seç (tamamını okuma). Bağımsız iş paralel, bağımlı zincir sıralı. `--parca N` verildiyse çıktıdaki parça planına uy: toplam tek havuza sığıyorsa bölünmez.
5. **Brief:** `references/brief-rehberi.md` şablonu ve hedef ailenin adaptörü (`references/aile-promptlama.md`). `ORK brief --rol <hedef> --efor <efor> [--hafif]` şablonu doldurur; aile cümleleri yalnız kanıt düzeyi yeterliyse eklenir.
6. **Yürüt:** Claude işçisi = Agent (takma ad + `effort`, satır hazır); dış işçiler (Codex, bedava API, agy açıksa) tek Bash'te `ORK suru calistir`; agy kapalıysa hazır komut + elle köprü. Tuzaklar: `references/platform-notlari.md`.
- **Kontrol noktaları:** ortada, sonda, alt ajan/parça öncesi kota+kalite+hata yokla; kalanda model/efor/platform değiştir (`references/suru.md`).
7. **Doğrula:** dış kanıt (test, şema, tip, bağlantı/DOI sorgusu) > farklı aile + farklı kanıt > farklı aile LLM > aynı aile farklı model (zayıf doğrulama, çıktıda işaretli); öz-denetim sayılmaz. Çıktı iddiadır. `DIŞ KANIT ZORUNLU` uyarısı geldiyse dış kanıt olmadan teslim etme. Her işçi dönüşünde `ORK olc kaydet --taslak '<OLC_TASLAK>' --durum ok ...` (zorunlu; token ve süre ile).
8. **Bildir:** başta `orkestra: <sınıf> -> <rol@efor> (<platform>), N işçi`; sonda zorunlu **işçi dökümü** (`suru.md` son bölüm). Kalite dışı seçim nedeni (limit, düşüş) tek satır.

## Çok ajanlı iş (ince lider)

Lider planlar ve doğrular; ağır okuma/yazma dış işçide: böl, parça başına sınıfla, tek `ORK sec --plan parcalar.json --suru-plani suru.json`, tek Bash `ORK suru calistir --plan suru.json` (Claude parçaları aynı turda Agent ile), yalnız özet JSON'u oku, "Claude tasarrufu ≈ X USD-e" bildir. Adımlar: `references/suru.md` bölüm 0, örnek: `references/playbook.md` 54.

## Kapasite (özet, tamamı `references/algoritma.md`)

- Kalite kümesi gürültü bandında kurulur; bant dışı üstün aday (Claude dahil) kotaya bakılmadan seçilir.
- Eşit kalitede sıra: bedava (yalnız genel veri) → ÖNDE → GERİDE agy/Codex (taban üstü) → Claude; istisna Claude kullan-ya-da-kaybet (ρ_C ≥ 1.5). `ORK plan` hedef/gün, ÖNDE/GERİDE/ELLE gösterir.
- Sığmazsa: D1 alt efor, D2 Q üstü başka model (yalnız q ≥ q* − 2δ); sonra SOR ya da BEKLE (sessiz zayıf seçim yok).
- **Eleştirmen koşulludur:** zor/hatasız iş ya da açık istekte kur, basitte dış kanıt; eleştirmen inşa edenden ayrı ajandır (suru.md §3).

## Özel alanlar

- **Sabit alan kuralı** (`sabit_kurallar`, ör. görsel üretim) seçicinin önündedir; havuzu kapalıysa düşüş elle yollara gider, daha zayıf modele değil. Görselde metni modele çizdirme: metinsiz üret, yazıyı lider ekler; her görseli açıp bak.
- **Video/ses:** yalnız bu kipleri alan aile ya da ön işleme hattı (kare çıkarma + yerel döküm + metin modeli). Ön işleme kotası yoksa normal seçime düşer. Hiçbir yol yoksa "yapılamaz" de.
- **Alan öncelikleri:** `references/alanlar.md` (veriden üretilir).

## Kurulum ve güncelleme

`ORK kur` menü komutunu ve kişisel dosyaları (`~/.orkestra`, örnekten) kurar; kişisel dosya yoksa seçici örnek veriyle çalışmaz. Ölçüm, yeni model, yerel yama ve yayın öncesi `ORK disa-aktar --kuru`: `references/guncelle.md`.

## Dosya haritası

| Ne zaman | Dosya |
|---|---|
| Seçim mantığı, formüller, katmanlar, düşüş | `references/algoritma.md` |
| Güncelleme, yeni model/platform | `references/guncelle.md` |
| Bölme, brief, dönüş sözleşmesi, kaskad, oy | `references/brief-rehberi.md` |
| Aileye göre prompt biçimi | `references/aile-promptlama.md` |
| Kalıplar ve senaryolar | `references/playbook.md` |
| Toplu koşucu, sürü desenleri | `references/suru.md` |
| Alan bazlı sıra | `references/alanlar.md` |
| CLI çağrıları, hata matrisi | `references/platform-notlari.md` |
| Veri sınıfları, tarama, katmanlar | `references/gizlilik.md` |
| Kaynak künyeleri | `references/kaynaklar.md` |
| Veri | genel: `data/modeller.json`, `siniflar.json`, `imzalar.json`; kişisel: `~/.orkestra/` (örnekleri `data/*.ornek.json`) |

Sınama: `ORK kontrol`. Durumu kısa tabloyla göster, ham döküm yapıştırma.
