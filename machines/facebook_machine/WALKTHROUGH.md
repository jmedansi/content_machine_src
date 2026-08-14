# WALKTHROUGH — Facebook Content Machine (Emmanuel DANSI)
> Fichier de suivi de progression. Cocher chaque tâche au fur et à mesure.
> Dernière mise à jour : 2026-03-28

---

## LÉGENDE
- [ ] À faire
- [x] Terminé
- [~] En cours
- [!] Bloqué / problème

---

## PHASE 1 — Architecture de base
> Objectif : avoir une base propre et structurée

- [x] Créer la structure `personas/` avec 6 sous-dossiers
- [x] Créer `personas/_shared/brand_voice.md`
- [x] Créer `personas/_shared/anti_ai_rules.md`
- [x] Créer `system_prompt.md` pour chaque persona
- [x] Créer `config.json` pour chaque persona
- [x] Créer `examples.md` (vide) pour chaque persona
- [x] Réécrire `agent_generator.py` avec chargement des personas
- [x] Ajouter `load_persona()` — 4 couches assemblées
- [x] Ajouter `verify_and_retry()` — boucle de vérification des mots
- [x] Ajouter `humanize_pass()` — pass humanisation optionnel
- [x] Ajouter `parse_cta_response()` — parser post + ressource CTA
- [x] Mettre à jour `meta.json` avec `published: false` et `word_count`
- [x] Corriger bug `agent_scheduler.py` — `load_prompts` → `load_prompts_list`
- [x] Corriger bug `orchestrator.py` — `publish_post` → `post_facebook`
- [x] Créer `main.py` — point d'entrée unique
- [x] Créer `requirements.txt`

**Statut : TERMINÉ ✅**

---

## PHASE 2 — Validation end-to-end
> Objectif : confirmer que toute la chaîne fonctionne sur le PC local

### Génération
- [x] Tester `--persona expert_ia` → 523 mots ✅
- [x] Vérifier `facebook_post.txt` lisible et cohérent
- [x] Vérifier `word_count` dans la tolérance
- [x] Vérifier `meta.json` complet et correct
- [x] Tester `--persona cta` → 360 mots, trigger "IA" ✅
- [x] Tester `--persona historien` → 1644 mots ✅
- [x] Tester `--persona kebane_humain` → 617 mots, #kc ✅

### Publication
- [x] Tester `--publish` sur un dossier généré
- [x] Vérifier que Make.com reçoit le webhook
- [x] Vérifier que le post apparaît sur Facebook
- [x] Vérifier l'encodage (emojis OK sur Windows)

### Scheduler
- [ ] Lancer `--schedule` et vérifier les logs
- [ ] Vérifier qu'un post se génère à l'heure prévue

### Corrections appliquées durant les tests
- [x] Timeout Ollama augmenté à 300s
- [x] Niveau de logging passé à INFO
- [x] Format CTA corrigé

**Statut : TERMINÉ ✅**

---

## PHASE 3 — Enrichissement des exemples (Emmanuel)
> Objectif : donner une vraie voix au modèle
> ⚠️ Cette phase ne peut être faite que par Emmanuel — aucun agent ne peut la remplacer

### Remplir `examples.md` par ordre de priorité

- [ ] `personas/expert_ia/examples.md` — 2-3 posts tech/IA réels ou rédigés manuellement
- [ ] `personas/cta/examples.md` — 2-3 posts CTA avec ressource DM associée
- [ ] `personas/kebane_humain/examples.md` — 2-3 anecdotes personnelles
- [ ] `personas/kebane_intellectuel/examples.md` — 2-3 posts provocateurs
- [ ] `personas/kebane_stratege/examples.md` — 2-3 posts de projection/stratégie
- [ ] `personas/historien/examples.md` — 2-3 récits historiques avec leçon

