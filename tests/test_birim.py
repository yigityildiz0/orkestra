"""v7.1 birim testleri (tasarım 12.3): kota çözücüleri, keşif yardımcıları, kişisel katman, uyarlanır ağırlık.
Ağ, model ve kayıt defteri yok: sahte G/Ç."""
import json
import os
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import _ortak as O
from ork import kesif, kota, secici
from ork.veri import Veri, kisisel_dizini

S = O.SIMDI


class KotaCozucu(unittest.TestCase):
    def test_claude_get_usage_gercek_bicim(self):
        g = {"plan": {"status": "ok", "windows": [
            {"label": "Current session", "percentUsed": 49, "resetsAt": "2026-11-15T15:00:00Z"},
            {"label": "Weekly · all models", "percentUsed": 20, "resetsAt": "2026-11-22T07:00:00Z"},
            {"label": "Weekly · OzelModel", "percentUsed": 90, "resetsAt": "2026-11-22T07:00:00Z"}]}}
        out = kota.claude_coz(json.dumps(g))
        self.assertAlmostEqual(out["5s"]["kalan"], 0.51)
        self.assertAlmostEqual(out["hafta"]["kalan"], 0.80)
        self.assertEqual(out["hafta"]["sifirlama"], "2026-11-22T07:00:00Z")

    def test_claude_status_ok_degil_none(self):
        self.assertIsNone(kota.claude_coz({"plan": {"status": "error", "windows": []}}))

    def test_codex_coz_ordinary_kredi_kayan(self):
        r = {"rateLimits": {"limitId": "codex", "primary": {"usedPercent": 0, "resetsAt": 1763300000,
                                                            "windowDurationMins": 300},
                            "secondary": {"usedPercent": 100, "resetsAt": 1763278080, "windowDurationMins": 10080}},
             "ordinaryUsageAllowed": False,
             "rateLimitResetCredits": {"availableCount": 1, "expiresAt": "2026-12-01T00:00:00Z"}}
        pen, ek = kota.codex_coz(r)
        self.assertIsNone(pen["5s"]["sifirlama"])           # usedPercent 0: kayan pencere, sıfırlama yok
        self.assertEqual(pen["hafta"]["kalan"], 0.0)
        self.assertFalse(ek["ordinary"])
        self.assertEqual(ek["reset_kredisi"]["adet"], 1)
        self.assertIsNotNone(ek["dolu_bitis"])

    def test_agy_kovalari_en_dusuk_okuma(self):
        okumalar = iter([0.96, 0.95, 0.97])

        def calistir(*_):
            k = next(okumalar)
            return json.dumps({"command": {"data": {"groups": [{"name": "Gemini", "buckets": [
                {"id": "gemini-weekly", "window": "weekly", "remaining_fraction": k, "reset_time": "2026-11-21T15:00Z"},
                {"id": "gemini-5h", "window": "5h", "remaining_fraction": 1.0}]}]}}})
        out = kota.agy_kovalari(_calistir=calistir, okuma=3, _uyu=lambda s: None)
        self.assertEqual(out["gemini-weekly"]["kalan"], 0.95)
        self.assertEqual(out["gemini-weekly"]["okuma"], 3)
        self.assertEqual(out["gemini-weekly"]["pencere"], "hafta")

    def test_bedava_sinirlar(self):
        g = {"daily_limit_tokens": 2_000_000, "daily_remaining_tokens": 1_500_000, "concurrent_requests": 3,
             "concurrency_limit": 8, "fair_share_active": True, "level": "ornek"}
        out = kota.bedava_kota_coz(g, {"x-ratelimit-remaining-requests": "1100"}, simdi=S)
        self.assertEqual(out["sinirlar"]["concurrency_limit"], 8)
        self.assertTrue(out["sinirlar"]["fair_share"])
        self.assertEqual(out["sinirlar"]["istek_5dk_kalan"], 1100.0)
        self.assertIsNone(kota.bedava_kota_coz({}, {}, simdi=S))

    def test_soguma_profil(self):
        p = {"503": [120, 240, 600]}
        self.assertEqual([kota.soguma_suresi("503", n, simdi=S, profil=p) for n in (1, 2, 3, 9)],
                         [120.0, 240.0, 600.0, 600.0])
        self.assertGreater(kota.soguma_suresi("503", 1, simdi=S), 120)      # profilsiz varsayılan

    def test_gecmis_ve_kalibre(self):
        with tempfile.TemporaryDirectory() as td:
            yol = Path(td) / "kota-gecmis.jsonl"
            sf = (S + timedelta(days=3)).isoformat()
            for i, k in enumerate((0.90, 0.90, 0.75)):
                an = {"havuzlar": {"codex_plus": {"durum": "ok", "pencereler": {"hafta": {"kalan": k, "sifirlama": sf}}}}}
                kota.gecmis_ekle(an, simdi=S + timedelta(hours=i), yol=yol)
            g = kota.gecmis_oku(yol)
            self.assertEqual(len(g), 2)                   # değişmeyen okuma yazılmaz
            olc = [{"havuz": "codex_plus", "zaman": (S + timedelta(minutes=90)).isoformat(), "maliyet_usd_e": 3.0}]
            k = kota.kalibre("codex_plus", "hafta", g, olc)
            self.assertAlmostEqual(k["K"], 20.0)          # 3 USD-e / 0.15
            self.assertIsNone(kota.kalibre("codex_plus", "hafta", g, []))


