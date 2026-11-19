"""Orkestra v7 tek giriş noktası. Yalnız Python standart kitaplığı (3.10+; 3.12'de doğrulandı); model çağırmaz.
Kısaltma: `ork` = `python -I "<skill klasörü>/scripts/ork.py"` (Claude Code'da "${CLAUDE_SKILL_DIR}/scripts/ork.py").

  ork sec --sinif kod --alan kod --alt-alan gunluk --veri genel [--boyut mikro..cok_buyuk] [--kipler metin,gorsel]
          [--duzenle] [--sure-dk N] [--parca N] [--kip hafif|ultra] [--zorla rol[:efor]] [--dis-onay] [--ciddi]
          [--dis-kanit test_tam|kapali_cevap|sema_dogrulayici] [--tok-tahmin giris:cikis] [--brief dosya]
          [--sor-yanit kod] [--sef rol:efor] [--tavan-yok] [--json] [--kuru]
                        çıkış: 0 seçildi/rota/elle, 4 SOR ya da onay gerekli, 5 BEKLE, 3 hata, 2 geçersiz ad
                        --sef: şef tavanı (R16; verilmezse oturum kaydı > algılama > faz.lider_rol, uyarılı)
  ork sec --plan parcalar.json [--suru-plani suru.json] [--claude 5s=..,hafta=..]   (çok parçalı iş, tek çağrı)
  ork suru calistir --plan suru.json [--paralel N] [--kuru] [--dusus izinli|yok]   (dış işçiler tek Bash'te)
  ork suru durum --is <is_id>  |  ork suru temizle --agy [--gun 7] [--uygula]
  ork plan [--json]                (hafta planı: havuz başına hedef/gün, ρ, ÖNDE/GERİDE, bugünkü sıra)
  ork gizlilik tara --dosya f      (değer basmadan bulgu türü + satır)
  ork neden <rol|kimlik> <sinif> [--alan ..] [--alt ..]
  ork alanlar                      (geçerli alan / alt alan / sınıf adları)
  ork kota [--taze] [--json] [--havuz ad] [--claude 5s=32,hafta=91] [--agy]
  ork kesif [--json] [--yaz] [--port] [--agy] [--giris] [--surum]
  ork guncelle [hizli|tam|platform|model <ad>] [--kuru] [--agy] [--json]  |  ork guncelle uygula --web sonuc.json
  ork guncelle platform-ekle <ad> [--kuru]  |  ork guncelle "<ad> platformunu ekledim"  |  uygula --platform f.json
  ork platform yoksay|kabul <id>   (yeni platform sinyali kararı)
  ork rol <rol> <sinif> --dogrulayici <üreten rol|kimlik> [--veri ..] [--sef rol:efor] [--tavan-yok]
  ork olc kaydet [--taslak <sec çıktısındaki olc_taslak JSON>] --durum ok ...  |  ork olc ozet
  ork brief --rol <hedef rol> [--sablon brief.json] [--hafif] [--efor high]
  ork ajanlar --denetle | --yaz [--kuru]
  ork kur [--denetle] [--kuru]     (menü komutu ~/.claude/commands, kişisel dosyalar ~/.orkestra)
  ork disa-aktar --kuru | --hedef <klasör>
  ork bedava calistir --model slug[:efor] --istem dosya --veri genel [--kuru]
  ork durum                        (soğuma ve histerezis durumu)
  ork kontrol                      (tüm testler + veri denetimi)
"""
import sys

sys.dont_write_bytecode = True                     # depo ağacına kullanıcı yolu içeren .pyc yazılmaz

import argparse  # noqa: E402
import difflib  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import unittest  # noqa: E402
from pathlib import Path  # noqa: E402

BURASI = Path(__file__).resolve().parent
sys.path.insert(0, str(BURASI))

from ork import araclar, guncelle, kesif, kota, secici, suru  # noqa: E402
from ork.veri import Veri, VeriHatasi, skill_kok  # noqa: E402


