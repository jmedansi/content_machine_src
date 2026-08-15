"""Instagram machine — machine autonome de génération + publication Instagram.

Structure (calquée sur facebook_machine) :
  agents/agent_publisher.py   Publication via Graph API (container → media_publish)
  agents/scheduler/agent.py   Wrapper délégant au scheduler partagé
  data/leads_station.db       DB plateforme (accounts + posts)
  persona/                    Personas modèles copiés à la création de compte
"""