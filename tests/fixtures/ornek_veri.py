"""Sentetik test verisi (# sentetik). Gerçek data/*.json şemasının alt kümesi; sayılar bilgi tabanına yakın ama
testler yalnız bu dosyaya bağlıdır, gerçek veri değişince testler bozulmaz. Kişisel veri yok."""
import copy

Z_OLCEK = "TEST-1"


def _v(z, g, dk, **alt):
    d = {"z": z, "z_kaynak": "aa", "gorev_usd": g, "dk": dk, "kaynak": "https://ornek.invalid/aa", "okuma": "2026-11-15"}
    if alt:
        d["alt"] = alt
    return d


def _alan(puan, olcut, efor=None, ci=None):
    return {"puan": puan, "olcut": olcut, "efor": efor, "ci": ci, "kaynak": "https://ornek.invalid/olcum",
            "okuma": "2026-11-15", "guven": "B"}


def _m(sag, hat, rol, nesil, varyantlar, durum="aktif", kipler=("metin", "gorsel"), alanlar=None, bay=None, **ek):
    d = {"saglayici": sag, "hat": hat, "rol": rol, "nesil": nesil, "durum": durum, "kapanis": None,
         "kipler": {"girdi": list(kipler), "cikti": ["metin"]}, "baglam": 400000, "gorev": "chat",
         "varyantlar": varyantlar, "alanlar": alanlar or {},
         "erisim_bayraklari": bay or {"yazma_izinli_ajan": True, "olgu_isi": True}}
    d.update(ek)
    return d


