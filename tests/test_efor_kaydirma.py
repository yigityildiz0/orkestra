"""Efor düzeyi karşılaştırma (2026-11): ölçüt birimine duyarlı efor kaydırması, efor bildirmeyen kayıtta üst efor
çapası, efor başına ölçüm, yetenek süzgeci, güncelleme yazıcısının şemaya uygunluğu ve referans Pareto'su.
Saf fonksiyon testleri: ağ, model ve gerçek kişisel veri yok."""
import copy
import unittest
from datetime import datetime, timezone

import _ortak as O  # noqa: F401  (yol ve yalıtım)
from ork import guncelle, kesif, secici

S_AYAR = {"delta": {"aa_z": 2, "aa_alt_test": 3, "vals": 4, "arena_ci_yoksa": 14, "diger": 3},
          "efor_kaydirma": {"egim": {"vals": 1.3, "arena:webdev": 7.0, "arena:creative": 0.0, "_varsayilan": 1.0},
                            "yukari_tavan_delta": 1.0, "bos_efor_ust": ["vals"]}}
M = {"varyantlar": {"low": {"z": 41}, "medium": {"z": 53}, "high": {"z": 55}, "xhigh": {"z": 56}, "max": {"z": 57}}}


class EforKaydirma(unittest.TestCase):
    def test_ayar_yoksa_eski_davranis_ham_z_farki(self):
        o = {"olcut": "vals:x", "puan": 60.0, "efor": "max"}
        self.assertAlmostEqual(secici.olcum_puani(o, M, "medium"), 60.0 - 4)

    def test_asagi_yon_olcut_egimiyle(self):
        o = {"olcut": "vals:x", "puan": 60.0, "efor": "max"}
        self.assertAlmostEqual(secici.olcum_puani(o, M, "medium", True, S_AYAR), 60.0 - 4 * 1.3)
        self.assertAlmostEqual(secici.olcum_puani(o, M, "max", True, S_AYAR), 60.0)

    def test_elo_olcutunde_z_basina_yedi(self):
        o = {"olcut": "arena:webdev", "puan": 1743.0, "efor": "max"}
        self.assertAlmostEqual(secici.olcum_puani(o, M, "high", True, S_AYAR), 1743.0 - 2 * 7)

    def test_egim_sifir_kaydirmaz(self):
        o = {"olcut": "arena:creative", "puan": 1449.0, "efor": "max"}
        self.assertAlmostEqual(secici.olcum_puani(o, M, "low", True, S_AYAR), 1449.0)

    def test_yukari_yon_gurultu_bandiyla_sinirli(self):
        # low'da ölçülmüş 40; max'a 16 Z x 1.3 = 20.8 puan çıkmaz: en çok +δ (vals 4)
        o = {"olcut": "vals:x", "puan": 40.0, "efor": "low"}
        self.assertAlmostEqual(secici.olcum_puani(o, M, "max", True, S_AYAR), 44.0)

    def test_bos_efor_dogrulanmis_olcutte_ust_capa(self):
        o = {"olcut": "vals:x", "puan": 60.0, "efor": None}
        self.assertAlmostEqual(secici.olcum_puani(o, M, "medium", True, S_AYAR), 60.0 - 4 * 1.3)

    def test_bos_efor_dogrulanmamis_olcutte_aynen(self):
        o = {"olcut": "scale:x", "puan": 82.0, "efor": None}
        self.assertAlmostEqual(secici.olcum_puani(o, M, "medium", True, S_AYAR), 82.0)

    def test_doymus_olcutte_kaydirma_yok(self):
        o = {"olcut": "vals:x", "puan": 60.0, "efor": "max"}
        self.assertAlmostEqual(secici.olcum_puani(o, M, "low", False, S_AYAR), 60.0)

    def test_efor_basina_olcum_once_gelir(self):
        o = {"olcut": "vals:x", "puan": 60.0, "efor": "max", "eforlar": {"max": 60.0, "medium": 58.5}}
        self.assertAlmostEqual(secici.olcum_puani(o, M, "medium", True, S_AYAR), 58.5)
        # ölçülmemiş high: Z bakımından en yakın ölçülü efor (max, |57-55| = medium ile eşit -> ad sırası) çapa
        p = secici.olcum_puani(o, M, "high", True, S_AYAR)
        self.assertTrue(57.0 <= p <= 62.6)

    def test_capraz_model_efor_sirasi_degisebilir(self):
        """Üst eforda önde olan model, düşük eforda geride kalabilir (kullanıcının sorduğu durum)."""
        a = {"varyantlar": {"high": {"z": 42}, "max": {"z": 55}}}      # efora çok duyarlı
        b = {"varyantlar": {"high": {"z": 55}, "max": {"z": 57}}}      # efora az duyarlı
        oa = {"olcut": "vals:x", "puan": 64.1, "efor": "max"}
        ob = {"olcut": "vals:x", "puan": 60.6, "efor": "max"}
        self.assertGreater(secici.olcum_puani(oa, a, "max", True, S_AYAR), secici.olcum_puani(ob, b, "max", True, S_AYAR))
        self.assertLess(secici.olcum_puani(oa, a, "high", True, S_AYAR), secici.olcum_puani(ob, b, "high", True, S_AYAR))