def _utf8():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def _istek_ekle(ap):
    ap.add_argument("--alan")
    ap.add_argument("--alt-alan", "--alt", dest="alt_alan")
    ap.add_argument("--sinif")
    ap.add_argument("--sinyal", action="append", default=[], help="zorluk sinyali (tekrarlanabilir)")
    ap.add_argument("--belirsiz", action="store_true")
    ap.add_argument("--kip", default="normal", choices=["normal", "ultra", "hafif"])
    ap.add_argument("--veri", choices=["genel", "kisisel", "gizli", "saglik", "bilinmiyor"])
    ap.add_argument("--dis-onay", dest="dis_onay", action="store_true",
                    help="kullanıcı bu konuşmada sağlık/gizli verinin host dışı sağlayıcıya gitmesini onayladı")
    ap.add_argument("--boyut", choices=["mikro", "kucuk", "orta", "buyuk", "cok_buyuk"])
    ap.add_argument("--ciddi", action="store_true", help="ciddi zor iş: Opus kapısı (ölçülü eşdeğer yoksa Opus)")
    ap.add_argument("--dis-kanit", dest="dis_kanit", help="tam dış kanıt türü (kanıtlı kaskad)")
    ap.add_argument("--tok-tahmin", dest="tok_tahmin", type=_tok_tahmin,
                    help="giris:cikis token tahmini (iş birimi yerine; >= 0)")
    ap.add_argument("--brief", help="brief dosyası: boyutundan token tahmini (tek atımlık dış çağrı)")
    ap.add_argument("--sor-yanit", dest="sor_yanit", help="kullanıcının SOR yanıtı (bu iş için)")
    ap.add_argument("--suru", action="store_true", help="sürü içi rol (tekil_secim=false modeller açılır)")
    ap.add_argument("--plan", help="parça listesi JSON (data/sema/sec-plan.schema.json)")
    ap.add_argument("--suru-plani", dest="suru_plani", help="dış parçaların koşucu planını bu dosyaya yaz")
    ap.add_argument("--ib", type=float)
    ap.add_argument("--sure-dk", "--sure", dest="sure_dk", type=float)
    ap.add_argument("--parca", type=int, help="paralel parça sayısı (iş birimi parça başına bölünür)")
    ap.add_argument("--kipler", help="metin,gorsel,pdf,ses,video")
    ap.add_argument("--duzenle", "--duzenleme", dest="duzenleme", action="store_true")
    ap.add_argument("--olgu", action="store_true")
    ap.add_argument("--zorla", help="rol[:efor] ya da kesin kimlik")
    ap.add_argument("--sef", help="şefin (liderin) model:efor tavanı, ör. opus:high (oturumda saklanır; R16)")
    ap.add_argument("--tavan-yok", dest="tavan_yok", action="store_true",
                    help="kullanıcı bu iş için şef tavanını açıkça kaldırdı (çıktıya uyarı düşer)")
    ap.add_argument("--host")
    ap.add_argument("--dizin", default=os.getcwd())
    ap.add_argument("--dogrulayici-var", dest="dogrulayici_var", action="store_true")
    ap.add_argument("--deterministik", action="store_true")
    ap.add_argument("--claude", help="get_usage kalan yüzdeleri: 5s=32,hafta=91")
    ap.add_argument("--taze", action="store_true")
    ap.add_argument("--ornek-kabul", dest="ornek_kabul", action="store_true",
                    help="kişisel dosya yokken örnek verilerle seçime izin ver")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--kuru", action="store_true", help="durum dosyasına yazma")


def _tok_tahmin(x):
    """argparse türü: giris:cikis, ikisi de >= 0 (geçersizse çıkış 2)."""
    try:
        return list(secici.tok_tahmin_coz(x))
    except secici.SecimHatasi as e:
        raise argparse.ArgumentTypeError(str(e))


