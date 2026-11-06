package com.renault.survaillern;

import android.Manifest;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.Bundle;
import android.util.Log;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.RadioButton;
import android.widget.Toast;
import androidx.appcompat.app.AppCompatActivity;
import androidx.core.app.ActivityCompat;
import androidx.core.content.ContextCompat;

import com.google.firebase.messaging.FirebaseMessaging;

import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;

public class MainActivity extends AppCompatActivity {

    // ==================== CONFIGURATION RÉSEAU ====================
    private static final String PC_IP = "192.168.0.X"; // IP locale du PC qui exécute le serveur (ipconfig)
    private static final int SEND_PORT = 5005;

    private WebView webViewStream;
    private RadioButton rbStepway, rbXjk;
    private Button btnEmergencyStop;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        webViewStream = findViewById(R.id.webViewStream);
        rbStepway = findViewById(R.id.rbStepway);
        rbXjk = findViewById(R.id.rbXjk);
        btnEmergencyStop = findViewById(R.id.btnEmergencyStop);

        setupNotifications();   // <-- AJOUT
        setupVideoFeed();

        rbStepway.setOnCheckedChangeListener((buttonView, isChecked) -> {
            if (isChecked) {
                sendUdpCommand("CMD:ZONE:STEPWAY");
                updateVideoUrl("stepway");
                Toast.makeText(MainActivity.this, "Zone: STEPWAY", Toast.LENGTH_SHORT).show();
            }
        });

        rbXjk.setOnCheckedChangeListener((buttonView, isChecked) -> {
            if (isChecked) {
                sendUdpCommand("CMD:ZONE:XJK");
                updateVideoUrl("xjk");
                Toast.makeText(MainActivity.this, "Zone: XJK", Toast.LENGTH_SHORT).show();
            }
        });

        btnEmergencyStop.setOnClickListener(v -> {
            sendUdpCommand("CMD:EMERGENCY_STOP");
            Toast.makeText(MainActivity.this, "ARRÊT D'URGENCE TRANSMIS !", Toast.LENGTH_SHORT).show();
        });
    }

    // ==================== NOTIFICATIONS FIREBASE (AJOUT) ====================
    private void setupNotifications() {
        // 1) Canal de notification (obligatoire Android 8+)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel channel = new NotificationChannel(
                    "intrusion_alerts", "Alertes d'intrusion", NotificationManager.IMPORTANCE_HIGH);
            getSystemService(NotificationManager.class).createNotificationChannel(channel);
        }

        // 2) Permission d'afficher des notifications (obligatoire Android 13+)
        if (Build.VERSION.SDK_INT >= 33
                && ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS)
                != PackageManager.PERMISSION_GRANTED) {
            ActivityCompat.requestPermissions(this,
                    new String[]{Manifest.permission.POST_NOTIFICATIONS}, 101);
        }

        // 3) Récupération du token du téléphone, affiché dans Logcat
        FirebaseMessaging.getInstance().getToken().addOnCompleteListener(task -> {
            if (task.isSuccessful()) {
                Log.d("FCM_TOKEN", "Token : " + task.getResult());
            } else {
                Log.e("FCM_TOKEN", "Échec récupération du token", task.getException());
            }
        });
    }

    // ==================== CONFIGURATION DU FLUX VIDÉO ====================
    private void setupVideoFeed() {
        WebSettings webSettings = webViewStream.getSettings();
        webSettings.setJavaScriptEnabled(true);
        webSettings.setLoadWithOverviewMode(true);
        webSettings.setUseWideViewPort(true);
        webSettings.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);

        webViewStream.setWebViewClient(new WebViewClient());
        updateVideoUrl("stepway");
    }

    private void updateVideoUrl(String zone) {
        String videoUrl = "http://" + PC_IP + ":5000/video_feed?zone=" + zone;
        String html = "<html>"
                + "<head><meta name='viewport' content='width=device-width, initial-scale=1.0'></head>"
                + "<body style='margin:0;padding:0;background:#000;overflow:hidden;'>"
                + "<img src='" + videoUrl + "' style='width:100%;height:100%;object-fit:fill;'/>"
                + "</body></html>";

        webViewStream.loadDataWithBaseURL("http://" + PC_IP + ":5000", html, "text/html", "UTF-8", null);
    }

    // ==================== ENVOI DES COMMANDES UDP ====================
    private void sendUdpCommand(final String message) {
        new Thread(() -> {
            try {
                DatagramSocket socket = new DatagramSocket();
                byte[] data = message.getBytes();
                InetAddress address = InetAddress.getByName(PC_IP);
                DatagramPacket packet = new DatagramPacket(data, data.length, address, SEND_PORT);

                socket.send(packet);
                socket.close();
            } catch (Exception e) {
                e.printStackTrace();
            }
        }).start();
    }
}