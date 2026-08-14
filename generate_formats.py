import json
from pathlib import Path

# Mapping of persona directory to its format details
FORMATS = {
    # LinkedIn
    "b2b_expert": {
        "format_name": "B2B Expert",
        "variables_requises": ["SITUATION_CLIENT", "ACTION_CONTRE_INTUITIVE", "RESULTAT_CHIFFRE", "MORALE_B2B"],
        "user_prompt_template": "Rédige un post LinkedIn orienté B2B Expert sur :\n\nSituation de départ du client ou de l'entreprise : {SITUATION_CLIENT}\nL'action surprenante/contre-intuitive mise en place : {ACTION_CONTRE_INTUITIVE}\nLe résultat chiffré obtenu : {RESULTAT_CHIFFRE}\nLa morale à retenir pour les autres dirigeants : {MORALE_B2B}\n\nTexte brut publiable. Pas de markdown. Pas de hashtags."
    },
    "carousel_pro": {
        "format_name": "Carousel Pro",
        "variables_requises": ["THEME_CAROUSEL", "PROBLEME_INTRODUIT", "EXEMPLES_ERREURS", "ETAPES_SOLUTION"],
        "user_prompt_template": "Rédige le script (texte des slides) pour un Carousel LinkedIn professionnel sur :\n\nThème du carousel : {THEME_CAROUSEL}\nProblème introduit (slide 2-3) : {PROBLEME_INTRODUIT}\nLes erreurs dénoncées (slides du milieu) : {EXEMPLES_ERREURS}\nLes étapes de la solution (dernières slides) : {ETAPES_SOLUTION}\n\nFormat : Chaque slide doit commencer par 'Slide X :'. Texte très court et percutant par slide. Ajoute un appel à l'action à la dernière slide."
    },
    "networker": {
        "format_name": "Networker",
        "variables_requises": ["SITUATION_VECUE", "DILEMME_OU_CHOIX", "QUESTION_OUVERTE"],
        "user_prompt_template": "Rédige un post LinkedIn court de type 'Networker' pour engager la conversation sur :\n\nSituation vécue (courte anecdote ou fait) : {SITUATION_VECUE}\nLe dilemme ou le choix inattendu : {DILEMME_OU_CHOIX}\nQuestion ouverte pour la communauté : {QUESTION_OUVERTE}\n\nTexte brut publiable. Pas de markdown. Pas de hashtags."
    },
    # Facebook
    "mini_formation": {
        "format_name": "Mini Formation",
        "variables_requises": ["COMPETENCE_CIBLEE", "ETAPE_1", "ETAPE_2", "ETAPE_3", "RESULTAT_PROMIS"],
        "user_prompt_template": "Rédige un post Facebook (Mini Formation) sur :\n\nLa compétence ou le problème à résoudre : {COMPETENCE_CIBLEE}\nÉtape 1 : {ETAPE_1}\nÉtape 2 : {ETAPE_2}\nÉtape 3 : {ETAPE_3}\nLe résultat promis à la fin : {RESULTAT_PROMIS}\n\nTexte aéré, utilise des emojis pertinents. Ajoute le mot-clé pour engager à la fin."
    },
    "storytelling_pro": {
        "format_name": "Storytelling Pro",
        "variables_requises": ["EVENEMENT_DECLENCHEUR", "MA_REACTION", "LA_LECON_APPRISE", "VISION_GLOBALE"],
        "user_prompt_template": "Rédige un post Facebook (Storytelling Pro) sur :\n\nL'événement déclencheur ou la conversation marquante : {EVENEMENT_DECLENCHEUR}\nMa réaction ou ma décision face à ça : {MA_REACTION}\nLa leçon que j'en tire aujourd'hui : {LA_LECON_APPRISE}\nMa vision globale pour l'avenir : {VISION_GLOBALE}\n\nTexte authentique, émotionnel, utilise des emojis. Signature de type leader à la fin."
    },
    "avis_tranches": {
        "format_name": "Avis Tranchés",
        "variables_requises": ["MYTHE_COURANT", "MON_AVIS_RADICAL", "ARGUMENT_1", "ARGUMENT_2", "APPEL_AU_DEBAT"],
        "user_prompt_template": "Rédige un post Facebook avec un avis tranché sur :\n\nMythe courant dans le digital/IA : {MYTHE_COURANT}\nMon avis radical (la vérité qui dérange) : {MON_AVIS_RADICAL}\nArgument 1 : {ARGUMENT_1}\nArgument 2 : {ARGUMENT_2}\nAppel au débat : {APPEL_AU_DEBAT}\n\nTexte direct, qui suscite des commentaires."
    },
    "business_auto": {
        "format_name": "Business Auto",
        "variables_requises": ["TÂCHE_CHRONOPHAGE", "OUTIL_UTILISE", "TEMPS_GAGNE", "CONSEIL_POUR_DEMARRER"],
        "user_prompt_template": "Rédige un post Facebook (Business Automatisé) sur :\n\nTâche qui prenait trop de temps : {TÂCHE_CHRONOPHAGE}\nL'outil ou l'agent IA utilisé pour l'automatiser : {OUTIL_UTILISE}\nLe gain de temps/argent mesurable : {TEMPS_GAGNE}\nUn conseil simple pour ceux qui veulent essayer : {CONSEIL_POUR_DEMARRER}\n\nPost orienté productivité et liberté, emojis pertinents."
    },
    "cta": {
        "format_name": "Appel à l'Action",
        "variables_requises": ["OFFRE_OU_RESSOURCE", "DOULEUR_CIBLE", "PREUVE_SOCIALE", "ACTION_REQUISE"],
        "user_prompt_template": "Rédige un post Facebook direct (Appel à l'Action) pour promouvoir :\n\nL'offre ou la ressource gratuite : {OFFRE_OU_RESSOURCE}\nLa douleur qu'elle résout pour la cible : {DOULEUR_CIBLE}\nUne petite preuve sociale : {PREUVE_SOCIALE}\nL'action exacte requise (ex: Commenter 'OUI') : {ACTION_REQUISE}\n\nCourt, incisif et orienté conversion."
    },
    "ia_design": {
        "format_name": "IA Design",
        "variables_requises": ["OUTIL_DESIGN", "TECHNIQUE_SECRETE", "AVANT_APRES", "IMPACT_VISUEL"],
        "user_prompt_template": "Rédige un post Facebook (IA Design) sur :\n\nL'outil utilisé (Midjourney, Canva IA, etc.) : {OUTIL_DESIGN}\nLa technique secrète ou le prompt astucieux : {TECHNIQUE_SECRETE}\nL'évolution (Avant sans IA / Après avec IA) : {AVANT_APRES}\nL'impact sur l'image de marque : {IMPACT_VISUEL}\n\nAccent sur la beauté et la puissance visuelle de l'IA."
    },
    "ia_integration": {
        "format_name": "IA Intégration",
        "variables_requises": ["PROCESSUS_TRADITIONNEL", "NOUVELLE_INTEGRATION_IA", "DIFFICULTE_SURMONTEE", "RESULTAT_FINAL"],
        "user_prompt_template": "Rédige un post Facebook (Intégration IA) sur :\n\nComment le processus fonctionnait avant (pénible/lent) : {PROCESSUS_TRADITIONNEL}\nComment j'ai intégré l'IA dans l'entreprise/l'équipe : {NOUVELLE_INTEGRATION_IA}\nLe frein ou la difficulté surmontée : {DIFFICULTE_SURMONTEE}\nLe résultat final (KPI, vitesse, qualité) : {RESULTAT_FINAL}\n\nPost orienté process, transformation d'entreprise et concret."
    },
    "post_court": {
        "format_name": "Pensée Courte",
        "variables_requises": ["PENSEE_DU_JOUR", "EXPLICATION_RAPIDE", "QUESTION_SIMPLE"],
        "user_prompt_template": "Rédige un post Facebook ultra-court (Pensée du Jour) sur :\n\nLa pensée choc ou l'insight : {PENSEE_DU_JOUR}\nUne phrase d'explication ou de contexte : {EXPLICATION_RAPIDE}\nQuestion très facile à répondre : {QUESTION_SIMPLE}\n\nFormat: 3-4 lignes maximum, très percutant."
    }
}

machines = {
    "linkedin_machine": Path("d:/Content_Machine/machines/linkedin_machine/accounts/1/persona"),
    "facebook_machine": Path("d:/Content_Machine/machines/facebook_machine/accounts/1/persona")
}

for machine_name, base_path in machines.items():
    if not base_path.exists():
        continue
        
    for persona_dir in base_path.iterdir():
        if not persona_dir.is_dir() or persona_dir.name.startswith("_"):
            continue
            
        persona_name = persona_dir.name
        if persona_name in FORMATS:
            format_file = persona_dir / "format.json"
            # N'écrase pas si déjà modifié (sauf si on veut tout forcer, mais on l'a déjà fait pour linkedin/defi_challenge)
            if not format_file.exists() or persona_name in FORMATS:
                with open(format_file, "w", encoding="utf-8") as f:
                    json.dump(FORMATS[persona_name], f, ensure_ascii=False, indent=2)
                print(f"Created format.json for {machine_name} -> {persona_name}")

print("Done.")