def _istek(a):
    i = {k: getattr(a, k) for k in ("alan", "alt_alan", "sinif", "belirsiz", "kip", "veri", "boyut", "ib", "sure_dk",
                                     "duzenleme", "olgu", "zorla", "host", "dizin", "dogrulayici_var", "deterministik",
                                     "dis_onay", "ciddi", "dis_kanit", "tok_tahmin", "sor_yanit", "suru", "brief",
                                     "tavan_yok")
         if getattr(a, k, None) not in (None, False)}
    if a.sinyal:
        i["sinyaller"] = a.sinyal
    if getattr(a, "parca", None) and a.parca > 1:
        i["parca"] = a.parca
    if a.kipler:
        i["kipler"] = [x.strip() for x in a.kipler.split(",") if x.strip()]
    return i


def _ad_dogrula(a, veri):
    """Bilinmeyen alan/alt alan/sınıf: çıkış 2 + yakın eşleşme önerisi (sessizce genel Z'ye düşülmez)."""
    s = veri.siniflar
    alanlar = s.get("alanlar") or {}
    takma = s.get("alan_takma") or secici.ALAN_TAKMA_VARSAYILAN
    gecerli_alan = set(alanlar) | set(takma) | {"genel"}
    gecerli_alt = {x for v in alanlar.values() for x in (v or [])}
    hatalar = []
    for ad, deger, kume in (("alan", a.alan, gecerli_alan), ("alt alan", a.alt_alan, gecerli_alt),
                            ("sınıf", a.sinif, set(s.get("q") or {}))):
        if deger and deger not in kume:
            yakin = difflib.get_close_matches(deger, sorted(kume), n=3)
            hatalar.append(f"bilinmeyen {ad}: {deger}" + (f" (yakın: {', '.join(yakin)})" if yakin else "")
                           + " · liste: ork alanlar")
    if a.alan and a.alt_alan and a.alan in alanlar and a.alt_alan in gecerli_alt and \
            a.alt_alan not in (alanlar.get(a.alan) or []):
        hatalar.append(f"{a.alt_alan} alt alanı {a.alan} alanında değil ({secici.alan_bul(a.alt_alan, s)})")
    return hatalar


def _ornek_engeli(veri, a):
    ornek = [ad for ad, yol in (veri.kaynaklar or {}).items() if str(yol or "").endswith(".ornek.json")]
    if ornek and not getattr(a, "ornek_kabul", False):
        return (f"HATA kişisel dosya yok, örnek veri yüklendi ({', '.join(ornek)}): `ork kur` ile kopyala ve "
                f"kendi planına göre düzenle; yalnız denemek için --ornek-kabul")
    return None


def _notlar(veri):
    for n in veri.notlar:
        if "ÖRNEK" in n or "skill klasöründe" in n:
            print(f"NOT {n}")


def _baglam(a):
    """--kuru: kota okuması hiçbir dosya yazmaz (claude-kota, kota-anlik, kota-gecmis, durum)."""
    veri = Veri.yukle()
    anlik = kota.oku(veri, taze=a.taze, claude=a.claude, yaz=not getattr(a, "kuru", False))
    durum = kota.durum_oku()
    durum["soguma"] = kota.soguma_secici_icin()
    return veri, anlik, durum


SOR_OTURUM_KODLARI = {secici.AGY_KABUL, secici.AGY_RET}


def _sor_yaniti_kaydet(a, veri, durum):
    """Oturum kapsamlı SOR yanıtı (T4: agy_kabul / agy_ret) durum.sor_kararlari'na yazılır (karar_suresi_saat);
    diğer yanıtlar yalnız bu iş içindir (--sor-yanit her çağrıda verilir)."""
    kod = getattr(a, "sor_yanit", None)
    if not kod or kod not in SOR_OTURUM_KODLARI or a.kuru:
        return
    from datetime import timedelta
    simdi = secici.simdi_utc()
    saat = float(veri.sor_ayari().get("karar_suresi_saat") or 5)
    kayit = {"kod": kod, "kapsam": "oturum", "zaman": simdi.isoformat(timespec="seconds"),
             "bitis": (simdi + timedelta(hours=saat)).isoformat(timespec="seconds")}

    def f(d):
        L = [x for x in (d.get("sor_kararlari") or []) if isinstance(x, dict) and x.get("kod") not in SOR_OTURUM_KODLARI]
        d["sor_kararlari"] = L + [kayit]
    kota.durum_guncelle(f)
    durum.setdefault("sor_kararlari", [])
    durum["sor_kararlari"] = [x for x in durum["sor_kararlari"] if isinstance(x, dict)
                              and x.get("kod") not in SOR_OTURUM_KODLARI] + [kayit]


