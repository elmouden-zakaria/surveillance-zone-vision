import argparse
import json
import os
import socket
import threading
import time
import cv2
import numpy as np
from flask import Flask, Response
from ultralytics import YOLO

ALERT_DELAY = 1.0
CONF_THRESHOLD = 0.5
ZONE_FILE = "zone.json"
points = []

flask_app = Flask(__name__)
latest_frame = None
frame_lock = threading.Lock()
firebase_ready = False
device_token = None

# État de la validation bimanuelle géré par le PC
bimanual_pressed = False

# --- PARAMÈTRES RÉSEAU UDP ---
# L'IP de votre tablette/téléphone Android (pour lui envoyer les statuts)
ANDROID_IP = "192.168.0.17"  # Mettez l'IP de votre appareil Android si différente
ANDROID_LISTEN_PORT = 5006
PC_LISTEN_PORT = 5005
udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

def udp_command_listener():
    """Écoute les commandes envoyées par l'application Android (ex: Arrêt d'urgence ou Bimanuel)"""
    global bimanual_pressed
    cmd_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        cmd_sock.bind(("0.0.0.0", PC_LISTEN_PORT))
        print(f"[INFO] Écoute des commandes UDP sur le port {PC_LISTEN_PORT}...")
    except Exception as e:
        print(f"[ERREUR] Impossible de lier le port UDP {PC_LISTEN_PORT}: {e}")
        return

    while True:
        try:
            data, addr = cmd_sock.recvfrom(1024)
            cmd = data.decode().strip()
            print(f"[COMMANDE REÇUE DE ANDROID] : {cmd}")
            
            if "BIMANUAL:PRESSE" in cmd:
                bimanual_pressed = True
            elif "BIMANUAL:NON PRESSE" in cmd:
                bimanual_pressed = False
            elif "CMD:EMERGENCY_STOP" in cmd:
                print("[ ALERTE ] ARRÊT D'URGENCE ACTIVÉ DEPUIS L'APPLICATION !")
        except Exception as e:
            print(f"[ERREUR UDP Listener] {e}")

# Démarrage du thread d'écoute UDP en arrière-plan
threading.Thread(target=udp_command_listener, daemon=True).start()

def send_udp_telemetry(status_scanner, st400="IDLE"):
    """Envoie l'état global du système vers l'application Android"""
    global bimanual_pressed
    bim_status = "PRESSE" if bimanual_pressed else "NON PRESSE"
    msg = f"SCANNER:{status_scanner};400:{st400};500:READY;600:IDLE;BIMANUAL:{bim_status}"
    try:
        udp_sock.sendto(msg.encode(), (ANDROID_IP, ANDROID_LISTEN_PORT))
    except Exception:
        pass

@flask_app.route("/video_feed")
def video_feed():
    def generate():
        while True:
            with frame_lock:
                if latest_frame is None:
                    continue
                ret, buffer = cv2.imencode(".jpg", latest_frame)
                jpg = buffer.tobytes()
            yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n")
    return Response(generate(), mimetype="multipart/x-mixed-replace; boundary=frame")

@flask_app.route("/")
def index():
    return ('<html><body style="margin:0;background:#000">'
            '<img src="/video_feed" style="width:100%"></body></html>')

def init_firebase():
    global firebase_ready
    try:
        import firebase_admin
        from firebase_admin import credentials
        cred = credentials.Certificate("serviceAccountKey.json")
        firebase_admin.initialize_app(cred)
        firebase_ready = True
        print("[INFO] Firebase initialisé.")
    except Exception as e:
        print(f"[INFO] Firebase non initialisé ({e}).")

def send_push_notification():
    """Envoie la notification Firebase au téléphone (dans un thread, sans figer la vidéo).
    Affiche dans le terminal la cause exacte si l'envoi échoue."""
    global firebase_ready, device_token
    if not firebase_ready:
        print("[PUSH] Firebase non initialisé : serviceAccountKey.json introuvable ou invalide.")
        return
    if not device_token:
        print('[PUSH] Aucun token : relance avec --device-token "TOKEN".')
        return

    def _send():
        try:
            from firebase_admin import messaging
            ts = time.strftime("%Y-%m-%d %H:%M:%S")
            message = messaging.Message(
                notification=messaging.Notification(
                    title="Intrusion détectée",
                    body=f"Personne détectée dans la zone interdite à {ts}",
                ),
                android=messaging.AndroidConfig(
                    priority="high",
                    notification=messaging.AndroidNotification(channel_id="intrusion_alerts"),
                ),
                token=device_token,
            )
            print(f"[PUSH] Notification envoyée : {messaging.send(message)}")
        except Exception as e:
            print(f"[PUSH] ERREUR : {e}")

    threading.Thread(target=_send, daemon=True).start()

def run_flask_server(port):
    flask_app.run(host="0.0.0.0", port=port, threaded=True, use_reloader=False)

def click_event(event, x, y, flags, param):
    global points
    if event == cv2.EVENT_LBUTTONDOWN:
        points.append((x, y))
    elif event == cv2.EVENT_RBUTTONDOWN and points:
        points.pop()

def save_zone(zone_points):
    with open(ZONE_FILE, "w") as f:
        json.dump(zone_points, f)
    print(f"[INFO] Zone enregistrée dans '{ZONE_FILE}'.")

def load_zone():
    if os.path.exists(ZONE_FILE):
        try:
            with open(ZONE_FILE, "r") as f:
                zone_points = json.load(f)
                if len(zone_points) >= 3:
                    print(f"[INFO] Zone chargée depuis '{ZONE_FILE}'.")
                    return zone_points
        except Exception as e:
            print(f"[ERREUR] Impossible de lire '{ZONE_FILE}': {e}")
    return None

