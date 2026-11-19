"""R17 sürekli yeniden değerlendirme ve gizlilik testleri. Ağ/gerçek model yok; sahte taşıyıcı ve saat."""
import json
import os
import unittest
from pathlib import Path

import _ortak as O
from ork import araclar, suru
from ork.veri import durum_dizini

SAHTE_ANAHTAR = "sentetik-anahtar-r17"


class SahteSaat:
    def __init__(self):
        self.t = 0.0

    def simdi(self):
        return self.t

    def uyu(self, sn):
        self.t += max(float(sn), 0.0)


class SahteTasiyici:
    def __init__(self, http_fn=None, surec_fn=None):
        self.http_fn = http_fn
        self.surec_fn = surec_fn
        self.istekler = []
        self.surecler = []

    def http(self, url, govde, basliklar, zaman_asimi):
        self.istekler.append(dict(govde))
        if self.http_fn:
            kod, icerik = self.http_fn(govde, len(self.istekler))
        else:
            kod, icerik = 200, "tamam"
        if kod == 200:
            return 200, {}, {"choices": [{"message": {"content": icerik}}],
                             "usage": {"prompt_tokens": 120, "completion_tokens": 30}}
        return kod, {}, {"error": icerik}

    def surec(self, argv, stdin, zaman_asimi, cwd=None, env=None):
        self.surecler.append(list(argv))
        if self.surec_fn:
            return self.surec_fn(list(argv), stdin)
        if "-o" in argv:
            yol = Path(argv[argv.index("-o") + 1])
            yol.parent.mkdir(parents=True, exist_ok=True)
            yol.write_text("tamam", encoding="utf-8")
            return 0, json.dumps({"usage": {"input_tokens": 80, "output_tokens": 20}}), ""
        return 0, json.dumps({"status": "SUCCESS", "response": "tamam",
                               "usage": {"input_tokens": 80, "output_tokens": 20}}), ""


def _veri_r17(ozel_bedava=False):
    def d(x):
        p = x["platformlar"]["platformlar"]
        p["codex"]["cagri"]["argv"] = ["{ikili}", "exec", "-m", "{kimlik}", "-c",
                                       "model_reasoning_effort={efor}", "-o", "{cikti}"]
        p["agy"]["gizlilik"] = "ozel"
        for hid in ("agy_gemini", "agy_claude_gpt", "agy_argon"):
            x["platformlar"]["havuzlar"][hid]["gizlilik"] = "ozel"
        p["agy"]["cagri"]["argv_oto"] = ["{ikili}", "-p", "{istem}", "--model", "{taban}",
                                         "--effort", "{efor}", "--mode", "{kip}",
                                         "--output-format", "json", "--print-timeout", "{sure}"]
        x["kullanici-kurallari"]["agy_otomatik"]["karar"] = {"teyit_edildi": True}
        x["kullanici-kurallari"]["agy_otomatik"]["isci_profili"] = {"dogrulandi": True, "kisisel_baglam_kabul": True}
        x["kullanici-kurallari"]["agy_otomatik"]["guvenceler"]["baslatma_araligi_sn"] = 0
        p["bedava"]["suru"] = {
            "hesap_eszamanli_kullan": 8,
            "model_eszamanli": {"deepseek-v4.1-flash": 4, "qwen3.8-flash-next": 4, "_arac": 4},
            "kardes": {},
            "yeniden_dene": {"503": {"geri_cekilme_sn": [1, 1], "en_cok": 5}},
            "ardisik_503_kardese": 10,
        }
        if ozel_bedava:
            p["bedava"]["gizlilik"] = "ozel"
            x["platformlar"]["havuzlar"]["bedava"]["gizlilik"] = "ozel"
            x["kullanici-kurallari"]["bedava_istisna"] = [
                {"platform": "bedava", "havuz": "bedava", "veri": "kisisel", "gizlilik": "ozel"}
            ]
    return O.veri71(d)


def _temizle_durum():
    for f in ("olc.jsonl", "agy-cagri.jsonl", "durum.json"):
        try:
            (durum_dizini() / f).unlink()
        except OSError:
            pass


