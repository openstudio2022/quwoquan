// 微信 OpenSDK 约定回调入口必须位于 <applicationId>.wxapi 包；
// 正式 applicationId 为 com.leadwise.quwoquan（app_artifact_manifest.yaml），
// 与 Java namespace com.quwoquan.quwoquan_app 分离。
package com.leadwise.quwoquan.wxapi;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;
import com.quwoquan.quwoquan_app.BuildConfig;
import com.quwoquan.quwoquan_app.WechatSdkCoordinator;
import com.tencent.mm.opensdk.modelbase.BaseReq;
import com.tencent.mm.opensdk.modelbase.BaseResp;
import com.tencent.mm.opensdk.openapi.IWXAPIEventHandler;
import com.tencent.mm.opensdk.openapi.WXAPIFactory;

/** 微信 OpenSDK 统一回调入口；按 transaction 分发 auth/share，分享结果最小化持久化。 */
public final class WXEntryActivity extends Activity implements IWXAPIEventHandler {
  @Override
  protected void onCreate(Bundle savedInstanceState) {
    super.onCreate(savedInstanceState);
    WXAPIFactory.createWXAPI(this, BuildConfig.QWQ_WECHAT_APP_ID, false)
        .handleIntent(getIntent(), this);
  }

  @Override
  protected void onNewIntent(Intent intent) {
    super.onNewIntent(intent);
    setIntent(intent);
    WXAPIFactory.createWXAPI(this, BuildConfig.QWQ_WECHAT_APP_ID, false)
        .handleIntent(intent, this);
  }

  @Override
  public void onReq(BaseReq request) {
    finish();
  }

  @Override
  public void onResp(BaseResp response) {
    WechatSdkCoordinator.handleWechatResponse(this, response);
    finish();
  }
}
