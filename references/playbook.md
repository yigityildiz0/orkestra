# Orkestra yolak kılavuzu (playbook)

Hangi amaç için hangi alt ajan kombinasyonu. Lider bu dosyayı baştan sona okumaz: görevin türüne uyan bölümü (içindekiler) ve gerekiyorsa öncelik cetvelini okur. Model adı yerine **rol** düşün; somut model ve eforu her seferinde seçici verir (`ork sec`, `ork rol`). Buradaki model örnekleri bugünkü veriyle tipik sonuçtur, kural değildir; alan sırası `alanlar.md`'dedir. Kullanıcının açık isteği her yolağı geçer.

Kısaltmalar: Z/Q = zekâ puanı / sınıf eşiği (ölçek `z_olcek`). İB = iş birimi. "Farklı aile" = farklı sağlayıcı (Claude, GPT, Gemini, açık ağırlıklı aileler). "Elle" = otomatik çağrı izni olmayan yol: hazır komut satırı, kullanıcı çalıştırır. "Bedava" = kullanıcı kuralındaki ücretsiz platform (yalnız `--veri genel`).

`ork rol` ve doğrulayıcı seçiminde `--dogrulayici` aile adı değil **üreten modelin rolünü ya da kimliğini** alır (ör. `--dogrulayici sol`); aileyi seçici çıkarır. Verilmezse aile eleme yapılmaz ve betik uyarır.

## İçindekiler
1. Öncelik cetveli
2. Roller (nöbetçi, kontrolcü, hakem, haberci, arşivci, muhalif)
3. Havuz dolu / limit karar ağacı
4. Kalıplar: 1-12
5. Senaryolar: kod (13-24), araştırma ve metin (25-33), medya (34-38), kota/zaman/gizlilik (39-50), karışık durumlar (51-53)
6. Yaratıcı mod
7. Keşfedilen yolaklar

---

## 1. Öncelik cetveli

Sıra her satırda soldan sağa; bir koşul öncekini geçersiz kılmaz, daraltır.

| Koşul | Önce | Sonra | En son / asla |
|---|---|---|---|
| Her iş | Q'yu geçen varyantlar | aralarında kalite kümesi (δ bandı) | Z < Q hiçbir kota durumunda |
| Kalite kümesi içinde | bedava/yerel (genel veride) | ana havuz dışı abonelik (tempo izin verdikçe) | ana havuz; son çeyreği yalnız ona özgü kalite ve kritik iş |
| Bir aile bandın dışında üstün | o aile (kotaya bakılmadan, taban hariç) | - | daha zayıf modele kaçmak |
| Doğrulama | dış kanıt (test, şema, DOI) | farklı aile + farklı kanıt | yazanın kendisi |
| Hakem / birleştirici | Z ≥ Q, farklı aile, `kamu` olmayan havuz | - | bedava platform hakem değil |
| İzleme (nöbetçi) | hızlı-ucuz rol (Haiku medium, Terra low; genel veride bedava) | - | büyük modeller yalnız başka aday yoksa |
| Sabit alan kuralı (ör. görsel üretim) | kuraldaki rol, efor ve yol | elle yollar | daha zayıf modele düşüş |
| Gizli/kişisel/sağlık veri | yerel araç + `ozel` havuz | - | `dis` ve `kamu` havuz |
| Kullanıcı bekliyor | `--sure-dk` ile Q'yu geçen en hızlı | hız-kalite seçimini kullanıcıya sor | Q'yu geçmeyen hızlı model; uzun süren model kritik yolda |
| Kota kıt | hafif kip: yeten en ucuz | parçala, sıfırlamaya ertele | tabanı delmek |
| Toplu basit iş taşıyor | dış abonelik ve yerel kapasitesi kadar | kalanı sıraya al | yüzlerce basit parçayı ana havuza akıtmak |

Altın kurallar: (1) zekâyı brief'e harca, işçiye değil; (2) doğrulanabilir parça ucuz modele, doğrulanamayan güçlüye; (3) her işçi brief + bağlam + kontrol maliyeti getirir, küçük işi bölme; (4) çıktı iddiadır, kanıtla doğrula.

## 2. Roller

Seçici: `python -I scripts/ork.py rol <rol> <izlenen işin sınıfı> --dogrulayici <üreten> --veri <...>`. Eşik `Z ≥ max(rol tabanı, işin Q'su - rol farkı)` (ultra kipinde artar; değerler `siniflar.json` `roller_is`). Üretenle aynı aile elenir; hızlı model öne geçer. İzleyici rollerde büyük modeller yalnız başka aday yoksa listelenir. Hakem ve muhalif `kamu` havuzdan seçilmez.

