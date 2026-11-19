"""Kota okuyucu (S20, S24, S39, S43 + adaptörler). Model çağrısı yok; ağ yok (sahte G/Ç); sır sızıntısı denetlenir."""
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path

import _ortak as O
from ork import kota, secici
from ork.veri import atomik_yaz, durum_dizini

S = O.SIMDI
SAHTE_SIR = "SIR-test-0000-sentetik"          # sentetik; çıktıda görünmemeli


class SahteSurec:
    def __init__(self, satirlar):
        self.satirlar = list(satirlar)
        self.yazilan = []
        self.stdin = self
        self.stdout = self

    def write(self, x):
        self.yazilan.append(x)

    def flush(self):
        pass

    def readline(self):
        return self.satirlar.pop(0) if self.satirlar else ""

    def kill(self):
        pass


def _temizle():
    for f in Path(durum_dizini()).glob("*"):
        if f.is_file():
            f.unlink()


class Adaptorler(unittest.TestCase):
    def setUp(self):
        _temizle()

    def test_codex_app_server(self):
        reset = int((S + timedelta(hours=2)).timestamp())
        yan = {"id": 2, "result": {"rateLimits": {
            "primary": {"usedPercent": 25, "resetsAt": reset, "windowDurationMins": 300},
            "secondary": {"usedPercent": 60, "resetsAt": reset + 86400, "windowDurationMins": 10080}}}}
        p = SahteSurec(['{"id":1,"result":{}}\n', json.dumps(yan) + "\n"])
        out = kota.codex_limits("codex.exe", _popen=lambda *a, **k: p)
        self.assertAlmostEqual(out["5s"]["kalan"], 0.75)
        self.assertAlmostEqual(out["hafta"]["kalan"], 0.40)
        self.assertIn("account/rateLimits/read", "".join(p.yazilan))
        self.assertNotIn("turn", "".join(p.yazilan))                 # model çağrısı yok

    def test_agy_usage(self):
        ham = {"command": {"data": {"groups": [
            {"name": "Gemini Models", "buckets": [{"window": "5h", "remaining_fraction": 0.8, "reset_time": "x"},
                                                  {"window": "weekly", "remaining_fraction": 0.6}]}]}}}
        out = kota.agy_limits(_calistir=lambda *a: json.dumps(ham))
        self.assertIn(("Gemini Models", "5s", 0.8, "x"), out)
        self.assertIn(("Gemini Models", "hafta", 0.6, ""), out)

    def test_claude_get_usage_bicimleri(self):
        self.assertEqual(kota.claude_coz("5s=32,hafta=91")["hafta"]["kalan"], 0.91)
        w = {"windows": [{"label": "Current session", "used_percent": 70, "resets_at": "2026-11-15T15:00:00Z"},
                         {"label": "Weekly (all models)", "utilization": 25}]}
        out = kota.claude_coz(w)
        self.assertAlmostEqual(out["5s"]["kalan"], 0.30)
        self.assertAlmostEqual(out["hafta"]["kalan"], 0.75)
        w2 = {"windows": [{"label": "Weekly (all models)", "used_percent": 40},
                          {"label": "Weekly ozelmodel", "used_percent": 99}]}
        self.assertAlmostEqual(kota.claude_coz(w2, alt_sayaclar=["ozelmodel"])["hafta"]["kalan"], 0.60)

    def test_claude_utilization_her_zaman_yuzde(self):
        """utilization Cetvel kuralıyla aynı: her zaman YÜZDE (0..100); ≤1 değer oran sayılmaz."""
        for kul, beklenen in ((0.25, 0.9975), (0.5, 0.995), (1, 0.99), (1.0, 0.99), (25, 0.75), (100, 0.0)):
            out = kota.claude_coz({"windows": [{"label": "Weekly (all models)", "utilization": kul}]})
            self.assertAlmostEqual(out["hafta"]["kalan"], beklenen, msg=f"utilization={kul}")
        # used_percent ile aynı birim: aynı sayı aynı kalanı verir
        for x in (0.5, 1, 40):
            a = kota.claude_coz({"windows": [{"label": "Current session", "utilization": x}]})
            b = kota.claude_coz({"windows": [{"label": "Current session", "used_percent": x}]})
            self.assertEqual(a["5s"]["kalan"], b["5s"]["kalan"])

    def test_codex_usedpercent_yoksa_pencere_atlanir(self):
        reset = int((S + timedelta(hours=2)).timestamp())
        r = {"rateLimits": {"primary": {"resetsAt": reset, "windowDurationMins": 300},
                            "secondary": {"usedPercent": 60, "resetsAt": reset, "windowDurationMins": 10080}}}
        pen, ek = kota.codex_coz(r)
        self.assertNotIn("5s", pen)                                    # %100 kalan uydurulmaz
        self.assertAlmostEqual(pen["hafta"]["kalan"], 0.40)
        self.assertTrue(any("5s" in n and "bilinmiyor" in n for n in ek["notlar"]), ek["notlar"])
        pen0, ek0 = kota.codex_coz({"rateLimits": {"primary": {"usedPercent": None}}})
        self.assertEqual(pen0, {})
        self.assertEqual(len(ek0["notlar"]), 1)
        pen1, ek1 = kota.codex_coz({"rateLimits": {"primary": {"usedPercent": 0}}})
        self.assertEqual(pen1["5s"]["kalan"], 1.0)                     # açık 0 geçerli: gerçekten %100 kalan
        self.assertEqual(ek1["notlar"], [])

    def test_codex_usedpercent_yoksa_birlesik_okumada_not_ve_bilinmiyor(self):
        bos = kota.codex_coz({"rateLimits": {"primary": {"resetsAt": 1}, "secondary": {"resetsAt": 1}}})
        a = kota.oku(O.veri(), S, adaptor={"codex": lambda: {"pencereler": bos[0], "ek": bos[1]},
                                           "bedava": lambda *x: (None, None)}, onbellek=False)
        h = a["havuzlar"]["codex_plus"]
        self.assertEqual(h["durum"], "bilinmiyor")
        self.assertTrue(all("bilinmiyor" in n for n in h["notlar"]) and len(h["notlar"]) == 2, h["notlar"])
        yarim = kota.codex_coz({"rateLimits": {"primary": {"windowDurationMins": 300},
                                               "secondary": {"usedPercent": 10}}})
        a = kota.oku(O.veri(), S, adaptor={"codex": lambda: {"pencereler": yarim[0], "ek": yarim[1]},
                                           "bedava": lambda *x: (None, None)}, onbellek=False)
        h = a["havuzlar"]["codex_plus"]
        self.assertEqual(h["durum"], "ok")
        self.assertEqual(set(h["pencereler"]), {"hafta"})
        self.assertTrue(any("5s" in n and "bilinmiyor" in n for n in h["notlar"]), h["notlar"])

    def test_bedava_kota_ve_sir_sizmaz(self):
        api = O.veri().api_ayari("bedava")
        self.assertEqual(api["anahtar_env"], "ORNEK_TEST_API_KEY")
        self.assertEqual(api["gun_tavan"], 1000000)
        cagrilar = []

        def get(api_, yol, anahtar):
            cagrilar.append((yol, anahtar == SAHTE_SIR))
            return 200, {}, {"daily_remaining_tokens": 500000, "daily_limit_tokens": 1000000}
        pen, neden = kota.bedava_limits("bedava", api, S, _get=get, _anahtar=lambda: SAHTE_SIR)
        self.assertEqual(cagrilar, [("/quota", True)])
        self.assertAlmostEqual(pen["gun"]["kalan"], 0.5)
        dokum = json.dumps([pen, neden, kota.durum_oku()], default=str)
        self.assertNotIn(SAHTE_SIR, dokum)
        self.assertFalse(kota.taban_guvenli("http://ornek.invalid/v1"))
        self.assertTrue(kota.taban_guvenli("https://ornek.invalid/v1"))
        pen2, neden2 = kota.bedava_limits("bedava2", api, S, _anahtar=lambda: None)
        self.assertIsNone(pen2)
        self.assertIn("anahtar yok", neden2)

    def test_birlesik_oku_ve_onbellek_S20(self):
        v = O.veri()
        ad = {"codex": lambda: {"hafta": {"kalan": 0.7, "sifirlama": S.isoformat()}},
              "bedava": lambda hid, api, simdi: ({"gun": {"kalan": 0.9}}, None)}
        a = kota.oku(v, S, adaptor=ad, claude="5s=80,hafta=60")
        self.assertEqual(a["havuzlar"]["codex_plus"]["durum"], "ok")
        self.assertEqual(a["havuzlar"]["claude_max"]["pencereler"]["hafta"]["kalan"], 0.6)
        self.assertEqual(a["havuzlar"]["agy_gemini"]["durum"], "bilinmiyor")     # izinsiz agy okunmaz
        self.assertEqual(kota.anlik_dogrula(a), [])
        b = kota.oku(v, S + timedelta(minutes=2), adaptor={"codex": lambda: None})
        self.assertTrue(b.get("onbellek"))
        c = kota.oku(v, S + timedelta(minutes=3), taze=True, adaptor={"codex": lambda: None,
                                                                        "bedava": lambda *x: (None, "yok")})
        self.assertFalse(c.get("onbellek"))
        self.assertEqual(c["havuzlar"]["codex_plus"]["durum"], "bilinmiyor")
        with self.assertRaises(SystemExit) as e, redirect_stdout(io.StringIO()):
            kota.main(["--help"])
        self.assertEqual(e.exception.code, 0)

    def test_S24_bitis_sonrasi_havuz_kapali(self):
        simdi = datetime(2030, 1, 1, 0, 1, tzinfo=timezone.utc)
        a = kota.oku(O.veri(), simdi, adaptor={"codex": lambda: None, "bedava": lambda *x: (None, None)},
                     onbellek=False)
        self.assertEqual(a["havuzlar"]["bedava"]["durum"], "kapali")


