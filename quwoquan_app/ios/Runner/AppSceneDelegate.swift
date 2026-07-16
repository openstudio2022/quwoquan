import Flutter
import UIKit

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
