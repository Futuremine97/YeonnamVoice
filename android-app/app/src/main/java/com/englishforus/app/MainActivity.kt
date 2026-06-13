package com.englishforus.app

import android.Manifest
import android.app.Activity
import android.app.AlertDialog
import android.content.Context
import android.content.pm.PackageManager
import android.os.Bundle
import android.webkit.PermissionRequest
import android.webkit.WebChromeClient
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.EditText
import android.widget.Toast

/**
 * English For Us — Android WebView 앱.
 *
 * 같은 Wi-Fi의 PC에서 도는 서버(server.py)의 화면(/app)을 불러온다.
 * 폰에서 사용하는 권한: 인터넷 + 마이크(영어 발화). 폰의 다른 데이터에는 접근하지 않는다.
 */
class MainActivity : Activity() {

    private lateinit var web: WebView
    private var pendingPermission: PermissionRequest? = null

    private val prefs by lazy { getSharedPreferences("efu", Context.MODE_PRIVATE) }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        web = WebView(this)
        setContentView(web)

        web.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            databaseEnabled = true
            mediaPlaybackRequiresUserGesture = false   // 음성 자동재생 허용
        }
        web.webViewClient = object : WebViewClient() {
            override fun onReceivedError(
                v: WebView?, req: android.webkit.WebResourceRequest?, err: android.webkit.WebResourceError?
            ) {
                // 서버에 접속 못하면 주소 다시 입력받기
                runOnUiThread { askServerUrl(true) }
            }
        }
        web.webChromeClient = object : WebChromeClient() {
            // WebView 안에서 getUserMedia(마이크) 요청 시 권한 부여
            override fun onPermissionRequest(request: PermissionRequest) {
                runOnUiThread {
                    if (hasMic()) {
                        request.grant(request.resources)
                    } else {
                        pendingPermission = request
                        requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), REQ_MIC)
                    }
                }
            }
        }

        if (!hasMic()) requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), REQ_MIC)

        val saved = prefs.getString("base_url", null)
        if (saved.isNullOrBlank()) askServerUrl(false) else loadApp(saved)
    }

    private fun hasMic() =
        checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED

    private fun normalize(url: String): String {
        var u = url.trim()
        if (!u.startsWith("http://") && !u.startsWith("https://")) u = "http://$u"
        return u.trimEnd('/')
    }

    private fun loadApp(base: String) {
        val b = normalize(base)
        prefs.edit().putString("base_url", b).apply()
        web.loadUrl("$b/app")
    }

    /** PC 서버 주소 입력 다이얼로그 (예: http://192.168.0.10:8000) */
    private fun askServerUrl(isError: Boolean) {
        val input = EditText(this).apply {
            hint = "http://192.168.0.10:8000"
            setText(prefs.getString("base_url", "http://"))
        }
        AlertDialog.Builder(this)
            .setTitle(if (isError) "서버에 연결할 수 없어요" else "PC 서버 주소 입력")
            .setMessage("같은 Wi-Fi에 연결된 PC에서 server.py가 실행 중이어야 합니다.\nPC의 IP와 포트(기본 8000)를 입력하세요.")
            .setView(input)
            .setCancelable(false)
            .setPositiveButton("연결") { _, _ ->
                val v = input.text.toString()
                if (v.isBlank()) { Toast.makeText(this, "주소를 입력하세요", Toast.LENGTH_SHORT).show(); askServerUrl(false) }
                else loadApp(v)
            }
            .show()
    }

    override fun onRequestPermissionsResult(rc: Int, perms: Array<out String>, results: IntArray) {
        super.onRequestPermissionsResult(rc, perms, results)
        if (rc == REQ_MIC) {
            val granted = results.isNotEmpty() && results[0] == PackageManager.PERMISSION_GRANTED
            pendingPermission?.let { if (granted) it.grant(it.resources) else it.deny() }
            pendingPermission = null
        }
    }

    // 뒤로가기 = 웹 히스토리 뒤로
    override fun onBackPressed() {
        if (web.canGoBack()) web.goBack() else super.onBackPressed()
    }

    companion object { private const val REQ_MIC = 1 }
}
