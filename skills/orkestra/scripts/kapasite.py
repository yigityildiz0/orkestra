#!/usr/bin/env python3
"""Orkestra model seçici (v5): zeka yeterliliği × gerçek kalan iş × tempo × harcanabilirlik × gecikme.

Karar sırası
0. Kullanıcının açık isteği (--zorla) ve projenin `.orkestra.json` kuralı (zorunlu/yasak/ağırlık/gizli/yasak_havuz)
   önce gelir; yasak model (Fable, Astra) hiçbir yoldan seçilmez. Kural yoksa kılavuz karar verir.
1. Zeka: her (model, efor) varyantının zeka puanı Z (AA Intelligence Index v5.0.1). İş sınıfı Q ister.
   Z < Q olan varyant elenir (kritikte Z ≥ Q+1). Başarı olasılığı p = 1/(1+e^-((Z-Q+2)/2)); beklenen
   maliyet = iş/p; zor ve kritik işte başarısızlığın bedeli ayrıca eklenir (tekrar deneme ucuz değil).
   Gereğin 10 puan üstü fazla-zeka cezası alır, 20 puan üstü yalnız başka aday yoksa seçilir:
   Haiku'nun işi Sol'a, Sonnet'e gitmez. AA kanıtı olmayan tahmini Z (z_kaynak "tahmin") Q ≥ 38 işte hiç
   kullanılmaz, altında 2 puan güvenlik payı ister. Ucuz/bedava havuz bu eşiği hiçbir yoldan delmez.
2. Kalan iş: 1 iş birimi (İB, ~40-60K token'lık orta iş) her (model, pencere) için o pencerenin şu
   yüzdesini yer (oran). Max 5x'te %5 ≠ Plus'ta %5. Oranlar tahmin; `olc` ölçüp düzeltir.
3. Kıtlık, ücretli havuz: iş / (işten sonra tabana kadar kalan) × √(1/tempo). Tempo = tabana kadar kalan pay /
   pencerenin kalan süre payı. Kalan kota kalan süreye göre BOLSA (harcama yavaş gitmiş) tempo > 1: kapasite ucuz
   (kullan ya da kaybet). Kalan kota kalan süreye göre AZSA (harcama hızlı gitmiş) tempo < 1: pahalı.
   Harcanabilir/bedava havuz (agy, taban 0; platformlar.json'daki bedava platform): kıtlık DÜZ = iş/100 × pencere
   saati/168 (günlük pencere haftada 7 kez yenilenir, %1'i haftalığın %1'inin 1/7'si değerinde). Havuz iş
   sığmayana kadar aynı ucuzlukta kalır (%40'ta da %3'te de ilk sırada), sığmayınca elenir: "kota bitti".
   Reseti geçmiş veri yenilenmiş sayılır.
4. Pencereler: 5s, gun, hafta. Codex ve Antigravity'de karar HAFTALIĞA, günlük kotalı platformda GÜNLÜĞE göre
   verilir; 5 saatlik yalnız gösterilir ve iş sığmıyorsa (%25 payla) o havuz elenir. Claude'da 5 saatlik de puana
   girer. Tabanlar: Codex haftalık %30, Claude haftalık %30 ve 5 saatlik %15 lider payı (hiçbir modda delinmez),
   Antigravity 0 (sıfıra kadar; kullanıcı kuralı 2026-11-08). agy'de haftalık bitince 5 saatlik işlemez (resmi).
5. Harcanabilirlik (kullanıcı kuralı, 2026-11-08): önce bedava platform (varsa), sonra Antigravity, sonra
   ChatGPT/Codex, en son Claude. Ağırlık agy 0.15 (üç havuz), Codex 0.9, Claude 2.5 (haftalığı azaldıkça,
   kalan süreyle orantılı artar). Aynı Claude modeli önce agy'nin kendi Claude havuzundan kullanılır.
6. Gizlilik: `gizlilik: kamu` olan havuz yalnız `--veri genel` işte aday (varsayılan bilinmiyor = elenir).
7. Gecikme: modelin dk_ib değeri varsa dk = iş × dk_ib × efor + bekleme; `--sure-dk` aşılırsa elenir, değilse
   puan × (1 + dk/120). Aynı modelin eforları puanca %10 içindeyse en ucuz (en hızlı) efor seçilir.
8. Sürü (`--yontem kapali|test|kapsam|acik`): doğrulayıcılı işte N paralel çağrı etkin Z'yi sınırlı artırır:
   ΔZ = k·s·v·min(T, a·log2 N), s = clamp((Z-(Q-8))/5, 0, 1), k ≤ 1 (kalite kaydından, yalnız aşağı).
   zor/kritik/görsel/video'da ΔZ = 0. Hakem/birleştirici bedava olmayan havuzdan, Z ≥ Q, seçici kurallarıyla.
9. EVREN soğuma (stratejik geri dönüş): evren_suru 429/503 gördüğünde ~/.orkestra/evren_durum.json "soguma" alanına
   model başına (ya da "*" tüm EVREN) busy_until yazar. Seçici bunu okur: soğuyan model/havuz bu süre boyunca aday
   dışı (neden "EVREN soğuma: 14 dk kaldı"); kardeş EVREN modeli varsa o, yoksa sıradaki havuz (eşik AYNEN: Z ≥ Q).
   Süre dolunca kayıt "yoklama": EVREN aday döner, ilk çağrı ping ile yoklar. İş acil değilse ve soğuma ≤30 dk ise
   BEKLE seçeneği; `--parca` ile parçalı işte KISMİ GEÇİŞ (yarısı şimdi başka havuza, yarısı EVREN'e / EVREN dönünce).
10. Rol (`--rol nobetci|kontrolcu|hakem|haberci|arsivci|muhalif`): diğer ajanları izleyen/denetleyen ucuz ve hızlı
   yardımcı. Eşik rol bazlı: Z ≥ max(rol tabanı, işin Q'su − rol farkı); üretenden (--dogrulayici) FARKLI aile; hakem ve
   muhalif bedava havuzdan seçilmez; hızlı modeller (Haiku, Luna, Flash, EVREN) öne geçer.
İşçi sayısı: SABİT TAVAN YOK (otomatik mod). Bağımsız parça sayısı (--parca), her havuzun tabana kadar kalan işi
ve platform eşzamanlılığı (esz / paralel_ajan) belirler; kullanıcı açıkça hafif/ultra derse o modun tavanı uygulanır.

puan = (w5·kıtlık_5s + kıtlık_gun + kıtlık_hafta) × havuz ağırlığı × fazla-zeka × hata bedeli × gecikme  (düşük = iyi)

Komutlar (yalnız lider, orkestrasyon başında; model çağırmaz, limit harcamaz):
  python -I kapasite.py --sinif kod --is 2 --claude-5s 45 --claude-hafta 92 \
      --claude-5s-reset 2026-11-08T12:10Z --claude-hafta-reset 2026-11-15T07:00Z --proje <cwd> [--parca 6]
  python -I kapasite.py --sinif basit --veri genel --is 0.5 --parca 40   # bedava platform açık, 40 bağımsız parça
  python -I kapasite.py durum                         # havuzlar, kalan İB, agy model listesi
  python -I kapasite.py neden --model sonnet:high --sinif zor   # bir varyantın puan dökümü
  python -I kapasite.py kontrol                       # kurallar sahte senaryolarla sınanır (FAIL -> çıkış 1)
  python -I kapasite.py --sinif zor --dogrulayici gpt-6.1-sol   # farklı aileden doğrulayıcı
  python -I kapasite.py --senaryo test.json           # sahte kota ile dene (_simdi anahtarı alır)
  python -I kapasite.py olc baslat | olc bitir --model gpt-6.1-terra --efor medium --is 1
  python -I kapasite.py kalite kaydet --model evren-glm-5.3 --efor low --yontem kapali --sinif basit --kabul 1
  python -I kapasite.py --rol nobetci --sinif kod --dogrulayici sonnet   # izleyici/denetçi alt ajan
"""
import argparse
import importlib.util
import json
import math
import os
import sys
import time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_DIR = os.environ.get("ORKESTRA_DIR") or os.path.expanduser(os.path.join("~", ".orkestra"))
OLCUM = os.path.join(STATE_DIR, "kapasite_olcum.json")
BASLANGIC = os.path.join(STATE_DIR, "olcum_baslangic.json")
KALITE = os.path.join(STATE_DIR, "kalite_kayit.jsonl")
HAM_ONBELLEK = os.path.join(os.environ.get("TEMP") or os.environ.get("TMPDIR") or ".", "orkestra_kapasite_ham.json")
TTL = 600
WIN_HOURS = {"5s": 5, "gun": 24, "hafta": 168}
PENCERELER = ("5s", "gun", "hafta")
PENCERE_AD = {"5s": "5s", "gun": "günlük", "hafta": "haftalık"}
PAY_5S = 1.25        # 5 saatlik sığma kontrolünde tahmin payı
TAMPON = 0.9         # toplu dağıtımda ücretli havuzun tabana kadar kalanının en çok %90'ı planlanır
VERI = ("genel", "kisisel", "gizli", "saglik", "bilinmiyor")
Z_KAYNAK = ("aa", "aa-indirimli", "tahmin")
TAHMIN_PAY = 2       # tahmini Z'li varyant eşiği bu kadar aşmalı
# platformlar.json ile eklenen havuzun eksik alan varsayılanları (SKILL.md ve INSTALL.md'de yazılı):
# karar penceresinde taban %10 (bedava/harcanabilir havuzda 0), 5s'te 0, ağırlık 1.0, w5 0.
YENI_HAVUZ = {"taban": {"5s": 0, "gun": 10, "hafta": 10}, "agirlik": 1.0, "w5": 0.0}
BEDAVA_VARSAYIM, UCRETLI_VARSAYIM = 80.0, 50.0

HAVUZ = {
    "claude":     {"taban": {"5s": 15, "hafta": 30}, "agirlik": 2.5, "w5": 1.0, "ad": "Claude Max"},
    "codex":      {"taban": {"5s": 0, "hafta": 30},  "agirlik": 0.9, "w5": 0.0, "ad": "ChatGPT/Codex"},
    # agy: ilk gözden çıkarılacak havuz, taban 0 (kullanıcı kuralı 2026-11-08), kıtlık düz. Üçü aynı ağırlıkta.
    "agy_gemini": {"taban": {"5s": 0, "hafta": 0},   "agirlik": 0.15, "w5": 0.0, "ad": "agy Gemini", "harcanabilir": True},
    "agy_argon":  {"taban": {"5s": 0, "hafta": 0},   "agirlik": 0.15, "w5": 0.0, "ad": "agy Argon", "harcanabilir": True},
    "agy_tp":     {"taban": {"5s": 0, "hafta": 0},   "agirlik": 0.15, "w5": 0.0, "ad": "agy Claude/GPT", "harcanabilir": True},
}

# Model: havuz, aile, medium eforda 1 İB oranı (pencere %'si), efor -> Z, çağrı.
# Z: Artificial Analysis Intelligence Index v5.0.1, efor başına (okuma 2026-11-08; /orkestra güncelle yeniler).
#   Opus low 35, medium 48, high 52, xhigh 57, max 59 | Sonnet low 26, medium 31, high 42, xhigh 50, max 55
#   Haiku low 19, medium 25, high 30, xhigh 35 (max 36: +1 puan 1.75 kat maliyet, alınmadı)
#   Sol low 35, medium 46, high 50, xhigh 52, max 55 | Terra low 29, medium 38, high 42, xhigh 45, max 51
#   Luna low 10, medium 18, high 21, xhigh 23 (max 28: Terra low daha ucuz ve akıllı, alınmadı) | Argon high 50
#   Flash low 23, medium 30, high 31. agy içindeki Claude = aynı model, ayrı havuz (agy'de yalnız low/medium/high).
#   Ölçülmeyen, seçiciye konmayan: Argon low/medium (agy'de var, AA puanı yok), gpt-oss-120b (AA v5'te puan yok,
#   18 Kasım'da kalkıyor). Z'siz varyant Q eşiğini ölçemez, o yüzden seçilmez.
# Oranlar: Codex Plus resmi 5 saatlik mesaj aralıklarıyla oranlı (Sol 15-160, Terra 35-285, Luna 350-3000:
#   Terra ≈ Sol/2, Luna ≈ Sol/20). Claude içi oran AA görev başı maliyetiyle oranlı (medium: Opus $2.45,
#   Sonnet $0.78, Haiku $0.09; Haiku 100K üstü istemde 5 kat pahalı, pay bırakıldı). agy oranları TAHMİN
#   (o_kaynak "tahmin"; resmi çarpan yok, kota "ajanın iş yükü" ile ölçülür). Hepsi öncül; `olc` düzeltir.
# dk_ib: 1 İB'nin medium eforda dakika tahmini (gecikme ve agy zaman aşımı için; efor çarpanıyla çarpılır;
#   Argon AA görev başı high'da 27.5 dk → medium eşdeğeri 28/1.5).
# Efor çarpanı (ec, medium=1): AA toplam endeks maliyeti oranı, model başına (2026-11-08 hesap). Kotanın dolar
#   maliyetiyle orantılı olduğu varsayımdır. ec'si olmayan model/efor genel EFOR_CARPAN'ı kullanır.
EFOR_CARPAN = {"low": 0.5, "medium": 1.0, "high": 1.5, "xhigh": 2.3, "max": 4.5}
EC_OPUS = {"low": 0.48, "medium": 1.0, "high": 1.34, "xhigh": 2.35, "max": 4.39}
EC_SONNET = {"low": 0.73, "medium": 1.0, "high": 1.87, "xhigh": 4.27, "max": 11.75}


def agy_cagri(ad):
    """agy çağrısı. {mode}: salt okunur iş plan, dosya düzenleyen iş (--duzenle) accept-edits.
    {sure}: işin büyüklüğüne göre zaman aşımı (3 × tahmini süre, en az 15 dk); dk bilinmiyorsa 0 = bitene kadar."""
    return 'agy -p "<brief>" --model ' + ad + ' --mode {mode} --output-format json --print-timeout {sure}'


MODEL = {
    "claude-opus":   dict(h="claude", aile="claude", o={"5s": 5.0, "hafta": 0.65}, ec=EC_OPUS,
                          z={"medium": 48, "high": 52, "xhigh": 57, "max": 59}, cagri="Agent model=opus effort={e}"),
    "claude-sonnet": dict(h="claude", aile="claude", o={"5s": 1.7, "hafta": 0.22}, ec=EC_SONNET,
                          z={"high": 42, "xhigh": 50, "max": 55}, cagri="Agent model=sonnet effort={e}"),
    "claude-haiku":  dict(h="claude", aile="claude", o={"5s": 0.3, "hafta": 0.04},
                          ec={"low": 0.55, "medium": 1.0, "high": 1.66, "xhigh": 2.64},
                          z={"low": 19, "medium": 25, "high": 30, "xhigh": 35}, cagri="Agent model=haiku effort={e}"),
    "gpt-6.1-sol":   dict(h="codex", aile="gpt", o={"5s": 7.0, "hafta": 1.2},
                          ec={"low": 0.61, "medium": 1.0, "high": 1.47, "xhigh": 1.85, "max": 2.89},
                          z={"low": 35, "medium": 46, "high": 50, "xhigh": 52, "max": 55},
                          cagri="codex exec -m gpt-6.1-sol -c model_reasoning_effort={e}"),
    "gpt-6.1-terra": dict(h="codex", aile="gpt", o={"5s": 3.5, "hafta": 0.6},
                          ec={"low": 0.58, "medium": 1.0, "high": 1.41, "xhigh": 2.11, "max": 5.12},
                          z={"low": 29, "medium": 38, "high": 42, "xhigh": 45, "max": 51},
                          cagri="codex exec -m gpt-6.1-terra -c model_reasoning_effort={e}"),
    "gpt-6-luna":    dict(h="codex", aile="gpt", o={"5s": 0.35, "hafta": 0.06},
                          ec={"low": 0.23, "medium": 1.0, "high": 1.58, "xhigh": 2.15},
                          z={"low": 10, "medium": 18, "high": 21, "xhigh": 23},
                          cagri="codex exec -m gpt-6-luna -c model_reasoning_effort={e}"),
    # dk_ib medium eşdeğeri (tahmini_dk efor çarpanıyla çarpar): AA'nın high'da ölçtüğü 28 dk / 1.5
    "gemini-4-argon": dict(h="agy_argon", aile="gemini", o={"hafta": 3.3}, o_kaynak="tahmin", dk_ib=28 / 1.5,
                           z={"high": 50}, cagri=agy_cagri("gemini-4-argon-{e}")),
    "gemini-3.8-flash": dict(h="agy_gemini", aile="gemini", o={"5s": 4.5, "hafta": 0.75}, o_kaynak="tahmin", dk_ib=6,
                             ec={"low": 0.5, "medium": 1.0, "high": 1.27},
                             z={"low": 23, "medium": 30, "high": 31}, cagri=agy_cagri("gemini-3.8-flash-{e}")),
    "agy-claude-opus-5-5":   dict(h="agy_tp", aile="claude", o={"5s": 29.5, "hafta": 5.0}, o_kaynak="tahmin", dk_ib=12,
                                  ec=EC_OPUS, z={"low": 35, "medium": 48, "high": 52},
                                  cagri=agy_cagri("claude-opus-5-5-{e}")),
    "agy-claude-sonnet-5-5": dict(h="agy_tp", aile="claude", o={"5s": 10.0, "hafta": 1.7}, o_kaynak="tahmin", dk_ib=10,
                                  ec=EC_SONNET, z={"low": 26, "medium": 31, "high": 42},
                                  cagri=agy_cagri("claude-sonnet-5-5-{e}")),
}


def efor_carpan(m, e):
    """Model başına efor çarpanı (ec); yoksa genel EFOR_CARPAN."""
    return (MODEL.get(m, {}).get("ec") or {}).get(e, EFOR_CARPAN[e])


# agy'de modelin adı (efor eki ile); `agy models` listesinde yoksa o varyant seçilmez
AGY_AD = {"gemini-4-argon": "gemini-4-argon-{e}", "gemini-3.8-flash": "gemini-3.8-flash-{e}",
          "agy-claude-opus-5-5": "claude-opus-5-5-{e}", "agy-claude-sonnet-5-5": "claude-sonnet-5-5-{e}"}
TAKMA = {"opus": "claude-opus", "sonnet": "claude-sonnet", "haiku": "claude-haiku", "sol": "gpt-6.1-sol",
         "terra": "gpt-6.1-terra", "luna": "gpt-6-luna", "argon": "gemini-4-argon", "flash": "gemini-3.8-flash",
         "agy-opus": "agy-claude-opus-5-5", "agy-sonnet": "agy-claude-sonnet-5-5"}

# Q aynı ölçekte (AA v5.0.1). Q yükseldikçe yalnız yüksek eforlu/güçlü varyant kalır.
SINIF = {
    "mekanik":   dict(q=16, aciklama="dosya düzeni, dönüştürme, kalıp arama; çıktısı kontrol edilebilir"),
    "basit":     dict(q=22, aciklama="özet, veri temizleme, net brief'li küçük düzenleme"),
    "arastirma": dict(q=38, aciklama="kaynak okuma, karşılaştırma (URL şart); olgusal doğruluk için Argon/Terra iyi"),
    "normal":    dict(q=41, aciklama="normal kodlama, backend, tek modül"),
    "kod":       dict(q=45, aciklama="çok dosyalı kod, ajan/terminal işi"),
    "zor":       dict(q=50, hata=3, aciklama="belirsiz hata, mimari, algoritma"),
    "kritik":    dict(q=55, hata=8, sert=True, aciklama="geri alınamaz/yüksek riskli karar, nihai doğrulama"),
    "gorsel":    dict(q=0, adaylar=["gpt-6.1-sol"], efor=["high"], carpan=4,
                      aciklama="görsel üret/düzenle: Codex image_gen (GPT Image, AA ve LMArena'da lider)"),
    "gorsel-anlama": dict(q=41, adaylar=["gemini-4-argon", "agy-claude-opus-5-5", "claude-opus",
                                         "gpt-6.1-sol", "gpt-6.1-terra"], aciklama="görsel/ekran anlama"),
    "video-anlama": dict(q=0, adaylar=[], yapilamaz="Claude ve GPT video almaz; agy -p video dosyası almaz (yalnız "
                         "etkileşimli agy'de sürükle-bırak). Otomatik yol: ffmpeg ile kare + Whisper ile ses, sonra "
                         "gorsel-anlama ve basit sınıfı.", aciklama="video izleme/anlama"),
    "video-uret": dict(q=0, adaylar=[], yapilamaz="Hiçbir CLI video üretmez. El ile: Gemini uygulaması/Flow (Omni Flash, "
                       "AI Pro kotası). Codex ve Claude yapamaz.", aciklama="video üretimi"),
}
YASAK = {"gpt-6-astra", "fable", "claude-fable"}

# Mod (tek /orkestra; kullanıcı "hafif/ultra" der ya da otomatik seçilir). Tabanlar hiçbir modda delinmez.
# q: gereken zekaya eklenen pay (ultra bir kademe akıllı ister, kritik 56'da kalır); claude: Claude Max ağırlık
# çarpanı; fazla_bas: fazla-zeka cezasının başladığı aşım; hata: başarısızlık bedeli çarpanı; paralel: işçi tavanı
# YALNIZ kullanıcı modu açıkça söylediyse (otomatik modda sabit tavan yok).
MOD = {
    "hafif":  dict(q=0, claude=2.5, fazla_bas=6, hata=0.5, paralel=2, aciklama="Claude'u en az harca; yeterli en ucuz model, az işçi"),
    "normal": dict(q=0, claude=1.0, fazla_bas=10, hata=1.0, paralel=None, aciklama="denge"),
    "ultra":  dict(q=3, claude=0.6, fazla_bas=16, hata=2.0, paralel=6, aciklama="kalite önce; bir kademe akıllı model, farklı aileden doğrulama"),
}

