# Orkestra

Claude Code için çok modelli iş yönlendirme skill'i. Alt ajanlı, paralel, uzun ya da görsel/video/ses işinde model, efor ve platformu **önce kaliteye, sonra kota kapasitesine** göre seçer; işi böler, brief yazar, çıktıyı farklı aileye doğrulatır.

- Kalite tabanı: işin eşiğini karşılamayan model hiçbir kipte seçilmez; kota azalınca iş zayıf modele değil sıraya girer.
- Kapasite: abonelik havuzlarının (Claude, Codex, Gemini/Antigravity), isteğe bağlı ücretsiz API'nin ve yerel modellerin kalanını okur; tabanları delmez, ana havuzun son payını korur.
- Gizlilik: veri sınıfı belirtilmezse kapalı davranır; sağlık ve gizli veri host sağlayıcı dışına onaysız gitmez.
- Kayıt: `orkestra güncelle` yeni modelleri, halefleri ve emeklilikleri bulur; ölçümleri kaynak bağlantısıyla işler.
- Şef tavanı: işçi, liderin (şefin) model ve eforunu aşmaz; iş eşiği tavanın üstündeyse kullanıcıya sorar.

## Kurulum

1. Bu klasörü `~/.claude/skills/orkestra` olarak kopyala.
2. `python -I ~/.claude/skills/orkestra/scripts/ork.py kur` çalıştır: `/orkestra-guncelle` menü komutunu `~/.claude/commands` altına koyar, kişisel dosyaları örnekten `~/.orkestra` altına üretir.
3. `~/.orkestra/kullanici-kurallari.json` (tabanlar, yasak aileler, gizlilik sözlüğü) ve `~/.orkestra/platformlar.json` (abonelikler, havuzlar) dosyalarını kendi planına göre düzenle.
4. `python -I ~/.claude/skills/orkestra/scripts/ork.py kontrol` ile sına.

Gereksinim: Python 3.10+ (yalnız standart kitaplık). Codex, Antigravity ve ücretsiz API isteğe bağlıdır; kurulu olmayan platform keşifte kapalı kalır.

## Kullanım

- `/orkestra <görev>`: görevi sınıflar, seçer, böler, yürütür, doğrular.
- `/orkestra kota`: havuz başına kalan kota.
- `/orkestra hafif | ultra <görev>`: en ucuz yeterli model / üst kademe serbest.
- `/orkestra neden <model> <sınıf>`: seçim ya da eleme dökümü.
- `/orkestra-guncelle [hizli|tam|platform|platform-ekle <ad>|model <ad>]`: model ve platform kaydını güncelle; tam kipte sahip olunan platformlar için web araştırma planı, `uygula --web` ile kaynaklı yazım ve değişiklik özeti.

Ayrıntı: `SKILL.md`, karar algoritması `references/algoritma.md`, gizlilik `references/gizlilik.md`.

## English

Orkestra is a Claude Code skill that routes multi-step and sub-agent work across Claude, Codex, Gemini, optional free APIs and local models. It selects quality first (a task never goes below its quality floor), then capacity (remaining subscription quota, per-pool floors and reserves). Workers never exceed the leader's own model and effort unless the user explicitly lifts that ceiling; `/orkestra-guncelle tam` plans source-backed web research per owned platform, and `platform-ekle <name>` registers a new platform as a non-selectable candidate. Personal settings live in `~/.orkestra/` and never in this repository; run `scripts/ork.py kur` after copying the folder to `~/.claude/skills/orkestra`. Docs are in Turkish.

Third-party scores and licensing notes: `NOTICE.md`.
