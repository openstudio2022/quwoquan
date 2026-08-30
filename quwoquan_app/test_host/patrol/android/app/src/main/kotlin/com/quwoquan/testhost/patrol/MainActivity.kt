package com.quwoquan.testhost.patrol

import android.os.Handler
import android.os.Looper
import com.quwoquan.quwoquan_app.RuntimeConfigMethodChannel
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import java.util.concurrent.Executors

class MainActivity : FlutterActivity() {
    // 读取涉及文件与验签，与生产侧一样不占用平台线程。
    private val runtimeConfigExecutor =
        Executors.newSingleThreadExecutor { runnable ->
            Thread(runnable, "qwq-uat-runtime-config").apply { isDaemon = true }
        }

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        // 共编译自生产源树的同一实现，宿主不持有测试专用的 runtime config 替身。
        RuntimeConfigMethodChannel.create(this).register(
            flutterEngine.dartExecutor.binaryMessenger,
            runtimeConfigExecutor,
            Handler(Looper.getMainLooper()),
        )
    }
}
