"""v7.1 seçici senaryoları (tasarım 12.2: T01-T34). Saf fonksiyon; ağ ve model yok. Varsayılan: agy otomatik açık,
yalın profil doğrulanmış, Q0 kota (claude/codex 0.9/0.9 3.5 g, agy_gemini 5s 1.0 hafta 0.9 3 g, agy_claude_gpt 1.0)."""
import unittest
from datetime import timedelta

import _ortak as O
from ork import secici

S = O.SIMDI
KOD = {"alan": "kod", "alt_alan": "gunluk", "sinif": "kod"}
RAPOR = {"alan": "yazim", "alt_alan": "rapor", "sinif": "normal"}
ZOR = {"alan": "kod", "alt_alan": "zor_ajan", "sinif": "zor", "sinyaller": ["geri_alinamaz", "cok_dosya", "test_yok"]}


def sec(istek, kota=None, durum=None, veri=None, simdi=S):
    return secici.sec(dict(istek), veri or O.veri71(), kota if kota is not None else O.kota71(), durum or {}, simdi)


def etiket(r):
    a = r.get("secim") or {}
    return f"{a.get('rol')}@{a.get('efor')} ({a.get('havuz')})" if a else None


def agy(**ao):
    def d(x):
        x["kullanici-kurallari"]["agy_otomatik"].update(ao)
    return d


class Tercih(unittest.TestCase):
    def test_T01_basit_genel_bedava(self):
        r = sec({"sinif": "basit", "veri": "genel"})
        self.assertEqual(etiket(r), "deepseek_flash@high (bedava)")
        self.assertEqual(r["secim"]["katman"], 0)
        self.assertIn("doygunluk", r["gerekce"])

    def test_T02_basit_bilinmiyor_codex_onde(self):
        r = sec({"sinif": "basit"})
        self.assertEqual(etiket(r), "terra@low (codex_plus)")
        self.assertEqual(r["secim"]["katman"], 1)
        self.assertAlmostEqual(r["secim"]["rho"], 1.733, places=2)
        self.assertAlmostEqual(r["faz"]["rho_C"], 1.619, places=2)

    def test_T03_kod_hydrogen_esitse_hydrogen(self):
        r = sec(dict(KOD, veri="genel"))
        self.assertEqual(etiket(r), "hydrogen@high (agy_gemini)")
        self.assertEqual(r["secim"]["katman"], 1)
        self.assertEqual(r["secim"]["yol"], "agy-oto")
        self.assertEqual(r["cagri"]["model"], "gemini-4-hydrogen")
        aileler = {x.split("@")[0] for x in r["E"]}
        self.assertTrue({"opus", "sonnet", "sol", "hydrogen"} <= aileler)
        self.assertAlmostEqual(r["secim"]["pay"], (1.87 + 0.039) / 4, places=3)

    def test_T04_bilinmiyor_veride_codex(self):
        self.assertEqual(etiket(sec(KOD)), "sol@medium (codex_plus)")

    def test_T05_agy_kapali_codex_elle_oneri_yok(self):
        r = sec(dict(KOD, veri="genel"), veri=O.veri71(agy(acik=False)))
        self.assertEqual(etiket(r), "sol@medium (codex_plus)")
        self.assertIsNone(r.get("elle_oneri"))

    def test_T06_rapor_claude_ustun(self):
        r = sec(dict(RAPOR, veri="genel"))
        self.assertEqual(etiket(r), "sonnet@xhigh (claude_max)")
        self.assertEqual(r["ust"], "anthropic")
        self.assertTrue(r["secim"]["rezerv_acik"])

    def test_T07_terminal_birlesik_kanit_aile_ici_agy_once(self):
        r = sec({"alan": "kod", "alt_alan": "terminal", "sinif": "kod", "veri": "genel"})
        self.assertEqual(etiket(r), "opus@high (agy_claude_gpt)")
        self.assertEqual(r["ust"], "anthropic")
        self.assertTrue(any("birleşik z=1.34" in v for v in r["elenen"].values()))

    def test_T08_sre_sol_ustun(self):
        r = sec({"alan": "kod", "alt_alan": "sre", "sinif": "kod", "veri": "genel"}, O.kota71(codex=(0.9, 0.45)))
        self.assertEqual(etiket(r), "sol@medium (codex_plus)")
        self.assertEqual(r["ust"], "openai")

    def test_T09_kritik_opus_xhigh(self):
        r = sec({"sinif": "kritik", "veri": "genel"})
        self.assertEqual(etiket(r), "opus@xhigh (claude_max)")
        self.assertTrue(r["secim"]["rezerv_acik"])


