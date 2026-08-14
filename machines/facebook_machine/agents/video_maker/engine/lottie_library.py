# lottie_library.py -- Bibliotheque Lottie etendue : B2B + compte perso
# Chaque keyword a plusieurs URLs candidates (fallbacks)
# Le downloader teste toutes les candidates et garde la premiere valide

from pathlib import Path

LOTTIE_LOCAL_DIR = Path(__file__).parent.parent / "assets" / "lottie"
LOTTIE_BULK_DIR  = LOTTIE_LOCAL_DIR / "bulk"

# ---------------------------------------------------------------------------
# BULK MAP : keyword -> fichier unique dans assets/lottie/bulk/
# 84 keywords x 84 fichiers DISTINCTS (113 disponibles, 0 doublons)
# Sources : useAnimations GitHub (ua_*) + LottieFiles CDN (cdn_*)
# ---------------------------------------------------------------------------
KEYWORD_TO_BULK = {
    # Finance / Tarifs
    "invoice":      "cdn_lf20_jcikwtux",
    "money":        "cdn_lf20_06a6pf9i",
    "payment":      "cdn_lf20_t9gkkhz4",
    "revenue":      "cdn_lf20_qm8eqzse",
    "growth":       "cdn_lf20_touohxv0",
    "chart":        "cdn_lf20_V9t630",
    "trending_up":  "ua_arrowUp",
    "savings":      "ua_archive",
    "investment":   "cdn_lf20_2m1smtya",
    "budget":       "cdn_lf20_4fET62",
    # Clients / Relations
    "clients":      "cdn_lf20_DMgKk1",
    "happy":        "cdn_lf20_obhph3sh",
    "handshake":    "cdn_lf20_pqnfmone",
    "team":         "cdn_lf20_7ex5ufle",
    "satisfaction": "ua_thumbUp",
    "trust":        "ua_lock",
    # Succès
    "success":      "cdn_lf20_jbrw3hcz",
    "trophy":       "cdn_lf20_puciaact",
    "star":         "ua_star",
    "winner":       "cdn_lf20_7zara4iv",
    "celebrate":    "cdn_lf20_rovf9gzu",
    "check":        "ua_checkmark",
    # Formation / Apprentissage
    "learning":     "cdn_lf20_fcfjwiyb",
    "book":         "ua_bookmark",
    "idea":         "ua_info",
    "skills":       "cdn_lf20_xyadoh9h",
    "student":      "cdn_lf20_8sn2ymow",
    # Temps / Productivité
    "time":         "cdn_lf20_xlmz9xwm",
    "clock":        "ua_calendar",
    "productivity": "ua_loading",
    "focus":        "ua_zoomIn",
    # Freelance / Business
    "freelance":    "cdn_lf20_9WL4VQ",
    "laptop":       "ua_edit",
    "business":     "cdn_lf20_9ZfVw0",
    "negotiation":  "cdn_lf20_FISfBK",
    "work":         "ua_folder",
    "strategy":     "ua_settings",
    "leadership":   "cdn_lf20_ISbOsd",
    "branding":     "cdn_lf20_QpeChC",
    "innovation":   "ua_plusToX",
    # Motivation / Mindset
    "motivation":   "cdn_lf20_RItkEz",
    "mindset":      "cdn_lf20_UJNc2t",
    "inspiration":  "cdn_lf20_bshezgfo",
    "courage":      "cdn_lf20_dmd1gncl",
    "perseverance": "ua_infinity",
    "discipline":   "cdn_lf20_fj8rlma5",
    # Santé / Sport
    "sport":        "ua_activity",
    "health":       "cdn_lf20_fwgp2r4s",
    "running":      "cdn_lf20_gb5bmwlm",
    "fitness":      "cdn_lf20_gr2cHM",
    "food":         "cdn_lf20_i9mxcD",
    "sleep":        "cdn_lf20_syqnfe7c",
    # Amour / Famille
    "love":         "ua_heart",
    "heart":        "cdn_lf20_ioxyd2gs",
    "family":       "ua_home",
    "friendship":   "cdn_lf20_lmceydcv",
    "couple":       "cdn_lf20_lxd6qbf3",
    "community":    "cdn_lf20_mjuuisyd",
    # Emotions
    "joy":          "cdn_lf20_mrg9xhbm",
    "sad":          "cdn_lf20_nc99k6bp",
    "smile":        "cdn_lf20_opn6z1qt",
    "surprise":     "cdn_lf20_pKiaUR",
    "laugh":        "cdn_lf20_prxhhnpq",
    # Culture / Lifestyle
    "music":        "ua_volume",
    "dance":        "ua_playPause",
    "travel":       "ua_explore",
    "africa":       "cdn_lf20_qj6ywemr",
    "world":        "cdn_lf20_sefbiwsx",
    "party":        "cdn_lf20_tn8qikk9",
    # Spiritualité
    "meditation":   "cdn_lf20_tnt528ff",
    "prayer":       "cdn_lf20_tzjfwgud",
    "peace":        "cdn_lf20_u4j3xm6r",
    "nature":       "cdn_lf20_v4yd7sef",
    # Tech / IA
    "tech":         "cdn_lf20_vowsuuvc",
    "ai":           "cdn_lf20_zPo7NV",
    "coding":       "ua_github",
    "phone":        "cdn_lf20_zyquagfl",
    "internet":     "cdn_lf20_zwath9pn",
    # CTA / UI
    "cta":          "ua_share",
    "arrow_down":   "ua_arrowDown",
    "fire":         "cdn_lf20_jicJD5",
    "rocket":       "cdn_lf20_qp1q7mct",
    "gift":         "ua_download",
    "notification": "ua_notification",
    # Alertes / Statuts
    "alert":        "ua_alertCircle",
    "warning":      "ua_alertTriangle",
    "checkbox":     "ua_checkBox",
    "error":        "ua_error",
    "help":         "ua_help",
    "menu":         "ua_menu",
    "menu2":        "ua_menu2",
    "menu3":        "ua_menu3",
    "menu4":        "ua_menu4",
    "search":       "ua_searchToX",
    "settings2":    "ua_settings2",
    "toggle":       "ua_toggle",
    "trash":        "ua_trash",
    "trash2":       "ua_trash2",
    "scroll":       "ua_scrollDown",
    "zoom_out":     "ua_zoomOut",
    "visibility":   "ua_visibility",
    "radio":        "ua_radioButton",
    # Social / Médias
    "facebook":     "ua_facebook",
    "instagram":    "ua_instagram",
    "linkedin":     "ua_linkedin",
    "twitter":      "ua_twitter",
    # Communication
    "email":        "ua_mail",
    "microphone":   "ua_microphone",
    "video":        "ua_video",
    "loading2":     "ua_loading2",
    "loading3":     "ua_loading3",
    "notification2":"ua_notification2",
    # Extra CDN
    "wallet":       "ua_youtube",
}

