"""Toplu koşucu (tasarım 12.3 test_suru): ağ ve model yok; sahte taşıyıcı ve sahte saat."""
import json
import os
import sys
import threading
import unittest
from pathlib import Path

import _ortak as O
from ork import kota, suru
from ork.veri import durum_dizini, sema_dogrula, json_oku

SAHTE_ANAHTAR = "sentetik-anahtar-0000"


class SahteSaat:
    def __init__(self):
        self.t = 0.0
        self.k = threading.Lock()

    def simdi(self):
        with self.k:
            return self.t

    def uyu(self, sn):
        with self.k:
            self.t += max(sn, 0)


class SahteTasiyici:
    def __init__(self, http=None, surec=None):
        self.http_senaryo = http or {}
        self.surec_fn = surec
        self.istekler = []
        self.surecler = []
        self.k = threading.Lock()

    def http(self, url, govde, basliklar, zaman_asimi):
        with self.k:
            self.istekler.append(govde)
            L = self.http_senaryo.get(govde["model"]) or [(200, "tamam")]
            x = L.pop(0) if len(L) > 1 else L[0]
        kod, metin = x
        if kod == 200:
            return 200, {}, {"choices": [{"message": {"content": metin}}],
                             "usage": {"prompt_tokens": 100, "completion_tokens": 20}}
        return kod, {}, {"error": metin}

    def surec(self, argv, stdin, zaman_asimi, cwd=None, env=None):
        with self.k:
            self.surecler.append(list(argv))
        return self.surec_fn(argv, stdin) if self.surec_fn else (0, "", "")


def _veri(agy_teyit=True):
    def d(x):
        p = x["platformlar"]["platformlar"]
        p["bedava"]["suru"] = {
            "hesap_eszamanli_kullan": 20, "model_eszamanli": {"deepseek-v4.1-flash": 3, "qwen3.8-flash-next": 3,
                                                             "gemma-4-31b": 8, "_arac": 8},
            "kardes": {"deepseek-v4.1-flash": ["qwen3.8-flash-next@medium"],
                       "gemma-4-31b": ["qwen3.8-flash-next@low"]},
            "kardes_kosul": {"gemma-4-31b": {"turkce": False, "kritik_kod": False}},
            "yeniden_dene": {"503": {"geri_cekilme_sn": [15, 30, 60], "en_cok": 6}},
            "oy_adaylari": ["qwen3.8-flash-next@medium", "gemma-4-31b@varsayilan"]}
        p["agy"]["cagri"]["argv_oto"] = ["{ikili}", "-p", "{istem}", "--model", "{taban}", "--effort", "{efor}",
                                         "--mode", "{kip}", "--output-format", "json", "--print-timeout", "{sure}"]
        x["kullanici-kurallari"]["agy_otomatik"]["karar"] = {"teyit_edildi": agy_teyit}
        x["kullanici-kurallari"]["agy_otomatik"]["guvenceler"].update(
            {"teyitsiz_profil": {"eszamanli": 1, "gunluk_cagri_tavani": 15}})
    return O.veri71(d)


def _oge(id_, model="deepseek-v4.1-flash", efor="high", yol="bedava-api", platform="bedava", havuz="bedava",
         brief="Genel bir soru: 2+2 kaç?", **ek):
    return dict({"id": id_, "brief": brief, "veri": "genel", "sinif": "basit", "alan": "genel",
                 "hedef": {"yol": yol, "platform": platform, "havuz": havuz, "model": model, "kimlik": model,
                           "efor": efor}}, **ek)


def _kos(isler, tas, veri=None, **k):
    ks = suru.Kosucu({"is_id": "t", "isler": isler}, veri or _veri(), tasiyici=tas, saat=k.pop("saat", SahteSaat()),
                     olc_yaz=False, durum_yaz=k.pop("durum_yaz", False), **k)
    ks._ikili = lambda pid: "araci.exe"
    return ks


