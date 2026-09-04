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

Une moyenne élevée peut masquer une longue perte d'identité. L'API publique exige donc simultanément :

- couverture globale >= 80 % ;
- score de tracking joueur >= 82 % ;
- couverture de la pire fenêtre de 30 s >= 65 % ;
- plus longue absence <= 5 s ;
- aucun changement de plan ;
- taux de ré-identification <= 5 % ;
- taux de rejet d'identité <= 5 %.

Mesures :
- `tracking_coverage_percent`
- `reidentifications`
- `identity_rejections`
- `mean_identity_appearance_similarity`
- `rejected_tracking_jumps`
- `minimum_window_coverage_percent`
- `longest_untracked_gap_seconds`
- `reidentification_rate_percent`
- `identity_rejection_rate_percent`

## Gate 3 — Ballon

Les statistiques issues du ballon ne sont considérées comme exploitables que si :
- le gate strict de continuité joueur est validé ;
- score de tracking joueur >= 82 % ;
- visibilité ballon >= 40 % des images échantillonnées ;
- au moins 30 images ont été analysées.

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

Le label interne `good` n'est pas une mesure de précision vérité terrain : il indique seulement que les diagnostics automatiques de continuité ont passé leurs seuils. Il ne suffit pas pour annoncer des statistiques commerciales fiables.

## Seuil de lancement d'un match de 90 minutes

Ne pas utiliser un match complet pour déboguer. Un test 90 min n'est justifié que lorsque :
- les tests 30 s, 2 min et 10 min passent ;
- aucun changement de joueur évident ;
- la mémoire GPU est stable ;
- le coût/minute est mesuré ;
- la précision des métriques affichées est acceptable.
