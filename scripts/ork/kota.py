"""Kota okuyucu: tüm havuzların kalan kotasını MODEL ÇAĞIRMADAN okur ve `kota-anlik` sözleşmesinde birleştirir.

Kaynaklar (v6 `kota_oku` okuma yolları korunarak):
- Codex: `codex app-server` -> `account/rateLimits/read` (5 saat + haftalık).
- agy: `agy -p /usage --output-format json` (yalnız --agy ya da güncelleme sırasında; ToS belirsizliği).
- Bedava OpenAI uyumlu API: `GET {taban}/quota` (+ kalan başlığı), ayrıntılar platformlar.json'dan (kodda ad/URL yok).
- Claude Max: programatik uç yok; lider `get_usage` okumasını `--claude 5s=..,hafta=..` ya da JSON dosyasıyla verir.
- Rust kota servisi (Cetvel): ORKESTRA_KOTA_KAYNAGI ya da kuruluysa %LOCALAPPDATA%/Cetvel/orkestra-uyum.json
  (otomatik keşif); taze (≤10 dk) ve şemaya uygunsa önce kullanılır, bayat/bozuksa kendi adaptörler okur.
Sır: API anahtarı yalnız ortam değişkeninden (Windows'ta HKCU\\Environment) belleğe okunur; hiçbir çıktıya,
dosyaya, URL'ye yazılmaz. Hata metninde yalnız istisna türü ve HTTP kodu. Okunamayan kaynak "bilinmiyor" yazılır.
Kullanım: python ork.py kota [--taze] [--json] [--havuz ad] [--claude 5s=32,hafta=91] [--agy]
"""
import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .veri import Veri, VeriHatasi, atomik_yaz, durum_dizini, json_oku, simdi_utc, zaman_coz

ANLIK_TAZE_SN = 600          # kota-anlik.json önbelleği (her işçiye tekrar okunmasın)
SERVIS_TAZE_SN = 600         # Rust servis anlığı bundan eskiyse kullanılmaz
DURUM_TAZE = 600             # bedava API durum kaydı bundan yeniyse istek atılmaz
VARSAYILAN_GUN_TAVAN = None  # bedava API tavanı veride yoksa: bilinmiyor (uydurma yok)


# ================================================================== durum dosyası (v6 durum_guncelle, genel)
def durum_yolu():
    return durum_dizini() / "durum.json"


def anlik_yolu():
    return Path(os.environ.get("ORKESTRA_KOTA_ANLIK") or (durum_dizini() / "kota-anlik.json"))


NOTLAR = []
_YAZIM = {"kapali": 0}          # kuru kip: >0 iken kota/durum dosyalarına hiçbir şey yazılmaz (yazmadan())


class yazmadan:
    """`with kota.yazmadan():` içinde durum.json, kota-anlik.json, kota-gecmis.jsonl ve claude-kota.json yazılmaz
    (`--kuru` "ne olur" denemeleri gerçek karara sızmasın)."""
    def __enter__(self):
        _YAZIM["kapali"] += 1
        return self

    def __exit__(self, *a):
        _YAZIM["kapali"] -= 1
        return False


def yazim_kapali():
    return _YAZIM["kapali"] > 0


def _durum_oku_kati(onar=False):
    """Durum sözlüğü; yok/boş -> {}. BOM'lu okur. Geçici okunamazsa birkaç kez dener, yine olmazsa None (çağıran
    yazmaz). Kalıcı bozuksa onar=True dosyayı .bozuk adıyla kenara alır ve {} döner."""
    yol = durum_yolu()
    bozuk = False
    for i in range(6):
        if not yol.exists():
            return {}
        try:
            metin = yol.read_text(encoding="utf-8-sig")
            d = json.loads(metin) if metin.strip() else {}
            if isinstance(d, dict):
                return d
            bozuk = True
            break
        except ValueError:
            bozuk = True
            time.sleep(0.02 * (i + 1))
        except OSError:
            bozuk = False
            time.sleep(0.02 * (i + 1))
    if bozuk and onar:
        try:
            os.replace(yol, str(yol) + ".bozuk")
            NOTLAR.append(f"durum dosyası bozuktu: {yol.name}.bozuk adıyla kenara alındı")
            return {}
        except OSError:
            return None
    return None


def durum_oku():
    return _durum_oku_kati() or {}


_DURUM_KILIT = threading.Lock()
KILIT_BAYAT_SN = 30


