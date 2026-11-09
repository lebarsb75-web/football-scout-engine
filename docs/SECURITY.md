# Sécurité — règles avant mise en ligne

La plateforme traite des vidéos envoyées par les utilisateurs et pourra déclencher des jobs GPU payants. Les deux flux doivent rester **fail closed** : en cas de configuration incomplète, rien de payant ne part.

## Protections déjà présentes sur `dev-v2`

Un envoi RunPod payant exige désormais simultanément :

1. `ENABLE_PAID_GPU=true` ;
2. un endpoint et une clé RunPod configurés côté serveur ;
3. un benchmark court réellement mesuré pour pouvoir estimer le coût ;
4. un plafond `approved_max_cost_usd` supérieur ou égal à l'estimation ;
5. un `COST_APPROVAL_SECRET` configuré côté serveur et fourni par l'appelant backend de confiance ;
6. un domaine vidéo autorisé dans `VIDEO_HOST_ALLOWLIST` ;
7. une clé d'idempotence valide réservée atomiquement avant l'appel au fournisseur payant.

La configuration de développement conserve `ENABLE_PAID_GPU=false`. Modifier ce seul drapeau ne suffit volontairement pas à dépenser du crédit.

## Idempotence et double dépense

`api/idempotency.py` utilise maintenant SQLite pour conserver les clés de soumission et leur état `pending` / `completed`.

Le point critique est la réservation **avant** le premier appel RunPod susceptible de créer un job facturable :

`validation -> estimation -> autorisation -> réserve idempotence -> appel RunPod -> enregistre job -> complète idempotence`

Deux requêtes concurrentes portant la même clé et le même payload ne peuvent donc pas toutes les deux franchir la réservation. La seconde reçoit un conflit tant que la première est `pending`. Une clé réutilisée avec un payload différent est refusée.

En cas de réponse réseau ambiguë ou de crash juste après l'acceptation côté fournisseur, la réservation reste volontairement `pending`. C'est un choix de sécurité : il vaut mieux demander une vérification opérateur que supprimer automatiquement la réservation et risquer de payer deux fois.

Pour le prototype mono-hôte, SQLite est suffisant. Avant plusieurs instances backend, déplacer la réservation atomique et le registre des jobs vers un stockage transactionnel partagé (par exemple Postgres). Les fichiers SQLite doivent être montés sur un volume persistant si le conteneur API est redémarré.

## Secrets

- La clé API RunPod et `COST_APPROVAL_SECRET` ne doivent jamais être placés dans `web/` ni envoyés au navigateur.
- Les secrets restent côté backend dans des variables d'environnement.
- Ne jamais committer un fichier `.env` réel ; `.gitignore` exclut ces fichiers.
- Ne pas écrire les secrets ou URL signées dans les logs, rapports, analytics ou captures d'écran.

## Vidéos / protection SSRF

Le moteur télécharge une URL vidéo. Une URL Internet arbitraire fournie directement par un utilisateur ne doit jamais être transmise au worker en production.

Flux cible :

`navigateur -> stockage objet privé -> URL signée courte durée -> validation backend -> RunPod`

Le backend refuse déjà pour les soumissions payantes :
- `localhost` ;
- les IP littérales privées / loopback / link-local / réservées ;
- les identifiants intégrés dans une URL ;
- tout hostname absent de `VIDEO_HOST_ALLOWLIST`.

À compléter avec le stockage choisi : validation des redirections, durée d'expiration courte, suppression automatique et contrôle serveur du fichier.

## Coût GPU

- `ENABLE_PAID_GPU=false` par défaut ;
- benchmark réel obligatoire avant estimation exploitable ;
- plafond de coût par requête ;
- secret d'approbation indépendant ;
- domaine vidéo explicitement autorisé ;
- réservation idempotente persistante avant le lancement ;
- nombre de workers RunPod contrôlé pendant la phase de test.

## Upload

Avant mise en production :
- limite de taille ;
- liste de formats acceptés ;
- validation MIME + extension + probe vidéo serveur ;
- durée maximale ;
- nom de fichier généré côté serveur ;
- pas de chemin fourni par l'utilisateur ;
- quotas utilisateur ;
- politique de suppression automatique.

## Comptes

Avant ouverture publique :
- authentification ;
- isolation stricte des matchs par utilisateur ;
- contrôle d'accès sur chaque rapport / vidéo / clip ;
- journal d'audit pour les analyses payantes ;
- suppression de compte et des données associées.

## API

- CORS limité au domaine du site ;
- rate limiting ;
- identifiants de jobs non devinables ;
- validation Pydantic / JSON schema ;
- pas de stack trace exposée au client ;
- timeouts réseau ;
- taille de réponse limitée ;
- migration vers idempotence partagée avant scaling horizontal.

## Données football

Les vidéos peuvent contenir des tiers, notamment des mineurs dans le football amateur. Avant commercialisation, prévoir une politique claire sur les droits de dépôt, la durée de conservation, les demandes de suppression et l'accès aux vidéos/rapports.
