package com.quwoquan.quwoquan_app;

import androidx.annotation.NonNull;
import io.flutter.Log;
import io.flutter.embedding.engine.FlutterEngine;
import io.flutter.embedding.engine.plugins.FlutterPlugin;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import java.util.WeakHashMap;

/** 冷启动延后注册的重 native 插件，首次进入 RTC / 创作入口时再链接。 */
final class StartupDeferredPluginRegistry {
  private static final String TAG = "QWQStartup";
  private static final Map<FlutterEngine, Set<String>> registeredGroups = new WeakHashMap<>();

  private StartupDeferredPluginRegistry() {}

  /** 首帧后、认证/遥测水合前的基础平台组。 */
  static synchronized boolean ensureStartupPostFirstFrame(@NonNull FlutterEngine flutterEngine) {
    if (isRegistered(flutterEngine, "startupPostFirstFrame")) {
      return true;
    }
    boolean attached = registerPlugin(
        flutterEngine, "audio_session", "com.ryanheise.audio_session.AudioSessionPlugin");
    attached &= registerPlugin(
        flutterEngine, "file_picker", "com.mr.flutter.plugin.filepicker.FilePickerPlugin");
    attached &= registerPlugin(
        flutterEngine, "flutter_contacts", "co.quis.flutter_contacts.FlutterContactsPlugin");
    attached &= registerPlugin(
        flutterEngine, "just_audio", "com.ryanheise.just_audio.JustAudioPlugin");
    attached &= registerPlugin(
        flutterEngine, "mobile_scanner", "dev.steenbakker.mobile_scanner.MobileScannerPlugin");
    attached &= registerPlugin(
        flutterEngine,
        "permission_handler_android",
        "com.baseflow.permissionhandler.PermissionHandlerPlugin");
    attached &= registerPlugin(
        flutterEngine, "record_android", "com.llfbandit.record.RecordPlugin");
    attached &= registerPlugin(
        flutterEngine, "share_plus", "dev.fluttercommunity.plus.share.SharePlusPlugin");
    attached &= registerPlugin(
        flutterEngine, "url_launcher_android", "io.flutter.plugins.urllauncher.UrlLauncherPlugin");
    attached &= registerPlugin(
        flutterEngine, "wakelock_plus", "dev.fluttercommunity.plus.wakelock.WakelockPlusPlugin");
    attached &= registerPlugin(
        flutterEngine, "webview_flutter_android", "io.flutter.plugins.webviewflutter.WebViewFlutterPlugin");
    attached &= registerPlugin(
        flutterEngine,
        "connectivity_plus",
        "dev.fluttercommunity.plus.connectivity.ConnectivityPlugin");
    attached &= registerPlugin(
        flutterEngine,
        "device_info_plus",
        "dev.fluttercommunity.plus.device_info.DeviceInfoPlusPlugin");
    attached &= registerPlugin(
        flutterEngine,
        "package_info_plus",
        "dev.fluttercommunity.plus.packageinfo.PackageInfoPlugin");
    if (attached) {
      markRegistered(flutterEngine, "startupPostFirstFrame");
      Log.i(TAG, "android_startup_post_first_frame_plugins_registered");
    }
    return attached;
  }

  static synchronized boolean ensureRtc(@NonNull FlutterEngine flutterEngine) {
    if (isRegistered(flutterEngine, "rtc")) {
      return true;
    }
    boolean attached = registerPlugin(
        flutterEngine, "flutter_webrtc", "com.cloudwebrtc.webrtc.FlutterWebRTCPlugin");
    attached &= registerPlugin(
        flutterEngine, "livekit_client", "io.livekit.plugin.LiveKitPlugin");
    if (attached) {
      markRegistered(flutterEngine, "rtc");
      Log.i(TAG, "android_deferred_rtc_plugins_registered");
    }
    return attached;
  }

  static synchronized boolean ensureContentEntry(@NonNull FlutterEngine flutterEngine) {
    if (isRegistered(flutterEngine, "contentEntry")) {
      return true;
    }
    boolean attached = registerPlugin(
        flutterEngine,
        "camera_android_camerax",
        "io.flutter.plugins.camerax.CameraAndroidCameraxPlugin");
    attached &= registerPlugin(
        flutterEngine,
        "image_picker_android",
        "io.flutter.plugins.imagepicker.ImagePickerPlugin");
    attached &= registerPlugin(
        flutterEngine,
        "photo_manager",
        "com.fluttercandies.photo_manager.PhotoManagerPlugin");
    attached &= registerPlugin(
        flutterEngine,
        "video_thumbnail",
        "xyz.justsoft.video_thumbnail.VideoThumbnailPlugin");
    if (attached) {
      markRegistered(flutterEngine, "contentEntry");
      Log.i(TAG, "android_deferred_content_entry_plugins_registered");
    }
    return attached;
  }

  static synchronized boolean ensureLocation(@NonNull FlutterEngine flutterEngine) {
    if (isRegistered(flutterEngine, "location")) {
      return true;
    }
    boolean attached = registerPlugin(
        flutterEngine,
        "geolocator_android",
        "com.baseflow.geolocator.GeolocatorPlugin");
    if (attached) {
      markRegistered(flutterEngine, "location");
      Log.i(TAG, "android_deferred_location_plugins_registered");
    }
    return attached;
  }

  private static boolean isRegistered(@NonNull FlutterEngine flutterEngine, @NonNull String group) {
    Set<String> groups = registeredGroups.get(flutterEngine);
    return groups != null && groups.contains(group);
  }

  private static void markRegistered(
      @NonNull FlutterEngine flutterEngine, @NonNull String group) {
    Set<String> groups = registeredGroups.get(flutterEngine);
    if (groups == null) {
      groups = new HashSet<>();
      registeredGroups.put(flutterEngine, groups);
    }
    groups.add(group);
  }

  private static boolean registerPlugin(
      @NonNull FlutterEngine flutterEngine,
      @NonNull String pluginName,
      @NonNull String className) {
    try {
      Class<?> pluginClass = Class.forName(className);
      if (!FlutterPlugin.class.isAssignableFrom(pluginClass)) {
        Log.e(TAG, "Deferred plugin does not implement FlutterPlugin: " + className);
        return false;
      }
      Class<? extends FlutterPlugin> flutterPluginClass =
          pluginClass.asSubclass(FlutterPlugin.class);
      if (flutterEngine.getPlugins().has(flutterPluginClass)) {
        return true;
      }
      Object plugin = pluginClass.getDeclaredConstructor().newInstance();
      flutterEngine.getPlugins().add((FlutterPlugin) plugin);
      return true;
    } catch (ClassNotFoundException | NoClassDefFoundError e) {
      Log.v(TAG, "Deferred plugin not present: " + pluginName);
      return false;
    } catch (Exception e) {
      Log.e(TAG, "Error registering deferred plugin " + pluginName + ", " + className, e);
      return false;
    }
  }
}