class GuncelleYazici(unittest.TestCase):
    def test_kip_adlari_sema_sozlugune(self):
        self.assertEqual(guncelle._kip_norm(["text", "image", "audio", "audio", "bilinmeyen"]), ["metin", "gorsel", "ses"])
        ms = kesif.codex_modelleri({"models": [{"slug": "x-1", "input_modalities": ["text", "image", "audio"]}]})
        self.assertEqual(ms[0]["kipler"], ["metin", "gorsel", "ses"])

    def test_gecmis_olayi_kapali_sozlukte(self):
        m = {}
        guncelle._gecmis(m, "2026-11-17", "serbest metinli olay", halef="y")
        guncelle._gecmis(m, "2026-11-17", "halef")
        self.assertEqual(m["gecmis"][0]["olay"], "durum")
        self.assertEqual(m["gecmis"][0]["not"], "serbest metinli olay")
        self.assertEqual(m["gecmis"][1]["olay"], "halef")

    def test_yasak_hattin_yeni_surumu_semaya_uygun(self):
        mod = {"roller": {"astra": {"saglayici": "openai", "hat": "astra", "aktif": "gpt-6-astra"}}, "modeller": {}}
        guncelle.yeni_kayit_ekle(mod, "gpt-6.2-astra", "yasak", datetime(2026, 11, 17, tzinfo=timezone.utc),
                                 {"kipler": ["metin", "audio"], "eforlar": ["low", "max"]}, "yasak hat")
        k = mod["modeller"]["gpt-6.2-astra"]
        self.assertEqual(k["durum"], "gozlem")
        self.assertEqual(k["soy"]["tur"], "olasi_halef")
        self.assertEqual(k["soy"]["yuva"], "astra")
        self.assertEqual(k["kipler"]["girdi"], ["metin", "ses"])
        self.assertTrue(k["kanit"])
        self.assertNotIn("yasak", k)

    def test_olcum_alt_test_efor_ve_pareto_yazar(self):
        K = "https://ornek.test/a"
        mod = {"roller": {"r1": {"saglayici": "p", "hat": "h1", "aktif": "m1"},
                          "r2": {"saglayici": "p", "hat": "h2", "aktif": "m2"}},
               "modeller": {
                   "m1": {"saglayici": "p", "hat": "h1", "durum": "aktif", "varyantlar": {}, "alanlar": {}},
                   "m2": {"saglayici": "p", "hat": "h2", "durum": "aktif", "alanlar": {}, "varyantlar": {
                       "max": {"z": 51, "gorev_usd": 0.96, "z_kaynak": "aa", "kaynak": K, "okuma": "2026-11-15",
                               "pareto": "aktif"}}}}}
        sonuc = {"varyant": [{"kimlik": "m1", "efor": "medium", "z": 53, "gorev_usd": 0.41, "dk": 3.1,
                              "alt": {"tb4": 56.1, "KOTU ANAHTAR": 1, "fc2": "x"}, "kaynak": K, "okuma": "2026-11-17"}],
                 "alan": [{"kimlik": "m1", "alt_alan": "sre", "olcut": "vals:srebench", "puan": 50.0, "efor": "max",
                           "eforlar": {"max": 50.0, "medium": 47.0, "yok": 1}, "gorev_usd": 2.4,
                           "kaynak": K, "okuma": "2026-11-17"}]}
        satir, red = guncelle.olcum_uygula(mod, copy.deepcopy(sonuc), datetime(2026, 11, 17, tzinfo=timezone.utc))
        self.assertEqual(red, [])
        v = mod["modeller"]["m1"]["varyantlar"]["medium"]
        self.assertEqual(v["alt"], {"tb4": 56.1})
        self.assertEqual(v["pareto"], "aktif")
        a = mod["modeller"]["m1"]["alanlar"]["sre"]
        self.assertEqual(a["eforlar"], {"max": 50.0, "medium": 47.0})
        self.assertEqual(a["gorev_usd"], 2.4)
        # m2@max (Z 51, 0.96 USD), m1@medium (Z 53, 0.41 USD) tarafından baskın
        self.assertEqual(mod["modeller"]["m2"]["varyantlar"]["max"]["pareto"], "baskin")
        self.assertIn("m1@medium", mod["modeller"]["m2"]["varyantlar"]["max"]["pareto_not"])

    def test_pareto_yasak_hatti_kumeye_almaz(self):
        K = "https://ornek.test/a"
        v = {"z_kaynak": "aa", "kaynak": K, "okuma": "2026-11-15"}
        mod = {"roller": {"r1": {"aktif": "m1"}, "r2": {"aktif": "m2"}},
               "modeller": {"m1": {"saglayici": "p", "hat": "ucuz", "durum": "aktif",
                                   "varyantlar": {"high": dict(v, z=60, gorev_usd=0.1)}},
                            "m2": {"saglayici": "p", "hat": "yasakli", "durum": "aktif",
                                   "varyantlar": {"high": dict(v, z=50, gorev_usd=5.0)}}}}
        guncelle.pareto_isaretle(mod, {"p"}, ("p/ucuz",))
        self.assertEqual(mod["modeller"]["m2"]["varyantlar"]["high"]["pareto"], "aktif")


