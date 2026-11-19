# Kaynak künyeleri

Diğer belgelerdeki kısa atıfların (`Yazar Yıl`) karşılığı. Düzey: **A** bağımsız/akademik ölçüm, **A-** tek çalışma ya da ön baskı, **B** satıcı iç testi ya da mühendislik yazısı, **C** yalnız tavsiye, **T** türetilmiş.

Durum sütunu:
- **ID (doğrulanmadı):** tanımlayıcı bellekten ya da önceki araştırma notundan geldi; `orkestra güncelle tam` sırasında bağlantı açılarak doğrulanmalıdır.
- **künye eksik:** atıf metinde var, tam künye kayıtlı değil. Uydurma tanımlayıcı yazılmadı; bulunana kadar bu satıra dayanan kural "denenebilir" sayılır.

Model puanları ve fiyatlar burada değil, kaynak bağlantısı ve okuma tarihiyle `data/modeller.json` içindedir.

## Bölme, çok ajan, planlama

| Kısa atıf | Konu | Düzey | Tanımlayıcı | Durum |
|---|---|---|---|---|
| Kim 2025 | Ajan sistemlerinde ölçekleme; paralel ve sıralı işte bölmenin etkisi, merkezi doğrulama | A | - | künye eksik |
| Anthropic 2025 | Çok ajanlı araştırma sistemi mühendislik yazısı (token çarpanları, kapsam satırı) | B | anthropic.com/engineering/multi-agent-research-system | ID (doğrulanmadı) |
| Cognition 2025 | Çok ajan karşıtı mühendislik yazısı (örtük kararların paylaşımı) | B | cognition.ai/blog/dont-build-multi-agents | ID (doğrulanmadı) |
| Cursor 2026 | Paralel ajanlarda sahiplik ve ayrı çalışma ağacı | B | - | künye eksik |
| Smékal 2026 | Ayrıntılı brief ve toplam token | A | - | künye eksik |
| COPE 2025-26 | Zayıf yürütücüye hedef düzeyinde plan | A- | arXiv 2506.11578 | ID (doğrulanmadı) |
| CUDA 2026 | Güçlü planı zayıf işçiye enjekte etme | A- | arXiv 2605.26720 | ID (doğrulanmadı) |
| Meta-Prompting 2024 | Lider-uzman ayrımı (Suzgun ve Kalai) | A | arXiv 2401.12954 | ID (doğrulanmadı) |
| ReWOO 2023 | Planlayıcı-yürütücü ayrımı ve token verimi | A | arXiv 2305.18323 | ID (doğrulanmadı) |
| BATS 2025 | Bütçe farkındalıklı araç kullanımı | A | - | künye eksik |
| Gema 2025 | Test anı hesabında ters ölçekleme, dikkat dağıtıcı bağlam | A | arXiv 2507.14417 | ID (doğrulanmadı) |

## Doğrulama, kaskad, oy

| Kısa atıf | Konu | Düzey | Tanımlayıcı | Durum |
|---|---|---|---|---|
| Huang 2023 | Dış geri bildirimsiz öz-düzeltmenin sınırı | A | arXiv 2310.01798 | ID (doğrulanmadı) |
| Han 2026 | Doğrulayıcı sırası | A | - | künye eksik |
| Panickssery 2024 | Hakemin kendi üretimini kayırması | A | arXiv 2404.13076 | ID (doğrulanmadı) |
| AutoMix | Doğrulamalı kaskad (Madaan ve ark. 2023) | A | arXiv 2310.12963 | ID (doğrulanmadı) |
| Brown 2024 | Tekrarlı örnekleme ve best-of-N | A | arXiv 2407.21787 | ID (doğrulanmadı) |
| Rajput 2026 | Ucuz doğrulayıcının ucuz model hatalarını kabul etmesi | A | - | künye eksik |
| Dekoninck 2024 | Yönlendirme ve kaskadın ortak çerçevesi | A/T | arXiv 2410.10347 | ID (doğrulanmadı) |
| Chen 2024 | Bileşik çıkarımda çağrı sayısı ve oy | A | arXiv 2403.02419 | ID (doğrulanmadı) |
| Smit 2024 | Çok ajanlı tartışma stratejileri | A | arXiv 2311.17371 | ID (doğrulanmadı) |
| Self-MoA 2025 | Farklı modelleri karıştırmanın getirisi | A | arXiv 2502.00674 | ID (doğrulanmadı) |

## Prompt biçimi

| Kısa atıf | Konu | Düzey | Tanımlayıcı | Durum |
|---|---|---|---|---|
| Sclar 2024 | Biçim duyarlılığı | A | arXiv 2310.11324 | ID (doğrulanmadı) |
| He 2024 | Prompt biçiminin başarıma etkisi | A | arXiv 2411.10541 | ID (doğrulanmadı) |
| Liu 2023 | Uzun bağlamda ortadaki bilginin kaybı | A | arXiv 2307.03172 | ID (doğrulanmadı) |
| Meincke 2025 | Düşünen modelde "adım adım" yönergesinin değeri | A | - | künye eksik |
| DeepSeek-R1 | Düşünen modelde zero-shot | A/B | arXiv 2501.12948 | ID (doğrulanmadı) |
| Tam 2024 | Biçim kısıtının akıl yürütmeye etkisi | A | arXiv 2408.02442 | ID (doğrulanmadı) |
| Basil 2025 | Uzman personasının olgusal doğruluğa etkisi | A | - | künye eksik |
| Leviathan 2025 | Düşünmesiz modelde istemi tekrarlamak | A | - | künye eksik |
| Systima 2026 | Ayraç türünün etkisi | A- | - | künye eksik |
| CulturALL, NAACL 2025 | Çok dilli ve kültür yüklü değerlendirme | A | - | künye eksik |

## Kota ve platform sınırları (v7.1, okuma 2026-11-15)

| Konu | Kaynak türü | Düzey | Nerede |
|---|---|---|---|
| Abonelik limitleri, sıfırlama, kredi | satıcı yardım/plan sayfaları + yerel okuma | R / Y | `platformlar.json` havuz `kaynak` alanları |
| Liste fiyatları (girdi/önbellek/çıktı) | satıcı fiyat sayfaları | R | `modeller.json` `fiyat` |
| Model zekâsı, görev maliyeti | bağımsız toplu ölçüm (AA), alan ölçümleri (Vals vb.) | B | `modeller.json` `varyantlar`, `alanlar` |
| Çağrı sabit yükü, kova eşlemesi, K_p | yerel ölçüm (sıfır ya da tek çağrı) | Y | kişisel `platformlar.json` |
| Otomatik çağrı şartları | satıcı ek şartları + resmî forum yanıtları | R / C | kişisel `kullanici-kurallari.json` `agy_otomatik.karar` |

Değerler bu belgeye kopyalanmaz; kaynak bağlantısı ve okuma tarihi kaydın yanındadır.

## Satıcı belgeleri

Satıcı prompt rehberleri ve CLI belgeleri (B ya da C) sürüme bağlıdır; atıf yerine `platform-notlari.md` içinde davranış olarak yazılır ve `guncelle` sırasında yeniden okunur. Kurulu istemcide doğrulanan davranış (ör. Agent aracının `effort` alanı) R sayılır.
