"""Toplu koşucu (tasarım 9.4): dış işçileri (bedava API, otomatik agy, Codex) TEK Bash çağrısıyla paralel yürütür.

İlke (ince lider): dış işçi bir Claude alt ajanına sarılmaz; lider yalnız ≤4 KB özet JSON'u ve gerekli çıktı
dosyalarını okur. Claude hedefli öğe çalıştırılmaz, özetin `claude_isleri` listesine hazır Agent satırıyla döner.

Güvenceler: gönderim öncesi gizlilik taraması (kamu/dış hedefte bulgu -> `engel`, sıfır istek), platform ve model
semaforları, agy başlatma aralığı + saatlik/günlük tavan + ilk 403'te kapanış, bedava 5 dk token penceresi (HOLD),
503 geri çekilme ve eş sınıf kardeşe düşüş (daha zayıf sınıfa asla), 429 adil pay beklemesi (deneme sayılmaz).
Platform/model adı kodda yok: sınırlar, çağrı şablonları ve kardeşler kişisel platformlar.json `suru` bloğundan.
Kullanım: ork suru calistir --plan suru.json [--paralel N] [--kuru] [--dusus izinli|yok] [--json]
          ork suru durum --is <is_id> · ork suru temizle --agy [--gun 7] [--uygula]
"""
import argparse
import collections
import contextlib
import copy
import hashlib
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path

from . import araclar, kota
from .veri import HASSAS_VERI, Veri, VeriHatasi, atomik_yaz, durum_dizini, json_oku, simdi_utc, skill_kok, zaman_coz

OZET_TAVAN = 4096
AGY_ISTEM_TAVAN = 28000
MIKRO_TOPLU_TAVAN = 8
DIS_YOLLAR = {"bedava-api", "agy-oto", "codex-exec"}
DUSUNME_ONEKI = "Araç kullanma; yalnız metin yanıt ver."
# askı/fesih işaretleri: stderr her zaman; stdout/response/error yalnız başarısız çağrıda taranır (başarılı yanıttaki
# "403" sözcüğü, ör. bir HTTP kod incelemesi, kapanış tetiklemesin)
ASKI_DESEN = re.compile(r"(?i)(\b403\b|forbidden|suspend|askıya|account (?:has been )?disabled|terms of service|"
                        r"permission_denied|permission denied|\brestricted\b|\bbanned\b|\bbanlan)")
AGY_KOTA_DESEN = re.compile(r"(?i)(resource_exhausted|quota|rate limit|limit reached|429)")
AGY_ARDISIK_DUR = 2                  # ardışık kalıcı/kota hatasında agy bu koşuda durur (SOR T4 notu)
SIR_ORTAM = re.compile(r"(?i)(KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|COOKIE|SESSION)S?$|_API_KEY")
VARSAYILAN_SURU = {"hesap_eszamanli_kullan": 8, "model_eszamanli": {"_arac": 4}, "zaman_asimi_sn": 900,
                   "max_tokens_varsayilan": 8000, "pencere_5dk_tampon": 0.2,
                   "yeniden_dene": {"503": {"geri_cekilme_sn": [15, 30, 60], "en_cok": 6},
                                    "ag": {"en_cok": 2, "bekle_sn": 10}, "429_tavan": 20},
                   "ardisik_503_kardese": 2, "kardes": {}, "kardes_kosul": {}, "soguma_profili": {}}


# ================================================================== taşıyıcı (gerçek G/Ç; testte sahtesi verilir)
class Tasiyici:
    def http(self, url, govde, basliklar, zaman_asimi):
        """(kod, başlıklar küçük harf, gövde JSON|None). Yönlendirme izlenmez (anahtar başka origin'e taşınmaz)."""
        req = urllib.request.Request(url, data=json.dumps(govde).encode("utf-8"), method="POST",
                                     headers=dict(basliklar, **{"Content-Type": "application/json"}))
        try:
            with urllib.request.build_opener(kota._Yonlendirmesiz).open(req, timeout=zaman_asimi) as r:
                ham, bas, kod = r.read(), {k.lower(): v for k, v in r.headers.items()}, r.status
        except urllib.error.HTTPError as e:
            bas = {k.lower(): v for k, v in (e.headers or {}).items()}
            try:
                ham = e.read()
            except Exception:
                ham = b""
            kod = e.code
        except (urllib.error.URLError, TimeoutError, OSError):
            return 599, {}, None                  # ağ/zaman aşımı: koşucunun ağ yeniden deneme dalı
        try:
            g = json.loads(ham.decode("utf-8")) if ham else None
        except ValueError:
            g = None
        return kod, bas, g

    def surec(self, argv, stdin_metin, zaman_asimi, cwd=None, env=None):
        """(çıkış kodu, stdout, stderr). Kabuk yok (shell=False); istem argv ya da stdin."""
        try:
            r = subprocess.run(argv, input=stdin_metin, capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=zaman_asimi, cwd=cwd, env=env,
                               stdin=None if stdin_metin is not None else subprocess.DEVNULL)
            return r.returncode, r.stdout or "", r.stderr or ""
        except subprocess.TimeoutExpired:
            return 124, "", "timeout"
        except OSError as e:
            return 127, "", type(e).__name__


class Saat:
    def simdi(self):
        return time.monotonic()

    def uyu(self, sn):
        if sn > 0:
            time.sleep(sn)


# ================================================================== yardımcılar
def _metin(brief):
    if not brief:
        return ""
    p = Path(str(brief))
    try:
        if len(str(brief)) < 400 and p.is_file():
            return p.read_text(encoding="utf-8")
    except OSError:
        pass
    return str(brief)


def _ozet_satiri(metin):
    for satir in (metin or "").splitlines():
        if satir.strip().upper().startswith("ÖZET:") or satir.strip().upper().startswith("OZET:"):
            return satir.split(":", 1)[1].strip()[:200]
    return " ".join((metin or "").split())[:200]


def _turkce_mi(metin):
    return bool(re.search(r"[çğıöşüÇĞİÖŞÜ]", metin or ""))


def _yaz(yol, metin):
    if not yol:
        return None
    p = Path(yol)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(metin or "", encoding="utf-8")
    return str(p)


def _kayit_yolu(ad):
    return durum_dizini() / ad


def _jsonl_ekle(yol, kayit):
    yol = Path(yol)
    yol.parent.mkdir(parents=True, exist_ok=True)
    with open(yol, "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(kayit, ensure_ascii=False) + "\n")


def _jsonl_oku(yol):
    yol = Path(yol)
    out = []
    if yol.is_file():
        for s in yol.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(s))
            except ValueError:
                continue
    return out


def temiz_ortam(veri, ek=None):
    """Alt süreç ortamı: kayıtlı anahtar/taban değişkenleri (anahtar_env, taban_env) ve adı sır gibi görünen
    değişkenler (*_KEY, *_TOKEN, *_SECRET, *_PASSWORD, ...) düşer; model çıktısı ya da istem enjeksiyonu `env` ile
    anahtarı göremez. CLI kimlikleri kendi yapılandırma dosyalarındadır (ortamda değil)."""
    adlar = set()
    for p in ((getattr(veri, "platformlar_ham", None) or {}).get("platformlar") or {}).values():
        if isinstance(p, dict):
            adlar.update(x for x in (p.get("anahtar_env"), p.get("taban_env")) if x)
            adlar.update(x for x in ((p.get("api") or {}).get("anahtar_env"), (p.get("api") or {}).get("taban_env"))
                         if x)
    for x in (getattr(veri, "kurallar", None) or {}).get("bedava_istisna") or []:
        if isinstance(x, dict) and x.get("anahtar_env"):
            adlar.add(x["anahtar_env"])
    env = {k: v for k, v in os.environ.items() if k not in adlar and not SIR_ORTAM.search(k)}
    env.update(ek or {})
    return env


@contextlib.contextmanager
def dosya_kilidi(yol, en_cok_sn=30.0):
    """Süreçler arası kısa kritik bölge (iki paralel `ork suru` aynı agy tavanını iki kez saymasın)."""
    yol = Path(yol)
    yol.parent.mkdir(parents=True, exist_ok=True)
    f = open(yol, "a+b")
    kilitli = False
    try:
        bas = time.monotonic()
        while True:
            try:
                f.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                kilitli = True
                break
            except OSError:
                if time.monotonic() - bas > en_cok_sn:
                    raise TimeoutError("agy kilit dosyası alınamadı")
                time.sleep(0.05)
        yield
    finally:
        if kilitli:
            try:
                f.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
        f.close()


def _doldur(sablon, alanlar):
    out = []
    for x in sablon:
        x = str(x)
        for k, v in alanlar.items():
            x = x.replace("{" + k + "}", str(v))
        out.append(x)
    return out


