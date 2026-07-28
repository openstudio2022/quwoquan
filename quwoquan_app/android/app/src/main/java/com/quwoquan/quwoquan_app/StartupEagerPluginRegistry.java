package com.quwoquan.quwoquan_app;

import androidx.annotation.NonNull;
import io.flutter.Log;
import io.flutter.embedding.engine.FlutterEngine;
import io.flutter.embedding.engine.plugins.FlutterPlugin;

/** Stable app-owned replacement for build-time mutation of GeneratedPluginRegistrant. */
final class StartupEagerPluginRegistry {
  private static final String TAG = "QWQStartup";

  private StartupEagerPluginRegistry() {}

  static void registerWith(@NonNull FlutterEngine flutterEngine) {
    registerPlugin(flutterEngine, "jni", "com.github.dart_lang.jni.JniPlugin");
    registerPlugin(flutterEngine, "jni_flutter", "com.github.dart_lang.jni_flutter.JniFlutterPlugin");
    registerPlugin(
        flutterEngine,
        "flutter_callkit_incoming",
        "com.hiennv.flutter_callkit_incoming.FlutterCallkitIncomingPlugin");
    registerPlugin(
        flutterEngine,
        "flutter_secure_storage",
        "com.it_nomads.fluttersecurestorage.FlutterSecureStoragePlugin");
    registerPlugin(
        flutterEngine,
        "firebase_core",
        "io.flutter.plugins.firebase.core.FlutterFirebaseCorePlugin");
    registerPlugin(
        flutterEngine,
        "firebase_messaging",
        "io.flutter.plugins.firebase.messaging.FlutterFirebaseMessagingPlugin");
    registerPlugin(
        flutterEngine,
        "shared_preferences_android",
        "io.flutter.plugins.sharedpreferences.SharedPreferencesPlugin");
    registerPlugin(flutterEngine, "sqflite_android", "com.tekartik.sqflite.SqflitePlugin");
    registerPlugin(
        flutterEngine,
        "video_player_android",
        "io.flutter.plugins.videoplayer.VideoPlayerPlugin");
    registerPlugin(
        flutterEngine,
        "flutter_plugin_android_lifecycle",
        "io.flutter.plugins.flutter_plugin_android_lifecycle.FlutterAndroidLifecyclePlugin");
    registerOptionalDevelopmentPlugin(
        flutterEngine,
        "integration_test",
        "dev.flutter.plugins.integration_test.IntegrationTestPlugin");
    registerOptionalDevelopmentPlugin(
        flutterEngine,
        "patrol",
        "pl.leancode.patrol.PatrolPlugin");
  }

  private static void registerPlugin(
      @NonNull FlutterEngine flutterEngine,
      @NonNull String pluginName,
      @NonNull String className) {
    try {
      Class<?> pluginClass = Class.forName(className);
      if (!FlutterPlugin.class.isAssignableFrom(pluginClass)) {
        Log.e(TAG, "Eager plugin does not implement FlutterPlugin: " + className);
        return;
      }
      Class<? extends FlutterPlugin> typedClass = pluginClass.asSubclass(FlutterPlugin.class);
      if (flutterEngine.getPlugins().has(typedClass)) {
        return;
      }
      flutterEngine.getPlugins().add(typedClass.getDeclaredConstructor().newInstance());
    } catch (Exception | LinkageError error) {
      Log.e(TAG, "Error registering eager plugin " + pluginName + ", " + className, error);
    }
  }

  private static void registerOptionalDevelopmentPlugin(
      @NonNull FlutterEngine flutterEngine,
      @NonNull String pluginName,
      @NonNull String className) {
    try {
      registerPlugin(flutterEngine, pluginName, className);
    } catch (LinkageError error) {
      Log.v(TAG, "Optional development plugin not present: " + pluginName);
    }
  }
}