# ---------------------------------------------------------------------------
# CANDIDATES : keyword -> liste d'URLs a tester (ordre de priorite)
# ---------------------------------------------------------------------------
LOTTIE_CANDIDATES = {

    # ── Finance / Tarifs (B2B) ───────────────────────────────────────────
    "invoice":      ["https://assets9.lottiefiles.com/packages/lf20_jcikwtux.json",
                     "https://assets3.lottiefiles.com/packages/lf20_sbts4qng.json"],
    "money":        ["https://assets2.lottiefiles.com/packages/lf20_06a6pf9i.json",
                     "https://assets9.lottiefiles.com/packages/lf20_atqzipf0.json"],
    "payment":      ["https://assets9.lottiefiles.com/packages/lf20_t9gkkhz4.json",
                     "https://assets6.lottiefiles.com/packages/lf20_ikga4ytd.json"],
    "revenue":      ["https://assets4.lottiefiles.com/packages/lf20_touohxv0.json",
                     "https://assets5.lottiefiles.com/packages/lf20_V9t630.json"],
    "growth":       ["https://assets4.lottiefiles.com/packages/lf20_touohxv0.json",
                     "https://assets1.lottiefiles.com/packages/lf20_qm8eqzse.json"],
    "chart":        ["https://assets1.lottiefiles.com/packages/lf20_qm8eqzse.json",
                     "https://assets5.lottiefiles.com/packages/lf20_V9t630.json"],
    "trending_up":  ["https://assets5.lottiefiles.com/packages/lf20_V9t630.json",
                     "https://assets4.lottiefiles.com/packages/lf20_touohxv0.json"],
    "savings":      ["https://assets9.lottiefiles.com/packages/lf20_atqzipf0.json",
                     "https://assets2.lottiefiles.com/packages/lf20_06a6pf9i.json"],
    "investment":   ["https://assets1.lottiefiles.com/packages/lf20_qm8eqzse.json",
                     "https://assets4.lottiefiles.com/packages/lf20_touohxv0.json"],
    "budget":       ["https://assets9.lottiefiles.com/packages/lf20_jcikwtux.json",
                     "https://assets2.lottiefiles.com/packages/lf20_06a6pf9i.json"],

    # ── Clients / Relations (B2B) ────────────────────────────────────────
    "clients":      ["https://assets2.lottiefiles.com/packages/lf20_DMgKk1.json",
                     "https://assets9.lottiefiles.com/packages/lf20_pqnfmone.json"],
    "happy":        ["https://assets3.lottiefiles.com/packages/lf20_obhph3sh.json",
                     "https://assets9.lottiefiles.com/packages/lf20_jbrw3hcz.json"],
    "handshake":    ["https://assets9.lottiefiles.com/packages/lf20_pqnfmone.json",
                     "https://assets2.lottiefiles.com/packages/lf20_DMgKk1.json"],
    "team":         ["https://assets2.lottiefiles.com/packages/lf20_DMgKk1.json",
                     "https://assets9.lottiefiles.com/packages/lf20_pqnfmone.json"],
    "satisfaction": ["https://assets9.lottiefiles.com/packages/lf20_jbrw3hcz.json",
                     "https://assets3.lottiefiles.com/packages/lf20_obhph3sh.json"],
    "trust":        ["https://assets9.lottiefiles.com/packages/lf20_pqnfmone.json",
                     "https://assets9.lottiefiles.com/packages/lf20_jbrw3hcz.json"],

    # ── Succes / Trophee (B2B + perso) ──────────────────────────────────
    "success":      ["https://assets9.lottiefiles.com/packages/lf20_jbrw3hcz.json",
                     "https://assets4.lottiefiles.com/packages/lf20_puciaact.json"],
    "trophy":       ["https://assets4.lottiefiles.com/packages/lf20_puciaact.json",
                     "https://assets9.lottiefiles.com/packages/lf20_jbrw3hcz.json"],
    "star":         ["https://assets3.lottiefiles.com/packages/lf20_obhph3sh.json",
                     "https://assets4.lottiefiles.com/packages/lf20_puciaact.json"],
    "winner":       ["https://assets4.lottiefiles.com/packages/lf20_puciaact.json",
                     "https://assets4.lottiefiles.com/packages/lf20_touohxv0.json"],
    "celebrate":    ["https://assets9.lottiefiles.com/packages/lf20_rovf9gzu.json",
                     "https://assets4.lottiefiles.com/packages/lf20_puciaact.json"],
    "check":        ["https://assets9.lottiefiles.com/packages/lf20_jbrw3hcz.json",
                     "https://assets3.lottiefiles.com/packages/lf20_obhph3sh.json"],

    # ── Formation / Apprentissage ────────────────────────────────────────
    "learning":     ["https://assets9.lottiefiles.com/packages/lf20_fcfjwiyb.json",
                     "https://assets9.lottiefiles.com/packages/lf20_xyadoh9h.json"],
    "book":         ["https://assets9.lottiefiles.com/packages/lf20_fcfjwiyb.json",
                     "https://assets9.lottiefiles.com/packages/lf20_xyadoh9h.json"],
    "idea":         ["https://assets9.lottiefiles.com/packages/lf20_fcfjwiyb.json",
                     "https://assets9.lottiefiles.com/packages/lf20_syqnfe7c.json"],
    "skills":       ["https://assets9.lottiefiles.com/packages/lf20_xyadoh9h.json",
                     "https://assets9.lottiefiles.com/packages/lf20_fcfjwiyb.json"],
    "student":      ["https://assets9.lottiefiles.com/packages/lf20_fcfjwiyb.json",
                     "https://assets9.lottiefiles.com/packages/lf20_xyadoh9h.json"],

    # ── Temps / Productivite ─────────────────────────────────────────────
    "time":         ["https://assets9.lottiefiles.com/packages/lf20_xlmz9xwm.json",
                     "https://assets9.lottiefiles.com/packages/lf20_qp1q7mct.json"],
    "clock":        ["https://assets9.lottiefiles.com/packages/lf20_xlmz9xwm.json",
                     "https://assets9.lottiefiles.com/packages/lf20_syqnfe7c.json"],
    "productivity": ["https://assets9.lottiefiles.com/packages/lf20_qp1q7mct.json",
                     "https://assets9.lottiefiles.com/packages/lf20_xlmz9xwm.json"],
    "focus":        ["https://assets9.lottiefiles.com/packages/lf20_syqnfe7c.json",
                     "https://assets9.lottiefiles.com/packages/lf20_qp1q7mct.json"],

    # ── Freelance / Business (B2B) ───────────────────────────────────────
    "freelance":    ["https://assets9.lottiefiles.com/packages/lf20_xyadoh9h.json",
                     "https://assets9.lottiefiles.com/packages/lf20_qp1q7mct.json"],
    "laptop":       ["https://assets9.lottiefiles.com/packages/lf20_fcfjwiyb.json",
                     "https://assets9.lottiefiles.com/packages/lf20_xyadoh9h.json"],
    "business":     ["https://assets9.lottiefiles.com/packages/lf20_qp1q7mct.json",
                     "https://assets2.lottiefiles.com/packages/lf20_DMgKk1.json"],
    "negotiation":  ["https://assets9.lottiefiles.com/packages/lf20_pqnfmone.json",
                     "https://assets2.lottiefiles.com/packages/lf20_DMgKk1.json"],
    "work":         ["https://assets9.lottiefiles.com/packages/lf20_qp1q7mct.json",
                     "https://assets9.lottiefiles.com/packages/lf20_xyadoh9h.json"],
    "strategy":     ["https://assets9.lottiefiles.com/packages/lf20_qp1q7mct.json",
                     "https://assets1.lottiefiles.com/packages/lf20_qm8eqzse.json"],
    "leadership":   ["https://assets2.lottiefiles.com/packages/lf20_DMgKk1.json",
                     "https://assets9.lottiefiles.com/packages/lf20_pqnfmone.json"],
    "branding":     ["https://assets4.lottiefiles.com/packages/lf20_puciaact.json",
                     "https://assets3.lottiefiles.com/packages/lf20_obhph3sh.json"],
    "innovation":   ["https://assets9.lottiefiles.com/packages/lf20_fcfjwiyb.json",
                     "https://assets9.lottiefiles.com/packages/lf20_syqnfe7c.json"],

    # ── Motivation / Mindset (perso) ─────────────────────────────────────
    "motivation":   ["https://assets9.lottiefiles.com/packages/lf20_jbrw3hcz.json",
                     "https://assets4.lottiefiles.com/packages/lf20_touohxv0.json",
                     "https://assets4.lottiefiles.com/packages/lf20_puciaact.json"],
    "mindset":      ["https://assets9.lottiefiles.com/packages/lf20_syqnfe7c.json",
                     "https://assets9.lottiefiles.com/packages/lf20_fcfjwiyb.json"],
    "inspiration":  ["https://assets3.lottiefiles.com/packages/lf20_obhph3sh.json",
                     "https://assets9.lottiefiles.com/packages/lf20_jbrw3hcz.json"],
    "courage":      ["https://assets4.lottiefiles.com/packages/lf20_puciaact.json",
                     "https://assets4.lottiefiles.com/packages/lf20_touohxv0.json"],
    "perseverance": ["https://assets9.lottiefiles.com/packages/lf20_jbrw3hcz.json",
                     "https://assets4.lottiefiles.com/packages/lf20_touohxv0.json"],
    "discipline":   ["https://assets9.lottiefiles.com/packages/lf20_xlmz9xwm.json",
                     "https://assets9.lottiefiles.com/packages/lf20_qp1q7mct.json"],

    # ── Sante / Sport (perso) ────────────────────────────────────────────
    "sport":        ["https://assets9.lottiefiles.com/packages/lf20_qp1q7mct.json",
                     "https://assets9.lottiefiles.com/packages/lf20_xyadoh9h.json"],
    "health":       ["https://assets9.lottiefiles.com/packages/lf20_jbrw3hcz.json",
                     "https://assets3.lottiefiles.com/packages/lf20_obhph3sh.json"],
    "running":      ["https://assets9.lottiefiles.com/packages/lf20_qp1q7mct.json",
                     "https://assets9.lottiefiles.com/packages/lf20_xyadoh9h.json"],
    "fitness":      ["https://assets9.lottiefiles.com/packages/lf20_qp1q7mct.json",
                     "https://assets9.lottiefiles.com/packages/lf20_xyadoh9h.json"],
    "food":         ["https://assets3.lottiefiles.com/packages/lf20_obhph3sh.json",
                     "https://assets9.lottiefiles.com/packages/lf20_rovf9gzu.json"],
    "sleep":        ["https://assets9.lottiefiles.com/packages/lf20_syqnfe7c.json",
                     "https://assets9.lottiefiles.com/packages/lf20_xlmz9xwm.json"],

    # ── Amour / Famille / Relations (perso) ─────────────────────────────
    "love":         ["https://assets3.lottiefiles.com/packages/lf20_obhph3sh.json",
                     "https://assets9.lottiefiles.com/packages/lf20_rovf9gzu.json"],
    "heart":        ["https://assets3.lottiefiles.com/packages/lf20_obhph3sh.json",
                     "https://assets9.lottiefiles.com/packages/lf20_jbrw3hcz.json"],
    "family":       ["https://assets2.lottiefiles.com/packages/lf20_DMgKk1.json",
                     "https://assets9.lottiefiles.com/packages/lf20_pqnfmone.json"],
    "friendship":   ["https://assets9.lottiefiles.com/packages/lf20_pqnfmone.json",
                     "https://assets2.lottiefiles.com/packages/lf20_DMgKk1.json"],
    "couple":       ["https://assets3.lottiefiles.com/packages/lf20_obhph3sh.json",
                     "https://assets9.lottiefiles.com/packages/lf20_pqnfmone.json"],
    "community":    ["https://assets2.lottiefiles.com/packages/lf20_DMgKk1.json",
                     "https://assets9.lottiefiles.com/packages/lf20_pqnfmone.json"],

    # ── Emotions (perso) ─────────────────────────────────────────────────
    "joy":          ["https://assets9.lottiefiles.com/packages/lf20_rovf9gzu.json",
                     "https://assets3.lottiefiles.com/packages/lf20_obhph3sh.json"],
    "sad":          ["https://assets9.lottiefiles.com/packages/lf20_jbrw3hcz.json",
                     "https://assets3.lottiefiles.com/packages/lf20_obhph3sh.json"],
    "smile":        ["https://assets3.lottiefiles.com/packages/lf20_obhph3sh.json",
                     "https://assets9.lottiefiles.com/packages/lf20_rovf9gzu.json"],
    "surprise":     ["https://assets9.lottiefiles.com/packages/lf20_rovf9gzu.json",
                     "https://assets3.lottiefiles.com/packages/lf20_obhph3sh.json"],
    "laugh":        ["https://assets3.lottiefiles.com/packages/lf20_obhph3sh.json",
                     "https://assets9.lottiefiles.com/packages/lf20_rovf9gzu.json"],

    # ── Culture / Musique / Voyage (perso) ──────────────────────────────
    "music":        ["https://assets9.lottiefiles.com/packages/lf20_rovf9gzu.json",
                     "https://assets3.lottiefiles.com/packages/lf20_obhph3sh.json"],
    "dance":        ["https://assets9.lottiefiles.com/packages/lf20_rovf9gzu.json",
                     "https://assets3.lottiefiles.com/packages/lf20_obhph3sh.json"],
    "travel":       ["https://assets9.lottiefiles.com/packages/lf20_qp1q7mct.json",
                     "https://assets4.lottiefiles.com/packages/lf20_touohxv0.json"],
    "africa":       ["https://assets4.lottiefiles.com/packages/lf20_touohxv0.json",
                     "https://assets2.lottiefiles.com/packages/lf20_DMgKk1.json"],
    "world":        ["https://assets4.lottiefiles.com/packages/lf20_touohxv0.json",
                     "https://assets1.lottiefiles.com/packages/lf20_qm8eqzse.json"],
    "party":        ["https://assets9.lottiefiles.com/packages/lf20_rovf9gzu.json",
                     "https://assets4.lottiefiles.com/packages/lf20_puciaact.json"],

    # ── Spiritualite / Meditation (perso) ────────────────────────────────
    "meditation":   ["https://assets9.lottiefiles.com/packages/lf20_syqnfe7c.json",
                     "https://assets9.lottiefiles.com/packages/lf20_xlmz9xwm.json"],
    "prayer":       ["https://assets9.lottiefiles.com/packages/lf20_syqnfe7c.json",
                     "https://assets3.lottiefiles.com/packages/lf20_obhph3sh.json"],
    "peace":        ["https://assets9.lottiefiles.com/packages/lf20_syqnfe7c.json",
                     "https://assets3.lottiefiles.com/packages/lf20_obhph3sh.json"],
    "nature":       ["https://assets9.lottiefiles.com/packages/lf20_syqnfe7c.json",
                     "https://assets4.lottiefiles.com/packages/lf20_touohxv0.json"],

    # ── Tech / IA (perso + B2B) ──────────────────────────────────────────
    "tech":         ["https://assets9.lottiefiles.com/packages/lf20_fcfjwiyb.json",
                     "https://assets9.lottiefiles.com/packages/lf20_xyadoh9h.json"],
    "ai":           ["https://assets9.lottiefiles.com/packages/lf20_syqnfe7c.json",
                     "https://assets9.lottiefiles.com/packages/lf20_fcfjwiyb.json"],
    "coding":       ["https://assets9.lottiefiles.com/packages/lf20_fcfjwiyb.json",
                     "https://assets9.lottiefiles.com/packages/lf20_xyadoh9h.json"],
    "phone":        ["https://assets9.lottiefiles.com/packages/lf20_qp1q7mct.json",
                     "https://assets9.lottiefiles.com/packages/lf20_fcfjwiyb.json"],
    "internet":     ["https://assets4.lottiefiles.com/packages/lf20_touohxv0.json",
                     "https://assets9.lottiefiles.com/packages/lf20_fcfjwiyb.json"],

    # ── CTA / UI ─────────────────────────────────────────────────────────
    "cta":          ["https://assets3.lottiefiles.com/packages/lf20_obhph3sh.json",
                     "https://assets9.lottiefiles.com/packages/lf20_rovf9gzu.json"],
    "arrow_down":   ["https://assets9.lottiefiles.com/packages/lf20_rovf9gzu.json",
                     "https://assets3.lottiefiles.com/packages/lf20_obhph3sh.json"],
    "fire":         ["https://assets9.lottiefiles.com/packages/lf20_rovf9gzu.json",
                     "https://assets4.lottiefiles.com/packages/lf20_puciaact.json"],
    "rocket":       ["https://assets4.lottiefiles.com/packages/lf20_touohxv0.json",
                     "https://assets4.lottiefiles.com/packages/lf20_puciaact.json"],
    "gift":         ["https://assets9.lottiefiles.com/packages/lf20_rovf9gzu.json",
                     "https://assets3.lottiefiles.com/packages/lf20_obhph3sh.json"],
    "notification": ["https://assets9.lottiefiles.com/packages/lf20_jbrw3hcz.json",
                     "https://assets9.lottiefiles.com/packages/lf20_rovf9gzu.json"],

    # ── Alertes / Statuts ────────────────────────────────────────────────
    "alert":        ["https://assets9.lottiefiles.com/packages/lf20_jbrw3hcz.json"],
    "warning":      ["https://assets9.lottiefiles.com/packages/lf20_jbrw3hcz.json"],
    "checkbox":     ["https://assets9.lottiefiles.com/packages/lf20_jbrw3hcz.json"],
    "error":        ["https://assets9.lottiefiles.com/packages/lf20_jbrw3hcz.json"],
    "help":         ["https://assets9.lottiefiles.com/packages/lf20_fcfjwiyb.json"],
    "menu":         ["https://assets9.lottiefiles.com/packages/lf20_qp1q7mct.json"],
    "menu2":        ["https://assets9.lottiefiles.com/packages/lf20_qp1q7mct.json"],
    "menu3":        ["https://assets9.lottiefiles.com/packages/lf20_qp1q7mct.json"],
    "menu4":        ["https://assets9.lottiefiles.com/packages/lf20_qp1q7mct.json"],
    "search":       ["https://assets9.lottiefiles.com/packages/lf20_fcfjwiyb.json"],
    "settings2":    ["https://assets9.lottiefiles.com/packages/lf20_qp1q7mct.json"],
    "toggle":       ["https://assets9.lottiefiles.com/packages/lf20_jbrw3hcz.json"],
    "trash":        ["https://assets9.lottiefiles.com/packages/lf20_jbrw3hcz.json"],
    "trash2":       ["https://assets9.lottiefiles.com/packages/lf20_jbrw3hcz.json"],
    "scroll":       ["https://assets9.lottiefiles.com/packages/lf20_rovf9gzu.json"],
    "zoom_out":     ["https://assets9.lottiefiles.com/packages/lf20_fcfjwiyb.json"],
    "visibility":   ["https://assets9.lottiefiles.com/packages/lf20_syqnfe7c.json"],
    "radio":        ["https://assets9.lottiefiles.com/packages/lf20_jbrw3hcz.json"],

    # ── Social / Médias ──────────────────────────────────────────────────
    "facebook":     ["https://assets9.lottiefiles.com/packages/lf20_rovf9gzu.json"],
    "instagram":    ["https://assets3.lottiefiles.com/packages/lf20_obhph3sh.json"],
    "linkedin":     ["https://assets2.lottiefiles.com/packages/lf20_DMgKk1.json"],
    "twitter":      ["https://assets9.lottiefiles.com/packages/lf20_rovf9gzu.json"],

    # ── Communication ────────────────────────────────────────────────────
    "email":        ["https://assets9.lottiefiles.com/packages/lf20_fcfjwiyb.json"],
    "microphone":   ["https://assets9.lottiefiles.com/packages/lf20_qp1q7mct.json"],
    "video":        ["https://assets9.lottiefiles.com/packages/lf20_xyadoh9h.json"],
    "loading2":     ["https://assets9.lottiefiles.com/packages/lf20_syqnfe7c.json"],
    "loading3":     ["https://assets9.lottiefiles.com/packages/lf20_syqnfe7c.json"],
    "notification2":["https://assets9.lottiefiles.com/packages/lf20_jbrw3hcz.json"],

    # ── Extra CDN ────────────────────────────────────────────────────────
    "wallet":       ["https://assets9.lottiefiles.com/packages/lf20_atqzipf0.json"],
}

