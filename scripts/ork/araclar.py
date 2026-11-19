"""SKILL.md ve references'ın andığı yardımcı alt komutlar: rol, olc, brief, ajanlar, disa-aktar, bedava.

Hiçbiri model çağırmaz; tek istisna `bedava calistir` (açık komutla, yalnız `--veri genel`, gönderim öncesi tarama,
`--kuru` ile istek yok). Model/platform adı kodda yok: hepsi data/*.json'dan.
"""
import argparse
import hashlib
import json
import math
import os
import re
import shutil
import sys
import urllib.request
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

from . import kota, secici
from .veri import Veri, VeriHatasi, durum_dizini, json_oku, sema_dogrula, simdi_utc, skill_kok, zaman_coz


# ================================================================== şef (lider) model ve efor (R16)
def _ayar_dosyalari(ay):
    """Algılamada okunan ayar dosyaları; ORKESTRA_SEF_AYARLARI (os.pathsep ayrımlı; boş = hiçbiri) geçersiz kılar."""
    ortam = os.environ.get("ORKESTRA_SEF_AYARLARI")
    if ortam is not None:
        return [Path(x).expanduser() for x in ortam.split(os.pathsep) if x.strip()]
    return [Path(x).expanduser() if str(x).startswith("~") else Path.cwd() / x for x in ay.get("ayar_dosyalari") or []]


