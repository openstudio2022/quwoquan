package com.quwoquan.quwoquan_app;

import androidx.annotation.NonNull;
import io.flutter.Log;
import io.flutter.embedding.engine.FlutterEngine;
import io.flutter.embedding.engine.plugins.FlutterPlugin;

/** 冷启动延后注册的重 native 插件，首次进入 RTC / 创作入口时再链接。 */
final class StartupDeferredPluginRegistry {
  private static final String TAG = "QWQStartup";
  private static boolean rtcRegistered;
  private static boolean contentEntryRegistered;
  private static boolean locationRegistered;

  private StartupDeferredPluginRegistry() {}

  static synchronized void ensureRtc(@NonNull FlutterEngine flutterEngine) {
    if (rtcRegistered) {
      return;
    }
    registerPlugin(
        flutterEngine, "flutter_webrtc", "com.cloudwebrtc.webrtc.FlutterWebRTCPlugin");
    registerPlugin(
        flutterEngine, "livekit_client", "io.livekit.plugin.LiveKitPlugin");
    registerPlugin(
        flutterEngine,
        "flutter_callkit_incoming",
        "com.hiennv.flutter_callkit_incoming.FlutterCallkitIncomingPlugin");
    rtcRegistered = true;
    Log.i(TAG, "android_deferred_rtc_plugins_registered");
  }

  static synchronized void ensureContentEntry(@NonNull FlutterEngine flutterEngine) {
    if (contentEntryRegistered) {
      return;
    }
    registerPlugin(
        flutterEngine,
        "camera_android_camerax",
        "io.flutter.plugins.camerax.CameraAndroidCameraxPlugin");
    registerPlugin(
        flutterEngine,
        "image_picker_android",
        "io.flutter.plugins.imagepicker.ImagePickerPlugin");
    registerPlugin(
        flutterEngine,
        "photo_manager",
        "com.fluttercandies.photo_manager.PhotoManagerPlugin");
    registerPlugin(
        flutterEngine,
        "video_thumbnail",
        "xyz.justsoft.video_thumbnail.VideoThumbnailPlugin");
    contentEntryRegistered = true;
    Log.i(TAG, "android_deferred_content_entry_plugins_registered");
  }

  static synchronized void ensureLocation(@NonNull FlutterEngine flutterEngine) {
    if (locationRegistered) {
      return;
    }
    registerPlugin(
        flutterEngine,
        "geolocator_android",
        "com.baseflow.geolocator.GeolocatorPlugin");
    locationRegistered = true;
    Log.i(TAG, "android_deferred_location_plugins_registered");
  }

  private static void registerPlugin(
      @NonNull FlutterEngine flutterEngine,
      @NonNull String pluginName,
      @NonNull String className) {
    try {
      Class<?> pluginClass = Class.forName(className);
      Object plugin = pluginClass.getDeclaredConstructor().newInstance();
      if (plugin instanceof FlutterPlugin) {
        flutterEngine.getPlugins().add((FlutterPlugin) plugin);
      } else {
        Log.e(TAG, "Deferred plugin does not implement FlutterPlugin: " + className);
      }
    } catch (ClassNotFoundException | NoClassDefFoundError e) {
      Log.v(TAG, "Deferred plugin not present: " + pluginName);
    } catch (Exception e) {
      Log.e(TAG, "Error registering deferred plugin " + pluginName + ", " + className, e);
    }
  }
}
