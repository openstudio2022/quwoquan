package com.quwoquan.quwoquan_app;

import android.app.Activity;
import android.content.Context;
import android.content.SharedPreferences;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.content.pm.Signature;
import android.net.Uri;
import android.os.Build;
import android.util.Log;
import androidx.annotation.Nullable;
import com.tencent.mm.opensdk.modelbase.BaseResp;
import com.tencent.mm.opensdk.modelmsg.SendAuth;
import com.tencent.mm.opensdk.modelmsg.SendMessageToWX;
import com.tencent.mm.opensdk.modelmsg.WXMediaMessage;
import com.tencent.mm.opensdk.modelmsg.WXWebpageObject;
import com.tencent.mm.opensdk.openapi.IWXAPI;
import com.tencent.mm.opensdk.openapi.WXAPIFactory;
import io.flutter.plugin.common.MethodCall;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import org.json.JSONObject;

/** 微信 OpenSDK 的单一协调器；登录与分享必须复用同一个 IWXAPI。 */
public final class WechatSdkCoordinator {
  private static final String TAG = "QWQWechatSdk";
  private static final String WECHAT_PACKAGE = "com.tencent.mm";
  private static final String PREFS = "qwq_wechat_share_outcomes";
  private static final String PENDING_PREFIX = "pending.";
  private static final String OUTCOME_PREFIX = "outcome.";
  private static final String TRANSACTION_PREFIX = "qwq-share:";
  private static final int MAX_THUMBNAIL_BYTES = 32 * 1024;
  private static volatile WechatSdkCoordinator instance;

  private final Activity activity;
  private final IWXAPI api;
  private final boolean registered;

  WechatSdkCoordinator(Activity activity) {
    this.activity = activity;
    this.api =
        WXAPIFactory.createWXAPI(
            activity.getApplicationContext(), BuildConfig.QWQ_WECHAT_APP_ID, true);
    this.registered =
        !BuildConfig.QWQ_WECHAT_APP_ID.isEmpty()
            && api.registerApp(BuildConfig.QWQ_WECHAT_APP_ID);
    instance = this;
  }

  Map<String, Object> capability(String target) {
    Map<String, Object> payload = new HashMap<>();
    payload.put("target", target);
    String unavailableReason = unavailableReason(target);
    payload.put("available", unavailableReason.isEmpty());
    payload.put(
        "reason", unavailableReason.isEmpty() ? "official_sdk" : unavailableReason);
    return payload;
  }

  boolean sendAuth(SendAuth.Req request) {
    return unavailableReason("wechatFriend").isEmpty() && api.sendReq(request);
  }

  Map<String, Object> shareWebpageCard(MethodCall call) {
    String target = stringArgument(call, "target");
    String requestId = stringArgument(call, "requestId");
    String title = stringArgument(call, "title");
    String description = stringArgument(call, "description");
    String webpageUrl = stringArgument(call, "webpageUrl");
    String referralDigest = stringArgument(call, "referralDigest");
    byte[] thumbnail = call.argument("thumbnail");

    String unavailableReason = unavailableReason(target);
    if (!unavailableReason.isEmpty()) {
      return result(target, requestId, "unavailable", unavailableReason);
    }
    if (requestId.isEmpty()
        || title.isEmpty()
        || !isHttpsUrl(webpageUrl)
        || (thumbnail != null && thumbnail.length > MAX_THUMBNAIL_BYTES)) {
      return result(target, requestId, "failed", "invalid_webpage_card");
    }

    WXWebpageObject webpage = new WXWebpageObject();
    webpage.webpageUrl = webpageUrl;
    WXMediaMessage message = new WXMediaMessage(webpage);
    message.title = title;
    message.description = description;
    if (thumbnail != null && thumbnail.length > 0) {
      message.thumbData = thumbnail;
    }

    SendMessageToWX.Req request = new SendMessageToWX.Req();
    request.transaction = TRANSACTION_PREFIX + requestId;
    request.message = message;
    request.scene =
        "wechatMoments".equals(target)
            ? SendMessageToWX.Req.WXSceneTimeline
            : SendMessageToWX.Req.WXSceneSession;

    persistPending(
        activity,
        resultWithMetadata(
            target,
            requestId,
            "accepted",
            "official_sdk",
            referralDigest,
            System.currentTimeMillis()));
    if (!api.sendReq(request)) {
      removePending(activity, requestId);
      return result(target, requestId, "failed", "sdk_request_rejected");
    }
    return result(target, requestId, "accepted", "official_sdk");
  }