def _sef_algila_ayrintili(veri, ortam=None):
    """Alan başına kaynaklı algılama: {model, efor, model_kaynak, efor_kaynak, kaynaklar, ortam_modeli}.
    ortam_modeli: model açık ortam değişkeninden (ORKESTRA_SEF / model değişkenleri) geldi (taze sinyal)."""
    ay = secici.sef_ayari(veri)
    ortam = os.environ if ortam is None else ortam
    o = {"model": None, "efor": None, "model_kaynak": None, "efor_kaynak": None, "kaynaklar": [],
         "ortam_modeli": False}
    for ad in ay.get("ortam_sef") or []:
        if ortam.get(ad):
            m_, _, e_ = str(ortam[ad]).replace("@", ":").partition(":")
            o["model"], o["efor"] = m_.strip() or None, e_.strip() or None
            o["model_kaynak"] = ad if o["model"] else None
            o["efor_kaynak"] = ad if o["efor"] else None
            o["kaynaklar"].append(ad)
            break
    for ad in ay.get("ortam_model") or []:
        if o["model"] is None and ortam.get(ad):
            o["model"], o["model_kaynak"] = ortam[ad], ad
            o["kaynaklar"].append(ad)
    o["ortam_modeli"] = o["model"] is not None
    for ad in ay.get("ortam_efor") or []:
        if o["efor"] is None and ortam.get(ad):
            o["efor"], o["efor_kaynak"] = ortam[ad], ad
            o["kaynaklar"].append(ad)
    for f in _ayar_dosyalari(ay):
        if o["model"] and o["efor"]:
            break
        try:
            d = json.loads(f.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            continue
        if not isinstance(d, dict):
            continue
        if o["model"] is None and isinstance(d.get(ay.get("ayar_model") or "model"), str):
            o["model"], o["model_kaynak"] = d[ay.get("ayar_model") or "model"], f.name
            o["kaynaklar"].append(f.name)
        if o["efor"] is None and isinstance(d.get(ay.get("ayar_efor") or "effortLevel"), str):
            o["efor"], o["efor_kaynak"] = d[ay.get("ayar_efor") or "effortLevel"], f.name
            o["kaynaklar"].append(f.name)
    o["efor"] = str(o["efor"]).strip().lower() if o["efor"] else None
    return o


def sef_algila(veri, ortam=None):
    """Oturum modeli/eforunu model çağırmadan algılar: ORKESTRA_SEF ('opus:high') > model/efor ortam değişkenleri >
    Claude Code ayar dosyaları (`model`, `effortLevel`). Dönüş (model, efor, kaynaklar); bulunmayan alan None."""
    o = _sef_algila_ayrintili(veri, ortam)
    return o["model"], o["efor"], o["kaynaklar"]


def _sef_kaydi_gecerli(k, ay, simdi):
    """Oturum kaydı yalnız aynı oturumda geçerli: kaydın oturumu ile ortamdaki oturum kimliği eşit olmalı (ikisi de
    yoksa oturumsuz kayıt geçerli; biri varken öteki yoksa geçersiz)."""
    if not isinstance(k, dict) or not k.get("deger"):
        return False
    b = zaman_coz(k.get("bitis"))
    if b and b <= simdi:
        return False
    oturum = (os.environ.get(ay.get("oturum_ortam") or "") or None) if ay.get("oturum_ortam") else None
    return (k.get("oturum") or None) == oturum


def _host_lider_rol(veri):
    """faz.lider_rol yoksa yedek: host platformun (liderin çalıştığı) erişimindeki en yüksek Z'li modelin rolü."""
    en = None
    for p in veri.platformlar.values():
        if not p.get("host"):
            continue
        for e in p.get("erisim", []):
            m = veri.model(e.get("kimlik") or "") or {}
            if not m or veri.yasak_mi(e.get("kimlik"), m)[0] or veri.once_sor_mi(e.get("kimlik"), m)[0]                     or m.get("durum", "aktif") != "aktif":
                continue                              # yasak/seçilemez model şef sayılmaz
            zs = [float(v["z"]) for v in (m.get("varyantlar") or {}).values() if v.get("z") is not None]
            rol = veri.model_rol(e.get("kimlik")) if m else None
            if zs and rol and (en is None or max(zs) > en[0]):
                en = (max(zs), rol)
    return en[1] if en else None


def _sef_deger(t, ham=None):
    """sef_coz sonucu -> kalıcı değer: kesin kimlik (yaklaşık eşleşmede ham ad: uyarı sürsün) + efor."""
    if t.get("yaklasik"):
        return {"model": ham or t["yaklasik"], "rol": t.get("rol"), "efor": t["efor"]}
    return {"kimlik": t["kimlik"], "rol": t.get("rol"), "efor": t["efor"]}


def sef_belirle(veri, durum=None, acik=None, kuru=False, ortam=None, simdi=None):
    """Şefin model:efor değeri ve notlar. Sıra: açık --sef (oturuma kaydedilir) > bu oturumda kaydedilmiş şef (taze
    ortam sinyali daha düşükse o) > otomatik algılama > faz.lider_rol (o da yoksa host platformun üst modeli) +
    varsayılan efor (uyarıyla). Dönüş (deger | None, notlar); deger {kimlik|model|rol, efor, kaynak}."""
    simdi = simdi or simdi_utc()
    ay = secici.sef_ayari(veri)
    notlar = []
    alg = _sef_algila_ayrintili(veri, ortam)
    if acik:
        t = secici.sef_coz(acik, veri)                  # geçersizse hata: sessizce tavansız devam yok
        if t["efor_varsayildi"] and alg["efor"] in secici.EFOR_SIRA_KUME:
            try:
                t2 = secici.sef_coz({"kimlik": t["kimlik"] if not t.get("yaklasik") else t["yaklasik"],
                                     "efor": alg["efor"]}, veri)
                notlar.append(f"--sef eforu verilmedi: algılanan efor {alg['efor']} ({alg['efor_kaynak']})")
                t = t2
            except secici.SecimHatasi:
                pass
        deger = _sef_deger(t, str(acik).replace("@", ":").partition(":")[0])
        if t["efor_varsayildi"]:
            deger["efor"] = None                        # varsayılan efor uyarısı her seçimde sürsün
        etiket = f"{deger.get('kimlik') or deger.get('model')}:{deger['efor'] or ''}".rstrip(":")
        if not kuru:
            kayit = {"deger": etiket, "kimlik": deger.get("kimlik"), "rol": deger.get("rol"), "kaynak": "--sef",
                     "zaman": simdi.isoformat(timespec="seconds"),
                     "bitis": (simdi + timedelta(hours=float(ay.get("oturum_saat") or 12))).isoformat(
                         timespec="seconds"),
                     "oturum": os.environ.get(ay.get("oturum_ortam") or "") or None}
            kota.durum_guncelle(lambda d: d.update(sef=kayit))
            if isinstance(durum, dict):
                durum["sef"] = kayit
        return dict(deger, kaynak="--sef"), notlar
    # otomatik algılama (model alanı ayrı kaynaklı)
    model, model_kaynak = alg["model"], alg["model_kaynak"]
    takma = {str(k).lower(): v for k, v in (ay.get("model_takma") or {}).items()}
    if model and str(model).strip().lower() in takma:
        hedef = takma[str(model).strip().lower()]
        notlar.append(f"şef modeli {model}: " + (f"{hedef} sayıldı (yürütme modeli)" if hedef else
                                                   "hesap varsayılanı, kesin model bilinmiyor"))
        model = hedef
    rol, kimlik, kesin = secici.sef_rol_bul_ayrintili(model, veri) if model else (None, None, False)
    if model and not rol:
        notlar.append(f"şef modeli tanınmadı ({model}); --sef rol:efor ver")
    if rol:
        # yaklaşık eşleşmede ham ad taşınır: seçici her çağrıda 'kayıtta yok' uyarısını basar
        algi = {"kimlik": kimlik, "rol": rol} if kesin else {"model": model, "rol": rol}
    else:
        rol = veri.faz().get("lider_rol")
        model_kaynak = "faz.lider_rol (varsayım)"
        if not rol:
            rol = _host_lider_rol(veri)
            model_kaynak = "host platformun üst modeli (varsayım)"
            if not rol:
                notlar.append("UYARI şef bilinmiyor (algılanamadı, faz.lider_rol ve host modeli yok): tavan "
                              "uygulanmadı; --sef rol:efor ver")
                return None, notlar
        notlar.append(f"şef modeli algılanamadı: {model_kaynak.split(' (')[0]}={rol} varsayıldı; --sef rol:efor ver")
        algi = {"rol": rol, "efor": None}
    efor = alg["efor"]
    if efor and efor not in secici.EFOR_SIRA_KUME:
        notlar.append(f"şef eforu tanınmadı ({efor}): varsayılan efor")
        efor = None
    algi["efor"] = efor
    algi["kaynak"] = ("algılandı: model " + (model_kaynak or "-") + " · efor "
                      + ((alg["efor_kaynak"] or "-") if efor else "varsayılan"))
    # oturum kaydı: bu oturumda verilmiş --sef; taze açık ortam sinyali (ORKESTRA_SEF / model değişkeni) daha düşükse
    # o geçer (şef /model ile düşürüldüyse eski yüksek kayıt tavanı gevşetmesin)
    k = (durum or {}).get("sef")
    if _sef_kaydi_gecerli(k, ay, simdi):
        d_ = str(k["deger"])
        kay = {"rol": k.get("rol") or d_.partition(":")[0], "efor": d_.partition(":")[2] or None,
               "kaynak": f"oturum kaydı ({k.get('kaynak') or '--sef'})"}
        if k.get("kimlik"):
            kay["kimlik"] = k["kimlik"]
        elif d_.partition(":")[0] != kay["rol"]:
            kay["model"] = d_.partition(":")[0]          # yaklaşık eşleşmiş ham ad (uyarı sürer)
        if alg["ortam_modeli"] and rol:
            try:
                sec_, kayit_mi = secici.sef_siki(kay, algi, veri)
            except secici.SecimHatasi:
                sec_, kayit_mi = kay, True
            if not kayit_mi:
                notlar.append(f"oturum kaydı ({d_}) taze algılamadan yüksek: algılanan şef uygulandı")
                return sec_, notlar
        return kay, notlar
    return algi, notlar


def _cikti(x, js):
    if js:
        print(json.dumps(x, ensure_ascii=False, indent=2, default=str))
    elif isinstance(x, (list, tuple)):
        print("\n".join(map(str, x)))
    else:
        print(x)


# ================================================================== rol
def rol_main(argv):
    ap = argparse.ArgumentParser(prog="ork rol", description="Yardımcı rol (nöbetçi, kontrolcü, hakem, haberci, "
                                 "arşivci, muhalif) için model; eşik siniflar.json roller_is")
    ap.add_argument("rol")
    ap.add_argument("sinif", help="izlenen işin sınıfı")
    ap.add_argument("--dogrulayici", help="üreten modelin rolü ya da kimliği (aynı aile elenir)")
    ap.add_argument("--veri")
    ap.add_argument("--alan")
    ap.add_argument("--alt", "--alt-alan", dest="alt_alan")
    ap.add_argument("--kip", default="normal", choices=["normal", "ultra", "hafif"])
    ap.add_argument("--claude")
    ap.add_argument("--sef", help="şefin model:efor tavanı (R16), ör. opus:high")
    ap.add_argument("--tavan-yok", dest="tavan_yok", action="store_true", help="kullanıcı tavanı açıkça kaldırdı")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--kuru", action="store_true", help="durum dosyasına (histerezis) yazma")
    a = ap.parse_args(argv)
    veri = Veri.yukle()
    anlik = kota.oku(veri, claude=a.claude, yaz=not a.kuru)
    durum = kota.durum_oku()
    durum["soguma"] = kota.soguma_secici_icin()
    rol = a.rol.lower().replace("ö", "o").replace("ç", "c").replace("ş", "s").replace("ı", "i")
    istek = {"rol_is": rol, "tur": "rol", "sinif": a.sinif, "veri": a.veri, "alan": a.alan or "mekanik",
             "alt_alan": a.alt_alan, "kip": a.kip}
    uyari = []
    if a.dogrulayici:
        hedef = a.dogrulayici.split("@")[0].split(":")[0]
        kimlik = (veri.roller.get(hedef) or {}).get("aktif") or hedef
        m = veri.model(kimlik)
        if not m:
            raise VeriHatasi(f"--dogrulayici çözülemedi: {a.dogrulayici}")
        istek["haric_aile"] = m.get("saglayici")
    else:
        uyari.append("UYARI --dogrulayici verilmedi: üretenle aynı aile elenmedi")
    sef, sef_not = sef_belirle(veri, durum, acik=a.sef, kuru=a.kuru)
    uyari += [f"NOT {n}" for n in sef_not]
    istek.update({"sef": sef, "tavan_yok": True if a.tavan_yok else None})
    istek = {k: v for k, v in istek.items() if v is not None}
    r = secici.sec(istek, veri, anlik, durum)
    if not a.kuru:
        kota.durum_birlestir(r.get("durum_guncel"))        # ölü bant/histerezis rol çağrılarında da sürer
    r.pop("durum_guncel", None)
    r["uyarilar"] = uyari + list(r.get("uyarilar") or [])
    if a.json:
        _cikti(r, True)
    else:
        print(f"ROL {rol} · " + (r.get("gerekce") or r.get("durum")))
        if r.get("cagri"):
            print("ÇAĞRI " + json.dumps(r["cagri"], ensure_ascii=False))
        for u in r["uyarilar"]:
            print(f"NOT {u}")
    return 0 if r.get("secim") else 2


# ================================================================== olc
def olc_yolu():
    return durum_dizini() / "olc.jsonl"


def _sema(ad):
    return json_oku(skill_kok() / "data" / "sema" / f"{ad}.schema.json")


def olc_kaydet(kayit, veri=None):
    """Kaydı tamamlar (zaman, havuz/aile modelden), şemaya göre doğrular, olc.jsonl'a ekler. (kayit, hatalar)."""
    k = {x: y for x, y in dict(kayit).items() if y is not None}
    k.setdefault("zaman", simdi_utc().isoformat(timespec="seconds"))
    if veri is not None and k.get("model"):
        kimlik = (veri.roller.get(k["model"]) or {}).get("aktif") or k["model"]
        k["model"] = kimlik                           # çıplak rol adı kayda geçmez
        m = veri.model(kimlik) or {}
        k.setdefault("aile", m.get("saglayici"))
        f = m.get("fiyat") or {}
        if k.get("maliyet_usd_e") is None and (k.get("giris_tok") or k.get("cikis_tok")) and                 f.get("girdi") is not None:
            # kalibrasyon girdisi (kota.kalibre): token × liste fiyatı; düşünme token'ı çıktı fiyatıyla
            k["maliyet_usd_e"] = round((float(k.get("giris_tok") or 0) * float(f.get("girdi") or 0)
                                        + (float(k.get("cikis_tok") or 0) + float(k.get("dusunme_tok") or 0))
                                        * float(f.get("cikti") or 0)) / 1e6, 6)
    k.setdefault("yeniden_deneme", 0)
    hatalar = sema_dogrula(k, _sema("olc-kayit"))
    if hatalar:
        return k, hatalar
    yol = olc_yolu()
    yol.parent.mkdir(parents=True, exist_ok=True)
    with open(yol, "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(k, ensure_ascii=False) + "\n")
    return k, []


def olc_oku(gun=None):
    yol = olc_yolu()
    if not yol.is_file():
        return []
    sinir = simdi_utc() - timedelta(days=gun) if gun else None
    out = []
    for satir in yol.read_text(encoding="utf-8").splitlines():
        try:
            k = json.loads(satir)
        except ValueError:
            continue
        z = zaman_coz(k.get("zaman"))
        if sinir and (not z or z < sinir):
            continue
        out.append(k)
    return out


SAYI_ALANLARI = ("giris_tok", "cikis_tok", "dusunme_tok", "onbellek_okuma", "sure_sn", "kota_delta_yuzde",
                 "is_birimi", "pay_tahmin")


def basari_hesapla(kayitlar):
    """Dış doğrulamalı (test/şema/yargıç) kayıtlardan model × sınıf başarı sayımı (tasarım 8.5): durum.basari."""
    out = {}
    for k in kayitlar:
        d = k.get("dogrulayici") if isinstance(k.get("dogrulayici"), dict) else None
        if not d or d.get("sonuc") not in ("dogrulandi", "curutuldu"):
            continue
        x = out.setdefault(k.get("model"), {}).setdefault(k.get("sinif"), {"n": 0, "ok": 0})
        x["n"] += 1
        x["ok"] += 1 if d["sonuc"] == "dogrulandi" else 0
    return out


def olc_main(argv):
    ap = argparse.ArgumentParser(prog="ork olc", description="Ölçüm kaydı (~/.orkestra/olc.jsonl)")
    alt = ap.add_subparsers(dest="eylem", required=True)
    k = alt.add_parser("kaydet")
    k.add_argument("--dosya", help="kayıt JSON dosyası (diğer bayrakları tamamlar)")
    k.add_argument("--taslak", help="ork sec çıktısındaki olc_taslak (JSON metni ya da dosya)")
    for ad in ("is", "parca", "sinif", "alan", "model", "efor", "havuz", "aile", "yol", "durum", "hata-sinifi",
               "brief-hash-a", "brief-hash-b", "dogrulayici"):
        k.add_argument(f"--{ad}")
    for ad in SAYI_ALANLARI:
        k.add_argument("--" + ad.replace("_", "-"), type=float)
    k.add_argument("--json", action="store_true")
    o = alt.add_parser("ozet")
    o.add_argument("--gun", type=int, default=7)
    o.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if a.eylem == "ozet":
        kay = olc_oku(a.gun)
        basari = basari_hesapla(kay)
        if basari:
            from .kota import durum_yaz
            durum_yaz({"basari": basari})
        ozet = {"kayit": len(kay), "model": Counter(f"{x.get('model')}@{x.get('efor')}" for x in kay),
                "durum": Counter(x.get("durum") for x in kay), "sinif": Counter(x.get("sinif") for x in kay),
                "havuz": Counter(x.get("havuz") for x in kay)}
        if a.json:
            _cikti(ozet, True)
        else:
            print(f"OLC son {a.gun} gün: {ozet['kayit']} kayıt" + ("" if kay else " (kayıt yok: çağrı satırındaki "
                                                                       "`ork olc kaydet` adımı atlanıyor olabilir)"))
            for b in ("model", "durum", "sinif", "havuz"):
                if ozet[b]:
                    print(f"  {b}: " + ", ".join(f"{x} {n}" for x, n in ozet[b].most_common(8)))
        return 0
    kayit = json_oku(a.dosya) if a.dosya else {}
    if a.taslak:
        t = a.taslak.strip()
        ts = json.loads(t) if t.startswith("{") else json_oku(t)
        izinli = set(((_sema("olc-kayit") or {}).get("properties") or {}).keys())
        kayit.update({x: y for x, y in (ts or {}).items() if y is not None and (not izinli or x in izinli)})
        kayit.setdefault("is_id", "is")
    esle = {"is": "is_id", "parca": "parca_id", "hata_sinifi": "hata_sinifi", "brief_hash_a": "brief_hash_A",
            "brief_hash_b": "brief_hash_B"}
    for ad, v in vars(a).items():
        if ad in ("eylem", "dosya", "json", "taslak") or v is None:
            continue
        if ad == "dogrulayici":
            v = {"model": v}
        kayit[esle.get(ad, ad)] = v
    k2, hatalar = olc_kaydet(kayit, Veri.yukle())
    if hatalar:
        print("HATA olc kaydı şemaya uymuyor: " + "; ".join(hatalar[:6]))
        return 3
    print(json.dumps(k2, ensure_ascii=False) if a.json else f"OLC kaydedildi -> {olc_yolu()}")
    return 0


# ================================================================== brief
ADAPTOR_SAGLAYICI = {"anthropic": "claude-xml", "openai": "openai-bolumlu", "google": "gemini-baglam-once"}
A_ALANLAR = ("ROL", "ORTAK KURALLAR", "KARAR SÖZLÜĞÜ", "ÇIKTI ŞEMASI", "ARAÇLAR / YASAKLAR", "DURMA KURALLARI")
B_ALANLAR = ("HEDEF ve NEDEN", "MİMARİ ÖZETİ", "PROJE GRAFİĞİ", "SAHİPLİK TABLOSU")
GRAFIK_SATIRI = ("proje grafiği varsa graphify-out/GRAPH_REPORT.md ve grafik sorgusunu oku; yoksa yoksay")
C_ALANLAR = ("PARÇA", "YAZILABİLİR / OKUNUR / YASAK YOLLAR", "GİRDİLER", "KAPSAM DIŞI", "UÇ DURUMLAR",
             "BİTTİ ÖLÇÜTÜ", "BÜTÇE")
DONUS = ("Dönüş: JSON {durum: ok|kismi|bloke|dogrulanamadi, ozet (<= 2000 token), dosyalar[], kanit[{tur, ref}], "
         "acik_sorular[], sonraki}. Ağır çıktı dosyaya; yanıtta yalnız yol.")
ZORUNLU = ("KAPSAM DIŞI", "BİTTİ ÖLÇÜTÜ", "KARAR SÖZLÜĞÜ")


def adaptor_sec(veri, hedef):
    kimlik = (veri.roller.get(hedef) or {}).get("aktif") or hedef
    m = veri.model(kimlik) or {}
    sag = m.get("saglayici") or (veri.roller.get(hedef) or {}).get("saglayici")
    if m.get("adaptor"):
        return m["adaptor"], None
    if sag in ADAPTOR_SAGLAYICI:
        return ADAPTOR_SAGLAYICI[sag], None
    if m.get("acik_agirlik") or (m.get("erisim_bayraklari") or {}).get("acik_agirlik"):
        return "cn-notr", None
    return "openai-bolumlu", "adaptör ölçülmedi (tanınmayan sağlayıcı)"


def _katman(alanlar, d, bos_yaz=True):
    """Katman metni. Katman etiketleri ([A. ...]) işçi istemine yazılmaz; yalnız alan başlıkları."""
    satir = []
    for x in alanlar:
        v = d.get(x)
        if isinstance(v, list):
            v = "\n".join(f"- {y}" for y in v)
        if v in (None, ""):
            if not bos_yaz:
                continue
            v = "<doldur>"
        satir.append(f"{x}: {v}")
    return "\n".join(satir)


def aile_cumleleri(veri, hedef, efor=None, tarih=None, deneme=False):
    """data/aile-cumleleri.json: hat -> [{cumle, kanit, kosul:{efor: [..]}}]. Yalnız A/B kanıtlı cümleler varsayılan;
    C ve DY düzeyi yalnız --deneme ile (kanıtsız kural varsayılan uygulanmaz)."""
    kimlik = (veri.roller.get(hedef) or {}).get("aktif") or hedef
    m = veri.model(kimlik) or {}
    hat = m.get("hat") or (veri.roller.get(hedef) or {}).get("hat")
    d = json_oku(skill_kok() / "data" / "aile-cumleleri.json") or {}
    out = []
    for x in (d.get("hatlar") or {}).get(hat or "", []):
        if x.get("kanit") not in ("A", "A-", "B") and not deneme:
            continue
        ef = (x.get("kosul") or {}).get("efor")
        if ef and efor not in ef:
            continue
        out.append(str(x.get("cumle", "")).replace("{tarih}", tarih or simdi_utc().date().isoformat()))
    return out


def brief_uret(sablon, veri, hedef, efor=None, hafif=False, deneme=False):
    """sablon: {"A": {...}, "B": {...}, "C": {...}} ya da düz anahtarlar. Adaptöre göre sarar.
    hafif=True (mekanik/basit, tek seferlik iş): yalnız C katmanı + dönüş; zorunlu alan yalnız BİTTİ ÖLÇÜTÜ."""
    d = {}
    for k in ("A", "B", "C"):
        d.update(sablon.get(k) or {})
    d.update({k: v for k, v in sablon.items() if k not in ("A", "B", "C")})
    d.setdefault("ÇIKTI ŞEMASI", DONUS)
    if not hafif:
        d.setdefault("PROJE GRAFİĞİ", GRAFIK_SATIRI)
    ek = aile_cumleleri(veri, hedef, efor, deneme=deneme)
    if ek:
        mevcut = d.get("DURMA KURALLARI")
        d["DURMA KURALLARI"] = "\n".join(([mevcut] if mevcut else []) + ek)
    zorunlu = ("BİTTİ ÖLÇÜTÜ",) if hafif else ZORUNLU
    eksik = [x for x in zorunlu if not d.get(x)]
    if hafif:
        A = _katman(("ÇIKTI ŞEMASI", "DURMA KURALLARI"), d, bos_yaz=False)
        B = ""
        C = _katman(C_ALANLAR, d, bos_yaz=False)
    else:
        A, B, C = _katman(A_ALANLAR, d), _katman(B_ALANLAR, d), _katman(C_ALANLAR, d)
    ad, notu = adaptor_sec(veri, hedef)
    if ad == "claude-xml":
        metin = f"<instructions>\n{A}\n</instructions>\n" + (f"<context>\n{B}\n</context>\n" if B else "") + \
            f"<task>\n{C}\n</task>"
    elif ad == "gemini-baglam-once":
        # A sabit önek olarak başta kalır (önbellek önek isabeti); bağlam görevden önce, görev en sonda
        metin = f"{A}\n\n" + (f"{B}\n\n" if B else "") + f"{C}\n\nYukarıdaki bilgilere dayanarak görevi yap; " \
            f"kesin ve doğrudan ol."
    elif ad == "cn-notr":
        gorev = d.get("BİTTİ ÖLÇÜTÜ") or ""
        metin = f"Görev: {gorev}\n<kurallar>\n{A}\n</kurallar>\n" + (f"<baglam>\n{B}\n</baglam>\n" if B else "") + \
            f"{C}\nTekrar: {gorev}"
    else:
        metin = "\n\n".join(x for x in (A, B, C) if x)
    return {"adaptor": ad, "not": notu, "metin": metin, "eksik": eksik, "aile_cumleleri": ek,
            "brief_hash_A": hashlib.sha256(A.encode("utf-8")).hexdigest()[:16],
            "brief_hash_B": hashlib.sha256(B.encode("utf-8")).hexdigest()[:16]}


def brief_main(argv):
    ap = argparse.ArgumentParser(prog="ork brief", description="A/B/C brief şablonunu hedef ailenin adaptörüyle doldurur")
    ap.add_argument("--rol", required=True, help="hedef rol ya da kesin kimlik")
    ap.add_argument("--sablon", help="JSON: {A:{..}, B:{..}, C:{..}}; yoksa boş iskelet")
    ap.add_argument("--efor", help="hedef efor (aileye özgü cümlelerin koşulu)")
    ap.add_argument("--hafif", action="store_true", help="mekanik/basit tek seferlik iş: yalnız C katmanı")
    ap.add_argument("--deneme", action="store_true", help="C/DY kanıtlı aile cümlelerini de ekle")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    veri = Veri.yukle()
    r = brief_uret(json_oku(a.sablon) if a.sablon else {}, veri, a.rol, efor=a.efor, hafif=a.hafif, deneme=a.deneme)
    if a.json:
        _cikti(r, True)
    else:
        print(r["metin"])
        print(f"\n# adaptör {r['adaptor']} · hash A {r['brief_hash_A']} B {r['brief_hash_B']}"
              + (f" · NOT {r['not']}" if r["not"] else "")
              + (f" · EKSİK zorunlu alan: {', '.join(r['eksik'])}" if r["eksik"] else ""))
    return 0 if not r["eksik"] else 1


# ================================================================== ajanlar
def _hedef_coz(veri, deger):
    rol, _, ef = str(deger).partition(":")
    kimlik = (veri.roller.get(rol) or {}).get("aktif")
    return rol, ef or None, kimlik


def _md_alan(metin, ad):
    m = re.search(rf"^{ad}:\s*(.+)$", metin, re.M)
    return m.group(1).strip().strip('"') if m else None


def _toml_alan(metin, ad):
    m = re.search(rf'^{ad}\s*=\s*"([^"]*)"', metin, re.M)
    return m.group(1) if m else None


def ajan_plani(veri, claude_dizin, codex_dizin):
    """[{dosya, platform, ad, beklenen_model, beklenen_efor, mevcut_model, mevcut_efor, sorun[]}]"""
    eslem = (veri.kurallar.get("ajan_dosyalari") or {})
    out = []
    for ad, deger in sorted((eslem.get("claude") or {}).items()) + ([("Explore", eslem["explore"])]
                                                                    if eslem.get("explore") else []):
        rol, ef, kimlik = _hedef_coz(veri, deger)
        f = Path(claude_dizin) / f"{ad}.md"
        mevcut = f.read_text(encoding="utf-8") if f.is_file() else None
        out.append({"dosya": str(f), "platform": "claude", "ad": ad, "beklenen_model": rol, "beklenen_efor": ef,
                    "kimlik": kimlik, "mevcut_model": _md_alan(mevcut, "model") if mevcut else None,
                    "mevcut_efor": _md_alan(mevcut, "effort") if mevcut else None, "var": mevcut is not None})
    for ad, deger in sorted((eslem.get("codex") or {}).items()):
        rol, ef, kimlik = _hedef_coz(veri, deger)
        f = Path(codex_dizin) / f"{ad}.toml"
        mevcut = f.read_text(encoding="utf-8") if f.is_file() else None
        out.append({"dosya": str(f), "platform": "codex", "ad": ad, "beklenen_model": kimlik, "beklenen_efor": ef,
                    "kimlik": kimlik, "mevcut_model": _toml_alan(mevcut, "model") if mevcut else None,
                    "mevcut_efor": _toml_alan(mevcut, "model_reasoning_effort") if mevcut else None,
                    "var": mevcut is not None})
    for x in out:
        sorun = []
        if not x["kimlik"]:
            sorun.append("eşlemedeki rol veride yok")
        if not x["var"]:
            sorun.append("dosya yok")
        else:
            mm = x["mevcut_model"]
            if mm != x["beklenen_model"]:
                sorun.append(f"model {mm} != {x['beklenen_model']}")
            if x["mevcut_efor"] != x["beklenen_efor"]:
                sorun.append(f"efor {x['mevcut_efor']} != {x['beklenen_efor']}")
            if mm:
                km = (veri.roller.get(mm) or {}).get("aktif") or mm
                yz, yg = veri.yasak_mi(km, veri.model(km))
                if yz:
                    sorun.append(f"YASAK: {yg}")
                elif veri.once_sor_mi(km, veri.model(km))[0]:
                    sorun.append(f"ÖNCE SOR: {km} ajan dosyasında sabit model olamaz (otomatik kullanılmaz)")
                elif veri.model(km) and veri.model(km).get("durum") in ("eski_nesil", "emekli"):
                    sorun.append(f"eski nesil: {km}")
        x["sorun"] = sorun
    return out


CLAUDE_SABLON = """---
name: {ad}
description: {aciklama}
model: {model}
effort: {efor}
{araclar}---
{govde}
"""
EXPLORE_ARACLAR = "tools: Read, Grep, Glob, Bash\n"
EXPLORE_GOVDE = ("Salt okuma keşif ajanı. Dosya yazma, düzenleme ya da silme yok. Bulguları yol + satır aralığıyla, "
                 "kısa döndür; bilmediğini acik_sorular olarak yaz.")


def _yedekle(f):
    f = Path(f)
    if f.is_file():
        y = f.with_name(f"{f.name}.bak-orkestra-{simdi_utc().strftime('%Y%m%d%H%M%S')}")
        shutil.copy2(f, y)
        return str(y)
    return None


def ajan_yaz(x):
    f = Path(x["dosya"])
    eski = f.read_text(encoding="utf-8") if f.is_file() else None
    if x["platform"] == "claude":
        if eski:
            yeni = re.sub(r"^model:.*$", f"model: {x['beklenen_model']}", eski, count=1, flags=re.M)
            if re.search(r"^effort:", yeni, re.M):
                yeni = re.sub(r"^effort:.*$", f"effort: {x['beklenen_efor']}", yeni, count=1, flags=re.M)
            else:
                yeni = re.sub(r"^model:.*$", lambda m: m.group(0) + f"\neffort: {x['beklenen_efor']}", yeni,
                              count=1, flags=re.M)
        else:
            exp = x["ad"] == "Explore"
            yeni = CLAUDE_SABLON.format(ad=x["ad"], model=x["beklenen_model"], efor=x["beklenen_efor"],
                                        aciklama="Salt okuma kod tabanı keşfi" if exp else "orkestra işçisi",
                                        araclar=EXPLORE_ARACLAR if exp else "",
                                        govde=EXPLORE_GOVDE if exp else "Brief'teki kapsamla çalış; kanıt döndür.")
    else:
        if not eski:
            return None, "codex ajan dosyası yok; elle oluşturulmalı (config.toml [agents] kaydı gerekir)"
        yeni = re.sub(r'^model\s*=.*$', f'model = "{x["beklenen_model"]}"', eski, count=1, flags=re.M)
        yeni = re.sub(r'^model_reasoning_effort\s*=.*$', f'model_reasoning_effort = "{x["beklenen_efor"]}"', yeni,
                      count=1, flags=re.M)
    if yeni == eski:
        return None, "değişiklik yok"
    y = _yedekle(f)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(yeni, encoding="utf-8", newline="\n")
    notu = "trusted_hash satırı var: Codex dosyayı yeniden onaylatabilir" if "trusted_hash" in yeni else None
    return y, notu


def ajanlar_main(argv):
    ap = argparse.ArgumentParser(prog="ork ajanlar", description="Platform ajan dosyalarını kullanici-kurallari.json "
                                 "ajan_dosyalari eşlemesine göre denetler / yazar")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--denetle", action="store_true")
    g.add_argument("--yaz", action="store_true")
    ap.add_argument("--kuru", action="store_true", help="--yaz: yalnız planı göster")
    ap.add_argument("--claude-dizin", default=str(Path.home() / ".claude" / "agents"))
    ap.add_argument("--codex-dizin", default=str(Path.home() / ".codex" / "agents"))
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    veri = Veri.yukle()
    plan = ajan_plani(veri, a.claude_dizin, a.codex_dizin)
    satir, kod = [], 0
    for x in plan:
        if a.denetle or a.kuru:
            durum = "OK" if not x["sorun"] else "SAPMA " + "; ".join(x["sorun"])
            satir.append(f"{x['platform']:6} {x['ad']:15} beklenen {x['beklenen_model']}:{x['beklenen_efor']} · {durum}")
            kod = kod or (1 if x["sorun"] else 0)
        elif x["sorun"]:
            y, notu = ajan_yaz(x)
            satir.append(f"{x['platform']:6} {x['ad']:15} -> {x['beklenen_model']}:{x['beklenen_efor']}"
                         + (f" (yedek {y})" if y else "") + (f" · NOT {notu}" if notu else ""))
    if a.json:
        _cikti(plan, True)
    else:
        _cikti(satir or ["ajan eşlemesi boş"], False)
    return kod


# ================================================================== gizlilik taraması
SIR_DESENLERI = [
    ("anahtar öneki", r"\b(?:sk-[A-Za-z0-9_-]{16,}|sk_live_[A-Za-z0-9]{12,}|gh[pousr]_[A-Za-z0-9]{20,}|"
                      r"github_pat_[A-Za-z0-9_]{20,}|xox[abprs]-[A-Za-z0-9-]{10,}|xapp-[A-Za-z0-9-]{10,}|"
                      r"AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{30,}|hf_[A-Za-z0-9]{20,}|ya29\.[A-Za-z0-9_-]{20,}|"
                      r"npm_[A-Za-z0-9]{20,}|glpat-[A-Za-z0-9_-]{16,})"),
    ("JWT", r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
    ("özel anahtar", r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    ("Bearer başlığı", r"(?i)authorization\s*:\s*bearer\s+[A-Za-z0-9._~+/=-]{12,}"),
    ("anahtar başlığı", r"(?i)\b(?:x-api-key|api-key|x-goog-api-key)\s*:\s*[A-Za-z0-9._~+/=-]{12,}"),
    ("bağlantı dizesi parolası", r"[a-z][a-z0-9+.-]*://[^\s:/@]+:[^\s@/]{4,}@"),
    ("anahtar ataması", r"(?i)(?:\b(?:setx|export|set)\s+|\$env:)?\b[A-Z0-9_]*(?:API_KEY|SECRET|TOKEN|PASSWORD|PASSWD)"
                        r"[A-Z0-9_]*\s*[:= ]\s*['\"]?[A-Za-z0-9._~+/-]{12,}"),
    ("parola ataması", r"(?:\b(?i:setx|export|set)\s+|\$env:)?(?:\b[A-Z0-9_]*(?:PAROLA|SIFRE|ŞİFRE)[A-Z0-9_]*"
                       r"\s*[:= ]\s*|\b(?i:[a-z_][a-z0-9_]*(?:parola|sifre)[a-z0-9_]*\s*=\s*))"
                       r"['\"]?(?!<)[A-Za-z0-9._~+/@!#$%^&*-]{8,}"),
    ("çıplak hex anahtar", r"(?<![0-9a-fA-F])[0-9a-f]{32}(?![0-9a-fA-F])"),
]
KIMLIK_FINANS_DESENLERI = [
    ("IBAN", r"\bTR\d{2}\s?(?:\d{4}\s?){5}\d{2}\b"),
]
KISISEL_DESENLER = [
    ("kullanıcı dizini", r"(?i)(?:\b[A-Z]:[\\/]+Users[\\/]+(?!Public\b|Default\b)\w[\w.-]*|/home/\w[\w.-]*|"
                         r"/Users/(?!Shared\b)\w[\w.-]*)"),
    ("sürücü yolu", r"(?<![\w%])(?![CcXx]:[\\/]+(?:Program Files|Windows)\b)[D-Zd-z]:[\\/]+[\w.-]+"),
    ("e-posta", r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    ("telefon", r"(?<![\d.])(?:\+90|0)\s?5\d{2}[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}(?!\d)"),
]


# Kişi düzeyi sağlık ve üçüncü kişi kaydı işaretleri (kamu/dış hedefte engel). Bilerek dar tutulur: kamuya açık klinik
# literatür ("hastalarda", "patients", doz tabloları) bedava kamu havuzuna gidebilmeli (R7, R13); yakalanan şey bir KİŞİYE ait kayıt
# biçimidir (etiketli ad, protokol/dosya no, doğum tarihi, tanı kodu satırı). Serbest metindeki kişi verisini yine
# yakalamaz: asıl kapı liderin veri beyanıdır (references/gizlilik.md).
_AD = r"[A-ZÇĞİÖŞÜ][a-zçğıöşü]{1,20}"
KISI_SAGLIK_DESENLERI = [
    ("kişi etiketli ad", rf"(?:\b(?:Hasta|Danışan|Danisan|Patient|Client|Bay|Bayan|Sn\.|Sayın|Dr\.)\s*(?:adı|adi|"
                         rf"name)?\s*[:：]?\s*{_AD}\s+{_AD}\b)"),
    ("ad soyad alanı", r"(?i)\b(?:ad[ıi]?\s*soyad[ıi]?|full\s+name|patient\s+name)\s*[:：]\s*\S+"),
    ("kayıt numarası", r"(?i)\b(?:protokol|dosya|hasta|kayıt|kayit|MRN|medical\s+record)\s*(?:no|numarası|numarasi|#|"
                       r"number)\s*[:：#]?\s*\d{3,}"),
    ("doğum tarihi", r"(?i)\b(?:doğum\s*tarihi|dogum\s*tarihi|d\.\s?t\.|DOB|date\s+of\s+birth)\s*[:：]?\s*\d{1,4}"
                     r"[./-]\d{1,2}[./-]\d{1,4}"),
    ("tanı kodu satırı", r"(?i)\b(?:tanı|tani|teşhis|teshis|ICD-?10|diagnosis|dx)\s*(?:kodu|code)?\s*[:：]\s*"
                         r"[A-TV-Z][0-9]{2}(?:\.[0-9A-Z]{1,4})?\b"),
]


def kisi_saglik_tara(metin):
    """[(tür, kısaltma)]: kişiye ait sağlık/üçüncü kişi kaydı biçimleri (değer basılmaz)."""
    bul = []
    for ad, d in KISI_SAGLIK_DESENLERI:
        for m in re.finditer(d, metin or ""):
            bul.append((ad, m.group(0)[:4] + "…"))
    return bul


def _entropi(s):
    n = len(s)
    return -sum(c / n * math.log2(c / n) for c in Counter(s).values()) if n else 0.0


def _tc_gecerli(s):
    d = [int(c) for c in s]
    if len(d) != 11 or d[0] == 0:
        return False
    return (sum(d[0:9:2]) * 7 - sum(d[1:8:2])) % 10 == d[9] and sum(d[:10]) % 10 == d[10]


_KATLA = str.maketrans("ğĞıİşŞçÇöÖüÜâÂîÎûÛ", "gGiIsScCoOuUaAiIuU")


def ascii_katla(s):
    return str(s).translate(_KATLA)


def anahtar_degerleri(veri):
    """platformlar.json'daki anahtar_env adlarının ortamdaki DEĞERLERİ (yalnız bellekte; asla yazdırılmaz)."""
    adlar = set()
    for p in ((veri.platformlar_ham or {}).get("platformlar") or {}).values():
        for k in ("anahtar_env", "taban_env"):
            if isinstance(p, dict) and p.get(k):
                adlar.add(p[k])
    for x in veri.kurallar.get("bedava_istisna") or []:
        if isinstance(x, dict) and x.get("anahtar_env"):
            adlar.add(x["anahtar_env"])
    return [os.environ[a] for a in sorted(adlar) if os.environ.get(a)]


def _yol_segment_tara(metin, yollar):
    """yasak_yol segment/harfiyen yol eşleşmeleri."""
    if not yollar:
        return []
    segmentler = set()
    for t in re.split(r"[\s\"'`()<>\[\]{},;|]+", metin):
        t = t.strip(".:")
        ayrac = len(re.findall(r"[\\/]", t))
        if ayrac >= 2 or (ayrac >= 1 and re.match(r"(?:~|[A-Za-z]:|[\\/])", t)):
            segmentler.update(x.lower() for x in re.split(r"[\\/]+", t) if x)
    bul = []
    for s in yollar:
        if not s:
            continue
        if re.search(r"[\\/\s]", s):        # çok parçalı giriş: harfiyen
            hit = re.search("(?i)" + re.escape(s).replace("/", r"[\\/]"), metin)
        else:
            hit = s.lower() in segmentler
        if hit:
            bul.append(("yasak yol", s[:2] + "…"))
    return bul


def tara(metin, kisisel=False, sozluk=(), yollar=(), degerler=(), kimlik_ve_yol=False):
    """[(tür, örnek kısaltılmış)]; değer asla tam yazılmaz. `yollar` (yasak_yol) yalnız yol bağlamında eşleşir:
    tek sözcük düz metinde değil, yalnız yol biçimli dizgenin (en az iki ayraç ya da kök/ev/sürücü önekli) bir
    parçasıyken; boşluk ya da ayraç içeren giriş harfiyen aranır."""
    kimlik_yol = bool(kisisel or kimlik_ve_yol)
    desenler = list(SIR_DESENLERI) + (list(KIMLIK_FINANS_DESENLERI) if kimlik_yol else []) + \
        (list(KISISEL_DESENLER) if kisisel else [])
    bul = []
    for ad, d in desenler:
        for m in re.finditer(d, metin):
            bul.append((ad, m.group(0)[:6] + "…"))
    for m in re.finditer(r"[A-Za-z0-9+/_=-]{40,}", metin):
        t = m.group(0)
        if _entropi(t) > 4.5 and re.search(r"\d", t) and re.search(r"[A-Z]", t) and re.search(r"[a-z]", t):
            bul.append(("yüksek entropi", t[:6] + "…"))
    for d in degerler:                  # ortamdaki anahtar değerleri sırdır: kişisel kipten bağımsız aranır
        if d and len(d) >= 8 and d in metin:
            bul.append(("ortamdaki anahtar değeri", "…"))
    if kimlik_yol:
        for m in re.finditer(r"(?<!\d)\d{11}(?!\d)", metin):
            if _tc_gecerli(m.group(0)):
                bul.append(("sağlamalı kimlik no", m.group(0)[:3] + "…"))
        bul.extend(_yol_segment_tara(metin, yollar))
    if kisisel:
        katli = ascii_katla(metin)
        for s in sozluk:
            # alt çizgi, rakam ve büyük harf sınır sayılır (ad_quick, AdSoyad yakalanır; küçük harfle süren sözcük
            # değil: 'kar' sözlükteyse 'karar' yakalanmaz); Türkçe harfler ASCII'ye katlanır (ğ = g, ı = i)
            if s and re.search(rf"(?<![A-Za-z0-9])(?i:{re.escape(ascii_katla(s))})(?=[^a-z]|$)", katli):
                bul.append(("kişisel sözlük", s[:2] + "…"))
    return bul


# ================================================================== disa-aktar
IZIN = ["SKILL.md", "README.md", "AGENTS.md", "CHANGELOG.md", "LICENSE", "NOTICE.md", ".gitignore", "references/*.md",
        "commands/*.md", "scripts/*.py", "scripts/ork/*.py", "tests/*.py", "tests/fixtures/*", "data/sema/*.json",
        "data/modeller.json", "data/imzalar.json", "data/siniflar.json", "data/aile-cumleleri.json",
        "data/*.ornek.json"]


def otomatik_sozluk():
    """Çalışma anında makineden türetilen tanımlayıcılar (ev klasörü adı, oturum adı, makine adı, git kullanıcı
    adı). Yalnız bellekte; çıktıya kısaltılmış yazılır."""
    out = set()
    try:
        out.add(Path.home().name)
    except (RuntimeError, OSError):
        pass
    for fn in (os.getlogin,):
        try:
            out.add(fn())
        except OSError:
            pass
    try:
        import socket
        out.add(socket.gethostname())
    except OSError:
        pass
    try:
        import subprocess
        r = subprocess.run(["git", "config", "--global", "user.name"], capture_output=True, text=True, timeout=5,
                           stdin=subprocess.DEVNULL)
        if r.returncode == 0 and r.stdout.strip():
            out.add(r.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        pass
    parca = set()
    for x in out:
        parca |= {p for p in re.split(r"[\s._-]+", x) if len(p) >= 4}
    return sorted(x for x in out | parca if x and len(x) >= 4 and x.lower() not in ("user", "admin", "desktop"))


def _yerel_kayitlar(metin):
    """modeller.json içinde makineye özgü keşif izi: 'yerel:' kaynaklı kanıt ya da gizli katalog işareti."""
    bul = []
    if re.search(r'"(?:kaynak|url)"\s*:\s*"yerel:', metin):
        bul.append(("yerel keşif kaydı (yerel: kaynak)", "…"))
    if re.search(r'"visibility"\s*:\s*"hide"', metin):
        bul.append(("gizli katalog kaydı", "…"))
    return bul


def disa_aktar(hedef, kuru=True, kok=None, veri=None, sozluksuz=False, ek_sozluk=None):
    """Herkese açık kopya: izin listesi + kişisel veri taraması. Sözlük = kişisel kurallar + makineden otomatik.
    Sözlük boşsa (sozluksuz değilse) durur. Dosya bazlı izin: gizlilik.ek_sozluk_izin {"LICENSE": ["Ad"]}."""
    kok = Path(kok or skill_kok())
    veri = veri or Veri.yukle()
    gz = veri.kurallar.get("gizlilik") or {}
    sozluk = list(gz.get("ek_sozluk") or []) + list(otomatik_sozluk() if ek_sozluk is None else ek_sozluk)
    yollar = list(gz.get("yasak_yol") or [])
    izin_s = gz.get("ek_sozluk_izin") or {}
    degerler = anahtar_degerleri(veri)
    if not sozluk and not sozluksuz:
        return {"dosya": [], "bulgular": {"(sözlük)": [("kişisel sözlük boş", "--sozluksuz ile geç")]},
                "kopyalandi": False, "sozluk": 0}
    dosyalar = sorted({p for d in IZIN for p in kok.glob(d) if p.is_file() and "__pycache__" not in p.parts
                       and p.suffix != ".pyc"})

    def tara_dosya(p, rel):
        try:
            m = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return [("okunamadı", "")]
        izinli = {x.lower() for x in izin_s.get(rel, [])}
        b = tara(m, kisisel=True, sozluk=[x for x in sozluk if x.lower() not in izinli], yollar=yollar,
                 degerler=degerler)
        if rel == "data/modeller.json":
            b += _yerel_kayitlar(m)
        return b

    bulgular = {}
    for p in dosyalar:
        rel = str(p.relative_to(kok)).replace("\\", "/")
        b = tara_dosya(p, rel)
        if b:
            bulgular[rel] = b
    uyari = []
    kopyalandi = False
    if not kuru and not bulgular:
        h = Path(hedef)
        izinli_rel = {str(p.relative_to(kok)).replace("\\", "/") for p in dosyalar}
        if h.exists():
            fazla = [str(q.relative_to(h)).replace("\\", "/") for q in h.rglob("*") if q.is_file()
                     and ".git" not in q.parts and str(q.relative_to(h)).replace("\\", "/") not in izinli_rel]
            if fazla:
                uyari.append(f"hedefte izin listesi dışı {len(fazla)} dosya var (silinmedi): {', '.join(fazla[:5])}")
        for p in dosyalar:
            q = h / p.relative_to(kok)
            q.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, q)
        for p in dosyalar:                       # kopyadan sonra hedefi yeniden tara
            rel = str(p.relative_to(kok)).replace("\\", "/")
            b = tara_dosya(h / p.relative_to(kok), rel)
            if b:
                bulgular[rel] = b
        kopyalandi = not bulgular
    return {"dosya": [str(p.relative_to(kok)).replace("\\", "/") for p in dosyalar], "bulgular": bulgular,
            "kopyalandi": kopyalandi, "sozluk": len(sozluk), "uyari": uyari}


def disa_aktar_main(argv):
    ap = argparse.ArgumentParser(prog="ork disa-aktar", description="Herkese açık kopya: izin listesi + kişisel veri "
                                 "taraması; bulgu varsa çıkış 1, kopya yok. Yayın ayrıca kullanıcı onayı ister.")
    ap.add_argument("--hedef")
    ap.add_argument("--kuru", action="store_true")
    ap.add_argument("--sozluksuz", action="store_true", help="kişisel sözlük boşken de çalış (önerilmez)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if not a.kuru and not a.hedef:
        ap.error("--hedef ya da --kuru gerekli")
    r = disa_aktar(a.hedef, kuru=a.kuru or not a.hedef, sozluksuz=a.sozluksuz)
    if a.json:
        _cikti(r, True)
    else:
        print(f"DIŞA AKTAR {len(r['dosya'])} dosya izin listesinde · sözlük {r.get('sozluk', 0)} öğe · bulgu "
              f"{len(r['bulgular'])} dosyada" + (" · kopyalandı -> " + a.hedef if r["kopyalandi"] else " · kopya yok"))
        for f, b in sorted(r["bulgular"].items()):
            print(f"  {f}: " + ", ".join(sorted({t for t, _ in b})))
        for u in r.get("uyari") or []:
            print(f"UYARI {u}")
    return 1 if r["bulgular"] else 0


# ================================================================== kur (menü komutu + kişisel dosyalar)
KISISEL_ORNEK = {"kullanici-kurallari.json": "kullanici-kurallari.ornek.json",
                 "platformlar.json": "platformlar.ornek.json"}


def kur_plani(ev=None, kok=None):
    """[{tur, kaynak, hedef, durum: yok|ayni|farkli|var}] (yazmadan)."""
    import hashlib as _h
    ev = Path(ev) if ev else Path.home()
    kok = Path(kok or skill_kok())
    out = []
    for f in sorted((kok / "commands").glob("*.md")):
        h = ev / ".claude" / "commands" / f.name
        d = "yok" if not h.exists() else ("ayni" if _h.sha256(h.read_bytes()).digest()
                                          == _h.sha256(f.read_bytes()).digest() else "farkli")
        out.append({"tur": "komut", "kaynak": str(f), "hedef": str(h), "durum": d})
    # kişisel dosyalar yükleyicinin okuduğu yere (veri.kisisel_dizini: ORKESTRA_KISISEL > ORKESTRA_DIR > ~/.orkestra)
    ddir = Path(os.environ.get("ORKESTRA_KISISEL") or os.environ.get("ORKESTRA_DIR") or (ev / ".orkestra"))
    for ad, ornek in KISISEL_ORNEK.items():
        h = ddir / ad
        durum = "yok"
        if h.exists():
            try:
                d = json_oku(h)
                durum = "var" if isinstance(d, dict) and int(d.get("sema") or d.get("surum") or 0) >= 7 else "eski"
            except (OSError, ValueError, TypeError):
                durum = "eski"                # okunamayan ya da bozuk dosya da yedeklenip yenilenir
        out.append({"tur": "kisisel", "kaynak": str(kok / "data" / ornek), "hedef": str(h), "durum": durum})
        eski = kok / "data" / ad
        if eski.exists():
            out.append({"tur": "tasi", "kaynak": str(eski), "hedef": str(h), "durum": "skill klasöründe"})
    return out


def kur_main(argv, ev=None, kok=None):
    ap = argparse.ArgumentParser(prog="ork kur", description="Menü komutunu ~/.claude/commands'a kopyalar (yedekli, "
                                 "idempotent); kişisel dosya yoksa örnekten ~/.orkestra'ya üretir (var olanı ezmez).")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--denetle", action="store_true", help="yalnız durum; sapma varsa çıkış 1")
    g.add_argument("--kuru", action="store_true", help="yapılacakları göster")
    a = ap.parse_args(argv)
    plan = kur_plani(ev, kok)
    satir, kod = [], 0
    for x in plan:
        if x["tur"] == "komut":
            if x["durum"] == "ayni":
                satir.append(f"KOMUT  {Path(x['hedef']).name}: kurulu")
                continue
            if a.denetle:
                satir.append(f"KOMUT  {Path(x['hedef']).name}: {x['durum']} -> ork kur")
                kod = 1
                continue
            if a.kuru:
                satir.append(f"KOMUT  {x['hedef']} yazılacak ({x['durum']})")
                continue
            y = _yedekle(x["hedef"]) if x["durum"] == "farkli" else None
            Path(x["hedef"]).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(x["kaynak"], x["hedef"])
            satir.append(f"KOMUT  {x['hedef']} yazıldı" + (f" (yedek {y})" if y else "")
                         + " · yeni oturumda '/' menüsünde görünür")
        elif x["tur"] == "kisisel":
            if x["durum"] == "var":
                satir.append(f"KİŞİSEL {Path(x['hedef']).name}: var (dokunulmadı)")
                continue
            eski_sema = x["durum"] == "eski"
            if a.denetle:
                satir.append(f"KİŞİSEL {Path(x['hedef']).name}: " + ("eski şema (v7 değil) -> ork kur (yedekleyip "
                             "örnekten üretir)" if eski_sema else "yok -> ork kur (örnekten)"))
                kod = 1
                continue
            if a.kuru:
                satir.append(f"KİŞİSEL {x['hedef']} " + ("eski şema: yedeklenip " if eski_sema else "") +
                             "örnekten üretilecek")
                continue
            from .veri import atomik_yaz
            y_eski = _yedekle(x["hedef"]) if eski_sema else None
            if y_eski:
                satir.append(f"KİŞİSEL {Path(x['hedef']).name}: eski şema yedeklendi ({y_eski}); ayarlarını yeni "
                             f"dosyaya elle taşı")
            eski = Path(kok or skill_kok()) / "data" / Path(x["hedef"]).name
            if eski.exists():                 # eski yerleşim: skill klasöründeki kişisel dosya kopyalanır
                atomik_yaz(x["hedef"], json_oku(eski))
                satir.append(f"KİŞİSEL {x['hedef']} skill klasöründeki kişisel dosyadan kopyalandı (aslını sil)")
                continue
            d = json_oku(x["kaynak"]) or {}
            d["katman"] = "kisisel"
            d["aciklama"] = "örnekten üretildi: kendi aboneliklerine, tabanlarına ve platformlarına göre düzenle"
            atomik_yaz(x["hedef"], d)
            satir.append(f"KİŞİSEL {x['hedef']} örnekten üretildi: DÜZENLE (plan, tabanlar, yasaklar)")
        elif x["tur"] == "tasi":
            satir.append(f"TAŞI   {x['kaynak']} -> {x['hedef']} (kişisel dosya skill klasöründe; senkron "
                         f"kopyalarına girer)")
            kod = kod or (1 if a.denetle else 0)
    _cikti(satir, False)
    return kod


# ================================================================== bedava
def bedava_platformu(veri):
    for x in veri.kurallar.get("bedava_istisna") or []:
        if isinstance(x, dict) and x.get("platform"):
            return x
    return None


def bedava_main(argv, _post=None, _veri=None):
    ap = argparse.ArgumentParser(prog="ork bedava", description="Bedava OpenAI uyumlu API ile metin işi (yalnız genel "
                                 "veri; gönderim öncesi tarama; bulgu varsa çıkış 3 ve sıfır istek)")
    alt = ap.add_subparsers(dest="eylem", required=True)
    c = alt.add_parser("calistir")
    c.add_argument("--model", required=True, help="slug[:efor]")
    c.add_argument("--istem", required=True, help="istem dosyası (UTF-8)")
    c.add_argument("--veri", required=True)
    c.add_argument("--cikti")
    c.add_argument("--kuru", action="store_true", help="tarama + istek gövdesi; ağ yok")
    a = ap.parse_args(argv)
    veri = _veri or Veri.yukle()
    b = bedava_platformu(veri)
    if not b:
        print("HATA bedava istisna tanımlı değil (kullanici-kurallari.json bedava_istisna)")
        return 2
    bp = veri.platformlar.get(b["platform"], {})
    bh = veri.havuz(b.get("havuz") or b["platform"])
    gz_b = b.get("gizlilik") or bh.get("gizlilik") or bp.get("gizlilik") or "kamu"
    izinli_veri = {"genel"} if (b.get("veri") != "kisisel" or gz_b != "ozel") else {"genel", "bilinmiyor", "kisisel"}
    if a.veri not in izinli_veri:
        tur = "kişisel-izinli (sır/sağlık/gizli hariç)" if "kisisel" in izinli_veri else "kamu: yalnız --veri genel"
        print(f"HATA bedava havuz {tur} (verilen {a.veri}); iş uygun modele gider")
        return 3
    bitis = zaman_coz(b.get("bitis"))
    if bitis and bitis <= simdi_utc():
        print(f"HATA bedava havuz kapandı ({b.get('bitis')})")
        return 2
    metin = Path(a.istem).read_text(encoding="utf-8")
    gz = veri.kurallar.get("gizlilik") or {}
    yollar = list(gz.get("yasak_yol") or [])
    degerler = anahtar_degerleri(veri)
    if gz_b in ("kamu", "dis"):
        bul = tara(metin, kisisel=True, sozluk=list(gz.get("ek_sozluk") or []) + otomatik_sozluk(),
                   yollar=yollar, degerler=degerler)
    else:
        bul = tara(metin, kisisel=False, yollar=yollar, degerler=degerler, kimlik_ve_yol=True)
    bul += kisi_saglik_tara(metin)
    if bul:
        print("ENGEL gönderim öncesi tarama: " + ", ".join(sorted({t for t, _ in bul})) + " · istek gönderilmedi")
        return 3
    slug, _, efor = a.model.partition(":")
    govde = {"model": slug, "messages": [{"role": "user", "content": metin}]}
    if efor:
        govde["reasoning_effort"] = efor
    if a.kuru:
        print(f"KURU tarama temiz · {slug}{':' + efor if efor else ''} · {len(metin)} karakter · istek yok")
        return 0
    api = veri.api_ayari(b["platform"])
    anahtar = kota.anahtar_oku(api.get("anahtar_env") or b.get("anahtar_env"))
    if not anahtar:
        print(f"HATA anahtar ortam değişkeninde yok ({api.get('anahtar_env') or b.get('anahtar_env')})")
        return 2
    taban = (api.get("taban_url") or "").rstrip("/")
    if not kota.taban_guvenli(taban):
        print("HATA taban URL https değil")
        return 2
    bas_ad = api.get("anahtar_basligi") or "Authorization"
    deger = anahtar if bas_ad.lower() != "authorization" else f"Bearer {anahtar}"
    req = urllib.request.Request(taban + "/chat/completions", data=json.dumps(govde).encode("utf-8"), method="POST",
                                 headers={bas_ad: deger, "Content-Type": "application/json",
                                          "User-Agent": "orkestra/7"})
    try:
        if _post:
            kod, yanit = _post(req)
        else:
            with urllib.request.build_opener(kota._Yonlendirmesiz).open(req, timeout=600) as r:
                kod, yanit = r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        sinif = kota.hata_isle(b.get("havuz") or b["platform"], str(e), e.code, kimlik=slug)
        print(f"HATA HTTP {e.code} ({sinif})")
        return 2
    except (OSError, ValueError) as e:
        print(f"HATA {type(e).__name__}")
        return 2
    icerik = (((yanit or {}).get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    if a.cikti:
        Path(a.cikti).write_text(icerik, encoding="utf-8")
        print(f"OK -> {a.cikti}")
    else:
        print(icerik)
    u = (yanit or {}).get("usage") or {}
    olc_kaydet({"is_id": "bedava", "sinif": "basit", "alan": "genel", "model": slug, "efor": efor or "varsayilan",
                "havuz": b.get("havuz") or b["platform"], "aile": "bedava", "yol": "bedava-api", "durum": "ok",
                "giris_tok": u.get("prompt_tokens"), "cikis_tok": u.get("completion_tokens")})
    return 0
