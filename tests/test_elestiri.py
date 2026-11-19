"""Eleştirmen bulgularının gerileme testleri (algoritma, kullanılabilirlik, gizlilik). Sentetik veri; ağ ve model yok."""
import io
import json
import os
import re
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import timedelta
from pathlib import Path

import _ortak as O
import ork.araclar as A
from ork import kota as K
from ork import secici
from ork.veri import Veri, yerel_birlestir, yerel_fark

S = O.SIMDI


def sec(istek, kota=None, durum=None, veri=None, simdi=S):
    return secici.sec(istek, veri or O.veri(), kota if kota is not None else O.kota(), durum or {}, simdi)


class Kalite(unittest.TestCase):
    def test_olcum_olcut_adiyla_alt_alanlar_arasi_bulunur(self):
        m = {"alanlar": {"yaratici": {"olcut": "arena:creative", "puan": 1449}}, "varyantlar": {"high": {"z": 50}}}
        p, _ = secici.olcum_bul(m, "high", "uzun_turkce", "arena:creative")
        self.assertEqual(p, 1449)

    def test_olcumsuz_aday_olculenin_onune_gecmez(self):
        v = O.veri()
        i = secici.istek_hazirla({"sinif": "kod", "alan": "kod", "alt_alan": "gunluk", "veri": "genel"}, v)
        a, _ = secici.adaylari_uret(i, v, {}, S)
        _, d, eksik = secici.kalite_hesapla(a, "gunluk", v)
        self.assertTrue(eksik)
        olculu = [x["q"] for x in a if not x.get("olcumsuz")]
        for x in a:
            if x.get("olcumsuz"):
                self.assertLess(x["q"], min(olculu))
        r = sec({"sinif": "kod", "alan": "kod", "alt_alan": "gunluk", "veri": "genel"})
        self.assertNotEqual(r["secim"]["rol"], "hydrogen")
        self.assertTrue(any("alan ölçümü yok" in x for x in r["elenen"].values()))

    def test_xhigh_kosulsuz_aday_olmaz_uzun_iste_olur(self):
        r = sec({"sinif": "normal", "veri": "genel"})
        self.assertNotEqual(r["secim"]["efor"], "xhigh")
        self.assertTrue(any("efor verimi" in x for x in r["elenen"].values()))
        i = secici.istek_hazirla({"sinif": "zor", "veri": "genel", "sinyaller": ["uzun_otonom"]}, O.veri())
        self.assertIn("uzun_otonom", i["sinyaller"])
        r2 = sec({"sinif": "zor", "veri": "genel", "sure_dk": 45})
        self.assertFalse(any("efor verimi" in x for k, x in r2["elenen"].items() if k.startswith("opus@xhigh")))

    def test_kritikte_tek_yeterli_efor_korunur(self):
        r = sec({"sinif": "kritik"})
        self.assertEqual((r["secim"]["rol"], r["secim"]["efor"]), ("opus", "xhigh"))

    def test_hafif_kip_tirmanmaz(self):
        v = O.veri()
        r = sec({"sinif": "normal", "veri": "genel", "kip": "hafif"})
        pay = v.siniflar["fazla_zeka"]["pay"]
        self.assertLessEqual(r["secim"]["z"], r["istek"]["Q"] + pay)
        self.assertEqual(r["isci_tavan"], 2)


class Dusus(unittest.TestCase):
    def test_D1_kalite_kumesi_sigmazsa_alt_efor(self):
        r = sec({"sinif": "zor", "veri": "genel", "sure_dk": 45}, O.kota(claude=(0.30, 0.9), codex=(0.9, 0.21)))
        self.assertEqual(r["durum"], "secildi")
        self.assertGreaterEqual(r["secim"]["z_etkin"], 50)
        self.assertEqual(r.get("dusus"), "D1")

    def test_D2_rezerv_yerine_Q_ustu_baska_havuz(self):
        r = sec({"sinif": "normal", "veri": "genel"}, O.kota(claude=(0.9, 0.9), codex_durum="kapali"))
        self.assertEqual(r["durum"], "secildi")
        self.assertEqual(r["secim"]["havuz"], "claude_max")
        self.assertGreaterEqual(r["secim"]["z_etkin"], r["istek"]["Q"])

    def test_ana_havuz_bilinmiyorsa_rezervden_ve_uyari(self):
        k = O.kota(codex=(0.9, 0.21))
        k["havuzlar"]["claude_max"] = {"durum": "bilinmiyor", "pencereler": {}}
        r = sec({"sinif": "normal", "veri": "genel"}, k)
        if r.get("secim") and r["secim"]["havuz"] == "claude_max":
            self.assertEqual(r["secim"]["katman"], 4)
        self.assertTrue(any("kotası bilinmiyor" in u for u in r["uyarilar"]))