class KesifYardimci(unittest.TestCase):
    def test_appx_kok_sahte_winreg(self):
        class K:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False
        anahtarlar = ["Ad.Uygulama_1.2_x64__abc", "Ad.UygulamaPrimaryRuntime_9_x64__abc", "Baska_1"]
        wr = SimpleNamespace(HKEY_CURRENT_USER=0, OpenKey=lambda *a: K(),
                             EnumKey=lambda k, i: anahtarlar[i] if i < len(anahtarlar) else (_ for _ in ()).throw(OSError()),
                             QueryValueEx=lambda k, ad: ("C:/Paket/Ad.Uygulama", 1))
        self.assertEqual(kesif._appx_kok("Ad.Uygulama_", _winreg=wr, _ps=lambda *a, **k: None),
                         ["C:/Paket/Ad.Uygulama"])

    def test_ikili_coz_yuksek_surum(self):
        with tempfile.TemporaryDirectory() as td:
            a, b = Path(td) / "eski" / "cli.exe", Path(td) / "yeni" / "cli.exe"
            for p in (a, b):
                p.parent.mkdir()
                p.write_bytes(b"x")
            sur = {str(a): "0.167.0", str(b): "0.169.0"}
            out = kesif.ikili_coz({"ikili": [str(a)], "appx": "Ad_", "appx_yol": "cli.exe"},
                                  surum_al=lambda y: sur.get(str(Path(y))), which=lambda x: None,
                                  _appx=lambda onek: [str(b.parent)])
            yol = out[0] if isinstance(out, tuple) else (out.get("yol") if isinstance(out, dict) else out)
            self.assertEqual(Path(yol), b)

    def test_masaustu_host(self):
        self.assertTrue(kesif.masaustu_host({"CLAUDE_CODE_ENTRYPOINT": "claude-desktop",
                                             "CLAUDE_CODE_SDK_HAS_HOST_AUTH_REFRESH": "1"}))
        self.assertFalse(kesif.masaustu_host({}))

    def test_takma_adlar(self):
        ikili = b'xx opus:"claude-opus-5-5" sonnet : "claude-sonnet-5-5" opus:"claude-opus-4-1"'
        out = kesif.claude_takma_adlari("x", _oku=lambda y: ikili)
        self.assertEqual(out, {"opus": "claude-opus-5-5", "sonnet": "claude-sonnet-5-5"})
        self.assertEqual(kesif.claude_takma_adlari("x", _oku=lambda y: (_ for _ in ()).throw(OSError())), {})

    def test_uc_girisi(self):
        api = {"anahtar_env": "YOK"}
        self.assertEqual(kesif.uc_girisi(api, _get=lambda *a: (200, {}, {}), _anahtar=lambda: "k")["giris"], "var")
        self.assertEqual(kesif.uc_girisi(api, _get=lambda *a: (401, {}, {}), _anahtar=lambda: "k")["giris"], "yok")
        self.assertEqual(kesif.uc_girisi(api, _anahtar=lambda: None)["giris"], "yok")

    def test_agy_dogrula_g1_kapali(self):
        def run(argv, **k):
            a = argv[1:]
            if a == ["models"]:
                out = "gemini-4-hydrogen\n"
            elif "/config" in a:
                out = json.dumps({"command": {"data": {"useG1Credits": True}}})
            elif "/effort" in a:
                out = json.dumps({"command": {"data": {"available": ["low", "medium", "high"]}}})
            else:
                out = "{}"
            return SimpleNamespace(stdout=out)
        out = kesif.agy_dogrula("agy", ["gemini-4-hydrogen"], _run=run)
        self.assertTrue(out["useG1Credits"])
        self.assertEqual(out["eforlar"]["gemini-4-hydrogen"], ["low", "medium", "high"])
        self.assertTrue(out["notlar"])

    def test_efor_farki(self):
        self.assertEqual(kesif.efor_farki(["none", "low"], ["low", "ultra"]), {"fazla": ["none"], "eksik": ["ultra"]})