def _surec_kilidi_al(sure=3.0):
    yol = str(durum_yolu()) + ".lock"
    son = time.monotonic() + sure
    while time.monotonic() < son:
        try:
            fd = os.open(yol, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            return yol
        except (FileExistsError, PermissionError):
            try:
                if time.time() - os.path.getmtime(yol) > KILIT_BAYAT_SN:
                    os.unlink(yol)
                    continue
            except OSError:
                pass
            time.sleep(0.005)
    return None


def durum_guncelle(fn):
    """Atomik oku-değiştir-yaz (iş parçacığı + süreç kilidi). Yalnız sayı/zaman/durum; içerik ve anahtar asla.
    Okunamıyorsa ya da kilit alınamıyorsa yazmaz (None)."""
    if yazim_kapali():
        d = json.loads(json.dumps(durum_oku()))
        fn(d)
        return d
    with _DURUM_KILIT:
        durum_dizini().mkdir(parents=True, exist_ok=True)
        kilit = _surec_kilidi_al()
        if not kilit:
            return None
        try:
            d = _durum_oku_kati(onar=True)
            if d is None:
                return None
            fn(d)
            tmp = Path(f"{durum_yolu()}.{os.getpid()}.{threading.get_ident()}.tmp")
            tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
            for i in range(8):
                try:
                    os.replace(tmp, durum_yolu())
                    break
                except PermissionError:
                    if i == 7:
                        os.unlink(tmp)
                        return None
                    time.sleep(0.02 * (i + 1))
            return d
        finally:
            try:
                os.unlink(kilit)
            except OSError:
                pass


def durum_yaz(ek):
    return durum_guncelle(lambda d: d.update({k: v for k, v in ek.items() if v is not None}))


def durum_birlestir(dout):
    """Seçicinin `durum_guncel` çıktısını (kota_ema, tercihli, son_secim) durum dosyasına derin birleştirir."""
    def f(d):
        for k, v in (dout or {}).items():
            if isinstance(v, dict) and isinstance(d.get(k), dict):
                for k2, v2 in v.items():
                    if isinstance(v2, dict) and isinstance(d[k].get(k2), dict):
                        d[k][k2].update(v2)
                    else:
                        d[k][k2] = v2
            else:
                d[k] = v
    return durum_guncelle(f)


# ================================================================== soğuma (v6, tüm havuzlar için genel)
# Anahtar: havuz kimliği (hesap düzeyi: günlük kota, eşzamanlılık, 5 dk pencere) ya da "havuz:model" (model düzeyi).
SOGUMA_KISA_SN = 60
SOGUMA_HATIRLA_SN = 3600
SOGUMA_TAVAN_SN = 36 * 3600
SOGUMA_ESZAMAN_SN = 30
SOGUMA_TUR_AD = {"503": "sunucu dolu (503)", "fair_share": "model payı dolu (fair share)",
                 "concurrency": "eşzamanlılık sınırı", "token_rate": "kısa token penceresi dolu",
                 "daily": "günlük kota bitti", "kota": "kota/harcama sınırı", "ag": "ağ hatası",
                 "diger": "sunucu hatası"}


def sonraki_gun_reset(simdi=None):
    simdi = simdi or simdi_utc()
    return (simdi + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)


def soguma_suresi(tur, ardisik=1, simdi=None, bitis=None, profil=None):
    """profil: platformun soğuma profili (ör. {"503": [120, 240, 600]}): verilen türde n. soğuma süresi listeden."""
    simdi = simdi or simdi_utc()
    n = max(int(ardisik or 1), 1)
    pr = (profil or {}).get(tur) if isinstance(profil, dict) else None
    if isinstance(pr, list) and pr:
        return float(pr[min(n - 1, len(pr) - 1)])
    ipucu = (bitis - simdi).total_seconds() if bitis else None
    ipucu = ipucu if ipucu and ipucu > 0 else None
    if tur == "daily":
        return min(max(ipucu or (sonraki_gun_reset(simdi) - simdi).total_seconds(), 60.0), float(SOGUMA_TAVAN_SN))
    if tur == "kota":
        return min(max(ipucu or 3600.0, 60.0), float(SOGUMA_TAVAN_SN))
    if tur == "503":
        return float(min(max(min(300 * 2 ** (n - 1), 1200), ipucu or 0), 3600))
    if tur == "token_rate":
        return float(min(max(ipucu or 300, 30), 900))
    if tur == "fair_share":
        return float(min(max(120 * 2 ** (n - 1), ipucu or 0), 600))
    if tur == "concurrency":
        return float(min(max(30 * n, ipucu or 0), 300))
    return float(min(60 * n, 600))


def _havuz_anahtari(ad):
    return str(ad).split(":", 1)[0]


def soguma_kaydet(ad, tur, bitis=None, simdi=None, profil=None):
    """`ad` için soğuma; ardışık hata 1 saatte birikir; aktif kayıt kısalmaz; 30 sn içindeki aynı olay ardışığı artırmaz."""
    simdi = simdi or simdi_utc()
    out = {}

    def f(d):
        s = d.get("soguma") if isinstance(d.get("soguma"), dict) else {}
        eski = s.get(ad) if isinstance(s.get(ad), dict) else {}
        try:
            son = float(eski.get("zaman") or 0)
            n0 = int(eski.get("ardisik") or 0)
        except (TypeError, ValueError, OverflowError):
            son, n0 = 0.0, 0
        eski_b = zaman_coz(eski.get("busy_until"))
        aktif = bool(eski_b and eski_b > simdi)
        if aktif and 0 <= simdi.timestamp() - son < SOGUMA_ESZAMAN_SN:
            n, zaman_ = max(n0, 1), son
        else:
            n = n0 + 1 if simdi.timestamp() - son < SOGUMA_HATIRLA_SN else 1
            zaman_ = simdi.timestamp()
        tur_h = tur
        if tur in ("ag", "diger") and n > 1 and eski.get("tur") in ("503", "fair_share", "concurrency", "token_rate"):
            tur_h = str(eski["tur"])
        sn = soguma_suresi(tur_h, n, simdi, bitis, profil)
        yeni_b, tur_ = simdi + timedelta(seconds=sn), tur_h
        if aktif and eski_b > yeni_b:
            yeni_b, tur_ = min(eski_b, simdi + timedelta(seconds=SOGUMA_TAVAN_SN)), str(eski.get("tur") or tur)
        k = {"tur": tur_, "ardisik": n, "zaman": zaman_, "busy_until": yeni_b.isoformat(timespec="seconds")}
        s[ad] = k
        d["soguma"] = s
        out.update(k)
    if durum_guncelle(f) is None and not out:
        sn = soguma_suresi(tur, 1, simdi, bitis)
        out.update({"tur": tur, "ardisik": 1, "zaman": simdi.timestamp(),
                    "busy_until": (simdi + timedelta(seconds=sn)).isoformat(timespec="seconds"), "yazilamadi": True})
    return out


def soguma_temizle(ad=None, simdi=None, yalniz=False):
    """Başarılı çağrı: `ad` ve (günlük değilse) havuz düzeyi kaydı silinir. ad=None: hepsi. yalniz: yalnız o anahtar."""
    simdi = simdi or simdi_utc()

    def f(d):
        s = d.get("soguma") if isinstance(d.get("soguma"), dict) else {}
        if ad is None:
            s = {}
        else:
            s.pop(ad, None)
            h = _havuz_anahtari(ad)
            if not yalniz and h != ad:
                g = s.get(h) if isinstance(s.get(h), dict) else {}
                b = zaman_coz(g.get("busy_until"))
                if not (g.get("tur") in ("daily", "kota") and b and b > simdi):
                    s.pop(h, None)
        d["soguma"] = s
    return durum_guncelle(f)


def soguma_oku(simdi=None, ham=None):
    """{ad: {tur, ardisik, busy_until(datetime), kalan_sn, durum: aktif|yoklama}}; bozuk kayıt atlanır; ≤36 sa."""
    simdi = simdi or simdi_utc()
    if ham is None:
        ham = durum_oku().get("soguma")
    out = {}
    for ad, k in (ham.items() if isinstance(ham, dict) else []):
        if not isinstance(k, dict):
            continue
        try:
            b = zaman_coz(k.get("busy_until"))
            if not b:
                continue
            kalan = (b - simdi).total_seconds()
        except (OverflowError, OSError, ValueError, TypeError):
            continue
        if kalan < -SOGUMA_HATIRLA_SN:
            continue
        if kalan > SOGUMA_TAVAN_SN:
            kalan, b = float(SOGUMA_TAVAN_SN), simdi + timedelta(seconds=SOGUMA_TAVAN_SN)
        try:
            n = int(k.get("ardisik") or 1)
        except (TypeError, ValueError, OverflowError):
            n = 1
        out[str(ad)] = {"tur": str(k.get("tur") or "diger"), "ardisik": n, "busy_until": b,
                        "kalan_sn": max(kalan, 0.0), "durum": "aktif" if kalan > 0 else "yoklama"}
    return out


def soguma_metni(sg):
    parca = []
    for ad, k in sorted(sg.items()):
        tur = SOGUMA_TUR_AD.get(k["tur"], k["tur"]) + (f" ×{k['ardisik']}" if k["ardisik"] > 1 else "")
        if k["durum"] == "aktif":
            dk = k["kalan_sn"] / 60
            parca.append(f"{ad} {tur}, " + (f"{dk / 60:.1f} sa kaldı" if dk >= 90 else f"{max(dk, 1):.0f} dk kaldı"))
        else:
            parca.append(f"{ad} soğuma bitti, yoklama bekliyor")
    return "; ".join(parca)


def soguma_secici_icin(simdi=None):
    """Seçiciye verilecek biçim: yalnız aktif kayıtlar, busy_until ISO."""
    return {ad: {"tur": k["tur"], "busy_until": k["busy_until"].isoformat()}
            for ad, k in soguma_oku(simdi).items() if k["durum"] == "aktif"}


# ================================================================== hata sınıflama (yeniden deneme yok)
def hata_sinifla(metin="", kod=None):
    """CLI/API çıkışını sınıflar. Dönüş: {sinif: gecici|kapasite|kota|kalici|bilinmiyor, soguma_tur, eylem}.
    Kota/kapasite hatası sarmalanıp yeniden denenmez (CLI'lar zaten dener): havuz soğumaya, başka aday."""
    t = (metin or "").lower()
    if any(x in t for x in ("enforced_spend_limit", "insufficient_quota", "usage limit", "quota exceeded",
                            "limit reached", "spend limit", "out of credits")):
        return {"sinif": "kota", "soguma_tur": "kota", "eylem": "baska_aday", "yeniden_dene": False}
    if "daily" in t and ("limit" in t or "quota" in t):
        return {"sinif": "kota", "soguma_tur": "daily", "eylem": "baska_aday", "yeniden_dene": False}
    if "fair share" in t or "fair_share" in t:
        return {"sinif": "kapasite", "soguma_tur": "fair_share", "eylem": "baska_aday", "yeniden_dene": False}
    if "concurren" in t:
        return {"sinif": "kapasite", "soguma_tur": "concurrency", "eylem": "baska_aday", "yeniden_dene": False}
    if kod in (503, 529) or "overloaded" in t or "service unavailable" in t:
        return {"sinif": "kapasite", "soguma_tur": "503", "eylem": "baska_aday", "yeniden_dene": False}
    if kod == 429 or "rate limit" in t or "rate_limit" in t or "too many requests" in t:
        return {"sinif": "kapasite", "soguma_tur": "token_rate", "eylem": "baska_aday", "yeniden_dene": False}
    if (kod in (400, 404) and ("not supported" in t or "model" in t)) or "model_not_found" in t \
            or "does not exist" in t or "not supported" in t:
        return {"sinif": "kalici", "soguma_tur": None, "eylem": "dur_model_yok", "yeniden_dene": False}
    if kod in (401, 403) or "unauthorized" in t or "forbidden" in t:
        return {"sinif": "kalici", "soguma_tur": None, "eylem": "dur_yetki", "yeniden_dene": False}
    if any(x in t for x in ("timeout", "timed out", "connection", "econnreset", "network")):
        return {"sinif": "gecici", "soguma_tur": "ag", "eylem": "baska_aday", "yeniden_dene": False}
    return {"sinif": "bilinmiyor", "soguma_tur": "diger", "eylem": "baska_aday", "yeniden_dene": False}


def hata_isle(havuz, metin="", kod=None, kimlik=None, bitis=None, simdi=None):
    """Sınıfla + soğuma yaz. Kota hatası havuz düzeyinde, kapasite hatası model düzeyinde soğutur."""
    s = hata_sinifla(metin, kod)
    if s["soguma_tur"]:
        ad = havuz if (s["sinif"] == "kota" or not kimlik) else f"{havuz}:{kimlik}"
        s["soguma"] = soguma_kaydet(ad, s["soguma_tur"], bitis=bitis, simdi=simdi)
        s["soguma_anahtari"] = ad
    return s


# ================================================================== Codex (v6 okuma yolu korunur)
def find_codex(veri=None):
    """En yeni Codex ikilisi: keşifteki tek çözüm (`kesif.ikili_coz`: imza globları + Appx kayıt defteri + --version);
    imza yoksa eski desenler (LOCALAPPDATA bin, WindowsApps, PATH)."""
    try:
        from . import kesif
        v = veri or Veri.yukle()
        imza = next((x for x in kesif.imza_listesi(v.imzalar) if (x.get("okuyucu") == "codex_app_server"
                                                                 or x.get("id") == (v.platformlar.get(
                                                                     next((h.get("platform") for h in
                                                                           v.havuzlar.values() if h.get("okuyucu")
                                                                           == "codex_app_server"), "")) or {}).get(
                                                                     "imza"))), None)
        if imza:
            b = kesif.ikili_coz(imza, surum_al=kesif._surum_komutla)
            if b and b.get("yol"):
                return b["yol"]
    except Exception:
        pass
    if os.name == "nt":
        la = os.environ.get("LOCALAPPDATA", "")
        c = glob.glob(os.path.join(la, "OpenAI", "Codex", "bin", "*", "codex.exe"))
        pf = os.environ.get("ProgramFiles", r"C:\Program Files")
        c += glob.glob(os.path.join(pf, "WindowsApps", "OpenAI.Codex_*", "app", "resources", "codex.exe"))
        c = [x for x in c if os.path.isfile(x)]
        if c:
            return max(c, key=os.path.getmtime)
    return shutil.which("codex")


def _codex_pencere_adi(w, varsayilan):
    dk = w.get("windowDurationMins") or w.get("window_minutes")
    if dk:
        return {300: "5s", 10080: "hafta", 1440: "gun"}.get(int(dk), varsayilan)
    return varsayilan


def codex_coz(rl_sonuc):
    """account/rateLimits/read sonucu -> (pencereler, ek). usedPercent 0 olan pencerede sıfırlama yok (kayan değer);
    usedPercent alanı yoksa pencere atlanır (0 sayılıp %100 kalan uydurulmaz), ek.notlar'a "bilinmiyor" düşülür.
    ordinaryUsageAllowed=false ise ek.ordinary False (havuz kota soğumasına alınır); sıfırlama kredisi yalnız bilgi."""
    r = rl_sonuc or {}
    rl = r.get("rateLimits") or {}
    pen = {}
    notlar = []
    for key, ad in (("primary", "5s"), ("secondary", "hafta")):
        w = rl.get(key)
        if w:
            pad = _codex_pencere_adi(w, ad)
            if w.get("usedPercent") is None:
                notlar.append(f"codex {pad} penceresi: usedPercent yok (bilinmiyor)")
                continue
            kul = float(w["usedPercent"])
            sif = datetime.fromtimestamp(w["resetsAt"], timezone.utc).isoformat() \
                if (w.get("resetsAt") and kul > 0) else None
            pen[pad] = {"kalan": round(max(0.0, 100 - kul) / 100.0, 4), "sifirlama": sif, "kaynak": "app-server"}
    rc = r.get("rateLimitResetCredits") or {}
    alt = {}
    for lid, x in (r.get("rateLimitsByLimitId") or {}).items():
        if lid != (rl.get("limitId") or "codex") and isinstance(x, dict):
            alt[lid] = {k: (x.get(k) or {}).get("usedPercent") for k in ("primary", "secondary")}
    son_reset = [w.get("resetsAt") for w in (rl.get("primary"), rl.get("secondary")) if isinstance(w, dict)
                 and w.get("resetsAt") and float(w.get("usedPercent") or 0) >= 100]
    ek = {"ordinary": r.get("ordinaryUsageAllowed", True) is not False,
          "reached": rl.get("rateLimitReachedType"),
          "reset_kredisi": {"adet": int(rc.get("availableCount") or 0), "son": rc.get("expiresAt")},
          "kredi_bakiye": (rl.get("credits") or {}).get("balance"), "plan": rl.get("planType"),
          "alt_pencereler": alt,
          "dolu_bitis": datetime.fromtimestamp(max(son_reset), timezone.utc).isoformat() if son_reset else None,
          "notlar": notlar}
    return pen, ek


def codex_limits(exe=None, _popen=None, ek=False, zaman_asimi=15.0):
    """{"5s": {"kalan": 0-1, "sifirlama": ISO}, "hafta": {...}} ya da None; ek=True: {"pencereler", "ek"}.
    Model çağırmaz (asla supportsLunaReserve gönderilmez). Toplam süre `zaman_asimi` ile sınırlı: app-server yanıt
    vermezse süreç öldürülür, sonuç "bilinmiyor" (ork sec donmaz); JSON olmayan satırlar atlanır."""
    import queue
    exe = exe or find_codex()
    if not exe:
        return None
    p = (_popen or subprocess.Popen)([exe, "app-server"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL, text=True, encoding="utf-8")
    kuyruk = queue.Queue()

    def okuyucu():                        # readline engelleyicidir: ayrı iş parçacığında
        try:
            for satir in iter(p.stdout.readline, ""):
                kuyruk.put(satir)
        except Exception:
            pass
        kuyruk.put(None)
    threading.Thread(target=okuyucu, daemon=True).start()
    bitis = time.monotonic() + float(zaman_asimi)
    try:
        def send(o):
            p.stdin.write(json.dumps(o) + "\n")
            p.stdin.flush()
        send({"id": 1, "method": "initialize", "params": {"clientInfo": {"name": "kota", "version": "1"}}})
        send({"method": "initialized"})
        send({"id": 2, "method": "account/rateLimits/read", "params": {"excludeResetCreditDetails": False}})
        while True:
            kalan = bitis - time.monotonic()
            if kalan <= 0:
                NOTLAR.append(f"codex app-server {float(zaman_asimi):g} sn içinde yanıt vermedi (bilinmiyor)")
                return None
            try:
                line = kuyruk.get(timeout=kalan)
            except queue.Empty:
                continue
            if line is None:
                return None
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if isinstance(msg, dict) and msg.get("id") == 2:
                pen, e = codex_coz(msg.get("result") or {})
                return {"pencereler": pen, "ek": e} if ek else pen
    except (OSError, ValueError):
        return None
    finally:
        try:
            p.kill()
        except Exception:
            pass


# ================================================================== agy (v6 okuma yolu; yalnız izinle)
def agy_yolu():
    if os.name == "nt":
        p = os.path.join(os.environ.get("LOCALAPPDATA", ""), "agy", "bin", "agy.exe")
        if os.path.exists(p):
            return p
    return shutil.which("agy")


def agy_calistir(*args, timeout=60):
    exe = agy_yolu()
    if not exe:
        raise FileNotFoundError("agy bulunamadı")
    ortam = dict(os.environ, MSYS_NO_PATHCONV="1")       # Git Bash '/usage' yol dönüşümü tuzağı
    return subprocess.run([exe, *args], capture_output=True, text=True, encoding="utf-8", timeout=timeout,
                          stdin=subprocess.DEVNULL, env=ortam).stdout


def _agy_pencere(ad):
    a = str(ad).lower()
    if "week" in a or "hafta" in a or "7d" in a:
        return "hafta"
    if "5" in a and ("h" in a or "saat" in a):
        return "5s"
    if "day" in a or "gun" in a or "24h" in a:
        return "gun"
    return a


def agy_limits(_calistir=None):
    """[(grup, pencere, kalan 0-1, sifirlama ISO)]. 0 token harcar (komut model çağırmaz)."""
    ham = (_calistir or agy_calistir)("-p", "/usage", "--output-format", "json", "--print-timeout", "40s")
    data = json.loads(ham) if isinstance(ham, str) else ham
    out = []
    for g in data["command"]["data"]["groups"]:
        for b in g["buckets"]:
            out.append((g["name"], _agy_pencere(b["window"]), round(float(b["remaining_fraction"]), 4),
                        str(b.get("reset_time") or "")))
    return out


def agy_kovalari(_calistir=None, okuma=1, aralik=2.0, _uyu=None):
    """{bucket_id: {"pencere", "kalan" (okumaların en düşüğü), "sifirlama", "grup", "okuma"}}. Okuma oynak (±0.01):
    varsayılan 1 okuma (her başsız çağrı sayılır), --taze ile 3 okuma ve en düşük kalan. 0 token."""
    out = {}
    for n in range(max(int(okuma), 1)):
        if n:
            (_uyu or time.sleep)(aralik)
        ham = (_calistir or agy_calistir)("-p", "/usage", "--output-format", "json", "--print-timeout", "40s")
        data = json.loads(ham) if isinstance(ham, str) else ham
        for g in ((data.get("command") or {}).get("data") or {}).get("groups") or []:
            for b in g.get("buckets") or []:
                bid = b.get("id") or f"{g.get('name')}:{b.get('window')}"
                k = round(float(b["remaining_fraction"]), 4)
                x = out.get(bid)
                if x is None or k < x["kalan"]:
                    out[bid] = {"pencere": _agy_pencere(b.get("window")), "kalan": k,
                                "sifirlama": str(b.get("reset_time") or "") or None, "grup": g.get("name"),
                                "okuma": (x or {}).get("okuma", 0) + 1}
                else:
                    x["okuma"] += 1
    return out


# ================================================================== bedava OpenAI uyumlu API (genel eklenti)
def anahtar_oku(env_adi):
    """Ortam değişkeni, yoksa (Windows) HKCU\\Environment. Değer döner ama ASLA yazdırılmaz/loglanmaz."""
    if not env_adi:
        return None
    v = os.environ.get(env_adi)
    if v:
        return v.strip()
    if os.name == "nt":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
                v = winreg.QueryValueEx(k, env_adi)[0]
                return str(v).strip() or None
        except OSError:
            return None
    return None


class _Yonlendirmesiz(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None                                   # 3xx izlenmez: anahtar başka origin'e taşınmaz


def taban_guvenli(taban):
    from urllib.parse import urlsplit
    u = urlsplit(taban or "")
    return (u.scheme == "https" and bool(u.hostname)) or \
        (u.scheme == "http" and (u.hostname or "") in ("127.0.0.1", "localhost", "::1"))


def api_get(api, yol, anahtar, zaman_asimi=8):
    """GET; (kod, başlıklar(küçük harf), json|None). Anahtar yalnız başlıkta; yönlendirme izlenmez; https değilse istek yok."""
    taban = (os.environ.get(api.get("taban_env") or "") or api.get("taban_url") or "").rstrip("/")
    if not taban_guvenli(taban):
        raise ValueError("taban URL https değil")
    bas_ad = api.get("anahtar_basligi") or "Authorization"
    deger = anahtar if bas_ad.lower() != "authorization" else f"Bearer {anahtar}"
    req = urllib.request.Request(taban + yol, headers={bas_ad: deger, "Accept": "application/json",
                                                        "User-Agent": "orkestra-kota/7"})
    try:
        with urllib.request.build_opener(_Yonlendirmesiz).open(req, timeout=zaman_asimi) as r:
            ham, bas, kod = r.read(), {k.lower(): v for k, v in r.headers.items()}, r.status
    except urllib.error.HTTPError as e:
        bas = {k.lower(): v for k, v in (e.headers or {}).items()}
        try:
            ham = e.read()
        except Exception:
            ham = b""
        kod = e.code
    try:
        govde = json.loads(ham.decode("utf-8")) if ham else None
    except ValueError:
        govde = None
    return kod, bas, govde


def _ilk(d, *yollar):
    for y in yollar:
        x = d
        for p in y.split("."):
            x = x.get(p) if isinstance(x, dict) else None
        if x is not None:
            return x
    return None


def bedava_kota_coz(govde, basliklar, simdi=None, api=None):
    """/quota gövdesi (+ kalan başlığı) -> durum kaydı ya da None. v6 alan adları + platformlar.json'dan ek adlar."""
    simdi = simdi or simdi_utc()
    api = api or {}
    g = govde if isinstance(govde, dict) else {}
    tavan = _ilk(g, "daily_limit_tokens", "cap_tokens", "daily_token_quota", "daily.limit_tokens") \
        or api.get("gun_tavan") or VARSAYILAN_GUN_TAVAN
    kalan = _ilk(g, "daily_remaining_tokens", "remaining_tokens", "daily.remaining_tokens", "remaining")
    if kalan is None and g.get("daily_used_tokens") is not None and tavan:
        kalan = tavan - g["daily_used_tokens"]
    bas = (api.get("kalan_basligi") or "").lower()
    if kalan is None and bas and basliklar.get(bas):
        try:
            kalan = float(basliklar[bas])
        except ValueError:
            kalan = None
    if g.get("exempt") is True and tavan:
        kalan = tavan
    if kalan is None or not tavan:
        return None
    try:
        kalan, tavan = float(kalan), float(tavan)
    except (TypeError, ValueError):
        return None
    reset = zaman_coz(_ilk(g, "daily_reset_at", "resets_at", "daily.reset_at")) or sonraki_gun_reset(simdi)
    cap, kul = g.get("cap"), g.get("used_tokens")
    return {"zaman": simdi.timestamp(), "kalan": max(kalan, 0.0), "tavan": tavan, "reset": reset.isoformat(),
            "pencere_tavan": cap, "pencere_kalan": (cap - (kul or 0)) if isinstance(cap, (int, float)) else None,
            "pencere_dk": g.get("window_minutes"), "concurrent": g.get("concurrent_requests"),
            "concurrency_limit": g.get("concurrency_limit"), "model_concurrency_limit": g.get("model_concurrency_limit"),
            "fair_share": g.get("fair_share_active"), "level": g.get("level"),
            "sinirlar": {"concurrent": g.get("concurrent_requests"), "concurrency_limit": g.get("concurrency_limit"),
                         "fair_share": g.get("fair_share_active"), "level": g.get("level"),
                         "istek_5dk_kalan": _sayi(basliklar.get("x-ratelimit-remaining-requests"))}}


def _sayi(x):
    try:
        return float(x) if x is not None else None
    except (TypeError, ValueError):
        return None


def bedava_limits(hid, api, simdi=None, ag=True, _get=None, _anahtar=None):
    """(pencereler | None, neden). Sıra: anahtar yoksa None; tukendi/günlük soğuma -> %0; durum ≤10 dk -> o;
    GET /quota; olmazsa eski durum (son sıfırlamadan sonraysa o, önceyse %100); o da yoksa None."""
    simdi = simdi or simdi_utc()
    anahtar = _anahtar() if _anahtar else anahtar_oku(api.get("anahtar_env"))
    if not anahtar:
        return None, "OKUNAMADI (anahtar yok)"
    d0 = durum_oku()
    d = ((d0.get("bedava") or {}).get(hid)) or {}
    tk = zaman_coz(d.get("tukendi_until"))
    if tk and tk > simdi + timedelta(seconds=SOGUMA_TAVAN_SN):
        tk = simdi + timedelta(seconds=SOGUMA_TAVAN_SN)
    g = soguma_oku(simdi, d0.get("soguma")).get(hid)
    if g and g["tur"] in ("daily", "kota") and g["durum"] == "aktif" and (not tk or g["busy_until"] > tk):
        tk = g["busy_until"]
    if tk and tk > simdi:
        return {"gun": {"kalan": 0.0, "sifirlama": tk.isoformat(), "kaynak": "soguma"}}, "günlük kota bitti"

    def pen(x):
        out = {"gun": {"kalan": round(x["kalan"] / x["tavan"], 4) if x.get("tavan") else 0.0,
                       "sifirlama": x.get("reset") or sonraki_gun_reset(simdi).isoformat(), "kaynak": "api_quota"}}
        if x.get("pencere_tavan") and x.get("pencere_kalan") is not None:
            sif = simdi + timedelta(minutes=float(x.get("pencere_dk") or 5))
            out["5dk"] = {"kalan": round(max(x["pencere_kalan"], 0) / x["pencere_tavan"], 4),
                          "sifirlama": sif.isoformat(), "kaynak": "api_quota"}
        return out

    def yaz(x):
        durum_guncelle(lambda dd: dd.setdefault("bedava", {}).__setitem__(hid, x))
    if d.get("kalan") is not None and d.get("tavan") and simdi.timestamp() - float(d.get("zaman", 0)) < DURUM_TAZE:
        return pen(d), None
    neden = None
    if ag:
        try:
            kod, bas, govde = (_get or api_get)(api, api.get("kota_yolu") or "/quota", anahtar)
            if kod in (401, 403):
                return None, f"OKUNAMADI (anahtar/şart, HTTP {kod})"
            if kod == 200:
                x = bedava_kota_coz(govde, bas, simdi, api)
                if x:
                    yaz(x)
                    return pen(x), None
            neden = f"OKUNAMADI (HTTP {kod})"
        except Exception as e:
            neden = f"OKUNAMADI ({type(e).__name__})"
    if d.get("kalan") is not None and d.get("tavan"):
        son_reset = sonraki_gun_reset(simdi) - timedelta(days=1)
        if float(d.get("zaman", 0)) >= son_reset.timestamp():
            return pen(d), neden
        return {"gun": {"kalan": 1.0, "sifirlama": sonraki_gun_reset(simdi).isoformat(), "kaynak": "tahmin"}}, neden
    return None, neden


def bedava_modeller(api, _get=None, _anahtar=None):
    """GET /models (tüm görev türleri). Anahtar yoksa None. Token harcamaz."""
    anahtar = _anahtar() if _anahtar else anahtar_oku(api.get("anahtar_env"))
    if not anahtar:
        return None
    kod, _, govde = (_get or api_get)(api, api.get("modeller_yolu") or "/models", anahtar)
    if kod != 200 or not isinstance(govde, dict):
        raise RuntimeError(f"HTTP {kod}")
    return [m for m in govde.get("data", []) if isinstance(m, dict)]


# ================================================================== Claude (get_usage girdisi)
def claude_coz(girdi, simdi=None, alt_sayaclar=()):
    """'5s=32,hafta=91[,5s_sifirlama=ISO,hafta_sifirlama=ISO]' (KALAN yüzde) ya da sözlük/JSON dosyası.
    Sözlük biçimleri: {"5s": 32, "hafta": 91} ya da {"windows": [{"label": "...", "used_percent"|"utilization"|
    "remaining_percent": x, "resets_at": ISO}]}; bu alanların hepsi YÜZDE (0..100; utilization 0.25 -> %0.25).
    Modele özgü alt sayaçlar ("... only", havuzun alt_sayaclar adları) havuzun genel penceresi sayılmaz.
    Dönüş: pencereler sözlüğü ya da None."""
    ozel = ("only",) + tuple(str(x).lower() for x in alt_sayaclar)
    if girdi is None:
        return None
    if isinstance(girdi, str):
        p = Path(girdi)
        if girdi.strip().startswith("{") or (len(girdi) < 260 and p.suffix == ".json" and p.exists()):
            girdi = json.loads(girdi) if girdi.strip().startswith("{") else json_oku(p)
        else:
            d = {}
            for parca in girdi.split(","):
                if "=" in parca:
                    k, v = parca.split("=", 1)
                    d[k.strip()] = v.strip()
            girdi = d
    out = {}
    if isinstance(girdi, dict) and isinstance(girdi.get("plan"), dict):
        plan = girdi["plan"]                      # gerçek get_usage: {"plan": {"status", "windows": [...]}}
        if plan.get("status") not in (None, "ok"):
            NOTLAR.append(f"get_usage status={plan.get('status')}")
            return None
        girdi = plan
    if isinstance(girdi, dict) and isinstance(girdi.get("windows"), list):
        for w in girdi["windows"]:
            lab = str(w.get("label") or w.get("name") or w.get("title") or "").lower()
            if "·" in lab or "•" in lab:                          # "Weekly · Fable": modele özgü alt sayaç
                bas, _, kuy = lab.replace("•", "·").partition("·")
                if "all" not in kuy:
                    continue
                lab = bas + " all models"
            haftalik = "week" in lab or "hafta" in lab or "7" in lab
            ad = "hafta" if haftalik else ("5s" if ("5" in lab or "session" in lab or "hour" in lab) else None)
            if not ad or any(x in lab for x in ozel):
                continue
            if w.get("remaining_percent") is not None:
                kalan = float(w["remaining_percent"]) / 100
            else:
                kul = w.get("used_percent", w.get("utilization", w.get("percent_used", w.get("percentUsed"))))
                if kul is None:
                    continue
                # tüm kullanım alanları (utilization dahil) her zaman YÜZDE 0..100; Cetvel kuralıyla aynı
                kalan = 1 - float(kul) / 100
            out[ad] = {"kalan": round(max(0.0, min(1.0, kalan)), 4),
                       "sifirlama": w.get("resets_at") or w.get("resetsAt"), "kaynak": "get_usage"}
        return out or None
    for ad in ("5s", "hafta"):
        # birim her zaman KALAN YÜZDE (5s=1 -> %1, 5s=0.5 -> %0.5); kesir yalnız açık alanla: "5s_kalan_oran"
        if isinstance(girdi, dict) and girdi.get(f"{ad}_kalan_oran") is not None:
            v = float(girdi[f"{ad}_kalan_oran"])
        elif isinstance(girdi, dict) and girdi.get(ad) is not None:
            v = float(girdi[ad]) / 100.0
        else:
            continue
        out[ad] = {"kalan": round(max(0.0, min(1.0, v)), 4),
                   "sifirlama": girdi.get(f"{ad}_sifirlama"), "kaynak": "get_usage"}
    return out or None


# ================================================================== Rust servis anlığı (sözleşme: kota-anlik.schema.json)
def anlik_dogrula(a):
    h = []
    if not isinstance(a, dict):
        return ["kök nesne değil"]
    if a.get("sema") != 1:
        h.append("sema != 1")
    if a.get("yazan") not in ("ork.kota", "rust-servis"):
        h.append("yazan geçersiz")
    if not zaman_coz(a.get("zaman")):
        h.append("zaman geçersiz")
    hv = a.get("havuzlar")
    if not isinstance(hv, dict):
        h.append("havuzlar nesne değil")
        return h
    for hid, x in hv.items():
        if not isinstance(x, dict) or x.get("durum") not in ("ok", "bilinmiyor", "kapali", "hata"):
            h.append(f"{hid}: durum geçersiz")
            continue
        for w, p in (x.get("pencereler") or {}).items():
            k = p.get("kalan") if isinstance(p, dict) else None
            if not isinstance(k, (int, float)) or isinstance(k, bool) or not 0 <= k <= 1:
                h.append(f"{hid}.{w}: kalan 0-1 değil")
    return h


def servis_anligi(yol, simdi=None):
    """(anlık | None, not). Bayat ya da şema hatalıysa None + gerekçe (sessizce kullanılmaz)."""
    simdi = simdi or simdi_utc()
    p = Path(yol)
    if not p.exists():
        return None, None
    try:
        a = json_oku(p)
    except VeriHatasi as e:
        return None, f"KOTA KAYNAĞI: yedek (servis anlığı bozuk: {e})"
    if not isinstance(a, dict) or a.get("yazan") != "rust-servis":
        return None, None
    h = anlik_dogrula(a)
    if h:
        return None, f"KOTA KAYNAĞI: yedek (servis şema hatası: {h[0]})"
    yas = (simdi - zaman_coz(a["zaman"])).total_seconds()
    if yas > SERVIS_TAZE_SN:
        return None, f"KOTA KAYNAĞI: yedek (servis bayat {int(yas // 60)} dk)"
    return a, "KOTA KAYNAĞI: rust-servis"


# ================================================================== servis kaynağı keşfi
SERVIS_KAPALI = ("kapali", "kapalı", "yok", "off", "false", "0")     # ORKESTRA_KOTA_KAYNAGI bu değerde: servis kapalı
CETVEL_DOSYALARI = ("orkestra-uyum.json", "anlik.json")             # keşif sırası (Cetvel dizininde)


def cetvel_dizini(env=None):
    """Cetvel servisinin keşif dizini: CETVEL_DIZINI (varsa) ya da %LOCALAPPDATA%/Cetvel. Kurulu değilse None."""
    env = os.environ if env is None else env
    d = (env.get("CETVEL_DIZINI") or "").strip()
    if d:
        return Path(d)
    la = (env.get("LOCALAPPDATA") or "").strip()
    return Path(la) / "Cetvel" if la else None


def servis_kaynagi_coz(acik=None, env=None):
    """(yol | None, kaynak) ; kaynak: 'arguman' | 'ortam' | 'kesif' | 'kapali' | None.
    Sıra: --servis > ORKESTRA_KOTA_KAYNAGI (kapalı sözcüğü servisi kapatır) > Cetvel keşfi (dizindeki ilk var olan
    dosya; sözleşme dışı dosya servis_anligi'nda sessizce elenir). Bu işlev yalnız yolu seçer; bayatlık ve şema
    denetimi servis_anligi'ndadır, geçmeyen kaynak kendi okuyucuya düşer."""
    env = os.environ if env is None else env
    if acik:
        return (None, "kapali") if str(acik).strip().lower() in SERVIS_KAPALI else (Path(acik), "arguman")
    ort = (env.get("ORKESTRA_KOTA_KAYNAGI") or "").strip()
    if ort:
        return (None, "kapali") if ort.lower() in SERVIS_KAPALI else (Path(ort), "ortam")
    kok = cetvel_dizini(env)
    if kok:
        for ad in CETVEL_DOSYALARI:
            if (kok / ad).is_file():
                return kok / ad, "kesif"
    return None, None


# ================================================================== birleşik okuma
def _havuz_kaydi(durum="ok", pencereler=None, notlar=None):
    return {"durum": durum, "pencereler": pencereler or {}, "notlar": list(notlar or [])}


def _yerel_havuz(veri, h):
    plat = veri.platformlar.get(h.get("platform"), {})
    return h.get("okuyucu") in (None, "yok") and (h.get("tur") == "yerel" or plat.get("ucret") == "yerel")


def _servisten_yeniden_dene(veri, h, kayit):
    """Servis anlığındaki kayıt güvenilir değilse True: kayıt yok, durum "ok" değil (bilinmiyor/hata/kapali/
    baglanmadi...) ya da yerel olmayan havuzda pencereler boş. Yerel havuzun boş penceresi doğaldır (sınırsız)."""
    if not isinstance(kayit, dict) or kayit.get("durum") != "ok":
        return True
    return not kayit.get("pencereler") and not _yerel_havuz(veri, h)


AGY_OKUMA_OTURUM_SN = 5 * 3600        # agy kapısı kapalıyken /usage en çok oturum (5 sa) başına bir kez


def agy_kayit_yolu():
    return durum_dizini() / "agy-cagri.jsonl"


def _agy_kayitlari():
    out = []
    yol = agy_kayit_yolu()
    if yol.is_file():
        for satir in yol.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(satir))
            except ValueError:
                continue
    return out


def agy_okuma_izni(veri, simdi=None, durum=None):
    """(okunsun mu, neden). Kapı açıkken önbellek dışı her okumada; kapı kapalı ama kişisel karar açıkken oturum başına
    bir kez; 403 kapanışında ya da kişisel karar yokken hiç. Başsız /usage okumaları da agy-cagri.jsonl'a yazılır ve
    kendi saatlik tavanına (güvenceler.saatlik_okuma_tavani, varsayılan 6) sayılır."""
    from . import secici                       # geç içe aktarma (secici kota'yı içe aktarmaz)
    simdi = simdi or simdi_utc()
    durum = durum if durum is not None else durum_oku()
    ao = veri.agy_otomatik()
    if not ao.get("acik"):
        return False, "agy okunmadı (otomatik karar yok; --agy ile izinli okuma)"
    if durum.get("agy_otomatik_kapali"):
        return False, "agy okunmadı (403/askı kapanışı)"
    g = ao.get("guvenceler") or {}
    tavan = int(g.get("saatlik_okuma_tavani") or 6)
    son_saat = [zaman_coz(x.get("zaman")) for x in _agy_kayitlari() if x.get("tur") == "okuma"]
    if sum(1 for z in son_saat if z and simdi - z <= timedelta(hours=1)) >= tavan:
        return False, f"agy okunmadı (saatlik okuma tavanı {tavan})"
    acik, _ = secici.agy_kapisi(veri, durum, simdi)
    if acik:
        return True, None
    son = zaman_coz(durum.get("agy_okuma_son"))
    if son and 0 <= (simdi - son).total_seconds() < AGY_OKUMA_OTURUM_SN:
        return False, "agy okunmadı (kapı kapalı: oturumda bir okuma yapıldı)"
    return True, None


def _agy_okuma_kaydi(simdi, durum_, n):
    if yazim_kapali():
        return
    try:
        agy_kayit_yolu().parent.mkdir(parents=True, exist_ok=True)
        with open(agy_kayit_yolu(), "a", encoding="utf-8", newline="\n") as f:
            for _ in range(max(int(n), 1)):
                f.write(json.dumps({"zaman": simdi.isoformat(timespec="seconds"), "tur": "okuma", "komut": "/usage",
                                    "durum": durum_}, ensure_ascii=False) + "\n")
    except OSError:
        pass
    durum_guncelle(lambda d: d.__setitem__("agy_okuma_son", simdi.isoformat(timespec="seconds")))


def _agy_kayit_satiri(komut):
    """Keşif/doğrulama başsız slash çağrısı (0 token) -> agy-cagri.jsonl okuma kaydı."""
    if yazim_kapali():
        return
    try:
        agy_kayit_yolu().parent.mkdir(parents=True, exist_ok=True)
        with open(agy_kayit_yolu(), "a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps({"zaman": simdi_utc().isoformat(timespec="seconds"), "tur": "okuma",
                                "komut": str(komut)[:40], "durum": "kesif"}, ensure_ascii=False) + "\n")
    except OSError:
        pass