MODELLER = {
    "sema": 7, "guncelleme": "2026-11-15T12:00:00Z", "z_olcek": Z_OLCEK,
    "roller": {
        "opus": {"saglayici": "anthropic", "hat": "opus", "aktif": "claude-opus-5-5"},
        "sonnet": {"saglayici": "anthropic", "hat": "sonnet", "aktif": "claude-sonnet-5-5"},
        "haiku": {"saglayici": "anthropic", "hat": "haiku", "aktif": "claude-haiku-5-5"},
        "fable": {"saglayici": "anthropic", "hat": "fable", "aktif": "claude-fable-5-2"},
        "mythos": {"saglayici": "anthropic", "hat": "mythos", "aktif": "claude-mythos-5-2"},
        "sol": {"saglayici": "openai", "hat": "sol", "aktif": "gpt-6.1-sol"},
        "terra": {"saglayici": "openai", "hat": "terra", "aktif": "gpt-6.1-terra"},
        "luna": {"saglayici": "openai", "hat": "luna", "aktif": "gpt-6-luna"},
        "astra": {"saglayici": "openai", "hat": "astra", "aktif": "gpt-6-astra"},
        "hydrogen": {"saglayici": "google", "hat": "hydrogen", "aktif": "gemini-4-hydrogen"},
        "acik": {"saglayici": "ornekai", "hat": "acik", "aktif": "acik-model-1"},
    },
    "modeller": {
        "claude-opus-5-5": _m("anthropic", "opus", "opus", "5.5", {
            "low": _v(35, 0.98, 3.1, tb4=40, briefcase=1500), "medium": _v(48, 2.45, 6.9, tb4=50, briefcase=1650),
            "high": _v(52, 3.46, 9.4, tb4=54, briefcase=1682), "xhigh": _v(57, 6.05, 15.8, tb4=56, briefcase=1690),
            "max": _v(59, 10.04, 25.4, tb4=57, briefcase=1700)},
            alanlar={"gunluk": _alan(90.3, "vals:vibe-code"), "sre": _alan(33.6, "vals:srebench"),
                     "terminal": _alan(65.2, "vals:terminal-bench"),
                     "finans_hukuk": _alan(44.5, "vals:tax_agent_bench")}),
        "claude-sonnet-5-5": _m("anthropic", "sonnet", "sonnet", "5.5", {
            "low": _v(26, 0.51, 2.6, tb4=30, briefcase=1450), "medium": _v(31, 0.78, 4.1, tb4=35, briefcase=1500),
            "high": _v(42, 1.64, 6.9, tb4=44, briefcase=1634), "xhigh": _v(50, 4.09, 14.5, tb4=48, briefcase=1660),
            "max": _v(55, 10.02, 33.3, tb4=50, briefcase=1670)},
            alanlar={"gunluk": _alan(92.4, "vals:vibe-code"), "sre": _alan(30.0, "vals:srebench"),
                     "terminal": _alan(64.1, "vals:terminal-bench")}),
        "claude-haiku-5-5": _m("anthropic", "haiku", "haiku", "5.5", {
            "low": _v(19, 0.044, 2.3), "medium": _v(25, 0.092, 4.1), "high": _v(30, 0.16, 6.6),
            "xhigh": _v(35, 0.25, 9.9), "max": _v(36, 0.41, 14.8)},
            alanlar={"gunluk": _alan(90.4, "vals:vibe-code")}),
        "claude-fable-5-2": _m("anthropic", "fable", "fable", "5.2", {
            "low": _v(54, 3.1, 5.6), "high": _v(62, 9.08, 15.5), "xhigh": _v(62, 14.83, 27.3)}),
        "claude-mythos-5-2": _m("anthropic", "mythos", "mythos", "5.2", {"high": _v(70, 5.0, 10.0)},
                                durum="onay_bekliyor", soy={"tur": "yeni_sinif", "yuva": None, "puan": -3}),
        "gpt-6.1-sol": _m("openai", "sol", "sol", "6.1", {
            "low": _v(35, 0.16, 2.0, tb4=31, briefcase=1115), "medium": _v(46, 0.36, 4.5, tb4=48, briefcase=1361),
            "high": _v(50, 0.59, 7.8, tb4=52, briefcase=1469), "xhigh": _v(52, 0.76, 10.0, tb4=53, briefcase=1504),
            "max": _v(55, 1.27, 22.9, tb4=55, briefcase=1555)},
            alanlar={"gunluk": _alan(88.9, "vals:vibe-code"), "sre": _alan(50.8, "vals:srebench"),
                     "terminal": _alan(55.1, "vals:terminal-bench"),
                     "finans_hukuk": _alan(21.8, "vals:tax_agent_bench")},
            soy={"tur": "resmi_halef", "yuva": "sol", "puan": None}),
        "gpt-6-sol": _m("openai", "sol", None, "6", {"high": _v(48, 0.9, 8.0)}, durum="eski_nesil"),
        "gpt-5.6-sol": _m("openai", "sol", None, "5.6", {"high": _v(45, 0.9, 8.0)}, durum="eski_nesil"),
        "gpt-6.1-terra": _m("openai", "terra", "terra", "6.1", {
            "none": _v(31, 0.23, 2.4), "low": _v(29, 0.071, 1.2, tb4=25), "medium": _v(38, 0.17, 2.8, tb4=36),
            "high": _v(42, 0.26, 4.3, tb4=40), "xhigh": _v(45, 0.40, 6.4, tb4=43), "max": _v(51, 0.96, 14.1, tb4=47)},
            bay={"yazma_izinli_ajan": False, "olgu_isi": True}),
        "gpt-6-luna": _m("openai", "luna", "luna", "6", {
            "low": _v(10, 0.005, 0.6), "medium": _v(18, 0.042, 3.6), "high": _v(21, 0.073, 5.8)},
            bay={"yazma_izinli_ajan": False, "olgu_isi": False}),
        "gpt-6-astra": _m("openai", "astra", "astra", "6", {
            "medium": _v(52, 2.73, 7.3), "high": _v(55, 3.24, 9.2), "xhigh": _v(55, 3.66, 11.7)}),
        "gemini-4-hydrogen": _m("google", "hydrogen", "hydrogen", "4", {
            "low": _v(27, 0.29, 1.4), "medium": _v(41, 0.8, 3.8), "high": _v(51, 1.87, 8.4)},
            kipler=("metin", "gorsel", "ses", "video", "pdf"),
            alanlar={"finans_hukuk": _alan(52.3, "vals:tax_agent_bench")},
            soy={"tur": "soy_yakin", "yuva": "flash", "puan": 2}),
        "gpt-oss-120b": _m("openai", "oss-120b", None, None, {"medium": _v(24, 0.05, 2.0)},
                           kapanis={"deger": "2026-11-18", "kaynak": "yerel", "okuma": "2026-11-15"}),
        "gemini-ornek-orchestrator-1": _m("google", "ornek-orchestrator", None, None, {}, durum="gozlem",
                                             soy={"tur": "yonlendirici", "yuva": None, "puan": None}),
        "acik-model-1": _m("ornekai", "acik", "acik", "1", {"high": _v(30, None, 3.0)}),
        "dots-ocr": _m("ornekai", "dots-ocr", None, None, {}, kipler=("gorsel", "pdf"), gorev="ocr"),
    },
    "liderler": {"sre": {"lider": "gpt-6.1-sol", "sira": ["gpt-6.1-sol@high"], "aday": None, "ardisik": 1}},
    "rotalar": {
        "video_analiz.konusmali": [
            {"yol": "agy-elle", "rol": "hydrogen", "efor": "high", "ne": "video+ses analizi"},
            {"yol": "gui-elle", "arac": "gemini-uygulamasi", "ne": "tek seferlik uzun video"},
            {"yol": "otomatik", "rol": "opus", "arac": "ffmpeg+faster-whisper-large-v3", "ne": "kare + döküm"}],
        "ses.dokum": [{"yol": "yerel", "arac": "faster-whisper-large-v3", "ne": "konuşma dökümü"},
                      {"yol": "bedava-api", "gorev": "asr", "kosul": "veri genel"}],
        "gorsel_uretim.t2i": [
            {"yol": "sabit", "rol": "sol", "efor": "high", "arac": "codex:image_gen"},
            {"yol": "gui-elle", "arac": "gemini-uygulamasi", "ne": "Codex kapalıyken"},
            {"yol": "agy-elle", "arac": "agy:generate_image", "ne": "dosya gerekiyorsa"}],
        "mekanik.toplu": [{"yol": "otomatik", "arac": "deterministik", "ne": "önce deterministik araç"}],
    },
    "gorsel_modeller": {"codex:image_gen": {"surum": None, "surum_dogrulama": "DY",
                                             "quality": ["low", "medium", "high", "auto"]}},
}

