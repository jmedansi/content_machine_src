# Content Machine — Architecture

## Vue d'ensemble

Système automatisé de création et publication de contenus sur 3 plateformes (Facebook, LinkedIn, Twitter/X) avec IA (Groq, Gemini, Kimi).

## Architecture

```
D:\Content_Machine\
├── core/                 # Infrastructure centrale
│   ├── config.py         # Variables d'environnement, paths
│   ├── db.py             # SQLAlchemy models (Account, Post, AccessLink)
│   ├── llm_router.py     # Routage LLM multi-provider (Groq→OpenAI→Anthropic→DeepSeek)
│   ├── groq_router.py    # Rotation clés API Groq + backoff 429
│   ├── gemini_router.py  # Gemini API rate-limiting (RPM/TPM)
│   ├── paths.py          # Paths canoniques (ROOT, DATA_DIR, DB_PATH, per-platform)
│   ├── logger.py         # Logger JSON structuré + rotation
│   ├── models.py         # Pydantic models (TaskCreate, TaskStatus, AccountCreate)
│   ├── task_tracker.py   # Suivi tâches SQLite (generate/validate/publish)
│   ├── notifier.py       # Notifications webhook/Telegram
│   ├── github_upload.py  # Upload contenu vers GitHub
│   ├── shared/
│   │   ├── base.py       # Abstract base: PlatformType, ContentType, PlatformABC
│   │   └── loader.py     # Plugin loader dynamique
│   ├── routes/           # Routes API FastAPI
│   │   ├── accounts.py   # CRUD comptes
│   │   ├── content_routes.py    # Listing/filtrage contenu
│   │   ├── generation_routes.py # Génération via LLM
│   │   ├── platform_routes.py   # Endpoints par plateforme
│   │   ├── status_routes.py     # Health/status
│   │   ├── validation_routes.py # Approve/reject contenu
│   │   └── api_helpers.py       # Helpers, erreurs, pagination
│   └── platforms/        # Adaptateurs plateforme
│       ├── facebook/     # Facebook Graph API adapter
│       ├── linkedin/     # LinkedIn UGC API adapter
│       └── twitter/      # Twitter/X v2 API adapter
│
├── common/               # Services partagés
│   ├── adapters/
│   │   ├── fb_adapter.py # Facebook Graph API (publish, upload, DM)
│   │   ├── li_adapter.py # LinkedIn UGC API (register, upload, carousel)
│   │   └── tw_adapter.py # Twitter v2 API (tweet, thread, media)
│   ├── services/
│   │   ├── text_generator.py # Génération LLM avec persona prompts + few-shot
│   │   └── api_client.py     # Client HTTP générique (requests + retry)
│   └── utils/
│       ├── persona_loader.py # Charge personas YAML/JSON
│       ├── smart_scheduler.py # Calcul créneaux optimaux
│       └── migration_tool.py  # Migration dossiers legacy → UUID
│
├── api/                  # Serveur API unifié (FastAPI)
│   ├── server.py         # App FastAPI + CORS
│   ├── routes/           # Enregistrement routes
│   └── schemas/          # Pydantic schemas request/response
│
├── scheduler/            # Système de planification
│   ├── unified.py        # Boucle principale: polls tasks → dispatch platforms
│   ├── topic_sync.py     # Sync topics Google Sheets/DB → per-account stores
│   ├── models.py         # Pydantic: ScheduledTask, TaskStatus, PlatformType
│   ├── canonical.py      # Paths canoniques pour accounts/content/meta
│   └── strategies/       # Stratégies d'ordonnancement
│       ├── FIFOStrategy
│       ├── PriorityStrategy
│       └── PersonaRoundRobin
│
├── orchestrator.py       # Point d'entrée principal
│                         # ContentOrchestrator: init platforms → dispatch generate/publish
│
├── machines/             # Pipeline par plateforme
│   ├── facebook_machine/
│   │   ├── main.py       # Orchestrateur FB: topic→copywriter→image→publisher
│   │   ├── agents/
│   │   │   ├── copywriter/agent.py     # Rédaction posts IA (persona-driven)
│   │   │   ├── image_creator/          # Génération images Gemini (Playwright)
│   │   │   ├── publisher/agent.py      # Publication Graph API
│   │   │   ├── scheduler/agent.py      # Planification créneaux FB
│   │   │   ├── topic_finder/agent.py   # Suggestions sujets IA
│   │   │   ├── video_maker/agent.py    # Pipeline Reels (TTS+subtitles+scenes)
│   │   │   │   └── engine/             # Moteur vidéo
│   │   │   │       ├── tts_engine.py        # Text-to-speech (Edge TTS/gTTS)
│   │   │   │       ├── subtitle_engine.py   # Générateur SRT/ASS
│   │   │   │       ├── slide_renderer.py    # Rendu slides → images
│   │   │   │       ├── cinema_compositor.py # Compositeur final (moviepy)
│   │   │   │       ├── scene_director.py    # Directeur de composition
│   │   │   │       ├── scene_sequencer.py   # Ordonnancement + timing
│   │   │   │       ├── script_generator.py  # Scripts vidéo via LLM
│   │   │   │       ├── gsap_renderer.py     # Animations GSAP (Playwright)
│   │   │   │       ├── lottie_library.py    # Bibliothèque animations Lottie
│   │   │   │       ├── lottie_downloader.py # Téléchargement Lottie
│   │   │   │       ├── lottie_bulk_downloader.py
│   │   │   │       ├── sfx_engine.py        # Sound effects
│   │   │   │       ├── sfx_generator.py     # Synthèse SFX (pydub)
│   │   │   │       └── chart_renderer.py    # Rendu graphiques (matplotlib)
│   │   │   ├── analytics/agent.py      # Insights Facebook
│   │   │   ├── memory/agent.py         # Mémoire contenu (évite répétition)
│   │   │   ├── group_poster/agent.py   # Publication groupes FB
│   │   │   └── twitter_publisher/agent.py # Cross-post FB→Twitter
│   │   ├── core/         # ⚠️ DUPLIQUÉ de core/ racine (garder racine)
│   │   ├── publisher/    # API Graph bas niveau
│   │   ├── tools/        # Scraper, login Playwright
│   │   ├── scripts/      # Sync FS→DB
│   │   └── accounts/     # Dossiers par compte (persona + content)
│   │
│   ├── linkedin_machine/
│   │   ├── main.py       # Orchestrateur LI: topics→writer→publisher
│   │   ├── agents/
│   │   │   ├── agent_writer.py         # Rédaction LinkedIn (carousel support)
│   │   │   ├── agent_publisher.py      # Publication UGC LinkedIn
│   │   │   ├── agent_topics.py         # Sujets LinkedIn pro
│   │   │   ├── agent_memory.py         # Mémoire contenu
│   │   │   ├── carousel_writer.py      # Génération carrousels/PDF
│   │   │   ├── image_generator.py      # Images pour posts
│   │   │   ├── google_sheets_utils.py  # Intégration Google Sheets
│   │   │   └── scheduler/agent.py      # Planification LI
│   │   ├── remotion-engine/            # Rendu carrousels (Node.js/Remotion)
│   │   └── accounts/     # Dossiers par compte
│   │
│   └── twitter_machine/
│       ├── main.py       # Orchestrateur TW: topics→writer→publisher
│       └── agents/
│           ├── agent_writer.py         # Rédaction tweets (single + thread)
│           ├── agent_publisher.py      # Publication v2 API
│           ├── agent_topics.py         # Sujets hashtags + trending
│           ├── persona_loader.py       # Personas TW
│           └── scheduler/agent.py      # Planification TW
│
├── shared_agents/        # Agents multi-plateformes (réutilisables)
│   ├── models.py         # Pydantic: AgentResult, ContentType, Persona
│   ├── copywriter/agent.py    # Copywriter générique (persona+platform agnostic)
│   ├── topic_finder/agent.py  # Moteur suggestions sujets
│   ├── photographer/agent.py  # Wrapper génération images (Gemini)
│   ├── scheduler/agent.py     # Ordonnancement cross-platform
│   └── video_maker/           # Moteur vidéo complet
│       ├── agent.py           # Orchestrateur vidéo
│       └── engine/            # 14 fichiers (identiques à fb_machine/agents/video_maker/engine)
│
├── dashboard/            # Dashboard web
│   ├── dashboard_api_v2.py   # FastAPI dashboard (comptes, tâches, contenu, planning)
│   ├── start_dashboard.py    # Lancement serveur uvicorn
│   ├── api/topics_store.py   # Stockage sujets (JSON-backed, per-platform per-account)
│   ├── templates/            # HTML templates
│   ├── css/, js/            # Frontend statique
│   └── check_*.py           # Scripts inspection DB
│
├── gateway/              # Webhooks & tunnels
│   ├── webhook_server.py     # Récepteur webhooks FB/LI
│   ├── webhook_monitor/agent.py # Agent monitoring commentaires (→ DM)
│   ├── start_tunnel.py       # Cloudflare tunnel
│   └── run_webhook_forever.py # Auto-restart webhook
│
├── gemini_dashboard_pro/ # Génération images Gemini
│   ├── app.py            # FastAPI app Gemini
│   ├── gemini_engine.py  # Playwright→Gemini (prompt→image)
│   └── watermark_tool.py # Suppression watermark
│
├── lib/                  # Utilitaires
│   ├── content_io.py     # Écritures atomiques, meta.json, checksum
│   └── db_utils.py       # Helpers SQLite bas niveau
│
├── tests/                # Suite de tests
│   ├── test_e2e.py                 # Tests plateforme loader + orchestrateur
│   ├── test_e2e_integration.py     # Tests pipeline: generate→validate→publish
│   ├── test_llm_router.py          # Tests LLM router
│   ├── test_linkedin_publisher.py  # Tests publisher LinkedIn
│   ├── test_content_io.py          # Tests content_io
│   ├── test_planning_api.py        # Tests API planning
│   ├── test_lab_merge.py           # Sanity lab template
│   └── run_topic_test.py           # Test manuel topic suggestions
│
├── tools/                # Scripts dev/ops
│   ├── print_accounts.py  # Afficher comptes depuis DB
│   ├── migrate_supervisor.py # Migration avec backup
│   └── check_dbs.py       # Inspecteur DB rapide
│
├── generate_formats.py   # Génération multi-formats (HTML, MD, TXT)
├── canva_linkedin.py     # Export carrousels Canva
└── google_slides_linkedin.py # Export carrousels Google Slides
```

