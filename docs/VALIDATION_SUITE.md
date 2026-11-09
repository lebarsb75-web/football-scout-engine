# Validation sur un lot de séquences annotées

Le moteur ne doit pas être présenté comme fiable sur la seule base d'un score de continuité. Il faut comparer les positions prédites à des annotations indépendantes de la vidéo.

## Préparation

Pour chaque extrait, conserver deux fichiers :
- le résultat privé d'analyse qui contient `validation.tracking_trace` ;
- les annotations humaines au format `contracts/tracking-annotations.example.json`.

Créer un fichier `manifest.json` dans le même dossier :

```json
{
  "sequences": [
    {
      "name": "match-01-extrait-01",
      "result": "results/extrait-01.json",
      "annotations": "labels/extrait-01.json"
    }
  ]
}
```

Ajouter **au moins 10 séquences indépendantes** avant de considérer la validation tracking comme réussie. Le nombre minimum est imposé par défaut.

## Commande

```bash
python scripts/evaluate_validation_suite.py manifest.json --output tracking-validation.json
```

Le script n'envoie aucune vidéo, n'appelle ni RunPod ni Cloudflare et n'entraîne aucun coût GPU.

- Code de sortie `0` : 10 séquences ou plus, toutes conformes au gate de suivi individuel.
- Code de sortie `1` : séquences manquantes, une ou plusieurs séquences non conformes, ou erreur de lecture d'une séquence.
- Code de sortie `2` : manifest invalide.

Le rapport liste les mesures et les échecs de chaque extrait pour aider à isoler les défauts. **Même si le suivi réussit, les statistiques de touches, possession, passes, duels, vitesse et distance ne sont pas validées automatiquement.** Leur comparaison à des annotations de référence est un chantier séparé, indispensable avant toute commercialisation.
