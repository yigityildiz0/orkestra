"""Platform keşfi ve model envanteri (tasarım 5b G1-G2). Model çağırmaz.

1) imzalar.json eşlemesi: ikili yolları (glob, "sürüme göre en yeni"), yapılandırma dizinleri (yalnız varlık),
   ücret türü, otomatik çağrı izni.
2) Genel sezgiler (imzasız yeni platform): PATH farkı, yeni ~/.<ad> klasörü, yeni *_API_KEY / *_BASE_URL ADI
   (değer asla okunmaz), açık yerel portlar (isteğe bağlı), yeni MCP sunucu ADI.
3) Model çekme: Codex models_cache.json, agy `models` (izinle), bedava API /models (tüm görev türleri).
Kurallar: ücretli/hesap gerektiren/girişsiz platform asla otomatik aktif olmaz; imzasız yeni platform "aday-platform".
Kimlik dosyaları (auth.json, oauth_creds.json) yalnız varlık olarak denetlenir, açılmaz.
"""
import argparse
import glob
import json
import os
import re
import shutil
import socket
import subprocess
import sys
from pathlib import Path

from .veri import Veri, VeriHatasi, atomik_yaz, durum_dizini, json_oku, simdi_utc

ORTAM_DESENLERI = (re.compile(r".+_API_KEY$"), re.compile(r".+_BASE_URL$"), re.compile(r"^(OPENAI|ANTHROPIC|GEMINI|GOOGLE_AI)_"))
VARSAYILAN_PORTLAR = (11434, 1234, 8080, 8000, 5000, 7860, 8188)
AD_SOZLUGU = re.compile(r"(cli|agent|llm|^ai$|code|chat|gpt|claude|gemini|qwen|deepseek|ollama|lms|opencode|aider|"
                        r"cursor|copilot|kimi|goose|crush|droid|jules|windsurf)", re.I)
UCRETSIZ_TURLER = {"abonelik", "bedava", "yerel"}


def anlik_yolu():
    return durum_dizini() / "kesif-anlik.json"


# ------------------------------------------------------------------ yol ve sürüm
def yol_genislet(desen):
    """'%LOCALAPPDATA%/x', '~/.y', '$HOME/z' -> mutlak yol dizgisi."""
    s = re.sub(r"%([A-Za-z0-9_()]+)%", lambda m: os.environ.get(m.group(1), m.group(0)), str(desen))
    return os.path.expanduser(os.path.expandvars(s))


_SURUM = re.compile(r"(?<![\w.])(\d+)\.(\d+)(?:\.(\d+))?(?:[-.]?(alpha|beta|rc)[.-]?(\d+)?(?:\.(\d+))?)?")


def surum_ayikla(metin):
    """'0.169.0-alpha.3' -> (0,169,0,-1,3,0); bulunamazsa None. Ön sürüm, kararlıdan küçük sayılır."""
    m = _SURUM.search(str(metin or ""))
    if not m:
        return None
    a, b, c, on, n1, n2 = m.groups()
    on_deger = {"alpha": -3, "beta": -2, "rc": -1}.get(on, 0)
    return (int(a), int(b), int(c or 0), on_deger, int(n1 or 0), int(n2 or 0))


def _surum_komutla(exe, zaman_asimi=5):
    try:
        r = subprocess.run([exe, "--version"], capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=zaman_asimi, stdin=subprocess.DEVNULL)
        return (r.stdout or r.stderr or "").strip()[:200]
    except (OSError, subprocess.SubprocessError):
        return None


def ikili_bul(desenler, surum_al=None, which=shutil.which):
    """Desenlerden (glob ya da 'PATH:ad') en yeni ikili. Sıra: yoldaki sürüm > --version (surum_al verilirse) > mtime.
    Dönüş: {"yol", "surum", "aday_sayisi"} ya da None."""
    adaylar = []
    for d in desenler or []:
        if str(d).startswith("PATH:"):
            w = which(str(d)[5:])
            if w:
                adaylar.append(w)
            continue
        adaylar += [x for x in glob.glob(yol_genislet(d)) if os.path.isfile(x)]
    adaylar = list(dict.fromkeys(adaylar))
    if not adaylar:
        return None
    bilgi = []
    for y in adaylar:
        sv = surum_ayikla(y.replace("\\", "/"))
        metin = None
        if sv is None and surum_al:
            metin = surum_al(y)
            sv = surum_ayikla(metin)
        try:
            mt = os.path.getmtime(y)
        except OSError:
            mt = 0
        bilgi.append((sv or (-1,), mt, y, metin))
    bilgi.sort(key=lambda x: (x[0], x[1]))
    sv, _, y, metin = bilgi[-1]
    return {"yol": y, "surum": ".".join(str(x) for x in sv[:3]) if sv and sv[0] >= 0 else None,
            "aday_sayisi": len(adaylar)}