def _sef_coz(a, veri, durum):
    """R16: --sef > oturum kaydı > otomatik algılama > faz.lider_rol (uyarılı). a.sef_deger'e yazar; notları basar."""
    deger, notlar = araclar.sef_belirle(veri, durum, acik=getattr(a, "sef", None), kuru=getattr(a, "kuru", False))
    a.sef_deger = deger
    for n in notlar:
        print(f"NOT {n}")
    return deger


def _not_yaz(u):
    print(u if str(u).startswith("NOT ") else f"NOT {u}")


def _ikili_doldur(cagri, veri):
    """Çağrı satırındaki {ikili} alanı keşifle doldurulur (imzalar.json desenleri, sürüme göre en yeni)."""
    if not cagri or "{ikili}" not in str(cagri.get("komut") or ""):
        return
    p = veri.platformlar.get(cagri.get("platform"), {})
    imza = next((x for x in kesif.imza_listesi(veri.imzalar) if x.get("id") == (p.get("imza") or
                                                                              cagri.get("platform"))), None)
    bul = kesif.ikili_bul((imza or {}).get("ikili")) if imza else None
    if bul and bul.get("yol"):
        cagri["komut"] = cagri["komut"].replace("{ikili}", f'"{bul["yol"]}"')
        cagri["bos_alanlar"] = [x for x in cagri.get("bos_alanlar") or [] if x != "ikili"]


def k_sec(argv):
    ap = argparse.ArgumentParser(prog="ork sec", description="İş -> platform/model/efor + gerekçe")
    _istek_ekle(ap)
    a = ap.parse_args(argv)
    veri, anlik, durum = _baglam(a)
    eng = _ornek_engeli(veri, a)
    if a.plan:
        if eng:
            print(eng)
            return 2
        _sef_coz(a, veri, durum)
        return _sec_plan(a, veri, anlik, durum)
    hata = _ad_dogrula(a, veri)
    if hata or eng:
        for h in hata + ([eng] if eng else []):
            print(h if h.startswith("HATA") else f"HATA {h}")
        return 2
    _sor_yaniti_kaydet(a, veri, durum)
    ist = _istek(a)
    sef = _sef_coz(a, veri, durum)
    if sef:
        ist["sef"] = sef
    r = secici.sec(ist, veri, anlik, durum)
    if not a.kuru:
        kota.durum_birlestir(r.get("durum_guncel"))
    r.pop("durum_guncel", None)
    _ikili_doldur(r.get("cagri"), veri)
    _ikili_doldur(r.get("cagri_elle"), veri)
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=2, default=str))
    else:
        _notlar(veri)
        print(r.get("gerekce", r.get("durum")))
        if r.get("sef"):
            sf = r["sef"]
            print(f"ŞEF {sf['etiket']} · tavan Z {sf['z']:g} + bant {sf['bant']:g}"
                  + (f" · {sf['kaynak']}" if sf.get("kaynak") else "")
                  + (f" · KALDIRILDI ({sf['kalkti']})" if sf.get("kalkti") else ""))
        if r.get("cagri"):
            print("ÇAĞRI " + json.dumps({k: v for k, v in r["cagri"].items() if k != "olc_taslak"}, ensure_ascii=False))
            print("OLC_TASLAK " + json.dumps(r["cagri"].get("olc_taslak"), ensure_ascii=False))
        for u in r.get("uyarilar") or []:
            _not_yaz(u)
        if r.get("durum") == "sor":
            print("SOR " + json.dumps({"soru": r.get("soru"), "secenekler": r.get("secenekler"),
                                       "varsayilan": r.get("varsayilan")}, ensure_ascii=False))
    return secici.CIKIS_KODU.get(r.get("durum"), 3)


