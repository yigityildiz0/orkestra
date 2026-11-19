"""Karar algoritması (tasarım bölüm 3): önce kalite, sonra kapasite.

Saf fonksiyonlar: tüm girdi parametreyle gelir (veri, kota anlığı, durum, saat); dosya okuyan tek yer
`proje_kurali` (proje .orkestra.json). Durum değişiklikleri (EMA, ρ histerezisi, son seçim) dönüşteki
`durum_guncel` alanındadır; kalıcılaştırma çağıranın (ork.py) işidir. Model çağrısı yok, ağ yok.

Değişmezler (hiçbir modda gevşemez): Q taban, tavan değil; tabanlar delinmez; yasak sağlayıcı/hat; gizlilik
fail-closed; kullanıcının açık isteği önce gelir (yasak/taban/gizlilik hariç); seçim deterministik.
Kodda model adı, sürüm ya da platform adı yok: hepsi data/*.json'dan (modeller, siniflar, platformlar, kurallar).
"""
import json
import math
import os
import re
from collections import Counter
from pathlib import Path

from .veri import (AGY_YOLLARI, EFOR_SIRA, HASSAS_VERI, KIP_EFORLARI, VeriHatasi, efor_arasi, efor_sira,
                   simdi_utc, zaman_coz)

EFOR_SIRA_KUME = set(EFOR_SIRA)

BOYUT_IB = {"mikro": 0.05, "kucuk": 0.3, "orta": 1.0, "buyuk": 3.0, "cok_buyuk": 10.0}
PENCERE_DK = {"5dk": 5, "5s": 300, "gun": 1440, "hafta": 10080}
HOST_YOLLARI = {
    "claude-code": {"claude-agent", "codex-exec", "agy-elle", "agy-oto", "bedava-api", "yerel", "elle"},
    "codex": {"codex-exec", "bedava-api", "agy-elle", "agy-oto", "yerel", "elle"},
    "agy": {"agy-elle", "yerel", "elle"},
}
# seçim durumu -> `ork sec` çıkış kodu (SOR kullanıcı kararı ister, BEKLE deterministik bekleme)
CIKIS_KODU = {"secildi": 0, "rota": 0, "elle": 0, "onay_gerekli": 4, "sor": 4, "bekle": 5, "hata": 3}
SOR_KATMAN = 6                         # Claude rezervine giren eşit kalite işi: otomatik aday değil, SOR
ELLE_YOLLAR = {"agy-elle", "elle"}
OTOMATIK_ROTA = {"yerel", "otomatik", "bedava-api"}
ELLE_ROTA = {"gui-elle", "agy-elle", "elle"}
ALAN_TAKMA_VARSAYILAN = {"gorsel": "gorsel_uretim"}
# siniflar.json "secici" bloğu yoksa kullanılan [T] tasarım parametreleri (olc ile ayarlanır)
VARSAYILAN_AYAR = {"elle_ceza": 1.3, "histerezis": 0.85, "esitlik_bandi": 0.10, "ayni_model_efor_bandi": 0.10,
                   "kova_adim": 0.05, "ema_alfa": 0.5, "ema_pencere_dk": 30, "bilinmiyor": {"k": 0.5,
                   "maliyet_carpani": 2}, "f_sinir": [0.3, 1.0], "tempo_t_min": 0.05, "sure_cezasi_dk": 120,
                   "tahmin_z_indirimi": 3, "tahmin_yasak_siniflar": ["zor", "kritik"], "halef_z_indirimi": 1,
                   "esdeger_yaklasik_z_indirimi": 2, "kanit_birikimi_olcut": 2, "token_is_birimi": 60000,
                   "kapanis_ceza_gun": 30, "kapanis_yasak_gun": 7, "xhigh_kosul_dk": 30, "hafif_isci": 2,
                   "kanit_birikimi_z": 1.0, "lider_brief_cikis_tok": 1500, "lider_ozet_giris_tok": 3500}
# Z kaynağı: ölçüm (aa, olcum, ...) | tahmin (indirimli, zor/kritikte yok) | halef_devralinan (resmî halef, önceki
# neslin ölçümü bir kez ve az indirimle taşınır; en son sürüm ilkesi gereği zor/kritikte de aday)
HALEF_Z = "halef_devralinan"


class SecimHatasi(VeriHatasi):
    pass


# ================================================================== yardımcılar
def _clamp(x, a, b):
    return max(a, min(b, x))


def ayar(veri):
    d = json.loads(json.dumps(VARSAYILAN_AYAR))
    for k, v in (veri.siniflar.get("secici") or {}).items():
        if isinstance(v, dict) and isinstance(d.get(k), dict):
            d[k].update(v)
        else:
            d[k] = v
    return d


def aday_adi(a):
    return f"{a.get('rol') or a['kimlik']}@{a['efor']}"


def aday_etiket(a):
    return f"{aday_adi(a)} ({a['yol']})"


def kademe(Q, siniflar):
    for k, (lo, hi) in (siniflar.get("kademeler") or {}).items():
        if lo <= Q <= hi:
            return k
    return "?"


def _sinif_sirasi(siniflar):
    return sorted(siniflar.get("q", {}), key=lambda s: siniflar["q"][s])


def bir_ust(sinif, siniflar):
    r = siniflar.get("zorluk_rubrigi") or {}
    merdiven = sorted(set((r.get("esikler") or {}).values()), key=lambda s: siniflar["q"].get(s, 0))
    if sinif not in merdiven:
        merdiven = _sinif_sirasi(siniflar)
    i = merdiven.index(sinif) if sinif in merdiven else -1
    return merdiven[min(i + 1, len(merdiven) - 1)] if i >= 0 else sinif


def rubrik(sinyaller, siniflar, belirsiz=False, alan=None):
    """Zorluk sinyali sayısı -> sınıf (siniflar.zorluk_rubrigi); kod/araştırma tür özel kuralı; belirsizlikte bir üst."""
    r = siniflar.get("zorluk_rubrigi") or {}
    bilinen = set(r.get("sinyaller") or [])
    bilinmeyen = [s for s in sinyaller if s not in bilinen]
    n = len({s for s in sinyaller if s in bilinen})
    sinif = None
    for aralik, ad in (r.get("esikler") or {}).items():
        a = str(aralik)
        if a.endswith("+"):
            ok = n >= int(a[:-1])
        elif "-" in a:
            lo, hi = (int(x) for x in a.split("-"))
            ok = lo <= n <= hi
        else:
            ok = n == int(a)
        if ok:
            sinif = ad
            break
    sinif = sinif or "normal"
    tur = r.get("tur_ozel") or {}
    q = siniflar.get("q") or {}
    if alan == "kod" and "kod" in tur and "kod" in q and sinif == "normal":
        sinif = "kod"
    if alan == "arastirma" and "arastirma" in tur and "arastirma" in q and n <= 2:
        sinif = "arastirma"
    if (belirsiz or bilinmeyen) and r.get("belirsizse") == "bir_ust":
        sinif = bir_ust(sinif, siniflar)
    return sinif


def alan_bul(alt, siniflar):
    for alan, alts in (siniflar.get("alanlar") or {}).items():
        if alt in (alts or []):
            return alan
    return None


def proje_kurali(dizin):
    """dizin'den yukarı `.orkestra.json` arar. Okunamazsa hata (kural sessizce düşmez).
    Biçim: {"zorunlu": {"gorsel": "sol:high", "*": "opus:high"}, "yasak": ["luna"], "yasak_havuz": ["bedava"],
            "gizli": true, "not": "..."}; gizli bool değilse güvenli tarafta gizli sayılır."""
    if not dizin:
        return {}
    d = Path(dizin).resolve()
    while True:
        f = d / ".orkestra.json"
        if f.is_file():
            try:
                k = json.loads(f.read_text(encoding="utf-8-sig"))
            except (OSError, ValueError) as e:
                raise SecimHatasi(f"proje kuralı okunamadı: {f} ({type(e).__name__}); düzelt ya da sil")
            if not isinstance(k, dict):
                raise SecimHatasi(f"proje kuralı nesne değil: {f}")
            gz = k.get("gizli", False)
            if not isinstance(gz, bool):
                gz = gz not in (None, 0, "", [], {})
            yasak = k.get("yasak", [])
            yh = k.get("yasak_havuz", [])
            return {"yol": str(f), "kok": str(d), "zorunlu": k.get("zorunlu") if isinstance(k.get("zorunlu"), dict)
                    else {}, "yasak": [yasak] if isinstance(yasak, str) else list(yasak or []),
                    "yasak_havuz": [yh] if isinstance(yh, str) else list(yh or []),
                    "gizli": gz, "not": k.get("not"), "varsayilan_veri": k.get("varsayilan_veri")}
        if d.parent == d:
            return {}
        d = d.parent


TOK_TAHMIN_BOYUT = {"mikro": [2000, 800], "kucuk": [8000, 3000], "orta": [30000, 8000], "buyuk": [80000, 20000],
                    "cok_buyuk": [200000, 50000]}          # [T] tek atımlık dış çağrı (giriş, çıkış) token varsayılanı


def tok_tahmin_coz(tk):
    """'giris:cikis' ya da [giris, cikis] -> (float, float); ikisi de >= 0 ve toplam > 0 olmalı (yoksa hata)."""
    try:
        if isinstance(tk, str) and ":" in tk:
            g_, _, c_ = tk.partition(":")
            out = (float(g_), float(c_))
        elif isinstance(tk, (list, tuple)) and len(tk) == 2:
            out = (float(tk[0]), float(tk[1]))
        else:
            raise ValueError
    except (TypeError, ValueError):
        raise SecimHatasi(f"--tok-tahmin biçimi giris:cikis (sayı) olmalı: {tk!r}")
    if out[0] < 0 or out[1] < 0 or not math.isfinite(out[0] + out[1]) or out[0] + out[1] <= 0:
        raise SecimHatasi(f"--tok-tahmin değerleri >= 0 ve toplamı > 0 olmalı: {tk!r}")
    return out


def _brief_metni(brief):
    p = Path(str(brief))
    try:
        if len(str(brief)) < 400 and p.is_file():
            return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        pass
    return str(brief)


def brief_tok_tahmini(brief, boyut, veri):
    """Brief boyutundan (giriş, çıkış) token tahmini: giriş = max(brief/3.5, boyut varsayılanı), çıkış = boyut
    varsayılanı (siniflar.secici.tok_tahmin_boyut, yoksa TOK_TAHMIN_BOYUT)."""
    tablo = dict(TOK_TAHMIN_BOYUT)
    tablo.update((veri.siniflar.get("secici") or {}).get("tok_tahmin_boyut") or {})
    g0, c0 = tablo.get(boyut or "orta") or tablo["orta"]
    return (max(len(_brief_metni(brief)) / 3.5, float(g0)), float(c0))


def _guvenli_proje(proje, gk):
    """Proje kökü kişisel `gizlilik.guvenli_projeler` listesinde mi (yol karşılaştırması, büyük/küçük harf duyarsız)."""
    if not proje or not proje.get("kok"):
        return False
    try:
        kok = Path(proje["kok"]).resolve()
    except OSError:
        return False
    for x in gk.get("guvenli_projeler") or []:
        try:
            if str(Path(os.path.expanduser(str(x))).resolve()).lower() == str(kok).lower():
                return True
        except OSError:
            continue
    return False


def istek_hazirla(istek, veri, proje=None):
    s = veri.siniflar
    i = dict(istek or {})
    if not s.get("q"):
        raise SecimHatasi("siniflar.json yok ya da q tablosu boş")
    takma = s.get("alan_takma") or ALAN_TAKMA_VARSAYILAN
    alan = i.get("alan") or (alan_bul(i.get("alt_alan"), s) if i.get("alt_alan") else None) or "genel"
    kip0 = set(i.get("kipler") or [])
    if alan == "genel" and not i.get("alt_alan"):          # medya kipi alan verilmeden geldiyse alanına eşle
        if "video" in kip0 and "video_analiz" in (s.get("alanlar") or {}):
            alan = "video_analiz"
        elif "ses" in kip0 and "ses" in (s.get("alanlar") or {}):
            alan = "ses"
    i["alan"] = takma.get(alan, alan)
    sinif = i.get("sinif")
    if not sinif:
        sinif = rubrik(i.get("sinyaller") or [], s, bool(i.get("belirsiz")), i["alan"])
    elif i.get("belirsiz"):
        sinif = bir_ust(sinif, s)
    if sinif not in s["q"]:
        raise SecimHatasi(f"bilinmeyen sınıf: {sinif} ({', '.join(_sinif_sirasi(s))})")
    i["sinif"], i["Q"] = sinif, s["q"][sinif]
    i["kritik"] = sinif == "kritik" or i["Q"] >= s["q"].get("kritik", 10 ** 6)
    ib = s.get("is_birimi") or {}
    i["ib"] = float(i.get("ib") or ib.get(i.get("boyut") or "orta") or BOYUT_IB.get(i.get("boyut") or "orta", 1.0))
    tk = i.get("tok_tahmin")
    if tk is not None:
        i["tok_tahmin"] = tok_tahmin_coz(tk)
    elif i.get("brief"):
        # brief verildiyse (plan parçası ya da --brief): tek atımlık dış çağrı için token tahmini (AA görev birimi
        # yerine). Girdi = brief tokenı ile boyut varsayılanının büyüğü; çıktı = boyut varsayılanı (efor çarpanı
        # kapasitede modelin efor maliyet oranıyla uygulanır).
        i["tok_tahmin"] = brief_tok_tahmini(i["brief"], i.get("boyut"), veri)
        i["tok_kaynak"] = "brief"
    else:
        i.pop("tok_tahmin", None)
    i.pop("brief", None)
    n = int(i.get("parca") or 1)
    if n > 1:                                # --parca N: seçim parça başına iş birimiyle yapılır
        i["ib_toplam"], i["ib"], i["parca"] = i["ib"], i["ib"] / n, n
    kip = list(i.get("kipler") or ["metin"])
    if i["alan"] == "video_analiz" and "video" not in kip:
        kip.append("video")
    if i["alan"] == "video_analiz" and i.get("alt_alan") == "konusmali" and "ses" not in kip:
        kip.append("ses")
    i["kipler"] = kip
    gk = veri.kurallar.get("gizlilik") or {}
    gz = gk.get("varsayilan_veri", "bilinmiyor")
    pv = (proje or {}).get("varsayilan_veri")          # proje varsayılanı (ör. herkese açık depo: genel)
    if pv not in ("genel", "kisisel", "gizli", "saglik", "bilinmiyor"):
        pv = None
    if pv == "genel" and not _guvenli_proje(proje, gk):
        # klonlanmış güvenilmeyen bir deponun .orkestra.json'u her işi `genel`e indirip kamu havuzunu açamaz:
        # gevşetme yalnız kişisel `gizlilik.guvenli_projeler` listesindeki kökte geçerli; sıkılaştırma her zaman
        pv = None
    i["veri"] = i.get("veri") or pv or gz
    if proje and proje.get("gizli"):
        i["veri"] = "gizli"
    i["host"] = veri.host(i.get("host"))
    i.setdefault("kip", "normal")
    i.setdefault("tur", "uretim")
    rol_ad = i.get("rol_is") or ("hakem" if i["tur"] == "dogrulama" else None)
    hk = (s.get("roller_is") or {}).get(rol_ad) if rol_ad else None
    if rol_ad and not isinstance(hk, dict):
        raise SecimHatasi(f"bilinmeyen rol: {rol_ad} ({', '.join(k for k in (s.get('roller_is') or {}) if not k.startswith('_') and isinstance(s['roller_is'][k], dict))})")
    if hk:                                   # rol eşiği: Z >= max(taban, Q_is - fark) (+3 ultra) (v6 rol tabanı)
        i["Q"] = max(float(hk.get("taban", 0)), i["Q"] - float(hk.get("fark", 0))) + (3 if i["kip"] == "ultra" else 0)
        if hk.get("bedava_izinli") is False:
            i["kamu_yasak"] = True
        i["izleyici"] = bool(hk.get("izleyici"))
    return i


# ================================================================== efor kuralları
def efor_kurali(siniflar, alt, rol):
    """{taban, tavan, kullanma}: _genel[rol] varsayılanı, üstüne alt alan (rol ya da _tumu)."""
    ek = siniflar.get("efor_kurallari") or {}
    out = {k: v for k, v in ((ek.get("_genel") or {}).get(rol) or {}).items() if k in ("taban", "tavan", "kullanma")}
    alt_k = ek.get(alt or "", {}) if isinstance(ek.get(alt or ""), dict) else {}
    x = alt_k.get(rol) or alt_k.get("_tumu") or {}
    out.update({k: v for k, v in x.items() if k in ("taban", "tavan", "kullanma")})
    return out


# ================================================================== şef tavanı (R16)
# İşçi, şefin (liderin) model x eforunu aşmaz. Aynı aile: en çok şefin modeli şefin eforunda (üst model ve üst efor
# yok). Başka aile: Z <= Z(şef) + gürültü bandı; alan ölçümü varsa alanda da şefi geçmez. Yalnız kullanıcının açık
# isteği (--tavan-yok, --zorla, ultra kipi, SOR yanıtı tavan_yok, sabit kullanıcı kuralı) kaldırır; çıktıya uyarı düşer.
SEF_VARSAYILAN = {"bant": "aa_z", "ortam_sef": ["ORKESTRA_SEF"], "ortam_model": ["ORKESTRA_SEF_MODEL", "ANTHROPIC_MODEL"],
                  "ortam_efor": ["ORKESTRA_SEF_EFOR", "CLAUDE_EFFORT", "CLAUDE_CODE_EFFORT_LEVEL"],
                  "ayar_dosyalari": [".claude/settings.local.json", ".claude/settings.json",
                                     "~/.claude/settings.json"], "ayar_model": "model", "ayar_efor": "effortLevel",
                  "oturum_ortam": "CLAUDE_CODE_SESSION_ID", "oturum_saat": 12}
TAVAN_TETIK = "T6"
TAVAN_YOK = "tavan_yok"                 # SOR T6 yanıtı: bu iş için tavanı kaldır (uyarıyla)
TAVAN_KALDIRAN = {"tavan_yok": "--tavan-yok", "ultra": "ultra kipi (açık istek)", "sor": "SOR yanıtı tavan_yok"}


def sef_ayari(veri):
    d = json.loads(json.dumps(SEF_VARSAYILAN))
    d.update({k: v for k, v in (veri.siniflar.get("sef_tavani") or {}).items() if not str(k).startswith("_")})
    return d


def sef_rol_bul_ayrintili(metin, veri):
    """Serbest model adı -> (rol, kimlik, kesin). kesin=False: kayıtta yok, ad parçasından en yakın rolün etkin
    sürümü varsayıldı (ör. 'claude-3-opus' -> opus etkin sürümü); çağıran uyarı basar (tavan gerçek şeften gevşek
    olabilir). Tarih soneki (-20261101) ve [1m] eki atılır."""
    t = re.sub(r"\[.*?\]", "", str(metin or "")).strip().lower()
    if not t:
        return None, None, False
    for aday in dict.fromkeys([t, re.sub(r"-(20\d{6}|20\d{2}-\d{2}-\d{2})$", "", t)]):
        if aday in veri.roller and (veri.roller[aday] or {}).get("aktif"):
            return aday, veri.roller[aday]["aktif"], True
        if veri.model(aday):
            return veri.model_rol(aday), aday, True
    parcalar = set(re.split(r"[^a-z0-9_]+", t))
    eslesen = sorted((r for r in veri.roller if r in parcalar and (veri.roller[r] or {}).get("aktif")),
                     key=len, reverse=True)
    if eslesen:
        return eslesen[0], veri.roller[eslesen[0]]["aktif"], False
    return None, None, False


def sef_rol_bul(metin, veri):
    """Serbest model adı ('opus', 'opus[1m]', 'claude-opus-5-5', 'sonnet') -> (rol, kimlik) ya da (None, None)."""
    return sef_rol_bul_ayrintili(metin, veri)[:2]