# ------------------------------------------------------------------ anlık görüntüler (yalnız ad/varlık)
def path_anligi(path=None):
    adlar = set()
    uzanti = {".exe", ".cmd", ".bat", ".ps1"} if os.name == "nt" else None
    for d in (path if path is not None else os.environ.get("PATH", "")).split(os.pathsep):
        if not d or not os.path.isdir(d):
            continue
        try:
            for f in os.listdir(d):
                p = os.path.join(d, f)
                if uzanti is not None:
                    st, ext = os.path.splitext(f)
                    if ext.lower() in uzanti:
                        adlar.add(st.lower())
                elif os.access(p, os.X_OK) and os.path.isfile(p):
                    adlar.add(f.lower())
        except OSError:
            continue
    return sorted(adlar)


def klasor_anligi(ev=None):
    ev = Path(ev) if ev else Path.home()
    out = set()
    try:
        out |= {p.name for p in ev.iterdir() if p.is_dir() and p.name.startswith(".")}
    except OSError:
        pass
    for env, on in (("APPDATA", "appdata/"), ("LOCALAPPDATA", "localappdata/")):
        k = os.environ.get(env)
        if k and os.path.isdir(k):
            try:
                out |= {on + p.name for p in Path(k).iterdir() if p.is_dir()}
                pr = Path(k) / "Programs"
                if pr.is_dir():
                    out |= {on + "programs/" + p.name for p in pr.iterdir() if p.is_dir()}
            except OSError:
                pass
    return sorted(out)


def ortam_adlari(ortam=None):
    """Yalnız ADLAR (değerler okunmaz)."""
    adlar = (ortam if ortam is not None else os.environ).keys()
    return sorted(a for a in adlar if any(d.search(a) for d in ORTAM_DESENLERI))


def port_tara(portlar=VARSAYILAN_PORTLAR, zaman_asimi=0.15):
    acik = []
    for p in portlar:
        try:
            with socket.create_connection(("127.0.0.1", int(p)), timeout=zaman_asimi):
                acik.append(int(p))
        except OSError:
            continue
    return acik


def mcp_adlari(claude_json=None, codex_toml=None):
    """MCP sunucu ADLARI (yapılandırma değerleri okunmaz/yazdırılmaz)."""
    adlar = set()
    cj = Path(claude_json) if claude_json else Path.home() / ".claude.json"
    try:
        d = json.loads(cj.read_text(encoding="utf-8-sig")) if cj.exists() else {}
        adlar |= {f"claude:{k}" for k in (d.get("mcpServers") or {})}
    except (OSError, ValueError):
        pass
    ct = Path(codex_toml) if codex_toml else Path.home() / ".codex" / "config.toml"
    try:
        if ct.exists():
            for m in re.finditer(r"^\[mcp_servers\.([A-Za-z0-9_.-]+)\]", ct.read_text(encoding="utf-8"), re.M):
                adlar.add(f"codex:{m.group(1).split('.')[0]}")
    except OSError:
        pass
    return sorted(adlar)


def anlik_al(port=False, ev=None, path=None, ortam=None, mcp=True):
    return {"zaman": simdi_utc().isoformat(timespec="seconds"), "path": path_anligi(path),
            "klasorler": klasor_anligi(ev), "ortam_adlari": ortam_adlari(ortam),
            "portlar": port_tara() if port else None, "mcp": mcp_adlari() if mcp else []}