SINIFLAR = {
    "sema": 7, "z_olcek": Z_OLCEK,
    "q": {"mekanik": 16, "basit": 22, "arastirma": 38, "normal": 41, "kod": 45, "zor": 50, "kritik": 56},
    "kademeler": {"K1": [0, 28], "K2": [29, 38], "K3": [39, 48], "K4": [49, 54], "K5": [55, 59], "K6": [60, 999]},
    "zorluk_rubrigi": {"sinyaller": {"cok_dosya": "", "belirsiz_hedef": "", "geri_alinamaz": "", "olgu_riski": "",
                                     "uzun_otonom": "", "test_yok": "", "alan_uzmanligi": ""},
                       "esikler": {"0-1": "basit", "2": "normal", "3": "zor", "4+": "kritik"},
                       "tur_ozel": {"kod": "", "arastirma": ""}, "belirsizse": "bir_ust"},
    "alanlar": {"kod": ["zor_ajan", "gunluk", "terminal", "sre"], "arastirma": ["sentez", "olgu_teyit", "finans_hukuk"],
                "yazim": ["rapor"], "video_analiz": ["konusmali"], "ses": ["dokum"], "gorsel_uretim": ["t2i"],
                "mekanik": ["toplu"]},
    "alan_olcutleri": {
        "gunluk": {"birincil": "vals:vibe-code", "kapsam": "model", "delta": "doymus_yayilim"},
        "sre": {"birincil": "vals:srebench", "kapsam": "model", "delta": "vals"},
        "terminal": {"birincil": "aa:tb4", "kapsam": "varyant", "anahtar": "tb4", "delta": "aa_alt_test",
                     "ikincil": "vals:terminal-bench"},
        "rapor": {"birincil": "aa:briefcase", "kapsam": "varyant", "anahtar": "briefcase", "delta": "aa_elo"},
        "toplu": {"birincil": None, "kapsam": "z", "delta": "aa_z"},
        "finans_hukuk": {"birincil": "vals:tax_agent_bench", "kapsam": "model", "delta": "vals"},
        "konusmali": {"birincil": None, "kapsam": "rota"}, "dokum": {"birincil": None, "kapsam": "rota"},
        "t2i": {"birincil": None, "kapsam": "rota"},
    },
    "delta": {"aa_z": 2, "aa_alt_test": 3, "aa_elo": 25, "vals": 4, "scale": 3, "arena": "ci_ortusme",
              "arena_ci_yoksa": 14, "diger": 3, "uretici": 5, "doymus_yayilim": 5, "alan_olcumu_yok_carpani": 1.5},
    "efor_kurallari": {
        "_genel": {"haiku": {"taban": "medium"}},
        "gunluk": {"sol": {"taban": "medium", "tavan": "xhigh"}, "terra": {"taban": "high", "tavan": "max"},
                   "opus": {"taban": "medium", "tavan": "xhigh"}, "sonnet": {"taban": "high", "tavan": "xhigh"},
                   "haiku": {"taban": "xhigh", "tavan": "max"}},
        "terminal": {"sol": {"taban": "medium", "tavan": "xhigh"}, "terra": {"taban": "high", "tavan": "max"},
                     "opus": {"taban": "medium", "tavan": "xhigh"}, "sonnet": {"taban": "xhigh", "tavan": "max"},
                     "haiku": {"kullanma": True}},
        "rapor": {"opus": {"taban": "medium", "tavan": "high"}, "sonnet": {"taban": "high", "tavan": "xhigh"}},
        "olgu_teyit": {"luna": {"kullanma": True}},
    },
    "fazla_zeka": {"pay": 8, "genislik": 12, "tavan": 1.3},
    "ust_kademe_genisligi": 10,
    "roller_is": {"hakem": {"taban": 22, "fark": 6}},
    "is_birimi": {"kucuk": 0.3, "orta": 1, "buyuk": 3, "cok_buyuk": 10},
    "secici": {"elle_ceza": 1.3, "histerezis": 0.85, "esitlik_bandi": 0.1, "kova_adim": 0.05, "ema_alfa": 0.5,
               "ema_pencere_dk": 30, "bilinmiyor": {"k": 0.5, "maliyet_carpani": 2}, "f_sinir": [0.3, 1.0],
               "tempo_t_min": 0.05, "sure_cezasi_dk": 120, "tahmin_z_indirimi": 3,
               "tahmin_yasak_siniflar": ["zor", "kritik"], "esdeger_yaklasik_z_indirimi": 2,
               "kanit_birikimi_olcut": 2},
}

KURALLAR = {
    "sema": 7, "katman": "ornek",
    "yasak": {"saglayici_hat": ["anthropic/fable", "openai/astra"], "takma_ad": ["fable"]},
    "tabanlar": {"codex_plus": {"hafta": 0.3}, "claude_max": {"hafta": 0.3, "5s": 0.15}, "agy_*": {"hafta": 0.0},
                 "bedava": {"gun": 0.0}},
    "rezervler": {"claude_max": {"tur": "kullanilabilir_payin", "deger": 0.25, "kime": ["claude_ustun", "kritik"]},
                  "codex_plus": {"tur": "mutlak", "deger": 0.05, "kime": ["gorsel_uretim"]}},
    "faz": {"ana_havuz": "claude_max", "claude_esik_u": 0.25, "rho_gir": 0.65, "rho_cik": 0.55,
            "lider_tampon_5s": 0.10},
    "sabit_kurallar": {"gorsel_uretim": {"rol": "sol", "efor": "high", "yol": "codex:image_gen",
                                         "gerekce": "kullanıcı kuralı"}},
    "gizlilik": {"varsayilan_veri": "bilinmiyor"},
    "agy_otomatik": False,
}