## Flow principal

1. **Topic Discovery** : `topic_finder` génère des sujets via LLM
2. **Copywriting** : `copywriter` rédige le contenu avec persona
3. **Image** : `image_creator` génère l'image via Gemini
4. **Validation** : contenu soumis pour approbation
5. **Publication** : `publisher` publie via l'adaptateur plateforme
6. **Monitoring** : `analytics` + `webhook_monitor` track l'engagement

## Dépendances clés

- **LLM** : Groq (principal), Gemini (images), Kimi (backup)
- **APIs** : Facebook Graph API, LinkedIn UGC API, Twitter v2 API
- **DB** : SQLite via SQLAlchemy (`content_machine.db`)
- **Scheduling** : Google Sheets (topics) + SQLite (tâches)
- **Vidéo** : MoviePy, Edge TTS, Playwright (GSAP/Lottie)
- **Serveur** : FastAPI (API + dashboard + webhooks)

## Patterns

- **Adaptateurs** : 1 adaptateur par plateforme (fb/li/tw) dans `common/adapters/`
- **Agents** : 1 agent par fonction (copywriter, publisher, scheduler, etc.)
- **Personas** : JSON/YAML dans `accounts/*/persona/` avec `system_prompt.md` + `config.json`
- **Contenu** : dossiers UUID dans `accounts/*/content/` avec `meta.json` + fichiers média
- **Scheduler** : 3 stratégies (FIFO, Priority, PersonaRoundRobin) avec créneaux optimaux

## Note sur duplication

Le dossier `machines/facebook_machine/core/` est une copie de `core/` racine.
**À conserver** : la version racine (source de vérité).
Le moteur vidéo existe en 2 copies quasi-identiques : `shared_agents/video_maker/engine/` et `machines/facebook_machine/agents/video_maker/engine/`.
**À conserver** : `shared_agents/video_maker/engine/` (référence).