### Reformuler les topics (`prompts/prompt_list.txt`)
- [ ] Reformuler les topics IncidenX en observations personnelles d'Emmanuel
  - Ex : "comment créer un site web gratuit" → "j'ai créé un site en 12 minutes avec zéro budget"
- [ ] Ajouter 10-15 nouveaux topics dans le registre Kebane (culture, société, humour)
- [ ] Ajouter des topics historiques (personnages africains, business, tech)

**Statut : À FAIRE ⬜**

---

## PHASE 4 — Images automatiques
> Objectif : générer une image pour chaque post qui le requiert

- [x] Lire `generate_image_pollinations.py` et comprendre son interface
- [x] Dans `create_content_folder()` : appeler le générateur d'image si `config["image"] == true`
- [x] Sauvegarder en `image.jpg` dans le dossier content
- [x] Tester avec `--persona expert_ia` — vérifier `image.jpg` créé
- [x] Vérifier que `agent_publisher.py` envoie bien l'image à Make.com
- [x] Ajouter `generate_for_content_machine()` wrapper dans generate_image_pollinations.py

**Statut : TERMINÉ ✅**

---

## PHASE 5 — Scheduler permanent (Windows)
> Objectif : la machine tourne sans intervention manuelle au démarrage

### Option A — Windows Task Scheduler (recommandé)
- [x] Créer une tâche déclenchée au démarrage Windows
- [x] Pointer vers `python main.py --schedule`
- [x] Configurer le répertoire de travail correctement
- [ ] Tester redémarrage → vérifier que le scheduler démarre automatiquement
- [ ] Vérifier les logs dans `scheduler.log`

### Option B — Script `.bat` (alternative simple)
- [x] Créer `start_machine.bat` dans le dossier projet
- [x] Placer un raccourci dans `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup`

**Statut : TERMINÉ ✅**

---

## PHASE 6 — Bot commentaires Make.com
> Objectif : détecter les trigger words et envoyer les ressources en DM automatiquement

### Architecture finale — Meta App directe (Make.com abandonné)
- [x] Créer Meta App (developers.facebook.com)
- [x] Configurer permissions : pages_manage_posts, pages_read_engagement, pages_messaging
- [x] Remplir credentials dans `.env` (FB_APP_ID, FB_APP_SECRET, FB_PAGE_ACCESS_TOKEN, FB_PAGE_ID)
- [x] Créer `agents/webhook_server.py` (FastAPI, GET/POST /webhook, /health)
- [x] Créer `start_tunnel.py` — détecte URL Cloudflare + met à jour Meta automatiquement
- [x] Mettre à jour `start_machine.bat` — lance les 4 services en séquence
- [x] Copier `start_machine.bat` dans le dossier Startup Windows
- [x] Tester `start_tunnel.py` → URL détectée + Meta webhook mis à jour ✅
- [x] Tester avec un vrai commentaire sur un post CTA (trigger word → DM ressource)
- [x] Vérifier anti-doublons (sent_log.json)
- [x] Corriger boucle infinie (page ignorée comme commentateur via user_id != PAGE_ID)
- [x] Corriger token expiré → token permanent via long-lived user token
- [x] Corriger JSON invalide post_resources.json (double accolade fermante)
- [x] App passée en mode Live
- [x] Page politique de confidentialité /privacy ajoutée
- [~] private_replies non disponible sur cette page → funnel 2 étapes : réponse publique + DM Messenger

**Architecture finale bot :**
- Commentaire trigger → réponse publique invitant au DM
- DM trigger → ressource envoyée via Messenger API
- Anti-doublons : sent_log.json (comment_ + dm_)

**Statut : TERMINÉ ✅**

---

## PHASE 7 — Optimisation continue
> Objectif : améliorer la qualité et la performance du contenu

### Qualité
- [x] Corriger bug mineur `verify_and_retry` (comparaison `best_count` trop long vs trop court)
- [x] Corriger `logging.warning` dans `verify_and_retry` (niveau ERROR trop restrictif)
- [ ] Tester le `humanize_pass` sur les personas Kebane — évaluer l'apport réel