class OpusKapisi(unittest.TestCase):
    def test_T10_ciddi_zor_agy_opus(self):
        r = sec(dict(ZOR, veri="genel"))
        self.assertTrue(r["opus_kapisi"])
        self.assertEqual(etiket(r), "opus@high (agy_claude_gpt)")
        el = r["elenen"]
        self.assertIn("opus kapısı", el.get("sol@high|codex", ""))
        self.assertIn("köprü", el.get("hydrogen@high|agy", ""))

    def test_T11_agy_opus_sigmazsa_claude(self):
        r = sec(dict(ZOR, veri="genel"), O.kota71(agy_claude_gpt=(1.0, 0.5)))
        self.assertEqual(etiket(r), "opus@high (claude_max)")
        self.assertEqual(r["secim"]["katman"], 3)

    def _hyd(self, puan):
        def d(x):
            x["modeller"]["modeller"]["gemini-4-hydrogen"]["alanlar"]["zor_ajan"] = {
                "puan": puan, "olcut": "aa:coding_agent", "efor": None, "kaynak": "https://ornek.invalid/x",
                "okuma": "2026-11-15", "guven": "B"}
        return d

    def test_T12_olculu_esdeger_kapidan_gecer(self):
        r = sec(dict(ZOR, veri="genel"), veri=O.veri71(self._hyd(58.5)))
        self.assertEqual(etiket(r), "hydrogen@high (agy_gemini)")
        self.assertIsNone(r["ust"])

    def test_T12b_birlesik_z_sinir(self):
        r = sec(dict(ZOR, veri="genel"), veri=O.veri71(self._hyd(57.0)))
        self.assertEqual(r["ust"], "anthropic")
        self.assertTrue(any("birleşik z=1.01" in v for v in r["elenen"].values()))
        self.assertEqual(etiket(r), "opus@high (agy_claude_gpt)")

    def test_T29_kopru_kapida_sayilmaz(self):
        r = sec(dict(ZOR, veri="genel"))
        self.assertIn("opus kapısı: ölçülü eşdeğer değil", r["elenen"]["hydrogen@high|agy"])

    def test_kopru_kapisiz_zorda_e_ye_girer_ve_kanit_daraltir(self):
        r = sec({"alan": "kod", "alt_alan": "zor_ajan", "sinif": "zor", "veri": "genel"})
        self.assertFalse(r["opus_kapisi"])
        self.assertEqual(r["ust"], "anthropic")            # köprü üstünlüğü gizlemez (birleşik z)
        v = O.veri71()
        i = secici.istek_hazirla({"alan": "kod", "alt_alan": "zor_ajan", "sinif": "zor", "veri": "genel"}, v)
        a, _ = secici.adaylari_uret(i, v, {}, S)
        secici.kalite_hesapla(a, "zor_ajan", v)
        h = next(x for x in a if x["rol"] == "hydrogen" and x["efor"] == "high")
        self.assertEqual(h["q_kaynak"], "kopru:aa:fc2")
        self.assertTrue(54.5 < h["q"] < 56.0, h["q"])           # medyan(ref) - 0.5δ; tasarım örneği 55.5