# Sürü yöntemleri (literatür yönünün AA ölçeğine çevirisi, ölçülmedi; k kalite kaydıyla yalnız aşağı ayarlanır).
# a, T: ΔZ = k·s·v·min(T, a·log2 N); v aynı model, vk karışık (Z farkı ≤ 4); hakem_is: hakem/birleştiricinin İB'si.
SURU_YONTEM = {
    "test":   dict(a=2.5, T=8, n0=4, nmax=8, v=0.7, vk=0.4, hakem_is=0.25, hakem=True,
                   kosul="çalıştırılabilir test; testi Z≥Q model yazmış ya da proje testi"),
    "kapali": dict(a=2.0, T=5, n0=3, nmax=5, v=0.7, vk=0.5, hakem_is=0.1, hakem=False,
                   kosul="kısa kapalı cevap (etiket, sayı, evet/hayır, şemalı JSON), çoğunluk oyu"),
    "kapsam": dict(a=1.5, T=4, n0=3, nmax=5, v=0.6, vk=0.6, hakem_is=0.3, hakem=True,
                   kosul="kaynak başına alıntılı çıkarım + betikle birebir alıntı denetimi"),
    "acik":   dict(a=1.0, T=3, n0=3, nmax=4, v=0.5, vk=0.3, hakem_is=0.3, hakem=True,
                   kosul="açık uçlu taslak; birleştirici Z≥Q"),
}
SURU_YASAK = {"zor", "kritik", "gorsel", "gorsel-anlama", "video-anlama", "video-uret"}
KARISIM_FARK = 4

# EVREN soğuma: kısa süreli dolulukta BEKLE önerisinin üst sınırı (dk) ve kısmi geçişte EVREN'e kalan pay.
BEKLE_DK = 30
KISMI_PAY = 0.5
SOGUMA_AD = {"503": "sunucu dolu (503)", "fair_share": "model payı dolu", "concurrency": "eşzamanlılık sınırı",
             "token_rate": "5 dk token penceresi dolu", "daily": "günlük kota bitti", "ag": "ağ hatası",
             "diger": "sunucu hatası"}

# Roller: diğer alt ajanları izleyen/denetleyen ucuz-hızlı yardımcılar. esik = max(taban, işin Q'su − fark);
# is: izlenen işin İB'si başına rolün İB'si; hiz: yavaş modele ×1.6; bedava: bedava havuz aday olabilir mi
# (doğruluk hakemi ve muhalif asla bedava havuz değil). Üreten verilirse (--dogrulayici) aynı aile elenir.
ROL = {
    "nobetci": dict(taban=18, fark=25, is_=0.15, hiz=True, bedava=True,
                    gorev="Diğer alt ajanların günlüğünü/çıktısını aralıklarla okur: döngü/takılma (aynı adım 3×), boş/yarım "
                          "çıktı, kırmızı test, kapsam dışı dosya, token israfı (beklenenin 3× fazlası), gizli veri gönderimi, "
                          "uydurma kaynak/URL. Bulursa lidere 1-3 satır UYARI + kanıt (dosya:satır); kendisi düzeltmez."),
    "kontrolcu": dict(taban=20, fark=20, is_=0.2, hiz=True, bedava=True,
                      gorev="Çıktıyı şema ve 'Bitti' kanıtına göre denetler: zorunlu alanlar, dosya var mı, test/komut çıktısı "
                            "ekli mi, alıntı kaynakta birebir mi (betikle). GEÇTİ/KALDI + eksik listesi; içerik doğruluğuna hükmetmez."),
    "hakem": dict(taban=22, fark=6, is_=0.25, hiz=False, bedava=False,
                  gorev="Üretenden farklı aileden ikinci görüş: bağımsız cevap ya da A/B karşılaştırma; çoğunluk oyunda 3 farklı "
                        "aile. Gerekçesi kısa, kanıta dayalı; uyuşmazlıkta lider bir kademe güçlü modele yükseltir."),
    "haberci": dict(taban=20, fark=22, is_=0.2, hiz=True, bedava=True,
                    gorev="Uzun çıktı/günlükleri lider için 5-10 satır özetler (karar, kanıt, açık sorular); yeni iddia eklemez."),
    "arsivci": dict(taban=16, fark=40, is_=0.1, hiz=True, bedava=True,
                    gorev="Sonuçları adlandırır, dizinler, CHECKPOINT/karar kaydı tutar, tekrarları birleştirir; içerik üretmez."),
    "muhalif": dict(taban=38, fark=8, is_=0.5, hiz=False, bedava=False,
                    gorev="Öneriye karşı en güçlü itirazları, başarısızlık senaryolarını ve gözden kaçan seçenekleri yazar "
                          "(red team); karar vermez, lider tartar."),
}
HIZLI = {"claude-haiku", "gpt-6-luna", "gemini-3.8-flash"}
# İzleyici/yardımcı rollerde (hiz=True: nöbetçi, kontrolcü, haberci, arşivci) büyük modeller yalnız başka aday yoksa.
BUYUK = {"claude-opus", "gpt-6.1-sol", "gemini-4-argon", "agy-claude-opus-5-5"}


def mod_sec(istek, sinif, ham):
    """otomatik: Claude kıtsa hafif; zor/kritik iş ve Claude bolsa ultra; yoksa normal. (mod, neden)"""
    if istek and istek != "otomatik":
        return istek, "kullanıcı"
    cl = ham.get("claude", {})
    c5, ch = cl.get("5s", [50, None])[0], cl.get("hafta", [50, None])[0]
    if ch < 45 or c5 < 30:
        return "hafif", f"Claude kıt (5s %{c5:g}, hafta %{ch:g})"
    if sinif == "kritik" and c5 >= 50 and ch >= 60:
        return "ultra", "kritik iş, Claude bol"
    return "normal", "varsayılan"


def q_etkin(sinif, kural):
    q = SINIF[sinif]["q"]
    if not q:
        return 0
    return min(q + MOD[kural.get("_mod", "normal")]["q"], max(q, SINIF["kritik"]["q"]))


class Hata(Exception):
    pass


# ---------------------------------------------------------------- kullanıcının platformları
PLATFORM_DOSYA = os.environ.get("ORKESTRA_PLATFORMLAR") or os.path.join(STATE_DIR, "platformlar.json")
OZEL_KOTA = {}
YUKLEME_NOTLARI = []
YUKLU_PLATFORM = {"yol": None}         # varsayılan dışı dosyaysa evren_suru çağrısına --platformlar eklenir
ZORUNLU_MODEL_ALAN = ("h", "aile", "o", "z", "cagri")
HAVUZ_ALAN = {"ad": str, "taban": dict, "agirlik": (int, float), "w5": (int, float), "bedava": bool,
              "harcanabilir": bool, "karar": str, "bitis": str, "gerekli_env": str, "gizlilik": str,
              "paralel_ajan": int, "esz": int, "suru": bool, "z_tavan": (int, float), "kota_okuyucu": str,
              "olc_esik": (int, float), "yasak_yol": list}
MODEL_ALAN = {"tps": (int, float), "dk_ib": (int, float), "bekle_dk": (int, float), "baglam": int, "cikti": int,
              "z_kaynak": str, "o_kaynak": str, "suru_cagri": str, "duzenle": dict, "duzenleyemez": bool,
              "api": str, "dusunme": bool, "ec": dict}


def env_var_mi(ad, env=None):
    """Ortam değişkeni VAR MI (değer döndürülmez, yazdırılmaz). Windows'ta HKCU\\Environment'a da bakar
    (kullanıcı değişkeni yeni ayarlandıysa açık kabuk onu henüz görmez)."""
    if env is not None:
        return bool(env.get(ad))
    if os.environ.get(ad):
        return True
    if os.name == "nt":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
                return bool(winreg.QueryValueEx(k, ad)[0])
        except OSError:
            return False
    return False


def taban_al(h, w):
    """Havuzun pencere tabanı; yazılmamışsa: 5s 0, bedava/harcanabilir 0, aksi halde YENI_HAVUZ (%10)."""
    t = HAVUZ[h].get("taban") or {}
    if w in t:
        return t[w]
    if w == "5s" or HAVUZ[h].get("bedava") or HAVUZ[h].get("harcanabilir"):
        return 0
    return YENI_HAVUZ["taban"].get(w, 0)


def platformlari_yukle(yol=None, simdi=None, env=None):
    """Kurulumda yapay zekâ yazar: ~/.orkestra/platformlar.json (yoksa yerleşik üç abonelik geçerli).
    {"kapali": ["agy_argon", "agy_tp"],                        sahip olunmayan havuzlar (model de düşer)
     "havuz": {"opencode_go": {"taban": {"5s": 0, "hafta": 10}, "agirlik": 0.6, "w5": 0, "ad": "OpenCode Go"},
               "bedava_api": {"taban": {"gun": 0}, "karar": "gun", "agirlik": 0.05, "bedava": true,
                              "bitis": "2026-12-01T03:00:00+03:00", "gerekli_env": "ANAHTAR_ADI", "gizlilik": "kamu",
                              "esz": 24, "paralel_ajan": 8, "suru": true, "z_tavan": 33, "kota_okuyucu": "evren"}},
     "model": {"kimi-k2": {"h": "opencode_go", "aile": "kimi", "o": {"hafta": 1.0}, "z": {"medium": 40},
               "cagri": "opencode run -m <sağlayıcı/model> \"<brief>\""}},
     "takma": {"kimi": "kimi-k2"},
     "kota": {"opencode_go": {"hafta": [70, null]}},            kotası otomatik okunamayan havuzun elle değeri
     "yasak": ["gpt-6-luna"]}
    Eksik havuz alanı: YENI_HAVUZ. `bitis` geçmişse ya da `gerekli_env` ortamda yoksa havuz ve modelleri yüklenmez
    (not düşülür; anahtarın değeri okunmaz/yazılmaz). Okunamazsa Hata (sessizce yerleşiğe dönmez)."""
    yol = yol or PLATFORM_DOSYA
    if not os.path.isfile(yol):
        return None
    try:
        with open(yol, encoding="utf-8-sig") as f:
            k = json.load(f)
    except (OSError, ValueError) as e:
        raise Hata(f"platform dosyası okunamadı: {yol} ({e})")
    if not isinstance(k, dict):
        raise Hata(f"platform dosyası nesne değil: {yol}")
    simdi = simdi or datetime.now(timezone.utc)
    for h in k.get("kapali", []):
        HAVUZ.pop(h, None)
    dusen = set()
    for h, v in (k.get("havuz") or {}).items():
        if not isinstance(v, dict):
            raise Hata(f"havuz.{h} nesne olmalı")
        for alan, tip in HAVUZ_ALAN.items():
            if alan in v and (not isinstance(v[alan], tip) or (tip is not bool and isinstance(v[alan], bool))):
                raise Hata(f"havuz.{h}.{alan}: tür yanlış ({type(v[alan]).__name__})")
        if "karar" in v and v["karar"] not in WIN_HOURS:
            raise Hata(f"havuz.{h}.karar: {v['karar']} (geçerli: {', '.join(WIN_HOURS)})")
        for alan in ("paralel_ajan", "esz"):
            if alan in v and v[alan] < 1:
                raise Hata(f"havuz.{h}.{alan} ≥ 1 olmalı")
        bad = [w for w in v.get("taban", {}) if w not in WIN_HOURS]
        if bad:
            raise Hata(f"havuz.{h}.taban: geçersiz pencere {bad}")
        for w, x in v.get("taban", {}).items():
            if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) or not 0 <= x <= 100:
                raise Hata(f"havuz.{h}.taban.{w}: 0-100 arası sayı olmalı ({x!r})")
        if v.get("bitis"):
            b = zaman(v["bitis"])
            if not b:
                raise Hata(f"havuz.{h}.bitis ISO tarih olmalı")
            if b <= simdi:
                dusen.add(h)
                YUKLEME_NOTLARI.append(f"{v.get('ad', h)}: ücretsiz dönem bitti ({v['bitis']}); ek ücretli servis kuralı gereği kapalı")
                continue
        if v.get("gerekli_env") and not env_var_mi(v["gerekli_env"], env):
            dusen.add(h)
            YUKLEME_NOTLARI.append(f"{v.get('ad', h)}: {v['gerekli_env']} ortam değişkeni yok, havuz kapalı")
            continue
        yeni = h not in HAVUZ
        HAVUZ[h] = (HAVUZ.get(h) or {**YENI_HAVUZ, "taban": dict(YENI_HAVUZ["taban"]), "ad": h}) | v
        if yeni and "taban" not in v and (v.get("bedava") or v.get("harcanabilir")):
            HAVUZ[h]["taban"] = {"5s": 0, "gun": 0, "hafta": 0}      # belgedeki gibi: bedava/harcanabilir havuz 0
    for m, v in (k.get("model") or {}).items():
        eksik = [x for x in ZORUNLU_MODEL_ALAN if x not in (v or {})]
        if eksik:
            raise Hata(f"model.{m}: eksik alan {eksik}")
        if v["h"] in dusen:
            continue
        if v["h"] not in HAVUZ:
            raise Hata(f"model.{m}: havuz '{v['h']}' tanımlı değil")
        bad = [e for e in v["z"] if e not in EFOR_CARPAN]
        if bad:
            raise Hata(f"model.{m}: geçersiz efor {bad} (geçerli: {', '.join(EFOR_CARPAN)})")
        for alan, tip in MODEL_ALAN.items():
            if alan in v and (not isinstance(v[alan], tip) or (tip is not bool and isinstance(v[alan], bool))):
                raise Hata(f"model.{m}.{alan}: tür yanlış")
        bad = [w for w in list(v["o"]) + list((v.get("duzenle") or {}).get("o", {})) if w not in WIN_HOURS]
        if bad:
            raise Hata(f"model.{m}.o: geçersiz pencere {bad}")
        bad = [e for e in v.get("ec", {}) if e not in EFOR_CARPAN]
        if bad:
            raise Hata(f"model.{m}.ec: geçersiz efor {bad}")
        if v.get("z_kaynak", "aa") not in Z_KAYNAK:
            raise Hata(f"model.{m}.z_kaynak: {v['z_kaynak']} (geçerli: {', '.join(Z_KAYNAK)})")
        tavan = HAVUZ[v["h"]].get("z_tavan")
        if tavan is not None and max(v["z"].values()) > tavan:
            raise Hata(f"model.{m}: Z {max(v['z'].values())} > havuz z_tavan {tavan} (eski ölçek? yalnız AA kaynağıyla yükselt)")
        MODEL[m] = v
    for m in [m for m, d in MODEL.items() if d["h"] not in HAVUZ]:
        MODEL.pop(m)
    for s in SINIF.values():
        if "adaylar" in s:
            s["adaylar"] = [m for m in s["adaylar"] if m in MODEL]
    for t, m in (k.get("takma") or {}).items():
        if m in MODEL:
            TAKMA[t] = m
    YASAK.update(k.get("yasak", []))
    OZEL_KOTA.update({h: w for h, w in (k.get("kota") or {}).items() if h in HAVUZ})
    YUKLU_PLATFORM["yol"] = os.path.abspath(yol)
    return yol


def karar_penceresi(h):
    if HAVUZ[h].get("karar"):
        return HAVUZ[h]["karar"]
    ws = {w for m, d in MODEL.items() if d["h"] == h for w in d["o"]} - {"5s"}
    return "gun" if ws == {"gun"} else "hafta"


def ozel_kota_ekle(ham, a, notlar):
    """Elle verilen kotalar (platform dosyası ve --kota havuz:pencere=kalan[@reset]); okunamayan havuz varsayım."""
    varsayim = set()
    for h, wins in OZEL_KOTA.items():
        if h in HAVUZ and h not in ham:
            ham[h] = {w: list(v) for w, v in wins.items()}
            if HAVUZ[h].get("kota_okuyucu"):          # otomatik okunması gerekirdi: elle değer varsayımdır
                varsayim.add(h)
                notlar.append(f"{HAVUZ[h]['ad']} kotası okunamadı: platformlar.json değeri kullanıldı (varsayım"
                              + (", bedava havuzda ceza yok)" if HAVUZ[h].get("bedava") else ", 2 kat pahalı)"))
    for spec in getattr(a, "kota", None) or []:
        try:
            hw, deger = spec.split("=", 1)
            h, w = hw.split(":", 1)
            kalan, _, reset = deger.partition("@")
            ham.setdefault(h, {})[w] = [float(kalan), reset or None]
            varsayim.discard(h)
        except ValueError:
            raise Hata(f"--kota biçimi: havuz:pencere=kalan[@ISO] (ör. opencode_go:hafta=70), verilen: {spec}")
    for h in HAVUZ:
        if h != "claude" and h not in ham:
            bed = HAVUZ[h].get("bedava")
            w = karar_penceresi(h)
            ham[h] = {w: [BEDAVA_VARSAYIM if bed else UCRETLI_VARSAYIM, None]}
            varsayim.add(h)
            notlar.append(f"{HAVUZ[h]['ad']} kotası okunamadı: {w} %{BEDAVA_VARSAYIM if bed else UCRETLI_VARSAYIM:g} varsayıldı"
                          + (" (bedava havuz, ceza yok)" if bed else ", 2 kat pahalı sayıldı (--kota ile ver)"))
    return varsayim