class KisiselKatman(unittest.TestCase):
    def test_kisisel_oncelik(self):
        with mock.patch.dict(os.environ, {"ORKESTRA_DIR": "/a", "ORKESTRA_KISISEL": "/b"}):
            self.assertEqual(kisisel_dizini(), Path("/b"))
        with mock.patch.dict(os.environ, {"ORKESTRA_DIR": "/a"}):
            os.environ.pop("ORKESTRA_KISISEL", None)
            self.assertEqual(kisisel_dizini(), Path("/a"))

    def test_agy_otomatik_bool_nesne(self):
        def f(v):
            return lambda d: d["kullanici-kurallari"].__setitem__("agy_otomatik", v) \
                if "kullanici-kurallari" in d else d["kurallar"].__setitem__("agy_otomatik", v)
        self.assertEqual(O.veri71(f(True)).agy_otomatik(), {"acik": True})
        self.assertEqual(O.veri71(f(False)).agy_otomatik(), {"acik": False})
        self.assertTrue(O.veri71(f({"acik": 1, "guvenceler": {}})).agy_otomatik()["acik"] is True)

    def test_tercihli_onde_goc(self):
        dout = {}
        self.assertTrue(secici._onde({"tercihli": {"codex_plus": True}}, "codex_plus", 0.95, 1.0, 0.1, dout))
        self.assertEqual(dout["onde"], {"codex_plus": True})


class ProjeVarsayilanVeri(unittest.TestCase):
    def test_varsayilan_veri_ve_gizli_ustun(self):
        v = O.veri71()
        istek = {"sinif": "basit", "alan": "kod", "alt_alan": "gunluk"}
        # güvenilmeyen (listede olmayan) proje kökü veriyi `genel`e indiremez
        i = secici.istek_hazirla(dict(istek), v, {"varsayilan_veri": "genel", "kok": str(O.KOK)})
        self.assertEqual(i["veri"], "bilinmiyor")
        v.kurallar.setdefault("gizlilik", {})["guvenli_projeler"] = [str(O.KOK)]
        i = secici.istek_hazirla(dict(istek), v, {"varsayilan_veri": "genel", "kok": str(O.KOK)})
        self.assertEqual(i["veri"], "genel")
        # sıkılaştırma her zaman geçerli
        v.kurallar["gizlilik"]["guvenli_projeler"] = []
        i = secici.istek_hazirla(dict(istek), v, {"varsayilan_veri": "kisisel", "kok": str(O.KOK)})
        self.assertEqual(i["veri"], "kisisel")
        v.kurallar["gizlilik"]["guvenli_projeler"] = [str(O.KOK)]
        i = secici.istek_hazirla(dict(istek), v, {"varsayilan_veri": "genel", "gizli": True})
        self.assertEqual(i["veri"], "gizli")
        i = secici.istek_hazirla(dict(istek, veri="kisisel"), v, {"varsayilan_veri": "genel"})
        self.assertEqual(i["veri"], "kisisel")