def _sec_plan(a, veri, anlik, durum):
    from ork.veri import json_oku
    plan = json_oku(a.plan)
    if not isinstance(plan, dict) or not isinstance(plan.get("parcalar"), list):
        print("HATA plan okunamadı (beklenen: {is_id, parcalar: [...]})")
        return 3
    # parça adları tekil yolla aynı denetimden geçer (bilinmeyen alan sessizce genel Z'ye düşmez)
    import types
    for p_ in plan["parcalar"]:
        if not isinstance(p_, dict):
            continue
        ns = types.SimpleNamespace(alan=p_.get("alan"), alt_alan=p_.get("alt_alan"), sinif=p_.get("sinif"))
        h = _ad_dogrula(ns, veri)
        if p_.get("tok_tahmin") is not None:
            try:
                secici.tok_tahmin_coz(p_["tok_tahmin"])
            except secici.SecimHatasi as e:
                h.append(str(e))
        if h:
            p_["_hata"] = h
    # R16: açık --sef plan değerini ezer (T6 sef_yukselt yolu); yoksa plan ile oturum/algılama şefinin sıkı olanı
    sd = getattr(a, "sef_deger", None)
    if sd and getattr(a, "sef", None):
        if plan.get("sef") and plan["sef"] != sd:
            print(f"NOT plan şefi ({plan['sef']}) yerine açık --sef {a.sef} uygulandı")
        plan["sef"] = sd
    elif sd or plan.get("sef"):
        try:
            sec_, oturum_mu = secici.sef_siki(sd, plan.get("sef"), veri)
        except secici.SecimHatasi as e:
            print(f"HATA plan şefi çözülemedi: {e}")
            return 3
        if sd and plan.get("sef") and not oturum_mu:
            print(f"NOT plan şefi oturum şefinden sıkı: {plan['sef']}")
        elif sd and plan.get("sef") and plan["sef"] != sd:
            print("NOT plan şefi oturum şefinden gevşek: oturum şefi uygulandı (yükseltmek için açık --sef)")
        plan["sef"] = sec_
    if getattr(a, "tavan_yok", False):
        plan["tavan_yok"] = True
    r = secici.plan_sec(plan, veri, anlik, durum)
    if not a.kuru:
        kota.durum_birlestir(r.get("durum_guncel"))
    r.pop("durum_guncel", None)
    if a.suru_plani:
        from ork.veri import atomik_yaz
        atomik_yaz(a.suru_plani, dict(r["suru_plani"], claude_tasarruf_usd_e=r["tasarruf"]["tasarruf_usd_e"]))
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=2, default=str))
    else:
        for p in r["parcalar"]:
            print(f"{p['id']}: {p.get('gerekce')}")
            for u in p.get("uyarilar") or []:
                if str(u).startswith("UYARI"):
                    print(f"{p['id']}: {u}")
        print(f"PLAN {r['ozet']} · Claude tasarrufu ≈ {r['tasarruf']['tasarruf_usd_e']} USD-e"
              + (f" (%{r['tasarruf']['oran'] * 100:.0f})" if r["tasarruf"].get("oran") is not None else ""))
        for c in r["claude_isleri"]:
            print(f"CLAUDE {c['id']}: {c['cagri']} · {c['sozlesme']}")
        if r.get("sor"):
            print("SOR " + json.dumps(r["sor"], ensure_ascii=False))
        if a.suru_plani:
            print(f"SÜRÜ planı -> {a.suru_plani} · yürüt: ork suru calistir --plan {a.suru_plani}")
    return 4 if r.get("sor") else 0


