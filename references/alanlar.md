# Alan bazlı öncelikler (ÜRETİLMİŞ DOSYA)

> Bu dosya `data/modeller.json` (`liderler`, `rotalar`) ve `data/siniflar.json` (`alanlar`) kaynağından `ork guncelle` (G10) ile üretilir. Elle düzenleme bir sonraki güncellemede silinir; değişiklik veri dosyasına yazılır. Bu dosya yalnız genel veriyi gösterir; kişisel yerel katmanı da içeren kopya `~/.orkestra/alanlar.md` dosyasındadır.

Okuma: sıra **aynı kademe içinde** kalite sırasıdır; hangi kademenin gerektiğini işin Q sınıfı belirler (`algoritma.md`). Gürültü bandı δ içindekiler eşit kalite sayılır ve kapasiteye göre dağıtılır. Rol adı her zaman ailenin en son sürümüdür; kesin kimlik `modeller.json` `roller` yuvasından çözülür. "elle" = otomatik çağrı izni olmayan yol (hazır komut satırı üretilir, kullanıcı çalıştırır). Bir alan kullanıcının sabit kuralındaysa (ör. görsel üretim) bu tablo değil kural geçerlidir.

Kaynak okuma tarihi: veri dosyasındaki `okuma` alanları. Ölçek kilidi: `z_olcek` = `AA-II-v5.0.1`.

## Kademe × model@efor

Kademe işin Q sınıfından gelir (`siniflar.json`); bir model@efor Z değeri o kademenin aralığına düşüyorsa oraya girer. Hücre: `rol efor Z`; `~` = tahmin (seçici indirim uygular). Kademe içindeki sıra kalite sırası değildir: aynı kademedeki adaylar arasında karar alan ölçümü, δ bandı ve kapasiteyle verilir. Kullanıcı yasakları ve tabanlar bu tabloyu geçer.

| Kademe | Z aralığı | Q sınıfları | Claude (CC) | GPT (Codex) | Gemini (agy, elle) | Açık ağırlık / bedava |
|---|---|---|---|---|---|---|
| K1 | 0-28 | mekanik (16), basit (22) | **Sonnet** low 26<br>**Haiku** low 19, medium 25 | **Luna** low 10, medium 18, high 21, xhigh 23, max 28 | **Hydrogen** low 27<br>**Flash (yedek)** low 23 | **DeepSeek Flash** none 19<br>**GLM** low 23, high ~28<br>**Qwen Flash** low ~26, medium ~27 |
| K2 | 29-38 | arastirma (38) | **Opus** low 35<br>**Sonnet** medium 31<br>**Haiku** high 30, xhigh 35, max 36 | **Sol** low 35<br>**Terra** none 31, low 29, medium 38 | **Flash (yedek)** medium 30, high 31 | **DeepSeek Flash** high 29, max 33<br>**GLM** max 32<br>**Qwen Flash** xhigh ~29 |
| K3 | 39-48 | normal (41), kod (45) | **Opus** medium 48<br>**Sonnet** high 42 | **Sol** medium 46<br>**Terra** high 42, xhigh 45<br>**Astra** low 43 | **Hydrogen** medium 41<br>**Argon** medium 48 | - |
| K4 | 49-54 | zor (50) | **Opus** high 52<br>**Sonnet** xhigh 50<br>**Fable** low 54 | **Sol** high 50, xhigh 52<br>**Terra** max 51<br>**Astra** medium 52 | **Hydrogen** high 51, xhigh 54<br>**Argon** high 50<br>**Carbon** low 54 | - |
| K5 | 55-59 | kritik (56) | **Opus** xhigh 57, max 59<br>**Sonnet** max 55<br>**Fable** medium 56 | **Sol** max 55<br>**Astra** high 55, xhigh 55, max 57 | **Carbon** medium 58 | - |
| K6 | 60+ | - | **Fable** high 62, xhigh 62, max 65 | - | **Carbon** high 60 | - |

### Seviye sınıfları (boyut)

`roller.boyut` aynı büyüklük sınıfındaki rolleri eşler (ör. Haiku ≈ Luna, Sonnet ≈ Sol). Bu eşleme fiyat ve model büyüklüğü içindir, kalite eşitliği iddiası değildir: kalite kararı Z ve alan ölçümüyle verilir.

| Sınıf | Roller (yolu ile) |
|---|---|
| S | Haiku (CC) ≈ Luna (Codex) ≈ Flash (yedek) (agy, elle) ≈ DeepSeek Flash (bedava-api) ≈ Qwen Flash (bedava-api) |
| S/M | Hydrogen (agy, elle) |
| M- | Terra (Codex) |
| M | Sonnet (CC) ≈ Sol (Codex) ≈ GLM (bedava-api) |
| L | Opus (CC) ≈ Astra (Codex) ≈ Argon (agy, elle) ≈ Carbon (agy, elle) |
| XL | Fable (CC) |

