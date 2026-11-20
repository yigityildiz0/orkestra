# Karar algoritması

Seçici (`scripts/ork/secici.py`) bu belgeyi uygular. Sayılar burada değil veri dosyalarındadır: eşikler ve bantlar `data/siniflar.json`, model zekâsı ve maliyeti `data/modeller.json`, havuzlar kişisel `platformlar.json`, kişisel tabanlar ve faz parametreleri `kullanici-kurallari.json` (ikisi de `~/.orkestra/` altındadır; örnekleri `data/*.ornek.json`). Bir parametre değişecekse veri dosyası değişir, bu belge değil.

Etiketler: [R] resmî, [B] bağımsız ölçüm, [Y] yerel ölçüm, [T] türetilmiş, [DY] doğrulanamadı.

## İçindekiler
1. Gösterim
2. Değişmezler
3. Akış (sözde kod)
4. Gerçek iş maliyeti
5. Küçük yüzde farkına dayanıklılık
6. Ana havuz fazı ve katmanlar
7. Kaskad, yükseltme, doğrulayıcı
8. Zarif düşüş
9. Gerekçe satırı ve ölçüm kaydı
10. Örnek çözüm
11. Hafta planı ve uyarlanır ağırlık
12. Şef tavanı (R16)
13. Uygulama dili: Python mu Rust mu

## 1. Gösterim

| Sembol | Anlam | Kaynak |
|---|---|---|
| `a = (m, e, y)` | aday: model kimliği, efor, erişim yolu (`claude-agent`, `codex-exec`, `agy-elle`, `bedava-api`, `yerel`, `elle`) | `platformlar.json` `erisim` |
| `p(a)` | adayın havuzu | `platformlar.json` `havuzlar` |
| `Z(a)` | varyant zekâsı (ölçek `z_olcek` ile kilitli) | `modeller.json` `varyantlar[e].z` |
| `q(a, alt)` | alt alan puanı **o eforda** (efor kaydırması: bölüm 3 E); yoksa `Z(a)` ve `alan_olcumu_yok` bayrağı | `modeller.json` `alanlar`, `varyantlar[e].alt` |
| `g(a)` | görev başı maliyet (USD eşdeğeri, liste fiyatıyla) | `varyantlar[e].gorev_usd` |
| `Q` | işin sınıf eşiği | `siniflar.json` `q` |
| `İB` | iş birimi: bir standart görev eşdeğeri; küçük, orta, büyük, çok büyük | `siniflar.json` `is_birimi` |
| `k_w, t_w, T_w` | pencere `w` için kalan oran, sıfırlamaya kalan süre, pencere uzunluğu | kota anlığı |
| `taban_w`, `rezerv_p` | delinmeyen alt sınır; korunan pay | `kullanici-kurallari.json` |
| `K_p,w` | havuzun pencere kapasitesi (USD eşdeğeri); öncül ya da kalibre | `platformlar.json` `K_p`, `~/.orkestra/kapasite_olcum.json` |
| `s_p` | sayaç düzeltmesi (havuzun modeli liste fiyatından farklı sayması) | `platformlar.json` `s_p` |
| `host` | liderin çalıştığı platform; erişim yollarını belirler | istek |

## 2. Değişmezler (hiçbir kipte gevşemez)

1. **Q taban, tavan değil.** `Z(a) >= Q`; kritik işte `Z >= Q_kritik`. `z_kaynak = tahmin` ise `Z - tahmin_indirimi` ve zor/kritikte aday değil. `z_kaynak = halef_devralinan` (otomatik halef, selefin ölçümü) ise `Z - halef_z_indirimi` ve zor/kritikte de adaydır; selef `yedek` durumunda kalır ve sıralamada halefin arkasına düşer. Kota baskısı Q'yu düşürmez; işi erteler (bölüm 8).
2. **Tabanlar delinmez.** Okunamayan havuz `k = 0.5, belirsiz` sayılır ve maliyeti 2 ile çarpılır; gerçek bir %50 okuması bu cezayı almaz. Okunamayan bedava havuz (anahtar yok, uç yanıtsız) hiç aday olmaz. Okunamayan ana havuz rezervi açık olsa da (üstün/kritik iş) yalnız katman 4'te kullanılır ve çıktıya "ana havuz kotası bilinmiyor" uyarısı düşer; üstün ya da kritik işte seçim ona düşerse SOR T0 (önce `get_usage` oku). Önbellekteki Claude değeri 45 dk, 5 saatlik penceresi 15 dk geçerlidir.
3. **Yasak** sağlayıcı/hat ve takma ad düzeyindedir (alt dize değil); gelecek sürümleri de kapsar. `onay_bekliyor` (yeni hat) seçilemez. **Önce sor** hattı (`kullanici-kurallari.once_sor.saglayici_hat`) yasak değildir ama aday kümesine girmez; yalnız kullanıcının açık isteğiyle (`--zorla`) seçilir. Normal seçimden sonra `_once_sor_onerisi` bakar: sınıf `kosul.siniflar` içinde, önce-sor adayının q'su otomatik adayların en iyisini en az `kosul.ustunluk_delta` × δ aşıyor (aynı ölçüt, ölçülmüş; köprülü ve ölçümsüz sayılmaz), aday havuzuna sığıyor ve hafif kip değilse sonuç SOR T7 olur (farkı koruyan en düşük efor önerilir; varsayılan ret). Sığmıyorsa ya da fark küçükse soru çıkmaz, otomatik seçim yürür.
4. **Gizlilik fail-closed.** `veri` ∈ {bilinmiyor, kisisel, gizli, saglik} ise `gizlilik = kamu` ya da `dis` olan havuz aday değil. Sıkı sınıflar (`saglik`, `gizli`) yalnız host sağlayıcıda (platform `host: true` ve imzası eşleşen) ve yerelde işlenir; başka sağlayıcı ancak `--dis-onay` ile (kullanıcının bu konuşmadaki açık onayı). Elle yol önerileri (`rotalar`) aynı süzgeçten geçer; `bilinmiyor` veride dış rota "yalnız genel veri" notuyla gösterilir.
5. **Kullanıcının açık isteği** önce gelir; yasak, taban ve gizlilik dışında her kuralı geçer. `--zorla` aday dışı bir hedefe giderse uyarı yazılır; Q altıysa onay istenir.
6. **Determinizm.** Aynı girdi aynı çıktıyı verir; `--json` tam kanıt dökümüdür.
7. **Ölçek kilidi.** `modeller.json` ile `siniflar.json` aynı `z_olcek` değerini taşımıyorsa seçici çalışmayı reddeder ("ölçek karışık: güncelle tam").
8. **Şef tavanı.** İşçi, şefin (liderin) model × eforunu aşmaz; Q tavanın üstündeyse daha zayıf modele düşülmez, SOR T6 sorulur. Yalnız kullanıcının açık isteği kaldırır (bölüm 12).