def sinyaller(onceki, simdiki, bilinen_adlar=()):
    """Önceki anlıkla fark -> [{tur, ad, guven, not}]. Bilinen platform adları (imzalardan) sinyal üretmez."""
    onceki = onceki or {}
    bil = {str(b).lower() for b in bilinen_adlar}
    out = []
    if onceki.get("path") is not None:
        for ad in sorted(set(simdiki.get("path") or []) - set(onceki.get("path") or [])):
            if AD_SOZLUGU.search(ad) and ad not in bil:
                out.append({"tur": "path", "ad": ad, "guven": "dusuk", "not": "PATH'te yeni yürütülebilir: bak"})
    if onceki.get("klasorler") is not None:
        for ad in sorted(set(simdiki.get("klasorler") or []) - set(onceki.get("klasorler") or [])):
            if AD_SOZLUGU.search(ad.rsplit("/", 1)[-1].lstrip(".")) and ad.rsplit("/", 1)[-1].lstrip(".").lower() \
                    not in bil:
                out.append({"tur": "klasor", "ad": ad, "guven": "orta", "not": "yeni yapılandırma klasörü"})
    for ad in sorted(set(simdiki.get("ortam_adlari") or []) - set(onceki.get("ortam_adlari") or [])):
        if onceki.get("ortam_adlari") is None:
            break                                      # ilk anlık: taban çizgisi, sinyal yok
        out.append({"tur": "ortam", "ad": ad, "guven": "orta", "not": "yeni anahtar/taban adı (değer okunmadı)"})
    if simdiki.get("portlar"):
        for p in sorted(set(simdiki["portlar"]) - set(onceki.get("portlar") or [])):
            out.append({"tur": "port", "ad": str(p), "guven": "yuksek", "not": "yerel sunucu yanıt veriyor"})
    for ad in sorted(set(simdiki.get("mcp") or []) - set(onceki.get("mcp") or [])):
        if onceki.get("mcp") is not None:
            out.append({"tur": "mcp", "ad": ad, "guven": "orta", "not": "yeni MCP sunucusu (çoğu ücretli/kredili)"})
    return out


ICERIK_SINYALI = ("config.json", "config.toml", "config.yaml", "settings.json", "models", "auth.json")


def anlik_ozeti(an):
    """Taban çizgisi olarak saklanan özet: yalnız sezgiyle eşleşen adlar (tüm PATH/uygulama envanteri değil)."""
    def eslesen(ls):
        return sorted(x for x in (ls or []) if AD_SOZLUGU.search(str(x).rsplit("/", 1)[-1].lstrip(".")))
    return {"zaman": an.get("zaman"), "ozet": True, "path": eslesen(an.get("path")),
            "klasorler": eslesen(an.get("klasorler")), "ortam_adlari": list(an.get("ortam_adlari") or []),
            "portlar": an.get("portlar"), "mcp": list(an.get("mcp") or [])}


def mutlak_sinyaller(an, bilinen_adlar=(), ev=None):
    """Taban çizgisi yokken (ilk koşu) mutlak sezgi: ~/.<ad> klasöründe yapılandırma/model dosyası olan, imzası
    olmayan araç. Dosya açılmaz; yalnız ad varlığı."""
    ev = Path(ev) if ev else Path.home()
    bil = {str(b).lower() for b in bilinen_adlar}
    out = []
    for ad in an.get("klasorler") or []:
        if "/" in ad or not ad.startswith("."):
            continue
        kisa = ad.lstrip(".").lower()
        if not AD_SOZLUGU.search(kisa) or kisa in bil or kisa in ("orkestra", "claude", "codex", "gemini"):
            continue
        try:
            icerik = {p.name.lower() for p in (ev / ad).iterdir()}
        except OSError:
            continue
        if icerik & set(ICERIK_SINYALI):
            out.append({"tur": "klasor", "ad": ad, "guven": "orta", "not": "yapılandırma/model dosyalı araç klasörü "
                                                                           "(ilk koşu, imzasız)"})
    return out


# ------------------------------------------------------------------ model listeleri
# Katalog kip adı -> şema kip adı (modeller.schema.json kipler.girdi: metin, gorsel, pdf, ses, video)
KIP_ADI = {"text": "metin", "image": "gorsel", "audio": "ses", "video": "video", "pdf": "pdf", "file": "pdf"}


def codex_modelleri(kaynak):
    """models_cache.json (yol ya da sözlük) -> [{slug, gorunurluk, eforlar, varsayilan_efor, baglam, kipler, etiket,
    upgrade, parmak_izi}]."""
    d = json_oku(kaynak) if not isinstance(kaynak, dict) else kaynak
    if not d:
        return []
    out = []
    for m in d.get("models", d if isinstance(d, list) else []):
        if not isinstance(m, dict) or not m.get("slug"):
            continue
        ef = [e.get("effort") if isinstance(e, dict) else e for e in (m.get("supported_reasoning_levels") or [])]
        kip = [KIP_ADI.get(x, x) for x in (m.get("input_modalities") or [])]
        out.append({"slug": m["slug"], "gorunurluk": m.get("visibility"), "eforlar": [e for e in ef if e],
                    "varsayilan_efor": m.get("default_reasoning_level"), "baglam": m.get("context_window"),
                    "kipler": kip, "etiket": (m.get("description") or "")[:120], "upgrade": m.get("upgrade"),
                    "parmak_izi": m.get("comp_hash"), "sira": m.get("priority")})
    return out