def oku(veri, simdi=None, taze=False, agy=None, claude=None, servis_yolu=None, adaptor=None, onbellek=True, yaz=True,
        _yalniz=None, _agy_neden=None):
    """Tüm havuzlar için birleşik anlık (kota-anlik sözleşmesi). adaptor: testte {"codex"|"agy"|"bedava": fn}.
    agy=None: agy_okuma_izni kararı (kapı açıksa; kapalıysa oturumda bir kez); agy=True (--agy) açık izin.
    yaz=False (`--kuru`): hiçbir kota/durum dosyası yazılmaz."""
    if not yaz:
        with yazmadan():
            return oku(veri, simdi, taze, agy, claude, servis_yolu, adaptor, onbellek, True, _yalniz, _agy_neden)
    simdi = simdi or simdi_utc()
    adaptor = adaptor or {}
    agy_neden = _agy_neden
    if agy is None:
        agy, agy_neden = agy_okuma_izni(veri, simdi)
    notlar = []
    alt = [a for h in veri.havuzlar.values() if h.get("okuyucu") == "claude_get_usage"
           for a in (h.get("alt_sayaclar") or {})]
    cl = claude_coz(claude, simdi, alt) if claude is not None else None
    servis_yolu, servis_kaynak = servis_kaynagi_coz(servis_yolu) if _yalniz is None else (None, None)
    if servis_yolu:
        a, n = servis_anligi(servis_yolu, simdi)
        if n:
            notlar.append(n)
        elif servis_kaynak == "kesif" and not a:
            notlar.append("KOTA KAYNAĞI: yedek (Cetvel dosyası sözleşmeye uymuyor)")
        if a:
            a = json.loads(json.dumps(a))
            a.setdefault("notlar", []).extend(notlar)
            if servis_kaynak == "kesif":
                a["notlar"].append("KOTA KAYNAĞI: Cetvel (otomatik keşif)")
            # serviste olmayan ya da serviste okunamamış havuzlar (durum ok değil: bilinmiyor/hata/kapali/baglanmadi;
            # ya da yerel olmayan havuzda pencereler boş) bilinmiyor kalmasın: yalnız onlar kendi okuyucuyla denenir
            sh = a.get("havuzlar") or {}
            eksik = {hid for hid, h in veri.havuzlar.items()
                     if h.get("okuyucu") != "claude_get_usage" and _servisten_yeniden_dene(veri, h, sh.get(hid))}
            if eksik:
                # taze dıştakini izler (--taze yoksa agy tek okuma); yaz=True: okuma kaydı ve durum yazılır (saatlik tavan
                # işlesin), --kuru ise dıştaki yazmadan() zaten yazımı kapatmıştır. onbellek=False: anlık dosyası yazılmaz.
                b = oku(veri, simdi, taze, agy, claude, None, adaptor, False, True, _yalniz=eksik, _agy_neden=agy_neden)
                hv = a.setdefault("havuzlar", {})
                for k, yeni in (b.get("havuzlar") or {}).items():
                    if k not in eksik:
                        continue
                    eski = hv.get(k)
                    # kendi okuyucu başarılıysa ya da servis kaydı yoksa/boş pencereli "ok" ise kendi okuma geçer;
                    # aksi hâlde servisin hata/kapali kaydı korunur, kendi okuyucunun notu eklenir
                    if not isinstance(eski, dict) or (yeni or {}).get("durum") == "ok" or eski.get("durum") == "ok":
                        hv[k] = yeni
                        if isinstance(eski, dict):
                            hv[k].setdefault("notlar", []).append(f"servis durumu {eski.get('durum')}"
                                                                  f"{'' if eski.get('pencereler') else ' (pencere yok)'}"
                                                                  ": kendi okuyucuyla okundu")
                    else:
                        eski.setdefault("notlar", []).extend(x for x in (yeni or {}).get("notlar") or []
                                                             if x not in eski["notlar"])
                a["notlar"].extend(x for x in b.get("notlar") or [] if x not in a["notlar"])
                a["notlar"].append("KOTA KAYNAĞI: serviste olmayan ya da okunamayan havuzlar kendi okuyucuyla: "
                                   + ", ".join(sorted(eksik)))
            _claude_ekle(a, veri, cl, simdi)
            _bitis_uygula(a, veri, simdi)
            return a
    if onbellek and not taze and _yalniz is None:
        try:
            on = json_oku(anlik_yolu())
            if isinstance(on, dict) and on.get("yazan") == "ork.kota" and zaman_coz(on.get("zaman")) \
                    and 0 <= (simdi - zaman_coz(on["zaman"])).total_seconds() < ANLIK_TAZE_SN:
                on["onbellek"] = True
                _claude_ekle(on, veri, cl, simdi)
                _bitis_uygula(on, veri, simdi)
                return on
        except VeriHatasi:
            pass
    anlik = {"sema": 1, "yazan": "ork.kota", "zaman": simdi.isoformat(timespec="seconds"), "havuzlar": {},
             "notlar": notlar, "yeni_modeller": [], "kalkan_modeller": []}
    codex_sonuc = agy_sonuc = None
    codex_okundu = agy_okundu = False
    for hid, h in sorted(veri.havuzlar.items()):
        if _yalniz is not None and hid not in _yalniz:
            continue
        ok = h.get("okuyucu")
        try:
            if ok == "codex_app_server":
                if not codex_okundu:
                    codex_okundu = True
                    try:
                        codex_sonuc = (adaptor.get("codex") or (lambda: codex_limits(ek=True)))()
                    except Exception as e:
                        codex_sonuc = None
                        notlar.append(f"codex OKUNAMADI ({type(e).__name__})")
                pen_c, ek_c = (codex_sonuc.get("pencereler"), codex_sonuc.get("ek")) \
                    if isinstance(codex_sonuc, dict) and "pencereler" in codex_sonuc else (codex_sonuc, None)
                if pen_c:
                    kay = _havuz_kaydi("ok", pen_c)
                    if ek_c:
                        kay["ek"] = ek_c
                        kay["notlar"].extend(ek_c.get("notlar") or [])
                        if not ek_c.get("ordinary", True):
                            kay["notlar"].append("ordinaryUsageAllowed=false: havuz kota soğumasında")
                            soguma_kaydet(hid, "kota", bitis=zaman_coz(ek_c.get("dolu_bitis")), simdi=simdi)
                        if (ek_c.get("reset_kredisi") or {}).get("adet"):
                            kay["notlar"].append(f"ücretsiz sıfırlama kredisi {ek_c['reset_kredisi']['adet']} adet "
                                                 f"(son {ek_c['reset_kredisi'].get('son') or '?'}; asla kendiliğinden "
                                                 f"kullanılmaz)")
                    anlik["havuzlar"][hid] = kay
                else:
                    anlik["havuzlar"][hid] = _havuz_kaydi("bilinmiyor", notlar=(ek_c or {}).get("notlar") or [
                        "codex okunamadı (kurulu değil ya da giriş yok)"])
            elif ok == "agy_usage":
                if not agy:
                    anlik["havuzlar"][hid] = _havuz_kaydi("bilinmiyor", notlar=[
                        agy_neden or "agy okunmadı (--agy ile izinli okuma)"])
                    continue
                if not agy_okundu:
                    agy_okundu = True
                    n_ok = 3 if taze else 1
                    try:
                        if adaptor.get("agy"):
                            agy_sonuc = adaptor["agy"]()
                        else:
                            agy_sonuc = agy_kovalari(okuma=n_ok)
                            _agy_okuma_kaydi(simdi, "ok", n_ok)
                    except Exception as e:
                        agy_sonuc = None
                        notlar.append(f"agy OKUNAMADI ({type(e).__name__})")
                        if not adaptor.get("agy"):
                            _agy_okuma_kaydi(simdi, "hata", 1)
                pen = {}
                kovalar = h.get("agy_kovalar") or {}
                if isinstance(agy_sonuc, dict):
                    for w, bid in kovalar.items():
                        x = agy_sonuc.get(bid)
                        if x:
                            pen[w] = {"kalan": x["kalan"], "sifirlama": x.get("sifirlama"), "kaynak": "agy_usage"}
                else:                                         # eski biçim: (grup, pencere, kalan, sıfırlama)
                    grup = str(h.get("agy_grup") or "").lower()
                    for g, w, k, r in agy_sonuc or []:
                        if grup and grup in g.lower():
                            pen[w] = {"kalan": k, "sifirlama": r or None, "kaynak": "agy_usage"}
                if pen:
                    anlik["havuzlar"][hid] = _havuz_kaydi("ok", pen, ["agy okuması ±0.01 oynak (en düşük alındı)"])
                else:
                    anlik["havuzlar"][hid] = _havuz_kaydi("bilinmiyor", notlar=[
                        "agy_kovalar eşlemesi yok ya da kova okunamadı" if not kovalar else "agy kovası bulunamadı"])
            elif ok == "bedava_api":
                api = veri.api_ayari(h.get("platform"))
                fn = adaptor.get("bedava")
                pen, neden = fn(hid, api, simdi) if fn else bedava_limits(hid, api, simdi)
                # anahtar yoksa çağrı kesin başarısız olur: havuz kapalı (bilinmiyor değil; seçici aday saymaz)
                kapali = not pen and "anahtar yok" in str(neden or "")
                anlik["havuzlar"][hid] = _havuz_kaydi("ok", pen, [neden] if neden else []) if pen else \
                    _havuz_kaydi("kapali" if kapali else "bilinmiyor", notlar=[neden] if neden else [])
                sn = (((durum_oku().get("bedava") or {}).get(hid)) or {}).get("sinirlar")
                if pen and sn:
                    anlik["havuzlar"][hid]["sinirlar"] = sn
            elif ok == "claude_get_usage":
                anlik["havuzlar"][hid] = _havuz_kaydi("bilinmiyor", notlar=[
                    "get_usage ile oku ve ver: ork kota --claude 5s=<kalan%>,hafta=<kalan%>"])
            elif _yerel_havuz(veri, h):
                anlik["havuzlar"][hid] = _havuz_kaydi("ok", {})
            else:
                anlik["havuzlar"][hid] = _havuz_kaydi("bilinmiyor", notlar=[f"okuyucu yok: {ok}"])
        except Exception as e:                       # bir havuzun hatası diğerlerini düşürmez
            anlik["havuzlar"][hid] = _havuz_kaydi("hata", notlar=[f"OKUNAMADI ({type(e).__name__})"])
    _claude_ekle(anlik, veri, cl, simdi)
    _bitis_uygula(anlik, veri, simdi)
    anlik["notlar"].extend(n for n in NOTLAR if n not in anlik["notlar"])
    if onbellek and not yazim_kapali():
        try:
            atomik_yaz(anlik_yolu(), anlik)
            gecmis_ekle(anlik, simdi)
        except OSError:
            pass
    return anlik


