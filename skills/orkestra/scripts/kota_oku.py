#!/usr/bin/env python3
"""Codex ve Antigravity kotalarını model çağırmadan okur, atlas dışı yeni modelleri bulur.

Kaynaklar: `codex app-server` account/rateLimits/read, `agy -p /usage`, `agy models`,
~/.codex/models_cache.json. Kimlik/token çıktıya alınmaz. Okunamayan kaynak yazılır; tahmin yok.
Windows, macOS ve Linux'ta çalışır (codex/agy PATH'te veya Windows'taki varsayılan kurulum yerinde).
Kullanım: python -I kota_oku.py [--fresh]
"""
import glob
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone


def _agy_yolu():
    if os.name == "nt":
        p = os.path.join(os.environ.get("LOCALAPPDATA", ""), "agy", "bin", "agy.exe")
        if os.path.exists(p):
            return p
    return shutil.which("agy")


AGY = _agy_yolu()
CACHE = os.path.join(os.path.expanduser("~"), ".codex", "models_cache.json")

# Atlasta tanınan modeller. Bunların dışındakiler "YENİ MODEL" diye bildirilir.
KNOWN_CODEX = {"gpt-6.1-sol", "gpt-6-astra", "gpt-6.1-terra", "gpt-6-sol", "gpt-6-luna",
               "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"}
KNOWN_AGY = {"gemini-4-argon-low", "gemini-4-argon-medium", "gemini-4-argon-high",
             "gemini-3.8-flash-low", "gemini-3.8-flash-medium", "gemini-3.8-flash-high",
             "claude-opus-5-5-low", "claude-opus-5-5-medium", "claude-opus-5-5-high",
             "claude-sonnet-5-5-low", "claude-sonnet-5-5-medium", "claude-sonnet-5-5-high",
             "gpt-oss-120b-medium"}


def find_codex():
    # Windows'ta en yeni sürüm hash klasöründedir (eski bin\codex.exe güncel model listesini okuyamaz).
    if os.name == "nt":
        c = glob.glob(os.path.join(os.environ.get("LOCALAPPDATA", ""), "OpenAI", "Codex", "bin", "*", "codex.exe"))
        if c:
            return max(c, key=os.path.getmtime)
    return shutil.which("codex")


def codex_limits():
    exe = find_codex()
    if not exe:
        return None
    p = subprocess.Popen([exe, "app-server"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL, text=True, encoding="utf-8")
    try:
        def send(o):
            p.stdin.write(json.dumps(o) + "\n")
            p.stdin.flush()
        send({"id": 1, "method": "initialize",
              "params": {"clientInfo": {"name": "kota", "version": "1"}}})
        p.stdout.readline()
        send({"method": "initialized"})
        send({"id": 2, "method": "account/rateLimits/read"})
        for _ in range(8):
            line = p.stdout.readline()
            if not line:
                break
            msg = json.loads(line)
            if msg.get("id") == 2:
                rl = msg["result"]["rateLimits"]
                out = {}
                for key, name in (("primary", "5s"), ("secondary", "hafta")):
                    w = rl.get(key)
                    if w:
                        out[name] = (100 - w["usedPercent"],
                                     datetime.fromtimestamp(w["resetsAt"], timezone.utc))
                return out
    finally:
        p.kill()
    return None


def agy_run(*args, timeout=90):
    if not AGY:
        raise FileNotFoundError("agy bulunamadı")
    return subprocess.run([AGY, *args], capture_output=True, text=True, encoding="utf-8",
                          timeout=timeout, stdin=subprocess.DEVNULL).stdout


def agy_limits():
    data = json.loads(agy_run("-p", "/usage", "--output-format", "json", "--print-timeout", "40s"))
    res = {}
    for g in data["command"]["data"]["groups"]:
        for b in g["buckets"]:
            res[(g["name"], b["window"])] = (round(b["remaining_fraction"] * 100), b["reset_time"])
    return res


def new_models():
    found = []
    if AGY:
        try:
            for line in agy_run("models").splitlines():
                slug = line.split("\t")[0].strip()
                if slug.startswith(("gemini", "claude", "gpt")) and slug not in KNOWN_AGY:
                    found.append(("agy", slug))
        except Exception:
            found.append(("agy", "LİSTE OKUNAMADI"))
    if os.path.exists(CACHE):
        try:
            with open(CACHE, encoding="utf-8") as f:
                d = json.load(f)
            for m in d.get("models", d):
                if m.get("visibility") == "list" and m.get("slug") not in KNOWN_CODEX:
                    found.append(("codex", m["slug"]))
        except Exception:
            found.append(("codex", "LİSTE OKUNAMADI"))
    return found


CACHE_FILE = os.path.join(os.environ.get("TEMP") or os.environ.get("TMPDIR") or ".", "orkestra_kota_onbellek.txt")
CACHE_TTL = 600  # sn; kota okumak model çağırmaz ama birkaç sn sürer, her işçiye tekrarlanmasın


def main():
    """Önbellekli giriş: 10 dk içinde tekrar çağrılırsa eski çıktıyı basar. --fresh zorlar."""
    import io
    import time
    from contextlib import redirect_stdout
    sys.stdout.reconfigure(encoding="utf-8")
    if "--fresh" not in sys.argv:
        try:
            age = time.time() - os.path.getmtime(CACHE_FILE)
            if age < CACHE_TTL:
                with open(CACHE_FILE, encoding="utf-8") as f:
                    print(f.read().rstrip())
                print(f"\n(önbellek: {int(age)} sn önce okundu; yenilemek için --fresh)")
                return 0
        except OSError:
            pass
    buf = io.StringIO()
    with redirect_stdout(buf):
        run()
    text = buf.getvalue()
    print(text.rstrip())
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            f.write(text)
    except OSError:
        pass
    return 0


def run():
    print("== KALAN KOTA (model çağrısı yapılmadı) ==")
    try:
        cx = codex_limits()
        for k, (left, reset) in (cx or {}).items():
            print(f"codex  {k:6s} %{left:<3d} reset {reset:%Y-%m-%d %H:%M}Z")
        if not cx:
            print("codex  OKUNAMADI (kurulu değil veya giriş yapılmamış)")
    except Exception as e:
        print(f"codex  OKUNAMADI ({type(e).__name__})")
    try:
        ag = agy_limits()
        for (grp, win), (left, reset) in ag.items():
            print(f"agy    {grp[:24]:24s} {win:7s} %{left:<3d} reset {reset}")
    except Exception as e:
        print(f"agy    OKUNAMADI ({type(e).__name__})")
    print("Claude Max: get_usage aracıyla (masaüstü uygulaması) veya /usage ile okunur.")

    nm = new_models()
    print("\n== MODEL KEŞFİ ==")
    if nm:
        for host, slug in nm:
            print(f"YENİ MODEL ({host}): {slug} -> atlas dışı; /orkestra güncelle ile kademeye yerleştir")
    else:
        print("Atlas dışı yeni model yok.")
    print("\nModel seçimi: kapasite betiği (kota + zeka + kalan iş + harcanabilirlik):")
    print("  python -I <kapasite betiği> --sinif <sınıf> --is <İB> --claude-5s <kalan%> --claude-hafta <kalan%>")


if __name__ == "__main__":
    sys.exit(main())
