import json, sqlite3, shutil, uuid
from pathlib import Path
from datetime import datetime, timedelta

BASE = Path("D:/Content_Machine/machines/facebook_machine/accounts/2")

# ─── 1. BACKUP OLD PLANNING ───
old_planned = BASE / "planned_topics.json"
backup = BASE / "planned_topics_backup.json"
if old_planned.exists() and not backup.exists():
    shutil.copy2(old_planned, backup)
    print(f"Backup saved: {backup}")

# ─── 2. DEFINE 120 SESSIONS ───
sessions = [
    # MODULE A: LES BASES (1-30)
    ("1/120", "C'est quoi l'IA ?", "Analogie enfant/chat/chien, reconnaissance de motifs, pas de magie ni conscience. Exemples 2026: YouTube, déverrouillage visage, Maps, tags Facebook. Interdit: algorithme, réseau de neurones, deep learning."),
    ("2/120", "IA vs Machine Learning vs Deep Learning", "3 boîtes concentriques. IA=grand concept. ML=apprend par exemples. DL=trouve des motifs invisibles. Analogie: cuisine → recette → créer sa recette. Interdit: poids, couches, backpropagation."),
    ("3/120", "Les données, carburant de l'IA", "Donnée=info (texte,image,son). Plus d'exemples=plus précis. Qualité>quantité. Analogie: ingrédients pourris=plat pourri. Interdit: big data, data mining, JSON, CSV."),
    ("4/120", "Comment l'IA apprend", "3 phases: montrer des exemples → tester → utiliser. Analogie: apprendre à conduire (moniteur→examen→solo). Interdit: backpropagation, gradient descent, loss function."),
    ("5/120", "Pourquoi l'IA se trompe", "Pas de compréhension réelle. Biais des données d'entraînement. Hallucinations des LLM. Cas non vus=erreur. Exemple: IA médicale formée que sur peaux claires."),
    ("6/120", "Les 5 mots clés à retenir", "Algorithme=recette. Modèle=cerveau entraîné. Données=ingrédients. Entraînement=apprentissage. Prompt=question. Chaque mot=1 analogie."),
    ("7/120", "À quoi sert l'IA concrètement", "4 catégories: gagner du temps, analyser, créer, décider. Exemples: artisan rédige devis, commerçant analyse ventes, créateur génère visuels. Interdit: promesses de résultats."),
    ("8/120", "Les idées reçues sur l'IA", "Démystifier: l'IA va me remplacer, c'est trop compliqué, réservé aux grandes entreprises, l'IA pense comme un humain, l'IA coûte cher. Interdit: citer des stats non vérifiées."),
    ("9/120", "L'IA gratuite vs payante", "Gratuit: ChatGPT, Canva, Gemini, Copilot (versions limitées). Payant: usage intensif/pro. Règle: gratuit suffit pour apprendre. Interdit: prix exacts d'abonnement."),
    ("10/120", "Les limites de l'IA en 2026", "Connaissance limitée dans le temps. Pas d'accès au réel. Pas de fiabilité 100%. Coût écologique. Interdit: diaboliser ou promettre."),
    ("11/120", "Comment l'IA voit le monde", "Pixels et motifs, pas des objets. Une chaise retournée n'est plus une chaise. Exemple: images adversariales. Exercice: imaginer comment l'IA 'voit'."),
    ("12/120", "Les différents types d'IA", "Générative (crée), prédictive (analyse/prévoit), réactive (répond). Exemples: ChatGPT, Netflix, Siri. Interdit: classification technique avancée."),
    ("13/120", "L'IA dans ton téléphone", "Photo mode nuit/portraits, clavier prédictif, assistant vocal, batterie adaptative, tri notifications. Exercice: ouvrir paramètres et trouver 3 fonctions IA."),
    ("14/120", "L'IA dans les apps du quotidien", "Maps (trafic), YouTube (suggestions), Netflix (recommandations), Spotify (playlists), Google Photos (reconnaissance)."),
    ("15/120", "Histoire de l'IA en 5 dates", "1956=naissance. 1997=DeepBlue bat Kasparov. 2011=Siri. 2022=ChatGPT. 2025-2026=IA partout. Message: 70 ans pour devenir accessible."),
    ("16/120", "Pourquoi l'IA explose maintenant", "3 raisons: +données, +puissance, meilleurs algo + accès gratuit. Analogie: l'IA était un avion en 1950, aujourd'hui une voiture pour tous."),
    ("17/120", "Comment l'IA est entraînée (sans jargon)", "Imagine 1 milliard de cartes mémoire ajustées une par une. Des millions de petits réglages par essais/erreurs. Interdit: jargon technique."),
    ("18/120", "IA forte vs IA faible", "Faible=spécialisée UNE tâche (ChatGPT, reconnaissance faciale). Forte=pense comme humain (n'existe pas). Rassurer: pas de conscience, pas de réveil."),
    ("19/120", "L'IA et la créativité humaine", "IA imite/combine/reproduit. Humain crée/ressent/innove. Complémentaire. Exemple: peintre utilise l'IA pour idées, vision finale humaine."),
    ("20/120", "Biais et éthique: précautions", "L'IA hérite des biais de ses créateurs et données. Exemple: recrutement biaisé. Règle: outil, responsabilité humaine. Interdit: citer des cas précis non vérifiés."),
    ("21/120", "L'IA dans les métiers du savoir", "Enseignement, conseil, médecine, droit. L'IA assiste sans remplacer le jugement humain. Interdit: promesses de précision."),
    ("22/120", "L'IA dans le commerce et la vente", "Chatbots service client, recommandations, analyse avis, gestion stocks. Interdit: stats de croissance ou ROI non vérifiés."),
    ("23/120", "L'IA dans la création de contenu", "Rédaction, images, vidéos, musique. Produire plus vite, style reste humain. Interdit: remplacer totalement la création humaine."),
    ("24/120", "L'IA et les données personnelles", "Ce qu'on partage peut être utilisé pour améliorer le service. Pas de mots de passe, RIB, infos médicales sur version gratuite. Paramètres de confidentialité."),
    ("25/120", "Quiz récap Module A (1-24)", "Revue des 24 séances sous forme questions/réponses. 5 questions pour vérifier ce qui a été retenu. Interdit: inventer des questions hors sujet."),
    ("26/120", "L'IA dans l'éducation", "Tuteur personnel 24/7, explications multiples, exercices sur mesure. Limite: l'IA peut se tromper, ne remplace pas un vrai professeur."),
    ("27/120", "L'IA dans la santé", "Aide au diagnostic, analyse d'images médicales, découverte médicaments. Limite: assiste le médecin, ne le remplace pas."),
    ("28/120", "L'IA dans les transports", "Voitures autonomes, optimisation trajets, gestion trafic, logistique. Interdit: affirmer que les voitures autonomes sont déjà parfaites."),
    ("29/120", "L'IA dans les finances", "Détection fraudes, conseillers robotisés, analyse marchés. Interdit: conseil financier personnalisé."),
    ("30/120", "L'IA dans l'agriculture", "Drones surveillance champs, détection maladies plantes, optimisation irrigation. Interdit: stats de rendement non vérifiées."),

    # MODULE B: PRATIQUE AVEC CHATGPT (31-60)
    ("31/120", "ChatGPT: premier contact", "C'est quoi, comment y accéder (chatgpt.com), interface, version gratuite. Interdit: prix exacts, fonctionnalités qui n'existent pas."),
    ("32/120", "ChatGPT: les bases de la conversation", "Dialoguer, reformuler, demander précisions, relancer. Interdit: techniques avancées."),
    ("33/120", "Écrire un bon prompt: la méthode", "Rôle + Contexte + Tâche + Format + Contrainte. 5 étapes. Interdit: chain-of-thought, few-shot, jargon."),
    ("34/120", "Les prompts pour le travail", "Email, compte-rendu, argumentaire. Interdit: promettre que c'est prêt à envoyer sans relecture."),
    ("35/120", "Les prompts pour les réseaux sociaux", "Posts Facebook/LinkedIn, descriptions, hashtags. Interdit: promettre du viral."),
    ("36/120", "Les prompts pour les études", "Résumer un cours, générer fiches, préparer examen, reformuler. Interdit: certifier l'exactitude."),
    ("37/120", "ChatGPT avec fichiers", "Uploader PDF/images/Excel. ChatGPT peut lire et analyser. Interdit: formats de fichiers qui n'existent pas."),
    ("38/120", "ChatGPT avec images", "Analyser photo, décrire image, lire texte dans une image. Interdit: reconnaissance parfaite à 100%."),
    ("39/120", "ChatGPT recherche web", "Activer la recherche (icône globe). Infos récentes. Interdit: dire que la recherche est activée par défaut."),
    ("40/120", "ChatGPT: bonnes pratiques", "Nouvelle conversation=nouveau sujet. Être précis. Donner des exemples. Interdit: techniques avancées."),
    ("41/120", "Les GPTs personnalisés", "Créer son assistant avec instructions sur mesure (ChatGPT payant). Interdit: promettre que c'est gratuit."),
    ("42/120", "Les limites de ChatGPT", "Hallucinations, connaissance limitée dans le temps, pas de fiabilité absolue. Toujours vérifier."),
    ("43/120", "ChatGPT pour traduire", "Traduction avec contexte, adaptation au ton. Interdit: traduction certifiée."),
    ("44/120", "ChatGPT pour corriger", "Correction orthographe/grammaire, amélioration style, adaptation ton. Interdit: correction parfaite."),
    ("45/120", "ChatGPT pour brainstormer", "Générer idées, variantes, angles différents. Interdit: promettre que les idées sont originales ou brevetables."),
    ("46/120", "ChatGPT pour argumenter", "Préparer argumentaire, anticiper objections, structurer discours. Interdit: simulation juridique."),
    ("47/120", "ChatGPT pour apprendre une langue", "Pratiquer conversation, corriger erreurs, jouer rôles. Interdit: remplacer un vrai cours de langue."),
    ("48/120", "ChatGPT pour coder (vue d'ensemble)", "Générer code simple, expliquer code, déboguer. Interdit: code de production sans review."),
    ("49/120", "ChatGPT pour les calculs et analyses", "Analyser données Excel, créer tableaux, interpréter chiffres. Interdit: analyse financière certifiée."),
    ("50/120", "ChatGPT pour planifier", "Créer plannings, to-do lists, calendriers éditoriaux. Interdit: promettre que le planning est réaliste."),
    ("51/120", "Comparer les réponses de ChatGPT", "Régénérer, demander version différente, comparer. Interdit: préférer une version sans raison."),
    ("52/120", "Les raccourcis qui changent tout", "/ pour commandes, @ pour GPT, copier/formater. Interdit: raccourcis qui n'existent pas."),
    ("53/120", "ChatGPT sur mobile", "App iOS/Android, voix, upload photo, widgets. Interdit: fonctionnalités qui n'existent pas sur mobile."),
    ("54/120", "ChatGPT et la productivité", "Intégrer ChatGPT dans sa routine quotidienne. Interdit: promettre des gains de temps chiffrés."),
    ("55/120", "Questions pièges à poser à ChatGPT", "Tester limites, repérer erreurs, développer esprit critique. Interdit: questions illégales ou dangereuses."),
    ("56/120", "Ne pas devenir dépendant de ChatGPT", "Garder jugement, vérifier faits, continuer à apprendre. Interdit: dire que l'IA rend moins intelligent."),
    ("57/120", "Alternative gratuite: Google Gemini", "Présentation, forces (recherche Google), différences ChatGPT. Interdit: comparatifs techniques détaillés."),
    ("58/120", "Alternative gratuite: Perplexity", "Assistant recherche+synthèse, sources citées. Idéal pour vérifier. Interdit: promettre des sources toujours fiables."),
    ("59/120", "Alternative gratuite: Claude", "Long contexte, idéal pour analyser documents volumineux. Interdit: fonctionnalités qui n'existent pas."),
    ("60/120", "Lequel choisir selon ton besoin", "ChatGPT (généraliste), Gemini (recherche), Perplexity (vérification), Claude (documents longs)."),

    # MODULE C: CRÉATION AVEC L'IA (61-90)
    ("61/120", "Générer des images: introduction", "Description→image. Principes de base. Interdit: outils qui n'existent pas."),
    ("62/120", "DALL-E dans ChatGPT", "Intégré à ChatGPT, gratuit limité. Interdit: nombre exact d'images gratuit."),
    ("63/120", "Canva IA", "Génération images, design assisté, magique. Interdit: fonctionnalités qui n'existent pas sur Canva."),
    ("64/120", "Écrire un bon prompt d'image", "Quoi (sujet)+Comment (style)+Ambiance (lumière/couleurs)+Format (ratio)."),
    ("65/120", "Les styles d'image possibles", "Réaliste, cartoon, 3D, pixel art, aquarelle, dessin animé. Interdit: styles qui n'existent pas."),
    ("66/120", "Créer des visuels pour les réseaux", "Formats: carré (1:1), story (9:16), bannière (16:9)."),
    ("67/120", "Créer des logos avec l'IA", "Décrire activité, préciser style, itérer. Interdit: logo professionnel sans ajustement humain."),
    ("68/120", "Créer des présentations avec l'IA", "Gamma.app, IA dans PowerPoint/Google Slides. Interdit: plugins qui n'existent pas."),
    ("69/120", "Générer de la musique avec l'IA", "Suno, Udio. Décrire style→obtenir musique. Interdit: qualité studio professionnelle garantie."),
    ("70/120", "Générer de la vidéo avec l'IA", "Runway, Pika, Canva. Interdit: durée ou qualité non disponible."),
    ("71/120", "L'IA pour les emails marketing", "Newsletters, objets, séquences automatiques. Interdit: promettre des taux d'ouverture."),
    ("72/120", "L'IA pour les descriptions produits", "Adapter ton à la cible, mettre en avant bénéfices. Interdit: SEO garanti."),
    ("73/120", "L'IA pour les fiches Google My Business", "Optimiser description, répondre avis, générer posts."),
    ("74/120", "L'IA pour le service client", "Chatbots, réponses automatiques, FAQ. Interdit: remplacer complètement l'humain."),
    ("75/120", "L'IA pour les CV et lettres de motivation", "Adapter au poste, mettre en avant compétences, corriger fautes."),
    ("76/120", "L'IA pour préparer un entretien", "Simuler entretien, préparer réponses, anticiper questions."),
    ("77/120", "L'IA pour les études de marché", "Analyser secteur, identifier tendances, étudier concurrence. Interdit: données chiffrées précises."),
    ("78/120", "L'IA pour la gestion de projet", "Créer cahier des charges, planifier tâches, estimer délais."),
    ("79/120", "L'IA pour les textes juridiques simples", "CGV, contrat prestation simple, mise en demeure. Limite: faire relire par vrai juriste."),
    ("80/120", "L'IA pour les recettes et menus", "Recettes selon ingrédients, adapter régimes. Interdit: conseils nutritionnels médicaux."),
    ("81/120", "L'IA pour les voyages", "Planifier itinéraire, suggérer activités, estimer budget. Interdit: prix exacts."),
    ("82/120", "L'IA pour la parentalité", "Idées activités enfants, conseils éducation, organisation familiale."),
    ("83/120", "L'IA pour le sport et la santé", "Plans entraînement, conseils nutrition, suivi objectifs. Limite: consulter un vrai pro."),
    ("84/120", "L'IA pour la maison et le bricolage", "Tutoriels, listes matériel, estimation quantités, dépannage."),
    ("85/120", "L'IA pour les finances personnelles", "Budget, suivi dépenses, objectifs épargne. Limite: pas conseil financier certifié."),
    ("86/120", "L'IA pour les jeux et loisirs", "Générer scénarios, quiz, défis, règles de jeu."),
    ("87/120", "L'IA pour les cadeaux", "Suggestions personnalisées selon budget, goûts, occasion."),
    ("88/120", "L'IA pour les discours et allocutions", "Structurer discours, adapter public, ajouter humour."),
    ("89/120", "L'IA pour les jeux de rôle et histoires", "Histoires interactives, mondes, personnages."),
    ("90/120", "L'IA pour méditer et se détendre", "Méditations guidées, exercices respiration, visualisations."),

    # MODULE D: MAÎTRISE ET AUTOMATISATION (91-120)
    ("91/120", "Automatiser avec l'IA", "Principes: si X alors Y, répétition=opportunité. Interdit: API, webhook, Zapier, code."),
    ("92/120", "Combiner les outils IA", "ChatGPT+Canva, ChatGPT+Excel, Perplexity+ChatGPT. Interdit: automatisation complexe."),
    ("93/120", "Créer son kit de prompts", "Collectionner, organiser, réutiliser ses meilleurs prompts."),
    ("94/120", "Les assistants personnalisés", "GPTs (ChatGPT), Gems (Gemini), projets (Claude)."),
    ("95/120", "L'IA pour analyser les avis clients", "Extraire tendances, sentiment général, points amélioration."),
    ("96/120", "L'IA pour la veille concurrentielle", "Surveiller tendances, analyser concurrents, détecter opportunités."),
    ("97/120", "Créer un site vitrine avec l'IA", "Générer contenu, visuels, structure. Interdit: site professionnel complet sans ajustements."),
    ("98/120", "L'IA pour les fiches produits e-commerce", "Titre, description, mots-clés, variantes."),
    ("99/120", "L'IA pour les tests A/B", "Générer variantes texte, analyser résultats. Interdit: stats de conversion."),
    ("100/120", "L'IA pour la prospection", "Identifier prospects, personnaliser messages, relancer."),
    ("101/120", "L'IA pour le community management", "Planifier, rédiger, adapter ton, répondre commentaires."),
    ("102/120", "L'IA pour l'emailing", "Séquences, objets, corps message, relances, segmentation."),
    ("103/120", "L'IA et le SEO", "Mots-clés, structurer article, balises méta. Limite: pistes, pas stratégie complète."),
    ("104/120", "L'IA pour les rapports et analyses", "Synthétiser données, créer tableaux, rédiger conclusions."),
    ("105/120", "L'IA pour les devis et factures", "Générer modèle, adapter tarifs, décrire prestations."),
    ("106/120", "L'IA pour les fiches de poste", "Description poste, missions, profil, avantages."),
    ("107/120", "L'IA pour les argumentaires commerciaux", "Avantages produits, objections, réponses types."),
    ("108/120", "L'IA pour les formations et tutoriels", "Structurer formation, générer exercices, plan pédagogique."),
    ("109/120", "Deep Dive: Perplexity pour la recherche", "Recherche approfondie, sources citées, suivi sujets."),
    ("110/120", "Deep Dive: NotebookLM pour l'étude", "Google NotebookLM, analyser sources multiples, générer notes."),
    ("111/120", "Deep Dive: Canva IA avancé", "Génération batch, designs automatiques, branding."),
    ("112/120", "Deep Dive: Excel + IA", "Formules complexes, analyse données, graphiques."),
    ("113/120", "Les tendances IA 2026-2027", "IA multimodale, agents autonomes, IA objets connectés."),
    ("114/120", "Les métiers qui émergent avec l'IA", "Prompt engineer, auditeur IA, formateur IA, éthicien IA."),
    ("115/120", "L'IA et l'emploi", "Transforme les métiers, supprime rarement. Nouveaux outils, nouvelles compétences."),
    ("116/120", "L'IA et l'environnement", "Coût énergétique, data centers, solutions plus vertes."),
    ("117/120", "L'IA et la régulation", "AI Act européen, droits d'auteur, transparence."),
    ("118/120", "Bilan: ce que tu as appris", "Récap 4 modules: bases, pratique, création, maîtrise. 10 questions."),
    ("119/120", "Ton plan d'action personnel", "Définir objectifs, choisir outils, planifier pratique. Un engagement concret."),
    ("120/120", "La suite du voyage", "Ressources, continuer à apprendre. De zéro à capable. L'IA est un outil dans ta boîte."),
]