class Gizlilik(unittest.TestCase):
    def test_saglik_verisi_host_disina_onaysiz_gitmez(self):
        for v in ("saglik", "gizli"):
            r = sec({"sinif": "normal", "veri": v})
            self.assertIn(r["secim"]["aile"], ("anthropic",), v)
            self.assertTrue(any("--dis-onay" in x for x in r["elenen"].values()))
        r = sec({"sinif": "normal", "veri": "saglik", "dis_onay": True}, O.kota(claude=(0.9, 0.9), codex=(0.9, 0.9)))
        self.assertFalse(any("--dis-onay" in x for x in r["elenen"].values()))

    def test_elle_secenekler_gizlilikten_suzulur(self):
        r = sec({"alan": "gorsel_uretim", "alt_alan": "t2i", "sinif": "normal", "veri": "kisisel"},
                O.kota(codex=(0.9, 0.20)))
        self.assertEqual(r["durum"], "elle")
        self.assertFalse(any("gemini-uygulamasi" in x for x in r["elle_secenekler"]))
        r2 = sec({"alan": "gorsel_uretim", "alt_alan": "t2i", "sinif": "normal", "veri": "genel"},
                 O.kota(codex=(0.9, 0.20)))
        self.assertTrue(any("gemini-uygulamasi" in x for x in r2["elle_secenekler"]))

    def test_bedava_havuz_okunamazsa_secilmez(self):
        k = O.kota()
        k["havuzlar"]["bedava"] = {"durum": "bilinmiyor", "pencereler": {}, "notlar": ["OKUNAMADI (anahtar yok)"]}
        r = sec({"sinif": "basit", "veri": "genel"}, k)
        self.assertNotEqual(r["secim"]["havuz"], "bedava")

    def test_kota_okuyucu_anahtar_yoksa_kapali(self):
        v = O.veri()
        an = K.oku(v, simdi=S, onbellek=False, adaptor={"codex": lambda: None,
                                                        "bedava": lambda h, a, s: (None, "OKUNAMADI (anahtar yok)")})
        self.assertEqual(an["havuzlar"]["bedava"]["durum"], "kapali")


class Kapasite(unittest.TestCase):
    def test_sigma_ham_degerle_kova_yalniz_tercihte(self):
        v = O.veri()
        h = v.havuz("codex_plus")
        p = secici.pencereler("codex_plus", h, v, O.kota(codex=(0.9, 0.349)), {}, S, {})
        self.assertAlmostEqual(p["hafta"]["k"], 0.30)
        self.assertGreater(p["hafta"]["m_ham"], p["hafta"]["m"])

    def test_ana_havuz_rezervinin_tek_kaynagi_faz(self):
        def d(x):
            x["kullanici-kurallari"]["faz"]["claude_esik_u"] = 0.5
        v = O.veri(d)
        self.assertAlmostEqual(secici._rezerv_miktar(v.rezerv("claude_max"), 0.3, v.faz()["claude_esik_u"]), 0.35)

    def test_parca_toplam_sigiyorsa_bolunmez(self):
        r = sec({"sinif": "kod", "alan": "kod", "alt_alan": "gunluk", "veri": "genel", "parca": 6})
        plan = r["parca_plani"]
        self.assertEqual(sum(x["parca"] for x in plan), 6)
        self.assertEqual(len(plan), 1)

    def test_dogrulayici_farkli_aile_yoksa_ayni_aile_zayif(self):
        r = sec({"sinif": "normal", "veri": "saglik"})
        d = r["dogrulayici"]
        if d["model"]:
            self.assertEqual(d["zayif_dogrulama"], d["model"]["aile"] == r["secim"]["aile"])
            self.assertNotEqual(d["model"]["kimlik"], r["secim"]["kimlik"])
        self.assertIn("kaskad", r)

    def test_video_kipi_alansiz_gelirse_video_analizine_eslenir(self):
        i = secici.istek_hazirla({"sinif": "normal", "kipler": ["metin", "video"]}, O.veri())
        self.assertEqual(i["alan"], "video_analiz")


