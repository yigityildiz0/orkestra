"""v7.2 denetim düzeltmeleri (niyet, kod, güvenlik eleştirmenleri): her bulgu için gerileme testi. Ağ ve model yok."""
import json
import os
import tempfile
import types
import unittest
from datetime import timedelta
from pathlib import Path

import _ortak as O
from ork import araclar, guncelle, kota, secici, suru
from ork.veri import durum_dizini

S = O.SIMDI
KOD = {"alan": "kod", "alt_alan": "gunluk", "sinif": "kod", "veri": "genel"}


def _kapi_kapali(d):
    d["kullanici-kurallari"]["agy_otomatik"]["isci_profili"] = {"dogrulandi": False, "kisisel_baglam_kabul": None}


def _sv(ek=None):
    """Koşucu verisi: agy argv_oto şablonu + isteğe bağlı değişiklik."""
    def d(x):
        x["platformlar"]["platformlar"]["agy"]["cagri"]["argv_oto"] = ["{ikili}", "-p", "{istem}", "--model", "{taban}",
                                                                   "--effort", "{efor}", "--mode", "{kip}"]
        if ek:
            ek(x)
    return O.veri71(d)


def sec(istek, k=None, veri=None, durum=None):
    return secici.sec(dict(istek), veri or O.veri71(), k or O.kota71(), durum or {}, S)


class Kota(unittest.TestCase):
    def test_kod2_claude_yuzde_birimi(self):
        self.assertEqual(kota.claude_coz("5s=1,hafta=50")["5s"]["kalan"], 0.01)
        self.assertEqual(kota.claude_coz("5s=0.5,hafta=50")["5s"]["kalan"], 0.005)
        self.assertEqual(kota.claude_coz("5s=100,hafta=100")["hafta"]["kalan"], 1.0)
        self.assertEqual(kota.claude_coz({"5s": 1})["5s"]["kalan"], 0.01)
        self.assertEqual(kota.claude_coz({"5s_kalan_oran": 0.5})["5s"]["kalan"], 0.5)

    def test_kod13_kuru_hicbir_dosya_yazmaz(self):
        for y in (kota.claude_yolu(), kota.anlik_yolu(), kota.gecmis_yolu(), kota.durum_yolu()):
            try:
                y.unlink()
            except OSError:
                pass
        ad = {"codex": lambda: None, "agy": lambda: {}, "bedava": lambda hid, api, simdi: (None, "x")}
        kota.oku(O.veri71(), claude="5s=90,hafta=90", adaptor=ad, yaz=False)
        with kota.yazmadan():
            kota.soguma_kaydet("codex_plus", "kota")
        for y in (kota.claude_yolu(), kota.anlik_yolu(), kota.gecmis_yolu(), kota.durum_yolu()):
            self.assertFalse(y.exists(), y.name)

    def test_kod13_bayat_5s_bilinmiyor(self):
        kota.durum_yolu().parent.mkdir(parents=True, exist_ok=True)
        eski = (S - timedelta(minutes=20)).isoformat()
        kota.claude_yolu().write_text(json.dumps({"zaman": eski, "pencereler": {
            "5s": {"kalan": 0.9}, "hafta": {"kalan": 0.8}}}), encoding="utf-8")
        an = {"havuzlar": {}}
        kota._claude_ekle(an, O.veri71(), None, S)
        pen = an["havuzlar"]["claude_max"]["pencereler"]
        self.assertNotIn("5s", pen)                      # 15 dk'dan eski 5s değeri kullanılmaz
        self.assertEqual(pen["hafta"]["kaynak"], "get_usage_bayat")

    def test_kod24_gecmis_tahmin_yazmaz_ve_budar(self):
        y = Path(tempfile.mkdtemp()) / "g.jsonl"
        y.write_text(json.dumps({"zaman": (S - timedelta(days=20)).isoformat(), "havuz": "x", "pencere": "hafta",
                                 "kalan": 0.5}) + "\n", encoding="utf-8")
        an = {"havuzlar": {"bedava": {"durum": "ok", "pencereler": {"gun": {"kalan": 1.0, "kaynak": "tahmin"}}},
                           "codex_plus": {"durum": "ok", "pencereler": {"hafta": {"kalan": 0.4, "kaynak": "app-server"}}}}}
        yeni = kota.gecmis_ekle(an, S, y)
        self.assertEqual([k["havuz"] for k in yeni], ["codex_plus"])
        self.assertEqual([k["havuz"] for k in kota.gecmis_oku(y)], ["codex_plus"])   # 20 günlük satır budandı

    def test_kod5_agy_okuma_kapali_kapida_oturumda_bir(self):
        v = O.veri71(_kapi_kapali)
        ok, _ = kota.agy_okuma_izni(v, S, {})
        self.assertTrue(ok)
        ok2, neden = kota.agy_okuma_izni(v, S, {"agy_okuma_son": (S - timedelta(hours=1)).isoformat()})
        self.assertFalse(ok2)
        self.assertIn("oturumda", neden)
        ok3, _ = kota.agy_okuma_izni(v, S, {"agy_otomatik_kapali": {"neden": "403"}})
        self.assertFalse(ok3)

    def test_kod9_codex_okuma_zaman_asimi(self):
        class Asili:
            def __init__(self, *a, **k):
                import threading
                self._olay = threading.Event()
                self.stdin = types.SimpleNamespace(write=lambda x: None, flush=lambda: None)
                self.stdout = types.SimpleNamespace(readline=lambda: (self._olay.wait(5), "")[1])

            def kill(self):
                self._olay.set()
        import time
        t = time.monotonic()
        self.assertIsNone(kota.codex_limits(exe="x", _popen=Asili, zaman_asimi=0.3))
        self.assertLess(time.monotonic() - t, 3)


