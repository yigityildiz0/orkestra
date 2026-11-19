"""R16 şef tavanı senaryoları: işçi şefin model x eforunu aşmaz; Q tavanın üstündeyse SOR T6; yalnız açık kullanıcı
isteği kaldırır (uyarıyla). Saf seçici + yardımcı CLI katmanı (algılama, oturum kaydı); ağ ve model yok."""
import json
import os
import tempfile
import unittest
from pathlib import Path

import _ortak as O
from ork import araclar, kota, secici, suru

S = O.SIMDI
KOD = {"alan": "kod", "alt_alan": "gunluk", "sinif": "kod", "veri": "genel"}
ZOR = {"alan": "kod", "alt_alan": "zor_ajan", "sinif": "zor", "veri": "genel",
       "sinyaller": ["geri_alinamaz", "cok_dosya", "test_yok"]}


def sec(istek, sef=None, veri=None, **ek):
    i = dict(istek, **ek)
    if sef:
        i["sef"] = sef
    return secici.sec(i, veri or O.veri71(), O.kota71(), {}, S)


def etiket(r):
    a = r.get("secim") or {}
    return f"{a.get('rol')}@{a.get('efor')} ({a.get('havuz')})" if a else None


def tavan_elenen(r, onek=""):
    return {k: v for k, v in (r.get("elenen") or {}).items() if v.startswith("şef tavanı") and k.startswith(onek)}


class SefCoz(unittest.TestCase):
    def test_rol_efor_ve_takma_ad_bicimleri(self):
        v = O.veri71()
        for x, beklenen in (("opus:high", "opus@high"), ("opus@high", "opus@high"), ("opus[1m]:xhigh", "opus@xhigh"),
                            ("claude-sonnet-5-5:high", "sonnet@high"), ({"rol": "haiku", "efor": "medium"},
                                                                         "haiku@medium")):
            t = secici.sef_coz(x, v)
            self.assertEqual(t["etiket"], beklenen, x)
        self.assertEqual(secici.sef_coz("opus:high", v)["z"], 52)
        self.assertEqual(secici.sef_coz("opus:high", v)["bant"], 2)       # gürültü bandı = delta.aa_z

    def test_efor_yoksa_varsayilan_uyarili(self):
        t = secici.sef_coz("opus", O.veri71())
        self.assertTrue(t["efor_varsayildi"])
        r = sec({"sinif": "basit", "veri": "genel"}, "opus")
        self.assertTrue(any("şef eforu bilinmiyor" in u for u in r["uyarilar"]))

    def test_cozulemeyen_sef_hata(self):
        with self.assertRaises(secici.SecimHatasi):
            secici.sef_coz("yok-boyle-model:high", O.veri71())

    def test_sef_yoksa_davranis_degismez(self):
        self.assertEqual(etiket(sec({"sinif": "kritik", "veri": "genel"})), "opus@xhigh (claude_max)")
        self.assertIsNone(sec({"sinif": "kritik", "veri": "genel"}).get("sef"))