class Cagri(unittest.TestCase):
    def test_claude_cagrisi_effort_ve_takma_tasir(self):
        r = sec({"sinif": "normal", "veri": "saglik"})
        c = r["cagri"]
        self.assertEqual(c["yol"], "claude-agent")
        self.assertIn(f"effort={c['efor']}", c["komut"])
        self.assertIn(f"model={c['takma']}", c["komut"])
        self.assertEqual(c["olc_taslak"]["model"], r["secim"]["kimlik"])

    def test_codex_sandbox_duzenlemede_dolar(self):
        r = sec({"sinif": "normal", "veri": "genel", "zorla": "sol:high", "duzenleme": True})
        self.assertIn("-s workspace-write", r["cagri"]["komut"])
        self.assertNotIn("sandbox", r["cagri"]["bos_alanlar"])


class Kota(unittest.TestCase):
    def test_claude_degeri_kendi_onbelleginde_45_dk(self):
        v = O.veri()
        K.claude_yolu().unlink(missing_ok=True)
        K.oku(v, simdi=S, onbellek=False, claude="5s=80,hafta=70", adaptor={"codex": lambda: None})
        an = K.oku(v, simdi=S + timedelta(minutes=25), onbellek=False, adaptor={"codex": lambda: None})
        self.assertEqual(an["havuzlar"]["claude_max"]["durum"], "ok")
        self.assertTrue(any("dk önceki" in n for n in an["havuzlar"]["claude_max"]["notlar"]))
        an2 = K.oku(v, simdi=S + timedelta(minutes=50), onbellek=False, adaptor={"codex": lambda: None})
        self.assertEqual(an2["havuzlar"]["claude_max"]["durum"], "bilinmiyor")


class Tarama(unittest.TestCase):
    def test_sozluk_alt_cizgi_ve_birlesik_ad(self):
        sz = ["Ali"]
        self.assertTrue(A.tara("ajan ali_quick low", kisisel=True, sozluk=sz))
        self.assertTrue(A.tara("AliVeli hesabı", kisisel=True, sozluk=sz))
        self.assertEqual(A.tara("Alican geldi", kisisel=True, sozluk=sz), [])
        self.assertTrue(A.tara("Çağrı geldi", kisisel=True, sozluk=["Cagri"]))   # Türkçe harf ASCII katlanır

    def test_ek_sir_ve_yol_desenleri(self):
        self.assertTrue(A.tara("hf_" + "a1B2c3D4e5F6g7H8i9J0k1"))
        self.assertTrue(A.tara("ya29." + "a0AfH6SMBx1234567890abcdef"))
        self.assertTrue(A.tara("X-Api-Key: " + "abcdef1234567890abcd"))
        self.assertTrue(A.tara("setx GIZLI_TOKEN " + "abcdef1234567890xyz"))
        self.assertTrue(A.tara("D:" + "\\Whisper\\modeller", kisisel=True))
        self.assertTrue(A.tara("anahtar degeri burada", degerler=["degeri burada"]))

    def test_disa_aktar_sozluksuz_durur(self):
        def d(x):
            x["kullanici-kurallari"]["gizlilik"] = {"ek_sozluk": []}
        r = A.disa_aktar(None, kuru=True, veri=O.veri(d), ek_sozluk=[])
        self.assertTrue(r["bulgular"])
        self.assertEqual(r["dosya"], [])