class Secici(unittest.TestCase):
    def test_kod1_ema_tabani_delmez(self):
        v = O.veri71()
        d = {"kota_ema": {"claude_max": {"5s": {"k": 0.60, "zaman": S.timestamp() - 600}}}}
        pens = secici.pencereler("claude_max", v.havuz("claude_max"), v, O.kota71(claude=(0.14, 0.9)), d, S, {})
        self.assertAlmostEqual(pens["5s"]["k_ham"], 0.14)          # sığma: okunan ile EMA'nın küçüğü
        r = sec({"sinif": "normal", "veri": "genel", "zorla": "opus:high"}, O.kota71(claude=(0.14, 0.9)), v, d)
        self.assertNotEqual((r.get("secim") or {}).get("havuz"), "claude_max")

    def test_kod3_bilinmeyen_claude_kritikte_T0(self):
        k = O.kota71()
        k["havuzlar"]["claude_max"] = {"durum": "bilinmiyor", "pencereler": {}}
        r = sec({"sinif": "kritik", "alan": "kod", "alt_alan": "gunluk", "veri": "genel"}, k)
        self.assertEqual(r["durum"], "sor")
        self.assertEqual(r["tetik"], "T0")
        self.assertEqual(secici.CIKIS_KODU["sor"], 4)
        r2 = sec({"sinif": "kritik", "alan": "kod", "alt_alan": "gunluk", "veri": "genel",
                  "sor_yanit": "kota_bilinmiyor_devam"}, k)
        self.assertEqual(r2["secim"]["katman"], 4)                 # yalnız katman 4 (rezerv açık olsa da)

    def test_kod4_rota_hedefi_claude_rezervini_sorgusuz_acmaz(self):
        d = tempfile.mkdtemp()
        Path(d, ".orkestra.json").write_text(json.dumps({"zorunlu": {"*": "opus:medium"}}), encoding="utf-8")
        k = O.kota71(claude=(0.9, 0.44), agy_claude_gpt=(1.0, 0.0))
        r = sec({"sinif": "normal", "veri": "genel", "dizin": d}, k)
        self.assertEqual(r["durum"], "sor")
        self.assertEqual(r["tetik"], "T2")
        r2 = sec({"sinif": "normal", "veri": "genel", "zorla": "opus:medium"}, k)     # kullanıcının açık isteği
        self.assertEqual(r2["durum"], "secildi")

    def test_kod12_onay_gerekli_cikis_4_ve_plana_girmez(self):
        self.assertEqual(secici.CIKIS_KODU["onay_gerekli"], 4)
        p = secici.plan_sec({"is_id": "t", "parcalar": [{"id": "a", "sinif": "kritik", "veri": "genel",
                                                          "zorla": "haiku:low"}]}, O.veri71(), O.kota71(), {}, S)
        self.assertEqual(p["parcalar"][0]["durum"], "onay_gerekli")
        self.assertEqual(p["suru_plani"]["isler"], [])
        self.assertEqual(p["claude_isleri"], [])
        self.assertEqual(p["sor"]["parcalar"][0]["id"], "a")

    def test_kod11_plan_ad_hatasi_sessizce_gecmez(self):
        import ork as _ork  # noqa: F401  (paket yolu)
        import importlib.util
        spec = importlib.util.spec_from_file_location("ork_cli", O.KOK / "scripts" / "ork.py")
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
        h = cli._ad_dogrula(types.SimpleNamespace(alan="kodd", alt_alan=None, sinif=None), O.veri71())
        self.assertTrue(h and "bilinmeyen alan" in h[0])
        p = secici.plan_sec({"parcalar": [{"id": "x", "alan": "kodd", "_hata": h}]}, O.veri71(), O.kota71(), {}, S)
        self.assertEqual(p["parcalar"][0]["durum"], "hata")
        self.assertEqual(p["suru_plani"]["isler"], [])

    def test_kod21_tok_tahmin_dogrulanir(self):
        for kotu in ("abc:1", "0:0", "-5:3", "1"):
            with self.assertRaises(secici.SecimHatasi):
                secici.tok_tahmin_coz(kotu)
        self.assertEqual(secici.tok_tahmin_coz("30000:8000"), (30000.0, 8000.0))

    def test_kod14_tasarruf_yalniz_gonderilen(self):
        p = secici.plan_sec({"parcalar": [dict(KOD, id="a"), {"id": "b", "sinif": "kritik", "veri": "genel",
                                                             "zorla": "haiku:low"}]}, O.veri71(), O.kota71(), {}, S)
        gonderilen = sum(x["c_claude_alternatif"] for x in p["parcalar"] if x["durum"] == "secildi")
        self.assertAlmostEqual(p["tasarruf"]["claude_alternatif_usd_e"], round(gonderilen, 3), places=3)

    def test_niyet2_saglik_rezervde_sor_T2(self):
        r = sec({"sinif": "normal", "alan": "yazim", "alt_alan": "rapor", "veri": "saglik"},
                O.kota71(claude=(0.8, 0.45)))
        self.assertEqual(r["durum"], "sor")
        self.assertEqual(r["tetik"], "T2")
        self.assertIn("veri sınıfı", r["soru"])

    def test_niyet2_saglik_bilinmeyen_claude_T0(self):
        k = O.kota71()
        k["havuzlar"]["claude_max"] = {"durum": "bilinmiyor", "pencereler": {}}
        r = sec({"sinif": "normal", "alan": "yazim", "alt_alan": "rapor", "veri": "saglik"}, k)
        self.assertEqual(r["durum"], "sor")
        self.assertEqual(r["tetik"], "T0")                 # sağlık verisi bilinmeyen kotayla sessizce Claude'a gitmez

    def test_kod14_tasarruf_tabani_tam_kotali(self):
        plan = {"parcalar": [dict(KOD, id="a"), dict(KOD, id="b")]}
        p1 = secici.plan_sec(plan, O.veri71(), O.kota71(), {}, S)
        p2 = secici.plan_sec(plan, O.veri71(), O.kota71(claude=(0.8, 0.45)), {}, S)
        a1, a2 = p1["tasarruf"]["claude_alternatif_usd_e"], p2["tasarruf"]["claude_alternatif_usd_e"]
        self.assertGreater(a1, 0)
        self.assertAlmostEqual(a1, a2, places=3)           # Claude son çeyrekteyken taban sıfıra inmez

    def test_niyet5_d2_iki_delta_siniri(self):
        for k in (O.kota71(claude=(0.14, 0.9), codex=(0.9, 0.22), agy_gemini=(0.05, 0.05)),
                  O.kota71(claude=(0.9, 0.31), codex=(0.9, 0.22))):
            for istek in ({"sinif": "normal", "alan": "yazim", "alt_alan": "uzun_turkce", "veri": "genel"},
                          dict(KOD), {"sinif": "normal", "veri": "genel"}):
                r = sec(istek, k)
                if r.get("dusus") == "D2":
                    self.assertGreaterEqual(r["secim"]["q"], r["q_tepe"] - 2 * r["delta"] - 1e-9, istek)
                for x in r.get("secenekler") or []:
                    if x["kod"] == "dis_alt":
                        self.assertIn("q_fark_delta", x)

    def test_niyet1_kapi_bekliyorken_claude_varsayilan_degil(self):
        v = O.veri71(_kapi_kapali)
        k = O.kota71(codex=(0.9, 0.2))                       # Codex tabanda: eşit kalitede Claude ya da agy kalır
        r = sec(KOD, k, v)
        if r.get("durum") == "sor":
            self.assertEqual(r["tetik"], "T4")
            kodlar = [x["kod"] for x in r["secenekler"]]
            self.assertEqual(kodlar[:2], [secici.AGY_KABUL, secici.AGY_RET])
            r2 = sec(KOD, k, v, {"sor_kararlari": [{"kod": secici.AGY_KABUL, "kapsam": "oturum",
                                                    "bitis": (S + timedelta(hours=5)).isoformat()}]})
            self.assertEqual(r2["secim"]["yol"], "agy-oto")              # oturum kabulü kapıyı açar
            r3 = sec(dict(KOD, sor_yanit=secici.AGY_RET), k, v)
            self.assertEqual(r3["secim"]["havuz"], "claude_max")
        else:
            self.assertNotEqual(r["secim"]["havuz"], "claude_max")

    def test_niyet12_fable_yasak_gerekcesi(self):
        for h in ("fable:high", "claude-fable-5-2"):
            r = sec({"sinif": "normal", "veri": "genel", "zorla": h})
            self.assertEqual(r["durum"], "hata")
            self.assertIn("yasak", r["gerekce"])

    def test_kod10_r3_dis_havuz_claudedan_once_kullan_kaybet_istisnasi(self):
        k = O.kota71(claude=(0.9, 0.80), codex=(0.9, 0.35), oran={"claude_max": 5 / 7, "codex_plus": 5 / 7})
        self.assertNotEqual(sec(KOD, k)["secim"]["havuz"], "claude_max")   # agy ya da Codex: Claude değil
        k2 = O.kota71(claude=(1.0, 0.70), oran={"claude_max": 12 / 168})
        r = sec(KOD, k2)
        self.assertEqual(r["secim"]["havuz"], "claude_max")      # Claude fazlası sıfırlamada yanacak
        self.assertGreaterEqual(r["faz"]["rho_C"], 1.5)

    def test_kod10_plan_sirasi(self):
        p = secici.hafta_plani(O.veri71(), O.kota71(claude=(0.9, 0.8), codex=(0.9, 0.35)), {}, S)
        s = p["sira"]
        self.assertLess(s.index("codex_plus"), s.index("claude_max"))

    def test_niyet10_plan_kapiyi_bilir(self):
        p = secici.hafta_plani(O.veri71(_kapi_kapali), O.kota71(), {}, S)
        dur = {x["havuz"]: x["durum"] for x in p["havuzlar"]}
        self.assertEqual(dur.get("agy_gemini"), "ELLE")
        self.assertNotIn("agy_gemini", p["sira"])

    def test_kod17_tek_varyant_delta(self):
        a = [{"kimlik": "m", "platform": "p", "q": 1500.0, "c_cap": 2.0, "efor": "high"},
             {"kimlik": "m", "platform": "p", "q": 1420.0, "c_cap": 1.0, "efor": "medium"}]
        self.assertEqual(secici._tek_varyant([dict(x) for x in a], 14)[0]["efor"], "high")   # 80 > δ: üst efor
        self.assertEqual(secici._tek_varyant([dict(x) for x in a], 100)[0]["efor"], "medium")

    def test_kod7_ayrik_kisisel_dizin(self):
        kis = Path(tempfile.mkdtemp())
        eski = os.environ.get("ORKESTRA_KISISEL")
        os.environ["ORKESTRA_KISISEL"] = str(kis)
        try:
            (kis / "platformlar.json").write_text("{}", encoding="utf-8")
            y = guncelle.yedekle(O.KOK / "data", S, yerel=True)
            self.assertTrue((Path(y) / "platformlar.json").exists())
            guncelle.veri_yaz(O.KOK / "data", O.veri71(), {"modeller": {}}, {"platformlar": {}}, True)
            self.assertTrue((kis / "modeller.yerel.json").exists())
            self.assertNotEqual(kis.resolve(), durum_dizini().resolve())
            self.assertFalse((durum_dizini() / "modeller.yerel.json").exists())
        finally:
            if eski is None:
                os.environ.pop("ORKESTRA_KISISEL", None)
            else:
                os.environ["ORKESTRA_KISISEL"] = eski

    def test_brief_tok_tahmini_kucuk_havuzu_sisirmez(self):
        i_ib = {"sinif": "kod", "alan": "kod", "alt_alan": "gunluk", "veri": "genel", "boyut": "orta"}
        b = Path(tempfile.mkdtemp()) / "brief.md"
        b.write_text("x" * 7000, encoding="utf-8")
        i = secici.istek_hazirla(dict(i_ib, brief=str(b)), O.veri71())
        self.assertEqual(i["tok_kaynak"], "brief")
        self.assertGreaterEqual(i["tok_tahmin"][0], 2000)


