"""Veri katmanı: yükleme sırası, katman birleştirme, hafif şema doğrulama, z_olcek kilidi, rol ve yasak çözümü.

Yükleme sırası:
  kişisel (kullanici-kurallari, platformlar): ORKESTRA_KISISEL > ~/.orkestra/<ad>.json (ORKESTRA_DIR; yalnız sema >= 7)
      > data/<ad>.json (eski yerleşim, uyarıyla) > data/<ad>.ornek.json (taze klon; `katman: ornek`)
  genel (modeller, imzalar, siniflar): data/<ad>.json + ~/.orkestra/<ad>.yerel.json yerel yama katmanı
      (yalnız değişen anahtarlar; `guncelle` buraya yazar, depo ağacı kirlenmez, üst akım güncellemesi maskelenmez).
Kişisel dosyalar skill klasöründe tutulmaz: senkron kopyalarına (Codex, Antigravity) ve depoya girmez.
Kod hiçbir model adını, sürümünü ya da platform adını sabit tutmaz: hepsi data/ altından gelir.
"""
import copy
import fnmatch
import json
import os
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

EFOR_SIRA = ["none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"]
KIP_EFORLARI = {"max", "ultra", "ultracode"}          # aday listesinde varsayılan olarak yok (bkz. secici)
VERI_ADLARI = ("modeller", "imzalar", "siniflar", "kullanici-kurallari", "platformlar")
GENEL = {"modeller", "imzalar", "siniflar"}
HASSAS_VERI = {"bilinmiyor", "kisisel", "gizli", "saglik"}
# platformlar.json `isci_yolu` -> seçicinin erişim yolu adı
YOL_ESLE = {"agent-araci": "claude-agent", "claude-agent": "claude-agent", "codex-exec": "codex-exec",
            "agy-elle": "agy-elle", "agy-oto": "agy-oto", "bedava-api": "bedava-api", "yerel": "yerel",
            "gui-elle": "elle", "elle": "elle", "arac": "arac"}
AGY_YOLLARI = {"agy-elle", "agy-oto"}          # otomatik çağrı kapısına (agy_otomatik) bağlı yol
# host adı takma adları (platformlar.json host_varsayilan: "claude")
HOST_ESLE = {"claude": "claude-code", "claude-code": "claude-code", "codex": "codex", "agy": "agy"}
OKUYUCU_ESLE = {"bedava_api_quota": "bedava_api", "bedava_api": "bedava_api", "claude_get_usage": "claude_get_usage",
                "codex_app_server": "codex_app_server", "agy_usage": "agy_usage"}


class VeriHatasi(Exception):
    """Veri dosyası eksik, bozuk ya da tutarsız (ör. z_olcek karışık)."""


# ------------------------------------------------------------------ yollar
def skill_kok():
    return Path(__file__).resolve().parents[2]


def veri_dizini():
    return Path(os.environ.get("ORKESTRA_VERI") or (skill_kok() / "data"))


def durum_dizini():
    return Path(os.environ.get("ORKESTRA_DIR") or (Path.home() / ".orkestra"))


def kisisel_dizini():
    """Kişisel katman (kurallar, platformlar, *.yerel.json): ORKESTRA_KISISEL > durum dizini. Durum dosyaları
    (durum.json, olc.jsonl, kota-anlik.json) her zaman ORKESTRA_DIR'de kalır."""
    return Path(os.environ.get("ORKESTRA_KISISEL") or durum_dizini())


def simdi_utc():
    return datetime.now(timezone.utc)


