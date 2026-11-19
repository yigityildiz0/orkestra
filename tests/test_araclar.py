"""araclar: rol, olc, brief, ajanlar, tara/disa-aktar, bedava (ağsız) + CLI bayrak takma adları ve çağrı satırı."""
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import _ortak as O
import ork.araclar as A
from ork import secici
from ork.veri import Veri

GERCEK = O.KOK / "data"
VAR = O.GERCEK_VAR


def _cagir(fn, argv):
    b = io.StringIO()
    with redirect_stdout(b):
        kod = fn(argv)
    return kod, b.getvalue()


class Olc(unittest.TestCase):
    def setUp(self):
        A.olc_yolu().unlink(missing_ok=True)

    def test_kaydet_ve_ozet(self):
        k, h = A.olc_kaydet({"is_id": "t", "sinif": "kod", "alan": "kod", "model": "claude-opus-5-5", "efor": "high",
                             "havuz": "claude_max", "aile": "anthropic", "durum": "ok"})
        self.assertEqual(h, [])
        self.assertIn("zaman", k)
        self.assertEqual(len(A.olc_oku()), 1)

    def test_sema_disi_kayit_yazilmaz(self):
        _, h = A.olc_kaydet({"is_id": "t", "sinif": "yok", "alan": "kod", "model": "m", "efor": "high",
                             "havuz": "h", "aile": "a", "durum": "ok"})
        self.assertTrue(h)
        self.assertEqual(A.olc_oku(), [])


class Tarama(unittest.TestCase):
    def test_sir_desenleri(self):
        # desenler parçalı yazılır: bu dosya dışa aktarma taramasından da geçer
        self.assertTrue(A.tara("OPENAI_API_KEY=" + "sk-" + "abcdefghijklmnopqrstuvwx"))
        self.assertTrue(A.tara("-----BEGIN RSA " + "PRIVATE KEY-----"))
        self.assertEqual(A.tara("Fransa'nın başkenti neresidir?"), [])

    def test_kisisel_ve_yol_baglami(self):
        b = {t for t, _ in A.tara("C:" + r"\Users\Ali\x ali" + "@ornek.com", kisisel=True)}
        self.assertTrue({"kullanıcı dizini", "e-posta"} <= b)
        self.assertEqual(A.tara("hukuki/klinik metin; klinik iddia", kisisel=True, yollar=["klinik"]), [])
        self.assertTrue(A.tara("~/Desk" + "top/a.txt", kisisel=True, yollar=["Desktop"]))
        self.assertTrue(A.tara("Docu" + "ments\\Beyin\\x.md", kisisel=True, yollar=["Documents" + "/Beyin"]))

    def test_tc_saglama(self):
        self.assertTrue(A._tc_gecerli("1000000" + "0146"))
        self.assertFalse(A._tc_gecerli("12345678901"))


class Brief(unittest.TestCase):
    def test_adaptor_ve_zorunlu_alan(self):
        v = O.veri()
        r = A.brief_uret({"A": {"ROL": "x"}}, v, "opus")
        self.assertEqual(r["adaptor"], "claude-xml")
        self.assertIn("KAPSAM DIŞI", r["eksik"])
        r2 = A.brief_uret({"A": {"ROL": "x"}}, v, "tanimsiz-model")
        self.assertEqual(r2["adaptor"], "openai-bolumlu")
        self.assertTrue(r2["not"])

    def test_A_hash_kardeslerde_ayni(self):
        v = O.veri()
        a = {"A": {"ROL": "x", "KARAR SÖZLÜĞÜ": "y"}}
        r1 = A.brief_uret(dict(a, C={"PARÇA": "1"}), v, "opus")
        r2 = A.brief_uret(dict(a, C={"PARÇA": "2"}), v, "opus")
        self.assertEqual(r1["brief_hash_A"], r2["brief_hash_A"])

    def test_proje_grafigi_satiri_B_katmaninda(self):
        """Genel satır her tam briefte B katmanında: grafik varsa oku, yoksa yoksay; kişisel yol yok; hafif briefte yok."""
        v = O.veri()
        r = A.brief_uret({"A": {"ROL": "x"}}, v, "sonnet")
        satir = "PROJE GRAFİĞİ: proje grafiği varsa graphify-out/GRAPH_REPORT.md ve grafik sorgusunu oku; yoksa yoksay"
        self.assertIn(satir, r["metin"])
        b = r["metin"].split("<context>")[1].split("</context>")[0]       # claude-xml: B katmanı <context> içinde
        self.assertIn(satir, b)
        self.assertEqual(r["metin"].count("GRAPH_REPORT.md"), 1)
        self.assertNotRegex(r["metin"], r"[A-Za-z]:[\/]")                  # sürücü yolu yok
        # lider kendi değerini verirse ona saygı gösterilir; hafif kipte (yalnız C katmanı) eklenmez
        r2 = A.brief_uret({"B": {"PROJE GRAFİĞİ": "grafik yok"}}, v, "sonnet")
        self.assertIn("PROJE GRAFİĞİ: grafik yok", r2["metin"])
        self.assertNotIn("GRAPH_REPORT", r2["metin"])
        r3 = A.brief_uret({"C": {"BİTTİ ÖLÇÜTÜ": "z"}}, v, "sonnet", hafif=True)
        self.assertNotIn("GRAPH_REPORT", r3["metin"])
        for hedef in ("sol", "hydrogen", "deepseek_flash"):                # her adaptörde B katmanı aynı satırı taşır
            self.assertIn("graphify-out/GRAPH_REPORT.md", A.brief_uret({"A": {"ROL": "x"}}, v, hedef)["metin"])