class TabanVeSor(unittest.TestCase):
    def test_T13_rapor_lider_payi_sor(self):
        r = sec(dict(RAPOR, veri="genel"), O.kota71(claude=(0.22, 0.9)))
        self.assertEqual(r["durum"], "sor")
        self.assertEqual(r["tetik"], "T1")
        kodlar = [x["kod"] for x in r["secenekler"]]
        self.assertEqual(kodlar, ["bekle", "lider_tamponu", "taban_istisna", "dis_alt", "kismi"])
        lt = r["secenekler"][1]
        self.assertAlmostEqual(lt["sonra_kalan"], 0.156, places=3)
        da = r["secenekler"][3]
        self.assertIn("opus@high (agy-oto)", da["aday"])
        self.assertAlmostEqual(da["q_fark"], -60, places=0)
        self.assertEqual(secici.CIKIS_KODU[r["durum"]], 4)

    def test_T14_kisa_bekleme_bekle(self):
        r = sec(dict(RAPOR, veri="genel"), O.kota71(claude=(0.22, 0.9), t5={"claude_max": 30}))
        self.assertEqual(r["durum"], "bekle")
        self.assertEqual(secici.CIKIS_KODU[r["durum"]], 5)

    def _t15(self):
        return O.kota71(claude=(0.9, 0.44), codex=(0.9, 0.21), agy_gemini=(0.2, 0.2), agy_claude_gpt=(0.1, 0.1),
                        agy_argon=0.1)

    def test_T15_tek_sigan_claude_rezerv_sor(self):
        r = sec(dict(KOD, veri="genel"), self._t15())
        self.assertEqual(r["durum"], "sor")
        self.assertEqual(r["tetik"], "T2")
        self.assertIn("claude_rezerv", [x["kod"] for x in r["secenekler"]])

    def test_T15b_sor_yaniti_rezervi_acar(self):
        d = {"sor_kararlari": [{"kod": "claude_rezerv", "kapsam": "oturum",
                                "bitis": (S + timedelta(hours=5)).isoformat()}]}
        r = sec(dict(KOD, veri="genel"), self._t15(), durum=d)
        self.assertEqual(r["durum"], "secildi")
        self.assertEqual(r["secim"]["havuz"], "claude_max")

    def test_T16_ust_rezerv_acik(self):
        r = sec(dict(RAPOR, veri="genel"), self._t15())
        self.assertEqual(etiket(r), "sonnet@xhigh (claude_max)")
        self.assertTrue(r["secim"]["rezerv_acik"])

    def test_T33_tetik_yok_bekle(self):
        r = sec({"sinif": "normal"}, O.kota71(claude=(0.9, 0.30), codex=(0.9, 0.20)), veri=O.veri71(agy(acik=False)))
        self.assertEqual(r["durum"], "bekle")
        self.assertEqual(r["istek"]["Q"], 41)
        self.assertIn("Q düşürülmez", r["gerekce"])


class Tempo(unittest.TestCase):
    def test_T17_codex_geride_yine_claudedan_once(self):
        # v7.2 (R3, denetim kod#10): Codex %35 > taban %20; GERİDE olsa da eşit kalitede Claude'dan önce
        k = O.kota71(claude=(0.9, 0.80), codex=(0.9, 0.35), oran={"claude_max": 5 / 7, "codex_plus": 5 / 7})
        r = sec(KOD, k)
        self.assertEqual(etiket(r), "sol@medium (codex_plus)")
        self.assertEqual(r["secim"]["katman"], 2)

    def test_T18_claude_5s_sikisinca_codex(self):
        k = O.kota71(claude=(0.30, 0.80), codex=(0.9, 0.35), oran={"claude_max": 5 / 7, "codex_plus": 5 / 7},
                     t5={"claude_max": 180})
        r = sec(KOD, k)
        self.assertEqual(etiket(r), "sol@medium (codex_plus)")
        self.assertAlmostEqual(r["faz"]["rho_C"], 0.111, places=2)

    def test_T19_kullan_ya_da_kaybet(self):
        r = sec(KOD, O.kota71(codex=(0.9, 0.5), oran={"codex_plus": 5 / 168}))
        self.assertEqual(etiket(r), "sol@medium (codex_plus)")
        self.assertGreater(r["secim"]["rho"], 7.0)

    def test_T20_claude_fazlasi_sifirlanacak(self):
        r = sec(KOD, O.kota71(claude=(1.0, 0.70), oran={"claude_max": 12 / 168}))
        self.assertEqual(etiket(r), "opus@medium (claude_max)")
        self.assertAlmostEqual(r["faz"]["rho_C"], 7.14, places=1)

    def test_T21_video_hydrogen_rezerv_acik(self):
        r = sec({"alan": "video_analiz", "alt_alan": "konusmali", "sinif": "normal", "veri": "genel"})
        self.assertEqual(etiket(r), "hydrogen@high (agy_gemini)")
        self.assertTrue(r["secim"]["rezerv_acik"])

    def test_T34_determinizm_ve_onde_histerezisi(self):
        a = sec(dict(KOD, veri="genel"))
        b = sec(dict(KOD, veri="genel"))
        self.assertEqual(a["gerekce"], b["gerekce"])
        self.assertTrue(a["durum_guncel"]["onde"]["agy_gemini"])
        k = O.kota71(codex=(0.9, 0.62))               # 1.5·0.96 = 1.44: (1-b)·1.62 = 1.46 altı -> çıkar
        self.assertFalse(sec(KOD, k, durum={"onde": {"codex_plus": True}})["durum_guncel"]["onde"]["codex_plus"])
        k2 = O.kota71(codex=(0.9, 0.65))              # 1.5·1.07 = 1.6 ≥ 1.46 (içerideyse kalır), < 1.78 (girmez)
        self.assertTrue(sec(KOD, k2, durum={"onde": {"codex_plus": True}})["durum_guncel"]["onde"]["codex_plus"])
        self.assertFalse(sec(KOD, k2, durum={"onde": {"codex_plus": False}})["durum_guncel"]["onde"]["codex_plus"])


