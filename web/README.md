# Application web

L'interface est une application responsive en français couvrant l'accueil,
l'import local, la sélection du joueur, l'estimation, la progression et le rapport.
Elle consomme uniquement les contrats publics du backend et n'affiche jamais les
valeurs brutes du worker.

## Tester gratuitement

Ouvrir `web/index.html` dans un navigateur moderne.

Le prototype permet de :
1. choisir une vidéo présente sur l'ordinateur ;
2. la lire localement dans le navigateur ;
3. mettre en pause à un moment où le joueur est clairement visible ;
4. cliquer directement sur le joueur ;
5. récupérer automatiquement le timestamp et les coordonnées normalisées nécessaires au moteur.

Sans URL signée et backend configuré, aucun bouton ne peut soumettre le fichier à
RunPod. Une fois connecté, le navigateur appelle successivement l'estimation,
la soumission idempotente, puis le rafraîchissement du job existant.

## Connexion au backend

Le parcours connecté utilise :
- upload vidéo vers stockage objet ;
- création d'une URL signée temporaire ;
- appel `/analysis/estimate` ;
- affichage du coût estimé ;
- confirmation utilisateur ;
- appel `/analysis/submit` seulement si le coût autorisé est suffisant et que `ENABLE_PAID_GPU=true` côté serveur ;
- suivi du job ;
- affichage du rapport filtré retourné par `api/results.py`.

Les champs `available: false` sont toujours rendus comme « Masquée », sans
reprendre la valeur brute. Un résultat `review_required` affiche un état non
exploitable et aucune statistique joueur.

## Preview publique gratuite

Le workflow `.github/workflows/pages.yml` publie uniquement le dossier `web/`
sur GitHub Pages à chaque push sur `dev-v2`. Il ne construit pas le worker,
n'appelle pas RunPod et ne peut donc déclencher aucune dépense GPU.
