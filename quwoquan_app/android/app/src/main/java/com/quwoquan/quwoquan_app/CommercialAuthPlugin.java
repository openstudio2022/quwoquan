package com.quwoquan.quwoquan_app;

import android.app.Activity;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.util.Base64;
import com.alipay.sdk.app.AuthTask;
import com.tencent.connect.common.Constants;
import com.tencent.mm.opensdk.modelbase.BaseResp;
import com.tencent.mm.opensdk.modelmsg.SendAuth;
import com.tencent.tauth.IUiListener;
import com.tencent.tauth.Tencent;
import com.tencent.tauth.UiError;
import io.flutter.plugin.common.MethodCall;
import io.flutter.plugin.common.MethodChannel;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.json.JSONObject;

/** 官方微信、支付宝、QQ SDK 到 Flutter NativeAuthBridge 的防腐层。 */
public final class CommercialAuthPlugin {
  private static final Pattern ALIPAY_AUTH_CODE =
      Pattern.compile("(?:^|[&{])auth_code=([^&}]+)");
  private static final SecureRandom RANDOM = new SecureRandom();
  private static volatile CommercialAuthPlugin instance;

  private final Activity activity;
  private final WechatSdkCoordinator wechatCoordinator;
  private final ExecutorService executor = Executors.newSingleThreadExecutor();
  private Tencent qqApi;
  private MethodChannel.Result pendingWechatResult;
  private String pendingWechatState;

  CommercialAuthPlugin(Activity activity, WechatSdkCoordinator wechatCoordinator) {
    this.activity = activity;
    this.wechatCoordinator = wechatCoordinator;
    instance = this;
  }

  public static void handleWechatResponse(BaseResp response) {
    CommercialAuthPlugin current = instance;
    if (current != null) {
      current.onWechatResponse(response);
    }
  }

  void handle(MethodCall call, MethodChannel.Result result) {
    String provider = stringArgument(call, "provider");
    switch (call.method) {
      case "getCapability":
        result.success(capability(provider));
        return;
      case "signIn":
        signIn(provider, stringArgument(call, "authorizationPayload"), result);
        return;
      default:
        result.notImplemented();
    }
  }

  boolean onActivityResult(int requestCode, int resultCode, Intent data) {
    if (requestCode != Constants.REQUEST_LOGIN) {
      return false;
    }
    Tencent.handleResultData(data, qqLoginListener);
    return true;
  }

  private Map<String, Object> capability(String provider) {
    Map<String, Object> payload = new HashMap<>();
    payload.put("provider", provider);
    boolean available;
    String reason;
    switch (provider) {
      case "wechat":
        Map<String, Object> wechatCapability =
            wechatCoordinator.capability("wechatFriend");
        available = Boolean.TRUE.equals(wechatCapability.get("available"));
        reason = wechatCapability.get("reason").toString();
        break;
      case "alipay":
        available = isPackageInstalled("com.eg.android.AlipayGphone");
        reason = available ? "official_sdk" : "alipay_not_installed";
        break;
      case "qq":
        available =
            !BuildConfig.QWQ_QQ_APP_ID.isEmpty()
                && (isPackageInstalled("com.tencent.mobileqq")
                    || isPackageInstalled("com.tencent.tim"));
        reason = available ? "official_sdk" : "qq_not_configured_or_installed";
        break;
      default:
        available = false;
        reason = "unsupported_provider";
        break;
    }
    payload.put("available", available);
    payload.put("reason", reason);
    return payload;
  }

  private void signIn(
      String provider, String authorizationPayload, MethodChannel.Result result) {
    switch (provider) {
      case "wechat":
        signInWechat(result);
        return;
      case "alipay":
        signInAlipay(authorizationPayload, result);
        return;
      case "qq":
        signInQq(result);
        return;
      default:
        result.error("native_auth_unavailable", "Provider unavailable.", null);
    }
  }

  private void signInWechat(MethodChannel.Result result) {
    if (!(Boolean) capability("wechat").get("available")) {
      result.error("native_auth_unavailable", "WeChat unavailable.", null);
      return;
    }
    if (pendingWechatResult != null) {
      result.error("native_auth_busy", "WeChat authorization already in progress.", null);
      return;
    }
    byte[] entropy = new byte[18];
    RANDOM.nextBytes(entropy);
    pendingWechatState = Base64.encodeToString(entropy, Base64.URL_SAFE | Base64.NO_WRAP | Base64.NO_PADDING);
    pendingWechatResult = result;
    SendAuth.Req request = new SendAuth.Req();
    request.scope = "snsapi_userinfo";
    request.state = pendingWechatState;
    if (!wechatCoordinator.sendAuth(request)) {
      clearWechatPending();
      result.error("native_auth_unavailable", "Unable to start WeChat authorization.", null);
    }
  }

