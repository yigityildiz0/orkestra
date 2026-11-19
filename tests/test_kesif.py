"""Keşif ve model envanteri (G1-G2). Gerçek PATH/dosya sistemi yerine geçici dizin ve sahte çıktılar."""
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import _ortak as O
from ork import kesif

FX = O.FIKSTUR


class ModelListeleri(unittest.TestCase):
    def test_codex_models_cache(self):
        m = kesif.codex_modelleri(FX / "codex_models_cache.json")
        slug = {x["slug"]: x for x in m}
        self.assertIn("gpt-6.1-sol", slug)
        self.assertEqual(slug["gpt-6.1-sol"]["varsayilan_efor"], "low")
        self.assertIn("xhigh", slug["gpt-6.1-sol"]["eforlar"])
        self.assertEqual(slug["ornek-gizli"]["gorunurluk"], "hide")          # gizli = gözlem, yine listelenir
        self.assertIn("gorsel", slug["gpt-6.1-sol"]["kipler"])

    def test_agy_models(self):
        m = kesif.agy_modelleri((FX / "agy_models.txt").read_text(encoding="utf-8"))
        h = [x for x in m if x["model"] == "gemini-4-hydrogen"]
        self.assertEqual({x["efor"] for x in h}, {"low", "medium", "high", "xhigh"})
        self.assertFalse(any(x["slug"].startswith("Fetching") for x in m))
        self.assertIn("gemini-ornek-orchestrator-1", {x["model"] for x in m})

    def test_bedava_tum_gorev_turleri(self):
        import json
        liste = json.loads((FX / "bedava_models.json").read_text(encoding="utf-8"))["data"]
        m = kesif.bedava_modelleri(liste)
        gorevler = {x["gorev"] for x in m}
        self.assertTrue({"chat", "ocr", "tts", "embedding", "rerank"} <= gorevler)


class PlatformKesfi(unittest.TestCase):
    def test_surum_karsilastirma(self):
        self.assertGreater(kesif.surum_ayikla("0.169.0"), kesif.surum_ayikla("0.168.9"))
        self.assertGreater(kesif.surum_ayikla("0.169.0"), kesif.surum_ayikla("0.169.0-alpha.3"))
        self.assertIsNone(kesif.surum_ayikla("sürüm yok"))

    def test_ikili_surume_gore_en_yeni(self):
        with tempfile.TemporaryDirectory() as d:
            for s in ("0.168.0", "0.169.0", "0.99.1"):
                p = Path(d, "bin", s)
                p.mkdir(parents=True)
                (p / "codex.exe").write_text("x")
            r = kesif.ikili_bul([str(Path(d, "bin", "*", "codex.exe"))], which=lambda x: None)
            self.assertEqual(r["surum"], "0.169.0")
            self.assertEqual(r["aday_sayisi"], 3)

    def test_ortam_yalniz_ad(self):
        adlar = kesif.ortam_adlari({"YENI_API_KEY": "deger-okunmaz", "PATH": "x", "OPENAI_BASE_URL": "y"})
        self.assertEqual(adlar, ["OPENAI_BASE_URL", "YENI_API_KEY"])

    def test_sinyaller(self):
        onceki = {"path": ["git"], "klasorler": [".claude"], "ortam_adlari": [], "mcp": []}
        simdi = {"path": ["git", "kimi", "notepad"], "klasorler": [".claude", ".kimi"],
                 "ortam_adlari": ["KIMI_API_KEY"], "mcp": ["claude:yeni"], "portlar": [11434]}
        s = kesif.sinyaller(onceki, simdi, bilinen_adlar=())
        turler = {(x["tur"], x["ad"]) for x in s}
        self.assertIn(("path", "kimi"), turler)
        self.assertNotIn(("path", "notepad"), turler)
        self.assertIn(("klasor", ".kimi"), turler)
        self.assertIn(("ortam", "KIMI_API_KEY"), turler)
        self.assertIn(("port", "11434"), turler)
        self.assertNotIn(("path", "kimi"), {(x["tur"], x["ad"]) for x in kesif.sinyaller(onceki, simdi, ["kimi"])})

    def test_imza_durumlari(self):
        with tempfile.TemporaryDirectory() as d:
            exe = Path(d, "arac.exe")
            exe.write_text("x")
            imzalar = {"platformlar": [
                {"id": "ucretli", "ikili": [str(exe)], "ucret": "ucretli-api"},
                {"id": "yeni_abonelik", "ikili": [str(exe)], "ucret": "abonelik"},
                {"id": "kayitli", "ikili": [str(exe)], "ucret": "abonelik"},
                {"id": "kayip_olan", "ikili": [str(Path(d, "yok.exe"))], "ucret": "abonelik"}]}
            platformlar = {"kayitli": {"imza": "kayitli"}, "kayip_olan": {"imza": "kayip_olan"}}
            r = kesif.imza_tara(imzalar, platformlar, which=lambda x: None)
        self.assertEqual(r["ucretli"]["durum"], "ucretli-kapali")       # ücretli asla otomatik aktif değil
        self.assertEqual(r["yeni_abonelik"]["durum"], "aday-platform")
        self.assertEqual(r["kayitli"]["durum"], "aktif")
        self.assertEqual(r["kayip_olan"]["durum"], "kayip")

    def test_giris_denetimi(self):
        imza = {"giris_komutu": {"tur": "komut", "cmd": ["{ikili}", "login", "status"], "basari_deseni": "Logged in"}}
        var = kesif.giris_denetle(imza, "codex", _run=lambda *a, **k: SimpleNamespace(stdout="Logged in using X", stderr="", returncode=0))
        yok = kesif.giris_denetle(imza, "codex", _run=lambda *a, **k: SimpleNamespace(stdout="Not logged in", stderr="", returncode=1))
        self.assertEqual((var, yok), ("var", "yok"))
        from unittest import mock
        temiz = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_CODE_ENTRYPOINT",
                                                                   "CLAUDE_CODE_SDK_HAS_HOST_AUTH_REFRESH")}
        with mock.patch.dict(os.environ, temiz, clear=True):
            self.assertEqual(kesif.giris_denetle({"giris_komutu": {"tur": "mcp"}}, "x"), "bilinmiyor")
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_ENTRYPOINT": "claude-desktop",
                                          "CLAUDE_CODE_SDK_HAS_HOST_AUTH_REFRESH": "1"}):
            self.assertEqual(kesif.giris_denetle({"giris_komutu": {"tur": "mcp"}}, "x"), "var (host)")

    def test_kesif_yap_yerel_kaynaklarla(self):
        v = O.veri()
        an = {"zaman": "2026-11-15T12:00:00+00:00", "path": [], "klasorler": [], "ortam_adlari": [], "mcp": []}
        r = kesif.kesif_yap(v, onceki={}, kaynaklar={"codex_cache": FX / "codex_models_cache.json", "anlik": an,
                                                     "bedava": {}, "which": lambda x: None})
        self.assertIn("codex", r["modeller"])
        self.assertTrue(kesif.rapor_satirlari(r) is not None)


if __name__ == "__main__":
    unittest.main()
