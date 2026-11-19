"""Testlerin ortak kurulumu: yol, yalıtılmış durum dizini, sentetik veri, sabit saat, kota anlığı üretici.
Testler gerçek ~/.orkestra'ya, ağa ya da modele dokunmaz (ORKESTRA_DIR geçici dizine yönlenir)."""
import importlib.util
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

KOK = Path(__file__).resolve().parents[1]
FIKSTUR = KOK / "tests" / "fixtures"
if str(KOK / "scripts") not in sys.path:
    sys.path.insert(0, str(KOK / "scripts"))

# gerçek kişisel katman (duman testleri için; yalnız okunur): ORKESTRA_KISISEL > önceki ORKESTRA_DIR > ~/.orkestra
KISISEL = Path(os.environ.get("ORKESTRA_KISISEL") or os.environ.get("ORKESTRA_DIR") or (Path.home() / ".orkestra"))
GECICI = tempfile.mkdtemp(prefix="ork-test-")
os.environ["ORKESTRA_DIR"] = GECICI
os.environ.pop("ORKESTRA_KISISEL", None)          # kişisel katman da geçici dizinden (yalıtım)
os.environ.pop("ORKESTRA_KOTA_KAYNAGI", None)
os.environ.pop("ORKESTRA_KOTA_ANLIK", None)
os.environ["CETVEL_DIZINI"] = os.path.join(GECICI, "cetvel-yok")      # gerçek Cetvel keşfi testlere karışmaz
# şef algılaması (R16) gerçek oturumdan etkilenmez: ortam değişkenleri ve ayar dosyaları yalıtılır
for _ad in ("ORKESTRA_SEF", "ORKESTRA_SEF_MODEL", "ORKESTRA_SEF_EFOR", "ANTHROPIC_MODEL", "CLAUDE_EFFORT",
            "CLAUDE_CODE_EFFORT_LEVEL", "CLAUDE_CODE_SESSION_ID"):
    os.environ.pop(_ad, None)
os.environ["ORKESTRA_SEF_AYARLARI"] = ""

from ork.veri import Veri  # noqa: E402

_spec = importlib.util.spec_from_file_location("ornek_veri", FIKSTUR / "ornek_veri.py")
ornek_veri = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ornek_veri)

SIMDI = datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc)


def _kisisel_var():
    import json as _j
    for ad in ("kullanici-kurallari", "platformlar"):
        f = KISISEL / f"{ad}.json"
        try:
            if int((_j.loads(f.read_text(encoding="utf-8-sig")) or {}).get("sema") or 0) < 7:
                return False
        except (OSError, ValueError):
            return False
    return all((KOK / "data" / f"{a}.json").exists() for a in ("modeller", "siniflar"))


GERCEK_VAR = _kisisel_var()
GERCEK_NEDEN = f"gerçek kişisel veri yok ({KISISEL}; ORKESTRA_KISISEL ile göster)"


def gercek_veri():
    """Gerçek genel veri + gerçek kişisel katman (salt okuma)."""
    return Veri.yukle(KOK / "data", KISISEL)


def veri(degistir=None):
    d = ornek_veri.veri_sozluk()
    if degistir:
        degistir(d)
    return Veri.sozlukten(d)


def ham():
    return ornek_veri.veri_sozluk()


def _pen(k5, kh, simdi, hafta_oran, t5_dk):
    out = {}
    if k5 is not None:
        out["5s"] = {"kalan": k5, "sifirlama": (simdi + timedelta(minutes=t5_dk)).isoformat(), "kaynak": "test"}
    if kh is not None:
        out["hafta"] = {"kalan": kh, "sifirlama": (simdi + timedelta(minutes=10080 * hafta_oran)).isoformat(),
                        "kaynak": "test"}
    return out


def kota(simdi=SIMDI, claude=(0.9, 0.9), codex=(0.9, 0.9), agy=0.9, bedava=0.9, codex_durum="ok",
         hafta_oran=0.5, t5_dk=150):
    """claude/codex: (5s kalan, hafta kalan). Sıfırlama: hafta penceresinin `hafta_oran`'ı kadar sonra."""
    h = {"claude_max": {"durum": "ok", "pencereler": _pen(*claude, simdi, hafta_oran, t5_dk)},
         "codex_plus": {"durum": codex_durum, "pencereler": _pen(*codex, simdi, hafta_oran, t5_dk)
                        if codex_durum == "ok" else {}},
         "agy_gemini": {"durum": "ok", "pencereler": {"hafta": {"kalan": agy, "sifirlama": (simdi + timedelta(days=3)).isoformat()}}},
         "bedava": {"durum": "ok", "pencereler": {"gun": {"kalan": bedava, "sifirlama": (simdi + timedelta(hours=15)).isoformat()},
                                                  "5dk": {"kalan": 1.0, "sifirlama": (simdi + timedelta(minutes=5)).isoformat()}}}}
    return {"sema": 1, "yazan": "ork.kota", "zaman": simdi.isoformat(), "havuzlar": h}


def veri71(degistir=None):
    d = ornek_veri.veri_v71_sozluk()
    if degistir:
        degistir(d)
    return Veri.sozlukten(d)


def kota71(simdi=SIMDI, claude=(0.9, 0.9), codex=(0.9, 0.9), agy_gemini=(1.0, 0.9), agy_claude_gpt=(1.0, 1.0),
           agy_argon=0.9, bedava=0.9, oran=None, t5=None, codex_ek=None, codex_durum="ok"):
    """v7.1 Q0 anlığı (tasarım 12.1). oran: havuz başına haftalık sıfırlamaya kalan oran (varsayılan claude/codex
    0.5, agy 3/7); t5: havuz başına 5 saatlik sıfırlamaya kalan dakika (varsayılan 150)."""
    oran = dict({"claude_max": 0.5, "codex_plus": 0.5, "agy_gemini": 3 / 7, "agy_claude_gpt": 3 / 7,
                 "agy_argon": 3 / 7}, **(oran or {}))
    t5 = dict({"claude_max": 150, "codex_plus": 150, "agy_gemini": 150, "agy_claude_gpt": 150}, **(t5 or {}))
    h = {"claude_max": {"durum": "ok", "pencereler": _pen(*claude, simdi, oran["claude_max"], t5["claude_max"])},
         "codex_plus": {"durum": codex_durum, "pencereler": _pen(*codex, simdi, oran["codex_plus"], t5["codex_plus"])
                        if codex_durum == "ok" else {}},
         "agy_gemini": {"durum": "ok", "pencereler": _pen(*agy_gemini, simdi, oran["agy_gemini"], t5["agy_gemini"])},
         "agy_claude_gpt": {"durum": "ok", "pencereler": _pen(*agy_claude_gpt, simdi, oran["agy_claude_gpt"],
                                                              t5["agy_claude_gpt"])},
         "agy_argon": {"durum": "ok", "pencereler": _pen(None, agy_argon, simdi, oran["agy_argon"], 0)},
         "bedava": {"durum": "ok", "pencereler": {"gun": {"kalan": bedava, "sifirlama": (simdi + timedelta(hours=15)).isoformat()},
                                                  "5dk": {"kalan": 1.0, "sifirlama": (simdi + timedelta(minutes=5)).isoformat()}}}}
    if codex_ek:
        h["codex_plus"]["ek"] = codex_ek
    return {"sema": 1, "yazan": "ork.kota", "zaman": simdi.isoformat(), "havuzlar": h}