  private void onWechatResponse(BaseResp response) {
    MethodChannel.Result result = pendingWechatResult;
    if (result == null || !(response instanceof SendAuth.Resp)) {
      return;
    }
    SendAuth.Resp authResponse = (SendAuth.Resp) response;
    if (response.errCode == BaseResp.ErrCode.ERR_USER_CANCEL) {
      clearWechatPending();
      result.error("native_auth_cancelled", "Authorization cancelled.", null);
      return;
    }
    if (response.errCode != BaseResp.ErrCode.ERR_OK
        || authResponse.code == null
        || authResponse.code.trim().isEmpty()
        || !pendingWechatState.equals(authResponse.state)) {
      clearWechatPending();
      result.error("native_auth_failed", "WeChat authorization failed.", null);
      return;
    }
    String ticket = authResponse.code.trim();
    clearWechatPending();
    result.success(ticketPayload("wechat", ticket));
  }

  private void clearWechatPending() {
    pendingWechatResult = null;
    pendingWechatState = null;
  }

  private void signInAlipay(String authorizationPayload, MethodChannel.Result result) {
    if (!(Boolean) capability("alipay").get("available") || authorizationPayload.isEmpty()) {
      result.error("native_auth_unavailable", "Alipay authorization unavailable.", null);
      return;
    }
    executor.execute(
        () -> {
          Map<String, String> response =
              new AuthTask(activity).authV2(authorizationPayload, true);
          activity.runOnUiThread(
              () -> {
                String status = response.get("resultStatus");
                if ("6001".equals(status)) {
                  result.error("native_auth_cancelled", "Authorization cancelled.", null);
                  return;
                }
                String rawResult = response.get("result");
                Matcher matcher = ALIPAY_AUTH_CODE.matcher(rawResult == null ? "" : rawResult);
                if (!"9000".equals(status) || !matcher.find()) {
                  result.error("native_auth_failed", "Alipay authorization failed.", null);
                  return;
                }
                result.success(ticketPayload("alipay", matcher.group(1)));
              });
        });
  }

  private void signInQq(MethodChannel.Result result) {
    if (!(Boolean) capability("qq").get("available")) {
      result.error("native_auth_unavailable", "QQ unavailable.", null);
      return;
    }
    if (pendingQqResult != null) {
      result.error("native_auth_busy", "QQ authorization already in progress.", null);
      return;
    }
    pendingQqResult = result;
    Tencent.setIsPermissionGranted(true, android.os.Build.MODEL);
    qq().login(activity, "get_user_info", qqLoginListener);
  }

  private MethodChannel.Result pendingQqResult;
  private final IUiListener qqLoginListener =
      new IUiListener() {
        @Override
        public void onComplete(Object value) {
          MethodChannel.Result result = pendingQqResult;
          pendingQqResult = null;
          if (result == null || !(value instanceof JSONObject)) {
            return;
          }
          JSONObject response = (JSONObject) value;
          String accessToken = response.optString(Constants.PARAM_ACCESS_TOKEN);
          String openId = response.optString(Constants.PARAM_OPEN_ID);
          String expiresIn = response.optString(Constants.PARAM_EXPIRES_IN);
          if (accessToken.isEmpty() || openId.isEmpty()) {
            result.error("native_auth_failed", "QQ authorization failed.", null);
            return;
          }
          qq().setAccessToken(accessToken, expiresIn);
          qq().setOpenId(openId);
          JSONObject ticket = new JSONObject();
          try {
            ticket.put("accessToken", accessToken);
            ticket.put("openId", openId);
          } catch (Exception ignored) {
            result.error("native_auth_failed", "QQ authorization failed.", null);
            return;
          }
          String encoded =
              Base64.encodeToString(
                  ticket.toString().getBytes(StandardCharsets.UTF_8),
                  Base64.URL_SAFE | Base64.NO_WRAP | Base64.NO_PADDING);
          // Frozen provider ticket prefix; `_v1` is the sole accepted byte shape,
          // not a negotiable multi-version envelope.
          result.success(ticketPayload("qq", "qq_mobile_v1." + encoded));
        }

        @Override
        public void onError(UiError error) {
          MethodChannel.Result result = pendingQqResult;
          pendingQqResult = null;
          if (result != null) {
            result.error("native_auth_failed", "QQ authorization failed.", null);
          }
        }

        @Override
        public void onCancel() {
          MethodChannel.Result result = pendingQqResult;
          pendingQqResult = null;
          if (result != null) {
            result.error("native_auth_cancelled", "Authorization cancelled.", null);
          }
        }

        @Override
        public void onWarning(int code) {}
      };

  private Tencent qq() {
    if (qqApi == null) {
      qqApi = Tencent.createInstance(BuildConfig.QWQ_QQ_APP_ID, activity.getApplicationContext());
    }
    return qqApi;
  }

  private boolean isPackageInstalled(String packageName) {
    try {
      activity.getPackageManager().getPackageInfo(packageName, 0);
      return true;
    } catch (PackageManager.NameNotFoundException error) {
      return false;
    }
  }

  private static Map<String, Object> ticketPayload(String provider, String ticket) {
    Map<String, Object> payload = new HashMap<>();
    payload.put("provider", provider);
    payload.put("ticket", ticket);
    return payload;
  }

  private static String stringArgument(MethodCall call, String key) {
    Object value = call.argument(key);
    return value == null ? "" : value.toString().trim();
  }
}