class GorselVeGizlilik(unittest.TestCase):
    def _ek(self):
        return {"reset_kredisi": {"adet": 1, "son": "2026-12-12"}, "ordinary": True}

    def test_T22a_kredi_48_sa_alti_elle(self):
        k = O.kota71(codex=(0.9, 0.2), oran={"codex_plus": 18 / 168}, codex_ek=self._ek())
        r = sec({"alan": "gorsel_uretim", "alt_alan": "t2i", "sinif": "normal"}, k)
        self.assertEqual(r["durum"], "elle")

    def test_T22b_kredi_sor(self):
        k = O.kota71(codex=(0.9, 0.2), oran={"codex_plus": 5 / 7}, codex_ek=self._ek())
        r = sec({"alan": "gorsel_uretim", "alt_alan": "t2i", "sinif": "normal"}, k)
        self.assertEqual(r["durum"], "sor")
        self.assertEqual(r["tetik"], "T3")
        self.assertEqual(r["secenekler"][0]["kod"], "sifirlama_kredisi")

    def test_T23_kisisel_kamu_ve_dis_yok(self):
        r = sec(dict(KOD, veri="kisisel"))
        self.assertEqual(etiket(r), "sol@medium (codex_plus)")

    def test_T24_yalin_profil_dogrulanmadi(self):
        r = sec(dict(KOD, veri="genel"), veri=O.veri71(agy(isci_profili={"dogrulandi": False,
                                                                           "kisisel_baglam_kabul": None})))
        self.assertEqual(etiket(r), "sol@medium (codex_plus)")
        self.assertTrue(any("kişisel bağlam" in v for k, v in r["elenen"].items() if k.startswith("agy-oto")))

    def test_T25_403_sonrasi_kapali(self):
        r = sec(dict(KOD, veri="genel"), durum={"agy_otomatik_kapali": {"neden": "403", "zaman": S.isoformat()}})
        self.assertEqual(etiket(r), "sol@medium (codex_plus)")

    def test_T26_hafif(self):
        r = sec({"sinif": "basit", "veri": "genel", "kip": "hafif"})
        self.assertEqual(etiket(r), "deepseek_flash@high (bedava)")

    def test_tekil_secim_false_suru_disi(self):
        r = sec({"sinif": "mekanik", "veri": "genel"})
        self.assertIn("tekil_secim", r["elenen"].get("glm|bedava", ""))