class Brief(unittest.TestCase):
    def test_katman_etiketi_sizmaz_ve_hafif(self):
        v = O.veri()
        r = A.brief_uret({"C": {"BİTTİ ÖLÇÜTÜ": "test geçer"}}, v, "sol", hafif=True)
        self.assertNotIn("[A.", r["metin"])
        self.assertEqual(r["eksik"], [])
        r2 = A.brief_uret({}, v, "opus")
        self.assertNotIn("SABİT ÖNEK", r2["metin"])

    def test_aile_cumlesi_kanit_duzeyine_gore(self):
        v = O.veri()
        r = A.brief_uret({}, v, "haiku")
        self.assertTrue(any("Bilgin eski olabilir" in x for x in r["aile_cumleleri"]))
        self.assertEqual(A.brief_uret({}, v, "sol")["aile_cumleleri"], [])                 # DY: varsayılan değil
        self.assertTrue(A.brief_uret({}, v, "sol", deneme=True)["aile_cumleleri"])


class Kurulum(unittest.TestCase):
    def test_kur_komutu_idempotent_ve_denetle(self):
        with tempfile.TemporaryDirectory() as ev, tempfile.TemporaryDirectory() as dd:
            eski = os.environ["ORKESTRA_DIR"]
            os.environ["ORKESTRA_DIR"] = dd
            try:
                b = io.StringIO()
                with redirect_stdout(b):
                    self.assertEqual(A.kur_main(["--denetle"], ev=ev), 1)
                    self.assertEqual(A.kur_main([], ev=ev), 0)
                    self.assertEqual(A.kur_main(["--denetle"], ev=ev), 0)
                    self.assertEqual(A.kur_main([], ev=ev), 0)
                self.assertTrue(Path(ev, ".claude", "commands", "orkestra-guncelle.md").is_file())
                self.assertTrue(Path(dd, "kullanici-kurallari.json").is_file())
                self.assertFalse(list(Path(ev, ".claude", "commands").glob("*.bak-orkestra-*")))
            finally:
                os.environ["ORKESTRA_DIR"] = eski

    def test_kur_eski_semayi_yedekleyip_yeniler(self):
        with tempfile.TemporaryDirectory() as ev, tempfile.TemporaryDirectory() as dd:
            eski = os.environ["ORKESTRA_DIR"]
            os.environ["ORKESTRA_DIR"] = dd
            try:
                Path(dd, "platformlar.json").write_text(json.dumps({"sema": 6, "platformlar": {}}), encoding="utf-8")
                b = io.StringIO()
                with redirect_stdout(b):
                    self.assertEqual(A.kur_main(["--denetle"], ev=ev), 1)
                    self.assertEqual(A.kur_main([], ev=ev), 0)
                self.assertGreaterEqual(json.loads(Path(dd, "platformlar.json").read_text(encoding="utf-8"))["sema"], 7)
                self.assertTrue(list(Path(dd).glob("platformlar.json.bak-orkestra-*")))
                self.assertIn("eski şema", b.getvalue())
            finally:
                os.environ["ORKESTRA_DIR"] = eski

    def test_menu_ve_skill_frontmatter(self):
        def fm(p):
            m = re.match(r"^---\n(.*?)\n---\n", p.read_text(encoding="utf-8"), re.S)
            self.assertIsNotNone(m, p.name)
            out = {}
            for satir in m.group(1).splitlines():
                k, _, v = satir.partition(":")
                out[k.strip()] = v.strip().strip('"')
            return out
        s = fm(O.KOK / "SKILL.md")
        self.assertEqual(s["name"], "orkestra")
        self.assertLessEqual(len(s["description"]) + len(s.get("when_to_use", "")), 1536)
        self.assertIn("guncelle", s.get("argument-hint", ""))
        c = fm(O.KOK / "commands" / "orkestra-guncelle.md")
        self.assertTrue(c.get("description"))
        self.assertEqual(c.get("disable-model-invocation"), "true")
        self.assertNotIn("scripts/ork.py\"", (O.KOK / "SKILL.md").read_text(encoding="utf-8").replace(
            '${CLAUDE_SKILL_DIR}/scripts/ork.py"', ""))          # göreli betik yolu yok