_EFOR_SONEK = re.compile(r"-(none|minimal|low|medium|high|xhigh|max|ultra)$")


def agy_modelleri(metin):
    """`agy models` çıktısı -> [{slug, ad, model, efor}]. Efor kimliğe gömülüdür."""
    out = []
    for line in (metin or "").splitlines():
        if "\t" not in line:
            continue
        slug, ad = (x.strip() for x in line.split("\t", 1))
        if not slug or " " in slug:
            continue
        m = _EFOR_SONEK.search(slug)
        out.append({"slug": slug, "ad": ad, "model": slug[:m.start()] if m else slug, "efor": m.group(1) if m else None})
    return out


def bedava_modelleri(liste):
    """/v1/models data[] -> [{slug, gorev, kipler, baglam, efor_takma, ucretsiz_bitis}] (TÜM görev türleri)."""
    out = []
    for m in liste or []:
        cap = m.get("capabilities") or {}
        kip = [KIP_ADI.get(x, x) for x in (m.get("modalities") or [])]
        out.append({"slug": m.get("id"), "gorev": m.get("task", "chat"), "kipler": kip,
                    "baglam": m.get("context_length"), "efor": cap.get("reasoning_effort_values"),
                    "efor_takma": cap.get("reasoning_effort_aliases"),
                    "ucretsiz_bitis": (m.get("pricing") or {}).get("free_until")})
    return out


# ------------------------------------------------------------------ imza taraması
def imza_listesi(imzalar):
    """imzalar.json kökü: {"platformlar": [...]}, {"imzalar": [...]}, {id: {...}} ya da liste."""
    if isinstance(imzalar, list):
        return imzalar
    if not isinstance(imzalar, dict):
        return []
    for k in ("platformlar", "imzalar"):
        if isinstance(imzalar.get(k), list):
            return imzalar[k]
    return [dict(v, id=v.get("id", k)) for k, v in imzalar.items() if isinstance(v, dict)]


def _var_mi(desen):
    """Yapılandırma yolu varlığı: '#alan' parçası atılır, glob desteklenir. Dosya açılmaz."""
    y = yol_genislet(str(desen).split("#", 1)[0])
    if any(c in y for c in "*?["):
        return bool(glob.glob(y))
    return os.path.exists(y)


def platform_durumu(imza, ikili, dizinler_var, giris, kayitli):
    ucret = imza.get("ucret", "bilinmiyor")
    if not ikili and not dizinler_var:
        return "kayip" if kayitli else "yok"
    if ucret not in UCRETSIZ_TURLER:
        return "ucretli-kapali"
    if giris == "yok":
        return "kapali"
    return "aktif" if kayitli else "aday-platform"


def imza_tara(imzalar, platformlar=None, surum_al=None, giris_al=None, which=shutil.which):
    """imzalar.json -> {id: {durum, ikili, surum, dizinler, giris, ucret, otomatik_cagri_izni}}."""
    platformlar = platformlar or {}
    out = {}
    for imza in imza_listesi(imzalar):
        pid = imza.get("id")
        if not pid:
            continue
        ikili = ikili_coz(imza, surum_al=surum_al, which=which) if imza.get("appx") else \
            ikili_bul(imza.get("ikili"), surum_al=surum_al, which=which)
        diz = [d for d in imza.get("yapilandirma", []) if _var_mi(d)]
        kayit = [p for k, p in platformlar.items() if k == pid or (p or {}).get("imza") == pid]
        kayitli = bool(kayit)
        # kişisel kayıttaki dizinler de varlık kanıtıdır (ör. yerel araç kurulum klasörü)
        diz += [d for p in kayit for d in ([p.get("dizin")] if p.get("dizin") else []) + list(p.get("dizinler") or [])
                if _var_mi(d)]
        giris = "bilinmiyor"
        if giris_al and ikili and imza.get("giris_komutu"):
            giris = giris_al(imza, ikili["yol"])
        if imza.get("tur") == "api" and kayitli:
            # API türünde ikili yoktur; varlık yalnız kayıt + anahtar ADININ ortamda olmasıyla (değer okunmaz)
            adlar = [p.get("anahtar_env") or (p.get("api") or {}).get("anahtar_env") for p in kayit]
            adlar = [a for a in adlar if a]
            from .kota import anahtar_oku          # ortam + (Windows) kullanıcı ortamı kaydı; değer yalnız varlık için
            durum = "aktif" if (not adlar or any(anahtar_oku(a) for a in adlar)) else "kapali"
            out[pid] = {"durum": durum, "ikili": None, "surum": None, "dizinler": diz, "giris": "bilinmiyor",
                        "ucret": imza.get("ucret"), "otomatik_cagri_izni": imza.get("otomatik_cagri_izni", True),
                        "not": "API: anahtar adı " + ("ortamda" if durum == "aktif" else "ortamda yok (kullanıcı ortamına bak)")}
            continue
        durum = platform_durumu(imza, ikili, bool(diz), giris, kayitli)
        if kayitli and durum == "aday-platform":
            durum = "aktif"
        out[pid] = {"durum": durum, "ikili": ikili["yol"] if ikili else None, "surum": ikili["surum"] if ikili else None,
                    "dizinler": diz, "giris": giris, "ucret": imza.get("ucret"), "kayitli": kayitli,
                    "otomatik_cagri_izni": imza.get("otomatik_cagri_izni", True)}
    for pid in platformlar:
        if pid not in out and platformlar[pid].get("imza") not in out:
            out[pid] = {"durum": "imzasiz-kayitli", "ucret": platformlar[pid].get("ucret")}
    return out