def capture_snapshot(cap, force_redraw=False):
    global points
    if not force_redraw:
        saved_points = load_zone()
        if saved_points:
            return saved_points

    points = []
    ret, frame = cap.read()
    if not ret:
        return None
    
    cv2.namedWindow("Dessine ta zone (photo figee)")
    cv2.setMouseCallback("Dessine ta zone (photo figee)", click_event)
    while True:
        display = frame.copy()
        for p in points:
            cv2.circle(display, p, 6, (0, 255, 255), -1)
        if len(points) > 1:
            cv2.polylines(display, [np.array(points, dtype=int)], isClosed=len(points) > 2, color=(0, 255, 255), thickness=2)
        cv2.imshow("Dessine ta zone (photo figee)", display)
        key = cv2.waitKey(1) & 0xFF
        if key == ord("s") and len(points) >= 3:
            cv2.destroyWindow("Dessine ta zone (photo figee)")
            save_zone(points)
            return list(points)
        elif key == ord("r"):
            ret, frame = cap.read()
            points = []
        elif key == ord("q"):
            cv2.destroyWindow("Dessine ta zone (photo figee)")
            return None

def build_zone_mask(zone_points, w, h):
    mask = np.zeros((h, w), dtype=np.uint8)
    cv2.fillPoly(mask, [np.array(zone_points, dtype=int)], 255)
    return mask

def box_touches_zone(box, mask, w, h):
    x1, y1, x2, y2 = map(int, box)
    x1, x2 = max(0, min(w - 1, x1)), max(0, min(w - 1, x2))
    y1, y2 = max(0, min(h - 1, y1)), max(0, min(h - 1, y2))
    if x2 <= x1 or y2 <= y1:
        return False
    region = mask[y1:y2, x1:x2]
    return region.size > 0 and region.max() > 0

def log_alert(track_id):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    with open("alerts.log", "a") as f:
        f.write(f"[{ts}] ALERTE : id {track_id} en contact\n")
    send_push_notification()

def main():
    global device_token, bimanual_pressed
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="0")
    parser.add_argument("--model", default="yolov8n.pt")
    parser.add_argument("--device-token", default=None)
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--redraw-zone", action="store_true")
    args = parser.parse_args()
    device_token = args.device_token

    init_firebase()
    if not device_token:
        print('[PUSH] Attention : aucun --device-token fourni, les notifications ne seront pas envoyées.')
    threading.Thread(target=run_flask_server, args=(args.port,), daemon=True).start()

    source = int(args.source) if args.source.isdigit() else args.source
    cap = cv2.VideoCapture(source)
    
    zone_points = capture_snapshot(cap, force_redraw=args.redraw_zone)
    cap.release()
    if not zone_points:
        return

    model = YOLO(args.model)
    entry_times, alerted_ids = {}, set()
    surveillance_on = False
    frame_counter, mask = 0, None

    results_gen = model.track(source=source, classes=[0], conf=CONF_THRESHOLD, stream=True, persist=True, verbose=False)

    print("\n[INFO] Système démarré.")
    print(" - Touche [ESPACE] : Activer/Désactiver la surveillance")
    print(" - Touche [B]      : Basculer l'état bimanuel (PRESSE / NON PRESSE)")
    print(" - Touche [Q]      : Quitter\n")

    for result in results_gen:
        frame = result.orig_img.copy()
        frame_counter += 1
        h, w = frame.shape[:2]
        if mask is None:
            mask = build_zone_mask(zone_points, w, h)
        cv2.polylines(frame, [np.array(zone_points, dtype=int)], isClosed=True, color=(255, 255, 255), thickness=1)

        current_ids_in_zone = set()
        intrusion_this_frame = False

        if result.boxes and result.boxes.id is not None:
            for box, track_id in zip(result.boxes.xyxy.cpu().numpy(), result.boxes.id.cpu().numpy()):
                track_id = int(track_id)
                if surveillance_on and box_touches_zone(box, mask, w, h):
                    x1, y1, x2, y2 = box
                    current_ids_in_zone.add(track_id)
                    entry_times.setdefault(track_id, time.time())
                    elapsed = time.time() - entry_times[track_id]
                    cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), (0, 0, 255), 3)

                    if elapsed >= ALERT_DELAY:
                        intrusion_this_frame = True
                        if track_id not in alerted_ids:
                            log_alert(track_id)
                            alerted_ids.add(track_id)

        for tid in list(entry_times.keys()):
            if tid not in current_ids_in_zone:
                entry_times.pop(tid, None)
                alerted_ids.discard(tid)

        if intrusion_this_frame:
            send_udp_telemetry("INTRUSION", "STOPPED")
            if (frame_counter // 8) % 2 == 0:
                cv2.rectangle(frame, (0, 0), (w, h), (0, 0, 255), 15)
        else:
            send_udp_telemetry("CLEAR", "WELDING" if surveillance_on else "STANDBY")

        # Affichage visuel sur la fenêtre OpenCV locale
        status_text = f"SURVEILLANCE: {'ON' if surveillance_on else 'OFF'} | BIMANUAL: {'PRESSE' if bimanual_pressed else 'NON PRESSE'}"
        cv2.putText(frame, status_text, (10, h - 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0) if surveillance_on else (150, 150, 150), 2)

        with frame_lock:
            global latest_frame
            latest_frame = frame

        cv2.imshow("zone_ultimate", frame)
        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break
        elif key == ord(" "):
            surveillance_on = not surveillance_on
            entry_times.clear()
            alerted_ids.clear()
            print(f"[INFO] Surveillance : {surveillance_on}")
        elif key == ord("b"):
            bimanual_pressed = not bimanual_pressed
            print(f"[INFO] État Bimanuel simulé (Clavier PC) -> {'PRESSE' if bimanual_pressed else 'NON PRESSE'}")

    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
