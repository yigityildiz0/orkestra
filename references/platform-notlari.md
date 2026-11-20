# Platform notları

Çağrı şablonlarının tek kaynağı kişisel `platformlar.json` (`~/.orkestra/`; örnek: `data/platformlar.ornek.json`) `cagri` alanıdır; seçici (`ork sec`) satırı doldurur. Bu belge şablonların arkasındaki tuzakları ve hata davranışını anlatır. `{kimlik}` her zaman seçicinin verdiği kesin model kimliğidir; rol adı CLI'a verilmez.

## 1. Claude Code (lider ve Claude işçisi)

- **İşçi = Agent aracı:** `model` (yalnız takma ad: opus, sonnet, haiku; kesin kimlik kabul edilmez, takma ad ailenin en son sürümüne kendiliğinden kayar) + `effort`. Kesin kimlik `ork olc kaydet` kaydına yazılır. **`claude -p` işçi değildir:** masaüstü oturum kimliği alt sürece geçmez ("Not logged in"); Codex ya da agy host iken Claude işçi yolu yoktur.
- **Kota:** lider `get_usage` JSON'unu verir (`ork kota --claude '<json>'`; biçim `plan.windows[]`, `percentUsed`, `resetsAt`; modele özgü "Weekly · <model>" alt sayaçları havuz penceresi sayılmaz; `status` ok değilse bilinmiyor).
- **Model öncelik sırası:** çağrıdaki `model` > ajan tanımındaki `model` > `CLAUDE_CODE_SUBAGENT_MODEL` > ana model. Yalnız-zorlama değişkeni tüm alt ajanları tek modele kilitler: kullanma.
- **Yerleşik Explore** abonelikte ana modelde çalışabilir: `~/.claude/agents/Explore.md` (aynı adlı kullanıcı alt ajanı yerleşiği geçersiz kılar ve kendi `model` alanını korur) salt okuma araçları ve `kullanici-kurallari.json` `ajan_dosyalari.explore` eşlemesiyle `ork ajanlar --yaz` tarafından üretilir.
- **Ajan dosyaları** (`~/.claude/agents/*.md`) yönlendirme kaynağı değildir; `ork ajanlar --denetle` yasak hat, Q altı ve eski nesil sapmasını raporlar.
- **Efor:** Agent aracı çağrı başına `effort` alır (low, medium, high, xhigh, max; kurulu istemcide doğrulandı); tanım dosyasında `effort:` ve `CLAUDE_CODE_SUBAGENT_EFFORT` daha zayıftır. Seçicinin çağrı satırı eforu her zaman yazar. Efor oturum içinde sabit tutulursa önbellek korunur.
- **Önbellek:** ana oturum önbelleği uzun, alt ajan/workflow önbelleği kısa; aynı önek ≥3 kez okunacaksa uzun TTL ayarı değerlendirilir. Model değişimi önbelleği sıfırlar; `model:` alanlı skill/komut akış içinde kullanılmaz.
- **Limit davranışı:** yedek model bayrağı yalnız aşırı yük/erişilemezlikte tetiklenir, kullanım limitinde tetiklenmez. Haftalık ve oturum limiti tüm modellerde ortaktır (`/model` değiştirmek işe yaramaz). Etkileşimli oturum sıfırlamayı bekleyebilir; print modu ve arka plan beklemez.
- **Araç çıktısı:** test/derleme çıktısını `tail` ya da hata deseniyle süz; araç yanıtı varsayılan sınırı aşan çıktı dosyaya.
- **Hızlı (fast) kip** ek kullanım kredisi ister: ek ücret yasağı varsa kullanma.

## 2. Codex

```
{ikili} exec -m {kimlik} -c model_reasoning_effort="{efor}" -c service_tier="default" -s {sandbox} --skip-git-repo-check --ephemeral --ignore-user-config --json -o {cikti} - < {brief_dosyasi}
```