def giris_denetle(imza, exe, zaman_asimi=15, _run=None):
    """Giriş denetimi (model çağırmaz). Biçimler: {"tur": "komut", "cmd": ["{ikili}", ...], "basari_deseni"},
    {"tur": "varlik", "dosya": ...} (yalnız varlık; dosya açılmaz), liste/dizgi (eski). mcp/uç türleri burada
    denetlenmez -> bilinmiyor. Çıktı metni saklanmaz; yalnız var/yok/bilinmiyor (e-posta vb. yazdırılmaz)."""
    g = imza.get("giris_komutu")
    if not g:
        return "bilinmiyor"
    desen = None
    if isinstance(g, dict):
        tur = g.get("tur")
        if tur == "mcp":
            # masaüstü host oturumu: kimlik alt sürece geçmez, `auth status` yanlış negatif verir
            if masaustu_host():
                return "var (host)"
            if not g.get("cmd"):
                return "bilinmiyor"
            tur = "komut"
        if tur == "varlik":
            d = g.get("dosya")
            return "var" if d and os.path.exists(yol_genislet(d)) else "bilinmiyor"
        if tur != "komut" or not g.get("cmd"):
            return "bilinmiyor"
        arg = [str(x).replace("{ikili}", exe) for x in g["cmd"]]
        desen = g.get("basari_deseni")
    else:
        arg = g if isinstance(g, list) else str(g).split()
        arg = [exe, *arg[1:]]
    try:
        r = (_run or subprocess.run)(arg, capture_output=True, text=True, encoding="utf-8", errors="replace",
                                     timeout=zaman_asimi, stdin=subprocess.DEVNULL,
                                     env=dict(os.environ, MSYS_NO_PATHCONV="1"))
    except (OSError, subprocess.SubprocessError):
        return "bilinmiyor"
    t = ((r.stdout or "") + (r.stderr or "")).lower()
    if "not logged" in t or "login required" in t or '"loggedin":false' in t.replace(" ", ""):
        return "yok"
    if desen:
        return "var" if desen.lower() in t else "bilinmiyor"
    if r.returncode == 0:
        return "var"
    return "bilinmiyor"


# ------------------------------------------------------------------ v7.1 doğrulama yolları (model çağırmaz)
APPX_ANAHTAR = r"Software\Classes\Local Settings\Software\Microsoft\Windows\CurrentVersion\AppModel\Repository\Packages"


def _appx_kok(onek, _winreg=None, _ps=None):
    """Appx paket kök klasörleri: HKCU paket deposu `PackageRootFolder` (yönetici gerekmez). Önek tam eşlenir
    (ör. 'Ad.Uygulama_' ile 'Ad.UygulamaPrimaryRuntime' karışmaz). Yedek: Get-AppxPackage InstallLocation."""
    out = []
    wr = _winreg
    if wr is None and os.name == "nt":
        try:
            import winreg as wr
        except ImportError:
            wr = None
    if wr is not None:
        try:
            with wr.OpenKey(wr.HKEY_CURRENT_USER, APPX_ANAHTAR) as k:
                i = 0
                while True:
                    try:
                        ad = wr.EnumKey(k, i)
                    except OSError:
                        break
                    i += 1
                    if not ad.startswith(onek):
                        continue
                    try:
                        with wr.OpenKey(k, ad) as k2:
                            kok = wr.QueryValueEx(k2, "PackageRootFolder")[0]
                            if kok:
                                out.append(str(kok))
                    except OSError:
                        continue
        except OSError:
            pass
    if not out and (_ps or os.name == "nt"):
        try:
            ad = onek.rstrip("_")
            r = (_ps or subprocess.run)(["powershell", "-NoProfile", "-Command",
                                         f"(Get-AppxPackage {ad}).InstallLocation"], capture_output=True, text=True,
                                        encoding="utf-8", errors="replace", timeout=20, stdin=subprocess.DEVNULL)
            out += [x.strip() for x in (r.stdout or "").splitlines() if x.strip()]
        except (OSError, subprocess.SubprocessError):
            pass
    return list(dict.fromkeys(out))


