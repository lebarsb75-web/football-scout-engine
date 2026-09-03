# Football Scout Platform

Prototype de plateforme d'analyse vidéo individuelle pour joueurs de football.

## Branche de développement

`dev-v2` contient la nouvelle version en construction. Elle reste séparée de `main`, qui est reliée à l'endpoint RunPod actuel. Le but est de pouvoir améliorer le produit sans déclencher volontairement d'analyse GPU payante.

## Ce qui existe déjà dans `dev-v2`

### Moteur vidéo (`handler.py`)
- sélection du joueur à un instant choisi dans la vidéo ;
- détection personnes + ballon avec YOLO ;
- tracking temporel ;
- ré-identification simple par apparence ;
- détection des changements de plan ;
- lissage des déplacements et rejet de sauts incohérents ;
- estimation touches / possession ;
- timestamps et fenêtres de clips autour des actions ;
- score de qualité et seuils de fiabilité ;
- distance métrique uniquement avec calibration compatible.

### Prototype web (`web/`)
- dépôt local d'une vidéo ;
- lecture du match dans le navigateur ;
- pause à l'instant souhaité ;
- clic directement sur le joueur ;
- génération automatique des coordonnées normalisées et du timestamp ;
- aperçu de la requête prête à être envoyée ;
- exécution GPU volontairement verrouillée dans le prototype.

### API de sécurité coût (`api/`)
- endpoint de santé ;
- estimation de coût basée sur un benchmark réel ;
- refus automatique d'une analyse tant qu'aucun benchmark n'a été mesuré ;
- refus si l'estimation dépasse le plafond autorisé ;
- `ENABLE_PAID_GPU=false` par défaut.

### Post-traitement (`scripts/`)
- création de clips avec FFmpeg à partir des fenêtres d'actions ;
- génération d'un rapport HTML joueur à partir du JSON d'analyse.

### Contrôle qualité
- contrats JSON ;
- documentation des seuils ;
- checks GitHub gratuits pour la syntaxe Python/JavaScript et les garde-fous essentiels.

## Entrée RunPod

```json
{
  "input": {
    "video_url": "https://temporary-url-to-match.mp4",
    "target_time_seconds": 12.0,
    "target": {"x": 0.51, "y": 0.63},
    "sample_fps": 5,
    "confidence": 0.22,
    "image_size": 960
  }
}
```

La plateforme laisse l'utilisateur mettre la vidéo en pause et cliquer sur le joueur. `target.x` et `target.y` sont des coordonnées normalisées de 0 à 1 sur cette image.

## Distance réelle

Un simple coefficient pixels → mètres est faux sur une caméra avec perspective, zoom ou mouvement.

La version actuelle accepte une homographie seulement pour un cas explicitement déclaré comme caméra fixe :

```json
{
  "pitch_calibration": {
    "static_camera": true,
    "image_points": [[120, 680], [1720, 680], [1450, 260], [430, 260]],
    "pitch_points_meters": [[0, 0], [105, 0], [105, 68], [0, 68]]
  }
}
```

Au moins quatre correspondances sont nécessaires. Sur une vidéo Veo / caméra qui bouge, la distance en mètres reste masquée tant qu'une calibration dynamique n'est pas ajoutée.

## Politique de coût pendant le développement

1. Pas de match complet pour déboguer.
2. Pas d'exécution payante tant que les contrôles gratuits ne sont pas terminés.
3. Premier test payant uniquement sur un extrait court.
4. Mesure du vrai temps GPU par minute de vidéo.
5. Calcul d'un coût prévisionnel avec marge de sécurité.
6. Match de 90 minutes seulement après validation technique et explicite du budget.

## Statut

Le produit est encore en développement. Les chiffres de touches, possession, distance et suivi doivent être validés contre des séquences annotées manuellement avant utilisation commerciale.
