# AGENTS.md

Bu depo bir Claude Code skill'idir (`SKILL.md`); başka ajanlar (Codex, Gemini) da aynı kuralla çalışır.

## Yapı

- `SKILL.md`: liderin okuduğu giriş; ayrıntı `references/` altında, ihtiyaç anında okunur.
- `scripts/ork.py`: tek giriş noktası, yalnız Python standart kitaplığı (3.10+). Model çağırmaz.
- `scripts/ork/`: `secici` (seçim), `kota` (kota okuma), `kesif` (platform keşfi), `guncelle` (kayıt güncelleme), `veri` (yükleme, şema, yerel katman), `araclar` (brief, ölçüm, tarama, dışa aktarma, kurulum).
- `data/`: genel veri (`modeller.json`, `siniflar.json`, `imzalar.json`, şemalar) ve kişisel dosya örnekleri (`*.ornek.json`). Kişisel dosyalar `~/.orkestra/` altındadır, depoya girmez.

## Kurallar

- Sınama: `python -I scripts/ork.py kontrol` (tüm testler + veri denetimi). Her değişiklikten sonra çalıştır; kırmızıyken teslim etme.
- Yeni davranışa test yaz (`tests/`, sentetik fikstür `tests/fixtures/ornek_veri.py`). Gerçek kişisel veriye dayanan testler `ORKESTRA_KISISEL` yoksa atlanır.
- Sayı ve eşik koda değil `data/` dosyasına yazılır; belge (`references/algoritma.md`) formülü anlatır.
- Skill metni rol adı kullanır, kesin kimlik ve sürüm numarası yazmaz; kesin kimlik `modeller.json` `roller` yuvasındadır.
- Kişisel veri (ad, yol, hesap, kota, yerel model envanteri) genel dosyalara yazılmaz. Yayın öncesi `python -I scripts/ork.py disa-aktar --kuru` temiz olmalı.
- Sır okunmaz, yazdırılmaz; anahtarlar yalnız ortam değişkeni adıyla bilinir.
- Belgeler Türkçe; kod tanımlayıcıları mevcut Türkçe ASCII düzenini korur.