class Temel(unittest.TestCase):
    def setUp(self):
        os.environ["ORNEK_TEST_API_KEY"] = SAHTE_ANAHTAR
        for f in ("agy-cagri.jsonl", "durum.json"):
            try:
                (durum_dizini() / f).unlink()
            except OSError:
                pass

    def tearDown(self):
        os.environ.pop("ORNEK_TEST_API_KEY", None)

    def test_503_iki_kez_kardese_duser(self):
        tas = SahteTasiyici({"deepseek-v4.1-flash": [(503, "x"), (503, "x"), (503, "x")],
                             "qwen3.8-flash-next": [(200, "ÖZET: dört")]})
        oz = _kos([_oge("a", brief="What is 2+2?")], tas).calistir()
        s = oz["isler"][0]
        self.assertEqual(s["durum"], "ok")
        self.assertEqual(s["dusus"], "kardes")
        self.assertTrue(s["model"].startswith("qwen3.8-flash-next"))
        self.assertEqual(s["ozet"], "dört")

    def test_turkce_ogede_gemmaya_dusulmez(self):
        v = _veri()
        v.platformlar_ham["platformlar"]["bedava"]["suru"]["kardes"]["deepseek-v4.1-flash"] = ["gemma-4-31b"]
        tas = SahteTasiyici({"deepseek-v4.1-flash": [(503, "x")]})
        oz = _kos([_oge("a", brief="Şu metni düzelt: ığüş çok güzel")], tas, veri=v).calistir()
        self.assertEqual(oz["isler"][0]["durum"], "bekle")              # kapasite dolu; daha zayıf sınıfa yok
        self.assertTrue(all(g["model"] == "deepseek-v4.1-flash" for g in tas.istekler))
        self.assertEqual(len(tas.istekler), 6)

    def test_429_deneme_sayilmaz(self):
        tas = SahteTasiyici({"deepseek-v4.1-flash": [(429, "fair share"), (429, "fair share"), (200, "ok")]})
        oz = _kos([_oge("a")], tas).calistir()
        self.assertEqual(oz["isler"][0]["durum"], "ok")
        self.assertEqual(oz["isler"][0]["deneme"], 0)

    def test_5dk_hold_bekletir(self):
        def d(x):
            x["platformlar"]["havuzlar"]["bedava"]["K_p"]["oncul"]["5dk_token"] = 12000
        v = O.veri71(d)
        saat = SahteSaat()
        tas = SahteTasiyici()
        oz = _kos([_oge("a", max_tokens=6000), _oge("b", max_tokens=6000, bagimli=["a"])], tas, veri=v,
                  saat=saat).calistir()
        self.assertEqual(oz["sayac"]["ok"], 2)
        self.assertGreaterEqual(saat.t, 300)                       # ikinci istek pencere boşalana kadar bekledi

    def test_tarama_bulgusu_engel_sifir_istek(self):
        tas = SahteTasiyici()
        oz = _kos([_oge("a", brief="anahtar: " + SAHTE_ANAHTAR), _oge("b")], tas).calistir()
        durum = {s["id"]: s["durum"] for s in oz["isler"]}
        self.assertEqual(durum, {"a": "engel", "b": "ok"})
        self.assertEqual(len(tas.istekler), 1)
        self.assertNotIn(SAHTE_ANAHTAR, json.dumps(oz))

    def test_kisisel_veri_kamu_hedefe_gitmez(self):
        tas = SahteTasiyici()
        oz = _kos([_oge("a", veri="kisisel")], tas).calistir()
        self.assertEqual(oz["isler"][0]["durum"], "engel")
        self.assertEqual(tas.istekler, [])

    def test_claude_ogesi_calistirilmaz(self):
        tas = SahteTasiyici()
        o = _oge("c", model="opus", yol="claude-agent", platform="claude", havuz="claude_max")
        oz = _kos([o], tas).calistir()
        self.assertEqual(len(oz["claude_isleri"]), 1)
        self.assertIn("Agent(", oz["claude_isleri"][0]["cagri"])
        self.assertEqual(tas.istekler, [])

    def test_ozet_semaya_uyar_ve_4kb(self):
        tas = SahteTasiyici({"deepseek-v4.1-flash": [(200, "x" * 5000)]})
        oz = _kos([_oge(f"p{n}") for n in range(40)], tas).calistir()
        self.assertLessEqual(len(json.dumps(oz, ensure_ascii=False).encode("utf-8")), 4096)
        sema = json_oku(O.KOK / "data" / "sema" / "suru-ozet.schema.json")
        self.assertEqual(sema_dogrula(oz, sema), [])

    def test_oy_iki_uyusursa_ucuncu_yok(self):
        tas = SahteTasiyici({"deepseek-v4.1-flash": [(200, "CEVAP: 4")], "qwen3.8-flash-next": [(200, "CEVAP: 4")],
                             "gemma-4-31b": [(200, "CEVAP: 5")]})
        oz = _kos([_oge("a", desen="oy", cevap_deseni=r"CEVAP:\s*(\S+)")], tas).calistir()
        self.assertEqual(oz["isler"][0]["durum"], "ok")
        self.assertEqual(len(tas.istekler), 2)

    def test_aday_yargic_test_kabuksuz(self):
        def surec(argv, stdin):
            return (0 if "gecer" in Path(argv[-1]).read_text(encoding="utf-8") else 1), "", ""
        tas = SahteTasiyici({"deepseek-v4.1-flash": [(200, "kalir")], "qwen3.8-flash-next": [(200, "gecer")]},
                            surec=surec)
        cik = str(Path(durum_dizini()) / "aday.txt")
        o = _oge("a", desen="aday_yargic", cikti=cik, dogrulama={"tur": "test", "komut": ["python", "-c", "x", "{cikti}"]})
        oz = _kos([o], tas).calistir()
        self.assertEqual(oz["isler"][0]["durum"], "ok")
        self.assertTrue(oz["isler"][0]["model"].startswith("qwen"))
        self.assertEqual(tas.surecler[0][:2], [sys.executable, "-I"])     # shell yok, izole yorumlayıcı