| Rol | Tipik rol@efor | İş | Bedava havuz |
|---|---|---|---|
| nöbetçi | Haiku medium, Terra low, Luna medium | ilerlemeyi izler; döngü, boş çıktı, kırmızı test, kapsam dışı dosya, token israfı, gizli veri gönderimi, uydurma kaynak, analiz felci | evet |
| kontrolcü | Haiku medium, Terra low | şema ve "bitti" kanıtı (dosya var mı, test çıktısı ekli mi, alıntı birebir mi) | evet |
| hakem | farklı aileden Q'ya yakın model | ikinci görüş, A/B; çoğunluk oyu = üreticinin cevabı + 2 farklı aileden hakem | hayır |
| haberci | hızlı-ucuz rol | uzun çıktıyı lider için 5-10 satır özet | evet |
| arşivci | en ucuz rol | adlandırma, dizin, CHECKPOINT, karar kaydı | evet |
| muhalif | farklı aileden güçlü model | red team: en güçlü itirazlar, başarısızlık senaryoları | hayır |

Nöbetçi nasıl çalışır: lider işçileri arka planda başlatır; nöbetçi aralıklarla ya da her işçi adımından sonra yalnız OKUR (günlük, diff özeti, test çıktısı) ve tek dosyaya ya da lidere yazar: `UYARI <işçi> <tür>: <kanıt dosya:satır>`. Lider karar verir (durdur, yeniden brief'le, yükselt). Nöbetçi düzeltmez, kod çalıştırmaz, işçiye yazmaz. Nöbetçi brief'i: izlenecek yollar, beklenen çıktı biçimi, "takılma" tanımı (aynı adım 3 kez, 10 dk çıktı yok), token bütçesi, izinli klasörler, gizli veri kalıpları, kaynak listesi.

`kritik` sınıfta hakem adayı çıkmayabilir: lider kendisi değerlendirir ya da kullanıcıya sorar.

## 3. Havuz dolu / limit karar ağacı

Her 429/503/kota hatası sınıflanır ve `~/.orkestra/durum.json`'a soğuma olarak yazılır (tüm havuzlar için aynı mekanizma); seçici ve `ork kota` bunu okur.

1. **Kısa dolu** (ipucu ≤ 60 sn): aynı modelde üstel bekleme + jitter, en çok 2 kez. Soğuma yok.
2. **Model dolu** (ipucusuz/uzun 503, adil pay sınırı): model soğumaya (üstel); aynı Z bandındaki **kardeş** modele geç; işin Q'su altına inilmez (çağrı satırı `--min-z <Q>` taşır).
3. **Havuz dolu** (günlük kota, kısa token penceresi, eşzamanlılık): havuzun tamamı soğumaya; seçici bu süre boyunca onsuz sıralar ve `NOT: <havuz> dolu, N dk soğumada; yerine <aday> (eşik aynı)` yazar.
4. **Bekle seçeneği:** iş acil değilse ve soğuma ≤ 30 dk: kuyruğa al, süre dolunca seçiciyi yeniden çalıştır. Günlük kotada beklenmez.
5. **Kısmi geçiş** (`--parca N`): havuz dalgalıysa parçaların en çok yarısı ona, kalanı sıradaki havuza; başka havuz yetmezse kalan da ona (boşta kalmaz).
6. **Yoklama:** süre dolunca ilk çağrı kısa ping; başarı kaydı siler, hata süreyi uzatır.
7. **Eşik asla düşmez:** yerine gelen model de Z ≥ Q olmalı.
8. Ana havuz son çeyrekte ve dış havuzlar doluysa: D1-D5 (`algoritma.md` bölüm 8); tabanı delmek seçenek değildir.

---

## 4. Kalıplar (senaryoların yapı taşları)

### 1. Üretici-eleştirmen döngüsü
- **Amaç:** tek geçişte kalitesi belirsiz çıktıyı bir tur düzelttirmek.
- **Ajanlar:** üretici (sınıfın seçtiği) → eleştirmen (hakem rolü, farklı aile) → üretici bir tur.
- **Sıra:** üret → eleştiri yalnız madde listesi → düzelt → kontrolcü kanıtı denetler. En çok 2 tur.
- **Ne zaman:** yazı, plan, tek modül kod. **Değil:** kapalı cevaplı iş (oy daha ucuz).
- **Maliyet:** ~1.6 × üretim.

### 2. Best-of-N doğrulayıcılı
- **Amaç:** N aday üret, dış doğrulayıcı (test, şema, alıntı denetimi) en iyisini seçsin.
- **Ajanlar:** N × Q'yu geçen ucuz üretici + betik doğrulayıcı.
- **Sıra:** küçük N, ardışık + erken durdurma, her denemede efor/aile/brief farkı → lider testleri ayrı kopyada koşar → kabul edilenlerin bir kısmı bağımsız denetim. Hiçbiri geçmezse N artmaz, model yükselir.
- **Ne zaman:** doğrulayıcı kesin. **Değil:** zor/kritik, öznel kalite, testi zayıf modelin yazdığı iş.
- **Maliyet:** N × küçük.

### 3. Kaskad (ucuzdan pahalıya)
- **Amaç:** çoğu parça ucuz modelde biter, yalnız düşenler güçlüye gider.
- **Ajanlar:** her kademe kendi sınıfında Q'yu geçer; merdiven `siniflar.json` `yukseltme_merdiveni`.
- **Sıra:** her kademede dış kontrol; kalan → bir üst kademe. Eforu değil modeli yükselt.
- **Ne zaman:** çok sayıda benzer parça, net geçme ölçütü ve `p_yukselt` başabaşın altında (`algoritma.md` bölüm 7). **Değil:** tek büyük, bölünmez iş; baştan zor belli iş.
- **Maliyet:** literatürde tipik %40-60 tasarruf; kötü durumda artı.
- **Kanıtlı kaskad:** genel veride ve tam dış kanıtta (`--dis-kanit test_tam|kapali_cevap|sema_dogrulayici`) ilk kademe Q altındaki bedava model olabilir; geçmeyen öğe Q'yu karşılayan modele çıkar (`ork suru` + `bagimli` ya da `aday_yargic`).

### 4. Gölge çalıştırma
- **Amaç:** ucuz model önce dener, güçlü model yalnız doğrular.
- **Ajanlar:** gölge (ucuz) → doğrulayıcı (Z ≥ Q, farklı aile) "doğru/yanlış + düzeltilecek yer".
- **Sıra:** gölge taslak → doğrulayıcı diff okur → yanlışsa güçlü üretici yeniden yazar.
- **Ne zaman:** doğrulamak üretmekten çok ucuzsa (özet, dönüşüm, çeviri). **Değil:** doğrulama da üretim kadar zorsa.
- **Maliyet:** güçlü modelin %20-30'u.

### 5. Nöbetçi deseni
- **Amaç:** uzun/paralel işte erken hata yakalamak.
- **Ajanlar:** işçiler + nöbetçi (farklı aile).
- **Sıra:** işçiler başlar → nöbetçi aralıklarla okur → UYARI → lider müdahale.
- **Ne zaman:** ≥3 paralel işçi, ≥20 dk iş, gizli veri ya da kaynak uydurma riski. **Değil:** 5 dk'lık tek iş.
- **Maliyet:** işin %3-8'i.

### 6. Jüri
- **Amaç:** öznel ya da çok boyutlu kararda tek modelin yanlılığını azaltmak.
- **Ajanlar:** 3 farklı aileden 3 oy (üreticinin cevabı + 2 hakem); saf jüride `--dogrulayici` vermeden 3 aile.
- **Sıra:** bağımsız puan/gerekçe (birbirini görmeden) → 2/3 uyuşma → uyuşmazlıkta bir kademe güçlü model. Tartışma turu yok.
- **Ne zaman:** tasarım seçimi, inceleme önceliği, metin değerlendirme. **Değil:** olgusal soru (kaynağa bak).
- **Maliyet:** 3 × küçük.

### 7. Muhalif ajan
- **Amaç:** önerinin kör noktasını bulmak.
- **Ajanlar:** önerici (güçlü) + muhalif (farklı aile).
- **Sıra:** öneri → "en güçlü 5 itiraz + başarısızlık senaryosu" → önerici yanıt → lider karar.
- **Ne zaman:** mimari, geri alınamaz karar. **Değil:** rutin iş.
- **Maliyet:** ~0.5 İB.

### 8. Harita-indirgeme
- **Amaç:** çok büyük girdiyi parçalayıp birleştirmek.
- **Ajanlar:** N × harita (genel veride bedava; değilse ucuz rol) + birleştirici (Z ≥ Q).
- **Sıra:** lider böler, aynı şablonla parça brief'i → şemalı JSON çıktılar → birleştirici → kontrolcü. Harita öğeleri tek `ork suru calistir` planında; birleştirici `bagimli` öğe.
- **Ne zaman:** envanter, özet, etiketleme. **Değil:** parçalar arası bağımlılık yüksekse.
- **Maliyet:** ucuz; asıl maliyet birleştirici.

### 9. Keşif turu
- **Amaç:** çözüm uzayını hızla genişletmek.
- **Ajanlar:** 3 farklı aileden kaşif bağımsız; sonra sentezci (güçlü).
- **Sıra:** aynı brief, birbirini görmeden 3 öneri → sentez: ortak çekirdek + en iyi aykırı fikir.
- **Ne zaman:** isimlendirme, ürün fikri, mimari seçenekler. **Değil:** tek doğru cevaplı iş.
- **Maliyet:** 3 × orta.

### 10. Bilgi ajanı önce
- **Amaç:** plan öncesi bağlam toplamak (salt okunur).
- **Ajanlar:** 1-3 okuyucu (salt okuma; genel veride bedava özet), lider plan.
- **Sıra:** okuyucular paralel → lider özetleri okur → plan → işçiler.
- **Ne zaman:** bilinmeyen kod tabanı/klasör. **Değil:** lider zaten biliyorsa.
- **Maliyet:** düşük; liderin bağlamını korur.

### 11. Çapraz aile doğrulama
- **Amaç:** aynı ailenin ortak hatasını yakalamak.
- **Ajanlar:** üretici A ailesi → doğrulayıcı B ailesi; mümkünse farklı kanıt/kip.
- **Sıra:** doğrulayıcı yalnız çıktıyı ve kanıtı görür (üreticinin gerekçesini değil) → uyuşmazlıkta lider.
- **Ne zaman:** her esaslı çıktı. **Değil:** betik kesin doğruluyorsa.
- **Maliyet:** üretimin %20-40'ı.

### 12. Kanıt kapısı
- **Amaç:** "bitti" iddiasını kanıta bağlamak.
- **Ajanlar:** kontrolcü + betik (test, grep, şema, ekran görüntüsü).
- **Sıra:** önce betik (ucuz, kesin) → yalnız betiğin ölçemediği kısım kontrolcüye → KALDI ise işçiye eksik listesi.
- **Ne zaman:** her işçi çıktısında.
- **Maliyet:** çok düşük.

---

## 5. Senaryolar

### Kod

### 13. Büyük kod tabanı haritalama
- **Ajanlar:** varsa önce bilgi grafiği aracı; dosya özetleri paralel (kamuya açık repoda bedava, değilse Codex read-only ya da agy; Claude Explore alt ajanı yerine `ork suru`); birleştirici `kod/refaktor` ya da `kod/zor_ajan` sınıfında; haberci özet.
- **Sıra:** grafik → dosya özetleri → birleştirici harita → kontrolcü rastgele 5 dosyayı doğrular.
- **Değil:** 10 dosyalık proje; gizli kod bedava havuza.
- **Maliyet:** birleştirme 0.5-1 İB.

### 14. Hata avı (dedektif + kontrolcü)
- **Ajanlar:** dedektif (`zor`; tipik Opus high ya da Sol high) + kontrolcü (minimal yeniden üretim, log kanıtı) + uzun sürerse nöbetçi. Ekran görüntülü hatada `kod/ekran_hata` sırası.
- **Sıra:** kontrolcü yeniden üretim betiği → dedektif hipotez + test → kontrolcü testi koşar → düzeltme.
- **Değil:** yazım hatası (lider düzeltir).
- **Maliyet:** 2-4 İB.

### 15. Çok dosyalı refaktör
- **Ajanlar:** üretici (`kod/refaktor`; tipik Opus) + nöbetçi (kapsam dışı dosya, kırmızı test) + farklı aileden hakem (diff).
- **Sıra:** plan + dosya listesi + sahiplik → dosya grupları → her grupta test → hakem diff → kontrolcü.
- **Değil:** test yoksa (önce senaryo 18).
- **Maliyet:** 3-6 İB.

### 16. Yeni özellik (dikey dilim)
- **Ajanlar:** lider brief → üretici (`kod/gunluk`, eşit kalite kümesi kapasiteye göre) → test yazıcı (farklı aile) → kontrolcü.
- **Değil:** gereksinim belirsiz (önce kalıp 9).
- **Maliyet:** 1-3 İB.

### 17. Kod incelemesi (iki farklı aile)
- **Ajanlar:** iki bağımsız inceleyici, farklı aile; lider birleştirir, tekrarları atar.
- **Sıra:** aynı diff, birbirini görmeden → yalnız ikisinin de ya da kanıtlı tekinin bulgusu raporlanır.
- **Değil:** biçim değişikliği (linter).
- **Maliyet:** 2 × 0.5 İB.

### 18. Test yazma
- **Ajanlar:** test yazıcı (net arayüzde ucuz rol) + kontrolcü (mutasyon denemesi); bedava yalnız test VERİSİ üretir.
- **Sıra:** arayüz listesi → testler → lider koşar → kasıtlı hata ekleyip testin yakaladığını gör.
- **Değil:** testi, test edilen kodu üreten zayıf model yazacaksa.
- **Maliyet:** 0.5-2 İB.

### 19. Güvenlik taraması
- **Ajanlar:** betik tarama (gizlilik tarayıcısı, grep) → bulgu triyajı (güçlü; kritikte `kritik`) → muhalif.
- **Değil:** kaynak kodu `kamu` havuza gönderip "sır var mı" sormak.
- **Maliyet:** 1-3 İB.

### 20. Bağımlılık/sürüm yükseltme
- **Ajanlar:** araştırmacı (değişiklik günlüğü, resmî doküman aracı) + üretici (`kod/goc` sırası) + nöbetçi (kırmızı test).
- **Sıra:** kırıcı değişiklik listesi → adım adım yükseltme → her adımda test.
- **Değil:** yama sürüm (lider).
- **Maliyet:** 1-2 İB.

### 21. Hipotez paralelliği
- **Ajanlar:** 3 hipotez işçisi (farklı aile), her biri tek hipotez; hakem kanıtı tartar.
- **Sıra:** lider 3 hipotez + ayırt edici deney → işçiler paralel → hakem → düzeltme.
- **Değil:** neden tekse.
- **Maliyet:** 3 × 0.5 İB.

### 22. Dokümantasyon / docstring
- **Ajanlar:** kamuya açık kodda bedava toplu iş, değilse ucuz rol; kontrolcü imza uyumu (betik).
- **Değil:** gizli kod bedava havuza.
- **Maliyet:** çok düşük.

### 23. Göç / büyük ölçekli mekanik değişiklik
- **Ajanlar:** codemod betiği (lider yazar) + istisna dosyaları için ucuz rol + kontrolcü (derleme/test). Dil/çatı göçü ise `kod/goc` sırası.
- **Sıra:** codemod küçük örneklemde → test → tüm dosyalar → istisnalar → derleme/test.
- **Değil:** her dosya farklı karar istiyorsa. Toptan bul-değiştir hatasına dikkat (brief'te yasakla, sonra tara).
- **Maliyet:** düşük.

### 24. Performans iyileştirme
- **Ajanlar:** profil betiği → analiz (güçlü) → uygulama → kontrolcü (ölçüm öncesi/sonrası).
- **Değil:** ölçmeden "hızlandır".
- **Maliyet:** 1-3 İB.

### Araştırma ve metin

### 25. Web araştırması (kaynak denetimli)
- **Ajanlar:** araştırmacı (`arastirma/web`) + kaynak denetçisi (her URL açılır, alıntı birebir) + nöbetçi (uydurma URL). Olgu teyidinde `arastirma/olgu_teyit` sırası; otomatik yolda dış kanıt şart.
- **Sıra:** soru ayrıştır → paralel arama → alıntılı iddialar → kontrolcü → lider sentez.
- **Değil:** URL'siz iddia kabul etmek.
- **Maliyet:** 1-2 İB.

### 26. Literatür / akademik
- **Ajanlar:** arama araçları (PubMed, Consensus vb.) → özetleyici (yalnız kamuya açık özetler bedavada; ayrı `basit --veri genel` seçimi) → kaynak denetimi (betik + kontrolcü) → sentez (`arastirma/sentez`).
- **Değil:** yayımlanmamış akademik metni `dis`/`kamu` havuza vermek.
- **Maliyet:** orta; atıf doğrulama şart.

### 27. Uzun belge özeti
- **Ajanlar:** bölüm özetleri (genel veride bedava, değilse ucuz rol) → birleştirici (`arastirma/uzun_belge`) → haberci. Uzun PDF'de efor orta (yüksek efor zararlı).
- **Değil:** kişisel/gizli belge `kamu` havuza.
- **Maliyet:** düşük.

### 28. Toplu çeviri
- **Ajanlar:** kamuya açık metinde bedava toplu iş, değilse ucuz rol; terim sözlüğü lider; kontrolcü (biçim, yer tutucu, kod korunmuş mu).
- **Değil:** hukuki/klinik metin (güçlü model + insan); uzun kültür yüklü Türkçe metin küçük modele.
- **Maliyet:** çok düşük.

### 29. Veri temizleme
- **Ajanlar:** betik önce (deterministik) → şemalı çoğunluk oyu (kamuya açık veride bedava) → uyuşmazlık parçaları güçlüye.
- **Değil:** kişisel veri (yerel betik + `ozel` havuz).
- **Maliyet:** neredeyse sıfır.

### 30. Belge / sunum üretimi
- **Ajanlar:** iskelet (`yazim/rapor`) → bölüm yazımı → görseller (sabit görsel kuralı, metinsiz) → kontrolcü (taşma, yazım, kaynak).
- **Değil:** tek paragraf.
- **Maliyet:** 1-3 İB + görsel kotası.

### 31. Yazı düzeltme / üslup
- **Ajanlar:** düzeltici + farklı aileden eleştirmen bir tur; Türkçe metinde dil denetim betiği varsa önce o.
- **Sıra:** düzeltici → madde listesi → son tur → lider anlam kaybı denetimi.
- **Maliyet:** düşük.

### 32. Soru-cevap / bilgi tabanı
- **Ajanlar:** alıntılı çıkarım (kamuya açık dokümanda bedava, `basit`) → birleştirici (`arastirma`) → kontrolcü alıntı.
- **Değil:** iç belge `kamu` havuza.
- **Maliyet:** düşük.

### 33. Karşılaştırma tablosu
- **Ajanlar:** kaynak toplayıcı → hücre doldurucu (kaynaklı) → hakem tutarlılık. Tablo modellemede `arastirma/tablo` sırası.
- **Değil:** kişisel finans/yatırım kararı (ayrı skill, uyarılar).
- **Maliyet:** düşük.

### Medya

### 34. Görsel üretim
- **Ajanlar:** sabit görsel kuralındaki rol, efor ve yol (`kullanici-kurallari.json` `sabit_kurallar.gorsel_uretim`; yoksa `alanlar.md`) → kontrolcü (görseli açar: yazı bozulması, logo taklidi) → yazı/isim lider ekler.
- **Sıra:** metinsiz görsel brief'i (konu, kompozisyon, `quality`, `size`) → üretici → kontrolcü → yazı bindirme. Var olan görseli düzenlemede girdi dosyası verilir.
- **Kural havuzu tabanda:** elle yollar (uygulama içi görsel üretim, otomatik çağrı izni olmayan platformun görsel aracı) önerilir; daha zayıf modele düşülmez; kullanıcıya sor.
- **Değil:** gerçek arayüz görüntüsü (headless tarayıcıyla ekran görüntüsü al).

### 35. Görsel anlama
- **Ajanlar:** `gorsel_analiz/<alt>` sırası (ekran-kod, OCR/sayma, grafik, uzun PDF); ikinci görüş farklı aile, yalnız belirsiz/önemli bulguda.
- **Değil:** görsel almayan model; tıbbi görüntüde insan doğrulaması olmadan karar.
- **Maliyet:** orta.

### 36. Video anlama
- **Ajanlar:** `video_analiz` rotası: video+ses alan aile (elle) ya da otomatik yol: ffmpeg kare (sahne değişimi) + yerel döküm + kare yorumu (`gorsel_analiz`) + transkript özeti + sentez.
- **Ne zaman:** kullanıcı yoksa ya da içerik gizliyse otomatik yol.
- **Değil:** video almayan modele "video ver".
- **Maliyet:** kare sayısıyla orantılı; kareyi seyrelt, uzun videoyu parçala.

### 37. Video üretimi
- **Ajanlar:** `video_uretim` rotası (uygulama/elle ya da yerel); ya da kodla video (Remotion, HyperFrames vb.; üretici kod sınıfında) + kare örneklemi denetimi.
- **Değil:** "yaptım" demek; yapılamıyorsa "yapılamaz".

### 38. Ses / konuşma
- **Ajanlar:** yerel döküm (otomatik varsayılan) → düzeltici (ucuz; genel veride bedava) → zamanlama betiği. TTS ve müzik `ses` rotası.
- **Değil:** sağlık görüşmesi `dis`/`kamu` havuza.
- **Maliyet:** neredeyse sıfır.

### Kota, zaman ve gizlilik

### 39. Havuz kısa süreli dolu
- **Ajanlar:** kardeş model → sıradaki havuz (eşik aynı) → iş acil değilse BEKLE.
- **Sıra:** bölüm 3 karar ağacı → `NOT` satırını kullanıcıya tek satırla aktar.
- **Değil:** günlük kota bitti (senaryo 40).

### 40. Bedava havuzun günlük kotası bitti
- **Ajanlar:** dış abonelik ve yerel; büyük toplu iş sıfırlama sonrasına ertelenir.
- **Sıra:** sığanı dış abonelikte → sığmayanı sıraya al. Taşan basit parçaları ana havuza akıtma.

### 41. Dalgalı havuz (kısmi geçiş)
- **Ajanlar:** `--parca N`: en çok yarısı dalgalı havuza, kalanı sıradakine; nöbetçi hataları izler.
- **Değil:** tek parça iş.

### 42. Kota kurtarma (yük kaydırma)
- **Ajanlar:** hafif kip; ağır okuma/yazma dış aboneliğe; lider yalnız plan + doğrulama; genel veri parçaları bedavaya.
- **Ne zaman:** ana havuz kısa pencere tamponuna ya da son çeyreğe yaklaştı. **Değil:** tabanı delmek; hepsi tabandaysa kullanıcıya sor.

### 43. Gizli veri
- **Ajanlar:** `--veri gizli|kisisel|saglik`: yerel betik + `ozel` havuzlar; nöbetçi çıktıda gizli veri arar.
- **Değil:** "anonimleştirdim" diye `kamu` havuza.

### 44. Uzun çalışan iş
- **Ajanlar:** işçiler arka planda + nöbetçi + arşivci (CHECKPOINT, `devir.json`) + haberci (periyodik özet).
- **Ne zaman:** > 30 dk. **Değil:** kullanıcı her adımı onaylamak istiyorsa.
- **Maliyet:** +%5-10 gözetim.

### 45. Acil iş (kullanıcı bekliyor)
- **Ajanlar:** `--sure-dk 10`: Q'yu geçen EN HIZLI aday; parçalama yok (brief maliyeti zamanı yer).
- **Değil:** Q'yu geçmeyen hızlı modeli zorlamak; kalite kritikse hız-kalite seçimini sor. Etkileşimli işte en yüksek efor yok (ilk token gecikmesi).

### 46. Kullanılmayan pencereyi değerlendirme
- **Ajanlar:** sıfırlamaya yaklaşan ve kullanılmamış payı olan havuzda (yüksek ρ) genel veriyle toplu iş; sabah örneklem denetimi.
- **Değil:** gizli veri; Q'yu geçmeyen model.

### 47. Öğrenci / akademik iş
- **Ajanlar:** araştırma (senaryo 26) + kaynak denetimi (her atıf açılır) + muhalif + yazar (`yazim`) + kontrolcü atıf biçimi.
- **Değil:** uydurma kaynak; yayımlanmamış metni `dis`/`kamu` havuza.

### 48. Sağlık / klinik
- **Ajanlar:** ilgili klinik skill + kanıt araçları + güçlü model (`arastirma/klinik`) + farklı aile ikinci görüş + insan onayı.
- **Değil:** `kamu` havuz, ucuz sürü, kanıtsız öneri.
- **Maliyet:** yüksek ama zorunlu.

### 49. Mimari karar
- **Ajanlar:** önerici (güçlü) + muhalif (farklı aile) + gerekirse keşif turu + lider karar notu.
- **Ne zaman:** kritik/zor. **Değil:** küçük modül.
- **Maliyet:** 2-4 İB.

### 50. Kota ölçümü (kalibrasyon)
- **Ajanlar:** tek işçi; aynı anda başka iş yok; önce ve sonra kota okuması; `olc` kaydı.
- **Ne zaman:** yeni model, öncül `K_p`. **Değil:** paralel iş sırasında.

### Karışık durumlar

### 51. Karışık duyarlılıkta iş
- **Ajanlar:** lider parçaları veri sınıfına böler; kamu parçaları `--veri genel`, gizli çekirdek `--veri gizli`; nöbetçi sızıntıyı izler.
- **Sıra:** her parçaya veri etiketi → kişisel ayrıntıyı çıkararak kamu parçayı yeniden yaz (`ork gizlilik tara --dosya`) → iki kol paralel (kamu kol `ork suru`, kişisel kol host/yerel) → birleştirme gizli koldaki modelde.
- **Değil:** parçalar ayrılamıyorsa (tümü gizli).

### 52. Gizli belge özeti ve risk incelemesi
- **Ajanlar:** yerel metin çıkarma → özetleyici (`--veri gizli`, `arastirma/finans_hukuk` ya da `uzun_belge`) → farklı aileden risk hakemi → kontrolcü (her risk maddesi belgede birebir alıntı).
- **Değil:** `dis`/`kamu` havuz; "hukuki görüş" vermek (karar kullanıcıda).

### 53. Ara sıra kırılan test
- **Ajanlar:** tekrar koşu betiği (N kez; ortam, sıra, zaman kaydı) → haberci istatistik özeti → hipotez paralelliği (senaryo 21) → dedektif (`zor`) → nöbetçi.
- **Sıra:** kırılma oranı → hipotez başına ayırt edici deney → düzeltme → aynı sayıda tekrarla oran karşılaştırması.

### 54. İnce lider çok ajanlı iş (uçtan uca)
- **İstek:** "Bu 6 modülün birim testlerini yaz, README'yi güncelle, 4 kaynak makaleyi özetle."
- **Böl ve sınıfla:** 6 × `kod/kod/gunluk` (genel, düzenleme, `dis_kanit: test_tam`), 1 × `normal/yazim` (genel), 4 × `arastirma/uzun_belge` (genel). `parcalar.json` = `{is_id, parcalar: [...]}`.
- **Seç (tek çağrı):** `ORK sec --plan parcalar.json --suru-plani suru.json --claude 5s=58,hafta=71` → ör. `6x hydrogen@high (agy-oto)`, `1x sol@medium (codex)`, `4x deepseek@high (bedava)`, `0 claude`; `SOR` satırı varsa önce tek soru.
- **Yürüt:** tek Bash `ORK suru calistir --plan suru.json`; `CLAUDE` satırı varsa aynı turda Agent ("çıktıyı <dosya>'ya yaz, ≤ 10 satır özet dön").
- **Doğrula:** testler koşucuda (`dogrulama: {tur: test, komut: [...]}`); lider yalnız özet JSON'u ve başarısız öğelerin çıktısını okur; makale özetinde DOI/künye denetimi liderde.
- **Bildir:** `orkestra: kod -> hydrogen@high (agy), 6 işçi; ...` + "Claude tasarrufu ≈ X USD-e (%Y)".
- **Neden:** Claude-yalnız aynı iş 5s penceresinin ~%30'u; ince lider brief + özet ≈ %0.6 [T].
- **Değil:** tek küçük iş; parçalar arası sıkı bağımlılık; kişisel veriyi ayırmadan kamu havuza gönderim.

---

## 6. Yaratıcı mod

Uyan yolak yoksa lider kendi yolağını tasarlar. Beş ilke:
1. **Hedef:** "bitti" neyle kanıtlanacak? Kanıtı önce yaz.
2. **Doğrulanabilirlik:** her parça için dış ya da farklı aileden doğrulayıcı; yoksa parçayı güçlü modele ver.
3. **Farklılık:** üreten ve denetleyen farklı bağlam, tercihen farklı aile; kritik yolda tek modele bağımlılık yok.
4. **Maliyet:** kalite kümesi içinde kapasiteye göre; Q delinmez; tahmini maliyeti seçiciyle ölç (`--parca`, `--sure-dk`).
5. **Geri dönüş:** her adım düşerse ne olacağı (kardeş model, sıradaki havuz, bekle, kullanıcıya sor) baştan yazılı.

Bileşen örnekleri: nöbetçi + kaskad; gölge çalıştırma + jüri; keşif turu + muhalif; ucuz modelle test verisi + güçlü modelle test; haberci zinciri ile uzun işte lider bağlamını koruma.

Yolak işe yaradıysa lider kullanıcıya önerir: "Bu yolağı 'Keşfedilen yolaklar' bölümüne ekleyeyim mi?" Onay gelmeden yazmaz. Kayıt biçimi senaryolarla aynı (Amaç, Ajanlar, Sıra, Ne zaman/Değil, Maliyet) artı tarih ve kanıt.

## 7. Keşfedilen yolaklar

(Henüz yok. Kullanıcı onayıyla eklenir.)