def ikili_coz(imza, surum_al=None, which=shutil.which, _appx=None):
    """Tek ikili çözümü (kota ve keşif aynı işlevi kullanır): imza globları + `appx` önekli paket kökü altındaki
    `appx_yol`. Her aday --version ile sürümlenir; en yüksek sürüm, eşitse en yeni mtime."""
    desen = list(imza.get("ikili") or [])
    for onek in ([imza["appx"]] if isinstance(imza.get("appx"), str) else list(imza.get("appx") or [])):
        for kok in (_appx or _appx_kok)(onek):
            desen.append(os.path.join(kok, imza.get("appx_yol") or ""))
    return ikili_bul(desen, surum_al=surum_al, which=which)


def masaustu_host(ortam=None):
    """Masaüstü uygulaması içinde çalışan host oturumu (alt süreç kimliği devralmaz; `auth status` yanlış negatif)."""
    o = ortam if ortam is not None else os.environ
    return o.get("CLAUDE_CODE_ENTRYPOINT") == "claude-desktop" and o.get("CLAUDE_CODE_SDK_HAS_HOST_AUTH_REFRESH") == "1"


TAKMA_AD_DESEN = re.compile(rb'\b(opus|sonnet|haiku|fable|mythos)\s*:\s*"(claude-[a-z0-9.\-]+)"')


def claude_takma_adlari(exe, _oku=None, en_cok=64 * 1024 * 1024):
    """İkili içinden takma ad -> kesin kimlik eşlemesi (sürüme duyarlı; eşleşme yoksa boş sözlük, hata değil)."""
    try:
        veri = (_oku or (lambda y: Path(y).read_bytes()[:en_cok]))(exe)
    except OSError:
        return {}
    out = {}
    for m in TAKMA_AD_DESEN.finditer(veri or b""):
        ad, kim = m.group(1).decode(), m.group(2).decode()
        # takma ad başına EN YÜKSEK sürüm (ikilideki ilk eşleşme eski bir eşleme tablosu olabilir)
        if ad not in out or _surum_anahtari(kim) > _surum_anahtari(out[ad]):
            out[ad] = kim
    return out


def _surum_anahtari(kimlik):
    return tuple(int(x) for x in re.findall(r"\d+", str(kimlik)))


def uc_girisi(api, _get=None, _anahtar=None):
    """Bedava uç girişi: GET {taban}/models 200 = var; anahtar yalnız başlıkta, https, yönlendirme izlenmez.
    /terms/status okunabiliyorsa kabul bilgisi (değer ne olursa olsun kapı `genel` kalır)."""
    from .kota import anahtar_oku, api_get
    anahtar = _anahtar() if _anahtar else anahtar_oku(api.get("anahtar_env"))
    if not anahtar:
        return {"giris": "yok", "neden": "anahtar ortamda yok"}
    try:
        kod, _, _ = (_get or api_get)(api, api.get("modeller_yolu") or "/models", anahtar)
    except Exception as e:
        return {"giris": "bilinmiyor", "neden": type(e).__name__}
    out = {"giris": "var" if kod == 200 else ("yok" if kod in (401, 403) else "bilinmiyor"), "http": kod}
    try:
        k2, _, g2 = (_get or api_get)(api, "/terms/status", anahtar)
        if k2 == 200 and isinstance(g2, dict):
            out["sartlar"] = {"kabul": g2.get("accepted", g2.get("kabul")),
                              "derlem_rizasi": g2.get("corpus_consent", g2.get("derlem_rizasi"))}
    except Exception:
        pass
    return out