# ================================================================== koşucu
class Kosucu:
    def __init__(self, plan, veri=None, tasiyici=None, saat=None, kuru=False, dusus="izinli", paralel=None,
                 durum_yaz=True, olc_yaz=True, simdi=None, kota_anlik=None, kota_okuyucu=None, dalga_boyutu=None):
        self.plan = plan or {}
        self.veri = veri or Veri.yukle()
        self.t = tasiyici or Tasiyici()
        self.saat = saat or Saat()
        self.kuru = kuru
        self.dusus = dusus
        self.paralel = paralel
        self.durum_yaz = durum_yaz
        self.olc_yaz = olc_yaz
        self.simdi = simdi or simdi_utc()
        self.kota_anlik = kota_anlik
        self.kota_okuyucu = kota_okuyucu
        self.dalga_boyutu = dalga_boyutu
        self.kilit = threading.Lock()
        self.sem = {}
        self.hold = collections.deque()           # (zaman, token) bedava 5 dk penceresi
        self.agy_son_baslatma = None
        self.agy_baslatmalar = []                 # planlanan başlatma anları (başlatma aralığı denetimi)
        self.agy_kapali = False
        self.agy_ardisik = 0                      # ardışık kalıcı/kota agy hatası
        self.agy_ikili_ozet = {}
        self.calisma_anlik = None                 # `sec` öğeleri için rezervasyonlu kota kopyası
        self.r17_gecmis = {}                      # parca_id -> [(dalga, yon, eski_imza, yeni_imza)]
        self.notlar = []
        # şef tavanı (R16): plan düzeyi `sef`; açık hedef, kardeş, oy adayı ve yargıç da şefi aşamaz
        # tavanı yalnız plan düzeyi (CLI --tavan-yok / kullanıcı) kaldırır; öğe düzeyindeki tavan_yok yok sayılır
        self.tavan_yok = bool(self.plan.get("tavan_yok"))
        self.sef = None
        self.sef_hata = None
        if self.plan.get("sef"):
            from . import secici
            try:
                self.sef = secici.sef_coz(self.plan["sef"], self.veri)
            except VeriHatasi as e:
                # sessizce tavansız devam yok: plan durur (açık hedefler denetlenemez)
                self.sef_hata = f"şef tavanı çözülemedi ({e}): plan durduruldu; --sef rol:efor ile yeniden çalıştır"
                self.notlar.append(f"HATA {self.sef_hata}")
        self.sonuclar = {}
        gz = self.veri.kurallar.get("gizlilik") or {}
        self.sozluk = list(gz.get("ek_sozluk") or []) + araclar.otomatik_sozluk()
        self.yollar = list(gz.get("yasak_yol") or [])
        self.degerler = araclar.anahtar_degerleri(self.veri)

    # ---------------------------------------------------------- yapılandırma
    def suru_ayari(self, pid):
        p = ((self.veri.platformlar_ham.get("platformlar") or {}).get(pid)) or {}
        d = json.loads(json.dumps(VARSAYILAN_SURU))
        for k, v in (p.get("suru") or {}).items():
            if isinstance(v, dict) and isinstance(d.get(k), dict):
                d[k].update(v)
            else:
                d[k] = v
        return d

    def _semafor(self, ad, n):
        with self.kilit:
            if ad not in self.sem:
                self.sem[ad] = threading.BoundedSemaphore(max(int(n), 1))
            return self.sem[ad]

    def _gizlilik(self, oge, metin):
        h = oge["hedef"]
        yol = h.get("yol")
        if yol == "yerel":
            return None
        hv = self.veri.havuz(h.get("havuz") or "")
        p = self.veri.platformlar.get(h.get("platform"), {})
        gz = hv.get("gizlilik") or p.get("gizlilik") or "ozel"
        vs = oge.get("veri") or "bilinmiyor"
        if gz in ("kamu", "dis"):
            if vs != "genel":
                return f"gizlilik: {gz} hedef yalnız veri=genel (verilen {vs})"
            bul = araclar.tara(metin, kisisel=True, sozluk=self.sozluk, yollar=self.yollar, degerler=self.degerler)
        else:
            if yol == "bedava-api":
                istisna = next((b for b in (self.veri.kurallar.get("bedava_istisna") or [])
                                if isinstance(b, dict) and b.get("platform") == h.get("platform")), None)
                if istisna and istisna.get("veri") != "kisisel" and vs != "genel":
                    return f"gizlilik: bedava istisna yalnız veri=genel (verilen {vs})"
            dis_onay = bool(oge.get("dis_onay") or (h.get("sec") or {}).get("dis_onay") or self.plan.get("dis_onay"))
            p_host = self.veri.host(p.get("imza") or h.get("platform") or "") if p.get("host") else None
            host_pl = self.veri.host(self.plan.get("host") or "claude-code")
            if vs in HASSAS_VERI and vs in ("saglik", "gizli") and not dis_onay and p_host != host_pl:
                return f"gizlilik: {gz} dış hedef veri={vs} için kullanıcı onayı (--dis-onay) ister"
            bul = araclar.tara(metin, kisisel=False, yollar=self.yollar, degerler=self.degerler, kimlik_ve_yol=True)
        bul += araclar.kisi_saglik_tara(metin)
        if bul:
            return "gönderim öncesi tarama: " + ", ".join(sorted({t for t, _ in bul}))
        return None

    def _olc(self, oge, model, efor, durum, tok=None, sure=None, hata=None, deneme=0, dusus=None):
        if not self.olc_yaz or self.kuru:
            return
        h = oge["hedef"]
        m = self.veri.model(h.get("kimlik") or "") or {}
        sinif = oge.get("sinif") if oge.get("sinif") in self.veri.siniflar.get("q", {}) else "basit"
        k = {"is_id": str(self.plan.get("is_id") or "suru"), "parca_id": oge["id"], "sinif": sinif,
             "alan": oge.get("alan") or "genel", "model": model, "efor": efor or "varsayilan",
             "havuz": h.get("havuz") or h.get("platform") or "?", "aile": m.get("saglayici") or "?", "yol": "suru",
             "durum": durum, "giris_tok": (tok or {}).get("giris"), "cikis_tok": (tok or {}).get("cikis"),
             "sure_sn": sure, "hata_sinifi": hata, "yeniden_deneme": int(deneme)}
        yuk = oge.get("_yukseltme")
        if isinstance(yuk, dict) and yuk.get("var"):
            k["yukseltme"] = {"var": True, "neden": str(yuk.get("neden") or "")[:240]}
        elif dusus:
            k["yukseltme"] = {"var": False, "neden": f"düşüş: {dusus}"[:240]}
        try:
            araclar.olc_kaydet(k, self.veri)          # veriyle: maliyet_usd_e (kalibrasyon girdisi) yazılır
        except (OSError, VeriHatasi):
            pass

    # ---------------------------------------------------------- ana akış
    def calistir(self):
        bas = self.saat.simdi()
        isler = [dict(x) for x in (self.plan.get("isler") or [])]
        claude, dis, digerleri = [], [], []
        for o in isler:
            o["id"] = str(o.get("id"))
            if self.sef_hata:
                self.sonuclar[o["id"]] = {"id": o["id"], "durum": "engel", "ozet": self.sef_hata}
                continue
            if o.get("tavan_yok") or (o.get("hedef") or {}).get("tavan_yok"):
                n_ = (f"UYARI {o['id']}: öğe düzeyi tavan_yok yok sayıldı (tavanı yalnız kullanıcı kaldırır: CLI "
                      f"--tavan-yok ya da plan düzeyi)")
                if n_ not in self.notlar:
                    self.notlar.append(n_)
            try:
                h = self._hedef(o)
            except VeriHatasi as e:
                self.sonuclar[o["id"]] = {"id": o["id"], "durum": "hata", "ozet": f"hedef çözülemedi: {e}"}
                continue
            if h is None:
                self.sonuclar[o["id"]] = {"id": o["id"], "durum": "hata", "ozet": "hedef çözülemedi"}
                continue
            o["hedef"] = h
            if h.get("yol") == "claude-agent":
                tn = self._tavan(h, h.get("kimlik") or h.get("model"))     # Claude işçisi de şefi aşamaz
                if tn:
                    self.sonuclar[o["id"]] = {"id": o["id"], "durum": "engel", "ozet": tn}
                    continue
                claude.append(o)
            elif h.get("yol") in DIS_YOLLAR:
                d_ = self.hedef_denetle(h)              # açık hedef de yasak/bitiş/kapalı/soğuma/taban/kapıdan geçer
                if d_:
                    self.sonuclar[o["id"]] = {"id": o["id"], "durum": d_[0], "ozet": d_[1]}
                    continue
                dis.append(o)
            else:
                digerleri.append(o)
                self.sonuclar[o["id"]] = {"id": o["id"], "durum": "bekle", "ozet": f"elle yol ({h.get('yol')}): "
                                          f"otomatik yürütülmez"}
        gruplar = self._mikro_gruplari(dis)
        paralel = self.paralel or max(1, sum(int(self.suru_ayari(p).get("hesap_eszamanli_kullan") or 1)
                                             for p in {o["hedef"]["platform"] for o in dis}) or 1)
        ex_max = max(1, min(paralel, 32))
        dalga_sinir = max(1, int(self.dalga_boyutu or self.plan.get("dalga_boyutu") or ex_max))
        bekleyen = list(gruplar)
        dalga_no = 0
        with ThreadPoolExecutor(max_workers=ex_max) as ex:
            while bekleyen:
                hazir = [g for g in bekleyen if self._bagimli_hazir(g)]
                if not hazir:
                    for g in bekleyen:
                        for o in g:
                            self.sonuclar[o["id"]] = {"id": o["id"], "durum": "bekle",
                                                      "ozet": "bağımlı öğe tamamlanmadı"}
                    break
                cozulen = [g for g in hazir if all(o["id"] in self.sonuclar for o in g)]
                calisacak = [g for g in hazir if any(o["id"] not in self.sonuclar for o in g)][:dalga_sinir]
                for g in cozulen + calisacak:
                    bekleyen.remove(g)
                if not calisacak:
                    continue
                dalga_no += 1
                if dalga_no > 1:
                    gidecek = []
                    for g in calisacak:
                        kaldi = []
                        for o in g:
                            if o["id"] in self.sonuclar:
                                continue
                            d_ = self.hedef_denetle(o["hedef"])
                            if d_:
                                self.sonuclar[o["id"]] = {"id": o["id"], "durum": d_[0], "ozet": d_[1]}
                            else:
                                kaldi.append(o)
                        if kaldi:
                            gidecek.append(kaldi)
                    calisacak = gidecek
                if calisacak:
                    list(ex.map(self._grup_yurut, calisacak))
                    if bekleyen:
                        self._dalga_yeniden_degerlendir(bekleyen, [o for g in calisacak for o in g], dalga_no)
        sure = round(self.saat.simdi() - bas, 1)
        return self._ozet(isler, claude, sure)

    def _bagimli_hazir(self, grup):
        """Bağımlılar bittiyse True; bağımlı başarısızsa öğe `bekle` yazılır (True döner, yürütülmez)."""
        for o in grup:
            for b in o.get("bagimli") or []:
                r = self.sonuclar.get(str(b))
                if not r:
                    return False
                if r.get("durum") != "ok":
                    self.sonuclar[o["id"]] = {"id": o["id"], "durum": "bekle", "ozet": f"bağımlı {b} {r.get('durum')}"}
        return True

    def _hedef(self, o):
        h = o.get("hedef") or {}
        if "sec" in h:
            from . import secici
            o.setdefault("_sec_istek", copy.deepcopy(h["sec"]))
            if self.calisma_anlik is None:
                if self.kota_anlik is None and self.kota_okuyucu:
                    self.kota_anlik = self.kota_okuyucu(self.veri)
                self.calisma_anlik = copy.deepcopy(self.kota_anlik or kota.oku(self.veri))
            ist = {k: v for k, v in dict(h["sec"]).items() if k not in ("sef", "tavan_yok")}
            ist, uy = secici.parca_tavani(ist, h["sec"], self.plan, self.veri)
            for u in uy:
                n_ = f"{o.get('id')}: {u}"
                if n_ not in self.notlar:
                    self.notlar.append(n_)
            r = secici.sec(ist, self.veri, self.calisma_anlik, kota.durum_oku())
            a = r.get("secim")
            if not a or r.get("durum") != "secildi":
                return None
            # kota rezervasyonu: N öğe aynı anlığı N kez saymasın (plan_sec ile aynı kural)
            self._kalan_kota_dus(a)
            return self._sec_hedef_yap(a, r.get("istek") or ist, cagri=r.get("cagri"))
        return dict(h) if h.get("yol") else None

    def _sec_hedef_yap(self, a, i_sec, cagri=None):
        from . import secici
        c = cagri or secici.cagri_uret(a, self.veri, i_sec)
        return {"yol": a["yol"], "platform": a["platform"], "havuz": a["havuz"], "model": c.get("model"),
                "kimlik": a["kimlik"], "efor": a["efor"], "efor_bayragi": bool(a.get("efor_bayragi")),
                "takma": c.get("takma"), "cagri": c.get("komut")}

    def _kalan_kota_dus(self, a):
        if self.calisma_anlik is None or not a:
            return
        for w, pay in (a.get("paylar") or {}).items():
            pen = (((self.calisma_anlik.get("havuzlar") or {}).get(a["havuz"]) or {}).get("pencereler") or {}).get(w)
            if isinstance(pen, dict) and pen.get("kalan") is not None:
                pen["kalan"] = max(0.0, float(pen["kalan"]) - float(pay))

    def _anlik_tazele(self):
        """R17: dalgalar arası kota anlığını yalnızca tazeleyici/kopya üzerinden yeniler (çevrimdışı testte ağ yok)."""
        if self.kota_okuyucu:
            taze = self.kota_okuyucu(self.veri)
            if isinstance(taze, dict):
                self.kota_anlik = taze
                self.calisma_anlik = copy.deepcopy(taze)
        elif self.kota_anlik is not None and self.calisma_anlik is None:
            self.calisma_anlik = copy.deepcopy(self.kota_anlik)
        return self.calisma_anlik

    def _havuz_bosluk(self, hid, anlik=None):
        """Havuzun pencere tabanı üzerindeki en dar boşluğu (kalan - taban); kapalı -1, okunamıyorsa None."""
        an = anlik if anlik is not None else self._anlik_denetim()
        if not an or not hid:
            return None
        kh = ((an.get("havuzlar") or {}).get(hid)) or {}
        if kh.get("durum") == "kapali":
            return -1.0
        farklar = [float(x["kalan"]) - self.veri.taban(hid, w)
                   for w, x in (kh.get("pencereler") or {}).items()
                   if isinstance(x, dict) and x.get("kalan") is not None]
        return min(farklar) if farklar else None

    @staticmethod
    def _hedef_imzasi(h):
        return (h.get("havuz"), h.get("kimlik") or h.get("model"), h.get("efor"))

    def _histerezis_engelli(self, oid, dalga_no, yon, h_yeni):
        """Ardışık iki dalgada tersine dönüşü ya da terk edilen hedefe/havuza geri dönüşü engeller."""
        gec = self.r17_gecmis.get(oid) or []
        if not gec:
            return False
        son_dalga, son_yon, son_eski, son_yeni = gec[-1]
        yeni = self._hedef_imzasi(h_yeni)
        if yeni == son_yeni:
            return True
        if dalga_no - son_dalga <= 1:
            if yeni == son_eski:
                return True
            if {son_yon, yon} == {"yukari", "asagi"}:
                return True
            if son_yon == "havuz" and yeni[0] == son_eski[0]:
                return True
        return False

    def _dalga_sinyalleri(self, dalga_isler):
        """Tamamlanan dalgadaki başarısızlık, boş yanıt, yüksek yeniden deneme ve havuz baskısını ölçer."""
        ay = self.veri.siniflar.get("secici") or {}
        histerezis = float(ay.get("histerezis", 0.85))
        kk = self.veri.siniflar.get("kanitli_kaskad") or {}
        max_den = int(kk.get("en_cok_deneme", 2))
        esik = max(0.05, 1.0 - histerezis)
        havuz_baskisi = set()
        zayif_isler, toplam = [], 0
        sinif_say, sinif_zayif = collections.Counter(), collections.Counter()
        for o in dalga_isler:
            r = self.sonuclar.get(o["id"])
            if not r or r.get("durum") == "engel":
                continue
            toplam += 1
            sinif = o.get("sinif") or "normal"
            sinif_say[sinif] += 1
            hid = (o.get("hedef") or {}).get("havuz")
            ozet_k = str(r.get("ozet") or "").lower()
            kap = r.get("hata") in ("kapasite", "kota") or "503" in ozet_k or "429" in ozet_k
            if kap and hid:
                havuz_baskisi.add(hid)
            bos = (r.get("durum") == "ok" and "_metin" in r and r.get("_metin") is not None
                   and not str(r.get("_metin")).strip()) or "boş çıktı" in ozet_k or "boş yanıt" in ozet_k
            kalite_hata = (r.get("durum") in ("hata", "kismi", "bekle") and not kap) or bos
            yuksek_deneme = (not kap) and int(r.get("deneme") or 0) >= max_den
            if kalite_hata or yuksek_deneme:
                neden = "boş yanıt" if bos else ("yüksek yeniden deneme" if yuksek_deneme else "işçi başarısızlığı")
                zayif_isler.append((o, neden))
                sinif_zayif[sinif] += 1
        yukselt_genel = bool(toplam and len(zayif_isler) / toplam >= esik)
        zayif_siniflar = {s for s, n in sinif_say.items() if n and sinif_zayif[s] / n >= esik}
        neden = zayif_isler[0][1] if zayif_isler else None
        return yukselt_genel, zayif_siniflar, neden, havuz_baskisi

    def _istek_oge_icin(self, o, yalniz_havuz=None):
        from . import secici
        ham = copy.deepcopy(o.get("_sec_istek")) if o.get("_sec_istek") else {
            "alan": o.get("alan") or "genel", "alt_alan": o.get("alt_alan"),
            "sinif": o.get("sinif") or "normal", "veri": o.get("veri") or "bilinmiyor",
            "boyut": o.get("boyut") or "orta", "dis_onay": bool(o.get("dis_onay") or self.plan.get("dis_onay")),
        }
        ham.setdefault("suru", True)
        if self.plan.get("host"):
            ham.setdefault("host", self.plan["host"])
        if self.plan.get("dizin"):
            ham.setdefault("dizin", self.plan["dizin"])
        if yalniz_havuz is not None:
            ham["yalniz_havuz"] = list(yalniz_havuz)
        ham, _ = secici.parca_tavani(ham, ham, self.plan, self.veri)
        proje = secici.proje_kurali(ham.get("dizin"))
        durum_h = kota.durum_oku()
        i = secici.istek_hazirla(ham, self.veri, proje)
        i["kademe"] = secici.kademe(i["Q"], self.veri.siniflar)
        i["_anahtar"] = f"{i['alan']}/{i.get('alt_alan') or '-'}/{i['sinif']}"
        secici._tavan_hazirla(i, self.veri, durum_h, self.simdi)
        return i, durum_h, proje

    def _uygun_dis_adaylar(self, o, yalniz_havuz=None, filtre=None, eski_hid=None):
        from . import secici
        i, durum_h, proje = self._istek_oge_icin(o, yalniz_havuz=yalniz_havuz)
        adaylar, _ = secici.adaylari_uret(i, self.veri, durum_h, self.simdi, proje, filtre=filtre)
        adaylar = [a for a in adaylar if a.get("yol") in DIS_YOLLAR]
        if not adaylar:
            return [], i, durum_h
        secici.kalite_hesapla(adaylar, i.get("alt_alan"), self.veri)
        an_den = self._anlik_denetim()
        an = an_den if an_den is not None else {}
        rc = secici.rho_claude(self.veri, an, durum_h, self.simdi)
        dout = {}
        uyg = []
        for a in adaylar:
            kp = secici.kapasite(a, i, self.veri, an, durum_h, self.simdi, None, dout, rho_C=rc.get("rho"))
            if not kp.get("uygun"):
                if (an_den is None and eski_hid and a.get("havuz") == eski_hid
                        and str(kp.get("neden", "")).startswith("bedava havuz okunamadı")):
                    kp = {"katman": 0, "S": float(a.get("g") or 0.0), "pay": 0.0, "paylar": {}, "c": 0.0,
                          "belirsiz": True}
                else:
                    continue
            if kp.get("katman") == secici.SOR_KATMAN:
                continue
            cand = dict(a, **{k: v for k, v in kp.items() if k != "uygun"})
            cand.setdefault("P", float(cand.get("S") or cand.get("g") or 0.0))
            h_alt = self._sec_hedef_yap(cand, i)
            if self.hedef_denetle(h_alt):
                continue
            cand["_hedef"] = h_alt
            uyg.append(cand)
        if not uyg:
            return [], i, durum_h
        sirali = secici.sirala(uyg, self.veri, i["Q"], durum_h, i["_anahtar"], dout)
        return sirali, i, durum_h

    def _aday_z_etkin(self, o, h_eski, i0, durum_h, proje):
        from . import secici
        eski_kim = h_eski.get("kimlik") or h_eski.get("model")
        eski_hid = h_eski.get("havuz")
        eski_ef = h_eski.get("efor") or (self.veri.platformlar.get(h_eski.get("platform")) or {}).get("varsayilan_efor")
        m_cur = self.veri.model(eski_kim) if eski_kim else None
        if eski_kim:
            adaylar, _ = secici.adaylari_uret(
                i0, self.veri, durum_h, self.simdi, proje, gevsek=True,
                filtre=lambda k, r, ef: (k == eski_kim or (m_cur is not None and self.veri.model(k) is m_cur))
                and (ef is None or not eski_ef or ef == eski_ef),
                yedek_izinli=True,
            )
            tam = next((a for a in adaylar if not eski_hid or a["havuz"] == eski_hid), None) or (
                adaylar[0] if adaylar else None)
            if tam is not None:
                return float(tam["z_etkin"]), eski_ef or tam["efor"]
            if m_cur:
                var = m_cur.get("varyantlar") or {}
                if eski_ef and (var.get(eski_ef) or {}).get("z") is not None:
                    return float(var[eski_ef]["z"]), eski_ef
                zs = [(float(v["z"]), e) for e, v in var.items() if isinstance(v, dict) and v.get("z") is not None]
                if zs:
                    z_max, e_max = max(zs)
                    return z_max, eski_ef or e_max
        return float(i0["Q"]), eski_ef

    def _dalga_secim_adayi(self, o, yukselt_gerek, yukselt_nedeni, havuz_baskisi, dalga_no):
        """R17: tek kalan parça için (sec_a, yon, neden) ya da None döner."""
        from . import secici
        h_eski = o["hedef"]
        eski_hid, eski_kim = h_eski.get("havuz"), h_eski.get("kimlik") or h_eski.get("model")
        i0, durum_h, proje = self._istek_oge_icin(o)
        q_taban = float(i0["Q"])
        m_cur = self.veri.model(eski_kim) if eski_kim else None
        eski_z, eski_ef = self._aday_z_etkin(o, h_eski, i0, durum_h, proje)
        ay = secici.ayar(self.veri)
        esit_bant = float(ay.get("esitlik_bandi", 0.10))
        kova_adim = float(ay.get("kova_adim", 0.05))
        histerezis = float(ay.get("histerezis", 0.85))
        aa_z = float(secici.delta_hesapla(i0.get("alt_alan"), "z", self.veri.siniflar))
        cur_bosluk = self._havuz_bosluk(eski_hid, self.calisma_anlik)
        kh_eski = (((self.calisma_anlik or {}).get("havuzlar") or {}).get(eski_hid) or {})
        denet_eski = self.hedef_denetle(h_eski)
        taban_yakin = (kh_eski.get("durum") == "kapali") or (eski_hid in havuz_baskisi) \
            or (denet_eski is not None) or (cur_bosluk is not None and cur_bosluk <= esit_bant)
        # 1. Havuz tabana yaklaştı/baskıda: eşdeğer başka havuz (Q, R16 ve anlamlı fark içinde)
        diger_havuzlar = [hid for hid in self.veri.havuzlar if hid != eski_hid]
        if taban_yakin and diger_havuzlar:
            adaylar, _, _ = self._uygun_dis_adaylar(o, yalniz_havuz=diger_havuzlar)
            esdeger = [a for a in adaylar if a["z_etkin"] >= max(q_taban, eski_z - aa_z)]
            saglikli = []
            for a in esdeger:
                if self._histerezis_engelli(o["id"], dalga_no, "havuz", a["_hedef"]):
                    continue
                alt_b = self._havuz_bosluk(a["havuz"], self.calisma_anlik)
                zorunlu = (cur_bosluk is None or cur_bosluk <= 0 or eski_hid in havuz_baskisi
                           or denet_eski is not None) and (alt_b is None or alt_b > kova_adim)
                anlamli = alt_b is not None and cur_bosluk is not None and (alt_b - cur_bosluk >= esit_bant)
                if zorunlu or anlamli:
                    saglikli.append((0 if (not yukselt_gerek or a["z_etkin"] >= eski_z) else 1,
                                     a["katman"], -(alt_b if alt_b is not None else 0.5), a["P"], a["id"], a))
            if saglikli:
                saglikli.sort(key=lambda x: x[:5])
                sec_a = saglikli[0][5]
                sebep = f"havuz {eski_hid} kapasite/kota baskısı" if eski_hid in havuz_baskisi else \
                    f"havuz {eski_hid} tabana yaklaştı"
                return sec_a, "havuz", f"{sebep} -> eşdeğer havuz {sec_a['havuz']}"
        # 2. Başarısızlık / boş yanıt / yüksek yeniden deneme -> bir üst efor ya da model
        if yukselt_gerek:
            if eski_ef:
                ust_ef, _, _ = self._uygun_dis_adaylar(
                    o, yalniz_havuz={eski_hid} if eski_hid else None,
                    filtre=lambda k, r, ef: (k == eski_kim or (m_cur is not None and self.veri.model(k) is m_cur))
                    and (ef is None or secici.efor_sira(ef) > secici.efor_sira(eski_ef)),
                    eski_hid=eski_hid,
                )
                ust_ef = [a for a in ust_ef if a["havuz"] == eski_hid and a["z_etkin"] >= max(q_taban, eski_z)
                          and not self._histerezis_engelli(o["id"], dalga_no, "yukari", a["_hedef"])]
                if ust_ef:
                    anlamli_ef = [a for a in ust_ef if a["z_etkin"] >= eski_z + aa_z] or \
                        [a for a in ust_ef if a["z_etkin"] > eski_z] or ust_ef
                    sec_a = min(anlamli_ef, key=lambda a: (secici.efor_sira(a["efor"]), -a["z_etkin"], a["id"]))
                    return sec_a, "yukari", f"{yukselt_nedeni} -> üst efor {eski_kim}@{eski_ef}->{sec_a['efor']}"
            tum, _, _ = self._uygun_dis_adaylar(o, eski_hid=eski_hid)
            ust_mod = [a for a in tum if a["z_etkin"] >= max(q_taban, eski_z + aa_z)
                       and not self._histerezis_engelli(o["id"], dalga_no, "yukari", a["_hedef"])]
            if ust_mod:
                sec_a = min(ust_mod, key=lambda a: (a["z_etkin"] - eski_z, a["katman"], a.get("g", 0), a["id"]))
                return sec_a, "yukari", (f"{yukselt_nedeni} -> üst model {eski_kim}@{eski_ef or '?'}->"
                                          f"{sec_a['kimlik']}@{sec_a['efor']}")
        # 3. Otomatik `sec` parçası sağlıklı dalgada anlamlı fiyat/katman iyileşmesinde güncellenir (histerezis=0.85)
        if o.get("_sec_istek"):
            tum, _, _ = self._uygun_dis_adaylar(o, eski_hid=eski_hid)
            mevcut = next((a for a in tum if a["havuz"] == eski_hid and a["kimlik"] == eski_kim
                           and a["efor"] == eski_ef), None)
            en_iyi = tum[0] if tum else None
            if en_iyi and mevcut and en_iyi["id"] != mevcut["id"] and en_iyi["z_etkin"] >= q_taban:
                yon = "yukari" if en_iyi["z_etkin"] > mevcut["z_etkin"] else (
                    "asagi" if en_iyi["z_etkin"] < mevcut["z_etkin"] else "havuz")
                if ((en_iyi["katman"] < mevcut["katman"])
                        or (en_iyi["katman"] == mevcut["katman"] and en_iyi["P"] < histerezis * mevcut["P"])) \
                        and not self._histerezis_engelli(o["id"], dalga_no, yon, en_iyi["_hedef"]):
                    return en_iyi, yon, f"kota yenilemesi (P {mevcut['P']:.2f}->{en_iyi['P']:.2f})"
        return None

    def _dalga_yeniden_degerlendir(self, bekleyen, dalga_isler, dalga_no):
        """R17: dalga bitiminde anlığı tazeler; kalan parçalar için seçimi histerezisle yeniden hesaplar."""
        self._anlik_tazele()
        yukselt_genel, zayif_siniflar, neden_w, havuz_baskisi = self._dalga_sinyalleri(dalga_isler)
        if self._anlik_denetim() is None and not yukselt_genel and not zayif_siniflar and not havuz_baskisi:
            return
        degisti = False
        for g in bekleyen:
            for o in g:
                if o["id"] in self.sonuclar:
                    continue
                if any((self.sonuclar.get(str(b)) or {}).get("durum") in ("hata", "engel", "bekle", "kismi")
                       for b in (o.get("bagimli") or [])):
                    continue
                sinif = o.get("sinif") or "normal"
                yukselt_bu = yukselt_genel or (sinif in zayif_siniflar)
                secim = self._dalga_secim_adayi(o, yukselt_bu, neden_w or "düşük başarı", havuz_baskisi, dalga_no)
                if not secim:
                    continue
                sec_a, yon, aciklama = secim
                h_eski = o["hedef"]
                h_yeni = sec_a["_hedef"]
                self.r17_gecmis.setdefault(o["id"], []).append(
                    (dalga_no, yon, self._hedef_imzasi(h_eski), self._hedef_imzasi(h_yeni)))
                o["hedef"] = h_yeni
                onceki_neden = (o.get("_yukseltme") or {}).get("neden")
                tam_neden = f"{onceki_neden}; {aciklama}" if onceki_neden else aciklama
                o["_yukseltme"] = {"var": True, "neden": tam_neden}
                self._kalan_kota_dus(sec_a)
                not_satir = (f"R17 dalga {dalga_no} {o['id']}: {h_eski.get('havuz')}/"
                             f"{h_eski.get('kimlik') or h_eski.get('model')}@{h_eski.get('efor')} -> "
                             f"{h_yeni.get('havuz')}/{h_yeni.get('kimlik')}@{h_yeni.get('efor')} ({aciklama})")
                self.notlar.append(not_satir)
                degisti = True
        if degisti:
            duz = [o for g in bekleyen for o in g]
            bekleyen[:] = self._mikro_gruplari(duz)

    def _anlik_denetim(self):
        """Taban denetimi için anlık: rezervasyonlu çalışma kopyası ya da verilen anlık (CLI her zaman taze okur);
        burada canlı okuma ya da önbellek tahmini yapılmaz."""
        if self.calisma_anlik is not None:
            return self.calisma_anlik
        return self.kota_anlik

    def hedef_denetle(self, h):
        """Açık hedef (plan dosyasından), kardeş, oy adayı ve yargıç için ortak sert denetim. Dönüş None ya da
        (durum, neden): yasak aile (R8), havuz bitişi/kapalı, soğuma, taban (kalan <= taban), agy kapısı."""
        from . import secici
        kim = h.get("kimlik") or h.get("model")
        for ad in {x for x in (kim, h.get("model")) if x}:
            y, g = self.veri.yasak_mi(ad, self.veri.model(ad))
            if y:
                return "engel", f"yasak hedef {ad} ({g})"
        tn = self._tavan(h, kim)
        if tn:
            return "engel", tn
        hid = h.get("havuz") or ""
        hv = self.veri.havuz(hid) if hid else {}
        pl = self.veri.platformlar.get(h.get("platform"), {})
        b = zaman_coz(hv.get("bitis") or pl.get("bitis"))
        if b and b <= self.simdi:
            return "engel", f"havuz kapandı ({hv.get('bitis') or pl.get('bitis')})"
        if pl and pl.get("durum", "aktif") != "aktif":
            return "engel", f"platform {h.get('platform')} {pl.get('durum')}"
        if h.get("yol") == "agy-oto":
            acik, neden = secici.agy_kapisi(self.veri, kota.durum_oku())
            if not acik:
                return "engel", f"agy kapısı kapalı: {neden}"
        sg = kota.soguma_secici_icin()
        for anahtar in (hid, f"{hid}:{kim}"):
            if anahtar and anahtar in sg:
                return "bekle", f"soğumada ({anahtar} {sg[anahtar].get('tur')})"
        an = self._anlik_denetim()
        if an is None:
            if hid and hid not in self.veri.ana_havuzlar() and not hv.get("bedava"):
                n_ = f"NOT {hid}: taban denetlenemedi (taze kota anlığı yok); plan seçicide denetlenmişti"
                if n_ not in self.notlar:
                    self.notlar.append(n_)
            return None
        kh = ((an.get("havuzlar") or {}).get(hid)) or {}
        if kh.get("durum") == "kapali":
            return "engel", f"havuz kapalı ({hid})"
        for w, x in (kh.get("pencereler") or {}).items():
            if isinstance(x, dict) and x.get("kalan") is not None and float(x["kalan"]) <= self.veri.taban(hid, w):
                return "bekle", f"{hid}.{w} tabanda (kalan %{float(x['kalan']) * 100:.0f})"
        return None

    def _tavan(self, h, kim):
        """Şef tavanı ihlali (neden) ya da None. Efor verilmemişse platformun varsayılan eforu, o da yoksa modelin en
        yüksek Z'li varyantı varsayılır (temkinli: katalog varsayılanı tuzaktır)."""
        if self.sef_hata:
            return self.sef_hata
        if not self.sef:
            return None
        from . import secici
        m = self.veri.model(kim) or self.veri.model(h.get("model") or "")
        kim = kim if self.veri.model(kim or "") else (h.get("model") if m else kim)
        if not m:
            neden = (f"şef tavanı denetlenemedi: {kim or h.get('model') or '?'} kayıtta yok (açık hedef; kayıtlı "
                     f"kimlik ver ya da kullanıcı --tavan-yok)")
        else:
            ef = h.get("efor") or (self.veri.platformlar.get(h.get("platform")) or {}).get("varsayilan_efor")
            var = {e: v.get("z") for e, v in (m.get("varyantlar") or {}).items() if v.get("z") is not None}
            if not var:
                neden = f"şef tavanı denetlenemedi: {kim} için Z yok (kullanıcı --tavan-yok)"
            else:
                if ef not in var:
                    ef = max(var, key=lambda e: (var[e], secici.efor_sira(e)))
                rol = self.veri.model_rol(kim) if kim else None
                neden = secici.tavan_ihlal(self.sef, kim, rol, ef, m)
        if neden and self.tavan_yok:                 # kullanıcı kaldırdı: geçer, uyarıyla
            n_ = f"UYARI şef tavanı aşıldı (--tavan-yok): {kim or h.get('model')} · {neden}"
            if n_ not in self.notlar:
                self.notlar.append(n_)
            return None
        return neden

    def _mikro_gruplari(self, dis):
        gruplar, mikro = [], {}
        for o in dis:
            h = o["hedef"]
            if h["yol"] == "agy-oto" and o.get("boyut") == "mikro" and not o.get("bagimli") and not o.get("desen"):
                anahtar = (h.get("model"), h.get("efor"), h.get("kip") or "plan")
                mikro.setdefault(anahtar, []).append(o)
            else:
                gruplar.append([o])
        for L in mikro.values():
            for n in range(0, len(L), MIKRO_TOPLU_TAVAN):
                gruplar.append(L[n:n + MIKRO_TOPLU_TAVAN])
        return gruplar

    def _grup_yurut(self, grup):
        try:
            if len(grup) > 1:
                return self._agy_toplu(grup)
            o = grup[0]
            metin = _metin(o.get("brief"))
            engel = self._gizlilik(o, metin)
            if engel:
                self.sonuclar[o["id"]] = {"id": o["id"], "durum": "engel", "ozet": engel}
                return
            if self.kuru:
                self.sonuclar[o["id"]] = {"id": o["id"], "durum": "ok", "ozet": "KURU: tarama temiz, istek yok",
                                          "model": f"{o['hedef'].get('model')}@{o['hedef'].get('efor')}"}
                return
            desen = o.get("desen")
            if desen == "oy":
                self.sonuclar[o["id"]] = self._oy(o, metin)
            elif desen == "aday_yargic":
                self.sonuclar[o["id"]] = self._aday_yargic(o, metin)
            else:
                self.sonuclar[o["id"]] = self._tek(o, metin)
        except Exception as e:                       # bir öğenin hatası diğerlerini düşürmez
            for o in grup:
                self.sonuclar.setdefault(o["id"], {"id": o["id"], "durum": "hata", "ozet": f"istisna {type(e).__name__}"})

    def _tek(self, o, metin, hedef=None, yaz=True):
        h = hedef or o["hedef"]
        yol = h["yol"]
        if yol == "bedava-api":
            r = self._bedava(o, metin, h)
        elif yol == "agy-oto":
            r = self._agy(o, metin, h)
        else:
            r = self._codex(o, metin, h)
        r["id"] = o["id"]
        if yaz and r.get("durum") == "ok" and r.get("_metin") is not None and o.get("cikti"):
            r["cikti"] = _yaz(o["cikti"], r["_metin"])
        if yaz and r.get("durum") == "ok" and (o.get("dogrulama") or {}).get("tur") == "test" and o.get("cikti"):
            g, _ = self._test(o["dogrulama"], o.get("cikti"))
            r["dogrulama"] = {"tur": "test", "sonuc": "gecti" if g else "kaldi"}
            if not g:
                r["durum"] = "kismi"
        r["ozet"] = r.get("ozet") or _ozet_satiri(r.get("_metin"))
        return r

    # ---------------------------------------------------------- bedava API
    def _bedava(self, o, metin, h):
        pid = h["platform"]
        ayar = self.suru_ayari(pid)
        api = self.veri.api_ayari(pid)
        anahtar = kota.anahtar_oku(api.get("anahtar_env"))
        if not anahtar:
            return {"durum": "hata", "ozet": "anahtar ortamda yok", "hata": "kalici"}
        taban = (os.environ.get(api.get("taban_env") or "") or api.get("taban_url") or "").rstrip("/")
        if not kota.taban_guvenli(taban):
            return {"durum": "hata", "ozet": "taban URL https değil", "hata": "kalici"}
        p = (self.veri.platformlar_ham.get("platformlar") or {}).get(pid) or {}
        uc = (p.get("uclar") or {}).get("chat") or "/chat/completions"
        bas_ad = api.get("anahtar_basligi") or "Authorization"
        bas = {bas_ad: anahtar if bas_ad.lower() != "authorization" else f"Bearer {anahtar}",
               "User-Agent": "orkestra-suru/7"}
        max_tok = int(o.get("max_tokens") or ayar.get("max_tokens_varsayilan") or 8000)
        tahmin = int(len(metin) / 3.5) + max_tok
        pencere = float((self.veri.K_p(h.get("havuz"), "5dk")[0]) or 0)
        tampon = float(ayar.get("pencere_5dk_tampon") or 0.2)
        yd = ayar.get("yeniden_dene") or {}
        y503 = yd.get("503") or {}
        geri = list(y503.get("geri_cekilme_sn") or [15, 30, 60])
        en_cok = int(y503.get("en_cok") or 6)
        ag = yd.get("ag") or {}
        model, efor = h.get("model") or h.get("kimlik"), h.get("efor")
        kardes_kul = False
        deneme = ardisik = bekleme429 = ag_n = 0
        bas_t = self.saat.simdi()
        while True:
            ms = (ayar.get("model_eszamanli") or {}).get(model, (ayar.get("model_eszamanli") or {}).get("_arac", 4))
            hs = self._semafor(f"{pid}", ayar.get("hesap_eszamanli_kullan") or 8)
            mss = self._semafor(f"{pid}:{model}", ms)
            if not self._hold_bekle(tahmin, pencere, tampon):
                return {"durum": "bekle", "ozet": "5 dk token penceresi boşalmadı (gönderilmedi)", "hata": "kapasite",
                        "model": f"{model}@{efor or '-'}", "deneme": deneme}
            govde = {"model": model, "messages": [{"role": "user", "content": metin}], "max_tokens": max_tok}
            if efor and efor not in ("varsayilan", "none_yok"):
                govde["reasoning_effort"] = efor
            erisim = (p.get("erisim") or {}).get(model) or {}
            if erisim.get("thinking"):
                govde["thinking"] = True
            with hs, mss:
                kod, basl, g = self.t.http(taban + uc, govde, bas, float(o.get("zaman_asimi_sn")
                                                                        or ayar.get("zaman_asimi_sn") or 900))
            if kod == 200 and isinstance(g, dict):
                icerik = (((g.get("choices") or [{}])[0].get("message") or {}).get("content")) or ""
                u = g.get("usage") or {}
                tok = {"giris": u.get("prompt_tokens"), "cikis": u.get("completion_tokens")}
                sure = round(self.saat.simdi() - bas_t, 1)
                self._olc(o, model, efor, "ok", tok, sure, None, deneme, "kardes" if kardes_kul else None)
                if self.durum_yaz and not self.kuru:
                    kota.soguma_temizle(f"{h.get('havuz')}:{model}", yalniz=True)
                return {"durum": "ok", "_metin": icerik, "model": f"{model}@{efor or '-'}", "havuz": h.get("havuz"),
                        "tok": tok, "sure_sn": sure, "deneme": deneme, "dusus": "kardes" if kardes_kul else None}
            metin_h = json.dumps(g, ensure_ascii=False)[:300] if g else ""
            if kod in (503, 529):
                deneme += 1
                ardisik += 1
                if ardisik >= int(ayar.get("ardisik_503_kardese") or 2) and not kardes_kul:
                    k2 = self._kardes(pid, model, o, metin, ayar)
                    if k2:
                        model, efor = k2
                        kardes_kul, ardisik = True, 0
                        continue
                if deneme >= en_cok:
                    self._soguma_503(h, model, ayar)
                    self._olc(o, model, efor, "hata", None, None, "kapasite", deneme)
                    return {"durum": "bekle", "ozet": f"503 x{deneme}: kapasite dolu", "hata": "kapasite",
                            "model": f"{model}@{efor or '-'}", "deneme": deneme}
                ra = basl.get("retry-after")
                try:
                    bekle = float(ra) if ra else geri[min(deneme - 1, len(geri) - 1)]
                except ValueError:
                    bekle = geri[min(deneme - 1, len(geri) - 1)]
                self.saat.uyu(bekle + random.uniform(0, 5))
                continue
            if kod == 429:
                bekleme429 += 1                               # adil pay: deneme sayılmaz
                if bekleme429 > int(yd.get("429_tavan") or 20):
                    return {"durum": "bekle", "ozet": "429 adil pay: model payı dolu", "hata": "kapasite",
                            "model": f"{model}@{efor or '-'}", "deneme": deneme}
                self.saat.uyu(5)
                continue
            if kod in (None, 0, 124, 599) or kod >= 520:
                ag_n += 1
                if ag_n > int(ag.get("en_cok") or 2):
                    return {"durum": "hata", "ozet": "ağ hatası", "hata": "gecici", "deneme": deneme}
                self.saat.uyu(float(ag.get("bekle_sn") or 10))
                continue
            s = kota.hata_sinifla(metin_h, kod)
            self._olc(o, model, efor, "hata", None, None, s["sinif"], deneme)
            return {"durum": "hata", "ozet": f"HTTP {kod} ({s['sinif']})", "hata": s["sinif"],
                    "model": f"{model}@{efor or '-'}", "deneme": deneme}

    def _kardes(self, pid, model, o, metin, ayar):
        """Eş sınıf kardeş (daha zayıf sınıfa düşülmez): koşul (Türkçe/kritik kod) uymazsa atlanır; `--dusus yok`
        kardeş tanımlı olsa da düşüşü kapatır; yasak/kapalı kardeş atlanır."""
        if self.dusus == "yok":
            return None
        for k in (ayar.get("kardes") or {}).get(model) or []:
            m, _, e = str(k).partition("@")
            if self.hedef_denetle({"yol": "bedava-api", "platform": pid, "model": m, "kimlik": m,
                                   "havuz": (o.get("hedef") or {}).get("havuz")}):
                continue
            kos = (ayar.get("kardes_kosul") or {}).get(m) or {}
            if kos.get("turkce") is False and (o.get("turkce") or _turkce_mi(metin)):
                continue
            if kos.get("kritik_kod") is False and o.get("sinif") in ("zor", "kritik") and o.get("alan") == "kod":
                continue
            return m, (e or None)
        return None

    def _soguma_503(self, h, model, ayar):
        if self.durum_yaz and not self.kuru:
            kota.soguma_kaydet(f"{h.get('havuz')}:{model}", "503", profil=ayar.get("soguma_profili"))

    def _hold_bekle(self, tahmin, pencere, tampon, en_cok_sn=600):
        """5 dk token penceresi: son 300 sn'de gönderilenlerin (giriş + max_tokens) toplamı tavanı aşacaksa bekler.
        True: yer ayrıldı; False: en_cok_sn içinde boşalmadı (rezervasyonsuz gönderim YOK: 429/adil pay fırtınası)."""
        if not pencere:
            return True
        tavan = (1 - tampon) * pencere
        bas = self.saat.simdi()
        while True:
            with self.kilit:
                t = self.saat.simdi()
                while self.hold and t - self.hold[0][0] > 300:
                    self.hold.popleft()
                if sum(x[1] for x in self.hold) + tahmin <= tavan or not self.hold:
                    self.hold.append((t, tahmin))
                    return True
            if self.saat.simdi() - bas > en_cok_sn:
                return False
            self.saat.uyu(1.0)

    # ---------------------------------------------------------- agy
    def _agy_ayari(self):
        ao = self.veri.agy_otomatik()
        g = dict(ao.get("guvenceler") or {})
        teyit = (ao.get("karar") or {}).get("teyit_edildi", True)
        if not teyit:
            g.update(g.get("teyitsiz_profil") or {})
        g.setdefault("eszamanli", 2)
        g.setdefault("baslatma_araligi_sn", 20)
        g.setdefault("saatlik_cagri_tavani", 10)
        g.setdefault("gunluk_cagri_tavani", 30)
        return ao, g, teyit

    def _agy_kayitlari(self):
        return _jsonl_oku(_kayit_yolu("agy-cagri.jsonl"))

    @staticmethod
    def _cagri_kaydi_mi(x):
        """Tavana sayılan kayıt: model çağrısı başlangıcı (yeni biçim) ya da eski tek satır; bitiş satırı ve /usage
        okuması sayılmaz (okumanın kendi tavanı var: kota.agy_okuma_izni)."""
        return x.get("tur") in (None, "cagri")

    def _agy_tavan(self, g, kayitlar=None):
        simdi = simdi_utc()
        k = [zaman_coz(x.get("zaman")) for x in (kayitlar if kayitlar is not None else self._agy_kayitlari())
             if self._cagri_kaydi_mi(x)]
        k = [z for z in k if z]
        saat = sum(1 for z in k if simdi - z <= timedelta(hours=1))
        gun = sum(1 for z in k if simdi - z <= timedelta(days=1))
        if saat >= int(g["saatlik_cagri_tavani"]):
            return f"agy saatlik çağrı tavanı ({g['saatlik_cagri_tavani']})"
        if gun >= int(g["gunluk_cagri_tavani"]):
            return f"agy günlük çağrı tavanı ({g['gunluk_cagri_tavani']})"
        return None

    def _agy_ikili_denetle(self, exe, ao):
        """Değişmemiş ikili (güvence `degismemis_ikili`): ilk doğrulanmış kullanımda sha256 durum.json'a yazılır (ilk
        kullanımda güven), sonra her koşuda karşılaştırılır; farklıysa engel (güncelleme sonrası yeniden doğrula)."""
        if not (ao.get("guvenceler") or {}).get("degismemis_ikili") or not os.path.isfile(exe):
            return None
        if exe not in self.agy_ikili_ozet:
            try:
                hsh = hashlib.sha256()
                with open(exe, "rb") as f:
                    for blok in iter(lambda: f.read(1 << 20), b""):
                        hsh.update(blok)
                self.agy_ikili_ozet[exe] = hsh.hexdigest()
            except OSError:
                return "agy ikilisi okunamadı (özet alınamadı)"
        ozet = self.agy_ikili_ozet[exe]
        kayit = (kota.durum_oku().get("agy_ikili") or {}).get("sha256")
        if kayit and kayit != ozet:
            return "agy ikilisi doğrulanandan farklı (güncellendi?): `ork kesif --agy` ile yeniden doğrula"
        if not kayit and self.durum_yaz and not self.kuru:
            kota.durum_yaz({"agy_ikili": {"sha256": ozet, "zaman": simdi_utc().isoformat(timespec="seconds")}})
        return None

    def _agy_cagir(self, o_ids, istem, h, kip, sure_dk, sema=None):
        """Tek agy çağrısı (güvenceler içinde). Dönüş: (durum, json|None, hata sınıfı, ham).
        Sıra: kapı (fail-closed) -> 403/ardışık hata kapanışı -> şablon -> ikili özeti -> yalın profil dosyası ->
        semafor -> [süreçler arası kilit: tavan + eşzamanlılık + başlatma kaydı] -> çağrı -> bitiş kaydı."""
        from . import secici
        ao, g, teyit = self._agy_ayari()
        acik, kneden = secici.agy_kapisi(self.veri, kota.durum_oku())
        if not acik:
            return "engel", None, "kalici", f"agy kapısı kapalı: {kneden}"
        if self.agy_kapali or (kota.durum_oku().get("agy_otomatik_kapali") and self.durum_yaz):
            return "engel", None, "kalici", "agy otomatik kapalı (403 ya da ardışık hata sonrası)"
        if not h.get("model") or not h.get("efor"):
            return "hata", None, "kalici", "agy çağrısı --model ve --effort olmadan yapılmaz (varsayılan model tuzağı)"
        if len(istem) > AGY_ISTEM_TAVAN:
            return "hata", None, "kalici", f"istem {len(istem)} > {AGY_ISTEM_TAVAN} karakter: brief'i böl"
        p = (self.veri.platformlar_ham.get("platformlar") or {}).get(h["platform"]) or {}
        sab = (p.get("cagri") or {}).get("argv_oto")
        if not sab:
            return "hata", None, "kalici", "platform cagri.argv_oto şablonu yok"
        exe = self._ikili(h["platform"])
        if not exe:
            return "hata", None, "kalici", "agy ikilisi bulunamadı"
        ik = self._agy_ikili_denetle(exe, ao)
        if ik:
            return "engel", None, "kalici", ik
        prof = ao.get("isci_profili") or {}
        yalin = os.path.expanduser(str(prof.get("settings") or ""))
        if prof.get("settings") and not os.path.isfile(yalin):
            if prof.get("dogrulandi"):
                # doğrulandı denen yalın profil dosyası yok: tam kişisel bağlama sessizce düşülmez
                return "engel", None, "kalici", "yalın işçi profili dosyası yok (doğrulama geçersiz): ork kesif --agy"
            yalin = ""                     # kullanıcı kişisel bağlamı açıkça kabul etti: profilsiz (notla)
            self.notlar.append("NOT agy yalın profil dosyası yok: kişisel bağlam kabulüyle profilsiz çağrıldı")
        alan = {"ikili": exe, "istem": istem, "taban": h.get("model"), "efor": h.get("efor"), "kip": kip,
                "sure": f"{int(sure_dk)}m", "yalin_ayar": yalin}
        argv = _doldur(sab, alan)
        if yalin and "--settings" not in argv:
            argv += ["--settings", yalin]
        argv = [x for x in argv if x != ""]
        if "--settings" in argv and argv.index("--settings") == len(argv) - 1:
            argv = argv[:-1]
        if sema:
            argv += ["--json-schema", str(sema)]
        cwd = os.path.expanduser(str(prof.get("calisma_dizini") or "")) or None
        if cwd:
            Path(cwd).mkdir(parents=True, exist_ok=True)
        kayit_yolu = _kayit_yolu("agy-cagri.jsonl")
        kilit_yolu = _kayit_yolu("agy.lock")
        cid = uuid.uuid4().hex[:12]
        sem = self._semafor("agy", g["eszamanli"])
        with sem:
            # süreçler arası rezervasyon: tavan ve eşzamanlılık BAŞLANGIÇ kayıtlarıyla sayılır (bitiş beklenmez)
            for _ in range(240):
                if self.agy_kapali:            # semafor beklerken kapanmış olabilir (403 ya da ardışık hata)
                    return "engel", None, "kalici", "agy bu koşuda durdu (403 ya da ardışık hata)"
                with self.kilit, dosya_kilidi(kilit_yolu):
                    kayitlar = self._agy_kayitlari()
                    tav = self._agy_tavan(g, kayitlar)
                    if tav:
                        return "bekle", None, "kota", tav
                    simdi_ = simdi_utc()
                    biten = {x.get("cid") for x in kayitlar if x.get("tur") == "cagri_son"}
                    ucus = [x for x in kayitlar if x.get("tur") == "cagri" and x.get("cid") not in biten
                            and x.get("pid") != os.getpid() and (zaman_coz(x.get("zaman")) or simdi_)
                            >= simdi_ - timedelta(seconds=sure_dk * 60 + 120)]
                    if len(ucus) < int(g["eszamanli"]):
                        t = self.saat.simdi()
                        bekle = float(g["baslatma_araligi_sn"]) - (t - self.agy_son_baslatma) \
                            if self.agy_son_baslatma is not None else 0
                        dis_son = max((zaman_coz(x.get("zaman")) for x in kayitlar if x.get("tur") == "cagri"
                                       and x.get("pid") != os.getpid() and zaman_coz(x.get("zaman"))), default=None)
                        if dis_son:
                            bekle = max(bekle, float(g["baslatma_araligi_sn"]) - (simdi_ - dis_son).total_seconds())
                        self.agy_son_baslatma = t + max(bekle, 0)
                        self.agy_baslatmalar.append(self.agy_son_baslatma)
                        if not self.kuru:
                            _jsonl_ekle(kayit_yolu, {"zaman": (simdi_ + timedelta(seconds=max(bekle, 0)))
                                                     .isoformat(timespec="seconds"), "tur": "cagri", "cid": cid,
                                                     "pid": os.getpid(), "model": h.get("model"),
                                                     "efor": h.get("efor"), "oge": len(o_ids), "teyitsiz": not teyit})
                        break
                self.saat.uyu(5.0)              # başka süreçte eşzamanlılık dolu: yer açılmasını bekle
            else:
                return "bekle", None, "kapasite", "agy eşzamanlılık (başka süreç) dolu"
            self.saat.uyu(max(bekle, 0))
            bas = self.saat.simdi()
            kod, out, err = self.t.surec(argv, None, sure_dk * 60 + 30, cwd=cwd,
                                         env=temiz_ortam(self.veri, {"MSYS_NO_PATHCONV": "1"}))
            sure = round(self.saat.simdi() - bas, 1)
            js = None
            try:
                js = json.loads(out) if out.strip() else None
            except ValueError:
                js = None
            basari = bool(js) and js.get("status") == "SUCCESS" and (js.get("response") or js.get("structured")) \
                and not js.get("finished_reason") and not js.get("denied_actions")
            kay = {"zaman": simdi_utc().isoformat(timespec="seconds"), "tur": "cagri_son", "cid": cid,
                   "pid": os.getpid(), "model": h.get("model"), "efor": h.get("efor"), "kip": kip, "sure_sn": sure,
                   "kod": kod, "oge": len(o_ids), "conversation_id": (js or {}).get("conversation_id"),
                   "usage": (js or {}).get("usage"), "teyitsiz": not teyit}
            hata_metni = (err or "") + ("" if basari else " " + (out or "")[-2000:] + " " + str((js or {}).get("error")
                                                                                              or ""))
            aski = bool(ASKI_DESEN.search(err or "")) or (not basari and bool(ASKI_DESEN.search(hata_metni)))
            kay["durum"] = "403" if aski else ("ok" if basari else "hata")
            if not self.kuru:
                _jsonl_ekle(kayit_yolu, kay)
            # ardışık kalıcı/kota hatası sayacı semafor İÇİNDE (bekleyen öğe kapanmayı görmeden başlamasın)
            kalici_ya_da_kota = (not basari and not aski and not (js and js.get("denied_actions"))
                                 and (kod in (1, 2) or bool(AGY_KOTA_DESEN.search(hata_metni))))
            with self.kilit:
                if basari:
                    self.agy_ardisik = 0
                elif kalici_ya_da_kota:
                    self.agy_ardisik += 1
                    if self.agy_ardisik >= AGY_ARDISIK_DUR and not self.agy_kapali:
                        self.agy_kapali = True
                        self.notlar.append(f"NOT agy {AGY_ARDISIK_DUR} ardışık kalıcı/kota hatası: bu koşuda agy durdu "
                                           f"(kalan agy öğeleri engel; kapı için SOR T4 / ork kota --agy)")
        if aski:
            self.agy_kapali = True
            if self.durum_yaz and not self.kuru:
                kota.durum_yaz({"agy_otomatik_kapali": {"neden": "403", "zaman": kay["zaman"]}})
            self.notlar.append("agy 403/askı: otomatik yol kapandı, kalan agy öğeleri iptal (SOR T4)")
            return "engel", js, "kalici", "403/askı"
        if basari:
            return "ok", js, None, None
        if kod in (1, 2):
            sonuc = ("hata", js, "kota" if AGY_KOTA_DESEN.search(hata_metni) else "kalici",
                     (err or "")[-200:] or f"çıkış {kod}")
        elif kod == 3 or kod == 124:
            sonuc = ("gecici", js, "gecici", (err or "")[-200:] or "model hatası/zaman aşımı")
        elif js and js.get("denied_actions"):
            sonuc = ("reddedildi", js, "kalici", "başsız modda araç reddedildi")
        else:
            sonuc = ("hata", js, "kota" if AGY_KOTA_DESEN.search(hata_metni) else "bilinmiyor",
                     "SUCCESS ama boş yanıt" if (js or {}).get("status") == "SUCCESS" else
                     ((err or "")[-200:] or "boş stdout"))
        return sonuc

    def _agy(self, o, metin, h):
        kip = h.get("kip") or ("accept-edits" if o.get("medya") else "plan")
        istem = (DUSUNME_ONEKI + "\n\n" + metin) if kip == "plan" else metin
        tahmin = float(o.get("tahmin_dk") or 5)
        sure = max(15.0, 3 * tahmin)
        deneme = 0
        d, js, hs, neden = self._agy_cagir([o["id"]], istem, h, kip, sure)
        if d == "reddedildi":                                     # tek önekli yeniden deneme
            deneme += 1
            d, js, hs, neden = self._agy_cagir([o["id"]], DUSUNME_ONEKI + "\n\n" + metin, h, "plan", sure)
        elif d == "gecici":
            deneme += 1
            d, js, hs, neden = self._agy_cagir([o["id"]], istem, h, kip, sure * 1.5)
        u = (js or {}).get("usage") or {}
        tok = {"giris": u.get("input_tokens"), "cikis": u.get("output_tokens")}
        if d == "ok":
            yan = js.get("response") or json.dumps(js.get("structured"), ensure_ascii=False)
            self._olc(o, h.get("kimlik") or h.get("model"), h.get("efor"), "ok", tok, deneme=deneme)
            return {"durum": "ok", "_metin": yan, "model": f"{h.get('model')}@{h.get('efor')}",
                    "havuz": h.get("havuz"), "tok": tok, "deneme": deneme}
        self._olc(o, h.get("kimlik") or h.get("model"), h.get("efor"), "hata", tok, None, hs, deneme=deneme)
        return {"durum": "engel" if d == "engel" else ("bekle" if d == "bekle" else "hata"), "ozet": neden,
                "hata": hs, "model": f"{h.get('model')}@{h.get('efor')}", "deneme": deneme}

    def _agy_toplu(self, grup):
        """Aynı (model, efor, kip) mikro öğeler tek çağrıda (n × sabit yük yerine 1 ×)."""
        temiz = []
        for o in grup:
            m = _metin(o.get("brief"))
            e = self._gizlilik(o, m)
            if e:
                self.sonuclar[o["id"]] = {"id": o["id"], "durum": "engel", "ozet": e}
            else:
                temiz.append((o, m))
        if not temiz:
            return
        if self.kuru:
            for o, _ in temiz:
                self.sonuclar[o["id"]] = {"id": o["id"], "durum": "ok", "ozet": "KURU: toplu agy öğesi, istek yok"}
            return
        h = temiz[0][0]["hedef"]
        istem = (DUSUNME_ONEKI + "\nHer öğeyi bağımsız yanıtla. Biçim: her öğe için '### ÖĞE <id>' başlığı ve altında "
                 "yanıt.\n\n" + "\n\n".join(f"### ÖĞE {o['id']}\n{m}" for o, m in temiz))
        sema = skill_kok() / "data" / "sema" / "agy-toplu.schema.json"
        d, js, hs, neden = self._agy_cagir([o["id"] for o, _ in temiz], istem, h, "plan", 15, sema=sema)
        if d != "ok":
            for o, _ in temiz:
                self._olc(o, h.get("kimlik") or h.get("model"), h.get("efor"), "hata", None, None, hs)
                self.sonuclar[o["id"]] = {"id": o["id"], "durum": "engel" if d == "engel" else "hata", "ozet": neden,
                                          "hata": hs}
            return
        parcalar = toplu_ayristir(js, [o["id"] for o, _ in temiz])
        for o, _ in temiz:
            y = parcalar.get(o["id"])
            if y is None:
                self._olc(o, h.get("kimlik") or h.get("model"), h.get("efor"), "hata", None, None, "bilinmiyor")
                self.sonuclar[o["id"]] = {"id": o["id"], "durum": "hata", "ozet": "toplu yanıtta öğe yok"}
                continue
            self._olc(o, h.get("kimlik") or h.get("model"), h.get("efor"), "ok" if str(y).strip() else "hata")
            r = {"id": o["id"], "durum": "ok", "model": f"{h.get('model')}@{h.get('efor')}", "havuz": h.get("havuz"),
                 "toplu": len(temiz), "_metin": y, "ozet": _ozet_satiri(y)}
            if o.get("cikti"):
                r["cikti"] = _yaz(o["cikti"], y)
            self.sonuclar[o["id"]] = r

    # ---------------------------------------------------------- Codex
    def _ikili(self, pid):
        from . import kesif
        p = self.veri.platformlar.get(pid, {})
        imza = next((x for x in kesif.imza_listesi(self.veri.imzalar) if x.get("id") == (p.get("imza") or pid)), None)
        if not imza:
            return None
        b = kesif.ikili_coz(imza) if imza.get("appx") else kesif.ikili_bul(imza.get("ikili"))
        return (b or {}).get("yol")

    def _codex(self, o, metin, h):
        pid = h["platform"]
        p = (self.veri.platformlar_ham.get("platformlar") or {}).get(pid) or {}
        c = p.get("cagri") or {}
        sab = c.get("argv")
        if not sab:
            return {"durum": "hata", "ozet": "platform cagri.argv şablonu yok", "hata": "kalici"}
        exe = self._ikili(pid)
        if not exe:
            return {"durum": "hata", "ozet": "ikili bulunamadı", "hata": "kalici"}
        cikti = o.get("cikti") or str(_kayit_yolu(f"suru/{self.plan.get('is_id') or 'is'}/{o['id']}.md"))
        Path(cikti).parent.mkdir(parents=True, exist_ok=True)
        sandbox = c.get("sandbox_duzenleme", "workspace-write") if o.get("duzenle") else \
            c.get("sandbox_varsayilan", "read-only")
        alan = {"ikili": exe, "kimlik": h.get("model") or h.get("kimlik"), "efor": h.get("efor"), "sandbox": sandbox,
                "cikti": cikti}
        argv = _doldur(sab, alan)
        ayar = self.suru_ayari(pid)
        sem = self._semafor(pid, ayar.get("hesap_eszamanli_kullan") or 2)
        bas = self.saat.simdi()
        cikar = set(c.get("auth_yedek_cikar") or [])
        argv2 = [x for x in argv if x not in cikar] if cikar else None
        yedek_kayitli = bool((((kota.durum_oku().get("cagri_ayar") or {}).get(pid)) or {}).get("auth_yedek"))
        zs = float(o.get("zaman_asimi_sn") or ayar.get("zaman_asimi_sn") or 900)
        env = temiz_ortam(self.veri)
        auth_deneme = 0
        with sem:
            if yedek_kayitli and argv2:
                # önceki koşuda yalıtılmış giriş başarısızdı: boşa ikinci başlatma yok, doğrudan yedek
                kod, out, err = self.t.surec(argv2, metin, zs, env=env)
                self._auth_notu(pid)
            else:
                kod, out, err = self.t.surec(argv, metin, zs, env=env)
                if kod != 0 and argv2 and re.search(r"(?i)401|not logged in|unauthori", (err or "") + (out or "")):
                    auth_deneme = 1
                    kod, out, err = self.t.surec(argv2, metin, zs, env=env)
                    self._auth_notu(pid)
                    if self.durum_yaz and not self.kuru:
                        kota.durum_guncelle(lambda d: d.setdefault("cagri_ayar", {}).setdefault(pid, {}).update(
                            {"auth_yedek": True}))
        sure = round(self.saat.simdi() - bas, 1)
        tok = {}
        for satir in (out or "").splitlines()[::-1]:
            try:
                ev = json.loads(satir)
            except ValueError:
                continue
            u = ev.get("usage") or (ev.get("msg") or {}).get("usage") if isinstance(ev, dict) else None
            if isinstance(u, dict):
                tok = {"giris": u.get("input_tokens"), "cikis": u.get("output_tokens")}
                break
        if kod == 0:
            try:
                yan = Path(cikti).read_text(encoding="utf-8")
            except OSError:
                yan = ""
            durum_c = "ok" if yan.strip() else "hata"
            self._olc(o, h.get("kimlik") or h.get("model"), h.get("efor"), durum_c, tok, sure,
                      None if yan.strip() else "bilinmiyor", auth_deneme)
            return {"durum": durum_c, "_metin": None, "cikti": cikti, "deneme": auth_deneme,
                    "ozet": _ozet_satiri(yan) if yan.strip() else "boş çıktı", "model": f"{alan['kimlik']}@{alan['efor']}",
                    "havuz": h.get("havuz"), "tok": tok, "sure_sn": sure}
        s = kota.hata_sinifla((err or "") + (out or "")[-500:], None)
        if s["sinif"] in ("kota", "kapasite") and self.durum_yaz and not self.kuru:
            kota.hata_isle(h.get("havuz") or pid, (err or "")[-500:], None, kimlik=alan["kimlik"])
        self._olc(o, h.get("kimlik") or h.get("model"), h.get("efor"), "hata", tok, sure, s["sinif"], auth_deneme)
        return {"durum": "hata", "ozet": f"çıkış {kod} ({s['sinif']})", "hata": s["sinif"],
                "model": f"{alan['kimlik']}@{alan['efor']}", "deneme": auth_deneme}

    def _auth_notu(self, pid):
        n = (f"NOT {pid}: yalıtılmış giriş başarısız; kullanıcı yapılandırması ve kullanıcı düzeyi talimat dosyası "
             f"(AGENTS.md) yüklenerek çalıştırıldı")
        with self.kilit:
            if n not in self.notlar:
                self.notlar.append(n)

    # ---------------------------------------------------------- desenler
    def _oy_hedefleri(self, o):
        h = o["hedef"]
        out = [h]
        for x in o.get("adaylar") or (self.suru_ayari(h["platform"]).get("oy_adaylari") or []):
            m, _, e = str(x.get("model") if isinstance(x, dict) else x).partition("@")
            if m and m != h.get("model"):
                h2 = dict(h, model=m, kimlik=m, efor=(x.get("efor") if isinstance(x, dict) else e) or None)
                if self.hedef_denetle(h2):              # yasak/kapalı oy adayı ya da yargıç atlanır
                    continue
                out.append(h2)
        return out[:max(int(o.get("k") or 3), 2)]

    def _oy(self, o, metin):
        """Kapalı cevaplı iş: ilk iki uyuşursa üçüncü yok; çoğunluk; üçü ayrışırsa `kismi` + yükselt."""
        desen = re.compile(o.get("cevap_deseni") or r"(?s)(.*)")
        hedefler = self._oy_hedefleri(o)
        cevaplar, sonuclar = [], []

        def cevap(r):
            m = desen.search(r.get("_metin") or "")
            return (m.group(1) if m and m.groups() else (m.group(0) if m else "")).strip().lower()
        for n, h in enumerate(hedefler):
            if n == 2 and len(cevaplar) == 2 and cevaplar[0] == cevaplar[1]:
                break
            r = self._tek(o, metin, hedef=h, yaz=False)
            sonuclar.append(r)
            if r.get("durum") == "ok":
                cevaplar.append(cevap(r))
        sayim = collections.Counter(c for c in cevaplar if c)
        if not sayim:
            return {"id": o["id"], "durum": "hata", "ozet": "oy: geçerli cevap yok", "deneme": len(sonuclar)}
        en, n = sayim.most_common(1)[0]
        kazanan = next(r for r in sonuclar if r.get("durum") == "ok" and cevap(r) == en)
        if o.get("cikti"):
            _yaz(o["cikti"], kazanan.get("_metin"))
        durum = "ok" if n >= 2 else "kismi"
        return {"id": o["id"], "durum": durum, "model": kazanan.get("model"), "cikti": o.get("cikti"),
                "ozet": f"oy {n}/{len(cevaplar)}: {en[:120]}" + ("" if n >= 2 else " · ayrıştı: yükselt"),
                "deneme": len(sonuclar), "oy_cagri": len(sonuclar)}

    def _aday_yargic(self, o, metin):
        """Testli kod/kısa metin: k aday; yargıç yerel test (shell=False); geçen ilk aday kabul."""
        hedefler = self._oy_hedefleri(o)
        dog = o.get("dogrulama") or {}
        for n, h in enumerate(hedefler):
            r = self._tek(o, metin, hedef=h, yaz=False)
            if r.get("durum") != "ok":
                continue
            yol = o.get("cikti") or str(_kayit_yolu(f"suru/{o['id']}-aday{n}.txt"))
            _yaz(yol, r.get("_metin"))
            if dog.get("tur") != "test":
                return {"id": o["id"], "durum": "ok", "model": r.get("model"), "cikti": yol, "ozet": r.get("ozet") or
                        _ozet_satiri(r.get("_metin")), "deneme": n + 1}
            g, cikis = self._test(dog, yol)
            if g:
                return {"id": o["id"], "durum": "ok", "model": r.get("model"), "cikti": yol, "deneme": n + 1,
                        "ozet": _ozet_satiri(r.get("_metin")), "dogrulama": {"tur": "test", "sonuc": "gecti"}}
        return {"id": o["id"], "durum": "kismi", "ozet": "aday_yargic: test geçen aday yok · yükselt", "deneme":
                len(hedefler), "dogrulama": {"tur": "test", "sonuc": "kaldi"}}

    def _test(self, dog, cikti):
        """Yerel test yargıcı: komut listesi, kabuk yok, `python` -> bu yorumlayıcı + -I, zaman aşımı. Model çıktısı
        güvenilmezdir (bedava kamu API dahil): test geçici bir klasördeki KOPYA üzerinde, sırsız ortamla ve o klasör
        çalışma dizini olarak koşar (proje dizini ve anahtarlar görünmez). Ağ kapatılamaz: test komutu çıktıyı o
        klasör dışında içe aktarmamalı (references/suru.md)."""
        komut = list(dog.get("komut") or [])
        if not komut:
            return False, "komut yok"
        if komut[0] in ("python", "python3", "py"):
            komut = [sys.executable, "-I"] + komut[1:]
        tmp = tempfile.mkdtemp(prefix="ork-test-")
        try:
            kopya = ""
            if cikti and Path(str(cikti)).is_file():
                kopya = str(Path(tmp) / Path(str(cikti)).name)
                shutil.copy2(str(cikti), kopya)
            komut = [str(x).replace("{cikti}", kopya or str(cikti or "")) for x in komut]
            kod, out, err = self.t.surec(komut, None, float(dog.get("zaman_asimi_sn") or 120), cwd=tmp,
                                         env=temiz_ortam(self.veri, {"PYTHONNOUSERSITE": "1"}))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        return kod == 0, (out + err)[-300:]

    # ---------------------------------------------------------- özet
    def _ozet(self, isler, claude, sure):
        sayac = collections.Counter()
        satirlar = []
        kfark = collections.defaultdict(float)
        for o in isler:
            r = self.sonuclar.get(o["id"])
            if not r:
                continue
            d = r.get("durum", "hata")
            sayac[d if d in ("ok", "kismi", "engel", "hata", "bekle") else "hata"] += 1
            s = {k: v for k, v in r.items() if not k.startswith("_") and v is not None}
            s["ozet"] = str(s.get("ozet") or "")[:200]
            satirlar.append(s)
            tok = r.get("tok") or {}
            h = o.get("hedef") or {}
            K, _, birim = self.veri.K_p(h.get("havuz") or "", "gun")
            if birim == "token" and K and (tok.get("giris") or tok.get("cikis")):
                kfark[f"{h.get('havuz')}.gun"] -= ((tok.get("giris") or 0) + (tok.get("cikis") or 0)) / K
        cl = []
        for o in claude:
            h = o["hedef"]
            cl.append({"id": o["id"], "cagri": h.get("cagri") or (f"Agent(subagent_type=\"general-purpose\", model="
                                                                 f"{h.get('takma') or h.get('model')}, effort={h.get('efor')}, "
                                                                 f"prompt=<{o.get('brief')}>)"),
                       "sozlesme": f"çıktıyı {o.get('cikti') or '<dosya>'} dosyasına yaz, en çok 10 satır özet dön"})
        notlar = list(self.notlar)
        ao, _, teyit = self._agy_ayari()
        if any((o.get("hedef") or {}).get("yol") == "agy-oto" for o in isler) and not teyit:
            notlar.append("NOT agy otomatik: askı riski ifadesi kullanıcıya teyit ettirilmedi (teyitsiz profil)")
        ozet = {"is_id": self.plan.get("is_id"), "sure_sn": sure,
                "sayac": {k: sayac.get(k, 0) for k in ("ok", "kismi", "engel", "hata", "bekle")},
                "isler": satirlar, "claude_isleri": cl,
                "kota_farki_tahmini": {k: round(v, 5) for k, v in kfark.items()},
                "claude_tasarruf_usd_e": self.plan.get("claude_tasarruf_usd_e"), "notlar": notlar}
        return ozet_kirp(ozet)