def _varsayilan_efor(kimlik, m, veri):
    if (m or {}).get("varsayilan_efor"):
        return m["varsayilan_efor"]
    for p in sorted(veri.platformlar.values(), key=lambda p: not p.get("host")):
        if any(e.get("kimlik") == kimlik for e in p.get("erisim", [])) and p.get("varsayilan_efor"):
            return p["varsayilan_efor"]
    var = [e for e, v in ((m or {}).get("varyantlar") or {}).items() if v.get("z") is not None]
    return "medium" if "medium" in var else (sorted(var, key=efor_sira)[len(var) // 2] if var else None)


def _model_duzeyi(m, efor):
    """Aynı ailede model karşılaştırması: modelin şef eforundaki Z'si; yoksa o efora kadarki en yüksek, o da yoksa en
    düşük bilinen Z."""
    var = {e: float(v["z"]) for e, v in ((m or {}).get("varyantlar") or {}).items() if v.get("z") is not None}
    if not var:
        return None
    if efor in var:
        return var[efor]
    alt = [z for e, z in var.items() if efor_sira(e) <= efor_sira(efor)]
    return max(alt) if alt else min(var.values())


def sef_coz(sef, veri):
    """'opus:high' | 'opus@high' | 'opus' | {'rol'|'kimlik', 'efor', 'kaynak'} -> tavan sözlüğü. Efor verilmezse
    modelin varsayılan eforu (uyarılı). Çözülemezse SecimHatasi (sessizce tavansız devam yok)."""
    kaynak = None
    if isinstance(sef, dict):
        ad = sef.get("kimlik") or sef.get("model") or sef.get("rol")
        ef, kaynak = sef.get("efor"), sef.get("kaynak")
    else:
        ad, _, ef = str(sef or "").replace("@", ":").partition(":")
    rol, kimlik, kesin = sef_rol_bul_ayrintili(ad, veri)
    m = veri.model(kimlik) if kimlik else None
    if not m:
        raise SecimHatasi(f"şef çözülemedi: {sef!r} (rol:efor, ör. opus:high)")
    ef = (str(ef).strip().lower() or None) if ef else None
    varsayildi = not ef
    if varsayildi:
        ef = _varsayilan_efor(kimlik, m, veri)
    z = _model_duzeyi(m, ef)
    if z is None or ef not in EFOR_SIRA_KUME:
        raise SecimHatasi(f"şef eforu çözülemedi: {sef!r} ({ef})")
    ay = sef_ayari(veri)
    bant = ay.get("bant")
    bant = float(bant) if isinstance(bant, (int, float)) else float((veri.siniflar.get("delta") or {}).get(bant, 2))
    return {"rol": rol, "kimlik": kimlik, "efor": ef, "aile": m.get("saglayici"), "z": z, "bant": bant,
            "etiket": f"{rol or kimlik}@{ef}", "kaynak": kaynak, "efor_varsayildi": varsayildi,
            "yaklasik": None if kesin else str(ad)}


def sef_siki(a, b, veri):
    """İki şef değerinden daha sıkı (düşük) olanı: (değer, a_mi). Karşılaştırma şefin eforundaki Z ile, eşitlikte
    düşük efor. Biri boşsa öteki. Çözülemeyen değer SecimHatasi (sessizce gevşek olana düşülmez)."""
    if not a or not b:
        return (a or b), bool(a)
    ta, tb = sef_coz(a, veri), sef_coz(b, veri)
    return (a, True) if (ta["z"], efor_sira(ta["efor"])) <= (tb["z"], efor_sira(tb["efor"])) else (b, False)


def tavan_ihlal(t, kimlik, rol, efor, m, z=None):
    """Aday (kimlik, efor) şef tavanını aşıyor mu: neden metni ya da None."""
    if not t or not m:
        return None
    if z is None:
        z = ((m.get("varyantlar") or {}).get(efor) or {}).get("z")
    if m.get("saglayici") == t["aile"]:
        if kimlik != t["kimlik"]:
            # aynı ailede başka model: gürültü bandı yok (Sonnet şefle Opus hiçbir eforda yok); şefin eforundaki
            # düzeyi şefinkini aşan model elenir
            zd = _model_duzeyi(m, t["efor"])
            if zd is not None and zd > t["z"]:
                return f"şef tavanı: {rol or kimlik} şef modelinin ({t['rol'] or t['kimlik']}) üstünde (aynı aile)"
        if efor_sira(efor) > efor_sira(t["efor"]):
            return f"şef tavanı: efor {efor} > şef {t['etiket']} (aynı aile)"
        return None
    if z is not None and float(z) > t["z"] + t["bant"]:
        return f"şef tavanı: Z {float(z):g} > şef {t['etiket']} Z {t['z']:g} + bant {t['bant']:g}"
    return None


def _tavan_hazirla(i, veri, durum, simdi):
    """i['_tavan'] (şef verilmişse) ve i['_tavan_kalkti'] (kullanıcının açık aşma isteği) alanlarını doldurur."""
    i["_tavan"] = None
    i.setdefault("_tavan_kalkti", None)
    if not i.get("sef"):
        return
    i["_tavan"] = sef_coz(i["sef"], veri)
    if i["_tavan_kalkti"]:
        return
    kilit = i.get("_tavan_kilit")             # plan/sürü parçası: zorla/ultra lider yazımıdır, kullanıcı isteği değil
    if i.get("tavan_yok"):
        i["_tavan_kalkti"] = TAVAN_KALDIRAN["tavan_yok"]
    elif i.get("zorla") and not kilit:
        i["_tavan_kalkti"] = "--zorla (açık istek)"
    elif i.get("kip") == "ultra" and not kilit:
        i["_tavan_kalkti"] = TAVAN_KALDIRAN["ultra"]
    elif TAVAN_YOK in _sor_kararlari(i, durum, simdi):
        i["_tavan_kalkti"] = TAVAN_KALDIRAN["sor"]


def _tavan_engeli(elenen, onek=None):
    return any(str(v).startswith("şef tavanı") and (onek is None or str(k).startswith(onek))
               for k, v in (elenen or {}).items())


def _sor_tavan(i, veri, dout, uyarilar, elenen, neden, en_iyi=None):
    """SOR T6: işin Q'su (ya da Opus kapısı) şef tavanının üstünde. Daha zayıf modele düşülmez."""
    t = i["_tavan"]
    soru = (f"{neden}; şef {t['etiket']} (Z {t['z']:g}) tavanı altında Q{i['Q']} karşılanmıyor: bu iş için tavanı "
            f"aşayım mı, yoksa bekleyelim/şef modelini yükseltelim mi?")
    sec_ = [{"kod": TAVAN_YOK, "ne": "bu iş için şef tavanını aş (uyarıyla)", "yanit": "--sor-yanit tavan_yok",
             "aday": aday_etiket(en_iyi) if en_iyi else None},
            {"kod": "sef_yukselt", "ne": "lider oturum modelini/eforunu yükseltir ve --sef ile yeniden seçer"},
            {"kod": "bekle", "ne": "çalıştırma (Q düşürülmez)"}]
    return _sor_sonuc(i, veri, dout, uyarilar, elenen, TAVAN_TETIK, soru, sec_)


def _tavansiz_en_iyi(i, veri, durum, simdi, proje, **k):
    a2, _ = adaylari_uret(dict(i, _tavan=None), veri, durum, simdi, proje, **k)
    return max(a2, key=lambda a: (a["z_etkin"], -a["g"], a["id"])) if a2 else None


def _tavan_alan_suz(A, i, veri, olcut, delta, elenen):
    """Başka aile adayı, şefin aynı ölçütteki alan ölçümünü (gürültü bandı δ içinde eşit) aşamaz. Şefin ölçümü yoksa
    yalnız Z tavanı geçerlidir."""
    t = i.get("_tavan")
    if not t or i.get("_tavan_kalkti") or not olcut or olcut == "z":
        return A
    ms = veri.model(t["kimlik"]) or {}
    anahtar = next((an for o, an in olcutler(i.get("alt_alan"), veri.siniflar, ms) if o == olcut), None)
    p_s, _ = olcum_bul(ms, t["efor"], i.get("alt_alan"), olcut, anahtar, s=veri.siniflar)
    if p_s is None:
        return A
    out = []
    for a in A:
        ham = a["q"] + (a["z"] - a["z_etkin"])
        if a["aile"] != t["aile"] and a.get("q_kaynak") == olcut and ham > p_s + delta:
            elenen.setdefault(a["id"], f"şef tavanı (alan {olcut}): {ham:.1f} > şef {t['etiket']} {p_s:.1f} + δ "
                                       f"{delta:g}")
            continue
        out.append(a)
    return out


# ================================================================== aday üretimi (bölüm 3.3 D)
def _kapanis_gun(x, simdi):
    if isinstance(x, dict):
        x = x.get("deger")
    k = zaman_coz(x)
    if not k:
        return None
    return (k - simdi).total_seconds() / 86400


def _soguma_aktif(soguma, anahtarlar, simdi):
    for a in anahtarlar:
        k = (soguma or {}).get(a)
        if isinstance(k, dict):
            b = zaman_coz(k.get("busy_until"))
            if b and b > simdi:
                return a, k
    return None, None


def _s_p(h, a):
    s = h.get("s_p", 1.0)
    if isinstance(s, dict):
        for anahtar in (a["kimlik"], a.get("rol"), a.get("hat")):
            if anahtar in s and isinstance(s[anahtar], (int, float)):
                return float(s[anahtar])
        v = s.get("varsayilan", s.get("*", 1.0))
        return float(v) if isinstance(v, (int, float)) else 1.0
    return float(s or 1.0)


SIKI_VERI = {"saglik", "gizli"}          # host sağlayıcısı ve yerel dışına yalnız kullanıcı onayıyla


def host_aileleri(veri, host):
    """Liderin çalıştığı platformun (host) model aileleri: veri dosyasından türetilir (kodda ad yok)."""
    out = set()
    for pid, p in veri.platformlar.items():
        if not p.get("host"):
            continue
        hk = veri.host(p.get("imza") or pid)
        if hk != host:
            continue
        for e in p.get("erisim", []):
            m = veri.model(e.get("kimlik") or "") or {}
            if m.get("saglayici") and not veri.yasak_mi(e.get("kimlik"), m)[0]:
                out.add(m["saglayici"])
    return out


AGY_KABUL, AGY_RET = "agy_kabul", "agy_ret"       # SOR T4 yanıtları (oturum kapsamı, durum.sor_kararlari)


def oturum_kararlari(durum, simdi=None):
    """durum.sor_kararlari içinde süresi geçmemiş oturum kapsamlı kodlar."""
    simdi = simdi or simdi_utc()
    out = set()
    for k in (durum or {}).get("sor_kararlari") or []:
        if not isinstance(k, dict) or k.get("kapsam") not in (None, "oturum"):
            continue
        b = zaman_coz(k.get("bitis"))
        if b and b <= simdi:
            continue
        out.add(k.get("kod"))
    return out


def agy_kapisi(veri, durum, simdi=None):
    """agy otomatik çağrı kapısı (tasarım 6.2): (açık mı, neden). Açılma: kişisel karar açık + 403 kapanışı yok +
    yalın işçi profili doğrulandı ya da kullanıcı kişisel bağlamı açıkça kabul etti (kişisel kayıt ya da bu oturumdaki
    SOR T4 yanıtı `agy_kabul`). Fail-closed: kapalı kapıda hiçbir otomatik agy çağrısı (koşucu dahil) yapılmaz."""
    ao = veri.agy_otomatik()
    if not ao.get("acik"):
        return False, "agy otomatik kapalı (kişisel karar yok)"
    kap = (durum or {}).get("agy_otomatik_kapali")
    if kap:
        return False, f"agy otomatik kapandı ({(kap or {}).get('neden', '403') if isinstance(kap, dict) else kap})"
    prof = ao.get("isci_profili") or {}
    if not (prof.get("dogrulandi") or prof.get("kisisel_baglam_kabul") is True
            or AGY_KABUL in oturum_kararlari(durum, simdi)):
        return False, "agy otomatik: kişisel bağlam (yalın işçi profili doğrulanmadı, kabul yok)"
    return True, None


def _wilson(ok, n, z=1.64):
    if n <= 0:
        return 0.0, 1.0
    p = ok / n
    d = 1 + z * z / n
    m = (p + z * z / (2 * n)) / d
    w = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, m - w), min(1.0, m + w)


def geri_bildirim_elenen(veri, durum, sinif):
    """durum.basari {kimlik: {sinif: {n, ok}}} (ork olc ozet yazar). En az en_az örnekli modeller arasında en iyinin
    Wilson alt sınırından fark_esigi kadar düşük başarılı model o sınıfta elenir (tasarım 8.5). Dönüş {kimlik: neden}."""
    gb = veri.siniflar.get("geri_bildirim") or {}
    en_az = int(gb.get("en_az_ornek", 20))
    fark = float(gb.get("fark_esigi", 0.05))
    z = float(gb.get("z", 1.64))
    oran = {}
    for kim, d in ((durum or {}).get("basari") or {}).items():
        x = (d or {}).get(sinif) if isinstance(d, dict) else None
        if isinstance(x, dict) and int(x.get("n") or 0) >= en_az:
            oran[kim] = (int(x.get("ok") or 0), int(x["n"]))
    if len(oran) < 2:
        return {}
    en_iyi = max(oran, key=lambda k: _wilson(*oran[k], z)[0])
    alt = _wilson(*oran[en_iyi], z)[0]
    return {k: f"geri bildirim: {sinif} başarısı {ok}/{n} < {en_iyi} alt sınırı {alt:.2f} - {fark:g}"
            for k, (ok, n) in oran.items() if k != en_iyi and ok / n < alt - fark}


def _gorev_usd(m, ef):
    """Görev başı maliyet. Değer yoksa ya da DY işaretliyse ücretsiz sayılmaz: modelin bilinen en yüksek varyant
    maliyeti kullanılır (temkinli); hiç yoksa 0 (yerel/bedava modeller)."""
    var = m.get("varyantlar") or {}
    v = var.get(ef) or {}
    if v.get("gorev_usd") is not None and not v.get("gorev_usd_dy"):
        return float(v["gorev_usd"])
    bilinen = [float(x["gorev_usd"]) for x in var.values() if x.get("gorev_usd") is not None]
    return max(bilinen) if bilinen else 0.0


def _efor_oran(m, ef):
    """Brief kaynaklı token tahmininde çıktı token'ının efor çarpanı: g(efor) / g(medium) (medium yoksa en ucuz bilinen
    varyant); ölçüm yoksa 1. Aynı modelin üst eforu daha çok düşünme token'ı yakar (AA görev maliyeti oranı) [T]."""
    var = m.get("varyantlar") or {}
    g = (var.get(ef) or {}).get("gorev_usd")
    if g is None or (var.get(ef) or {}).get("gorev_usd_dy"):
        return 1.0
    ref = (var.get("medium") or {}).get("gorev_usd")
    if ref is None:
        bilinen = [float(x["gorev_usd"]) for x in var.values() if x.get("gorev_usd")]
        ref = min(bilinen) if bilinen else None
    if not ref:
        return 1.0
    return _clamp(float(g) / float(ref), 0.25, 4.0)


def adaylari_uret(i, veri, durum, simdi, proje=None, gevsek=False, filtre=None, yedek_izinli=False):
    """(adaylar, elenen). gevsek=True: kullanıcı/proje zorunluluğu için yumuşak elemeler (Q, efor kuralı, max,
    sınıf dışı) uygulanmaz; sert elemeler (yasak, gizlilik, kip, katalog, soğuma, bitiş) her zaman uygulanır."""
    s, k = veri.siniflar, veri.kurallar
    ay = ayar(veri)
    hostlar = HOST_YOLLARI.get(i["host"], HOST_YOLLARI["claude-code"])
    siki = i["veri"] in SIKI_VERI and not i.get("dis_onay")
    host_aile = host_aileleri(veri, i["host"]) if siki else set()
    proje = proje or {}
    pyasak = {str(x).lower() for x in proje.get("yasak", [])}
    pyasak_havuz = set(proje.get("yasak_havuz", []))
    soguma = (durum or {}).get("soguma") or {}
    agy_acik, agy_neden = agy_kapisi(veri, durum, simdi)
    gb_elenen = geri_bildirim_elenen(veri, durum, i.get("sinif"))
    yalniz_havuz = set(i.get("yalniz_havuz") or [])
    tahmin_yasak = {s["q"][x] for x in ay["tahmin_yasak_siniflar"] if x in s["q"]}
    tahmin_esik = min(tahmin_yasak) if tahmin_yasak else 10 ** 6
    adaylar, elenen = [], {}

    def ele(ad, neden):
        elenen.setdefault(ad, neden)

    for pid, p in sorted(veri.platformlar.items()):
        if p.get("durum", "aktif") != "aktif":
            continue
        for e in p.get("erisim", []):
            yol = e.get("yol") or p.get("yol")
            agy_yolu = yol in AGY_YOLLARI
            if agy_yolu:                    # agy erişimi: kapı açıksa otomatik (agy-oto), değilse elle köprü
                yol = "agy-oto" if agy_acik else "agy-elle"
            if e.get("rol"):
                rol = e["rol"]
                kimlik = (veri.roller.get(rol) or {}).get("aktif")
            elif e.get("hat"):
                sag, hat = e["hat"].split("/", 1)
                rol = veri.hat_rol(sag, hat)
                kimlik = (veri.roller.get(rol) or {}).get("aktif") if rol else None
            else:
                kimlik = e.get("kimlik")
                rol = veri.model_rol(kimlik) if kimlik else None
            if not kimlik:
                continue
            m = veri.model(kimlik)
            ad0 = f"{rol or kimlik}|{pid}"
            if filtre and not filtre(kimlik, rol, None):
                continue
            if e.get("durum") == "kapsam_disi":
                ele(ad0, "erişim kapsam dışı")
                continue
            if yalniz_havuz and e.get("havuz") not in yalniz_havuz:
                continue
            if agy_yolu and not agy_acik and agy_neden and "kişisel bağlam" in agy_neden:
                ele(f"agy-oto|{pid}", agy_neden)
            if kimlik in gb_elenen and not i.get("suru"):
                ele(ad0, gb_elenen[kimlik])
                continue
            if e.get("tekil_secim") is False and not i.get("suru"):
                ele(ad0, "yalnız sürü içinde (tekil_secim=false)")
                continue
            if yol not in hostlar:
                ele(ad0, f"host {i['host']} bu yola erişemez ({yol})")
                continue
            if m is None:
                ele(ad0, "kayıt yok (güncelle)")
                continue
            if e.get("kimlikler") is not None and kimlik not in e["kimlikler"]:
                ele(ad0, f"katalogda yok: {kimlik} (sessizce başka modele düşülmez)")
                continue
            yz, yg = veri.yasak_mi(kimlik, m)
            if yz:
                ele(ad0, yg)
                continue
            if not i.get("once_sor_izni"):
                oz, og = veri.once_sor_mi(kimlik, m)
                if oz:
                    ele(ad0, og)
                    continue
            if str(rol or "").lower() in pyasak or kimlik.lower() in pyasak:
                ele(ad0, "proje yasağı")
                continue
            dur = m.get("durum", "aktif")
            if dur == "onay_bekliyor":
                ele(ad0, "onay_bekliyor (yeni hat)")
                continue
            if dur in ("emekli", "eski_nesil", "gozlem"):
                ele(ad0, f"durum {dur}")
                continue
            if dur == "yedek" and not yedek_izinli:
                ele(ad0, "yedek (aktif rol erişilebilirken seçilmez)")
                continue
            kgs = [x for x in (_kapanis_gun(m.get("kapanis"), simdi), _kapanis_gun(e.get("kapanis"), simdi))
                   if x is not None]
            kg = min(kgs) if kgs else None
            if kg is not None and kg <= ay["kapanis_yasak_gun"]:
                ele(ad0, f"kapanış ≤{ay['kapanis_yasak_gun']} gün" if kg > 0 else "emekli (kapanış geçti)")
                continue
            if (m.get("gorev") or "chat") != "chat" and i.get("tur") != "arac":
                ele(ad0, f"araç modeli ({m.get('gorev')})")
                continue
            girdi = set((m.get("kipler") or {}).get("girdi") or ["metin"])
            eksik = [x for x in i["kipler"] if x not in girdi]
            if eksik:
                ele(ad0, f"kip eksik: {','.join(eksik)}")
                continue
            hid = e.get("havuz")
            if not hid:
                ele(ad0, "havuz doğrulanmadı")
                continue
            h = veri.havuz(hid)
            gz = h.get("gizlilik") or p.get("gizlilik") or "ozel"
            if gz == "kamu" and i["veri"] != "genel":
                ele(ad0, f"gizlilik: {hid} kamu havuzu, veri={i['veri']}")
                continue
            if gz == "kamu" and i.get("kamu_yasak"):
                ele(ad0, f"rol {i.get('rol_is') or 'hakem'} kamu havuzdan seçilmez")
                continue
            if gz == "dis" and i["veri"] in HASSAS_VERI:
                ele(ad0, f"gizlilik: {hid} dış havuz, veri={i['veri']}")
                continue
            p_host = veri.host(p.get("imza") or pid) if p.get("host") else None
            if siki and not _yerel_mi(h, p) and not (p_host == i["host"] and m.get("saglayici") in host_aile):
                ele(ad0, f"gizlilik: veri={i['veri']} host dışı sağlayıcıya ({m.get('saglayici')}) yalnız "
                         f"kullanıcı onayıyla (--dis-onay)")
                continue
            if hid in pyasak_havuz or (h.get("bedava") and "bedava" in pyasak_havuz):
                ele(ad0, "proje yasak_havuz")
                continue
            bitis = zaman_coz(h.get("bitis") or p.get("bitis"))
            if bitis and bitis <= simdi:
                ele(ad0, f"havuz kapandı ({h.get('bitis') or p.get('bitis')})")
                continue
            sk, _ = _soguma_aktif(soguma, (hid, kimlik, f"{hid}:{kimlik}"), simdi)
            if sk:
                ele(ad0, f"soğumada ({sk})")
                continue
            if i.get("baglam_gerek") and (m.get("baglam") or 0) < i["baglam_gerek"]:
                ele(ad0, "bağlam yetersiz")
                continue
            # Yetenek süzgeci: alt alan bir araç yeteneği istiyorsa (ör. web: canlı web araması) o yeteneği
            # KANITLA taşımayan erişim yolu aday olmaz. Bilinmeyen (kayıt yok) elenmez; yalnız açık `false` eler.
            gy = olcut_tanimi(i.get("alt_alan"), s).get("gerekli_yetenek") or []
            if gy and not gevsek:
                yet = dict(p.get("yetenekler") or {})
                yet.update(e.get("yetenekler") or {})
                yok = [y for y in gy if yet.get(y) is False]
                if yok:
                    ele(ad0, f"yetenek yok: {','.join(yok)} ({pid} bu yolda sunmuyor)")
                    continue
            bay = m.get("erisim_bayraklari") or {}
            if i.get("duzenleme") and bay.get("yazma_izinli_ajan") is False:
                ele(ad0, "yazma izinli ajan değil")
                continue
            if i.get("olgu") and bay.get("olgu_isi") is False:
                ele(ad0, "olgu işinde kullanılmaz")
                continue
            if i.get("haric_aile") and m.get("saglayici") == i["haric_aile"]:
                ele(ad0, "doğrulayıcı farklı aileden olmalı")
                continue
            if i.get("haric_kimlik") and kimlik == i["haric_kimlik"]:
                ele(ad0, "doğrulayıcı üretenle aynı model olamaz")
                continue
            ek = efor_kurali(s, i.get("alt_alan"), rol)
            if ek.get("kullanma") and not gevsek:
                ele(ad0, f"efor kuralı: {i.get('alt_alan')} işinde kullanılmaz")
                continue
            eforlar = e.get("eforlar")
            if eforlar is None:
                eforlar = list((m.get("varyantlar") or {}).keys())
            if e.get("z_duzeltme") is not None:
                duz = float(e["z_duzeltme"])
            else:
                duz = -float(ay["esdeger_yaklasik_z_indirimi"]) if e.get("esdeger") == "yaklasik" else 0.0
            elle = yol in ("elle", "agy-elle") or (bool(e.get("elle")) and not agy_yolu)
            for ef in eforlar:
                ad = f"{rol or kimlik}@{ef}|{pid}"
                if filtre and not filtre(kimlik, rol, ef):
                    continue
                v = (m.get("varyantlar") or {}).get(ef)
                if not v or v.get("z") is None:
                    ele(ad, "bu eforda Z yok")
                    continue
                z = float(v["z"])
                tahmin = v.get("z_kaynak") == "tahmin"
                indirim = float(ay["tahmin_z_indirimi"]) if tahmin else \
                    (float(ay["halef_z_indirimi"]) if v.get("z_kaynak") == HALEF_Z else 0.0)
                z_et = z - indirim + duz
                a = {"kimlik": kimlik, "rol": rol, "efor": ef, "yol": yol, "platform": pid, "havuz": hid,
                     "efor_bayragi": bool(e.get("efor_bayragi")), "fiyat": m.get("fiyat") or {},
                     "aile": m.get("saglayici"), "hat": m.get("hat"), "z": z, "z_etkin": z_et,
                     "z_kaynak": v.get("z_kaynak"), "g": _gorev_usd(m, ef), "g_oran": _efor_oran(m, ef),
                     "dk": float(v.get("dk") or 0.0), "elle": bool(elle), "kapanis_gun": kg,
                     "sablon": e.get("kimlik_sablon"), "takma": e.get("takma"), "id": ad, "yedek": dur == "yedek"}
                tn = tavan_ihlal(i.get("_tavan"), kimlik, rol, ef, m, z)
                if tn:
                    if not i.get("_tavan_kalkti"):
                        ele(ad, tn)
                        continue
                    a["tavan_asim"] = tn
                if not gevsek:
                    if tahmin and i["Q"] >= tahmin_esik:
                        ele(ad, "z_kaynak=tahmin, zor/kritikte kullanılmaz")
                        continue
                    if z_et < i["Q"]:
                        ele(ad, f"Z<Q ({z_et:g}<{i['Q']})")
                        continue
                    tavan = None if i["kip"] == "ultra" else ek.get("tavan")
                    if not efor_arasi(ef, ek.get("taban"), tavan):
                        ele(ad, f"efor kuralı dışı ({ek.get('taban')}..{tavan})")
                        continue
                    if ef in KIP_EFORLARI and i["kip"] != "ultra":
                        a["kip_eforu"] = True
                adaylar.append(a)
    if not gevsek:
        # max/ultra yalnız kritikte ve başka aday kalmamışsa
        normal = [a for a in adaylar if not a.get("kip_eforu")]
        if normal or not i["kritik"]:
            for a in adaylar:
                if a.get("kip_eforu"):
                    ele(a["id"], "max/ultra varsayılan değil (yalnız kritikte tek aday ya da --zorla)")
            adaylar = normal
    return adaylar, elenen


# ================================================================== kalite (bölüm 3.3 E)
def olcut_tanimi(alt, siniflar):
    return ((siniflar.get("alan_olcutleri") or {}).get(alt) or {}) if alt else {}


def _alan_kayitlari(m, alt):
    x = (m.get("alanlar") or {}).get(alt) if alt else None
    if x is None:
        return []
    return [o for o in (x if isinstance(x, list) else [x]) if isinstance(o, dict) and o.get("olcut")]


def efor_egimi(olcut, s):
    """1 Z puanının bu ölçütün biriminde karşılığı (siniflar.efor_kaydirma.egim: tam ölçüt adı > önek > _varsayilan).
    Z ile ölçüt aynı birimde değildir: Elo ölçütünde 1 Z ≈ 7 Elo, yüzde ölçütlerinde ≈ 1.3 puan (kalibrasyon notu
    veri dosyasında). Ayar yoksa 1.0 (eski davranış: ham Z farkı)."""
    eg = ((s or {}).get("efor_kaydirma") or {}).get("egim") or {}
    on = str(olcut or "").split(":", 1)[0]
    x = eg.get(olcut, eg.get(on, eg.get("_varsayilan", 1.0)))
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else 1.0


def _bos_efor_ust(olcut, s):
    """Efor bildirmeyen kayıt en üst eforda mı ölçülmüş sayılsın: yalnız uygulaması DOĞRULANMIŞ ölçütlerde
    (siniflar.efor_kaydirma.bos_efor_ust: tam ölçüt adı ya da önek). Doğrulanmamış kaynakta puan tüm eforlara aynen."""
    L = ((s or {}).get("efor_kaydirma") or {}).get("bos_efor_ust") or []
    olcut = str(olcut or "")
    return olcut in L or olcut.split(":", 1)[0] in L


def _efor_kaydir(p0, z0, z1, o, s):
    """Ölçülen efordan (z0) istenen efora (z1) kaydırma. Aşağı yön tam uygulanır (temkinli); yukarı yön, yani ölçülmemiş
    daha yüksek efor, ölçütün gürültü bandının `yukari_tavan_delta` katıyla sınırlanır: ölçüm olmadan üstünlük yok."""
    dz = float(z1) - float(z0)
    ek = (s or {}).get("efor_kaydirma") or {}
    if not ek:
        return p0 + dz
    kay = dz * efor_egimi(o.get("olcut"), s)
    if kay > 0:
        kay = min(kay, float(ek.get("yukari_tavan_delta", 1.0)) * delta_hesapla(None, str(o.get("olcut") or "z"), s, o))
    return p0 + kay


def olcum_puani(o, m, efor, kaydir=True, s=None):
    """Model düzeyi ölçüm -> istenen efordaki puan.
    1) `eforlar` sözlüğünde o efor ölçülmüşse aynen o değer (efor başına ölçüm her şeyin önündedir).
    2) `eforlar` var ama o efor yoksa: Z bakımından en yakın ÖLÇÜLÜ efor çapa alınır ve kaydırılır.
    3) Tek ölçüm + `efor` (ölçümün yapıldığı efor) doluysa diğer eforlara Z farkı × ölçüt eğimi kadar kaydırılır.
    4) `efor` boşsa (kaynak eforu bildirmiyor) puan tüm eforlara aynen uygulanır.
    Doymuş ölçütte kaydırma yok (kaydir=False): eşik üstü zekâ farkı o ölçütte puan farkı üretmez."""
    v = m.get("varyantlar") or {}

    def z(e):
        return (v.get(e) or {}).get("z")

    ef = o.get("eforlar")
    if isinstance(ef, dict):
        if ef.get(efor) is not None:
            return float(ef[efor])
        olc = [(e, float(p)) for e, p in ef.items() if isinstance(p, (int, float)) and z(e) is not None]
        if olc and kaydir and z(efor) is not None:
            e0, p0 = min(olc, key=lambda t_: (abs(float(z(t_[0])) - float(z(efor))), t_[0]))
            return _efor_kaydir(p0, z(e0), z(efor), o, s)
        if olc and o.get("puan") is None:
            return max(p for _, p in olc) if not kaydir else None
    if o.get("puan") is None:
        return None
    e0 = o.get("efor")
    if not e0 and kaydir and _bos_efor_ust(o.get("olcut"), s):
        # kaynak eforu bildirmiyor: sıralama tabloları modeli en üst ayarında ölçer (Vals, AA, Arena'da doğrulandı);
        # çapa = modelin Z'si en yüksek ölçülü eforu. Böylece düşük efor, üst eforun puanını bedavaya taşımaz.
        ust = [(float(x["z"]), efor_sira(e)) for e, x in v.items()
               if isinstance(x, dict) and isinstance(x.get("z"), (int, float)) and e not in ("ultra", "varsayilan")]
        if ust:
            zt = max(ust)[0]
            e0 = min((e for e, x in v.items() if isinstance(x, dict) and x.get("z") == zt
                      and e not in ("ultra", "varsayilan")), key=efor_sira)
    if not e0 or e0 == efor or not kaydir:
        return float(o["puan"])
    z0, z1 = z(e0), z(efor)
    if z0 is None or z1 is None:
        return float(o["puan"])
    return _efor_kaydir(float(o["puan"]), z0, z1, o, s)


def olcum_bul(m, efor, alt, olcut, anahtar=None, kaydir=True, s=None):
    """(puan, örnek kayıt) ya da (None, None). Kaynak sırası: varyant alt testi (anahtar) > model alanlar[alt]
    (aynı ölçüt) > 'aa:<anahtar>' biçiminden varyant alt testi."""
    if not olcut:
        return None, None
    v = (m.get("varyantlar") or {}).get(efor) or {}
    if anahtar and isinstance(v.get("alt"), dict) and v["alt"].get(anahtar) is not None:
        return float(v["alt"][anahtar]), {"olcut": olcut}
    # önce bu alt alanın kaydı, sonra aynı ölçütü taşıyan herhangi bir alt alan kaydı (ölçüt adı tek kaynak:
    # ör. uzun_turkce ve yaratici aynı arena:creative ölçümünü kullanır)
    sirali = _alan_kayitlari(m, alt) + [o for a2 in sorted(m.get("alanlar") or {}) if a2 != alt
                                         for o in _alan_kayitlari(m, a2)]
    for o in sirali:
        if o.get("olcut") == olcut:
            p = olcum_puani(o, m, efor, kaydir, s)
            if p is not None:
                return p, o
    on, _, ad = olcut.partition(":")
    if on == "aa" and isinstance(v.get("alt"), dict) and v["alt"].get(ad) is not None:
        return float(v["alt"][ad]), {"olcut": olcut}
    return None, None


def olcutler(alt, siniflar, m=None):
    """[(olcut, anahtar)] birincil önce. Tanım yoksa modelin alanlar[alt] kaydındaki ölçüt."""
    t = olcut_tanimi(alt, siniflar)
    out = []
    b = t.get("birincil")
    if b and b != "arac":
        out.append((b, t.get("anahtar") if t.get("kapsam") == "varyant" else None))
    ik = t.get("ikincil")
    for x in (ik if isinstance(ik, list) else [ik] if ik else []):
        out.append((x, None))
    if not t and m is not None:
        out += [(o["olcut"], None) for o in _alan_kayitlari(m, alt)]
    return out


def delta_hesapla(alt, olcut, siniflar, ornek=None):
    d = siniflar.get("delta") or {}
    t = olcut_tanimi(alt, siniflar)
    anahtar = t.get("delta")
    if ornek and ornek.get("doymus"):
        anahtar = "doymus_yayilim"
    if olcut == "z":
        anahtar = "aa_z"
    if not anahtar:
        on = olcut.split(":", 1)[0]
        anahtar = {"aa": "aa_alt_test"}.get(on, on)
    if anahtar == "arena":
        ci = (ornek or {}).get("ci")
        if isinstance(ci, list) and len(ci) == 2 and all(isinstance(x, (int, float)) for x in ci):
            return abs(float(ci[1]) - float(ci[0]))
        return float(d.get("arena_ci_yoksa", 14))
    x = d.get(anahtar)
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        return float(x)
    return float(d.get("diger", d.get("aa_z", 2)))


def kalite_hesapla(adaylar, alt, veri):
    """Her adaya q yazar. Dönüş: (olcut, delta, alan_olcumu_eksik).
    Birincil ölçütü olmayan aday için köprü (tasarım 3.2.1): siniflar.kopru[alt] listesindeki ilk ölçüt F hem adayda
    hem birincil ölçülü bir referansta varsa q = min(q*, medyan_r[q_r + δ_P (F_a - F_r) / δ_F] - 0.5 δ_P). Köprülü aday
    q* belirleyemez, Opus kapısında sayılmaz; köprü bulunamazsa eski kural (ölçülen varken E'ye girmez). Z köprü değildir."""
    s = veri.siniflar
    for a in adaylar:              # ikinci hesapta önceki turun bayrakları ve referans tabanı taşınmaz
        for k in ("kopru", "kopru_ref", "olcumsuz", "kanit_z", "q_ham"):
            a.pop(k, None)
    carpan = float((s.get("delta") or {}).get("alan_olcumu_yok_carpani", 1.5))
    t = olcut_tanimi(alt, s)
    ilk_m = veri.model(adaylar[0]["kimlik"]) if adaylar else None
    liste = olcutler(alt, s, ilk_m)
    if not liste:
        for a in adaylar:
            a["q"], a["q_kaynak"] = a["z_etkin"], "z"
        acik_z = t.get("kapsam") == "z"
        d = delta_hesapla(alt, "z", s) * (1.0 if (acik_z or not alt) else carpan)
        return "z", d, bool(alt) and not acik_z
    olcut, anahtar = liste[0]
    var, ornek = {}, None
    kaydir = t.get("delta") != "doymus_yayilim"
    for a in adaylar:
        p, o = olcum_bul(veri.model(a["kimlik"]) or {}, a["efor"], alt, olcut, anahtar, kaydir, s)
        if p is not None:
            var[a["id"]] = p
            ornek = ornek or o
    if not var:
        for a in adaylar:
            a["q"], a["q_kaynak"] = a["z_etkin"], "alan_olcumu_yok"
        return "z", delta_hesapla(alt, "z", s) * carpan, True
    d0 = delta_hesapla(alt, olcut, s, ornek)
    for a in adaylar:
        if a["id"] in var:
            a["q"], a["q_kaynak"] = var[a["id"]] - (a["z"] - a["z_etkin"]), olcut
    olculen = [a for a in adaylar if a["id"] in var]
    q_tepe0 = max(a["q"] for a in olculen)
    kopru = s.get("kopru") or {}
    kl = kopru.get(alt) if alt in kopru else kopru.get("_varsayilan") or []
    for a in adaylar:
        if a["id"] in var:
            continue
        ma = veri.model(a["kimlik"]) or {}
        for F in kl or []:
            if F == "z":
                continue
            Fa, _ = olcum_bul(ma, a["efor"], alt, F, F.split(":", 1)[-1] if F.startswith("aa:") else None, s=s)
            if Fa is None:
                continue
            refs = {}
            for r in olculen:
                Fr, _ = olcum_bul(veri.model(r["kimlik"]) or {}, r["efor"], alt, F,
                                  F.split(":", 1)[-1] if F.startswith("aa:") else None, s=s)
                if Fr is None:
                    continue
                if r["kimlik"] not in refs or r["q"] > refs[r["kimlik"]][0]:
                    refs[r["kimlik"]] = (r["q"], Fr)
            if not refs:
                continue
            dF = delta_hesapla(None, F, s) or 1.0
            tah = sorted(qr + d0 * (Fa - Fr) / dF for qr, Fr in refs.values())
            n = len(tah)
            med = tah[n // 2] if n % 2 else (tah[n // 2 - 1] + tah[n // 2]) / 2
            a["q"] = min(q_tepe0, med - 0.5 * d0) - (a["z"] - a["z_etkin"])
            a["q_kaynak"], a["kopru"], a["kopru_ref"] = f"kopru:{F}", True, len(refs)
            break
    eksik = [a for a in adaylar if a["id"] not in var and not a.get("kopru")]
    d = d0 * (carpan if eksik else 1.0)
    # Ölçümsüz aday ölçülenlerin ortalamasına yerleştirilmez (Elo ile Z karıştırılmaz): en düşük ölçülen q'nun δ
    # altına konur ve `olcumsuz` işaretlenir; ölçülü aday varken kalite kümesine girmez.
    q_min = min(a["q"] for a in olculen)
    for a in eksik:
        a["q"], a["q_kaynak"], a["olcumsuz"] = q_min - d, "alan_olcumu_yok", True
    return olcut, d, bool(eksik)


def doygunluk(adaylar, i, veri):
    """Mekanik/basit sınıfta eşik üstü zekâ ölçülebilir kazanç sayılmaz (tasarım 3.2.2): q = min(q, Q + pay)."""
    pay = (veri.siniflar.get("doygunluk") or {}).get(i.get("sinif"))
    if pay is None:
        return False
    tavan = float(i["Q"]) + float(pay)
    for a in adaylar:
        a.setdefault("q_ham", a["q"])
        a["q"] = min(a["q"], tavan)
    return True


def kanit_birikimi(E, alt, veri):
    """Birleşik kanıt (tasarım 3.2.3): E içinde bir aile F, en az iki bağımsız ölçütte (hem F hem en iyi rakip ölçülü)
    her birinde geride değilse (d_i >= 0) ve z_F = Σ(d_i/δ_i)/√n >= kanit_birikimi_z ise E F'ye daralır. Küçük farkların
    birikmesi tek başına daraltmaz (0.4δ + 0.4δ -> z 0.57). Köprülü adayın birincil değeri q'sudur."""
    ay = ayar(veri)
    gerek = int(ay["kanit_birikimi_olcut"])
    esik = float(ay.get("kanit_birikimi_z", 1.0))
    s = veri.siniflar
    en, delta = {}, {}
    kaydir = olcut_tanimi(alt, s).get("delta") != "doymus_yayilim"
    for a in E:
        m = veri.model(a["kimlik"]) or {}
        for n_, (olcut, anahtar) in enumerate(olcutler(alt, s, m)):
            p, o = olcum_bul(m, a["efor"], alt, olcut, anahtar, kaydir if n_ == 0 else True, s)
            if p is None and n_ == 0 and a.get("kopru"):
                p = a["q"] + (a["z"] - a["z_etkin"])
            if p is None:
                continue
            test = olcut.split(":", 1)[-1]          # aynı test farklı değerlendiriciden = tek kanıt
            d = en.setdefault(test, {})
            d[a["aile"]] = max(d.get(a["aile"], -1e18), p)
            # birincil ölçütte alt alanın δ'sı, ikincilde ölçütün kendi değerlendiricisinin δ'sı
            delta.setdefault(test, delta_hesapla(alt if n_ == 0 else None, olcut, s, o) or 1.0)
    aileler = {a["aile"] for a in E}
    en_iyi, en_z = None, 0.0
    for F in sorted(aileler):
        oranlar, geride = [], False
        for test, d in en.items():
            if F not in d or len(d) < 2:
                continue
            rakip = max(v for f, v in d.items() if f != F)
            fark = d[F] - rakip
            if fark < 0:
                geride = True
                break
            oranlar.append(fark / delta[test])
        if geride or len(oranlar) < gerek:
            continue
        z = sum(oranlar) / math.sqrt(len(oranlar))
        if z >= esik and z > en_z:
            en_iyi, en_z = F, z
    if en_iyi:
        E_ = [a for a in E if a["aile"] == en_iyi]
        for a in E_:
            a["kanit_z"] = round(en_z, 3)
    return en_iyi


# ================================================================== kapasite (bölüm 3.3 F, 3.5, 3.6)
def pencereler(hid, h, veri, kota, durum, simdi, dout):
    """Havuzun pencere görünümü: {w: {k (kova+EMA), belirsiz, t_dk, T_dk, taban, m, sifirlama}} ya da None (kapalı)."""
    ay = ayar(veri)
    kh = ((kota or {}).get("havuzlar") or {}).get(hid)
    if kh and kh.get("durum") == "kapali":
        return None
    tanim = {p["ad"]: p for p in h.get("pencereler", []) if isinstance(p, dict) and p.get("ad")}
    okunan = (kh or {}).get("pencereler") or {}
    adlar = list(tanim) or list(okunan) or ["hafta"]
    ok = bool(kh) and kh.get("durum", "ok") == "ok"
    out = {}
    ts = simdi.timestamp()
    adim = float(ay["kova_adim"]) or 0.05
    alfa = float(ay["ema_alfa"])
    ema_sn = float(ay["ema_pencere_dk"]) * 60
    for w in adlar:
        T = float(tanim.get(w, {}).get("uzunluk_dk") or PENCERE_DK.get(w) or 0) or None
        o = okunan.get(w) if ok else None
        taban = veri.taban(hid, w)
        if o and o.get("kalan") is not None:
            k_ham = _clamp(float(o["kalan"]), 0.0, 1.0)
            onceki = (((durum or {}).get("kota_ema") or {}).get(hid) or {}).get(w)
            if onceki and 0 <= ts - float(onceki.get("zaman", 0)) <= ema_sn:
                k_e = alfa * k_ham + (1 - alfa) * float(onceki.get("k", k_ham))
            else:
                k_e = k_ham
            dout.setdefault("kota_ema", {}).setdefault(hid, {})[w] = {"k": round(k_e, 6), "zaman": ts}
            k = math.floor(k_e / adim + 1e-9) * adim          # kova: yalnız tercih/katman (ρ, f, S) için
            k_sig = min(k_ham, k_e)        # sığma/taban: okunan ile EMA'nın küçüğü (hızlı düşüşte EMA tabanı delmesin)
            sif = zaman_coz(o.get("sifirlama"))
            belirsiz = False
        else:
            k_e = k = k_sig = float(ay["bilinmiyor"]["k"])
            sif, belirsiz = None, True
        t = max((sif - simdi).total_seconds() / 60.0, 0.0) if sif else ((T / 2.0) if T else None)
        # sığma, taban ve lider payı denetimi temkinli ham değerle (kova ve EMA yalnız tercih için)
        out[w] = {"k": round(k, 6), "k_ham": round(k_sig, 6), "k_ema": round(k_e, 6), "belirsiz": belirsiz,
                  "t_dk": t, "T_dk": T, "taban": taban, "m": max(0.0, k - taban), "m_ham": max(0.0, k_sig - taban),
                  "sifirlama": sif}
    return out


def _azalma(x, ana, faz, rz):
    """Rezervin zamanla azalan çarpanı a(t) (tasarım 8.1): ana havuzda sıfırlamaya rezerv_azalma_saat'ten az kalınca
    doğrusal olarak 0'a; Claude dışı `azalan` rezervde a = t/T (sıfırlamada 0, biriktirme yok)."""
    t, T = x.get("t_dk"), x.get("T_dk")
    if t is None or not T or x.get("sifirlama") is None:
        return 1.0
    if ana:
        saat = float(faz.get("rezerv_azalma_saat") or 0)
        return 1.0 if saat <= 0 else _clamp((t / 60.0) / saat, 0.0, 1.0)
    if rz and rz.get("azalan"):
        return _clamp(t / T, 0.0, 1.0)
    return 1.0


def _rezerv_miktar(rz, taban, ana_u=None, a_t=1.0):
    """Rezerv payı R = r · U · a(t). Ana havuzda tek kaynak faz.claude_esik_u (taban üstü payın oranı); rezerv
    kaydının `deger` alanı ana havuzda yok sayılır (iki parametre ayrışıp sessizce yanlış çalışmasın)."""
    if ana_u is not None:
        return float(ana_u) * (1.0 - taban) * a_t
    if not rz:
        return 0.0
    if rz.get("tur") == "mutlak":
        return float(rz.get("deger", 0)) * a_t
    return float(rz.get("deger", 0)) * (1.0 - taban) * a_t


def _rezerv_acik(rz, i, a, ust):
    if i.get("rezerv_izni") and a["havuz"] in i["rezerv_izni"]:
        return True                      # SOR yanıtı: kullanıcı bu iş için rezervi açtı
    if not rz:
        return False
    kime = set(rz.get("kime") or [])
    if i["alan"] in kime:
        return True
    if "kritik" in kime and i["kritik"]:
        return True
    if ust and ust == a["aile"] and any(x == "ustun" or x.endswith("_ustun") for x in kime):
        return True
    return False


def _x(x, tmin):
    """Tempo payda çarpanı: sıfırlamaya kalan oran; kullanılmamış kayan pencerede (sıfırlama yok) 1."""
    if x.get("t_dk") is not None and x.get("T_dk") and x.get("sifirlama") is not None:
        return max(x["t_dk"] / x["T_dk"], tmin)
    return 0.5 if x.get("belirsiz") else 1.0


def _onde(durum, hid, o_rho, rho_C, b, dout):
    """Göreli tempo ölü bandı (tasarım 8.2): önceki ÖNDE ise o·ρ >= (1 - b)·ρ_C ile kalır, değilse (1 + b)·ρ_C ile
    girer. Eski `tercihli` durumu okunur (göç)."""
    d = durum or {}
    eski = (d.get("onde") or {}).get(hid)
    if eski is None:
        eski = (d.get("tercihli") or {}).get(hid)
    yeni = o_rho >= ((1 - b) if eski else (1 + b)) * rho_C
    dout.setdefault("onde", {})[hid] = bool(yeni)
    return bool(yeni)


def rho_claude(veri, kota, durum, simdi):
    """Ana havuzun tempo oranı ρ_C (tasarım 8.2): haftalık (azalan rezerv düşülmüş) ve 5 saatlik (taban + lider
    tamponu düşülmüş) oranlar; 5s sıkışınca küçüğü. Okunamıyorsa 1 (nötr) ve belirsiz."""
    ay = ayar(veri)
    faz = veri.faz()
    tmin = float(ay["tempo_t_min"])
    for hid in sorted(veri.ana_havuzlar()):
        h = veri.havuz(hid)
        if not h:
            continue
        pens = pencereler(hid, h, veri, kota, durum, simdi, {})
        if not pens or any(x["belirsiz"] for x in pens.values()):
            return {"rho": 1.0, "belirsiz": True}
        out = {"belirsiz": False}
        if "hafta" in pens:
            x = pens["hafta"]
            U = 1.0 - x["taban"]
            R = _rezerv_miktar(None, x["taban"], float(faz["claude_esik_u"]), _azalma(x, True, faz, None))
            out["rho_h"] = 0.0 if (x["m"] <= R or U - R <= 0) else (x["m"] - R) / ((U - R) * _x(x, tmin))
        if "5s" in pens:
            x = pens["5s"]
            lt = float(faz["lider_tampon_5s"])
            payda = (1.0 - x["taban"] - lt) * _x(x, tmin)
            out["rho_5s"] = max(0.0, (x["k"] - x["taban"] - lt)) / payda if payda > 0 else 0.0
        rh = out.get("rho_h", out.get("rho_5s", 1.0))
        r5 = out.get("rho_5s")
        out["rho"] = rh if (r5 is None or r5 >= 1.0) else min(rh, r5)
        return out
    return {"rho": 1.0, "belirsiz": True}


def _yerel_mi(h, p):
    return h.get("tur") == "yerel" or p.get("ucret") == "yerel" or (
        not h.get("pencereler") and h.get("K_p") is None and bool(h.get("bedava")))


def _sabit_yuk(h, a, i):
    """Çağrı başı sabit yük (USD-e): havuzun cagri_sabit_yuk_token × modelin girdi fiyatı (tasarım 8.4); toplu
    planda aynı çağrıyı paylaşan öğe sayısına bölünür."""
    y = h.get("cagri_sabit_yuk_token")
    if isinstance(y, dict):
        y = y.get("deger", y.get("varsayilan"))
    fiyat = (a.get("fiyat") or {}).get("girdi")
    if not y or fiyat is None:
        return 0.0
    n = float(i.get("n_cagri") or 1)
    pay = float(i.get("sabit_yuk_paylasim") or 1)
    return float(y) * float(fiyat) / 1e6 * n / max(pay, 1.0)


def kapasite(a, i, veri, kota, durum, simdi, ust, dout, rho_C=None):
    """Adayın havuzunda işi değerlendirir. Dönüş: uygun, katman (seviye), S, pay, paylar, c, rho, neden, engel_saat.
    Seviye (v7.2): 0 bedava/yerel · 1 Claude dışı ÖNDE · 2 Claude dışı GERİDE · 3 ana havuz · 4 kotası okunamayan
    havuz (dış önce, ana sonra) · 5 Claude dışı kendi rezervinden · 6 (SOR) ana havuz rezervine giren eşit kalite işi."""
    ay = ayar(veri)
    hid = a["havuz"]
    h = veri.havuz(hid)
    p = veri.platformlar.get(a["platform"], {})
    faz = veri.faz()
    bedava = bool(h.get("bedava")) or p.get("ucret") == "bedava"
    ana = hid in veri.ana_havuzlar()
    if _yerel_mi(h, p):
        return {"uygun": True, "katman": 0, "S": 0.0, "pay": 0.0, "paylar": {}, "c": 0.0, "belirsiz": False}
    pens = pencereler(hid, h, veri, kota, durum, simdi, dout)
    if pens is None:
        return {"uygun": False, "neden": "havuz kapalı (kota okuyucu)"}
    belirsiz = any(x["belirsiz"] for x in pens.values())
    if bedava and belirsiz:
        # bedava havuz okunamıyorsa (anahtar yok, ağ yok) katman 0'da seçilmez: çağrı kesin başarısız olur
        return {"uygun": False, "neden": "bedava havuz okunamadı (anahtar/ağ); seçilmez"}
    carp = float(ay["bilinmiyor"]["maliyet_carpani"]) if belirsiz else 1.0
    gc = h.get("gorsel_tur_carpani") if i["alan"] == "gorsel_uretim" else None
    gc = (sum(gc) / len(gc) if isinstance(gc, list) and gc else float(gc or 1.0))
    c_sabit = _sabit_yuk(h, a, i)
    tok = i.get("tok_tahmin")
    if tok and i.get("tok_kaynak") == "brief":
        tok = (tok[0], tok[1] * float(a.get("g_oran") or 1.0))      # efor: düşünme token'ı (bkz. _efor_oran)
    if tok and (a.get("fiyat") or {}).get("girdi") is not None:
        f_ = a["fiyat"]
        c_usd = (tok[0] * float(f_.get("girdi") or 0) + tok[1] * float(f_.get("cikti") or 0)) / 1e6 * _s_p(h, a) \
            * carp + c_sabit
    else:
        c_usd = i["ib"] * a["g"] * _s_p(h, a) * carp * gc + c_sabit
    c_tok = (float(tok[0] + tok[1]) if tok else i["ib"] * float(ay["token_is_birimi"])) * carp
    karar = [w for w in veri.karar_pencereleri(hid) if w in pens] or \
        [max(pens, key=lambda w: pens[w]["T_dk"] or 0)]
    rw = "hafta" if "hafta" in pens else karar[0]           # rezervin uygulandığı pencere
    rz = veri.rezerv(hid)
    ana_u = float(faz["claude_esik_u"]) if ana else None
    acik = _rezerv_acik(rz or ({"kime": ["claude_ustun", "kritik"]} if ana else None), i, a, ust)
    paylar, notlar, Kler, sigar_n = {}, [], {}, []
    lider_tampon = 0.0 if i.get("lider_tamponu_izni") else float(faz["lider_tampon_5s"])
    kal_h = ((durum or {}).get("kapasite_kalibre") or {}).get(hid) or {}
    for w, x in pens.items():
        K, kk, birim = veri.K_p(hid, w)
        kal = kal_h.get(w) if isinstance(kal_h.get(w), dict) else None
        if K and kal and birim != "token" and isinstance(kal.get("K"), (int, float)) and                 0.25 * K <= float(kal["K"]) <= 4.0 * K:
            K, kk = float(kal["K"]), "kalibre_olcum"         # kota.kalibrasyon_hesapla (ork plan yazar)
        if not K:
            # pencere K'sı yok: K'sı bilinen daha uzun pencereden türetme [T]: uzunluk oranı, ama en az 1/6 (kısa
            # pencereler orantılı paydan cömerttir; bu temkinli DEĞİL, sezgisel bir alt sınırdır: aşımı soğumayla
            # düzelir, eksik tahmin havuzu hiç kullandırmaz). Veride K_p tanımlamak her zaman yeğdir.
            kaynak = [(ow, veri.K_p(hid, ow)) for ow in pens if ow != w and veri.K_p(hid, ow)[0]
                      and (pens[ow]["T_dk"] or 0) > (x["T_dk"] or 0)]
            if not kaynak:
                return {"uygun": False, "neden": f"{hid}.{w}: K_p yok"}
            ow, (Kk, _, birim) = max(kaynak, key=lambda z: pens[z[0]]["T_dk"] or 0)
            oran = (x["T_dk"] / pens[ow]["T_dk"]) if (x["T_dk"] and pens[ow]["T_dk"]) else 1 / 6
            K, kk = Kk * max(oran, 1 / 6.0), "turetilmis"
        Kler[w] = kk
        c = c_tok if birim == "token" else c_usd
        pay = c / K
        sure = i.get("sure_dk")
        if sure and x["t_dk"] is not None and x["T_dk"] and sure > x["t_dk"]:
            oran = x["t_dk"] / sure
            simdi_pay, sonra_pay = pay * oran, pay * (1 - oran)
            sigar = simdi_pay <= x["m_ham"] and sonra_pay <= 1.0 - x["taban"]
            notlar.append(f"{w} iki pencere: şimdi %{simdi_pay * 100:.1f}, sıfırlama sonrası %{sonra_pay * 100:.1f}")
            paylar[w] = simdi_pay
        else:
            sigar = pay <= x["m_ham"]
            paylar[w] = pay
        if not sigar:
            return {"uygun": False, "neden": f"{hid}.{w} sığmıyor (pay %{pay * 100:.1f} > taban üstü "
                                             f"%{x['m_ham'] * 100:.1f})", "engel_saat": x["sifirlama"],
                    "engel_tur": f"{w} taban", "pay": pay, "paylar": {w: pay}}
        if paylar[w] > 0:
            sigar_n.append(x["m_ham"] / paylar[w])
    if ana and "5s" in pens and "5s" in paylar:
        x5 = pens["5s"]
        if paylar["5s"] > 0:
            sigar_n.append(max(0.0, x5["k_ham"] - x5["taban"] - lider_tampon) / paylar["5s"])
        if x5["k_ham"] - paylar["5s"] < x5["taban"] + lider_tampon:
            return {"uygun": False, "neden": "lider payı: ana havuz 5s taban+tampon altına iner (işçi açılmaz, lider "
                                             "devreder)",
                    "engel_saat": x5["sifirlama"], "engel_tur": "lider payı", "pay": paylar["5s"],
                    "paylar": dict(paylar), "sonra_kalan_5s": x5["k_ham"] - paylar["5s"], "taban_5s": x5["taban"]}
    tmin = float(ay["tempo_t_min"])
    f_lo, f_hi = ay["f_sinir"]
    rholar = []
    for w in karar:
        x = pens[w]
        U = 1.0 - x["taban"]
        R = _rezerv_miktar(rz, x["taban"], ana_u, _azalma(x, ana, faz, rz)) if w == rw else 0.0
        R_eff = 0.0 if acik else R
        payda = (U - R_eff) * _x(x, tmin)
        rholar.append(max(0.0, x["m"] - R_eff) / payda if payda > 0 else 0.0)
    rho = min(rholar) if rholar else 0.0
    pk = pens[rw]
    m, taban, t, T = pk["m"], pk["taban"], pk["t_dk"], pk["T_dk"]
    R_eff = 0.0 if acik else _rezerv_miktar(rz, taban, ana_u, _azalma(pk, ana, faz, rz))
    pay_k = paylar.get(rw, 0.0)
    rezervden = (pk["m_ham"] - pay_k) < R_eff - 1e-12
    if m > 0 and T and t is not None and (1.0 - taban) > 0:
        f = _clamp((t / T) / (m / (1.0 - taban)), f_lo, f_hi)
    else:
        f = 1.0
    S = (pay_k / m) * f if m > 0 else float("inf")
    onde = None
    if bedava:
        katman = 0
    elif ana:
        # ana havuz okunamıyorsa taban korunduğu kanıtlanamaz: rezerv açık olsa da (üstün/kritik iş) katman 4 +
        # "önce kota oku" (seçilirse SOR T0); rezervine giren eşit kalite işi otomatik aday değil (SOR T2)
        if belirsiz:
            katman = 4
            notlar.append(f"{hid} kotası bilinmiyor: önce oku (get_usage -> ork kota --claude 5s=..,hafta=..)")
        else:
            katman = SOR_KATMAN if rezervden else 3
    else:
        # Claude en son biter (R3): taban üstündeki dış havuz eşit kalitede Claude'dan önce gelir; göreli tempo
        # (ÖNDE 1 / GERİDE 2) dış havuzları kendi arasında sıralar. Tek istisna kullan-ya-da-kaybet: Claude'un taban
        # üstü fazlası temposunun faz.claude_kullan_kaybet_rho katını aşıyorsa (ör. sıfırlamaya saatler kala bol kota)
        # o fazla zaten yanacaktır; GERİDE dış havuz Claude'un arkasına geçer (katman 3.5)
        o = tempo_agirligi(faz, durum, hid)
        rc = 1.0 if rho_C is None else float(rho_C)
        onde = False if belirsiz else _onde(durum, hid, o * rho, rc, float(faz.get("tempo_bant", 0.1)), dout)
        kk_rho = float(faz.get("claude_kullan_kaybet_rho", 1.5))
        geride = 3.5 if (rho_C is not None and rc >= kk_rho) else 2
        # okunamayan dış havuz öne geçmez: bilinen Claude'dan sonra (katman 4, havuz sırasıyla bilinmeyen Claude'dan önce)
        katman = 5 if rezervden else (4 if belirsiz else (1 if onde else geride))
    return {"uygun": True, "katman": katman, "S": S, "pay": pay_k, "paylar": paylar, "c": c_usd, "c_sabit": c_sabit,
            "rho": rho, "onde": onde, "belirsiz": belirsiz, "rezervden": rezervden, "rezerv_acik": acik,
            "notlar": notlar, "karar": karar, "K_kaynak": Kler,
            "parca_sigar": int(min(sigar_n) + 1e-9) if sigar_n else 10 ** 6}


def u_claude(veri, kota, durum, simdi):
    """Ana havuzun taban üstü kullanılabilir payının kalan oranı (haftalık)."""
    for hid in sorted(veri.ana_havuzlar()):
        h = veri.havuz(hid)
        if not h:
            continue
        pens = pencereler(hid, h, veri, kota, durum, simdi, {})
        if pens and "hafta" in pens:
            x = pens["hafta"]
            return round(x["m"] / (1.0 - x["taban"]), 3) if x["taban"] < 1 else 0.0
    return None


# ================================================================== sıralama
def _sabit_sira(a, veri):
    """Son eşitlik bozucu: siniflar.secici.sabit_sira (platform kimliği ya da 'bedava'); listede yoksa bedava/yerel
    önce, ana havuz en son."""
    sira = list((veri.siniflar.get("secici") or {}).get("sabit_sira") or [])
    h = veri.havuz(a["havuz"])
    p = veri.platformlar.get(a["platform"], {})
    bedava = bool(h.get("bedava")) or p.get("ucret") in ("bedava", "yerel")
    if a["platform"] in sira:
        return sira.index(a["platform"])
    if bedava and "bedava" in sira:
        return sira.index("bedava")
    if bedava:
        return -1
    if a.get("elle"):
        return len(sira) + 2
    if a["havuz"] in veri.ana_havuzlar():
        return len(sira) + 1
    return len(sira)


def havuz_sira(a, veri):
    """Seviye içi havuz sırası (tasarım 3.3): bedava/yerel 0, faz.dis_sira içindeki indeks + 1, ana havuz en son."""
    h = veri.havuz(a["havuz"])
    p = veri.platformlar.get(a["platform"], {})
    if h.get("bedava") or p.get("ucret") in ("bedava", "yerel"):
        return 0
    if a["havuz"] in veri.ana_havuzlar():
        return 99
    ds = list(veri.faz().get("dis_sira") or [])
    return (ds.index(a["havuz"]) + 1) if a["havuz"] in ds else len(ds) + 1


def _fazla_zeka(a, Q, siniflar):
    fz = siniflar.get("fazla_zeka") or {}
    pay, gen, tav = float(fz.get("pay", 8)), float(fz.get("genislik", 12)), float(fz.get("tavan", 1.3))
    return 1.0 + (tav - 1.0) * _clamp((a["z"] - Q - pay) / gen, 0.0, 1.0)


def _tek_varyant(adaylar, delta):
    """Aynı modelin (aynı platform) eforları q bakımından ölçütün gürültü bandı (δ) içindeyse en ucuz efor. Bant
    ölçeğe bağlı değildir (göreli %10 Elo ölçeğinde ~140 puan olurdu)."""
    grup = {}
    for a in adaylar:
        grup.setdefault((a["kimlik"], a["platform"]), []).append(a)
    out = []
    for g in grup.values():
        qmax = max(x["q"] for x in g)
        yakin = [x for x in g if x["q"] >= qmax - float(delta)]
        out.append(min(yakin, key=lambda x: (x["c_cap"], efor_sira(x["efor"]))))
    return out


def sirala(adaylar, veri, Q, durum, anahtar, dout):
    """Anahtar (tasarım 3.3): (seviye, havuz_sira, P, -q, dk, sabit_sira, id). Eşitlik bandı ve histerezis yalnız
    aynı (seviye, havuz_sira) içinde: dış havuz sırası (bedava -> agy -> Codex -> Claude) P ile bozulmaz."""
    if not adaylar:
        return []
    ay = ayar(veri)
    tek_yol = all(a.get("elle") for a in adaylar)
    for a in adaylar:
        ceza_elle = float(ay["elle_ceza"]) if (a.get("elle") and not tek_yol) else 1.0
        kg = a.get("kapanis_gun")
        ceza_kap = 2.0 if (kg is not None and kg <= ay["kapanis_ceza_gun"]) else 1.0
        S = a["S"] if math.isfinite(a["S"]) else 1e9
        a["P"] = S * _fazla_zeka(a, Q, veri.siniflar) * (1 + a["dk"] / float(ay["sure_cezasi_dk"])) * ceza_elle * ceza_kap
        a["havuz_sira"] = havuz_sira(a, veri)
        a["_elle_sira"] = 1 if (a.get("elle") and not tek_yol) else 0
    # elle yol otomatik yolun önüne geçmez (elle yol yalnız ELLE ÖNERİ olarak ya da tek yol iken seçim olur)
    sira = sorted(adaylar, key=lambda a: (a["_elle_sira"], a["katman"], a["havuz_sira"], a["P"], -a["q"], a["dk"],
                                          _sabit_sira(a, veri), a["id"]))
    en = sira[0]
    esit = float(ay["esitlik_bandi"])
    # eşitlik bandı: aynı seviye ve havuz sırasında P bant içinde -> yüksek q > düşük gecikme > sabit sıra
    bant = [a for a in sira if a["katman"] == en["katman"] and a["havuz_sira"] == en["havuz_sira"]
            and a["_elle_sira"] == en["_elle_sira"] and a["P"] <= en["P"] * (1 + esit) + 1e-12]
    bant.sort(key=lambda a: (-round(a["q"], 6), a["dk"], _sabit_sira(a, veri), a["P"], a["id"]))
    sira = bant + [a for a in sira if a not in bant]
    # histerezis: önceki seçim aynı seviye/havuz sırasında ve yeni aday belirgin ucuz değilse korunur
    onceki = ((durum or {}).get("son_secim") or {}).get(anahtar)
    if onceki:
        eski = next((a for a in sira if a["id"] == onceki), None)
        if eski and eski is not sira[0] and eski["katman"] == sira[0]["katman"] \
                and eski["havuz_sira"] == sira[0]["havuz_sira"] \
                and not (sira[0]["P"] < float(ay["histerezis"]) * eski["P"]):
            sira.remove(eski)
            sira.insert(0, eski)
            eski["histerezis"] = True
    return sira


# ================================================================== çağrı ve gerekçe
def cagri_uret(a, veri, i, ek=None):
    """Çıplak rol adı asla CLI'a gitmez: model alanı her zaman kesin kimlik (gerekirse platform slug şablonu)."""
    kimlik = a["kimlik"]
    if a.get("sablon"):
        kimlik = a["sablon"].format(kimlik=a["kimlik"], efor=a["efor"])
    taban = kimlik
    c = {"model": kimlik, "efor": a["efor"], "yol": a["yol"], "platform": a["platform"], "havuz": a["havuz"]}
    if a.get("takma"):
        c["takma"] = a["takma"]          # Agent aracı yalnız takma ad alır; takma ad ailenin en son sürümüne kayar
    pc = veri.platformlar.get(a["platform"], {}).get("cagri") or {}
    sab = (pc.get("sablon_oto") or pc.get("sablon")) if a.get("yol") == "agy-oto" else pc.get("sablon")
    if a.get("yol") == "agy-oto":
        c["yurut"] = "ork suru calistir --plan <plan.json> (tek Bash; güvenceler kişisel kayıtta)"
        c["taban"] = taban
    if sab:
        c["sablon"] = sab
        dolu = sab
        sandbox = pc.get("sandbox_duzenleme", "workspace-write") if i.get("duzenleme") else \
            pc.get("sandbox_varsayilan")
        for k, v in (("kimlik", kimlik), ("slug", kimlik), ("taban", taban), ("efor", a["efor"]),
                     ("takma", a.get("takma")), ("sandbox", sandbox)):
            if v:
                dolu = dolu.replace("{" + k + "}", str(v))
        c["komut"] = dolu                  # kalan {..} alanları (ikili ork.py'de; brief/çıktı dosyası lider doldurur)
        c["bos_alanlar"] = sorted(set(re.findall(r"\{(\w+)\}", dolu)))
    if a.get("elle"):
        c["elle"] = True
    c["olc"] = "sonuç dönünce: ork olc kaydet --taslak <olc_taslak> --giris-tok N --cikis-tok N --sure-sn S --durum ok"
    c["olc_taslak"] = {"model": a["kimlik"], "efor": a["efor"], "havuz": a["havuz"], "aile": a.get("aile"),
                       "yol": a["yol"], "sinif": i.get("sinif"), "alan": i.get("alan"), "alt_alan": i.get("alt_alan"),
                       "is_birimi": i.get("ib"), "pay_tahmin": round(float(a.get("pay") or 0.0), 6)}
    if ek:
        c.update(ek)
    return c


ONEMLI_ELEME = ("kalite kümesi", "kanıt birikimi", "Pareto", "sığmıyor", "lider payı", "Z<Q", "efor kuralı", "yasak",
                "onay_bekliyor")


def _elenen_onem(kv):
    k, v = kv
    sira = next((n for n, x in enumerate(ONEMLI_ELEME) if x in v), len(ONEMLI_ELEME))
    return (sira, k)


def gerekce_satiri(i, sec, E, delta, olcut, u_C, elenen, dogr):
    parca = [f"SEÇİM {aday_etiket(sec)}" if sec else "SEÇİM yok",
             f"{i['alan']}/{i.get('alt_alan') or '-'}",
             f"Q{i['Q']}→{i.get('kademe', '?')}"]
    if E:
        adlar = [aday_adi(a) for a in E]
        cift = {x for x in adlar if adlar.count(x) > 1}      # aynı rol@efor farklı platformda: platformu göster
        parca.append("E={" + ", ".join(f"{aday_adi(a)}/{a['platform']}" if aday_adi(a) in cift else aday_adi(a)
                                       for a in E[:5]) + "}" + f" δ={delta:g} ({olcut})")
    if u_C is not None:
        parca.append(f"faz u_C={u_C:.2f}")
    if sec and sec.get("katman") is not None:
        r = sec.get("rho")
        parca.append(f"{sec['havuz']}" + (f" ρ={r:.2f}" if r is not None and math.isfinite(r) else "")
                     + f" katman{sec['katman']}")
        if sec.get("c") is not None:
            parca.append(f"c={sec['c']:.2f} USD-e, pay %{sec.get('pay', 0) * 100:.1f}")
    el = [f"{k.replace('|', '/')} ({v})" for k, v in sorted(elenen.items(), key=_elenen_onem)[:3]]
    if el:
        parca.append("ELENEN " + ", ".join(el))
    if dogr:
        parca.append(f"doğrulayıcı: {dogr}")
    return " · ".join(parca)


def _ozet(a):
    if not a:
        return None
    anahtarlar = ("id", "kimlik", "rol", "efor", "yol", "platform", "havuz", "aile", "hat", "z", "z_etkin", "q", "katman",
                  "P", "pay", "paylar", "c", "c_sabit", "rho", "onde", "elle", "rezervden", "rezerv_acik", "belirsiz",
                  "histerezis", "notlar", "q_kaynak", "havuz_sira")
    return {k: a.get(k) for k in anahtarlar if k in a}


# ================================================================== rotalar (deterministik ön geçit, elle yollar)
def rota_listesi(veri, alan, alt):
    r = veri.modeller.get("rotalar") or {}
    if alt and f"{alan}.{alt}" in r:
        return r[f"{alan}.{alt}"]
    for k in sorted(r):
        if k.startswith(f"{alan}."):
            return r[k]
    return []


BEYANLI_HASSAS = {"kisisel", "gizli", "saglik"}     # açıkça beyan edilmiş hassas veri (bilinmiyor değil)


def _rota_gizlilik(x, veri):
    """Rota gizliliği: rota kaydı > platform kaydı (agy-elle: otomatik çağrısız platform) > yol varsayılanı.
    Elle GUI rotasında beyan yoksa `dis` sayılır (fail-closed)."""
    if x.get("gizlilik"):
        return x["gizlilik"]
    yol = x.get("yol")
    if yol in ("yerel", "otomatik", "sabit"):
        return "ozel"
    if yol == "bedava-api":
        for p in veri.platformlar.values():
            if p.get("yol") == "bedava-api" and p.get("gizlilik"):
                return p["gizlilik"]
        return "kamu"
    if yol in AGY_YOLLARI:
        for p in veri.platformlar.values():
            if p.get("yol") in AGY_YOLLARI and p.get("gizlilik"):
                return p["gizlilik"]
    return "dis"


def _rota_uygun(x, i, veri=None):
    kosul = str(x.get("kosul") or "")
    gz_r = _rota_gizlilik(x, veri) if veri is not None else ("kamu" if x.get("yol") == "bedava-api" else "dis")
    if x.get("yol") == "bedava-api":
        bedava_kisisel = bool(veri is not None and gz_r == "ozel" and any(
            isinstance(b, dict) and b.get("veri") == "kisisel"
            for b in (veri.kurallar.get("bedava_istisna") or [])))
        if not bedava_kisisel and i["veri"] != "genel":
            return False
    elif "veri genel" in kosul and i["veri"] != "genel" and gz_r != "ozel":
        return False
    if veri is not None and i["veri"] in BEYANLI_HASSAS and gz_r in ("dis", "kamu"):
        return False
    if veri is not None and i["veri"] in SIKI_VERI and not i.get("dis_onay") and x.get("yol") not in \
            ("yerel", "otomatik", "sabit"):
        return False                       # sağlık/gizli veride elle dış uygulama da yeni alıcıdır
    return True


def _rota_metni(x, veri=None, i=None):
    ad = x.get("arac") or x.get("rol") or x.get("gorev") or "?"
    s = f"{x.get('yol')}:{ad}" + (f" ({x.get('ne')})" if x.get("ne") else "")
    if veri is not None and i is not None and i["veri"] == "bilinmiyor" and _rota_gizlilik(x, veri) in ("dis", "kamu"):
        s += " [dış havuz: yalnız genel veri]"
    return s


def _elle_secenekler(veri, i, sabit=None, yerel_dahil=True):
    """Elle ve yerel seçenekler; gizlilikten süzülür (açık hassas veri beyanında dış/kamu yol önerilmez)."""
    if sabit and sabit.get("elle"):
        return [x for x in sabit["elle"]]
    yollar = ELLE_ROTA | ({"yerel"} if yerel_dahil else set())
    R = [x for x in rota_listesi(veri, i["alan"], i.get("alt_alan"))
         if x.get("yol") in yollar and _rota_uygun(x, i, veri)]
    if i["veri"] in BEYANLI_HASSAS:                      # hassas veride yerel yol önce
        R.sort(key=lambda x: 0 if x.get("yol") == "yerel" else 1)
    return [_rota_metni(x, veri, i) for x in R]


# ================================================================== ana fonksiyon
def sec(istek, veri, kota=None, durum=None, simdi=None, _ic=False):
    """İş isteği -> seçim sözlüğü. istek alanları:
    alan, alt_alan, sinif | sinyaller(+belirsiz), kipler, duzenleme, olgu, veri, baglam_gerek, ib | boyut, sure_dk,
    kip (normal|ultra|hafif), zorla ("rol[:efor]" | kimlik), tur (uretim|dogrulama|rol|arac), host, dizin,
    dogrulayici_var (dış kanıt: test/şema/DOI), deterministik (lider: deterministik araç işi çözer)."""
    simdi = simdi or simdi_utc()
    durum = durum or {}
    kota = kota or {}
    veri.olcek_kilidi()
    proje = proje_kurali((istek or {}).get("dizin"))
    i = istek_hazirla(istek, veri, proje)
    i["kademe"] = kademe(i["Q"], veri.siniflar)
    dout = {}
    uyarilar = []
    anahtar = f"{i['alan']}/{i.get('alt_alan') or '-'}/{i['sinif']}"
    i["_anahtar"] = anahtar
    _tavan_hazirla(i, veri, durum, simdi)
    sabit = (veri.kurallar.get("sabit_kurallar") or {}).get(i["alan"])
    pz = (proje.get("zorunlu") or {}) if proje else {}
    takma = veri.siniflar.get("alan_takma") or ALAN_TAKMA_VARSAYILAN
    pz = {takma.get(k, k): v for k, v in pz.items()}
    hedef = kaynak = None
    if i.get("zorla"):
        hedef, kaynak = i["zorla"], "kullanıcı isteği (--zorla)"
        i["once_sor_izni"] = True               # açık kullanıcı isteği: önce-sor hattı bu iş için serbest
    elif i["alan"] in pz or "*" in pz:
        hedef, kaynak = pz.get(i["alan"], pz.get("*")), f"proje kuralı {proje.get('yol')}"
        if sabit and not _ayni_hedef(hedef, sabit):
            uyarilar.append(f"kullanıcı kuralıyla çelişki: sabit kural {sabit.get('rol')}:{sabit.get('efor')} "
                            f"({sabit.get('gerekce', '')}); proje kuralını düzelt ya da kullanıcıya sor")
    if hedef:
        yg = _hedef_yasak(hedef, veri)
        if yg:
            return _sonuc("hata", i, None, veri, dout, uyarilar + [f"{hedef}: {yg}"],
                          gerekce=f"HATA zorunlu hedef {hedef} yasak ({yg}); kullanıcı kuralı, sessizce başka modele "
                                  f"düşülmedi", elenen={})
        return _zorunlu(hedef, kaynak, i, veri, kota, durum, simdi, proje, dout, uyarilar, sabit)
    if sabit:
        return _sabit_kural(sabit, i, veri, kota, durum, simdi, proje, dout, uyarilar)
    r = _on_gecit(i, veri, kota, durum, simdi, proje, dout, uyarilar)
    if r:
        return r
    r = _normal(i, veri, kota, durum, simdi, proje, dout, uyarilar, anahtar, _ic)
    return r if _ic else _once_sor_onerisi(r, i, veri, kota, durum, simdi, proje, dout, uyarilar)


ONCE_SOR_KABUL, ONCE_SOR_RET = "once_sor_kabul", "once_sor_ret"


def _once_sor_onerisi(r, i, veri, kota, durum, simdi, proje, dout, uyarilar):
    """SOR T7: kullanıcının `once_sor` hattındaki model (yasak değil, ama otomatik seçilmez) bu işte AÇIK önde ve
    havuzuna sığıyorsa normal seçim yerine tek soru döner. Koşullar (kullanici-kurallari.once_sor.kosul): iş sınıfı
    listede, önce-sor adayının alan puanı otomatik adayların en iyisini en az `ustunluk_delta` x δ aşıyor (aynı ölçüt,
    ölçülmüş), aday sığıyor. Yanıt: kabul -> `--zorla rol:efor`; ret -> `--sor-yanit once_sor_ret` (normal seçim)."""
    kural = veri.kurallar.get("once_sor") or {}
    if not kural.get("saglayici_hat") or ONCE_SOR_RET in _sor_kararlari(i, durum, simdi):
        return r
    kosul = kural.get("kosul") or {}
    if i.get("sinif") not in (kosul.get("siniflar") or ["zor", "kritik"]) or i.get("kip") == "hafif":
        return r
    i2 = dict(i, once_sor_izni=True)
    A, _ = adaylari_uret(i2, veri, durum, simdi, proje)
    os_ad = [a for a in A if veri.once_sor_mi(a["kimlik"])[0]]
    if not os_ad:
        return r
    olcut, delta, _e = kalite_hesapla(A, i.get("alt_alan"), veri)
    os_ad = [a for a in os_ad if not a.get("olcumsuz") and not a.get("kopru")]
    oto = [a for a in A if not veri.once_sor_mi(a["kimlik"])[0] and not a.get("olcumsuz")]
    if not os_ad:
        return r
    esik = float(kosul.get("ustunluk_delta", 1.0)) * delta
    q_oto = max((a["q"] for a in oto), default=None)
    uygun = [a for a in os_ad if q_oto is None or a["q"] - q_oto >= esik]
    uygun = _kapasiteli(sorted(uygun, key=lambda a: efor_sira(a["efor"])), i2, veri, kota, durum, simdi, None,
                        dict(dout), {}, [])
    if not uygun:
        return r
    en_q = max(a["q"] for a in uygun)
    a = next(x for x in uygun if x["q"] >= en_q - delta)          # farkı koruyan en düşük efor
    fark = None if q_oto is None else a["q"] - q_oto
    oto_ozet = (f"{r['secim']['rol']}@{r['secim']['efor']}" if r.get("secim") else f"otomatik sonuç: {r.get('durum')}")
    soru = (f"{aday_etiket(a)} bu işte açık önde ("
            + (f"+{fark:.1f} = {fark / delta:.1f}δ, {olcut}" if fark is not None else "Q'yu karşılayan tek aday")
            + f"), ama pahalı: görev başı ≈ {a.get('c_cap', 0.0):.2f} USD-e, havuz payı %{100 * a.get('pay', 0.0):.1f}. "
              f"Kullanılsın mı, yoksa {oto_ozet} ile mi devam edeyim?")
    secenekler = [{"kod": ONCE_SOR_KABUL, "ne": f"bu iş için {aday_etiket(a)}", "yanit": f"--zorla {a['rol']}:{a['efor']}"},
                  {"kod": ONCE_SOR_RET, "ne": f"otomatik seçimle devam ({oto_ozet})",
                   "yanit": f"--sor-yanit {ONCE_SOR_RET}"}]
    return _sor_sonuc(i, veri, dout, uyarilar, r.get("elenen") or {}, "T7", soru, secenekler,
                      varsayilan=ONCE_SOR_RET, otomatik=r.get("secim"), E=r.get("E"))


def _ayni_hedef(hedef, sabit):
    rol, _, ef = str(hedef).replace("@", ":").partition(":")
    return rol == sabit.get("rol") and (not ef or ef == sabit.get("efor"))


def _hedef_yasak(hedef, veri):
    """Zorunlu hedef (rol ya da kesin kimlik) yasak aileden mi: hedef çözülmeden önce (gerekçe 'yasak' olsun)."""
    ad = str(hedef).replace("@", ":").partition(":")[0].strip()
    if not ad:
        return None
    kimlik = (veri.roller.get(ad) or {}).get("aktif") if ad in veri.roller else ad
    y, g = veri.yasak_mi(kimlik or ad, veri.model(kimlik or ad))
    if not y and kimlik and kimlik != ad:
        y, g = veri.yasak_mi(ad, veri.model(ad))
    return g if y else None


def _hedef_filtre(hedef, veri):
    ad, _, ef = str(hedef).replace("@", ":").partition(":")
    ad = ad.strip()
    ef = ef.strip() or None
    if ad in veri.roller:
        def f(kimlik, rol, efor):
            return rol == ad and (efor is None or ef is None or efor == ef)
        return f, ad, ef

    def g(kimlik, rol, efor):
        return kimlik == ad and (efor is None or ef is None or efor == ef)
    return g, ad, ef


def _sonuc(durum_, i, sec_a, veri, dout, uyarilar, **ek):
    t = i.get("_tavan")
    if sec_a and sec_a.get("tavan_asim"):
        u = (f"UYARI şef tavanı aşıldı ({i.get('_tavan_kalkti')}): {aday_adi(sec_a)} · {sec_a['tavan_asim']}")
        if u not in uyarilar:
            uyarilar.append(u)
    if t and t.get("efor_varsayildi"):
        u = f"UYARI şef eforu bilinmiyor: {t['etiket']} varsayıldı (modelin varsayılan eforu); --sef rol:efor ver"
        if u not in uyarilar:
            uyarilar.append(u)
    if t and t.get("yaklasik"):
        u = (f"UYARI şef modeli kayıtta yok ({t['yaklasik']}): en yakın rolün etkin sürümü {t['kimlik']} varsayıldı; "
             f"eski/başka sürümse tavan gerçek şeften gevşek olabilir; --sef kesin_kimlik:efor ver")
        if u not in uyarilar:
            uyarilar.append(u)
    if t:
        ek.setdefault("sef", {"etiket": t["etiket"], "z": t["z"], "bant": t["bant"], "kaynak": t.get("kaynak"),
                              "kalkti": i.get("_tavan_kalkti")})
    r = {"durum": durum_, "istek": {k: i.get(k) for k in ("alan", "alt_alan", "sinif", "Q", "kademe", "veri", "kipler",
                                                          "ib", "host", "kip")},
         "secim": _ozet(sec_a), "uyarilar": uyarilar, "durum_guncel": dout}
    if sec_a:
        r["cagri"] = cagri_uret(sec_a, veri, i, ek.pop("cagri_ek", None))
    else:
        ek.pop("cagri_ek", None)
    r.update(ek)
    return r


def _kapasiteli(adaylar, i, veri, kota, durum, simdi, ust, dout, elenen, engeller):
    out = []
    for a in adaylar:
        kp = kapasite(a, i, veri, kota, durum, simdi, ust, dout, rho_C=i.get("_rho_C"))
        if not kp["uygun"]:
            elenen.setdefault(a["id"], kp["neden"])
            a["_ret"] = kp
            if kp.get("engel_saat"):
                engeller.append((kp["engel_saat"], a["havuz"]))
            continue
        a.pop("_ret", None)
        a.update({k: v for k, v in kp.items() if k != "uygun"})
        a["c_cap"] = kp.get("c", 0.0)
        out.append(a)
    return out


def _bekle(i, veri, dout, uyarilar, elenen, engeller, neden):
    en = min(engeller, key=lambda x: x[0]) if engeller else None
    satir = f"BEKLE · {i['alan']}/{i.get('alt_alan') or '-'} · Q{i['Q']} · {neden}"
    if en:
        satir += f" · en erken çözüm {en[0].isoformat(timespec='minutes')} ({en[1]} sıfırlanınca)"
    satir += " · ya da kapsamı daralt (kısmi) / kullanıcıya devret; Q düşürülmez"
    return _sonuc("bekle", i, None, veri, dout, uyarilar, gerekce=satir, elenen=elenen,
                  en_erken_cozum=en[0].isoformat() if en else None, en_erken_havuz=en[1] if en else None)


def _zorunlu(hedef, kaynak, i, veri, kota, durum, simdi, proje, dout, uyarilar, sabit):
    f, ad, ef = _hedef_filtre(hedef, veri)
    adaylar, elenen = adaylari_uret(i, veri, durum, simdi, proje, gevsek=True, filtre=f, yedek_izinli=True)
    if not adaylar and i.get("_tavan") and _tavan_engeli(elenen):
        return _sor_tavan(i, veri, dout, uyarilar, elenen, f"zorunlu hedef {hedef} ({kaynak})",
                          _tavansiz_en_iyi(i, veri, durum, simdi, proje, gevsek=True, filtre=f, yedek_izinli=True))
    if not adaylar:
        neden = "; ".join(sorted(set(elenen.values()))) or "kayıt/katalog yok"
        if sabit and kaynak.startswith("sabit"):
            return {"durum": "hata", "elenen": elenen}
        return _sonuc("hata", i, None, veri, dout, uyarilar + [f"NOT {hedef}: {neden}"],
                      gerekce=f"HATA zorunlu hedef {hedef} çözülemedi ({neden}); sessizce başka modele düşülmedi",
                      elenen=elenen)
    # en son sürüm önce, yedek yalnız sonra; elle yol (ör. agy kapalıyken) otomatik yoldan sonra; aynı hedefin
    # havuzları dış sıra ile (Claude dışı önce, ana havuz en son: R3), alfabe yalnız son eşitlik bozucu
    def _hs(a):
        return havuz_sira(a, veri)
    adaylar = sorted(adaylar, key=lambda a: (bool(a.get("elle")), bool(a.get("yedek")), _hs(a), a["id"]))
    if ef:
        aday = adaylar
    else:
        # efor verilmemiş: Q'yu ve alan efor tabanını karşılayan EN UCUZ efor (en düşük efor değil)
        def uygun(a):
            ek = efor_kurali(veri.siniflar, i.get("alt_alan"), a.get("rol"))
            return a["z_etkin"] >= i["Q"] and efor_arasi(a["efor"], ek.get("taban"), None) \
                and a["efor"] not in KIP_EFORLARI
        u = [a for a in adaylar if uygun(a)]
        aday = sorted(u, key=lambda a: (bool(a.get("elle")), bool(a.get("yedek")), a["g"], efor_sira(a["efor"]),
                                        _hs(a), a["id"])) if u else \
            sorted(adaylar, key=lambda a: (bool(a.get("elle")), bool(a.get("yedek")), -a["z_etkin"], _hs(a), a["id"]))
    engeller = []
    kap = []
    rezervde = None
    # rezerv yalnız kullanıcının açık isteğinde (--zorla) adayın ailesine üstünlük sayılarak açılır; rota, ön işleme,
    # proje ve sabit kural hedefleri Claude'un korunan son çeyreğini sorgusuz açamaz (SOR T2)
    ust_z = None
    for a in aday:                      # aynı hedefin bir sonraki eforu/havuzu (ör. ana platform dolu, agy yolu)
        a["q"] = a["z_etkin"]
        ust_z = a["aile"] if str(kaynak).startswith("kullanıcı") else None
        kap = _kapasiteli([a], i, veri, kota, durum, simdi, ust_z, dout, elenen, engeller)
        if kap and kap[0].get("katman") == SOR_KATMAN:
            rezervde = rezervde or kap[0]
            kap = []
            continue
        if kap:
            break
    if not kap:
        if rezervde:
            return _sor_t2(i, veri, kota, durum, simdi, dout, uyarilar, elenen, [rezervde], None,
                           f"zorunlu hedef {hedef} ({kaynak})")
        if sabit and kaynak.startswith("sabit"):
            return {"durum": "dolu", "elenen": elenen, "engeller": engeller}
        return _bekle(i, veri, dout, uyarilar, elenen, engeller, f"zorunlu hedef {hedef} havuzu dolu")
    a = kap[0]
    durum_ = "secildi"
    if a["z_etkin"] < i["Q"]:
        durum_ = "onay_gerekli"
        uyarilar.append(f"UYARI {aday_adi(a)} Z={a['z_etkin']:g} < Q{i['Q']}: kullanıcı onayı gerekir")
    ek = {}
    if sabit and sabit.get("yol"):
        ek = _arac_ek(sabit, veri)
    satir = f"SEÇİM {aday_etiket(a)} · {kaynak} · Q{i['Q']}→{i['kademe']} · katman{a.get('katman')}"
    return _sonuc(durum_, i, a, veri, dout, uyarilar, gerekce=satir, elenen=elenen, cagri_ek=ek, kaynak=kaynak)


def _arac_ek(sabit, veri):
    yol = sabit.get("yol") or ""
    ek = {"arac": yol.split(":", 1)[-1] if ":" in yol else yol, "arac_yolu": yol}
    gm = ((veri.modeller.get("gorsel_modeller") or {}).get(yol)) or {}
    q = gm.get("quality") or []
    ek["parametreler"] = {"quality": sabit.get("quality") or ("high" if "high" in q else (q[-1] if q else None)),
                          "size": sabit.get("size") or "auto"}
    ek["kalite_kollari"] = "görsel modeli sürümü + quality/size + iyi prompt (metin modeli kaliteyi belgeli etkilemiyor)"
    return ek


def _sabit_kural(sabit, i, veri, kota, durum, simdi, proje, dout, uyarilar):
    hedef = f"{sabit.get('rol')}:{sabit.get('efor')}" if sabit.get("efor") else sabit.get("rol")
    i2 = dict(i, kipler=["metin"], _tavan_kalkti=i.get("_tavan_kalkti") or "sabit kullanıcı kuralı")
    r = _zorunlu(hedef, "sabit kural", i2, veri, kota, durum, simdi, proje, dout, uyarilar, sabit)
    if r.get("durum") in ("secildi", "onay_gerekli"):
        r["gerekce"] = r["gerekce"].replace("sabit kural", f"sabit kural ({sabit.get('gerekce', 'kullanıcı kuralı')})")
        r["istek"]["kipler"] = i["kipler"]
        return r
    elle = _elle_secenekler(veri, i, sabit)
    t3 = _sifirlama_kredisi(r, kota, simdi, veri)
    if t3:
        hid, adet, son, saat = t3
        soru = (f"{i['alan']} sabit kural havuzu ({hid}) tabanda; tek seferlik ücretsiz sıfırlama kredisini kullanayım "
                f"mı? (geri alınamaz, kalan {adet}, son {son or '?'})")
        sec_ = [{"kod": "sifirlama_kredisi", "ne": "kredi ile haftalık pencereyi sıfırla (geri alınamaz)",
                 "havuz": hid, "adet": adet, "son": son},
                {"kod": "elle", "ne": "elle yol: " + ("; ".join(elle) if elle else "uygulama")},
                {"kod": "bekle", "ne": f"haftalık sıfırlamayı bekle (~{saat:.0f} sa)"}]
        satir = f"SOR T3 · {i['alan']} · {soru} · seçenekler: sifirlama_kredisi, elle, bekle · varsayılan bekle"
        return _sonuc("sor", i, None, veri, dout, uyarilar, gerekce=satir, soru=soru, tetik="T3", secenekler=sec_,
                      varsayilan="bekle", elle_secenekler=elle, elenen=r.get("elenen", {}))
    satir = (f"ELLE · {i['alan']} · sabit kural havuzu kapalı ({sabit.get('rol')}@{sabit.get('efor')} {sabit.get('yol')})"
             + (" · elle seçenekler: " + "; ".join(elle) if elle else "")
             + " · başka modele düşülmedi (kullanıcı kuralı)")
    en = min(r.get("engeller") or [], key=lambda x: x[0]) if r.get("engeller") else None
    return _sonuc("elle", i, None, veri, dout, uyarilar + ["kullanıcıya not: sabit kural havuzu dolu"],
                  gerekce=satir, elle_secenekler=elle, elenen=r.get("elenen", {}),
                  en_erken_cozum=en[0].isoformat() if en else None)


def _sifirlama_kredisi(r, kota, simdi, veri):
    """SOR T3: sabit kural havuzu tabanda, kota anlığında `ek.reset_kredisi.adet >= 1` ve haftalık sıfırlamaya
    >= 48 sa varsa (havuz, adet, son, saat); yoksa None. Kredi asla kendiliğinden kullanılmaz."""
    for _, hid in r.get("engeller") or []:
        kh = ((kota or {}).get("havuzlar") or {}).get(hid) or {}
        rk = ((kh.get("ek") or {}).get("reset_kredisi") or {})
        if int(rk.get("adet") or 0) < 1:
            continue
        sif = zaman_coz(((kh.get("pencereler") or {}).get("hafta") or {}).get("sifirlama"))
        if not sif:
            continue
        saat = (sif - simdi).total_seconds() / 3600.0
        if saat >= 48:
            return hid, int(rk["adet"]), rk.get("son"), saat
    return None


def _on_gecit(i, veri, kota, durum, simdi, proje, dout, uyarilar):
    """Deterministik/yerel ön geçit (tasarım 3.3 A) ve model dışı rotalar (ses, video üretim ...)."""
    if i.get("tur") in ("dogrulama", "arac", "rol"):
        return None
    R = rota_listesi(veri, i["alan"], i.get("alt_alan"))
    if i.get("deterministik"):
        d = next((x for x in R if x.get("arac") == "deterministik"), None) or \
            {"yol": "otomatik", "arac": "deterministik", "ne": "deterministik araç (betik, rg, jq, AST)"}
        return _sonuc("rota", i, None, veri, dout, uyarilar, rota=d,
                      gerekce=f"ROTA {_rota_metni(d)} · model çağrısı yok (deterministik ön geçit)")
    t = olcut_tanimi(i.get("alt_alan"), veri.siniflar)
    if t.get("kapsam") != "rota" or not R:
        return None
    ilk = R[0]
    if ilk.get("rol") and not ilk.get("arac"):
        return None                                   # model akışı (ör. video analizi): _normal + ön işleme
    oto = [x for x in R if x.get("yol") in OTOMATIK_ROTA and _rota_uygun(x, i, veri)]
    elle = _elle_secenekler(veri, i, yerel_dahil=False)
    if not oto:
        return _sonuc("elle", i, None, veri, dout, uyarilar, elle_secenekler=elle,
                      gerekce=f"ELLE · {i['alan']}/{i.get('alt_alan')} · otomatik yol yok · " + "; ".join(elle))
    x = oto[0]
    if x.get("rol"):
        hedef = f"{x['rol']}:{x['efor']}" if x.get("efor") else x["rol"]
        r = _zorunlu(hedef, f"rota {_rota_metni(x)}", dict(i, kipler=["metin"]), veri, kota, durum, simdi, proje,
                     dout, uyarilar, None)
        r["rota"], r["elle_secenekler"] = x, elle
        return r
    return _sonuc("rota", i, None, veri, dout, uyarilar, rota=x, elle_secenekler=elle,
                  gerekce=f"ROTA {_rota_metni(x)} · {i['alan']}/{i.get('alt_alan')}"
                          + (" · elle: " + "; ".join(elle) if elle else ""))


def _on_isleme_rotasi(i, veri):
    if "video" not in i["kipler"] and "ses" not in i["kipler"]:
        return None
    for x in rota_listesi(veri, i["alan"], i.get("alt_alan")):
        if x.get("yol") == "otomatik" and x.get("rol"):
            return x
    return None


def _efor_verim_suz(A, i, veri, ay, delta, elenen):
    """siniflar.json efor_genel.xhigh_kosulu ve azalan_getiri_katsayilari.verimli_tavan uygulanır: üst efor ancak
    (a) ultra kipi, (b) uzun iş (uzun_otonom sinyali ya da sure_dk >= xhigh_kosul_dk), (c) alt alan kuralı o eforu
    taban olarak istiyorsa, (d) aynı modelin sınır altı eforu Q'yu karşılamıyorsa (A'da yoksa) ya da (e) ölçülmüş
    kazanç δ'yı aşıyorsa kalır. Alt alan kuralında açık tavan varsa verimli_tavan yerine o geçer."""
    if i["kip"] == "ultra":
        return A
    s = veri.siniflar
    vt = (s.get("azalan_getiri_katsayilari") or {}).get("verimli_tavan") or {}
    uzun = "uzun_otonom" in (i.get("sinyaller") or []) or float(i.get("sure_dk") or 0) >= float(ay["xhigh_kosul_dk"])
    ekk = s.get("efor_kurallari") or {}
    alt_k = ekk.get(i.get("alt_alan") or "") if isinstance(ekk.get(i.get("alt_alan") or ""), dict) else {}
    out = []
    for a in A:
        ka = alt_k.get(a.get("rol")) or alt_k.get("_tumu") or {}
        sinir = None if ka.get("tavan") else vt.get(a.get("rol"))
        if not uzun and efor_sira(ka.get("taban") or "none") < efor_sira("xhigh"):
            sinir = "high" if sinir is None or efor_sira(sinir) > efor_sira("high") else sinir
        if sinir is None or efor_sira(a["efor"]) <= efor_sira(sinir):
            out.append(a)
            continue
        alt_ad = [b for b in A if b["kimlik"] == a["kimlik"] and b["platform"] == a["platform"]
                  and efor_sira(b["efor"]) <= efor_sira(sinir)]
        if not alt_ad:
            out.append(a)                    # Q'yu yalnız bu efor karşılıyor
            continue
        en_alt = max(alt_ad, key=lambda b: b["q"])
        olculu = a.get("q_kaynak") not in ("z", "alan_olcumu_yok") and en_alt.get("q_kaynak") == a.get("q_kaynak")
        if olculu and a["q"] - en_alt["q"] > delta:
            out.append(a)                    # ölçülmüş kazanç gürültü bandını aşıyor
            continue
        elenen.setdefault(a["id"], f"efor verimi: {a['efor']} koşulu yok (uzun iş/ultra/ölçülmüş kazanç); "
                                   f"{en_alt['efor']} yeterli")
    return out or A


def _isci_dagit(sec_a, oto, n):
    """Parça planı: önce seçilen havuz; toplam sığıyorsa bölünmez. Sığmayan kısım aynı sıradaki farklı havuzlara
    kapasiteleri ölçüsünde; yine kalırsa BEKLE parçası."""
    plan, kalan, kullanilan = [], n, set()
    for a in [sec_a] + [b for b in oto if b is not sec_a]:
        if a["havuz"] in kullanilan:
            continue
        kullanilan.add(a["havuz"])
        k = min(kalan, int(a.get("parca_sigar", n)))
        if k > 0:
            plan.append({"aday": aday_etiket(a), "parca": k, "havuz": a["havuz"]})
            kalan -= k
        if not kalan:
            break
    if kalan:
        plan.append({"aday": "BEKLE (sıfırlama sonrası)", "parca": kalan, "havuz": None})
    return plan


def opus_kapisi(i, veri):
    """Ciddi zor iş (tasarım 4): sınıf listede ve (--ciddi ya da sinyallerden biri) ise kapı tanımı, değilse None."""
    ok = veri.siniflar.get("opus_kapisi") or {}
    if not ok or i.get("sinif") not in (ok.get("siniflar") or []):
        return None
    if i.get("ciddi") or set(i.get("sinyaller") or []) & set(ok.get("sinyaller") or []):
        return ok
    return None


def _kapi_suz(A, i, veri, delta, olcut, elenen, kapi):
    """Opus kapısı açıkken: Opus eforu en az efor_tabani; Opus olmayan aday yalnız doğrudan alan ölçümüyle Opus'un
    en iyisinin δ içindeyse (alan ölçümü hiç yoksa Z_etkin >= Z(opus@taban)); köprü ve tahmin sayılmaz. Aynı model
    başka havuzdaysa (ör. agy'deki Opus) kapıyı geçer."""
    rol = kapi.get("rol") or "opus"
    ef_t = kapi.get("efor_tabani") or "high"
    opus = [a for a in A if a.get("rol") == rol]
    if not opus:
        return A, None
    gecen = []
    for a in opus:
        if efor_sira(a["efor"]) < efor_sira(ef_t):
            elenen.setdefault(a["id"], f"opus kapısı: efor {a['efor']} < {ef_t}")
        else:
            gecen.append(a)
    if not gecen:
        return A, None
    dogrudan = [a["q"] for a in gecen if not a.get("kopru") and not a.get("olcumsuz")]
    q_opus = max(dogrudan) if dogrudan else max(a["q"] for a in gecen)
    z_ref = max((a["z"] for a in gecen if a["efor"] == ef_t), default=min(a["z"] for a in gecen))
    out = list(gecen)
    for a in A:
        if a.get("rol") == rol:
            continue
        olculu = a.get("q_kaynak") not in ("z", "alan_olcumu_yok") and not a.get("kopru") and not a.get("olcumsuz")
        if olcut == "z":
            ok = a["z_etkin"] >= z_ref
        else:
            ok = olculu and a["q"] >= q_opus - delta
        if ok:
            out.append(a)
        else:
            elenen.setdefault(a["id"], "opus kapısı: ölçülü eşdeğer değil" + (" (köprü sayılmaz)" if a.get("kopru")
                                                                               else ""))
    return out, q_opus


def _sor_kararlari(i, durum, simdi):
    """Kullanıcının önceki SOR yanıtı (durum.sor_kararlari, kapsam süresince) ya da bu istekteki --sor-yanit."""
    kodlar = set()
    if i.get("sor_yanit"):
        kodlar.add(i["sor_yanit"])
    for k in (durum or {}).get("sor_kararlari") or []:
        if not isinstance(k, dict):
            continue
        b = zaman_coz(k.get("bitis"))
        if b and b <= simdi:
            continue
        if k.get("kapsam") == "is" and k.get("anahtar") not in (None, i.get("_anahtar")):
            continue
        kodlar.add(k.get("kod"))
    return kodlar


def _kaskad_basla(i, veri, durum, simdi, proje, kota, dout):
    """Kanıtlı kaskad (tasarım 7.3): tam dış kanıtla (test, kapalı cevap, şema) arastirma/normal sınıfında ilk deneme
    bedava havuzdaki en iyi modelden (Q - Z_etkin <= z_acigi); kabul dış kanıttan geçer, değilse normal seçime yükselir."""
    kk = veri.siniflar.get("kanitli_kaskad") or {}
    if not kk or i.get("dis_kanit") not in (kk.get("dis_kanit") or []) or i["sinif"] not in (kk.get("siniflar") or []):
        return None
    if i["veri"] not in (kk.get("veri") or ["genel"]):
        return None
    i2 = dict(i, Q=float(i["Q"]) - float(kk.get("z_acigi", 0)))
    A, _ = adaylari_uret(i2, veri, durum, simdi, proje)
    bed = []
    for a in A:
        h = veri.havuz(a["havuz"])
        if not (h.get("bedava") or veri.platformlar.get(a["platform"], {}).get("ucret") == "bedava"):
            continue
        kp = kapasite(a, i2, veri, kota, durum, simdi, None, dout)
        if kp.get("uygun"):
            a.update({k: v for k, v in kp.items() if k != "uygun"})
            bed.append(a)
    if not bed:
        return None
    b = max(bed, key=lambda a: (a["z_etkin"], -a["g"], a["id"]))
    return b


def _dis_alt_secenek(alt, q_y, delta):
    """SOR dis_alt seçeneği: kalite farkı δ biriminde (kullanıcı ne kadar zayıf olduğunu görür)."""
    fark = alt["q"] - q_y
    return {"kod": "dis_alt", "ne": "kalite kümesi dışındaki en iyi sığan aday (daha zayıf)", "aday": aday_etiket(alt),
            "q_fark": round(fark, 2), "delta": delta,
            "q_fark_delta": round(fark / delta, 1) if delta else None,
            "yanit": f"--zorla {alt.get('rol') or alt['kimlik']}:{alt['efor']}"}


def _sor_sonuc(i, veri, dout, uyarilar, elenen, tetik, soru, secenekler, **ek):
    ek.setdefault("varsayilan", "bekle")
    satir = (f"SOR {tetik} · {i['alan']}/{i.get('alt_alan') or '-'} · Q{i['Q']} · {soru} · seçenekler: "
             + ", ".join(x["kod"] for x in secenekler) + f" · varsayılan {ek['varsayilan']} · Q düşürülmez")
    return _sonuc("sor", i, None, veri, dout, uyarilar, gerekce=satir, soru=soru, tetik=tetik,
                  secenekler=secenekler, elenen=elenen, **ek)


def _sor_t2(i, veri, kota, durum, simdi, dout, uyarilar, elenen, rezervde, t_dis, baglam=None, ek=None):
    """SOR T2: yalnız Claude'un korunan son çeyreği sığıyor (eşit kalite işi, hassas veri ya da zorunlu/rota hedefi)."""
    r = min(rezervde, key=lambda a: (a.get("P") or a.get("S") or 0, a["id"]))
    hassas = i.get("veri") in SIKI_VERI and not i.get("dis_onay")
    if hassas:
        soru = (f"Bu iş veri sınıfı ({i['veri']}) nedeniyle yalnız Claude/yerelde işlenebilir; Claude'un korunan son "
                f"çeyreğinden {aday_adi(r)} kullanayım mı?")
    elif baglam:
        soru = f"{baglam} yalnız Claude'un korunan son çeyreğine sığıyor; {aday_adi(r)} kullanayım mı?"
    else:
        soru = f"Eşit kalitede Claude dışı yer yok; Claude'un korunan son çeyreğinden {aday_adi(r)} kullanayım mı?"
    uC = u_claude(veri, kota, durum, simdi)
    tb = next((veri.taban(hid, "hafta") for hid in sorted(veri.ana_havuzlar())), 0.0)
    U = max(1.0 - tb, 1e-9)
    secenekler = [{"kod": "claude_rezerv", "ne": "Claude rezervinden çalıştır", "aday": aday_etiket(r),
                   "pay": round(r.get("pay") or 0, 4),
                   "sonra_u_C": round(max(0.0, (uC or 0) - (r.get("pay") or 0) / U), 3) if uC is not None else None}]
    secenekler.append({"kod": "bekle", "ne": "havuz açılınca" if baglam else "Claude dışı havuz açılınca",
                       "ne_zaman": t_dis.isoformat() if t_dis else None})
    secenekler.extend(ek or [])
    secenekler.append({"kod": "kismi", "ne": "kapsamı daralt, kısmi teslim"})
    return _sor_sonuc(i, veri, dout, uyarilar, elenen, "T2", soru, secenekler)


def _sor_t4(i, veri, dout, uyarilar, elenen, agy_a, claude_a, E, ust, cagri_elle=None):
    """SOR T4: agy kapısı kişisel bağlam kabulü bekliyor ve kalite kümesinde sığan agy adayı var (seçim aksi hâlde
    Claude'a ya da hiçbir yere düşer). Yanıt oturum boyunca saklanır (`ork sec --sor-yanit agy_kabul|agy_ret`)."""
    soru = ("agy işçi çağrısı kişisel talimat/bağlam dosyalarını (MCP, oturum kancası, GEMINI.md) sağlayıcıya "
            f"gönderebilir (yalın profil doğrulanmadı); {aday_adi(agy_a)} agy'de otomatik çalışsın mı?"
            + (f" Hayırsa iş Claude'da ({aday_adi(claude_a)}) yürür." if claude_a else ""))
    secenekler = [{"kod": AGY_KABUL, "ne": "kişisel bağlam gönderimini bu oturum için kabul et (agy otomatik)",
                   "aday": aday_etiket(agy_a), "kapsam": "oturum"},
                  {"kod": AGY_RET, "ne": ("Claude ile sürdür: " + aday_etiket(claude_a)) if claude_a
                   else "elle köprüyle sürdür", "kapsam": "oturum"},
                  {"kod": "elle", "ne": "hazır agy komutunu kendi terminalinde çalıştır (elle köprü)"}]
    return _sor_sonuc(i, veri, dout, uyarilar, elenen, "T4", soru, secenekler, E=[a["id"] for a in E], ust=ust,
                      varsayilan=AGY_RET if claude_a else "elle", cagri_elle=cagri_elle,
                      claude_alternatif=_ozet(claude_a))


def _sor_ya_da_bekle(i, veri, kota, durum, simdi, dout, uyarilar, elenen, engeller, ctx):
    """Otomatik aday kalmadığında (tasarım 5.3): tetik varsa SOR (tek soru + seçenekler), yoksa ya da en erken açılış
    bekle_esik_dk içindeyse BEKLE. Q hiçbir koşulda düşmez.
    T1 Claude gerekli ama taban/lider payında · T2 yalnız Claude rezervi sığıyor (hassas veri dahil) · T4 agy kapısı
    bekliyor · T5 uzun bekleme (açılış > bekle_esik_dk) ve bekleme dışında bir yol (daha zayıf aday) var."""
    faz = veri.faz()
    esik_dk = float(faz.get("bekle_esik_dk", 45))
    E, ust, kapi, q_y, delta, A_dis = ctx["E"], ctx["ust"], ctx["kapi"], ctx["q_y"], ctx["delta"], ctx["A_dis"]
    ana = veri.ana_havuzlar()
    ana_aile = {a["aile"] for a in ctx["adaylar"] if a["havuz"] in ana}
    E_ana = [a for a in E if a["havuz"] in ana]

    def acilis(L):
        z = [a["_ret"].get("engel_saat") for a in L if a.get("_ret") and a["_ret"].get("engel_saat")]
        return min(z) if z else None

    def dk(t):
        return None if t is None else max((t - simdi).total_seconds() / 60.0, 0.0)

    # sıkı veri sınıfı (sağlık/gizli, dış onay yok) yalnız host'ta işlenir: Claude gerekli sayılır
    hassas = i.get("veri") in SIKI_VERI and not i.get("dis_onay")
    claude_gerekli = (ust in ana_aile) or i["kritik"] or hassas \
        or bool(kapi and E and all(a["aile"] in ana_aile for a in E))
    engel = [a for a in E_ana if a.get("_ret") and a["_ret"].get("engel_tur")]
    rezervde = list(ctx["rezervdekiler"])
    if claude_gerekli and engel:
        t0 = acilis(engel)
        if t0 is not None and dk(t0) <= esik_dk:
            return _bekle(i, veri, dout, uyarilar, elenen, engeller, f"Claude {dk(t0):.0f} dk içinde açılıyor "
                          f"(≤{esik_dk:g} dk: karar gerekmez)")
        a0 = min(engel, key=lambda a: a["_ret"].get("pay") or 0)
        r0 = a0["_ret"]
        neden = "veri sınıfı nedeniyle yalnız Claude/yerelde işlenebilir" if (hassas and ust not in ana_aile) \
            else "Claude'da daha iyi"
        soru = (f"Bu iş ({i['alan']}/{i.get('alt_alan') or '-'}) {neden} ama Claude {r0.get('engel_tur')} "
                f"engelinde; nasıl ilerleyeyim?")
        secenekler = [{"kod": "bekle", "ne": "Claude açılınca yap", "ne_zaman": t0.isoformat() if t0 else None}]
        if r0.get("engel_tur") == "lider payı" and r0.get("sonra_kalan_5s") is not None \
                and r0["sonra_kalan_5s"] >= r0.get("taban_5s", 0):
            secenekler.append({"kod": "lider_tamponu", "ne": f"liderin tamponundan {aday_adi(a0)}",
                               "aday": aday_etiket(a0), "pay": round(r0.get("pay") or 0, 4),
                               "sonra_kalan": round(r0["sonra_kalan_5s"], 4)})
        secenekler.append({"kod": "taban_istisna", "ne": "tabanı yalnız bu iş için del (açık sözünle)",
                           "aday": aday_etiket(a0), "pay": round(r0.get("pay") or 0, 4)})
        alt = _en_iyi_dis_alt(A_dis, E, i, veri, kota, durum, simdi, dout)
        if alt:
            secenekler.append(_dis_alt_secenek(alt, q_y, delta))
        secenekler.append({"kod": "kismi", "ne": "kapsamı daralt, kısmi teslim"})
        return _sor_sonuc(i, veri, dout, uyarilar, elenen, "T1", soru, secenekler, E=[a["id"] for a in E], ust=ust)
    if rezervde:
        # hassas veride de (Claude gerekli ama yalnız rezerv sığıyor) sessiz BEKLE yok: T2
        t_dis = acilis([a for a in E if a["havuz"] not in ana])
        if not hassas and t_dis is not None and dk(t_dis) <= esik_dk:
            return _bekle(i, veri, dout, uyarilar, elenen, engeller, f"Claude dışı havuz {dk(t_dis):.0f} dk içinde "
                          f"açılıyor")
        alt = _en_iyi_dis_alt(A_dis, E, i, veri, kota, durum, simdi, dout)
        r = _sor_t2(i, veri, kota, durum, simdi, dout, uyarilar, elenen, rezervde, t_dis,
                    ek=[_dis_alt_secenek(alt, q_y, delta)] if alt else None)
        r.update({"E": [a["id"] for a in E], "ust": ust})
        return r
    if ctx.get("agy_bekleyen"):
        return _sor_t4(i, veri, dout, uyarilar, elenen, ctx["agy_bekleyen"], None, E, ust)
    # tetik yok: açılış yakınsa ya da bekleme dışında yol yoksa BEKLE; uzun beklemede daha zayıf bir yol varsa
    # kullanıcıya sor (T5): sessiz uzun bekleme de sessiz zayıf seçim de yok
    en = min(engeller, key=lambda x: x[0]) if engeller else None
    bekleme = dk(en[0]) if en else None
    alt = _en_iyi_dis_alt(A_dis, E, i, veri, kota, durum, simdi, dout) if (bekleme is None or bekleme > esik_dk) \
        else None
    if alt:
        lider = E[0] if E else None
        soru = (f"Kalite kümesindeki havuzlar dolu ({', '.join(sorted({a['havuz'] for a in E}))}); en erken açılış "
                + (f"{bekleme / 60:.1f} sa sonra ({en[1]})" if en else "bilinmiyor")
                + f"; beklensin mi, yoksa daha zayıf {aday_adi(alt)} ile mi ilerleyeyim?")
        secenekler = [{"kod": "bekle", "ne": "havuz açılınca yap", "ne_zaman": en[0].isoformat() if en else None,
                       "havuz": en[1] if en else None}, _dis_alt_secenek(alt, q_y, delta),
                      {"kod": "kismi", "ne": "kapsamı daralt, kısmi teslim"}]
        return _sor_sonuc(i, veri, dout, uyarilar, elenen, "T5", soru, secenekler, E=[a["id"] for a in E], ust=ust,
                          kalite_lideri=aday_etiket(lider) if lider else None)
    return _bekle(i, veri, dout, uyarilar, elenen, engeller, "kalite kümesindeki hiçbir havuzda yer yok")


def _en_iyi_dis_alt(A_dis, E, i, veri, kota, durum, simdi, dout):
    """E dışındaki Q üstü, otomatik yolda sığan en iyi aday (SOR dis_alt seçeneği)."""
    idler = {a["id"] for a in E}
    L = [dict(a) for a in A_dis if a["id"] not in idler and not a.get("elle") and not a.get("kip_eforu")
         and a["z_etkin"] >= i["Q"] and not a.get("olcumsuz")]
    uy = []
    for a in L:
        kp = kapasite(a, i, veri, kota, durum, simdi, None, dout, rho_C=i.get("_rho_C"))
        if kp.get("uygun") and kp.get("katman") != SOR_KATMAN:
            a.update({k: v for k, v in kp.items() if k != "uygun"})
            uy.append(a)
    return max(uy, key=lambda a: (a["q"], -a["c"], a["id"])) if uy else None


def _normal(i, veri, kota, durum, simdi, proje, dout, uyarilar, anahtar, _ic):
    s = veri.siniflar
    ay = ayar(veri)
    i["_anahtar"] = anahtar
    kararlar = _sor_kararlari(i, durum, simdi)
    if "claude_rezerv" in kararlar:
        i["rezerv_izni"] = sorted(veri.ana_havuzlar())
        uyarilar.append("SOR yanıtı: claude_rezerv (bu kapsamda Claude rezervi açık)")
    if "lider_tamponu" in kararlar:
        i["lider_tamponu_izni"] = True
        uyarilar.append("SOR yanıtı: lider_tamponu (5s tabanı korunur, lider tamponu kullanılır)")
    rc = rho_claude(veri, kota, durum, simdi)
    i["_rho_C"] = rc["rho"]
    adaylar, elenen = adaylari_uret(i, veri, durum, simdi, proje)
    if not adaylar:
        a2, _ = adaylari_uret(i, veri, durum, simdi, proje, yedek_izinli=True)
        if a2:
            adaylar = a2
            uyarilar.append("aktif rol erişilemedi: yedek modeller açıldı")
    if not adaylar and i.get("_tavan") and _tavan_engeli(elenen):
        en = _tavansiz_en_iyi(i, veri, durum, simdi, proje)
        if en:
            return _sor_tavan(i, veri, dout, uyarilar, elenen, "Q'yu karşılayan aday yalnız tavan üstünde", en)
    if not adaylar and not _ic and _on_isleme_rotasi(i, veri):
        return _on_isleme(i, veri, kota, durum, simdi, proje, dout, uyarilar, elenen)
    if not adaylar:
        neden = "Q'yu karşılayan aday yok"
        if i["veri"] in SIKI_VERI and any("--dis-onay" in v for v in elenen.values()):
            neden += f" (veri={i['veri']}: host dışı sağlayıcı kullanıcı onayı ister: --dis-onay)"
        return _bekle(i, veri, dout, uyarilar, elenen, [], neden)
    # E. kalite kümesi
    ust_g = float(s.get("ust_kademe_genisligi", 10))
    if i["kip"] == "ultra":
        A_K = adaylar
    elif i["kip"] == "hafif":                 # yeten en ucuz: Q ile Q + fazla_zeka.pay arası, tırmanma yok
        pay_fz = float((s.get("fazla_zeka") or {}).get("pay", 8))
        A_K = [a for a in adaylar if a["z_etkin"] <= i["Q"] + pay_fz] or \
            sorted(adaylar, key=lambda a: a["z_etkin"])[:1]
    else:
        A_K = [a for a in adaylar if a["z_etkin"] <= i["Q"] + ust_g] or adaylar
    if len(A_K) < len(adaylar):
        kalite_hesapla(adaylar, i.get("alt_alan"), veri)      # pencere dışındakilere de q (düşüş ve alternatif için)
        doygunluk(adaylar, i, veri)
    olcut, delta, _ = kalite_hesapla(A_K, i.get("alt_alan"), veri)
    doygun = doygunluk(A_K, i, veri)
    if i.get("_tavan") and not i.get("_tavan_kalkti"):
        A_K = _tavan_alan_suz(A_K, i, veri, olcut, delta, elenen)
        adaylar = _tavan_alan_suz(adaylar, i, veri, olcut, delta, {})
        if not A_K:
            en = _tavansiz_en_iyi(i, veri, durum, simdi, proje)
            return _sor_tavan(i, veri, dout, uyarilar, elenen, f"alan ölçümünde ({olcut}) Q'yu karşılayan aday "
                                                               f"yalnız şefin üstünde", en)
    A_K0 = list(adaylar)                      # düşüş (D1/D2) için filtre öncesi tüm Q üstü adaylar
    A_K = _efor_verim_suz(A_K, i, veri, ay, delta, elenen)
    # Pareto (maliyet kararı) kalite kanıtından sonra uygulanır: baskın olunan varyant ailesinin ölçüm kanıtı sayılır
    olculu_var = any(not a.get("olcumsuz") for a in A_K)
    for a in A_K:
        if a.get("olcumsuz") and olculu_var:
            elenen.setdefault(a["id"], f"alan ölçümü yok ({olcut}); ölçülmüş aday varken seçilmez")
    A_Kq = [a for a in A_K if not (a.get("olcumsuz") and olculu_var)]
    aileler_AK = {a["aile"] for a in A_Kq}
    kapi = opus_kapisi(i, veri) if i["kip"] != "hafif" else None
    q_opus = None
    if kapi and i.get("_tavan") and not i.get("_tavan_kalkti"):
        k_rol, k_ef = kapi.get("rol") or "opus", kapi.get("efor_tabani") or "high"

        def kapi_ustu(id_):                  # aday kimliği: "rol@efor|platform"
            r_, _, e_ = str(id_).split("|")[0].partition("@")
            return r_ == k_rol and efor_sira(e_) >= efor_sira(k_ef)
        tavanli = [k_ for k_, v in elenen.items() if kapi_ustu(k_) and str(v).startswith("şef tavanı")]
        # tavan altında Q'yu karşılayan kapı Opus'u var ama pencere/ölçüm/Pareto/verim süzgecinde düştüyse sorun
        # tavan değildir (normal akış kapıyı işler); Q'yu karşılamayan alt efor tavan sorunudur
        tavansiz_var = any(kapi_ustu(a["id"]) for a in A_K0)
        if tavanli and not tavansiz_var:
            en = _tavansiz_en_iyi(i, veri, durum, simdi, proje, filtre=lambda k_, r_, e_: r_ == k_rol)
            return _sor_tavan(i, veri, dout, uyarilar, elenen, f"ciddi zor iş: Opus kapısı ({k_rol} >= {k_ef}) şef "
                                                               f"tavanının üstünde, Opus yalnız kullanıcı izniyle", en)
    if kapi:
        A_Kq, q_opus = _kapi_suz(A_Kq, i, veri, delta, olcut, elenen, kapi)
    dogrudan = [a["q"] for a in A_Kq if not a.get("kopru")]
    q_y = max(dogrudan) if dogrudan else max(a["q"] for a in A_Kq)
    E = A_Kq if i["kip"] == "hafif" else [a for a in A_Kq if a["q"] >= q_y - delta]
    for a in A_Kq:
        if a not in E:
            elenen.setdefault(a["id"], f"kalite kümesi dışı (q {a['q']:.1f} < {q_y - delta:.1f})")
    F = kanit_birikimi(E, i.get("alt_alan"), veri) if i["kip"] != "hafif" else None
    if F:
        dar = [a for a in E if a["aile"] == F]
        kz = next((a.get("kanit_z") for a in dar if a.get("kanit_z") is not None), None)
        for a in E:
            if a not in dar:
                elenen.setdefault(a["id"], f"kanıt birikimi: {F} birleşik z={kz} (≥2 bağımsız ölçütte geride değil)")
        E = dar
    E = _pareto(E, elenen)
    A_Kq = _pareto(A_Kq, {})
    aileler_E = {a["aile"] for a in E}
    ust = next(iter(aileler_E)) if (len(aileler_E) == 1 and len(aileler_AK) >= 2) else None
    # Elle yol (agy kapalıyken, uygulama) kalite lideriyse: ELLE ÖNERİ + en iyi otomatik alternatif
    E_elle = sorted((a for a in E if a.get("elle")), key=lambda a: (-a["q"], a["g"], a["id"]))
    E_oto = [a for a in E if not a.get("elle")]
    alternatif = False
    if E_elle and not E_oto:
        A_oto = [a for a in A_Kq if not a.get("elle")] or \
            [a for a in adaylar if not a.get("elle") and not a.get("kip_eforu")
             and not (a.get("olcumsuz") and olculu_var)]        # pencere üstü (fazla zekâ eleme yapmaz)
        if A_oto:
            q2 = max(a["q"] for a in A_oto)
            E_oto = [a for a in A_oto if a["q"] >= q2 - delta]
            alternatif = True
            for a in E_oto:
                elenen.pop(a["id"], None)
    elle_lider = bool(E_elle) and (alternatif or not E_oto or E_elle[0]["q"] > max(a["q"] for a in E_oto))
    # F. kapasite (yalnız kalite kümesi içinde)
    engeller = []
    uyg = _kapasiteli(E_oto + E_elle, i, veri, kota, durum, simdi, ust, dout, elenen, engeller)
    rezervdekiler = [a for a in uyg if a.get("katman") == SOR_KATMAN]
    for a in rezervdekiler:
        elenen.setdefault(a["id"], "ana havuz rezervine girer (eşit kalite işi: otomatik değil, SOR)")
    uyg = [a for a in uyg if a.get("katman") != SOR_KATMAN]
    u_C = u_claude(veri, kota, durum, simdi)
    dusus = None

    def _en_katman(L):
        return min((a["katman"] for a in L if not a.get("elle")), default=None)
    k0 = _en_katman(uyg)
    if (k0 is None or k0 >= 4) and E_oto:
        # Zarif düşüş (algoritma 8). D1: kalite kümesindeki modelin alt eforu (Q ve alan efor tabanı korunur);
        # düşüş adayları tüm Q üstü adaylar, efor verimi süzgecinden geçmiş (pahalı üst efor düşüşte açılmaz)
        A_d = [a for a in _efor_verim_suz(A_K0, i, veri, ay, delta, {}) if not a.get("kip_eforu")]
        if kapi:
            A_d, _ = _kapi_suz(A_d, i, veri, delta, olcut, {}, kapi)

        def _hedef_katman(L):
            L = [a for a in L if a["katman"] != SOR_KATMAN]
            # hiç sığan yoksa her katman; yalnız rezervden sığıyorsa yalnız rezerv dışı (≤3) katmanlar
            L = [a for a in L if k0 is None or a["katman"] <= 3]
            if not L:
                return []
            kmin = min(a["katman"] for a in L)
            return [a for a in L if a["katman"] == kmin]
        kim = {(a["kimlik"], a["platform"]): a for a in E_oto}
        d1 = [a for a in A_d if not a.get("elle") and a not in E_oto and (a["kimlik"], a["platform"]) in kim
              and efor_sira(a["efor"]) < efor_sira(kim[(a["kimlik"], a["platform"])]["efor"])
              and a["z_etkin"] >= i["Q"]]
        d1.sort(key=lambda a: (-a["q"], a["id"]))
        k1 = _kapasiteli(d1, i, veri, kota, durum, simdi, ust, dout, {}, engeller)
        rezervdekiler.extend(a for a in k1 if a.get("katman") == SOR_KATMAN)
        u1 = _hedef_katman(k1)
        if u1:
            for a in u1:
                elenen.pop(a["id"], None)
            uyg = u1 + [a for a in uyg if a.get("elle")]
            dusus = "D1"
            uyarilar.append(f"ZARİF DÜŞÜŞ D1: kalite kümesi sığmadı ya da yalnız rezervden; aynı modelin alt eforu "
                            f"(Q{i['Q']} korunur)")
        k0 = _en_katman(uyg)
        if (k0 is None or k0 >= 4) and not ust:
            # D2: Q üstündeki başka model/havuz (üstün aile varken yapılmaz: kalite önce, iş ertelenir)
            secili = {a["id"] for a in uyg}
            d2 = [a for a in A_d if not a.get("elle") and a not in E_oto and a["id"] not in secili
                  and a["z_etkin"] >= i["Q"] and not (a.get("olcumsuz") and olculu_var)]
            k2 = _kapasiteli(d2, i, veri, kota, durum, simdi, ust, dout, {}, engeller)
            rezervdekiler.extend(a for a in k2 if a.get("katman") == SOR_KATMAN)
            u2 = _hedef_katman(k2)
            # otomatik D2 yalnız kalite farkı en çok 2δ iken (daha uzak aday sessizce seçilmez: SOR dis_alt seçeneği)
            q2_tum = max((a["q"] for a in u2), default=None)
            u2 = [a for a in u2 if a["q"] >= q_y - 2 * delta]
            if q2_tum is not None and not u2:
                uyarilar.append(f"D2 yapılmadı: sığan en iyi aday q {q2_tum:.1f}, q* {q_y:.1f} - 2δ altında "
                                f"({(q2_tum - q_y) / delta:.1f}δ); karar kullanıcıda")
            if u2:
                q2 = max(a["q"] for a in u2)
                u2 = [a for a in u2 if a["q"] >= q2 - delta]
                for a in u2:
                    elenen.pop(a["id"], None)
                uyg = u2 + [a for a in uyg if a.get("elle")]
                dusus = "D2"
                uyarilar.append(f"ZARİF DÜŞÜŞ D2: kalite kümesi sığmadı ya da yalnız rezervden; Q{i['Q']} üstündeki "
                                f"en iyi sığan aday (q {q2:.1f} < q* {q_y:.1f}, {(q2 - q_y) / delta:.1f}δ)")
    # ELLE ÖNERİ yalnız kapasitesi sığan elle adaydan (sığmıyorsa okunmamış kota notu)
    elle_oneri = next((a for a in uyg if a.get("elle")), None) if elle_lider else None
    if elle_lider and not elle_oneri:
        uyarilar.append(f"elle kalite lideri {aday_adi(E_elle[0])} ({E_elle[0]['havuz']}) sığmıyor ya da kotası "
                        f"okunmadı (ork kota --agy)")
    agy_acik, agy_neden = agy_kapisi(veri, durum, simdi)
    agy_t4 = bool(not agy_acik and veri.agy_otomatik().get("acik") and agy_neden and "kişisel" in agy_neden
                  and not ({AGY_KABUL, AGY_RET} & kararlar))
    if not agy_acik and veri.agy_otomatik().get("acik") and any(a["yol"] == "agy-elle" for a in E):
        uyarilar.append(agy_neden)
    if not [a for a in uyg if not a.get("elle")]:
        if not _ic and _on_isleme_rotasi(i, veri):
            r = _on_isleme(i, veri, kota, durum, simdi, proje, dout, uyarilar, elenen)
            s_on = r.get("secim") or {}
            if agy_t4 and elle_oneri and elle_oneri["yol"] == "agy-elle" and s_on.get("havuz") in veri.ana_havuzlar():
                # medyayı doğrudan alan agy adayı kapıda; ön işleme Claude'a düşüyor: T4
                t4 = _sor_t4(i, veri, dout, uyarilar, elenen, elle_oneri, s_on, E, ust,
                             cagri_elle=cagri_uret(elle_oneri, veri, i))
                t4["on_isleme"] = r.get("on_isleme")
                return t4
            if elle_oneri:
                r["elle_oneri"] = _ozet(elle_oneri)
                r["cagri_elle"] = cagri_uret(elle_oneri, veri, i)
                r["gerekce"] += f" · ELLE ÖNERİ {aday_etiket(elle_oneri)} (rapora)"
            return r
        if not uyg or not elle_oneri:
            agy_bek = next((a for a in uyg if a.get("elle") and a["yol"] == "agy-elle"), None) if agy_t4 else None
            ctx = {"E": E, "ust": ust, "kapi": kapi, "q_y": q_y, "delta": delta, "A_dis": A_K0, "adaylar": adaylar,
                   "rezervdekiler": rezervdekiler, "agy_bekleyen": agy_bek}
            if not _ic:
                return _sor_ya_da_bekle(i, veri, kota, durum, simdi, dout, uyarilar, elenen, engeller, ctx)
            return _bekle(i, veri, dout, uyarilar, elenen, engeller, "kalite kümesindeki hiçbir havuzda yer yok")
    uyg = _tek_varyant(uyg, delta) if uyg else []
    sira = sirala(uyg, veri, i["Q"], durum, anahtar, dout)
    oto = [a for a in sira if not a.get("elle")]
    if alternatif and oto and elle_oneri:
        uyarilar.append(f"kalite lideri yalnız elle yolda ({aday_etiket(elle_oneri)}); otomatik alternatif seçildi")
    sec_a = oto[0] if oto else None
    ana_h = veri.ana_havuzlar()
    if not sec_a and not _ic and agy_t4 and elle_oneri and elle_oneri["yol"] == "agy-elle":
        # otomatik aday yok, kalite lideri agy'de kapıda: elle köprü yerine önce kapı sorulur
        return _sor_t4(i, veri, dout, uyarilar, elenen, elle_oneri, None, E, ust,
                       cagri_elle=cagri_uret(elle_oneri, veri, i))
    if sec_a and not _ic and sec_a["havuz"] in ana_h and agy_t4:
        # Claude'a düşüyor ama kalite kümesinde sığan agy adayı kapıda bekliyor: Claude varsayılan olmaz, T4 sorulur
        agy_a = next((a for a in sira if a.get("elle") and a["yol"] == "agy-elle"), None)
        if agy_a:
            return _sor_t4(i, veri, dout, uyarilar, elenen, agy_a, sec_a, E, ust,
                           cagri_elle=cagri_uret(agy_a, veri, i))
    hassas_v = i.get("veri") in SIKI_VERI and not i.get("dis_onay")
    if sec_a and not _ic and sec_a["havuz"] in ana_h and sec_a.get("belirsiz") and (ust or i["kritik"] or hassas_v) \
            and "kota_bilinmiyor_devam" not in kararlar:
        # üstün/kritik işte ana havuz okunamıyorsa taban korunduğu kanıtlanamaz: önce kota okunur (T0)
        return _sor_sonuc(i, veri, dout, uyarilar, elenen, "T0",
                          "Claude kotası okunamadı; lider get_usage ile okuyup --claude 5s=..,hafta=.. ile yeniden "
                          "seçmeli (okunamıyorsa kullanıcıdan /usage yüzdelerini iste)",
                          [{"kod": "kota_oku", "ne": "get_usage oku ve yeniden çalıştır"},
                           {"kod": "kota_bilinmiyor_devam", "ne": f"bilinmeyen kotayla {aday_etiket(sec_a)} (taban "
                                                                   f"riski kullanıcıda)", "aday": aday_etiket(sec_a)}],
                          varsayilan="kota_oku", E=[a["id"] for a in E], ust=ust)
    if sec_a:
        dout.setdefault("son_secim", {})[anahtar] = sec_a["id"]
    if sec_a and sec_a.get("katman") == 5:
        uyarilar.append(f"{sec_a['havuz']} rezervinden kullanıldı (başka aday yok)")
    if any(a.get("belirsiz") and a["havuz"] in ana_h for a in uyg):
        uyarilar.append("ana havuz kotası bilinmiyor (katman 4, en son): get_usage oku ve --claude 5s=..,hafta=.. ver")
    if sec_a and sec_a.get("yol") == "agy-oto":
        ao = veri.agy_otomatik()
        if not (ao.get("karar") or {}).get("teyit_edildi", True):
            uyarilar.append("NOT agy otomatik: askı riski ifadesi kullanıcıya teyit ettirilmedi (teyitsiz profil)")
    tanim = olcut_tanimi(i.get("alt_alan"), s)
    if tanim.get("zorunlu_dis_kanit") and not i.get("dogrulayici_var"):
        uyarilar.append(f"DIŞ KANIT ZORUNLU ({i.get('alt_alan')}): DOI/PMID/bağlantı sorgusu yapılmadan çıktı kabul "
                        f"edilmez")
    dogr = None
    if sec_a and not _ic:
        dogr = dogrulayici_sec(sec_a, i, veri, kota, durum, simdi)
        dogr["dis_kanit_zorunlu"] = bool(tanim.get("zorunlu_dis_kanit"))
    satir = gerekce_satiri(i, sec_a or elle_oneri, E, delta, olcut, u_C, elenen, dogr.get("ozet") if dogr else None)
    if kapi:
        satir += " · opus kapısı"
    if doygun:
        satir += f" · doygunluk Q+{(s.get('doygunluk') or {}).get(i['sinif'])}"
    parca_plani = None
    if sec_a and int(i.get("parca") or 1) > 1:
        parca_plani = _isci_dagit(sec_a, oto, int(i["parca"]))
        satir += " · PARÇA " + ", ".join(f"{x['parca']}x {x['aday']}" for x in parca_plani)
    isci_tavan = int(ay["hafif_isci"]) if i["kip"] == "hafif" else None
    if isci_tavan:
        satir += f" · hafif: en çok {isci_tavan} işçi"
    if elle_oneri:
        satir += f" · ELLE ÖNERİ {aday_etiket(elle_oneri)}" + (f" + otomatik {aday_etiket(sec_a)}" if sec_a else "")
    kaskad = None
    if sec_a:
        mer = s.get("yukseltme_merdiveni") or {}
        kaskad = {"basla": aday_adi(sec_a), "merdiven": mer.get(sec_a["platform"]) or [],
                  "en_cok": mer.get("en_cok"), "kural": mer.get("kural"),
                  "dis_dogrulayici": bool(i.get("dogrulayici_var") or i.get("dis_kanit"))}
        if not _ic:
            b = _kaskad_basla(i, veri, durum, simdi, proje, kota, dout)
            if b and b["id"] != sec_a["id"]:
                kk = s.get("kanitli_kaskad") or {}
                kaskad.update({"basla": aday_adi(b), "basla_etiket": aday_etiket(b), "kabul": f"dış kanıt "
                               f"({i.get('dis_kanit')})", "yukselt": aday_adi(sec_a),
                               "en_cok_deneme": kk.get("en_cok_deneme", 2), "cagri_basla": cagri_uret(b, veri, i)})
                satir += f" · KANITLI KASKAD {aday_etiket(b)} -> {aday_adi(sec_a)}"
    return _sonuc("secildi" if sec_a else "elle", i, sec_a, veri, dout, uyarilar, gerekce=satir, elenen=elenen,
                  E=[a["id"] for a in E], delta=delta, olcut=olcut, q_tepe=q_y, ust=ust, dusus=dusus,
                  faz={"u_C": u_C, "rho_C": round(rc["rho"], 3)}, yedekler=[_ozet(a) for a in (oto[1:4] if oto else [])],
                  elle_oneri=_ozet(elle_oneri), dogrulayici=dogr, kaskad=kaskad, isci_tavan=isci_tavan,
                  cagri_elle=cagri_uret(elle_oneri, veri, i) if elle_oneri else None, parca_plani=parca_plani,
                  opus_kapisi=bool(kapi), q_opus=q_opus)


def _pareto(adaylar, elenen):
    """Aynı havuzda q ve maliyet bakımından baskın olan varyant varsa elenir."""
    out = []
    for a in adaylar:
        baskin = next((b for b in adaylar if b is not a and b["havuz"] == a["havuz"] and b["q"] >= a["q"]
                       and b["g"] <= a["g"] and (b["q"] > a["q"] or b["g"] < a["g"])), None)
        if baskin:
            elenen.setdefault(a["id"], f"Pareto: {aday_adi(baskin)} baskın")
        else:
            out.append(a)
    return out or adaylar


def _on_isleme(i, veri, kota, durum, simdi, proje, dout, uyarilar, elenen):
    """Medya kipi otomatik yolda yoksa: rotalardaki 'otomatik' ön işleme hattı (ör. ffmpeg kare + yerel döküm) +
    metin/görsel modeli. Elle yol (ör. agy) varsa rapora öneri olarak eklenir."""
    x = _on_isleme_rotasi(i, veri)
    i2 = dict(i, kipler=["metin", "gorsel"])
    hedef = f"{x['rol']}:{x['efor']}" if x.get("efor") else x["rol"]
    # ön işleme sonrası iş metin+görsel kipinde NORMAL seçimden geçer (kalite kümesi, eşitlikte Claude dışı önce,
    # SOR); rotadaki rol yalnız ipucu: normal seçim model bulamazsa (ölçüm yok, yalnız elle yol) devreye girer
    anahtar = f"{i['alan']}/{i.get('alt_alan') or '-'}/{i['sinif']}/on_isleme"
    r = _normal(i2, veri, kota, durum, simdi, proje, dout, uyarilar, anahtar, False)
    if not r.get("secim") and r.get("durum") not in ("sor",):
        r2 = _zorunlu(hedef, f"ön işleme ipucu {x.get('arac')}", i2, veri, kota, durum, simdi, proje, dout, uyarilar,
                      None)
        if r2.get("secim") or r2.get("durum") == "sor":
            r2["gerekce"] = f"(normal seçim model bulamadı: rota ipucu {hedef}) " + r2.get("gerekce", "")
            if r.get("elle_oneri") and not r2.get("elle_oneri"):
                r2["elle_oneri"], r2["cagri_elle"] = r.get("elle_oneri"), r.get("cagri_elle")
            r = r2
    r["on_isleme"] = x.get("arac")
    r["gerekce"] = f"ÖN İŞLEME ({x.get('arac')}) · " + r.get("gerekce", "")
    r["elle_secenekler"] = _elle_secenekler(veri, i)
    r["elenen_ilk"] = elenen
    return r


def dogrulayici_sec(sec_a, i, veri, kota, durum, simdi):
    """Farklı aile; dış kanıt varsa önce o. Öz-denetim yok."""
    out = {"dis_kanit": bool(i.get("dogrulayici_var"))}
    istek = {k: i.get(k) for k in ("alan", "alt_alan", "sinif", "kipler", "veri", "host", "ib", "dizin", "olgu",
                                   "dis_onay")}
    istek.update({"tur": "dogrulama", "haric_aile": sec_a["aile"], "kip": "normal", "sef": i.get("sef")})
    if i.get("_tavan_kalkti") in TAVAN_KALDIRAN.values():
        istek["tavan_yok"] = True
    try:
        r = sec(istek, veri, kota, durum, simdi, _ic=True)
    except VeriHatasi:
        r = {"secim": None}
    out["model"] = r.get("secim")
    out["zayif_dogrulama"] = False
    if not out["model"]:
        # belge sırasının 4. basamağı: aynı aile, farklı model (zayıf doğrulama etiketiyle)
        ist2 = dict(istek, haric_aile=None, haric_kimlik=sec_a["kimlik"])
        try:
            r2 = sec(ist2, veri, kota, durum, simdi, _ic=True)
        except VeriHatasi:
            r2 = {"secim": None}
        if r2.get("secim"):
            out["model"], out["zayif_dogrulama"] = r2["secim"], True
    parcalar = []
    if out["dis_kanit"]:
        parcalar.append("dış kanıt")
    if out["model"]:
        parcalar.append(f"{out['model']['rol'] or out['model']['kimlik']}@{out['model']['efor']}"
                        + (" (zayıf: aynı aile)" if out["zayif_dogrulama"] else ""))
    out["ozet"] = " + ".join(parcalar) or "doğrulanamadı (uygun doğrulayıcı yok)"
    return out


def neden(hedef, sinif, veri, kota=None, durum=None, simdi=None, istek=None):
    """'neden <model|rol> <sinif>': hedefin seçilmeme/seçilme gerekçesi."""
    ist = dict(istek or {})
    ist.setdefault("sinif", sinif)
    r = sec(ist, veri, kota, durum, simdi)
    f, ad, ef = _hedef_filtre(hedef, veri)
    satirlar = []
    sec_a = r.get("secim")
    if sec_a and f(sec_a["kimlik"], sec_a["rol"], sec_a["efor"]):
        satirlar.append(f"{hedef}: SEÇİLDİ ({r['gerekce']})")
    for aid, nd in sorted((r.get("elenen") or {}).items()):
        kim_rol = aid.split("|")[0]
        ad_, _, ef_ = kim_rol.partition("@")
        if ad_ == ad and (ef is None or not ef_ or ef_ == ef):
            satirlar.append(f"{aid}: {nd}")
    if not satirlar:
        satirlar.append(f"{hedef}: elenmedi ama sıralamada geride (seçilen: "
                        f"{aday_etiket(sec_a) if sec_a else 'yok'})")
    return satirlar, r


# ================================================================== çok parçalı plan (tasarım 9.3)
def parca_tavani(istek, p, plan, veri):
    """R16 plan/sürü parçası: tavanı yalnız kullanıcı kaldırır (CLI --tavan-yok ya da plan düzeyi tavan_yok). Parça
    düzeyindeki tavan_yok ve sor_yanit=tavan_yok yok sayılır; parça zorla/ultra tavanı kaldırmaz (ihlalde SOR T6);
    parçanın kendi şefi yalnız daha sıkıysa geçer. Dönüş (istek, uyarılar)."""
    uy = []
    istek = dict(istek)
    plan = plan or {}
    if p.get("tavan_yok"):
        uy.append("UYARI parça düzeyi tavan_yok yok sayıldı: tavanı yalnız kullanıcı kaldırır (CLI --tavan-yok ya da "
                  "plan düzeyi tavan_yok)")
    if istek.get("sor_yanit") == TAVAN_YOK and not plan.get("tavan_yok"):
        istek.pop("sor_yanit")
        uy.append("UYARI parça düzeyi sor_yanit=tavan_yok yok sayıldı: yanıtı kullanıcı CLI'dan verir")
    sef = plan.get("sef")
    if p.get("sef"):
        sec_, parca_mi = sef_siki(p["sef"], sef, veri)
        if sef and not parca_mi:
            uy.append(f"UYARI parça şefi ({p['sef']}) plan şefinden gevşek: plan şefi uygulandı")
        sef = sec_
    if sef:
        istek["sef"] = sef
    if plan.get("tavan_yok"):
        istek["tavan_yok"] = True
    else:
        istek["_tavan_kilit"] = True
    return istek, uy


PARCA_DISI = ("id", "brief", "cikti", "desen", "bagimli", "sema", "max_tokens", "dogrulama", "zaman_asimi_sn",
              "turkce", "cevap_deseni", "k", "yargic")
DIS_YOLLAR = ("bedava-api", "agy-oto", "codex-exec")


def _lider_fiyat(veri):
    """İnce lider maliyeti için liderin fiyatı: faz.lider_rol > ana havuzdaki en pahalı girdi fiyatlı model."""
    rol = veri.faz().get("lider_rol")
    if rol and (veri.roller.get(rol) or {}).get("aktif"):
        f = (veri.model(veri.roller[rol]["aktif"]) or {}).get("fiyat")
        if f:
            return f
    en = None
    for pid, p in veri.platformlar.items():
        for e in p.get("erisim", []):
            if e.get("havuz") in veri.ana_havuzlar():
                f = (veri.model(e.get("kimlik") or "") or {}).get("fiyat") or {}
                if f.get("girdi") is not None and (en is None or f["girdi"] > en["girdi"]):
                    en = f
    return en or {"girdi": 0.0, "cikti": 0.0}


def plan_sec(plan, veri, kota=None, durum=None, simdi=None):
    """Parçaları sırayla seçer; her seçimin payı yerel kota kopyasından düşülür (kota rezervasyonu: 10 parça aynı
    havuzu 10 kez saymaz). Dış parçalar `suru_plani` (ork suru calistir girdisi), Claude parçaları `claude_isleri`
    (hazır Agent satırı), kullanıcı kararı gerekenler tek birleşik `sor`. Model çağrısı yok."""
    import copy as _c
    simdi = simdi or simdi_utc()
    k = _c.deepcopy(kota or {})
    d = _c.deepcopy(durum or {})
    d.pop("kota_ema", None)
    parcalar = list((plan or {}).get("parcalar") or [])
    ay = ayar(veri)
    mikro = [p for p in parcalar if p.get("boyut") == "mikro"]
    paylasim = min(8, len(mikro)) if mikro else 1
    out, isler, claude_isleri, sorlar, dout_top = [], [], [], [], {}
    c_alt_top = c_claude = 0.0
    sayac = Counter()
    for n, p in enumerate(parcalar):
        pid = str(p.get("id") or f"p{n + 1}")
        if p.get("_hata"):                    # ad doğrulaması (ork.py) geçmeyen parça: sessizce genel Z'ye düşülmez
            out.append({"id": pid, "durum": "hata", "secim": None, "gerekce": "HATA " + "; ".join(p["_hata"]),
                        "cagri": None})
            continue
        istek = {x: v for x, v in p.items() if x not in PARCA_DISI and not x.startswith("_")
                 and x not in ("sef", "tavan_yok")}
        uy_parca = []
        try:
            istek, uy_parca = parca_tavani(istek, p, plan, veri)
        except VeriHatasi as e:
            out.append({"id": pid, "durum": "hata", "secim": None, "gerekce": f"HATA {e}", "cagri": None})
            continue
        if p.get("brief") and not p.get("tok_tahmin"):
            istek["brief"] = p["brief"]       # brief boyutundan token tahmini (AA görev birimi yerine)
        if p.get("boyut") == "mikro":
            istek["sabit_yuk_paylasim"] = paylasim
        try:
            r = sec(istek, veri, k, d, simdi)
        except VeriHatasi as e:
            out.append({"id": pid, "durum": "hata", "secim": None, "gerekce": f"HATA {e}", "cagri": None})
            continue
        dg = r.pop("durum_guncel", {}) or {}
        for anahtar, deger in dg.items():
            if anahtar == "kota_ema":
                continue
            if isinstance(deger, dict):
                d.setdefault(anahtar, {}).update(deger)
                dout_top.setdefault(anahtar, {}).update(deger)
        a = r.get("secim")
        satir = {"id": pid, "durum": r["durum"], "secim": a, "gerekce": r.get("gerekce"), "cagri": r.get("cagri"),
                 "uyarilar": uy_parca + list(r.get("uyarilar") or []), "sef": r.get("sef")}
        # Claude-yalnız karşılığı (tasarruf tahmini): aynı istek yalnız ana havuzla, rezervasyonsuz anlıkla
        try:
            # karşılaştırma tabanı "her şey Claude'da olsaydı" maliyeti: ana havuz tam kotalı varsayılır
            k_alt = _c.deepcopy(kota or {})
            for hid in veri.ana_havuzlar():
                hk = (k_alt.setdefault("havuzlar", {}).get(hid)) or {}
                pens_ = {w: dict(x, kalan=1.0) for w, x in (hk.get("pencereler") or {}).items()} or \
                    {"hafta": {"kalan": 1.0, "sifirlama": None}, "5s": {"kalan": 1.0, "sifirlama": None}}
                k_alt["havuzlar"][hid] = {"durum": "ok", "pencereler": pens_}
            d_alt = _c.deepcopy(durum or {})
            for hid in veri.ana_havuzlar():
                (d_alt.get("kota_ema") or {}).pop(hid, None)
            ra = sec(dict(istek, yalniz_havuz=sorted(veri.ana_havuzlar())), veri, k_alt, d_alt, simdi, _ic=True)
            c_alt = float(((ra.get("secim") or {}).get("c")) or 0.0)
        except VeriHatasi:
            c_alt = 0.0
        satir["c_claude_alternatif"] = round(c_alt, 4)
        if r["durum"] == "secildi" and a:
            c_alt_top += c_alt               # tasarruf: yalnız gönderilen parçalar iki tarafta da sayılır
            for w, pay in (a.get("paylar") or {}).items():
                pen = (((k.get("havuzlar") or {}).get(a["havuz"]) or {}).get("pencereler") or {}).get(w)
                if isinstance(pen, dict) and pen.get("kalan") is not None:
                    pen["kalan"] = max(0.0, float(pen["kalan"]) - float(pay))
            c = r.get("cagri") or {}
            if a["havuz"] in veri.ana_havuzlar():
                c_claude += float(a.get("c") or 0.0)
                claude_isleri.append({"id": pid, "cagri": c.get("komut"), "takma": c.get("takma"), "efor": a["efor"],
                                      "brief": p.get("brief"), "cikti": p.get("cikti"),
                                      "sozlesme": f"çıktıyı {p.get('cikti') or '<dosya>'} dosyasına yaz, en çok 10 "
                                                  f"satır özet dön"})
                sayac["claude"] += 1
            elif a["yol"] in DIS_YOLLAR:
                isler.append({"id": pid, "brief": p.get("brief"), "cikti": p.get("cikti"),
                              "hedef": {"yol": a["yol"], "platform": a["platform"], "havuz": a["havuz"],
                                        "model": c.get("model"), "kimlik": a["kimlik"], "efor": a["efor"],
                                        "efor_bayragi": bool(a.get("efor_bayragi"))},
                              "veri": r["istek"].get("veri"), "sinif": r["istek"].get("sinif"),
                              "alan": r["istek"].get("alan"), "alt_alan": r["istek"].get("alt_alan"),
                              "boyut": p.get("boyut"),
                              **{x: p[x] for x in ("desen", "bagimli", "sema", "max_tokens", "dogrulama",
                                                   "zaman_asimi_sn", "turkce", "cevap_deseni", "k", "yargic")
                                 if p.get(x) is not None}})
                sayac[f"{aday_adi(a)} ({a['platform']})"] += 1
            else:
                sayac[f"{aday_adi(a)} ({a['yol']})"] += 1
        elif r["durum"] in ("sor", "onay_gerekli"):
            # onay gerektiren seçim (Q altı zorunlu hedef) onaysız gönderilmez: birleşik SOR'a girer
            sorlar.append({"id": pid, "tetik": r.get("tetik") or "onay", "soru": r.get("soru") or
                           "; ".join(u for u in r.get("uyarilar") or [] if "onay" in u) or "kullanıcı onayı gerekir",
                           "secenekler": r.get("secenekler") or [{"kod": "onay", "ne": "bu seçimle çalıştır",
                                                                  "aday": aday_etiket(a) if a else None},
                                                                 {"kod": "bekle", "ne": "çalıştırma"}]})
        out.append(satir)
    lf = _lider_fiyat(veri)
    n_dis = len(isler)
    c_lider = n_dis * (float(ay["lider_brief_cikis_tok"]) * float(lf.get("cikti") or 0)
                       + float(ay["lider_ozet_giris_tok"]) * float(lf.get("girdi") or 0)) / 1e6
    ince = c_claude + c_lider
    tasarruf = {"claude_alternatif_usd_e": round(c_alt_top, 3), "ince_lider_claude_usd_e": round(ince, 3),
                "tasarruf_usd_e": round(c_alt_top - ince, 3),
                "oran": round(1 - ince / c_alt_top, 3) if c_alt_top > 0 else None,
                "not": "lider planlama tokenı iki durumda da aynıdır; lider brief + özet okuma payı eklendi"}
    ozet = ", ".join(f"{v}x {k_}" for k_, v in sorted(sayac.items()) if k_ != "claude")
    ozet = (ozet + ", " if ozet else "") + f"{sayac.get('claude', 0)} claude"
    sor = None
    if sorlar:
        sor = {"soru": f"{len(sorlar)} parça kullanıcı kararı bekliyor: " + " | ".join(
            f"{x['id']}: {x['soru']}" for x in sorlar), "parcalar": sorlar, "varsayilan": "bekle"}
    return {"durum": "sor" if sor else "plan", "is_id": (plan or {}).get("is_id"), "parcalar": out,
            "suru_plani": dict({"is_id": (plan or {}).get("is_id"), "isler": isler},
                               **{k_: plan[k_] for k_ in ("sef", "tavan_yok") if (plan or {}).get(k_)}),
            "claude_isleri": claude_isleri,
            "sor": sor, "ozet": ozet, "tasarruf": tasarruf, "durum_guncel": dout_top}


# ================================================================== uyarlanır ağırlık (tasarım 8.3)
def tempo_agirligi(faz, durum, hid, simdi=None):
    """o_p: durum.tempo_agirlik_uyarlanmis (7 gün içinde ve faz.uyarlanir_agirlik açıksa) > faz.tempo_agirlik > 1.
    Güncelleme günde birdir (uyarlanir_agirlik); kayıt bir hafta geçerli, sonra statik değere döner."""
    statik = float((faz.get("tempo_agirlik") or {}).get(hid, 1.0))
    if not (faz.get("uyarlanir_agirlik") or {}).get("acik"):
        return statik
    x = ((durum or {}).get("tempo_agirlik_uyarlanmis") or {}).get(hid) or {}
    z = zaman_coz(x.get("zaman"))
    if z is None or not isinstance(x.get("o"), (int, float)):
        return statik
    if ((simdi or simdi_utc()) - z).total_seconds() > 7 * 86400:
        return statik
    return float(x["o"])


def uyarlanir_agirlik(veri, kota, durum, gecmis, simdi=None):
    """Günde bir: ḋ = son min(3 gün, sıfırlamadan beri) harcama hızı (pp/gün); artık L = m - ḋ·t_gün.
    L > 0.10·U -> o ← min(ust, o·adim); m/ḋ < t_gün - 1 (öngörülen erken tükenme) -> o ← max(alt, o/adim).
    Dönüş {hid: {o, zaman, neden}} (yalnız ana havuz dışı, kotası okunan, hafta penceresi olan havuzlar)."""
    simdi = simdi or simdi_utc()
    faz = veri.faz()
    ua = faz.get("uyarlanir_agirlik") or {}
    if not ua.get("acik"):
        return {}
    alt, ust, adim = float(ua.get("alt", 1.0)), float(ua.get("ust", 3.0)), float(ua.get("adim", 1.25))
    ana = veri.ana_havuzlar()
    out = {}
    for hid, h in sorted(veri.havuzlar.items()):
        p = veri.platformlar.get(h.get("platform"), {})
        if hid in ana or h.get("bedava") or p.get("ucret") == "bedava" or _yerel_mi(h, p):
            continue
        pens = pencereler(hid, h, veri, kota, durum, simdi, {})
        x = (pens or {}).get("hafta")
        if not x or x["belirsiz"] or not x.get("t_dk"):
            continue
        L = sorted((k for k in gecmis or [] if k.get("havuz") == hid and k.get("pencere") == "hafta"
                    and isinstance(k.get("kalan"), (int, float)) and zaman_coz(k.get("zaman"))),
                   key=lambda k: zaman_coz(k["zaman"]))
        sf = x["sifirlama"].isoformat() if x.get("sifirlama") else None
        L = [k for k in L if (simdi - zaman_coz(k["zaman"])).total_seconds() <= 3 * 86400
             and (sf is None or k.get("sifirlama") in (None, sf) or zaman_coz(k.get("sifirlama")) == x["sifirlama"])]
        if len(L) < 2:
            continue
        gun = (zaman_coz(L[-1]["zaman"]) - zaman_coz(L[0]["zaman"])).total_seconds() / 86400.0
        if gun < 0.5:
            continue
        hiz = max(0.0, (float(L[0]["kalan"]) - float(L[-1]["kalan"])) / gun)       # oran/gün
        t_gun = x["t_dk"] / 1440.0
        U = 1.0 - x["taban"]
        # günde bir güncelleme (idempotent): son kayıt 24 sa içindeyse yeni değer üretilmez; taban, kayıtlı o
        # (24 sa'ten eskiyse de) yoksa statik o. Her `ork plan` çalışması ağırlığı katlamaz.
        kay = ((durum or {}).get("tempo_agirlik_uyarlanmis") or {}).get(hid) or {}
        kz = zaman_coz(kay.get("zaman"))
        if kz is not None and 0 <= (simdi - kz).total_seconds() < 86400:
            continue
        statik = float((faz.get("tempo_agirlik") or {}).get(hid, 1.0))
        o = float(kay["o"]) if isinstance(kay.get("o"), (int, float)) else statik
        artik = x["m_ham"] - hiz * t_gun
        if artik > 0.10 * U:
            yeni, neden = min(ust, o * adim), f"öngörülen artık %{artik * 100:.0f} > %10·U"
        elif hiz > 0 and x["m_ham"] / hiz < t_gun - 1:
            yeni, neden = max(alt, o / adim), f"öngörülen tükenme {x['m_ham'] / hiz:.1f} gün < {t_gun - 1:.1f}"
        else:
            continue
        out[hid] = {"o": round(yeni, 3), "zaman": simdi.isoformat(timespec="seconds"), "neden": neden}
    return out


# ================================================================== hafta planı (tasarım 8.8)
def hafta_plani(veri, kota, durum, simdi=None, olc=None, gecmis=None):
    """Model çağırmayan hafta planı: havuz başına kalan, taban, R(t), sıfırlamaya gün, hedef/gün = (m - R)/t_gün,
    ρ, o·ρ, ÖNDE/GERİDE/ELLE; bugünkü sıra (bedava -> ÖNDE -> GERİDE dış havuzlar dis_sira ile -> ana havuz)."""
    simdi = simdi or simdi_utc()
    ay = ayar(veri)
    faz = veri.faz()
    tmin = float(ay["tempo_t_min"])
    rc = rho_claude(veri, kota, durum, simdi)
    ana = veri.ana_havuzlar()
    satirlar, notlar = [], []
    agy_acik, agy_neden = agy_kapisi(veri, durum, simdi)
    agy_platform = {pid for pid, p in veri.platformlar.items()
                    if any((e.get("yol") or p.get("yol")) in AGY_YOLLARI for e in p.get("erisim", []))}
    if agy_platform and not agy_acik:
        notlar.append(f"agy havuzları ELLE ({agy_neden}): otomatik sıradan çıkarıldı")
    for hid, h in sorted(veri.havuzlar.items()):
        p = veri.platformlar.get(h.get("platform"), {})
        if _yerel_mi(h, p) or p.get("durum", "aktif") != "aktif":
            continue
        pens = pencereler(hid, h, veri, kota, durum, simdi, {})
        if not pens:
            satirlar.append({"havuz": hid, "kalan": 0.0, "taban": 0.0, "R": 0.0, "gun": 0.0, "hedef_pp_gun": 0.0,
                             "rho": 0.0, "o_rho": 0.0, "durum": "KAPALI"})
            continue
        karar = [w for w in veri.karar_pencereleri(hid) if w in pens] or list(pens)
        w = "hafta" if "hafta" in pens else karar[0]
        x = pens[w]
        bedava = bool(h.get("bedava")) or p.get("ucret") == "bedava"
        rz = veri.rezerv(hid)
        R = _rezerv_miktar(rz, x["taban"], float(faz["claude_esik_u"]) if hid in ana else None,
                           _azalma(x, hid in ana, faz, rz))
        gun = (x["t_dk"] or 0) / 1440.0
        U = 1.0 - x["taban"]
        rho = 0.0 if U - R <= 0 else max(0.0, x["m"] - R) / ((U - R) * _x(x, tmin))
        o = tempo_agirligi(faz, durum, hid, simdi)
        if bedava:
            d = "BEDAVA"
        elif hid in ana:
            d = "ANA"
        elif h.get("platform") in agy_platform and not agy_acik:
            d = "ELLE"
        elif x["belirsiz"]:
            d = "BİLİNMİYOR"
        else:
            # seçiciyle aynı histerezisli karar (durum.onde; plan durumu değiştirmez)
            d = "ÖNDE" if _onde(durum, hid, o * rho, rc["rho"], float(faz.get("tempo_bant", 0.1)), {}) else "GERİDE"
        satirlar.append({"havuz": hid, "pencere": w, "kalan": x["k_ham"], "taban": x["taban"], "R": round(R, 4),
                         "gun": round(gun, 2), "hedef_pp_gun": round(max(0.0, x["m_ham"] - R) / max(gun, 1e-6) * 100, 1)
                         if gun > 0 else 0.0, "rho": round(rho, 3), "o_rho": round(o * rho, 3), "durum": d,
                         "sifirlama": x["sifirlama"].isoformat() if x["sifirlama"] else None})
        ek = (((kota or {}).get("havuzlar") or {}).get(hid) or {}).get("ek") or {}
        rk = ek.get("reset_kredisi") or {}
        if int(rk.get("adet") or 0) > 0:
            notlar.append(f"{hid}: ücretsiz sıfırlama kredisi {rk['adet']} (son {rk.get('son') or '?'}) · kullanma "
                          f"önerisi: yalnız haftanın ilk yarısında havuz biterse ve ona özgü iş bekliyorsa; geri "
                          f"alınamaz, SOR T3 ile")
    ds = list(faz.get("dis_sira") or [])

    def sira_anahtari(x):
        return ds.index(x["havuz"]) if x["havuz"] in ds else len(ds)
    # bugünkü sıra (R3): bedava -> ÖNDE dış -> GERİDE dış -> Claude -> bilinmeyen; ELLE havuzlar otomatik sırada yok
    sira = [x["havuz"] for x in satirlar if x["durum"] == "BEDAVA"]
    sira += [x["havuz"] for x in sorted((x for x in satirlar if x["durum"] == "ÖNDE"), key=sira_anahtari)]
    geride = [x["havuz"] for x in sorted((x for x in satirlar if x["durum"] == "GERİDE"), key=sira_anahtari)]
    anah = [x["havuz"] for x in satirlar if x["durum"] == "ANA"]
    if rc["rho"] >= float(faz.get("claude_kullan_kaybet_rho", 1.5)) and not rc.get("belirsiz"):
        sira += anah + geride             # Claude kullan-ya-da-kaybet: fazlası yanacak, GERİDE dış havuzdan önce
        notlar.append(f"Claude kullan-ya-da-kaybet (ρ_C {rc['rho']:.2f}): eşit kalitede GERİDE dış havuzdan önce")
    else:
        sira += geride + anah
    sira += [x["havuz"] for x in sorted((x for x in satirlar if x["durum"] == "BİLİNMİYOR"), key=sira_anahtari)]
    uy = uyarlanir_agirlik(veri, kota, durum, gecmis, simdi) if gecmis else {}
    for hid, x in uy.items():
        notlar.append(f"{hid}: tempo ağırlığı -> {x['o']} ({x['neden']})")
    if olc:
        dis = [k for k in olc if k.get("havuz") not in ana]
        notlar.append(f"son 7 gün: {len(dis)} çağrı Claude dışında, {len(olc) - len(dis)} Claude'da (olc)")
    return {"zaman": simdi.isoformat(timespec="seconds"), "rho_C": round(rc["rho"], 3), "havuzlar": satirlar,
            "sira": sira, "notlar": notlar, "tempo_agirlik_uyarlanmis": uy}
