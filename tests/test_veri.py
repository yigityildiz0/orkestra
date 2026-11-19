"""Veri katmanı + gerçek data/*.json duman testi (dosyalar varsa). Gerçek veri değişebilir: duman testleri yalnız
değişmezleri sınar (yasak hat seçilmez, kesin kimlik, ölçek kilidi, rol çözümü)."""
import json
import unittest
from pathlib import Path

import _ortak as O
from ork import secici
from ork.veri import Veri, VeriHatasi, json_oku, platform_normalle, sema_dogrula

GERCEK = O.KOK / "data"
VAR = O.GERCEK_VAR


class Katman(unittest.TestCase):
    def test_platform_normalle(self):
        p = platform_normalle("agy", O.ham()["platformlar"]["platformlar"]["agy"])
        self.assertEqual(p["yol"], "agy-elle")
        e = {x["kimlik"]: x for x in p["erisim"]}
        self.assertEqual(e["gemini-4-hydrogen"]["kimlik_sablon"], "gemini-4-hydrogen-{efor}")
        self.assertTrue(e["gemini-4-hydrogen"]["elle"])                    # otomatik_cagri false
        self.assertEqual(e["claude-opus-5-5"]["z_duzeltme"], -2)

    def test_K_p_bicimleri(self):
        v = O.veri()
        self.assertEqual(v.K_p("claude_max", "hafta")[:2], (600.0, "oncul"))
        self.assertIsNone(v.K_p("claude_max", "5s")[0])                     # null: seçicide türetilir
        self.assertEqual(v.K_p("bedava", "gun"), (1000000.0, "oncul", "token"))
        self.assertEqual(v.karar_pencereleri("claude_max"), ["5s", "hafta"])
        self.assertEqual(v.havuz("bedava")["okuyucu"], "bedava_api")

    def test_taban_glob_ve_faz(self):
        v = O.veri()
        self.assertEqual(v.taban("claude_max", "5s"), 0.15)
        self.assertEqual(v.taban("agy_gemini", "hafta"), 0.0)
        self.assertEqual(v.faz()["claude_esik_u"], 0.25)

    def test_rol_cozumu(self):
        v = O.veri()
        self.assertEqual(v.rol_coz("sol"), "gpt-6.1-sol")
        with self.assertRaises(VeriHatasi):
            v.rol_coz("olmayan")

    def test_sema_dogrulayici(self):
        sema = {"type": "object", "required": ["a"], "properties": {"a": {"type": "integer", "minimum": 1}},
                "additionalProperties": False}
        self.assertEqual(sema_dogrula({"a": 2}, sema), [])
        self.assertTrue(sema_dogrula({"a": 0, "b": 1}, sema))


@unittest.skipUnless(VAR, O.GERCEK_NEDEN)
class GercekVeriDuman(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.v = O.gercek_veri()

    def test_olcek_ve_rol(self):
        h = self.v.denetle()
        self.assertFalse([x for x in h if x.startswith("ölçek karışık")], h)
        for rol in ("opus", "sonnet", "haiku", "sol", "terra"):
            if rol in self.v.roller:
                self.assertIn(self.v.rol_coz(rol), self.v.model_kayitlari)

    def test_sema_varsa_gecerli(self):
        sd = GERCEK / "sema"
        if not any(sd.glob("*.schema.json")):
            self.skipTest("şema dosyaları henüz yok")
        h = [x for x in self.v.denetle(sd) if x.startswith("şema")]
        self.assertEqual(h, [])

    def test_secimler_degismezleri_korur(self):
        yasak = set((self.v.kurallar.get("yasak") or {}).get("saglayici_hat", []))
        roller = set(self.v.roller)
        kota = O.kota()
        istekler = [{"sinif": s} for s in ("mekanik", "basit", "normal", "kod", "zor", "kritik")]
        for alan, alts in (self.v.siniflar.get("alanlar") or {}).items():
            for alt in alts:
                istekler.append({"alan": alan, "alt_alan": alt, "sinif": "normal"})
        for ist in istekler:
            r = secici.sec(ist, self.v, kota, {}, O.SIMDI)
            s = r.get("secim")
            if s:
                self.assertNotIn(f"{s['aile']}/{s['hat']}", yasak, ist)
                self.assertNotIn(r["cagri"]["model"], roller, ist)          # çıplak rol adı CLI'a gitmez
                if r["durum"] == "secildi" and r.get("kaynak") is None:      # normal akış: Q taban
                    self.assertGreaterEqual(s["z_etkin"], r["istek"]["Q"] - 1e-9, ist)

    def test_gorsel_sabit_kural(self):
        sab = (self.v.kurallar.get("sabit_kurallar") or {}).get("gorsel_uretim")
        if not sab:
            self.skipTest("sabit kural yok")
        r = secici.sec({"alan": "gorsel_uretim", "sinif": "normal"}, self.v, O.kota(), {}, O.SIMDI)
        self.assertEqual(r["cagri"]["model"], self.v.rol_coz(sab["rol"]))
        self.assertEqual(r["cagri"]["efor"], sab["efor"])

    def test_ornek_dosyalar_kisisel_veri_icermez(self):
        sozluk = [x.lower() for x in ((self.v.kurallar.get("gizlilik") or {}).get("ek_sozluk") or [])]
        for f in GERCEK.glob("*.ornek.json"):
            metin = f.read_text(encoding="utf-8").lower()
            for s in sozluk:
                self.assertNotIn(s, metin, f"{f.name}: kişisel sözlük öğesi")


if __name__ == "__main__":
    unittest.main()