def toplu_ayristir(js, idler):
    """Toplu agy yanıtı: şemalı alan ({"ogeler": [{id, yanit}]}) ya da metindeki '### ÖĞE <id>' blokları."""
    st = (js or {}).get("structured")
    if isinstance(st, dict) and isinstance(st.get("ogeler"), list):
        return {str(x.get("id")): x.get("yanit") for x in st["ogeler"] if isinstance(x, dict)}
    metin = (js or {}).get("response") or ""
    try:
        d = json.loads(metin)
        if isinstance(d, dict) and isinstance(d.get("ogeler"), list):
            return {str(x.get("id")): x.get("yanit") for x in d["ogeler"] if isinstance(x, dict)}
    except ValueError:
        pass
    out = {}
    bloklar = re.split(r"(?m)^#{2,4}\s*ÖĞE\s+(\S+)\s*$", metin)
    for n in range(1, len(bloklar) - 1, 2):
        out[bloklar[n].strip()] = bloklar[n + 1].strip()
    return {k: v for k, v in out.items() if k in set(idler)}


def ozet_kirp(ozet, tavan=OZET_TAVAN):
    """Özet JSON'u tavanı aşarsa önce öğe özetleri kısalır, sonra öğe ayrıntısı yalnız kimlik + durum kalır."""
    def boy(x):
        return len(json.dumps(x, ensure_ascii=False).encode("utf-8"))
    if boy(ozet) <= tavan:
        return ozet
    for n in (100, 40, 0):
        for s in ozet["isler"]:
            s["ozet"] = s.get("ozet", "")[:n]
        if boy(ozet) <= tavan:
            return ozet
    ozet["isler"] = [{"id": s["id"], "durum": s.get("durum")} for s in ozet["isler"]]
    while boy(ozet) > tavan and ozet["isler"]:
        ozet["isler"].pop()
        ozet["kirpildi"] = True
    return ozet