- **Brief stdin'den:** `-` ile brief dosyadan okunur; uzun brief komut satırı sınırına, tırnak ve `$` kaçışına takılmaz. `{sandbox}` seçicide dolar (düzenleme varsa `sandbox_duzenleme`, yoksa `sandbox_varsayilan`); dolmayan alanlar çıktıdaki `bos_alanlar` listesindedir.

- **İkili yolu sürüm taşır:** birden çok kurulum yolu olabilir (PATH, masaüstü uygulama paketi); keşif Appx paket kökünü kayıt defterinden (`PackageRootFolder`, yönetici gerekmez) bulur, `--version` ile en yeniyi seçer (`ikili_coz`).
- **`service_tier="default"` ve `--ignore-user-config`:** kullanıcı yapılandırmasındaki hızlı kip (kotayı katlar) ve varsayılan yüksek efor işçiye geçmez. Bayrakla kimlik doğrulama ilk çağrıda doğrulanacak [DY]: 401'de bir kez bayraksız denenir (`auth_yedek_cikar`).
- **Kota:** app-server `account/rateLimits/read`; `usedPercent 0` olan pencerede sıfırlama zamanı yoktur (kayan); `ordinaryUsageAllowed:false` havuzu kota soğumasına alır. **Sıfırlama kredisi** (`ek.reset_kredisi`) geri alınamaz: yalnız SOR T3 ile, kullanıcı onayıyla. Plan/deney kaydı bırakan uygunluk okumaları onaysız yapılmaz.
- **Efor her çağrıda yazılır;** katalog varsayılanı düşük olabilir.
- **`-s` (sandbox) asla atlanmaz.** Salt okuma işte `read-only`; yazdıran işte `workspace-write -C <klasör>` (klasör dışı için `--add-dir`).
- **Windows'ta yazdıran iş:** `--ignore-user-config` kullanıcının `[windows] sandbox` ayarını da düşürür; varsayılan kum havuzu dosya yazmayı ve komut çalıştırmayı reddeder ("ortam politikası engelledi"). Yazdıran işte `-c 'windows.sandbox="elevated"'` ekle (kullanıcı bu kipi bir kez kurmuş olmalı; değilse `"unelevated"` dene). İlk çağrıda tek satırlık yazma + komut denemesiyle doğrula.
- **Görsel girdisi** `-i <dosya>` verilirken brief yine stdin'den gelir; stdin boş bırakılırsa (`< /dev/null`) brief'i argüman olarak ver, yoksa süreç asılı kalır.
- **Yapılandırılmış çıktı:** `--output-schema f.json -o sonuc.json` yalnız son iletiyi yazar. `--json` olay akışında `turn.completed.usage` (girdi, önbellekli, çıktı, akıl yürütme) bedava ölçümdür: `olc` kaydı buradan beslenir.
- **Kısa model adı** (yalnız rol adı) istemcide sessiz kabul edilip sunucuda yanıltıcı hata verebilir: daima tam kimlik.
- **Profil:** `codex -p <ad>` ayrı yapılandırma dosyası okur. Bedava OpenAI uyumlu platformla profil yolu, kullanıcı düzeyindeki ajan talimat dosyasının (AGENTS.md) kamu havuza gitmediği doğrulanana kadar **kapalıdır**.
- **Görsel üretim:** çağıran model sabit kuraldaki rol ve efordur; brief "görsel üretim aracınla üret ve şu klasöre kaydet" der, tek seferde. Kalite kolları görsel modelin kendisi, `quality`, `size` ve prompt'tur (konu, kompozisyon, tırnak içinde yazılacak metin, korunacak/değişecek ayrımı). Görselli tur kotayı metin turundan hızlı tüketir.
- **Hızlı kip** kotayı katlar; varsayılan değil.
- **Uzun oturumu bölmek** efor düşürmekten çok kota kurtarır (maliyeti bağlam uzunluğu × çağrı sayısı belirler).
- **Efor (Sol ailesi):** en son Sol sürümünde `low` uçurumdur (Z ve alt testler sert düşer), `medium` sonrası kazanç küçüktür; taban `medium`, olağan iş `medium`/`high`. `max` yalnız açık istekte. Katalogdaki `ultra` bir mod, efor değil: Z'si yoktur, seçilmez.
- **Bağlam:** modelin API bağlamı CLI varsayılanından büyük olabilir (Codex varsayılanı kısa pencere; uzun pencere `model_context_window` ister ve uzun bağlam eşiğinin üstünde girdi ücreti artar). Seçici CLI kataloğundaki değeri kullanır.
- **Kredi:** modelin Codex kredi oranı resmî fiyat sayfasından `kredi_carpani` olarak tutulur; yeni sürümde orana güvenme, sayfadan oku.