class KaskadVeGeriBildirim(unittest.TestCase):
    def test_T27_kanitli_kaskad(self):
        r = sec({"sinif": "normal", "veri": "genel", "dis_kanit": "kapali_cevap"})
        self.assertEqual(r["durum"], "secildi")
        self.assertEqual(r["kaskad"]["basla"], "deepseek_flash@high")
        self.assertIn("dış kanıt", r["kaskad"]["kabul"])
        self.assertEqual(r["kaskad"]["yukselt"], f"{r['secim']['rol']}@{r['secim']['efor']}")

    def test_T28_zor_kaskad_yok(self):
        r = sec({"sinif": "zor", "veri": "genel", "dis_kanit": "kapali_cevap"})
        self.assertNotIn("kabul", r["kaskad"] or {})

    def test_T30_kucuk_farklar_birikmez(self):
        v = O.veri71()

        def a(aile, id_, tb4, vt):
            return {"id": id_, "kimlik": id_, "aile": aile, "efor": "high", "z": 50, "z_etkin": 50, "q": tb4}

        def d(x):
            mm = x["modeller"]["modeller"]
            mm["claude-opus-5-5"]["varyantlar"]["high"]["alt"]["tb4"] = 51.2          # +0.4δ (δ 3)
            mm["claude-opus-5-5"]["alanlar"]["terminal"]["puan"] = 56.7               # +0.4δ (δ 4)
            mm["gpt-6.1-sol"]["varyantlar"]["high"]["alt"]["tb4"] = 50.0
            mm["gpt-6.1-sol"]["alanlar"]["terminal"]["puan"] = 55.1
        v = O.veri71(d)
        E = [dict(a("anthropic", "claude-opus-5-5", 0, 0)), dict(a("openai", "gpt-6.1-sol", 0, 0))]
        self.assertIsNone(secici.kanit_birikimi(E, "terminal", v))

    def test_T31_geri_bildirim_eler(self):
        d = {"basari": {"deepseek-v4.1-flash": {"basit": {"n": 20, "ok": 10}},
                        "claude-haiku-5-5": {"basit": {"n": 20, "ok": 19}}}}
        r = sec({"sinif": "basit", "veri": "genel"}, durum=d)
        self.assertNotEqual((r["secim"] or {}).get("kimlik"), "deepseek-v4.1-flash")
        self.assertTrue(any("geri bildirim" in v for k, v in r["elenen"].items() if k.startswith("deepseek")))


class Plan(unittest.TestCase):
    def test_T32_plan_rezervasyon(self):
        parcalar = [dict(KOD, id=f"p{n}", veri="genel") for n in range(1, 4)]
        r = secici.plan_sec({"is_id": "t32", "parcalar": parcalar}, O.veri71(), O.kota71(), {}, S)
        sec_ = [f"{p['secim']['rol']}@{p['secim']['efor']} ({p['secim']['havuz']})" for p in r["parcalar"]]
        self.assertEqual(sec_, ["hydrogen@high (agy_gemini)", "opus@medium (agy_claude_gpt)",
                                "sol@medium (codex_plus)"])
        self.assertEqual(len(r["suru_plani"]["isler"]), 3)
        self.assertEqual(r["claude_isleri"], [])
        self.assertGreater(r["tasarruf"]["claude_alternatif_usd_e"], 0)
        self.assertIn("0 claude", r["ozet"])

    def test_plan_claude_parcasi_agent_satiri(self):
        parcalar = [dict(RAPOR, id="r1", veri="genel"), dict(KOD, id="k1", veri="genel")]
        r = secici.plan_sec({"is_id": "x", "parcalar": parcalar}, O.veri71(), O.kota71(), {}, S)
        self.assertEqual(len(r["claude_isleri"]), 1)
        self.assertIn("Agent(", r["claude_isleri"][0]["cagri"])
        self.assertEqual([x["id"] for x in r["suru_plani"]["isler"]], ["k1"])

    def test_plan_sor_birlesir(self):
        parcalar = [dict(RAPOR, id="r1", veri="genel"), dict(RAPOR, id="r2", veri="genel")]
        r = secici.plan_sec({"is_id": "x", "parcalar": parcalar}, O.veri71(), O.kota71(claude=(0.22, 0.9)), {}, S)
        self.assertEqual(r["durum"], "sor")
        self.assertEqual(len(r["sor"]["parcalar"]), 2)


if __name__ == "__main__":
    unittest.main()
