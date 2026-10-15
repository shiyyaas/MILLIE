package com.millie.app;

import android.Manifest;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.Bundle;
import android.util.Log;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import androidx.annotation.NonNull;
import androidx.appcompat.app.AppCompatActivity;
import androidx.core.app.ActivityCompat;
import androidx.core.content.ContextCompat;

import com.chaquo.python.PyObject;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;

import java.io.File;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.ArrayList;
import java.util.List;

public class MainActivity extends AppCompatActivity {

    private static final String TAG = "MILLIE_MainActivity";
    private static final int PERMISSION_REQUEST_CODE = 1001;
    private static final int PORT = 8770;
    private static final String SERVER_URL = "http://127.0.0.1:" + PORT;

    private WebView webView;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        webView = findViewById(R.id.webview);
        setupWebView();

        checkAndRequestPermissions();

        initPythonAndStartBackend();
        waitForServerAndLoad();
    }

    private void setupWebView() {
        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setCacheMode(WebSettings.LOAD_DEFAULT);
        settings.setDatabaseEnabled(true);
        settings.setAllowFileAccess(true);
        settings.setAllowContentAccess(true);
        settings.setMediaPlaybackRequiresUserGesture(false);

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, String url) {
                view.loadUrl(url);
                return true;
            }
        });
    }

    private void checkAndRequestPermissions() {
        List<String> permissions = new ArrayList<>();
        permissions.add(Manifest.permission.ACCESS_FINE_LOCATION);
        permissions.add(Manifest.permission.ACCESS_COARSE_LOCATION);

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            permissions.add(Manifest.permission.BLUETOOTH_SCAN);
            permissions.add(Manifest.permission.BLUETOOTH_CONNECT);
        }

        List<String> listPermissionsNeeded = new ArrayList<>();
        for (String p : permissions) {
            if (ContextCompat.checkSelfPermission(this, p) != PackageManager.PERMISSION_GRANTED) {
                listPermissionsNeeded.add(p);
            }
        }

        if (!listPermissionsNeeded.isEmpty()) {
            ActivityCompat.requestPermissions(
                    this,
                    listPermissionsNeeded.toArray(new String[0]),
                    PERMISSION_REQUEST_CODE
            );
        }
    }

    private void initPythonAndStartBackend() {
        if (!Python.isStarted()) {
            Python.start(new AndroidPlatform(this));
        }

        File filesDir = getFilesDir();
        Python py = Python.getInstance();

        // Set MILLIE_HOME in Python environment
        PyObject osModule = py.getModule("os");
        PyObject environ = osModule.get("environ");
        environ.callAttr("__setitem__", "MILLIE_HOME", filesDir.getAbsolutePath());

        new Thread(() -> {
            try {
                PyObject millieModule = py.getModule("millie");
                millieModule.callAttr("start_server", PORT);
            } catch (Exception e) {
                Log.e(TAG, "Error running Python backend", e);
            }
        }, "MillieBackendThread").start();
    }

    private void waitForServerAndLoad() {
        new Thread(() -> {
            boolean serverReady = false;
            int maxAttempts = 100;
            int attempts = 0;

            while (!serverReady && attempts < maxAttempts) {
                attempts++;
                try {
                    URL url = new URL(SERVER_URL + "/api/radar");
                    HttpURLConnection connection = (HttpURLConnection) url.openConnection();
                    connection.setConnectTimeout(800);
                    connection.setReadTimeout(800);
                    connection.setRequestMethod("GET");
                    int responseCode = connection.getResponseCode();
                    if (responseCode >= 200 && responseCode < 500) {
                        serverReady = true;
                    }
                    connection.disconnect();
                } catch (Exception ignored) {
                }

                if (!serverReady) {
                    try {
                        Thread.sleep(250);
                    } catch (InterruptedException e) {
                        break;
                    }
                }
            }

            if (serverReady) {
                runOnUiThread(() -> webView.loadUrl(SERVER_URL));
            } else {
                Log.e(TAG, "Backend server failed to respond on port " + PORT);
            }
        }, "ServerPollThread").start();
    }

    @Override
    public void onBackPressed() {
        if (webView != null && webView.canGoBack()) {
            webView.goBack();
        } else {
            super.onBackPressed();
        }
    }
}
