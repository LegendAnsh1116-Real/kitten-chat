package com.kitten.chat

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.webkit.*
import android.widget.Toast
import androidx.activity.OnBackPressedCallback
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat

class MainActivity : AppCompatActivity() {

    private lateinit var webView: WebView
    private var filePathCallback: ValueCallback<Array<android.net.Uri>>? = null

    private val fileChooserLauncher =
        registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
            if (result.resultCode == RESULT_OK) {
                val intentData: Intent? = result.data
                val selectedUri: android.net.Uri? = intentData?.data
                selectedUri?.let { uri ->
                    try {
                        val inputStream = contentResolver.openInputStream(uri)
                        val bytes = inputStream?.readBytes()
                        val base64String = android.util.Base64.encodeToString(bytes, android.util.Base64.NO_WRAP)
                        webView.post {
                            webView.evaluateJavascript("window.updateProfilePicture('$base64String');", null)
                        }
                        filePathCallback?.onReceiveValue(arrayOf(uri))
                    } catch (e: Exception) {
                        filePathCallback?.onReceiveValue(null)
                    }
                }
            } else {
                filePathCallback?.onReceiveValue(null)
            }
            filePathCallback = null
        }

    private val requestPermissionLauncher = registerForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { permissions ->
        val allGranted = permissions.entries.all { it.value }
        if (allGranted) {
            val isStorage = permissions.containsKey(Manifest.permission.READ_EXTERNAL_STORAGE) ||
                    permissions.containsKey(Manifest.permission.READ_MEDIA_IMAGES)
            if (isStorage) triggerGallery()
        } else {
            Toast.makeText(this, "Permission denied. Please enable in Settings.", Toast.LENGTH_LONG).show()
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        webView = findViewById(R.id.webView)
        webView.setBackgroundColor(android.graphics.Color.TRANSPARENT)
        webView.setLayerType(WebView.LAYER_TYPE_HARDWARE, null)
        webView.isVerticalScrollBarEnabled = false
        webView.isHorizontalScrollBarEnabled = false
        checkAndRequestPermissions()

        webView.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            allowFileAccess = true
            allowContentAccess = true
            mediaPlaybackRequiresUserGesture = false
            mixedContentMode = WebSettings.MIXED_CONTENT_ALWAYS_ALLOW

            // 🔥 ADD THESE
            loadWithOverviewMode = true
            useWideViewPort = true
            setSupportZoom(false)
            builtInZoomControls = false
            displayZoomControls = false
        }

        webView.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(
                view: WebView?,
                request: WebResourceRequest?
            ): Boolean {
                return false
            }
        }

        webView.webChromeClient = object : WebChromeClient() {
            override fun onShowFileChooser(v: WebView?, f: ValueCallback<Array<android.net.Uri>>?, p: FileChooserParams?): Boolean {
                filePathCallback = f
                p?.createIntent()?.let { fileChooserLauncher.launch(it) }
                return true
            }
            override fun onPermissionRequest(request: PermissionRequest?) { request?.grant(request.resources) }
        }

        webView.addJavascriptInterface(AndroidBridge(), "Android")

        // 🔥 DEBUG (remove in release if needed)
        val isDebuggable = (applicationInfo.flags and android.content.pm.ApplicationInfo.FLAG_DEBUGGABLE) != 0
        if (isDebuggable) {
            WebView.setWebContentsDebuggingEnabled(true)
        }


        // 🔥 PERFORMANCE + SCALING FIX

        webView.loadUrl("https://kitten-couple-chat.site")

        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (webView.canGoBack()) webView.goBack()
                else webView.evaluateJavascript("if(window.showExitPopup){window.showExitPopup();}else{window.history.back();}", null)
            }
        })
    }

    private fun checkAndRequestPermissions() {
        val storage = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) Manifest.permission.READ_MEDIA_IMAGES else Manifest.permission.READ_EXTERNAL_STORAGE
        val list = arrayOf(Manifest.permission.CAMERA, Manifest.permission.RECORD_AUDIO, storage)
        val toRequest = list.filter { ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED }
        if (toRequest.isNotEmpty()) requestPermissionLauncher.launch(toRequest.toTypedArray())
    }

    private fun triggerGallery() {
        val intent = Intent(Intent.ACTION_GET_CONTENT).apply {
            type = "image/*"
            addCategory(Intent.CATEGORY_OPENABLE)
        }
        fileChooserLauncher.launch(Intent.createChooser(intent, "Select Picture"))
    }

    private fun showSettingsDialog(title: String, message: String) {
        AlertDialog.Builder(this)
            .setTitle(title)
            .setMessage(message)
            .setPositiveButton("Settings") { _, _ ->
                val intent = Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS)
                intent.data = android.net.Uri.fromParts("package", packageName, null)
                startActivity(intent)
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    inner class AndroidBridge {
        @JavascriptInterface
        fun closeApp() { finishAffinity() }

        @JavascriptInterface
        fun openGallery() {
            runOnUiThread {
                val storage = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) Manifest.permission.READ_MEDIA_IMAGES else Manifest.permission.READ_EXTERNAL_STORAGE
                when {
                    ContextCompat.checkSelfPermission(this@MainActivity, storage) == PackageManager.PERMISSION_GRANTED -> triggerGallery()
                    ActivityCompat.shouldShowRequestPermissionRationale(this@MainActivity, storage) -> requestPermissionLauncher.launch(arrayOf(storage))
                    else -> {
                        // This handles the "Never show again" case
                        if (ContextCompat.checkSelfPermission(this@MainActivity, storage) == PackageManager.PERMISSION_DENIED) {
                            showSettingsDialog("Storage Permission", "Please allow storage access in Settings to upload photos.")
                        } else {
                            requestPermissionLauncher.launch(arrayOf(storage))
                        }
                    }
                }
            }
        }

        @JavascriptInterface
        fun requestCameraAndMic() {
            runOnUiThread {
                val camera = Manifest.permission.CAMERA
                if (ContextCompat.checkSelfPermission(this@MainActivity, camera) != PackageManager.PERMISSION_GRANTED) {
                    if (!ActivityCompat.shouldShowRequestPermissionRationale(this@MainActivity, camera)) {
                        showSettingsDialog("Camera Permission", "Camera access is permanently denied. Please enable it in Settings.")
                    } else {
                        requestPermissionLauncher.launch(arrayOf(camera, Manifest.permission.RECORD_AUDIO))
                    }
                } else {
                    Toast.makeText(this@MainActivity, "Already enabled", Toast.LENGTH_SHORT).show()
                }
            }
        }
    }
}