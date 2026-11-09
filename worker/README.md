# Backend Cloudflare privé

Ce Worker remplace les champs techniques du prototype par un vrai parcours :

1. le navigateur découpe la vidéo en parties de 90 Mo ;
2. le Worker autorise chaque partie avec un jeton signé court ;
3. R2 conserve la vidéo dans un bucket privé ;
4. RunPod reçoit une URL de lecture temporaire ;
5. le résultat brut est filtré par les mêmes quality gates que l'API Python ;
6. la vidéo est supprimée à la fin du job, avec un nettoyage de secours après 48 heures.

Les jobs et les clés d'idempotence sont stockés dans D1. Une soumission concurrente
avec la même clé est donc bloquée avant l'appel payant à RunPod.

## Ressources à créer

```bash
npx wrangler r2 bucket create football-scout-videos
npx wrangler d1 create football-scout-db
```

Reporter l'identifiant D1 retourné dans `wrangler.jsonc`, puis initialiser la base :

```bash
npx wrangler d1 execute football-scout-db --remote --file schema.sql
```

## Secrets

Les valeurs réelles ne doivent jamais être placées dans GitHub ou dans le frontend.

```bash
npx wrangler secret put APP_ACCESS_CODE
npx wrangler secret put UPLOAD_SIGNING_SECRET
npx wrangler secret put RUNPOD_API_KEY
```

`UPLOAD_SIGNING_SECRET` doit être une valeur aléatoire d'au moins 32 octets.

## Déploiement verrouillé

La configuration versionnée conserve volontairement :

```json
"BENCHMARK_GPU_SECONDS_PER_VIDEO_MINUTE": "0",
"ENABLE_PAID_GPU": "false"
```

Dans cet état, l'estimation échoue avant l'upload et aucun job RunPod ne peut être
créé. Ces deux valeurs ne seront modifiées qu'après validation du smoke test de
26 secondes sur le moteur `2.4-dev`, avec un worker maximum.

## Vérifications locales

```bash
npm test
npm run check
```