PLATFORMLAR = {
    "sema": 7, "katman": "ornek", "host_varsayilan": "claude",
    "platformlar": {
        "claude": {"tur": "cli", "imza": "claude", "ucret": "abonelik", "durum": "aktif", "isci_yolu": "agent-araci", "host": True,
                   "cagri": {"tur": "agent-araci", "sablon": "Agent(subagent_type=\"general-purpose\", model={takma}, effort={efor}, prompt={brief})"},
                   "havuzlar": ["claude_max"], "erisim": {
                       "claude-opus-5-5": {"slug": "claude-opus-5-5", "eforlar": ["low", "medium", "high", "xhigh", "max"], "havuz": "claude_max", "takma": "opus"},
                       "claude-sonnet-5-5": {"slug": "claude-sonnet-5-5", "eforlar": ["low", "medium", "high", "xhigh", "max"], "havuz": "claude_max", "takma": "sonnet"},
                       "claude-haiku-5-5": {"slug": "claude-haiku-5-5", "eforlar": ["low", "medium", "high", "xhigh", "max"], "havuz": "claude_max", "takma": "haiku"},
                       "claude-fable-5-2": {"slug": "claude-fable-5-2", "eforlar": ["low", "high", "xhigh"], "havuz": "claude_max", "takma": "fable"},
                       "claude-mythos-5-2": {"slug": "claude-mythos-5-2", "eforlar": ["high"], "havuz": "claude_max"}}},
        "codex": {"tur": "cli", "imza": "codex", "ucret": "abonelik", "durum": "aktif", "isci_yolu": "codex-exec",
                  "havuzlar": ["codex_plus"],
                  "cagri": {"tur": "komut", "sablon": "{ikili} exec -m {kimlik} -c model_reasoning_effort=\"{efor}\" -s {sandbox}"},
                  "erisim": {
                      "gpt-6.1-sol": {"slug": "gpt-6.1-sol", "eforlar": ["low", "medium", "high", "xhigh", "max"], "havuz": "codex_plus"},
                      "gpt-6.1-terra": {"slug": "gpt-6.1-terra", "eforlar": ["none", "low", "medium", "high", "xhigh", "max"], "havuz": "codex_plus"},
                      "gpt-6-luna": {"slug": "gpt-6-luna", "eforlar": ["low", "medium", "high"], "havuz": "codex_plus"},
                      "gpt-6-astra": {"slug": "gpt-6-astra", "eforlar": ["medium", "high", "xhigh"], "havuz": "codex_plus"},
                      "gpt-6-sol": {"slug": "gpt-6-sol", "eforlar": ["high"], "havuz": "codex_plus"},
                      "gpt-5.6-sol": {"slug": "gpt-5.6-sol", "eforlar": ["high"], "havuz": "codex_plus"}}},
        "agy": {"tur": "cli", "imza": "agy", "ucret": "abonelik", "durum": "aktif", "isci_yolu": "agy-elle",
                "otomatik_cagri": False, "havuzlar": ["agy_gemini"], "erisim": {
                    "gemini-4-hydrogen": {"slug": "gemini-4-hydrogen-{efor}", "eforlar": ["low", "medium", "high"], "havuz": "agy_gemini"},
                    "claude-opus-5-5": {"slug": "claude-opus-5-5-{efor}", "eforlar": ["low", "medium", "high"], "havuz": "agy_gemini", "esdeger": "yaklasik", "z_duzeltme": -2},
                    "gpt-oss-120b": {"slug": "gpt-oss-120b-medium", "eforlar": ["medium"], "havuz": "agy_gemini", "kapanis": "2026-11-18"}}},
        "bedava": {"tur": "api", "imza": "openai-uyumlu", "ucret": "bedava", "durum": "aktif", "isci_yolu": "bedava-api",
                   "taban_url": "https://ornek.invalid/v1", "anahtar_env": "ORNEK_TEST_API_KEY",
                   "kota": {"tur": "uc", "yol": "/quota"}, "model_liste": {"tur": "uc", "yol": "/models"},
                   "havuzlar": ["bedava"], "bitis": "2030-01-01T03:00:00+03:00", "gizlilik": "kamu",
                   "erisim": {"acik-model-1": {"slug": "acik-model-1", "eforlar": ["high"], "havuz": "bedava"},
                              "dots-ocr": {"slug": "dots-ocr", "eforlar": [], "havuz": "bedava"}}},
        "yerel": {"tur": "yerel", "ucret": "yerel", "durum": "aktif", "isci_yolu": "yerel", "havuzlar": ["yerel"],
                  "erisim": {}},
    },
    "havuzlar": {
        "claude_max": {"platform": "claude", "pencereler": [{"ad": "5s", "uzunluk_dk": 300}, {"ad": "hafta", "uzunluk_dk": 10080}],
                       "karar": ["5s", "hafta"], "K_p": {"oncul": {"hafta": 600, "5s": None}, "kalibre": None, "birim": "USD-e"},
                       "s_p": {"varsayilan": 1.0, "claude-sonnet-5-5": 1.18}, "gizlilik": "ozel", "okuyucu": "claude_get_usage"},
        "codex_plus": {"platform": "codex", "pencereler": [{"ad": "5s", "uzunluk_dk": 300}, {"ad": "hafta", "uzunluk_dk": 10080}],
                       "karar": ["hafta"], "K_p": {"oncul": {"hafta": 35, "5s": 5.5}, "kalibre": None, "birim": "USD-e"},
                       "s_p": {"varsayilan": 1.0}, "gorsel_tur_carpani": [3, 5], "gizlilik": "ozel",
                       "okuyucu": "codex_app_server"},
        "agy_gemini": {"platform": "agy", "pencereler": [{"ad": "hafta", "uzunluk_dk": 10080}], "karar": ["hafta"],
                       "K_p": {"oncul": {"hafta": 4}, "birim": "USD-e"}, "gizlilik": "dis", "okuyucu": "agy_usage"},
        "bedava": {"platform": "bedava", "pencereler": [{"ad": "gun", "uzunluk_dk": 1440}, {"ad": "5dk", "uzunluk_dk": 5}],
                   "karar": ["gun", "5dk"], "K_p": {"oncul": {"gun_token": 1000000, "5dk_token": 200000}, "birim": "token"},
                   "bedava": True, "gizlilik": "kamu", "okuyucu": "bedava_api_quota", "bitis": "2030-01-01T03:00:00+03:00"},
        "yerel": {"platform": "yerel", "pencereler": [], "karar": [], "K_p": None, "bedava": True, "gizlilik": "ozel",
                  "okuyucu": None},
    },
}

