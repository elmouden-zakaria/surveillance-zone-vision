# Surveillance de zone par vision artificielle

Prototype de surveillance d'une zone interdite : une webcam filme la zone, un programme Python détecte les
personnes avec **YOLOv8** et déclenche une alerte lorsqu'une personne reste plus d'une seconde dans le périmètre
tracé par l'utilisateur. L'alerte est affichée à l'écran, enregistrée dans un journal et transmise à une
**application Android** (vidéo en direct, état du système, notification push).

Projet réalisé dans le cadre d'un stage d'application en milieu industriel (génie mécatronique).

> **Avertissement.** Ce dépôt contient un prototype de supervision, validé en simulation sur ordinateur.
> Il ne constitue **pas** un dispositif de sécurité certifié et ne remplace ni les protections câblées,
> ni l'arrêt d'urgence réglementaire. Le bouton « arrêt d'urgence » de l'application est une commande de démonstration.

## Fonctionnalités

- Détection de personnes en temps réel (YOLOv8n) avec suivi par identifiant
- Zone interdite dessinée par l'utilisateur sur une image figée, enregistrée dans `zone.json`
- Détection d'intrusion par recouvrement entre la boîte de la personne et le masque de la zone, avec temporisation (1 s)
- Journal horodaté des alertes (`alerts.log`)
- Flux vidéo MJPEG diffusé par Flask (port 5000)
- Échanges avec l'application par UDP (commandes sur le port 5005, état sur le port 5006)
- Notification push via Firebase Cloud Messaging
- Application Android (Java) : vidéo en direct, choix de ligne, état de sécurité, bouton d'arrêt d'urgence de démonstration

## Architecture

```
Webcam ──► PC (Python, OpenCV, YOLOv8, Flask) ──► Application Android (WebView)
                 │        ▲                              ▲
                 │        └── UDP 5005 : commandes       │
                 ├──────────► UDP 5006 : état ────────────┤
                 ├──────────► HTTP 5000 : vidéo MJPEG ────┤
                 ├──────────► Firebase (FCM) : notification
                 └──────────► alerts.log
```

## Installation du serveur

Prérequis : Python 3.10 ou plus récent, une webcam.

```bash
git clone https://github.com/VOTRE_PSEUDO/surveillance-zone-vision.git
cd surveillance-zone-vision/server
python -m pip install -r requirements.txt
```

Le modèle `yolov8n.pt` est téléchargé automatiquement au premier lancement.

## Configuration

Dans `server/server_stream.py`, adapter si besoin :

| Paramètre | Rôle | Valeur par défaut |
|---|---|---|
| `ANDROID_IP` | adresse IP du téléphone (état envoyé par UDP) | `192.168.0.17` |
| `ALERT_DELAY` | durée de présence avant alerte | `1.0` s |
| `CONF_THRESHOLD` | seuil de confiance de détection | `0.5` |

### Notifications Firebase (facultatif)

1. Créer un projet sur la console Firebase.
2. Paramètres du projet > Comptes de service > **Générer une nouvelle clé privée** : renommer le fichier en
   `serviceAccountKey.json` et le placer à côté de `server_stream.py`.
3. Ajouter l'application Android au **même** projet Firebase (voir `android/README.md`).

Ces deux fichiers sont des secrets : ils sont exclus du dépôt par `.gitignore`. Ne les publiez jamais.

## Utilisation

```bash
cd server
python server_stream.py --source 0 --device-token "TOKEN_DU_TELEPHONE"
```

- Au premier lancement, une fenêtre affiche une image figée : cliquer les sommets de la zone, puis appuyer sur `s`.
  La zone est enregistrée dans `zone.json` et rechargée automatiquement ensuite.
- Pour redessiner la zone : ajouter `--redraw-zone`.
- Sans `--device-token`, le système fonctionne sans notification.

| Touche | Action |
|---|---|
| `ESPACE` | activer / désactiver la surveillance |
| `B` | simuler l'état de la commande bimanuelle |
| `Q` | quitter |

Le flux vidéo est consultable sur `http://IP_DU_PC:5000`.

## Application Android

Voir [`android/README.md`](android/README.md).

## Limites et perspectives

- L'arrêt d'urgence logiciel doit être relié à un automate et à un relais de sécurité (l'arrêt câblé est conservé).
- L'UDP n'a ni accusé de réception ni authentification : prévoir un jeton, un signal de vie et un réseau dédié.
- Détection par boîte englobante : à affiner (position des pieds, segmentation).
- Webcam sensible à l'éclairage : prévoir une caméra industrielle IP et un éclairage adapté.
- Gestion de plusieurs zones.

## Licence

MIT, voir [`LICENSE`](LICENSE).

## Auteur

Zakaria El Mouden
