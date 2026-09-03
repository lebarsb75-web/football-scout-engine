# Sécurité — règles avant mise en ligne

## Secrets

- La clé API RunPod ne doit jamais être placée dans `web/` ni envoyée au navigateur.
- Les secrets doivent rester côté backend dans des variables d'environnement.
- Ne jamais committer un fichier `.env` réel.

## Coût GPU

- `ENABLE_PAID_GPU=false` par défaut.
- Un benchmark réel est obligatoire avant estimation de coût.
- Une analyse ne peut partir que si le plafond autorisé couvre l'estimation avec marge de sécurité.
- Le backend doit limiter le nombre de jobs simultanés par utilisateur.
- Le worker RunPod doit rester à un maximum contrôlé pendant la phase de test.

## Vidéos

- Utiliser un stockage objet privé.
- Le navigateur reçoit une URL d'upload signée temporaire.
- RunPod reçoit une URL de lecture signée temporaire.
- Les URLs doivent expirer rapidement après traitement.
- Prévoir suppression automatique des vidéos selon la politique produit.

## Protection SSRF

Le moteur télécharge une URL vidéo. En production, il ne doit pas accepter une URL Internet arbitraire fournie directement par un utilisateur.

Le backend devra :
- générer lui-même l'URL signée ;
- n'autoriser que le domaine de stockage choisi ;
- refuser localhost, IP privées, metadata endpoints et redirections vers des hôtes non autorisés.

## Upload

- limite de taille ;
- liste de formats acceptés ;
- validation MIME + extension ;
- durée maximale ;
- nom de fichier généré côté serveur ;
- pas de chemin fourni par l'utilisateur.

## Comptes

Avant ouverture publique :
- authentification ;
- isolation stricte des matchs par utilisateur ;
- contrôle d'accès sur chaque rapport / vidéo / clip ;
- journalisation des actions sensibles ;
- suppression de compte et données.

## API

- CORS limité au domaine du site ;
- rate limiting ;
- identifiants de jobs non devinables ;
- validation Pydantic / JSON schema ;
- pas de détail de stack trace exposé au client ;
- timeouts réseau ;
- taille de réponse limitée.

## Données football

Les vidéos peuvent contenir des tiers, notamment des mineurs dans le football amateur. Avant commercialisation, prévoir une politique claire sur les droits de dépôt, la durée de conservation et les demandes de suppression.