def agy_dogrula(exe, tabanlar, _run=None, kayit=None):
    """agy model/efor/yapılandırma doğrulaması (slash komutları, 0 token): `models`, her taban için `/effort`,
    `/config` (`useG1Credits` true ise havuz kapalı: ek ücret yasağı), `/credits`. Dönüş özet sözlüğü.
    Her başsız çağrı `kayit(komut)` ile agy-cagri.jsonl'a okuma olarak yazılır (güvence: her çağrı görünür)."""
    ortam = dict(os.environ, MSYS_NO_PATHCONV="1")

    def calistir(*arg):
        if kayit:
            kayit(" ".join(str(x) for x in arg[:2]))
        r = (_run or subprocess.run)([exe, *arg], capture_output=True, text=True, encoding="utf-8", errors="replace",
                                     timeout=60, stdin=subprocess.DEVNULL, env=ortam)
        return r.stdout or ""

    def js(metin):
        try:
            return json.loads(metin)
        except ValueError:
            return {}
    out = {"modeller": agy_modelleri(calistir("models")), "eforlar": {}, "notlar": []}
    for t in tabanlar:
        d = js(calistir("-p", "/effort", "--model", t, "--output-format", "json"))
        av = (((d.get("command") or {}).get("data") or {}).get("available")) or d.get("available")
        if isinstance(av, list):
            out["eforlar"][t] = [str(x) for x in av]
    cfg = js(calistir("-p", "/config", "--output-format", "json"))
    c = ((cfg.get("command") or {}).get("data") or cfg) if isinstance(cfg, dict) else {}
    g1 = bool(c.get("useG1Credits")) if isinstance(c, dict) else False
    out["useG1Credits"] = g1
    if g1:
        out["notlar"].append("useG1Credits=true: ek ücretli kredi kullanımı açık; havuz kapalı sayılır (SOR)")
    cr = js(calistir("-p", "/credits", "--output-format", "json"))
    out["kredi"] = ((cr.get("command") or {}).get("data")) if isinstance(cr, dict) else None
    return out


def efor_farki(kayit_eforlari, kesif_eforlari):
    """Kayıtlı efor listesi ile CLI'ın sunduğu liste farkı: {"fazla": kayıtta olup sunulmayan, "eksik": sunulup
    kayıtta olmayan} (ör. Terra 'none')."""
    a, b = set(kayit_eforlari or []), set(kesif_eforlari or [])
    return {"fazla": sorted(a - b), "eksik": sorted(b - a)}


# ------------------------------------------------------------------ ana keşif
def kesif_yap(veri, onceki=None, port=False, agy=False, giris=False, surum=False, kaynaklar=None):
    """Keşif sonucu sözlüğü. kaynaklar (test): {"codex_cache": yol|dict, "agy_models": metin, "bedava": {hid: liste},
    "anlik": hazır anlık, "which": fn}."""
    kaynaklar = kaynaklar or {}
    onceki = onceki if onceki is not None else (json_oku(anlik_yolu()) if anlik_yolu().exists() else {})
    an = kaynaklar.get("anlik") or anlik_al(port=port)
    bilinen = set()
    for i in imza_listesi(veri.imzalar):
        bilinen.add(str(i.get("id", "")).lower())
        for d in i.get("ikili") or []:
            if str(d).startswith("PATH:"):
                bilinen.add(str(d)[5:].lower())
    pl = imza_tara(veri.imzalar or {}, veri.platformlar, surum_al=_surum_komutla if surum else None,
                   giris_al=giris_denetle if giris else None, which=kaynaklar.get("which") or shutil.which)
    modeller, notlar = {}, []
    # Codex
    cc = kaynaklar.get("codex_cache")
    if cc is None:
        cc = Path.home() / ".codex" / "models_cache.json"
    try:
        cm = codex_modelleri(cc)
        if cm:
            modeller["codex"] = cm
    except VeriHatasi:
        notlar.append("codex LİSTE OKUNAMADI")
    # agy (yalnız izinle; model çağrısı yok ama ToS gereği istek üzerine): model listesi + efor + /config + /credits
    agy_d = None
    if kaynaklar.get("agy_models") is not None:
        modeller["agy"] = agy_modelleri(kaynaklar["agy_models"])
    elif agy:
        try:
            from .kota import agy_yolu, _agy_kayit_satiri
            exe = agy_yolu()
            if not exe:
                raise FileNotFoundError("agy")
            tabanlar = sorted({e.get("kimlik") for p in veri.platformlar.values() for e in p.get("erisim", [])
                               if (e.get("yol") or p.get("yol")) in ("agy-elle", "agy-oto") and e.get("kimlik")})
            agy_d = (kaynaklar.get("agy_dogrula") or agy_dogrula)(exe, tabanlar, kayit=_agy_kayit_satiri)
            modeller["agy"] = agy_d.get("modeller") or []
            notlar += agy_d.get("notlar") or []
        except Exception as e:
            notlar.append(f"agy LİSTE OKUNAMADI ({type(e).__name__})")
    giris_uclari = {}
    # bedava API'ler
    for hid, h in veri.havuzlar.items():
        if h.get("okuyucu") != "bedava_api":
            continue
        pid = h.get("platform")
        if (kaynaklar.get("bedava") or {}).get(pid) is not None:
            modeller[pid] = bedava_modelleri(kaynaklar["bedava"][pid])
            continue
        if kaynaklar.get("bedava") is not None:
            continue
        try:
            from .kota import bedava_modeller
            ls = bedava_modeller(veri.api_ayari(pid))
            if ls is not None:
                modeller[pid] = bedava_modelleri(ls)
        except Exception as e:
            notlar.append(f"{pid} LİSTE OKUNAMADI ({type(e).__name__})")
        if giris:
            giris_uclari[pid] = uc_girisi(veri.api_ayari(pid))
            if pid in pl:
                pl[pid]["giris"] = giris_uclari[pid].get("giris")
    sinyal = sinyaller(onceki, an, bilinen)
    if not onceki and kaynaklar.get("anlik") is None:
        sinyal += mutlak_sinyaller(an, bilinen)
    aday_pl = [s for s in sinyal if s["tur"] in ("path", "klasor", "ortam", "port", "mcp")]
    takma = {}
    if surum and kaynaklar.get("anlik") is None:
        for i in imza_listesi(veri.imzalar):
            if (veri.platformlar.get(i.get("id")) or {}).get("host") and (pl.get(i.get("id")) or {}).get("ikili"):
                takma = claude_takma_adlari(pl[i["id"]]["ikili"])
                break
    return {"zaman": an["zaman"], "platformlar": pl, "modeller": modeller, "sinyaller": sinyal,
            "aday_platformlar": aday_pl, "anlik": an, "notlar": notlar, "agy_dogrulama": agy_d,
            "giris_uclari": giris_uclari, "claude_takma": takma}