  List<Map<String, Object>> consumePendingOutcomes() {
    SharedPreferences preferences =
        activity.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    List<Map<String, Object>> outcomes = new ArrayList<>();
    SharedPreferences.Editor editor = preferences.edit();
    for (Map.Entry<String, ?> entry : preferences.getAll().entrySet()) {
      if (!entry.getKey().startsWith(OUTCOME_PREFIX) || !(entry.getValue() instanceof String)) {
        continue;
      }
      Map<String, Object> decoded = decodeOutcome((String) entry.getValue());
      if (decoded != null) {
        outcomes.add(decoded);
      }
      editor.remove(entry.getKey());
    }
    editor.apply();
    return outcomes;
  }

  /** WXEntryActivity 的统一回调入口；未知 transaction 只记录 contract failure。 */
  public static void handleWechatResponse(Context context, BaseResp response) {
    if (response instanceof SendAuth.Resp) {
      CommercialAuthPlugin.handleWechatResponse(response);
      return;
    }
    if (!(response instanceof SendMessageToWX.Resp)) {
      Log.w(TAG, "unsupported_response type=" + response.getClass().getSimpleName());
      return;
    }
    String requestId = requestIdFromTransaction(response.transaction);
    if (requestId.isEmpty()) {
      Log.e(TAG, "contract_failure missing_share_transaction");
      return;
    }
    SharedPreferences preferences = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    String pending = preferences.getString(PENDING_PREFIX + requestId, "");
    Map<String, Object> pendingPayload = decodeOutcome(pending);
    if (pendingPayload == null) {
      Log.e(TAG, "contract_failure unknown_share_request requestId=" + requestId);
      return;
    }
    String target = stringValue(pendingPayload.get("target"));
    String referralDigest = stringValue(pendingPayload.get("referralDigest"));
    String outcome = outcomeFromErrorCode(response.errCode);
    String reason = reasonFromErrorCode(response.errCode);
    Map<String, Object> terminal =
        resultWithMetadata(
            target,
            requestId,
            outcome,
            reason,
            referralDigest,
            System.currentTimeMillis());
    preferences
        .edit()
        .remove(PENDING_PREFIX + requestId)
        .putString(OUTCOME_PREFIX + requestId, new JSONObject(terminal).toString())
        .apply();
  }

  private String unavailableReason(String target) {
    if (BuildConfig.QWQ_WECHAT_APP_ID.isEmpty()) {
      return "wechat_app_id_missing";
    }
    if (BuildConfig.QWQ_WECHAT_ANDROID_SIGNATURE.isEmpty()) {
      return "wechat_signature_missing";
    }
    if (!isPackageInstalled()) {
      return "wechat_not_installed";
    }
    if (!signatureMatches()) {
      return "wechat_signature_mismatch";
    }
    if (!registered) {
      return "wechat_registration_failed";
    }
    int supportedApi = api.getWXAppSupportAPI();
    if (supportedApi <= 0) {
      return "wechat_sdk_unsupported";
    }
    if ("wechatMoments".equals(target)
        && supportedApi
            < com.tencent.mm.opensdk.constants.Build.TIMELINE_SUPPORTED_SDK_INT) {
      return "wechat_moments_unsupported";
    }
    if (!"wechatFriend".equals(target) && !"wechatMoments".equals(target)) {
      return "unsupported_target";
    }
    return "";
  }

