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
    appDelegate.installNativeStartupRecoveryRoot(in: recoveryWindow)
    appDelegate.showNativeStartupRecovery()
    NSLog("QWQStartup ios_native_startup_recovery_scene_connected")
  }
}

@objc final class AppSceneDelegate: FlutterSceneDelegate {
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