def rapor_satirlari(sonuc):
    s = []
    for pid, p in sorted(sonuc["platformlar"].items()):
        if p["durum"] == "yok":
            continue
        n = len(sonuc["modeller"].get(pid, []))
        s.append(f"{pid:10s} {p['durum']:15s} ücret {p.get('ucret') or '?':10s} sürüm {p.get('surum') or '-':10s}"
                 + (f" {n} model" if n else "") + (" (elle)" if p.get("otomatik_cagri_izni") is False else ""))
        if p["durum"] in ("aday-platform", "ucretli-kapali") and not p.get("kayitli"):
            s.append(f"  YENİ PLATFORM {pid} ({p['durum']}, ücret: {p.get('ucret')}) -> açmak için onay · öneri: "
                     f"ork guncelle platform-ekle {pid}")
        if p["durum"] == "kayip":
            s.append(f"  KAYIP {pid}: ikili/dizin bulunamadı, havuz devre dışı")
    for x in sonuc["sinyaller"]:
        s.append(f"SİNYAL {x['tur']}: {x['ad']} ({x['guven']}) {x['not']} · öneri: ork guncelle platform-ekle "
                 f"{x['ad']} (yanlış pozitif: ork platform yoksay {x['ad']})")
    for n in sonuc["notlar"]:
        s.append(f"NOT {n}")
    return s


def main(argv=None):
    ap = argparse.ArgumentParser(prog="ork kesif", description="Platform ve model envanteri (model çağırmaz).")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--yaz", action="store_true", help="kesif-anlik.json'u güncelle")
    ap.add_argument("--port", action="store_true", help="yerel portları yokla")
    ap.add_argument("--agy", action="store_true", help="agy models listesini çek")
    ap.add_argument("--giris", action="store_true", help="giriş komutlarını çalıştır (yalnız var/yok)")
    ap.add_argument("--surum", action="store_true", help="sürümü --version ile doğrula")
    a = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    veri = Veri.yukle()
    r = kesif_yap(veri, port=a.port, agy=a.agy, giris=a.giris, surum=a.surum)
    if a.yaz:
        atomik_yaz(anlik_yolu(), anlik_ozeti(r["anlik"]))
    if a.json:
        r = dict(r, anlik=anlik_ozeti(r["anlik"]))       # tüm PATH/uygulama envanteri basılmaz
    print(json.dumps(r, ensure_ascii=False, indent=2, default=str) if a.json else "\n".join(rapor_satirlari(r)))
    return 0