def zaman_coz(x):
    """ISO-8601 dizgi ya da epoch -> aware datetime; bozuksa None."""
    if isinstance(x, datetime):
        return x if x.tzinfo else x.replace(tzinfo=timezone.utc)
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        try:
            return datetime.fromtimestamp(x, timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if not isinstance(x, str) or not x:
        return None
    try:
        d = datetime.fromisoformat(x.replace("Z", "+00:00"))
    except ValueError:
        try:
            d = datetime.fromisoformat(x[:10])
        except ValueError:
            return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


# ------------------------------------------------------------------ JSON G/Ç
def json_oku(yol):
    """UTF-8 (BOM'lu da) JSON okur. Yoksa None; bozuksa VeriHatasi."""
    yol = Path(yol)
    if not yol.exists():
        return None
    try:
        metin = yol.read_text(encoding="utf-8-sig")
    except OSError as e:
        raise VeriHatasi(f"okunamadı: {yol.name} ({type(e).__name__})")
    if not metin.strip():
        return {}
    try:
        return json.loads(metin)
    except ValueError as e:
        raise VeriHatasi(f"bozuk JSON: {yol.name} ({e})")


_YAZ_KILIT = threading.Lock()


def atomik_yaz(yol, veri):
    """Geçici dosya + os.replace. Windows'ta hedef o an açıksa birkaç kez dener."""
    yol = Path(yol)
    yol.parent.mkdir(parents=True, exist_ok=True)
    with _YAZ_KILIT:
        tmp = yol.with_name(f"{yol.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            json.dump(veri, f, ensure_ascii=False, indent=2)
            f.write("\n")
        for i in range(8):
            try:
                os.replace(tmp, yol)
                return yol
            except PermissionError:
                if i == 7:
                    try:
                        os.unlink(tmp)
                    finally:
                        raise
                time.sleep(0.02 * (i + 1))
    return yol


YEREL_KATMAN_ANAHTARLARI = ("modeller", "roller", "liderler", "rotalar", "gorsel_modeller", "platformlar")


def yerel_birlestir(taban, yerel):
    """Genel dosya + yerel yama: sözlük bölümlerinde kayıt düzeyinde üzerine yazma (None = sil), diğer kökler
    doğrudan. Taban değiştirilmez."""
    out = copy.deepcopy(taban or {})
    for k, v in (yerel or {}).items():
        if k in ("sema", "katman", "aciklama"):
            continue
        if k in YEREL_KATMAN_ANAHTARLARI and isinstance(v, dict):
            d = out.setdefault(k, {})
            for kk, vv in v.items():
                if vv is None:
                    d.pop(kk, None)
                else:
                    d[kk] = vv
        else:
            out[k] = v
    return out


def yerel_fark(taban, yeni):
    """yerel_birlestir'in tersi: tabandan farklı olan kayıtlar (yama). Silinen kayıt None."""
    fark = {"sema": 7, "katman": "yerel", "aciklama": "guncelle yerel yaması; genel dosyanın üstüne birleşir"}
    for k in set(taban or {}) | set(yeni or {}):
        a, b = (taban or {}).get(k), (yeni or {}).get(k)
        if a == b:
            continue
        if k in YEREL_KATMAN_ANAHTARLARI and isinstance(a, dict) and isinstance(b, dict):
            d = {kk: b.get(kk) for kk in set(a) | set(b) if a.get(kk) != b.get(kk)}
            if d:
                fark[k] = d
        else:
            fark[k] = b
    return fark


def yukle_bir(ad, vdir=None, ddir=None):
    """(sözlük, kaynak_yolu, notlar). Bulunamazsa ({}, None, [not])."""
    vdir = Path(vdir) if vdir else veri_dizini()
    ddir = Path(ddir) if ddir else kisisel_dizini()
    notlar = []
    if ad in GENEL:
        aday = vdir / f"{ad}.json"
        if not aday.exists():
            notlar.append(f"{ad}.json bulunamadı")
            return {}, None, notlar
        d = json_oku(aday)
        if not isinstance(d, dict):
            raise VeriHatasi(f"{aday.name} kökü nesne değil")
        yer = ddir / f"{ad}.yerel.json"
        if yer.exists():
            y = json_oku(yer)
            if isinstance(y, dict) and int(y.get("sema") or 0) >= 7:
                d = yerel_birlestir(d, y)
                notlar.append(f"{ad}: yerel yama katmanı birleşti ({yer.name})")
            else:
                notlar.append(f"{yer} v7 şemasında değil; yok sayıldı")
        return d, aday, notlar
    ust = ddir / f"{ad}.json"
    if ust.exists():
        d = json_oku(ust)
        if isinstance(d, dict) and int(d.get("sema") or d.get("surum") or 0) >= 7:
            return d, ust, notlar
        notlar.append(f"{ust} v7 şemasında değil (sema<7); yok sayıldı")
    for aday in (vdir / f"{ad}.json", vdir / f"{ad}.ornek.json"):
        if aday.exists():
            d = json_oku(aday)
            if not isinstance(d, dict):
                raise VeriHatasi(f"{aday.name} kökü nesne değil")
            if aday.name.endswith(".ornek.json"):
                notlar.append(f"{ad}: kişisel kopya yok, ÖRNEK dosya kullanıldı (ork kur ile {ddir} altına kopyala "
                              f"ve kendi planına göre düzenle)")
            else:
                notlar.append(f"{ad}: kişisel dosya skill klasöründe ({aday.parent.name}/); {ddir} altına taşı "
                              f"(senkron kopyalarına girmesin)")
            return d, aday, notlar
    notlar.append(f"{ad}.json bulunamadı")
    return {}, None, notlar


# ------------------------------------------------------------------ hafif JSON Schema doğrulayıcı (2020-12 alt kümesi)
_TUR = {"object": dict, "array": list, "string": str, "boolean": bool, "null": type(None)}


def _tur_uygun(x, t):
    if t == "integer":
        return isinstance(x, int) and not isinstance(x, bool)
    if t == "number":
        return isinstance(x, (int, float)) and not isinstance(x, bool)
    return isinstance(x, _TUR.get(t, object))


def sema_dogrula(x, sema, yol="$", kok=None, hatalar=None):
    """Desteklenen: type, required, properties, additionalProperties, patternProperties, items, enum, const,
    minimum, maximum, minItems, pattern, anyOf, oneOf, allOf, $ref (#/$defs/...). Dönüş: hata listesi."""
    hatalar = [] if hatalar is None else hatalar
    kok = sema if kok is None else kok
    if not isinstance(sema, dict):
        return hatalar
    if "$ref" in sema:
        ref = sema["$ref"]
        if ref.startswith("#/"):
            hedef = kok
            for p in ref[2:].split("/"):
                hedef = hedef.get(p, {}) if isinstance(hedef, dict) else {}
            sema_dogrula(x, hedef, yol, kok, hatalar)
    t = sema.get("type")
    if t is not None:
        turler = t if isinstance(t, list) else [t]
        if not any(_tur_uygun(x, tt) for tt in turler):
            hatalar.append(f"{yol}: tür {turler} bekleniyordu, {type(x).__name__} geldi")
            return hatalar
    if "enum" in sema and x not in sema["enum"]:
        hatalar.append(f"{yol}: {x!r} izinli değil {sema['enum']}")
    if "const" in sema and x != sema["const"]:
        hatalar.append(f"{yol}: {x!r} != {sema['const']!r}")
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        if "minimum" in sema and x < sema["minimum"]:
            hatalar.append(f"{yol}: {x} < {sema['minimum']}")
        if "maximum" in sema and x > sema["maximum"]:
            hatalar.append(f"{yol}: {x} > {sema['maximum']}")
    if isinstance(x, str) and "pattern" in sema and not re.search(sema["pattern"], x):
        hatalar.append(f"{yol}: desen uymuyor")
    if isinstance(x, dict):
        for r in sema.get("required", []):
            if r not in x:
                hatalar.append(f"{yol}: zorunlu alan yok: {r}")
        props = sema.get("properties", {})
        pprops = sema.get("patternProperties", {})
        ek = sema.get("additionalProperties", True)
        for k, v in x.items():
            if k in props:
                sema_dogrula(v, props[k], f"{yol}.{k}", kok, hatalar)
                continue
            eslesti = False
            for desen, alt in pprops.items():
                if re.search(desen, k):
                    sema_dogrula(v, alt, f"{yol}.{k}", kok, hatalar)
                    eslesti = True
            if not eslesti:
                if ek is False:
                    hatalar.append(f"{yol}: beklenmeyen alan: {k}")
                elif isinstance(ek, dict):
                    sema_dogrula(v, ek, f"{yol}.{k}", kok, hatalar)
    if isinstance(x, list):
        if "minItems" in sema and len(x) < sema["minItems"]:
            hatalar.append(f"{yol}: en az {sema['minItems']} öğe")
        if isinstance(sema.get("items"), dict):
            for i, v in enumerate(x):
                sema_dogrula(v, sema["items"], f"{yol}[{i}]", kok, hatalar)
    for anahtar in ("anyOf", "oneOf"):
        if anahtar in sema:
            uyan = sum(1 for s in sema[anahtar] if not sema_dogrula(x, s, yol, kok, []))
            if uyan == 0 or (anahtar == "oneOf" and uyan > 1):
                hatalar.append(f"{yol}: {anahtar} koşulu sağlanmadı")
    for s in sema.get("allOf", []):
        sema_dogrula(x, s, yol, kok, hatalar)
    return hatalar


# ------------------------------------------------------------------ efor yardımcıları
def efor_sira(e):
    try:
        return EFOR_SIRA.index(e)
    except ValueError:
        return -1


def efor_arasi(e, taban=None, tavan=None):
    i = efor_sira(e)
    if taban and i < efor_sira(taban):
        return False
    if tavan and i > efor_sira(tavan):
        return False
    return True


# ------------------------------------------------------------------ platform normalleştirme
def platform_normalle(pid, p):
    """Ham platform kaydı -> seçici biçimi. Ham veriyi değiştirmez."""
    q = dict(p)
    yol = YOL_ESLE.get(p.get("isci_yolu"), p.get("yol") or p.get("isci_yolu"))
    q["yol"] = yol
    elle_platform = p.get("otomatik_cagri") is False
    hav0 = (p.get("havuzlar") or [None])[0]
    e = p.get("erisim")
    liste = []
    if isinstance(e, dict):
        for kimlik, x in e.items():
            x = x if isinstance(x, dict) else {}
            slug = x.get("slug") or kimlik
            liste.append({"kimlik": kimlik, "yol": YOL_ESLE.get(x.get("yol"), x.get("yol")) or yol,
                          "havuz": x.get("havuz") if "havuz" in x else hav0, "eforlar": x.get("eforlar"),
                          "esdeger": x.get("esdeger", "tam"), "z_duzeltme": x.get("z_duzeltme"),
                          "kimlik_sablon": slug if slug != kimlik else None, "kapanis": x.get("kapanis"),
                          "takma": x.get("takma"), "efor_takma": x.get("efor_takma"),
                          "elle": bool(x.get("elle", elle_platform)), "kimlikler": x.get("kimlikler"),
                          "tekil_secim": x.get("tekil_secim"), "efor_bayragi": bool(x.get("efor_bayragi")),
                          "durum": x.get("durum"), "turkce_son_metin": x.get("turkce_son_metin")})
    elif isinstance(e, list):
        for x in e:
            if isinstance(x, dict):
                y = dict(x)
                y["yol"] = YOL_ESLE.get(y.get("yol"), y.get("yol")) or yol
                y.setdefault("havuz", hav0)
                y.setdefault("elle", elle_platform)
                liste.append(y)
    q["erisim"] = liste
    return q


# ------------------------------------------------------------------ Veri nesnesi
class Veri:
    """Tüm veri dosyalarının birleşik görünümü. Saf okuma; yazma guncelle.py'de."""

    def __init__(self, modeller=None, siniflar=None, kurallar=None, platformlar=None, imzalar=None,
                 kaynaklar=None, notlar=None):
        self.modeller = modeller or {}
        self.siniflar = siniflar or {}
        self.kurallar = kurallar or {}
        self.platformlar_ham = platformlar or {}
        self.imzalar = imzalar or {}
        self.kaynaklar = kaynaklar or {}
        self.notlar = list(notlar or [])

    # --- yükleme
    @classmethod
    def yukle(cls, vdir=None, ddir=None):
        d, kay, notlar = {}, {}, []
        for ad in VERI_ADLARI:
            x, yol, n = yukle_bir(ad, vdir, ddir)
            d[ad], kay[ad] = x, str(yol) if yol else None
            notlar += n
        return cls(d["modeller"], d["siniflar"], d["kullanici-kurallari"], d["platformlar"], d["imzalar"],
                   kay, notlar)

    @classmethod
    def sozlukten(cls, d):
        return cls(d.get("modeller"), d.get("siniflar"), d.get("kullanici-kurallari") or d.get("kurallar"),
                   d.get("platformlar"), d.get("imzalar"))

    # --- erişimciler
    @property
    def roller(self):
        return self.modeller.get("roller", {})

    @property
    def model_kayitlari(self):
        return self.modeller.get("modeller", {})

    @property
    def platformlar(self):
        """Normalleştirilmiş platformlar: `yol` (seçici yol adı) ve `erisim` LİSTESİ
        [{kimlik, yol, havuz, eforlar, esdeger, z_duzeltme, kimlik_sablon, kapanis, elle}]. Ham biçim (erisim sözlüğü,
        isci_yolu) ve eski liste biçimi ikisi de kabul edilir."""
        p = self.platformlar_ham
        ham = p.get("platformlar") or p.get("platform") or {}
        return {pid: platform_normalle(pid, x) for pid, x in ham.items() if isinstance(x, dict)}

    @property
    def havuzlar(self):
        p = self.platformlar_ham
        ham = p.get("havuzlar") or p.get("havuz") or {}
        out = {}
        for hid, h in ham.items():
            if isinstance(h, dict):
                h2 = dict(h)
                h2["okuyucu"] = OKUYUCU_ESLE.get(h.get("okuyucu"), h.get("okuyucu"))
                out[hid] = h2
        return out

    def host(self, ad=None):
        ad = ad or self.platformlar_ham.get("host_varsayilan") or "claude-code"
        return HOST_ESLE.get(ad, ad)

    def api_ayari(self, pid):
        """Bedava OpenAI uyumlu platformun bağlantı ayarı (kodda ad/URL yok; hepsi platformlar.json'dan).
        Anahtarın yalnız ortam değişkeni ADI tutulur."""
        p = (self.platformlar_ham.get("platformlar") or {}).get(pid) or {}
        api = dict(p.get("api") or {})
        api.setdefault("taban_url", p.get("taban_url"))
        api.setdefault("taban_env", p.get("taban_env"))
        api.setdefault("anahtar_env", p.get("anahtar_env"))
        api.setdefault("kota_yolu", (p.get("kota") or {}).get("yol") or "/quota")
        api.setdefault("modeller_yolu", (p.get("model_liste") or {}).get("yol") or "/models")
        api.setdefault("kalan_basligi", (p.get("kota") or {}).get("kalan_basligi"))
        for hid in p.get("havuzlar") or []:
            kp = (self.havuz(hid).get("K_p") or {})
            on = kp.get("oncul") if isinstance(kp, dict) else None
            if isinstance(on, dict) and on.get("gun_token"):
                api.setdefault("gun_tavan", on["gun_token"])
        return api

    def K_p(self, hid, pencere):
        """(K, kaynak, birim). K_p biçimleri: {"oncul": {"hafta": 600, "5s": null}, "kalibre": {...}|null, "birim"},
        {"hafta": {"oncul": .., "kalibre": ..}}, {"oncul": 600} ya da sayı. Token birimli havuzda anahtar '<pencere>_token'."""
        h = self.havuz(hid)
        kp = h.get("K_p")
        if kp is None:
            return None, None, None
        if isinstance(kp, (int, float)) and not isinstance(kp, bool):
            return float(kp), "sabit", "USD-e"
        birim = kp.get("birim") or "USD-e"
        adlar = (pencere, f"{pencere}_token")
        for kat in ("kalibre", "oncul"):
            x = kp.get(kat)
            if isinstance(x, dict):
                for a in adlar:
                    if x.get(a):
                        return float(x[a]), kat, birim
            elif isinstance(x, (int, float)) and not isinstance(x, bool) and x:
                if pencere == self.karar_pencereleri(hid)[0]:
                    return float(x), kat, birim
        x = kp.get(pencere)
        if isinstance(x, dict):
            v = x.get("kalibre") if x.get("kalibre") is not None else x.get("oncul")
            if v:
                return float(v), "kalibre" if x.get("kalibre") is not None else "oncul", birim
        return None, None, birim

    def karar_pencereleri(self, hid):
        h = self.havuz(hid)
        k = h.get("karar")
        if isinstance(k, str) and k:
            return [k]
        if isinstance(k, list) and k:
            return list(k)
        adlar = [p.get("ad") for p in h.get("pencereler", []) if isinstance(p, dict) and p.get("ad")]
        return ["hafta"] if "hafta" in adlar else (adlar[:1] or ["hafta"])

    def model(self, kimlik):
        return self.model_kayitlari.get(kimlik)

    def rol_coz(self, rol):
        """Rol adı (ör. 'sol') -> kesin kimlik. Çıplak rol adı asla CLI'a gitmez."""
        r = self.roller.get(rol)
        if not r or not r.get("aktif"):
            raise VeriHatasi(f"rol çözülemedi: {rol}")
        return r["aktif"]

    def hat_rol(self, saglayici, hat):
        for ad, r in self.roller.items():
            if r.get("saglayici") == saglayici and r.get("hat") == hat:
                return ad
        return None

    def model_rol(self, kimlik):
        m = self.model(kimlik) or {}
        if m.get("rol"):
            return m["rol"]
        return self.hat_rol(m.get("saglayici"), m.get("hat"))

    def havuz(self, hid):
        return self.havuzlar.get(hid) or {}

    def ana_havuzlar(self):
        a = (self.kurallar.get("faz") or {}).get("ana_havuz")
        if not a:
            # kodda platform adı yok: faz.ana_havuz verilmemişse host platformun (liderin çalıştığı) havuzları
            a = sorted({e.get("havuz") for p in self.platformlar.values() if p.get("host")
                        for e in p.get("erisim", []) if e.get("havuz")})
        return set(a if isinstance(a, list) else [a])

    def taban(self, hid, pencere):
        """kullanici-kurallari.tabanlar: {"claude_max": {"hafta": .30, "5s": .15}, "agy_*": {"hafta": 0}}. Glob destekli."""
        tablo = self.kurallar.get("tabanlar") or {}
        if hid in tablo:
            return float((tablo[hid] or {}).get(pencere, 0.0))
        for desen, v in tablo.items():
            if fnmatch.fnmatch(hid, desen):
                return float((v or {}).get(pencere, 0.0))
        return 0.0

    def rezerv(self, hid):
        return (self.kurallar.get("rezervler") or {}).get(hid)

    def faz(self):
        f = {"claude_esik_u": 0.25, "lider_tampon_5s": 0.10, "tempo_agirlik": {}, "dis_sira": [],
             "tempo_bant": 0.10, "rezerv_azalma_saat": 24, "bekle_esik_dk": 45,
             "uyarlanir_agirlik": {"acik": False, "alt": 1.0, "ust": 3.0, "adim": 1.25}}
        f.update({k: v for k, v in (self.kurallar.get("faz") or {}).items() if v is not None})
        return f

    def agy_otomatik(self):
        """Kişisel agy otomatik çağrı kararı, nesne biçiminde. Eski bool {"acik": bool} olur; yoksa kapalı."""
        x = self.kurallar.get("agy_otomatik")
        if isinstance(x, dict):
            d = copy.deepcopy(x)
            d["acik"] = bool(d.get("acik"))
            return d
        return {"acik": bool(x)}

    def sor_ayari(self):
        s = {"karar_suresi_saat": 5}
        s.update(self.kurallar.get("sor") or {})
        return s

    # --- yasak (sağlayıcı/hat + takma ad; alt dize DEĞİL)
    def yasak_mi(self, kimlik, kayit=None):
        y = self.kurallar.get("yasak") or {}
        hatlar = {s.lower() for s in y.get("saglayici_hat", [])}
        takma = {s.lower() for s in y.get("takma_ad", [])}
        kayit = kayit if kayit is not None else (self.model(kimlik) or {})
        sag, hat = kayit.get("saglayici"), kayit.get("hat")
        if not (sag and hat):
            from . import guncelle as _g          # geç içe aktarma: döngüsel bağımlılık yok
            c = _g.kimlik_coz(kimlik)
            sag, hat = sag or c["saglayici"], hat or c["hat"]
        if f"{(sag or '').lower()}/{(hat or '').lower()}" in hatlar:
            return True, f"yasak hat {sag}/{hat}"
        adlar = {str(kimlik).lower(), (hat or "").lower()} | {str(t).lower() for t in kayit.get("takma", [])}
        if adlar & takma:
            return True, f"yasak takma ad {sorted(adlar & takma)[0]}"
        return False, None

    def once_sor_mi(self, kimlik, kayit=None):
        """Kullanıcının `once_sor` kuralı: bu hat yasak değildir ama otomatik seçilmez; yalnız kullanıcı onayıyla
        (SOR T7 yanıtı ya da açık --zorla). Dönüş: (bool, gerekçe)."""
        o = self.kurallar.get("once_sor") or {}
        hatlar = {s.lower() for s in o.get("saglayici_hat", [])}
        if not hatlar:
            return False, None
        kayit = kayit if kayit is not None else (self.model(kimlik) or {})
        sag, hat = kayit.get("saglayici"), kayit.get("hat")
        if not (sag and hat):
            from . import guncelle as _g
            c = _g.kimlik_coz(kimlik)
            sag, hat = sag or c["saglayici"], hat or c["hat"]
        if f"{(sag or '').lower()}/{(hat or '').lower()}" in hatlar:
            return True, f"önce sor: {sag}/{hat} otomatik seçilmez (kullanıcı kuralı; onayla --zorla)"
        return False, None

    # --- denetim
    def denetle(self, sema_dizini=None):
        """Tutarlılık + (varsa) şema denetimi. Dönüş: hata listesi (boş = temiz)."""
        h = []
        zo_m = self.modeller.get("z_olcek")
        zo_s = self.siniflar.get("z_olcek")
        if zo_s and zo_m and zo_s != zo_m:
            h.append(f"ölçek karışık: modeller {zo_m} != siniflar kilidi {zo_s} (güncelle tam)")
        for kim, m in self.model_kayitlari.items():
            for e, v in (m.get("varyantlar") or {}).items():
                if v.get("z_olcek") and zo_m and v["z_olcek"] != zo_m:
                    h.append(f"ölçek karışık: {kim}@{e} {v['z_olcek']}")
                if v.get("z") is not None and v.get("z_kaynak") in ("aa", "olcum") and not v.get("kaynak"):
                    h.append(f"kaynaksız sayı: {kim}@{e}.z")
        for rol, r in self.roller.items():
            if r.get("aktif") and r["aktif"] not in self.model_kayitlari:
                h.append(f"rol {rol}: aktif kimlik kayıtta yok ({r['aktif']})")
        h += self._maliyet_sirasi()
        if sema_dizini:
            sd = Path(sema_dizini)
            esle = {"modeller": self.modeller, "siniflar": self.siniflar, "kullanici-kurallari": self.kurallar,
                    "platformlar": self.platformlar_ham, "imzalar": self.imzalar}
            for ad, x in esle.items():
                s = sd / f"{ad}.schema.json"
                if s.exists() and x:
                    for e in sema_dogrula(x, json_oku(s)):
                        h.append(f"şema {ad}: {e}")
        return h

    BOYUT_SIRA = {"XS": 0, "S": 1, "M": 2, "L": 3, "XL": 4}

    def _maliyet_sirasi(self):
        """Aynı sağlayıcıda, aynı eforda küçük boyutlu rolün görev maliyeti büyüğünü aşamaz (veri girişi hatası
        yakalar). gorev_usd_dy işaretli varyant (bilinçli istisna, kaynak notlu) denetim dışıdır."""
        h = []
        gruplar = {}
        for rol, r in self.roller.items():
            b = self.BOYUT_SIRA.get(r.get("boyut") or "")
            m = self.model_kayitlari.get(r.get("aktif") or "")
            if b is None or not m or m.get("durum") in ("yedek", "eski_nesil", "emekli"):
                continue
            gruplar.setdefault(r.get("saglayici"), []).append((b, rol, m))
        for sag, liste in gruplar.items():
            for b1, r1, m1 in liste:
                for b2, r2, m2 in liste:
                    if b1 >= b2:
                        continue
                    for e, v1 in (m1.get("varyantlar") or {}).items():
                        v2 = (m2.get("varyantlar") or {}).get(e) or {}
                        c1, c2 = v1.get("gorev_usd"), v2.get("gorev_usd")
                        if c1 is None or c2 is None or v1.get("gorev_usd_dy") or v2.get("gorev_usd_dy"):
                            continue
                        if c1 > c2:
                            h.append(f"maliyet sırası: {r1}@{e} ({c1}) > {r2}@{e} ({c2}); küçük model pahalı "
                                     f"görünüyor (veri hatası değilse gorev_usd_dy ve not ekle)")
        return h

    def olcek_kilidi(self):
        """Seçici çalışmadan önce: ölçek karışıksa VeriHatasi."""
        for e in self.denetle():
            if e.startswith("ölçek karışık"):
                raise VeriHatasi(e)
