import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  group('native launch screen contract', () {
    test(
      'Android native launch background is content-free transition only',
      () {
        for (final path in const [
          'android/app/src/main/res/drawable/launch_background.xml',
          'android/app/src/main/res/drawable-v21/launch_background.xml',
          'android/app/src/main/res/drawable-night/launch_background.xml',
          'android/app/src/main/res/drawable-night-v21/launch_background.xml',
        ]) {
          final xml = _readAppFile(path);
          expect(xml, contains('<shape'));
          expect(xml, contains('<gradient'));
          expect(xml, isNot(contains('<layer-list')));
          expect(xml, isNot(contains('<bitmap')));
          expect(xml, isNot(contains('@drawable/launch_splash_icon')));
          expect(xml, isNot(contains('@drawable/launch_brand_cluster')));
          expect(xml, isNot(contains('@drawable/launch_background_full')));
          expect(xml, isNot(contains('android:gravity="center"')));
        }
      },
    );

    test('Android native layer does not implement a mirrored welcome page', () {
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

      final java = _readAppFile(
        'android/app/src/main/java/com/quwoquan/quwoquan_app/MainActivity.java',
      );
      for (final forbidden in const [
        'NativeWelcomeView',
        'StartupActivity',
        'addContentView',
        'FlutterUiDisplayListener',
        'quwoquan/startup/native',
        'nativeStartupElapsedMs',
        'flutterWelcomeReady',
        'flutterWelcomeCompleted',
        'android_native_welcome',
        'android_startup_welcome_first_draw',
        'drawFlower',
        '趣我圈',
        '遇见同趣',
        '启动中',
      ]) {
        expect(java, isNot(contains(forbidden)), reason: forbidden);
      }
    });

    test('Android launcher enters MainActivity directly', () {
      final manifest = _readAppFile('android/app/src/main/AndroidManifest.xml');
      expect(manifest, isNot(contains('android:name=".StartupActivity"')));
      expect(manifest, contains('android:name=".MainActivity"'));
      expect(manifest, contains('android:exported="true"'));
      expect(manifest, contains('android:theme="@style/LaunchTheme"'));
      expect(manifest, contains('android.intent.category.LAUNCHER'));
      expect(manifest, isNot(contains('@style/FlutterStartupTheme')));
      expect(manifest, isNot(contains('nativeStartupStartedElapsedRealtime')));
    });

    test('Android themes do not use transparent startup overlay host', () {
      for (final path in const [
        'android/app/src/main/res/values/styles.xml',
        'android/app/src/main/res/values-night/styles.xml',
      ]) {
        final xml = _readAppFile(path);
        expect(xml, contains('<style name="LaunchTheme"'));
        expect(xml, contains('<style name="NormalTheme"'));
        expect(xml, contains('@drawable/launch_background'));
        expect(xml, isNot(contains('FlutterStartupTheme')));
        expect(xml, isNot(contains('Theme.Translucent.NoTitleBar')));
        expect(xml, isNot(contains('android:windowIsTranslucent')));
        expect(xml, isNot(contains('@android:color/transparent')));
        expect(xml, isNot(contains('Theme.SplashScreen')));
        expect(xml, isNot(contains('windowSplashScreenAnimatedIcon')));
        expect(xml, isNot(contains('windowSplashScreenBackground')));
      }

      for (final path in const [
        'android/app/src/main/res/values-v31/styles.xml',
        'android/app/src/main/res/values-night-v31/styles.xml',
      ]) {
        final xml = _readAppFile(path);
        expect(xml, contains('<style name="LaunchTheme"'));
        expect(xml, contains('<style name="NormalTheme"'));
        expect(xml, contains('@drawable/launch_background'));
        expect(xml, contains('android:windowSplashScreenBackground'));
        expect(xml, contains('@drawable/launch_empty_icon'));
        expect(xml, isNot(contains('FlutterStartupTheme')));
        expect(xml, isNot(contains('Theme.Translucent.NoTitleBar')));
        expect(xml, isNot(contains('android:windowIsTranslucent')));
        expect(xml, isNot(contains('@android:color/transparent')));
        expect(xml, isNot(contains('Theme.SplashScreen')));
        expect(xml, isNot(contains('@drawable/launch_splash_icon')));
        expect(xml, isNot(contains('@mipmap/ic_launcher')));
      }

      final emptyIcon = _readAppFile(
        'android/app/src/main/res/drawable/launch_empty_icon.xml',
      );
      expect(emptyIcon, contains('android:width="1dp"'));
      expect(emptyIcon, contains('android:height="1dp"'));
      expect(emptyIcon, contains('#00000000'));
      expect(emptyIcon, isNot(contains('@drawable')));
      expect(emptyIcon, isNot(contains('@mipmap')));
    });

    test(
      'Flutter welcome screen is the only branded welcome implementation',
      () {
        final runtime = _readAppFile('lib/app/app_startup_runtime.dart');
        final bridge = _readAppFile('lib/core/platform/native_bridge.dart');
        final welcome = _readAppFile(
          'lib/ui/welcome/pages/welcome_screen.dart',
        );
        final shell = _readAppFile('lib/quwoquan_app_shell.dart');

        for (final source in [runtime, bridge, welcome, shell]) {
          expect(source, isNot(contains('nativeStartupElapsed')));
          expect(source, isNot(contains('nativeStartupElapsedMs')));
          expect(source, isNot(contains('flutterWelcomeReady')));
          expect(source, isNot(contains('flutterWelcomeCompleted')));
          expect(source, isNot(contains('completeNativeWelcomeOverlay')));
          expect(source, isNot(contains('quwoquan/startup/native')));
        }

        expect(bridge, isNot(contains('StartupNativeBridge')));
        expect(welcome, isNot(contains('initialSequenceElapsed')));
        expect(welcome, isNot(contains('sequenceEnabled')));
        expect(welcome, isNot(contains('onFlutterWelcomeReady')));
        expect(welcome, contains('_beginAnimatedSequence'));
        expect(welcome, contains('waitUntilFirstFrameRasterized'));
        expect(welcome, contains('_visibleFrameGuard'));
        expect(shell, contains('_maxStartupWelcomeReplayCount = 2'));
        expect(shell, contains('startupStillStartingInline'));
        expect(shell, contains("_buildStartupFallbackApp"));
        expect(shell, contains("'result': degraded ? 'degraded' : 'entered'"));
      },
    );

    test(
      'startup first-frame probe launches MainActivity and forbids native welcome',
      () {
        final probe = _readAppFile(
          'scripts/device/verify_startup_first_frame.py',
        );
        expect(
          probe,
          contains(
            'DEFAULT_ANDROID_ACTIVITY = "com.quwoquan.quwoquan_app/.MainActivity"',
          ),
        );
        expect(probe, contains('nativeWelcomeDetected'));
        expect(probe, contains('FORBIDDEN_NATIVE_WELCOME_LOG_PATTERNS'));
        expect(probe, contains('"install", "-r", "-d"'));
        expect(probe, contains('"uninstall", args.android_package'));
        expect(probe, contains('android-install.txt'));
        expect(probe, isNot(contains('.StartupActivity')));
        expect(probe, isNot(contains('startupWelcomeFirstDrawMs')));
        expect(probe, contains('"android_flutter_welcome_ready"'));
        expect(
          probe,
          contains(
            'parser.add_argument("--android-visible-by-ms", type=int, default=2000)',
          ),
        );
      },
    );

    test('iOS launch storyboard does not mirror the welcome page', () {
      final plist = _readAppFile('ios/Runner/Info.plist');
      final storyboard = _readAppFile(
        'ios/Runner/Base.lproj/LaunchTransitionScreen.storyboard',
      );
      final mainStoryboard = _readAppFile(
        'ios/Runner/Base.lproj/Main.storyboard',
      );
      final xcodeProject = _readAppFile('ios/Runner.xcodeproj/project.pbxproj');
      expect(plist, contains('<string>LaunchTransitionScreen</string>'));
      expect(
        _appFile('ios/Runner/Base.lproj/LaunchScreen.storyboard').existsSync(),
        isFalse,
      );
      expect(xcodeProject, contains('LaunchTransitionScreen.storyboard'));
      expect(xcodeProject, isNot(contains('LaunchScreen.storyboard')));
      expect(storyboard, isNot(contains('image="LaunchImage"')));
      expect(storyboard, isNot(contains('QWQ-LAUNCH-IMAGE')));
      expect(storyboard, isNot(contains('<image name="LaunchImage"')));
      expect(storyboard, contains('image="LaunchTransitionBackground"'));
      expect(storyboard, contains('QWQ-LAUNCH-TRANSITION-BACKGROUND'));
      expect(storyboard, contains('backgroundColor'));
      expect(mainStoryboard, contains('red="0.0196078431"'));
      expect(storyboard, contains('red="0.0392156863"'));
      expect(storyboard, contains('green="0.5176470588"'));
      expect(storyboard, contains('blue="1"'));
    });

    test(
      'Flutter bootstrap starts local HTTPS trust before runApp without blocking first frame',
      () {
        final dart = _readAppFile('lib/app_bootstrap.dart');
        final beforeRunApp = dart.substring(0, dart.indexOf('runApp('));
        expect(beforeRunApp, contains('startupPrerequisites ='));
        expect(beforeRunApp, isNot(contains('await startupPrerequisites')));
        expect(
          dart,
          contains('await LocalDevHttpsTrust.installForCurrentRuntime();'),
        );
        expect(dart, contains('startupPrerequisites: startupPrerequisites'));
        expect(
          dart,
          isNot(contains('_installLocalDevHttpsTrustAfterFirstFrame')),
        );

        final shell = _readAppFile('lib/quwoquan_app_shell.dart');
        final scheduler = _readAppFile('lib/app/startup_init_scheduler.dart');
        expect(shell, contains('startupPrerequisites'));
        expect(shell, contains('_startupPrerequisiteBudget'));
        expect(scheduler, contains('_completeStartupPrerequisitesThenReady'));
      },
    );
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
