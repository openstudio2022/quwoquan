package com.quwoquan.quwoquan_app;

import android.Manifest;
import android.content.Context;
import android.content.pm.PackageManager;
import android.os.Build;
import android.telephony.PhoneStateListener;
import android.telephony.TelephonyDisplayInfo;
import android.telephony.TelephonyManager;
import io.flutter.plugin.common.MethodCall;
import io.flutter.plugin.common.MethodChannel;

/**
 * 将 Android 蜂窝接入代际收口为 g5/g4/unknown。
 *
 * <p>该能力只细化已由 connectivity_plus 确认的移动网络；没有 READ_PHONE_STATE
 * 运行时授权时必须诚实返回 unknown，Dart 侧会降级为 telemetry 的 mobile。</p>
 */
final class CellularNetworkProbePlugin {
  private final Context applicationContext;
  private final TelephonyManager telephonyManager;
  // 0 等于 TelephonyDisplayInfo 的 NONE 值。保持字面量以避免 Android 11 以下
  // 在加载本类时解析 API 30 常量。
  private volatile int displayOverrideNetworkType = 0;
  private PhoneStateListener displayInfoListener;
  private boolean displayListenerRegistered;

  CellularNetworkProbePlugin(Context context) {
    applicationContext = context.getApplicationContext();
    telephonyManager =
        (TelephonyManager) applicationContext.getSystemService(Context.TELEPHONY_SERVICE);
  }

  void handle(MethodCall call, MethodChannel.Result result) {
    if (!"readGeneration".equals(call.method)) {
      result.notImplemented();
      return;
    }
    result.success(readGeneration());
  }

  void dispose() {
    if (telephonyManager == null || displayInfoListener == null || !displayListenerRegistered) {
      return;
    }
    telephonyManager.listen(displayInfoListener, PhoneStateListener.LISTEN_NONE);
    displayListenerRegistered = false;
  }

  private String readGeneration() {
    if (telephonyManager == null || !hasPhoneStatePermission()) {
      return "unknown";
    }
    try {
      registerDisplayInfoListenerIfSupported();
      if (isFiveGOverride(displayOverrideNetworkType)) {
        return "g5";
      }
      final int dataNetworkType = telephonyManager.getDataNetworkType();
      if (isFiveGDataNetworkType(dataNetworkType)) {
        return "g5";
      }
      if (isFourGOverride(displayOverrideNetworkType) || dataNetworkType == TelephonyManager.NETWORK_TYPE_LTE) {
        return "g4";
      }
    } catch (SecurityException ignored) {
      // 权限可能在预检查与 Telephony 调用之间被用户收回。
    } catch (RuntimeException ignored) {
      // 调制解调器缺失或暂不可用时，代际必须保持未知。
    }
    return "unknown";
  }

  private boolean hasPhoneStatePermission() {
    return Build.VERSION.SDK_INT < Build.VERSION_CODES.M
        || applicationContext.checkSelfPermission(Manifest.permission.READ_PHONE_STATE)
            == PackageManager.PERMISSION_GRANTED;
  }

  @SuppressWarnings("deprecation")
  private void registerDisplayInfoListenerIfSupported() {
    if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R || displayListenerRegistered) {
      return;
    }
    displayInfoListener =
        new PhoneStateListener() {
          @Override
          public void onDisplayInfoChanged(TelephonyDisplayInfo displayInfo) {
            displayOverrideNetworkType = displayInfo.getOverrideNetworkType();
          }
        };
    telephonyManager.listen(displayInfoListener, PhoneStateListener.LISTEN_DISPLAY_INFO_CHANGED);
    displayListenerRegistered = true;
  }

  private static boolean isFiveGDataNetworkType(int networkType) {
    return Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q
        && networkType == TelephonyManager.NETWORK_TYPE_NR;
  }

  private static boolean isFiveGOverride(int overrideNetworkType) {
    if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) {
      return false;
    }
    if (overrideNetworkType == TelephonyDisplayInfo.OVERRIDE_NETWORK_TYPE_NR_NSA
        || overrideNetworkType == TelephonyDisplayInfo.OVERRIDE_NETWORK_TYPE_NR_NSA_MMWAVE) {
      return true;
    }
    return Build.VERSION.SDK_INT >= Build.VERSION_CODES.S
        && overrideNetworkType == TelephonyDisplayInfo.OVERRIDE_NETWORK_TYPE_NR_ADVANCED;
  }

  private static boolean isFourGOverride(int overrideNetworkType) {
    if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) {
      return false;
    }
    return overrideNetworkType == TelephonyDisplayInfo.OVERRIDE_NETWORK_TYPE_LTE_CA
        || overrideNetworkType == TelephonyDisplayInfo.OVERRIDE_NETWORK_TYPE_LTE_ADVANCED_PRO;
  }
}