class Suru(unittest.TestCase):
    def setUp(self):
        for f in ("agy-cagri.jsonl", "durum.json", "agy.lock"):
            try:
                (durum_dizini() / f).unlink()
            except OSError:
                pass

    def _kos(self, isler, veri, surec=None):
        from test_suru import SahteSaat, SahteTasiyici
        tas = SahteTasiyici(surec=surec or (lambda a, s: (0, json.dumps({"status": "SUCCESS", "response": "ÖZET: ok"}),
                                                          "")))
        ks = suru.Kosucu({"is_id": "t", "isler": isler}, veri, tasiyici=tas, saat=SahteSaat(), olc_yaz=False,
                         durum_yaz=False)
        ks._ikili = lambda pid: "araci.exe"
        return ks, tas

    def _agy(self, id_, **ek):
        return dict({"id": id_, "brief": "Genel soru", "veri": "genel", "sinif": "basit", "alan": "genel",
                     "hedef": {"yol": "agy-oto", "platform": "agy", "havuz": "agy_gemini", "model": "gemini-4-hydrogen",
                               "kimlik": "gemini-4-hydrogen", "efor": "high"}}, **ek)

    def test_guv1_kapali_kapida_acik_hedef_calismaz(self):
        ks, tas = self._kos([self._agy("a")], _sv(_kapi_kapali))
        oz = ks.calistir()
        self.assertEqual(oz["isler"][0]["durum"], "engel")
        self.assertEqual(tas.surecler, [])

    def test_guv2_tavan_kosu_icinde_asilmaz(self):
        def d(x):
            x["kullanici-kurallari"]["agy_otomatik"]["guvenceler"].update(saatlik_cagri_tavani=3, eszamanli=2)
        ks, tas = self._kos([self._agy(f"a{n}") for n in range(6)], _sv(d))
        oz = ks.calistir()
        self.assertLessEqual(len(tas.surecler), 3)
        self.assertEqual(oz["sayac"]["ok"], 3)

    def test_guv3_acik_hedef_yasak_model_gonderilmez(self):
        o = {"id": "a", "brief": "Genel soru", "veri": "genel", "sinif": "basit", "alan": "genel",
             "hedef": {"yol": "bedava-api", "platform": "bedava", "havuz": "bedava", "model": "gpt-6-astra",
                       "kimlik": "gpt-6-astra", "efor": "high"}}
        ks, tas = self._kos([o], O.veri71())
        oz = ks.calistir()
        self.assertEqual(oz["isler"][0]["durum"], "engel")
        self.assertEqual(tas.istekler, [])

    def test_guv3_taban_ve_kapali_havuz(self):
        an = O.kota71(agy_gemini=(0.0, 0.0))
        ks, tas = self._kos([self._agy("a")], _sv())
        ks.kota_anlik = an
        oz = ks.calistir()
        self.assertEqual(oz["isler"][0]["durum"], "bekle")
        self.assertEqual(tas.surecler, [])

    def test_guv6_cocuk_ortaminda_anahtar_yok(self):
        os.environ["ORNEK_SIR_API_KEY"] = "gizli-deger-123456"
        try:
            env = suru.temiz_ortam(O.veri71())
            self.assertNotIn("ORNEK_SIR_API_KEY", env)
            self.assertIn("PATH", {k.upper() for k in env})
        finally:
            os.environ.pop("ORNEK_SIR_API_KEY", None)

    def test_guv8_ardisik_kalici_hatada_durur(self):
        ks, tas = self._kos([self._agy(f"a{n}") for n in range(6)], _sv(),
                            surec=lambda a, s: (1, "", "RESOURCE_EXHAUSTED quota"))
        oz = ks.calistir()
        self.assertLessEqual(len(tas.surecler), 3)            # en çok 1 + eşzamanlı (2); kalanlar engel
        self.assertGreaterEqual(oz["sayac"]["engel"], 3)
        self.assertTrue(any("ardışık" in n for n in oz["notlar"]))

    def test_guv8_basarili_yanittaki_403_kapatmaz(self):
        ks, tas = self._kos([self._agy("a")], _sv(),
                            surec=lambda a, s: (0, json.dumps({"status": "SUCCESS",
                                                               "response": "ÖZET: 403 forbidden kodu incelendi"}), ""))
        oz = ks.calistir()
        self.assertEqual(oz["isler"][0]["durum"], "ok")
        self.assertFalse(ks.agy_kapali)

    def test_guv9_dusus_yok_kardese_gitmez(self):
        from test_suru import _veri, _oge, SahteTasiyici, SahteSaat
        os.environ["ORNEK_TEST_API_KEY"] = "sentetik-anahtar-0000"
        try:
            tas = SahteTasiyici({"deepseek-v4.1-flash": [(503, "x")]})
            ks = suru.Kosucu({"is_id": "t", "isler": [_oge("a", brief="What is 2+2?")]}, _veri(), tasiyici=tas,
                             saat=SahteSaat(), olc_yaz=False, durum_yaz=False, dusus="yok")
            ks.calistir()
            self.assertTrue(all(g["model"] == "deepseek-v4.1-flash" for g in tas.istekler))
        finally:
            os.environ.pop("ORNEK_TEST_API_KEY", None)

    def test_guv12_kisi_duzeyi_saglik_kaydi_engel(self):
        self.assertTrue(araclar.kisi_saglik_tara("Hasta: Ayşe Demir, protokol no 123456"))
        self.assertTrue(araclar.kisi_saglik_tara("Tanı: M54.5"))
        self.assertEqual(araclar.kisi_saglik_tara("Bel ağrılı hastalarda egzersiz etkisi (RCT, n=120)"), [])

    def test_guv15_hold_dolarsa_gondermez(self):
        ks, _ = self._kos([], O.veri71())
        ks.hold.append((ks.saat.simdi(), 10 ** 9))
        self.assertFalse(ks._hold_bekle(100, 1000, 0.2, en_cok_sn=5))

    def test_guv10_temizle_tam_kok(self):
        d = Path(tempfile.mkdtemp())
        (d / "ab12.pb").write_text("x")
        (d / "xab12y.pb").write_text("x")
        y = durum_dizini() / "agy-cagri.jsonl"
        y.parent.mkdir(parents=True, exist_ok=True)
        y.write_text(json.dumps({"zaman": (S - timedelta(days=30)).isoformat(), "conversation_id": "ab12"}) + "\n",
                     encoding="utf-8")
        v = O.veri71(lambda x: x["platformlar"]["platformlar"]["agy"].__setitem__("konusma_dizini", str(d / "*.pb")))
        r = suru.temizle(7, False, v)
        self.assertEqual(r["aday"], 1)


if __name__ == "__main__":
    unittest.main()
