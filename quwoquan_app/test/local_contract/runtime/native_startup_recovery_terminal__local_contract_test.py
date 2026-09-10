"""spec_ref: specs/feature-tree/runtime/runtime-client-foundation/cold-start-performance/spec.md#gwt-002

编译并执行生产源中的纯原生分流；无需设备、Flutter 或网络。
"""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
IOS = ROOT / "ios/Runner/AppDelegate.swift"
IOS_RECOVERY = ROOT / "ios/Runner/NativeRecoveryVersionResponse.swift"
ANDROID = ROOT / "android/app/src/main/java/com/quwoquan/quwoquan_app/StartupGateActivity.java"


def declaration(source, start):
    begin = source.index(start)
    brace = source.index("{", begin)
    depth = 1
    end = brace + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[begin:end]


class NativeRecoveryTerminalTest(unittest.TestCase):
    def test_swift_production_access_branches(self):
        body = IOS_RECOVERY.read_text()
        self.run_native("swift", body + '''
for failed in [false, true] {
  for valid in [false, true] {
    for network in [false, true] {
      let mode = NativeRecoveryAccess.resolve(activationFailed: failed, configValid: valid, networkAllowed: network)
      assert(mode == ((failed || !valid) ? .configuration : (network ? .remote : .offline)))
      assert(mode.allowsWeb == (!failed && valid && network))
    }
  }
}
''')

    def test_java_production_access_branches(self):
        body = declaration(ANDROID.read_text(), "enum NativeRecoveryAccess")
        self.run_native("java", body + '''
class Probe {
  public static void main(String[] args) {
    for (boolean failed : new boolean[]{false, true})
      for (boolean valid : new boolean[]{false, true})
        for (boolean network : new boolean[]{false, true}) {
          NativeRecoveryAccess mode = NativeRecoveryAccess.resolve(failed, valid, network);
          NativeRecoveryAccess expected = failed || !valid ? NativeRecoveryAccess.CONFIGURATION : network ? NativeRecoveryAccess.REMOTE : NativeRecoveryAccess.OFFLINE;
          if (mode != expected || mode.allowsWeb() != (!failed && valid && network)) throw new AssertionError();
        }
  }
}
''')

    def test_swift_local_surface_executes_without_web_or_checking(self):
        source = IOS.read_text()
        policy = IOS_RECOVERY.read_text()
        method = declaration(source, "  private func applyNativeLocalRecovery").replace("private func", "func", 1)
        self.run_native("swift", policy + '''
class UILabel { var text: String? }
class RecoveryActionButton {
  var isHidden = false
  var isEnabled = true
  var recoveryAction: (() -> Void)?
  var label = ""
}
class Surface { var accessibilityIdentifier = "" }
class Probe {
  var startupRecoveryView: Surface? = Surface()
  var guidance = ""
  func configureRecoveryButton(_ button: RecoveryActionButton, title: String, filled: Bool, enabled: Bool) {
    button.label = title; button.isEnabled = enabled
  }
  func showRecoveryToast(_ message: String) { guidance = message }
''' + method + '''
}
for mode in [NativeRecoveryAccess.offline, .configuration] {
  let probe = Probe(), title = UILabel(), message = UILabel()
  let primary = RecoveryActionButton(), web = RecoveryActionButton()
  web.recoveryAction = { assertionFailure("web must be removed") }
  probe.applyNativeLocalRecovery(mode, titleLabel: title, messageLabel: message, primaryButton: primary, webButton: web)
  assert(title.text == (mode == .configuration ? "应用配置不可用" : "应用暂时无法启动"))
  assert(!(message.text ?? "").contains("正在检查"))
  assert(primary.isEnabled && primary.label == "查看恢复指引")
  assert(web.isHidden && !web.isEnabled && web.recoveryAction == nil)
  primary.recoveryAction?()
  assert(probe.guidance.contains("run.sh"))
}
''')

    def test_java_local_surface_executes_without_web_or_checking(self):
        source = ANDROID.read_text()
        policy = declaration(source, "enum NativeRecoveryAccess")
        method = declaration(source, "  private void applyNativeLocalRecovery")
        self.run_native("java", policy + '''
class View { static final int GONE = 8; }
class TextView {
  String text = "";
  void setText(String value) { text = value; }
  void setContentDescription(String value) {}
}
class Button extends TextView {
  boolean enabled = true; int visibility; java.util.function.Consumer<Object> action;
  void setEnabled(boolean value) { enabled = value; }
  void setVisibility(int value) { visibility = value; }
  void setOnClickListener(java.util.function.Consumer<Object> value) { action = value; }
}
class Toast {
  static final int LENGTH_LONG = 1;
  static String guidance = "";
  static Toast makeText(Object owner, String text, int length) { guidance = text; return new Toast(); }
  void show() {}
}
class Probe {
  void configureRecoveryButton(Button button, String text, boolean filled, boolean enabled) {
    button.text = text; button.enabled = enabled;
  }
''' + method + '''
  public static void main(String[] args) {
    for (NativeRecoveryAccess mode : new NativeRecoveryAccess[]{NativeRecoveryAccess.OFFLINE, NativeRecoveryAccess.CONFIGURATION}) {
      Probe probe = new Probe(); TextView title = new TextView(), message = new TextView();
      Button primary = new Button(), web = new Button();
      web.action = ignored -> { throw new AssertionError("web must be removed"); };
      probe.applyNativeLocalRecovery(mode, title, message, primary, web);
      if (!title.text.equals(mode == NativeRecoveryAccess.CONFIGURATION ? "应用配置不可用" : "应用暂时无法启动")) throw new AssertionError();
      if (message.text.contains("正在检查") || !primary.enabled || !primary.text.equals("查看恢复指引")) throw new AssertionError();
      if (web.visibility != View.GONE || web.enabled || web.action != null) throw new AssertionError();
      primary.action.accept(null);
      if (!Toast.guidance.contains("run.sh")) throw new AssertionError();
    }
  }
}
''')

    def test_existing_runner_version_cases_compile_against_extracted_model(self):
        runner = (ROOT / "ios/RunnerTests/RunnerTests.swift").read_text()
        names = [
            "testIOSNativeRecoveryAcceptsCanonicalNullableUpdateWire",
            "testIOSNativeRecoveryRejectsNonCanonicalOrUntrustedWire",
        ]
        methods = [declaration(runner, "  func " + name) for name in names]
        methods.extend(declaration(runner, "  private func " + name) for name in (
            "recoveryVersionPayload", "parseIOSRecovery", "trustedRecoveryURL"
        ))
        # 不复制断言：原样执行 RunnerTests 中既有的版本解析正反例。
        source = IOS_RECOVERY.read_text() + "\nimport XCTest\nclass RecoveryTests: XCTestCase {\n"
        source += "\n".join(methods) + "\n}\n"
        source += "let suite = RecoveryTests.defaultTestSuite\nsuite.run()\n"
        source += "guard let result = suite.testRun, result.executionCount == 2, result.hasSucceeded else { fatalError(\"Runner version cases failed\") }\n"
        self.run_native("swift", source)

    def test_production_and_patrol_share_single_model_source(self):
        import json

        for relative in ("ios", "test_host/patrol/ios"):
            project = ROOT / relative / "Runner.xcodeproj/project.pbxproj"
            result = subprocess.run(
                ["plutil", "-convert", "json", "-o", "-", str(project)],
                capture_output=True, text=True, check=True, timeout=10,
            )
            objects = json.loads(result.stdout)["objects"]
            references = [key for key, value in objects.items()
                          if value.get("isa") == "PBXFileReference"
                          and value.get("path", "").endswith("NativeRecoveryVersionResponse.swift")]
            self.assertEqual(len(references), 1)
            reference = references[0]
            self.assertEqual((ROOT / relative / "Runner" / objects[reference]["path"]).resolve(), IOS_RECOVERY)
            runner = next(value for value in objects.values()
                          if value.get("isa") == "PBXNativeTarget" and value.get("name") == "Runner")
            source_ids = [file for phase in runner["buildPhases"]
                          if objects[phase]["isa"] == "PBXSourcesBuildPhase"
                          for file in objects[phase]["files"]]
            self.assertEqual(sum(objects[file].get("fileRef") == reference for file in source_ids), 1)
        self.assertNotIn("struct NativeRecoveryVersionResponse", IOS.read_text())
        self.assertIn("@testable import Runner", (ROOT / "ios/RunnerTests/RunnerTests.swift").read_text())

    def test_deadlines_and_url_early_returns_are_wired(self):
        swift = declaration(IOS.read_text(), "  private func checkNativeRecoveryVersion")
        java = declaration(ANDROID.read_text(), "  private void checkNativeRecoveryVersion")
        self.assertIn("DispatchQueue.main.asyncAfter", swift)
        self.assertIn("mainHandler.postDelayed(deadline, 1500L)", java)
        early_url = swift.split("guard let url = components.url else", 1)[1].split("var request", 1)[0]
        self.assertIn("applyNativeVersionUnavailable", early_url)
        self.assertIn("deadline.cancel()", early_url)
        for body in (swift, java):
            self.assertIn("applyNativeLocalRecovery", body)
            self.assertNotIn("shouldRecover", body)
            self.assertNotIn("markStarting", body)

    def run_native(self, language, source):
        output = ROOT.parent / ".qwq_output/env/repo/local/native-recovery-tests"
        output.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=output) as directory:
            directory = Path(directory)
            path = directory / ("main.swift" if language == "swift" else "Probe.java")
            path.write_text(source)
            if language == "swift":
                flags = []
                if "import XCTest" in source:
                    platform = subprocess.check_output(
                        ["xcrun", "--sdk", "macosx", "--show-sdk-platform-path"], text=True
                    ).strip()
                    frameworks = str(Path(platform) / "Developer/Library/Frameworks")
                    swift_support = str(Path(platform) / "Developer/usr/lib")
                    flags = ["-F", frameworks, "-I", swift_support, "-L", swift_support,
                             "-Xlinker", "-rpath", "-Xlinker", frameworks,
                             "-Xlinker", "-rpath", "-Xlinker", swift_support,
                             "-Xlinker", "-rpath", "-Xlinker",
                             str(Path(platform).parents[2] / "SharedFrameworks") ]
                commands = [["xcrun", "swiftc", *flags, "-module-cache-path", str(output / "swift-cache"), str(path), "-o", str(directory / "probe")], [str(directory / "probe")]]
            else:
                commands = [["javac", "-d", str(directory), str(path)], ["java", "-cp", str(directory), "Probe"]]
            for command in commands:
                result = subprocess.run(command, capture_output=True, text=True, timeout=60)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