# ================================================================== CLI
def suru_kayit_yolu(is_id):
    return durum_dizini() / "suru" / f"{is_id or 'is'}-ozet.json"


def temizle(gun=7, uygula=False, veri=None, _tasi=None):
    """Koşucunun yazdığı agy konuşma kimliklerine ait dosyalar (platform `konusma_dizini` globu) Geri Dönüşüm
    Kutusu'na taşınır; yalnız kullanıcı çalıştırınca, varsayılan yalnız listeler."""
    veri = veri or Veri.yukle()
    sinir = simdi_utc() - timedelta(days=gun)
    kimlikler = {x.get("conversation_id") for x in _jsonl_oku(_kayit_yolu("agy-cagri.jsonl"))
                 if x.get("conversation_id") and (zaman_coz(x.get("zaman")) or sinir) < sinir}
    desenler = [p.get("konusma_dizini") for p in (veri.platformlar_ham.get("platformlar") or {}).values()
                if isinstance(p, dict) and p.get("konusma_dizini")]
    import glob
    dosyalar = []
    for d in desenler:
        for f in glob.glob(os.path.expanduser(os.path.expandvars(d))):
            kok = os.path.basename(f).split(".", 1)[0]          # tam dosya kökü (alt dize değil)
            if kok in kimlikler:
                dosyalar.append(f)
    tasinan = []
    if uygula:
        for f in dosyalar:
            if (_tasi or _geri_donusum)(f):
                tasinan.append(f)
    return {"aday": len(dosyalar), "tasinan": len(tasinan), "kimlik": len(kimlikler)}