## 3. Akış

```
sec(istek, veri, kota, durum, saat) -> Secim

A. SINIFLANDIRMA
   is.sinif  = istek.sinif ?? rubrik(sinyaller)      # 0-1 sinyal basit, 2 normal, 3 zor, 4+ kritik; belirsiz -> bir üst
   is.Q      = siniflar.q[is.sinif]
   is.IB     = boyut ⊗ olc.P90(sinif, alan)          # ölçüm varsa düzeltilir
   is.veri   = istek.veri ?? kural.gizlilik.varsayilan_veri
   deterministik ön geçit işi çözüyorsa -> araç, model yok

B. SABİT KURALLAR
   kural.sabit_kurallar[is.alan] varsa -> o rol/efor/yol; uygun değilse (taban, rezerv, gizlilik) -> düşüş ELLE yolları
   proje .orkestra.json zorunlu[alan] varsa -> o hedef; efor yoksa Q'yu ve alan efor tabanını karşılayan EN UCUZ efor
   (en düşük efor değil); hedef aday dışıysa UYARI, Q altıysa onay

C. KALİTE TABANI
   K_req = kademe(is.Q) ; efor_kurallari[alt_alan][rol] = {taban, tavan}

D. ADAY KÜMESİ (her aktif platform, her rol, her efor)
   m = roller[rol].aktif                       # en son sürüm; CLI'a kesin kimlik gider
   ELE: yasak | durum ∉ {aktif, yedek} | kip eksik | gizlilik (sıkı sınıfta host dışı, --dis-onay yoksa)
        | Z_etkin < Q | efor alan tabanı altı ya da tavanı üstü (ultra kipinde tavan yok)
        | bağlam yetmez | düzenleme gerekli ve yazma_izinli_ajan = false | olgu işi ve olgu_isi = false
        | yetenek yok: alt alanın `gerekli_yetenek` listesindeki araç (ör. web: `web_arama`) platformun/erişimin
          `yetenekler` kaydında açıkça `false` (bilinmeyen elenmez; ölçüm iyi olsa da aracı olmayan yol boş döner)
        | aynı havuz ve alt alanda Pareto-baskın | max/ultra/ultracode (zorla ya da kritikte tek aday değilse)

E. KALİTE KÜMESİ (önce kalite)
   q(a) bütün adaylar için hesaplanır; ölçüm aranırken aynı ölçüt adı bütün alt alanlarda aranır
   Efor kaydırması (siniflar.efor_kaydirma): alan ölçümü aday eforunda değilse o efora taşınır, böylece modeller
          aynı eforda değil KENDİ eforlarında karşılaştırılır (üst eforda önde olan model düşük eforda geride kalabilir):
          1) kayıtta `eforlar[e]` varsa o değer (efor başına ölçüm her şeyin önünde)
          2) yoksa çapa = ölçümün yapıldığı efor (`efor`; `eforlar` varsa Z'ce en yakın ölçülü efor):
             q(e) = puan(e0) + (Z(e) - Z(e0)) x egim[ölçüt]   # egim: 1 Z'nin ölçüt birimindeki karşılığı
          3) `efor` boşsa ve ölçüt `bos_efor_ust` listesindeyse (kaynağın en üst ayarı ölçtüğü doğrulanmış) çapa
             modelin en yüksek Z'li eforu; listede değilse puan tüm eforlara aynen
          aşağı yön tam uygulanır; yukarı yön (ölçülmemiş üst efor) en çok +yukari_tavan_delta x δ; doymuş ölçütte
          ve egim = 0 ölçütte kaydırma yok
   Efor verimi (ultra dışında): xhigh ve üstü yalnız uzun otonom işte (sure_dk >= xhigh_kosul_dk ya da uzun_otonom
                sinyali), alt alan kuralı o eforu taban istiyorsa ya da modelin Q'yu karşılayan tek eforuysa kalır;
                verimli_tavan üstü efor, aynı modelin sınır altı eforu varsa ve ölçülmüş kazanç δ'yı aşmıyorsa ELE
   A_K = {a : Z(a) <= Q + ust_kademe_genisligi}  ; boşsa A_K = A ; ultra kipinde A_K = A
   hafif kipinde A_K = {a : Z(a) <= Q + fazla_zeka.pay} (tırmanma yok), işçi tavanı hafif_isci
   Ölçümsüz: alan ölçümü olmayan aday q = min(ölçülen q) - δ alır ve ölçülen aday varken E'ye girmez
   q*  = max q(a) ; δ = siniflar.delta[olcut(q*)] (ölçüm yoksa δ × alan_olcumu_yok_carpani)
   E   = {a : q(a) >= q* - δ}
   Köprü: alan ölçümü olmayan aday için siniflar.kopru[alt_alan] ölçütlerinin referans medyanı - 0.5δ; köprülü
          aday q* belirleyemez, Opus kapısında sayılmaz
   Doygunluk: mekanik/basit işte Z >= Q + siniflar.doygunluk[sinif] olan adayların q'su eşit sayılır (zekâ fazlası
          ölçülebilir kazanç vermez); doymuş ölçütte (doymus_yayilim) efor farkı puana kaydırılmaz
   Kanıt birikimi (birleşik): aile için z = Σ(d_i/δ_i)/√n >= secici.kanit_birikimi_z, her d_i >= 0 ve n >= 2
          bağımsız ölçüt (ikincil ölçüt kendi δ'sıyla); geçerse E o aileye daralır. Pareto kanıttan SONRA uygulanır
   Geri bildirim: durum.basari (dış doğrulamalı) Wilson alt sınırı en iyinin fark_esigi altına düşen model o
          sınıfta elenir; tekil_secim=false model yalnız sürü içinde (--suru)
   Opus kapısı (zor + geri_alinamaz/olgu_riski/alan_uzmanligi sinyali ya da --ciddi): Opus >= high; Opus olmayan
          aday yalnız doğrudan alan ölçümüyle en iyi Opus'un δ içindeyse (ölçüm yoksa Z_etkin >= Z(opus@high))
   UST = E tek aileye indiyse o aile (Claude dahil): kotaya bakılmadan o aile içinden seçilir

F. KAPASİTE (yalnız E içinde)
   c     = İB × g(a) × s_p × (belirsiz ? 2 : 1) + c_sabit   # g bilinmiyor/DY: bilinen en yüksek görev maliyeti
           c_sabit = cagri_sabit_yuk_token × fiyat.girdi / 1e6 (mikro toplu çağrıda ÷ sabit_yuk_paylasim);
           --tok-tahmin giris:cikis ya da brief (plan parçası, --brief) verilirse İB × g yerine token × fiyat;
           brief kaynaklı tahminde giriş = max(brief/3.5, boyut varsayılanı), çıkış = boyut varsayılanı ×
           g(efor)/g(medium) (secici.tok_tahmin_boyut) [T]; tek atımlık dış çağrı AA görev birimiyle şişirilmez
   K_p   = öncül; `ork plan` kalibrasyonu (kota-gecmis + olc maliyet_usd_e) öncülün 0.25-4 katıysa onun yerine
           (ana havuz lider ile ortak olduğundan kendiliğinden kalibre edilmez)
   her karar penceresi w:  k_w = EMA(k_w) ; k̂_w = kova(k_w) ; m_w = max(0, k̂_w - taban_w)
                           m_ham,w = max(0, min(k_okunan,w, k_w) - taban_w)   # hızlı düşüşte EMA tabanı delmez
                           pay_w > m_ham,w ise ELE (sığma, taban, lider payı temkinli ham değerle; kova/EMA yalnız ρ ve katman)
   etkin kalan kuralı:     bir havuzun etkin kalanı bütün pencerelerinin (5 saatlik, haftalık, günlük) en küçüğüdür (`min_w`);
                           her pencere ayrı denetlenir. Haftalık %0 iken 5 saatlik %100 görünse de havuz kullanılamaz (aday olmaz).
   x   = max(t/T, tempo_t_min) (kullanılmamış kayan pencere: 1; belirsiz: 0.5)
   R   = rezerv × a(t)   # azalan rezerv: ana havuz a = min(1, t_saat/rezerv_azalma_saat), dış havuz a = t/T
   ρ_p = (m - R) / ((1 - taban - R) × x)                                       # tempo oranı
   ρ_C = ρ_C,hafta (ρ_C,5s >= 1 ise) yoksa min(ρ_C,5s, ρ_C,hafta)
   ÖNDE(p) ⇔ o_p · ρ_p >= (1 ± tempo_bant) · ρ_C   (giriş +, çıkış −; durum.onde; belirsiz dış havuz asla ÖNDE)
   f   = clamp((t/T) / (m / (1 - taban)), f_sinir)                            # kullan ya da kaybet
   S   = (pay / m) × f
   seviye(a) = katman(a, ρ, u_C, UST, is)                                     # bölüm 6
   P   = S × ceza_fazla_zeka(a) × (1 + dk(a)/sure_cezasi_dk) × elle_ceza(a)
   Secim = argmin (seviye, havuz_sira, P, -q, dk, sabit_sira)   # havuz_sira = faz.dis_sira; bant ve histerezis
                                                                  # yalnız aynı (seviye, havuz_sira) içinde
   Histerezis: aynı (alan, alt_alan, sınıf) için önceki seçim hâlâ E'de ve aynı seviyedeyse,
               yeni aday ancak P_yeni < histerezis × P_eski ise geçer
   Eşitlik (P'ler esitlik_bandi içinde): yüksek q > düşük gecikme > farklı aile doğrulama ihtiyacı > sabit sıra
   Model başına tek varyant: aynı modelin eforları q bakımından ayni_model_efor_bandi içindeyse en ucuz efor

G. ÇIKTI
   E'nin hiçbir adayı sığmıyorsa bölüm 8 (D1, D2) ; yine yoksa BEKLE
   Secim(a, cagri, gerekce, yedekler = ilk 3 (E ∪ A_K), dogrulayici = dogrulayici_sec(a, is), kaskad, isci_tavan,
         dusus, parca_plani) ; elle öneri yalnız sığan adaylardan
   alt alanın ölçüt tanımında zorunlu_dis_kanit varsa ve --dogrulayici-var yoksa UYARI "DIŞ KANIT ZORUNLU"
   (onay değil: kanıt üretimden sonra gelir; lider kanıt olmadan teslim etmez)
```