def _kos(isler, tas, veri=None, **kw):
    plan = dict({"is_id": kw.pop("is_id", "r17-test"), "isler": isler}, **kw.pop("plan_ek", {}))
    ks = suru.Kosucu(plan, veri or _veri_r17(), tasiyici=tas, saat=SahteSaat(),
                     olc_yaz=kw.pop("olc_yaz", True), durum_yaz=False, dalga_boyutu=1, **kw)
    ks._ikili = lambda pid: "araci.exe"
    return ks


class R17YenidenDegerlendirmeTestleri(unittest.TestCase):
    def setUp(self):
        os.environ["ORNEK_TEST_API_KEY"] = SAHTE_ANAHTAR
        _temizle_durum()

    def test_dalga_arasi_bos_yanit_ust_efor_ve_olc(self):
        cagir_n = {"n": 0}

        def surec_fn(argv, stdin):
            cagir_n["n"] += 1
            if cagir_n["n"] == 1:
                return 0, json.dumps({"status": "SUCCESS", "response": "   ",
                                      "usage": {"input_tokens": 50, "output_tokens": 1}}), ""
            return 0, json.dumps({"status": "SUCCESS", "response": "çözüldü",
                                  "usage": {"input_tokens": 80, "output_tokens": 30}}), ""

        tas = SahteTasiyici(surec_fn=surec_fn)
        isler = [
            {"id": "w1", "brief": "Birinci basit görev", "veri": "genel", "sinif": "basit", "alan": "genel",
             "hedef": {"yol": "agy-oto", "platform": "agy", "havuz": "agy_gemini",
                       "model": "gemini-4-hydrogen", "kimlik": "gemini-4-hydrogen", "efor": "medium"}},
            {"id": "w2", "brief": "İkinci basit görev", "veri": "genel", "sinif": "basit", "alan": "genel",
             "hedef": {"yol": "agy-oto", "platform": "agy", "havuz": "agy_gemini",
                       "model": "gemini-4-hydrogen", "kimlik": "gemini-4-hydrogen", "efor": "medium"}},
        ]
        k = O.kota71(agy_gemini=(0.9, 0.9), codex=(0.9, 0.9), bedava=0.9)
        oz = _kos(isler, tas, kota_anlik=k).calistir()
        w2 = next(x for x in oz["isler"] if x["id"] == "w2")
        self.assertEqual(w2["durum"], "ok")
        self.assertEqual(w2["model"], "gemini-4-hydrogen@high")
        self.assertIn("high", tas.surecler[-1])
        olc = [r for r in araclar.olc_oku() if r.get("parca_id") == "w2"]
        self.assertTrue(olc)
        self.assertTrue(olc[-1]["yukseltme"]["var"])
        self.assertIn("boş yanıt", olc[-1]["yukseltme"]["neden"])
        self.assertIn("üst efor", olc[-1]["yukseltme"]["neden"])

    def test_yuksek_yeniden_deneme_sonrasi_ust_modele_cikar(self):
        cagir_n = {"n": 0}

        def http_fn(govde, _):
            cagir_n["n"] += 1
            if cagir_n["n"] <= 2:
                return 503, "yoğun"
            return 200, "nihayet tamam"

        tas = SahteTasiyici(http_fn=http_fn)
        isler = [
            {"id": "p1", "brief": "Genel kolay iş 1", "veri": "genel", "sinif": "basit", "alan": "genel",
             "hedef": {"yol": "bedava-api", "platform": "bedava", "havuz": "bedava",
                       "model": "deepseek-v4.1-flash", "kimlik": "deepseek-v4.1-flash", "efor": "high"}},
            {"id": "p2", "brief": "Genel kolay iş 2", "veri": "genel", "sinif": "basit", "alan": "genel",
             "hedef": {"yol": "bedava-api", "platform": "bedava", "havuz": "bedava",
                       "model": "deepseek-v4.1-flash", "kimlik": "deepseek-v4.1-flash", "efor": "high"}},
        ]
        k = O.kota71(agy_gemini=(0.9, 0.9), codex=(0.9, 0.9), bedava=0.9)
        oz = _kos(isler, tas, kota_anlik=k).calistir()
        p2 = next(x for x in oz["isler"] if x["id"] == "p2")
        self.assertEqual(p2["durum"], "ok")
        self.assertNotEqual(p2["havuz"], "bedava")
        olc = [r for r in araclar.olc_oku() if r.get("parca_id") == "p2"]
        self.assertTrue(olc)
        self.assertTrue(olc[-1]["yukseltme"]["var"])
        self.assertIn("yüksek yeniden deneme", olc[-1]["yukseltme"]["neden"])
        self.assertIn("üst model", olc[-1]["yukseltme"]["neden"])

    def test_havuz_tabana_yaklasinca_esdeger_havuza_gecer(self):
        tas = SahteTasiyici()
        anliklar = [
            O.kota71(agy_gemini=(0.9, 0.9), codex=(0.9, 0.9), agy_claude_gpt=(0.9, 0.9), agy_argon=0.9, bedava=0.0),
            O.kota71(agy_gemini=(0.9, 0.05), codex=(0.9, 0.9), agy_claude_gpt=(0.02, 0.02), agy_argon=0.02,
                     bedava=0.0),
        ]
        # İlk dalga kota_anlik=anliklar[0] ile çalışır; dalgalar arası kota_okuyucu taze anlığı (anliklar[1]) döner.
        say = {"i": 1}

        def okuyucu(_v):
            idx = min(say["i"], len(anliklar) - 1)
            say["i"] += 1
            return anliklar[idx]

        isler = [
            {"id": "k1", "brief": "Kod parça 1", "veri": "genel", "sinif": "kod", "alan": "kod",
             "hedef": {"yol": "agy-oto", "platform": "agy", "havuz": "agy_gemini",
                       "model": "gemini-4-hydrogen", "kimlik": "gemini-4-hydrogen", "efor": "high"}},
            {"id": "k2", "brief": "Kod parça 2", "veri": "genel", "sinif": "kod", "alan": "kod",
             "hedef": {"yol": "agy-oto", "platform": "agy", "havuz": "agy_gemini",
                       "model": "gemini-4-hydrogen", "kimlik": "gemini-4-hydrogen", "efor": "high"}},
        ]
        oz = _kos(isler, tas, kota_anlik=anliklar[0], kota_okuyucu=okuyucu).calistir()
        k2 = next(x for x in oz["isler"] if x["id"] == "k2")
        self.assertEqual(k2["durum"], "ok")
        self.assertEqual(k2["havuz"], "codex_plus")
        olc = [r for r in araclar.olc_oku() if r.get("parca_id") == "k2"]
        self.assertTrue(olc)
        self.assertIn("tabana yaklaştı", olc[-1]["yukseltme"]["neden"])
        self.assertIn("codex_plus", olc[-1]["yukseltme"]["neden"])

    def test_histerezis_ardisik_tersine_donusu_ve_gurultuyu_engeller(self):
        # 1) Ardışık iki dalgada tersine havuz dönüşü engellenir (agy_gemini -> codex_plus -> agy_gemini YOK)
        tas = SahteTasiyici()
        anliklar = [
            O.kota71(agy_gemini=(0.9, 0.9), codex=(0.9, 0.9), agy_claude_gpt=(0.02, 0.02), agy_argon=0.02, bedava=0.0),
            O.kota71(agy_gemini=(0.9, 0.03), codex=(0.9, 0.9), agy_claude_gpt=(0.02, 0.02), agy_argon=0.02, bedava=0.0),
            O.kota71(agy_gemini=(1.0, 1.0), codex=(0.9, 0.25), agy_claude_gpt=(0.02, 0.02), agy_argon=0.02, bedava=0.0),
        ]
        idx = {"i": 0}

        def okuyucu(_v):
            k = anliklar[min(idx["i"], len(anliklar) - 1)]
            idx["i"] += 1
            return k

        isler = [
            {"id": "h1", "brief": "Parça 1", "veri": "genel", "sinif": "kod", "alan": "kod",
             "hedef": {"yol": "agy-oto", "platform": "agy", "havuz": "agy_gemini",
                       "model": "gemini-4-hydrogen", "kimlik": "gemini-4-hydrogen", "efor": "high"}},
            {"id": "h2", "brief": "Parça 2", "veri": "genel", "sinif": "kod", "alan": "kod",
             "hedef": {"yol": "agy-oto", "platform": "agy", "havuz": "agy_gemini",
                       "model": "gemini-4-hydrogen", "kimlik": "gemini-4-hydrogen", "efor": "high"}},
            {"id": "h3", "brief": "Parça 3", "veri": "genel", "sinif": "kod", "alan": "kod",
             "hedef": {"yol": "agy-oto", "platform": "agy", "havuz": "agy_gemini",
                       "model": "gemini-4-hydrogen", "kimlik": "gemini-4-hydrogen", "efor": "high"}},
        ]
        ks = _kos(isler, tas, kota_anlik=anliklar[0], kota_okuyucu=okuyucu)
        oz = ks.calistir()
        h3 = next(x for x in oz["isler"] if x["id"] == "h3")
        self.assertEqual(h3["durum"], "ok")
        self.assertEqual(h3["havuz"], "codex_plus")
        self.assertEqual(len(ks.r17_gecmis["h3"]), 1)

        # 2) Anlamsız küçük boşluk farkında (alt_b - cur_b < esitlik_bandi) geçiş olmaz
        an_gurultu = O.kota71(agy_gemini=(0.9, 0.08), codex=(0.9, 0.29),
                              agy_claude_gpt=(0.02, 0.02), agy_argon=0.02, bedava=0.0)
        ks2 = _kos(
            [{"id": "g1", "brief": "B1", "veri": "genel", "sinif": "kod", "alan": "kod",
              "hedef": {"yol": "agy-oto", "platform": "agy", "havuz": "agy_gemini",
                        "model": "gemini-4-hydrogen", "kimlik": "gemini-4-hydrogen", "efor": "high"}},
             {"id": "g2", "brief": "B2", "veri": "genel", "sinif": "kod", "alan": "kod",
              "hedef": {"yol": "agy-oto", "platform": "agy", "havuz": "agy_gemini",
                        "model": "gemini-4-hydrogen", "kimlik": "gemini-4-hydrogen", "efor": "high"}}],
            SahteTasiyici(), kota_anlik=an_gurultu, kota_okuyucu=lambda _v: an_gurultu,
        )
        oz2 = ks2.calistir()
        self.assertEqual(next(x for x in oz2["isler"] if x["id"] == "g2")["havuz"], "agy_gemini")
        self.assertNotIn("g2", ks2.r17_gecmis)

    def test_sef_tavani_ve_q_tabani_korunur(self):
        say = {"n": 0}

        def surec_fn(argv, stdin):
            say["n"] += 1
            if say["n"] == 1:
                return 0, json.dumps({"status": "SUCCESS", "response": "",
                                      "usage": {"input_tokens": 50, "output_tokens": 0}}), ""
            if "-o" in argv:
                p = Path(argv[argv.index("-o") + 1])
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text("tavan içinde tamam", encoding="utf-8")
                return 0, json.dumps({"usage": {"input_tokens": 60, "output_tokens": 15}}), ""
            return 0, json.dumps({"status": "SUCCESS", "response": "tavan içinde tamam",
                                  "usage": {"input_tokens": 60, "output_tokens": 15}}), ""

        tas = SahteTasiyici(surec_fn=surec_fn)
        k = O.kota71(agy_gemini=(0.9, 0.9), codex=(0.9, 0.9), agy_claude_gpt=(0.9, 0.9), bedava=0.0)
        # şef tavanı sonnet:high (Z=42): w2 (Z=41, Q=41) yukarıdaki high (Z=51) veya sol@medium (Z=46) hedeflerine
        # ÇIKAMAZ; w3 (terra@medium, Z=38, Q=38) ise en çok terra@high'a (Z=42) çıkar, xhigh'a (Z=45) çıkamaz.
        isler = [
            {"id": "s1", "brief": "Başarısız dalga", "veri": "genel", "sinif": "normal", "alan": "genel",
             "hedef": {"yol": "agy-oto", "platform": "agy", "havuz": "agy_gemini",
                       "model": "gemini-4-hydrogen", "kimlik": "gemini-4-hydrogen", "efor": "medium"}},
            {"id": "s2", "brief": "Normal iş Q=41", "veri": "genel", "sinif": "normal", "alan": "genel",
             "hedef": {"yol": "agy-oto", "platform": "agy", "havuz": "agy_gemini",
                       "model": "gemini-4-hydrogen", "kimlik": "gemini-4-hydrogen", "efor": "medium"}},
            {"id": "s3", "brief": "Araştırma iş Q=38", "veri": "genel", "sinif": "arastirma", "alan": "genel",
             "hedef": {"yol": "codex-exec", "platform": "codex", "havuz": "codex_plus",
                       "model": "gpt-6.1-terra", "kimlik": "gpt-6.1-terra", "efor": "medium"}},
        ]
        oz = _kos(isler, tas, kota_anlik=k, plan_ek={"sef": "sonnet:high"}).calistir()
        s2 = next(x for x in oz["isler"] if x["id"] == "s2")
        s3 = next(x for x in oz["isler"] if x["id"] == "s3")
        self.assertEqual(s2["durum"], "ok")
        self.assertEqual(s2["model"], "gemini-4-hydrogen@medium")
        self.assertEqual(s3["durum"], "ok")
        self.assertEqual(s3["model"], "gpt-6.1-terra@high")

    def test_gizlilik_ozel_kisisel_izin_ve_sir_hasta_korunur(self):
        v = _veri_r17(ozel_bedava=True)
        tas = SahteTasiyici()
        k = O.kota71(agy_gemini=(0.9, 0.9), codex=(0.9, 0.9), bedava=0.9)
        isler = [
            {"id": "ok_kisisel", "brief": "Kişisel özet hazırla", "veri": "kisisel", "sinif": "basit", "alan": "genel",
             "hedef": {"yol": "agy-oto", "platform": "agy", "havuz": "agy_gemini",
                       "model": "gemini-4-hydrogen", "kimlik": "gemini-4-hydrogen", "efor": "low"}},
            {"id": "ok_bedava", "brief": "Kişisel not düzenle", "veri": "kisisel", "sinif": "basit", "alan": "genel",
             "hedef": {"yol": "bedava-api", "platform": "bedava", "havuz": "bedava",
                       "model": "deepseek-v4.1-flash", "kimlik": "deepseek-v4.1-flash", "efor": "high"}},
            {"id": "blk_hasta_etiket", "brief": "Klinik not", "veri": "saglik", "sinif": "basit", "alan": "genel",
             "hedef": {"yol": "agy-oto", "platform": "agy", "havuz": "agy_gemini",
                       "model": "gemini-4-hydrogen", "kimlik": "gemini-4-hydrogen", "efor": "low"}},
            {"id": "blk_hasta_icerik", "brief": "Hasta: Ayşe Demir, Tanı: M54.5", "veri": "kisisel",
             "sinif": "basit", "alan": "genel",
             "hedef": {"yol": "agy-oto", "platform": "agy", "havuz": "agy_gemini",
                       "model": "gemini-4-hydrogen", "kimlik": "gemini-4-hydrogen", "efor": "low"}},
            {"id": "blk_sir", "brief": "TOK" + "EN=abcdefghijklmnopqrstu", "veri": "kisisel",
             "sinif": "basit", "alan": "genel",
             "hedef": {"yol": "agy-oto", "platform": "agy", "havuz": "agy_gemini",
                       "model": "gemini-4-hydrogen", "kimlik": "gemini-4-hydrogen", "efor": "low"}},
            # desen parçalı yazılır: dışa aktarma gizlilik taraması ham kaynakta 11 haneli TCKN bulmasın
            {"id": "blk_kimlik", "brief": "Müşteri no " + "1000000" + "0146", "veri": "kisisel",
             "sinif": "basit", "alan": "genel",
             "hedef": {"yol": "bedava-api", "platform": "bedava", "havuz": "bedava",
                       "model": "deepseek-v4.1-flash", "kimlik": "deepseek-v4.1-flash", "efor": "high"}},
        ]
        oz = _kos(isler, tas, veri=v, kota_anlik=k, olc_yaz=False).calistir()
        dur = {x["id"]: x["durum"] for x in oz["isler"]}
        self.assertEqual(dur["ok_kisisel"], "ok")
        self.assertEqual(dur["ok_bedava"], "ok")
        self.assertEqual(dur["blk_hasta_etiket"], "engel")
        self.assertEqual(dur["blk_hasta_icerik"], "engel")
        self.assertEqual(dur["blk_sir"], "engel")
        self.assertEqual(dur["blk_kimlik"], "engel")


if __name__ == "__main__":
    unittest.main()