# ================================================================== kota geçmişi ve kalibrasyon (tasarım 8.3, 8.6)
def gecmis_yolu():
    return durum_dizini() / "kota-gecmis.jsonl"


def gecmis_oku(yol=None):
    yol = Path(yol or gecmis_yolu())
    out = []
    if yol.is_file():
        for satir in yol.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(satir))
            except ValueError:
                continue
    return out


GECMIS_SAKLA_GUN = 14
GECMIS_DISI_KAYNAK = {"tahmin", "soguma", "get_usage_bayat", "senaryo"}


def gecmis_ekle(anlik, simdi=None, yol=None):
    """Taze GERÇEK okumayı (yalnız değişen havuz/pencere) kota-gecmis.jsonl'a ekler; tahmin, soğuma ve bayat önbellek
    kaynaklı değerler yazılmaz (kalibrasyonu kirletmez). 14 günden eski satırlar budanır. İçerik yok: zaman, havuz,
    pencere, kalan, sıfırlama."""
    simdi = simdi or simdi_utc()
    yol = Path(yol or gecmis_yolu())
    if yazim_kapali() or (anlik or {}).get("onbellek"):
        return []
    eski = gecmis_oku(yol)
    sinir = simdi - timedelta(days=GECMIS_SAKLA_GUN)
    tut = [k for k in eski if (zaman_coz(k.get("zaman")) or simdi) >= sinir]
    if len(tut) < len(eski):
        try:
            yol.write_text("".join(json.dumps(k, ensure_ascii=False) + "\n" for k in tut), encoding="utf-8")
        except OSError:
            pass
    son = {}
    for k in tut:
        son[(k.get("havuz"), k.get("pencere"))] = k
    yeni = []
    for hid, x in ((anlik or {}).get("havuzlar") or {}).items():
        if (x or {}).get("durum") != "ok":
            continue
        for w, p in (x.get("pencereler") or {}).items():
            if str(p.get("kaynak") or "") in GECMIS_DISI_KAYNAK:
                continue
            k = {"zaman": simdi.isoformat(timespec="seconds"), "havuz": hid, "pencere": w, "kalan": p.get("kalan"),
                 "sifirlama": p.get("sifirlama")}
            o = son.get((hid, w))
            if not o or o.get("kalan") != k["kalan"] or o.get("sifirlama") != k["sifirlama"]:
                yeni.append(k)
    if yeni:
        yol.parent.mkdir(parents=True, exist_ok=True)
        with open(yol, "a", encoding="utf-8", newline="\n") as f:
            for k in yeni:
                f.write(json.dumps(k, ensure_ascii=False) + "\n")
    return yeni