## Kod

| Alt alan | Lider | Sıra | Bant içi eşitlik / not | Kaynak |
|---|---|---|---|---|
| `zor_ajan` | Opus (CC) | Opus high (CC) > Sonnet xhigh (CC) > Sol xhigh (Codex) > Hydrogen high (agy, elle) > Terra max (Codex) | bant içinde: kapasiteye göre; Opus/Sonnet farkı eşit; Sol'a fark 6 puan, Sol 8.4x ucuz; Argon'a kod ajanı verme | https://artificialanalysis.ai/agents/coding-agents |
| `gunluk` | Sol (Codex) | Sol high (Codex) > Sonnet high (CC) > Opus medium (CC) > Haiku xhigh (CC) > DeepSeek Flash high (bedava-api) > Terra high (Codex) | bant içinde: kapasiteye göre; ölçüt doymuş: eşit kalite kümesi, kapasiteye göre dağıt | https://www.vals.ai/benchmarks/vibe-code |
| `terminal` | Sonnet (CC) | Sonnet max (CC) > Opus xhigh (CC) > Sol max (Codex) > Terra max (Codex) | bant içinde: kapasiteye göre; Hydrogen bu işte yetmez | https://www.vals.ai/benchmarks/terminal-bench-4 |
| `sre` | Sol (Codex) | Sol high (Codex) > Argon high (agy, elle) > Opus high (CC) > Sonnet high (CC) | ayrışık (lider bandın dışında); Sol açık önde | https://www.vals.ai/benchmarks/srebench |
| `goc` | Sonnet (CC) | Sonnet high (CC) > Opus high (CC) > Sol high (Codex) > DeepSeek Flash high (bedava-api) | ayrışık (lider bandın dışında); Hydrogen bu tabloda yok (eski 82.7 kaydı doğrulanamadı, 2026-11-19'da kaldırıldı); Argon 70.8 | https://www.vals.ai/benchmarks/code-migration-v1-1 |
| `refaktor` | Opus (CC) | Opus high (CC) > Argon high (agy, elle) > Sonnet high (CC) > Sol high (Codex) | ayrışık (lider bandın dışında) | https://labs.scale.com/leaderboard/swe-atlas |
| `ui` | Opus (CC) | Opus high (CC) > Sonnet xhigh (CC) > Sol max (Codex) > Hydrogen high (agy, elle) | ayrışık (lider bandın dışında); Haiku verme | https://arena.ai/leaderboard/webdev |
| `ekran_hata` | Opus (CC) | Opus medium (CC) > Sonnet high (CC) > Argon high (agy, elle) > Haiku xhigh (CC) > Sol high (Codex) | ayrışık (lider bandın dışında); Opus farkı +11.9 | https://www.vals.ai/benchmarks/swebench-multimodal |
| `algoritma` | Argon (agy, elle) | Argon high (agy, elle) > Sol high (Codex) > Opus high (CC) > Sonnet high (CC) | bant içinde: kapasiteye göre | https://www.vals.ai/benchmarks/ioi |
| `otomasyon` | Argon (agy, elle) | Argon high (agy, elle) > Hydrogen high (agy, elle) > Sonnet high (CC) > Opus high (CC) > DeepSeek Flash high (bedava-api) | bant içinde: kapasiteye göre; otomatik yolda Sonnet/Opus | https://artificialanalysis.ai/evaluations |

## Araştırma ve olgu

| Alt alan | Lider | Sıra | Bant içi eşitlik / not | Kaynak |
|---|---|---|---|---|
| `kaynak` | araç | araç: pubmed > araç: cochrane > araç: consensus | ayrışık (lider bandın dışında); DOI/PMID doğrula; alana özgü sıra kişisel yama katmanında | yerleşik ilke: model belleği olgu kaynağı değil; birincil veri tabanı ve sistematik derleme |
| `web` | Opus (CC) | Opus high (CC) > Sol high (Codex) > Sonnet high (CC) | bant içinde: kapasiteye göre; Gemini ailesi için ölçüm yok | https://www.vals.ai/benchmarks/web_search |
| `sentez` | Sol (Codex) | Sol high (Codex) > Sonnet high (CC) > Opus high (CC) > Hydrogen high (agy, elle) | bant içinde: kapasiteye göre; ilk üç eşit: kapasiteye göre dağıt | https://www.vals.ai/benchmarks/science_index |
| `akil_yurutme` | Opus (CC) | Opus xhigh (CC) > Sol xhigh (Codex) > Hydrogen xhigh (agy, elle) > Argon high (agy, elle) | ayrışık (lider bandın dışında); Opus +9.1 | https://artificialanalysis.ai/evaluations/hle-diamond |
| `olgu_teyit` | Argon (agy, elle) | Argon high (agy, elle) > Hydrogen high (agy, elle) > Opus max (CC) > Sol xhigh (Codex) | ayrışık (lider bandın dışında); otomatik yolda Opus/Sol + dış kanıt şart | https://artificialanalysis.ai/evaluations/omniscience |
| `klinik` | Opus (CC) | Opus high (CC) > Argon high (agy, elle) > Sonnet high (CC) > Sol high (Codex) | bant içinde: kapasiteye göre; Opus + Argon çapraz; kaynak PubMed; hasta verisi buluta gitmez | https://artificialanalysis.ai/evaluations/omniscience |
| `uzun_belge` | Sonnet (CC) | Sonnet high (CC) > Sol high (Codex) > Haiku xhigh (CC) | bant içinde: kapasiteye göre | https://artificialanalysis.ai/evaluations/mlcr-aa |
| `finans_hukuk` | Hydrogen (agy, elle) | Hydrogen high (agy, elle) > Argon high (agy, elle) > Opus high (CC) > Sonnet high (CC) | ayrışık (lider bandın dışında); Sol/Terra/Luna bu işte dip; kritikte Hydrogen xhigh | https://www.vals.ai/benchmarks/tax_agent_bench |
| `tablo` | Sonnet (CC) | Sonnet high (CC) > Hydrogen high (agy, elle) > Opus high (CC) > Terra medium (Codex) > Sol high (Codex) | bant içinde: kapasiteye göre; 12x maliyet farkı: eşit kalite kümesi | https://www.vals.ai/benchmarks/emb-v1-1 |

## Görsel analiz

| Alt alan | Lider | Sıra | Bant içi eşitlik / not | Kaynak |
|---|---|---|---|---|
| `ekran_kod` | Opus (CC) | Opus medium (CC) > Sonnet high (CC) > Argon high (agy, elle) | ayrışık (lider bandın dışında) | https://www.vals.ai/benchmarks/swebench-multimodal |
| `ocr_sayma` | Hydrogen (agy, elle) | Hydrogen medium (agy, elle) > Argon high (agy, elle) > Terra high (Codex) > Opus high (CC) > Sol high (Codex) | bant içinde: kapasiteye göre; Hydrogen ≈ Argon; otomatik yolda Terra 1. | https://playground.roboflow.com/leaderboard |
| `grafik` | Argon (agy, elle) | Argon high (agy, elle) > Hydrogen high (agy, elle) > Opus high (CC) > Terra high (Codex) > Sonnet high (CC) | bant içinde: kapasiteye göre; satıcı beyanı | https://deepmind.google/models/model-cards/gemini-4-argon/ |
| `uzun_pdf` | Hydrogen (agy, elle) | Hydrogen medium (agy, elle) > Sol high (Codex) > Opus high (CC) > Sonnet high (CC) | bant içinde: kapasiteye göre; yüksek efor zararlı: medium | https://artificialanalysis.ai/evaluations/gdp-pdf |
| `bilgisayar_kontrol` | Opus (CC) | Opus high (CC) > Sonnet high (CC) > Sol high (Codex) > Hydrogen high (agy, elle) > Terra high (Codex) | bant içinde: kapasiteye göre; satıcı beyanları, alt kümeler farklı | https://www.anthropic.com/news/claude-sonnet-5-5 |
| `tibbi` | Hydrogen (agy, elle) | Hydrogen high (agy, elle) > Terra high (Codex) | bant içinde: kapasiteye göre; güncel nesil ölçüm yok; insan doğrulaması şart; yalnız anonim görsel | DY |
| `toplu_sinif` | Haiku (CC) | Haiku medium (CC) | bant içinde: kapasiteye göre; doğrulanan iş; bedava platformda görsel model (istek başı görsel sınırı platform kataloğundan) | DY |

**`ocr_sayma` rotası** (sırayla):
1. bedava-api: görev: ocr (OCR (kamu verisi, ücretsiz); veri genel)

## Video analiz

**`konusmali` rotası** (sırayla):
1. agy, elle: Hydrogen high (video+ses analizi; accept-edits kipi şart; çalışma klasöründe yalnız okunacak dosya; >45 dk parçala)
2. agy, elle: Argon high (çok uzun/zor video, ikinci görüş; Hydrogen havuzu doluysa)
3. uygulama, elle: gemini-uygulamasi (tek seferlik uzun video; abonelik sınırı: süre ve dosya boyutu)
4. otomatik: Opus + ffmpeg+faster-whisper-large-v3 (kare + döküm + metin modeli; Gemini yolu yoksa, gizli içerik ya da kullanıcı yoksa; kare başına ~300-2.700 token)

**`saf_gorsel` rotası** (sırayla):
1. agy, elle: Hydrogen medium (görsel video analizi; efor doğrulanmadı)
2. otomatik: Terra + ffmpeg (kare çıkar + görsel okuma; ucuz kare okuma)
3. otomatik: Opus + ffmpeg (kare çıkar + ayrıntılı okuma)

**`uzun` rotası** (sırayla):
1. agy, elle: Argon high (uzun video)
2. uygulama, elle: gemini-uygulamasi (uzun video)
3. otomatik: Sonnet high + ffmpeg+faster-whisper-large-v3 (parçala + kare + döküm)

## Ses

**`dokum` rotası** (sırayla):
1. yerel: faster-whisper-large-v3 (konuşma dökümü (otomatik varsayılan))
2. agy, elle: Hydrogen low (konuşma anlama)
3. bedava-api: görev: asr (konuşma dökümü; veri genel)

**`tts` rotası** (sırayla):
1. yerel: chatterbox (Türkçe TTS)
2. yerel: kokoro (İngilizce TTS)
3. bedava-api: görev: tts (TTS; veri genel; Türkçe doğrulanmadı)

**`muzik` rotası** (sırayla):
1. yerel: ace-step (müzik)
2. uygulama, elle: flow-music (müzik)

## Yazım

| Alt alan | Lider | Sıra | Bant içi eşitlik / not | Kaynak |
|---|---|---|---|---|
| `rapor` | Sonnet (CC) | Sonnet xhigh (CC) > Opus xhigh (CC) > Opus high (CC) > Hydrogen xhigh (agy, elle) | ayrışık (lider bandın dışında); Claude açık önde: kalite önce kuralı Claude seçer | https://artificialanalysis.ai/evaluations/aa-briefcase |
| `uzun_turkce` | Opus (CC) | Opus high (CC) > Argon high (agy, elle) > Sonnet high (CC) | bant içinde: kapasiteye göre; bağımsız Türkçe ölçüm yok; kendi A/B; küçük modellere uzun Türkçe verme; Claude tokenizer'ı aynı metne ~%30 fazla token | https://arena.ai/leaderboard/text/creative-writing |
| `yaratici` | Argon (agy, elle) | Argon high (agy, elle) > Opus high (CC) > Hydrogen high (agy, elle) > Flash (yedek) high (agy, elle) | bant içinde: kapasiteye göre; CI örtüşür | https://arena.ai/leaderboard/text/creative-writing |
| `talimat_izleme` | Sol (Codex) | Sol high (Codex) > Argon high (agy, elle) > Opus high (CC) | bant içinde: kapasiteye göre; ölçütler çelişiyor | https://labs.scale.com/leaderboard/multichallenge |

## Görsel üretim

**`t2i` rotası** (sırayla):
1. sabit: Sol high + codex:image_gen (görsel üretim (kullanıcı sabit kuralı varsa önce o))
2. uygulama, elle: chatgpt-uygulamasi (Codex kotası doluyken aynı GPT görsel ailesi (sabit kural: GPT); uygulama sınırı ayrı sayılabilir [DY])
3. uygulama, elle: gemini-uygulamasi (Codex kapalıyken, çok dilli metin, 4K)
4. agy, elle: agy:generate_image (dosya gerekiyorsa; model ve havuz doğrulanmadı; çıktı konuşma klasörüne düşer)

**`duzenleme` rotası** (sırayla):
1. sabit: Sol high + codex:image_gen (görsel düzenleme; girdi görselinde stdin kapatılır)
2. uygulama, elle: chatgpt-uygulamasi (Codex kotası doluyken aynı GPT görsel ailesi (sabit kural: GPT); uygulama sınırı ayrı sayılabilir [DY])
3. uygulama, elle: gemini-uygulamasi (Codex kapalıyken)

## Video üretim

**`t2v` rotası** (sırayla):
1. uygulama, elle: gemini-omni-flash (video üretim; Flow kredisi)
2. otomatik: Sonnet high (kod olarak video (Remotion/HyperFrames))

**`i2v` rotası** (sırayla):
1. uygulama, elle: gemini-omni-flash (görselden video)

## Mekanik ve toplu

**`toplu` rotası** (sırayla):
1. otomatik: deterministik (önce deterministik araç (rg, AST, codemod, jq, pdftotext, ffmpeg))

Ölçümü olmayan alt alanlar (q = Z, δ × 1.5): `nobetci`, `dogrulayici`

## Görsel/video üretim modelleri (çağıran modelden ayrı)

| Yol | Sürüm doğrulama | Kalite kolları / not |
|---|---|---|
| `codex:image_gen` | DY | görsel modeli sürümü, quality, size, prompt (konu, kompozisyon, tırnak içinde metin, korunacak/değişecek ayrımı) |
| `gemini-uygulamasi:nano-banana` | R | - |
| `agy:generate_image` | DY | - |
| `gemini-omni-flash` | R | - |
