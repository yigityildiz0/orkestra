#!/usr/bin/env python3
"""EVREN tek çağrı / sürü aracı (yalnız stdlib). EVREN (SSYZ) OpenAI uyumlu /v1/chat/completions ucuna N paralel
çağrı yapar, sonuçları yönteme göre birleştirir. EVREN ÇIKTISI ASLA KOD OLARAK ÇALIŞTIRILMAZ: adaylar yalnız dosyaya
yazılır; testi lider ayrı kopyada kendisi koşar.

Güvenlik ve gizlilik (varsayılan kapalı):
- Anahtar yalnız EVREN_API_KEY ortam değişkeninden (Windows'ta HKCU\\Environment), bellekte. argv'ye, dosyaya,
  log'a, hata metnine yazılmaz; çıktılar ve hata metinleri anahtar değerine ve "Bearer …"a karşı maskelenir.
- `--veri genel` zorunlu (yoksa çıkış 2). Gönderimden önce içerik taraması (anahtar kalıpları, anahtarın kendisi,
  sağlamalı TCKN, TR IBAN, Luhn kart, e-posta, +90 telefon, sağlık terimleri, gizli dosya yolu) ve yol yasağı
  (.ssh, .env, auth.json, *.pem/*.key, ~/.codex + platformlar.json `yasak_yol`). Eşleşme: çıkış 3, sıfır istek,
  yalnız eşleşen TÜRÜN adı yazılır; geçersiz kılma yok.
Dayanıklılık: dosya kilitli slotlar (toplam esz), model payı AIMD (fair_share'de düşer, 10 başarıda +1), 5 dk token
kovası (pencere tavanının %80'i), 429 Retry-After (≤60 sn) / resets_at bekleme, 503'te bant içi sonraki model,
400 unsupported_parameter'da parametreyi bir kez çıkarma, `length`/boş yanıtta bir kez max_tokens × 2.
Stratejik soğuma (kalıcı, süreçler arası: ~/.orkestra/evren_durum.json "soguma", kilitli ve atomik; kota_oku yazar/okur):
  (a) kısa ipucu (Retry-After/resets_at ≤ 60 sn) → aynı modelde üstel bekleme + jitter (en çok 2 kez);
  (b) uzun/ipucusuz 503, fair share → model soğumaya (503: 5-10-20 dk üstel), aynı Z bandındaki kardeş modele geçiş
      (--sinif eşiğinin ve birincil Z−1'in altına inilmez; --kardessiz kapatır);
  (c) günlük kota (daily_reset_at, yoksa 00:00Z = 03:00 TSİ), 5 dk token penceresi, eşzamanlılık → "*" (tüm EVREN)
      soğuma; seçici bu süre boyunca EVREN'siz sıralar. Soğuyan model sıfır istekle atlanır; hepsi soğumadaysa çıkış 4.
  Süre dolunca ilk çağrı 16 token'lık ping ile yoklar: başarı → kayıt silinir, hata → ardışık+1, soğuma uzar.
  Sürüde aynı hata bir çalıştırmada bir kez sayılır (20 paralel 503 ardışığı 20 artırmaz).

Alt komutlar:
  calistir (varsayılan)  --veri genel --model m[:efor][,m2:efor] --istem <dosya|-> [--yontem tek|kapali|test|kapsam|acik|ilk|juri]
                         [--n 3 --genislet 5 --sistem <dosya> --sema <json dosyası> --kaynaklar <klasör> --max-tokens 4096
                          --sure-sn 1800 --cikti <klasör> --uzanti py --kuru]
  toplu <girdi.jsonl>    öğe başına N (kapali/tek), ortak eşzamanlılık; pilot: ilk 20 öğede uyuşmazlık > %40 → çıkış 5
  ping                   16 token'lık canlı hız/kuyruk ölçümü (sabit, kamuya açık içerik)
  kota                   GET /v1/quota özeti (token harcamaz)
  modeller               GET /v1/models listesi (token harcamaz; /orkestra güncelle için)
  tara <dosya|klasör>    gizlilik taraması (istek yok)
  kabul <ozet.json> evet|hayir [--sinif s]   kalite kaydı (~/.orkestra/kalite_kayit.jsonl; içerik yok)
  soguma [--temizle <model>|*|hepsi]         soğuma durumu (istek yok); temizle elle siler
  kontrol                ağsız birim sınamaları
Çıkış: 0 tamam, 2 ayar/argüman/anahtar yok, 3 gizlilik reddi, 4 EVREN kullanılamıyor (günlük kota, şart, 503/429
tükendi, tüm denemeler hata) → seçicide --haric evren, 5 uzlaşma/aday yok → yükselt (daha güçlü model).
stdout: içeriksiz tek satır JSON; içerik yalnız <cikti>/aday_XX.* ve <cikti>/ozet.json'da.
"""
import argparse
import concurrent.futures as cf
import hashlib
import importlib.util
import json
import math
import os
import random
import re
import secrets
import sys
import threading
import time
import unicodedata
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
KOTA_DOSYA = os.path.join(HERE, "kota_oku.py")
VARSAYILAN_TABAN = "https://evren-llmapi.ssyz.org.tr/v1"
GUNLUK_TAVAN = 15_000_000
PENCERE_SN, PENCERE_TAVAN = 300, 2_500_000      # ölçülen: 5 dk pencerede 2.5M token
KOVA_PAY = 0.8
SLOT_ICERIKSIZ_SN = 2100      # içeriği okunamayan eski kilit için bayatlık (en uzun çağrı 1800 sn + pay)
YONTEMLER = ("tek", "kapali", "test", "kapsam", "acik", "ilk", "juri")
CIKTI_TAVAN = {"deepseek-v4.1-flash": 65536}       # diğerleri 16384
YEREL_HOST = ("127.0.0.1", "localhost", "[::1]")
SINIF_Q = {"mekanik": 16, "basit": 22, "arastirma": 38, "normal": 41, "kod": 45, "zor": 50, "kritik": 55}
KISA_BEKLE_SN = 60            # bu kadar kısa ipucu: aynı modelde bekle (soğumaya alma)
GENEL = "*"
TUR_AD = {"503": "sunucu dolu (503)", "fair_share": "model payı dolu", "concurrency": "eşzamanlılık sınırı",
          "token_rate": "5 dk token penceresi dolu", "daily": "günlük kota bitti", "ag": "ağ hatası", "diger": "sunucu hatası"}


def sure_sayi(x, ust=86400.0):
    """Sunucu süre ipucu (Retry-After vb.) -> saniye ya da None. inf, NaN, negatif ve 1 günden uzun değer bozuk sayılır."""
    try:
        v = float(x)
    except (TypeError, ValueError, OverflowError):
        return None
    return v if math.isfinite(v) and 0 <= v <= ust else None


GENEL_YASAK_BILESEN = {".ssh", ".aws", ".gnupg", ".codex", ".azure", ".kube"}
GENEL_YASAK_AD = re.compile(r"(?i)^(\.env(\..*)?|auth\.json|credentials(\..*)?|\.netrc|\.git-credentials|id_rsa.*|id_ed25519.*|.*\.pem|.*\.key|.*\.p12|.*\.pfx)$")


class Cikis(Exception):
    def __init__(self, kod, mesaj):
        super().__init__(mesaj)
        self.kod, self.mesaj = kod, mesaj


class AgHatasi(Exception):
    pass


def dizin():
    return os.environ.get("ORKESTRA_DIR") or os.path.join(os.path.expanduser("~"), ".orkestra")


def kota_modulu():
    spec = importlib.util.spec_from_file_location("kota_oku", KOTA_DOSYA)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# ---------------------------------------------------------------- anahtar ve maskeleme
def anahtar_al():
    v = os.environ.get("EVREN_API_KEY")
    if v:
        return v.strip()
    if os.name == "nt":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
                return str(winreg.QueryValueEx(k, "EVREN_API_KEY")[0]).strip() or None
        except OSError:
            return None
    return None


def maskele(s, anahtar=None):
    s = str(s)
    if anahtar and len(anahtar) >= 4:
        s = s.replace(anahtar, "***")
    s = re.sub(r"(?i)(bearer\s+)\S+", r"\1***", s)
    s = re.sub(r"(?i)(x-api-key[\"']?\s*[:=]\s*[\"']?)[^\s\"',}]+", r"\1***", s)
    return re.sub(r"\bevren_llm_[A-Za-z0-9_-]+", "evren_llm_***", s)


# ---------------------------------------------------------------- platform (izinli modeller, Z bandı, esz)
def platform_yolu(acik=None):
    return acik or os.environ.get("ORKESTRA_PLATFORMLAR") or os.path.join(dizin(), "platformlar.json")


def platform_yukle(yol=None):
    """İzinli modeller, Z bandı, esz ve yasak_yol platformlar.json'dan (seçicinin `--platformlar` dosyası
    `--platformlar` ya da ORKESTRA_PLATFORMLAR ile buraya da verilir). FAIL-CLOSED: dosya yok, okunamıyor, bozuk ya da
    EVREN havuzu/modeli yoksa `hata` dolu döner ve gönderen komutlar (calistir, toplu, ping, --kuru, tara) çıkış 2 verir;
    yasak_yol sessizce boşalmaz."""
    yol = platform_yolu(yol)
    p = {"esz": 24, "paralel_ajan": 8, "yasak_yol": [], "modeller": {}, "anahtar_ad": {}, "ad_api": {},
         "kaynak": yol, "havuz_ad": "evren", "hata": None}
    if not os.path.isfile(yol):
        p["hata"] = f"platform dosyası yok: {yol} (yasak_yol/izin listesi uygulanamaz; --platformlar ya da ORKESTRA_PLATFORMLAR)"
        return p
    try:
        with open(yol, encoding="utf-8-sig") as f:
            k = json.load(f)
        if not isinstance(k, dict):
            raise ValueError("nesne değil")
    except (OSError, ValueError) as e:
        p["hata"] = f"platform dosyası okunamadı/bozuk: {yol} ({type(e).__name__})"
        return p
    havuz = None
    for h, v in (k.get("havuz") or {}).items():
        if isinstance(v, dict) and (v.get("kota_okuyucu") == "evren" or h == "evren"):
            havuz = h
            try:
                p["esz"] = int(v.get("esz", p["esz"]))
                p["paralel_ajan"] = int(v.get("paralel_ajan", p["paralel_ajan"]))
            except (TypeError, ValueError):
                p["hata"] = f"platform dosyası: havuz.{h}.esz/paralel_ajan sayı değil"
                return p
            yy = v.get("yasak_yol", [])
            if not isinstance(yy, list):
                p["hata"] = f"platform dosyası: havuz.{h}.yasak_yol liste değil"
                return p
            p["yasak_yol"] = [str(x) for x in yy if str(x).strip()]
            break
    if not havuz:
        p["hata"] = f"platform dosyasında EVREN havuzu yok (kota_okuyucu \"evren\"): {yol}"
        return p
    p["havuz_ad"] = havuz
    for ad, d in (k.get("model") or {}).items():
        if not isinstance(d, dict) or d.get("h") != havuz or not d.get("api"):
            continue
        for e, z in (d.get("z") or {}).items():
            ef = "kapali" if d.get("dusunme") is False else e
            p["modeller"].setdefault(d["api"], {})[ef] = z
            p["anahtar_ad"][(d["api"], ef)] = (ad, e)
            p["ad_api"].setdefault(ad, (d["api"], "kapali" if d.get("dusunme") is False else None))
    for t, ad in (k.get("takma") or {}).items():          # seçicinin takma adları (glm, ds) da kabul
        if ad in p["ad_api"]:
            p["ad_api"].setdefault(t, p["ad_api"][ad])
    if not p["modeller"]:
        p["hata"] = f"platform dosyasında EVREN modeli yok: {yol}"
    return p


def platform_sart(plat):
    if plat.get("hata"):
        raise Cikis(2, plat["hata"])


def model_listesi(spec, efor, plat):
    """'glm-5.3:high,deepseek-v4.1-flash:high' -> [(api, efor)]; izin listesi ve Z bandı (fark ≤ 4) denetimi."""
    out = []
    for parca in [x.strip() for x in (spec or "").split(",") if x.strip()]:
        api, _, e = parca.partition(":")
        if api not in plat["modeller"] and api in plat.get("ad_api", {}):   # seçici adı (evren-glm-5.3) / takma (glm)
            api, sabit = plat["ad_api"][api]
            e = sabit or e
        e = e or efor
        izin = plat["modeller"].get(api)
        if izin is None:
            raise Cikis(2, f"izin listesinde olmayan model: {api} (izinli: {', '.join(plat['modeller'])})")
        if not e:
            e = next(iter(izin))
        if e not in izin:
            raise Cikis(2, f"{api} için geçersiz efor {e} (geçerli: {', '.join(izin)})")
        if (api, e) not in out:
            out.append((api, e))
    if not out:
        raise Cikis(2, "--model gerekli")
    return out


def kardes_bul(modeller, plat, sinif=None, en_cok=2, min_z=None):
    """Birincil model soğuma/503'teyse geçilecek AYNI Z BANDINDAKİ kardeş EVREN modelleri (yalnız sıralı yedek,
    sürü karışımına girmez). Eşik delinmez: kardeşin Z'si birincilin en çok 1 altı ve eşik (min_z = seçicinin etkin
    Q'su, seçicinin ÇAĞRI satırı --min-z ile verir; yoksa --sinif'in Q'su) varsa onun altına inmez (birincil zaten
    eşiğin altındaysa, ör. sürü, birincilin altına inilmez); Z farkı ≤ 4."""
    if not modeller:
        return []
    api0, e0 = modeller[0]
    z0 = plat["modeller"].get(api0, {}).get(e0)
    if z0 is None:
        return []
    q = min_z if min_z is not None else SINIF_Q.get(sinif or "")
    out = []
    for api, efs in plat["modeller"].items():
        if api == api0 or any(api == m for m, _ in modeller):
            continue
        for e, z in efs.items():
            if abs(z - z0) > 4 or z < z0 - 1:
                continue
            if q is not None and z < q and z < z0:
                continue
            out.append((abs(z - z0), -z, api, e))
    out.sort()
    tek, gor = [], set()
    for _, _, api, e in out:
        if api not in gor:
            gor.add(api)
            tek.append((api, e))
    return tek[:en_cok]


def bant_ayir(modeller, plat):
    """Birincil ve Z farkı ≤ 4 olanlar sürüde karışık kullanılabilir; bant dışı olanlar yalnız sıralı yedek."""
    z0 = plat["modeller"][modeller[0][0]][modeller[0][1]]
    return [m for m in modeller if abs(plat["modeller"][m[0]][m[1]] - z0) <= 4]