def kalibre(hid, pencere, gecmis, olc, esik_pp=10.0, alfa=0.3, onceki=None):
    """K̂ = Σc / Δk: aynı pencere döneminde (arada sıfırlama yok) iki okuma arası düşüş Δk >= esik_pp iken o aralıktaki
    olc maliyet toplamı (`maliyet_usd_e` ya da `pay_tahmin` × öncül K). EMA α ile önceki ölçümle birleşir.
    Dönüş {"K", "n", "son"} ya da None (yetersiz kanıt)."""
    L = sorted((k for k in gecmis if k.get("havuz") == hid and k.get("pencere") == pencere
                and isinstance(k.get("kalan"), (int, float))), key=lambda k: str(k.get("zaman")))
    en_iyi = None
    for a_i in range(len(L)):
        for b_i in range(a_i + 1, len(L)):
            a, b = L[a_i], L[b_i]
            if a.get("sifirlama") != b.get("sifirlama"):
                continue
            dk = (float(a["kalan"]) - float(b["kalan"])) * 100
            if dk < esik_pp:
                continue
            za, zb = zaman_coz(a["zaman"]), zaman_coz(b["zaman"])
            c = sum(float(x.get("maliyet_usd_e") or 0) for x in olc if x.get("havuz") == hid
                    and za and zb and zaman_coz(x.get("zaman")) and za <= zaman_coz(x["zaman"]) <= zb)
            if c > 0:
                en_iyi = (c / (dk / 100.0), b["zaman"])
            break
    if not en_iyi:
        return None
    K, son = en_iyi
    if onceki and onceki.get("K"):
        K = alfa * K + (1 - alfa) * float(onceki["K"])
    return {"K": round(K, 4), "n": int((onceki or {}).get("n") or 0) + 1, "son": son}