class Katman(unittest.TestCase):
    def test_yerel_yama_gidis_donus(self):
        taban = {"sema": 7, "modeller": {"a": {"z": 1}, "b": {"z": 2}}, "roller": {"r": {"aktif": "a"}}}
        yeni = {"sema": 7, "modeller": {"a": {"z": 1}, "b": {"z": 3}, "c": {"z": 4}}, "roller": {"r": {"aktif": "c"}}}
        f = yerel_fark(taban, yeni)
        self.assertEqual(set(f["modeller"]), {"b", "c"})
        self.assertEqual(yerel_birlestir(taban, f)["modeller"], yeni["modeller"])
        self.assertEqual(yerel_birlestir(taban, f)["roller"], yeni["roller"])

    def test_genel_veri_yerel_kayda_basvurmaz(self):
        """Depodaki modeller.json kişisel yerel katmandaki bir modele (rota, sıra, lider) başvurmaz; başvurursa kişisel
        envanter herkese açık dosyaya sızar ve yerel katmansız kurulumda kırık rota kalır."""
        m = json.loads((O.KOK / "data" / "modeller.json").read_text(encoding="utf-8"))
        kay = set(m.get("modeller") or {})
        for k, lst in (m.get("rotalar") or {}).items():
            for r in lst:
                if r.get("yol") == "yerel":
                    self.assertIn(r.get("arac"), kay, f"{k}: {r.get('arac')}")
        for alt, L in (m.get("liderler") or {}).items():
            for x in [L.get("lider"), L.get("aday")] + list(L.get("sira") or []):
                if x and not str(x).startswith("arac:"):
                    self.assertIn(str(x).split("@")[0], kay, f"liderler.{alt}: {x}")
        self.assertEqual(A.tara((O.KOK / "references" / "alanlar.md").read_text(encoding="utf-8"),
                                kisisel=True), [])

    def test_kucuk_modelin_maliyeti_buyugunden_fazla_olamaz(self):
        def d(x):
            x["modeller"]["roller"]["haiku"]["boyut"] = "S"
            x["modeller"]["roller"]["opus"]["boyut"] = "L"
            x["modeller"]["modeller"]["claude-haiku-5-5"]["varyantlar"]["high"]["gorev_usd"] = 99.0
        h = O.veri(d).denetle()
        self.assertTrue(any("maliyet" in x for x in h), h)


class CLI(unittest.TestCase):
    def test_bilinmeyen_alt_alan_yakın_oneriyle_reddedilir(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("ork_cli2", O.KOK / "scripts" / "ork.py")
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        import argparse
        ap = argparse.ArgumentParser()
        m._istek_ekle(ap)
        a = ap.parse_args(["--sinif", "kod", "--alan", "kod", "--alt-alan", "gunluk_typo"])
        h = m._ad_dogrula(a, O.veri())
        self.assertTrue(h)
        self.assertIn("gunluk", h[0])
        self.assertIn("alanlar", m.KOMUTLAR)
        self.assertIn("kur", m.KOMUTLAR)


class Belge(unittest.TestCase):
    """Tasarım 12.3: SKILL.md bütçesi ve genel örneklerde güvenli varsayılanlar."""
    KOK = Path(__file__).resolve().parents[1]

    def test_skill_md_12000_bayt(self):
        self.assertLessEqual(len((self.KOK / "SKILL.md").read_bytes()), 12000)

    def test_ornek_agy_otomatik_kapali(self):
        k = json.loads((self.KOK / "data" / "kullanici-kurallari.ornek.json").read_text(encoding="utf-8"))
        self.assertIs(Veri.sozlukten({"kurallar": k}).agy_otomatik()["acik"], False)

    def test_sabit_sira_bedava_agy_codex_claude(self):
        s = json.loads((self.KOK / "data" / "siniflar.json").read_text(encoding="utf-8"))
        self.assertEqual(s["secici"]["sabit_sira"], ["bedava", "agy", "codex", "claude"])

    def test_suru_md_haritada(self):
        self.assertIn("references/suru.md", (self.KOK / "SKILL.md").read_text(encoding="utf-8"))
        self.assertTrue((self.KOK / "references" / "suru.md").is_file())


if __name__ == "__main__":
    unittest.main()