class AyniAile(unittest.TestCase):
    def test_opus_high_ust_efor_yok_kritik_sor(self):
        r = sec({"sinif": "kritik", "veri": "genel"}, "opus:high")
        self.assertEqual(r["durum"], "sor")
        self.assertEqual(r["tetik"], "T6")
        self.assertIn("Q düşürülmez", r["gerekce"])
        kod = [x["kod"] for x in r["secenekler"]]
        self.assertEqual(kod, ["tavan_yok", "sef_yukselt", "bekle"])
        self.assertEqual(r["varsayilan"], "bekle")
        self.assertEqual(r["secenekler"][0]["aday"], "opus@xhigh (claude-agent)")
        self.assertIn("efor xhigh > şef opus@high", tavan_elenen(r, "opus@xhigh")["opus@xhigh|claude"])
        self.assertEqual(secici.CIKIS_KODU[r["durum"]], 4)

    def test_opus_high_kod_tavan_icinde_secer(self):
        r = sec(KOD, "opus:high")
        self.assertEqual(r["durum"], "secildi")
        self.assertEqual(r["sef"]["etiket"], "opus@high")
        for aid in r["E"]:
            ad, _, ef = aid.split("|")[0].partition("@")
            if ad in ("opus", "sonnet"):
                self.assertIn(ef, ("low", "medium", "high"))
        self.assertTrue(tavan_elenen(r, "opus@max"))

    def test_sonnet_high_opus_yok_sonnet_en_cok_high(self):
        r = sec({"sinif": "basit", "veri": "genel"}, "sonnet:high")
        self.assertEqual(r["durum"], "secildi")
        el = tavan_elenen(r)
        self.assertTrue(all("üstünde (aynı aile)" in v for k, v in el.items() if k.startswith("opus@")))
        self.assertIn("opus@low|claude", el)                 # Opus düşük eforda da yok (üst model)
        self.assertIn("efor xhigh > şef sonnet@high", el["sonnet@xhigh|claude"])
        self.assertNotIn("haiku@high|claude", el)           # alt model şef eforuna kadar serbest

    def test_sonnet_high_kod_q_tavan_ustu_sor(self):
        r = sec(KOD, "sonnet:high")
        self.assertEqual((r["durum"], r["tetik"]), ("sor", "T6"))
        self.assertIn("şef sonnet@high (Z 42)", r["soru"])

    def test_haiku_medium_yalniz_z_27_alti(self):
        r = sec({"sinif": "mekanik", "veri": "genel"}, "haiku:medium")
        self.assertEqual(r["durum"], "secildi")
        self.assertLessEqual(r["secim"]["z"], 27)
        el = tavan_elenen(r)
        self.assertIn("sonnet@low|claude", el)
        self.assertIn("efor high > şef haiku@medium", el["haiku@high|claude"])
        self.assertEqual((sec(KOD, "haiku:medium")["durum"]), "sor")

    def test_opus_kapisi_tavanin_altinda(self):
        r = sec(ZOR, "opus:medium")                          # Opus kapısı high ister, şef medium
        self.assertEqual((r["durum"], r["tetik"]), ("sor", "T6"))
        self.assertIn("Opus kapısı", r["soru"])
        self.assertTrue(r["secenekler"][0]["aday"].startswith("opus@"))
        self.assertEqual(etiket(sec(ZOR, "opus:high")), "opus@high (agy_claude_gpt)")


class BaskaAile(unittest.TestCase):
    def test_hydrogen_sefi_bant_ve_alan(self):
        r = sec(KOD, "hydrogen:high")                        # Z 51 + bant 2
        self.assertEqual(etiket(r), "hydrogen@high (agy_gemini)")
        el = tavan_elenen(r)
        self.assertIn("efor xhigh > şef hydrogen@high", el["hydrogen@xhigh|agy"])
        self.assertIn("Z 57 > şef hydrogen@high Z 51 + bant 2", el["opus@xhigh|claude"])
        self.assertNotIn("sol@xhigh|codex", el)              # Z 52 bant içinde: eşit sayılır
        self.assertIn("şef tavanı (alan vals:vibe-code)", el["opus@high|agy"])   # Z 52 bantta ama alanda şefin üstünde

    def test_sol_sefi(self):
        r = sec(KOD, "sol:medium")                           # Z 46 + 2
        self.assertEqual(r["durum"], "secildi")
        self.assertIn("Z 52 > şef sol@medium Z 46", tavan_elenen(r)["opus@high|claude"])
        self.assertIn("efor high > şef sol@medium", tavan_elenen(r)["sol@high|codex"])
        self.assertLessEqual(r["secim"]["z"], 48)

    def test_bedava_api_havuzu_tavanda(self):
        r = sec({"sinif": "mekanik", "veri": "genel"}, "haiku:medium")
        self.assertIn("Z 29 > şef haiku@medium Z 25", tavan_elenen(r)["deepseek_flash@high|bedava"])
        r2 = sec({"sinif": "basit", "veri": "genel"}, "sonnet:high")
        self.assertEqual(etiket(r2), "deepseek_flash@high (bedava)")
        self.assertFalse(tavan_elenen(r2, "deepseek"))

    def test_alan_olcumu_sefi_gecemez(self):
        r = sec({"alan": "kod", "alt_alan": "sre", "sinif": "kod", "veri": "genel"}, "opus:high")
        self.assertIn("şef tavanı (alan vals:srebench)", tavan_elenen(r)["sol@medium|codex"])
        self.assertNotEqual(r["secim"]["aile"], "openai")