@unittest.skipUnless(VAR, O.GERCEK_NEDEN)
class GercekVeri(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.v = O.gercek_veri()

    def test_ajanlar_yaz_yasak_hatti_duzeltir(self):
        with tempfile.TemporaryDirectory() as cd, tempfile.TemporaryDirectory() as xd:
            yasak = next((r for r, x in self.v.roller.items() if x.get("saglayici") == "openai"
                          and (self.v.yasak_mi(x.get("aktif") or "", None)[0]
                               or self.v.once_sor_mi(x.get("aktif") or "", None)[0])), None)
            if yasak is None:
                self.skipTest("kişisel kuralda yasak ya da önce-sor OpenAI hattı yok")
            eslem = self.v.kurallar.get("ajan_dosyalari") or {}
            for ad in (eslem.get("codex") or {}):
                Path(xd, f"{ad}.toml").write_text(f'name = "{ad}"\nmodel = "{self.v.roller[yasak]["aktif"]}"\n'
                                                  'model_reasoning_effort = "low"\n', encoding="utf-8")
            plan = A.ajan_plani(self.v, cd, xd)
            self.assertTrue(any("YASAK" in s or "ÖNCE SOR" in s for x in plan for s in x["sorun"]))
            for x in plan:
                if x["sorun"]:
                    A.ajan_yaz(x)
            plan2 = A.ajan_plani(self.v, cd, xd)
            self.assertEqual([x["sorun"] for x in plan2], [[] for _ in plan2])
            self.assertTrue(Path(cd, "Explore.md").is_file())
            self.assertIn("tools:", Path(cd, "Explore.md").read_text(encoding="utf-8"))
            self.assertTrue(list(Path(xd).glob("*.bak-orkestra-*")))

    def test_disa_aktar_genel_dosyalar_temiz(self):
        r = A.disa_aktar(None, kuru=True, veri=self.v)
        self.assertEqual(r["bulgular"], {})
        self.assertNotIn("data/kullanici-kurallari.json", r["dosya"])
        self.assertNotIn("data/platformlar.json", r["dosya"])

    def test_bedava_ag_yok(self):
        b = A.bedava_platformu(self.v)
        if not b:
            self.skipTest("bedava istisna yok")
        with tempfile.TemporaryDirectory() as d:
            f = Path(d, "i.txt")
            f.write_text("Fransa'nın başkenti neresidir?", encoding="utf-8")
            post = []
            bp = self.v.platformlar.get(b["platform"], {})
            bh = self.v.havuz(b.get("havuz") or b["platform"])
            gz_b = b.get("gizlilik") or bh.get("gizlilik") or bp.get("gizlilik") or "kamu"
            if b.get("veri") == "kisisel" and gz_b == "ozel":
                self.assertEqual(_cagir(lambda a: A.bedava_main(a, _post=post.append, _veri=self.v),
                                        ["calistir", "--model", "x", "--istem", str(f), "--veri", "saglik"])[0], 3)
                self.assertEqual(_cagir(lambda a: A.bedava_main(a, _post=post.append, _veri=self.v),
                                        ["calistir", "--model", "x", "--istem", str(f), "--veri", "kisisel", "--kuru"])[0], 0)
            else:
                self.assertEqual(_cagir(lambda a: A.bedava_main(a, _post=post.append, _veri=self.v),
                                        ["calistir", "--model", "x", "--istem", str(f), "--veri", "kisisel"])[0], 3)
                self.assertEqual(_cagir(lambda a: A.bedava_main(a, _post=post.append, _veri=self.v),
                                        ["calistir", "--model", "x", "--istem", str(f), "--veri", "genel", "--kuru"])[0], 0)
            f.write_text("TOK" + "EN=abcdefghijklmnopqrstu", encoding="utf-8")
            self.assertEqual(_cagir(lambda a: A.bedava_main(a, _post=post.append, _veri=self.v),
                                    ["calistir", "--model", "x", "--istem", str(f), "--veri", "genel"])[0], 3)
            f.write_text("Hasta: Ayşe Demir, Tanı: M54.5", encoding="utf-8")
            self.assertEqual(_cagir(lambda a: A.bedava_main(a, _post=post.append, _veri=self.v),
                                    ["calistir", "--model", "x", "--istem", str(f), "--veri", "genel"])[0], 3)
            self.assertEqual(post, [])

    def test_rol_esigi_ve_aile_elemesi(self):
        k = O.kota()
        i = secici.istek_hazirla({"rol_is": "hakem", "tur": "rol", "sinif": "kod", "veri": "genel"}, self.v)
        hk = self.v.siniflar["roller_is"]["hakem"]
        self.assertEqual(i["Q"], max(hk["taban"], self.v.siniflar["q"]["kod"] - hk["fark"]))
        self.assertTrue(i["kamu_yasak"])
        r = secici.sec({"rol_is": "hakem", "tur": "rol", "sinif": "kod", "veri": "genel", "haric_aile": "anthropic"},
                       self.v, k, {})
        s = r.get("secim") or r.get("elle_oneri")
        if s:
            self.assertNotEqual(s["aile"], "anthropic")

    def test_claude_cagrisi_takma_ad_tasir(self):
        r = secici.sec({"sinif": "kod", "alan": "kod", "alt_alan": "refaktor", "veri": "kisisel"}, self.v,
                       O.kota(codex=(0.0, 0.0)), {})
        c = r.get("cagri") or {}
        if c.get("yol") == "claude-agent":
            self.assertTrue(c.get("takma"))
            self.assertNotIn("{takma}", c.get("komut", ""))
            self.assertNotEqual(c["model"], c["takma"])        # CLI kesin kimlik, Agent takma ad

    def test_parca_plani(self):
        r = secici.sec({"sinif": "normal", "alan": "yazim", "alt_alan": "rapor", "veri": "genel", "parca": 4},
                       self.v, O.kota(), {})
        if r.get("secim"):
            self.assertEqual(sum(x["parca"] for x in r["parca_plani"]), 4)


class CLI(unittest.TestCase):
    def test_skill_md_bayraklari_taninir(self):
        import ork as _p  # noqa: F401
        import importlib.util
        spec = importlib.util.spec_from_file_location("ork_cli", O.KOK / "scripts" / "ork.py")
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        import argparse
        ap = argparse.ArgumentParser()
        m._istek_ekle(ap)
        a = ap.parse_args(["--sinif", "kod", "--alan", "kod", "--alt-alan", "ui", "--veri", "genel", "--boyut", "orta",
                           "--kipler", "metin,gorsel", "--duzenle", "--sure-dk", "10", "--parca", "3", "--kip", "hafif",
                           "--zorla", "sol:high", "--json"])
        i = m._istek(a)
        self.assertEqual((i["alt_alan"], i["duzenleme"], i["sure_dk"], i["parca"]), ("ui", True, 10.0, 3))
        for alt in ("rol", "olc", "brief", "ajanlar", "disa-aktar", "bedava", "kota", "sec", "neden", "guncelle",
                    "kontrol"):
            self.assertIn(alt, m.KOMUTLAR)


if __name__ == "__main__":
    unittest.main()