def _agy_js(yanit="ÖZET: tamam", **ek):
    return json.dumps(dict({"status": "SUCCESS", "response": yanit, "usage": {"input_tokens": 9000,
                                                                             "output_tokens": 50},
                            "conversation_id": "k1"}, **ek))


class Agy(unittest.TestCase):
    def setUp(self):
        for f in ("agy-cagri.jsonl", "durum.json"):
            try:
                (durum_dizini() / f).unlink()
            except OSError:
                pass

    def _o(self, id_, **ek):
        return _oge(id_, model="gemini-4-hydrogen", efor="high", yol="agy-oto", platform="agy", havuz="agy_gemini",
                    **ek)

    def test_mikro_ogeler_tek_cagri(self):
        yan = "\n".join(f"### ÖĞE m{n}\nyanıt {n}" for n in range(5))
        tas = SahteTasiyici(surec=lambda a, s: (0, _agy_js(yan), ""))
        cik = Path(durum_dizini()) / "mikro"
        oz = _kos([self._o(f"m{n}", boyut="mikro", cikti=str(cik / f"m{n}.md")) for n in range(5)], tas).calistir()
        self.assertEqual(len(tas.surecler), 1)
        self.assertEqual(oz["sayac"]["ok"], 5)
        self.assertEqual((cik / "m3.md").read_text(encoding="utf-8"), "yanıt 3")

    def test_bos_yanit_ve_ret_tek_onekli_tekrar(self):
        cevaplar = [(0, _agy_js("", denied_actions=["write_file"]), ""), (0, _agy_js("ÖZET: ikinci"), "")]
        tas = SahteTasiyici(surec=lambda a, s: cevaplar.pop(0))
        oz = _kos([self._o("a")], tas).calistir()
        self.assertEqual(oz["isler"][0]["durum"], "ok")
        self.assertEqual(len(tas.surecler), 2)
        self.assertTrue(tas.surecler[1][2].startswith(suru.DUSUNME_ONEKI))

    def test_bos_stdout_cikis_0_hata(self):
        tas = SahteTasiyici(surec=lambda a, s: (0, "", ""))
        self.assertEqual(_kos([self._o("a")], tas).calistir()["isler"][0]["durum"], "hata")

    def test_eszamanlilik_ve_baslatma_araligi(self):
        saat = SahteSaat()
        aktif, en = [0], [0]
        k = threading.Lock()

        def surec(a, s):
            with k:
                aktif[0] += 1
                en[0] = max(en[0], aktif[0])
            with k:
                aktif[0] -= 1
            return 0, _agy_js(), ""
        tas = SahteTasiyici(surec=surec)
        ks = _kos([self._o(f"a{n}") for n in range(4)], tas, saat=saat)
        oz = ks.calistir()
        self.assertEqual(oz["sayac"]["ok"], 4)
        self.assertLessEqual(en[0], 2)
        b = sorted(ks.agy_baslatmalar)
        self.assertTrue(all(y - x >= 20 - 1e-9 for x, y in zip(b, b[1:])), b)

    def test_gunluk_tavan_bekle(self):
        y = durum_dizini() / "agy-cagri.jsonl"
        y.parent.mkdir(parents=True, exist_ok=True)
        from ork.veri import simdi_utc
        z = simdi_utc().isoformat(timespec="seconds")
        y.write_text("".join(json.dumps({"zaman": z, "durum": "ok"}) + "\n" for _ in range(10)), encoding="utf-8")
        tas = SahteTasiyici(surec=lambda a, s: (0, _agy_js(), ""))
        oz = _kos([self._o("a")], tas).calistir()
        self.assertEqual(oz["isler"][0]["durum"], "bekle")              # saatlik tavan 10
        self.assertEqual(tas.surecler, [])

    def test_403_kapanis_kaydi(self):
        tas = SahteTasiyici(surec=lambda a, s: (1, "", "HTTP 403 Forbidden: account suspended"))
        oz = _kos([self._o("a"), self._o("b", bagimli=["a"])], tas, durum_yaz=True).calistir()
        self.assertEqual(oz["isler"][0]["durum"], "engel")
        self.assertTrue(kota.durum_oku().get("agy_otomatik_kapali"))
        self.assertTrue(any("403" in n for n in oz["notlar"]))

    def test_model_eksik_reddedilir(self):
        tas = SahteTasiyici(surec=lambda a, s: (0, _agy_js(), ""))
        o = self._o("a")
        o["hedef"]["efor"] = None
        oz = _kos([o], tas).calistir()
        self.assertEqual(oz["isler"][0]["durum"], "hata")
        self.assertEqual(tas.surecler, [])

    def test_teyitsiz_profil_notu(self):
        tas = SahteTasiyici(surec=lambda a, s: (0, _agy_js(), ""))
        oz = _kos([self._o("a")], tas, veri=_veri(agy_teyit=False)).calistir()
        self.assertTrue(any("teyit" in n for n in oz["notlar"]))


class Yardimcilar(unittest.TestCase):
    def test_toplu_ayristir_sema_ve_metin(self):
        self.assertEqual(suru.toplu_ayristir({"structured": {"ogeler": [{"id": "a", "yanit": "1"}]}}, ["a"]),
                         {"a": "1"})
        self.assertEqual(suru.toplu_ayristir({"response": "### ÖĞE a\nx\n### ÖĞE b\ny"}, ["a", "b"]),
                         {"a": "x", "b": "y"})

    def test_kuru_kosu_istek_yok(self):
        tas = SahteTasiyici()
        oz = _kos([_oge("a")], tas, kuru=True).calistir()
        self.assertEqual(oz["sayac"]["ok"], 1)
        self.assertEqual(tas.istekler, [])


if __name__ == "__main__":
    unittest.main()
