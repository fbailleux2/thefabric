# TheFabric

TheFabric fusionne cinq briques locales :

- Jean-Marc pour l'analyse d'une session de travail et la reconstruction du processus reel
- PySpur pour generer un workflow importable dans un builder visuel
- Hermes Agent pour la memoire, la procedure executable, et la boucle d'apprentissage
- BundleFabric pour retrouver ou creer un bundle specialise
- KFabric pour preparer la recherche documentaire et le corpus qui ancre l'automatisation

L'idee du MVP est simple :

1. on decrit une session quotidienne d'un utilisateur "lambda" en JSON
2. TheFabric produit un JSON pivot d'intelligence de session
3. ce JSON est projete en artefacts Jean-Marc, PySpur et Hermes
4. TheFabric cherche un bundle existant compatible dans BundleFabric
5. si aucun bundle n'est suffisamment pertinent, TheFabric en cree un compatible
6. TheFabric construit ensuite une requete KFabric pour aller chercher les documents qui serviront aux agents
7. Hermes recoit enfin une projection explicite de memoire, skill et protocole d'apprentissage

## Pourquoi Hermes est central ici

Dans TheFabric, Hermes n'est pas seulement un runtime secondaire :

- il recupere les faits durables a memoriser
- il recoit une skill procedurale directement derivee de la session observee
- il porte la boucle "observer -> agir -> tracer -> apprendre"
- il s'appuie sur le bundle retenu et sur le corpus KFabric pour rendre l'automatisation robuste

Autrement dit, PySpur formalise le workflow, mais Hermes execute, apprend et capitalise.

## Structure generee

Une execution cree typiquement :

- `session_intelligence.json` : le JSON pivot TheFabric
- `jean_marc/` : `process_analysis.json` et `field_observation.json`
- `pyspur/workflow_template.json` : workflow importable/adaptable dans PySpur
- `hermes/` : `ingestion.json`, `MEMORY.md`, `USER.md`, et une skill Hermes
- `bundles/` : resolution de bundles et bundle cree si necessaire
- `kfabric/` : `query_create.json` et plan d'appels API
- `run_summary.md` : lecture humaine du resultat

## Usage

Depuis la racine du repo :

```bash
python3 -m thefabric run \
  --input examples/daily_session.json \
  --output artifacts/demo
```

Optionnellement, si KFabric tourne en local :

```bash
python3 -m thefabric run \
  --input examples/daily_session.json \
  --output artifacts/demo \
  --kfabric-url http://127.0.0.1:8000 \
  --kfabric-api-key change-me
```

## Format d'entree

Le fichier d'entree decrit une session quotidienne :

- metadonnees de session
- objectif principal
- procedure declaree connue ou non
- liste d'activites horodatees
- artefacts d'entree/sortie
- decisions, blocages, documents necessaires

Un exemple complet est fourni dans `examples/daily_session.json`.
