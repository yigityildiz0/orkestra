#!/usr/bin/env python3
"""Codex, Antigravity ve (anahtarı varsa) EVREN kotalarını model çağırmadan okur, atlas dışı yeni modelleri bulur.

Kaynaklar: `codex app-server` account/rateLimits/read, `agy -p /usage`, `agy models`,
~/.codex/models_cache.json, EVREN `GET /v1/quota` ve `GET /v1/models` (token harcamaz).
Kimlik/token çıktıya alınmaz: EVREN anahtarı yalnız EVREN_API_KEY ortam değişkeninden (Windows'ta
HKCU\\Environment) bellekte okunur, hiçbir yere yazılmaz; hata metninde yalnız istisna türü ve HTTP kodu.
Okunamayan kaynak yazılır; tahmin yok. Windows, macOS ve Linux'ta çalışır.
Kullanım: python -I kota_oku.py [--fresh]
"""
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


def _agy_yolu():
    if os.name == "nt":
        p = os.path.join(os.environ.get("LOCALAPPDATA", ""), "agy", "bin", "agy.exe")
        if os.path.exists(p):
            return p
    return shutil.which("agy")


AGY = _agy_yolu()
CACHE = os.path.join(os.path.expanduser("~"), ".codex", "models_cache.json")

# Atlasta tanınan modeller. Bunların dışındakiler "YENİ MODEL" diye bildirilir.
KNOWN_CODEX = {"gpt-6.1-sol", "gpt-6-astra", "gpt-6.1-terra", "gpt-6-sol", "gpt-6-luna",
               "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"}
KNOWN_AGY = {"gemini-4-argon-low", "gemini-4-argon-medium", "gemini-4-argon-high",
             "gemini-3.8-flash-low", "gemini-3.8-flash-medium", "gemini-3.8-flash-high",
             "claude-opus-5-5-low", "claude-opus-5-5-medium", "claude-opus-5-5-high",
             "claude-sonnet-5-5-low", "claude-sonnet-5-5-medium", "claude-sonnet-5-5-high",
             "gpt-oss-120b-medium"}


def find_codex():
    # Windows'ta en yeni sürüm hash klasöründedir (eski bin\codex.exe güncel model listesini okuyamaz).
    if os.name == "nt":
        c = glob.glob(os.path.join(os.environ.get("LOCALAPPDATA", ""), "OpenAI", "Codex", "bin", "*", "codex.exe"))
        if c:
            return max(c, key=os.path.getmtime)
    return shutil.which("codex")