class ServisVeSoguma(unittest.TestCase):
    def setUp(self):
        _temizle()

    def _yaz(self, ad, a):
        p = Path(durum_dizini()) / ad
        atomik_yaz(p, a)
        return p

    def test_S39_rust_servis_anligi(self):
        taze = {"sema": 1, "yazan": "rust-servis", "zaman": S.isoformat(),
                "havuzlar": {"codex_plus": {"durum": "ok", "pencereler": {"hafta": {"kalan": 0.5}}}}}
        a, n = kota.servis_anligi(self._yaz("s1.json", taze), S + timedelta(minutes=5))
        self.assertIsNotNone(a)
        a, n = kota.servis_anligi(self._yaz("s2.json", dict(taze, zaman=(S - timedelta(minutes=34)).isoformat())), S)
        self.assertIsNone(a)
        self.assertIn("bayat 34 dk", n)
        bozuk = dict(taze, havuzlar={"codex_plus": {"durum": "ok", "pencereler": {"hafta": {"kalan": 7}}}})
        a, n = kota.servis_anligi(self._yaz("s3.json", bozuk), S)
        self.assertIsNone(a)
        self.assertIn("şema", n)
        os.environ["ORKESTRA_KOTA_KAYNAGI"] = str(Path(durum_dizini()) / "s2.json")
        try:
            b = kota.oku(O.veri(), S, adaptor={"codex": lambda: None, "bedava": lambda *x: (None, None)},
                         onbellek=False)
        finally:
            os.environ.pop("ORKESTRA_KOTA_KAYNAGI", None)
        self.assertEqual(b["yazan"], "ork.kota")
        self.assertTrue(any("yedek" in x for x in b["notlar"]))

    # ---- Cetvel otomatik keşfi (ORKESTRA_KOTA_KAYNAGI yokken)
    def _cetvel(self, ad, a, ham=None):
        d = Path(tempfile.mkdtemp(prefix="cetvel-", dir=durum_dizini()))
        if ham is not None:
            (d / ad).write_text(ham, encoding="utf-8")
        else:
            atomik_yaz(d / ad, a)
        return d

    def _oku_kesif(self, d, simdi=S, env_kaynak=None):
        eski = os.environ.get("CETVEL_DIZINI")
        os.environ["CETVEL_DIZINI"] = str(d)
        if env_kaynak:
            os.environ["ORKESTRA_KOTA_KAYNAGI"] = env_kaynak
        try:
            return kota.oku(O.veri(), simdi, adaptor={"codex": lambda: None, "bedava": lambda *x: (None, None)},
                            onbellek=False)
        finally:
            os.environ.pop("ORKESTRA_KOTA_KAYNAGI", None)
            os.environ["CETVEL_DIZINI"] = eski

    def _uyum(self, zaman=None, **ek):
        a = {"sema": 1, "yazan": "rust-servis", "zaman": (zaman or S).isoformat(),
             "havuzlar": {"codex_plus": {"durum": "ok", "kullanilabilir": True,
                                         "pencereler": {"hafta": {"kalan": 0.5}, "5s": {"kalan": 0.9}}}}}
        a.update(ek)
        return a

    def test_cetvel_kesfi_taze_uyum_dosyasi(self):
        d = self._cetvel("orkestra-uyum.json", self._uyum())
        b = self._oku_kesif(d, S + timedelta(minutes=2))
        self.assertEqual(b["yazan"], "rust-servis")
        self.assertAlmostEqual(b["havuzlar"]["codex_plus"]["pencereler"]["hafta"]["kalan"], 0.5)
        self.assertTrue(any("Cetvel (otomatik keşif)" in x for x in b["notlar"]))

    def test_cetvel_kesfi_bayat_kendi_okuyucuya_duser(self):
        d = self._cetvel("orkestra-uyum.json", self._uyum())
        b = self._oku_kesif(d, S + timedelta(minutes=34))
        self.assertEqual(b["yazan"], "ork.kota")
        self.assertTrue(any("bayat 34 dk" in x for x in b["notlar"]), b["notlar"])

    def test_cetvel_kesfi_bozuk_json_kendi_okuyucuya_duser(self):
        d = self._cetvel("orkestra-uyum.json", None, ham="{bozuk")
        b = self._oku_kesif(d)
        self.assertEqual(b["yazan"], "ork.kota")
        self.assertTrue(any("yedek" in x and "bozuk" in x for x in b["notlar"]), b["notlar"])

    def test_cetvel_kesfi_sema_hatasi_kendi_okuyucuya_duser(self):
        bozuk = self._uyum(havuzlar={"codex_plus": {"durum": "ok", "pencereler": {"hafta": {"kalan": 7}}}})
        b = self._oku_kesif(self._cetvel("orkestra-uyum.json", bozuk))
        self.assertEqual(b["yazan"], "ork.kota")
        self.assertTrue(any("şema" in x for x in b["notlar"]), b["notlar"])

    def test_cetvel_kesfi_sozlesme_disi_dosya_elenir(self):
        v2 = {"sema": 2, "yazan": "cetvel", "zaman": S.isoformat(), "havuzlar": {}}
        b = self._oku_kesif(self._cetvel("anlik.json", v2))
        self.assertEqual(b["yazan"], "ork.kota")
        self.assertTrue(any("sözleşmeye uymuyor" in x for x in b["notlar"]), b["notlar"])

    def test_cetvel_yoksa_sessizce_kendi_okuyucu(self):
        b = self._oku_kesif(Path(durum_dizini()) / "olmayan-cetvel")
        self.assertEqual(b["yazan"], "ork.kota")
        self.assertFalse(any("Cetvel" in x or "KOTA KAYNAĞI" in x for x in b["notlar"]), b["notlar"])

    def test_ortam_degiskeni_kesfi_gecer_ve_kapali_servisi_kapatir(self):
        d = self._cetvel("orkestra-uyum.json", self._uyum())
        b = self._oku_kesif(d, env_kaynak="kapali")
        self.assertEqual(b["yazan"], "ork.kota")                      # taze Cetvel dosyası var ama kapatıldı
        yol, kaynak = kota.servis_kaynagi_coz(env={"ORKESTRA_KOTA_KAYNAGI": "x.json", "CETVEL_DIZINI": str(d)})
        self.assertEqual((str(yol), kaynak), ("x.json", "ortam"))
        yol, kaynak = kota.servis_kaynagi_coz(env={"CETVEL_DIZINI": str(d)})
        self.assertEqual((yol.name, kaynak), ("orkestra-uyum.json", "kesif"))
        self.assertEqual(kota.servis_kaynagi_coz("kapali", env={})[1], "kapali")
        self.assertEqual(kota.servis_kaynagi_coz(env={"LOCALAPPDATA": str(d)})[1], None)   # LOCALAPPDATA/Cetvel yok
        self.assertEqual(kota.cetvel_dizini({"LOCALAPPDATA": "X"}).name, "Cetvel")

    def test_serviste_olmayan_havuz_kendi_okuyucuyla_tamamlanir(self):
        d = self._cetvel("orkestra-uyum.json", self._uyum())
        bedava = lambda hid, api, simdi: ({"gun": {"kalan": 0.8, "kaynak": "api_quota"}}, None)   # noqa: E731
        eski = os.environ.get("CETVEL_DIZINI")
        os.environ["CETVEL_DIZINI"] = str(d)
        try:
            b = kota.oku(O.veri(), S + timedelta(minutes=1), adaptor={"codex": lambda: None, "bedava": bedava},
                         onbellek=False)
        finally:
            os.environ["CETVEL_DIZINI"] = eski
        self.assertEqual(b["yazan"], "rust-servis")
        self.assertAlmostEqual(b["havuzlar"]["codex_plus"]["pencereler"]["hafta"]["kalan"], 0.5)   # servisten
        self.assertAlmostEqual(b["havuzlar"]["bedava"]["pencereler"]["gun"]["kalan"], 0.8)          # kendi okuyucu
        self.assertTrue(any("serviste olmayan" in x for x in b["notlar"]), b["notlar"])

    def _cetvel_oku(self, havuzlar, codex=None, bedava=None):
        d = self._cetvel("orkestra-uyum.json", self._uyum(havuzlar=havuzlar))
        eski = os.environ.get("CETVEL_DIZINI")
        os.environ["CETVEL_DIZINI"] = str(d)
        try:
            return kota.oku(O.veri(), S + timedelta(minutes=1),
                            adaptor={"codex": codex or (lambda: None), "bedava": bedava or (lambda *x: (None, None))},
                            onbellek=False)
        finally:
            os.environ["CETVEL_DIZINI"] = eski

    @staticmethod
    def _yeniden_okunanlar(b):
        n = next(x for x in b["notlar"] if "kendi okuyucuyla:" in x)
        return set(n.split("kendi okuyucuyla:", 1)[1].replace(" ", "").split(","))

    def test_cetvelde_okunamayan_havuz_kendi_okuyucuyla_denenir(self):
        """Dosyada bulunan ama durumu ok olmayan (bilinmiyor/hata/kapali) ya da penceresi boş havuz kendi okuyucuyla
        yeniden denenir; kendi okuma başarılıysa servisin kaydı yerine geçer."""
        bedava = lambda hid, api, simdi: ({"gun": {"kalan": 0.8, "kaynak": "api_quota"}}, None)   # noqa: E731
        codex = lambda: {"hafta": {"kalan": 0.3, "sifirlama": None}}                              # noqa: E731
        for durum in ("bilinmiyor", "hata", "kapali"):
            hv = {"codex_plus": {"durum": durum, "pencereler": {}}, "bedava": {"durum": durum, "pencereler": {}},
                  "yerel": {"durum": "ok", "pencereler": {}}}
            b = self._cetvel_oku(hv, codex=codex, bedava=bedava)
            self.assertEqual(b["yazan"], "rust-servis")
            self.assertEqual(b["havuzlar"]["codex_plus"]["durum"], "ok", durum)
            self.assertAlmostEqual(b["havuzlar"]["codex_plus"]["pencereler"]["hafta"]["kalan"], 0.3)
            self.assertAlmostEqual(b["havuzlar"]["bedava"]["pencereler"]["gun"]["kalan"], 0.8)
            self.assertTrue(any(f"servis durumu {durum}" in x for x in b["havuzlar"]["bedava"]["notlar"]))
            yeniden = self._yeniden_okunanlar(b)
            self.assertTrue({"codex_plus", "bedava"} <= yeniden, yeniden)
            self.assertNotIn("yerel", yeniden)                        # yerel havuzda boş pencere doğaldır
            self.assertNotIn("claude_max", yeniden)

    def test_cetvelde_bos_pencereli_ok_havuz_yeniden_denenir(self):
        codex = lambda: {"hafta": {"kalan": 0.25, "sifirlama": None}}                             # noqa: E731
        hv = {"codex_plus": {"durum": "ok", "pencereler": {}}}
        b = self._cetvel_oku(hv, codex=codex)
        self.assertAlmostEqual(b["havuzlar"]["codex_plus"]["pencereler"]["hafta"]["kalan"], 0.25)
        self.assertIn("codex_plus", self._yeniden_okunanlar(b))
        b = self._cetvel_oku(hv)                                      # kendi okuyucu da okuyamazsa: dolu sayılmaz
        self.assertEqual(b["havuzlar"]["codex_plus"]["durum"], "bilinmiyor")

    def test_cetvelde_okunan_havuz_yeniden_okunmaz_hata_korunur(self):
        cagri = []
        codex = lambda: cagri.append(1)                               # noqa: E731
        b = self._cetvel_oku(self._uyum()["havuzlar"], codex=codex)   # codex_plus ok + pencereli: dokunulmaz
        self.assertEqual(cagri, [])
        self.assertAlmostEqual(b["havuzlar"]["codex_plus"]["pencereler"]["hafta"]["kalan"], 0.5)
        hv = {"codex_plus": {"durum": "hata", "pencereler": {}, "notlar": ["servis: bağlantı koptu"]}}
        b = self._cetvel_oku(hv, codex=codex)                         # kendi okuyucu da başarısız: servis kaydı kalır
        self.assertEqual(cagri, [1])
        h = b["havuzlar"]["codex_plus"]
        self.assertEqual(h["durum"], "hata")
        self.assertIn("servis: bağlantı koptu", h["notlar"])
        self.assertTrue(any("codex okunamadı" in x for x in h["notlar"]), h["notlar"])

    def _cetvelli_agy_oku(self, v, durum=None, **kw):
        """Cetvel (yalnız codex) + agy havuzları serviste yok: agy_kovalari çağrılarını sayar."""
        d = self._cetvel("orkestra-uyum.json", self._uyum())
        cagrilar = []

        def sahte(okuma=3, **_):
            cagrilar.append(okuma)
            return {"gemini-weekly": {"kalan": 0.9, "sifirlama": None}, "gemini-5h": {"kalan": 0.9, "sifirlama": None}}
        eski, eski_k = os.environ.get("CETVEL_DIZINI"), kota.agy_kovalari
        os.environ["CETVEL_DIZINI"] = str(d)
        kota.agy_kovalari = sahte
        try:
            if durum:
                atomik_yaz(kota.durum_yolu(), durum)
            b = kota.oku(v, S + timedelta(minutes=1), adaptor={"codex": lambda: None, "bedava": lambda *x: (None, None)},
                         onbellek=False, **kw)
        finally:
            kota.agy_kovalari = eski_k
            os.environ["CETVEL_DIZINI"] = eski
        return b, cagrilar

    def test_cetvel_tamamlamada_agy_tek_okuma_ve_kayitli(self):
        """Serviste olmayan agy havuzları taze=True ile 3 kez okunmaz; okuma kaydı yazılır (saatlik tavan işler)."""
        b, cagrilar = self._cetvelli_agy_oku(O.veri71())
        self.assertEqual(cagrilar, [1])
        self.assertEqual(b["havuzlar"]["agy_gemini"]["durum"], "ok")
        satirlar = [json.loads(x) for x in kota.agy_kayit_yolu().read_text(encoding="utf-8").splitlines()]
        self.assertEqual([x["tur"] for x in satirlar], ["okuma"])
        self.assertTrue(kota.durum_oku().get("agy_okuma_son"))

    def test_cetvel_tamamlamada_agy_saatlik_tavan_isler(self):
        v = O.veri71(lambda d: d["kullanici-kurallari"]["agy_otomatik"].setdefault("guvenceler", {})
                     .update(saatlik_okuma_tavani=2))
        sayilar = [len(self._cetvelli_agy_oku(v)[1]) for _ in range(4)]
        self.assertEqual(sayilar, [1, 1, 0, 0])               # 2 okumadan sonra tavan dolar; agy atlanır

    def test_cetvel_tamamlamada_agy_kuru_yazmaz(self):
        _, cagrilar = self._cetvelli_agy_oku(O.veri71(), yaz=False)
        self.assertEqual(cagrilar, [1])
        self.assertFalse(kota.agy_kayit_yolu().exists())
        self.assertFalse(kota.durum_oku().get("agy_okuma_son"))

    def test_cetvel_tamamlamada_agy_kapanis_nedeni_korunur(self):
        b, cagrilar = self._cetvelli_agy_oku(O.veri71(), durum={"agy_otomatik_kapali": {"neden": "403"}})
        self.assertEqual(cagrilar, [])
        notlar = " ".join(b["havuzlar"]["agy_gemini"]["notlar"])
        self.assertIn("403/askı kapanışı", notlar)
        self.assertNotIn("--agy ile izinli okuma)", notlar.replace("otomatik karar yok; --agy ile izinli okuma)", ""))

    def test_cetvelin_gercek_uyum_ciktisi_kabul_edilir(self):
        """Cetvel'in `oku --yaz` ile ürettiği gerçek orkestra-uyum.json (tests/fixtures) sözleşmeden kaymasın."""
        a = json.loads((O.FIKSTUR / "cetvel-uyum-ornek.json").read_text(encoding="utf-8"))
        self.assertEqual(kota.anlik_dogrula(a), [])
        zaman = kota.zaman_coz(a["zaman"])
        d = self._cetvel("orkestra-uyum.json", a)
        b = self._oku_kesif(d, zaman + timedelta(minutes=1))
        self.assertEqual(b["yazan"], "rust-servis")
        self.assertEqual(b["havuzlar"]["codex_plus"]["pencereler"]["hafta"]["kalan"], 1.0)

    def test_S43_kota_hatasi_yeniden_denenmez_soguma(self):
        s = kota.hata_sinifla("Error: enforced_spend_limit_reached", 429)
        self.assertEqual(s["sinif"], "kota")
        self.assertFalse(s["yeniden_dene"])
        self.assertEqual(kota.hata_sinifla("model not supported", 400)["eylem"], "dur_model_yok")
        self.assertEqual(kota.hata_sinifla("", 503)["sinif"], "kapasite")
        kota.hata_isle("codex_plus", "enforced_spend_limit_reached", 429, kimlik="gpt-6.1-sol", simdi=S)
        sg = kota.soguma_secici_icin(S + timedelta(minutes=1))
        self.assertIn("codex_plus", sg)
        r = secici.sec({"alan": "kod", "alt_alan": "sre", "sinif": "kod"}, O.veri(), O.kota(), {"soguma": sg},
                       S + timedelta(minutes=1))
        self.assertNotEqual((r.get("secim") or {}).get("havuz"), "codex_plus")
        kota.soguma_temizle("codex_plus", S)
        self.assertNotIn("codex_plus", kota.soguma_secici_icin(S + timedelta(minutes=2)))

    def test_durum_birlestir(self):
        kota.durum_birlestir({"tercihli": {"codex_plus": True}, "son_secim": {"a": "x"}})
        kota.durum_birlestir({"tercihli": {"agy_gemini": False}})
        d = kota.durum_oku()
        self.assertEqual(d["tercihli"], {"codex_plus": True, "agy_gemini": False})
        self.assertEqual(d["son_secim"], {"a": "x"})


if __name__ == "__main__":
    unittest.main()