IMZALAR = {"sema": 7, "platformlar": [], "sezgiler": {}, "kurallar": {}}


def veri_sozluk_eski():
    return copy.deepcopy({"modeller": MODELLER, "siniflar": SINIFLAR, "kullanici-kurallari": KURALLAR,
                          "platformlar": PLATFORMLAR, "imzalar": IMZALAR})


def veri_sozluk():
    return _ortak_ek(veri_sozluk_eski())


# ====================================================================== v7.1 senaryo fikstürü (# sentetik)
# Tasarım 12.1: gerçek Z/g/alt değerleriyle (AA II v5.0.1 okuması 2026-11-15) agy havuzları, bedava (genel ad) sürü
# modelleri, göreli tempo ve azalan rezerv parametreleri. Testler yalnız bu dosyaya bağlıdır.
def _v2(z, g, dk, alt=None, kaynak="aa"):
    d = {"z": z, "z_kaynak": kaynak, "gorev_usd": g, "dk": dk, "kaynak": "https://ornek.invalid/aa", "okuma": "2026-11-15"}
    if alt:
        d["alt"] = dict(alt)
    return d


def _alt(tb4, fc2, briefcase, omni, gdp_pdf):
    return {"tb4": tb4, "fc2": fc2, "briefcase": briefcase, "omni": omni, "gdp_pdf": gdp_pdf}


def _fiyat(g, o, c):
    return {"girdi": g, "onbellek": o, "cikti": c, "birim": "USD/1M"}


