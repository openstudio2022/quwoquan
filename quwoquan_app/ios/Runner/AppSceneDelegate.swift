import Flutter
import UIKit

/// 唯一的 scene delegate。
///
/// scene 配置不挂 storyboard，Main.storyboard（含 FlutterViewController）只在这里按
/// 当前进程的 native startup gate 决定是否实例化：仅激活 / 恢复启动装原生 root，
/// 正常启动才创建 FlutterViewController。这样 UIKit 持久化的 UISceneSession 里永远
/// 只有一份配置，不会因为上一次冷启动走了 gate 而让下一次正常启动继承一份
/// 不会实例化 Flutter 的配置。
@objc class AppSceneDelegate: FlutterSceneDelegate {
  private var nativeStartupWindow: UIWindow?

  override func scene(
    _ scene: UIScene,
    willConnectTo session: UISceneSession,
    options connectionOptions: UIScene.ConnectionOptions
  ) {
    guard let windowScene = scene as? UIWindowScene,
          let appDelegate = UIApplication.shared.delegate as? AppDelegate
    else {
      super.scene(scene, willConnectTo: session, options: connectionOptions)
      return
    }
    // 旧的持久化 session 可能仍携带 storyboard 配置，此时 UIKit 已经创建了 window 并
    // 实例化了 root；复用它而不是再造第二个 window。
    let sceneWindow = window ?? UIWindow(windowScene: windowScene)
    if appDelegate.connectNativeStartupSceneIfNeeded(in: sceneWindow) {
      nativeStartupWindow = sceneWindow
      window = sceneWindow
      return
    }
    if sceneWindow.rootViewController == nil {
      sceneWindow.rootViewController =
        UIStoryboard(name: "Main", bundle: nil).instantiateInitialViewController()
    }
    window = sceneWindow
    sceneWindow.makeKeyAndVisible()
    appDelegate.attachFlutterSceneWindow(sceneWindow)
    NSLog("QWQStartup ios_flutter_scene_connected")
    super.scene(
      scene,
      willConnectTo: session,
      options: connectionOptions
    )
  }

  // Flutter 自绘 UI 不消费 UIKit state restoration；返回持久化 activity 会让
  // 系统在冷启动时尝试恢复过期 scene 状态，Debug 直装场景下可能卡死在启动屏。
  override func stateRestorationActivity(for scene: UIScene) -> NSUserActivity? {
    nil
  }

  override func scene(
    _ scene: UIScene,
    openURLContexts URLContexts: Set<UIOpenURLContext>
  ) {
    if let url = URLContexts.first?.url,
       CommercialAuthPlugin.shared?.handle(url: url) == true {
      return
    }
    super.scene(scene, openURLContexts: URLContexts)
  }

  override func scene(_ scene: UIScene, continue userActivity: NSUserActivity) {
    if CommercialAuthPlugin.shared?.handle(userActivity: userActivity) == true {
      return
    }
    super.scene(scene, continue: userActivity)
  }
}

/// 兼容已持久化的旧 session：此前仅激活 / 恢复启动会把 delegateClass 写成本类并随
/// UISceneSession 持久化。保留类名但不再有任何分叉行为，让这些设备的下一次冷启动
/// 直接回到唯一的 AppSceneDelegate 路径。不得再被任何 UISceneConfiguration 选择。
@objc final class StartupRecoverySceneDelegate: AppSceneDelegate {}
