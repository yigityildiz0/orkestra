"""Seçici senaryoları (tasarım bölüm 10: S01-S26, S28, S29, S32, S38, S42). Saf fonksiyon; ağ ve model yok."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import _ortak as O
from ork import secici
from ork.veri import VeriHatasi

S = O.SIMDI


def sec(istek, kota=None, durum=None, veri=None, simdi=S):
    return secici.sec(istek, veri or O.veri(), kota if kota is not None else O.kota(), durum or {}, simdi)


def kimlik(r):
    return (r.get("secim") or {}).get("kimlik")


class KaliteVeDegismezler(unittest.TestCase):
    def test_S01_kritik_rezerv_acilir(self):
        r = sec({"sinif": "kritik"}, O.kota(claude=(0.9, 0.40)))
        self.assertEqual(r["durum"], "secildi")
        self.assertEqual((r["secim"]["rol"], r["secim"]["efor"]), ("opus", "xhigh"))
        self.assertTrue(r["secim"]["rezerv_acik"])
        self.assertEqual(r["secim"]["katman"], 3)                       # v7.2: ana havuz seviyesi 3
        self.assertNotEqual(r["dogrulayici"]["model"]["aile"], "anthropic")     # hakem eşiği Q-6

    def test_S02_tum_havuzlar_tabanda_bekle(self):
        r = sec({"sinif": "normal"}, O.kota(claude=(0.9, 0.30), codex=(0.9, 0.20)))   # T33: tetik yok
        self.assertEqual(r["durum"], "bekle")
        self.assertEqual(r["istek"]["Q"], 41)                 # Q düşmez
        self.assertIsNotNone(r["en_erken_cozum"])
        self.assertIn("Q düşürülmez", r["gerekce"])

    def test_S03_yalniz_tahmin_adaylari_zorda_kullanilmaz(self):
        def d(x):
            for m in x["modeller"]["modeller"].values():
                for v in (m.get("varyantlar") or {}).values():
                    v["z_kaynak"] = "tahmin"
        r = sec({"sinif": "zor"}, veri=O.veri(d))
        self.assertEqual(r["durum"], "bekle")
        self.assertTrue(any("tahmin" in v for v in r["elenen"].values()))

    def test_S04_belirsiz_bir_ust(self):
        s = O.veri().siniflar
        self.assertEqual(secici.rubrik(["cok_dosya", "belirsiz_hedef"], s), "normal")
        self.assertEqual(secici.rubrik(["cok_dosya", "belirsiz_hedef"], s, belirsiz=True), "zor")
        self.assertEqual(secici.rubrik(["cok_dosya", "bilinmeyen_sinyal"], s), "normal")   # 1 bilinen + belirsizlik
        self.assertEqual(secici.rubrik(["cok_dosya", "belirsiz_hedef"], s, alan="kod"), "kod")

    def test_S05_rol_kesin_kimlige_cozulur(self):
        r = sec({"sinif": "normal", "zorla": "sol:high"})
        self.assertEqual(r["cagri"]["model"], "gpt-6.1-sol")
        self.assertEqual(r["cagri"]["efor"], "high")
        for sinif in ("mekanik", "basit", "normal", "kod", "zor", "kritik"):
            for alan, alt in (("kod", "gunluk"), ("kod", "sre"), ("genel", None)):
                r = sec({"sinif": sinif, "alan": alan, "alt_alan": alt})
                self.assertNotIn(kimlik(r), ("gpt-6-sol", "gpt-5.6-sol"))
                if r.get("cagri"):
                    self.assertNotIn(r["cagri"]["model"], ("sol", "opus", "sonnet", "haiku", "terra", "luna"))

    def test_S07_katalogda_olmayan_kimlik_sessizce_dusmez(self):
        r = sec({"sinif": "normal", "zorla": "gpt-9-hayali"})
        self.assertEqual(r["durum"], "hata")
        self.assertIn("sessizce", r["gerekce"])
        self.assertIsNone(r["secim"])

    def test_S08_yasak_hat_ve_takma_ad(self):
        v = O.veri()
        for k in ("gpt-6.1-astra", "gpt-6-astra", "claude-fable-5-3", "claude-fable-5-2", "fable"):
            self.assertTrue(v.yasak_mi(k)[0], k)
        self.assertFalse(v.yasak_mi("gpt-6.1-sol")[0])
        self.assertFalse(v.yasak_mi("claude-opus-5-5")[0])
        for sinif in ("normal", "zor", "kritik"):
            r = sec({"sinif": sinif})
            self.assertNotIn((r.get("secim") or {}).get("hat"), ("fable", "astra"))
        r = sec({"sinif": "kritik", "zorla": "claude-fable-5-2"})
        self.assertEqual(r["durum"], "hata")
        self.assertIn("yasak", r["gerekce"])

    def test_S09_yeni_hat_onay_bekliyor(self):
        r = sec({"sinif": "kritik"})
        self.assertNotEqual(kimlik(r), "claude-mythos-5-2")
        self.assertTrue(any("onay_bekliyor" in v for k, v in r["elenen"].items() if k.startswith("mythos")))
        r = sec({"sinif": "kritik", "zorla": "mythos"})
        self.assertEqual(r["durum"], "hata")

    def test_S38_olcek_karisik_reddedilir(self):
        def d(x):
            x["siniflar"]["z_olcek"] = "BASKA-OLCEK"
        with self.assertRaises(VeriHatasi):
            sec({"sinif": "normal"}, veri=O.veri(d))


class Kapasite(unittest.TestCase):
    IS = {"alan": "kod", "alt_alan": "gunluk", "sinif": "normal"}

    def test_S10_yuzde_degil_pay_ve_kova(self):
        a = sec(self.IS, O.kota(claude=(0.9, 0.51), codex=(0.9, 0.50)))
        b = sec(self.IS, O.kota(claude=(0.9, 0.50), codex=(0.9, 0.51)))
        self.assertEqual(a["secim"]["havuz"], b["secim"]["havuz"])

    def test_S11_ardisik_okuma_platform_degismez(self):
        durum = {}
        havuzlar = []
        for i, k in enumerate((0.50, 0.51, 0.50)):
            simdi = S + timedelta(minutes=5 * i)
            r = sec(self.IS, O.kota(simdi=simdi, claude=(0.9, 0.7), codex=(0.9, k)), durum, simdi=simdi)
            for anahtar, deger in r["durum_guncel"].items():
                durum.setdefault(anahtar, {}).update(deger)
            havuzlar.append(r["secim"]["havuz"])
        self.assertEqual(len(set(havuzlar)), 1, havuzlar)

    def test_S12_okunamayan_havuz_belirsiz_2x(self):
        v = O.veri()
        i = secici.istek_hazirla(dict(self.IS), v)
        a, _ = secici.adaylari_uret(i, v, {}, S)
        sol = next(x for x in a if x["kimlik"] == "gpt-6.1-sol" and x["efor"] == "medium")
        oku = secici.kapasite(dict(sol), i, v, O.kota(codex=(0.9, 0.5)), {}, S, None, {})
        bil = secici.kapasite(dict(sol), i, v, O.kota(codex_durum="bilinmiyor"), {}, S, None, {})
        self.assertTrue(bil["belirsiz"])
        self.assertAlmostEqual(bil["c"], 2 * oku["c"])
        r = sec(self.IS, O.kota(claude=(0.9, 0.5), codex_durum="bilinmiyor"))
        self.assertEqual(r["secim"]["havuz"], "claude_max")

    def test_S13_codex_tempo_altinda_once(self):
        r = sec(self.IS, O.kota(claude=(0.9, 0.72), codex=(0.9, 0.65)))
        self.assertEqual(r["secim"]["havuz"], "codex_plus")
        self.assertEqual(r["secim"]["katman"], 1)
        self.assertAlmostEqual(r["faz"]["u_C"], 0.571, places=2)    # kova: 0.72 -> 0.70

    def test_S14_codex_tempo_ustunde_yine_once(self):
        # v7.2 (R3): taban üstündeki dış havuz GERİDE olsa da eşit kalitede Claude'dan önce (seviye 2 < 3)
        r = sec(self.IS, O.kota(claude=(0.9, 0.72), codex=(0.9, 0.45)))
        self.assertEqual(r["secim"]["havuz"], "codex_plus")
        self.assertEqual(r["secim"]["katman"], 2)

    def test_S15_claude_son_ceyrek_korunur(self):
        # Claude son çeyrekte: ρ_C,h = 0 -> Codex göreli tempoda ÖNDE (v7.1: seviye 1; eskiden 3)
        r = sec(self.IS, O.kota(claude=(0.9, 0.44), codex=(0.9, 0.45)))
        self.assertEqual(r["secim"]["havuz"], "codex_plus")
        self.assertEqual(r["secim"]["katman"], 1)
        self.assertLessEqual(r["secim"]["pay"], 0.45 - 0.20)      # Codex tabanı delinmez

    def test_S16_olu_bant(self):
        # göreli tempo ölü bandı: giriş (1+b)·ρ_C, çıkış (1-b)·ρ_C; eski `tercihli` durumu okunur (göç)
        b, rc = 0.10, 1.0
        self.assertTrue(secici._onde({"onde": {"codex_plus": True}}, "codex_plus", 0.95, rc, b, {}))
        self.assertFalse(secici._onde({"onde": {"codex_plus": False}}, "codex_plus", 1.05, rc, b, {}))
        self.assertFalse(secici._onde({}, "codex_plus", 1.05, rc, b, {}))
        self.assertTrue(secici._onde({}, "codex_plus", 1.11, rc, b, {}))
        self.assertFalse(secici._onde({"onde": {"codex_plus": True}}, "codex_plus", 0.89, rc, b, {}))
        self.assertTrue(secici._onde({"tercihli": {"codex_plus": True}}, "codex_plus", 0.95, rc, b, {}))
        d = {}
        secici._onde({}, "codex_plus", 2.0, rc, b, d)
        self.assertEqual(d, {"onde": {"codex_plus": True}})

    def test_S17_claude_ustunse_kacilmaz(self):
        r = sec({"alan": "yazim", "alt_alan": "rapor", "sinif": "normal"}, O.kota(claude=(0.9, 0.44), codex=(0.9, 0.9)))
        self.assertEqual(r["secim"]["aile"], "anthropic")
        self.assertEqual(r["ust"], "anthropic")
        self.assertTrue(r["secim"]["rezerv_acik"])

    def test_S18_sol_ustunse_secilir(self):
        r = sec({"alan": "kod", "alt_alan": "sre", "sinif": "kod"}, O.kota(claude=(0.9, 0.30), codex=(0.9, 0.45)))
        self.assertEqual(r["secim"]["rol"], "sol")

    def test_S19_kanit_birikimi_biraz_daha_iyi(self):
        r = sec({"alan": "kod", "alt_alan": "terminal", "sinif": "kod"}, O.kota(claude=(0.9, 0.9), codex=(0.9, 0.9)))
        self.assertEqual(r["secim"]["aile"], "anthropic")
        self.assertTrue(any("kanıt birikimi" in v for v in r["elenen"].values()))

    def test_S21_lider_payi(self):
        # açılış 150 dk > 45 dk: SOR (Claude üstün, lider payı engeli); ≤ 45 dk: BEKLE
        r = sec({"alan": "yazim", "alt_alan": "rapor", "sinif": "normal"}, O.kota(claude=(0.22, 0.9), codex=(0.9, 0.9)))
        self.assertEqual(r["durum"], "sor")
        self.assertTrue(any("lider payı" in v for v in r["elenen"].values()))
        r2 = sec({"alan": "yazim", "alt_alan": "rapor", "sinif": "normal"},
                 O.kota(claude=(0.22, 0.9), codex=(0.9, 0.9), t5_dk=30))
        self.assertEqual(r2["durum"], "bekle")

    def test_S22_pencere_siniri_iki_pay(self):
        v = O.veri()
        i = secici.istek_hazirla(dict(self.IS, sure_dk=40), v)
        a, _ = secici.adaylari_uret(i, v, {}, S)
        sol = next(x for x in a if x["kimlik"] == "gpt-6.1-sol" and x["efor"] == "medium")
        kp = secici.kapasite(dict(sol), i, v, O.kota(codex=(0.9, 0.9), t5_dk=20), {}, S, None, {})
        self.assertTrue(kp["uygun"])
        self.assertTrue(any("iki pencere" in n for n in kp["notlar"]))

    def test_S23_bilinmeyen_veri_dis_ve_kamu_havuz_yok(self):
        r = sec({"sinif": "basit"})
        self.assertNotIn(r["secim"]["havuz"], ("bedava", "agy_gemini"))
        el = " ".join(r["elenen"].values())
        self.assertIn("kamu havuzu", el)
        self.assertIn("dış havuz", el)
        r2 = sec({"sinif": "basit", "veri": "genel"})
        self.assertEqual(r2["secim"]["havuz"], "bedava")              # bedava + genel veri: katman 0

    def test_S24_bedava_bitis_sonrasi_kapali(self):
        simdi = datetime(2030, 1, 1, 0, 1, tzinfo=timezone.utc)       # 03.01 TSİ (fikstür bitişi)
        r = sec({"sinif": "basit", "veri": "genel"}, O.kota(simdi=simdi), simdi=simdi)
        self.assertNotEqual(r["secim"]["havuz"], "bedava")
        self.assertTrue(any("kapandı" in v for v in r["elenen"].values()))

    def test_S42_mekanik_haiku_ve_luna(self):
        v = O.veri()
        i = secici.istek_hazirla({"alan": "mekanik", "alt_alan": "toplu", "sinif": "mekanik"}, v)
        a, _ = secici.adaylari_uret(i, v, {}, S)
        roller = {x["rol"] for x in a}
        self.assertIn("haiku", roller)
        self.assertIn("luna", roller)
        self.assertFalse(any(x["rol"] == "haiku" and x["efor"] == "low" for x in a))   # _genel taban medium
        i2 = secici.istek_hazirla({"alan": "mekanik", "alt_alan": "toplu", "sinif": "mekanik", "olgu": True}, v)
        a2, el = secici.adaylari_uret(i2, v, {}, S)
        self.assertNotIn("luna", {x["rol"] for x in a2})


class SabitKuralRotaProje(unittest.TestCase):
    def test_S25_gorsel_uretim_sol_high(self):
        r = sec({"alan": "gorsel_uretim", "alt_alan": "t2i", "sinif": "normal"})
        self.assertEqual(r["durum"], "secildi")
        self.assertEqual(r["cagri"]["model"], "gpt-6.1-sol")
        self.assertEqual(r["cagri"]["efor"], "high")
        self.assertEqual(r["cagri"]["arac"], "image_gen")
        self.assertEqual(r["cagri"]["parametreler"]["quality"], "high")
        self.assertIn("size", r["cagri"]["parametreler"])

    def test_S26_gorsel_codex_tabanda_elle(self):
        r = sec({"alan": "gorsel", "sinif": "normal"}, O.kota(codex=(0.9, 0.20)))
        self.assertEqual(r["durum"], "elle")
        self.assertIsNone(r["secim"])
        self.assertTrue(any("gemini" in s for s in r["elle_secenekler"]))
        self.assertIn("başka modele düşülmedi", r["gerekce"])

    def test_S28_video_analizi_otomatik_on_isleme(self):
        r = sec({"alan": "video_analiz", "alt_alan": "konusmali", "sinif": "normal"})
        self.assertIn("ffmpeg", r["on_isleme"])
        # ön işleme sonrası normal seçim: rota rolü (opus) yalnız ipucu; eşit kalitede Claude dışı önce (R3)
        self.assertNotEqual(r["secim"]["havuz"], "claude_max")
        self.assertTrue(any("agy-elle" in s for s in r["elle_secenekler"]))

    def test_S28b_video_genel_veride_elle_oneri_ve_otomatik(self):
        r = sec({"alan": "video_analiz", "alt_alan": "konusmali", "sinif": "normal", "veri": "genel"})
        self.assertNotEqual(r["secim"]["havuz"], "claude_max")
        self.assertEqual((r.get("elle_oneri") or {}).get("rol"), "hydrogen")
        self.assertEqual(r["cagri_elle"]["model"], "gemini-4-hydrogen-high")

    def test_elle_lider_ve_otomatik_alternatif(self):
        r = sec({"alan": "arastirma", "alt_alan": "finans_hukuk", "sinif": "normal", "veri": "genel"})
        self.assertEqual(r["durum"], "secildi")
        self.assertEqual(r["elle_oneri"]["rol"], "hydrogen")
        self.assertEqual(r["secim"]["aile"], "anthropic")              # en iyi otomatik alternatif
        self.assertIn("ELLE ÖNERİ", r["gerekce"])
        r2 = sec({"alan": "arastirma", "alt_alan": "finans_hukuk", "sinif": "normal"})   # veri bilinmiyor: agy yok
        self.assertIsNone(r2.get("elle_oneri"))

    def test_S29_proje_zorunlu_efor_yoksa_en_ucuz_uygun(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, ".orkestra.json").write_text(json.dumps({"zorunlu": {"gorsel": "terra"}}), encoding="utf-8")
            r = sec({"alan": "gorsel", "sinif": "normal", "dizin": d})
        self.assertEqual(r["secim"]["rol"], "terra")
        self.assertEqual(r["secim"]["efor"], "high")                 # Q41'i karşılayan en ucuz (low değil)
        self.assertTrue(any("çelişki" in u for u in r["uyarilar"]))

    def test_proje_kurali_bozuksa_hata(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, ".orkestra.json").write_text("{bozuk", encoding="utf-8")
            with self.assertRaises(secici.SecimHatasi):
                sec({"sinif": "normal", "dizin": d})

    def test_rota_ses_dokum_yerel(self):
        r = sec({"alan": "ses", "alt_alan": "dokum", "sinif": "basit"})
        self.assertEqual(r["durum"], "rota")
        self.assertEqual(r["rota"]["arac"], "faster-whisper-large-v3")

    def test_deterministik_on_gecit(self):
        r = sec({"alan": "mekanik", "alt_alan": "toplu", "sinif": "mekanik", "deterministik": True})
        self.assertEqual(r["durum"], "rota")
        self.assertIsNone(r["secim"])

    def test_S32_dogrulayici_farkli_aile(self):
        r = sec({"alan": "kod", "alt_alan": "sre", "sinif": "kod"}, O.kota(claude=(0.9, 0.9), codex=(0.9, 0.9)))
        self.assertEqual(r["secim"]["aile"], "openai")
        dm = r["dogrulayici"]["model"]
        self.assertIsNotNone(dm)
        self.assertNotEqual(dm["aile"], "openai")

    def test_kapanis_yakin_secilemez(self):
        v = O.veri()
        i = secici.istek_hazirla({"sinif": "mekanik", "veri": "genel"}, v)
        a, el = secici.adaylari_uret(i, v, {}, S)
        self.assertNotIn("gpt-oss-120b", {x["kimlik"] for x in a})
        self.assertTrue(any("kapanış" in x for k, x in el.items() if k.startswith("gpt-oss")))

    def test_gerekce_satiri_ve_determinizm(self):
        a = sec({"alan": "kod", "alt_alan": "gunluk", "sinif": "normal"})
        b = sec({"alan": "kod", "alt_alan": "gunluk", "sinif": "normal"})
        self.assertEqual(a["gerekce"], b["gerekce"])
        self.assertTrue(a["gerekce"].startswith("SEÇİM "))
        self.assertIn("Q41→K3", a["gerekce"])
        self.assertIn("olc", a["cagri"])

    def test_soguma_eler(self):
        durum = {"soguma": {"codex_plus": {"tur": "kota", "busy_until": (S + timedelta(hours=1)).isoformat()}}}
        r = sec({"alan": "kod", "alt_alan": "sre", "sinif": "kod"}, O.kota(), durum)
        self.assertNotEqual(r["secim"]["havuz"], "codex_plus")
        self.assertTrue(any("soğumada" in v for v in r["elenen"].values()))

    def test_neden(self):
        satirlar, _ = secici.neden("luna", "normal", O.veri(), O.kota(), {}, S)
        self.assertTrue(any("Z<Q" in s for s in satirlar))

    def test_haftalik_sifir_5s_yuz_dis_havuz_secilmez(self):
        k_v71 = O.kota71(claude=(0.9, 0.9), codex=(1.0, 0.0), agy_gemini=(1.0, 0.0),
                         agy_claude_gpt=(1.0, 0.0), agy_argon=0.0, bedava=0.0)
        # gunluk + veri=genel: kalite kümesi ve gizlilikten geçip kapasite denetiminde "hafta sığmıyor" ile elenir
        r = sec({"alan": "kod", "alt_alan": "gunluk", "sinif": "normal", "veri": "genel"}, k_v71, veri=O.veri71())
        self.assertEqual(r["durum"], "secildi")
        self.assertEqual(r["secim"]["havuz"], "claude_max")
        self.assertTrue(any("|codex" in ad and "hafta sığmıyor" in nd for ad, nd in r["elenen"].items()))
        self.assertTrue(any("|agy" in ad and "hafta sığmıyor" in nd for ad, nd in r["elenen"].items()))


if __name__ == "__main__":
    unittest.main()