MODELLER_V71 = {
    "claude-opus-5-5": _m("anthropic", "opus", "opus", "5.5", {
        "low": _v2(35, 0.98, 3.1, _alt(31.3, 15.8, 1278, 39, 25.6)),
        "medium": _v2(48, 2.45, 6.9, _alt(52.5, 33.1, 1617, 40, 25.6)),
        "high": _v2(52, 3.46, 9.4, _alt(56.6, 35.9, 1682, 42, 28.8)),
        "xhigh": _v2(57, 6.05, 15.8, _alt(59.6, 43.8, 1761, 43, 26.6)),
        "max": _v2(59, 10.04, 25.4, _alt(59.6, 46.4, 1801, 48, 26.2))},
        kipler=("metin", "gorsel", "pdf"),
        alanlar={"zor_ajan": _alan(58.2, "aa:coding_agent"), "gunluk": _alan(90.3, "vals:vibe-code"),
                 "terminal": _alan(65.2, "vals:terminal-bench"), "sre": _alan(33.6, "vals:srebench"),
                 "finans_hukuk": _alan(44.5, "vals:tax_agent_bench")}, fiyat=_fiyat(4, 0.2, 20)),
    "claude-sonnet-5-5": _m("anthropic", "sonnet", "sonnet", "5.5", {
        "low": _v2(26, 0.51, 2.6, _alt(20.7, 7.1, 1268, 20, 16.0)),
        "medium": _v2(31, 0.78, 4.1, _alt(29.8, 11.0, 1437, 19, 20.2)),
        "high": _v2(42, 1.64, 6.9, _alt(43.9, 25.7, 1634, 19, 25.2)),
        "xhigh": _v2(50, 4.09, 14.5, _alt(57.1, 35.6, 1740, 21, 24.6)),
        "max": _v2(55, 10.02, 33.3, _alt(63.6, 41.7, 1816, 30, 25.8))},
        kipler=("metin", "gorsel", "pdf"),
        alanlar={"zor_ajan": _alan(56.3, "aa:coding_agent"), "gunluk": _alan(92.4, "vals:vibe-code"),
                 "terminal": _alan(64.1, "vals:terminal-bench"), "finans_hukuk": _alan(42.0, "vals:tax_agent_bench")},
        fiyat=_fiyat(2, 0.1, 10)),
    "claude-haiku-5-5": _m("anthropic", "haiku", "haiku", "5.5", {
        "low": _v2(19, 0.044, 2.3, _alt(12.6, 8.0, 1113, 2, 11.2)),
        "medium": _v2(25, 0.092, 4.1, _alt(15.2, 16.1, 1366, 4, 15.2)),
        "high": _v2(30, 0.16, 6.6, _alt(21.7, 23.2, 1441, 5, 17.2)),
        "xhigh": _v2(35, 0.25, 9.9, _alt(29.3, 29.9, 1523, 8, 18.2)),
        "max": _v2(36, 0.41, 14.8, _alt(32.8, 34.9, 1573, 12, 20.8))},
        alanlar={"gunluk": _alan(90.4, "vals:vibe-code")}, fiyat=_fiyat(0.1, 0.01, 0.5)),
    "gpt-6.1-sol": _m("openai", "sol", "sol", "6.1", {
        "low": _v2(35, 0.16, 2.0, _alt(30.8, 20.2, 1115, 38, 27.0)),
        "medium": _v2(46, 0.36, 4.5, _alt(48.0, 33.4, 1361, 40, 30.0)),
        "high": _v2(50, 0.59, 7.8, _alt(51.5, 36.7, 1469, 41, 32.0)),
        "xhigh": _v2(52, 0.76, 10.0, _alt(54.0, 38.5, 1504, 42, 31.8)),
        "max": _v2(55, 1.27, 22.9, _alt(56.1, 40.6, 1555, 42, 31.0))},
        alanlar={"zor_ajan": _alan(52.2, "aa:coding_agent"), "gunluk": _alan(88.9, "vals:vibe-code"),
                 "terminal": _alan(55.1, "vals:terminal-bench"), "sre": _alan(50.8, "vals:srebench"),
                 "finans_hukuk": _alan(21.8, "vals:tax_agent_bench")},
        soy={"tur": "resmi_halef", "yuva": "sol", "puan": None}, fiyat=_fiyat(2, 0.1, 10)),
    "gpt-6.1-terra": _m("openai", "terra", "terra", "6.1", {
        "none": _v2(31, 0.23, 2.4, _alt(26.8, 33.4, 1226, -5, 23.2)),
        "low": _v2(29, 0.071, 1.2, _alt(15.2, 24.5, 1032, 23, 25.6)),
        "medium": _v2(38, 0.17, 2.8, _alt(32.3, 34.5, 1191, 27, 28.4)),
        "high": _v2(42, 0.26, 4.3, _alt(41.9, 37.5, 1265, 28, 28.0)),
        "xhigh": _v2(45, 0.40, 6.4, _alt(46.5, 36.9, 1334, 29, 26.6)),
        "max": _v2(51, 0.96, 14.1, _alt(55.6, 42.3, 1401, 30, 28.6))},
        alanlar={"zor_ajan": _alan(48.6, "aa:coding_agent")},
        bay={"yazma_izinli_ajan": False, "olgu_isi": True}, fiyat=_fiyat(1, 0.05, 5)),
    "gemini-4-hydrogen": _m("google", "hydrogen", "hydrogen", "4", {
        "low": _v2(27, 0.29, 1.4, _alt(6.6, 9.3, 947, 36, 28.2)),
        "medium": _v2(41, 0.8, 3.8, _alt(29.3, 31.5, 1296, 42, 32.8)),
        "high": _v2(51, 1.87, 8.4, _alt(54.0, 36.3, 1497, 44, 30.0)),
        "xhigh": _v2(54, 3.16, 14.8, _alt(53.5, 39.0, 1568, 46, 27.6))},
        kipler=("metin", "gorsel", "ses", "video", "pdf"),
        alanlar={"gunluk": _alan(87.8, "vals:vibe-code", efor="xhigh"),
                 "terminal": _alan(54.0, "vals:terminal-bench"),
                 "finans_hukuk": _alan(52.3, "vals:tax_agent_bench", efor="high")},
        soy={"tur": "soy_yakin", "yuva": "flash", "puan": 2}, fiyat=_fiyat(1.5, 0.075, 7.5)),
    "gemini-4-argon": _m("google", "argon", "argon", "4", {
        "medium": _v2(48, 4.31, 28.5, _alt(55.1, 25.0, 1467, 41, 25.6)),
        "high": _v2(50, 4.97, 30.9, _alt(57.1, 25.7, 1485, 46, 21.8))},
        kipler=("metin", "gorsel", "ses", "video"),
        alanlar={"zor_ajan": _alan(45.5, "aa:coding_agent"), "terminal": _alan(57.6, "vals:terminal-bench"),
                 "sre": _alan(44.3, "vals:srebench"), "finans_hukuk": _alan(49.2, "vals:tax_agent_bench")},
        fiyat=_fiyat(2, 0.2, 10)),
    "deepseek-v4.1-flash": _m("deepseek", "deepseek-flash", "deepseek_flash", "4.1", {
        "none": _v2(19, None, 1.1), "high": _v2(29, 0.46, 1.8), "max": _v2(33, 0.6, 3.0)},
        alanlar={"gunluk": _alan(87.7, "vals:vibe-code")}, fiyat=_fiyat(0, 0, 0)),
    "qwen3.8-flash-next": _m("qwen", "qwen-flash", "qwen_flash", "3.8", {
        "low": _v2(26, None, 1.0, kaynak="tahmin"), "medium": _v2(27, None, 1.5, kaynak="tahmin"),
        "xhigh": _v2(29, 0.57, 15.0, kaynak="tahmin")}, fiyat=_fiyat(0, 0, 0)),
    "glm-5.3": _m("zhipu", "glm", "glm", "5.3", {
        "low": _v2(23, None, 2.0), "high": _v2(28, None, 4.0, kaynak="tahmin"), "max": _v2(32, 5.01, 9.0)},
        kipler=("metin",), fiyat=_fiyat(0, 0, 0)),
    "gemma-4-31b": _m("google-acik", "gemma", "gemma", "4", {"varsayilan": _v2(4, None, 0.5)}, fiyat=_fiyat(0, 0, 0)),
}

