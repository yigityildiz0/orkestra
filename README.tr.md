[English](README.md) · **Türkçe**

# Orkestra

Alt ajanlı ve çok adımlı işlerde model, efor ve platformu seçen bir Claude Code skill'i: **önce kalite, sonra kota**.

Claude Code'un yanında başka abonelikleri (Codex, Antigravity üzerinden Gemini, ücretsiz API, yerel modeller) de kullananlar için. Her alt görevde modeli elle seçmek ya da diğerleri boştayken tek kotayı bitirmek istemeyenlere yarar.

```sh
git clone https://github.com/yigityildiz0/orkestra ~/.claude/skills/orkestra && python3 -I ~/.claude/skills/orkestra/scripts/ork.py kur
```

Windows (PowerShell) ve kalan kurulum adımları [Kurulum](#kurulum) bölümünde.

## Özellikler

- **Kalite tabanı.** Her iş sınıfının bir kalite eşiği vardır. Eşiğin altındaki model sonucu üretmek için seçilmez; kota azalırsa iş zayıf modele düşmez, sıraya girer.
- **Kapasiteye duyarlı.** Abonelik havuzlarının (Claude, Codex, Gemini/Antigravity), isteğe bağlı ücretsiz API'lerin ve yerel modellerin kalanını okur. Havuz başına koyduğun tabanların altına inmez; son payı kritik işler için ayırır.
- **Şef tavanı.** İşçi, liderin kendi model ve eforunu aşmaz. İş bunun üstünü gerektiriyorsa sessizce düşürmez, sana sorar.
- **Farklı aileyle doğrulama.** Çıktıyı önce dış kanıt (test, şema, bağlantı sorgusu), sonra farklı bir model ailesi denetler. Lider kendi işine not vermez.
- **Varsayılan olarak gizlilik.** Veri sınıfı belirtilmemişse "bilinmiyor" sayılır. Sağlık ve gizli veri, sen açıkça onaylamadıkça yalnız host sağlayıcıda ve yerel modellerde kalır.
- **Kendini güncelleyen kayıt.** `/orkestra-guncelle` yeni modelleri, halefleri ve emeklilikleri bulur; her puanı kaynak bağlantısıyla yazar.
- **Ucuz çalışır.** Betikler yalnız Python standart kitaplığını kullanır ve kendileri model çağırmaz; kota okumak ve model seçmek sıfır token harcar.

## Bir iş nasıl yönlendirilir

1. **Sınıflama:** iş sınıfı (mekanik, basit, araştırma, normal, kod, zor, kritik), alan, veri sınıfı, boyut.
2. **Kota okuma:** havuz başına kalan pay; okunamayan havuz "bilinmiyor" sayılır ve öne geçmez.
3. **Seçim:** `ork sec` modeli, eforu, platformu, hazır çağrı satırını ve yedekleri verir.
4. **Bölme ve brief:** bağımsız parçalar paralel koşar; her birine hedef model ailesine göre yazılmış kısa bir brief gider.
5. **Yürütme ve doğrulama:** işçiler döner; sonuç yukarıdaki sırayla denetlenir.
6. **Bildirim:** lider seçimi başta söyler, sonda her işçiyi listeler.

Küçük işi bölmez: lider kendisi yapar.

## Kurulum

**Gereksinim:** Python 3.10 ya da üstü (3.12'de doğrulandı) ve Claude Code. Codex, Antigravity ve ücretsiz API isteğe bağlıdır; kurulu olmayan platform keşifte kapalı kalır.

1. Bu depoyu skill klasörüne koy.

   ```sh
   # macOS / Linux / Git Bash
   git clone https://github.com/yigityildiz0/orkestra ~/.claude/skills/orkestra
   ```

   ```powershell
   # Windows PowerShell
   git clone https://github.com/yigityildiz0/orkestra "$HOME\.claude\skills\orkestra"
   ```

   Git yoksa **Code** düğmesinden `main` dalının ZIP'ini indir, `~/.claude/skills/orkestra` olarak aç.

2. Kurulum betiğini çalıştır. `/orkestra-guncelle` menü komutunu `~/.claude/commands` altına kopyalar, kişisel dosyalarını örneklerden `~/.orkestra` altında üretir. Zaten var olan dosyalara dokunmaz.

   ```sh
   python3 -I ~/.claude/skills/orkestra/scripts/ork.py kur
   ```

   Windows'ta: `python -I "$HOME\.claude\skills\orkestra\scripts\ork.py" kur`. Aşağıda `ork` bu komutun yerine geçer.

3. `~/.orkestra` altındaki iki kişisel dosyayı düzenle:
   - `kullanici-kurallari.json`: kuralların (tabanlar, yasak model aileleri, gizlilik listeleri, ek ücret politikası).
   - `platformlar.json`: platformların ve havuzların. Codex ve Antigravity `"durum": "kapali"` olarak başlar; sahip olduklarını `"aktif"` yap. Hangi CLI'ların kurulu ve girişli olduğunu `ork kesif --giris` gösterir.

4. Kurulumu sına, sonra yeni bir Claude Code oturumu aç.

   ```sh
   ork kontrol
   ```

`~` ev klasörüdür (Windows'ta `%USERPROFILE%`). Kişisel dosyalar yalnız `~/.orkestra` altındadır, bu depoya girmez.

## Kullanım

| Komut | Ne yapar |
|---|---|
| `/orkestra <görev>` | Görevi sınıflar, seçer, böler, yürütür, doğrular. |
| `/orkestra kota` | Havuz başına kalan kota. |
| `/orkestra hafif <görev>` | Hafif: eşiği hâlâ karşılayan en ucuz model, en çok 2 işçi. |
| `/orkestra ultra <görev>` | Ultra: üst kademe serbest, farklı aile doğrular. Tabanlar ve gizlilik aynen geçerli. |
| `/orkestra neden <model> <sınıf>` | Bir modelin neden seçildiğini ya da elendiğini gösterir. |
| `/orkestra plan` | Hafta planı: havuz başına günlük hedef. |
| `/orkestra aç` / `kapat` | Bu oturumda her esaslı işi orkestrayla yürütür ya da bırakır. |
| `/orkestra-guncelle [hizli \| tam \| platform \| platform-ekle <ad> \| model <ad>]` | Model ve platform kaydını günceller. `tam` kipi, sahip olduğun platformlar için kaynaklı web araştırması planlar. |

Düz sözle de yönlendirebilirsin: "4 ajan çalıştır", "bunu Codex'e yaptır", "Claude harcama".

`ork --help` tüm komut satırı başvurusunu verir.

## Güncelleme

- **Skill:** `git -C ~/.claude/skills/orkestra pull`, ardından menü komutunu tazelemek için bir kez daha `ork kur`.
- **Model ve platformlar:** `/orkestra-guncelle`. Yeni model çıkınca ya da ayda bir çalıştır.

## Kaldırma

`~/.claude/skills/orkestra` skill klasörünü ve `~/.claude/commands/orkestra-guncelle.md` menü komutunu sil. Kurallarını, platform dosyanı ve ölçüm geçmişini de silmek istersen `~/.orkestra` klasörünü kaldır.

## Sorun giderme

| Belirti | Çözüm |
|---|---|
| `HATA kişisel dosya yok, örnek veri yüklendi` | Kişisel dosyalar yok. `ork kur` çalıştır, sonra düzenle. `--ornek-kabul` seçiciyi yalnız örnek veriyle dener. |
| `/orkestra-guncelle` `/` menüsünde yok | `ork kur` çalıştır, yeni oturum aç. |
| Bir platform hiç seçilmiyor | `platformlar.json` içinde hâlâ kapalı ya da girişi yok. `ork kesif --giris` ile bak. |
| Bir havuz "bilinmiyor" görünüyor | Kotası okunamıyor. Claude kotasının programatik ucu yok: `--claude 5s=<kalan>,hafta=<kalan>` ile ver ya da lider kullanım ekranından okusun. |
| `ork sec` 4 ya da 5 koduyla çıkıyor | 4: seçici önce senin yanıtına ya da onayına ihtiyaç duyuyor. 5: hiçbir havuzda yer yok; mesaj en erken ne zaman açılacağını söyler. |
| `ork kontrol` hata veriyor | `python --version` ile sürümü bak (3.10 ya da üstü). Yine hata varsa çıktıyla birlikte issue aç. |

## Depo yapısı

| Yol | İçerik |
|---|---|
| `SKILL.md` | Liderin okuduğu giriş. |
| `references/` | İhtiyaç anında okunan ayrıntı: algoritma, brief, gizlilik, güncelleme akışı, platform notları. |
| `scripts/ork.py`, `scripts/ork/` | Komut satırı aracı: seçici, kota okuyucu, keşif, güncelleyici. |
| `data/` | Genel model verisi, şemalar ve kişisel dosyaların `*.ornek.json` örnekleri. |
| `commands/` | `/orkestra-guncelle` menü komutu. |
| `tests/` | Test paketi; `ork kontrol` çalıştırır. |

Skill'in kendisi ve başvuru belgeleri Türkçedir; skill açıklaması iki dillidir.

## Katkı

Her değişiklikten önce `ork kontrol` çalıştır, yeni davranışa test ekle. Yayından önce `ork disa-aktar --kuru` temiz çıkmalı (kişisel veri yok). Kurallar [AGENTS.md](AGENTS.md) içinde.

## Lisans

[MIT](LICENSE). Üçüncü taraf puanları ve lisans notları: [NOTICE.md](NOTICE.md).
