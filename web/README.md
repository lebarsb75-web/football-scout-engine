# Prototype web

Cette interface est volontairement utilisable sans serveur et sans RunPod.

## Tester gratuitement

Ouvrir `web/index.html` dans un navigateur moderne.

Le prototype permet de :
1. choisir une vidéo présente sur l'ordinateur ;
2. la lire localement dans le navigateur ;
3. mettre en pause à un moment où le joueur est clairement visible ;
4. cliquer directement sur le joueur ;
5. récupérer automatiquement le timestamp et les coordonnées normalisées nécessaires au moteur.

Le bouton GPU est désactivé. Aucune requête RunPod n'est faite par ce prototype.

## Connexion future au backend

Quand l'API et le stockage seront déployés :
- upload vidéo vers stockage objet ;
- création d'une URL signée temporaire ;
- appel `/analysis/estimate` ;
- affichage du coût estimé ;
- confirmation utilisateur ;
- appel `/analysis/submit` seulement si le coût autorisé est suffisant et que `ENABLE_PAID_GPU=true` côté serveur ;
- suivi du job ;
- affichage du rapport et des clips.