  private boolean signatureMatches() {
    String expected = normalizeDigest(BuildConfig.QWQ_WECHAT_ANDROID_SIGNATURE);
    if (expected.isEmpty()) {
      return false;
    }
    try {
      PackageInfo packageInfo;
      if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
        packageInfo =
            activity
                .getPackageManager()
                .getPackageInfo(
                    activity.getPackageName(), PackageManager.GET_SIGNING_CERTIFICATES);
        Signature[] signatures = packageInfo.signingInfo.getApkContentsSigners();
        for (Signature signature : signatures) {
          if (expected.equals(md5(signature.toByteArray()))) {
            return true;
          }
        }
        return false;
      }
      packageInfo =
          activity
              .getPackageManager()
              .getPackageInfo(activity.getPackageName(), PackageManager.GET_SIGNATURES);
      for (Signature signature : packageInfo.signatures) {
        if (expected.equals(md5(signature.toByteArray()))) {
          return true;
        }
      }
    } catch (Exception error) {
      Log.e(TAG, "signature_check_failed", error);
    }
    return false;
  }

  private boolean isPackageInstalled() {
    try {
      activity.getPackageManager().getPackageInfo(WECHAT_PACKAGE, 0);
      return true;
    } catch (PackageManager.NameNotFoundException error) {
      return false;
    }
  }

  private static boolean isHttpsUrl(String raw) {
    Uri uri = Uri.parse(raw);
    return "https".equalsIgnoreCase(uri.getScheme()) && uri.getHost() != null;
  }

  private static String md5(byte[] value) throws Exception {
    byte[] digest = MessageDigest.getInstance("MD5").digest(value);
    StringBuilder builder = new StringBuilder(digest.length * 2);
    for (byte item : digest) {
      builder.append(String.format(Locale.US, "%02x", item & 0xff));
    }
    return builder.toString();
  }

  private static String normalizeDigest(String raw) {
    return raw.replace(":", "").replace("-", "").trim().toLowerCase(Locale.US);
  }

  private static void persistPending(Context context, Map<String, Object> payload) {
    String requestId = stringValue(payload.get("requestId"));
    context
        .getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        .edit()
        .putString(PENDING_PREFIX + requestId, new JSONObject(payload).toString())
        .apply();
  }

  private static void removePending(Context context, String requestId) {
    context
        .getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        .edit()
        .remove(PENDING_PREFIX + requestId)
        .apply();
  }

  @Nullable
  private static Map<String, Object> decodeOutcome(String encoded) {
    if (encoded == null || encoded.isEmpty()) {
      return null;
    }
    try {
      JSONObject json = new JSONObject(encoded);
      Map<String, Object> payload = new HashMap<>();
      payload.put("target", json.optString("target"));
      payload.put("requestId", json.optString("requestId"));
      payload.put("channel", json.optString("channel", "wechat"));
      payload.put("referralDigest", json.optString("referralDigest"));
      payload.put("outcome", json.optString("outcome"));
      payload.put("reason", json.optString("reason"));
      payload.put("occurredAtMillis", json.optLong("occurredAtMillis"));
      return payload;
    } catch (Exception error) {
      Log.e(TAG, "contract_failure invalid_persisted_outcome", error);
      return null;
    }
  }

  private static String outcomeFromErrorCode(int errCode) {
    if (errCode == BaseResp.ErrCode.ERR_OK) {
      return "completed";
    }
    if (errCode == BaseResp.ErrCode.ERR_USER_CANCEL) {
      return "cancelled";
    }
    return "failed";
  }

  private static String reasonFromErrorCode(int errCode) {
    if (errCode == BaseResp.ErrCode.ERR_OK) {
      return "official_sdk_callback";
    }
    if (errCode == BaseResp.ErrCode.ERR_USER_CANCEL) {
      return "user_cancelled";
    }
    return "sdk_callback_" + errCode;
  }

  private static String requestIdFromTransaction(String transaction) {
    if (transaction == null || !transaction.startsWith(TRANSACTION_PREFIX)) {
      return "";
    }
    return transaction.substring(TRANSACTION_PREFIX.length()).trim();
  }

  private static Map<String, Object> result(
      String target, String requestId, String outcome, String reason) {
    Map<String, Object> payload = new HashMap<>();
    payload.put("target", target);
    payload.put("requestId", requestId);
    payload.put("outcome", outcome);
    payload.put("reason", reason);
    return payload;
  }

  private static Map<String, Object> resultWithMetadata(
      String target,
      String requestId,
      String outcome,
      String reason,
      String referralDigest,
      long occurredAtMillis) {
    Map<String, Object> payload = result(target, requestId, outcome, reason);
    payload.put("channel", "wechat");
    payload.put("referralDigest", referralDigest);
    payload.put("occurredAtMillis", occurredAtMillis);
    return payload;
  }

  private static String stringArgument(MethodCall call, String key) {
    Object value = call.argument(key);
    return value == null ? "" : value.toString().trim();
  }

  private static String stringValue(Object value) {
    return value == null ? "" : value.toString().trim();
  }
}