## 3. Antigravity (agy) ve otomatik çağrı izni olmayan platformlar

```
{ikili} -p "{istem}" --model {taban} --effort {efor} --mode {plan|accept-edits} --output-format json --print-timeout {sure}
```

- **Otomatik yol (`agy-oto`)** yalnız kişisel `agy_otomatik.acik` ve yalın işçi profili doğrulanmış (ya da kişisel bağlam kabul edilmiş: kişisel kayıt ya da oturumdaki SOR T4 `agy_kabul`) iken; yürütücü `ork suru` (`references/suru.md`). Güvenceler: kapı her çağrıda, eşzamanlılık ve tavan süreçler arası kilitle, başlatma aralığı, ilk 403'te ve 2 ardışık kalıcı/kota hatasında kapanış, değişmemiş ikili (sha256), sırsız alt süreç ortamı; kod agy kimlik dosyalarını açmaz.
- **`--model` ve `--effort` zorunlu:** model verilmezse varsayılan (çoğu kez en pahalı) model yanar; tam slug + `--effort` birlikte çıkış 1 verir. İstem argv'dedir (≤ 28 000 karakter; `-p -` stdin okumaz).
- **Başarı ölçütü `response` dolu:** `SUCCESS` + boş yanıt ya da `denied_actions` hatadır (bir kez "araç kullanma" önekiyle yeniden).
- **Kişisel bağlam:** her `-p` çağrısı kullanıcının MCP sunucularını, oturum kancasını ve GEMINI.md'yi yükler (~26-40K sabit token + kişisel bağlam): yalın profil doğrulanmadan otomatik yol kapalı (fail-closed).
- **Ek ücret:** `/config` `useG1Credits:true` ise havuz kapalı sayılır.
- **Konuşma DB'si** çağrı başına birikir: `ork suru temizle --agy` (Geri Dönüşüm Kutusu, kullanıcı çalıştırır).