class SikiVeriSor(unittest.TestCase):
    def test_saglik_claude_tabaninda_sor_T1(self):
        r = secici.sec({"sinif": "normal", "alan": "yazim", "alt_alan": "rapor", "veri": "saglik"}, O.veri71(),
                       O.kota71(claude=(0.14, 0.9)), {}, S)
        self.assertEqual(r["durum"], "sor")
        self.assertEqual(r["tetik"], "T1")
        self.assertIn("veri sınıfı", r["soru"])

    def test_elle_yol_otomatigin_onune_gecmez(self):
        def kapali(d):
            d["kullanici-kurallari"]["agy_otomatik"].update(acik=False)
        r = secici.sec({"alan": "kod", "alt_alan": "gunluk", "sinif": "kod", "veri": "genel", "zorla": "opus"},
                       O.veri71(kapali), O.kota71(), {}, S)
        self.assertNotEqual((r.get("secim") or {}).get("yol"), "agy-elle")


class UyarlanirAgirlik(unittest.TestCase):
    def _veri(self):
        def f(d):
            k = d.get("kullanici-kurallari") or d["kurallar"]
            k.setdefault("faz", {})["uyarlanir_agirlik"] = {"acik": True, "alt": 1.0, "ust": 3.0, "adim": 1.25}
        return O.veri71(f)

    def _gecmis(self, hid, kalanlar, sf):
        return [{"zaman": (S - timedelta(days=2 - i)).isoformat(), "havuz": hid, "pencere": "hafta", "kalan": k,
                 "sifirlama": sf} for i, k in enumerate(kalanlar)]

    def test_artik_buyutur_tukenme_kucultur(self):
        v = self._veri()
        an = O.kota71(codex=(0.9, 0.80), agy_gemini=(1.0, 0.20))
        sf_c = an["havuzlar"]["codex_plus"]["pencereler"]["hafta"]["sifirlama"]
        sf_a = an["havuzlar"]["agy_gemini"]["pencereler"]["hafta"]["sifirlama"]
        g = self._gecmis("codex_plus", [0.82, 0.81, 0.80], sf_c) + self._gecmis("agy_gemini", [0.80, 0.50, 0.20], sf_a)
        out = secici.uyarlanir_agirlik(v, an, {}, g, S)
        o_c = float(v.faz()["tempo_agirlik"].get("codex_plus", 1.0))
        o_a = float(v.faz()["tempo_agirlik"].get("agy_gemini", 1.0))
        self.assertAlmostEqual(out["codex_plus"]["o"], round(min(3.0, o_c * 1.25), 3))   # yavaş harcıyor: artık
        self.assertAlmostEqual(out["agy_gemini"]["o"], round(max(1.0, o_a / 1.25), 3))   # hızlı: erken tükenme
        d = {"tempo_agirlik_uyarlanmis": out}
        self.assertEqual(secici.tempo_agirligi(v.faz(), d, "codex_plus", S), out["codex_plus"]["o"])
        # kayıt bir hafta geçerli (günlük güncelleme idempotent), sonra statik değere döner
        self.assertEqual(secici.tempo_agirligi(v.faz(), d, "codex_plus", S + timedelta(hours=25)),
                         out["codex_plus"]["o"])
        self.assertEqual(secici.tempo_agirligi(v.faz(), d, "codex_plus", S + timedelta(days=8)), o_c)

    def test_ayni_gun_ikinci_plan_katlamaz(self):
        v = self._veri()
        an = O.kota71(codex=(0.9, 0.80), agy_gemini=(1.0, 0.20))
        sf_c = an["havuzlar"]["codex_plus"]["pencereler"]["hafta"]["sifirlama"]
        g = self._gecmis("codex_plus", [0.82, 0.81, 0.80], sf_c)
        out = secici.uyarlanir_agirlik(v, an, {}, g, S)
        d = {"tempo_agirlik_uyarlanmis": out}
        for n in range(5):                                   # aynı gün tekrar: değer değişmez
            self.assertEqual(secici.uyarlanir_agirlik(v, an, d, g, S + timedelta(hours=n + 1)), {})
        ertesi = secici.uyarlanir_agirlik(v, an, d, g, S + timedelta(hours=25))
        self.assertAlmostEqual(ertesi["codex_plus"]["o"], round(min(3.0, out["codex_plus"]["o"] * 1.25), 3))

    def test_kapali_bos(self):
        self.assertEqual(secici.uyarlanir_agirlik(O.veri71(), O.kota71(), {}, [], S), {})


if __name__ == "__main__":
    unittest.main()