def k_plan(argv):
    ap = argparse.ArgumentParser(prog="ork plan", description="Hafta planı (model çağırmaz): havuz başına kalan, taban, "
                                 "R(t), hedef/gün, ρ, ÖNDE/GERİDE, bugünkü sıra")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--claude")
    ap.add_argument("--taze", action="store_true")
    ap.add_argument("--kuru", action="store_true", help="uyarlanır ağırlığı ve kalibrasyonu durum.json'a yazma")
    a = ap.parse_args(argv)
    veri, anlik, durum = _baglam(a)
    olc7, gecmis = araclar.olc_oku(7), kota.gecmis_oku()
    p = secici.hafta_plani(veri, anlik, durum, olc=olc7, gecmis=gecmis)
    kal = kota.kalibrasyon_hesapla(veri, gecmis, araclar.olc_oku(14), durum)
    for hid, ws in kal.items():
        for w, x in ws.items():
            p["notlar"].append(f"{hid}.{w}: K_p ölçüm {x['K']} USD-e (n={x['n']}; öncülün 0.25-4 katıysa seçici kullanır)")
    if not a.kuru:
        ek = {}
        if p.get("tempo_agirlik_uyarlanmis"):
            ek["tempo_agirlik_uyarlanmis"] = p["tempo_agirlik_uyarlanmis"]
        if kal:
            ek["kapasite_kalibre"] = kal
        if ek:
            kota.durum_birlestir(ek)
    if a.json:
        print(json.dumps(p, ensure_ascii=False, indent=2, default=str))
        return 0
    print(f"{'havuz':16s} {'kalan':>6s} {'taban':>6s} {'R(t)':>6s} {'gün':>5s} {'hedef/gün':>10s} {'ρ':>6s} "
          f"{'o·ρ':>6s} durum")
    for x in p["havuzlar"]:
        print(f"{x['havuz']:16s} {x['kalan']:6.2f} {x['taban']:6.2f} {x['R']:6.3f} {x['gun']:5.1f} "
              f"{x['hedef_pp_gun']:9.1f}pp {x['rho']:6.2f} {x['o_rho']:6.2f} {x['durum']}")
    print("SIRA bugün: " + " -> ".join(p["sira"]))
    for n in p["notlar"]:
        print(f"NOT {n}")
    return 0


def k_gizlilik(argv):
    ap = argparse.ArgumentParser(prog="ork gizlilik", description="Kamu/dış havuza gönderim öncesi tarama (değer "
                                 "basılmaz: bulgu türü + satır numarası)")
    ap.add_argument("eylem", choices=["tara"])
    ap.add_argument("--dosya", required=True)
    a = ap.parse_args(argv)
    veri = Veri.yukle()
    gz = veri.kurallar.get("gizlilik") or {}
    sozluk = list(gz.get("ek_sozluk") or []) + araclar.otomatik_sozluk()
    toplam = 0
    for n, satir in enumerate(Path(a.dosya).read_text(encoding="utf-8").splitlines(), 1):
        b = araclar.tara(satir, kisisel=True, sozluk=sozluk, yollar=list(gz.get("yasak_yol") or []),
                         degerler=araclar.anahtar_degerleri(veri)) + araclar.kisi_saglik_tara(satir)
        for tur in sorted({t for t, _ in b}):
            print(f"BULGU satır {n}: {tur}")
            toplam += 1
    print("TEMİZ (kamu/dış havuza gidebilir; 'genel' beyanı yine liderin)" if not toplam else
          f"ENGEL {toplam} bulgu: kamu/dış havuza gönderilmez; kişisel parçayı ayır ya da yeniden yaz")
    return 0 if not toplam else 1


def k_neden(argv):
    ap = argparse.ArgumentParser(prog="ork neden")
    ap.add_argument("hedef")
    ap.add_argument("sinif_ad")
    _istek_ekle(ap)
    a = ap.parse_args(argv)
    veri, anlik, durum = _baglam(a)
    ist = _istek(a)
    sef = _sef_coz(a, veri, durum)
    if sef:
        ist["sef"] = sef
    satirlar, _ = secici.neden(a.hedef, a.sinif_ad, veri, anlik, durum, istek=ist)
    print("\n".join(satirlar))
    return 0


