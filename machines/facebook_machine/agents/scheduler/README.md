# Scheduler Agent (Orchestrateur)

**Rôle** : Nœud central qui exécute le pipeline de publication. Il lie tous les autres agents entre eux en vérifiant systématiquement le retour de `AgentResult`.

## Architecture du Pipeline
1. `Topic Finder` : Trouve le sujet du jour et l'angle. Si échec → **Arrêt immédiat**
2. `Copywriter` : Rédige le post via Ollama. Si échec → **Arrêt immédiat**
3. `Image Creator` : Génère l'image si activé. Si échec → *Warning (le texte seul sera publié)*
4. `Reel Maker` : Assemble la vidéo (uniquement si le format demandé est 'reel'). Si échec → *Warning*
5. `Publisher` : Envoie à l'API Meta. Si échec → **Arrêt immédiat**

## Entrées / Sorties

*   **Variables d'environnement requises :** Hérite de l'arbre global (voir `core/config.py`).
*   **Fonction principale :** `run_pipeline(post_type="expert_ia", publish=True) -> AgentResult`

## Exécution
```bash
# Lancer un test complet sans publication
python agents/scheduler/agent.py --type expert_ia --no-publish

# Lancer pour de vrai
python agents/scheduler/agent.py --type expert_ia
```
Grâce à `AgentResult`, si un nœud plante, l'erreur remontera proprement au lieu de faire crasher les scripts en aval (ex: ffmpeg ne plantera plus si le post.txt est vide).