# ---------------------------------------------------------------- gizlilik
DESENLER = [
    ("api anahtarı (sk-)", re.compile(r"\bsk-(?:ant-|proj-)?[A-Za-z0-9_-]{16,}")),
    ("github belirteci", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}|\bgithub_pat_[A-Za-z0-9_]{20,}")),
    ("aws anahtarı", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("google anahtarı", re.compile(r"\bAIza[0-9A-Za-z_-]{30,}")),
    ("evren anahtarı", re.compile(r"\bevren_llm_[A-Za-z0-9_-]{8,}")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{4,}")),
    ("özel anahtar", re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY")),
    # SCREAMING_SNAKE (.env: SECRET_KEY=, DB_PASSWORD=, AWS_SECRET_ACCESS_KEY=), JSON ("api_key": "…"), YAML;
    # değer: rakam içeren ≥6 karakter ya da ≥16 karakter (get_token() gibi kod adları tutmasın)
    ("parola/anahtar ataması", re.compile(
        r"(?i)[A-Za-z0-9_.\-]*(?:api[_-]?key|secret|token|passw(?:or)?d|passphrase|pwd|parola|şifre|sifre|credential)"
        r"[A-Za-z0-9_.\-]*[\"']?\s*[:=]\s*[\"']?(?:(?=[^\s'\",;]*\d)[^\s'\",;]{6,}|[^\s'\",;()]{16,})")),
    ("yetki başlığı", re.compile(r"(?i)\bauthorization\s*[:=]\s*[\"']?(?:bearer|basic|token)\s+[A-Za-z0-9._~+/=-]{8,}"
                                 r"|\bbearer\s+[A-Za-z0-9._~+/=-]{20,}")),
    ("slack belirteci", re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,}")),
    ("bağlantı dizesi parolası", re.compile(r"(?i)\b[a-z][a-z0-9+.-]*://[^\s:/@]+:[^\s@/]{4,}@")),
    ("e-posta", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}\b")),
    ("telefon (+90)", re.compile(r"(?:\+90[\s-]?|(?<!\d)0)5\d{2}[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}(?!\d)")),
    ("gizli dosya yolu", re.compile(r"(?i)(?:^|[\s\"'=/\\(])(?:\.env(?:\.[a-z]+)?|id_rsa|id_ed25519|auth\.json|credentials\.json|\.git-credentials|\.netrc)(?=$|[\s\"')/\\,;])|[/\\]\.ssh[/\\]")),
    ("sağlık terimi", re.compile(r"(?i)\b(?:hasta(?:nın|ya|yı|lar\w*|nede\w*|ne\w*)?|epikriz\w*|anamnez\w*|tanısı|tanı|teşhis\w*|reçete\w*|tahlil\w*)\b")),
]


def tckn_gecerli(s):
    d = [int(c) for c in s]
    if len(d) != 11 or d[0] == 0:
        return False
    return (sum(d[0:9:2]) * 7 - sum(d[1:8:2])) % 10 == d[9] and sum(d[:10]) % 10 == d[10]


def iban_gecerli(s):
    s = re.sub(r"\s", "", s).upper()
    if not re.fullmatch(r"TR\d{24}", s):
        return False
    r = s[4:] + s[:4]
    return int("".join(str(int(c, 36)) for c in r)) % 97 == 1


def luhn_gecerli(s):
    d = [int(c) for c in re.sub(r"\D", "", s)]
    if not 13 <= len(d) <= 19:
        return False
    t = 0
    for i, x in enumerate(reversed(d)):
        if i % 2:
            x *= 2
            x = x - 9 if x > 9 else x
        t += x
    return t % 10 == 0


def tara_metin(metin, anahtar=None):
    """Eşleşen TÜRLERİN adları (içerik değil)."""
    bulunan = []
    if anahtar and len(anahtar) >= 8 and anahtar in metin:
        bulunan.append("anahtar değeri")
    for ad, rx in DESENLER:
        if rx.search(metin):
            bulunan.append(ad)
    # ayraçlı yazımlar da (100 000 001 46, 100.000.001-46, TR33 0006-1005 …): ayraç silinip sağlama denetlenir
    if any(tckn_gecerli(re.sub(r"\D", "", m.group())) for m in re.finditer(r"(?<![\d.\-])\d(?:[ .\-]?\d){10}(?![\d])", metin)):
        bulunan.append("TCKN")
    if any(iban_gecerli(re.sub(r"[\s.\-]", "", m.group())) for m in re.finditer(r"(?i)\bTR(?:[ .\-]?\d){24}(?!\d)", metin)):
        bulunan.append("IBAN")
    if any(luhn_gecerli(m.group()) for m in re.finditer(r"(?<!\d)(?:\d[ .\-]?){12,18}\d(?!\d)", metin)):
        bulunan.append("kart numarası")
    if yuksek_entropi(metin):
        bulunan.append("yüksek entropili dizgi (olası anahtar)")
    return sorted(set(bulunan))


def yuksek_entropi(metin):
    """≥32 karakterlik, büyük+küçük harf+rakam karışık, entropisi ≥ 4 bit/karakter dizgi (rastgele anahtar).
    Git SHA / hex özetler (yalnız küçük harf+rakam) ve düz kelimeler tutmaz."""
    for m in re.finditer(r"[A-Za-z0-9+/_\-]{32,}={0,2}", metin):
        s = m.group()
        if not (re.search(r"[a-z]", s) and re.search(r"[A-Z]", s) and re.search(r"\d", s)):
            continue
        say = {}
        for c in s:
            say[c] = say.get(c, 0) + 1
        h = -sum(n / len(s) * math.log2(n / len(s)) for n in say.values())
        if h >= 4.0:
            return True
    return False


def _yol_yasak_tek(p, plat):
    parcalar = re.split(r"[\\/]+", p)
    if any(x.lower() in GENEL_YASAK_BILESEN for x in parcalar) or GENEL_YASAK_AD.match(os.path.basename(p)):
        return "gizli dosya yolu"
    pl = p.replace("\\", "/").casefold()
    for y in plat.get("yasak_yol", []):
        if y and y.replace("\\", "/").casefold() in pl:
            return "yasak klasör (platformlar.json yasak_yol)"
    return None


def yol_yasak(yol, plat):
    """Ham (abspath) VE çözülmüş (realpath: 8.3 kısa ad, junction, symlink) yol denetlenir; biri yasaksa ret."""
    ham = os.path.abspath(yol)
    try:
        coz = os.path.realpath(yol)
    except (OSError, ValueError):
        coz = ham
    return _yol_yasak_tek(ham, plat) or (_yol_yasak_tek(coz, plat) if coz != ham else None)


IKILI_UZANTI = {".pdf", ".sqlite", ".sqlite3", ".db", ".doc", ".xls", ".ppt", ".exe", ".dll", ".bin", ".zip", ".7z",
                ".rar", ".gz", ".tar", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff", ".heic",
                ".mp3", ".mp4", ".mov", ".wav", ".m4a", ".pkl", ".npy", ".parquet"}
OFIS_ZIP = {".docx", ".xlsx", ".pptx", ".odt", ".ods", ".odp"}


def metin_coz(yol, en_cok=4_000_000):
    """Dosyanın taranabilir metni ya da None (taranamaz: ikili, büyük, çözülemeyen). utf-8(-sig), BOM'lu utf-16,
    cp1254 denenir; docx/xlsx/pptx/odt içindeki XML metni çıkarılır. Taranamayan dosya FAIL-CLOSED sayılır."""
    import zipfile
    try:
        if os.path.getsize(yol) > en_cok:
            return None
        uz = os.path.splitext(yol)[1].lower()
        if uz in OFIS_ZIP:
            parca = []
            with zipfile.ZipFile(yol) as z:
                for i in z.infolist():
                    if i.file_size > en_cok:
                        return None
                    if i.filename.lower().endswith((".xml", ".rels", ".txt")):
                        x = z.read(i).decode("utf-8", "replace")
                        parca += [re.sub(r"<[^>]+>", "", x), re.sub(r"<[^>]+>", " ", x)]
                    elif not i.filename.endswith("/"):
                        return None                         # gömülü görsel/ikili: taranamaz
            return "\n".join(parca)
        if uz in IKILI_UZANTI:
            return None
        with open(yol, "rb") as f:
            b = f.read()
    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile):
        return None
    if b.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            return b.decode("utf-16")
        except UnicodeDecodeError:
            return None
    if b"\x00" in b[:65536]:
        return None
    for kod in ("utf-8-sig", "cp1254"):
        try:
            return b.decode(kod)
        except UnicodeDecodeError:
            continue
    return None


def dosya_oku(yol, plat, en_cok=4_000_000):
    neden = yol_yasak(yol, plat)
    if neden:
        raise Cikis(3, f"gizlilik reddi: {neden}")
    if os.path.getsize(yol) > en_cok:
        raise Cikis(2, f"dosya çok büyük (>{en_cok // 1_000_000} MB): parçala")
    metin = metin_coz(yol, en_cok)
    if metin is None:
        raise Cikis(3, "gizlilik reddi: dosya taranamıyor (ikili/çözülemeyen kodlama)")
    return metin


def proje_engeli(yollar, plat):
    """Projenin `.orkestra.json` kuralı (seçiciyle aynı): cwd'den ve her dosyanın klasöründen yukarı en yakın
    dosya. gizli (bool dışı dolu değer de) ya da yasak_havuz EVREN havuzunu içeriyorsa ya da dosya okunamıyorsa
    neden döner (fail-closed); yoksa None."""
    baslar = {os.getcwd()} | {os.path.dirname(os.path.abspath(y)) for y in yollar if y and y != "-"}
    hv = {str(plat.get("havuz_ad") or "evren").lower(), "evren"}
    for d in baslar:
        while True:
            f = os.path.join(d, ".orkestra.json")
            if os.path.isfile(f):
                try:
                    with open(f, encoding="utf-8-sig") as fh:
                        k = json.load(fh)
                    if not isinstance(k, dict):
                        raise ValueError
                except (OSError, ValueError):
                    return f"proje kuralı okunamadı ({f}): güvenli tarafta gönderilmez"
                gz = k.get("gizli", False)
                if gz not in (False, None, 0, "", [], {}):
                    return f"proje gizli ({f})"
                yh = k.get("yasak_havuz", [])
                yh = [yh] if isinstance(yh, str) else yh if isinstance(yh, list) else []
                if hv & {str(x).strip().lower() for x in yh}:
                    return f"proje yasak_havuz EVREN'i dışlıyor ({f})"
                break
            ust = os.path.dirname(d)
            if ust == d:
                break
            d = ust
    return None


# ---------------------------------------------------------------- metin işleme ve birleştirme
def kacis(s):
    return s.replace("<think>", "&lt;think&gt;").replace("</think>", "&lt;/think&gt;")


def think_ayikla(s):
    s = re.sub(r"(?s)<think>.*?</think>", "", s or "")
    if "</think>" in s:
        s = s.rsplit("</think>", 1)[1]
    return s.strip()


def sade(s):
    s = unicodedata.normalize("NFKC", s).casefold()
    s = "".join(" " if unicodedata.category(c).startswith(("P", "S")) else c for c in s)
    return " ".join(s.split())


def json_ayikla(s):
    s = s.strip()
    m = re.search(r"(?s)```(?:json)?\s*(.*?)```", s)
    if m:
        s = m.group(1).strip()
    return json.loads(s)


def sema_uygun(x, sema):
    """Küçük JSON şema doğrulayıcı: type, required, properties, items, enum, additionalProperties:false."""
    if not isinstance(sema, dict):
        return True
    if "enum" in sema and x not in sema["enum"]:
        return False
    t = sema.get("type")
    tipler = {"object": dict, "array": list, "string": str, "boolean": bool, "null": type(None)}
    if t == "integer":
        if isinstance(x, bool) or not isinstance(x, int):
            return False
    elif t == "number":
        if isinstance(x, bool) or not isinstance(x, (int, float)):
            return False
    elif t in tipler and not isinstance(x, tipler[t]):
        return False
    if isinstance(x, dict):
        if any(k not in x for k in sema.get("required", [])):
            return False
        props = sema.get("properties", {})
        if sema.get("additionalProperties") is False and any(k not in props for k in x):
            return False
        if not all(sema_uygun(x[k], props[k]) for k in x if k in props):
            return False
    if isinstance(x, list) and "items" in sema:
        if not all(sema_uygun(i, sema["items"]) for i in x):
            return False
    return True


def oy_anahtari(metin, sema):
    """Kapalı cevabın kanonik biçimi; şemayı geçmeyen ya da boş yanıt None (geçersiz oy)."""
    if sema is not None:
        try:
            x = json_ayikla(metin)
        except ValueError:
            return None
        if not sema_uygun(x, sema):
            return None
        return json.dumps(x, sort_keys=True, ensure_ascii=False)
    k = sade(metin)
    return k or None


def oy_karar(oylar, toplam):
    """Oybirliği ya da (toplam ≥ 5 iken) ≥ %75 aynı → karar. (karar|None, uzlaşı oranı)."""
    gecerli = [o for o in oylar if o is not None]
    if len(gecerli) < 2:
        return None, 0.0
    say = {}
    for o in gecerli:
        say[o] = say.get(o, 0) + 1
    en, n = max(say.items(), key=lambda x: x[1])
    gerek = toplam if toplam < 5 else max(2, math.ceil(0.75 * toplam))
    return (en if n >= gerek else None), round(n / toplam, 3)


def alinti_dogrula(iddialar, kaynak):
    """Kaynakta birebir (boşluk sadeleştirilmiş) bulunmayan alıntılı iddia atılır."""
    ks = " ".join(kaynak.split())
    out = []
    for i in iddialar if isinstance(iddialar, list) else []:
        if not isinstance(i, dict):
            continue
        a = " ".join(str(i.get("birebir_alinti", "")).split())
        if a and a in ks and str(i.get("iddia", "")).strip():
            out.append(i)
    return out


KAPSAM_SEMA = {"type": "object", "required": ["iddialar"], "properties": {"iddialar": {"type": "array", "items": {
    "type": "object", "required": ["iddia", "birebir_alinti"],
    "properties": {"iddia": {"type": "string"}, "birebir_alinti": {"type": "string"}, "satir": {"type": "integer"}}}}}}
KAPSAM_SISTEM = ("Yalnız verilen KAYNAK metnine dayan. Soruyla ilgili her iddia için kaynaktan BİREBİR alıntı ver. "
                 "Kaynakta yoksa iddia yazma. Yalnız şu JSON'u döndür: {\"iddialar\": [{\"iddia\": str, "
                 "\"birebir_alinti\": str, \"satir\": int}]}")
JURI_SISTEM = "Verilen ölçüte göre 0-10 arası tek bir puan ver. Yalnız sayıyı yaz."


def kod_ayikla(metin):
    m = re.search(r"(?s)```[\w+-]*\n(.*?)```", metin)
    return m.group(1) if m else metin


# ---------------------------------------------------------------- aktarım
def taban_dogrula(taban):
    """Anahtar yalnız https'e (ya da sınama için yerel adrese) gider; aksi halde Cikis(2)."""
    from urllib.parse import urlsplit
    u = urlsplit(taban or "")
    if u.scheme == "https" and u.hostname:
        return taban
    if u.scheme == "http" and (u.hostname or "") in ("127.0.0.1", "localhost", "::1"):
        return taban
    raise Cikis(2, "EVREN_BASE_URL https olmalı (anahtar düz http'ye gönderilmez)")


def http_aktarim(taban, anahtar, okuma_sn=120):
    """Gerçek aktarım: POST {taban}/chat/completions, SSE akışı. Dönüş (kod, başlıklar, yük). Yük 200'de
    {"content", "finish_reason", "usage"}, aksi halde hata gövdesi. Ağ hatası: AgHatasi (anahtar içermez).
    Yönlendirme İZLENMEZ (3xx = hata): urllib X-API-Key'i başka origin'e taşırdı. [DONE] ya da finish_reason
    gelmeden biten akış yarım sayılır (AgHatasi), başarı değil."""
    import http.client
    taban_dogrula(taban)
    acici = yonlendirmesiz_acici()

    def gonder(govde, toplam_sn):
        req = urllib.request.Request(taban.rstrip("/") + "/chat/completions", data=json.dumps(govde).encode("utf-8"),
                                     method="POST", headers={"X-API-Key": anahtar, "Content-Type": "application/json",
                                                             "Accept": "text/event-stream", "User-Agent": "orkestra-evren/1"})
        bas_t = time.monotonic()
        try:
            r = acici.open(req, timeout=okuma_sn)
        except urllib.error.HTTPError as e:
            bas = {k.lower(): v for k, v in (e.headers or {}).items()}
            try:
                g = json.loads(e.read().decode("utf-8") or "{}")
            except (ValueError, OSError, http.client.HTTPException):
                g = {}
            if 300 <= e.code < 400:
                g = {"error": {"code": "redirect_refused"}}      # anahtar yönlendirme hedefine gitmedi
            return e.code, bas, g
        except (urllib.error.URLError, OSError, TimeoutError, http.client.HTTPException) as e:
            raise AgHatasi(type(e).__name__)
        try:
            with r:
                bas = {k.lower(): v for k, v in r.headers.items()}
                if "text/event-stream" not in bas.get("content-type", ""):
                    j = json.loads(r.read().decode("utf-8"))
                    c = (j.get("choices") or [{}])[0]
                    return r.status, bas, {"content": (c.get("message") or {}).get("content") or "",
                                           "finish_reason": c.get("finish_reason"), "usage": j.get("usage")}
                parcalar, bitis, kullanim, tamam = [], None, None, False
                for satir in r:
                    if time.monotonic() - bas_t > toplam_sn:
                        raise AgHatasi("toplam süre aşıldı")
                    s = satir.decode("utf-8", "replace").strip()
                    if not s.startswith("data:"):
                        continue
                    d = s[5:].strip()
                    if d == "[DONE]":
                        tamam = True
                        break
                    try:
                        ch = json.loads(d)
                    except ValueError:
                        continue
                    if ch.get("error"):
                        return 500, bas, ch
                    for c in ch.get("choices") or []:
                        delta = c.get("delta") or {}
                        if delta.get("content"):
                            parcalar.append(delta["content"])
                        if c.get("finish_reason"):
                            bitis = c["finish_reason"]
                    if ch.get("usage"):
                        kullanim = ch["usage"]
                if not tamam and bitis is None:
                    raise AgHatasi("akış yarım (DONE/finish_reason yok)")
                return r.status, bas, {"content": "".join(parcalar), "finish_reason": bitis, "usage": kullanim}
        except (OSError, TimeoutError, ValueError, http.client.HTTPException) as e:
            raise AgHatasi(type(e).__name__)
    return gonder


class _Yonlendirmesiz(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None                                     # 3xx izlenmez → HTTPError (anahtar yeni hedefe gitmez)


def yonlendirmesiz_acici():
    return urllib.request.build_opener(_Yonlendirmesiz)


# ---------------------------------------------------------------- motor: slot, AIMD, kova, hata politikası
class Motor:
    def __init__(self, aktarim, plat, saat=time.monotonic, uyku=time.sleep, kota=None, sure_sn=1800):
        self.aktarim, self.plat, self.saat, self.uyku = aktarim, plat, saat, uyku
        self.kota = kota
        self.sure_sn = sure_sn
        self.kilit = threading.Condition()
        durum = self._durum()
        # kayıtlı model payı 1 saat geçerli (düşen model kalıcı kısılmasın); sonra varsayılana döner
        taze = time.time() - float(durum.get("model_pay_zaman") or 0) < 3600
        self.pay = {m: int(v) for m, v in (durum.get("model_pay") or {}).items()
                    if taze and isinstance(v, (int, float)) and v >= 1}
        self.aktif, self.ardisik = {}, {}
        self.kova = []
        self.kova_tavan = KOVA_PAY * float(durum.get("pencere_tavan") or PENCERE_TAVAN)
        self.harcama = {"ham_girdi": 0, "onbellekli": 0, "cikti": 0, "kota_agirlikli": 0.0}
        self.hatalar, self.istek_sayisi, self.bekleme_sn = [], 0, 0.0
        self.tps = dict(durum.get("tps") or {})
        self.slot_dizin = os.path.join(dizin(), "evren_slot")
        self.esz = max(1, int(plat.get("esz", 24)) - 2)
        self.notlar, self.sog_yazildi, self.sog_kalici = [], set(), set()
        self.sog_bilinen = set(self.soguma_oku())
        self.yoklama, self.yoklama_olay = {}, {}
        self.rastgele = random.random                   # jitter (sınamada sabitlenir)

    # -- stratejik soğuma (kayıt kota_oku'da: durum dosyası "soguma", kilitli ve atomik)
    def soguma_oku(self):
        try:
            return self.kota.soguma_oku() if self.kota and hasattr(self.kota, "soguma_oku") else {}
        except Exception:
            return {}

    def not_ekle(self, metin):
        with self.kilit:
            if metin not in self.notlar:
                self.notlar.append(metin)

    @staticmethod
    def kalan_metni(sn):
        dk = sn / 60
        return f"{dk / 60:.1f} sa" if dk >= 90 else f"{max(dk, 1):.0f} dk"

    def soguma_isle(self, ad, tur, bitis=None):
        """(ad, tur) bu çalıştırmada en çok bir kez kaydedilir: sürüde 20 paralel 503 ardışığı 20 artırmasın."""
        with self.kilit:
            if (ad, tur) in self.sog_yazildi:
                return None
            self.sog_yazildi.add((ad, tur))
            self.sog_bilinen.add(ad)
        if not (self.kota and hasattr(self.kota, "soguma_kaydet")):
            return None
        try:
            k = self.kota.soguma_kaydet(ad, tur, bitis)
            b = datetime.fromisoformat(k["busy_until"])
            kalan = (b - datetime.now(timezone.utc)).total_seconds()
        except Exception:
            return None
        dn = getattr(self.kota, "DURUM_NOTLARI", None)
        while isinstance(dn, list) and dn:                # bozuk durum dosyası .bozuk adıyla kenara alındıysa söyle
            self.not_ekle(dn.pop(0))
        ad_ = "EVREN (tümü)" if ad == GENEL else ad
        if k.get("yazilamadi"):                       # durum dosyası yazılamadı: soğuma kalıcı değil, yanlış bilgi verme
            self.not_ekle(f"{ad_}: {TUR_AD.get(tur, tur)}; soğuma KAYDEDİLEMEDİ (durum dosyası yazılamadı/kilitli),"
                          " sonraki çağrılar bunu bilmez")
            return k
        with self.kilit:
            self.sog_kalici.add(ad)
        self.not_ekle(f"{ad_} soğumaya alındı: {TUR_AD.get(k.get('tur') or tur, k.get('tur') or tur)}"
                      + (f" ×{k.get('ardisik')}" if (k.get("ardisik") or 1) > 1 else "") + f", {self.kalan_metni(kalan)}")
        return k

    def soguma_bitir(self, api):
        with self.kilit:
            if api not in self.sog_bilinen and GENEL not in self.sog_bilinen:
                return
            self.sog_bilinen.discard(api)
            self.sog_bilinen.discard(GENEL)
            self.sog_yazildi = {x for x in self.sog_yazildi if x[0] not in (api, GENEL)}
        try:
            self.kota.soguma_temizle(api)
        except Exception:
            pass

    def soguma_eki(self):
        sg = self.soguma_oku()
        if not sg:
            return ""
        try:
            m = self.kota.soguma_metni(sg)
        except Exception:
            return ""
        return f" (soğuma: {m}; seçiciyi yeniden çalıştır: EVREN'siz sıralar, ya da bekle)"

    @staticmethod
    def hata_turu(kod, k):
        if kod == 503:
            return "503"
        return {"fair_share_limit_exceeded": "fair_share", "concurrency_limit_exceeded": "concurrency",
                "token_rate_limit_exceeded": "token_rate", "daily_token_limit_exceeded": "daily"}.get(k, "diger")

    @staticmethod
    def ipucu(bas, govde, gunluk=False):
        """Sunucunun bekleme ipucu: (saniye | None, bitiş datetime | None). Retry-After, sonra error.evren.resets_at
        / daily_reset_at. gunluk=True (daily_token_limit_exceeded): önce daily_reset_at, sonra resets_at, en son
        Retry-After (kısa pencere ipucu günlük soğumayı kısaltmasın). Bozuk değer (inf, NaN, negatif, >1 gün) yok sayılır."""
        simdi = datetime.now(timezone.utc)

        def baslik():
            sn = sure_sayi((bas or {}).get("retry-after"))
            return (sn, simdi + timedelta(seconds=sn)) if sn is not None else None

        if not gunluk:
            r = baslik()
            if r:
                return r
        ev = (((govde or {}).get("error") or {}).get("evren") or {}) if isinstance(govde, dict) else {}
        for alan in (("daily_reset_at", "resets_at") if gunluk else ("resets_at", "daily_reset_at")):
            ra = ev.get(alan) if isinstance(ev, dict) else None
            if ra:
                try:
                    d = datetime.fromisoformat(str(ra).replace("Z", "+00:00"))
                    d = d if d.tzinfo else d.replace(tzinfo=timezone.utc)
                    return max((d - simdi).total_seconds(), 0.0), d
                except (ValueError, OverflowError):
                    pass
        return (baslik() or (None, None)) if gunluk else (None, None)

    def yokla(self, api, efor):
        """Süresi dolan soğuma: 16 token'lık ping (sabit, kamuya açık içerik). Motor başına model başına bir kez;
        aynı anda gelen diğer iş parçacıkları sonucu bekler. Başarı → kayıt silinir; hata → ardışık+1, soğuma uzar."""
        with self.kilit:
            if api in self.yoklama:
                return self.yoklama[api]
            olay = self.yoklama_olay.get(api)
            sahip = olay is None
            if sahip:
                olay = self.yoklama_olay[api] = threading.Event()
        if not sahip:
            olay.wait(90)
            return self.yoklama.get(api, False)
        ok = False
        try:
            g = self.govde(api, efor, "Yalnız 'tamam' yaz.", None, 16, None, 0.0, set())
            slot = self.slot_al()
            try:
                self.istek_sayisi += 1
                kod, bas, yuk = self.aktarim(g, 60)
            finally:
                self.slot_birak(slot)
            self.basliklar(bas or {})
            ok = kod == 200
            if ok:
                self.soguma_bitir(api)
                self.not_ekle(f"{api} soğuma bitti, ping yanıt verdi: yeniden aday")
            else:
                hata = (yuk or {}).get("error") if isinstance(yuk, dict) else None
                k = (hata or {}).get("code") or "" if isinstance(hata, dict) else ""
                self.soguma_isle(api, self.hata_turu(kod, k), self.ipucu(bas, yuk)[1])
                self.not_ekle(f"{api} yoklama başarısız (HTTP {kod}): soğuma uzadı")
        except AgHatasi:
            self.soguma_isle(api, "ag")
        finally:
            with self.kilit:
                self.yoklama[api] = ok
            olay.set()
        return ok

    def soguma_suz(self, modeller):
        """Soğumadaki modeli sıfır istekle atlar; süresi dolanı ping ile yoklar. '*' (tüm EVREN) etkinse kısa ise
        (≤60 sn) bekler, uzunsa Cikis(4). Hepsi soğumadaysa Cikis(4) ve en erken süre."""
        sg = self.soguma_oku()
        if not sg:
            return modeller
        g = sg.get(GENEL)
        if g and g["durum"] == "aktif":
            if g["kalan_sn"] <= KISA_BEKLE_SN and g["tur"] != "daily":
                self._bekle(g["kalan_sn"] + 0.5)
            else:
                raise Cikis(4, f"EVREN soğumada: {TUR_AD.get(g['tur'], g['tur'])}, {self.kalan_metni(g['kalan_sn'])} kaldı"
                               " → seçici EVREN'siz sıralar (iş acil değilse bekle)")
        elif g and g["durum"] == "yoklama" and modeller:
            # ping hedefi: kendi aktif soğuması OLMAYAN ilk model (aktif model kaydını erken bitirmesin)
            hedef = next((m for m in modeller if not ((sg.get(m[0]) or {}).get("durum") == "aktif")), None)
            if hedef is None:
                en = min(sg[m[0]]["kalan_sn"] for m in modeller)
                raise Cikis(4, f"tüm EVREN modelleri soğumada (en erken {self.kalan_metni(en)})" + self.soguma_eki())
            if not self.yokla(*hedef):
                raise Cikis(4, "EVREN yoklaması başarısız: soğuma uzadı" + self.soguma_eki())
        out, atlanan = [], []
        for api, e in modeller:
            k = sg.get(api)
            if k and k["durum"] == "aktif":
                atlanan.append((api, k["kalan_sn"]))
                continue
            if k and k["durum"] == "yoklama" and not self.yokla(api, e):
                atlanan.append((api, (self.soguma_oku().get(api) or k)["kalan_sn"]))
                continue
            out.append((api, e))
        if not out:
            en = min(x[1] for x in atlanan) if atlanan else 0
            raise Cikis(4, f"tüm EVREN modelleri soğumada (en erken {self.kalan_metni(en)})" + self.soguma_eki())
        if atlanan:
            self.not_ekle(", ".join(f"{a} soğumada ({self.kalan_metni(sn)})" for a, sn in atlanan)
                          + f"; yerine {out[0][0]}:{out[0][1]}")
        return out

    def _durum(self):
        try:
            return self.kota.durum_oku() if self.kota else {}
        except Exception:
            return {}

    def _durum_yaz(self, ek):
        if self.kota:
            try:
                self.kota.durum_yaz(ek)
            except OSError:
                pass

    # -- dosya kilitli slot (süreçler arası toplam eşzamanlılık)
    # Kilit içeriği: "<pid> <belirteç> <son_geçerlilik_epoch>". Bayatlık sahibinin kendi bildirdiği süreye göre
    # (sure_sn + 300); başkasının uzun çağrısının kilidi çalınmaz. Bırakma yalnız kendi belirteciyle.
    @staticmethod
    def _kilit_oku(yol):
        try:
            with open(yol, encoding="utf-8") as f:
                p = f.read().split()
            return p[1], float(p[2])
        except (OSError, ValueError, IndexError):
            return None, None

    def _bayat_mi(self, yol):
        _, son = self._kilit_oku(yol)
        if son is not None:
            return time.time() > son
        try:
            return time.time() - os.path.getmtime(yol) > SLOT_ICERIKSIZ_SN
        except OSError:
            return False

    def slot_al(self):
        os.makedirs(self.slot_dizin, exist_ok=True)
        bas = self.saat()
        while True:
            for i in range(self.esz):
                yol = os.path.join(self.slot_dizin, f"{i:02d}.lock")
                belirtec = secrets.token_hex(8)
                try:
                    fd = os.open(yol, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                    os.write(fd, f"{os.getpid()} {belirtec} {time.time() + self.sure_sn + 300:.0f}".encode())
                    os.close(fd)
                    return yol, belirtec
                except PermissionError:                     # Windows: başka iş parçacığı silerken (silme beklemede)
                    continue
                except FileExistsError:
                    if self._bayat_mi(yol):
                        # yeniden adlandırma atomik: yalnız bir süreç kazanır; sonra gerçekten bayat mı diye bakılır
                        gecici = f"{yol}.bayat.{belirtec}"
                        try:
                            os.replace(yol, gecici)
                        except OSError:
                            continue
                        if self._bayat_mi(gecici):
                            try:
                                os.unlink(gecici)
                            except OSError:
                                pass
                        else:                                   # arada taze kilit gelmiş: sahibine geri ver
                            try:
                                os.rename(gecici, yol)
                            except OSError:
                                pass
            if self.saat() - bas > self.sure_sn:
                raise Cikis(4, "eşzamanlılık slotu bulunamadı")
            self.uyku(1.0)

    @classmethod
    def slot_birak(cls, slot):
        yol, belirtec = slot if isinstance(slot, tuple) else (slot, None)
        # Windows: başka iş parçacığı/süreç kilidi o an okuyorsa (bayatlık denetimi) açma ve silme kısa süre
        # PermissionError verir; yeniden dene (sızan kilit slotu kalıcı kapatırdı).
        for i in range(50):
            if not os.path.exists(yol):
                return
            b, _ = cls._kilit_oku(yol)
            if b is None and os.path.exists(yol):
                time.sleep(0.002 * (i + 1))
                continue
            if belirtec is not None and b != belirtec:
                return                                          # kilit artık başkasının: dokunma
            try:
                os.unlink(yol)
                return
            except FileNotFoundError:
                return
            except OSError:
                time.sleep(0.002 * (i + 1))

    # -- model payı (AIMD)
    def _pay(self, api):
        return self.pay.get(api, 6)

    def model_gir(self, api):
        with self.kilit:
            while self.aktif.get(api, 0) >= self._pay(api):
                self.kilit.wait(0.5)
            self.aktif[api] = self.aktif.get(api, 0) + 1

    def model_cik(self, api, basari):
        with self.kilit:
            self.aktif[api] = max(0, self.aktif.get(api, 1) - 1)
            if basari:
                self.ardisik[api] = self.ardisik.get(api, 0) + 1
                if self.ardisik[api] >= 10:
                    self.pay[api] = min(self._pay(api) + 1, self.esz)
                    self.ardisik[api] = 0
            self.kilit.notify_all()

    def pay_dusur(self, api, yeni=None):
        """Yalnız AŞAĞI: yarıya ya da sunucunun bildirdiği (küçükse) değere; hesap tavanı (32) payı yükseltmez."""
        with self.kilit:
            yari = self._pay(api) // 2
            try:
                y = int(yeni) if yeni else None
            except (TypeError, ValueError):
                y = None
            self.pay[api] = max(1, min(yari, y) if y else yari)
            self.ardisik[api] = 0
        self.pay_kaydet()

    def pay_kaydet(self):
        self._durum_yaz({"model_pay": dict(self.pay), "model_pay_zaman": time.time()})

    # -- 5 dk token kovası
    def kova_bekle(self, tahmin):
        while True:
            with self.kilit:
                t = self.saat()
                self.kova = [(a, b) for a, b in self.kova if t - a < PENCERE_SN]
                dolu = sum(b for _, b in self.kova)
                if not self.kova or dolu + tahmin <= self.kova_tavan:
                    self.kova.append((t, tahmin))
                    return
                bekle = PENCERE_SN - (t - self.kova[0][0]) + 0.1
            self.bekleme_sn += bekle
            self.uyku(min(bekle, 60))

    def _bekle(self, sn):
        try:
            sn = float(sn)
        except (TypeError, ValueError):
            sn = 5.0
        sn = min(max(sn if math.isfinite(sn) else 5.0, 0.5), 60.0)
        self.bekleme_sn += sn
        self.uyku(sn)

    @staticmethod
    def retry_after(bas, govde, varsayilan=5.0):
        sn = sure_sayi((bas or {}).get("retry-after"))
        if sn is not None:
            return min(sn, 60.0)
        ra = ((govde or {}).get("error") or {}).get("evren", {}).get("resets_at") if isinstance(govde, dict) else None
        if ra:
            try:
                d = datetime.fromisoformat(str(ra).replace("Z", "+00:00"))
                d = d if d.tzinfo else d.replace(tzinfo=timezone.utc)
                return min(max((d - datetime.now(timezone.utc)).total_seconds(), 0.5), 60.0)
            except (ValueError, OverflowError, TypeError):
                pass
        return varsayilan

    def basliklar(self, bas):
        k = bas.get("x-evren-daily-remaining-tokens")
        if k is not None:
            try:
                self._durum_yaz({"kalan": float(k), "tavan": self._durum().get("tavan") or GUNLUK_TAVAN,
                                 "zaman": time.time()})
            except ValueError:
                pass

    def govde(self, api, efor, istem, sistem, mt, sema, sicaklik, cikar):
        msj = ([{"role": "system", "content": kacis(sistem)}] if sistem else []) + [{"role": "user", "content": kacis(istem)}]
        g = {"model": api, "messages": msj, "stream": True, "stream_options": {"include_usage": True},
             "max_tokens": mt, "temperature": sicaklik}
        if efor == "kapali":
            g["thinking"] = False
        elif efor:
            g["reasoning_effort"] = efor
        if sema is not None:
            g["response_format"] = {"type": "json_schema", "json_schema": {"name": "cikti", "schema": sema}}
        for p in cikar:
            g.pop(p, None)
        return g

    def cagri(self, modeller, istem, sistem=None, mt=4096, sema=None, sicaklik=0.0, uzat_izin=True, soguma_atla=False):
        """Tek mantıksal çağrı; hata politikasına göre bekler/sonraki modele geçer. Başarıda
        {"metin", "model", "efor", "usage", "sure"}; kullanılamazsa Cikis(4); yanıt yoksa Cikis(5).
        Önce soğuma süzgeci (soguma_atla: ping/yoklama komutu için kapalı)."""
        if not soguma_atla:
            modeller = self.soguma_suz(modeller)
        i, cikar, sayac, uzat, ag, tur503 = 0, set(), {}, not uzat_izin, 0, 0
        dolu, kisa = set(), {}
        bas_t = self.saat()
        while True:
            if self.saat() - bas_t > self.sure_sn:
                raise Cikis(4, "süre aşıldı")
            if i >= len(modeller):
                # hepsi 503: soğuması KALICI yazılan model yeniden denenmez (dolu sunucuya vurma; seçici EVREN'siz
                # sıralar). 5/15/45 geri çekilme yalnız soğuması yazılamayanlar için (kota modülü yok/dosya kilitli).
                tekrar = [modeller[j] for j in sorted(dolu) if modeller[j][0] not in self.sog_kalici]
                if dolu and len(dolu) == len(modeller) and tekrar and tur503 < 3:
                    self._bekle((5, 15, 45)[tur503])
                    tur503 += 1
                    modeller, i, dolu = tekrar, 0, set()
                    continue
                raise Cikis(4, "tüm EVREN modelleri dolu/hatalı" + self.soguma_eki())
            api, efor = modeller[i]
            tavan = CIKTI_TAVAN.get(api, 16384)
            mt_ = min(mt if efor == "kapali" else max(mt, 2048), tavan)
            g = self.govde(api, efor, istem, sistem, mt_, sema, sicaklik, cikar)
            self.kova_bekle(len(json.dumps(g["messages"], ensure_ascii=False)) / 3.0 + mt_)
            slot = self.slot_al()
            self.model_gir(api)
            t0 = self.saat()
            basari = False
            try:
                self.istek_sayisi += 1
                kod, bas, yuk = self.aktarim(g, max(self.sure_sn - (t0 - bas_t), 30))
                basari = kod == 200
            except AgHatasi as e:
                self.hatalar.append(f"{api}: ağ {e}")
                ag += 1
                if ag > 1:
                    i, ag = i + 1, 0
                self._bekle(2.0)                              # kopma/yarım akış: kısa geri çekilme
                continue
            finally:
                self.model_cik(api, basari)
                self.slot_birak(slot)
            bas = bas or {}
            self.basliklar(bas)
            if kod == 200:
                metin = think_ayikla((yuk or {}).get("content") or "")
                if ((yuk or {}).get("finish_reason") == "length" or not metin) and not uzat:
                    uzat, mt = True, min(mt_ * 2, tavan)
                    continue
                if not metin:
                    raise Cikis(5, f"{api}: boş yanıt")
                u = (yuk or {}).get("usage") or {}
                gi, ci = int(u.get("prompt_tokens") or 0), int(u.get("completion_tokens") or 0)
                ob = int(((u.get("prompt_tokens_details") or {}).get("cached_tokens")) or 0)
                sure = max(self.saat() - t0, 1e-3)
                with self.kilit:
                    self.harcama["ham_girdi"] += gi
                    self.harcama["onbellekli"] += ob
                    self.harcama["cikti"] += ci
                    self.harcama["kota_agirlikli"] += (gi - ob) + 0.03 * ob + ci
                    if ci:
                        self.tps[api] = round(0.7 * self.tps.get(api, ci / sure) + 0.3 * ci / sure, 2)
                self.soguma_bitir(api)
                return {"metin": metin, "model": api, "efor": efor, "usage": u, "sure": round(sure, 2)}
            hata = (yuk or {}).get("error") if isinstance(yuk, dict) else None
            hata = hata if isinstance(hata, dict) else {}
            k = hata.get("code") or ""
            sayac[k] = sayac.get(k, 0) + 1
            self.hatalar.append(f"{api}: HTTP {kod} {k}".strip())
            if kod == 429:
                if k == "daily_token_limit_exceeded":
                    _, yarin = self.ipucu(bas, yuk, gunluk=True)
                    simdi_ = datetime.now(timezone.utc)
                    if not yarin or yarin <= simdi_:
                        yarin = (simdi_ + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                    yarin = min(yarin, simdi_ + timedelta(hours=36))   # bozuk/uç sunucu değeri EVREN'i kilitlemesin
                    self._durum_yaz({"kalan": 0.0, "tukendi_until": yarin.isoformat(), "zaman": time.time()})
                    self.soguma_isle(GENEL, "daily", yarin)
                    raise Cikis(4, f"günlük EVREN kotası bitti ({yarin:%Y-%m-%d %H:%M}Z'de yenilenir; 00:00Z = 03:00 TSİ):"
                                   " seçici o zamana dek EVREN'siz sıralar")
                if k == "fair_share_limit_exceeded":
                    self.pay_dusur(api, (hata.get("evren") or {}).get("concurrency_limit"))
                    self.soguma_isle(api, "fair_share", self.ipucu(bas, yuk)[1])
                    if i + 1 < len(modeller):
                        i += 1
                        continue
                    if sayac[k] > 2:
                        raise Cikis(4, "fair share: model payı dolu")
                    self._bekle(self.retry_after(bas, yuk))
                    continue
                if k == "token_rate_limit_exceeded":
                    sn, bitis = self.ipucu(bas, yuk)
                    if sn is None or sn > KISA_BEKLE_SN:
                        self.soguma_isle(GENEL, "token_rate", bitis)
                        raise Cikis(4, "EVREN 5 dk token penceresi dolu" + self.soguma_eki())
                if k == "concurrency_limit_exceeded":
                    with self.kilit:
                        self.esz = max(1, int(self.esz * 0.75))
                if sayac[k] > 3:
                    if k == "concurrency_limit_exceeded":
                        self.soguma_isle(GENEL, "concurrency", self.ipucu(bas, yuk)[1])
                    i += 1
                    continue
                self._bekle(self.retry_after(bas, yuk))
                continue
            if kod == 503:
                sn, bitis = self.ipucu(bas, yuk)
                n = kisa.get(api, 0)
                if sn is not None and sn <= KISA_BEKLE_SN and n < 2:
                    kisa[api] = n + 1                     # (a) kısa dolu: aynı modelde üstel bekleme + jitter
                    self._bekle(max(sn, 1.0) * (2 ** n) * (1 + 0.25 * self.rastgele()))
                    continue
                self.soguma_isle(api, "503", bitis)       # (b) uzun/ipucusuz: model soğumaya, kardeşe geç
                dolu.add(i)
                i += 1
                continue
            if kod == 400 and k == "unsupported_parameter":
                p = hata.get("param")
                if p and p not in cikar and p not in ("model", "messages"):
                    cikar.add(p)
                    continue
                raise Cikis(5, f"{api}: desteklenmeyen parametre")
            if kod in (401,):
                raise Cikis(4, "anahtar geçersiz (401)")
            if kod == 403:
                raise Cikis(4, "şart kabulü gerekli (403): kullanıcı portalda kendisi kabul eder" if "terms" in k
                            else f"erişim reddi (403 {k})")
            if kod == 404:
                oner = [m for m in (hata.get("evren") or {}).get("suggested_models", []) if m in self.plat["modeller"]]
                self.hatalar.append(f"{api}: model bulunamadı" + (f" (öneri: {', '.join(oner)})" if oner else " → YENİ MODEL (evren) bildir"))
                i += 1
                continue
            if kod in (502, 504):                             # ağ geçidi: kısa soğuma (1-10 dk), kalıcı 502'de her
                self.soguma_isle(api, "diger", self.ipucu(bas, yuk)[1])   # yeni çağrı aynı modele vurmasın
            i += 1                                            # 500, diğer 5xx, bilinmeyen: sıradaki model (soğuma yok)


# ---------------------------------------------------------------- yöntemler
def paralel(motor, n, fn):
    """n işi aynı anda en çok (slot) kadar koşturur; sonuç ya da Cikis listesi (sırayla)."""
    out = [None] * n
    with cf.ThreadPoolExecutor(max_workers=max(1, min(n, motor.esz))) as ex:
        fs = {ex.submit(fn, i): i for i in range(n)}
        for f in cf.as_completed(fs):
            try:
                out[fs[f]] = f.result()
            except Cikis as e:
                out[fs[f]] = e
            except Exception as e:                          # tek adayın beklenmeyen hatası sürüyü düşürmesin
                out[fs[f]] = Cikis(4, f"beklenmeyen {type(e).__name__}")
    return out


def yaz(cikti, ad, metin):
    os.makedirs(cikti, exist_ok=True)
    yol = os.path.join(cikti, ad)
    with open(yol, "w", encoding="utf-8") as f:
        f.write(metin)
    return yol


def calistir_yontem(a, motor, plat, istem, sistem, sema, cikti):
    """Dönüş: (çıkış kodu, özet sözlüğü)."""
    modeller = model_listesi(a.model, a.efor, plat)
    bant = bant_ayir(modeller, plat)
    kardes = [] if getattr(a, "kardessiz", False) else kardes_bul(modeller, plat, getattr(a, "sinif", None),
                                                                  min_z=getattr(a, "min_z", None))
    yontem = a.yontem
    oz = {"yontem": yontem, "modeller": [f"{m}:{e}" for m, e in modeller], "hatalar": []}
    if kardes:
        oz["kardes"] = [f"{m}:{e}" for m, e in kardes]

    def tekli(i, sic=None, ist=None, sis=None, sm="__yok__"):
        sira = (bant[i % len(bant):] + bant[:i % len(bant)] + [m for m in modeller if m not in bant]
                + [k for k in kardes if k not in modeller])
        return motor.cagri(sira, ist if ist is not None else istem, sis if sis is not None else sistem, a.max_tokens,
                           sema if sm == "__yok__" else sm, (0.0 if a.n <= 1 else 0.7) if sic is None else sic)

    if yontem == "tek":
        r = paralel(motor, 1, tekli)[0]
        if isinstance(r, Cikis):
            raise r
        yaz(cikti, "aday_01.txt", r["metin"])
        oz.update(n_istenen=1, n_tamam=1, karar_dosya="aday_01.txt", model_kullanilan=f"{r['model']}:{r['efor']}")
        return 0, oz
    if yontem == "kapali":
        sonuc = paralel(motor, a.n, tekli)
        oylar = [None if isinstance(r, Cikis) else oy_anahtari(r["metin"], sema) for r in sonuc]
        karar, uz = oy_karar(oylar, a.n)
        if karar is None and a.genislet > a.n:
            ek = paralel(motor, a.genislet - a.n, lambda i: tekli(i + a.n))
            sonuc += ek
            oylar += [None if isinstance(r, Cikis) else oy_anahtari(r["metin"], sema) for r in ek]
            karar, uz = oy_karar(oylar, a.genislet)
        for i, r in enumerate(sonuc):
            if not isinstance(r, Cikis):
                yaz(cikti, f"aday_{i + 1:02d}.txt", r["metin"])
        oz.update(n_istenen=len(sonuc), n_tamam=sum(1 for r in sonuc if not isinstance(r, Cikis)), uzlasi=uz,
                  gecersiz_oy=sum(1 for o in oylar if o is None), uyusmazlik=karar is None)
        if all(isinstance(r, Cikis) and r.kod == 4 for r in sonuc):
            raise sonuc[0]
        if karar is None:
            return 5, oz
        oz["karar"] = json.loads(karar) if sema is not None else next(
            r["metin"] for r, o in zip(sonuc, oylar) if o == karar)
        return 0, oz
    if yontem in ("test", "acik"):
        sonuc = paralel(motor, a.n, tekli)
        dosyalar = []
        for i, r in enumerate(sonuc):
            if isinstance(r, Cikis):
                continue
            metin = kod_ayikla(r["metin"]) if yontem == "test" else r["metin"]
            ad = f"aday_{i + 1:02d}.{a.uzanti if yontem == 'test' else 'txt'}"
            yaz(cikti, ad, metin)                              # yalnız dosyaya; ASLA çalıştırılmaz
            dosyalar.append(ad)
        oz.update(n_istenen=a.n, n_tamam=len(dosyalar), adaylar=dosyalar,
                  not_="adaylar çalıştırılmadı; testi lider ayrı geçici kopyada koşar" if yontem == "test" else None)
        if all(isinstance(r, Cikis) and r.kod == 4 for r in sonuc):
            raise sonuc[0]
        return (0 if dosyalar else 5), oz
    if yontem == "ilk":
        bitti = threading.Event()

        def ilk_fn(i):
            if bitti.is_set():
                return None
            r = tekli(i)
            bitti.set()
            return r
        sonuc = [r for r in paralel(motor, max(a.n, len(bant)), ilk_fn) if r and not isinstance(r, Cikis)]
        if not sonuc:
            return 5, oz
        yaz(cikti, "aday_01.txt", sonuc[0]["metin"])
        oz.update(n_istenen=a.n, n_tamam=len(sonuc), karar_dosya="aday_01.txt")
        return 0, oz
    if yontem == "kapsam":
        if not a.kaynaklar or not os.path.isdir(a.kaynaklar):
            raise Cikis(2, "kapsam: --kaynaklar <klasör> gerekli")
        kaynaklar = []
        for ad in sorted(os.listdir(a.kaynaklar)):
            yol = os.path.join(a.kaynaklar, ad)
            if os.path.isfile(yol):
                metin = dosya_oku(yol, plat)
                t = tara_metin(metin, motor_anahtar(motor))
                if t:
                    raise Cikis(3, "gizlilik reddi (kaynak): " + ", ".join(t))
                kaynaklar.append((ad, metin))
        if not kaynaklar:
            raise Cikis(2, "kapsam: kaynak dosyası yok")

        def kapsam_fn(i):
            ad, metin = kaynaklar[i]
            return tekli(i, sic=0.0, ist=f"SORU:\n{istem}\n\nKAYNAK ({ad}):\n{metin}", sis=KAPSAM_SISTEM, sm=KAPSAM_SEMA)
        sonuc = paralel(motor, len(kaynaklar), kapsam_fn)
        iddialar, atilan = {}, 0
        for (ad, metin), r in zip(kaynaklar, sonuc):
            if isinstance(r, Cikis):
                continue
            try:
                ham = json_ayikla(r["metin"]).get("iddialar", [])
            except (ValueError, AttributeError):
                ham = []
            dog = alinti_dogrula(ham, metin)
            atilan += len(ham) - len(dog)
            for x in dog:
                h = hashlib.sha1(sade(str(x["iddia"])).encode("utf-8")).hexdigest()[:12]
                k = iddialar.setdefault(h, {"iddia": x["iddia"], "kaynaklar": []})
                k["kaynaklar"].append({"kaynak": ad, "birebir_alinti": x["birebir_alinti"], "satir": x.get("satir")})
        liste = sorted(iddialar.values(), key=lambda x: -len(x["kaynaklar"]))
        for x in liste:
            x["destek"] = len(x["kaynaklar"])
        yaz(cikti, "iddialar.json", json.dumps(liste, ensure_ascii=False, indent=1))
        oz.update(n_istenen=len(kaynaklar), n_tamam=sum(1 for r in sonuc if not isinstance(r, Cikis)),
                  iddia_sayisi=len(liste), atilan_alinti=atilan, karar_dosya="iddialar.json")
        if all(isinstance(r, Cikis) and r.kod == 4 for r in sonuc):
            raise sonuc[0]
        return (0 if liste else 5), oz
    if yontem == "juri":
        aileler = []
        for m in modeller:
            if m[0] not in [x[0] for x in aileler]:
                aileler.append(m)
        if len(aileler) < 2:
            raise Cikis(2, "juri: en az 2 farklı model ver (--model glm-5.3:high,deepseek-v4.1-flash:high,...)")

        def juri_fn(i):
            return motor.cagri([aileler[i]], istem, JURI_SISTEM, a.max_tokens, None, 0.0)
        sonuc = paralel(motor, len(aileler), juri_fn)
        puanlar = []
        for r in sonuc:
            if isinstance(r, Cikis):
                continue
            m = re.search(r"\d+(?:[.,]\d+)?", r["metin"])
            if m:
                puanlar.append(min(max(float(m.group().replace(",", ".")), 0.0), 10.0))
        if len(puanlar) < 2:
            return 5, oz
        puanlar.sort()
        orta = puanlar[len(puanlar) // 2] if len(puanlar) % 2 else (puanlar[len(puanlar) // 2 - 1] + puanlar[len(puanlar) // 2]) / 2
        oz.update(n_istenen=len(aileler), n_tamam=len(puanlar), puanlar=puanlar, karar=orta)
        return 0, oz
    raise Cikis(2, f"bilinmeyen yöntem {yontem}")


def motor_anahtar(motor):
    return getattr(motor, "_anahtar", None)


# ---------------------------------------------------------------- komutlar
def gonderim_kapisi(plat, yollar):
    """Gönderen her komutun ortak kapısı: platform dosyası (yasak_yol) ve projenin .orkestra.json kuralı."""
    platform_sart(plat)
    neden = proje_engeli(yollar, plat)
    if neden:
        raise Cikis(3, "gizlilik reddi: " + neden)


def sema_metni(sema):
    return json.dumps(sema, ensure_ascii=False) if sema is not None else ""


def guvenli_id(x):
    """toplu öğe kimliği klasör adı olur: yol ayırıcı/'..' içeremez (çıktı --cikti dışına yazılmaz)."""
    t = re.sub(r"[^A-Za-z0-9_.-]", "_", str(x))[:64].strip(".") or "oge"
    return t


def _istem_oku(a, plat, stdin):
    if not a.istem:
        raise Cikis(2, "--istem <dosya|-> gerekli (istem argv ile verilmez)")
    gonderim_kapisi(plat, [a.istem, a.sistem, a.sema, a.kaynaklar])
    metin = stdin.read() if a.istem == "-" else dosya_oku(a.istem, plat)
    sistem = dosya_oku(a.sistem, plat) if a.sistem else None
    sema = None
    if a.sema:
        try:
            sema = json.loads(dosya_oku(a.sema, plat))
        except ValueError:
            raise Cikis(2, "--sema geçerli JSON değil")
    return metin, sistem, sema


def komut_calistir(a, ortam):
    plat = ortam["plat"]
    if a.veri != "genel":
        raise Cikis(2, "--veri genel zorunlu: yalnız kamuya açık veri EVREN'e gider (kişisel/gizli/sağlık/bilinmiyor → abonelik modeli)")
    istem, sistem, sema = _istem_oku(a, plat, ortam.get("stdin", sys.stdin))
    anahtar = ortam["anahtar"]
    t = tara_metin(istem + "\n" + (sistem or "") + "\n" + sema_metni(sema), anahtar)
    if t:
        raise Cikis(3, "gizlilik reddi: " + ", ".join(t))
    modeller = model_listesi(a.model, a.efor, plat)
    if a.kuru:
        g_tok = (len(istem) + len(sistem or "")) / 3.0
        n = a.n if a.yontem in ("kapali", "test", "acik", "ilk") else 1
        tps = min(plat.get("tps", {}).get(modeller[0][0], 10), 30) if plat.get("tps") else 10
        plan = {"kuru": True, "anahtar": "var" if anahtar else "yok", "modeller": [f"{m}:{e}" for m, e in modeller],
                "bant_ici": [f"{m}:{e}" for m, e in bant_ayir(modeller, plat)], "yontem": a.yontem, "n": n,
                "n_en_cok": a.genislet if a.yontem == "kapali" else n, "tahmini_girdi_token": int(g_tok),
                "tahmini_kota_yuzde": round(100 * (a.genislet if a.yontem == "kapali" else n) * (g_tok + a.max_tokens) / GUNLUK_TAVAN, 3),
                "tahmini_sure_dk": round(a.max_tokens / tps / 60, 1), "tarama": "temiz", "platform": plat["kaynak"],
                "yasak_yol_sayisi": len(plat.get("yasak_yol", []))}
        return 0, plan
    if not anahtar:
        raise Cikis(2, "EVREN_API_KEY yok (kullanıcı ortam değişkeni)")
    motor = ortam["motor"]()
    motor._anahtar = anahtar
    cikti = a.cikti or os.path.join(dizin(), "evren_cikti", datetime.now().strftime("%Y%m%d-%H%M%S-") + secrets.token_hex(3))
    t0 = motor.saat()
    try:
        kod, oz = calistir_yontem(a, motor, plat, istem, sistem, sema, cikti)
    except Cikis as e:
        kod, oz = e.kod, {"yontem": a.yontem, "hata": e.mesaj}
    oz.update(id=os.path.basename(cikti), cikti=cikti, veri=a.veri, sure_sn=round(motor.saat() - t0, 1),
              istek=motor.istek_sayisi, bekleme_sn=round(motor.bekleme_sn, 1), harcama=motor.harcama,
              hatalar=(oz.get("hatalar") or []) + motor.hatalar, tps=motor.tps, sinif=a.sinif)
    if motor.notlar:
        oz["notlar"] = list(motor.notlar)
    d = motor._durum()
    if d.get("kalan") is not None:
        oz["kota"] = {"kalan_yuzde": round(100 * d["kalan"] / (d.get("tavan") or GUNLUK_TAVAN), 1)}
    motor._durum_yaz({"tps": motor.tps})
    motor.pay_kaydet()
    yaz(cikti, "ozet.json", maskele(json.dumps(oz, ensure_ascii=False, indent=1, default=str), anahtar))
    meta = {k: oz.get(k) for k in ("id", "yontem", "n_istenen", "n_tamam", "uzlasi", "uyusmazlik", "istek", "sure_sn",
                                   "hata", "cikti") if oz.get(k) is not None}
    meta["harcama_token"] = int(motor.harcama["kota_agirlikli"])
    if motor.notlar:
        meta["not"] = "; ".join(motor.notlar)
    meta["cikis"] = kod
    return kod, meta


def komut_toplu(a, ortam):
    """girdi.jsonl: her satır {"id": .., "istem": ..}; yöntem tek ya da kapali. Pilot: ilk 20'de uyuşmazlık > %40 → 5."""
    plat = ortam["plat"]
    if a.veri != "genel":
        raise Cikis(2, "--veri genel zorunlu")
    if a.yontem not in ("tek", "kapali"):
        raise Cikis(2, "toplu: yöntem tek ya da kapali")
    anahtar = ortam["anahtar"]
    gonderim_kapisi(plat, [a.girdi, a.sistem, a.sema])
    try:
        satirlar = [json.loads(x) for x in dosya_oku(a.girdi, plat).splitlines() if x.strip()]
        sema = json.loads(dosya_oku(a.sema, plat)) if a.sema else None
    except ValueError:
        raise Cikis(2, "toplu: girdi satırları ya da --sema geçerli JSON değil")
    if not all(isinstance(x, dict) for x in satirlar):
        raise Cikis(2, "toplu: her satır {\"id\": .., \"istem\": ..} nesnesi olmalı")
    sistem = dosya_oku(a.sistem, plat) if a.sistem else None
    t = tara_metin((sistem or "") + "\n" + sema_metni(sema), anahtar)
    if t:
        raise Cikis(3, "gizlilik reddi (sistem/şema): " + ", ".join(t))
    gor = set()
    for s in satirlar:
        t = tara_metin(str(s.get("istem", "")), anahtar)
        if t:
            raise Cikis(3, f"gizlilik reddi (öğe {guvenli_id(s.get('id'))}): " + ", ".join(t))
        g = guvenli_id(s.get("id"))
        if g in gor:
            raise Cikis(2, f"toplu: yinelenen/çakışan id ({g})")
        gor.add(g)
    if a.kuru:
        return 0, {"kuru": True, "oge": len(satirlar), "tahmini_cagri": len(satirlar) * (a.n if a.yontem == "kapali" else 1)}
    if not anahtar:
        raise Cikis(2, "EVREN_API_KEY yok")
    motor = ortam["motor"]()
    motor._anahtar = anahtar
    cikti = a.cikti or os.path.join(dizin(), "evren_cikti", "toplu-" + datetime.now().strftime("%Y%m%d-%H%M%S-") + secrets.token_hex(3))
    sonuclar = {}

    def oge(s):
        b = argparse.Namespace(**vars(a))
        alt = os.path.join(cikti, guvenli_id(s.get("id")))
        try:
            kod, oz = calistir_yontem(b, motor, plat, str(s["istem"]), sistem, sema, alt)
        except Cikis as e:
            kod, oz = e.kod, {"hata": e.mesaj}
        return s.get("id"), kod, oz

    def parti(liste):
        with cf.ThreadPoolExecutor(max_workers=max(1, motor.esz // max(a.n, 1))) as ex:
            for i, kod, oz in ex.map(oge, liste):
                sonuclar[guvenli_id(i)] = {"cikis": kod, "karar": oz.get("karar"), "uzlasi": oz.get("uzlasi")}
    parti(satirlar[:20])
    uyus = sum(1 for v in sonuclar.values() if v["cikis"] == 5)
    pilot_red = a.yontem == "kapali" and len(sonuclar) >= 10 and uyus / len(sonuclar) > 0.4
    if not pilot_red:
        parti(satirlar[20:])
    motor.pay_kaydet()
    yaz(cikti, "toplu_ozet.json", json.dumps(sonuclar, ensure_ascii=False, indent=1))
    meta = {"oge": len(satirlar), "tamam": sum(1 for v in sonuclar.values() if v["cikis"] == 0),
            "uyusmazlik": sum(1 for v in sonuclar.values() if v["cikis"] == 5), "istek": motor.istek_sayisi,
            "harcama_token": int(motor.harcama["kota_agirlikli"]), "cikti": cikti,
            "pilot": "uyuşmazlık > %40: parti güçlü modele" if pilot_red else "geçti"}
    if motor.notlar:
        meta["not"] = "; ".join(motor.notlar)
    return (5 if pilot_red else 0), meta


def komut_ping(a, ortam):
    anahtar = ortam["anahtar"]
    if not anahtar:
        raise Cikis(2, "EVREN_API_KEY yok")
    plat = ortam["plat"]
    platform_sart(plat)
    modeller = model_listesi(a.model or "deepseek-v4.1-flash:kapali" if "kapali" in plat["modeller"].get("deepseek-v4.1-flash", {})
                             else a.model or next(iter(plat["modeller"])), a.efor, plat)
    motor = ortam["motor"]()
    t0 = motor.saat()
    r = motor.cagri(modeller[:1], "Yalnız 'tamam' yaz.", None, 16, None, 0.0, uzat_izin=False, soguma_atla=True)
    sure = motor.saat() - t0
    motor.soguma_bitir(r["model"])
    d = motor._durum()
    return 0, {"model": f"{r['model']}:{r['efor']}", "sure_sn": round(sure, 2), "token": (r["usage"] or {}).get("total_tokens"),
               "kalan_yuzde": round(100 * d["kalan"] / (d.get("tavan") or GUNLUK_TAVAN), 2) if d.get("kalan") is not None else None,
               "yanit_bos_degil": bool(r["metin"]), "soguma": motor.soguma_eki().strip() or "yok"}


def komut_soguma(a, ortam):
    """Soğuma durumu (istek yok, anahtar gerekmez). --temizle <api>|*|hepsi elle siler."""
    km = ortam.get("kota") or kota_modulu()
    if a.temizle:
        if a.temizle in ("hepsi", "tumu", "tümü"):
            km.soguma_temizle(None)
            km.durum_guncelle(lambda d: d.pop("tukendi_until", None))   # elle çıkış: günlük kilit de kalkar
        else:
            km.soguma_temizle(a.temizle, yalniz=True)                    # yalnız o anahtar ('*' ayrı silinir)
    sg = km.soguma_oku()
    return 0, {"soguma": {ad: {"tur": k["tur"], "ardisik": k["ardisik"], "durum": k["durum"],
                               "kalan_dk": round(k["kalan_sn"] / 60, 1), "busy_until": k["busy_until"].isoformat()}
                          for ad, k in sg.items()}, "ozet": km.soguma_metni(sg) or "soğuma yok"}


def komut_kota(a, ortam):
    km = ortam.get("kota") or kota_modulu()
    if not ortam["anahtar"]:
        raise Cikis(2, "EVREN_API_KEY yok")
    kod, bas, g = km._evren_get("/quota", ortam["anahtar"])
    if kod != 200:
        raise Cikis(4, f"/v1/quota HTTP {kod}")
    x = km.evren_quota_coz(g, bas)
    if not x:
        raise Cikis(4, "/v1/quota beklenmeyen biçim")
    km.durum_yaz(x)
    return 0, {"kalan_yuzde": round(100 * x["kalan"] / x["tavan"], 2), "kalan_M": round(x["kalan"] / 1e6, 2),
               "reset": x["reset"], "eszamanli": x.get("concurrent"), "eszamanli_tavan": x.get("concurrency_limit"),
               "pencere_kalan_M": None if x.get("pencere_kalan") is None else round(x["pencere_kalan"] / 1e6, 2),
               "fair_share": x.get("fair_share"), "level": x.get("level"),
               "model_eszamanli_tavan": x.get("model_concurrency_limit") if x.get("model_concurrency_limit") is not None else "yok"}


def komut_modeller(a, ortam):
    km = ortam.get("kota") or kota_modulu()
    if not ortam["anahtar"]:
        raise Cikis(2, "EVREN_API_KEY yok")
    kod, _, g = km._evren_get("/models", ortam["anahtar"])
    if kod != 200 or not isinstance(g, dict):
        raise Cikis(4, f"/v1/models HTTP {kod}")
    return 0, {"modeller": [{k: m.get(k) for k in ("id", "task", "context_length", "default_max_output_tokens")}
                            for m in g.get("data", []) if isinstance(m, dict)]}


def komut_tara(a, ortam):
    """Gizlilik taraması, FAIL-CLOSED: okunamayan/ikili/büyük/çözülemeyen her dosya 'taranamadı' sayılır ve çıkış 3
    verir (Codex EVREN ajanına verilecek kopyanın kapısı). Projenin .orkestra.json gizli/yasak_havuz kuralı da."""
    plat, bulunan, n, taranamayan = ortam["plat"], {}, 0, 0
    platform_sart(plat)
    neden = proje_engeli([a.hedef if os.path.isdir(a.hedef) else os.path.dirname(os.path.abspath(a.hedef))], plat)
    if neden:
        bulunan[neden] = 1
    yollar = []
    if os.path.isdir(a.hedef):
        for kok, _, ds in os.walk(a.hedef):
            yollar += [os.path.join(kok, d) for d in ds]
    else:
        yollar = [a.hedef]
    for y in yollar:
        neden = yol_yasak(y, plat)
        if neden:
            bulunan.setdefault(neden, 0)
            bulunan[neden] += 1
            continue
        metin = metin_coz(y)
        if metin is None:
            taranamayan += 1
            continue
        n += 1
        for t in tara_metin(metin, ortam["anahtar"]):
            bulunan[t] = bulunan.get(t, 0) + 1
    if not yollar:
        taranamayan += 1                                       # hedef yok/boş: temiz denmez
    return (3 if bulunan or taranamayan else 0), {"taranan": n, "taranamayan": taranamayan, "bulunan_tur": bulunan}


def komut_kabul(a, ortam):
    with open(a.ozet, encoding="utf-8") as f:
        oz = json.load(f)
    plat = ortam["plat"]
    kul = oz.get("model_kullanilan") or (oz.get("modeller") or [""])[0]
    api, _, ef = kul.partition(":")
    ad, efor = plat["anahtar_ad"].get((api, ef), (f"evren-{api}", ef))
    x = {"model": ad, "efor": efor, "yontem": oz.get("yontem"), "sinif": a.sinif or oz.get("sinif"),
         "kabul": 1 if a.karar == "evet" else 0, "zaman": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    os.makedirs(dizin(), exist_ok=True)
    with open(os.path.join(dizin(), "kalite_kayit.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(x, ensure_ascii=False) + "\n")
    return 0, {"kaydedildi": x}


# ---------------------------------------------------------------- kontrol (ağsız)
def kontrol(_a=None, _ortam=None):
    import contextlib
    import io
    import shutil
    import tempfile
    sonuc = []

    def dogrula(ad, kosul):
        sonuc.append((ad, bool(kosul)))

    td = tempfile.mkdtemp(prefix="evren_kontrol_")
    eski_env = {k: os.environ.get(k) for k in ("ORKESTRA_DIR", "ORKESTRA_PLATFORMLAR", "EVREN_API_KEY")}
    os.environ["ORKESTRA_DIR"] = td
    TEST_PLATFORM = {"havuz": {"evren": {"ad": "EVREN (test)", "kota_okuyucu": "evren", "esz": 24, "paralel_ajan": 8,
                                         "yasak_yol": ["Documents/Notlar", "gizliklasor"]}},
                     "model": {"evren-deepseek-v4.1-flash": {"h": "evren", "api": "deepseek-v4.1-flash", "z": {"high": 27}},
                               "evren-deepseek-v4.1-flash-nr": {"h": "evren", "api": "deepseek-v4.1-flash", "dusunme": False,
                                                                "z": {"low": 17}},
                               "evren-glm-5.3": {"h": "evren", "api": "glm-5.3", "z": {"low": 21, "high": 28}},
                               "evren-zayif": {"h": "evren", "api": "zayif-model", "z": {"medium": 20}}},
                     "takma": {"glm": "evren-glm-5.3"}}
    os.environ["ORKESTRA_PLATFORMLAR"] = os.path.join(td, "platformlar.json")
    with open(os.environ["ORKESTRA_PLATFORMLAR"], "w", encoding="utf-8") as f:
        json.dump(TEST_PLATFORM, f)
    ANAHTAR = "TEST-KEY-123"
    km = kota_modulu()

    class Saat:
        def __init__(self):
            self.t, self.uykular = 1000.0, []

        def __call__(self):
            return self.t

        def uyu(self, sn):
            self.uykular.append(round(sn, 2))
            self.t += sn

    def sahte(yanitlar):
        """yanitlar: liste; her öğe (kod, başlık, yük) ya da çağrılabilir(govde)->üçlü. Sıra tükenince son öğe."""
        kayit = []
        kilit = threading.Lock()

        def f(govde, sn):
            with kilit:
                kayit.append(json.loads(json.dumps(govde)))
                y = yanitlar[min(len(kayit) - 1, len(yanitlar) - 1)]
            return y(govde) if callable(y) else y
        f.kayit = kayit
        return f

    def ok(metin, finish="stop", bas=None):
        return 200, bas or {}, {"content": metin, "finish_reason": finish, "usage": {"prompt_tokens": 10, "completion_tokens": 5}}

    def calis(argv, yanitlar=None, stdin_metin="", anahtar=ANAHTAR, saat=None, tut_soguma=False):
        saat = saat or Saat()
        if not tut_soguma:                                    # her sınama temiz soğuma durumuyla başlar
            km.soguma_temizle()
        akt = sahte(yanitlar or [ok("A")])
        plat = platform_yukle()
        ortam = {"anahtar": anahtar, "plat": plat, "stdin": io.StringIO(stdin_metin), "kota": km,
                 "motor": lambda: Motor(akt, plat, saat=saat, uyku=saat.uyu, kota=km, sure_sn=1800)}
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            kod = ana(argv, ortam)
        return kod, out.getvalue(), err.getvalue(), akt, saat

    def oku(yol):
        with open(yol, encoding="utf-8", errors="replace") as f:
            return f.read()

    def istem_dosya(metin, ad="istem.txt"):
        yol = os.path.join(td, ad)
        with open(yol, "w", encoding="utf-8") as f:
            f.write(metin)
        return yol

    try:
        cik = os.path.join(td, "cikti")
        temel = ["calistir", "--veri", "genel", "--model", "deepseek-v4.1-flash:high", "--cikti", cik]
        # 30: gizlilik → çıkış 3, sıfır istek
        tc = "10000000146"                                    # sağlaması geçerli örnek TCKN
        for ad, metin in [("TCKN", f"kimlik {tc}"), ("IBAN", "TR33 0006 1005 1978 6457 8413 26"), ("e-posta", "yaz: ali@ornek.com"),
                          ("sk-", "sk-" + "a" * 24), ("ghp_", "ghp_" + "A" * 30), ("AKIA", "AKIA" + "ABCDEFGHIJKLMNOP"),
                          ("özel anahtar", "-----BEGIN RSA PRIVATE KEY-----"), ("anahtar değeri", "bu " + ANAHTAR),
                          ("kart", "4111 1111 1111 1111"), ("sağlık", "hastanın epikriz notu"), ("telefon", "+90 532 123 45 67")]:
            kod, out, err, akt, _ = calis(temel + ["--istem", istem_dosya(metin)])
            dogrula(f"gizlilik: {ad} → çıkış 3, sıfır istek, içerik yazılmaz", kod == 3 and not akt.kayit and metin not in out + err)
        kod, out, err, akt, _ = calis(temel + ["--istem", istem_dosya("Türkiye'nin başkenti neresi? tanım: başkent")])
        dogrula("temiz kamuya açık istem geçer ('tanım' sağlık terimi sayılmaz)", kod == 0 and len(akt.kayit) == 1)
        dogrula("yol yasağı: .env, .ssh, auth.json reddedilir", all(yol_yasak(p, {"yasak_yol": []}) for p in
                (os.path.join(td, ".env"), os.path.join(td, ".ssh", "x.txt"), os.path.join(td, "auth.json"), os.path.join(td, "a.pem"))))
        dogrula("yol yasağı: platformlar.json yasak_yol (ör. özel notlar klasörü) reddedilir",
                yol_yasak(os.path.join(td, "Documents", "Notlar", "not.md"), {"yasak_yol": ["Documents\\Notlar"]}))
        # 31: --veri yok → 2
        kod, _, _, akt, _ = calis(["calistir", "--model", "glm-5.3:high", "--istem", istem_dosya("selam")])
        dogrula("--veri yok → çıkış 2, sıfır istek", kod == 2 and not akt.kayit)
        kod, _, _, akt, _ = calis(["calistir", "--veri", "bilinmiyor", "--model", "glm-5.3:high", "--istem", istem_dosya("selam")])
        dogrula("--veri bilinmiyor → çıkış 2, sıfır istek", kod == 2 and not akt.kayit)
        kod, _, _, akt, _ = calis(temel + ["--istem", istem_dosya("selam")], anahtar=None)
        dogrula("anahtar yok → çıkış 2", kod == 2 and not akt.kayit)
        kod, _, _, akt, _ = calis(["calistir", "--veri", "genel", "--model", "gemma-4-31b", "--istem", istem_dosya("selam")])
        dogrula("izin listesi dışı model → çıkış 2", kod == 2 and not akt.kayit)
        # 32: oybirliği
        kp = ["calistir", "--veri", "genel", "--model", "deepseek-v4.1-flash:high", "--yontem", "kapali", "--n", "3", "--cikti", cik]
        kod, out, _, akt, _ = calis(kp + ["--istem", istem_dosya("etiket?")], [ok("A"), ok("a "), ok("A.")])
        oz = json.loads(oku(os.path.join(cik, "ozet.json")))
        dogrula("['A','a ','A.'] → karar A, uzlaşı 1.0, 3 çağrı", kod == 0 and oz.get("uzlasi") == 1.0 and len(akt.kayit) == 3
                and sade(oz.get("karar", "")) == "a")
        # 33: 2-1 → 5 çağrı; 5'te < 4 → 5
        kod, _, _, akt, _ = calis(kp + ["--istem", istem_dosya("etiket?")], [ok("A"), ok("A"), ok("B"), ok("A"), ok("A")])
        dogrula("2-1 → 5 çağrıya genişler, 4/5 A → karar", kod == 0 and len(akt.kayit) == 5)
        kod, _, _, akt, _ = calis(kp + ["--istem", istem_dosya("etiket?")], [ok("A"), ok("A"), ok("B"), ok("B"), ok("C")])
        dogrula("5'te ≥4 aynı yok → çıkış 5 (yükselt)", kod == 5 and len(akt.kayit) == 5)
        # 34: şema
        sema_yol = istem_dosya(json.dumps({"type": "object", "required": ["etiket"], "properties": {"etiket": {"type": "string", "enum": ["x", "y"]}}}), "sema.json")
        kod, _, _, akt, _ = calis(kp + ["--istem", istem_dosya("etiket?"), "--sema", sema_yol],
                                  [ok('{"etiket": "x"}'), ok('```json\n{"etiket":"x"}\n```'), ok('{"etiket": "z"}'), ok('{"etiket": "x"}'), ok('{"etiket": "x"}')])
        oz = json.loads(oku(os.path.join(cik, "ozet.json")))
        dogrula("şemayı geçmeyen yanıt geçersiz oy; 4/5 x → karar {'etiket': 'x'}", kod == 0 and oz.get("gecersiz_oy") == 1
                and oz.get("karar") == {"etiket": "x"} and "response_format" in akt.kayit[0])
        # 35: 429 Retry-After ve fair share
        r429 = (429, {"retry-after": "7"}, {"error": {"code": "rate_limit_exceeded"}})
        kod, _, _, akt, saat = calis(temel + ["--istem", istem_dosya("selam")], [r429, ok("tamam")])
        dogrula("429 + Retry-After: 7 → sahte saatte 7 sn bekler, sonra başarı", kod == 0 and 7.0 in saat.uykular and len(akt.kayit) == 2)
        fs = (429, {}, {"error": {"code": "fair_share_limit_exceeded", "evren": {"concurrency_limit": 2}}})
        plat = platform_yukle()
        saat = Saat()
        m = Motor(sahte([fs, ok("tamam")]), plat, saat=saat, uyku=saat.uyu, kota=km)
        r = m.cagri([("glm-5.3", "high"), ("deepseek-v4.1-flash", "high")], "selam")
        dogrula("fair_share → model payı 2'ye düşer ve bant içi diğer modele geçer", m.pay.get("glm-5.3") == 2 and r["model"] == "deepseek-v4.1-flash")
        # 36: günlük kota
        km.durum_yaz({"tukendi_until": None})
        kod, _, _, akt, _ = calis(temel + ["--istem", istem_dosya("selam")], [(429, {}, {"error": {"code": "daily_token_limit_exceeded"}})])
        d = km.durum_oku()
        dogrula("429 daily → çıkış 4, durum kalan 0 ve tukendi_until", kod == 4 and d.get("kalan") == 0 and d.get("tukendi_until"))
        os.unlink(km.evren_durum_yolu())
        # 37: 503 → ikinci model
        kod, _, _, akt, _ = calis(["calistir", "--veri", "genel", "--model", "glm-5.3:high,deepseek-v4.1-flash:high", "--cikti", cik,
                                   "--istem", istem_dosya("selam")], [(503, {}, {"error": {"code": "model_capacity_exhausted"}}), ok("tamam")])
        dogrula("503 → listedeki ikinci modele geçer", kod == 0 and [g["model"] for g in akt.kayit] == ["glm-5.3", "deepseek-v4.1-flash"])
        kod, _, _, akt, saat = calis(["calistir", "--veri", "genel", "--model", "glm-5.3:high", "--cikti", cik, "--istem", istem_dosya("selam")],
                                     [(503, {}, {"error": {"code": "model_capacity_exhausted"}})])
        dogrula("hepsi 503 → glm ve kardeşi birer kez denenir, soğumaya alınır; dolu sunucuya yeniden vurmadan çıkış 4",
                kod == 4 and [g["model"] for g in akt.kayit] == ["glm-5.3", "deepseek-v4.1-flash"] and not saat.uykular
                and {"glm-5.3", "deepseek-v4.1-flash"} <= set(km.soguma_oku()))
        saat = Saat()
        m = Motor(sahte([(503, {}, {"error": {"code": "model_capacity_exhausted"}})]), platform_yukle(), saat=saat,
                  uyku=saat.uyu, kota=None)
        try:
            m.cagri([("glm-5.3", "high")], "selam")
        except Cikis:
            pass
        dogrula("soğuma yazılamıyorsa (kota modülü yok) eski 5/15/45 sn geri çekilme sürer", saat.uykular[:3] == [5, 15, 45])
        # 37b: stratejik soğuma (kalıcı durum dosyası; sahte saatte bekleme, gerçek saatte busy_until)
        def sg():
            return km.soguma_oku()

        def son_json(o):
            return json.loads(o.strip().splitlines()[-1])

        def sonra(sn):
            return (datetime.now(timezone.utc) + timedelta(seconds=sn)).isoformat()
        r503 = (503, {}, {"error": {"code": "model_capacity_exhausted"}})
        glm = ["calistir", "--veri", "genel", "--model", "glm-5.3:high", "--cikti", cik, "--istem", istem_dosya("selam")]
        km.soguma_temizle()
        saat = Saat()
        akt = sahte([(503, {}, {"error": {"code": "model_capacity_exhausted", "evren": {"resets_at": sonra(20)}}}), ok("tamam")])
        m = Motor(akt, platform_yukle(), saat=saat, uyku=saat.uyu, kota=km)
        m.rastgele = lambda: 1.0
        r = m.cagri([("glm-5.3", "high"), ("deepseek-v4.1-flash", "high")], "selam")
        dogrula("(a) 503 + resets_at 20 sn → aynı modelde ~20-25 sn üstel+jitter bekler, soğumaya almaz",
                r["model"] == "glm-5.3" and [g["model"] for g in akt.kayit] == ["glm-5.3", "glm-5.3"]
                and any(19 <= u <= 25.1 for u in saat.uykular) and "glm-5.3" not in sg())
        kod, out, _, akt, _ = calis(glm, [r503, ok("tamam")])
        k = sg().get("glm-5.3")
        dogrula("(b) ipucusuz 503 → glm 5 dk soğumaya, aynı Z bandındaki kardeş deepseek high'a geçer, not çıktıda",
                kod == 0 and [g["model"] for g in akt.kayit] == ["glm-5.3", "deepseek-v4.1-flash"] and k and k["durum"] == "aktif"
                and 240 < k["kalan_sn"] <= 300 and "soğuma" in son_json(out).get("not", ""))
        kod, out, _, akt, _ = calis(glm, [ok("tamam")], tut_soguma=True)
        dogrula("soğumadaki glm sıfır istekle atlanır, doğrudan kardeş; not 'yerine' yazar",
                kod == 0 and [g["model"] for g in akt.kayit] == ["deepseek-v4.1-flash"] and "yerine" in son_json(out).get("not", ""))
        kod, out, _, akt, _ = calis(glm + ["--kardessiz"], [ok("tamam")], tut_soguma=True)
        dogrula("kardeşsiz tek model soğumada → çıkış 4, sıfır istek, kalan dk yazılır", kod == 4 and not akt.kayit and "dk" in out)
        gecmis = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
        km.soguma_temizle()
        km.durum_yaz({"soguma": {"glm-5.3": {"tur": "503", "ardisik": 1, "zaman": time.time() - 420, "busy_until": gecmis}}})
        kod, _, _, akt, _ = calis(glm, [ok("tamam"), ok("cevap")], tut_soguma=True)
        dogrula("soğuma bitti → önce 16 token ping; başarı → kayıt silinir, asıl çağrı aynı modelde",
                kod == 0 and len(akt.kayit) == 2 and akt.kayit[0]["max_tokens"] == 16 and akt.kayit[1]["model"] == "glm-5.3"
                and "glm-5.3" not in sg())
        km.durum_yaz({"soguma": {"glm-5.3": {"tur": "503", "ardisik": 1, "zaman": time.time() - 420, "busy_until": gecmis}}})
        kod, _, _, akt, _ = calis(glm, [r503, ok("tamam")], tut_soguma=True)
        k = sg().get("glm-5.3")
        dogrula("yoklama 503 → ardışık 2, soğuma 10 dk'ya uzar, iş kardeşe gider",
                kod == 0 and k and k["ardisik"] == 2 and 540 < k["kalan_sn"] <= 600 and akt.kayit[-1]["model"] == "deepseek-v4.1-flash")
        sifir = (datetime.now(timezone.utc) + timedelta(hours=5)).replace(microsecond=0)
        kod, _, _, akt, _ = calis(temel + ["--istem", istem_dosya("selam")],
                                  [(429, {}, {"error": {"code": "daily_token_limit_exceeded", "evren": {"daily_reset_at": sifir.isoformat()}}})])
        g = sg().get("*")
        kod2, _, _, akt2, _ = calis(temel + ["--istem", istem_dosya("selam")], [ok("x")], tut_soguma=True)
        dogrula("429 daily + daily_reset_at → '*' soğuma o saate dek; sonraki çağrı sıfır istekle çıkış 4",
                kod == 4 and g and g["tur"] == "daily" and abs((g["busy_until"] - sifir).total_seconds()) < 2 and kod2 == 4 and not akt2.kayit)
        os.unlink(km.evren_durum_yolu())
        kod, _, _, akt, _ = calis(temel + ["--istem", istem_dosya("selam")],
                                  [(429, {}, {"error": {"code": "token_rate_limit_exceeded", "evren": {"resets_at": sonra(240)}}})])
        g = sg().get("*")
        dogrula("429 token penceresi (resets_at 4 dk) → '*' 4 dk soğuma, çıkış 4, tek istek",
                kod == 4 and len(akt.kayit) == 1 and g and g["tur"] == "token_rate" and 200 < g["kalan_sn"] <= 240)
        kod, _, _, akt, saat = calis(temel + ["--istem", istem_dosya("selam")],
                                     [(429, {"retry-after": "10"}, {"error": {"code": "token_rate_limit_exceeded"}}), ok("t")])
        dogrula("429 token penceresi kısa (Retry-After 10) → bekler, soğumaya almaz", kod == 0 and 10.0 in saat.uykular and "*" not in sg())
        kod, _, _, akt, _ = calis(temel + ["--istem", istem_dosya("selam")],
                                  [(429, {"retry-after": "1"}, {"error": {"code": "concurrency_limit_exceeded"}})])
        g = sg().get("*")
        dogrula("eşzamanlılık sınırı 4+ kez → '*' kısa soğuma (≤5 dk), çıkış 4", kod == 4 and g and g["tur"] == "concurrency"
                and g["kalan_sn"] <= 300)
        kod, _, _, akt, saat = calis(temel + ["--istem", istem_dosya("selam")], [ok("t")], tut_soguma=True)
        dogrula("'*' eşzamanlılık soğuması kısa (≤60 sn) → bekleyip dener; başarıda '*' silinir",
                kod == 0 and saat.uykular and "*" not in sg())
        plat = platform_yukle()
        dogrula("kardeş: glm high 28 → deepseek high 27 (Z bandı ≤4, birincil−1'in altı yok)",
                kardes_bul([("glm-5.3", "high")], plat) == [("deepseek-v4.1-flash", "high")])
        dogrula("kardeş eşiği delmez: glm low 21 + --sinif basit (Q22) → Z20/Z17 kardeş yok; sınıfsız Z20 (birincil−1) olur",
                kardes_bul([("glm-5.3", "low")], plat, "basit") == [] and kardes_bul([("glm-5.3", "low")], plat) == [("zayif-model", "medium")])
        km.soguma_temizle()
        saat = Saat()
        m = Motor(sahte([r503]), plat, saat=saat, uyku=saat.uyu, kota=km)
        paralel(m, 6, lambda i: m.cagri([("glm-5.3", "high")], "x"))
        dogrula("sürüde 6 paralel 503 → glm ardışığı yalnız 1 (çalıştırma başına bir kez)", (sg().get("glm-5.3") or {}).get("ardisik") == 1)
        km.soguma_kaydet("deepseek-v4.1-flash", "503")
        kod, out, _, akt, _ = calis(["ping", "--model", "deepseek-v4.1-flash:high"], [ok("tamam")], tut_soguma=True)
        dogrula("ping soğumayı atlar (yoklama aracı) ve başarıda kaydı siler",
                kod == 0 and len(akt.kayit) == 1 and "deepseek-v4.1-flash" not in sg())
        km.soguma_kaydet("glm-5.3", "503")
        kod, out, _, akt, _ = calis(["soguma"], tut_soguma=True)
        j = son_json(out)
        kod2, out2, _, _, _ = calis(["soguma", "--temizle", "hepsi"], tut_soguma=True)
        dogrula("soguma komutu: istek yok, model ve kalan dk yazar; --temizle hepsi siler",
                kod == 0 and not akt.kayit and "glm-5.3" in j["soguma"] and son_json(out2)["ozet"] == "soğuma yok")
        # ---- denetim düzeltmeleri (2026-11-09)
        km.soguma_temizle()
        saat = Saat()
        akt = sahte([r503])
        m = Motor(akt, plat, saat=saat, uyku=saat.uyu, kota=km)
        try:
            m.cagri([("glm-5.3", "high"), ("deepseek-v4.1-flash", "high")], "x")
        except Cikis:
            pass
        dogrula("iki model de 503 → her biri bir kez denenir (2 istek), ikisi de soğumada, bekleme yok",
                len(akt.kayit) == 2 and not saat.uykular and {"glm-5.3", "deepseek-v4.1-flash"} <= set(sg()))
        km.soguma_temizle()
        gecmis = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
        km.durum_yaz({"soguma": {"*": {"tur": "token_rate", "ardisik": 1, "zaman": time.time() - 400, "busy_until": gecmis},
                                 "glm-5.3": {"tur": "503", "ardisik": 2, "zaman": time.time() - 60, "busy_until": sonra(900)}}})
        akt = sahte([ok("tamam"), ok("cevap")])
        m = Motor(akt, plat, saat=Saat(), uyku=lambda s: None, kota=km)
        r = m.cagri([("glm-5.3", "high"), ("deepseek-v4.1-flash", "high")], "selam")
        dogrula("'*' yoklama: ping aktif soğumadaki glm'e değil deepseek'e gider; glm kaydı erken silinmez",
                akt.kayit[0]["model"] == "deepseek-v4.1-flash" and akt.kayit[0]["max_tokens"] == 16
                and r["model"] == "deepseek-v4.1-flash" and (sg().get("glm-5.3") or {}).get("durum") == "aktif" and "*" not in sg())
        km.durum_yaz({"soguma": {"*": {"tur": "token_rate", "ardisik": 1, "zaman": time.time() - 400, "busy_until": gecmis},
                                 "glm-5.3": {"tur": "503", "ardisik": 1, "zaman": time.time() - 60, "busy_until": sonra(600)},
                                 "deepseek-v4.1-flash": {"tur": "503", "ardisik": 1, "zaman": time.time() - 60,
                                                         "busy_until": sonra(300)}}})
        akt = sahte([ok("tamam")])
        m = Motor(akt, plat, saat=Saat(), uyku=lambda s: None, kota=km)
        try:
            m.cagri([("glm-5.3", "high"), ("deepseek-v4.1-flash", "high")], "selam")
            hata = None
        except Cikis as e:
            hata = e
        dogrula("'*' yoklama ama bütün modeller aktif soğumada → ping yok, sıfır istek, çıkış 4",
                hata is not None and hata.kod == 4 and not akt.kayit)
        km.soguma_temizle()
        km.durum_guncelle(lambda d: d.pop("tukendi_until", None))
        sifir = (datetime.now(timezone.utc) + timedelta(hours=5)).replace(microsecond=0)
        calis(temel + ["--istem", istem_dosya("selam")],
              [(429, {"retry-after": "60"}, {"error": {"code": "daily_token_limit_exceeded",
                                                       "evren": {"resets_at": sonra(240), "daily_reset_at": sifir.isoformat()}}})])
        g = sg().get("*")
        dogrula("günlük 429'da hem resets_at (4 dk) hem daily_reset_at (5 sa): soğuma daily_reset_at'e dek",
                g and g["tur"] == "daily" and abs((g["busy_until"] - sifir).total_seconds()) < 2)
        km.soguma_temizle()
        calis(temel + ["--istem", istem_dosya("selam")],
              [(429, {}, {"error": {"code": "daily_token_limit_exceeded", "evren": {"daily_reset_at": "2099-01-01T00:00:00Z"}}})])
        g = sg().get("*")
        tk = km._zaman(km.durum_oku().get("tukendi_until"))
        dogrula("uç daily_reset_at (2099): '*' soğuma ve tukendi_until en çok 36 sa",
                g and g["kalan_sn"] <= 36 * 3600 and tk and tk <= datetime.now(timezone.utc) + timedelta(hours=36, seconds=5))
        kod, out, _, _, _ = calis(["soguma", "--temizle", "hepsi"], tut_soguma=True)
        dogrula("soguma --temizle hepsi: tukendi_until da kalkar (elle çıkış)", kod == 0 and not km.durum_oku().get("tukendi_until"))
        for bas_ in ({"retry-after": "inf"}, {"retry-after": "1e999"}, {"retry-after": "nan"}, {"retry-after": "-5"}):
            kod, _, _, akt, _ = calis(glm, [(503, bas_, {"error": {"code": "model_capacity_exhausted"}}), ok("tamam")])
            dogrula(f"503 + bozuk Retry-After {bas_['retry-after']}: çökmez, soğuma + kardeşe geçer",
                    kod == 0 and akt.kayit[-1]["model"] == "deepseek-v4.1-flash")
        kod, _, _, akt, saat = calis(temel + ["--istem", istem_dosya("selam")],
                                     [(429, {"retry-after": "nan"}, {"error": {"code": "rate_limit_exceeded"}}), ok("t")])
        dogrula("429 + Retry-After nan: çökmez, varsayılan 5 sn bekler, başarı", kod == 0 and 5.0 in saat.uykular)
        kod, out, _, akt, _ = calis(glm, [(502, {}, {"error": {"code": "bad_gateway"}}), ok("tamam")])
        k = sg().get("glm-5.3")
        dogrula("502 → glm kısa soğuma (≤10 dk, 'diger'), kardeşe geçer",
                kod == 0 and akt.kayit[-1]["model"] == "deepseek-v4.1-flash" and k and k["tur"] == "diger" and k["kalan_sn"] <= 600)
        km.soguma_kaydet("*", "token_rate")
        km.soguma_kaydet("glm-5.3", "503")
        calis(["soguma", "--temizle", "glm-5.3"], tut_soguma=True)
        dogrula("soguma --temizle glm-5.3: yalnız glm silinir, '*' token penceresi kalır", "glm-5.3" not in sg() and "*" in sg())
        km.soguma_temizle()

        class YazamayanKota:
            def soguma_oku(self):
                return {}

            def soguma_kaydet(self, ad, tur, bitis=None):
                return {"tur": tur, "ardisik": 1, "busy_until": sonra(300), "yazilamadi": True}

            def soguma_temizle(self, *a, **k):
                return None

            def soguma_metni(self, s):
                return ""
        saat = Saat()
        m = Motor(sahte([r503]), plat, saat=saat, uyku=saat.uyu, kota=YazamayanKota())
        try:
            m.cagri([("glm-5.3", "high")], "x")
        except Cikis:
            pass
        dogrula("soğuma yazılamazsa not 'KAYDEDİLEMEDİ' der ('soğumaya alındı' demez), 5/15/45 geri çekilme sürer",
                any("KAYDEDİLEMEDİ" in n for n in m.notlar) and not any("soğumaya alındı" in n for n in m.notlar)
                and saat.uykular[:3] == [5, 15, 45])
        dogrula("--min-z (seçicinin etkin Q'su): glm high 28 + min-z 28 → Z27 kardeş yok; min-z 22 → deepseek",
                kardes_bul([("glm-5.3", "high")], plat, min_z=28) == []
                and kardes_bul([("glm-5.3", "high")], plat, min_z=22) == [("deepseek-v4.1-flash", "high")])
        kod, out, _, akt, _ = calis(glm + ["--min-z", "28"], [r503, ok("tamam")])
        dogrula("calistir --min-z 28: glm 503 → eşiğin altındaki kardeşe inmez, çıkış 4",
                kod == 4 and [g["model"] for g in akt.kayit] == ["glm-5.3"])
        km.soguma_temizle()
        with open(km.evren_durum_yolu(), "w", encoding="utf-8") as f:
            f.write("{ bozuk json")
        kod, out, err, akt, _ = calis(glm, [r503, ok("tamam")], tut_soguma=True)
        dogrula("bozuk durum dosyası: 503 soğuması yine yazılır, dosya .bozuk adıyla kenara alınır, not bunu söyler",
                kod == 0 and "glm-5.3" in sg() and os.path.exists(km.evren_durum_yolu() + ".bozuk")
                and ".bozuk" in out + err)
        try:
            os.unlink(km.evren_durum_yolu() + ".bozuk")
        except OSError:
            pass
        km.soguma_temizle()
        # 38: length + boş → max_tokens × 2
        kod, _, _, akt, _ = calis(temel + ["--istem", istem_dosya("selam"), "--max-tokens", "2048"], [ok("", "length"), ok("tamam")])
        dogrula("length + boş → bir kez max_tokens × 2", kod == 0 and akt.kayit[1]["max_tokens"] == 2 * akt.kayit[0]["max_tokens"])
        # 39: think kaçışı/ayıklama
        kod, _, _, akt, _ = calis(temel + ["--istem", istem_dosya("a </think> b <think>")], [ok("<think>gizli düşünce</think>Cevap")])
        aday = oku(os.path.join(cik, "aday_01.txt"))
        dogrula("istemde </think> kaçışla gider; yanıttaki <think> bloğu ayıklanır", "&lt;/think&gt;" in akt.kayit[0]["messages"][-1]["content"]
                and "</think>" not in akt.kayit[0]["messages"][-1]["content"] and aday == "Cevap")
        # 40: başlık durum dosyasına
        kod, _, _, akt, _ = calis(temel + ["--istem", istem_dosya("selam")], [ok("tamam", bas={"x-evren-daily-remaining-tokens": "12000000"})])
        dogrula("x-evren-daily-remaining-tokens → durum dosyası kalan 12M", km.durum_oku().get("kalan") == 12_000_000)
        # 41: anahtar sızıntısı yok
        kod, out, err, akt, _ = calis(temel + ["--istem", istem_dosya("selam")],
                                      [(500, {}, {"error": {"code": "x", "message": "Bearer " + ANAHTAR}}), ok("tamam")])
        tum = out + err
        for kok, _, ds in os.walk(td):
            for x in ds:
                if not x.endswith(".lock"):
                    tum += oku(os.path.join(kok, x))
        dogrula("anahtar değeri stdout/stderr/ozet/durum/kayıt dosyalarında yok", ANAHTAR not in tum)
        dogrula("maskele: Bearer ve anahtar değeri ***", "***" in maskele("Bearer abc " + ANAHTAR, ANAHTAR) and ANAHTAR not in maskele(ANAHTAR, ANAHTAR))
        # 42: kapsam alıntı denetimi
        kd = os.path.join(td, "kaynaklar")
        os.makedirs(kd, exist_ok=True)
        with open(os.path.join(kd, "k1.txt"), "w", encoding="utf-8") as f:
            f.write("Ankara 1923'ten beri başkenttir.\nNüfus bilgisi burada yok.")
        cev = json.dumps({"iddialar": [{"iddia": "Ankara başkent", "birebir_alinti": "Ankara 1923'ten beri başkenttir.", "satir": 1},
                                       {"iddia": "Nüfus 6M", "birebir_alinti": "nüfusu 6 milyondur", "satir": 2}]})
        kod, _, _, akt, _ = calis(["calistir", "--veri", "genel", "--model", "glm-5.3:high", "--yontem", "kapsam", "--kaynaklar", kd,
                                   "--cikti", cik, "--istem", istem_dosya("başkent?")], [ok(cev)])
        idd = json.loads(oku(os.path.join(cik, "iddialar.json")))
        dogrula("kapsam: kaynakta birebir bulunmayan alıntılı iddia atılır", kod == 0 and [x["iddia"] for x in idd] == ["Ankara başkent"])
        # 43: test yöntemi adayları çalıştırmaz
        kod, _, _, akt, _ = calis(["calistir", "--veri", "genel", "--model", "deepseek-v4.1-flash:high", "--yontem", "test", "--n", "4",
                                   "--uzanti", "py", "--cikti", cik, "--istem", istem_dosya("fonksiyon yaz")],
                                  [ok("```python\nprint('x')\n```")])
        kaynak = oku(os.path.abspath(__file__))
        yasakli = ["sub" + "process", "os." + "system", "os." + "popen", "ex" + "ec(", "ev" + "al(", "run" + "py", "multi" + "processing"]
        dogrula("test: 4 aday yalnız dosyaya yazılır; betikte süreç/eval/exec çağrısı yok", kod == 0 and
                sorted(x for x in os.listdir(cik) if x.startswith("aday_") and x.endswith(".py")) == [f"aday_0{i}.py" for i in range(1, 5)]
                and not any(y in kaynak for y in yasakli))
        # kuru: ağ yok
        kod, out, _, akt, _ = calis(temel + ["--istem", istem_dosya("selam"), "--kuru"], anahtar=None)
        dogrula("--kuru: anahtarsız da plan verir, sıfır istek", kod == 0 and not akt.kayit and '"kuru": true' in out)
        # 400 unsupported_parameter
        kod, _, _, akt, _ = calis(temel + ["--istem", istem_dosya("selam")],
                                  [(400, {}, {"error": {"code": "unsupported_parameter", "param": "stream_options"}}), ok("tamam")])
        dogrula("400 unsupported_parameter → parametre bir kez çıkarılır", kod == 0 and "stream_options" not in akt.kayit[1])
        # thinking kapalı ve efor
        kod, _, _, akt, _ = calis(["calistir", "--veri", "genel", "--model", "deepseek-v4.1-flash:kapali", "--cikti", cik,
                                   "--istem", istem_dosya("selam")])
        dogrula("ds-nr: thinking false gider, reasoning_effort gitmez", akt.kayit[0].get("thinking") is False and "reasoning_effort" not in akt.kayit[0])
        # Z bandı
        plat = platform_yukle()
        dogrula("karışım bandı: Z20 birincil, ds 27 bant dışı", bant_ayir([("zayif-model", "medium"), ("deepseek-v4.1-flash", "high")], plat)
                == [("zayif-model", "medium")])
        # token kovası
        saat = Saat()
        m = Motor(sahte([ok("x")]), plat, saat=saat, uyku=saat.uyu, kota=km)
        m.kova_tavan = 1000
        m.kova_bekle(800)
        m.kova_bekle(800)
        dogrula("5 dk token kovası: tavanı aşan ikinci çağrı pencere açılana kadar bekler", sum(saat.uykular) >= 299)
        # slot: bayat kilit temizlenir
        sd = os.path.join(td, "evren_slot")
        os.makedirs(sd, exist_ok=True)
        m.esz = 1
        bayat = os.path.join(sd, "00.lock")
        with open(bayat, "w"):
            pass
        os.utime(bayat, (time.time() - 3600, time.time() - 3600))
        y = m.slot_al()
        dogrula("slot: içeriksiz ve 35 dk'dan eski kilit bayat sayılır ve alınır", y[0] == bayat and os.path.exists(bayat))
        m.slot_birak(y)
        with open(bayat, "w") as f:                       # uzun çağrının taze kilidi: mtime eski ama süresi dolmamış
            f.write(f"999 baskasi {time.time() + 3000:.0f}")
        os.utime(bayat, (time.time() - 1000, time.time() - 1000))
        m.sure_sn = 2
        try:
            m.slot_al()
            dogrula("slot: süresi dolmamış (sahibi 1800 sn çağrıda) kilit 16 dk sonra çalınmaz", False)
        except Cikis:
            dogrula("slot: süresi dolmamış (sahibi 1800 sn çağrıda) kilit 16 dk sonra çalınmaz", os.path.exists(bayat))
        m.sure_sn = 1800
        Motor.slot_birak((bayat, "yanlis-belirtec"))
        dogrula("slot_birak yalnız kendi belirteciyle siler (başkasının kilidine dokunmaz)", os.path.exists(bayat))
        os.unlink(bayat)
        m2 = Motor(sahte([ok("x")]), plat, kota=km, uyku=lambda s: time.sleep(0.01))
        m2.esz = 2
        with cf.ThreadPoolExecutor(max_workers=8) as ex:
            r_ = list(ex.map(lambda i: m2.cagri([("glm-5.3", "high")], "selam"), range(24)))
        dogrula("slot yarışı: 24 paralel çağrı, 2 slot → hepsi başarılı, kilit kalmaz",
                all(not isinstance(x, Cikis) for x in r_) and not [x for x in os.listdir(sd) if x.endswith(".lock")])
        # gerçek HTTP yolu (127.0.0.1 sahte sunucu, SSE)
        import http.server

        class H(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                ln = int(self.headers.get("Content-Length", 0))
                self.rfile.read(ln)
                H.anahtar_basligi = self.headers.get("X-API-Key")
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("x-evren-daily-remaining-tokens", "14000000")
                self.end_headers()
                for p in ("An", "kara"):
                    self.wfile.write(f"data: {json.dumps({'choices': [{'delta': {'content': p}}]})}\n\n".encode())
                self.wfile.write(b'data: {"choices":[{"delta":{},"finish_reason":"stop"}],"usage":{"prompt_tokens":9,"completion_tokens":2}}\n\n')
                self.wfile.write(b"data: [DONE]\n\n")

            def log_message(self, *a):
                pass
        sv = http.server.HTTPServer(("127.0.0.1", 0), H)
        th = threading.Thread(target=sv.serve_forever, daemon=True)
        th.start()
        try:
            kod_, bas_, yuk_ = http_aktarim(f"http://127.0.0.1:{sv.server_port}/v1", ANAHTAR, okuma_sn=10)(
                {"model": "glm-5.3", "messages": []}, 30)
        finally:
            sv.shutdown()
            sv.server_close()
        dogrula("gerçek HTTP/SSE yolu (127.0.0.1): içerik birleşir, usage ve başlık okunur, anahtar X-API-Key'de",
                kod_ == 200 and yuk_["content"] == "Ankara" and yuk_["usage"]["completion_tokens"] == 2
                and bas_.get("x-evren-daily-remaining-tokens") == "14000000" and H.anahtar_basligi == ANAHTAR)
        dogrula("tara_metin: TCKN sağlaması yanlışsa eşleşmez", "TCKN" not in tara_metin("12345678901"))
        # ---- denetim düzeltmeleri (ikinci tur)
        # tara fail-closed ve kodlamalar
        tk = os.path.join(td, "tara_k")
        os.makedirs(tk, exist_ok=True)
        with open(os.path.join(tk, "u16.txt"), "w", encoding="utf-16") as f:
            f.write("kimlik 10000000146")
        with open(os.path.join(tk, "cp.txt"), "w", encoding="cp1254") as f:
            f.write("şöyle: kimlik 10000000146")
        import zipfile
        with zipfile.ZipFile(os.path.join(tk, "rapor.docx"), "w") as z:
            z.writestr("word/document.xml", "<w:t>kimlik 1000000</w:t><w:t>0146</w:t>")
        kod, out, _, akt, _ = calis(["tara", tk])
        j = json.loads(out.strip().splitlines()[-1])
        dogrula("tara: UTF-16, cp1254 ve docx içindeki TCKN bulunur (atlanmaz), çıkış 3", kod == 3 and j["taranan"] == 3
                and j["bulunan_tur"].get("TCKN") == 3)
        tk2 = os.path.join(td, "tara_k2")
        os.makedirs(tk2, exist_ok=True)
        with open(os.path.join(tk2, "veri.bin"), "wb") as f:
            f.write(b"\x00\x01\x02gizli")
        with open(os.path.join(tk2, "foto.png"), "wb") as f:
            f.write(b"\x89PNG....")
        with open(os.path.join(tk2, "temiz.txt"), "w", encoding="utf-8") as f:
            f.write("Ankara Türkiye'nin başkentidir.")
        kod, out, _, akt, _ = calis(["tara", tk2])
        j = json.loads(out.strip().splitlines()[-1])
        dogrula("tara: ikili/görsel dosya 'taranamayan' sayılır ve çıkış 3 (temiz denmez)", kod == 3 and j["taranamayan"] == 2
                and j["taranan"] == 1)
        os.unlink(os.path.join(tk2, "veri.bin"))
        os.unlink(os.path.join(tk2, "foto.png"))
        kod, out, _, akt, _ = calis(["tara", tk2])
        dogrula("tara: yalnız temiz metin → çıkış 0", kod == 0)
        # sır kalıpları (denetimdeki örnekler) ve yanlış pozitif sınırı
        for ornek in ['{"api_key": "q8Zt3LmN9pXw2Rk7"}', "SECRET_KEY=q8Zt3LmN9pXw2Rk7Vb", "DB_PASSWORD=Hunter2Hunter2",
                      "AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
                      "Authorization: Bearer q8Zt3LmN9pXw2Rk7Vb1x", "xoxb-1234567890-abcdefghij", "TC: 100 000 001 46",
                      "TC 100.000.001-46", "IBAN TR33-0006-1005-1978-6457-8413-26", "postgres://ali:S3cretPw@db:5432/x",
                      "-----BEGIN OPENSSH PRIVATE KEY-----", "anahtar Zq8T3LmN9pXw2Rk7Vb1xYc4Wd6Ef8Gh0Jk"]:
            dogrula(f"tarama yakalar: {ornek[:28]}…", bool(tara_metin(ornek)))
        for temiz in ["max_tokens: 4096", "token = get_token()", "commit 3f2a9c1e5b7d4a6f8e0c2b4d6f8a0c2e4b6d8f0a",
                      "Türkiye'nin başkenti Ankara'dır.", "telefon 0532 123 45 67 değil, sayı 12345678901"]:
            dogrula(f"yanlış pozitif yok: {temiz[:28]}…", not [t for t in tara_metin(temiz) if t != "telefon (+90)"])
        dogrula("şema Türkçe terim ensure_ascii olmadan taranır", bool(tara_metin(sema_metni({"enum": ["hastanın tanısı"]}))))
        # platform dosyası fail-closed
        eski_p = os.environ["ORKESTRA_PLATFORMLAR"]
        os.environ["ORKESTRA_PLATFORMLAR"] = os.path.join(td, "yok.json")
        kod, _, _, akt, _ = calis(temel + ["--istem", istem_dosya("selam")])
        kod2, _, _, _, _ = calis(["tara", tk2])
        dogrula("platformlar.json yok: calistir ve tara çıkış 2 (yasak_yol sessizce boşalmaz), sıfır istek",
                kod == 2 and kod2 == 2 and not akt.kayit)
        bozuk = os.path.join(td, "bozuk.json")
        with open(bozuk, "w", encoding="utf-8") as f:
            f.write('{"havuz": {"evren": {"yasak_yol": ["Documents/Notlar"],}}}')
        os.environ["ORKESTRA_PLATFORMLAR"] = bozuk
        kod, _, _, akt, _ = calis(temel + ["--istem", istem_dosya("selam")])
        dogrula("platformlar.json bozuk: çıkış 2, sıfır istek", kod == 2 and not akt.kayit)
        os.environ["ORKESTRA_PLATFORMLAR"] = eski_p
        kod, out, _, akt, _ = calis(temel + ["--istem", istem_dosya("selam"), "--platformlar", bozuk])
        dogrula("--platformlar ile verilen dosya kullanılır (bozuksa çıkış 2)", kod == 2 and not akt.kayit)
        # seçici adı ve takma ad kabul
        kod, out, _, akt, _ = calis(["calistir", "--veri", "genel", "--model", "evren-glm-5.3:high", "--cikti", cik,
                                     "--istem", istem_dosya("selam")])
        kod2, _, _, akt2, _ = calis(["calistir", "--veri", "genel", "--model", "evren-deepseek-v4.1-flash-nr", "--cikti", cik,
                                     "--istem", istem_dosya("selam")])
        dogrula("seçici adı (evren-glm-5.3:high) ve -nr adı API adına çevrilir", kod == 0 and akt.kayit[0]["model"] == "glm-5.3"
                and kod2 == 0 and akt2.kayit[0].get("thinking") is False)
        # 8.3 kısa ad / realpath
        uzun = os.path.join(td, "Documents", "Notlar")
        os.makedirs(uzun, exist_ok=True)
        dosya = os.path.join(uzun, "not.md")
        with open(dosya, "w", encoding="utf-8") as f:
            f.write("x")
        kisa = dosya
        if os.name == "nt":
            import ctypes
            tampon = ctypes.create_unicode_buffer(1024)
            if ctypes.windll.kernel32.GetShortPathNameW(dosya, tampon, 1024):
                kisa = tampon.value
        dogrula("yol yasağı 8.3 kısa adla (DOCUME~1) atlatılamaz (realpath)" + ("" if kisa != dosya else " [8.3 kapalı: uzun ad]"),
                bool(yol_yasak(kisa, platform_yukle())))
        # projenin .orkestra.json kuralı evren_suru'da da
        gp = os.path.join(td, "gizli_proje")
        os.makedirs(gp, exist_ok=True)
        with open(os.path.join(gp, ".orkestra.json"), "w", encoding="utf-8") as f:
            json.dump({"gizli": True}, f)
        gi = os.path.join(gp, "sozlesme.md")
        with open(gi, "w", encoding="utf-8") as f:
            f.write("Musteri sozlesmesi taslagi: fiyat 1.2M")
        kod, _, _, akt, _ = calis(temel + ["--istem", gi])
        with open(os.path.join(gp, ".orkestra.json"), "w", encoding="utf-8") as f:
            json.dump({"yasak_havuz": ["EVREN"]}, f)
        kod2, _, _, akt2, _ = calis(temel + ["--istem", gi])
        dogrula("proje .orkestra.json gizli/yasak_havuz EVREN: çıkış 3, sıfır istek", kod == 3 and kod2 == 3
                and not akt.kayit and not akt2.kayit)
        # toplu: id ile dışarı yazma yok
        tg = istem_dosya(json.dumps({"id": "../../disari", "istem": "selam"}) + "\n", "toplu.jsonl")
        tc_ = os.path.join(td, "toplu_cikti")
        kod, _, _, akt, _ = calis(["toplu", tg, "--veri", "genel", "--model", "glm-5.3:high", "--cikti", tc_])
        dogrula("toplu: '../' içeren id --cikti dışına yazamaz", kod == 0 and not os.path.exists(os.path.join(td, "disari"))
                and os.path.isdir(tc_))
        # model payı yalnız aşağı ve kalıcı (1 saat)
        saat = Saat()
        m = Motor(sahte([ok("x")]), plat, saat=saat, uyku=saat.uyu, kota=km)
        m.pay_dusur("glm-5.3", 32)
        dogrula("pay_dusur(32): pay 6'dan 32'ye ÇIKMAZ (yarıya iner)", m.pay["glm-5.3"] == 3)
        m2_ = Motor(sahte([ok("x")]), plat, saat=saat, uyku=saat.uyu, kota=km)
        km.durum_yaz({"model_pay_zaman": time.time() - 7200})
        m3_ = Motor(sahte([ok("x")]), plat, saat=saat, uyku=saat.uyu, kota=km)
        dogrula("model payı diske yazılır; 1 saatten eskiyse varsayılana döner", m2_.pay.get("glm-5.3") == 3 and "glm-5.3" not in m3_.pay)
        # paralel: beklenmeyen istisna sürüyü düşürmez
        sayac_ = {"n": 0}

        def patlak(govde):
            sayac_["n"] += 1
            if sayac_["n"] == 2:
                raise RuntimeError("beklenmeyen")
            return ok("A")
        kod, _, _, akt, _ = calis(kp + ["--istem", istem_dosya("etiket?")], [patlak])
        dogrula("kapali n=3, bir aday beklenmeyen istisna: sürü düşmez, ozet.json yazılır", os.path.exists(os.path.join(cik, "ozet.json"))
                and kod in (0, 5))
        # kota komutu model eşzamanlılığını da basar
        eski_get = km._evren_get
        km._evren_get = lambda yol, a_, **k: (200, {}, {"daily_remaining_tokens": 1e7, "daily_limit_tokens": 1.5e7,
                                                         "model_concurrency_limit": 6})
        try:
            kod, out, _, _, _ = calis(["kota"])
        finally:
            km._evren_get = eski_get
        dogrula("kota: model_eszamanli_tavan alanı basılır", kod == 0 and '"model_eszamanli_tavan": 6' in out)

        # ağ: yönlendirme anahtar taşımaz, http taban reddedilir, yarım akış başarı sayılmaz
        import http.server
        import socket

        class B(http.server.BaseHTTPRequestHandler):
            alinan = []

            def _kayit(self):
                B.alinan.append(self.headers.get("X-API-Key"))
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b"{}")
            do_GET = do_POST = _kayit

            def log_message(self, *a):
                pass
        sb = http.server.HTTPServer(("127.0.0.1", 0), B)

        class Y(http.server.BaseHTTPRequestHandler):
            def _yon(self):
                self.send_response(302)
                self.send_header("Location", f"http://127.0.0.1:{sb.server_port}/v1/x")
                self.send_header("Content-Length", "0")
                self.end_headers()
            do_GET = do_POST = _yon

            def log_message(self, *a):
                pass
        sy = http.server.HTTPServer(("127.0.0.1", 0), Y)

        class K(http.server.BaseHTTPRequestHandler):
            mod = "eof"
            protocol_version = "HTTP/1.1"

            def do_POST(self):
                self.rfile.read(int(self.headers.get("Content-Length", 0)))
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                if K.mod == "eof":
                    self.send_header("Connection", "close")
                    self.end_headers()
                    self.wfile.write(b'data: {"choices":[{"delta":{"content":"def f(x):\\n    return"}}]}\n\n')
                    self.wfile.flush()
                    self.close_connection = True
                else:
                    self.send_header("Transfer-Encoding", "chunked")
                    self.end_headers()
                    parca = b'data: {"choices":[{"delta":{"content":"yar"}}]}\n\n'
                    self.wfile.write(f"{len(parca) + 50:x}\r\n".encode() + parca)
                    self.wfile.flush()
                    self.connection.shutdown(socket.SHUT_RDWR)
                    self.close_connection = True

            def log_message(self, *a):
                pass
        sk = http.server.HTTPServer(("127.0.0.1", 0), K)
        ts = [threading.Thread(target=x.serve_forever, daemon=True) for x in (sb, sy, sk)]
        for t_ in ts:
            t_.start()
        try:
            kod_, _, yuk_ = http_aktarim(f"http://127.0.0.1:{sy.server_port}/v1", "FAKE-KEY-POST", okuma_sn=10)(
                {"model": "glm-5.3", "messages": []}, 30)
            eski_url = os.environ.get("EVREN_BASE_URL")
            os.environ["EVREN_BASE_URL"] = f"http://127.0.0.1:{sy.server_port}/v1"
            try:
                kod2_, _, _ = km._evren_get("/quota", "FAKE-KEY-REDIRECT")
            finally:
                if eski_url is None:
                    os.environ.pop("EVREN_BASE_URL", None)
                else:
                    os.environ["EVREN_BASE_URL"] = eski_url
            dogrula("302 yönlendirme izlenmez: anahtar başka origin'e gitmez (POST ve GET)", kod_ == 302 and kod2_ == 302
                    and "FAKE-KEY-POST" not in B.alinan and "FAKE-KEY-REDIRECT" not in B.alinan)
            try:
                http_aktarim("http://evren.ornek.org/v1", "x")
                dogrula("http:// taban (yerel değil) reddedilir", False)
            except Cikis as e:
                dogrula("http:// taban (yerel değil) reddedilir", e.kod == 2)
            sonuclar_ = []
            for mod_ in ("eof", "chunked"):
                K.mod = mod_
                try:
                    http_aktarim(f"http://127.0.0.1:{sk.server_port}/v1", "x", okuma_sn=10)({"model": "glm-5.3", "messages": []}, 30)
                    sonuclar_.append("başarı")
                except AgHatasi:
                    sonuclar_.append("AgHatasi")
                except Exception as e:
                    sonuclar_.append(type(e).__name__)
            dogrula("akış kopması: EOF'ta yarım içerik ve chunked IncompleteRead → AgHatasi (başarı/çöküş değil)",
                    sonuclar_ == ["AgHatasi", "AgHatasi"])
        finally:
            for x in (sb, sy, sk):
                x.shutdown()
                x.server_close()
    finally:
        for k, v in eski_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(td, ignore_errors=True)
    gecen = sum(1 for _, x in sonuc if x)
    for ad, x in sonuc:
        print(("PASS " if x else "FAIL ") + ad)
    print(f"\n{gecen}/{len(sonuc)} kural geçti")
    return 0 if gecen == len(sonuc) else 1


# ---------------------------------------------------------------- giriş
def ayristirici():
    ap = argparse.ArgumentParser(description="EVREN sürü/tek çağrı (çıktıyı asla çalıştırmaz)")
    alt = ap.add_subparsers(dest="komut")

    def ortak(p):
        p.add_argument("--veri", choices=["genel", "kisisel", "gizli", "saglik", "bilinmiyor"], default="bilinmiyor")
        p.add_argument("--model", help="api[:efor][,api2:efor2] (efor: low|medium|high|kapali)")
        p.add_argument("--efor", choices=["low", "medium", "high", "kapali"])
        p.add_argument("--dusunme", choices=["kapali"], help="thinking false (= --efor kapali)")
        p.add_argument("--yontem", choices=YONTEMLER, default="tek")
        p.add_argument("--n", type=int, default=3)
        p.add_argument("--genislet", type=int, default=5)
        p.add_argument("--istem")
        p.add_argument("--sistem")
        p.add_argument("--sema")
        p.add_argument("--kaynaklar")
        p.add_argument("--max-tokens", dest="max_tokens", type=int, default=4096)
        p.add_argument("--sure-sn", dest="sure_sn", type=float, default=1800)
        p.add_argument("--cikti")
        p.add_argument("--uzanti", default="txt")
        p.add_argument("--sinif")
        p.add_argument("--kuru", action="store_true")
        p.add_argument("--platformlar", help="seçicinin platform dosyası (varsayılan ORKESTRA_PLATFORMLAR / ~/.orkestra)")
        p.add_argument("--kardessiz", action="store_true", help="soğuma/503'te aynı Z bandındaki kardeş modele geçme")
        p.add_argument("--min-z", dest="min_z", type=float,
                       help="kardeş eşiği (seçicinin etkin Q'su; ÇAĞRI satırı otomatik ekler): kardeş Z bunun altına inmez")
    ortak(alt.add_parser("calistir"))
    t = alt.add_parser("toplu")
    t.add_argument("girdi")
    ortak(t)
    p = alt.add_parser("ping")
    p.add_argument("--model")
    p.add_argument("--efor")
    p.add_argument("--platformlar")
    alt.add_parser("kota")
    alt.add_parser("modeller")
    t = alt.add_parser("tara")
    t.add_argument("hedef")
    t.add_argument("--platformlar")
    k = alt.add_parser("kabul")
    k.add_argument("ozet")
    k.add_argument("karar", choices=["evet", "hayir"])
    k.add_argument("--sinif")
    sg = alt.add_parser("soguma")
    sg.add_argument("--temizle", help="api model adı, * ya da hepsi")
    alt.add_parser("kontrol")
    return ap


def ana(argv=None, ortam=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0].startswith("-"):
        argv = ["calistir"] + argv
    ap = ayristirici()
    try:
        a = ap.parse_args(argv)
    except SystemExit as e:
        return 2 if e.code else 0
    if a.komut == "kontrol":
        return kontrol()
    if ortam is None:
        anahtar = anahtar_al()
        plat = platform_yukle(getattr(a, "platformlar", None))
        km = kota_modulu()
        try:
            akt = http_aktarim(os.environ.get("EVREN_BASE_URL") or VARSAYILAN_TABAN, anahtar or "")
        except Cikis as e:
            print(json.dumps({"cikis": e.kod, "hata": e.mesaj}, ensure_ascii=False))
            return e.kod
        ortam = {"anahtar": anahtar, "plat": plat, "kota": km,
                 "motor": lambda: Motor(akt, plat, kota=km, sure_sn=getattr(a, "sure_sn", 1800))}
    elif getattr(a, "platformlar", None):
        ortam = dict(ortam, plat=platform_yukle(a.platformlar))
    anahtar = ortam.get("anahtar")
    if getattr(a, "dusunme", None) == "kapali":
        a.efor = "kapali"
    for alan in ("n", "genislet", "max_tokens"):
        if getattr(a, alan, 1) is not None and getattr(a, alan, 1) < 1:
            print(json.dumps({"cikis": 2, "hata": f"--{alan} ≥ 1"}, ensure_ascii=False))
            return 2
    if getattr(a, "n", 1) > 10 or getattr(a, "genislet", 1) > 10:
        print(json.dumps({"cikis": 2, "hata": "N > 10 kullanılmaz: genişliği artır, N'yi değil"}, ensure_ascii=False))
        return 2
    if getattr(a, "genislet", None) is not None and a.genislet < a.n:
        a.genislet = a.n
    try:
        kod, meta = {"calistir": komut_calistir, "toplu": komut_toplu, "ping": komut_ping, "kota": komut_kota,
                     "modeller": komut_modeller, "tara": komut_tara, "kabul": komut_kabul,
                     "soguma": komut_soguma}[a.komut](a, ortam)
    except Cikis as e:
        kod, meta = e.kod, {"cikis": e.kod, "hata": e.mesaj}
    except Exception as e:                                    # beklenmeyen: yalnız tür adı (anahtar sızmasın)
        kod, meta = 4, {"cikis": 4, "hata": f"beklenmeyen {type(e).__name__}"}
    meta.setdefault("cikis", kod)
    print(maskele(json.dumps(meta, ensure_ascii=False, default=str), anahtar))
    return kod


if __name__ == "__main__":
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8")
        except AttributeError:
            pass
    sys.exit(ana())