- `ceza_fazla_zeka(a) = 1 + (tavan - 1) × clamp((Z(a) - Q - pay) / genislik, 0, 1)`: yalnız eşitlik bozucu, eleme yapmaz (`siniflar.json` `fazla_zeka`).
- `elle_ceza`: otomatik çağrı izni olmayan yol için `secici.elle_ceza`; işin tek yolu elle ise 1.
- Erişim yolu host'a bağlıdır: Codex liderken Claude işçisi yolu yoktur; agy liderken yalnız elle ve yerel yollar.

## 4. Gerçek iş maliyeti

- `g(a)` görev başı toplam maliyettir (girdi + önbellek + çıktı token'ı × liste fiyatı). Token fiyatı pahalı ama az token harcayan model böylece doğru fiyatlanır: eşit Z'de en token-verimli Claude kademesi beklenenden ucuz, en uzun yazan beklenenden pahalı görünür.
- Gerçek iş maliyeti endeksi (GIME) = `g(a) / g(referans)`; referans `siniflar.json` `gime_referans` varyantıdır. Yalnız insan okuması içindir; seçici `g` ile çalışır.
- Bir alt alanda aynı harness'tan görev başı maliyet varsa (ör. SRE, vergi, kod göçü) o alanın maliyeti onunla değişir. Farklı harness'lar aynı karşılaştırmada karıştırılmaz.
- "Dolar başına en ucuz" ile "kotaya en ucuz" ayrışır: `c` kotaya `K_p` ile çevrilir. Dolar başına ucuz bir model küçük bir havuzdaysa her iş havuzun büyük payını yer.

## 5. Küçük yüzde farkına dayanıklılık

| Mekanizma | Tanım | Neden |
|---|---|---|
| İş birimi payı | Ham yüzde değil `pay = c / K_p` karşılaştırılır | Büyük havuzda %1, küçük havuzdaki %1'in katlarıdır |
| Kova | `k̂ = ⌊k / kova_adim⌋ × kova_adim` | %50 ile %51 aynı kovaya düşer |
| EMA | Son okuma `ema_pencere_dk` içindeyse `k̂ = α k̂_yeni + (1 - α) k̂_eski` | Gecikmeli sayaçlar sıçramaz |
| Göreli bant | Dış havuz `o·ρ >= (1+b)·ρ_C` ile ÖNDE'ye girer, `< (1−b)·ρ_C` ile çıkar (`faz.tempo_bant`); durum `durum.json onde` | Eşik çevresinde salınım yok |
| Histerezis | Önceki seçim, yeni aday belirgin ucuz değilse korunur | Ardışık işlerde önbellek kaybı yok |
| Eşitlik bandı | P'ler bant içindeyse sabit eşitlik bozucular | Küçük sayısal fark karar vermez |
| Bilinmiyor ≠ %50 | Okunamayan havuz `belirsiz` + 2x maliyet | Okunamayan havuz öne geçmez |
| Pencere sınırı | Sıfırlamaya `pencere_sinir_dk`'dan az varsa sıfırlama sonrası değer varsayılmaz; pencereyi aşan iş iki pencereye ayrı yazılır | Erken iyimserlik yok |

## 6. Ana havuz fazı ve katmanlar

Ana havuz (`faz.ana_havuz`, tipik olarak Claude aboneliği) en büyük havuzdur ve en son bitmelidir; ama kalite önce gelir. Ana havuzun korunan payı tek kaynaktan gelir: `faz.claude_esik_u`; havuzun `rezervler` kaydında ayrı bir değer varsa yok sayılır.

`u_C = m_C,hafta / (1 - taban_C,hafta)`: ana havuzun taban üstü kullanılabilir payının kalan oranı. `u_C <= claude_esik_u` "son çeyrek" sayılır. Eşik kalan yüzdeye değil taban üstü paya uygulanır; aksi hâlde yüksek bir taban kuralı hiç tetiklemezdi (örnek: taban %30, eşik 0.25 ise kalan ≈ %47.5'te tetiklenir).

`seviye(a)` (küçük olan önce; aynı seviyede `faz.dis_sira`, sonra P):

| Seviye | Kim | Koşul |
|---|---|---|
| 0 | Bedava API, yerel | `veri = genel` (bedava için), sığıyor, soğumada değil |
| 1 | Claude dışı abonelik ÖNDE | göreli tempo (`o·ρ` ile `ρ_C`, bant), taban ve rezerv üstü |
| 2 | Claude dışı abonelik GERİDE | taban ve rezerv üstü (R3: Claude'dan önce) |
| 3 | Ana havuz (Claude) | `u_C > claude_esik_u` ve 5s'de `k_ham - pay >= taban + lider_tampon` |
| 3.5 | Claude dışı GERİDE, Claude kullan-ya-da-kaybet | `ρ_C >= faz.claude_kullan_kaybet_rho` (Claude fazlası sıfırlamada yanacak) |
| 4 | Kotası okunamayan havuz | dış önce (havuz sırası), ana havuz en son; NOT ile (üstün/kritik işte ana havuz → SOR T0) |
| 5 | Dış havuz kendi rezervinden | başka aday yoksa, NOT ile |
| 6 | Ana havuzun rezervi (eşit kalite işi) | otomatik değil → SOR T2 |
| ∞ | Tabana dokunan | asla |

- **Üstünlük (`UST`):** E tek aileye indiyse katman sırası o aile içinde uygulanır; üstün aile ana havuzsa rezerv de serbesttir (`kime: claude_ustun`). Kritik iş için rezerv serbesttir (`kime: kritik`).
- **Davranış:** Claude en son biter (R3). Eşit kalitedeki iş bedava → ÖNDE dış havuz → GERİDE dış havuz (taban üstü) → Claude sırasıyla gider; tempo yalnız dış havuzları kendi arasında sıralar. İstisna: Claude'un fazlası kendi temposunun `claude_kullan_kaybet_rho` katını aşıyorsa (sıfırlamaya az kalmışken bol kota) Claude GERİDE dış havuzun önüne geçer, çünkü o fazla zaten yanacaktır. Claude rezervi eşit kalite işine yalnız kullanıcı onayıyla (SOR T2) açılır; rota, ön işleme, proje ve sabit kural hedefleri de rezervi sorgusuz açamaz (yalnız kullanıcının `--zorla`'sı). Sıfırlamaya yaklaşan havuzda `t/T` küçülür, ρ büyür, `f` düşer: kullanılmayan kota boşa gitmez.
- **Kalite önce:** bir aile bandın dışında ya da ≥2 bağımsız ölçütte öndeyse ondan kaçılmaz. Lider aday yalnız elle yoldaysa seçim "ELLE ÖNERİ + en iyi otomatik alternatif" çiftidir.
- **Lider payı:** ana havuzun kısa penceresi `taban_5s + lider_tampon_5s` altına inince o havuzdan işçi açılmaz; lider ağır okuma/yazmayı da devreder.
- Faz yorumu [T]: "son %25 kalasıya kadar dış abonelik tercih" = ana havuzun taban üstü payının son çeyreği korunur; öncesinde eşit kalitedeki iş dışarıya, yalnız tempo izin verdikçe. Tersi isteniyorsa yalnız `faz.claude_esik_u` değişir.

## 7. Kaskad, yükseltme, doğrulayıcı

```
yurut(is, Secim):
  dış doğrulayıcı var VE p_yukselt(sinif, alan) < 1 - (c_ucuz + c_dogrulama) / c_guclu:
       başla = Q'yu karşılayan en düşük P'li aday (kaskad; Q altına asla)
  değilse: başla = Secim                                  # zor belliyse doğrudan güçlü
  sonuç = çalıştır(başla, brief)
  doğrulama sırası: dış kanıt > farklı aile + farklı kanıt/kip > farklı aile LLM > aynı aile farklı model
  çürütüldü -> yükselt (merdiven: efor değil model) ; en çok yukseltme_merdiveni.en_cok kez
  doğrulanamadı (kota, 429, zaman aşımı) -> etiketle; kabul edilmiş sayılmaz
  kabul edilenlerin kaskad.orneklem_orani kadarı (en az orneklem_en_az) bağımsız denetlenir
  best-of-N: N <= best_of_n_tavan, ardışık + erken durdurma, her denemede efor/aile/brief farkı
  oy: yalnız kapalı cevaplı, zor olmayan işte; ilk iki uyuşursa üçüncü yok; ayrışırsa üçüncü oy bir kademe güçlüden
  her çağrı -> olc kaydı
```

- Yükseltme merdiveni rol adlarıyla `siniflar.json` `yukseltme_merdiveni` içindedir. Zekâ yetmiyorsa efor değil model yükselir.
- `dogrulayici_sec(a, is)`: aynı algoritma, `tur = dogrulama`, ek eleme `aile(b) ≠ aile(a)`; mümkünse farklı kip ya da kanıt kaynağı (test, DOI sorgusu). Farklı aile yoksa (gizlilik, kota) aynı aileden farklı model seçilir ve `zayif_dogrulama` işaretlenir; o da yoksa "doğrulanamadı" yazılır. Doğrulayıcı da üreticinin gizlilik süzgecinden geçer.
- **Kanıtlı kaskad** (`siniflar.kanitli_kaskad`): arastirma/normal sınıfında, genel veride ve tam dış kanıt (`--dis-kanit test_tam|kapali_cevap|sema_dogrulayici`) varken Q'nun `z_acigi` altındaki ucuz aday ilk deneme olabilir; kabul edilen çıktı yine dış kanıttan ya da Q'yu karşılayan modelden geçer (en çok `en_cok_deneme`).
- Kaskad metriği kendi doğrulayıcısından okunmaz: ucuz doğrulayıcı ucuz modelin yanlışlarının önemli kısmını kabul eder [B].

## 8. Zarif düşüş

| Adım | Ne | Ne zaman |
|---|---|---|
| D1 | E'deki modelin daha düşük eforu (verim süzgecinden geçen, Pareto dışı) | Q ve alan efor tabanı korunuyor, sığıyor; en düşük katman, en iyi q |
| D2 | Q üstündeki başka model ya da havuz, E dışından | E sığmadı, D1 yok; `UST` varken uygulanmaz; yalnız `q >= q* - 2δ` (daha uzak aday otomatik seçilmez, SOR `dis_alt` seçeneği farkı δ biriminde gösterir); E'nin en iyi sığanı rezervdeyse yalnız katman ≤ 3 hedef |
| D3 | Kapsamı daralt, `durum: kismi` döndür | Parça bölünebiliyorsa |
| D4 | Checkpoint + `devir.json` | Uzun işte havuz biterken |
| SOR | Kullanıcıya tek soru (`durum=sor`, çıkış 4): T0 ana havuz kotası okunamadı ve üstün/kritik iş ona düşüyor; T1 Claude gerekli ama lider payı/5s/hafta tabanında; T2 yalnız Claude rezervi sığıyor (sağlık/gizli veride de: sessiz BEKLE yok); T3 sabit kural havuzu kapalı, sıfırlama kredisi var ve haftalık sıfırlamaya ≥ 48 sa; T4 agy kapısı kişisel bağlam kabulü bekliyor ve kalite kümesinde sığan agy adayı varken seçim Claude'a (ya da hiçbir yere) düşüyor; T5 tetik yok, açılış > `bekle_esik_dk` ve daha zayıf bir sığan aday var; T6 Q (ya da Opus kapısı) şef tavanının üstünde (seçenekler `tavan_yok`, `sef_yukselt`, `bekle`; varsayılan bekle); T7 önce-sor hattındaki model açık önde ve sığıyor (seçenekler `once_sor_kabul` = `--zorla rol:efor`, `once_sor_ret` = otomatik seçimle devam; varsayılan ret). Onay gerektiren zorunlu hedef (Q altı) de çıkış 4 ve planda gönderilmez. Yanıt `--sor-yanit`; T4 yanıtı (`agy_kabul`/`agy_ret`) `durum.sor_kararlari`'nda oturum boyunca (5 sa) saklanır | Aday kalmadı ya da Claude varsayılan olacaktı |
| D5 | BEKLE (en erken açılış; karar gerektirmez, çıkış 5) | Açılış ≤ `bekle_esik_dk` ya da tetik ve alternatif yok |
| ELLE | Yalnız elle yolu olan iş: hazır komut satırı + en iyi otomatik alternatif | Kullanıcı yoksa otomatik alternatif yürür, elle öneri rapora yazılır |

429 ve kota hatası sarmalanıp yeniden denenmez (CLI'lar zaten dener). Çıkış sınıflanır (`gecici | kapasite | kota | kalici | bilinmiyor`), `durum.json`'a soğuma yazılır, havuz ya da model değişir.

## 9. Gerekçe satırı ve ölçüm kaydı

Her seçim tek satır gerekçe üretir (`--json` tam döküm). Biçim:

```
SEÇİM <rol>@<efor> (<yol>) · <alan>/<alt_alan> · Q<n>-><kademe> · E={...} δ=<n> (<ölçüt>) ·
faz u_C=<n> · <havuz> ρ=<n> katman<n> · c=<n> USD-e, pay %<n> · ELENEN <aday> (<neden>), ... · doğrulayıcı: <...>
```

`~/.orkestra/olc.jsonl` kaydı her çağrıdan sonra zorunludur ve kendiliğinden yazılmaz: lider `ork olc kaydet` çalıştırır (`ork bedava` kendi kaydını yazar; `ork olc ozet` boşsa adım atlanıyordur) (şema `data/sema/olc-kayit.schema.json`): zaman, iş/parça kimliği, sınıf, alan, model, efor, havuz, aile, brief önek hash'leri, giriş/çıkış/düşünme/önbellek token'ı, süre, durum, hata sınıfı, yükseltme, doğrulayıcı, kota farkı. Çağrı satırı sonuç dönünce `ork olc kaydet` adımını içerir; Claude alt ajanında lider Agent sonucunun kullanım alanlarını iletir.

Kalibrasyon: ana havuz lider ile ortak olduğundan `K_p` çağrı başına değil oturum düzeyinde güncellenir: iki kota okuması arasındaki Δk ile aynı aralıktaki `pay` toplamı oranlanır; `olc.kalibrasyon_esigi_pp` birikince EMA (`kalibrasyon_ema_alfa`). Başarı/başarısızlık (dış doğrulayıcıdan) model × sınıf başına geri bildirim olarak tutulur.

## 10. Örnek çözüm (sentetik değerlerle)

İş: kod/gunluk, Q kod, boyut orta, veri genel, testli. Okuma: ana havuz haftalık kalan 0.61, dış abonelik haftalık kalan 0.70, sıfırlamaya 4 gün.

1. A_K: Q'yu geçen Opus medium, Sonnet high, Sol high, Sol medium; Haiku elenir (Z < Q). Terra high aynı havuzda Sol medium'a Pareto-baskın: elenir.
2. Ölçüt doymuş (kod/gunluk), δ = doymuş yayılım: dört aday da E içinde; tek aile üstünlüğü yok.
3. `u_C = (0.60 - 0.30) / 0.70 ≈ 0.43 > 0.25` (kova 0.60): ana havuz katman 3 adayı.
4. Dış abonelik: `m = 0.70 - 0.30 = 0.40`, `t/T = 4/7 ≈ 0.57`, ρ ≈ 0.40 / (0.70 × 0.57) ≈ 1.0 >= rho_gir: tercihli, katman 1.
5. Seçim: katman 1'deki en düşük P (Sol medium ile Sol high q bakımından bant içindeyse en ucuz efor). Doğrulayıcı: test + farklı aile.

Aynı iş, dış havuz tempo gerisinde (GERİDE) ise: dış havuz katman 2, ana havuz katman 3: yine dış havuz (taban üstünde kaldıkça); yalnız Claude kullan-ya-da-kaybet durumundaysa (ρ_C ≥ 1.5) dış havuz 3.5'e iner. Ana havuz bandın dışında önde olsaydı (ör. yazım/rapor) kotaya bakılmadan ana havuz seçilirdi.

## 11. Hafta planı ve uyarlanır ağırlık

`ork plan` model çağırmaz: havuz başına kalan, taban, R(t), sıfırlamaya gün, hedef/gün = (m − R)/t_gün, ρ, o·ρ ve ÖNDE/GERİDE (seçiciyle aynı histerezisli karar) ya da ELLE (agy kapısı kapalı: otomatik sırada yok); bugünkü sıra bedava → ÖNDE → GERİDE (dis_sira) → ana (Claude kullan-ya-da-kaybet ise ana GERİDE'nin önünde). `faz.uyarlanir_agirlik` açıksa günde bir (son kayıt 24 sa içindeyse yeni değer yok; taban kayıtlı `o`, yoksa statik): son 3 günün harcama hızıyla öngörülen artık `> %10·U` ise `o ← min(ust, o·adim)`, öngörülen tükenme sıfırlamadan bir günden fazla önceyse `o ← max(alt, o/adim)`; kayıt bir hafta geçerlidir. Kalibrasyon: `kota-gecmis.jsonl` gerçek okuma çiftleri (tahmin/soğuma/bayat önbellek yazılmaz, 14 gün saklanır) ile aynı aralığın `olc` `maliyet_usd_e` toplamı oranlanır; `ork plan` `durum.kapasite_kalibre`'ye yazar.

## 12. Şef tavanı (R16)

Kullanıcının şef (lider) olarak seçtiği model ve efor işçilerin tavanıdır. Seçici tavanı aday üretiminde uygular (`secici.tavan_ihlal`); aynı kural `ork rol`, `ork sec --plan` parçaları, doğrulayıcı/hakem seçimi ve koşucunun açık hedefleri, kardeşleri, oy adayları ve yargıcı (`suru.hedef_denetle`) için de geçerlidir.

| Durum | Kural | Örnek (şef) |
|---|---|---|
| Aynı aile, aynı model | efor ≤ şef eforu | Opus high: Opus en çok high (xhigh/max yok) |
| Aynı aile, başka model | model düzeyi (şef eforundaki Z) ≤ Z(şef), bant yok; efor ≤ şef eforu | Sonnet high: Opus hiçbir eforda yok; Haiku en çok high |
| Başka aile/platform | Z(a) ≤ Z(şef) + bant (bant = `delta.aa_z`, gürültü içinde eşit sayılır) | Hydrogen high (51): Sol xhigh (52) geçer, Opus xhigh (57) geçmez |
| Alan ölçümü | şefin aynı ölçütte ölçümü varsa başka aile adayı onu δ'dan fazla aşamaz | Opus high şefken SRE'de Sol elenir |
| Opus kapısı (ciddi zor iş) | tavanın altında kalır: kapıyı karşılayan Opus yalnız tavan üstündeyse SOR T6 (tavan altında Q'yu karşılayan kapı Opus'u pencere/ölçüm/Pareto süzgecinde düştüyse T6 değil, normal akış) | Opus medium şef + ciddi zor iş: SOR |

- **Q tavanın üstünde:** tavana uyan aday kalmazsa (ya da kalite kümesinin tamamı alanda şefin üstündeyse) `durum=sor`, `tetik=T6`; daha zayıf modele sessizce düşülmez. Seçenekler: `tavan_yok` (bu iş için aş, uyarıyla), `sef_yukselt` (lider oturum modelini/eforunu yükseltir, `--sef` ile yeniden seçer), `bekle`.
- **Kaldıranlar (5; çıktıya `UYARI şef tavanı aşıldı` düşer):** `--tavan-yok`, `--zorla`, ultra kipi (açık istek), SOR yanıtı `tavan_yok`, sabit kullanıcı kuralı (ör. görsel üretim kuralı). Proje kuralı ve rota hedefleri tavanı kaldırmaz.
- **Plan ve sürü (`secici.parca_tavani`):** tavanı yalnız kullanıcı kaldırır: CLI `--tavan-yok` ya da plan düzeyi `tavan_yok`. Parça/öğe düzeyindeki `tavan_yok` ve `sor_yanit: tavan_yok` yok sayılır (`UYARI`); parçadaki `zorla`/ultra lider yazımıdır, tavanı kaldırmaz (ihlalde SOR T6). Parça `sef`'i yalnız plan şefinden sıkıysa geçer. Plan şefi: açık `--sef` plan değerini ezer (T6 `sef_yukselt` yolu); verilmezse plan değeri ile oturum/algılama şefinin sıkı olanı. Parça uyarıları plan çıktısına (`<id>: UYARI ...`, JSON `parcalar[].uyarilar`) düşer.
- **Koşucu (`suru._tavan`) fail-open değildir:** şef varken kayıtsız model ya da Z'siz hedef `engel` olur; çözülemeyen plan şefi tüm planı durdurur; Claude işçisi hedefi de denetlenir; plan düzeyi `tavan_yok` ile geçen ihlal `UYARI` notu bırakır.
- **Şefin belirlenmesi (`ork.py`, `araclar.sef_belirle`):** `--sef rol:efor` (kesin kimlikle oturuma kaydedilir: `durum.sef`, `sef_tavani.oturum_saat` ve oturum kimliğiyle; efor verilmezse önce algılanan efor) > bu oturumdaki kayıt (oturum kimliği eşit olmalı; taze açık ortam sinyali `ORKESTRA_SEF`/model değişkeni daha düşükse o) > otomatik algılama (`sef_tavani.ortam_sef`, `ortam_model`, `ortam_efor`; ayar dosyalarında `model` / `effortLevel`; `model_takma`: `opusplan` -> yürütme modeli Sonnet) > `faz.lider_rol` (o da yoksa host platformun en üst seçilebilir modeli) ve modelin varsayılan eforu (uyarılı). Kaynak alan başına yazılır (`model faz.lider_rol (varsayım) · efor CLAUDE_EFFORT`). Kayıtta olmayan model adı (ör. eski sürüm) en yakın rolün etkin sürümüne eşlenir ve her seçimde `UYARI şef modeli kayıtta yok` basılır. `CLAUDE_EFFORT` çağıran sürecin eforudur: ork bir alt ajandan çağrılıyorsa lider `--sef` vermelidir. Saf seçici `sef` verilmezse tavan uygulamaz (kütüphane ve test kullanımı).
- Parametreler `data/siniflar.json` `sef_tavani` bloğundadır; kodda model adı yoktur.

## 13. Uygulama dili: Python mu Rust mu

**Karar (2026-11-16): seçici, kota okuyucu ve güncelleme yardımcısı Python'da (yalnız standart kitaplık) kalır; Rust'a taşınmaz.** Yarar çok küçük, maliyet büyük. Ölçüm [Y]: önbellekli `ork sec` uçtan uca ≈ 0,33 s (boş yorumlayıcı ≈ 0,05 s); seçici hesabı bir saniyenin çok altındadır. Süreyi belirleyen şeyler soğuk kota okuması (Codex app-server ilk çağrıda ≈ 6 s) ve işçi çağrısıdır (saniyeden dakikalara); ikisi de G/Ç'dir ve Rust'ta da aynı sürer. Rust en iyi durumda çağrı başına birkaç yüz ms kazandırır, bu hiçbir iş akışında hissedilmez. Karşılığında ≈ 12 bin satır betiğin ve 14 test dosyasının yeniden yazılıp doğrulanması gerekir; seçici ince bir davranış kayması riski taşır (eşik, yuvarlama, histerezis). Dağıtım da ağırlaşır: skill metin ve betikten oluşur, Python her ortamda hazırdır ve `ork güncelle` ile yapay zekânın okuyup yama yapabildiği tek dosya olarak denetlenebilir; Rust ikilisi platform başına derleme (araç zinciri ya da önceden derlenmiş ikili, imza ve güvenlik uyarıları) ister ve bu okunabilirliği keser.

**Rust nerede yarar sağlar:** hızı, kararlılığı ve kaynak tüketimi önemli, sürekli çalışan katmanda: kota ve ajan olay okuyucusu (Cetvel). Orkestra bu katmanın verisini §8 sözleşmesiyle (`platform-notlari.md`, `orkestra-uyum.json`) otomatik okur; Rust yararı orkestra taşınmadan alınır, Cetvel yoksa orkestra aynı kotayı kendi okuyucusuyla okur. **Yeniden değerlendirme ölçütleri** (biri ölçülürse): önbellekli tek çağrı > ≈ 1 s ya da toplu `suru` yürütmesinde seçici darboğaz olur; tek ikili olarak dağıtım gereği doğar; Cetvel çekirdeği seçiciyi kütüphane olarak barındırmak ister (seçici saf fonksiyon ve JSON veriden ibaret olduğu için taşınabilir, ama ayrı tasarım ve eşdeğerlik testi gerekir). Ölçüm olmadan dönüşüm yapılmaz.