def kalibrasyon_hesapla(veri, gecmis, olc, durum=None):
    """K_p ölçümü (açık iş 8): ana havuz dışındaki her havuz/pencere için kalibre(); sonuç durum.kapasite_kalibre'ye
    yazılır ve seçici K_p öncülü yerine (öncülün 0.25-4 katı içindeyse) bunu kullanır. Ana havuz lider ile ortak
    olduğundan (Δk liderin de harcamasını içerir) kendiliğinden kalibre edilmez. Dönüş {hid: {w: {K, n, son}}}."""
    s = veri.siniflar.get("olc") or {}
    esik, alfa = float(s.get("kalibrasyon_esigi_pp", 10)), float(s.get("kalibrasyon_ema_alfa", 0.3))
    eski = (durum or {}).get("kapasite_kalibre") or {}
    ana = veri.ana_havuzlar()
    out = {}
    for hid, h in sorted(veri.havuzlar.items()):
        if hid in ana or h.get("bedava") or h.get("tur") == "yerel":
            continue
        for pn in h.get("pencereler") or []:
            w = pn.get("ad") if isinstance(pn, dict) else None
            if not w:
                continue
            onceki = (eski.get(hid) or {}).get(w)
            r = kalibre(hid, w, gecmis, olc, esik, alfa, onceki)
            if r and (not onceki or onceki.get("son") != r.get("son")):
                out.setdefault(hid, {})[w] = r
    return out