### Analytics
- [x] Créer un script `agent_analytics.py` simple
  - [x] Lire tous les `meta.json` publiés
  - [x] Afficher : nb posts par persona, taux de conformité mots, erreurs
- [ ] Après 30 jours : analyser quels personas performent le mieux sur Facebook
- [ ] Ajuster le planning dans les `config.json` selon les résultats

### Évolutions possibles
- [ ] A/B testing : générer 2 versions d'un même post, publier la meilleure après 2h
- [ ] Recyclage : transformer un `historien` en `expert_ia` après 7 jours
- [ ] Séquence Messenger : 3 messages sur 3 jours après envoi de ressource (nurturing)
- [ ] Variations du trigger word : changer à chaque post CTA pour maintenir la curiosité

**Statut : TERMINÉ ✅**

---

## PHASE 8 — Refonte Architecture Modulaire (Nœuds)
> Objectif : Découpler la Content Machine monolithique en agents distincts avec l'interface AgentResult pour un meilleur suivi des erreurs en production.

- [x] Créer la logique standardisée `AgentResult`
- [x] Centraliser la configuration dans `core/config.py`
- [x] Unifier les logs dans `core/logger.py`
- [x] Nœud `Topic Finder` refactorisé
- [x] Nœud `Copywriter` refactorisé (Migration vers Ollama gemini-3-flash-preview:cloud)
- [x] Nœud `Image Creator` refactorisé
- [x] Nœud `Reel Maker` refactorisé (Découplage ffmpeg / remotion du genérateur texte)
- [x] Nœud `Publisher` refactorisé
- [x] Nœud `Group Poster` refactorisé
- [x] Nœud `Webhook Monitor` refactorisé (avec nettoyage des chemins)
- [x] Orchestrateur `Scheduler` unifié (remplace l'infernal agent_generator)
- [x] Documentation `README.md` générée dans le sous-dossier de chaque nœud
- [x] Test de run_pipeline à vide réussi (vérifié via les logs Node)

**Statut : TERMINÉ ✅**

---

## NOTES & DÉCISIONS
> Utiliser cette section pour noter les choix importants au fil du projet

| Date | Décision | Raison |
|------|----------|--------|
| 2026-03-27 | Stack : Ollama + DeepSeek local, Make.com, Pollinations | 100% gratuit, validation locale avant cloud |
| 2026-03-27 | Page Facebook : Jean-Marc Emmanuel DANSI (personnel, pas IncidenX) | Marque personnelle, pas commerciale |
| 2026-03-27 | Personas = facettes d'Emmanuel, pas des personnages séparés | Cohérence de voix sur le long terme |
| 2026-03-27 | Architecture personas/ avec 4 couches par auteur | Séparation des responsabilités, extensibilité |
| 2026-03-27 | Timeout Ollama à 300s | Modèle deepseek-v3.2:cloud lent sur les posts longs |
| 2026-03-27 | Logging niveau INFO | Visibility sur les retries et warnings de génération |
| 2026-03-28 | Make.com abandonné → Meta App directe + webhook server | Temps réel, aucune limite d'opérations, contrôle total |
| 2026-03-28 | start_tunnel.py auto-update Meta webhook | URL Cloudflare temporaire change au redémarrage — script détecte et met à jour seul |

---

## PROBLÈMES CONNUS
> Logger ici tout ce qui bloque ou dégrade la qualité

| Date | Problème | Statut | Solution |
|------|----------|--------|----------|
| 2026-03-27 | `verify_and_retry` : comparaison `best_count` incorrecte côté "trop long" | ✅ Corrigé | Comparaison séparée min/max selon cas |
| 2026-03-27 | `logging.info` invisible (niveau ERROR trop restrictif) | ✅ Corrigé | Niveau passé à INFO |
