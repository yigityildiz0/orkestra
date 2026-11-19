# Çalışma döngüsü

Her işte geçerlidir; işin boyutuna göre ölçeklenir. Tek adımlık işte yalnız 3 (Uygula) ve 4 (Doğrula). Kişiye özgü yollar ve kapanış adımları `data/kullanici-kurallari.json` `kapanis_kancasi` alanındadır.

0. **Sınıflandır:** küçük / çok adımlı / riskli. Sınıf plan derinliğini ve onay gereğini belirler. Riskli: geri alınamaz, dış sisteme yazan, çok dosyalı ya da olgu riski taşıyan iş (`siniflar.json` `zorluk_rubrigi`).
1. **Anla:** kullanıcının bütün isteklerini numaralı listeye çıkar (sonradan eklenenler dahil), "bitti" ölçütünü yaz. Mevcut sistemi hedefli incele (büyük dosyayı gereksiz yere bütünüyle yükleme), varsayımı doğrula; not ile canlı dosya çelişirse canlıya güven. Sonucu değiştirmeyen belirsizlikte varsay ve belirt; değiştirende soruları tek mesajda topla, beklerken bağımsız kısmı ilerlet.
2. **Planla:** kurulu skill, MCP ve CLI'yi değerlendir, uygunsa kullan. Bağımsız işleri paralelleştir (paralel işçiye çakışmayan dosya ver), bağımlıları sırala. Model, efor ve platform seçimi orkestra seçicisinden gelir.
3. **Uygula:** küçük, geri alınabilir adımlar. Mimariyi, bağımlılıkları ve kullanıcının değişikliklerini koru; ilgisiz refaktör yapma (bağımlılık kurulumu açık talepte serbest). Belirtiyi değil kök nedeni çöz.
4. **Doğrula:** "bitti" demeden çalıştır, test et, çıktıya bak; ön yüzü gerçek tarayıcıda gör. Önemli işte bağımsız gözle (eleştirmen ajan ya da kendi ikinci okuman) hata ara. Yeni kanıt yoksa aynı kontrolü ya da başarısız çözümü tekrarlama; iki deneme başarısızsa yaklaşımı değiştir, elenen hipotezleri yaz. Testi ya da güvenlik kontrolünü hatayı gizlemek için kapatma; test edilemeyeni açıkça söyle, sahte entegrasyon sunma.
5. **Kapat:** 1. adımdaki listeyi madde madde işaretle (yapıldı / yapılmadı + neden). Uzun görevde ana oturum durumu yerleşik görev listesinde ya da `CHECKPOINT.md`'de tutar (proje kökünde; proje yoksa `kapanis_kancasi.checkpoint.proje_yoksa` dizininde; alt ajan yazmaz); oturum ya da ajan değişiminde devir özeti bırak. Ardından görev sonu özeti (`kapanis_kancasi.gorev_sonu_ozeti` biçimi; yoksa: sonuç, etkilenen dosya/sistem, doğrulama/test, kalan risk ya da sonraki adım).

Orkestra ile ilişkisi: 2. adımda bölme ve seçim (`SKILL.md` akışı), 4. adımda doğrulayıcı sırası (`brief-rehberi.md`), 5. adımda `olc` kaydının tamamlanması.