CLAUDE_TAZE_SN = 2700         # get_usage değeri kendi önbelleğinde 45 dk geçerli (genel anlık 10 dk)
CLAUDE_5S_TAZE_SN = 900       # 5 saatlik pencere hızlı değişir (ultracode): 15 dk'dan eski 5s değeri "bilinmiyor"


def claude_yolu():
    return durum_dizini() / "claude-kota.json"


def _claude_ekle(anlik, veri, cl, simdi=None):
    """get_usage değeri verildiyse yazılır ve kendi önbelleğine kaydedilir; verilmediyse 45 dk içindeki son değer
    'bayat' notuyla kullanılır (genel anlık yenilense de Claude sessizce 'bilinmiyor'a düşmez)."""
    simdi = simdi or simdi_utc()
    notu = None
    if cl:
        if not yazim_kapali():
            try:
                atomik_yaz(claude_yolu(), {"zaman": simdi.isoformat(timespec="seconds"), "pencereler": cl})
            except OSError:
                pass
    else:
        try:
            on = json_oku(claude_yolu()) if claude_yolu().exists() else None
        except VeriHatasi:
            on = None
        z = zaman_coz((on or {}).get("zaman"))
        if z and 0 <= (simdi - z).total_seconds() < CLAUDE_TAZE_SN and (on or {}).get("pencereler"):
            yas = (simdi - z).total_seconds()
            cl = {w: dict(p, kaynak="get_usage_bayat") for w, p in on["pencereler"].items()
                  if isinstance(p, dict) and not (w == "5s" and yas >= CLAUDE_5S_TAZE_SN)}
            notu = f"Claude kotası {int(yas // 60)} dk önceki get_usage okuması (bayat olabilir)" + \
                (" · 5s penceresi 15 dk'dan eski: bilinmiyor (get_usage yeniden oku)" if yas >= CLAUDE_5S_TAZE_SN
                 else "")
    if not cl:
        # önbellekteki genel anlık eski bir Claude değeri taşıyorsa (45 dk'yı aşmış) sessizce kullanılmaz
        for hid, h in veri.havuzlar.items():
            if h.get("okuyucu") == "claude_get_usage" and ((anlik.get("havuzlar") or {}).get(hid) or {}).get(
                    "durum") == "ok":
                anlik["havuzlar"][hid] = _havuz_kaydi("bilinmiyor", notlar=[
                    "get_usage ile oku ve ver: ork kota --claude 5s=<kalan%>,hafta=<kalan%>"])
        return
    for hid, h in veri.havuzlar.items():
        if h.get("okuyucu") == "claude_get_usage":
            anlik.setdefault("havuzlar", {})[hid] = _havuz_kaydi("ok", cl, [notu] if notu else [])


