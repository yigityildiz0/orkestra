# Aile bazlı promptlama

Lider aynı brief'i (`brief-rehberi.md`) hedef modelin ailesine göre biçimlendirir. `ork brief` adaptörü `data/modeller.json` `saglayici` alanından seçer. Yeni ya da tanınmayan sağlayıcı için varsayılan `openai-bolumlu` (en sade) + "adaptör ölçülmedi" notu.

Kanıt düzeyi: **A** bağımsız/akademik ölçüm, **B** satıcı iç testi, **C** yalnız tavsiye. Yalnız C düzeyli kural varsayılan olarak uygulanmaz; "denenebilir" olarak durur.

## 1. Ortak çekirdek (tüm aileler)

| Kural | Kanıt |
|---|---|
| Biçim ve şablon farkı sonucu çok oynatır, modeller arası korelasyon zayıftır: önemli ve yinelenen işte 2-3 şablon 12-20 örnekli mini değerlendirmeyle denenir | Sclar 2024, He 2024 (A) |
| Uzun belge başta, soru/görev en sonda; kritik bilgiyi ortaya gömme | Liu 2023 (A), Anthropic (B) |
| Düşünen modelde "adım adım düşün" yazma; düşünme miktarı efor parametresiyle yönetilir ("az düşün" demek güvenilir değil) | Meincke 2025 (A), satıcılar (C) |
| Düşünen modelde varsayılan zero-shot; örnek yalnız biçim için, 1-3 tane | DeepSeek-R1 ve izleyen çalışmalar (A/B) |
| JSON'da akıl yürütme alanı cevap alanından önce, ya da iki aşama (serbest yanıt, sonra biçimlendir) | Tam 2024 (A) |
| Persona ya da "uzman rolü" olgusal doğruluğu artırmaz | Basil 2025 (A) |
| Düşünmesiz modelde istemi iki kez yazmak doğruluğu artırır | Leviathan 2025 (A) |
| Ayraç türü modern modellerde çoğunlukla etkisizdir; tek tür seç ve tutarlı kullan | Systima 2026 (A-) |
| Çıktı dilini açık yaz; talimat İngilizce + içerik Türkçe makul; kültür yüklü Türkçe işte talimat da Türkçe | CulturALL, NAACL 2025 (A; Türkçe için doğrudan ölçüm yok) |
| Model olgu belleği değildir: kaynak, sayı, sürüm bilgisi araçtan istenir; brief "bilmiyorsan ara ya da `acik_sorular`a yaz" der | T |

## 2. Adaptörler