class Kaldirma(unittest.TestCase):
    def _uyari(self, r, ne):
        return [u for u in r["uyarilar"] if u.startswith("UYARI şef tavanı aşıldı") and ne in u]

    def test_tavan_yok(self):
        r = sec({"sinif": "kritik", "veri": "genel"}, "opus:high", tavan_yok=True)
        self.assertEqual(etiket(r), "opus@xhigh (claude_max)")
        self.assertTrue(self._uyari(r, "--tavan-yok"))
        self.assertEqual(r["sef"]["kalkti"], "--tavan-yok")

    def test_zorla(self):
        r = sec({"sinif": "kritik", "veri": "genel"}, "sonnet:high", zorla="opus:xhigh")
        self.assertEqual(r["durum"], "secildi")
        self.assertTrue(self._uyari(r, "--zorla"))
        self.assertTrue(any("şef modelinin (sonnet) üstünde" in u for u in r["uyarilar"]))

    def test_ultra_acik_istek(self):
        r = sec({"sinif": "kritik", "veri": "genel"}, "sonnet:high", kip="ultra")
        self.assertEqual(r["durum"], "secildi")
        self.assertTrue(self._uyari(r, "ultra"))

    def test_sor_yaniti_tavan_yok(self):
        r = sec({"sinif": "kritik", "veri": "genel"}, "opus:high", sor_yanit="tavan_yok")
        self.assertEqual(etiket(r), "opus@xhigh (claude_max)")
        self.assertTrue(self._uyari(r, "SOR yanıtı"))

    def test_sabit_kullanici_kurali_uyarili(self):
        r = sec({"alan": "gorsel_uretim", "sinif": "normal"}, "haiku:medium")
        self.assertEqual((r["durum"], r["secim"]["rol"]), ("secildi", "sol"))
        self.assertTrue(self._uyari(r, "sabit kullanıcı kuralı"))

    def test_tavan_icindeki_secimde_uyari_yok(self):
        r = sec(KOD, "opus:high")
        self.assertFalse(self._uyari(r, ""))
        self.assertIsNone(r["sef"]["kalkti"])


class RolPlanSuru(unittest.TestCase):
    def test_hakem_rolu_tavanda(self):
        r = sec({"rol_is": "hakem", "tur": "rol", "sinif": "kod", "alan": "mekanik", "haric_aile": "anthropic"},
                "sonnet:high")
        self.assertEqual(r["durum"], "secildi")
        self.assertLessEqual(r["secim"]["z"], 44)

    def test_dogrulayici_tavanda(self):
        r = sec({"sinif": "basit", "veri": "genel"}, "sonnet:high")
        m = r["dogrulayici"]["model"]
        self.assertTrue(m)
        self.assertLessEqual(m["z"], 44)
        r2 = sec({"sinif": "mekanik", "veri": "genel"}, "haiku:low")
        self.assertLessEqual(r2["secim"]["z"], 21)
        m2 = r2["dogrulayici"]["model"]
        self.assertTrue(m2 is None or m2["z"] <= 21)

    def test_plan_parcalari_tavanda_ve_sor_birlesir(self):
        plan = {"is_id": "t", "sef": "sonnet:high", "parcalar": [
            {"id": "a", "sinif": "basit", "veri": "genel", "brief": "kısa iş"},
            {"id": "b", "alan": "kod", "alt_alan": "gunluk", "sinif": "kod", "veri": "genel", "brief": "kod işi"}]}
        r = secici.plan_sec(plan, O.veri71(), O.kota71(), {}, S)
        d = {p["id"]: p for p in r["parcalar"]}
        self.assertEqual(d["a"]["durum"], "secildi")
        self.assertEqual(d["b"]["durum"], "sor")
        self.assertEqual(r["durum"], "sor")
        self.assertEqual(r["sor"]["parcalar"][0]["tetik"], "T6")
        self.assertEqual(r["suru_plani"]["sef"], "sonnet:high")
        r2 = secici.plan_sec(dict(plan, tavan_yok=True), O.veri71(), O.kota71(), {}, S)
        self.assertEqual({p["id"]: p["durum"] for p in r2["parcalar"]}["b"], "secildi")

    def test_suru_acik_hedef_tavanda(self):
        h_ust = {"yol": "codex-exec", "platform": "codex", "havuz": "codex_plus", "kimlik": "gpt-6.1-sol",
                 "model": "gpt-6.1-sol", "efor": "high"}
        h_alt = dict(h_ust, kimlik="gpt-6.1-terra", model="gpt-6.1-terra", efor="medium")
        k = suru.Kosucu({"is_id": "t", "sef": "sonnet:high", "isler": []}, O.veri71(), durum_yaz=False, olc_yaz=False)
        d = k.hedef_denetle(h_ust)
        self.assertEqual(d[0], "engel")
        self.assertIn("şef tavanı", d[1])
        self.assertIsNone(k._tavan(h_alt, "gpt-6.1-terra"))
        h_efsiz = dict(h_ust, efor=None)                      # efor yoksa en yüksek Z'li varyant (temkinli)
        self.assertTrue(k._tavan(h_efsiz, "gpt-6.1-sol"))
        k2 = suru.Kosucu({"is_id": "t", "sef": "sonnet:high", "tavan_yok": True, "isler": []}, O.veri71(),
                         durum_yaz=False, olc_yaz=False)
        self.assertIsNone(k2._tavan(h_ust, "gpt-6.1-sol"))