- **Elle köprü:** platformun şartları üçüncü taraf ajandan otomatik çağrıyı desteklemiyorsa (`imzalar.json` `otomatik_cagri_izni: false`, `kullanici-kurallari.json` `agy_otomatik: false`) orkestra brief + hazır komut satırı üretir, kullanıcı kendi terminalinde çalıştırır, çıktı dosyasını orkestraya okutur. Kullanıcı yoksa seçimin otomatik alternatifi yürür, elle öneri rapora yazılır.
- **Kip ve izin (headless):** başsız modda onay isteyen araç sessizce reddedilir (çıkış 0); `--mode auto` bu hesapta yok. Headless modda izin için `--settings` ile `permissions.allow` (ör. `read_file(<klasör>/**)`, `run_command(cargo *)`) verilir; medya/dosya okuyan işte `--mode accept-edits` (ve yalnız okunacak dosyalar), salt düşünmede `--mode plan`.
- **Efor ayrı bayrakla** (`efor_bayragi: true`): slug taban kimliktir; liste platformun model komutundan, eforlar `/effort`.
- **Her iş yeni çağrı** (oturum sürdürme yok); küçük işleri ayrı çağrılarla gönderme: boş çağrı bile on binlerce token sabit yük taşır, tek brief'te topla.
- **Kota okuma:** `/usage` kovaları (`agy_kovalar` ile havuz penceresine eşlenir; eşleme yoksa bilinmiyor); okuma ±0.01 oynar: varsayılan 1 okuma (`--taze` ile 3, en düşüğü). Kapı açıkken 10 dk önbellek dışında; kapı kapalı ama kişisel karar açıkken oturum (5 sa) başına bir kez; 403 kapanışında hiç. Her okuma `agy-cagri.jsonl`'a yazılır ve kendi saatlik tavanına (`saatlik_okuma_tavani`, varsayılan 6) sayılır. Git Bash'te slash komutları için `MSYS_NO_PATHCONV=1` gerekir (yoksa `/usage` bir dosya yoluna çevrilir ve gerçek model çağrısı olur; alternatif: PowerShell ya da Python alt süreci).
- **Görsel üretim aracı** çıktıyı çalışma klasörüne değil platformun konuşma klasörüne yazar.
- **JSON zarfı:** `response`, `status`, `usage`, `conversation_id`, `duration_seconds`; `status` başarı değilse sonucu kullanma.
- **Gizlilik:** istem ve kod platform iyileştirmesinde kullanılabilir: havuz `dis` sayılır (`gizlilik.md`).
- **Canlı web araması yok (başsız mod):** `-p` çağrısında web aracı onay ister ve sessizce reddedilir (çıkış 0, boş ya da kaynaksız yanıt). Platform kaydında `yetenekler.web_arama: false`; seçici `web` alt alanında agy'yi aday yapmaz. Araştırma briefinde 'emin değilsen boş bırak' cümlesi bu durumu gizler: boş dönen araştırma çıktısı başarı sayılmaz.

## 4. Gemini ailesi (agy içinde ya da API)

- Video ve ses girdisini doğrudan alan aile budur; diğer ailelerde ön işleme hattı gerekir.
- Sabit düşünme bütçesi, en düşük düşünme düzeyi ve aralık dışı sıcaklık hata verir ya da yok sayılır; düşünme kapatılamaz.
- Ham JSON araç çağrısı yerine yerel araç bildirimi.
- Açık önbellek yok, örtük önbellek var; ajan döngüsünde her istek yeterli yeni token eklemezse son kısım yeniden ücretlenir.

## 5. Bedava OpenAI uyumlu platform eklentisi

- Ayrıntı (ad, taban URL, model listesi, bitiş tarihi, ortam değişkeni adı) yalnız `platformlar.json` ve `kullanici-kurallari.json` `bedava_istisna` içindedir; genel kodda platform adı yoktur.
- Metin işi doğrudan HTTP (`ork bedava ...`); dosya düzenleyen iş Codex profiliyle temiz kopyada. Göndermeden önce gizlilik taraması (`gizlilik.md`); taranamayan dosya varsa gönderim yok.
- Anahtar yalnız ortam değişkeninden; yalnız https taban adrese gider; yönlendirme izlenmez.
- Bitiş tarihi geçince havuz kendiliğinden `kapali`; kod hatasız çalışmaya devam eder.
- **Dayanıklılık:** 503 (sunucu dolu) geri çekilme + eş sınıf kardeş; 429 adil pay (model başına eşzamanlılık) deneme sayılmaz; 5 dk token penceresi dolunca bekleme; 400 kalıcı. Ayrıntı ve sınırlar kişisel `platformlar.json` `suru`, koşucu `references/suru.md`.
- **Efor tuzağı:** bazı modellerde efor verilmezse en yüksek efor çalışır: efor her istekte açık.
- Efor takma adları tek varyant sayılır; dağıtım zamanı çıkış tarihi değildir; ağırlık hassasiyeti değişimi (ör. düşük hassasiyetten yükseğe) parmak izi değişikliğidir.

## 6. Yerel

- Yerel araçlar (döküm, TTS, görsel/video üretim) kota yemez; sınır VRAM ve süredir, GPU aynı anda bir iş.
- Sunucu gerektiren araç kapalıysa önce başlat; indirme, ağırlık ve önbellek kullanıcı kuralındaki disk kısıtına tabidir.