| Adaptör | Aileler | Brief dönüşümü | Efor / düşünme | Yapılandırılmış çıktı | Yasak / teknik |
|---|---|---|---|---|---|
| `claude-xml` | Opus, Sonnet, Haiku | A/B/C katmanları `<instructions>`, `<context>`, `<documents>` etiketlerine; belgeler `<document><source><document_content>`; "yapma" yerine "ne yap + neden"; markdown'sız prompt daha az markdown üretir (C) | Efor parametresi; satıcı başlangıç önerisi (B): Opus medium, Sonnet ajan işinde medium, zorda high; Haiku en az medium (low uzun ajan işinde aramayı atlar). Bağlayıcı olan seçicinin efor kuralıdır (`siniflar.json`), bu satır değil | Print modunda şema bayrağı / structured outputs; desteklenmeyen şema özellikleri (özyineleme, min/max, minLength) ayıklanır; şema değişimi önbelleği bozar | Prefill yok; sabit düşünme bütçesi yok; zorunlu araç seçimi yerine otomatik + katı şema; yanıtta akıl yürütme isteme |
| `openai-bolumlu` | Sol, Terra, Luna | `Role / Goal / Success criteria / Constraints / Tools / Output / Stop rules` başlıkları; kısa ve sade (sadeleştirilmiş prompt iç değerlendirmede daha yüksek skor ve belirgin token düşüşü, B) | Önce eksik başarı ölçütü ve doğrulama adımı eklenir, sonra efor artırılır; efor her çağrıda açık yazılır (katalog varsayılanı düşük olabilir); çıktı payı geniş | `codex exec --output-schema <f.json> -o <sonuc.json>` (yalnız son ileti yazılır) | ALWAYS/NEVER yalnız gerçek değişmezde; dil "kullanıcının dilinde" değil açıkça; Sol işçisine açık durma ölçütü + araç çağrısı sınırı (önceki nesilde kelimesi kelimesine yorum ve sarmal görüldü, B; güncel nesil için DY); Luna çıktısı mutlaka doğrulanır; Terra'ya yazma izni seçicinin `erisim_bayraklari` kaydına bağlıdır (izinsiz eylem gözlemi DY: kaynak künyesi eksik, `kaynaklar.md`) |
| `gemini-baglam-once` | Hydrogen, Argon, Flash | Bağlam önce, soru en sonda ("Yukarıdaki bilgilere dayanarak ..."); tek tür ayraç; rol, kısıt ve biçim sistem talimatında; "kesin ve doğrudan" | `thinking_level` (Hydrogen varsayılanı yüksek; eforu yaz); sabit düşünme bütçesi ve en düşük düzey hata verir; düşünme kapatılamaz | Basit işte örnek + prompt; karmaşıkta structured output; **yerel araç bildirimi** (ham JSON araç çağrısı hata üretir) | temperature/top_p/top_k yok sayılır; prefill yok; Google "her zaman few-shot" der (C, ölçüm yok: varsayılan değil); agy'de medya/dosya için `--mode accept-edits`, salt düşünmede `--mode plan` |
| `cn-notr` | Bedava API'deki açık ağırlıklı Çin modelleri (DeepSeek, GLM, Qwen) | Resmî rehber yok; kısa sistem + tek kullanıcı mesajı; XML benzeri ayraç + düz metin; talimat başta ve sonda 1-2 satır tekrar (sigorta, ölçüm yok) | Efor takma adları birleştirilir (ör. medium = high); bazı modellerde düşünme kapatılamaz; düşük efor çok turlu işte toplam süreyi kısaltmayabilir | `response_format=json_object` + prompt'ta "json" kelimesi + örnek + yeterli `max_tokens` (bazı modellerde çıktı tavanı düşük) | Few-shot kapalı; "step by step" yok; yalnız kamuya açık veri; dosya düzenleyen işte ajan kabuğu üzerinden |

## 3. Aileye özgü cümleler

Kaynak ve düzey `data/aile-cumleleri.json` dosyasındadır; `ork brief` yalnız A ve B düzeyini kendiliğinden ekler, C ve DY yalnız `--deneme` ile (denenebilir, ölçümle karar ver).

- **Sonnet (B):** JSON ve düşünmesiz akıl yürütmede "Think the problem through before you answer." En yüksek eforda "iş bitince dur, ekstra inceleme ya da alt ajan açma" cümlesi maliyeti belirgin düşürür.
- **Haiku (B):** brief'e bugünün tarihi + "bilgin eski olabilir, ara" eklemek arama oranını artırır; low yerine medium erken durmayı belirgin azaltır.
- **Opus (C, denenebilir):** uzun sessiz görevde ara hatırlatıcı; keşif işinde "önce geniş keşfet, sonra daralt".
- **Sol (DY, denenebilir):** açık durma ölçütü + araç çağrısı sınırı (bkz. tablo).
- **Terra (DY, denenebilir):** dosya yazdırmak yerine diff döndürt.

## 4. Uygulama

1. `ork brief --rol <hedef rol> --efor <efor> --sablon <dosya> [--hafif] [--deneme]` çıktısını kullan; elle yazılacaksa sırayla: çekirdek kurallar, adaptör dönüşümü, aileye özgü cümle.
2. Aynı işi farklı ailelere veriyorsan (oy, çapraz doğrulama) içerik aynı kalır, yalnız biçim değişir; aksi hâlde karşılaştırma bozulur.
3. Önemli yinelenen işte şablonu bir kez mini değerlendirmeyle seç ve `olc` kaydında `brief_hash_A` ile izle.
4. Adaptör kuralı ölçümle çelişirse ölçüm geçer; kuralı silmeyi `guncelle` raporunda öner.