# ─── 3. BUILD NEW planned_topics.json ───
topics = []
for num, title, context in sessions:
    topics.append({
        "id": str(uuid.uuid4()),
        "persona": "mini_formation",
        "topic": f"Séance {num} — {title}",
        "context": context,
        "audience": "débutant absolu",
        "objectif": "formation",
        "format": "formation",
        "used": False,
        "validated": False,
        "date_prevue": None,
        "variables": {}
    })

# Structure: { persona_name: [topics] } for backward compatibility
new_planning = {"mini_formation": topics}

with open(old_planned, "w", encoding="utf-8") as f:
    json.dump(new_planning, f, indent=2, ensure_ascii=False)
print(f"✅ {len(topics)} sessions injected into planned_topics.json")

# ─── 4. CLEAN DB ───
db_path = "D:/Content_Machine/machines/facebook_machine/data/leads_station.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Delete all pending/written/error posts for account 2
for status in ["pending", "written", "error", "rejected"]:
    cursor.execute("DELETE FROM posts WHERE account_id = 2 AND status = ?", (status,))
    deleted = cursor.rowcount
    print(f"Deleted {deleted} {status} posts from DB (account 2)")

conn.commit()
conn.close()

# ─── 5. UPDATE SCHEDULE (2x/day mini_formation) ───
schedule_path = BASE / "schedule.json"
new_schedule = {
    "schedule": [
        {"time": "09:00", "persona": "mini_formation", "type": "post"},
        {"time": "18:00", "persona": "mini_formation", "type": "post"}
    ]
}
schedule_path.write_text(json.dumps(new_schedule, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"✅ Schedule updated: 2 posts/day (09:00, 18:00)")

# Also update the global schedule
global_schedule = Path("D:/Content_Machine/machines/facebook_machine/data/schedule.json")
if global_schedule.exists():
    global_schedule.write_text(json.dumps(new_schedule["schedule"], indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"✅ Global schedule updated too")

print("\n🎯 Planning injecté avec succès!")