@unittest.skipUnless(O.GERCEK_VAR, O.GERCEK_NEDEN)
class YetenekSuzgeci(unittest.TestCase):
    def test_web_isinde_web_araci_olmayan_yol_elenir(self):
        v = O.gercek_veri()
        self.assertIn("web_arama", (v.siniflar["alan_olcutleri"]["web"].get("gerekli_yetenek") or []))
        yok = [pid for pid, p in v.platformlar.items() if (p.get("yetenekler") or {}).get("web_arama") is False]
        if not yok:
            self.skipTest("web_arama=false işaretli platform yok")
        i = secici.istek_hazirla({"sinif": "arastirma", "alan": "arastirma", "alt_alan": "web", "veri": "genel"}, v)
        adaylar, elenen = secici.adaylari_uret(i, v, {}, O.SIMDI)
        self.assertFalse([a for a in adaylar if a["platform"] in yok])
        self.assertTrue([n for n in elenen.values() if "yetenek yok" in n])


@unittest.skipUnless(O.GERCEK_VAR, O.GERCEK_NEDEN)
class OnceSor(unittest.TestCase):
    """`once_sor` hattı: yasak değil, otomatik seçilmez; açık önde ve sığıyorsa SOR T7; --zorla ile seçilir."""

    def setUp(self):
        self.v = O.gercek_veri()
        self.hat = ((self.v.kurallar.get("once_sor") or {}).get("saglayici_hat") or [None])[0]
        if not self.hat:
            self.skipTest("kişisel kuralda önce-sor hattı yok")
        sag, hat = self.hat.split("/")
        self.rol = next(r for r, x in self.v.roller.items() if x.get("saglayici") == sag and x.get("hat") == hat)
        self.kota = {}                                   # kota okunmadı: havuzlar belirsiz ama kullanılabilir

    def _sec(self, **ek):
        ist = dict({"sinif": "zor", "alan": "arastirma", "alt_alan": "sentez", "veri": "genel",
                    "sef": "fable:max"}, **ek)
        return secici.sec(ist, self.v, self.kota, {}, O.SIMDI)

    def test_otomatik_adaylarda_yok(self):
        i = secici.istek_hazirla({"sinif": "zor", "alan": "arastirma", "alt_alan": "sentez", "veri": "genel"}, self.v)
        adaylar, elenen = secici.adaylari_uret(i, self.v, {}, O.SIMDI)
        self.assertFalse([a for a in adaylar if a["rol"] == self.rol])
        self.assertTrue(any("önce sor" in n for n in elenen.values()))

    def test_secim_ya_otomatik_ya_t7_ama_asla_sessiz_degil(self):
        r = self._sec()
        if r["durum"] == "sor" and r.get("tetik") == "T7":
            kodlar = [x["kod"] for x in r["secenekler"]]
            self.assertEqual(kodlar, [secici.ONCE_SOR_KABUL, secici.ONCE_SOR_RET])
            self.assertEqual(r["varsayilan"], secici.ONCE_SOR_RET)
            self.assertIn(f"--zorla {self.rol}:", r["secenekler"][0]["yanit"])
        elif r.get("secim"):
            self.assertNotEqual(r["secim"]["rol"], self.rol)

    def test_ret_yaniti_normal_secime_doner(self):
        r = self._sec(sor_yanit=secici.ONCE_SOR_RET)
        self.assertNotEqual(r.get("tetik"), "T7")
        if r.get("secim"):
            self.assertNotEqual(r["secim"]["rol"], self.rol)

    def test_basit_iste_sorulmaz(self):
        r = self._sec(sinif="normal")
        self.assertNotEqual(r.get("tetik"), "T7")


if __name__ == "__main__":
    unittest.main()
