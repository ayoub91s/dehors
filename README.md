# dehors. V15 — agenda connecté

L'application lit `events.json` à chaque ouverture (et après rechargement de la page). Le calendrier affiche les occurrences datées, tandis que « À ne pas manquer » affiche les événements à venir.

## Mise en ligne

1. Créer un dépôt GitHub public et y envoyer **le contenu** de ce dossier (y compris `.github/workflows`).
2. Dans **Settings → Pages**, choisir **Deploy from a branch**, branche `main`, dossier `/ (root)`.
3. Dans **Actions**, exécuter manuellement le workflow « Actualiser les événements » une première fois. Ensuite, il est planifié chaque jour (l'horaire peut varier).
4. Ouvrir l'URL GitHub Pages du dépôt. Le flux JSON sera lu automatiquement à chaque chargement.

Le script `update_events.py` lit les données ouvertes de la Région Île-de-France (OpenAgenda). Il ne crée aucune annonce de toutes pièces et conserve le dernier fichier `events.json` si la synchronisation échoue. La disponibilité, les horaires et les tarifs sont à confirmer sur la source. Les événements qui ne sont pas dans le jeu de données régional (notamment les nocturnes privées) nécessitent une source complémentaire. La date de mise à jour est visible dans l'application.

**Limites :** dans un fichier HTML ouvert en `file://`, la récupération du flux local JSON est bloquée par les navigateurs. Il faut un hébergement web. Les événements déjà intégrés à la V14 restent accessibles en mode local. Il n'y a pas encore de notifications push, ni de mise à jour en arrière-plan sur un téléphone fermé.

Source : https://data.iledefrance.fr/explore/dataset/evenements-publics-cibul/api/