class Algilama(unittest.TestCase):
    def setUp(self):
        self._eski = {k: os.environ.get(k) for k in ("ORKESTRA_SEF_AYARLARI",)}
        kota.durum_guncelle(lambda d: d.pop("sef", None))

    def tearDown(self):
        for k, v in self._eski.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        kota.durum_guncelle(lambda d: d.pop("sef", None))

    def _veri(self):
        return O.veri71(lambda d: d["kullanici-kurallari"].setdefault("faz", {}).update(lider_rol="opus"))

    def test_ortam_ve_ayar_dosyasi(self):
        with tempfile.TemporaryDirectory() as t:
            f = Path(t) / "settings.json"
            f.write_text(json.dumps({"model": "sonnet", "effortLevel": "low"}), encoding="utf-8")
            os.environ["ORKESTRA_SEF_AYARLARI"] = str(f)
            m, e, k = araclar.sef_algila(self._veri(), ortam={"CLAUDE_EFFORT": "high"})
            self.assertEqual((m, e), ("sonnet", "high"))          # ortam eforu dosyanın önünde
            self.assertEqual(k, ["CLAUDE_EFFORT", "settings.json"])
            deger, notlar = araclar.sef_belirle(self._veri(), {}, ortam={"CLAUDE_EFFORT": "high"})
            self.assertEqual((deger["rol"], deger["efor"]), ("sonnet", "high"))
            self.assertIn("algılandı", deger["kaynak"])
            self.assertEqual(notlar, [])

    def test_bilinmiyorsa_lider_rol_uyarili(self):
        deger, notlar = araclar.sef_belirle(self._veri(), {}, ortam={})
        self.assertEqual((deger["rol"], deger["efor"]), ("opus", None))
        self.assertTrue(any("faz.lider_rol=opus varsayıldı" in n for n in notlar))
        t = secici.sef_coz(deger, self._veri())
        self.assertTrue(t["efor_varsayildi"])

    def test_acik_sef_oturuma_kaydedilir(self):
        v = self._veri()
        deger, _ = araclar.sef_belirle(v, {}, acik="sonnet:high", ortam={"CLAUDE_EFFORT": "max"})
        self.assertEqual(deger["kaynak"], "--sef")
        d = kota.durum_oku()
        self.assertEqual(d["sef"]["deger"], "claude-sonnet-5-5:high")    # kesin kimlik saklanır
        self.assertEqual((d["sef"]["kimlik"], d["sef"]["rol"]), ("claude-sonnet-5-5", "sonnet"))
        deger2, _ = araclar.sef_belirle(v, d, ortam={"CLAUDE_EFFORT": "max"})
        self.assertEqual((deger2["rol"], deger2["efor"]), ("sonnet", "high"))
        self.assertIn("oturum kaydı", deger2["kaynak"])

    def test_kuru_kaydetmez_ve_gecersiz_hata(self):
        araclar.sef_belirle(self._veri(), {}, acik="haiku:low", kuru=True)
        self.assertNotIn("sef", kota.durum_oku())
        with self.assertRaises(secici.SecimHatasi):
            araclar.sef_belirle(self._veri(), {}, acik="olmayan:high")