ROLLER_V71 = {"argon": {"saglayici": "google", "hat": "argon", "aktif": "gemini-4-argon"},
              "deepseek_flash": {"saglayici": "deepseek", "hat": "deepseek-flash", "aktif": "deepseek-v4.1-flash"},
              "qwen_flash": {"saglayici": "qwen", "hat": "qwen-flash", "aktif": "qwen3.8-flash-next"},
              "glm": {"saglayici": "zhipu", "hat": "glm", "aktif": "glm-5.3"},
              "gemma": {"saglayici": "google-acik", "hat": "gemma", "aktif": "gemma-4-31b"}}

V71_SINIF_EK = {
    "alan_olcutleri": {"zor_ajan": {"birincil": "aa:coding_agent", "kapsam": "model", "delta": "aa_alt_test",
                                    "ikincil": "aa:tb4"}},
    "efor_kurallari": {"zor_ajan": {"sol": {"taban": "medium", "tavan": "xhigh"}, "terra": {"taban": "high", "tavan": "max"},
                                    "opus": {"taban": "medium", "tavan": "xhigh"},
                                    "sonnet": {"taban": "xhigh", "tavan": "max"}, "haiku": {"kullanma": True},
                                    "hydrogen": {"taban": "high", "tavan": "high"}}},
}


def _v71_ek(d):
    m = d["modeller"]
    m["modeller"].update(copy.deepcopy(MODELLER_V71))
    m["roller"].update(copy.deepcopy(ROLLER_V71))
    s = d["siniflar"]
    for k, v in V71_SINIF_EK.items():
        s.setdefault(k, {}).update(copy.deepcopy(v))
    k = d["kullanici-kurallari"]
    k["agy_otomatik"] = {"acik": True, "isci_profili": {"dogrulandi": True, "kisisel_baglam_kabul": None},
                         "karar": {"tarih": "2026-11-15", "teyit_edildi": True},
                         "guvenceler": {"eszamanli": 2, "baslatma_araligi_sn": 20, "saatlik_cagri_tavani": 10,
                                        "gunluk_cagri_tavani": 30}}
    p = d["platformlar"]
    p["platformlar"]["claude"]["erisim"]["claude-haiku-5-5"]["eforlar"] = ["low", "medium", "high"]
    p["platformlar"]["claude"]["erisim"].pop("claude-fable-5-2", None)
    p["platformlar"]["codex"]["erisim"]["gpt-6.1-terra"]["eforlar"] = ["low", "medium", "high", "xhigh", "max"]
    p["platformlar"]["agy"] = {
        "tur": "cli", "imza": "agy", "ucret": "abonelik", "durum": "aktif", "isci_yolu": "agy-oto",
        "otomatik_cagri": False, "havuzlar": ["agy_gemini", "agy_claude_gpt", "agy_argon"], "gizlilik": "dis",
        "cagri": {"tur": "suru", "sablon_oto": "{ikili} -p {istem} --model {taban} --effort {efor} --mode {kip} "
                                              "--output-format json --print-timeout {sure}"},
        "erisim": {
            "gemini-4-hydrogen": {"slug": "gemini-4-hydrogen", "efor_bayragi": True,
                                  "eforlar": ["low", "medium", "high", "xhigh"], "havuz": "agy_gemini"},
            "gemini-4-argon": {"slug": "gemini-4-argon", "efor_bayragi": True, "eforlar": ["medium", "high"],
                               "havuz": "agy_argon"},
            "claude-opus-5-5": {"slug": "claude-opus-5-5", "efor_bayragi": True, "eforlar": ["low", "medium", "high"],
                                "havuz": "agy_claude_gpt", "esdeger": "yaklasik", "z_duzeltme": -2},
            "claude-sonnet-5-5": {"slug": "claude-sonnet-5-5", "efor_bayragi": True,
                                  "eforlar": ["low", "medium", "high"], "havuz": "agy_claude_gpt",
                                  "esdeger": "yaklasik", "z_duzeltme": -2},
            "gpt-oss-120b": {"slug": "gpt-oss-120b", "eforlar": ["medium"], "havuz": "agy_claude_gpt",
                             "kapanis": "2026-11-18"}}}
    p["platformlar"]["bedava"]["erisim"] = {
        "deepseek-v4.1-flash": {"slug": "deepseek-v4.1-flash", "eforlar": ["none", "high"], "havuz": "bedava",
                                "z_duzeltme": -2},
        "qwen3.8-flash-next": {"slug": "qwen3.8-flash-next", "eforlar": ["low", "medium"], "havuz": "bedava"},
        "glm-5.3": {"slug": "glm-5.3", "eforlar": ["low", "high"], "havuz": "bedava", "z_duzeltme": -2,
                    "tekil_secim": False},
        "gemma-4-31b": {"slug": "gemma-4-31b", "eforlar": ["varsayilan"], "havuz": "bedava", "tekil_secim": False,
                        "turkce_son_metin": False},
        "dots-ocr": {"slug": "dots-ocr", "eforlar": [], "havuz": "bedava"}}
    hv = p["havuzlar"]
    hv["claude_max"]["K_p"] = {"oncul": {"hafta": 600, "5s": 75}, "kalibre": None, "birim": "USD-e"}
    hv["agy_gemini"] = {"platform": "agy", "pencereler": [{"ad": "5s", "uzunluk_dk": 300},
                                                          {"ad": "hafta", "uzunluk_dk": 10080}],
                        "karar": ["hafta"], "K_p": {"oncul": {"hafta": 4.0, "5s": 4.0}, "birim": "USD-e"},
                        "cagri_sabit_yuk_token": 26000, "gizlilik": "dis", "okuyucu": "agy_usage",
                        "agy_kovalar": {"hafta": "gemini-weekly", "5s": "gemini-5h"}}
    hv["agy_claude_gpt"] = {"platform": "agy", "pencereler": [{"ad": "5s", "uzunluk_dk": 300},
                                                              {"ad": "hafta", "uzunluk_dk": 10080}],
                            "karar": ["hafta", "5s"], "K_p": {"oncul": {"hafta": 4.0, "5s": 4.0}, "birim": "USD-e"},
                            "cagri_sabit_yuk_token": 40000, "gizlilik": "dis", "okuyucu": "agy_usage",
                            "agy_kovalar": {"hafta": "3p-weekly", "5s": "3p-5h"}}
    hv["agy_argon"] = {"platform": "agy", "pencereler": [{"ad": "hafta", "uzunluk_dk": 10080}], "karar": ["hafta"],
                       "K_p": {"oncul": {"hafta": 4.0}, "birim": "USD-e"}, "s_p": {"varsayilan": 1.5},
                       "cagri_sabit_yuk_token": 31000, "gizlilik": "dis", "okuyucu": "agy_usage",
                       "agy_kovalar": {"hafta": "gemini-argon-wtu-weekly"}}
    hv["bedava"]["K_p"] = {"oncul": {"gun_token": 12000000, "5dk_token": 2000000}, "birim": "token"}
    return d