# ---------------------------------------------------------------- veri
def kota_modulu():
    spec = importlib.util.spec_from_file_location("kota_oku", os.path.join(HERE, "kota_oku.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def zaman(x):
    if isinstance(x, datetime):
        return x if x.tzinfo else x.replace(tzinfo=timezone.utc)
    if not x or not isinstance(x, str):
        return None
    try:
        d = datetime.fromisoformat(x.replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _ek_oku(k, out, havuzlar):
    """`kota_okuyucu` alanı olan havuzlar (genel kanca: kota_oku.ek_limitler(ad)). Hata metninde yalnız tür adı."""
    for h in havuzlar:
        try:
            r = k.ek_limitler(HAVUZ[h]["kota_okuyucu"])
        except Exception as e:
            out.setdefault("_notlar", []).append(f"{HAVUZ[h]['ad']}: kota okunamadı ({type(e).__name__})")
            continue
        if r:
            out[h] = {w: [v[0], zaman(v[1]).isoformat() if zaman(v[1]) else None] for w, v in r.items()}


def ham_oku(fresh=False):
    """havuz -> pencere -> [kalan%, reset ISO|None]; ayrıca _agy_models. Model çağırmaz."""
    ekler = [h for h, v in HAVUZ.items() if v.get("kota_okuyucu")]
    if not fresh:
        try:
            if time.time() - os.path.getmtime(HAM_ONBELLEK) < TTL:
                with open(HAM_ONBELLEK, encoding="utf-8") as f:
                    d = json.load(f)
                if isinstance(d, dict) and d:
                    eksik = [h for h in ekler if h not in d]
                    if eksik:
                        _ek_oku(kota_modulu(), d, eksik)
                    return d
        except (OSError, ValueError):
            pass
    k, out = kota_modulu(), {}
    try:
        cx = k.codex_limits() or {}
        if cx:
            out["codex"] = {w: [v[0], zaman(v[1]).isoformat()] for w, v in cx.items()}
    except Exception:
        pass
    try:
        harita = {"Gemini Models": "agy_gemini", "Gemini 4 Argon": "agy_argon", "Claude and GPT models": "agy_tp"}
        for (grp, win), (left, reset) in k.agy_limits().items():
            if grp in harita:
                z = zaman(reset)
                out.setdefault(harita[grp], {})[{"5h": "5s", "weekly": "hafta"}.get(win, win)] = [left, z.isoformat() if z else None]
    except Exception:
        pass
    try:
        ids = [ln.split("\t")[0].strip() for ln in k.agy_run("models").splitlines() if ln.strip()]
        if ids:
            out["_agy_models"] = ids
    except Exception:
        pass
    _ek_oku(k, out, ekler)
    if out:
        try:
            tmp = HAM_ONBELLEK + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({x: v for x, v in out.items() if x != "_notlar"}, f)
            os.replace(tmp, HAM_ONBELLEK)
        except OSError:
            pass
    return out


def temizle(ham, simdi, notlar):
    """Bozuk pencereyi atar, kalanı 0-100'e kısar, reseti geçmiş pencereyi yenilenmiş sayar."""
    temiz = {}
    for h, wins in ham.items():
        if h.startswith("_"):
            temiz[h] = wins
            continue
        if h not in HAVUZ or not isinstance(wins, dict):
            continue
        for w, v in wins.items():
            if w.startswith("_"):
                temiz.setdefault(h, {})[w] = v
                continue
            if w not in WIN_HOURS or not isinstance(v, (list, tuple)) or len(v) != 2:
                notlar.append(f"{h} {w}: bozuk veri atıldı")
                continue
            kalan, reset = v
            if isinstance(kalan, bool) or not isinstance(kalan, (int, float)) or not math.isfinite(kalan):
                notlar.append(f"{h} {w}: kalan sayı değil, atıldı")
                continue
            kalan = min(max(float(kalan), 0.0), 100.0)
            zr = zaman(reset)
            if zr and zr <= simdi:
                notlar.append(f"{h} {w}: reset geçti, yenilenmiş (%100) sayıldı")
                kalan, zr = 100.0, None
            temiz.setdefault(h, {})[w] = [kalan, zr.isoformat() if zr else None]
    return temiz


def claude_ekle(ham, a, notlar):
    if "claude" not in HAVUZ:
        ham.pop("claude", None)
        return ham
    c = {}
    if a.claude_5s is not None:
        c["5s"] = [a.claude_5s, a.claude_5s_reset]
    if a.claude_hafta is not None:
        c["hafta"] = [a.claude_hafta, a.claude_hafta_reset]
    if c:
        ham["claude"] = c
    cl = ham.get("claude")
    if not cl:
        notlar.append("Claude kotası verilmedi: %50/%50 varsayıldı ve 2 kat pahalı sayıldı (get_usage değerini ver)")
        ham["claude"] = {"5s": [50.0, None], "hafta": [50.0, None], "_varsayim": True}
    else:
        for w in ("5s", "hafta"):
            if w not in cl:
                notlar.append(f"Claude {w} verilmedi: %50 varsayıldı")
                cl[w] = [50.0, None]
                cl["_varsayim"] = True
    return ham


def eksik_doldur(ham, notlar):
    """temizle'den SONRA: karar penceresi (Codex/agy haftalık, günlük kotalı platformda günlük; Claude'da 5s ve
    haftalık) yoksa ya da bozuk diye atıldıysa havuz puan 0 alıp öne geçmesin: okunamayan havuzla aynı notlu
    varsayım (%50, 2 kat pahalı; bedava havuzda %80, ceza yok). Taban bu durumda doğrulanamaz, not bunu söyler."""
    for h in HAVUZ:
        if h == "claude":
            cl = ham.setdefault("claude", {})
            for w in ("5s", "hafta"):
                if w not in cl:
                    cl[w] = [50.0, None]
                    cl["_varsayim"] = True
                    notlar.append(f"Claude {w} verisi yok/bozuk: %50 varsayıldı, 2 kat pahalı sayıldı")
            continue
        if h not in ham:
            continue                                   # hiç okunamadı: ozel_kota_ekle ya da degerle eler
        w = karar_penceresi(h)
        if w not in ham[h]:
            bed = HAVUZ[h].get("bedava")
            v = BEDAVA_VARSAYIM if bed else UCRETLI_VARSAYIM
            ham[h][w] = [v, None]
            ham[h]["_varsayim"] = True
            notlar.append(f"{HAVUZ[h]['ad']} {PENCERE_AD[w]} (karar) penceresi okunamadı/bozuk: %{v:g} varsayıldı,"
                          f" taban doğrulanamaz" + (" (bedava, ceza yok)" if bed else ", 2 kat pahalı sayıldı"))
    return ham


def oranlar():
    r = {m: dict(d["o"]) for m, d in MODEL.items()}
    try:
        with open(OLCUM, encoding="utf-8") as f:
            kayit = json.load(f).get("oran", {})
        for m, wins in kayit.items():
            if m not in r or not isinstance(wins, dict):
                continue
            for w, x in wins.items():
                onc = MODEL[m]["o"].get(w)
                try:
                    v = float(x)
                except (TypeError, ValueError):
                    continue
                if onc and math.isfinite(v) and 0.2 * onc <= v <= 5 * onc:
                    r[m][w] = v
    except (OSError, ValueError, AttributeError):
        pass
    return r


def model_coz(ad):
    """'sonnet:high', 'claude-sonnet', 'sol' -> ('claude-sonnet', 'high'|None). Bilinmeyen: Hata."""
    m, _, e = str(ad).strip().partition(":")
    m = TAKMA.get(m.lower(), m.lower())
    if m in YASAK or any(y in m for y in ("astra", "fable")):
        raise Hata(f"{ad}: YASAK model (Fable/Astra) -> kullanıcıya sor")
    if m not in MODEL:
        raise Hata(f"{ad}: bilinmeyen model. Geçerli: {', '.join(MODEL)} (takma: {', '.join(TAKMA)})")
    if e and e not in MODEL[m]["z"]:
        raise Hata(f"{ad}: {m} için geçersiz efor '{e}'. Geçerli: {', '.join(MODEL[m]['z'])}")
    return m, (e or None)


def havuz_adlari(x, kaynak):
    """Havuz adı listesi (yasak_havuz, --haric): büyük/küçük harf ve boşluk duyarsız; tanımsız ad UYARI ile
    yine listede kalır (anahtarı olmadığı için yüklenmemiş havuz da yazılabilir)."""
    x = [x] if isinstance(x, str) else x if isinstance(x, (list, tuple, set)) else []
    out = set()
    for a in x:
        a = str(a).strip().lower()
        if not a:
            continue
        if a not in HAVUZ:
            print(f"UYARI {kaynak}: '{a}' tanımlı/yüklü havuz değil (havuzlar: {', '.join(HAVUZ)})", file=sys.stderr)
        out.add(a)
    return out


def proje_kurali(yol):
    """cwd'den yukarı `.orkestra.json` arar. Okunamazsa Hata (kuralı sessizce düşürmez). Biçim:
    {"zorunlu": {"gorsel": "sol:high", "*": "opus:high"}, "yasak": ["luna"], "agirlik": {"codex": 0.8},
     "gizli": true, "yasak_havuz": ["evren"], "not": "..."}
    gizli: projenin verisi gizli sayılır (kamuya açık havuz hiçbir sınıfta aday olmaz). agirlik 0.01-5'e kırpılır."""
    if not yol:
        return {}, None
    d = os.path.abspath(yol)
    while True:
        f = os.path.join(d, ".orkestra.json")
        if os.path.isfile(f):
            try:
                with open(f, encoding="utf-8-sig") as fh:
                    k = json.load(fh)
            except (OSError, ValueError) as e:
                raise Hata(f"proje kuralı okunamadı: {f} ({e}); düzelt ya da sil")
            if not isinstance(k, dict):
                raise Hata(f"proje kuralı nesne değil: {f}")
            y = k.get("yasak", [])
            y = [y] if isinstance(y, str) else y if isinstance(y, list) else []
            yasak = set()
            for x in y:
                try:
                    yasak.add(model_coz(x)[0])
                except Hata as e:
                    if "YASAK" not in str(e):
                        print(f"UYARI {f}: yasak listesinde {e}")
            ag = {}
            for h, v in (k.get("agirlik") or {}).items() if isinstance(k.get("agirlik"), dict) else []:
                if h not in HAVUZ or isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
                    print(f"UYARI {f}: agirlik.{h}={v!r} yok sayıldı (havuz: {', '.join(HAVUZ)})")
                    continue
                ag[h] = min(max(float(v), 0.01), 5.0)
            zr = k.get("zorunlu") if isinstance(k.get("zorunlu"), dict) else {}
            # gizlilik kuralı güvenli tarafta okunur (fail-closed): bool dışı dolu değer de gizli sayılır
            gz = k.get("gizli", False)
            if not isinstance(gz, bool):
                print(f"UYARI {f}: gizli={gz!r} bool değil; güvenli tarafta GİZLİ sayıldı (true/false yaz)")
                gz = gz not in (None, 0, "", [], {})
            yh = havuz_adlari(k.get("yasak_havuz", []), f"{f}: yasak_havuz")
            return {"yasak": yasak, "agirlik": ag, "zorunlu": zr, "not": k.get("not"),
                    "gizli": gz, "yasak_havuz": yh}, f
        ust = os.path.dirname(d)
        if ust == d:
            return {}, None
        d = ust


# ---------------------------------------------------------------- kalite kaydı (sürü kalibrasyonu)
_KALITE_ONB = {}


def kalite_kayitlari():
    try:
        mt = os.path.getmtime(KALITE)
    except OSError:
        return []
    if _KALITE_ONB.get("yol") == KALITE and _KALITE_ONB.get("mt") == mt:
        return _KALITE_ONB["r"]
    r = []
    try:
        with open(KALITE, encoding="utf-8") as f:
            for ln in f:
                try:
                    x = json.loads(ln)
                    if isinstance(x, dict) and x.get("kabul") in (0, 1):
                        r.append(x)
                except ValueError:
                    continue
    except OSError:
        return []
    _KALITE_ONB.update(yol=KALITE, mt=mt, r=r)
    return r


def kalite_k(model, yontem):
    """k = clamp((kabul − 0.75) / 0.15, 0, 1), model × yöntem başına, en az 20 kayıttan sonra; önce 1. k > 1 asla."""
    r = [x["kabul"] for x in kalite_kayitlari() if x.get("model") == model and x.get("yontem") == yontem]
    if len(r) < 20:
        return 1.0
    return min(max((sum(r) / len(r) - 0.75) / 0.15, 0.0), 1.0)


def kalite_z(model, efor, z):
    """30 kayıtta kabul < 0.8 → Z − 2 (yalnız aşağı; Z yalnız AA güncellemesiyle yükselir)."""
    r = [x["kabul"] for x in kalite_kayitlari() if x.get("model") == model and x.get("efor") == efor]
    return z - 2 if len(r) >= 30 and sum(r) / len(r) < 0.8 else z


def kalite_kaydet(a):
    m, e = model_coz(a.model or "")
    if a.kabul not in (0, 1):
        raise Hata("--kabul 0|1")
    os.makedirs(os.path.dirname(KALITE), exist_ok=True)
    x = {"model": m, "efor": a.efor or e, "yontem": a.yontem or "tek", "sinif": a.sinif, "kabul": a.kabul,
         "zaman": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    with open(KALITE, "a", encoding="utf-8") as f:
        f.write(json.dumps(x, ensure_ascii=False) + "\n")
    print("kaydedildi:", x, "| k =", round(kalite_k(m, x["yontem"]), 2))
    return 0


# ---------------------------------------------------------------- puanlama
def agy_var(m, e, ham):
    ids = ham.get("_agy_models")
    if m not in AGY_AD or not ids:
        return True
    return AGY_AD[m].format(e=e) in ids


def havuz_agirligi(h, ham, kural, simdi):
    w = kural.get("agirlik", {}).get(h, HAVUZ[h]["agirlik"])
    if h != "claude" and ham.get(h, {}).get("_varsayim") and not HAVUZ[h].get("bedava"):
        w *= 2.0
    if h == "claude":
        cl = ham.get("claude", {})
        w *= MOD[kural.get("_mod", "normal")]["claude"]
        if cl.get("_varsayim"):
            w *= 2.0
        kalan, reset = cl.get("hafta", [100, None])
        if kalan < 50:
            zr = zaman(reset)
            t = min(max((zr - simdi).total_seconds() / 3600 / 168, 0.0), 1.0) if zr else 1.0
            w *= 1 + (50 - kalan) / 25 * t          # hafta sonuna doğru etkisi azalır (kullan ya da kaybet)
    return w


def _duz_alan(m, kural, alan):
    """--duzenle (dosya düzenleyen iş) iken modelin `duzenle` alt alanı (o, cagri, dk_ib) önce gelir."""
    d = MODEL[m]
    if kural.get("_duzenle") and alan in (d.get("duzenle") or {}):
        return d["duzenle"][alan]
    return d.get(alan)


def tahmini_dk(m, e, is_, kural):
    dk = _duz_alan(m, kural, "dk_ib")
    if dk is None:
        return None
    return is_ * dk * efor_carpan(m, e) + MODEL[m].get("bekle_dk", 0)


def degerle(m, e, z, sinif, is_, ham, oran, simdi, kural, dogrulayici=False):
    """(puan, not, döküm) ya da (None, neden, None). Düşük puan iyi."""
    d, s = MODEL[m], SINIF[sinif]
    h = d["h"]
    hv = HAVUZ[h]
    q = q_etkin(sinif, kural)
    md = MOD[kural.get("_mod", "normal")]
    esik = q + 1 if s.get("sert") and not dogrulayici else q - 1 if s.get("sert") else q
    if kural.get("_min_z"):
        esik = max(esik, kural["_min_z"])
    if d.get("z_kaynak") == "tahmin" and q and not kural.get("_suru"):
        if q >= 38:
            return None, f"zeka yetmez (tahmini Z{z:g}, AA kanıtı yok: Q{q} işte kullanılmaz)", None
        if z < esik + TAHMIN_PAY:
            return None, f"zeka yetmez (tahmini Z{z:g} < {esik}+{TAHMIN_PAY} güvenlik payı)", None
    if z < esik:
        return None, f"zeka yetmez (Z{z:g} < {esik})", None
    if h in kural.get("_haric", ()) or h in kural.get("yasak_havuz", ()):
        return None, "hariç tutuldu (--haric / proje yasak_havuz; limit değil)", None
    if hv.get("gizlilik") == "kamu" and kural.get("_veri", "bilinmiyor") != "genel":
        return None, f"veri '{kural.get('_veri', 'bilinmiyor')}': kamuya açık havuza gönderilmez (--veri genel gerekir; limit değil)", None
    sg = kural.get("_soguma") or {}
    if sg and hv.get("kota_okuyucu") == "evren":
        for ad in ("*", d.get("api", m)):
            k = sg.get(ad)
            if k and k.get("durum") == "aktif":
                return None, (f"EVREN soğuma: {sure_metni(k['kalan_sn'])} kaldı ({SOGUMA_AD.get(k['tur'], k['tur'])}"
                              + (f" ×{k['ardisik']}" if k.get("ardisik", 1) > 1 else "") + "; geçici)"), None
    if kural.get("_baglam") and d.get("baglam") and kural["_baglam"] * 1000 > d["baglam"]:
        return None, f"bağlam yetmez ({d['baglam'] // 1000}K < {kural['_baglam']:g}K)", None
    if kural.get("_duzenle") and d.get("duzenleyemez"):
        return None, "dosya düzenleyemez (yalnız metin işi; limit değil)", None
    if not agy_var(m, e, ham):
        return None, "agy model listesinde yok (kalkmış olabilir)", None
    p = 1 / (1 + math.exp(-(z - q + 2) / 2.0)) if q else 1.0
    pencereler = ham.get(h)
    if not pencereler:
        return None, f"{hv['ad']} kotası okunamadı", None
    duz = bool(hv.get("harcanabilir") or hv.get("bedava"))
    o_m = _duz_alan(m, kural, "o") if kural.get("_duzenle") and (d.get("duzenle") or {}).get("o") else oran[m]
    kitlar, kalan_ib, notlar = {}, [], []
    harcar, musaitler = {}, {}
    tempo_h = 1.0
    for w in ("hafta", "gun", "5s"):                     # uzun pencere önce: red nedeni bağlayıcı olanı söylesin
        if w not in pencereler:
            continue
        kalan, reset = pencereler[w]
        r = o_m.get(w)
        if r is None:
            continue
        taban = taban_al(h, w)
        musait = kalan - taban
        zr = zaman(reset)
        t = min(max((zr - simdi).total_seconds() / 3600 / WIN_HOURS[w], 0.02), 1.0) if zr else 1.0
        if duz:
            tempo, ef = 1.0, efor_carpan(m, e)
        else:
            tempo = min(max(musait / ((100 - taban) * t), 0.4), 5.0) if musait > 0 else 0.4
            ef = efor_carpan(m, e) ** (0.5 if tempo >= 3 else 1.0)   # boş kapasitede yüksek efor ucuzlar
        harca = r * is_ * ef / p * s.get("carpan", 1)    # görsel üretim kotayı 3-5 kat hızlı yer
        if w == "5s":
            if harca * PAY_5S > musait:
                parca = max(musait / PAY_5S / (r * ef / p), 0)
                bekle = f", {max((zr - simdi).total_seconds() / 3600, 0):.1f} sa sonra yenilenir" if zr else ""
                return None, f"5s'e sığmaz -> sıradaki devralır (≤{parca:.1f} İB'lik parçalara böl{bekle})", None
        elif harca > musait:
            if not taban:                                  # taban 0: kota bitti (agy'de 5s de işlemez)
                return None, f"{PENCERE_AD[w]} kotası bitti/yetmez (kalan %{kalan:g}, iş ≈%{harca:.1f}, taban 0)", None
            return None, f"{PENCERE_AD[w]} %{taban:g} tabanına iner (kalan %{kalan:g})", None
        elif not duz:
            tempo_h = tempo
        # toplu dağıtım için bu işin pencereden beklenen tüketimi (p ve 5s payı dahil) ve tabana kadar kalan
        harcar[w] = harca * (PAY_5S if w == "5s" else 1.0)
        musaitler[w] = musait
        kalan_ib.append(musait / (harcar[w] / is_))
        # düz kıtlık: pencerenin %'si haftalık eşdeğere çevrilir (günlük pencere haftada 7 kez yenilenir: %1'i 1/7 değerinde)
        kitlar[w] = (harca / 100 * WIN_HOURS[w] / 168 if duz else
                     harca / max(musait - harca, 1e-6) * (1 / tempo) ** 0.5)
    if not kitlar:
        return None, "pencere verisi yok", None
    kw = karar_penceresi(h)
    if kw not in kitlar or (hv["w5"] and "5s" not in kitlar):
        eksik = kw if kw not in kitlar else "5s"
        return None, f"{PENCERE_AD[eksik]} penceresi verisi yok: taban doğrulanamaz (limit değil, veri eksik)", None
    asim = z - q if q else 0
    rol = ROL.get(kural.get("_rol") or "")
    fazla = 2 ** (max(0, asim - (4 if rol else md["fazla_bas"])) / 4)   # rol: eşiğe yakın ucuz model
    hata = 1 + s.get("hata", 0) * md["hata"] * (1 - p)
    kitlik = hv["w5"] * kitlar.get("5s", 0) + kitlar.get("gun", 0) + kitlar.get("hafta", 0)
    ag = havuz_agirligi(h, ham, kural, simdi)
    dk = tahmini_dk(m, e, is_, kural)
    gecikme = 1.0
    if dk is not None:
        if kural.get("_sure_dk") and dk > kural["_sure_dk"]:
            return None, f"süreye sığmaz (~{dk:.0f} dk > {kural['_sure_dk']:g} dk; limit değil)", None
        gecikme = 1 + dk / 120
    puan = kitlik * ag * fazla * hata * gecikme
    if rol and rol["hiz"] and not hizli_mi(m):
        puan *= 1.6
    if tempo_h < 0.6:
        notlar.append(f"haftalık tempo geride (x{tempo_h:.2f})")
    if ham.get(h, {}).get("_varsayim"):
        notlar.append("kota varsayım")
    if d.get("o_kaynak") == "tahmin":
        notlar.append("oran tahmin")
    if d.get("z_kaynak") in ("tahmin", "aa-indirimli"):
        notlar.append(f"Z {d['z_kaynak']}")
    if dk is not None:
        notlar.append(f"~{dk:.0f} dk")
    elif kural.get("_sure_dk"):
        notlar.append("süre bilinmiyor (dk_ib yok; süre bütçesi denetlenmedi)")
    nt = f"Z{z:g} p{p:.2f}, kalan ≈{min(kalan_ib):.1f} İB" + (f", fazla-zeka x{fazla:.2f}" if fazla > 1.01 else "")
    if notlar:
        nt += ", " + ", ".join(notlar)
    dokum = dict(kitlik_5s=kitlar.get("5s"), kitlik_gun=kitlar.get("gun"), kitlik_hafta=kitlar.get("hafta"),
                 w5=hv["w5"], agirlik=ag, fazla=fazla, hata=hata, gecikme=gecikme, p=p, asim=asim, puan=puan,
                 kalan_ib=min(kalan_ib), dk=dk, duz=duz, harca=harcar, musait=musaitler)
    return puan, nt, dokum


def aile(m):
    return MODEL[m]["aile"]


def hizli_mi(m):
    """Rol için hızlı model: Haiku, Luna, Flash ya da bedava HTTP havuzu (EVREN) ve dk_ib ≤ 12."""
    d = MODEL[m]
    return m in HIZLI or bool(HAVUZ[d["h"]].get("bedava") and (d.get("dk_ib") or 99) <= 12)


def sure_metni(sn):
    dk = sn / 60
    return f"{dk / 60:.1f} sa" if dk >= 90 else f"{max(dk, 1):.0f} dk"


def ne_zaman(dk):
    """'~12 dk sonra' ya da (1 dk altı) 'saniyeler içinde': '~0 dk sonra' yazılmasın."""
    return "saniyeler içinde" if dk < 1 else f"~{dk:.0f} dk sonra"


def soguma_engeli(red, kural, q):
    """Uygun model yokken soğuma çözüm mü: zekâsı yeten (Z ≥ q) bir EVREN varyantını YALNIZ soğuma elediyse
    (kalan_sn, tür) en erkeni (model ancak kendi kaydı ve '*' bitince döner: ikisinin uzunu); değilse None."""
    sg = kural.get("_soguma") or {}
    out = []
    for m, e, n in red:
        if "soğuma" not in n or HAVUZ[MODEL[m]["h"]].get("kota_okuyucu") != "evren" or MODEL[m]["z"][e] < q:
            continue
        api = MODEL[m].get("api", m)
        ks = [k for a, k in sg.items() if a in ("*", api) and k.get("durum") == "aktif"]
        if ks:
            k = max(ks, key=lambda k: k["kalan_sn"])
            out.append((k["kalan_sn"], k["tur"]))
    return min(out) if out else None


def soguma_hazirla(ham_sg, simdi, notlar=None):
    """Soğuma kayıtlarını seçicinin biçimine çevirir (kota_oku.soguma_oku). ham_sg: senaryo '_soguma' sözlüğü ya da
    "dosya" (gerçek durum dosyası). EVREN havuzu yüklü değilse {}. Hata: {} + not (seçim durmaz)."""
    if not any(v.get("kota_okuyucu") == "evren" for v in HAVUZ.values()):
        return {}
    try:
        k = kota_modulu()
        if ham_sg == "dosya":
            ham_sg = k.durum_oku().get("soguma")
        return k.soguma_oku(simdi, ham_sg or {}) if ham_sg else {}
    except Exception as e:
        if notlar is not None:
            notlar.append(f"EVREN soğuma durumu okunamadı ({type(e).__name__}); soğuma yok sayıldı")
        return {}


def evren_soguma_durumu(sonuc, red, kural, q):
    """Soğumanın bu seçime etkisi: {"aktif_dk", "tur", "sogudu" (zekâsı yeten EVREN varyantı soğuma yüzünden elendi),
    "evren_kazandi", "kardes_sogudu" [api], "yoklama" [api], "riskli"}. Soğuma yoksa None."""
    sg = kural.get("_soguma") or {}
    if not sg:
        return None
    ev = [m for m, d in MODEL.items() if HAVUZ[d["h"]].get("kota_okuyucu") == "evren"]
    if not ev:
        return None
    api = {m: MODEL[m].get("api", m) for m in ev}
    sog = [(m, e, n) for m, e, n in red if m in api and "soğuma" in n and MODEL[m]["z"][e] >= q]
    aktif = [k for a, k in sg.items() if k["durum"] == "aktif" and (a == "*" or a in api.values())]
    yok = sorted(a for a, k in sg.items() if k["durum"] == "yoklama" and (a == "*" or a in api.values()))
    kazandi = bool(sonuc) and sonuc[0][1] in api
    ev_sonuc = {api[x[1]] for x in sonuc if x[1] in api}
    kardes = sorted({api[m] for m, _, _ in sog} - ev_sonuc) if ev_sonuc else []
    if not sog and not yok:
        return None
    en = min(aktif, key=lambda k: k["kalan_sn"]) if aktif else None
    return {"aktif_dk": None if not en else round(en["kalan_sn"] / 60, 1), "tur": en["tur"] if en else None,
            "sogudu": bool(sog), "evren_kazandi": kazandi, "kardes_sogudu": kardes, "yoklama": yok,
            "riskli": bool(ev_sonuc) and bool(kardes or yok)}


def soguma_notlari(es, sonuc, kural, q):
    """'EVREN dolu: 12 dk soğumada; yerine agy Gemini gemini-3.8-flash:low (eşik aynı)' ve BEKLE notları."""
    if not es or not sonuc:
        return []
    out = []
    _, m0, e0 = sonuc[0][:3]
    z0, h0 = MODEL[m0]["z"][e0], MODEL[m0]["h"]
    tur = SOGUMA_AD.get(es["tur"] or "", es["tur"] or "")
    if es["sogudu"] and not es["evren_kazandi"]:
        out.append(f"EVREN dolu: {tur}, {sure_metni(es['aktif_dk'] * 60) if es['aktif_dk'] is not None else '?'} soğumada;"
                   f" yerine {HAVUZ[h0]['ad']} {m0}:{e0} (eşik aynı: Z{z0:g} ≥ Q{q}; limit zorladı, kalite değil)")
        acil = kural.get("_sure_dk") and es["aktif_dk"] is not None and kural["_sure_dk"] < es["aktif_dk"] + 10
        if es["aktif_dk"] is not None and es["aktif_dk"] <= BEKLE_DK and not acil:
            out.append(f"BEKLE seçeneği: iş acil değilse kuyruğa al; {ne_zaman(es['aktif_dk'])} seçiciyi yeniden çalıştır"
                       " (EVREN döner, ilk çağrı ping ile yoklar; başarısızsa soğuma uzar)")
        elif es["aktif_dk"] is not None and es["aktif_dk"] > BEKLE_DK:
            out.append(f"EVREN {sure_metni(es['aktif_dk'] * 60)} sonra döner: bekleme önerilmez"
                       + (" (günlük sıfırlama 00:00Z = 03:00 TSİ)" if es["tur"] == "daily" else ""))
    elif es["evren_kazandi"] and es["kardes_sogudu"]:
        out.append(f"EVREN {', '.join(es['kardes_sogudu'])} soğumada; aynı Z bandındaki kardeş {m0}:{e0} seçildi (eşik aynı)")
    if es["yoklama"] and es["evren_kazandi"]:
        out.append(f"EVREN soğuması bitti ({', '.join(es['yoklama'])}): ilk çağrı 16 token ping ile yoklar;"
                   " başarısızsa soğuma uzar, seçiciyi yeniden çalıştır")
    return out


def rol_sec(rol, sinif, is_, ham, oran, simdi, kural, uretici=None):
    """Rol adayları (sonuc, red, esik, q_is). Eşik rol bazlı; üretenden farklı aile; hakem/muhalif bedava havuzdan değil."""
    r = ROL[rol]
    q_is = SINIF[sinif]["q"] if sinif and SINIF[sinif]["q"] else SINIF["normal"]["q"]
    esik = max(r["taban"], q_is - r["fark"])
    ad = f"rol-{rol}"
    SINIF[ad] = dict(q=esik, aciklama=r["gorev"])
    k = dict(kural, _rol=rol)
    k.setdefault("_mod", "normal")
    if not r["bedava"]:
        k["_haric"] = set(k.get("_haric", ())) | {h for h in HAVUZ if HAVUZ[h].get("bedava")}
    try:
        sonuc, red = sirala(ad, is_ * r["is_"], ham, oran, simdi, k, uretici)
        kural["_rol_esik_etkin"] = q_etkin(ad, k)          # mod payı dahil (ultra: +3); başlıkta yazılır
    finally:
        SINIF.pop(ad, None)
    if r["hiz"]:                                          # izleyici rolde Opus/Sol/Argon yalnız son çare
        kucuk = [x for x in sonuc if x[1] not in BUYUK]
        if kucuk and len(kucuk) < len(sonuc):
            red = red + [(x[1], x[2], "büyük model bu rolde boşa (daha ucuz aday var)") for x in sonuc if x[1] in BUYUK]
            sonuc = kucuk
    return sonuc, red, esik, q_is


def sirala(sinif, is_, ham, oran, simdi, kural, dogrulayici=None):
    adaylar = SINIF[sinif].get("adaylar", list(MODEL))
    yasak = YASAK | set(kural.get("yasak", set()))
    sonuc, red = [], []
    for m in adaylar:
        for e, z in MODEL[m]["z"].items():
            if SINIF[sinif].get("efor") and e not in SINIF[sinif]["efor"]:
                continue
            if m in yasak:
                red.append((m, e, "yasak (kural/proje)"))
                continue
            if dogrulayici and aile(m) == aile(dogrulayici):
                red.append((m, e, "doğrulayıcı farklı aileden olmalı"))
                continue
            puan, nt, dk = degerle(m, e, kalite_z(m, e, z), sinif, is_, ham, oran, simdi, kural, dogrulayici=bool(dogrulayici))
            if puan is None:
                red.append((m, e, nt))
            else:
                sonuc.append((puan, m, e, nt, dk))
    # 20 puandan fazla gereğin üstündeki varyant yalnız başka aday yoksa (güçlü modeli boşa harcama)
    q = q_etkin(sinif, kural)
    if q and any(x[4]["asim"] <= 20 for x in sonuc):
        for x in [x for x in sonuc if x[4]["asim"] > 20]:
            red.append((x[1], x[2], f"gereğinden çok güçlü (Z{q + x[4]['asim']:g}), başka aday var"))
        sonuc = [x for x in sonuc if x[4]["asim"] <= 20]
    sonuc.sort(key=lambda x: x[0])
    # Claude'u koru (kullanıcı kuralı, 2026-11-08): Claude kazandıysa ve zekası en fazla 2 puan düşük, puanı en fazla
    # 2.2 kat kötü bir Claude dışı varyant varsa (Sol ≈ Sonnet), o öne geçer. Ultra modda kalite önce: uygulanmaz.
    if sonuc and kural.get("_mod", "normal") != "ultra" and MODEL[sonuc[0][1]]["h"] == "claude":
        z0 = MODEL[sonuc[0][1]]["z"][sonuc[0][2]]
        for i, x in enumerate(sonuc[1:], 1):
            if MODEL[x[1]]["h"] != "claude" and MODEL[x[1]]["z"][x[2]] >= z0 - 2 and x[0] <= 2.2 * sonuc[0][0]:
                sonuc.insert(0, sonuc.pop(i))
                break
    # Model başına tek varyant; aynı modelin eforları puanca %10 içindeyse en ucuz efor (daha hızlı, kota dostu).
    gor, tekil = set(), []
    for x in sonuc:
        if x[1] in gor:
            continue
        gor.add(x[1])
        yakin = [y for y in sonuc if y[1] == x[1] and y[0] <= x[0] * 1.10]
        tekil.append(min(yakin, key=lambda y: (efor_carpan(y[1], y[2]), y[0])))
    return tekil, red


def havuz_limit(h, kural):
    """Platform eşzamanlılığı: dosya düzenleyen ajan paralel_ajan; metin çağrısı esz − 2 (güvenlik payı). Yoksa None."""
    hv = HAVUZ[h]
    return hv.get("paralel_ajan") if kural.get("_duzenle") else (hv["esz"] - 2 if hv.get("esz") else hv.get("paralel_ajan"))


def kota_sigar(dk, kul=None):
    """Bu varyantın işinden havuza daha kaç tane sığar: her pencerede (tabana kadar kalan − planlanmış tüketim) /
    beklenen tüketim (p ve 5s payı dahil). Ücretli havuzda kalanın yalnız %90'ı planlanır (tahmin hatası tamponu);
    bedava/harcanabilir havuz sıfıra kadar. Tek iş tek başına sığıyorsa (seçimin kendisi) en az 1."""
    kul = kul or {}
    tampon = 1.0 if dk["duz"] else TAMPON
    sig = sig0 = None
    for w, hr in dk["harca"].items():
        hr = max(hr, 1e-9)
        a = int(max(dk["musait"][w] * tampon - kul.get(w, 0.0), 0) // hr)
        b = int(max(dk["musait"][w] - kul.get(w, 0.0), 0) // hr)
        sig = a if sig is None else min(sig, a)
        sig0 = b if sig0 is None else min(sig0, b)
    if sig is None:
        return 0
    return max(sig, min(sig0, 1) if not kul else 0)


def havuz_kapasite(h, dk, is_, kural):
    """Bir havuzda AYNI ANDA kaç işçi: kotaya sığan iş ve platform eşzamanlılığı. Sabit mod tavanı burada yok."""
    sig = kota_sigar(dk)
    lim = havuz_limit(h, kural)
    return max(0, min(sig, lim) if lim else sig)


def dagit(sonuc, is_, kural, parca):
    """Parçaları en iyi adaydan başlayarak dağıtır. Dönüş: ([(model, efor, adet)], sığmayan, {havuz: özet}).
    - Kota havuz başına PENCERE TÜKETİMİ olarak izlenir (aynı havuzdaki farklı modeller farklı yer).
    - Bedava havuz: eşzamanlılık kapasite değil; kotaya sığan parçalar o havuzda DALGA halinde sıraya girer
      (dalga = ⌈adet / eşzamanlı⌉); yalnız --sure-dk dalgalarla aşılırsa ya da kota yetmezse sıradaki havuza taşar.
    - Kullanıcının açıkça seçtiği mod tavanı (hafif 2, ultra 6) yalnız bedava OLMAYAN havuzlara uygulanır."""
    kul, adet, say = {}, {}, {}
    mt = MOD[kural.get("_mod", "normal")]["paralel"] if kural.get("_mod_kaynak") == "kullanıcı" else None
    durum = {"kalan": parca, "ucretli": 0}

    def yerlestir(paysiz):
        for _, m, e, _, dk in sonuc:
            if durum["kalan"] <= 0:
                break
            h = MODEL[m]["h"]
            hv, lim = HAVUZ[h], havuz_limit(h, kural)
            if paysiz and hv.get("kota_okuyucu") != "evren":
                continue
            k = min(kota_sigar(dk, kul.get(h)), durum["kalan"])
            if not paysiz and kural.get("_evren_pay") is not None and hv.get("kota_okuyucu") == "evren":
                k = min(k, max(math.ceil(parca * kural["_evren_pay"]) - adet.get(h, 0), 0))   # kısmi geçiş
            if hv.get("bedava"):
                if lim and kural.get("_sure_dk") and dk.get("dk"):
                    en_cok_dalga = max(1, int(kural["_sure_dk"] // dk["dk"]))
                    k = min(k, en_cok_dalga * lim - adet.get(h, 0))
            else:
                if lim:
                    k = min(k, lim - adet.get(h, 0))
                if mt:
                    k = min(k, mt - durum["ucretli"])
            if k <= 0:
                continue
            say[(m, e)] = say.get((m, e), 0) + k
            durum["kalan"] -= k
            adet[h] = adet.get(h, 0) + k
            if not hv.get("bedava"):
                durum["ucretli"] += k
            hk = kul.setdefault(h, {})
            for w, hr in dk["harca"].items():
                hk[w] = hk.get(w, 0.0) + k * hr
    yerlestir(False)
    if durum["kalan"] > 0 and kural.get("_evren_pay") is not None:
        yerlestir(True)        # kısmi geçiş: başka havuz yetmedi → kalan EVREN'e (boşta bırakma; EVREN düşerse yeniden dağıt)
    out = [(m, e, k) for (m, e), k in say.items()]
    ozet = {}
    for h, n in adet.items():
        lim = havuz_limit(h, kural) if HAVUZ[h].get("bedava") else None
        es = min(n, lim) if lim else n
        dks = [dk["dk"] for _, m, _, _, dk in sonuc if MODEL[m]["h"] == h and dk.get("dk")]
        dalga = math.ceil(n / es) if es else 1
        ozet[h] = dict(adet=n, eszamanli=es, dalga=dalga, dk=round(dalga * max(dks), 0) if dks else None)
    return out, parca - sum(x[2] for x in out), ozet


def paralel_tavan(sonuc, is_, kural, parca=None):
    """Aynı anda kaç işçi: SABİT TAVAN YOK. --parca verilmişse dağılımın eşzamanlı toplamı (dağılımla aynı sayı);
    verilmemişse adayların havuz kapasitelerinin toplamı (kuramsal üst sınır; lider --parca vermeli)."""
    if not sonuc:
        return 0
    parca = parca or kural.get("_parca")
    if parca:
        _, _, ozet = dagit(sonuc, is_, kural, parca)
        return max(1, sum(o["eszamanli"] for o in ozet.values()))
    kap = havuz_kapasiteleri(sonuc, is_, kural)
    bedava = sum(v for h, v in kap.items() if HAVUZ[h].get("bedava"))
    ucretli = sum(v for h, v in kap.items() if not HAVUZ[h].get("bedava"))
    mt = MOD[kural.get("_mod", "normal")]["paralel"] if kural.get("_mod_kaynak") == "kullanıcı" else None
    return max(1, bedava + (min(ucretli, mt) if mt else ucretli))


def havuz_kapasiteleri(sonuc, is_, kural):
    """Tüm adaylar üzerinden havuz başına eşzamanlı kapasite (aynı havuzun en büyüğü)."""
    havuz = {}
    for _, m, _, _, dk in sonuc:
        h = MODEL[m]["h"]
        havuz[h] = max(havuz.get(h, 0), havuz_kapasite(h, dk, is_, kural))
    return havuz


class _Bos(dict):
    def __missing__(self, k):
        return "{" + k + "}"


def cagri_yap(m, e, kural, is_=1.0, yedek=(), sablon=None, **ek):
    """Çağrı şablonunu doldurur: {e} efor, {mode} plan|accept-edits, {sure} agy zaman aşımı, {veri} (yalnız
    --veri genel iken), {yedek} aynı havuzdaki eşiği geçen diğer varyantlar, {n} {y} sürü."""
    if sablon:
        s = sablon
    elif kural.get("_duzenle"):
        s = _duz_alan(m, kural, "cagri")
    else:
        s = MODEL[m]["cagri"]
    dk = tahmini_dk(m, e, is_, kural)
    veri = kural.get("_veri", "bilinmiyor")

    def etiket(x, f):
        return f"{MODEL[x].get('api', x)}:{'kapali' if MODEL[x].get('dusunme') is False else f}"
    alan = dict(e=e, mode="accept-edits" if kural.get("_duzenle") else "plan",
                sure=f"{max(15, math.ceil(3 * dk))}m" if dk else "0",
                yedek="".join("," + etiket(x, f) for x, f in yedek if etiket(x, f) != etiket(m, e)),
                api=MODEL[m].get("api", m))
    if veri == "genel":
        alan["veri"] = "genel"
    alan.update(ek)
    out = s.format_map(_Bos(alan))
    if not sablon and "evren_suru" in out and kural.get("_q") and "--min-z" not in out and "--sinif" not in out:
        out += f" --min-z {kural['_q']:g}"              # 503/soğumada kardeş model seçicinin eşiğinin altına inmesin
    yp = YUKLU_PLATFORM["yol"]
    if "evren_suru" in out and yp and yp != os.path.abspath(PLATFORM_DOSYA) and "--platformlar" not in out:
        out += f' --platformlar "{yp}"'                 # evren_suru aynı yasak_yol/izin listesini görsün
    return out


def ayni_havuz_yedek(m0, e0, sinif, is_, ham, oran, simdi, kural):
    """Kazananla aynı havuzda eşiği geçen diğer varyantlar (bant içi yedek; daha düşük Z'ye inilmez)."""
    h0 = MODEL[m0]["h"]
    out = []
    for m, d in MODEL.items():
        if d["h"] != h0 or m == m0 or m in YASAK:
            continue
        for e, z in d["z"].items():
            p = degerle(m, e, kalite_z(m, e, z), sinif, is_, ham, oran, simdi, kural)[0]
            if p is not None:
                out.append((p, m, e))
    return [(m, e) for _, m, e in sorted(out)[:2]]


def karisim_uygun(zler):
    """Karışık sürü yalnız Z farkı ≤ 4 olan varyantlarla (Z20 + Z27 olmaz)."""
    return bool(zler) and max(zler) - min(zler) <= KARISIM_FARK


def suru_dz(z, q, yontem, n, karisik=False, k=1.0, test_evren=False):
    """Etkin Z artışı. Testi aynı (zayıf) model ailesi yazdıysa, yöntem yoksa ya da N<2 ise 0. k ve sonuç ≤ T."""
    y = SURU_YONTEM.get(yontem)
    if not y or n < 2 or test_evren:
        return 0.0
    s = min(max((z - (q - 8)) / 5, 0.0), 1.0)
    v = y["vk"] if karisik else y["v"]
    return min(max(k, 0.0), 1.0) * s * v * min(y["T"], y["a"] * math.log2(n))


def suru_oner(sinif, is_, ham, oran, simdi, kural, sonuc, red):
    """Doğrulayıcılı işte (`--yontem`) tek başına eşiği geçemeyen bedava/sürü havuzu varyantı için en küçük N.
    Hakem/birleştirici bedava olmayan havuzlardan seçilir (Codex %30 ve Claude %30/%15 tabanları sirala'da korunur)."""
    y = kural.get("_yontem")
    if y not in SURU_YONTEM or sinif in SURU_YASAK or not SINIF[sinif]["q"]:
        return None
    yd, q = SURU_YONTEM[y], q_etkin(sinif, kural)
    esik = q + 1 if SINIF[sinif].get("sert") else q
    esik = max(esik, kural.get("_min_z") or 0)
    en_iyi = None
    for m, e, neden_ in red:
        d = MODEL[m]
        if "zeka yetmez" not in neden_ or not HAVUZ[d["h"]].get("suru"):
            continue
        tahmin = d.get("z_kaynak") == "tahmin"
        if tahmin and q >= 38:
            continue
        z, k = kalite_z(m, e, d["z"][e]), kalite_k(m, y)
        hedef = esik + (1 if tahmin else 0)
        bul = None
        for n in range(yd["n0"], yd["nmax"] + 1):
            ze = z + suru_dz(z, q, y, n, k=k, test_evren=kural.get("_test_evren"))
            if ze >= hedef:
                bul = (n, ze)
                break
        if not bul:
            continue
        k2 = dict(kural, _suru=True, _min_z=None)
        puan, nt, dk = degerle(m, e, bul[1], sinif, is_ * bul[0], ham, oran, simdi, k2)
        if puan is None:
            continue
        if en_iyi is None or puan < en_iyi["puan"]:
            en_iyi = dict(model=m, efor=e, yontem=y, n0=bul[0], nmax=max(bul[0], yd["nmax"]), z=z,
                          z_etkin=round(bul[1], 1), k=round(k, 2), puan=puan, kosul=yd["kosul"])
    if not en_iyi:
        return None
    hakem = None
    if yd["hakem"]:
        bedava = {h for h in HAVUZ if HAVUZ[h].get("bedava")}
        for haric in (bedava | {"claude"}, bedava):          # Claude Max yalnız başka hakem yoksa
            hk = dict(kural, _haric=set(kural.get("_haric", ())) | haric, _min_z=max(q, kural.get("_min_z") or 0))
            hs, _ = sirala(sinif, yd["hakem_is"], ham, oran, simdi, hk)
            if hs:
                hakem = f"{hs[0][1]}:{hs[0][2]}"
                break
        if not hakem:
            return None                                    # hakemsiz sürü kabul edilmez
    else:
        hakem = None
    ilk_bedava = bool(sonuc) and HAVUZ[MODEL[sonuc[0][1]]["h"]].get("bedava")
    en_iyi["etiket"] = "SÜRÜ" if ilk_bedava else "KASKAD: önce dene"
    en_iyi["hakem"] = hakem
    en_iyi["yukselt"] = f"{sonuc[0][1]}:{sonuc[0][2]}" if sonuc else None
    en_iyi["hakem_min_z"] = q
    sab = MODEL[en_iyi["model"]].get("suru_cagri") or MODEL[en_iyi["model"]]["cagri"]
    en_iyi["cagri"] = cagri_yap(en_iyi["model"], en_iyi["efor"], kural, is_, sablon=sab, y=y, n=en_iyi["n0"])
    return en_iyi


def zorunlu_hedef(kural, sinif, zorla):
    hedef = zorla or kural.get("zorunlu", {}).get(sinif)
    yildiz = False
    if not hedef:
        hedef = kural.get("zorunlu", {}).get("*")
        yildiz = bool(hedef)
    if not hedef:
        return None
    m, e = model_coz(hedef)
    if yildiz and "adaylar" in SINIF[sinif] and m not in SINIF[sinif]["adaylar"]:
        return None                                   # "*" sabit kuralı (görsel = Sol high) delmez
    return m, e or next(iter(MODEL[m]["z"]))


# ---------------------------------------------------------------- girdi
def hazirla(a):
    notlar = []
    if a.senaryo:
        with open(a.senaryo, encoding="utf-8-sig") as f:
            ham = json.load(f)
        if not isinstance(ham, dict):
            raise Hata("senaryo nesne olmalı")
    else:
        ham = ham_oku(a.fresh)
    simdi = zaman(ham.pop("_simdi", None)) or datetime.now(timezone.utc)
    notlar.extend(ham.pop("_notlar", []) or [])
    sg_ham = ham.pop("_soguma", None) if a.senaryo else "dosya"     # senaryo: yalnız kendi _soguma'sı (belirlenimci)
    ham = claude_ekle(dict(ham), a, notlar)
    varsayim = ozel_kota_ekle(ham, a, notlar)
    ham = eksik_doldur(temizle(ham, simdi, notlar), notlar)
    if "claude" in HAVUZ and any(n.startswith("Claude") and "varsayıldı" in n for n in notlar):
        ham.setdefault("claude", {})["_varsayim"] = True
    for h in varsayim:
        ham.setdefault(h, {})["_varsayim"] = True
    kural, yol = proje_kurali(a.proje)
    kural["_veri"] = "gizli" if kural.get("gizli") else (getattr(a, "veri", None) or "bilinmiyor")
    for alan, arg in (("_sure_dk", "sure_dk"), ("_yontem", "yontem"), ("_min_z", "min_z"), ("_baglam", "baglam"),
                      ("_duzenle", "duzenle"), ("_parca", "parca"), ("_test_evren", "test_evren")):
        v = getattr(a, arg, None)
        if v not in (None, False, "yok"):
            kural[alan] = v
    kural["_haric"] = havuz_adlari(getattr(a, "haric", None) or [], "--haric")
    kural["_soguma"] = soguma_hazirla(sg_ham, simdi, notlar)
    return ham, simdi, oranlar(), kural, yol, notlar


def kota_satirlari(ham, simdi):
    out = []
    for h in HAVUZ:
        if h not in ham:
            out.append(f"{h:11s} okunamadı")
            continue
        parca = []
        for w in PENCERELER:
            if w not in ham[h]:
                continue
            kalan, reset = ham[h][w]
            zr = zaman(reset)
            tb = taban_al(h, w)
            parca.append(f"{w} {cubuk(kalan, tb)} %{kalan:g}" + (f" reset {max((zr - simdi).total_seconds() / 3600, 0):.0f}sa" if zr else "")
                         + f" taban %{tb:g}" + (" (karar dışı)" if w == "5s" and not HAVUZ[h]["w5"] else ""))
        etiket = (" [varsayım]" if ham[h].get("_varsayim") else "") + (" [bedava]" if HAVUZ[h].get("bedava") else "")
        if HAVUZ[h].get("bitis"):
            etiket += f" bitiş {HAVUZ[h]['bitis'][:10]}"
        out.append(f"{h:11s} " + " | ".join(parca) + etiket)
    return out


def cubuk(kalan, taban, n=10):
    """Kalan kota çubuğu: █ harcanabilir, ▓ dokunulmayan yedek (taban), · boş. Her hücre %10."""
    out = ""
    for i in range(n):
        alt = i * 100 / n
        out += ("▓" if alt < taban else "█") if alt < kalan else "·"
    return out


# ---------------------------------------------------------------- komutlar
KOTA_NEDEN = ("taban", "kota", "5s'e sığmaz")


def gerekce(s, sonuc, red, kural):
    """Seçim tek bir etkene dayanıyorsa (tek aday, zekâ fazlası, kotası biten/tabandaki havuz, bedava havuzun
    yetmemesi) bunu açıkça söyleyen notlar."""
    if not sonuc:
        return []
    q = q_etkin(s, kural)
    _, m0, e0 = sonuc[0][:3]
    z0 = MODEL[m0]["z"][e0]
    h0 = MODEL[m0]["h"]
    yeterli_red = [(m, e, n) for m, e, n in red if MODEL[m]["z"][e] >= q and "zeka yetmez" not in n]
    out = []
    if z0 - q >= 8 and s not in ("gorsel",):
        ucuz = [x for x in yeterli_red if MODEL[x[0]]["z"][x[1]] < z0]
        out.append(f"zekâ fazlası +{z0 - q}: {m0}:{e0} işin gerektirdiğinden güçlü"
                   + (f"; daha uygun {ucuz[0][0]}:{ucuz[0][1]} elendi ({ucuz[0][2]})" if ucuz else "; eşiğe daha yakın yeterli aday yok"))
    if len(sonuc) == 1 and yeterli_red:
        out.append(f"tek aday kaldı; örn. {yeterli_red[0][0]}:{yeterli_red[0][1]} {yeterli_red[0][2]}")
    # Kazanandan ucuz (daha düşük ağırlıklı) havuz kota yüzünden elendiyse: "limit zorladı" (agy bitti → Codex,
    # Codex tabanda → Claude). Taban 0 havuzda "kotası bitti", tabanlı havuzda "tabana yakın".
    kalan_havuz = {MODEL[x[1]]["h"] for x in sonuc}
    ucuzlar, en_z = {}, {}
    for m, e, n in yeterli_red:
        h = MODEL[m]["h"]
        if h == h0 or h in kalan_havuz or HAVUZ[h]["agirlik"] >= HAVUZ[h0]["agirlik"]:
            continue
        if any(k in n for k in KOTA_NEDEN) and "süre" not in n and "soğuma" not in n:
            z = MODEL[m]["z"][e]
            if h in en_z and z <= en_z[h]:
                continue                                   # havuz başına en güçlü varyantın nedeni (belirli)
            en_z[h] = z
            if "5s'e sığmaz" in n:
                ucuzlar[h] = "5 saatlik kotası doldu"
            elif taban_al(h, karar_penceresi(h)) == 0:
                ucuzlar[h] = "kotası bitti"
            else:
                ucuzlar[h] = "tabana yakın"
    if ucuzlar:
        ad0 = "Claude" if h0 == "claude" else HAVUZ[h0]["ad"]
        out.append(f"{ad0} seçildi çünkü " + ", ".join(f"{HAVUZ[h]['ad']} {v}" for h, v in sorted(ucuzlar.items()))
                   + " (limit zorladı, kalite değil)")
    # Bedava havuz bu sınıfa zekâ yüzünden yetmediyse: genişlik ilkesi (işi böl, basit parçaları oraya ver)
    for h, hv in HAVUZ.items():
        if not hv.get("bedava") or h in kalan_havuz:
            continue
        zs = [MODEL[m]["z"][e] for m, e, n in red if MODEL[m]["h"] == h and "zeka yetmez" in n]
        if zs and len(zs) == sum(1 for m, d in MODEL.items() if d["h"] == h for _ in d["z"]):
            out.append(f"{hv['ad']} bu sınıfa yetmez (en iyi Z{max(zs):g} < Q{q}); mekanik/basit alt parçaları "
                       f"`--sinif basit --veri genel` ile oraya ver, birleştirmeyi bu seçim yapsın")
    return out


def _red_pencere(n):
    """Red notundan reddi veren pencere (yalnız kota/taban nedenleri)."""
    if "5s'e sığmaz" in n:
        return "5s"
    if any(k in n for k in ("tabanına iner", "kotası bitti")):
        for w, ad in PENCERE_AD.items():
            if n.startswith(ad + " "):
                return w
    return None


def en_erken_cozum(red, ham, simdi):
    """'uygun model yok' için bekleme: yalnız zekâsı yeten varyantları kota/taban yüzünden eleyen pencerelerin
    reseti (haftalık engel varken 5 saatlik yenilenme çözüm sayılmaz). Bilinmiyorsa None."""
    zs = []
    for m, e, n in red:
        if "zeka yetmez" in n:
            continue
        w = _red_pencere(n)
        h = MODEL[m]["h"]
        if not w or w not in ham.get(h, {}):
            continue
        zr = zaman(ham[h][w][1])
        if zr and zr > simdi:
            zs.append((zr - simdi).total_seconds() / 3600)
    return min(zs, default=None)


def _yok_nedeni(red):
    """'uygun model yok' için havuz başına ASIL neden: zekâsı yeten varyantın reddi (kota/taban/veri/süre),
    yalnız hepsi zekâ yüzünden elendiyse en güçlü varyantın zekâ notu."""
    neden = {}
    for m, e, n in red:
        h = MODEL[m]["h"]
        oncelik = (0 if "zeka yetmez" in n else 1, MODEL[m]["z"][e])
        if h not in neden or oncelik > neden[h][0]:
            neden[h] = (oncelik, f"{m}:{e} {n}")
    return {h: v[1] for h, v in neden.items()}


def rol_yaz(a, ham, simdi, oran, kural, dog):
    """--rol: izleyici/denetçi alt ajan önerisi (sınıf tablosu yerine)."""
    r = ROL[a.rol]
    kural["_mod"], mneden = mod_sec(a.mod, a.sinif or "normal", ham)
    kural["_mod_kaynak"] = "kullanıcı" if mneden == "kullanıcı" else "otomatik"
    sonuc, red, esik, q_is = rol_sec(a.rol, a.sinif, a.is_, ham, oran, simdi, kural, dog)
    etkin = kural.pop("_rol_esik_etkin", esik)
    kural["_q"] = etkin
    print(f"\n== ROL: {a.rol} (izlenen iş {a.sinif or 'normal'} Q{q_is} → rol eşiği Z≥{esik}"
          + (f", {kural['_mod']} modda etkin Z≥{etkin}" if etkin != esik else "")
          + (f"; üreten {dog} → farklı aile" if dog else "") + (", bedava havuz yok" if not r["bedava"] else "") + ") ==")
    if not dog and a.rol in ("nobetci", "kontrolcu", "hakem", "muhalif"):
        print("NOT: üreten verilmedi (--dogrulayici <üreten MODEL adı>, ör. claude-sonnet): aile eleme YAPILMADI;"
              " farklı aile kuralı için ver")
    out = {"rol": a.rol, "esik": esik, "esik_etkin": etkin, "gorev": r["gorev"]}
    if not sonuc:
        print(f"{a.rol:10s}: uygun model yok -> lider kendisi izler ya da kullanıcıya sor")
        for h, n in _yok_nedeni(red).items():
            print(f"   {HAVUZ[h]['ad']:15s} {n}")
        out["model"] = None
    else:
        print(f"{a.rol:10s}: " + " > ".join(f"{m}:{e} ({p:.3g})" for p, m, e, _, _ in sonuc[:4]))
        ilk = sonuc[0]
        print(f"   ↳ GÖREV: {r['gorev']}")
        print(f"   ↳ ÇAĞRI: {cagri_yap(ilk[1], ilk[2], kural, a.is_ * r['is_'])}")
        if a.rol == "hakem":
            aileler, cogun = set(), []
            for _, m, e, _, _ in sonuc:
                if aile(m) not in aileler:
                    aileler.add(aile(m))
                    cogun.append(f"{m}:{e}")
            if len(cogun) >= 2:
                print(f"   ↳ ÇOĞUNLUK OYU: üreticinin cevabı + {', '.join(cogun[:2])} = 3 farklı aile, 3 oy"
                      " (2/3 uyuşmazsa bir kademe güçlü modele)" if dog and len(cogun) == 2 else
                      f"   ↳ ÇOĞUNLUK OYU: {', '.join(cogun[:3])} (farklı aileler; 2/3 uyuşmazsa bir kademe güçlü modele)")
            elif cogun:
                print("   ↳ ÇOĞUNLUK OYU kurulamaz: farklı aileden tek hakem var; ikinci görüş olarak kullan")
            out["cogunluk"] = cogun[:3]
        if a.rol == "nobetci":
            print("   ↳ ÇALIŞMA: arka planda, her 5-10 dk ya da her işçi adımından sonra; yalnız okur, uyarıyı lidere yazar;"
                  " lider durdurur/yeniden brief'ler")
        if a.sinif and a.rol != "arsivci":
            for p, m, e, nt, _ in sonuc[:6]:
                print(f"   {m + ':' + e:30s} {p:9.5f}  {nt}")
        out.update(model=ilk[1], efor=ilk[2], cagri=cagri_yap(ilk[1], ilk[2], kural, a.is_ * r["is_"]),
                   yedek=[f"{m}:{e}" for _, m, e, _, _ in sonuc[1:3]])
    if a.json:
        print("\nJSON " + json.dumps(out, ensure_ascii=False, default=str))
    return 0


def sec(a):
    ham, simdi, oran, kural, yol, notlar = hazirla(a)
    dog = model_coz(a.dogrulayici)[0] if a.dogrulayici else None
    print("== KOTA (model çağrısı yok) ==")
    print("\n".join(kota_satirlari(ham, simdi)))
    if yol:
        print(f"Proje kuralı: {yol}" + (f" ({kural.get('not')})" if kural.get("not") else ""))
    for n in YUKLEME_NOTLARI + notlar:
        print("NOT:", n)
    kamu = [HAVUZ[h]["ad"] for h in HAVUZ if HAVUZ[h].get("gizlilik") == "kamu"]
    if kamu and kural["_veri"] != "genel":
        print(f"NOT: {', '.join(kamu)} elendi: veri sınıfı '{kural['_veri']}' (gizlilik varsayılan kapalı; kamuya açık veri"
              f" ise --veri genel ver)")
    if kural.get("_soguma"):
        try:
            print("EVREN SOĞUMA:", kota_modulu().soguma_metni(kural["_soguma"]))
        except Exception:
            pass
    if getattr(a, "rol", None):
        return rol_yaz(a, ham, simdi, oran, kural, dog)
    print(f"\n== ÖNERİ (iş {a.is_:g} İB; düşük puan iyi; ilki elenirse sıradaki) ==")
    json_out, basilan = {}, set()
    for s in ([a.sinif] if a.sinif else list(SINIF)):
        if SINIF[s].get("yapilamaz"):
            print(f"{s:13s}: OTOMATİK YAPILAMAZ -> {SINIF[s]['yapilamaz']}")
            json_out[s] = {"model": None, "yapilamaz": SINIF[s]["yapilamaz"]}
            continue
        zr = zorunlu_hedef(kural, s, a.zorla)
        if zr:
            m, e = zr
            puan, nt, _ = degerle(m, e, MODEL[m]["z"][e], s, a.is_, ham, oran, simdi, kural)
            uyari = None if puan is not None else f"ZORUNLU ama {nt} -> kullanıcıdan onay al"
            print(f"{s:13s}: ZORUNLU {m}:{e} (kullanıcı/proje kuralı)" + (f"  !! {uyari}" if uyari else ""))
            json_out[s] = {"model": m, "efor": e, "neden": "zorunlu", "cagri": cagri_yap(m, e, dict(kural, _q=None), a.is_),
                           "uyari": uyari}
            continue
        kural["_mod"], mneden = mod_sec(a.mod, s, ham)
        kural["_mod_kaynak"] = "kullanıcı" if mneden == "kullanıcı" else "otomatik"
        kural["_q"] = q_etkin(s, kural)                    # ÇAĞRI satırında evren_suru --min-z (kardeş eşiği)
        sonuc, red = sirala(s, a.is_, ham, oran, simdi, kural, dog)
        suru = suru_oner(s, a.is_, ham, oran, simdi, kural, sonuc, red)
        if not sonuc:
            neden = _yok_nedeni(red)
            bekle = en_erken_cozum(red, ham, simdi)
            sgb = soguma_engeli(red, kural, q_etkin(s, kural))
            if sgb:
                bekle = sgb[0] / 3600 if bekle is None else min(bekle, sgb[0] / 3600)
            print(f"{s:13s}: uygun model yok -> kullanıcıya sor." + (f" Engeli kaldıran en erken yenilenme {bekle:.1f} sa sonra."
                                                                     if bekle is not None else ""))
            for h, n in neden.items():
                print(f"   {HAVUZ[h]['ad']:15s} {n}")
            if sgb:
                dk_ = sgb[0] / 60
                acil = kural.get("_sure_dk") and kural["_sure_dk"] < dk_ + 10
                if sgb[1] != "daily" and dk_ <= BEKLE_DK and not acil:
                    print(f"   ↳ BEKLE: EVREN {ne_zaman(dk_)} döner ({SOGUMA_AD.get(sgb[1], sgb[1])} soğuması); iş acil değilse"
                          " kuyruğa al, sonra seçiciyi yeniden çalıştır (ilk çağrı ping ile yoklar)")
                else:
                    print(f"   ↳ NOT: EVREN {sure_metni(sgb[0])} sonra döner ({SOGUMA_AD.get(sgb[1], sgb[1])}): bekleme önerilmez"
                          + (" (günlük sıfırlama 00:00Z = 03:00 TSİ)" if sgb[1] == "daily" else "")
                          + "; kullanıcıya sor (başka havuz yok/yetmiyor)")
            if suru:
                print(f"   ↳ {suru['etiket']}: {suru['model']}:{suru['efor']} ×{suru['n0']}-{suru['nmax']} {suru['yontem']}"
                      f" → etkin Z{suru['z_etkin']:g}, hakem {suru['hakem'] or '-'} | {suru['cagri']}")
            json_out[s] = {"model": None, "neden": list(neden.values()), "bekle_sa": None if bekle is None else round(bekle, 1),
                           "suru": suru, "soguma_bekle_dk": round(sgb[0] / 60, 1) if sgb else None,
                           "soguma_tur": sgb[1] if sgb else None}
            continue
        par = paralel_tavan(sonuc, a.is_, kural, a.parca)
        if a.parca:
            ptxt = f"  | eşzamanlı {par} ({a.parca} parça)"
        else:
            kap = havuz_kapasiteleri(sonuc, a.is_, kural)
            ptxt = ("  | paralel: --parca ver (havuz kapasitesi: "
                    + ", ".join(f"{HAVUZ[h]['ad'].split(' (')[0]} ≤{v}" for h, v in kap.items() if v) + ")")
        print(f"{s:13s} Q{q_etkin(s, kural):<2d} {kural['_mod']:6s}: " + " > ".join(f"{m}:{e} ({p:.3g})" for p, m, e, _, _ in sonuc[:3])
              + ptxt)
        es = evren_soguma_durumu(sonuc, red, kural, q_etkin(s, kural))
        notlar_s = gerekce(s, sonuc, red, kural) + soguma_notlari(es, sonuc, kural, q_etkin(s, kural))
        kismi = None
        parca_simdi = a.parca
        if es and a.parca and a.parca >= 2:
            acil = kural.get("_sure_dk") and es["aktif_dk"] is not None and kural["_sure_dk"] < es["aktif_dk"] + 10
            if es["riskli"]:
                kural["_evren_pay"] = KISMI_PAY
                kismi = {"tur": "dalgali", "evren_en_cok": math.ceil(a.parca * KISMI_PAY)}
            elif es["sogudu"] and not es["evren_kazandi"] and es["aktif_dk"] is not None and es["aktif_dk"] <= BEKLE_DK and not acil:
                parca_simdi = math.ceil(a.parca * KISMI_PAY)
                kismi = {"tur": "bekle", "simdi": parca_simdi, "kuyruk": a.parca - parca_simdi, "dk": es["aktif_dk"]}
        for n in notlar_s:
            anahtar_ = n.split(" (en iyi Z")[0]            # tam tabloda aynı bedava-havuz notu bir kez
            if a.sinif or anahtar_ not in basilan:
                print(f"   ↳ NOT: {n}")
                basilan.add(anahtar_)
        dag, sigmayan, dozet = dagit(sonuc, a.is_, kural, parca_simdi) if a.parca else ([], 0, {})
        kural.pop("_evren_pay", None)
        if kismi and kismi["tur"] == "dalgali" and dag:
            ev_n = sum(k for m, _, k in dag if HAVUZ[MODEL[m]["h"]].get("kota_okuyucu") == "evren")
            diger = sum(k for m, _, k in dag if HAVUZ[MODEL[m]["h"]].get("kota_okuyucu") != "evren")
            neden_ = ", ".join(es["kardes_sogudu"] + [f"{x} yoklanacak" for x in es["yoklama"]])
            if diger:
                print(f"   ↳ KISMİ GEÇİŞ: EVREN dalgalı ({neden_}); {ev_n} parça EVREN'e, {diger} parça"
                      " sıradaki havuza (EVREN düşerse iş yarım kalmaz)")
            else:
                print(f"   ↳ KISMİ GEÇİŞ: EVREN dalgalı ({neden_}); başka havuza sığmadı, {ev_n} parçanın hepsi EVREN'de"
                      " (düşen parça olursa seçiciyi o parçalar için yeniden çalıştır)")
            kismi["evren"], kismi["diger"] = ev_n, diger
        elif kismi and kismi["tur"] == "bekle":
            print(f"   ↳ KISMİ GEÇİŞ (bekle): şimdi {parca_simdi} parça aşağıdaki dağılımla; kalan {kismi['kuyruk']} parça"
                  f" {ne_zaman(kismi['dk'])} EVREN'e (o zaman seçiciyi --parca {kismi['kuyruk']} ile yeniden çalıştır)")
        if dag:
            print("   ↳ İŞÇİ: " + ", ".join(f"{k}× {m}:{e}" for m, e, k in dag)
                  + (f"; {sigmayan} parça sığmadı (sıraya al ya da kota yenilenince)" if sigmayan else ""))
            for h, o in dozet.items():
                if o["dalga"] > 1:
                    print(f"   ↳ DALGA: {HAVUZ[h]['ad'].split(' (')[0]} {o['adet']} parça, aynı anda ≤{o['eszamanli']},"
                          f" {o['dalga']} dalga" + (f" (~{o['dk']:.0f} dk)" if o["dk"] else ""))
        suru_goster = bool(suru and (suru["etiket"].startswith("KASKAD") or suru["puan"] < sonuc[0][0]))
        if suru_goster:
            print(f"   ↳ {suru['etiket']}: {suru['model']}:{suru['efor']} ×{suru['n0']}-{suru['nmax']} {suru['yontem']} → etkin Z"
                  f"{suru['z_etkin']:g} (hakem {suru['hakem'] or 'yok: uyuşmazlık ' + str(suru['yukselt']) + ' modeline'})"
                  f" | {suru['cagri']}")
        ilk = sonuc[0]
        yedek = ayni_havuz_yedek(ilk[1], ilk[2], s, a.is_, ham, oran, simdi, kural) if HAVUZ[MODEL[ilk[1]]["h"]].get("bedava") else []
        json_out[s] = {"model": ilk[1], "efor": ilk[2], "puan": round(ilk[0], 6),
                       "cagri": cagri_yap(ilk[1], ilk[2], kural, a.is_, yedek),
                       "yedek": [f"{m}:{e}" for _, m, e, _, _ in sonuc[1:3]], "mod": kural["_mod"], "mod_neden": mneden,
                       "paralel_tavan": par if a.parca else None, "dagilim": [f"{k}x{m}:{e}" for m, e, k in dag],
                       "dalga": dozet, "gerekce": notlar_s,
                       "kapasite": None if a.parca else havuz_kapasiteleri(sonuc, a.is_, kural),
                       "dk": None if ilk[4]["dk"] is None else round(ilk[4]["dk"], 1), "suru": suru if suru_goster else None,
                       "evren_soguma": es, "kismi": kismi}
        if a.sinif:
            for p, m, e, nt, _ in sonuc:
                print(f"   {m + ':' + e:30s} {p:9.5f}  {nt}  | {cagri_yap(m, e, kural, a.is_)}")
            for m, e, nt in red:
                print(f"   {m + ':' + e:30s}        --  {nt}")
    if a.json:
        print("\nJSON " + json.dumps(json_out, ensure_ascii=False, default=str))
    print(f"\nOranlar tahmin + ölçüm (ölçüm: {olcum_sayisi()}). Sıra: bedava > agy > Codex > Claude. YASAK: {', '.join(sorted(YASAK))}")


def durum(a):
    ham, simdi, oran, kural, yol, notlar = hazirla(a)
    print("== HAVUZLAR ==")
    print("\n".join(kota_satirlari(ham, simdi)))
    for n in YUKLEME_NOTLARI + notlar:
        print("NOT:", n)
    print("\n== KALAN İŞ (tabana kadar, varsayılan eforda) ==")
    for m, d in MODEL.items():
        h = d["h"]
        if h not in ham:
            continue
        ibs = [f"{w} {max(ham[h][w][0] - taban_al(h, w), 0) / oran[m][w]:.1f}" for w in PENCERELER if w in ham[h] and w in oran[m]]
        print(f"{m:28s} {HAVUZ[h]['ad'][:22]:22s} " + " | ".join(ibs) + " İB" + (" (oran tahmin)" if d.get("o_kaynak") == "tahmin" else ""))
    ids = ham.get("_agy_models")
    print("\nagy modelleri:", ", ".join(ids) if ids else "okunamadı")


def neden(a):
    ham, simdi, oran, kural, _, notlar = hazirla(a)
    if not a.model or not a.sinif:
        raise Hata("neden: --model ve --sinif gerekli")
    kural["_mod"], mn = mod_sec(a.mod, a.sinif, ham)
    print(f"mod: {kural['_mod']} ({mn}), etkin Q{q_etkin(a.sinif, kural)}, veri {kural['_veri']}")
    m, e = model_coz(a.model)
    for ef in ([e] if e else list(MODEL[m]["z"])):
        z = kalite_z(m, ef, MODEL[m]["z"][ef])
        puan, nt, dk = degerle(m, ef, z, a.sinif, a.is_, ham, oran, simdi, kural)
        print(f"{m}:{ef} sınıf {a.sinif} (Q{SINIF[a.sinif]['q']}), Z{z:g}" + (f" ({MODEL[m]['z_kaynak']})" if MODEL[m].get("z_kaynak") else ""))
        if puan is None:
            print("   ELENDİ:", nt)
            continue
        print(f"   puan {puan:.5f} = (w5 {dk['w5']} × kıtlık_5s {dk['kitlik_5s'] or 0:.4f} + kıtlık_gun {dk['kitlik_gun'] or 0:.4f}"
              f" + kıtlık_hafta {dk['kitlik_hafta'] or 0:.4f}{' düz' if dk['duz'] else ''}) × ağırlık {dk['agirlik']:.2f}"
              f" × fazla-zeka {dk['fazla']:.2f} × hata bedeli {dk['hata']:.2f} × gecikme {dk['gecikme']:.2f}")
        print("  ", nt)
    for n in YUKLEME_NOTLARI + notlar:
        print("NOT:", n)


# ---------------------------------------------------------------- kontrol: kurallar sahte senaryolarla
def _senaryo(**h):
    s = {"_simdi": "2026-11-11T10:00Z"}
    rs, rh = "2026-11-11T13:00Z", "2026-11-14T22:00Z"
    for k, (a5, ah) in h.items():
        s[k] = {} if k == "agy_argon" else {"5s": [a5, rs]}
        s[k]["hafta"] = [ah, rh]
    return s


# Sınamada kullanılan bedava platform (gerçek platformlar.json'dan bağımsız; değerler 2026-11-08 tasarımıyla aynı).
TEST_BEDAVA = {
    "havuz": {"evren": {"ad": "EVREN (test)", "taban": {"gun": 0}, "karar": "gun", "agirlik": 0.05, "w5": 0.0,
                        "bedava": True, "harcanabilir": True, "bitis": "2026-12-01T03:00:00+03:00",
                        "gerekli_env": "ORKESTRA_TEST_ANAHTAR", "gizlilik": "kamu", "paralel_ajan": 8, "esz": 24,
                        "suru": True, "z_tavan": 33, "kota_okuyucu": "evren", "olc_esik": 0.2}},
    "model": {
        "evren-deepseek-v4.1-flash": {"h": "evren", "aile": "deepseek", "api": "deepseek-v4.1-flash", "o": {"gun": 0.5},
                                      "o_kaynak": "tahmin", "ec": {"high": 1.0}, "z": {"high": 27}, "z_kaynak": "aa-indirimli",
                                      "dk_ib": 10, "bekle_dk": 2, "baglam": 1048576,
                                      "cagri": "evren_suru --model {api}:{e}{yedek} --veri {veri}",
                                      "suru_cagri": "evren_suru --model {api}:{e} --veri {veri} --yontem {y} --n {n}",
                                      "duzenle": {"o": {"gun": 8.0}, "dk_ib": 40,
                                                  "cagri": "codex exec -p evren -m {api} -c model_reasoning_effort={e}"}},
        "evren-deepseek-v4.1-flash-nr": {"h": "evren", "aile": "deepseek", "api": "deepseek-v4.1-flash", "dusunme": False,
                                         "o": {"gun": 0.35}, "o_kaynak": "tahmin", "ec": {"low": 1.0}, "z": {"low": 17},
                                         "z_kaynak": "aa-indirimli", "dk_ib": 5, "bekle_dk": 2, "duzenleyemez": True,
                                         "baglam": 1048576, "cagri": "evren_suru --model {api}:kapali --veri {veri}"},
        "evren-glm-5.3": {"h": "evren", "aile": "glm", "api": "glm-5.3", "o": {"gun": 0.5}, "o_kaynak": "tahmin",
                          "ec": {"low": 0.6, "high": 1.0}, "z": {"low": 21, "high": 28}, "z_kaynak": "aa-indirimli",
                          "dk_ib": 12, "bekle_dk": 2, "baglam": 524288,
                          "cagri": "evren_suru --model {api}:{e}{yedek} --veri {veri}",
                          "suru_cagri": "evren_suru --model {api}:{e} --veri {veri} --yontem {y} --n {n}",
                          "duzenle": {"o": {"gun": 8.0}, "dk_ib": 45,
                                      "cagri": "codex exec -p evren -m {api} -c model_reasoning_effort={e}"}}},
    "takma": {"glm": "evren-glm-5.3", "ds": "evren-deepseek-v4.1-flash", "ds-nr": "evren-deepseek-v4.1-flash-nr"},
    "kota": {"evren": {"gun": [80, None]}},
}


def kontrol(_a):
    import contextlib
    import copy
    import io
    import shutil
    import tempfile

    class A:
        claude_5s = claude_hafta = claude_5s_reset = claude_hafta_reset = None
        fresh = False
        proje = None
        senaryo = None
        kota = None
    global KALITE
    kalite_eski = KALITE
    gecici = tempfile.mkdtemp(prefix="orkestra_kontrol_")
    KALITE = os.path.join(gecici, "kalite_kayit.jsonl")             # gerçek kalite kaydına dokunma
    oran = {m: dict(d["o"]) for m, d in MODEL.items()}            # ölçümden bağımsız: öncüllerle sına
    sonuc = []

    def calis(s, sinif, is_=1.0, dog=None, kural=None, mod="normal", kaynak="otomatik", red_de=False):
        notlar = []
        simdi = zaman(s["_simdi"])
        ham = {k: v for k, v in s.items() if k != "_simdi"}
        ham = eksik_doldur(temizle(claude_ekle(json.loads(json.dumps(ham)), A, notlar), simdi, notlar), notlar)
        k = dict(kural or {})
        k["_mod"], k["_mod_kaynak"] = mod, kaynak
        k.setdefault("_veri", "bilinmiyor")
        return sirala(sinif, is_, ham, oran, simdi, k, dog)

    def dogrula(ad, kosul):
        sonuc.append((ad, bool(kosul)))

    def hv(x):
        return MODEL[x[1]]["h"]

    bol = dict(claude=(100, 95), codex=(100, 90), agy_gemini=(100, 80), agy_argon=(0, 80), agy_tp=(100, 80))
    for s in ("mekanik", "basit", "arastirma", "normal", "kod", "zor"):
        ilk = calis(_senaryo(**bol), s)[0][0]
        dogrula(f"bol kota, {s}: Claude Max seçilmez", hv(ilk) != "claude")
    noagy = dict(claude=(100, 95), codex=(100, 60), agy_gemini=(100, 3), agy_argon=(0, 3), agy_tp=(100, 3))
    for s in ("normal", "kod"):
        ilk = calis(_senaryo(**noagy), s)[0][0]
        dogrula(f"agy yok, Codex %60, {s}: Codex seçilir", hv(ilk) == "codex")
    for s in ("mekanik", "basit"):
        for m_, e_, z_ in [(x[1], x[2], MODEL[x[1]]["z"][x[2]]) for x in calis(_senaryo(**bol), s)[0][:1]]:
            dogrula(f"{s}: kazananın zekası yeter ve aşırı değil", SINIF[s]["q"] <= z_ <= SINIF[s]["q"] + 20)
    # 2026-11-08: agy tabanı 0 olunca "Flash bitmiş" = %0. agy Claude havuzu sıfıra kadar harcanabilir: mekanik iş
    # oradaki en küçük varyanta (Sonnet low, Z26) ya da Haiku'ya gider; Opus'a ve Claude Max Sonnet'e gitmez.
    haiku = dict(claude=(80, 95), codex=(100, 31), agy_gemini=(100, 0), agy_argon=(0, 0), agy_tp=(100, 80))
    ilk = calis(_senaryo(**haiku), "mekanik")[0][0]
    dogrula("Flash bitmiş, Codex tabanda: mekanik iş agy Sonnet low ya da Haiku'ya (Opus'a değil)",
            (ilk[1], ilk[2]) in (("agy-claude-sonnet-5-5", "low"), ("claude-haiku", "low"), ("claude-haiku", "medium")))
    haiku_tp0 = dict(claude=(80, 95), codex=(100, 31), agy_gemini=(100, 0), agy_argon=(0, 0), agy_tp=(100, 0))
    ilk = calis(_senaryo(**haiku_tp0), "mekanik")[0][0]
    dogrula("agy ve Codex bitmiş: mekanik iş Haiku'ya (Sonnet/Opus'a değil)", ilk[1] == "claude-haiku")
    ilk = calis(_senaryo(**bol), "kritik")[0][0]
    dogrula("kritik: Z ≥ 57 (Opus yüksek efor)", MODEL[ilk[1]]["z"][ilk[2]] >= 57)
    sq = dict(claude=(100, 95), codex=(100, 90), agy_gemini=(100, 80), agy_argon=(0, 80), agy_tp=(100, 90))
    ilk = calis(_senaryo(**sq), "zor")[0][0]
    dogrula("zor, agy Claude havuzu bol: agy'deki Claude modeli Claude Max'ten önce", ilk[1] != "claude-sonnet" and ilk[1] != "claude-opus")
    taban = dict(claude=(100, 95), codex=(100, 30.5), agy_gemini=(100, 80), agy_argon=(0, 80), agy_tp=(100, 80))
    dogrula("Codex haftalık %30.5: Codex seçilmez", all(hv(x) != "codex" for x in calis(_senaryo(**taban), "normal")[0]))
    c5 = dict(claude=(16, 95), codex=(100, 31), agy_gemini=(100, 3), agy_argon=(0, 3), agy_tp=(100, 3))
    son, red = calis(_senaryo(**c5), "kod")
    dogrula("Claude 5s %16 (lider payı 15): Claude alt ajana verilmez", all(hv(x) != "claude" for x in son))
    cx5 = dict(claude=(100, 95), codex=(2, 90), agy_gemini=(100, 3), agy_argon=(0, 3), agy_tp=(100, 3))
    son, red = calis(_senaryo(**cx5), "normal")
    dogrula("Codex 5s dolu, haftalık bol: başka havuz devralır", son and hv(son[0]) != "codex" and any("5s'e sığmaz" in r[2] for r in red))
    son, _ = calis(_senaryo(**bol), "gorsel")
    dogrula("görsel üretim yalnız Sol high (kullanıcı kuralı)", [(x[1], x[2]) for x in son] == [("gpt-6.1-sol", "high")])
    son, _ = calis(_senaryo(**taban), "gorsel")
    dogrula("görsel, Codex tabanda: model yok (kullanıcıya sor)", son == [])
    try:
        model_coz("fable")
        dogrula("--zorla fable reddedilir", False)
    except Hata:
        dogrula("--zorla fable reddedilir", True)
    son, _ = calis(_senaryo(**bol), "kritik", dog="claude-opus")
    dogrula("kritik doğrulayıcı (yazan Opus): farklı aileden bulunur", son and aile(son[0][1]) != "claude")
    son, _ = calis(_senaryo(**bol), "normal", kural={"yasak": {"gpt-6.1-terra"}})
    dogrula("proje yasağı uygulanır", all(x[1] != "gpt-6.1-terra" for x in son))
    ilk = calis(_senaryo(**bol), "zor", mod="ultra")[0][0]
    dogrula("ultra, zor: bir kademe akıllı (Z ≥ 53)", MODEL[ilk[1]]["z"][ilk[2]] >= 53)
    ilk = calis(_senaryo(**bol), "kritik", mod="ultra")[0][0]
    dogrula("ultra, kritik: hâlâ seçilebilir aday var (Z ≥ 57)", MODEL[ilk[1]]["z"][ilk[2]] >= 57)
    for s in ("mekanik", "normal", "kod"):
        son, _ = calis(_senaryo(**bol), s, mod="hafif")
        dogrula(f"hafif, {s}: Claude Max seçilmez ve zeka yeter", hv(son[0]) != "claude"
                and MODEL[son[0][1]]["z"][son[0][2]] >= SINIF[s]["q"])
    son, _ = calis(_senaryo(**taban), "normal", mod="ultra")
    dogrula("ultra da Codex %30 tabanını delmez", all(hv(x) != "codex" for x in son))
    kit = {"claude": {"5s": [80, None], "hafta": [35, None]}}
    dogrula("otomatik: Claude haftalığı %35 ise hafif", mod_sec("otomatik", "kod", kit)[0] == "hafif")
    dogrula("otomatik: kritik iş ve Claude bol ise ultra", mod_sec(None, "kritik", {"claude": {"5s": [90, None], "hafta": [90, None]}})[0] == "ultra")
    dogrula("otomatik: zor iş ultra değil (Claude'u koru)", mod_sec(None, "zor", {"claude": {"5s": [90, None], "hafta": [90, None]}})[0] == "normal")
    # İşçi sayısı: otomatik modda sabit tavan yok; kullanıcı açıkça hafif/ultra derse tavan geçer
    son, _ = calis(_senaryo(**bol), "normal", mod="hafif", kaynak="kullanıcı")
    dogrula("kullanıcı 'hafif' dedi: paralel tavan ≤ 2", paralel_tavan(son, 1.0, {"_mod": "hafif", "_mod_kaynak": "kullanıcı"}, 10) <= 2)
    son, _ = calis(_senaryo(**bol), "mekanik")
    dogrula("otomatik mod, 12 bağımsız parça, bol kota: paralel 12 (sabit 4/6 tavanı yok)",
            paralel_tavan(son, 0.5, {"_mod": "normal", "_mod_kaynak": "otomatik"}, 12) == 12)
    dogrula("otomatik mod, 8 parça: işçi 8 (parça sayısını aşmaz)", paralel_tavan(son, 0.5, {"_mod": "normal"}, 8) == 8)
    dag, sig, _ = dagit(son, 1.0, {"_mod": "normal"}, 40)
    dogrula("dağıtım: 40 parça en ucuz havuzdan başlayarak dağıtılır, toplam 40", sum(x[2] for x in dag) + sig == 40
            and dag and (dag[0][0], dag[0][1]) == (son[0][1], son[0][2]))
    yakin = dict(claude=(100, 95), codex=(100, 45), agy_gemini=(100, 3), agy_argon=(0, 3), agy_tp=(100, 3))
    son, _ = calis(_senaryo(**yakin), "kod")
    dogrula("Claude'u koru: Codex %45'te bile kod işi GPT'ye (Sol/Terra ≈ Sonnet)", hv(son[0]) == "codex")
    dar = dict(claude=(100, 95), codex=(100, 32), agy_gemini=(100, 3), agy_argon=(0, 3), agy_tp=(100, 3))
    son, _ = calis(_senaryo(**dar), "kod")
    dogrula("Codex %32 (tabana 2 puan): kod işi Claude'a döner", hv(son[0]) == "claude")
    dogrula("video üretimi ve video anlama otomatik 'yapılamaz' der", all(SINIF[k].get("yapilamaz") for k in ("video-uret", "video-anlama")))
    for s in ("mekanik", "basit"):
        ilk = calis(_senaryo(**bol), s)[0][0]
        dogrula(f"{s}: Opus/Sol/Sonnet'e gitmez", ilk[1] not in ("claude-opus", "gpt-6.1-sol", "claude-sonnet", "agy-claude-opus-5-5"))
    # (a) harcanabilir havuz düz kıtlık: agy %40/%20/%10/%3'te mekanik ve basit işte İLK sırada (Codex/Haiku'ya kaymaz)
    for yuzde in (40, 20, 10, 3):
        sen = dict(claude=(100, 95), codex=(100, 90), agy_gemini=(100, yuzde), agy_argon=(0, yuzde), agy_tp=(100, yuzde))
        for s in ("mekanik", "basit"):
            ilk = calis(_senaryo(**sen), s)[0][0]
            dogrula(f"agy %{yuzde}, {s}: agy ilk sırada (sıfıra kadar harca)", hv(ilk).startswith("agy"))
    for cx in (100, 60, 35):                                       # Codex'in bolluğu agy önceliğini bozmaz
        sen = dict(claude=(100, 95), codex=(100, cx), agy_gemini=(100, 10), agy_argon=(0, 10), agy_tp=(100, 10))
        ilk = calis(_senaryo(**sen), "mekanik")[0][0]
        dogrula(f"agy %10, Codex %{cx}: mekanik agy'de", hv(ilk).startswith("agy"))
    # ---- denetim düzeltmeleri (2026-11-08, ikinci tur)
    s0 = zaman("2026-11-11T10:00Z")
    sc = _senaryo(**bol)
    sc["codex"] = {"5s": [100, "2026-11-11T13:00Z"]}
    ilk = calis(sc, "mekanik")[0][0]
    dogrula("Codex yalnız 5s döndü (haftalık yok): mekanik iş Codex'e gitmez (puan 0 açığı kapalı)", hv(ilk) != "codex")
    r_ = degerle("gpt-6-luna", "medium", 18, "mekanik", 1, {"codex": {"5s": [100.0, None]}}, oran, s0, {"_mod": "normal"})
    dogrula("degerle: karar penceresi verisi yoksa eler ('verisi yok', taban doğrulanamaz)", r_[0] is None and "verisi yok" in r_[1])
    nt = []
    t_ = eksik_doldur(temizle({"codex": {"5s": [100, None], "hafta": [float("nan"), None]},
                               "claude": {"5s": [float("nan"), None], "hafta": [90, None]}}, s0, nt), nt)
    dogrula("bozuk haftalık (NaN) atılır, %50 varsayım + 'taban doğrulanamaz' notu; Claude 5s NaN da %50 varsayım",
            t_["codex"]["hafta"][0] == 50 and t_["codex"].get("_varsayim") and t_["claude"]["5s"][0] == 50
            and any("taban doğrulanamaz" in n for n in nt))

    def tuketim(dag, son, h):
        t = {}
        for m, e, k in dag:
            dk = next(x[4] for x in son if (x[1], x[2]) == (m, e))
            if MODEL[m]["h"] == h:
                for w, hr in dk["harca"].items():
                    t[w] = t.get(w, 0.0) + k * hr
        return t
    cl_only = dict(claude=(100, 95), codex=(100, 30), agy_gemini=(100, 0), agy_argon=(0, 0), agy_tp=(100, 0))
    son, _ = calis(_senaryo(**cl_only), "normal")
    dag, _, _ = dagit(son, 1.0, {"_mod": "normal"}, 100)
    t = tuketim(dag, son, "claude")
    dogrula("toplu dağıtım (100 parça): Claude 5s ve haftalık BEKLENEN tüketim (p, 5s payı dahil) tabana kadar kalanı aşmaz",
            dag and t.get("5s", 0) <= 85 and t.get("hafta", 0) <= 65)
    cx60 = dict(claude=(100, 95), codex=(100, 60), agy_gemini=(100, 0), agy_argon=(0, 0), agy_tp=(100, 0))
    son, _ = calis(_senaryo(**cx60), "normal")
    dag, _, _ = dagit(son, 1.0, {"_mod": "normal"}, 100)
    t = tuketim(dag, son, "codex")
    dogrula("toplu dağıtım: Codex haftalık %30 tabanı ve 5s %100 beklenen tüketimle aşılmaz",
            dag and t.get("hafta", 0) <= 30 and t.get("5s", 0) <= 100)
    son, _ = calis(_senaryo(**bol), "mekanik")
    k_ = {"_mod": "normal", "_mod_kaynak": "otomatik"}
    dag, sig, oz = dagit(son, 0.5, k_, 200)
    dogrula("paralel (--parca) = dağılımın eşzamanlı toplamı (ilk 4 aday kırpması yok)",
            paralel_tavan(son, 0.5, k_, 200) == max(1, sum(o["eszamanli"] for o in oz.values()))
            and sum(x[2] for x in dag) + sig == 200)
    a5 = dict(claude=(100, 95), codex=(100, 90), agy_gemini=(100, 0), agy_argon=(0, 0), agy_tp=(5, 60))
    son, red = calis(_senaryo(**a5), "kod")
    g = gerekce("kod", son, red, {"_mod": "normal"})
    dogrula("agy Claude/GPT yalnız 5 saatlikte dolu: not '5 saatlik kotası doldu' der, 'tabana yakın' demez",
            any("agy Claude/GPT 5 saatlik kotası doldu" in n for n in g) and not any("tabana yakın" in n for n in g))
    hepsi2 = dict(claude=(100, 30.5), codex=(100, 30.5), agy_gemini=(100, 0), agy_argon=(0, 0), agy_tp=(100, 0))
    sc = _senaryo(**hepsi2)
    son, red = calis(sc, "normal")
    hm_ = temizle({k: v for k, v in json.loads(json.dumps(sc)).items() if k != "_simdi"}, s0, [])
    b_ = en_erken_cozum(red, hm_, s0)
    dogrula("uygun model yok, engeller haftalık: bekleme haftalık resetten (≈84 sa), 5 saatlikten (3 sa) değil",
            son == [] and b_ is not None and b_ > 50)
    hm_ = temizle({k: v for k, v in json.loads(json.dumps(_senaryo(**bol))).items() if k != "_simdi"}, s0, [])
    r_ = degerle("gpt-6.1-terra", "high", 42, "normal", 1, hm_, oran, s0, {"_mod": "normal", "_sure_dk": 5})
    dogrula("--sure-dk ile dk_ib'siz model (Codex) 'süre bilinmiyor' notu alır", r_[0] is not None and "süre bilinmiyor" in r_[1])
    dogrula("Argon high 1 İB ≈ 28 dk (efor çarpanı iki kez uygulanmaz)", abs(tahmini_dk("gemini-4-argon", "high", 1, {}) - 28) < 0.5)
    # platform dosyası: yalnız OpenCode Go (Kimi) + Codex olan bir kullanıcı; sonra yerleşik tablolar geri yüklenir
    yedek = copy.deepcopy((HAVUZ, MODEL, SINIF, YASAK, OZEL_KOTA, TAKMA, YUKLEME_NOTLARI))

    def geri_yukle():
        h_, m_, si_, y_, o_, t_, n_ = copy.deepcopy(yedek)
        HAVUZ.clear(); HAVUZ.update(h_); MODEL.clear(); MODEL.update(m_)
        SINIF.clear(); SINIF.update(si_); YASAK.clear(); YASAK.update(y_); OZEL_KOTA.clear(); OZEL_KOTA.update(o_)
        TAKMA.clear(); TAKMA.update(t_); YUKLEME_NOTLARI[:] = n_

    def yukle(icerik, simdi=None, env=None):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(icerik, f)
        try:
            return platformlari_yukle(f.name, simdi=simdi, env=env)
        finally:
            os.unlink(f.name)
    try:
        ornek = {"kapali": ["claude", "agy_gemini", "agy_argon", "agy_tp"],
                 "havuz": {"opencode_go": {"taban": {"hafta": 10}, "agirlik": 0.6, "ad": "OpenCode Go"}},
                 "model": {"kimi-k2": {"h": "opencode_go", "aile": "kimi", "o": {"hafta": 1.0},
                                       "z": {"medium": 44, "high": 48}, "cagri": "opencode run -m kimi-k2"}}}
        yukle(ornek)
        oran.update({m: dict(d["o"]) for m, d in MODEL.items() if m not in oran})
        s_ = {"_simdi": "2026-11-11T10:00Z", "codex": {"hafta": [90, "2026-11-14T22:00Z"]},
              "opencode_go": {"hafta": [80, "2026-11-14T22:00Z"]}}
        son, _ = calis(s_, "normal")
        dogrula("platform dosyası: Claude kapalıyken Claude modeli önerilmez", son and all(hv(x) != "claude" for x in son))
        dogrula("platform dosyası: yeni havuz (OpenCode Go/Kimi) aday olur", any(x[1] == "kimi-k2" for x in son))
    finally:
        geri_yukle()
    # (i) eklenen havuzun eksik alanları belgedeki varsayılanla (taban %10, ağırlık 1.0) doldurulur
    try:
        yukle({"havuz": {"yeni": {"ad": "Yeni"}}, "model": {"yeni-m": {"h": "yeni", "aile": "x", "o": {"hafta": 1},
                                                                        "z": {"medium": 40}, "cagri": "x"}}})
        dogrula("yeni havuz varsayılanı: taban hafta %10, ağırlık 1.0, w5 0",
                taban_al("yeni", "hafta") == 10 and HAVUZ["yeni"]["agirlik"] == 1.0 and HAVUZ["yeni"]["w5"] == 0.0)
    finally:
        geri_yukle()
    try:
        yukle({"havuz": {"bed": {"ad": "Bed", "bedava": True, "karar": "gun"}},
               "model": {"bed-m": {"h": "bed", "aile": "x", "o": {"gun": 1}, "z": {"medium": 30}, "cagri": "x"}}})
        dogrula("yeni bedava havuz taban yazmazsa taban 0 (belgedeki gibi, %10 değil)", taban_al("bed", "gun") == 0)
    finally:
        geri_yukle()
    for kotu in ("a", -5, 120, True):
        try:
            yukle({"havuz": {"x": {"ad": "X", "taban": {"hafta": kotu}}}})
            dogrula(f"havuz.taban {kotu!r} → Hata (TypeError izi değil)", False)
        except Hata:
            dogrula(f"havuz.taban {kotu!r} → Hata (TypeError izi değil)", True)
        finally:
            geri_yukle()
    # gerekçe: limit zorlayınca söyler, bol kotada boş yere söylemez, ucuz yeterliyse zekâ fazlası demez
    cxt = dict(claude=(100, 95), codex=(100, 29), agy_gemini=(100, 3), agy_argon=(0, 3), agy_tp=(100, 3))
    son, red = calis(_senaryo(**cxt), "kod")
    g = gerekce("kod", son, red, {"_mod": "normal"})
    dogrula("Codex tabanda, kod Claude'a: 'limit zorladı' notu Codex'i anar", any("limit zorladı" in n and "Codex" in n for n in g))
    son, red = calis(_senaryo(**bol), "kod")
    dogrula("bol kota, kod: 'limit zorladı' notu yok", not any("limit zorladı" in n for n in gerekce("kod", son, red, {"_mod": "normal"})))
    son, red = calis(_senaryo(**bol), "mekanik")
    dogrula("bol kota, mekanik: zekâ fazlası uyarısı yok", not any("zekâ fazlası" in n for n in gerekce("mekanik", son, red, {"_mod": "normal"})))
    # (e) taban 0 havuz için "kota bitti" (tabana yakın değil); agy bitince Codex'e kayışta da not
    agy0 = dict(claude=(100, 95), codex=(100, 90), agy_gemini=(100, 0), agy_argon=(0, 0), agy_tp=(100, 0))
    son, red = calis(_senaryo(**agy0), "normal")
    g = gerekce("normal", son, red, {"_mod": "normal"})
    dogrula("agy bitti, normal Codex'e: not 'agy ... kotası bitti' der, 'tabana yakın' demez",
            hv(son[0]) == "codex" and any("kotası bitti" in n and "agy" in n and "limit zorladı" in n for n in g)
            and not any("agy" in n and "tabana yakın" in n for n in g))
    # (d) 'uygun model yok': havuz başına gerçek neden (kota/taban), zekâsı yetmeyen varyantın notu değil
    hepsi = dict(claude=(100, 30.5), codex=(100, 30.5), agy_gemini=(100, 0), agy_argon=(0, 0), agy_tp=(100, 0))
    son, red = calis(_senaryo(**hepsi), "normal")
    yn = _yok_nedeni(red)
    dogrula("uygun model yok: Codex ve Claude nedeni taban, 'zeka yetmez' değil",
            son == [] and "taban" in yn.get("codex", "") and "taban" in yn.get("claude", "") and "zeka" not in yn.get("codex", ""))
    # (f) proje ağırlığı 0.15 kırpılmaz (alt sınır 0.01)
    with tempfile.TemporaryDirectory() as td:
        with open(os.path.join(td, ".orkestra.json"), "w", encoding="utf-8") as f:
            json.dump({"agirlik": {"codex": 0.15}, "gizli": True, "yasak_havuz": ["agy_tp"]}, f)
        with contextlib.redirect_stdout(io.StringIO()):
            pk, _ = proje_kurali(td)
    dogrula(".orkestra.json ağırlığı 0.15 korunur (0.2'ye kırpılmaz)", pk["agirlik"].get("codex") == 0.15)
    dogrula(".orkestra.json gizli ve yasak_havuz okunur", pk["gizli"] is True and pk["yasak_havuz"] == {"agy_tp"})
    with tempfile.TemporaryDirectory() as td:
        with open(os.path.join(td, ".orkestra.json"), "w", encoding="utf-8") as f:
            json.dump({"gizli": "true", "yasak_havuz": [" Agy_TP "]}, f)
        with contextlib.redirect_stdout(io.StringIO()) as o_, contextlib.redirect_stderr(io.StringIO()):
            pk, _ = proje_kurali(td)
    dogrula(".orkestra.json gizli \"true\" (metin) → güvenli tarafta gizli + UYARI; yasak_havuz büyük harf/boşluk normalize",
            pk["gizli"] is True and "UYARI" in o_.getvalue() and pk["yasak_havuz"] == {"agy_tp"})
    with contextlib.redirect_stderr(io.StringIO()) as e_:
        hn = havuz_adlari(["Evren", "EVREN", "codex"], "--haric")
    dogrula("--haric Evren/EVREN → 'evren' (büyük-küçük harf duyarsız), tanımsız ad UYARI", hn == {"evren", "codex"}
            and "UYARI" in e_.getvalue())
    # (h)(9) Claude haftalık %30 ve 5s %15, Codex %30: hiçbir modda delinmez
    for mod_ in ("hafif", "normal", "ultra"):
        cl30 = dict(claude=(100, 30.5), codex=(100, 90), agy_gemini=(100, 3), agy_argon=(0, 3), agy_tp=(100, 3))
        son, _ = calis(_senaryo(**cl30), "zor", mod=mod_)
        dogrula(f"{mod_}: Claude haftalık %30.5 → Claude seçilmez", all(hv(x) != "claude" for x in son))
        cl15 = dict(claude=(15.5, 90), codex=(100, 30.5), agy_gemini=(100, 3), agy_argon=(0, 3), agy_tp=(100, 3))
        son, _ = calis(_senaryo(**cl15), "kod", mod=mod_)
        dogrula(f"{mod_}: Claude 5s %15.5 ve Codex %30.5 → ikisi de seçilmez", all(hv(x) not in ("claude", "codex") for x in son))
    # (j) agy oranları tahmin işaretli
    dogrula("agy oranları 'tahmin' işaretli ve not metninde görünür",
            all(MODEL[m].get("o_kaynak") == "tahmin" for m in AGY_AD)
            and any("oran tahmin" in x[3] for x in calis(_senaryo(**bol), "mekanik")[0] if hv(x).startswith("agy")))
    # (b)(c) agy çağrısı: zaman aşımı işin büyüklüğüne göre; düzenleme işi accept-edits, salt okunur iş plan
    c_ = cagri_yap("gemini-4-argon", "high", {"_mod": "normal"}, 3.0)
    dk_ = int(c_.split("--print-timeout ")[1].rstrip("m"))
    dogrula("agy Argon 3 İB: --print-timeout 180s değil, ≥ 3 × tahmini süre", "180s" not in c_ and dk_ >= 3 * 3 * 28)
    dogrula("agy salt okunur iş --mode plan, düzenleyen iş --mode accept-edits",
            "--mode plan" in cagri_yap("gemini-3.8-flash", "low", {}, 1) and
            "--mode accept-edits" in cagri_yap("gemini-3.8-flash", "low", {"_duzenle": True}, 1))
    dogrula("efor çarpanı model başına (Sonnet max ≈ 11.75, genel 4.5 değil)", efor_carpan("claude-sonnet", "max") > 10)
    MODEL["test-efor"] = dict(h="codex", aile="test", o={"hafta": 0.3}, ec={"low": 0.7, "high": 0.85},
                              z={"low": 41, "high": 43}, cagri="x")
    oran["test-efor"] = {"hafta": 0.3}
    son, _ = calis(_senaryo(**bol), "normal")
    dogrula("efor seçici: aynı modelin eforları puanca %10 içindeyse ucuz efor (low, high'dan %7 kötü)",
            [x[2] for x in son if x[1] == "test-efor"] == ["low"])
    MODEL.pop("test-efor")
    oran.pop("test-efor")
    # sürü formülü (tasarım 4.2)
    dogrula("suru_dz(28, 41, test, 8) == 0 (s=0: normal işte sürü yetmez)", suru_dz(28, 41, "test", 8) == 0)
    dogrula("suru_dz(21, 22, kapali, 3) ≈ 2.2", abs(suru_dz(21, 22, "kapali", 3) - 2.22) < 0.05)
    dogrula("yöntem yok / testi EVREN yazdı → ΔZ = 0", suru_dz(27, 22, "yok", 5) == 0 and suru_dz(27, 22, "test", 8, test_evren=True) == 0)
    dogrula("test N=100, k=5 olsa bile ΔZ ≤ 8 (k ≤ 1)", suru_dz(30, 30, "test", 100, k=5) <= 8.0001)
    dogrula("karışık sürü: Z20 + Z27 reddedilir, ds 27 + glm 28 olur", not karisim_uygun([20, 27]) and karisim_uygun([27, 28]))
    # ---- bedava platform (EVREN benzeri) testleri
    SAHTE = "SAHTE-ANAHTAR-DEGERI-123"
    env = {"ORKESTRA_TEST_ANAHTAR": SAHTE}
    simdi0 = zaman("2026-11-11T10:00Z")
    try:
        yukle(TEST_BEDAVA, simdi=simdi0, env=env)
        oran.update({m: dict(d["o"]) for m, d in MODEL.items()})
        dogrula("bedava platform yüklendi; sahte anahtar değeri hiçbir tabloda/notta yok", "evren" in HAVUZ and SAHTE not in
                json.dumps([HAVUZ, MODEL, YUKLEME_NOTLARI, OZEL_KOTA], default=str))

        def evs(yuzde, **ek):
            s = _senaryo(**{**bol, **ek})
            s["evren"] = {"gun": [yuzde, "2026-11-12T00:00Z"]}
            return s
        G = {"_veri": "genel"}
        for s in ("mekanik", "basit"):
            ilk = calis(evs(100), s, kural=G)[0][0]
            dogrula(f"EVREN bol, {s}, --veri genel: ilk aday EVREN (agy'den önce)", hv(ilk) == "evren")
        ilk = calis(evs(100), "basit", kural=G)[0][0]
        dogrula("basit: EVREN ilk ve Z ≥ 22 (glm low 21 elenir)", hv(ilk) == "evren" and MODEL[ilk[1]]["z"][ilk[2]] >= 22)
        for s in ("arastirma", "normal", "kod", "zor", "kritik"):
            son, _ = calis(evs(100), s, kural=G)
            dogrula(f"{s}: hiçbir EVREN varyantı yok (Z ≤ 28 < Q)", all(hv(x) != "evren" for x in son))
        ham_ = temizle(evs(100), simdi0, [])
        kg = {"_mod": "normal", "_veri": "genel"}
        p_low = degerle("evren-glm-5.3", "low", 21, "mekanik", 1, ham_, oran, simdi0, kg)[0]
        p_high, _, dk_high = degerle("evren-glm-5.3", "high", 28, "mekanik", 1, ham_, oran, simdi0, kg)
        dogrula("mekanik: glm low, glm high'ın önünde (fazla-zeka cezası)", p_low < p_high and dk_high["fazla"] > 1)
        for v in ("bilinmiyor", "kisisel", "saglik", "gizli"):
            son, red = calis(evs(100), "mekanik", kural={"_veri": v})
            dogrula(f"--veri {v}: EVREN elenir, neden 'veri'", all(hv(x) != "evren" for x in son)
                    and any("veri" in r[2] for r in red if MODEL[r[0]]["h"] == "evren"))
        son, _ = calis(evs(100), "mekanik", kural={"_veri": "gizli", "gizli": True})
        dogrula("proje gizli: EVREN yok", all(hv(x) != "evren" for x in son))
        son, _ = calis(evs(100), "mekanik", kural={"_veri": "genel", "yasak_havuz": {"evren"}})
        son2, _ = calis(evs(100), "mekanik", kural={"_veri": "genel", "_haric": {"evren"}})
        dogrula("yasak_havuz ve --haric: EVREN yok", all(hv(x) != "evren" for x in son + son2))
        for yuzde in (20, 10):
            for s in ("mekanik", "basit"):
                ilk = calis(evs(yuzde), s, kural=G)[0][0]
                dogrula(f"EVREN günlük %{yuzde}, {s}: hâlâ ilk (düz kıtlık)", hv(ilk) == "evren")
        son, red = calis(evs(0), "mekanik", kural=G)
        dogrula("EVREN %0: elenir ('kotası bitti'), agy devralır", hv(son[0]).startswith("agy")
                and any("bitti" in r[2] for r in red if MODEL[r[0]]["h"] == "evren"))
        nt = []
        t_ = temizle({"evren": {"gun": [5, "2026-11-10T00:00Z"]}}, simdi0, nt)
        dogrula("gun reseti geçmiş: %100 sayılır, pencere atılmaz", t_["evren"]["gun"][0] == 100.0)
        dogrula("kota satırında gun penceresi ve [bedava] görünür", any("gun " in x and "[bedava]" in x for x in
                kota_satirlari({"evren": {"gun": [50.0, None]}}, simdi0)))
        hm = {}
        nt = []
        vs = ozel_kota_ekle(hm, A, nt)
        dogrula("anahtar var, kota okunamadı: %80, pencere gun, ağırlık ×1 (bedava)", hm["evren"]["gun"][0] == 80
                and "evren" in vs and havuz_agirligi("evren", {"evren": {"_varsayim": True}}, {}, simdi0) == HAVUZ["evren"]["agirlik"])
        s80 = evs(80)
        s80["evren"]["_varsayim"] = True
        ilk = calis(s80, "mekanik", kural=G)[0][0]
        dogrula("kota varsayım %80 iken mekanikte hâlâ EVREN ilk", hv(ilk) == "evren")
        son, red = calis(evs(100), "mekanik", kural={"_veri": "genel", "_sure_dk": 10, "_duzenle": True})
        dogrula("--sure-dk 10 + düzenleme işi: EVREN Codex ajanı 'süreye sığmaz'", all(hv(x) != "evren" for x in son)
                and any("süreye sığmaz" in r[2] for r in red if MODEL[r[0]]["h"] == "evren"))
        son, red = calis(evs(100), "mekanik", kural={"_veri": "genel", "_sure_dk": 10})
        dogrula("--sure-dk 10, metin işi: doğrudan çağrı (ds-nr/glm low) sığar", son and hv(son[0]) == "evren")
        c_ = cagri_yap(son[0][1], son[0][2], {"_veri": "genel"}, 1)
        dogrula("metin işi çağrısı doğrudan HTTP betiği (Codex değil), --veri genel dolu", "evren_suru" in c_ and "codex" not in c_
                and "--veri genel" in c_)
        c_ = cagri_yap("evren-glm-5.3", "high", {"_veri": "genel", "_duzenle": True}, 1)
        dogrula("dosya düzenleyen iş: codex exec -p evren", c_.startswith("codex exec -p evren"))
        ilk = calis(evs(100), "mekanik", kural={"_veri": "genel", "_duzenle": True})[0][0]
        dogrula("--duzenle, süre bütçesi yok: EVREN Codex ajanı (günlük %8/İB = haftalık eşdeğer %1.1) agy'den önce",
                hv(ilk) == "evren" and cagri_yap(ilk[1], ilk[2], {"_veri": "genel", "_duzenle": True}, 1).startswith("codex exec -p evren"))
        son, red = calis(evs(100), "mekanik", kural={"_veri": "genel", "_duzenle": True})
        dogrula("--duzenle: ds-nr (thinking kapalı, Codex'ten verilemez) elenir", any(r[0] == "evren-deepseek-v4.1-flash-nr"
                and "düzenleyemez" in r[2] for r in red))
        # sürü
        son, red = calis(evs(100), "basit", kural={"_veri": "genel", "_yontem": "kapali"})
        k_ = {"_mod": "normal", "_veri": "genel", "_yontem": "kapali"}
        ham_ = temizle(evs(100), simdi0, [])
        so = suru_oner("basit", 1.0, ham_, oran, simdi0, k_, son, red)
        dogrula("basit + kapali: glm low ×3 için sürü önerilir (etkin Z ≥ 22, hakem yok)", so and so["model"] == "evren-glm-5.3"
                and so["efor"] == "low" and so["n0"] == 3 and so["z_etkin"] >= 22 and so["hakem"] is None)
        MODEL["evren-hayali"] = {"h": "evren", "aile": "hayal", "o": {"gun": 0.5}, "z": {"high": 33}, "cagri": "x",
                                 "suru_cagri": "evren_suru --n {n} --yontem {y} --veri {veri}"}
        oran["evren-hayali"] = {"gun": 0.5}
        MODEL["evren-hayali"]["z"]["high"] = 38                     # z_tavan yalnız yüklemede: hayali 38'lik model
        kt = {"_mod": "normal", "_veri": "genel", "_yontem": "test"}
        son, red = sirala("normal", 1.0, ham_, oran, simdi0, kt)
        so = suru_oner("normal", 1.0, ham_, oran, simdi0, kt, son, red)
        dogrula("hayali Z38, normal, test: etkin Z ≥ 41 ve 'KASKAD: önce dene', hakem bedava değil",
                so and so["model"] == "evren-hayali" and so["z_etkin"] >= 41 and so["etiket"].startswith("KASKAD")
                and so["hakem"] and not HAVUZ[MODEL[so["hakem"].split(":")[0]]["h"]].get("bedava"))
        MODEL["evren-hayali"]["z"]["high"] = 48
        for s in ("zor", "kritik"):
            son, red = sirala(s, 1.0, ham_, oran, simdi0, dict(kt))
            dogrula(f"{s}: hayali Z48'de bile sürü önerisi yok", suru_oner(s, 1.0, ham_, oran, simdi0, dict(kt), son, red) is None)
        MODEL["evren-hayali"]["z_kaynak"] = "tahmin"
        MODEL["evren-hayali"]["z"]["high"] = 40
        son, red = sirala("arastirma", 1.0, ham_, oran, simdi0, {"_mod": "normal", "_veri": "genel"})
        dogrula("z_kaynak tahmin, Z40: Q≥38 işte elenir", all(x[1] != "evren-hayali" for x in son))
        MODEL.pop("evren-hayali")
        oran.pop("evren-hayali")
        bozuk = copy.deepcopy(TEST_BEDAVA)
        bozuk["model"]["evren-glm-5.3"]["z"]["high"] = 43
        try:
            yukle(bozuk, simdi=simdi0, env=env)
            dogrula("bedava havuzda Z > z_tavan 33 → yükleme Hata (eski ölçek koruması)", False)
        except Hata:
            dogrula("bedava havuzda Z > z_tavan 33 → yükleme Hata (eski ölçek koruması)", True)
        kk = {"_mod": "normal", "_veri": "genel", "_yontem": "kapsam"}
        son, red = sirala("arastirma", 1.0, ham_, oran, simdi0, kk)
        MODEL["evren-hayali"] = {"h": "evren", "aile": "hayal", "o": {"gun": 0.5}, "z": {"high": 36}, "cagri": "x"}
        oran["evren-hayali"] = {"gun": 0.5}
        son, red = sirala("arastirma", 1.0, ham_, oran, simdi0, kk)
        so = suru_oner("arastirma", 1.0, ham_, oran, simdi0, kk, son, red)
        dogrula("kapsam birleştiricisi Haiku olmaz (Z30 < 38)", so is None or not so["hakem"].startswith("claude-haiku"))
        hm2 = temizle(evs(100, codex=(100, 30.5)), simdi0, [])
        son, red = sirala("arastirma", 1.0, hm2, oran, simdi0, kk)
        so = suru_oner("arastirma", 1.0, hm2, oran, simdi0, kk, son, red)
        dogrula("Codex %30.5 iken hakem Codex'ten seçilmez", so is None or MODEL[so["hakem"].split(":")[0]]["h"] != "codex")
        MODEL.pop("evren-hayali")
        oran.pop("evren-hayali")
        son, _ = calis(evs(100, codex=(100, 30.5)), "normal", kural=G)
        son2, _ = calis(evs(100, claude=(16, 95), codex=(100, 31)), "kod", kural=G)
        dogrula("EVREN yüklüyken Codex %30.5 seçilmez; Claude 5s %16 kuralı aynen", all(hv(x) != "codex" for x in son)
                and all(hv(x) != "claude" for x in son2))
        with open(KALITE, "w", encoding="utf-8") as f:
            for i in range(20):
                f.write(json.dumps({"model": "evren-glm-5.3", "efor": "low", "yontem": "kapali", "kabul": 1 if i < 14 else 0}) + "\n")
        _KALITE_ONB.clear()
        son, red = calis(evs(100), "basit", kural={"_veri": "genel", "_yontem": "kapali"})
        so = suru_oner("basit", 1.0, ham_, oran, simdi0, {"_mod": "normal", "_veri": "genel", "_yontem": "kapali"}, son, red)
        dogrula("kalite kaydı kabul 0.7 (20 kayıt) → k = 0, glm low sürüsü önerilmez", kalite_k("evren-glm-5.3", "kapali") == 0
                and not (so and so["model"] == "evren-glm-5.3" and so["efor"] == "low"))
        os.unlink(KALITE)
        _KALITE_ONB.clear()
        son, _ = calis(evs(100), "mekanik", kural=G)
        dogrula("bedava kazanırsa işçi tavanı EVREN eşzamanlılığından (≤ esz−2), sabit 4 değil",
                4 < paralel_tavan(son, 0.5, {"_mod": "normal", "_veri": "genel"}, 30) <= 30)
        dogrula("düzenleyen EVREN ajanı tavanı paralel_ajan 8", havuz_kapasite("evren", son[0][4], 0.5, {"_duzenle": True}) <= 8)
        son, _ = calis(evs(100), "basit", 0.5, kural=G)
        kg2 = {"_mod": "normal", "_veri": "genel"}
        dag, sig, oz = dagit(son, 0.5, kg2, 200)
        dogrula("200 parça basit, EVREN günlüğe sığar: hepsi EVREN'de dalga halinde (eşzamanlılık kapasite sayılmaz)",
                sig == 0 and dag and all(MODEL[m]["h"] == "evren" for m, _, _ in dag) and oz["evren"]["dalga"] >= 2
                and oz["evren"]["eszamanli"] <= 22)
        dag, sig, oz = dagit(son, 0.5, dict(kg2, _sure_dk=20), 200)
        dogrula("--sure-dk 20: EVREN dalga sayısı süreye göre sınırlanır, kalan parça sıradaki havuza",
                oz["evren"]["adet"] <= 2 * 22 and any(MODEL[m]["h"] != "evren" for m, _, _ in dag))
        son, _ = calis(evs(100), "mekanik", 0.5, kural=G, mod="hafif", kaynak="kullanıcı")
        dag, _, _ = dagit(son, 0.5, {"_mod": "hafif", "_mod_kaynak": "kullanıcı", "_veri": "genel"}, 50)
        dogrula("kullanıcı 'hafif': işçi tavanı (2) yalnız ücretli havuzlara; bedava EVREN 50 parçanın hepsini alır",
                sum(k for m, _, k in dag if MODEL[m]["h"] == "evren") == 50)
        # ---- EVREN soğuma (sahte durum: kota_oku.soguma_oku biçimi) ve stratejik geri dönüş
        km_ = kota_modulu()

        def sgham(d):
            return {ad: {"tur": t, "ardisik": n, "busy_until": datetime.fromtimestamp(simdi0.timestamp() + dk * 60,
                                                                                       timezone.utc).isoformat()}
                    for ad, (dk, t, n) in d.items()}

        def sgd(d):
            return km_.soguma_oku(simdi0, sgham(d))
        Gs = dict(G, _soguma=sgd({"glm-5.3": (12, "503", 1)}))
        son, red = calis(evs(100), "basit", kural=Gs)
        es = evren_soguma_durumu(son, red, Gs, 22)
        dogrula("glm soğumada (12 dk): basit iş aynı Z bandındaki kardeş deepseek'e (EVREN kalır), glm 'soğuma' ile elenir",
                son and son[0][1] == "evren-deepseek-v4.1-flash" and any(r[0] == "evren-glm-5.3" and "soğuma" in r[2] for r in red)
                and any("kardeş" in n for n in soguma_notlari(es, son, Gs, 22)))
        Gt = dict(G, _soguma=sgd({"*": (12, "503", 1)}))
        for s_, q_ in (("mekanik", 16), ("basit", 22)):
            son, red = calis(evs(100), s_, kural=Gt)
            nt = soguma_notlari(evren_soguma_durumu(son, red, Gt, q_), son, Gt, q_)
            dogrula(f"'*' soğuma 12 dk, {s_}: EVREN aday dışı, yedek Z ≥ Q{q_} (eşik delinmez), not 'EVREN dolu' + BEKLE",
                    son and all(hv(x) != "evren" for x in son) and all(MODEL[x[1]]["z"][x[2]] >= q_ for x in son)
                    and any(n.startswith("EVREN dolu") for n in nt) and any(n.startswith("BEKLE") for n in nt))
        Ga = dict(Gt, _sure_dk=5)
        son, red = calis(evs(100), "basit", kural=Ga)
        nt = soguma_notlari(evren_soguma_durumu(son, red, Ga, 22), son, Ga, 22)
        dogrula("acil iş (--sure-dk 5 < soğuma 12 dk): BEKLE önerilmez", son and not any(n.startswith("BEKLE") for n in nt))
        Gd = dict(G, _soguma=sgd({"*": (14 * 60, "daily", 1)}))
        son, red = calis(evs(100), "basit", kural=Gd)
        nt = soguma_notlari(evren_soguma_durumu(son, red, Gd, 22), son, Gd, 22)
        dogrula("günlük kota soğuması (14 sa): EVREN yok, BEKLE yok, 'bekleme önerilmez' ve 03:00 TSİ notu",
                son and all(hv(x) != "evren" for x in son) and not any(n.startswith("BEKLE") for n in nt)
                and any("önerilmez" in n and "03:00" in n for n in nt))
        Gy = dict(G, _soguma=sgd({"glm-5.3": (-5, "503", 2)}))
        son, red = calis(evs(100), "basit", kural=Gy)
        nt = soguma_notlari(evren_soguma_durumu(son, red, Gy, 22), son, Gy, 22)
        dogrula("soğuma bitti (5 dk önce): EVREN yeniden aday, not 'ping ile yoklar'", son and hv(son[0]) == "evren"
                and any("ping" in n for n in nt))
        dogrula("süresi 2 saat önce dolmuş kayıt yok sayılır", sgd({"glm-5.3": (-120, "503", 1)}) == {})
        son, red = calis(evs(100), "mekanik", 0.5, kural=Gs)
        es = evren_soguma_durumu(son, red, Gs, 16)
        dag, sig, _ = dagit(son, 0.5, dict(G, _mod="normal", _evren_pay=KISMI_PAY), 40)
        ev_n = sum(k for m, _, k in dag if MODEL[m]["h"] == "evren")
        dogrula("KISMİ GEÇİŞ (dalgalı: glm soğumada) + 40 parça → EVREN ≤ 20, kalan başka havuza, hepsi yerleşir",
                es and es["riskli"] and 0 < ev_n <= 20 and sig == 0 and sum(x[2] for x in dag) == 40)

        def sec_cikti(senaryo, **ek):
            with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
                json.dump(senaryo, f)
            ns = argparse.Namespace(senaryo=f.name, fresh=False, claude_5s=None, claude_hafta=None, claude_5s_reset=None,
                                    claude_hafta_reset=None, kota=None, proje=None, veri="genel", sure_dk=None, yontem="yok",
                                    min_z=None, baglam=None, duzenle=False, parca=None, test_evren=False, haric=None,
                                    dogrulayici=None, sinif="basit", zorla=None, mod="otomatik", is_=0.5, json=True, rol=None)
            vars(ns).update(ek)
            buf = io.StringIO()
            try:
                with contextlib.redirect_stdout(buf):
                    sec(ns)
            finally:
                os.unlink(f.name)
            return buf.getvalue()
        sen = dict(evs(100), _soguma=sgham({"*": (12, "503", 1)}))
        out_ = sec_cikti(sen, parca=40)
        j = json.loads(out_.split("JSON ", 1)[1].splitlines()[0])["basit"]
        dogrula("sec (sahte durum '*' 12 dk, 40 parça): 'EVREN dolu' + BEKLE + KISMİ GEÇİŞ (bekle) 20 şimdi / 20 kuyruk",
                "EVREN dolu" in out_ and "BEKLE" in out_ and "KISMİ GEÇİŞ (bekle)" in out_ and j["kismi"]["simdi"] == 20
                and j["kismi"]["kuyruk"] == 20 and sum(int(x.split("x", 1)[0]) for x in j["dagilim"]) == 20)
        out_ = sec_cikti(dict(evs(100), _soguma=sgham({"glm-5.3": (12, "503", 1)})), parca=40, sinif="mekanik")
        dogrula("sec (glm soğumada, 40 parça mekanik): KISMİ GEÇİŞ dalgalı satırı ve EVREN SOĞUMA özeti",
                "KISMİ GEÇİŞ: EVREN dalgalı" in out_ and "EVREN SOĞUMA:" in out_)
        out_ = sec_cikti(evs(100), parca=40)
        dogrula("soğuma yoksa KISMİ/BEKLE/SOĞUMA satırı yok (davranış değişmez)",
                "KISMİ" not in out_ and "BEKLE" not in out_ and "SOĞUMA" not in out_)
        # ---- roller (nöbetçi/denetçi alt ajanlar)
        kb = {"_veri": "bilinmiyor", "_mod": "normal"}
        son, red, esik, _ = rol_sec("nobetci", "kod", 1.0, ham_, oran, simdi0, kb, "claude-sonnet")
        dogrula("--rol nobetci (kod, üreten Sonnet): eşik 20, Claude ailesi yok, ilk aday hızlı-ucuz, EVREN yok (veri bilinmiyor)",
                son and esik == 20 and all(aile(x[1]) != "claude" for x in son) and all(MODEL[x[1]]["z"][x[2]] >= 20 for x in son)
                and hizli_mi(son[0][1]) and all(hv(x) != "evren" for x in son))
        son, _, _, _ = rol_sec("nobetci", "kod", 1.0, ham_, oran, simdi0, dict(kb, _veri="genel"), "claude-sonnet")
        dogrula("--rol nobetci, veri genel: bedava EVREN nöbetçi olabilir ve öne geçer", son and hv(son[0]) == "evren")
        son, _, _, _ = rol_sec("nobetci", "kod", 1.0, ham_, oran, simdi0, kb)
        dogrula("--rol nobetci üretensiz: Opus/Sol/Argon gibi büyük model ilk değil (ucuz-hızlı önce)",
                son and son[0][1] not in ("claude-opus", "gpt-6.1-sol", "gemini-4-argon", "agy-claude-opus-5-5"))
        son, red, esik, _ = rol_sec("hakem", "kod", 1.0, ham_, oran, simdi0, dict(kb, _veri="genel"), "gpt-6.1-sol")
        dogrula("--rol hakem (kod, üreten Sol): eşik 39, GPT ailesi yok, EVREN (bedava) asla hakem değil",
                son and esik == 39 and all(aile(x[1]) != "gpt" for x in son) and all(hv(x) != "evren" for x in son)
                and all(MODEL[x[1]]["z"][x[2]] >= 39 for x in son))
        _, _, esik, _ = rol_sec("muhalif", "zor", 1.0, ham_, oran, simdi0, kb)
        _, _, esik2, _ = rol_sec("arsivci", "kritik", 1.0, ham_, oran, simdi0, kb)
        dogrula("rol eşikleri: muhalif zor → 42, arşivci kritikte bile 16", esik == 42 and esik2 == 16)
        dogrula("rol sınıfı geçici: SINIF tablosu kirlenmez", not any(k.startswith("rol-") for k in SINIF))
        # ---- denetim düzeltmeleri (2026-11-09)
        son, red, _, _ = rol_sec("nobetci", "kod", 1.0, ham_, oran, simdi0, kb, "gpt-6.1-sol")
        dogrula("--rol nobetci (üreten Sol): Opus/Sol/Argon/agy-Opus listede yok (daha ucuz aday varken son çare)",
                son and all(x[1] not in BUYUK for x in son) and any("büyük model" in r[2] for r in red))
        dogrula("ne_zaman: 1 dk altı 'saniyeler içinde' ('~0 dk sonra' değil)",
                ne_zaman(0.5) == "saniyeler içinde" and ne_zaman(12) == "~12 dk sonra")
        out_ = sec_cikti(evs(100), sinif="basit")
        j = json.loads(out_.split("JSON ", 1)[1].splitlines()[0])["basit"]
        out2_ = sec_cikti(evs(100), sinif="mekanik")
        j2 = json.loads(out2_.split("JSON ", 1)[1].splitlines()[0])["mekanik"]
        dogrula("EVREN ÇAĞRI satırı seçicinin etkin eşiğini taşır (basit --min-z 22, mekanik --min-z 16): kardeş eşiği delmez",
                "--min-z 22" in j["cagri"] and "--min-z 16" in j2["cagri"])
        olu = dict(claude=(100, 30), codex=(100, 30), agy_gemini=(0, 0), agy_argon=(0, 0), agy_tp=(0, 0))
        out_ = sec_cikti(dict(evs(100, **olu), _soguma=sgham({"*": (12, "503", 1)})), sinif="mekanik", parca=10)
        j = json.loads(out_.split("JSON ", 1)[1].splitlines()[0])["mekanik"]
        dogrula("tek aday EVREN ve '*' 12 dk soğumada: bekleme 12 dk (Codex haftalık 84 sa değil) + BEKLE satırı",
                j["model"] is None and j["bekle_sa"] == 0.2 and j["soguma_bekle_dk"] == 12.0 and "BEKLE: EVREN ~12 dk" in out_)
        out_ = sec_cikti(dict(evs(100, **olu), _soguma=sgham({"*": (14 * 60, "daily", 1)})), sinif="mekanik", parca=10)
        j = json.loads(out_.split("JSON ", 1)[1].splitlines()[0])["mekanik"]
        dogrula("tek aday EVREN, günlük soğuma 14 sa: bekle 14 sa, 'bekleme önerilmez' + 03:00 TSİ, BEKLE yok",
                j["bekle_sa"] == 14.0 and "bekleme önerilmez" in out_ and "03:00" in out_ and "BEKLE:" not in out_)
        out_ = sec_cikti(dict(evs(100, **olu), _soguma=sgham({"glm-5.3": (12, "503", 1)})), sinif="mekanik", parca=10)
        j = json.loads(out_.split("JSON ", 1)[1].splitlines()[0])["mekanik"]
        dogrula("KISMİ GEÇİŞ, başka havuz yok: 10 parçanın hepsi EVREN'de (yarısı boşta kalmaz), satır gerçek dağılımı yazar",
                sum(int(x.split("x", 1)[0]) for x in j["dagilim"]) == 10 and all("evren" in x for x in j["dagilim"])
                and j["kismi"]["diger"] == 0 and "hepsi EVREN'de" in out_ and "parça sığmadı" not in out_)
        out_ = sec_cikti(evs(100), rol="hakem", sinif="kod", dogrulayici="gpt-6.1-sol", mod="ultra")
        dogrula("--rol hakem ultra: başlık mod payıyla etkin eşiği yazar (Z≥39, etkin Z≥42); ÇOĞUNLUK = üretici + 2 hakem",
                "etkin Z≥42" in out_ and ("üreticinin cevabı +" in out_ or "ÇOĞUNLUK OYU kurulamaz" in out_))
        out_ = sec_cikti(evs(100), rol="nobetci", sinif="kod")
        dogrula("--rol nobetci üretensiz: 'aile eleme YAPILMADI' uyarısı", "aile eleme YAPILMADI" in out_)
        geri_yukle()
        oran = {m: dict(d["o"]) for m, d in MODEL.items()}
        yukle(TEST_BEDAVA, simdi=zaman("2026-12-01T04:00+03:00"), env=env)
        dogrula("bitiş geçti (1 Ara 04:00): bedava havuz yüklenmez, not yazılır", "evren" not in HAVUZ
                and any("bitti" in n for n in YUKLEME_NOTLARI))
        geri_yukle()
        yukle(TEST_BEDAVA, simdi=simdi0, env={})
        dogrula("anahtar ortamda yok: havuz yüklenmez", "evren" not in HAVUZ and not any(m.startswith("evren") for m in MODEL))
    finally:
        geri_yukle()
    dogrula("geri yüklemeden sonra MODEL'de evren-* kalmaz", not any(m.startswith("evren") for m in MODEL) and "evren" not in HAVUZ)
    # kota okuyucu (kota_oku.py) ağsız sınamaları
    try:
        km = kota_modulu()
        for ad, ok in km.kontrol_testleri():
            dogrula("kota_oku: " + ad, ok)
    except Exception as e:
        dogrula(f"kota_oku sınamaları çalıştı ({type(e).__name__})", False)
    KALITE = kalite_eski
    shutil.rmtree(gecici, ignore_errors=True)                     # %TEMP%'te klasör biriktirme
    gecen = sum(1 for _, ok in sonuc if ok)
    for ad, ok in sonuc:
        print(("PASS " if ok else "FAIL ") + ad)
    print(f"\n{gecen}/{len(sonuc)} kural geçti")
    return 0 if gecen == len(sonuc) else 1


def olcum_sayisi():
    try:
        with open(OLCUM, encoding="utf-8") as f:
            return sum(json.load(f).get("n", {}).values())
    except (OSError, ValueError, AttributeError):
        return 0


def olc(a):
    os.makedirs(STATE_DIR, exist_ok=True)
    notlar = []
    if a.adim == "baslat":
        ham = claude_ekle(ham_oku(fresh=True), a, notlar)
        with open(BASLANGIC, "w", encoding="utf-8") as f:
            json.dump({"t": time.time(), "ham": ham}, f)
        print("Başlangıç:", {h: {w: v[0] for w, v in d.items() if not w.startswith("_")} for h, d in ham.items() if not h.startswith("_")})
        return 0
    m, e = model_coz(a.model or "")
    efor = a.efor or e or next(iter(MODEL[m]["z"]))
    with open(BASLANGIC, encoding="utf-8") as f:
        bas = json.load(f)
    son = claude_ekle(ham_oku(fresh=True), a, notlar)
    h = MODEL[m]["h"]
    b, s = bas["ham"].get(h, {}), son.get(h, {})
    try:
        with open(OLCUM, encoding="utf-8") as f:
            kayit = json.load(f)
    except (OSError, ValueError):
        kayit = {}
    kayit.setdefault("oran", {}).setdefault(m, {})
    kayit.setdefault("n", {})
    guncel = oranlar()[m]
    esik = HAVUZ[h].get("olc_esik", 2)
    for w in PENCERELER:
        if w not in s or w not in b:
            continue
        rb, rs = zaman(b[w][1]), zaman(s[w][1])
        if rb and rs and rs > rb:
            print(f"{w}: arada reset oldu, ölçüm yok sayıldı")
            continue
        delta = b[w][0] - s[w][0]
        if delta < esik:
            print(f"{w}: fark %{delta:g} yetersiz (eşik %{esik:g}; daha büyük işte ölç)")
            continue
        yeni = delta / a.is_ / efor_carpan(m, efor)
        eski = guncel.get(w, yeni)
        kayit["oran"][m][w] = round(0.7 * eski + 0.3 * yeni, 3)
        kayit["n"][m] = kayit["n"].get(m, 0) + 1
        print(f"{w}: %{delta:g} / {a.is_:g} İB ({efor}) -> oran {eski} => {kayit['oran'][m][w]}")
    tmp = OLCUM + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(kayit, f, indent=1)
    os.replace(tmp, OLCUM)
    print("Uyarı: aynı anda başka kullanım (claude.ai, Codex uygulaması) ölçümü bozar.")
    return 0


def main():
    for st in (sys.stdout, sys.stderr):
        st.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Orkestra model seçici")
    ap.add_argument("komut", nargs="?", default="sec", choices=["sec", "durum", "neden", "kontrol", "olc", "kalite"])
    ap.add_argument("adim", nargs="?", choices=["baslat", "bitir", "kaydet"])
    ap.add_argument("--sinif", choices=list(SINIF))
    ap.add_argument("--is", dest="is_", type=float, default=1.0)
    ap.add_argument("--model")
    ap.add_argument("--efor", choices=list(EFOR_CARPAN))
    ap.add_argument("--zorla", help="kullanıcının açıkça istediği model[:efor]")
    ap.add_argument("--proje", default=os.getcwd(), help=".orkestra.json aranacak klasör")
    ap.add_argument("--dogrulayici", help="işi yapan model; doğrulayıcı farklı aileden seçilir")
    ap.add_argument("--senaryo", help="test: kota JSON dosyası (_simdi anahtarı isteğe bağlı)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--mod", default="otomatik", choices=["otomatik", *MOD], help="hafif: Claude'u en az harca; ultra: kalite önce")
    ap.add_argument("--claude-5s", type=float)
    ap.add_argument("--claude-hafta", type=float)
    ap.add_argument("--claude-5s-reset")
    ap.add_argument("--claude-hafta-reset")
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--kota", action="append", help="elle kota: havuz:pencere=kalan[@ISO], tekrarlanabilir")
    ap.add_argument("--platformlar", help="platform dosyası (varsayılan ~/.orkestra/platformlar.json)")
    ap.add_argument("--veri", choices=VERI, default="bilinmiyor",
                    help="işin verisi; kamuya açık havuz (gizlilik: kamu) yalnız 'genel' ile aday (varsayılan bilinmiyor)")
    ap.add_argument("--sure-dk", type=float, help="kullanıcı bekliyorsa süre bütçesi (dk); aşan varyant elenir")
    ap.add_argument("--yontem", choices=["yok", *SURU_YONTEM], default="yok", help="sürü yöntemi (doğrulayıcı varsa)")
    ap.add_argument("--min-z", type=float, help="yükseltmede en düşük Z (uyuşmazlık sonrası)")
    ap.add_argument("--haric", action="append", help="bu çalıştırmada hariç havuz (ör. evren çıkış 4 verdiyse)")
    ap.add_argument("--baglam", type=float, help="gereken bağlam (bin token)")
    ap.add_argument("--duzenle", action="store_true", help="iş dosya düzenler (agy accept-edits, bedava platformda Codex ajanı)")
    ap.add_argument("--parca", type=int, help="bağımsız parça sayısı (işçi sayısı buna ve kotaya göre)")
    ap.add_argument("--test-evren", action="store_true", help="testi sürüdeki (zayıf) model yazdı: sürü ΔZ = 0")
    ap.add_argument("--kabul", type=int, help="kalite kaydet: 1 kabul, 0 ret")
    ap.add_argument("--rol", choices=list(ROL), help="izleyici/denetçi alt ajan rolü (nöbetçi, kontrolcü, hakem...)")
    a = ap.parse_args()
    if not math.isfinite(a.is_) or a.is_ <= 0:
        sys.exit("--is sonlu ve 0'dan büyük olmalı")
    if a.parca is not None and a.parca < 1:
        sys.exit("--parca ≥ 1 olmalı")
    try:
        if a.komut != "kontrol":
            yuklu = platformlari_yukle(a.platformlar)
            if yuklu and a.komut in ("durum",):
                print(f"Platform dosyası: {yuklu}")
        if a.zorla:
            model_coz(a.zorla)
        if a.komut == "olc":
            if a.adim not in ("baslat", "bitir"):
                raise Hata("olc baslat | olc bitir")
            return olc(a)
        if a.komut == "kalite":
            if a.adim != "kaydet":
                raise Hata("kalite kaydet --model m --efor e --yontem y --sinif s --kabul 0|1")
            a.yontem = None if a.yontem == "yok" else a.yontem
            return kalite_kaydet(a)
        return {"sec": sec, "durum": durum, "neden": neden, "kontrol": kontrol}[a.komut](a) or 0
    except Hata as e:
        print("HATA:", e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
