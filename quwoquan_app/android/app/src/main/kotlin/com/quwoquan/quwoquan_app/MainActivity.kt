package com.quwoquan.quwoquan_app

import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {
    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(
            flutterEngine.dartExecutor.binaryMessenger,
            "quwoquan/auth/one_tap"
        ).setMethodCallHandler { call, result ->
            when (call.method) {
                "isAvailable" -> result.success(false)
                "requestLoginToken" -> result.error(
                    "one_tap_sdk_not_configured",
                    "One-tap login SDK is not configured for this build.",
                    null
                )
                else -> result.notImplemented()
            }
        }
    }
}
