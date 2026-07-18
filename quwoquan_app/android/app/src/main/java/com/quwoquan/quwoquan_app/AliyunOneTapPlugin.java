package com.quwoquan.quwoquan_app;

import android.app.Activity;
import io.flutter.plugin.common.MethodCall;
import io.flutter.plugin.common.MethodChannel;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.HashMap;
import java.util.Map;
import org.json.JSONObject;

/**
 * 阿里云号码认证 SDK 的可选二进制防腐层。
 *
 * <p>官方客户端 SDK 只能从已登录控制台下载，因此编译期不直接引用其类。受控构建将官方 AAR
 * 注入 vendor/commercial_auth/aliyun/android 后，本类通过固定官方 API 反射接线；缺包或缺方案密钥时
 * fail-closed，Flutter 自动回退手机号验证码。
 */
final class AliyunOneTapPlugin {
  private static final String HELPER_CLASS =
      "com.mobile.auth.gatewayauth.PhoneNumberAuthHelper";
  private static final String LISTENER_CLASS =
      "com.mobile.auth.gatewayauth.TokenResultListener";

  private final Activity activity;
  private Object helper;
  private MethodChannel.Result pendingResult;

  AliyunOneTapPlugin(Activity activity) {
    this.activity = activity;
    initialize();
  }

  void handle(MethodCall call, MethodChannel.Result result) {
    switch (call.method) {
      case "isAvailable":
        result.success(isAvailable());
        return;
      case "probe":
        Map<String, Object> probe = new HashMap<>();
        // 反射桥当前只能在授权页打开后取得 token，不能形成入口阶段可提交凭据。
        // Flutter 据此 fail-closed 隐藏入口，避免用点击后的失败探测能力。
        probe.put(
            "availability",
            isAvailable()
                ? "invalidProbe"
                : (BuildConfig.QWQ_ALIYUN_PNVS_SECRET_INFO.isEmpty()
                    ? "notConfigured"
                    : "sdkUnavailable"));
        probe.put("vendor", isAvailable() ? "aliyun" : "");
        probe.put("reason", isAvailable() ? "prelogin_token_not_resolved" : "sdk_not_ready");
        result.success(probe);
        return;
      case "requestLoginToken":
        requestLoginToken(result);
        return;
      default:
        result.notImplemented();
    }
  }

  private boolean isAvailable() {
    return helper != null && !BuildConfig.QWQ_ALIYUN_PNVS_SECRET_INFO.isEmpty();
  }

  private void initialize() {
    if (BuildConfig.QWQ_ALIYUN_PNVS_SECRET_INFO.isEmpty()) {
      return;
    }
    try {
      Class<?> helperClass = Class.forName(HELPER_CLASS);
      Class<?> listenerClass = Class.forName(LISTENER_CLASS);
      Object listener =
          Proxy.newProxyInstance(
              listenerClass.getClassLoader(),
              new Class<?>[] {listenerClass},
              (proxy, method, arguments) -> {
                String payload =
                    arguments == null || arguments.length == 0 || arguments[0] == null
                        ? ""
                        : arguments[0].toString();
                if ("onTokenSuccess".equals(method.getName())) {
                  completeSuccess(payload);
                } else if ("onTokenFailed".equals(method.getName())) {
                  completeFailure(payload);
                }
                return null;
              });
      Method getInstance =
          helperClass.getMethod("getInstance", android.content.Context.class, listenerClass);
      helper = getInstance.invoke(null, activity.getApplicationContext(), listener);
      helperClass
          .getMethod("setAuthSDKInfo", String.class)
          .invoke(helper, BuildConfig.QWQ_ALIYUN_PNVS_SECRET_INFO);
    } catch (Exception ignored) {
      helper = null;
    }
  }

  private synchronized void requestLoginToken(MethodChannel.Result result) {
    if (!isAvailable()) {
      result.error(
          "one_tap_sdk_not_configured",
          "One-tap login SDK is not configured for this build.",
          null);
      return;
    }
    if (pendingResult != null) {
      result.error("one_tap_busy", "One-tap login is already in progress.", null);
      return;
    }
    pendingResult = result;
    try {
      helper
          .getClass()
          .getMethod("getLoginToken", android.content.Context.class, int.class)
          .invoke(helper, activity, 5000);
    } catch (Exception ignored) {
      pendingResult = null;
      result.error("one_tap_unavailable", "Unable to start one-tap login.", null);
    }
  }

  private synchronized void completeSuccess(String rawPayload) {
    MethodChannel.Result result = pendingResult;
    if (result == null) {
      return;
    }
    try {
      JSONObject response = new JSONObject(rawPayload);
      String code = response.optString("code");
      String token = response.optString("token");
      if (!"600000".equals(code) || token.isEmpty()) {
        completeFailure(rawPayload);
        return;
      }
      pendingResult = null;
      quitLoginPage();
      Map<String, Object> payload = new HashMap<>();
      payload.put("vendor", "aliyun");
      payload.put("carrierToken", token);
      result.success(payload);
    } catch (Exception ignored) {
      pendingResult = null;
      quitLoginPage();
      result.error("one_tap_failed", "One-tap login failed.", null);
    }
  }

  private synchronized void completeFailure(String rawPayload) {
    MethodChannel.Result result = pendingResult;
    if (result == null) {
      return;
    }
    pendingResult = null;
    quitLoginPage();
    String normalized = rawPayload == null ? "" : rawPayload.toLowerCase();
    String code = normalized.contains("cancel")
        ? "one_tap_cancelled"
        : "one_tap_failed";
    result.error(code, "One-tap login failed.", null);
  }

  private void quitLoginPage() {
    if (helper == null) {
      return;
    }
    try {
      helper.getClass().getMethod("quitLoginPage").invoke(helper);
    } catch (Exception ignored) {
      // SDK 版本不支持主动关闭时，由其默认授权页生命周期接管。
    }
  }
}
