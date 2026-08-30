package com.quwoquan.quwoquan_app;

import android.content.Context;
import android.os.Handler;
import android.util.Log;
import io.flutter.plugin.common.BinaryMessenger;
import io.flutter.plugin.common.MethodCall;
import io.flutter.plugin.common.MethodChannel;
import java.util.Map;
import java.util.concurrent.Executor;

/**
 * runtime config 的 Dart 对端：channel 名、方法分派与错误映射。
 *
 * <p>生产 App 与 Patrol UAT test host 共用本类，因此 UAT 宿主读到的 runtime config 与生产 App 出自同一
 * 实现。若让 test host 复制第二份分派面，两条启动路径的行为等价性就失去了机械保证。test host 通过源集纳入
 * 本文件所在目录，而不是维护副本。
 *
 * <p>store 与 coordinator 由本类持有，供同包内的启动流程复用；跨包调用方只需要 {@link #create} 与
 * {@link #register}。
 */
public final class RuntimeConfigMethodChannel {
  public static final String CHANNEL_NAME = "quwoquan/runtime/config";

  private static final String LOG_TAG = "QWQStartup";

  private final RuntimeConfigPackageStore store;
  private final RuntimeConfigActivationCoordinator coordinator;

  private RuntimeConfigMethodChannel(
      RuntimeConfigPackageStore store, RuntimeConfigActivationCoordinator coordinator) {
    this.store = store;
    this.coordinator = coordinator;
  }

  public static RuntimeConfigMethodChannel create(Context context) {
    RuntimeConfigPackageStore createdStore = AndroidRuntimeConfig.createStore(context);
    return new RuntimeConfigMethodChannel(
        createdStore,
        new RuntimeConfigActivationCoordinator(
            context.getApplicationContext().getNoBackupFilesDir(), createdStore));
  }

  /**
   * @param callExecutor 承载原生读取的后台执行器，读取涉及文件与验签，不能占用平台线程。
   * @param replyHandler 回复 Dart 的主线程 handler。
   */
  public void register(
      BinaryMessenger binaryMessenger, Executor callExecutor, Handler replyHandler) {
    new MethodChannel(binaryMessenger, CHANNEL_NAME)
        .setMethodCallHandler(
            (MethodCall call, MethodChannel.Result result) ->
                callExecutor.execute(() -> handleCall(call, result, replyHandler)));
  }

  RuntimeConfigPackageStore store() {
    return store;
  }

  RuntimeConfigActivationCoordinator coordinator() {
    return coordinator;
  }

  Map<String, Object> readVerifiedPackage() throws RuntimeConfigPackageStore.RuntimeConfigException {
    return coordinator.readVerifiedFlutterEnvelope();
  }

  private void handleCall(
      MethodCall call, MethodChannel.Result result, Handler replyHandler) {
    try {
      Object response;
      switch (call.method) {
        case "readRuntimeConfig":
          response = readVerifiedPackage();
          break;
        case "readRuntimeConfigState":
          response = store.readStateEnvelope();
          break;
        default:
          replyHandler.post(result::notImplemented);
          return;
      }
      replyHandler.post(() -> result.success(response));
    } catch (RuntimeConfigPackageStore.RuntimeConfigException error) {
      Log.e(LOG_TAG, "android_runtime_config_operation_failed code=" + error.code, error);
      replyHandler.post(
          () -> result.error(error.code, "Native runtime configuration operation failed.", null));
    } catch (RuntimeException error) {
      Log.e(LOG_TAG, "android_runtime_config_internal_failure", error);
      replyHandler.post(
          () ->
              result.error(
                  RuntimeConfigPackageStore.registeredErrorCode(
                      "runtime_config_internal_failure"),
                  "Native runtime configuration operation failed.",
                  null));
    }
  }
}