def _geri_donusum(yol):
    """Yol komut metnine gömülmez (tırnak enjeksiyonu yok): betik bloğuna argüman olarak geçer."""
    if os.name != "nt":
        return False
    ps = ("& { param($p) Add-Type -AssemblyName Microsoft.VisualBasic; "
          "[Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile($p,'OnlyErrorDialogs','SendToRecycleBin') }")
    try:
        return subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps, str(yol)],
                              capture_output=True, timeout=30).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def main(argv=None):
    ap = argparse.ArgumentParser(prog="ork suru", description="Dış işçileri tek çağrıda paralel yürütür (ince lider).")
    alt = ap.add_subparsers(dest="eylem", required=True)
    c = alt.add_parser("calistir")
    c.add_argument("--plan", required=True)
    c.add_argument("--paralel", type=int)
    c.add_argument("--kuru", action="store_true", help="tarama + çözüm; istek yok")
    c.add_argument("--dusus", choices=["izinli", "yok"], default="izinli")
    c.add_argument("--sef", help="şef model:efor tavanı (R16); verilmezse plan > oturum kaydı > algılama")
    c.add_argument("--tavan-yok", dest="tavan_yok", action="store_true", help="kullanıcı tavanı açıkça kaldırdı")
    c.add_argument("--json", action="store_true")
    d = alt.add_parser("durum")
    d.add_argument("--is", dest="is_id", required=True)
    t = alt.add_parser("temizle")
    t.add_argument("--agy", action="store_true", required=True)
    t.add_argument("--gun", type=int, default=7)
    t.add_argument("--uygula", action="store_true", help="Geri Dönüşüm Kutusu'na taşı (yoksa yalnız listeler)")
    a = ap.parse_args(argv)
    if a.eylem == "durum":
        x = json_oku(suru_kayit_yolu(a.is_id))
        print(json.dumps(x or {"durum": "yok"}, ensure_ascii=False))
        return 0
    if a.eylem == "temizle":
        print(json.dumps(temizle(a.gun, a.uygula), ensure_ascii=False))
        return 0
    plan = json_oku(a.plan)
    if not isinstance(plan, dict):
        print("HATA plan okunamadı")
        return 3
    if isinstance(plan.get("suru_plani"), dict):            # `ork sec --plan` çıktısı doğrudan verilebilir
        plan = dict(plan["suru_plani"], claude_tasarruf_usd_e=(plan.get("tasarruf") or {}).get("tasarruf_usd_e"))
    veri = Veri.yukle()
    # R16 (ork sec --plan ile aynı): açık --sef plan değerini ezer; yoksa plan ile oturum şefinin sıkı olanı
    from . import secici
    sef, notlar = araclar.sef_belirle(veri, kota.durum_oku(), acik=a.sef, kuru=a.kuru)
    for n in notlar:
        print(f"NOT {n}", file=sys.stderr)
    if a.sef:
        plan = dict(plan, sef=sef)
    elif sef or plan.get("sef"):
        try:
            plan = dict(plan, sef=secici.sef_siki(sef, plan.get("sef"), veri)[0])
        except secici.SecimHatasi as e:
            print(f"HATA plan şefi çözülemedi: {e}")
            return 3
    if a.tavan_yok:
        plan = dict(plan, tavan_yok=True)
    an = kota.oku(veri, yaz=not a.kuru)          # açık hedeflerin taban/kapalı denetimi için taze anlık
    taze_okuyucu = (lambda v: kota.oku(v, onbellek=False, yaz=not a.kuru))
    ozet = Kosucu(plan, veri=veri, kuru=a.kuru, dusus=a.dusus, paralel=a.paralel, kota_anlik=an,
                  kota_okuyucu=taze_okuyucu).calistir()
    if not a.kuru:                               # kuru kip dosya yazmaz
        try:
            atomik_yaz(suru_kayit_yolu(plan.get("is_id")), ozet)
        except OSError:
            pass
    print(json.dumps(ozet, ensure_ascii=False))
    return 0 if not ozet["sayac"].get("hata") else 1
