import Flutter
import UIKit

@main
@objc class AppDelegate: FlutterAppDelegate, FlutterImplicitEngineDelegate {
  override func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
  ) -> Bool {
    // 与生产同构的两阶段冷启动中的第一阶段：编排方先用带 request digest 的启动参数激活
    // runtime config，再让 Patrol 正常启动宿主进入 Flutter。验签、CAS、落盘与回执全部走
    // 共编译自生产源树的 coordinator，本壳只负责「消费一次请求后不再继续启动」。
    //
    // 判否不在此处呈现终态：编排方以「回执未在超时内出现」判否，与生产 canonical
    // executor 的判否口径一致。
    let activation = NativeRuntimeConfigActivationCoordinator
      .consumePendingActivationRequest(
        arguments: ProcessInfo.processInfo.arguments,
        coldStartAllowed: true
      )
    if activation.requested {
      if activation.activated {
        NSLog("QWQStartup uat_host_runtime_config_activation_complete")
      } else {
        NSLog(
          "QWQStartup uat_host_runtime_config_activation_failed code=%@ issues=%@",
          activation.errorCode,
          activation.validationIssues.joined(separator: ",")
        )
      }
      return true
    }
    return super.application(application, didFinishLaunchingWithOptions: launchOptions)
  }

  func didInitializeImplicitFlutterEngine(_ engineBridge: FlutterImplicitEngineBridge) {
    GeneratedPluginRegistrant.register(with: engineBridge.pluginRegistry)
    // 与生产 Runner 共编译同一份 NativeRuntimeConfigSupply.swift，因此 UAT 宿主
    // 读到的 runtime config 与生产 App 出自同一实现，而非测试专用替身。
    NativeRuntimeConfigChannel.register(
      binaryMessenger: engineBridge.applicationRegistrar.messenger()
    )
  }
}
