# Quality gates avant commercialisation

## Règle générale

Aucune statistique ne doit être affichée comme fiable uniquement parce que le moteur a produit un nombre. La qualité de l'analyse doit être mesurée séparément.

## Gate 0 — Sécurité coût

Avant un test GPU de développement :
- durée de l'extrait connue ;
- type de GPU connu ;
- coût maximal estimé ;
- aucun second worker ;
- pas de match complet tant que les extraits courts ne sont pas validés.

## Gate 1 — Sélection joueur

Le joueur sélectionné doit être détecté sur l'image de référence et la détection doit être proche du point cliqué.

Échec : pas d'analyse longue, retour utilisateur pour choisir une meilleure image.

## Gate 2 — Tracking joueur

Objectif prototype : couverture >= 80 % sur des séquences où le joueur est visible.

Mesures :
- `tracking_coverage_percent`
- `reidentifications`
- `identity_rejections`
- `mean_identity_appearance_similarity`
- `rejected_tracking_jumps`

## Gate 3 — Ballon

Les statistiques issues du ballon ne sont considérées comme exploitables que si :
- tracking joueur >= 75 % ;
- visibilité ballon >= 35 % des images échantillonnées ;
- score qualité global >= 70 %.

En dessous, touches et possession restent des estimations techniques et ne doivent pas être présentées au client comme des statistiques vérifiées.

## Gate 4 — Distance

### Caméra fixe
Une homographie terrain peut permettre une distance métrique si quatre correspondances terrain/image ou plus sont disponibles.

### Caméra mobile / Veo / diffusion
Une homographie unique est insuffisante. La distance en mètres est masquée jusqu'à mise en place d'une calibration dynamique du terrain.

## Gate 5 — Validation sur vérité terrain

Avant vente : constituer un jeu d'au moins 10 séquences annotées manuellement avec :
- identité joueur image par image ou par intervalles ;
- touches de balle réelles ;
- périodes de possession ;
- actions importantes ;
- distance de référence lorsque mesurable.

Comparer ensuite prédiction et annotation.

## Seuil de lancement d'un match de 90 minutes

Ne pas utiliser un match complet pour déboguer. Un test 90 min n'est justifié que lorsque :
- les tests 30 s, 2 min et 10 min passent ;
- aucun changement de joueur évident ;
- la mémoire GPU est stable ;
- le coût/minute est mesuré ;
- la précision des métriques affichées est acceptable.