def _bitis_uygula(anlik, veri, simdi):
    for hid, h in veri.havuzlar.items():
        b = zaman_coz(h.get("bitis") or (veri.platformlar.get(h.get("platform")) or {}).get("bitis"))
        if b and b <= simdi:
            anlik.setdefault("havuzlar", {})[hid] = _havuz_kaydi("kapali", notlar=[f"bitiş geçti ({h.get('bitis')})"])


# ================================================================== metin çıktısı
def metin(anlik, simdi=None, yalniz=None):
    simdi = simdi or simdi_utc()
    s = ["== KALAN KOTA (model çağrısı yapılmadı) ==" + (" [önbellek]" if anlik.get("onbellek") else "")]
    for hid, x in sorted((anlik.get("havuzlar") or {}).items()):
        if yalniz and hid != yalniz:
            continue
        if x.get("durum") != "ok" or not x.get("pencereler"):
            s.append(f"{hid:16s} {x.get('durum', '?').upper()}" + (f" ({'; '.join(x.get('notlar') or [])})"
                                                                     if x.get("notlar") else ""))
            continue
        for w, p in sorted(x["pencereler"].items()):
            r = zaman_coz(p.get("sifirlama"))
            s.append(f"{hid:16s} {w:6s} %{p['kalan'] * 100:5.1f}" + (f"  sıfırlama {r:%Y-%m-%d %H:%M}Z" if r else ""))
        for n in x.get("notlar") or []:
            s.append(f"{'':16s} NOT {n}")
        if x.get("sinirlar"):
            s.append(f"{'':16s} sınırlar " + ", ".join(f"{k}={v}" for k, v in x["sinirlar"].items() if v is not None))
    sg = soguma_oku(simdi)
    if sg:
        s.append(f"SOĞUMA: {soguma_metni(sg)}")
    for n in anlik.get("notlar") or []:
        s.append(f"NOT {n}")
    return "\n".join(s)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="ork kota", description="Kalan kotayı model çağırmadan okur.")
    ap.add_argument("--taze", action="store_true", help="10 dk önbelleği atla")
    ap.add_argument("--json", action="store_true", help="kota-anlik sözleşmesinde JSON yaz")
    ap.add_argument("--havuz", help="yalnız bu havuz")
    ap.add_argument("--claude", help="get_usage kalan yüzdeleri: 5s=32,hafta=91 ya da JSON dosyası")
    ap.add_argument("--agy", action="store_true", default=None,
                    help="agy kotasını da oku (agy_otomatik açıksa zaten okunur; 0 token)")
    ap.add_argument("--servis", help="Rust servis anlığı yolu (varsayılan: ORKESTRA_KOTA_KAYNAGI, yoksa Cetvel keşfi; "
                                     "'kapali' servisi kapatır)")
    a = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    veri = Veri.yukle()
    anlik = oku(veri, taze=a.taze, agy=a.agy, claude=a.claude, servis_yolu=a.servis)
    if a.json:
        print(json.dumps(anlik if not a.havuz else {**anlik, "havuzlar": {a.havuz: anlik["havuzlar"].get(a.havuz)}},
                         ensure_ascii=False, indent=2))
    else:
        print(metin(anlik, yalniz=a.havuz))
    return 0
