import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  group('startup native/Flutter handoff contract', () {
    test('Android 使用自适应渐变背景和同源透明品牌簇，不拉伸整屏截图', () {
      for (final path in const <String>[
        'android/app/src/main/res/drawable/launch_background.xml',
        'android/app/src/main/res/drawable-v21/launch_background.xml',
        'android/app/src/main/res/drawable-night/launch_background.xml',
        'android/app/src/main/res/drawable-night-v21/launch_background.xml',
      ]) {
        final xml = _readAppFile(path);
        expect(xml, contains('<gradient'));
        expect(xml, contains('@drawable/launch_brand_cluster'));
        expect(xml, contains('android:width="393dp"'));
        expect(xml, contains('android:height="500dp"'));
        expect(xml, isNot(contains('@drawable/launch_welcome_final')));
      }

      for (final path in const <String>[
        'android/app/src/main/res/drawable-nodpi/launch_brand_cluster.png',
        'assets/brand/launch_welcome_background_master.png',
        'assets/brand/launch_brand_cluster_full_master.png',
      ]) {
        final file = _appFile(path);
        expect(file.existsSync(), isTrue, reason: path);
        expect(file.lengthSync(), greaterThan(10 * 1024), reason: path);
      }

      final generator = _readAppFile(
        'tool/generate_native_launch_welcome_final_test.dart',
      );
      expect(generator, contains('WelcomeBrandCluster'));
      expect(generator, contains('WelcomeFlowerMark'));
      expect(generator, contains('petalBloomAmounts: _fullBloom'));
      expect(generator, contains('_centerCrop'));
      expect(generator, contains("FontLoader('Noto Sans SC')"));
    });

    test('Android launcher 直达 MainActivity，原生层没有第二套动态欢迎页', () {
      expect(
        _appFile(
          'android/app/src/main/java/com/quwoquan/quwoquan_app/NativeWelcomeView.java',
        ).existsSync(),
        isFalse,
      );
      expect(
        _appFile(
          'android/app/src/main/java/com/quwoquan/quwoquan_app/StartupActivity.java',
        ).existsSync(),
        isFalse,
      );

      final manifest = _readAppFile('android/app/src/main/AndroidManifest.xml');
      expect(manifest, contains('android:name=".MainActivity"'));
      expect(manifest, contains('android.intent.category.LAUNCHER'));
      expect(manifest, isNot(contains('.StartupActivity')));

      final java = _readAppFile(
        'android/app/src/main/java/com/quwoquan/quwoquan_app/MainActivity.java',
      );
      for (final forbidden in const <String>[
        'NativeWelcomeView',
        'StartupActivity',
        'addContentView',
        'FlutterUiDisplayListener',
        'drawFlower',
        'flutterWelcomeReady',
        'flutterWelcomeCompleted',
        '启动中',
      ]) {
        expect(java, isNot(contains(forbidden)), reason: forbidden);
      }
      expect(java, contains('elapsedSinceProcessStartMs'));
      expect(java, contains('android_process'));
    });

    test('Android 12 使用同源静态花瓣 icon，Launch/Normal 使用同一背景', () {
      for (final path in const <String>[
        'android/app/src/main/res/values/styles.xml',
        'android/app/src/main/res/values-night/styles.xml',
        'android/app/src/main/res/values-v31/styles.xml',
        'android/app/src/main/res/values-night-v31/styles.xml',
      ]) {
        final xml = _readAppFile(path);
        expect(xml, contains('<style name="LaunchTheme"'));
        expect(xml, contains('<style name="NormalTheme"'));
        expect(xml, contains('@drawable/launch_background'));
        expect(xml, isNot(contains('FlutterStartupTheme')));
        expect(xml, isNot(contains('Theme.SplashScreen')));
        expect(xml, isNot(contains('android:windowIsTranslucent')));
      }
      for (final path in const <String>[
        'android/app/src/main/res/values-v31/styles.xml',
        'android/app/src/main/res/values-night-v31/styles.xml',
      ]) {
        final xml = _readAppFile(path);
        expect(xml, contains('@mipmap/ic_launcher'));
        expect(xml, contains('windowSplashScreenIconBackgroundColor'));
        expect(xml, isNot(contains('@drawable/launch_empty_icon')));
      }
    });

    test('Flutter 是唯一动效所有者，生产没有最少等待 6 秒', () {
      final welcome = _readAppFile('lib/ui/welcome/pages/welcome_screen.dart');
      final timeline = _readAppFile(
        'lib/ui/welcome/welcome_motion_timeline.dart',
      );
      final flower = _readAppFile(
        'lib/ui/welcome/widgets/welcome_flower_mark.dart',
      );
      final shell = _readAppFile('lib/quwoquan_app_shell.dart');

      expect(timeline, contains('StartupWelcomeTiming production'));
      expect(timeline, contains('Duration(seconds: 3)'));
      expect(timeline, contains('Duration(seconds: 6)'));
      expect(timeline, contains('maxReplayCount: 2'));
      expect(timeline, contains('minimumCompressionRatio = 0.65'));
      expect(timeline, contains("motionSpecVersion = 'petal_bloom_v2'"));
      expect(
        timeline,
        contains('gatheringOrder = <int>[7, 6, 5, 4, 3, 2, 1, 0]'),
      );
      expect(
        timeline,
        contains('bloomingOrder = <int>[0, 1, 2, 3, 4, 5, 6, 7]'),
      );
      expect(welcome, contains('SingleTickerProviderStateMixin'));
      expect(welcome, contains('_terminal'));
      expect(welcome, contains('WelcomeExitReason.deadline'));
      expect(welcome, contains('WelcomeFlowMode.startup'));
      expect(welcome, isNot(contains('waitUntilFirstFrameRasterized')));
      expect(welcome, isNot(contains('WidgetsBinding.instance.endOfFrame')));
      expect(welcome, isNot(contains('minEnterDelay')));
      expect(welcome, isNot(contains('maxWaitingBloomCycles')));
      expect(welcome, isNot(contains('List<AnimationController>')));
      expect(flower, contains('historicalBudVisualFactor = 0.561024'));
      expect(flower, contains('canvas.scale(visualFactor)'));
      expect(flower, isNot(contains('Matrix4')));
      expect(flower, isNot(contains('rotateX')));
      expect(flower, isNot(contains('scaleY')));
      expect(shell, contains('ensureAppRouterLibraryLoaded'));
      expect(shell, contains('WelcomeFlowMode.frozen'));
      expect(shell, contains('Duration(milliseconds: 120)'));
      expect(shell, contains("phase: 'welcome_overlay_removed'"));
      expect(shell, contains("'overlayRemovedMs': removedMs"));
      expect(shell, contains("trigger: 'deadline_fallback'"));
      expect(shell, contains('_buildStartupFallbackApp'));
    });

    test('三端从平台最早时钟计算 6 秒预算，只传时间不传动画状态', () {
      final bridge = _readAppFile(
        'lib/core/platform/startup_native_bridge.dart',
      );
      final runtime = _readAppFile('lib/app/app_startup_runtime.dart');
      final android = _readAppFile(
        'android/app/src/main/java/com/quwoquan/quwoquan_app/MainActivity.java',
      );
      final ios = _readAppFile('ios/Runner/AppDelegate.swift');
      final web = _readAppFile('web/index.html');

      expect(bridge, contains('elapsedSinceProcessStartMs'));
      expect(bridge, contains('deadlineOrigin'));
      expect(runtime, contains('elapsedSinceProcessStart'));
      expect(runtime, contains("'fallbackDart'"));
      final welcome = _readAppFile('lib/ui/welcome/pages/welcome_screen.dart');
      expect(welcome, contains('hydrateNativeProcessSegments'));
      expect(welcome, contains('unawaited('));
      expect(welcome, contains('_armDeadline();'));
      expect(welcome, isNot(contains('await AppStartupRuntime.instance')));
      expect(android, contains('SystemClock.elapsedRealtime()'));
      expect(android, contains('android_process'));
      expect(android, contains('recordStartupEvent'));
      expect(android, contains('startup_event'));
      expect(
        android.indexOf('registerStartupTimingsChannel(flutterEngine);'),
        lessThan(
          android.indexOf('super.configureFlutterEngine(flutterEngine);'),
        ),
      );
      expect(ios, contains('ProcessInfo.processInfo.systemUptime'));
      expect(ios, contains('ios_process'));
      expect(ios, contains('recordStartupEvent'));
      expect(
        ios.indexOf('registerStartupTimingsChannel('),
        lessThan(ios.indexOf('GeneratedPluginRegistrant.register')),
      );
      expect(web, contains('__qwqStartupStartedAtMs'));
      expect(web, contains('__qwqStartupElapsedMs'));
      for (final source in <String>[android, ios, bridge]) {
        expect(source, isNot(contains('animationProgress')));
        expect(source, isNot(contains('replayCount')));
        expect(source, isNot(contains('petal')));
      }
    });

    test('iOS LaunchScreen 使用自适应背景与独立同源品牌簇', () {
      final plist = _readAppFile('ios/Runner/Info.plist');
      final storyboard = _readAppFile(
        'ios/Runner/Base.lproj/LaunchTransitionScreen.storyboard',
      );
      expect(plist, contains('<string>LaunchTransitionScreen</string>'));
      expect(storyboard, contains('image="LaunchTransitionBackground"'));
      expect(storyboard, contains('image="LaunchBrandCluster"'));
      expect(storyboard, contains('QWQ-LAUNCH-BRAND-CENTER-X'));
      expect(storyboard, contains('QWQ-LAUNCH-BRAND-CENTER-Y'));
      expect(storyboard, contains('constant="393"'));
      expect(storyboard, contains('constant="500"'));

      final adaptiveBackgrounds = <String, (int, int)>{
        'ios/Runner/Assets.xcassets/LaunchTransitionBackground.imageset/LaunchTransitionBackground.png':
            (1, 3),
        'ios/Runner/Assets.xcassets/LaunchTransitionBackground.imageset/LaunchTransitionBackground@2x.png':
            (2, 6),
        'ios/Runner/Assets.xcassets/LaunchTransitionBackground.imageset/LaunchTransitionBackground@3x.png':
            (3, 9),
      };
      for (final entry in adaptiveBackgrounds.entries) {
        final file = _appFile(entry.key);
        expect(file.existsSync(), isTrue, reason: entry.key);
        expect(_pngSize(file), entry.value, reason: entry.key);
      }

      for (final path in const <String>[
        'ios/Runner/Assets.xcassets/LaunchBrandCluster.imageset/LaunchBrandCluster.png',
        'ios/Runner/Assets.xcassets/LaunchBrandCluster.imageset/LaunchBrandCluster@2x.png',
        'ios/Runner/Assets.xcassets/LaunchBrandCluster.imageset/LaunchBrandCluster@3x.png',
      ]) {
        final file = _appFile(path);
        expect(file.existsSync(), isTrue, reason: path);
        expect(file.lengthSync(), greaterThan(5 * 1024), reason: path);
      }
    });

    test('设备 probe 明确检查原生镜像、可见时限和 Flutter 欢迎事件', () {
      final probe = _readAppFile(
        'scripts/device/verify_startup_first_frame.py',
      );
      final motionProbe = _readAppFile(
        'scripts/device/verify_welcome_motion_frames.py',
      );
      expect(
        probe,
        contains(
          'DEFAULT_ANDROID_ACTIVITY = "com.quwoquan.quwoquan_app/.MainActivity"',
        ),
      );
      expect(probe, contains('nativeWelcomeDetected'));
      expect(probe, contains('FORBIDDEN_NATIVE_WELCOME_LOG_PATTERNS'));
      expect(probe, contains('--android-visible-by-ms'));
      expect(probe, contains('--skip-screenshots'));
      expect(probe, contains('firstVisibleMs'));
      expect(probe, contains('startupSequenceMotionCurrent'));
      expect(probe, contains('petal_bloom_v2'));
      expect(probe, contains('android_flutter_welcome_ready'));
      expect(probe, isNot(contains('.StartupActivity')));
      expect(
        motionProbe,
        contains('GATHERING_ORDER = (7, 6, 5, 4, 3, 2, 1, 0)'),
      );
      expect(
        motionProbe,
        contains('BLOOMING_ORDER = (0, 1, 2, 3, 4, 5, 6, 7)'),
      );
      expect(motionProbe, contains('oriented_minor'));
      expect(motionProbe, contains('center_radius'));
      expect(motionProbe, contains('frame_displacement'));
    });

    test('启动 prerequisites 首帧后并行且失败不阻断 Shell readiness', () {
      final bootstrap = _readAppFile('lib/app_bootstrap.dart');
      final scheduler = _readAppFile('lib/app/startup_init_scheduler.dart');
      final beforeRunApp = bootstrap.substring(0, bootstrap.indexOf('runApp('));
      expect(beforeRunApp, isNot(contains('await startupPrerequisites')));
      expect(beforeRunApp, isNot(contains('hydrateNativeProcessSegments')));
      expect(
        scheduler,
        contains('_markShellReadyAndObserveStartupPrerequisites'),
      );
      expect(scheduler, contains('onShellReady(true)'));
      expect(
        scheduler.indexOf('onShellReady(true)'),
        lessThan(scheduler.indexOf('await prerequisites.timeout')),
      );
    });
  });
}

String _readAppFile(String relativePath) =>
    _appFile(relativePath).readAsStringSync();

File _appFile(String relativePath) {
  final direct = File(relativePath);
  if (direct.existsSync()) {
    return direct;
  }
  return File('quwoquan_app/$relativePath');
}

(int, int) _pngSize(File file) {
  final bytes = file.readAsBytesSync();
  expect(bytes.length, greaterThanOrEqualTo(24), reason: file.path);
  int uint32(int offset) =>
      (bytes[offset] << 24) |
      (bytes[offset + 1] << 16) |
      (bytes[offset + 2] << 8) |
      bytes[offset + 3];
  return (uint32(16), uint32(20));
}
