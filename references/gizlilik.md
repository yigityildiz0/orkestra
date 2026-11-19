# Gizlilik

Varsayılan **kapalı** (fail-closed). Seçiciye her istekte `--veri` verilir; verilmezse `kullanici-kurallari.json` `gizlilik.varsayilan_veri` (tipik olarak `bilinmiyor`) kullanılır.

## 1. Veri sınıfları ve havuz gizliliği

| `veri` | Anlam | İzinli havuz gizliliği |
|---|---|---|
| `genel` | Kamuya açık, kişisel olmayan veri | `ozel`, `dis`, `kamu` |
| `bilinmiyor` | Beyan yok | `ozel` |
| `kisisel` | Kişisel veri, kişisel not, üçüncü kişi verisi | `ozel` |
| `gizli` | Sır, kurumsal/yayımlanmamış metin, finans/kimlik verisi | `ozel`, yalnız host sağlayıcı ve yerel (başkası `--dis-onay` ile) |
| `saglik` | Sağlık/klinik veri | `ozel`, yalnız host sağlayıcı ve yerel (başkası `--dis-onay` ile); insan onayı |

Havuz gizliliği (`platformlar.json` havuz `gizlilik`): `ozel` = kullanıcının aboneliği, verisi eğitimde kullanılmayan yol (bu etiket hesap ayarına bağlıdır: sağlayıcının eğitim/iyileştirme ayarı açıksa havuzu `dis` işaretle); `dis` = istem/kod platform iyileştirmesinde kullanılabilir (ör. şartları böyle olan abonelik); `kamu` = gönderilen her şey herkese açık sayılır (bedava platform).

- `kullanici-kurallari.json` `gizlilik.dis_havuza_gitmez` listesi `dis` ve `kamu` havuzlarına hiçbir veri beyanıyla gitmez.
- Proje `.orkestra.json` `"gizli": true` (bool dışı dolu değer de gizli sayılır, uyarıyla) ya da `"yasak_havuz": [...]` (büyük/küçük harf duyarsız) o projede ilgili havuzları hiçbir sınıfta aday yapmaz.
- "Anonimleştirdim" beyanı tek başına `genel` yapmaz: tarama serbest metindeki ad, adres gibi verileri yakalamaz; asıl kapı veri beyanıdır.
- Sıkı sınıflar (`saglik`, `gizli`) `ozel` havuzların da yalnız host sağlayıcıdakine (liderin çalıştığı platform) ve yerele gider: veri zaten o sağlayıcıdadır, ikinci bir sağlayıcıya kopyalanmaz. Kullanıcı bu konuşmada açıkça onaylarsa `--dis-onay`. Doğrulayıcı ve elle yol önerileri de aynı süzgeçten geçer.
- Karışık duyarlılıkta iş bölünür: kamu parçaları `genel`, gizli çekirdek `gizli`; birleştirme gizli koldaki modelde (playbook senaryo 51).

## 2. Gönderim öncesi tarama (`ork bedava` ve dışa aktarma)

Eşleşmede çıkış 3, sıfır istek; geçersiz kılma yok, iş özel havuzdaki modele gider.

- Anahtar kalıpları (sağlayıcı önekleri, JWT, özel anahtar başlığı, `Authorization: Bearer`, bağlantı dizesi parolası, `.env`/JSON/YAML atamaları), yüksek entropili uzun dizgi.
- Sağlamalı kimlik ve finans numaraları (ulusal kimlik numarası, IBAN, Luhn kart; boşluk, nokta, tire ayraçlı yazım dahil), e-posta, telefon, sağlık terimleri.
- Yasak yollar: `.env`, `.ssh`, oturum dosyaları, `*.pem` ve `kullanici-kurallari.json` `gizlilik.yasak_yol` öğeleri (kısa ad, junction, sembolik bağ çözülerek).
- Klasör taraması birden çok metin kodlamasını ve ofis belgelerinin içini okur; okunamayan, ikili, görsel ya da büyük dosya `taranamayan` sayılır ve gönderimi durdurur.
- `platformlar.json` yoksa, bozuksa ya da bedava havuz tanımlı değilse gönderim yapılmaz (çıkış 2).

## 3. Sırlar

- API anahtarı yalnız ortam değişkeninin **adıyla** bilinir; değeri okunmaz, yazdırılmaz, dosyaya, URL'ye, Git'e, kalıcı nota yazılmaz.
- Kimlik/oturum dosyaları yalnız varlık olarak denetlenir, açılmaz.
- Keşif ortam değişkeni adlarını sinyal olarak kullanır (`*_API_KEY`, `*_BASE_URL`), değerlerini değil.