def _ortak_ek(d):
    """Eski ve yeni fikstürün ortak v7.1 parametreleri (tasarım 12.1)."""
    k = d["kullanici-kurallari"]
    k["tabanlar"]["codex_plus"] = {"hafta": 0.2}
    k["rezervler"]["codex_plus"] = {"tur": "mutlak", "deger": 0.10, "kime": ["gorsel_uretim"], "azalan": True}
    k["rezervler"]["agy_gemini"] = {"tur": "kullanilabilir_payin", "deger": 0.10, "kime": ["video_analiz", "ses"],
                                    "azalan": True}
    k["faz"].update({"tempo_agirlik": {"agy_gemini": 2.0, "agy_claude_gpt": 2.0, "agy_argon": 1.5, "codex_plus": 1.5},
                     "dis_sira": ["agy_gemini", "agy_claude_gpt", "agy_argon", "codex_plus"], "tempo_bant": 0.10,
                     "rezerv_azalma_saat": 24, "bekle_esik_dk": 45})
    k["faz"].pop("rho_gir", None)
    k["faz"].pop("rho_cik", None)
    k["agy_otomatik"] = k.get("agy_otomatik") if isinstance(k.get("agy_otomatik"), dict) else {"acik": False}
    s = d["siniflar"]
    s["doygunluk"] = {"mekanik": 2, "basit": 6}
    s["kopru"] = {"gunluk": ["aa:fc2"], "zor_ajan": ["aa:fc2", "aa:tb4"], "goc": ["aa:fc2"], "refaktor": ["aa:fc2"],
                  "web": ["aa:omni"], "sentez": ["aa:critpt"], "uzun_belge": ["aa:gdp_pdf"], "klinik": ["aa:omni"],
                  "_varsayilan": []}
    s["kanitli_kaskad"] = {"siniflar": ["arastirma", "normal"], "z_acigi": 16, "veri": ["genel"],
                           "dis_kanit": ["test_tam", "kapali_cevap", "sema_dogrulayici"], "en_cok_deneme": 2}
    s["opus_kapisi"] = {"siniflar": ["zor"], "sinyaller": ["geri_alinamaz", "olgu_riski", "alan_uzmanligi"],
                        "efor_tabani": "high", "kopru_yasak": True, "rol": "opus"}
    s["geri_bildirim"] = {"en_az_ornek": 20, "z": 1.64, "fark_esigi": 0.05}
    s["is_birimi"]["mikro"] = 0.05
    s["secici"]["kanit_birikimi_z"] = 1.0
    s["secici"]["sabit_sira"] = ["bedava", "agy", "codex", "claude"]
    return d


def veri_v71_sozluk():
    return _v71_ek(_ortak_ek(veri_sozluk_eski()))