def codex_limits():
    exe = find_codex()
    if not exe:
        return None
    p = subprocess.Popen([exe, "app-server"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL, text=True, encoding="utf-8")
    try:
        def send(o):
            p.stdin.write(json.dumps(o) + "\n")
            p.stdin.flush()
        send({"id": 1, "method": "initialize",
              "params": {"clientInfo": {"name": "kota", "version": "1"}}})
        p.stdout.readline()
        send({"method": "initialized"})
        send({"id": 2, "method": "account/rateLimits/read"})
        for _ in range(8):
            line = p.stdout.readline()
            if not line:
                break
            msg = json.loads(line)
            if msg.get("id") == 2:
                rl = msg["result"]["rateLimits"]
                out = {}
                for key, name in (("primary", "5s"), ("secondary", "hafta")):
                    w = rl.get(key)
                    if w:
                        out[name] = (100 - w["usedPercent"],
                                     datetime.fromtimestamp(w["resetsAt"], timezone.utc))
                return out
    finally:
        p.kill()
    return None


def agy_run(*args, timeout=90):
    if not AGY:
        raise FileNotFoundError("agy bulunamadı")
    return subprocess.run([AGY, *args], capture_output=True, text=True, encoding="utf-8",
                          timeout=timeout, stdin=subprocess.DEVNULL).stdout


def agy_limits():
    data = json.loads(agy_run("-p", "/usage", "--output-format", "json", "--print-timeout", "40s"))
    res = {}
    for g in data["command"]["data"]["groups"]:
        for b in g["buckets"]:
            res[(g["name"], b["window"])] = (round(b["remaining_fraction"] * 100), b["reset_time"])
    return res


# ---------------------------------------------------------------- EVREN (SSYZ, ücretsiz; anahtar varsa)
# Atlasta bilinen EVREN modelleri (seçicide olan + bilerek dışarıda bırakılan). Dışındaki sohbet modeli "YENİ MODEL".
KNOWN_EVREN = {"deepseek-v4.1-flash", "glm-5.3", "qwen3.8-flash-next", "gemma-4-31b", "qwen3-vl-30b", "auto",
               "mimo-v2.6-pro"}
EVREN_VARSAYILAN_TAVAN = 15_000_000
DURUM_TAZE = 600                       # sn: durum dosyası bundan yeniyse istek atılmaz


def durum_dizini():
    return os.environ.get("ORKESTRA_DIR") or os.path.join(os.path.expanduser("~"), ".orkestra")


def evren_durum_yolu():
    return os.path.join(durum_dizini(), "evren_durum.json")


def evren_anahtar():
    """EVREN_API_KEY: önce ortam, sonra (Windows) HKCU\\Environment. Değer döner ama ASLA yazdırılmaz/loglanmaz."""
    v = os.environ.get("EVREN_API_KEY")
    if v:
        return v.strip()
    if os.name == "nt":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
                v = winreg.QueryValueEx(k, "EVREN_API_KEY")[0]
                return str(v).strip() or None
        except OSError:
            return None
    return None


def evren_taban_url():
    return (os.environ.get("EVREN_BASE_URL") or "https://evren-llmapi.ssyz.org.tr/v1").rstrip("/")


class _Yonlendirmesiz(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None                                   # 3xx izlenmez: X-API-Key başka origin'e taşınmaz


def evren_taban_guvenli(taban):
    """Anahtar yalnız https'e (sınama için yerel http) gider."""
    from urllib.parse import urlsplit
    u = urlsplit(taban)
    return (u.scheme == "https" and bool(u.hostname)) or (u.scheme == "http" and (u.hostname or "") in ("127.0.0.1", "localhost", "::1"))


def _evren_get(yol, anahtar, zaman_asimi=8):
    """GET; (kod, başlıklar(küçük harf), json|None). Anahtar yalnız başlıkta; hata metnine girmez. Yönlendirme
    izlenmez (3xx kodu döner), taban https değilse istek atılmaz (ValueError)."""
    taban = evren_taban_url()
    if not evren_taban_guvenli(taban):
        raise ValueError("EVREN_BASE_URL https değil")
    req = urllib.request.Request(taban + yol, headers={"X-API-Key": anahtar, "Accept": "application/json",
                                                        "User-Agent": "orkestra-kota/1"})
    try:
        with urllib.request.build_opener(_Yonlendirmesiz).open(req, timeout=zaman_asimi) as r:
            ham = r.read()
            bas = {k.lower(): v for k, v in r.headers.items()}
            kod = r.status
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


def sonraki_gun_reset(simdi=None):
    """EVREN günlük penceresi 00:00Z'de (03:00 TSİ) yenilenir (API daily_reset_at verirse o geçer)."""
    simdi = simdi or datetime.now(timezone.utc)
    return (simdi + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)


def _zaman(x):
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        try:
            return datetime.fromtimestamp(x, timezone.utc)
        except (OverflowError, OSError, ValueError):          # 1e30, NaN, inf: bozuk kayıt, yok say
            return None
    if not isinstance(x, str) or not x:
        return None
    try:
        d = datetime.fromisoformat(x.replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _ilk(d, *yollar):
    for y in yollar:
        x = d
        for p in y.split("."):
            x = x.get(p) if isinstance(x, dict) else None
        if x is not None:
            return x
    return None


def evren_quota_coz(govde, basliklar, simdi=None):
    """/v1/quota gövdesi (+ x-evren-daily-remaining-tokens başlığı) -> durum sözlüğü ya da None.
    Ölçülmüş alanlar (2026-11-08): used_tokens, cap, window_minutes, reset_at, daily_used_tokens, daily_limit_tokens,
    daily_remaining_tokens, daily_reset_at, concurrent_requests, concurrency_limit, model_concurrency_limit,
    fair_share_active, level. Olası başka adlar da okunur."""
    simdi = simdi or datetime.now(timezone.utc)
    g = govde if isinstance(govde, dict) else {}
    tavan = _ilk(g, "daily_limit_tokens", "cap_tokens", "daily_token_quota", "daily.limit_tokens") or EVREN_VARSAYILAN_TAVAN
    kalan = _ilk(g, "daily_remaining_tokens", "remaining_tokens", "daily.remaining_tokens", "remaining")
    if kalan is None and g.get("daily_used_tokens") is not None:
        kalan = tavan - g["daily_used_tokens"]
    if kalan is None and basliklar.get("x-evren-daily-remaining-tokens"):
        try:
            kalan = float(basliklar["x-evren-daily-remaining-tokens"])
        except ValueError:
            kalan = None
    if g.get("exempt") is True:
        kalan = tavan
    if kalan is None:
        return None
    try:
        kalan, tavan = float(kalan), float(tavan)
    except (TypeError, ValueError):
        return None
    reset = _zaman(_ilk(g, "daily_reset_at", "resets_at", "daily.reset_at")) or sonraki_gun_reset(simdi)
    cap, kul = g.get("cap"), g.get("used_tokens")
    return {"zaman": simdi.timestamp(), "kalan": max(kalan, 0.0), "tavan": tavan, "reset": reset.isoformat(),
            "pencere_tavan": cap, "pencere_kalan": (cap - (kul or 0)) if isinstance(cap, (int, float)) else None,
            "pencere_dk": g.get("window_minutes"), "concurrent": g.get("concurrent_requests"),
            "concurrency_limit": g.get("concurrency_limit"), "model_concurrency_limit": g.get("model_concurrency_limit"),
            "fair_share": g.get("fair_share_active"), "level": g.get("level")}


DURUM_NOTLARI = []


def _durum_oku_kati(onar=False):
    """Durum sözlüğü; dosya yoksa ya da boşsa {}. UTF-8 BOM'u okur (PowerShell 5.1 Set-Content). Dosya o an
    okunamıyorsa (Windows os.replace anı) birkaç kez dener, yine olmazsa None (çağıran yazmaz: boş sözlükle bütün
    durumu ezmesin). İçerik kalıcı bozuksa (JSON değil, kök sözlük değil): onar=True (yazıcı, kilit altında) dosyayı
    .bozuk adıyla kenara alır ve {} döner (durum kendini onarır); onar=False None döner."""
    yol = evren_durum_yolu()
    bozuk = False
    for i in range(6):
        if not os.path.exists(yol):
            return {}
        try:
            with open(yol, encoding="utf-8-sig") as f:
                metin = f.read()
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
            os.replace(yol, yol + ".bozuk")
            DURUM_NOTLARI.append(f"durum dosyası bozuktu: {os.path.basename(yol)}.bozuk adıyla kenara alındı, boş durumla sürdü")
            return {}
        except OSError:
            return None
    return None


def durum_oku():
    return _durum_oku_kati() or {}


_DURUM_KILIT = threading.Lock()
KILIT_BAYAT_SN = 30


def _surec_kilidi_al(sure=3.0):
    """Süreçler arası kilit: O_EXCL ile evren_durum.json.lock (bayat: 30 sn). Alınamazsa None."""
    yol = evren_durum_yolu() + ".lock"
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
    """Atomik oku-değiştir-yaz: fn(d) durum sözlüğünü yerinde değiştirir. Yalnız sayılar/zamanlar (içerik ve anahtar
    asla). İş parçacıkları VE süreçler arası kilitli (paralel evren_suru süreçleri birbirinin tukendi_until/kalan/
    model_pay/soguma güncellemesini ezmez). Durum okunamıyorsa ya da kilit alınamıyorsa yazmaz (None); veri kaybettirmez."""
    with _DURUM_KILIT:
        os.makedirs(durum_dizini(), exist_ok=True)
        kilit = _surec_kilidi_al()
        if not kilit:
            return None
        try:
            d = _durum_oku_kati(onar=True)
            if d is None:
                return None
            fn(d)
            tmp = evren_durum_yolu() + f".{os.getpid()}.{threading.get_ident()}.tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False)
            for i in range(8):
                try:
                    os.replace(tmp, evren_durum_yolu())
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
    """Üst düzey alanları birleştirir (None değerler yazılmaz). Bkz. durum_guncelle."""
    return durum_guncelle(lambda d: d.update({k: v for k, v in ek.items() if v is not None}))


# ---------------------------------------------------------------- EVREN soğuma (dayanıklılık durumu)
# Durum dosyasının "soguma" alanı: {"<api model>" | "*": {"tur", "ardisik", "zaman", "busy_until"}}. "*" hesap
# düzeyidir (günlük kota, eşzamanlılık, 5 dk token penceresi): bütün EVREN modelleri. Kaydı sunucu sınırını
# (429/503) gören evren_suru yazar; seçici (kapasite) ve kota_oku okur. Süre dolunca kayıt "yoklama" durumuna
# geçer: ilk çağrı küçük bir ping ile yoklar (başarı → kayıt silinir, hata → ardışık+1, soğuma uzar).
GENEL = "*"
SOGUMA_KISA_SN = 60          # bu kadar kısa bekleme isteyen hata aynı modelde beklenir (soğumaya alınmaz)
SOGUMA_HATIRLA_SN = 3600     # ardışık sayısı bu süre içinde birikir; süresi dolalı 1 saati geçen kayıt unutulur
SOGUMA_TAVAN_SN = 36 * 3600  # hiçbir soğuma (günlük dahil) bundan uzun sürmez: bozuk/uç sunucu değeri EVREN'i kilitlemesin
SOGUMA_ESZAMAN_SN = 30       # aktif kaydın ilk 30 sn'sinde gelen aynı hata (başka süreç, aynı olay) ardışığı artırmaz
SOGUMA_TUR_AD = {"503": "sunucu dolu (503)", "fair_share": "model payı dolu (fair share)",
                 "concurrency": "eşzamanlılık sınırı", "token_rate": "5 dk token penceresi dolu",
                 "daily": "günlük kota bitti", "ag": "ağ hatası", "diger": "sunucu hatası"}


def soguma_suresi(tur, ardisik=1, simdi=None, bitis=None):
    """Hata türüne göre soğuma (sn). bitis: sunucunun bildirdiği resets_at / daily_reset_at (datetime) varsa.
    503: 5-10-20 dk üstel (sunucu daha uzun derse o, en çok 60 dk); günlük: sonraki sıfırlama (daily_reset_at, yoksa
    00:00Z = 03:00 TSİ); token penceresi: resets_at (yoksa 5 dk); fair share 2-4-8 dk; eşzamanlılık kısa (30 sn × n, ≤5 dk)."""
    simdi = simdi or datetime.now(timezone.utc)
    n = max(int(ardisik or 1), 1)
    ipucu = (bitis - simdi).total_seconds() if bitis else None
    ipucu = ipucu if ipucu and ipucu > 0 else None
    if tur == "daily":
        return min(max(ipucu or (sonraki_gun_reset(simdi) - simdi).total_seconds(), 60.0), float(SOGUMA_TAVAN_SN))
    if tur == "503":
        return float(min(max(min(300 * 2 ** (n - 1), 1200), ipucu or 0), 3600))
    if tur == "token_rate":
        return float(min(max(ipucu or 300, 30), 900))
    if tur == "fair_share":
        return float(min(max(120 * 2 ** (n - 1), ipucu or 0), 600))
    if tur == "concurrency":
        return float(min(max(30 * n, ipucu or 0), 300))
    return float(min(60 * n, 600))


def soguma_kaydet(ad, tur, bitis=None, simdi=None):
    """`ad` (api model adı ya da "*") için soğuma kaydı; ardışık hata 1 saat içinde birikir. Dönüş: kayıt.
    Kayıt hâlâ aktifse süre kısalmaz (busy_until = max(eski, yeni), uzun olanın türü kalır; ör. günlük '*' üstüne gelen
    token penceresi onu 4 dk'ya düşürmez). Aktif kaydın ilk 30 sn'sinde gelen hata ardışığı artırmaz (iki süreç aynı
    503'ü görünce 5 dk yerine 10 dk yazılmasın)."""
    simdi = simdi or datetime.now(timezone.utc)
    out = {}

    def f(d):
        s = d.get("soguma") if isinstance(d.get("soguma"), dict) else {}
        eski = s.get(ad) if isinstance(s.get(ad), dict) else {}
        try:
            son = float(eski.get("zaman") or 0)
            n0 = int(eski.get("ardisik") or 0)
        except (TypeError, ValueError, OverflowError):
            son, n0 = 0.0, 0
        eski_b = _zaman(eski.get("busy_until"))
        aktif = bool(eski_b and eski_b > simdi)
        if aktif and 0 <= simdi.timestamp() - son < SOGUMA_ESZAMAN_SN:
            n, zaman_ = max(n0, 1), son                       # aynı olay: ardışık artmaz, pencere ilk kayda bağlı
        else:
            n = n0 + 1 if simdi.timestamp() - son < SOGUMA_HATIRLA_SN else 1
            zaman_ = simdi.timestamp()
        tur_h = tur
        if tur in ("ag", "diger") and n > 1 and eski.get("tur") in ("503", "fair_share", "concurrency", "token_rate"):
            tur_h = str(eski["tur"])     # bilgi taşımayan hata (ağ, 502) önceki 'dolu' soğumasını kısaltmasın: yoklama
        sn = soguma_suresi(tur_h, n, simdi, bitis)   # başarısız → aynı türde bir kademe uzar (503×2 → ×3 = 20 dk)
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
    """Başarılı çağrı/yoklama: `ad` kaydı ve (sunucu yanıt verdiğine göre) "*" kaydı silinir; yalnız süresi dolmamış
    günlük "*" kalır (günlük kota başka modelde de bitmiştir).
    ad=None: hepsi. yalniz=True (elle `soguma --temizle <model>`): yalnız o anahtar silinir, "*" dokunulmaz."""
    def f(d):
        s = d.get("soguma") if isinstance(d.get("soguma"), dict) else {}
        if ad is None:
            s = {}
        elif yalniz:
            s.pop(ad, None)
        else:
            s.pop(ad, None)
            g = s.get(GENEL) if isinstance(s.get(GENEL), dict) else {}
            b = _zaman(g.get("busy_until"))
            if ad != GENEL and not (g.get("tur") == "daily" and b and b > (simdi or datetime.now(timezone.utc))):
                s.pop(GENEL, None)
        d["soguma"] = s
    return durum_guncelle(f)


def soguma_oku(simdi=None, ham=None):
    """{ad: {"tur", "ardisik", "busy_until"(datetime), "kalan_sn", "durum": "aktif"|"yoklama"}}. ham verilmezse durum
    dosyasından. Süresi 1 saatten uzun önce dolmuş kayıt yok sayılır (iyileşmiş). Bozuk kayıt atlanır (diğerleri
    geçerli kalır). Kalan süre en çok 36 sa (bozuk/uç değer EVREN'i kalıcı kilitlemesin)."""
    simdi = simdi or datetime.now(timezone.utc)
    if ham is None:
        ham = durum_oku().get("soguma")
    out = {}
    for ad, k in (ham.items() if isinstance(ham, dict) else []):
        if not isinstance(k, dict):
            continue
        try:
            b = _zaman(k.get("busy_until"))
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
    """Kısa özet: 'glm-5.3 sunucu dolu (503) ×2, 12 dk kaldı; deepseek-v4.1-flash soğuma bitti, yoklama bekliyor'."""
    parca = []
    for ad, k in sorted(sg.items(), key=lambda x: (x[0] != GENEL, x[0])):
        ad_ = "EVREN (tümü)" if ad == GENEL else ad
        tur = SOGUMA_TUR_AD.get(k["tur"], k["tur"]) + (f" ×{k['ardisik']}" if k["ardisik"] > 1 else "")
        if k["durum"] == "aktif":
            dk = k["kalan_sn"] / 60
            parca.append(f"{ad_} {tur}, " + (f"{dk / 60:.1f} sa kaldı" if dk >= 90 else f"{max(dk, 1):.0f} dk kaldı"))
        else:
            parca.append(f"{ad_} soğuma bitti, yoklama bekliyor (ilk çağrı ping atar)")
    return "; ".join(parca)


EVREN_SON_NEDEN = {"neden": None}


def evren_limits(simdi=None, ag=True, _get=None):
    """{'gun': (kalan_yuzde, reset_dt)} ya da None (havuz yok/okunamadı; neden EVREN_SON_NEDEN'de).
    Sıra: anahtar yoksa None; durum dosyasında tukendi_until gelecekteyse %0; durum 10 dk'dan yeniyse o (istek yok);
    GET /v1/quota; olmazsa eski durum (son 00:00Z'den sonraysa o değer, önceyse %100); o da yoksa None
    (seçici platformlar.json `kota` değerini varsayım olarak kullanır)."""
    simdi = simdi or datetime.now(timezone.utc)
    anahtar = evren_anahtar()
    if not anahtar:
        EVREN_SON_NEDEN["neden"] = "OKUNAMADI (anahtar yok)"
        return None
    d = durum_oku()
    tk = _zaman(d.get("tukendi_until"))
    if tk and tk > simdi + timedelta(seconds=SOGUMA_TAVAN_SN):
        tk = simdi + timedelta(seconds=SOGUMA_TAVAN_SN)      # bozuk/uç değer: en çok 36 sa
    g = soguma_oku(simdi, d.get("soguma")).get(GENEL)
    if g and g["tur"] == "daily" and g["durum"] == "aktif" and (not tk or g["busy_until"] > tk):
        tk = g["busy_until"]
    if tk and tk > simdi:
        EVREN_SON_NEDEN["neden"] = "günlük kota bitti"
        return {"gun": (0, tk)}

    def yuzde(x):
        return ((round(100.0 * x["kalan"] / x["tavan"], 1) if x.get("tavan") else 0.0),
                _zaman(x.get("reset")) or sonraki_gun_reset(simdi))
    if d.get("kalan") is not None and d.get("tavan") and simdi.timestamp() - d.get("zaman", 0) < DURUM_TAZE:
        EVREN_SON_NEDEN["neden"] = None
        return {"gun": yuzde(d)}
    if ag:
        try:
            kod, bas, govde = (_get or _evren_get)("/quota", anahtar)
            if kod in (401, 403):
                EVREN_SON_NEDEN["neden"] = f"OKUNAMADI (anahtar/şart, HTTP {kod})"
                return None
            if kod == 200:
                x = evren_quota_coz(govde, bas, simdi)
                if x:
                    durum_yaz(x)
                    EVREN_SON_NEDEN["neden"] = None
                    return {"gun": yuzde(x)}
            EVREN_SON_NEDEN["neden"] = f"OKUNAMADI (HTTP {kod})"
        except Exception as e:
            EVREN_SON_NEDEN["neden"] = f"OKUNAMADI ({type(e).__name__})"
    if d.get("kalan") is not None and d.get("tavan"):
        son_reset = sonraki_gun_reset(simdi) - timedelta(days=1)
        if d.get("zaman", 0) >= son_reset.timestamp():
            return {"gun": yuzde(d)}
        return {"gun": (100.0, sonraki_gun_reset(simdi))}
    return None


OKUYUCU = {"evren": evren_limits}


def ek_limitler(ad):
    """Genel kanca: platformlar.json'da `kota_okuyucu` adı verilen havuzun okuyucusu. Bilinmeyen ad: None."""
    f = OKUYUCU.get(ad)
    return f() if f else None


def evren_modeller(_get=None):
    """GET /v1/models (anahtar yoksa None). Token harcamaz."""
    anahtar = evren_anahtar()
    if not anahtar:
        return None
    kod, _, govde = (_get or _evren_get)("/models", anahtar)
    if kod != 200 or not isinstance(govde, dict):
        raise RuntimeError(f"HTTP {kod}")
    return [m for m in govde.get("data", []) if isinstance(m, dict)]


def kontrol_testleri():
    """Ağsız sınamalar (kapasite.py kontrol çağırır): sahte anahtar, sahte GET, geçici durum dizini."""
    import tempfile
    global evren_anahtar
    sonuc = []
    eski = {k: os.environ.get(k) for k in ("EVREN_API_KEY", "ORKESTRA_DIR")}
    gercek = evren_anahtar
    td = tempfile.mkdtemp(prefix="orkestra_kota_")
    os.environ["ORKESTRA_DIR"] = td
    simdi = datetime(2026, 11, 11, 10, 0, tzinfo=timezone.utc)

    def sil():
        try:
            os.unlink(evren_durum_yolu())
        except OSError:
            pass

    def yasak(*a, **k):
        raise AssertionError("istek atılmamalı")
    try:
        os.environ.pop("EVREN_API_KEY", None)
        evren_anahtar = lambda: None                                  # noqa: E731 (HKCU'yu da okumasın)
        r = evren_limits(simdi, _get=yasak)
        sonuc.append(("anahtar yok: None, 'OKUNAMADI (anahtar yok)', istek yok",
                      r is None and EVREN_SON_NEDEN["neden"] == "OKUNAMADI (anahtar yok)"))
        evren_anahtar = lambda: "TEST-KEY-123"                        # noqa: E731

        def sahte(yol, anahtar, **k):
            return 200, {}, {"daily_remaining_tokens": 7_500_000, "daily_limit_tokens": 15_000_000,
                             "concurrent_requests": 2, "concurrency_limit": 32, "cap": 2_500_000, "used_tokens": 0}
        r = evren_limits(simdi, _get=sahte)
        sonuc.append(("sahte /v1/quota 7.5M/15M → gun %50, reset sonraki 00:00Z (03:00 TSİ)",
                      bool(r) and r["gun"][0] == 50.0 and r["gun"][1] == datetime(2026, 11, 12, tzinfo=timezone.utc)))
        with open(evren_durum_yolu(), encoding="utf-8") as f:
            ham = f.read()
        sonuc.append(("durum dosyasına eşzamanlılık ve 5 dk pencere yazılır, anahtar değeri yazılmaz",
                      '"concurrency_limit": 32' in ham and '"pencere_tavan": 2500000' in ham and "TEST-KEY-123" not in ham))
        r = evren_limits(simdi, _get=yasak)
        sonuc.append(("durum 10 dk'dan yeni → istek atılmaz", bool(r) and r["gun"][0] == 50.0))
        sil()
        r = evren_limits(simdi, _get=lambda *a, **k: (200, {"x-evren-daily-remaining-tokens": "3000000"}, {}))
        sonuc.append(("gövde yok, yalnız başlık → başlıktan okur (%20)", bool(r) and r["gun"][0] == 20.0))
        sil()
        r = evren_limits(simdi, _get=lambda *a, **k: (200, {}, {"exempt": True}))
        sonuc.append(("exempt: true → %100", bool(r) and r["gun"][0] == 100.0))
        sil()
        r = evren_limits(simdi, _get=lambda *a, **k: (403, {}, {"error": {"code": "terms_not_accepted"}}))
        sonuc.append(("403 → None, 'anahtar/şart'", r is None and "şart" in (EVREN_SON_NEDEN["neden"] or "")))
        durum_yaz({"tukendi_until": "2026-11-12T00:00:00+00:00"})
        r = evren_limits(simdi, _get=sahte)
        sonuc.append(("tukendi_until gelecekte → %0", bool(r) and r["gun"][0] == 0))
        sil()
        durum_yaz({"zaman": (simdi - timedelta(days=1)).timestamp(), "kalan": 1000.0, "tavan": 15e6})
        r = evren_limits(simdi, _get=lambda *a, **k: (500, {}, None))
        sonuc.append(("okunamadı, eski durum dünkü → %100 (gün yenilendi)", bool(r) and r["gun"][0] == 100.0))
        sil()
        r = evren_limits(simdi, _get=lambda *a, **k: (500, {}, None))
        sonuc.append(("okunamadı, durum yok → None (seçici notlu varsayım kullanır)", r is None))
        sonuc.append(("ek_limitler bilinmeyen okuyucu → None", ek_limitler("yok-boyle") is None))
        # süreçler arası kilit: 3 süreç × 60 farklı anahtar aynı durum dosyasına → hiçbiri kaybolmaz
        sil()
        betik = ("import importlib.util,sys;s=importlib.util.spec_from_file_location('k',sys.argv[1]);"
                 "m=importlib.util.module_from_spec(s);s.loader.exec_module(m);"
                 "[m.durum_yaz({sys.argv[2]+str(i):i}) for i in range(60)]")
        ortam = dict(os.environ, ORKESTRA_DIR=td)
        ps = [subprocess.Popen([sys.executable, "-I", "-c", betik, os.path.abspath(__file__), ad], env=ortam,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) for ad in ("A", "B", "C")]
        for p_ in ps:
            p_.wait(timeout=120)
        d = durum_oku()
        sonuc.append(("3 paralel süreç × 60 durum_yaz: 180 anahtarın hepsi korunur (süreçler arası kilit)",
                      sum(1 for k in d if k[:1] in "ABC") == 180))
        with open(evren_durum_yolu() + ".lock", "w") as f:            # bayat kilit (ölü süreç)
            f.write("1")
        os.utime(evren_durum_yolu() + ".lock", (time.time() - 120, time.time() - 120))
        sonuc.append(("bayat süreç kilidi (30 sn'den eski) temizlenir, yazım sürer", bool(durum_yaz({"z1": 1}))
                      and durum_oku().get("z1") == 1))
        # EVREN soğuma: süreler, ardışık birikim, yoklama durumu, temizleme, günlük → %0
        sil()
        s1, s2, s3, s4 = (soguma_suresi("503", n, simdi) for n in (1, 2, 3, 4))
        sonuc.append(("soğuma 503: 5/10/20 dk üstel, 20 dk tavan", (s1, s2, s3, s4) == (300, 600, 1200, 1200)))
        sonuc.append(("soğuma 503: sunucu resets_at 35 dk derse o (≤60 dk)",
                      soguma_suresi("503", 1, simdi, simdi + timedelta(minutes=35)) == 2100))
        sonuc.append(("soğuma günlük: daily_reset_at yoksa sonraki 00:00Z (03:00 TSİ)",
                      soguma_suresi("daily", 1, simdi) == (sonraki_gun_reset(simdi) - simdi).total_seconds()))
        sonuc.append(("soğuma eşzamanlılık kısa (≤5 dk), token penceresi resets_at",
                      soguma_suresi("concurrency", 9, simdi) <= 300
                      and soguma_suresi("token_rate", 1, simdi, simdi + timedelta(minutes=4)) == 240))
        k1 = soguma_kaydet("glm-5.3", "503", simdi=simdi)
        k2 = soguma_kaydet("glm-5.3", "503", simdi=simdi + timedelta(minutes=6))
        sg = soguma_oku(simdi + timedelta(minutes=7))
        sonuc.append(("soğuma kaydı: ikinci 503 ardışık 2, süre uzar (5 → 10 dk), durum aktif",
                      k1["ardisik"] == 1 and k2["ardisik"] == 2 and sg["glm-5.3"]["durum"] == "aktif"
                      and 8 * 60 < sg["glm-5.3"]["kalan_sn"] <= 9 * 60))
        sg = soguma_oku(simdi + timedelta(minutes=20))
        sonuc.append(("soğuma süresi dolunca 'yoklama' (aday döner, ilk çağrı ping)", sg["glm-5.3"]["durum"] == "yoklama"))
        sonuc.append(("süresi 1 saatten eski dolmuş kayıt yok sayılır", "glm-5.3" not in soguma_oku(simdi + timedelta(hours=2))))
        soguma_kaydet(GENEL, "concurrency", simdi=simdi)
        soguma_temizle("glm-5.3", simdi=simdi)
        sg = soguma_oku(simdi)
        sonuc.append(("başarı: model kaydı ve günlük olmayan '*' kaydı silinir", "glm-5.3" not in sg and GENEL not in sg))
        soguma_kaydet(GENEL, "daily", bitis=simdi + timedelta(hours=14), simdi=simdi)
        soguma_temizle("deepseek-v4.1-flash", simdi=simdi)
        r = evren_limits(simdi, _get=yasak)
        sonuc.append(("günlük '*' soğuma başarıyla silinmez ve kota %0 gösterir (istek yok)",
                      GENEL in soguma_oku(simdi) and bool(r) and r["gun"][0] == 0))
        sonuc.append(("soğuma metni: dk/sa ve yoklama yazar", "sa kaldı" in soguma_metni(soguma_oku(simdi))
                      and "yoklama" in soguma_metni({"x": {"tur": "503", "ardisik": 1, "busy_until": simdi,
                                                           "kalan_sn": 0, "durum": "yoklama"}})))
        bozuk = soguma_oku(simdi, {"a": "x", "b": {"busy_until": "yok"},
                                   "c": {"busy_until": (simdi + timedelta(minutes=3)).isoformat(), "ardisik": "?"}})
        sonuc.append(("bozuk soğuma kaydı atlanır, çökmez", list(bozuk) == ["c"] and bozuk["c"]["ardisik"] == 1))
        # dayanıklılık düzeltmeleri (denetim 2026-11-09)
        iyi = {"busy_until": (simdi + timedelta(hours=10)).isoformat(), "tur": "daily", "ardisik": 1}
        uc = soguma_oku(simdi, {"glm-5.3": {"busy_until": 1e30}, "x": {"busy_until": float("nan")},
                                "y": {"busy_until": float("inf")}, GENEL: iyi})
        sonuc.append(("busy_until 1e30/NaN/inf: yalnız o kayıt atlanır, geçerli günlük '*' kalır (çökmez)",
                      list(uc) == [GENEL] and uc[GENEL]["tur"] == "daily"))
        sil()
        with open(evren_durum_yolu(), "w", encoding="utf-8-sig") as f:      # PowerShell 5.1 Set-Content -Encoding UTF8
            json.dump({"soguma": {GENEL: dict(iyi, tur="503")}}, f)
        sonuc.append(("UTF-8 BOM'lu durum dosyası okunur (geçerli '*' soğuma yok sayılmaz)",
                      soguma_oku(simdi).get(GENEL, {}).get("tur") == "503"))
        for ad_, icerik in (("bozuk JSON", "{ bozuk json"), ("liste kökü", "[1,2,3]")):
            sil()
            with open(evren_durum_yolu(), "w", encoding="utf-8") as f:
                f.write(icerik)
            k = soguma_kaydet("glm-5.3", "503", simdi=simdi)
            sonuc.append((f"{ad_}: dosya .bozuk adıyla kenara alınır, soğuma yazılır (kendini onarır)",
                          not k.get("yazilamadi") and "glm-5.3" in soguma_oku(simdi) and os.path.exists(evren_durum_yolu() + ".bozuk")))
            os.unlink(evren_durum_yolu() + ".bozuk")
        sil()
        with open(evren_durum_yolu(), "w", encoding="utf-8") as f:
            f.write("")
        sonuc.append(("boş durum dosyası {} sayılır, yazım sürer", bool(durum_yaz({"z2": 2})) and durum_oku().get("z2") == 2))
        sil()
        soguma_kaydet(GENEL, "daily", bitis=simdi + timedelta(hours=10), simdi=simdi)
        k = soguma_kaydet(GENEL, "token_rate", bitis=simdi + timedelta(minutes=4), simdi=simdi + timedelta(minutes=1))
        sonuc.append(("aktif günlük '*' üstüne token penceresi: süre kısalmaz, tür günlük kalır",
                      k["tur"] == "daily" and soguma_oku(simdi)[GENEL]["kalan_sn"] >= 9.9 * 3600))
        sil()
        k1 = soguma_kaydet("glm-5.3", "503", simdi=simdi)
        k2 = soguma_kaydet("glm-5.3", "503", simdi=simdi + timedelta(seconds=5))
        sonuc.append(("iki süreç aynı 503'ü 30 sn içinde: ardışık 1 kalır (5 dk, 10 dk değil)",
                      k1["ardisik"] == 1 and k2["ardisik"] == 1 and soguma_oku(simdi)["glm-5.3"]["kalan_sn"] <= 310))
        sil()
        soguma_kaydet(GENEL, "daily", bitis=datetime(2099, 1, 1, tzinfo=timezone.utc), simdi=simdi)
        sonuc.append(("uç daily_reset_at (2099): soğuma en çok 36 sa", soguma_oku(simdi)[GENEL]["kalan_sn"] <= 36 * 3600))
        durum_yaz({"tukendi_until": "2099-01-01T00:00:00+00:00"})
        r = evren_limits(simdi, _get=yasak)
        sonuc.append(("uç tukendi_until (2099): kota reseti en çok 36 sa sonra", bool(r) and r["gun"][1] <= simdi + timedelta(hours=36)))
        sil()
        soguma_kaydet(GENEL, "token_rate", simdi=simdi)
        soguma_kaydet("glm-5.3", "503", simdi=simdi)
        soguma_temizle("glm-5.3", simdi=simdi, yalniz=True)
        sg = soguma_oku(simdi)
        sonuc.append(("elle tek model temizleme (yalniz): '*' token penceresi kalır", "glm-5.3" not in sg and GENEL in sg))
        sil()
        soguma_kaydet(GENEL, "token_rate")      # gerçek saat: soguma_ekle canlı okur (sabit test saati 11 Kasım'dan sonra bayatlar)
        bayat = "== KALAN KOTA ==\nevren  gun    %50\nevren  SOĞUMA: glm-5.3 sunucu dolu (503), 12 dk kaldı\n" \
                "       (seçici soğuyan modeli aday dışı bırakır; x)\nClaude Max: y\n"
        yeni = soguma_ekle(bayat)
        sonuc.append(("kota çıktısı: önbellekteki bayat SOĞUMA satırı atılır, canlısı 'Claude Max' önüne",
                      "12 dk kaldı" not in yeni and yeni.index("SOĞUMA: EVREN (tümü)") < yeni.index("Claude Max")))
        sil()
        durum_yaz({"soguma": {"glm-5.3": {"tur": "503", "ardisik": 2, "zaman": simdi.timestamp() - 700,
                                          "busy_until": (simdi - timedelta(minutes=1)).isoformat()}}})
        k = soguma_kaydet("glm-5.3", "ag", simdi=simdi)
        sonuc.append(("süresi dolmuş 503×2 sonrası yoklamada ağ hatası: soğuma kısalmaz (503×3 = 20 dk, 'ag' 3 dk değil)",
                      k["tur"] == "503" and k["ardisik"] == 3 and soguma_oku(simdi)["glm-5.3"]["kalan_sn"] >= 1190))
        soguma_temizle()
    finally:
        evren_anahtar = gercek
        for k, v in eski.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(td, ignore_errors=True)
    return sonuc


def new_models():
    found = []
    try:
        ms = evren_modeller()
        for m in ms or []:
            if m.get("task", "chat") == "chat" and m.get("id") not in KNOWN_EVREN:
                found.append(("evren", m.get("id")))
    except Exception:
        found.append(("evren", "LİSTE OKUNAMADI"))
    if AGY:
        try:
            for line in agy_run("models").splitlines():
                slug = line.split("\t")[0].strip()
                if slug.startswith(("gemini", "claude", "gpt")) and slug not in KNOWN_AGY:
                    found.append(("agy", slug))
        except Exception:
            found.append(("agy", "LİSTE OKUNAMADI"))
    if os.path.exists(CACHE):
        try:
            with open(CACHE, encoding="utf-8") as f:
                d = json.load(f)
            for m in d.get("models", d):
                if m.get("visibility") == "list" and m.get("slug") not in KNOWN_CODEX:
                    found.append(("codex", m["slug"]))
        except Exception:
            found.append(("codex", "LİSTE OKUNAMADI"))
    return found


CACHE_FILE = os.path.join(os.environ.get("TEMP") or os.environ.get("TMPDIR") or ".", "orkestra_kota_onbellek.txt")
CACHE_TTL = 600  # sn; kota okumak model çağırmaz ama birkaç sn sürer, her işçiye tekrarlanmasın


def main():
    """Önbellekli giriş: 10 dk içinde tekrar çağrılırsa eski çıktıyı basar. --fresh zorlar."""
    import io
    import time
    from contextlib import redirect_stdout
    sys.stdout.reconfigure(encoding="utf-8")
    if "--fresh" not in sys.argv:
        try:
            age = time.time() - os.path.getmtime(CACHE_FILE)
            if age < CACHE_TTL:
                with open(CACHE_FILE, encoding="utf-8") as f:
                    print(soguma_ekle(f.read()).rstrip())
                print(f"\n(önbellek: {int(age)} sn önce okundu; yenilemek için --fresh; SOĞUMA satırı canlı)")
                return 0
        except OSError:
            pass
    buf = io.StringIO()
    with redirect_stdout(buf):
        run()
    text = buf.getvalue()
    print(soguma_ekle(text).rstrip())
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            f.write(text)
    except OSError:
        pass
    return 0


def soguma_satirlari():
    """Canlı soğuma satırları (dosyadan, istek yok). Önbelleğe girmez: önbellekten dönen 'N dk kaldı' bayat olmasın."""
    try:
        sg = soguma_oku() if evren_anahtar() else {}
    except Exception:
        return []
    if not sg:
        return []
    return [f"evren  SOĞUMA: {soguma_metni(sg)}",
            "       (seçici soğuyan modeli aday dışı bırakır; `evren_suru soguma` ayrıntı, `--temizle` siler)"]


def soguma_ekle(metin):
    """Kota metnindeki (önbellekli ya da yeni) SOĞUMA satırlarını atıp canlılarını 'Claude Max' satırından önce koyar."""
    satir = [s for s in metin.splitlines() if not s.startswith("evren  SOĞUMA:")
             and not s.startswith("       (seçici soğuyan modeli")]
    canli = soguma_satirlari()
    i = next((j for j, s in enumerate(satir) if s.startswith("Claude Max:")), len(satir))
    return "\n".join(satir[:i] + canli + satir[i:]) + "\n"


def run():
    print("== KALAN KOTA (model çağrısı yapılmadı) ==")
    try:
        cx = codex_limits()
        for k, (left, reset) in (cx or {}).items():
            print(f"codex  {k:6s} %{left:<3d} reset {reset:%Y-%m-%d %H:%M}Z")
        if not cx:
            print("codex  OKUNAMADI (kurulu değil veya giriş yapılmamış)")
    except Exception as e:
        print(f"codex  OKUNAMADI ({type(e).__name__})")
    try:
        ag = agy_limits()
        for (grp, win), (left, reset) in ag.items():
            print(f"agy    {grp[:24]:24s} {win:7s} %{left:<3d} reset {reset}")
    except Exception as e:
        print(f"agy    OKUNAMADI ({type(e).__name__})")
    try:
        ev = evren_limits()
        if ev:
            d = durum_oku()
            left, reset = ev["gun"]
            print(f"evren  gun    %{left:<5g} reset {reset:%Y-%m-%d %H:%M}Z"
                  + (f" (kalan {d['kalan'] / 1e6:.1f}M / {d['tavan'] / 1e6:.0f}M)" if d.get("kalan") is not None else "")
                  + (f" | eşzamanlı {d.get('concurrent')}/{d.get('concurrency_limit')}" if d.get("concurrency_limit") else ""))
        elif EVREN_SON_NEDEN["neden"] != "OKUNAMADI (anahtar yok)":
            print(f"evren  {EVREN_SON_NEDEN['neden']}")
    except Exception as e:
        print(f"evren  OKUNAMADI ({type(e).__name__})")
    print("Claude Max: get_usage aracıyla (masaüstü uygulaması) veya /usage ile okunur.")

    nm = new_models()
    print("\n== MODEL KEŞFİ ==")
    if nm:
        for host, slug in nm:
            print(f"YENİ MODEL ({host}): {slug} -> atlas dışı; /orkestra güncelle ile kademeye yerleştir")
    else:
        print("Atlas dışı yeni model yok.")
    print("\nModel seçimi: kapasite betiği (kota + zeka + kalan iş + harcanabilirlik):")
    print("  python -I <kapasite betiği> --sinif <sınıf> --is <İB> --claude-5s <kalan%> --claude-hafta <kalan%>")


if __name__ == "__main__":
    sys.exit(main())