## 4. Kişisel ve herkese açık katman

| Öğe | Katman |
|---|---|
| `SKILL.md`, `references/*`, `scripts/`, `tests/`, `data/sema/`, `data/modeller.json`, `data/imzalar.json`, `data/siniflar.json`, `data/*.ornek.json`, `commands/` | genel (yayımlanabilir) |
| `~/.orkestra/kullanici-kurallari.json`, `~/.orkestra/platformlar.json`, `~/.orkestra/modeller.yerel.json` | kişisel ayar (repoya yalnız `data/*.ornek.json`); `ork kur` örnekten üretir |
| `~/.orkestra/*` geri kalanı (kota anlıkları, ölçümler, soğuma, platform kararları, yedekler), proje `.orkestra.json`, platform yapılandırma ve ajan dosyaları | kişisel durum (hiç) |

Yükleme sırası: genel dosya `data/<ad>.json`, üstüne `~/.orkestra/<ad>.yerel.json` yaması (yalnız `modeller`, `roller` ve kayıtlı üst alanlar); kişisel dosya önce `~/.orkestra`, yoksa eski kurulumdaki `data/` (uyarıyla), o da yoksa `*.ornek.json` (uyarıyla; seçici `--ornek-kabul` olmadan çalışmaz). `ORKESTRA_DIR` bu klasörü değiştirir. Güncelleme yazarken yalnız farkı yerel yamaya yazar.

Herkese açık kopya `ork disa-aktar --hedef <klasör> [--kuru]` ile üretilir: izin listesi (yeni dosya varsayılan olarak dışarıda), sonra kişisel veri tarayıcısı (kullanıcı dizini ve sürücü yolu deseni, e-posta, telefon, sağlamalı numaralar, yüksek entropi, anahtar ataması, ortamdaki anahtar değerleri (yalnız bellekte), makineden türetilen adlar (ev klasörü, oturum, makine, git kullanıcı adı) ve `kullanici-kurallari.json` `gizlilik.ek_sozluk` + `yasak_yol` sözlüğü; sözlüğün kendisi repoya girmez). Sözlük eşleşmesi Türkçe harfleri ASCII'ye katlar ve alt çizgi, rakam ya da büyük harfi sınır sayar (`ad_quick`, `AdSoyad` yakalanır). Sözlük boşsa dışa aktarma durur (`--sozluksuz` bilerek geçer). Kopyalamadan sonra hedef yeniden taranır, hedefteki fazla dosyalar uyarılır. Bulgu varsa çıkış ≠ 0, yayın yok. Yayın ayrıca kullanıcı onayı ister.

## 5. Kamu ve kişisel parça ayrımı (çok ajanlı iş)

- Lider işi kamu ve kişisel parçalara böler; kamu parçasını bağlamdan kopyalamadan **yeniden yazar**.
  - Kamu olabilir: genel kütüphane/API/algoritma sorusu (sentetik örnek; proje adı, yol, anahtar yok), kamuya açık kaynak araştırması (URL, DOI, makale metni), yer tutuculu genel taslak (`[AD SOYAD]`), açık lisanslı ya da herkese açık depodaki kod.
  - Kamu olamaz: `gizlilik.dis_havuza_gitmez` listesi, özel depo kodu (kullanıcı beyanı yoksa), kullanıcıya ait ham belge, kişisel notlar, üçüncü kişi verisi.
- Proje `.orkestra.json` `varsayilan_veri` (ör. herkese açık depoda `"genel"`); `gizli: true` her zaman üstündür. `genel`e indirme yalnız kişisel `gizlilik.guvenli_projeler` listesindeki köklerde geçerlidir (klonlanmış yabancı bir depo kamu havuzunu açamaz); sıkılaştırma (`kisisel`, `gizli`, `saglik`) her projede geçerlidir.
- `ork suru` her kamu/dış gönderimde tarar (sır/kişisel desenler + kişi düzeyi sağlık/üçüncü kişi kaydı: etiketli ad, protokol/dosya no, doğum tarihi, tanı kodu satırı); bulgu → `engel`, sıfır istek. Kamuya açık klinik literatür ("hastalarda", doz tabloları) bilerek engellenmez. Lider bölme kararında `ork gizlilik tara --dosya f` (değer basmaz, tür + satır).
- **Fail-closed yollar:** agy otomatik çağrısı kullanıcının MCP/kanca/talimat dosyası bağlamını yükleyebilir: yalın profil doğrulanmadan ya da kullanıcı kişisel bağlamı açıkça kabul etmeden otomatik yol yok. Codex profiliyle bedava platform, kullanıcı düzeyi ajan talimat dosyasının gitmediği doğrulanana kadar kapalı.
