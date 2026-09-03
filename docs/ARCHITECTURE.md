# Football Scout Platform — Architecture cible

## Objectif produit

Permettre à un joueur amateur de déposer une vidéo de match, sélectionner le joueur à suivre, lancer une analyse, puis récupérer un rapport lisible et des séquences vidéo utiles.

## Pipeline cible

1. **Upload vidéo**
   - Le navigateur charge la vidéo vers un stockage objet.
   - Le fichier n'est jamais envoyé directement depuis le navigateur vers RunPod.
   - L'API génère une URL temporaire signée pour le moteur GPU.

2. **Sélection du joueur**
   - L'utilisateur met la vidéo en pause sur une image où il est visible.
   - Il clique sur lui.
   - Le front enregistre `target.x`, `target.y` et `target_time_seconds`.

3. **Pré-contrôle gratuit**
   - Validation du format, de la durée et de la taille.
   - Estimation du coût GPU avant envoi.
   - Aucune requête RunPod n'est lancée sans validation explicite côté produit pendant la phase de développement.

4. **Analyse GPU**
   - Détection personnes + ballon.
   - Tracking temporel du joueur.
   - Ré-identification simple par apparence après perte de tracking.
   - Détection des changements de plan.
   - Détection et rejet des déplacements physiquement incohérents.
   - Estimation touches / possession lorsque la visibilité du ballon est suffisante.

5. **Contrôle qualité automatique**
   - Couverture de tracking.
   - Visibilité du ballon.
   - Similarité d'apparence du joueur.
   - Nombre de ruptures / ré-identifications.
   - Rejet automatique des statistiques trop peu fiables.

6. **Post-traitement**
   - Création de fenêtres temporelles autour des actions détectées.
   - Génération future des clips via FFmpeg.
   - Rapport joueur et chronologie du match.

7. **Restitution**
   - Tableau de bord match.
   - Statistiques avec niveau de confiance.
   - Clips téléchargeables/partageables.
   - Rapport PDF à terme.

## Composants

### `handler.py`
Moteur RunPod Serverless. Le GPU ne doit être sollicité que pour une analyse validée.

### `web/`
Prototype d'interface web. Il fonctionne sans backend pour la sélection locale du joueur et la préparation d'une requête d'analyse.

### Backend à connecter ensuite
Responsabilités prévues :
- comptes utilisateurs ;
- stockage vidéo ;
- création des URLs signées ;
- orchestration des jobs RunPod ;
- suivi de statut ;
- historique des matchs ;
- facturation client ;
- contrôle du budget GPU.

## Principe de fiabilité

Le produit ne doit jamais transformer une estimation faible en statistique présentée comme certaine. Toute métrique sensible passe par un seuil de qualité. Si le seuil n'est pas atteint, l'interface affiche que la donnée nécessite une vérification ou la masque.

## Distance parcourue

Une conversion naïve pixels → mètres n'est pas acceptable sur une caméra qui panote ou zoome. La version actuelle ne renvoie une distance métrique que si une calibration de terrain est fournie avec `static_camera: true`.

Pour une version commerciale compatible avec des vidéos Veo ou des caméras mobiles, il faudra une calibration dynamique du terrain image par image ou par segment de caméra.

## Coûts

Le développement du code, les commits GitHub et les contrôles statiques ne consomment pas le crédit RunPod. Les crédits GPU ne sont consommés qu'au moment d'une exécution réelle d'un worker. Pendant la phase de validation, les essais doivent être courts et précédés d'une estimation de coût.