## 7. Hata matrisi

| Belirti | Sınıf | Davranış |
|---|---|---|
| 429 + `retry-after` | gecici | bekle + jitter (±%25), aynı model |
| Kademeli artış sınırı | gecici | dakikada bir adım artır |
| Harcama sınırı (retry-after yok) | kota | yeniden deneme yok; havuz soğumaya, başka aday |
| 529 / aşırı yük | kapasite | kotaya yazılmaz; model başına kısa soğuma |
| "Selected model is at capacity" | kapasite | kısa bekleme, sonra aynı bant kardeş model |
| Havuz kovası %0 | kota | aynı platformda diğer havuz ya da sıradaki aday |
| Bedava API 429/503 | gecici/kapasite | soğuma kaydı; kardeş model (Q altına inmeden); günlük kotada `*` soğuma |
| 400 "model not supported" / kimlik yok | kalici | dur; sessiz düşüş yok; NOT satırı |
| Zaman aşımı, boş çıktı | bilinmiyor | doğrulanamadı etiketi; checkpoint'ten yeniden |

Kurallar: yeniden deneme tek katmanda (CLI'lar zaten dener); orkestra çıkışı sınıflar, `~/.orkestra/durum.json`'a soğuma yazar, havuz ya da model değiştirir. Yazan işçi hatada kaldığı yerden değil checkpoint'ten başlar; parça bitmeden havuz değiştirilmez. Toplu fan-out kademeli açılır (1, 2, 4, 8).

## 8. Kota kaynağı: Cetvel keşfi ve `ORKESTRA_KOTA_KAYNAGI`

`ork kota` (ve seçici) kalan kotayı şu sırayla alır; her adım geçmezse bir sonrakine düşer, bozuk veri sessizce kullanılmaz:

| Sıra | Kaynak | Not |
|---|---|---|
| 1 | `ork kota --servis <yol>` | Tek çağrılık elle yol. `kapali` bu çağrıda servisi kapatır |
| 2 | `ORKESTRA_KOTA_KAYNAGI` ortam değişkeni | Servis anlık dosyasının tam yolu. `kapali` (ya da `yok`, `off`, `false`, `0`) servisi ve keşfi tümüyle kapatır, yalnız kendi okuyucular çalışır |
| 3 | Cetvel keşfi (varsayılan) | `%LOCALAPPDATA%\Cetvel` (ya da `CETVEL_DIZINI`) içinde `orkestra-uyum.json`, yoksa `anlik.json`. Cetvel kurulu değilse bu adım sessizce atlanır |
| 4 | Kendi okuyucular | Codex app-server, agy (izinliyse), bedava API, Claude için lider okuması (`--claude`) |

- **Kabul koşulu** (`servis_anligi`): `sema = 1`, `yazan = "rust-servis"`, her havuzda geçerli durum ve `kalan` ∈ [0, 1], `zaman` ≤ 10 dk eski. Cetvel'in `anlik.json` v2 belgesi (`sema = 2`) bu sözleşmenin dışındadır; orkestra pratikte `orkestra-uyum.json` okur.
- **Düşüş:** bayat, bozuk JSON, şema hatası ya da sözleşme dışı dosyada kendi okuyucular çalışır ve çıktının `notlar` alanına `KOTA KAYNAĞI: yedek (<neden>)` yazılır.
- **Kısmi kapsam:** serviste olmayan havuz (ör. bedava API) yalnız o havuz için kendi okuyucuyla okunur; servisin verdiği havuzlar için Codex/agy tekrar sorgulanmaz. Claude 5s ve haftalık değeri her durumda lider okumasından (`get_usage`) gelir.
- **Doğrulama:** `ork kota --json` çıktısında `yazan: "rust-servis"` ve notlarda `KOTA KAYNAĞI: Cetvel (otomatik keşif)` görülür. Cetvel olmadan hiçbir davranış değişmez.