class Cli(unittest.TestCase):
    def _cli(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("ork_cli_sef", O.KOK / "scripts" / "ork.py")
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        m._baglam = lambda a: (O.veri71(), O.kota71(), {})
        return m

    def _calistir(self, m, argv):
        import contextlib
        import io
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            kod = m.main(argv)
        return kod, out.getvalue()

    def test_sec_sor_t6_ve_sef_satiri(self):
        m = self._cli()
        kod, cikti = self._calistir(m, ["sec", "--sinif", "kritik", "--veri", "genel", "--sef", "opus:high", "--kuru"])
        self.assertEqual(kod, 4)
        self.assertIn("SOR T6", cikti)
        self.assertIn("ŞEF opus@high · tavan Z 52 + bant 2 · --sef", cikti)
        kod, cikti = self._calistir(m, ["sec", "--sinif", "kritik", "--veri", "genel", "--sef", "opus:high",
                                        "--tavan-yok", "--kuru"])
        self.assertEqual(kod, 0)
        self.assertIn("KALDIRILDI (--tavan-yok)", cikti)
        self.assertIn("UYARI şef tavanı aşıldı", cikti)
        kod, cikti = self._calistir(m, ["sec", "--sinif", "kritik", "--veri", "genel", "--sef", "opus:high",
                                        "--kuru", "--json"])
        self.assertEqual(json.loads(cikti)["sef"]["etiket"], "opus@high")

    def test_sec_plan_sef_parcalara_gider(self):
        m = self._cli()
        with tempfile.TemporaryDirectory() as t:
            f = Path(t, "p.json")
            f.write_text(json.dumps({"is_id": "t", "parcalar": [
                {"id": "a", "alan": "kod", "alt_alan": "gunluk", "sinif": "kod", "veri": "genel"}]}), encoding="utf-8")
            sp = Path(t, "s.json")
            kod, cikti = self._calistir(m, ["sec", "--plan", str(f), "--suru-plani", str(sp), "--sef", "sonnet:high",
                                            "--kuru"])
            self.assertEqual(kod, 4)
            self.assertIn("SOR T6", cikti)
            self.assertEqual(json.loads(sp.read_text(encoding="utf-8"))["sef"]["rol"], "sonnet")

    def test_acik_sef_plan_degerini_ezer_ve_parca_uyarisi_basilir(self):
        m = self._cli()
        with tempfile.TemporaryDirectory() as t:
            f = Path(t, "p.json")
            f.write_text(json.dumps({"is_id": "t", "sef": "opus:max", "parcalar": [
                {"id": "a", "sinif": "basit", "veri": "genel", "tavan_yok": True}]}), encoding="utf-8")
            sp = Path(t, "s.json")
            kod, cikti = self._calistir(m, ["sec", "--plan", str(f), "--suru-plani", str(sp), "--sef", "sonnet:high",
                                            "--kuru"])
            self.assertIn("açık --sef sonnet:high uygulandı", cikti)
            self.assertEqual(json.loads(sp.read_text(encoding="utf-8"))["sef"]["rol"], "sonnet")
            self.assertIn("a: UYARI parça düzeyi tavan_yok yok sayıldı", cikti)


class DenetimBulgulari(unittest.TestCase):
    """v7.1 R16 denetimi: plan/sürü yolunda tavan yalnız kullanıcı isteğiyle kalkar; fail-open yok; algılama kesin."""

    def setUp(self):
        self._eski = {k: os.environ.get(k) for k in ("CLAUDE_CODE_SESSION_ID",)}
        os.environ.pop("CLAUDE_CODE_SESSION_ID", None)
        kota.durum_guncelle(lambda d: d.pop("sef", None))

    def tearDown(self):
        for k, v in self._eski.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        kota.durum_guncelle(lambda d: d.pop("sef", None))

    def _plan(self, *parcalar, **ek):
        return secici.plan_sec(dict({"is_id": "t", "sef": "sonnet:high", "parcalar": list(parcalar)}, **ek),
                               O.veri71(), O.kota71(), {}, S)

    def test_parca_sefi_plan_tavanini_yukseltemez(self):
        r = self._plan({"id": "a", "alan": "kod", "alt_alan": "gunluk", "sinif": "kod", "veri": "genel",
                        "sef": "opus:max"})
        p = r["parcalar"][0]
        self.assertEqual(p["durum"], "sor")                    # sonnet:high tavanı sürer: T6
        self.assertTrue(any("parça şefi (opus:max) plan şefinden gevşek" in u for u in p["uyarilar"]))
        self.assertEqual(p["sef"]["etiket"], "sonnet@high")
        r2 = self._plan({"id": "a", "sinif": "basit", "veri": "genel", "sef": "haiku:medium"})
        self.assertEqual(r2["parcalar"][0]["sef"]["etiket"], "haiku@medium")    # daha sıkı parça şefi geçer

    def test_parca_tavan_yok_ve_zorla_tavani_kaldirmaz(self):
        kod = {"alan": "kod", "alt_alan": "gunluk", "sinif": "kod", "veri": "genel"}
        r = self._plan(dict(kod, id="b", tavan_yok=True), dict(kod, id="c", zorla="opus:xhigh"),
                       dict(kod, id="d", sor_yanit="tavan_yok"))
        d = {p["id"]: p for p in r["parcalar"]}
        self.assertEqual({k: v["durum"] for k, v in d.items()}, {"b": "sor", "c": "sor", "d": "sor"})
        self.assertTrue(any("parça düzeyi tavan_yok yok sayıldı" in u for u in d["b"]["uyarilar"]))
        self.assertTrue(any("sor_yanit=tavan_yok yok sayıldı" in u for u in d["d"]["uyarilar"]))
        r2 = self._plan(dict(kod, id="c", zorla="opus:xhigh"), tavan_yok=True)    # kullanıcı (plan/CLI) kaldırır
        p = r2["parcalar"][0]
        self.assertEqual(p["durum"], "secildi")
        self.assertTrue(any(u.startswith("UYARI şef tavanı aşıldı") for u in p["uyarilar"]))

    def test_suru_oge_tavan_yok_yok_sayilir_plan_duzeyi_uyarili(self):
        h = {"yol": "codex-exec", "platform": "codex", "havuz": "codex_plus", "kimlik": "gpt-6.1-sol",
             "model": "gpt-6.1-sol", "efor": "xhigh", "tavan_yok": True}
        k = suru.Kosucu({"is_id": "t", "sef": "sonnet:high", "isler": []}, O.veri71(), durum_yaz=False, olc_yaz=False)
        self.assertEqual(k.hedef_denetle(h)[0], "engel")
        k2 = suru.Kosucu({"is_id": "t", "sef": "sonnet:high", "tavan_yok": True, "isler": []}, O.veri71(),
                         durum_yaz=False, olc_yaz=False)
        self.assertIsNone(k2._tavan(h, "gpt-6.1-sol"))
        self.assertTrue(any(n.startswith("UYARI şef tavanı aşıldı (--tavan-yok)") for n in k2.notlar))

    def test_suru_tavan_fail_open_degil(self):
        def z_sil(d):
            d["modeller"]["modeller"]["gpt-6.1-terra"]["varyantlar"] = {}
        k = suru.Kosucu({"is_id": "t", "sef": "opus:high", "isler": []}, O.veri71(z_sil), durum_yaz=False,
                        olc_yaz=False)
        bilinmeyen = {"yol": "bedava-api", "platform": "bedava", "havuz": "bedava", "model": "bilinmeyen-dev-model",
                      "kimlik": "bilinmeyen-dev-model", "efor": "high"}
        self.assertIn("kayıtta yok", k._tavan(bilinmeyen, "bilinmeyen-dev-model"))
        zsiz = {"yol": "codex-exec", "platform": "codex", "havuz": "codex_plus", "kimlik": "gpt-6.1-terra",
                "model": "gpt-6.1-terra", "efor": "medium"}
        self.assertIn("Z yok", k._tavan(zsiz, "gpt-6.1-terra"))
        k2 = suru.Kosucu({"is_id": "t", "sef": "olmayan:high", "isler": []}, O.veri71(), durum_yaz=False,
                         olc_yaz=False)
        self.assertEqual(k2.hedef_denetle(zsiz)[0], "engel")       # çözülemeyen şef: plan durur
        self.assertTrue(any(n.startswith("HATA şef tavanı çözülemedi") for n in k2.notlar))

    def test_suru_claude_hedefi_de_tavanda(self):
        plan = {"is_id": "t", "sef": "sonnet:high", "isler": [
            {"id": "x", "brief": "b", "hedef": {"yol": "claude-agent", "platform": "claude", "havuz": "claude_max",
                                                "kimlik": "claude-opus-5-5", "model": "opus", "efor": "xhigh"}}]}
        oz = suru.Kosucu(plan, O.veri71(), kuru=True, durum_yaz=False, olc_yaz=False).calistir()
        x = next(o for o in oz["isler"] if o["id"] == "x")
        self.assertEqual(x["durum"], "engel")
        self.assertIn("şef tavanı", x["ozet"])

    def test_ayni_ailede_bant_yok(self):
        t = secici.sef_coz("sonnet:high", O.veri71())
        m = {"saglayici": t["aile"], "varyantlar": {"high": {"z": t["z"] + 1}, "low": {"z": t["z"] - 5}}}
        self.assertIn("aynı aile", secici.tavan_ihlal(t, "claude-baska-model", None, "low", m))

    def test_yaklasik_sef_uyarili_ve_tarihli_kimlik_kesin(self):
        t = secici.sef_coz("claude-3-opus:high", O.veri71())
        self.assertEqual(t["yaklasik"], "claude-3-opus")
        r = sec({"sinif": "basit", "veri": "genel"}, "claude-3-opus:high")
        self.assertTrue(any("şef modeli kayıtta yok (claude-3-opus)" in u for u in r["uyarilar"]))
        self.assertIsNone(secici.sef_coz("claude-opus-5-5-20261101:high", O.veri71())["yaklasik"])

    def test_efor_verilmeyen_sef_algilanan_eforu_kullanir(self):
        d, notlar = araclar.sef_belirle(O.veri71(), {}, acik="opus", ortam={"CLAUDE_EFFORT": "high"}, kuru=True)
        self.assertEqual((d["kimlik"], d["efor"]), ("claude-opus-5-5", "high"))
        self.assertTrue(any("algılanan efor high" in n for n in notlar))

    def test_oturum_kaydi_taze_dusuk_algilamayla_daralir(self):
        v = O.veri71()
        araclar.sef_belirle(v, {}, acik="opus:high", ortam={})
        d = kota.durum_oku()
        dusuk, notlar = araclar.sef_belirle(v, d, ortam={"ORKESTRA_SEF": "sonnet:medium"})
        self.assertEqual((dusuk["rol"], dusuk["efor"]), ("sonnet", "medium"))
        self.assertTrue(any("taze algılamadan yüksek" in n for n in notlar))
        yuksek, _ = araclar.sef_belirle(v, d, ortam={"ORKESTRA_SEF": "opus:max"})
        self.assertEqual((yuksek["rol"], yuksek["efor"]), ("opus", "high"))      # kayıt sıkıysa kayıt

    def test_oturum_kimligi_yoksa_oturumlu_kayit_gecmez(self):
        v = O.veri71()
        os.environ["CLAUDE_CODE_SESSION_ID"] = "oturum-1"
        araclar.sef_belirle(v, {}, acik="haiku:low", ortam={})
        os.environ.pop("CLAUDE_CODE_SESSION_ID")
        d, _ = araclar.sef_belirle(v, kota.durum_oku(), ortam={})
        self.assertNotIn("oturum kaydı", d["kaynak"])

    def test_kaynak_etiketi_alan_basina(self):
        v = O.veri71(lambda d: d["kullanici-kurallari"].setdefault("faz", {}).update(lider_rol="opus"))
        d, _ = araclar.sef_belirle(v, {}, ortam={"CLAUDE_EFFORT": "high"}, kuru=True)
        self.assertEqual(d["kaynak"], "algılandı: model faz.lider_rol (varsayım) · efor CLAUDE_EFFORT")

    def test_opusplan_yurutme_modeli_ve_host_yedegi(self):
        def takma(d):
            d["siniflar"].setdefault("sef_tavani", {})["model_takma"] = {"opusplan": "sonnet"}
        d, notlar = araclar.sef_belirle(O.veri71(takma), {}, ortam={"ANTHROPIC_MODEL": "opusplan",
                                                                     "CLAUDE_EFFORT": "high"}, kuru=True)
        self.assertEqual((d["rol"], d["efor"]), ("sonnet", "high"))
        d2, n2 = araclar.sef_belirle(O.veri71(), {}, ortam={}, kuru=True)          # faz.lider_rol yok: host yedeği
        self.assertIsNotNone(d2)
        self.assertTrue(any("host platformun üst modeli" in n for n in n2))


if __name__ == "__main__":
    unittest.main()
