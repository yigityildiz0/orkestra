#!/usr/bin/env python3
"""Orkestra model seçici (v4): zeka yeterliliği × gerçek kalan iş × tempo × harcanabilirlik.

Karar sırası
0. Kullanıcının açık isteği (--zorla) ve projenin `.orkestra.json` kuralı (zorunlu/yasak/ağırlık) önce
   gelir; yasak model (Fable, Astra) hiçbir yoldan seçilmez. Kural yoksa kılavuz karar verir.
1. Zeka: her (model, efor) varyantının zeka puanı Z (AA Intelligence Index v5 civarı). İş sınıfı Q ister.
   Z < Q olan varyant elenir (kritikte Z ≥ Q+1). Başarı olasılığı p = 1/(1+e^-((Z-Q+2)/2)); beklenen
   maliyet = iş/p; zor ve kritik işte başarısızlığın bedeli ayrıca eklenir (tekrar deneme ucuz değil).
   Gereğin 10 puan üstü fazla-zeka cezası alır, 20 puan üstü yalnız başka aday yoksa seçilir:
   Haiku'nun işi Sol'a, Sonnet'e gitmez.
2. Kalan iş: 1 iş birimi (İB, ~40-60K token'lık orta iş) her (model, pencere) için o pencerenin şu
   yüzdesini yer (oran). Max 5x'te %5 ≠ Plus'ta %5. Oranlar tahmin; `olc` ölçüp düzeltir.
3. Kıtlık: iş / (işten sonra tabana kadar kalan) × √(1/tempo). Tempo: haftanın geçen kısmına göre
   öndeysen kapasite ucuz (kullan ya da kaybet), gerideysen pahalı. Reseti geçmiş veri yenilenmiş sayılır.
4. Pencereler: Codex ve Antigravity'de karar HAFTALIĞA göre verilir; 5 saatlik yalnız gösterilir ve
   iş sığmıyorsa (%25 payla) o havuz elenir, sıradaki devralır. Claude'da 5 saatlik de puana girer.
   Haftalık tabanlar: Codex %30, Claude %30, Antigravity %5. Claude 5 saatlikte %15 lider payı.
5. Harcanabilirlik (kullanıcı kuralı, 2026-11-08): önce Antigravity, sonra ChatGPT/Codex, en son Claude.
   Ağırlık agy 0.5-0.7, Codex 1.0, Claude 2.0 (haftalığı azaldıkça, kalan süreyle orantılı artar).
   Aynı Claude modeli (Sonnet/Opus) önce agy'nin kendi Claude havuzundan kullanılır; o dolunca
   Claude Max'e düşer (aynı Z, daha düşük ağırlık).

puan = (w5·kıtlık_5s + kıtlık_hafta) × havuz ağırlığı × fazla-zeka × hata bedeli   (düşük = iyi)

Komutlar (yalnız lider, orkestrasyon başında; model çağırmaz, limit harcamaz):
  python -I kapasite.py --sinif kod --is 2 --claude-5s 45 --claude-hafta 92 \
      --claude-5s-reset 2026-11-08T12:10Z --claude-hafta-reset 2026-11-15T07:00Z --proje <cwd>
  python -I kapasite.py durum                         # havuzlar, kalan İB, agy model listesi
  python -I kapasite.py neden --model sonnet:high --sinif zor   # bir varyantın puan dökümü
  python -I kapasite.py kontrol                       # kurallar sahte senaryolarla sınanır (FAIL -> çıkış 1)
  python -I kapasite.py --sinif zor --dogrulayici gpt-6.1-sol   # farklı aileden doğrulayıcı
  python -I kapasite.py --senaryo test.json           # sahte kota ile dene (_simdi anahtarı alır)
  python -I kapasite.py olc baslat | olc bitir --model gpt-6.1-terra --efor medium --is 1
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
STATE_DIR = os.path.expanduser(os.path.join("~", ".orkestra"))
OLCUM = os.path.join(STATE_DIR, "kapasite_olcum.json")
BASLANGIC = os.path.join(STATE_DIR, "olcum_baslangic.json")
HAM_ONBELLEK = os.path.join(os.environ.get("TEMP", "."), "orkestra_kapasite_ham.json")
TTL = 600
WIN_HOURS = {"5s": 5, "hafta": 168}
PAY_5S = 1.25        # 5 saatlik sığma kontrolünde tahmin payı

HAVUZ = {
    "claude":     {"taban": {"5s": 15, "hafta": 30}, "agirlik": 2.5, "w5": 1.0, "ad": "Claude Max"},
    "codex":      {"taban": {"5s": 0, "hafta": 30},  "agirlik": 0.9, "w5": 0.0, "ad": "ChatGPT/Codex"},
    "agy_gemini": {"taban": {"5s": 0, "hafta": 5},   "agirlik": 0.5, "w5": 0.0, "ad": "agy Gemini"},
    "agy_argon":  {"taban": {"5s": 0, "hafta": 5},   "agirlik": 0.7, "w5": 0.0, "ad": "agy Argon"},
    "agy_tp":     {"taban": {"5s": 0, "hafta": 5},   "agirlik": 0.6, "w5": 0.0, "ad": "agy Claude/GPT"},
}

# Model: havuz, aile, medium eforda 1 İB oranı (pencere %'si), efor -> Z, çağrı.
# Z: Artificial Analysis Intelligence Index v5.0.1, efor başına (okuma 2026-11-08; /orkestra güncelle yeniler).
#   Opus low 35, medium 48, high 52, xhigh 57, max 59 | Sonnet low 26, medium 31, high 42, xhigh 50, max 55
#   Haiku low 19, medium 25, high 30, xhigh 35 | Sol low 35, medium 46, high 50, xhigh 52, max 55
#   Terra low 29, medium 38, high 42, xhigh 45, max 51 | Luna high 21, max 28 (medium tahmin) | Argon high 50
#   Flash low 23, medium 30 (high 31: +1 puan için israf, alınmadı). agy içindeki Claude = aynı model, ayrı havuz.
# Oranlar: Codex Plus resmi 5 saatlik mesaj aralıklarıyla oranlı (Sol 15-160, Terra 35-285, Luna 350-3000:
#   Terra ≈ Sol/2, Luna ≈ Sol/15). Claude içi oran AA görev başı maliyetiyle oranlı (medium: Opus $2.45,
#   Sonnet $0.78, Haiku $0.09; Haiku 100K üstü istemde 5 kat pahalı, pay bırakıldı). Hepsi tahmin; `olc` düzeltir.
# Efor çarpanı: AA çıktı token'ı (medium=1): Opus low .5 high 1.3 xhigh 2.4 max 5.1; Sol high 1.6 xhigh 2.2 max 4.2.
EFOR_CARPAN = {"low": 0.5, "medium": 1.0, "high": 1.5, "xhigh": 2.3, "max": 4.5}
MODEL = {
    "claude-opus":   dict(h="claude", aile="claude", o={"5s": 5.0, "hafta": 0.65},
                          z={"medium": 48, "high": 52, "xhigh": 57, "max": 59}, cagri="Agent model=opus effort={e}"),
    "claude-sonnet": dict(h="claude", aile="claude", o={"5s": 1.7, "hafta": 0.22},
                          z={"high": 42, "xhigh": 50, "max": 55}, cagri="Agent model=sonnet effort={e}"),
    "claude-haiku":  dict(h="claude", aile="claude", o={"5s": 0.3, "hafta": 0.04},
                          z={"low": 19, "medium": 25, "high": 30}, cagri="Agent model=haiku effort={e}"),
    "gpt-6.1-sol":   dict(h="codex", aile="gpt", o={"5s": 7.0, "hafta": 1.2},
                          z={"low": 35, "medium": 46, "high": 50, "xhigh": 52, "max": 55},
                          cagri="codex exec -m gpt-6.1-sol -c model_reasoning_effort={e}"),
    "gpt-6.1-terra": dict(h="codex", aile="gpt", o={"5s": 3.5, "hafta": 0.6},
                          z={"low": 29, "medium": 38, "high": 42, "xhigh": 45, "max": 51},
                          cagri="codex exec -m gpt-6.1-terra -c model_reasoning_effort={e}"),
    "gpt-6-luna":    dict(h="codex", aile="gpt", o={"5s": 0.5, "hafta": 0.08},
                          z={"medium": 17, "high": 21},
                          cagri="codex exec -m gpt-6-luna -c model_reasoning_effort={e}"),
    "gemini-4-argon": dict(h="agy_argon", aile="gemini", o={"hafta": 3.3},
                           z={"high": 50}, cagri="agy -p --model gemini-4-argon-{e}"),
    "gemini-3.8-flash": dict(h="agy_gemini", aile="gemini", o={"5s": 4.5, "hafta": 0.75},
                             z={"low": 23, "medium": 30}, cagri="agy -p --model gemini-3.8-flash-{e}"),
    "agy-claude-opus-5-5":   dict(h="agy_tp", aile="claude", o={"5s": 29.5, "hafta": 5.0},
                                  z={"medium": 48, "high": 52}, cagri="agy -p --model claude-opus-5-5-{e}"),
    "agy-claude-sonnet-5-5": dict(h="agy_tp", aile="claude", o={"5s": 10.0, "hafta": 1.7},
                                  z={"high": 42}, cagri="agy -p --model claude-sonnet-5-5-{e}"),
}
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
# çarpanı; fazla_bas: fazla-zeka cezasının başladığı aşım; hata: başarısızlık bedeli çarpanı; paralel: işçi tavanı.
MOD = {
    "hafif":  dict(q=0, claude=2.5, fazla_bas=6, hata=0.5, paralel=2, aciklama="Claude'u en az harca; yeterli en ucuz model, az işçi"),
    "normal": dict(q=0, claude=1.0, fazla_bas=10, hata=1.0, paralel=4, aciklama="denge"),
    "ultra":  dict(q=3, claude=0.6, fazla_bas=16, hata=2.0, paralel=6, aciklama="kalite önce; bir kademe akıllı model, farklı aileden doğrulama"),
}


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
ZORUNLU_MODEL_ALAN = ("h", "aile", "o", "z", "cagri")


def platformlari_yukle(yol=None):
    """Kurulumda yapay zekâ yazar: ~/.orkestra/platformlar.json (yoksa yerleşik üç abonelik geçerli).
    {"kapali": ["agy_argon", "agy_tp"],                        sahip olunmayan havuzlar (model de düşer)
     "havuz": {"opencode_go": {"taban": {"5s": 0, "hafta": 10}, "agirlik": 0.6, "w5": 0, "ad": "OpenCode Go"}},
     "model": {"kimi-k2": {"h": "opencode_go", "aile": "kimi", "o": {"hafta": 1.0}, "z": {"medium": 40},
               "cagri": "opencode run -m <sağlayıcı/model> \"<brief>\""}},
     "kota": {"opencode_go": {"hafta": [70, null]}},            kotası otomatik okunamayan havuzun elle değeri
     "yasak": ["gpt-6-luna"]}
    Okunamazsa Hata (sessizce yerleşiğe dönmez)."""
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
    for h in k.get("kapali", []):
        HAVUZ.pop(h, None)
    for h, v in (k.get("havuz") or {}).items():
        if not isinstance(v, dict):
            raise Hata(f"havuz.{h} nesne olmalı")
        HAVUZ[h] = (HAVUZ.get(h) or {"taban": {"5s": 0, "hafta": 5}, "agirlik": 1.0, "w5": 0.0, "ad": h}) | v
    for m, v in (k.get("model") or {}).items():
        eksik = [x for x in ZORUNLU_MODEL_ALAN if x not in (v or {})]
        if eksik:
            raise Hata(f"model.{m}: eksik alan {eksik}")
        if v["h"] not in HAVUZ:
            raise Hata(f"model.{m}: havuz '{v['h']}' tanımlı değil")
        bad = [e for e in v["z"] if e not in EFOR_CARPAN]
        if bad:
            raise Hata(f"model.{m}: geçersiz efor {bad} (geçerli: {', '.join(EFOR_CARPAN)})")
        MODEL[m] = v
    for m in [m for m, d in MODEL.items() if d["h"] not in HAVUZ]:
        MODEL.pop(m)
    for s in SINIF.values():
        if "adaylar" in s:
            s["adaylar"] = [m for m in s["adaylar"] if m in MODEL]
    YASAK.update(k.get("yasak", []))
    OZEL_KOTA.update(k.get("kota") or {})
    return yol


def ozel_kota_ekle(ham, a, notlar):
    """Elle verilen kotalar (platform dosyası ve --kota havuz:pencere=kalan[@reset]); okunamayan havuz varsayım."""
    for h, wins in OZEL_KOTA.items():
        if h in HAVUZ and h not in ham:
            ham[h] = {w: list(v) for w, v in wins.items()}
    for spec in a.kota or []:
        try:
            hw, deger = spec.split("=", 1)
            h, w = hw.split(":", 1)
            kalan, _, reset = deger.partition("@")
            ham.setdefault(h, {})[w] = [float(kalan), reset or None]
        except ValueError:
            raise Hata(f"--kota biçimi: havuz:pencere=kalan[@ISO] (ör. opencode_go:hafta=70), verilen: {spec}")
    varsayim = set()
    for h in HAVUZ:
        if h != "claude" and h not in ham:
            ham[h] = {"hafta": [50.0, None]}
            varsayim.add(h)
            notlar.append(f"{HAVUZ[h]['ad']} kotası okunamadı: %50 varsayıldı, 2 kat pahalı sayıldı (--kota ile ver)")
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


def ham_oku(fresh=False):
    """havuz -> pencere -> [kalan%, reset ISO|None]; ayrıca _agy_models. Model çağırmaz."""
    if not fresh:
        try:
            if time.time() - os.path.getmtime(HAM_ONBELLEK) < TTL:
                with open(HAM_ONBELLEK, encoding="utf-8") as f:
                    d = json.load(f)
                if isinstance(d, dict) and d:
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
    if out:
        try:
            tmp = HAM_ONBELLEK + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(out, f)
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


def proje_kurali(yol):
    """cwd'den yukarı `.orkestra.json` arar. Okunamazsa Hata (kuralı sessizce düşürmez). Biçim:
    {"zorunlu": {"gorsel": "sol:high", "*": "opus:high"}, "yasak": ["luna"], "agirlik": {"codex": 0.8}, "not": "..."}"""
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
                ag[h] = min(max(float(v), 0.2), 5.0)
            zr = k.get("zorunlu") if isinstance(k.get("zorunlu"), dict) else {}
            return {"yasak": yasak, "agirlik": ag, "zorunlu": zr, "not": k.get("not")}, f
        ust = os.path.dirname(d)
        if ust == d:
            return {}, None
        d = ust


# ---------------------------------------------------------------- puanlama
def agy_var(m, e, ham):
    ids = ham.get("_agy_models")
    if m not in AGY_AD or not ids:
        return True
    return AGY_AD[m].format(e=e) in ids


def havuz_agirligi(h, ham, kural, simdi):
    w = kural.get("agirlik", {}).get(h, HAVUZ[h]["agirlik"])
    if h != "claude" and ham.get(h, {}).get("_varsayim"):
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


def degerle(m, e, z, sinif, is_, ham, oran, simdi, kural, dogrulayici=False):
    """(puan, not, döküm) ya da (None, neden, None). Düşük puan iyi."""
    d, s = MODEL[m], SINIF[sinif]
    q = q_etkin(sinif, kural)
    md = MOD[kural.get("_mod", "normal")]
    esik = q + 1 if s.get("sert") and not dogrulayici else q - 1 if s.get("sert") else q
    if z < esik:
        return None, f"zeka yetmez (Z{z} < {esik})", None
    if not agy_var(m, e, ham):
        return None, "agy model listesinde yok (kalkmış olabilir)", None
    p = 1 / (1 + math.exp(-(z - q + 2) / 2.0)) if q else 1.0
    h = d["h"]
    pencereler = ham.get(h)
    if not pencereler:
        return None, f"{HAVUZ[h]['ad']} kotası okunamadı", None
    kitlar, kalan_ib, notlar = {}, [], []
    tempo_h = 1.0
    for w in ("5s", "hafta"):
        if w not in pencereler:
            continue
        kalan, reset = pencereler[w]
        r = oran[m].get(w)
        if r is None:
            continue
        taban = HAVUZ[h]["taban"].get(w, 0)
        musait = kalan - taban
        zr = zaman(reset)
        t = min(max((zr - simdi).total_seconds() / 3600 / WIN_HOURS[w], 0.02), 1.0) if zr else 1.0
        tempo = min(max(musait / ((100 - taban) * t), 0.4), 5.0) if musait > 0 else 0.4
        ef = EFOR_CARPAN[e] ** (0.5 if tempo >= 3 else 1.0)   # boş kapasitede yüksek efor ucuzlar
        harca = r * is_ * ef / p * s.get("carpan", 1)    # görsel üretim kotayı 3-5 kat hızlı yer
        if w == "5s":
            if harca * PAY_5S > musait:
                parca = max(musait / PAY_5S / (r * ef / p), 0)
                bekle = f", {max((zr - simdi).total_seconds() / 3600, 0):.1f} sa sonra yenilenir" if zr else ""
                return None, f"5s'e sığmaz -> sıradaki devralır (≤{parca:.1f} İB'lik parçalara böl{bekle})", None
        elif harca > musait:
            return None, f"haftalık %{taban} tabanına iner (kalan %{kalan:g})", None
        else:
            tempo_h = tempo
        kalan_ib.append(musait / (r * ef))
        kitlar[w] = harca / max(musait - harca, 1e-6) * (1 / tempo) ** 0.5
    if not kitlar:
        return None, "pencere verisi yok", None
    asim = z - q if q else 0
    fazla = 2 ** (max(0, asim - md["fazla_bas"]) / 4)
    hata = 1 + s.get("hata", 0) * md["hata"] * (1 - p)
    kitlik = HAVUZ[h]["w5"] * kitlar.get("5s", 0) + kitlar.get("hafta", 0)
    ag = havuz_agirligi(h, ham, kural, simdi)
    puan = kitlik * ag * fazla * hata
    if tempo_h < 0.6:
        notlar.append(f"haftalık tempo geride (x{tempo_h:.2f})")
    if ham.get(h, {}).get("_varsayim"):
        notlar.append("kota varsayım")
    nt = f"Z{z} p{p:.2f}, kalan ≈{min(kalan_ib):.1f} İB" + (f", fazla-zeka x{fazla:.2f}" if fazla > 1.01 else "")
    if notlar:
        nt += ", " + ", ".join(notlar)
    dokum = dict(kitlik_5s=kitlar.get("5s"), kitlik_hafta=kitlar.get("hafta"), w5=HAVUZ[h]["w5"], agirlik=ag,
                 fazla=fazla, hata=hata, p=p, asim=asim, puan=puan, kalan_ib=min(kalan_ib))
    return puan, nt, dokum


def aile(m):
    return MODEL[m]["aile"]


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
            puan, nt, dk = degerle(m, e, z, sinif, is_, ham, oran, simdi, kural, dogrulayici=bool(dogrulayici))
            if puan is None:
                red.append((m, e, nt))
            else:
                sonuc.append((puan, m, e, nt, dk))
    # 20 puandan fazla gereğin üstündeki varyant yalnız başka aday yoksa (güçlü modeli boşa harcama)
    q = q_etkin(sinif, kural)
    if q and any(x[4]["asim"] <= 20 for x in sonuc):
        for x in [x for x in sonuc if x[4]["asim"] > 20]:
            red.append((x[1], x[2], f"gereğinden çok güçlü (Z{q + x[4]['asim']}), başka aday var"))
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
    gor, tekil = set(), []
    for x in sonuc:
        if x[1] not in gor:
            gor.add(x[1])
            tekil.append(x)
    return tekil, red


def paralel_tavan(sonuc, is_, kural):
    """Aynı anda kaç işçi: mod tavanı ile adayların tabana kadar kalan işinin (havuz başına) toplamından küçüğü.
    Gerçek sayıyı lider bağımsız parça sayısına göre seçer; bu yalnız üst sınır."""
    havuz = {}
    for _, m, _, _, dk in sonuc[:4]:
        h = MODEL[m]["h"]
        havuz[h] = max(havuz.get(h, 0), dk["kalan_ib"])
    sigar = int(sum(v // is_ for v in havuz.values()))
    return max(1, min(MOD[kural.get("_mod", "normal")]["paralel"], sigar)) if sonuc else 0


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
    ham = claude_ekle(dict(ham), a, notlar)
    varsayim = ozel_kota_ekle(ham, a, notlar)
    ham = temizle(ham, simdi, notlar)
    if "claude" in HAVUZ and any(n.startswith("Claude") and "varsayıldı" in n for n in notlar):
        ham.setdefault("claude", {})["_varsayim"] = True
    for h in varsayim:
        ham.setdefault(h, {})["_varsayim"] = True
    kural, yol = proje_kurali(a.proje)
    return ham, simdi, oranlar(), kural, yol, notlar


def kota_satirlari(ham, simdi):
    out = []
    for h in HAVUZ:
        if h not in ham:
            out.append(f"{h:11s} okunamadı")
            continue
        parca = []
        for w in ("5s", "hafta"):
            if w not in ham[h]:
                continue
            kalan, reset = ham[h][w]
            zr = zaman(reset)
            parca.append(f"{w} {cubuk(kalan, HAVUZ[h]['taban'].get(w, 0))} %{kalan:g}" + (f" reset {max((zr - simdi).total_seconds() / 3600, 0):.0f}sa" if zr else "")
                         + f" taban %{HAVUZ[h]['taban'].get(w, 0)}" + (" (karar dışı)" if w == "5s" and not HAVUZ[h]["w5"] else ""))
        out.append(f"{h:11s} " + " | ".join(parca) + (" [varsayım]" if ham[h].get("_varsayim") else ""))
    return out


def cubuk(kalan, taban, n=10):
    """Kalan kota çubuğu: █ harcanabilir, ▓ dokunulmayan yedek (taban), · boş. Her hücre %10."""
    out = ""
    for i in range(n):
        alt = i * 100 / n
        out += ("▓" if alt < taban else "█") if alt < kalan else "·"
    return out


# ---------------------------------------------------------------- komutlar
def sec(a):
    ham, simdi, oran, kural, yol, notlar = hazirla(a)
    dog = model_coz(a.dogrulayici)[0] if a.dogrulayici else None
    print("== KOTA (model çağrısı yok) ==")
    print("\n".join(kota_satirlari(ham, simdi)))
    if yol:
        print(f"Proje kuralı: {yol}" + (f" ({kural.get('not')})" if kural.get("not") else ""))
    for n in notlar:
        print("NOT:", n)
    print(f"\n== ÖNERİ (iş {a.is_:g} İB; düşük puan iyi; ilki elenirse sıradaki) ==")
    json_out = {}
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
            json_out[s] = {"model": m, "efor": e, "neden": "zorunlu", "cagri": MODEL[m]["cagri"].format(e=e), "uyari": uyari}
            continue
        kural["_mod"], mneden = mod_sec(a.mod, s, ham)
        sonuc, red = sirala(s, a.is_, ham, oran, simdi, kural, dog)
        if not sonuc:
            neden = {}
            for m, e, n in red:
                neden.setdefault(MODEL[m]["h"], f"{m}:{e} {n}")
            sifir = [zaman(ham[h][w][1]) for h in ham if not h.startswith("_") for w in ham[h] if not w.startswith("_") and zaman(ham[h][w][1])]
            bekle = min(((z - simdi).total_seconds() / 3600 for z in sifir), default=None)
            print(f"{s:13s}: uygun model yok -> kullanıcıya sor." + (f" En erken yenilenme {bekle:.1f} sa sonra." if bekle is not None else ""))
            for h, n in neden.items():
                print(f"   {HAVUZ[h]['ad']:15s} {n}")
            json_out[s] = {"model": None, "neden": list(neden.values()), "bekle_sa": None if bekle is None else round(bekle, 1)}
            continue
        par = paralel_tavan(sonuc, a.is_, kural)
        print(f"{s:13s} Q{q_etkin(s, kural):<2d} {kural['_mod']:6s}: " + " > ".join(f"{m}:{e} ({p:.3f})" for p, m, e, _, _ in sonuc[:3])
              + f"  | paralel ≤{par}")
        ilk = sonuc[0]
        json_out[s] = {"model": ilk[1], "efor": ilk[2], "puan": round(ilk[0], 4), "cagri": MODEL[ilk[1]]["cagri"].format(e=ilk[2]),
                       "yedek": [f"{m}:{e}" for _, m, e, _, _ in sonuc[1:3]], "mod": kural["_mod"], "mod_neden": mneden,
                       "paralel_tavan": par}
        if a.sinif:
            for p, m, e, nt, _ in sonuc:
                print(f"   {m + ':' + e:30s} {p:7.3f}  {nt}  | {MODEL[m]['cagri'].format(e=e)}")
            for m, e, nt in red:
                print(f"   {m + ':' + e:30s}      --  {nt}")
    if a.json:
        print("\nJSON " + json.dumps(json_out, ensure_ascii=False))
    print(f"\nOranlar tahmin + ölçüm (ölçüm: {olcum_sayisi()}). Sıra: agy > Codex > Claude. YASAK: {', '.join(sorted(YASAK))}")


def durum(a):
    ham, simdi, oran, kural, yol, notlar = hazirla(a)
    print("== HAVUZLAR ==")
    print("\n".join(kota_satirlari(ham, simdi)))
    for n in notlar:
        print("NOT:", n)
    print("\n== KALAN İŞ (tabana kadar, varsayılan eforda) ==")
    for m, d in MODEL.items():
        h = d["h"]
        if h not in ham:
            continue
        ibs = [f"{w} {max(ham[h][w][0] - HAVUZ[h]['taban'].get(w, 0), 0) / oran[m][w]:.1f}" for w in ("5s", "hafta") if w in ham[h] and w in oran[m]]
        print(f"{m:24s} {HAVUZ[h]['ad']:15s} " + " | ".join(ibs) + " İB")
    ids = ham.get("_agy_models")
    print("\nagy modelleri:", ", ".join(ids) if ids else "okunamadı")


def neden(a):
    ham, simdi, oran, kural, _, notlar = hazirla(a)
    if not a.model or not a.sinif:
        raise Hata("neden: --model ve --sinif gerekli")
    kural["_mod"], mn = mod_sec(a.mod, a.sinif, ham)
    print(f"mod: {kural['_mod']} ({mn}), etkin Q{q_etkin(a.sinif, kural)}")
    m, e = model_coz(a.model)
    for ef in ([e] if e else list(MODEL[m]["z"])):
        z = MODEL[m]["z"][ef]
        puan, nt, dk = degerle(m, ef, z, a.sinif, a.is_, ham, oran, simdi, kural)
        print(f"{m}:{ef} sınıf {a.sinif} (Q{SINIF[a.sinif]['q']}), Z{z}")
        if puan is None:
            print("   ELENDİ:", nt)
            continue
        print(f"   puan {puan:.4f} = (w5 {dk['w5']} × kıtlık_5s {dk['kitlik_5s'] or 0:.4f} + kıtlık_hafta {dk['kitlik_hafta'] or 0:.4f})"
              f" × ağırlık {dk['agirlik']:.2f} × fazla-zeka {dk['fazla']:.2f} × hata bedeli {dk['hata']:.2f}")
        print("  ", nt)
    for n in notlar:
        print("NOT:", n)


# ---------------------------------------------------------------- kontrol: kurallar sahte senaryolarla
def _senaryo(**h):
    s = {"_simdi": "2026-11-11T10:00Z"}
    rs, rh = "2026-11-11T13:00Z", "2026-11-14T22:00Z"
    for k, (a5, ah) in h.items():
        s[k] = {} if k == "agy_argon" else {"5s": [a5, rs]}
        if k == "agy_argon":
            s[k]["hafta"] = [ah, rh]
        else:
            s[k]["hafta"] = [ah, rh]
    return s


def kontrol(_a):
    class A:
        claude_5s = claude_hafta = claude_5s_reset = claude_hafta_reset = None
        fresh = False
        proje = None
        senaryo = None
    oran = {m: dict(d["o"]) for m, d in MODEL.items()}            # ölçümden bağımsız: öncüllerle sına
    sonuc = []

    def calis(s, sinif, is_=1.0, dog=None, kural=None, mod="normal"):
        notlar = []
        simdi = zaman(s["_simdi"])
        ham = {k: v for k, v in s.items() if k != "_simdi"}
        ham = temizle(claude_ekle(json.loads(json.dumps(ham)), A, notlar), simdi, notlar)
        k = dict(kural or {})
        k["_mod"] = mod
        return sirala(sinif, is_, ham, oran, simdi, k, dog)

    def dogrula(ad, kosul):
        sonuc.append((ad, bool(kosul)))

    bol = dict(claude=(100, 95), codex=(100, 90), agy_gemini=(100, 80), agy_argon=(0, 80), agy_tp=(100, 80))
    for s in ("mekanik", "basit", "arastirma", "normal", "kod", "zor"):
        ilk = calis(_senaryo(**bol), s)[0][0]
        dogrula(f"bol kota, {s}: Claude Max seçilmez", MODEL[ilk[1]]["h"] != "claude")
    noagy = dict(claude=(100, 95), codex=(100, 60), agy_gemini=(100, 3), agy_argon=(0, 3), agy_tp=(100, 3))
    for s in ("normal", "kod"):
        ilk = calis(_senaryo(**noagy), s)[0][0]
        dogrula(f"agy yok, Codex %60, {s}: Codex seçilir", MODEL[ilk[1]]["h"] == "codex")
    for s in ("mekanik", "basit"):
        for m_, e_, z_ in [(x[1], x[2], MODEL[x[1]]["z"][x[2]]) for x in calis(_senaryo(**bol), s)[0][:1]]:
            dogrula(f"{s}: kazananın zekası yeter ve aşırı değil", SINIF[s]["q"] <= z_ <= SINIF[s]["q"] + 20)
    haiku = dict(claude=(80, 95), codex=(100, 31), agy_gemini=(100, 5), agy_argon=(0, 3), agy_tp=(100, 80))
    ilk = calis(_senaryo(**haiku), "mekanik")[0][0]
    dogrula("Flash bitmiş, Codex tabanda: mekanik iş Haiku'ya (agy Sonnet/Opus'a değil)", ilk[1] == "claude-haiku")
    ilk = calis(_senaryo(**bol), "kritik")[0][0]
    dogrula("kritik: Z ≥ 57 (Opus yüksek efor)", MODEL[ilk[1]]["z"][ilk[2]] >= 57)
    sq = dict(claude=(100, 95), codex=(100, 90), agy_gemini=(100, 80), agy_argon=(0, 80), agy_tp=(100, 90))
    ilk = calis(_senaryo(**sq), "zor")[0][0]
    dogrula("zor, agy Claude havuzu bol: agy'deki Claude modeli Claude Max'ten önce", ilk[1] != "claude-sonnet" and ilk[1] != "claude-opus")
    taban = dict(claude=(100, 95), codex=(100, 30.5), agy_gemini=(100, 80), agy_argon=(0, 80), agy_tp=(100, 80))
    dogrula("Codex haftalık %30.5: Codex seçilmez", all(MODEL[x[1]]["h"] != "codex" for x in calis(_senaryo(**taban), "normal")[0]))
    c5 = dict(claude=(16, 95), codex=(100, 31), agy_gemini=(100, 3), agy_argon=(0, 3), agy_tp=(100, 3))
    son, red = calis(_senaryo(**c5), "kod")
    dogrula("Claude 5s %16 (lider payı 15): Claude alt ajana verilmez", all(MODEL[x[1]]["h"] != "claude" for x in son))
    cx5 = dict(claude=(100, 95), codex=(2, 90), agy_gemini=(100, 3), agy_argon=(0, 3), agy_tp=(100, 3))
    son, red = calis(_senaryo(**cx5), "normal")
    dogrula("Codex 5s dolu, haftalık bol: başka havuz devralır", son and MODEL[son[0][1]]["h"] != "codex" and any("5s'e sığmaz" in r[2] for r in red))
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
        dogrula(f"hafif, {s}: Claude Max seçilmez ve zeka yeter", MODEL[son[0][1]]["h"] != "claude"
                and MODEL[son[0][1]]["z"][son[0][2]] >= SINIF[s]["q"])
    son, _ = calis(_senaryo(**taban), "normal", mod="ultra")
    dogrula("ultra da Codex %30 tabanını delmez", all(MODEL[x[1]]["h"] != "codex" for x in son))
    kit = {"claude": {"5s": [80, None], "hafta": [35, None]}}
    dogrula("otomatik: Claude haftalığı %35 ise hafif", mod_sec("otomatik", "kod", kit)[0] == "hafif")
    dogrula("otomatik: kritik iş ve Claude bol ise ultra", mod_sec(None, "kritik", {"claude": {"5s": [90, None], "hafta": [90, None]}})[0] == "ultra")
    dogrula("otomatik: zor iş ultra değil (Claude'u koru)", mod_sec(None, "zor", {"claude": {"5s": [90, None], "hafta": [90, None]}})[0] == "normal")
    son, _ = calis(_senaryo(**bol), "normal", mod="hafif")
    dogrula("hafif: paralel tavan ≤ 2", paralel_tavan(son, 1.0, {"_mod": "hafif"}) <= 2)
    yakin = dict(claude=(100, 95), codex=(100, 45), agy_gemini=(100, 3), agy_argon=(0, 3), agy_tp=(100, 3))
    son, _ = calis(_senaryo(**yakin), "kod")
    dogrula("Claude'u koru: Codex %45'te bile kod işi GPT'ye (Sol/Terra ≈ Sonnet)", MODEL[son[0][1]]["h"] == "codex")
    dar = dict(claude=(100, 95), codex=(100, 32), agy_gemini=(100, 3), agy_argon=(0, 3), agy_tp=(100, 3))
    son, _ = calis(_senaryo(**dar), "kod")
    dogrula("Codex %32 (tabana 2 puan): kod işi Claude'a döner", MODEL[son[0][1]]["h"] == "claude")
    dogrula("video üretimi ve video anlama otomatik 'yapılamaz' der", all(SINIF[k].get("yapilamaz") for k in ("video-uret", "video-anlama")))
    for s in ("mekanik", "basit"):
        ilk = calis(_senaryo(**bol), s)[0][0]
        dogrula(f"{s}: Opus/Sol/Sonnet'e gitmez", ilk[1] not in ("claude-opus", "gpt-6.1-sol", "claude-sonnet", "agy-claude-opus-5-5"))
    # platform dosyası: yalnız OpenCode Go (Kimi) + Codex olan bir kullanıcı; sonra yerleşik tablolar geri yüklenir
    import copy
    import tempfile
    yedek = copy.deepcopy((HAVUZ, MODEL, SINIF, YASAK, OZEL_KOTA))
    try:
        ornek = {"kapali": ["claude", "agy_gemini", "agy_argon", "agy_tp"],
                 "havuz": {"opencode_go": {"taban": {"hafta": 10}, "agirlik": 0.6, "ad": "OpenCode Go"}},
                 "model": {"kimi-k2": {"h": "opencode_go", "aile": "kimi", "o": {"hafta": 1.0},
                                       "z": {"medium": 44, "high": 48}, "cagri": "opencode run -m kimi-k2"}}}
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(ornek, f)
        platformlari_yukle(f.name)
        os.unlink(f.name)
        oran.update({m: dict(d["o"]) for m, d in MODEL.items() if m not in oran})
        s_ = {"_simdi": "2026-11-11T10:00Z", "codex": {"hafta": [90, "2026-11-14T22:00Z"]},
              "opencode_go": {"hafta": [80, "2026-11-14T22:00Z"]}}
        son, _ = calis(s_, "normal")
        dogrula("platform dosyası: Claude kapalıyken Claude modeli önerilmez", son and all(MODEL[x[1]]["h"] != "claude" for x in son))
        dogrula("platform dosyası: yeni havuz (OpenCode Go/Kimi) aday olur", any(x[1] == "kimi-k2" for x in son))
    finally:
        h_, m_, si_, y_, o_ = yedek
        HAVUZ.clear(); HAVUZ.update(h_); MODEL.clear(); MODEL.update(m_)
        SINIF.clear(); SINIF.update(si_); YASAK.clear(); YASAK.update(y_); OZEL_KOTA.clear(); OZEL_KOTA.update(o_)
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
    for w in ("5s", "hafta"):
        if w not in s or w not in b:
            continue
        rb, rs = zaman(b[w][1]), zaman(s[w][1])
        if rb and rs and rs > rb:
            print(f"{w}: arada reset oldu, ölçüm yok sayıldı")
            continue
        delta = b[w][0] - s[w][0]
        if delta < 2:
            print(f"{w}: fark %{delta:g} yetersiz (daha büyük işte ölç)")
            continue
        yeni = delta / a.is_ / EFOR_CARPAN[efor]
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
    ap.add_argument("komut", nargs="?", default="sec", choices=["sec", "durum", "neden", "kontrol", "olc"])
    ap.add_argument("adim", nargs="?", choices=["baslat", "bitir"])
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
    a = ap.parse_args()
    if not math.isfinite(a.is_) or a.is_ <= 0:
        sys.exit("--is sonlu ve 0'dan büyük olmalı")
    try:
        if a.komut != "kontrol":
            yuklu = platformlari_yukle(a.platformlar)
            if yuklu and a.komut in ("durum",):
                print(f"Platform dosyası: {yuklu}")
        if a.zorla:
            model_coz(a.zorla)
        if a.komut == "olc":
            if not a.adim:
                raise Hata("olc baslat | olc bitir")
            return olc(a)
        return {"sec": sec, "durum": durum, "neden": neden, "kontrol": kontrol}[a.komut](a) or 0
    except Hata as e:
        print("HATA:", e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
