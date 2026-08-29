import Flutter
import UIKit

/// Scene used only for a confirmed same-artifact startup fatal.
///
/// It is selected by AppDelegate before Main.storyboard resolution, so this
/// path cannot instantiate FlutterViewController or the implicit engine.
@objc final class StartupRecoverySceneDelegate: UIResponder, UIWindowSceneDelegate {
  var window: UIWindow?

  func scene(
    _ scene: UIScene,
    willConnectTo session: UISceneSession,
    options connectionOptions: UIScene.ConnectionOptions
  ) {
    guard let windowScene = scene as? UIWindowScene,
          let appDelegate = UIApplication.shared.delegate as? AppDelegate
    else {
      return
    }
    let recoveryWindow = UIWindow(windowScene: windowScene)
    window = recoveryWindow
    _ = appDelegate.connectNativeStartupSceneIfNeeded(in: recoveryWindow)
  }
}

@objc final class AppSceneDelegate: FlutterSceneDelegate {
  private var nativeStartupWindow: UIWindow?

  override func scene(
    _ scene: UIScene,
    willConnectTo session: UISceneSession,
    options connectionOptions: UIScene.ConnectionOptions
  ) {
    if let windowScene = scene as? UIWindowScene,
       let appDelegate = UIApplication.shared.delegate as? AppDelegate {
      let recoveryWindow = UIWindow(windowScene: windowScene)
      if appDelegate.connectNativeStartupSceneIfNeeded(in: recoveryWindow) {
        // The static Info.plist scene configuration names AppSceneDelegate.
        // Branch before FlutterSceneDelegate so activation/recovery never
        // asks it to create the implicit Flutter engine.
        nativeStartupWindow = recoveryWindow
        return
      }
    }
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