def k_alanlar(argv):
    ap = argparse.ArgumentParser(prog="ork alanlar", description="Geçerli alan, alt alan ve sınıf adları")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    s = Veri.yukle().siniflar
    if a.json:
        print(json.dumps({"siniflar": s.get("q"), "alanlar": s.get("alanlar")}, ensure_ascii=False, indent=2))
        return 0
    print("SINIF " + ", ".join(f"{k} (Q{v})" for k, v in sorted((s.get("q") or {}).items(), key=lambda x: x[1])))
    for alan, alts in (s.get("alanlar") or {}).items():
        print(f"{alan:14s} " + ", ".join(alts or []))
    print("genel          (alt alan yok: genel Z)")
    return 0


def k_platform(argv):
    ap = argparse.ArgumentParser(prog="ork platform", description="Yeni platform sinyali kararı (yanlış pozitif "
                                 "yoksayılır; kabul, aday platformun aktifleşme koşullarından biridir: + giriş + "
                                 "otomatik çağrı izni + ücretsiz/abonelik + erişim; kayıt `ork guncelle platform-ekle`)")
    ap.add_argument("eylem", choices=["yoksay", "kabul", "liste"])
    ap.add_argument("id", nargs="?")
    a = ap.parse_args(argv)
    if a.eylem == "liste":
        print(json.dumps(guncelle.platform_kararlari(), ensure_ascii=False))
        return 0
    if not a.id:
        ap.error("platform kimliği gerekli")
    d = guncelle.platform_karari_yaz(a.eylem, a.id)
    print(f"PLATFORM {a.id}: {a.eylem} · yoksay {len(d['yoksay'])}, kabul {len(d['kabul'])}")
    return 0


def k_durum(argv):
    print(kota.soguma_metni(kota.soguma_oku()) or "soğuma yok")
    d = kota.durum_oku()
    print(json.dumps({k: d.get(k) for k in ("sef", "onde", "tercihli", "son_secim", "agy_otomatik_kapali",
                                            "sor_kararlari", "basari")}, ensure_ascii=False, indent=2))
    return 0


def _atlananlar(sonuc):
    out = {}
    for _, neden in sonuc.skipped:
        out[neden] = out.get(neden, 0) + 1
    return out


def k_kontrol(argv):
    testler = skill_kok() / "tests"
    ortam = {k: os.environ.get(k) for k in ("ORKESTRA_DIR", "ORKESTRA_KISISEL", "ORKESTRA_KOTA_KAYNAGI",
                                                  "ORKESTRA_KOTA_ANLIK")}
    paket = unittest.defaultTestLoader.discover(str(testler), pattern="test_*.py", top_level_dir=str(testler))
    sonuc = unittest.TextTestRunner(verbosity=1).run(paket)
    for k, v in ortam.items():                    # testler durum dizinini geçici klasöre yönlendirir: geri al
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    for neden, n in sorted(_atlananlar(sonuc).items()):
        print(f"ATLANDI {n} test: {neden}")
    hata = []
    try:
        v = Veri.yukle()
        hata = v.denetle(skill_kok() / "data" / "sema")
        _notlar(v)
    except VeriHatasi as e:
        hata = [str(e)]
    for h in hata[:30]:
        print(f"VERİ {h}")
    return 0 if sonuc.wasSuccessful() and not hata else 1


KOMUTLAR = {"sec": k_sec, "neden": k_neden, "alanlar": k_alanlar, "kota": kota.main, "kesif": kesif.main,
            "guncelle": guncelle.main, "platform": k_platform, "durum": k_durum, "kontrol": k_kontrol,
            "rol": araclar.rol_main, "olc": araclar.olc_main, "brief": araclar.brief_main,
            "ajanlar": araclar.ajanlar_main, "kur": araclar.kur_main, "disa-aktar": araclar.disa_aktar_main,
            "bedava": araclar.bedava_main, "suru": suru.main, "plan": k_plan, "gizlilik": k_gizlilik}


def main(argv=None):
    _utf8()
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help") or argv[0] not in KOMUTLAR:
        print(__doc__)
        return 0 if (not argv or argv[0] in ("-h", "--help")) else 2
    try:
        return KOMUTLAR[argv[0]](argv[1:]) or 0
    except VeriHatasi as e:
        print(f"HATA {e}")
        return 3


if __name__ == "__main__":
    sys.exit(main())
