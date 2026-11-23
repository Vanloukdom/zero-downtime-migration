# La mise à jour sans interruption — expand/contract

[![ci-cd](https://github.com/Vanloukdom/zero-downtime-migration/actions/workflows/ci-cd.yml/badge.svg)](https://github.com/Vanloukdom/zero-downtime-migration/actions/workflows/ci-cd.yml)
![Python](https://img.shields.io/badge/Python-3.12-blue) ![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688) ![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791) ![k3s](https://img.shields.io/badge/k3s-deploy-FFC61C)

> Projet **07/10** de la série *« 10 problèmes que tout ingénieur logiciel devrait savoir résoudre »*.
> Démo : `https://migration.apps.vansoreldatacloud.com` · Documentation interactive : `https://migration.apps.vansoreldatacloud.com/docs`


## Le problème

L'application tourne **24 h/24**. Il faut modifier une **colonne critique** (`full_name` → `first_name` + `last_name`) et déployer un nouveau backend, alors que des milliers d'utilisateurs utilisent encore **l'ancienne version**. Sans interruption, sans casser la v1 et avec un **retour arrière possible**.

## La solution

Pattern **expand / contract** (*parallel change*) :

| Étape | Migration | Code déployé | Retour arrière |
|---|---|---|---|
| 1. Expand | `002` : ajout des colonnes nullables (ALTER instantané) + trigger de synchronisation | `SCHEMA_PHASE=expand` : écrit les deux formats, lit l'ancien | ✅ vers v1 |
| 2. Backfill | `003` : remplissage **par lots** de 1 000 lignes | — | ✅ |
| 3. Migrate | — | `SCHEMA_PHASE=migrate` : lit le nouveau format | ✅ vers expand |
| 4. Contract | `004` : suppression de `full_name` (**plusieurs releases plus tard**) | `SCHEMA_PHASE=contract` | ❌ seule étape irréversible |

- **Trigger de synchronisation bidirectionnel** : pendant le rolling update, un pod v1 qui écrit `full_name` et un pod v2 qui écrit `first_name/last_name` restent cohérents.
- Migrations **versionnées**, sous **verrou consultatif** (un seul migrateur même avec N pods) et avec `lock_timeout` : échouer vite plutôt que bloquer le trafic.
- La migration tourne dans un **Job Kubernetes avant** le déploiement du code ; rolling update `maxUnavailable: 0` et readiness probes.

## Architecture

```mermaid
flowchart LR
    V1[v1 : full_name] --> E[EXPAND : + first/last nullables\n+ trigger de sync]
    E --> B[BACKFILL par lots]
    B --> M[MIGRATE : lecture des nouvelles colonnes]
    M --> C[CONTRACT : DROP full_name]
    E -. rollback .-> V1
    M -. rollback .-> E
```

## API

| Méthode | Route | Rôle |
|---|---|---|
| GET | `/version` | Version et phase du schéma |
| POST | `/customers` | Créer un client |
| GET | `/customers/{id}` | Lire un client |

### Démo

```bash
URL=https://migration.apps.vansoreldatacloud.com
# Phase suivante : modifier SCHEMA_PHASE / MIGRATE_TO puis pousser sur main
kubectl -n p07-migration logs job/migrate
watch -n1 "curl -s $URL/version"   # aucune erreur pendant le rolling update
```

## Lancer en local

```bash
docker compose up --build          # API sur http://localhost:8000/docs
```

## Tests

```bash
docker compose up -d db
pip install -r requirements.txt -r requirements-dev.txt
ADMIN_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/postgres pytest -q
```

Ce qui est prouvé : Cycle complet v1 → expand → backfill (2 500 lignes) → migrate → contract, avec écritures v1 et v2 entrelacées et lecture croisée (rollback) ; migrations idempotentes.

## Déploiement en production (k3s sur VPS)

Pipeline GitHub Actions `test → build → deploy` :

1. **test** : pytest avec PostgreSQL en service ;
2. **build** : image multi-couches poussée sur `ghcr.io/vanloukdom/zero-downtime-migration` (tags `sha` et `latest`) ;
3. **deploy** : `kubectl apply -k k8s/` dans le namespace `p07-migration`, puis attente du `rollout status`.

Secrets à créer dans *Settings → Secrets and variables → Actions* :

| Secret | Contenu |
|---|---|
| `KUBECONFIG_B64` | `base64 -w0 kubeconfig` du cluster k3s (sans ce secret, l'étape deploy est ignorée) |
| `POSTGRES_PASSWORD` | Mot de passe PostgreSQL (fixe : ne pas le changer après le premier déploiement) |
| `APP_SECRET` | `openssl rand -hex 32` |

Côté cluster : Traefik (inclus dans k3s), cert-manager avec un `ClusterIssuer` `letsencrypt-prod`, un enregistrement DNS `*.apps.vansoreldatacloud.com` vers le VPS, et le package GHCR passé en **public** (ou un `imagePullSecret`).

Sécurité des pods : utilisateur non root, système de fichiers en lecture seule, capabilities supprimées, requests/limits, probes `/healthz` et `/readyz`, métriques Prometheus sur `/metrics`.

## Pour aller plus loin

pg-osc / pgroll pour les très grosses tables ; `CREATE INDEX CONCURRENTLY` ; feature flags (Unleash) pour basculer la lecture sans redéployer.

---
Van Sorel LOUKDOM · DevOps / Cloud & Data Engineer · Licence MIT