# ---------------------------------------------------------------------------
# LOTTIE_MAP : priorité bulk/ > local_map.json > CDN candidats
# ---------------------------------------------------------------------------
def _build_map() -> dict:
    """
    Construit LOTTIE_MAP pour chaque keyword :
      1. Fichier bulk unique (KEYWORD_TO_BULK) si présent -> file:// URI
      2. Sinon local_map.json (anciens téléchargements)
      3. Sinon première candidate CDN (fallback)
    """
    import json

    # Charger l'ancienne local_map
    local_map_file = LOTTIE_LOCAL_DIR / "local_map.json"
    local_map = {}
    if local_map_file.exists():
        try:
            local_map = json.loads(local_map_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    result = {}
    for keyword, candidates in LOTTIE_CANDIDATES.items():
        # Priorité 1 : fichier bulk unique
        bulk_key = KEYWORD_TO_BULK.get(keyword)
        if bulk_key:
            bulk_path = LOTTIE_BULK_DIR / f"{bulk_key}.json"
            if bulk_path.exists():
                result[keyword] = bulk_path.as_uri()
                continue

        # Priorité 2 : local_map.json (anciens fichiers racine)
        if keyword in local_map and Path(local_map[keyword]).exists():
            result[keyword] = Path(local_map[keyword]).as_uri()
            continue

        # Priorité 3 : CDN fallback
        result[keyword] = candidates[0]

    return result


LOTTIE_MAP = _build_map()

# ---------------------------------------------------------------------------
# KEYWORD_TRIGGERS : mots du texte -> keyword Lottie
# ---------------------------------------------------------------------------
KEYWORD_TRIGGERS = {
    # Finance / B2B
    "tarif":        "invoice",
    "prix":         "invoice",
    "facture":      "invoice",
    "devis":        "invoice",
    "salaire":      "money",
    "argent":       "money",
    "revenu":       "revenue",
    "croissance":   "growth",
    "graphique":    "chart",
    "economie":     "savings",
    "epargne":      "savings",
    "investiss":    "investment",
    "budget":       "budget",
    # Clients / B2B
    "client":       "clients",
    "satisfait":    "happy",
    "heureux":      "happy",
    "partenaire":   "handshake",
    "equipe":       "team",
    "confiance":    "trust",
    # Succes
    "succes":       "success",
    "reussi":       "success",
    "trophee":      "trophy",
    "gagner":       "winner",
    "celebr":       "celebrate",
    # Formation
    "apprend":      "learning",
    "formation":    "learning",
    "competence":   "skills",
    "etudi":        "student",
    "livre":        "book",
    "connaissance": "idea",
    # Temps / Productivite
    "temps":        "time",
    "heure":        "clock",
    "productiv":    "productivity",
    "concentr":     "focus",
    "disciplin":    "discipline",
    # Freelance / Business
    "freelance":    "freelance",
    "independant":  "freelance",
    "projet":       "laptop",
    "travail":      "work",
    "negoci":       "negotiation",
    "strateg":      "strategy",
    "leader":       "leadership",
    "innov":        "innovation",
    "brand":        "branding",
    # Motivation / Mindset
    "motiv":        "motivation",
    "inspir":       "inspiration",
    "courage":      "courage",
    "persever":     "perseverance",
    "mindset":      "mindset",
    # Sante / Sport
    "sport":        "sport",
    "sante":        "health",
    "courir":       "running",
    "fitness":      "fitness",
    "manger":       "food",
    "dormir":       "sleep",
    "sommeil":      "sleep",
    # Amour / Famille
    "amour":        "love",
    "coeur":        "heart",
    "famille":      "family",
    "ami":          "friendship",
    "couple":       "couple",
    "communaut":    "community",
    # Emotions
    "joie":         "joy",
    "triste":       "sad",
    "sourire":      "smile",
    "rire":         "laugh",
    "surpris":      "surprise",
    # Culture / Voyage
    "musique":      "music",
    "danse":        "dance",
    "voyag":        "travel",
    "afrique":      "africa",
    "monde":        "world",
    "fete":         "party",
    # Spiritualite
    "meditat":      "meditation",
    "priere":       "prayer",
    "paix":         "peace",
    "nature":       "nature",
    # Tech / IA
    "technolog":    "tech",
    "intellig":     "ai",
    "artifici":     "ai",
    "code":         "coding",
    "programm":     "coding",
    "telephone":    "phone",
    "internet":     "internet",
    # CTA
    "commente":     "cta",
    "partage":      "fire",
    "abonne":       "notification",
    "gratuit":      "gift",
    "offre":        "gift",
    "rocket":       "rocket",
    # Social / Médias
    "facebook":     "facebook",
    "instagram":    "instagram",
    "linkedin":     "linkedin",
    "twitter":      "twitter",
    # Communication
    "email":        "email",
    "mail":         "email",
    "micro":        "microphone",
    "video":        "video",
    "portefeuill":  "wallet",
    # Alertes / UI
    "alerte":       "alert",
    "erreur":       "error",
    "aide":         "help",
    "visible":      "visibility",
    "recherch":     "search",
    "supprim":      "trash",
    "chargement":   "loading2",
}


def get_lottie_url(keyword: str) -> str | None:
    return LOTTIE_MAP.get(keyword)


def detect_lottie_keyword(text: str) -> str | None:
    text_lower = text.lower()
    for trigger, keyword in KEYWORD_TRIGGERS.items():
        if trigger in text_lower:
            return keyword
    return None


def get_lottie_for_scene(scene: dict) -> str | None:
    explicit = scene.get("lottie_keyword")
    if explicit:
        url = get_lottie_url(explicit)
        if url:
            return url
    text = scene.get("title", "") + " " + scene.get("subtitle", "")
    keyword = detect_lottie_keyword(text)
    if keyword:
        return get_lottie_url(keyword)
    return None


def reload_map():
    """Recharge LOTTIE_MAP depuis local_map.json (apres download)."""
    global LOTTIE_MAP
    LOTTIE_MAP = _build_map()
