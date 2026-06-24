import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  group('native launch screen contract', () {
    test('Android native launch background is not a static welcome bitmap', () {
      for (final path in const [
        'android/app/src/main/res/drawable/launch_background.xml',
        'android/app/src/main/res/drawable-v21/launch_background.xml',
        'android/app/src/main/res/drawable-night/launch_background.xml',
        'android/app/src/main/res/drawable-night-v21/launch_background.xml',
      ]) {
        final xml = _readAppFile(path);
        expect(xml, contains('<shape'));
        expect(xml, contains('<gradient'));
        expect(xml, contains('android:startColor="#1491FF"'));
        expect(xml, contains('android:centerColor="#0A84FF"'));
        expect(xml, contains('android:endColor="#1554D1"'));
        expect(xml, isNot(contains('<layer-list')));
        expect(xml, isNot(contains('@drawable/launch_splash_icon')));
        expect(xml, isNot(contains('android:gravity="center"')));
        expect(xml, isNot(contains('@drawable/launch_background_full')));
        expect(xml, isNot(contains('<bitmap')));
        expect(xml, isNot(contains('@drawable/launch_brand_cluster')));
        expect(xml, isNot(contains('<color android:color="#0A84FF"')));
        expect(xml, isNot(contains('<color android:color="#0F172A"')));
      }
    });

    test(
      'Android native welcome host is only the pre-Flutter transition guard',
      () {
        final nativeWelcome = _readAppFile(
          'android/app/src/main/java/com/quwoquan/quwoquan_app/NativeWelcomeView.java',
        );
        expect(nativeWelcome, contains('class NativeWelcomeView'));
        expect(nativeWelcome, contains('SEQUENCE_DURATION_MS = 1500L'));
        expect(nativeWelcome, contains('PETAL_STAGGER_MS = 70L'));
        expect(nativeWelcome, contains('INITIAL_PETAL_PROGRESS = 0.24f'));
        expect(nativeWelcome, contains('drawFlower'));
        expect(nativeWelcome, contains('启动中，马上进入'));
        expect(nativeWelcome, contains('趣我圈'));
        expect(nativeWelcome, contains('遇见同趣，绽放热爱'));
      },
    );

    test(
      'native launch asset generator does not mirror Flutter welcome content',
      () {
        final script = _readAppFile(
          'scripts/media/generate_native_launch_assets.py',
        );
        final androidSplashIcon = _functionBody(
          script,
          'generate_android_splash_icon',
        );
        final iosOverlay = _functionBody(script, 'generate_ios_launch_overlay');

        expect(script, contains('Flutter welcome screen is the only place'));
        expect(script, isNot(contains('launch_background_full')));
        expect(androidSplashIcon, isNot(contains('draw_flower')));
        expect(iosOverlay, isNot(contains('draw_welcome_content')));
      },
    );

    test(
      'Android 12+ launcher uses transition background, not system splash',
      () {
        for (final path in const [
          'android/app/src/main/res/values-v31/styles.xml',
          'android/app/src/main/res/values-night-v31/styles.xml',
        ]) {
          final xml = _readAppFile(path);
          expect(xml, isNot(contains('android:windowDisablePreview')));
          expect(xml, isNot(contains('android:windowSplashScreenBackground')));
          expect(xml, isNot(contains('windowSplashScreenBackground')));
          expect(
            xml,
            isNot(contains('android:windowSplashScreenAnimatedIcon')),
          );
          expect(xml, isNot(contains('windowSplashScreenAnimatedIcon')));
          expect(xml, isNot(contains('Theme.SplashScreen')));
          expect(xml, isNot(contains('postSplashScreenTheme')));
          expect(xml, contains('@drawable/launch_background'));
          expect(xml, contains('FlutterStartupTheme'));
        }
      },
    );

    test(
      'Android Flutter host startup theme is transparent over native welcome',
      () {
        for (final path in const [
          'android/app/src/main/res/values/styles.xml',
          'android/app/src/main/res/values-night/styles.xml',
          'android/app/src/main/res/values-v31/styles.xml',
          'android/app/src/main/res/values-night-v31/styles.xml',
        ]) {
          final xml = _readAppFile(path);
          final style = _styleBody(xml, 'FlutterStartupTheme');
          expect(style, contains('Theme.Translucent.NoTitleBar'));
          expect(style, contains('android:windowIsTranslucent'));
          expect(style, contains('@android:color/transparent'));
          expect(style, contains('android:backgroundDimEnabled'));
          expect(style, isNot(contains('@drawable/launch_background')));
        }
      },
    );

    test('iOS launch storyboard does not mirror the welcome page', () {
      final storyboard = _readAppFile(
        'ios/Runner/Base.lproj/LaunchScreen.storyboard',
      );
      expect(storyboard, isNot(contains('image="LaunchImage"')));
      expect(storyboard, isNot(contains('QWQ-LAUNCH-IMAGE')));
      expect(storyboard, isNot(contains('<image name="LaunchImage"')));
      expect(storyboard, contains('image="LaunchTransitionBackground"'));
      expect(storyboard, contains('QWQ-LAUNCH-TRANSITION-BACKGROUND'));
      expect(storyboard, contains('backgroundColor'));
    });

    test('generated native transition assets are present for both platforms', () {
      for (final path in const [
        'android/app/src/main/res/drawable-mdpi/launch_splash_icon.png',
        'android/app/src/main/res/drawable-hdpi/launch_splash_icon.png',
        'android/app/src/main/res/drawable-xhdpi/launch_splash_icon.png',
        'android/app/src/main/res/drawable-xxhdpi/launch_splash_icon.png',
        'android/app/src/main/res/drawable-xxxhdpi/launch_splash_icon.png',
        'ios/Runner/Assets.xcassets/LaunchImage.imageset/LaunchImage.png',
        'ios/Runner/Assets.xcassets/LaunchImage.imageset/LaunchImage@2x.png',
        'ios/Runner/Assets.xcassets/LaunchImage.imageset/LaunchImage@3x.png',
        'ios/Runner/Assets.xcassets/LaunchTransitionBackground.imageset/LaunchTransitionBackground.png',
        'ios/Runner/Assets.xcassets/LaunchTransitionBackground.imageset/LaunchTransitionBackground@2x.png',
        'ios/Runner/Assets.xcassets/LaunchTransitionBackground.imageset/LaunchTransitionBackground@3x.png',
      ]) {
        final file = _appFile(path);
        expect(file.existsSync(), isTrue, reason: path);
        final minBytes = path.endsWith('launch_splash_icon.png') ? 64 : 1024;
        expect(file.lengthSync(), greaterThan(minBytes), reason: path);
      }

      for (final path in const [
        'android/app/src/main/res/drawable-mdpi/launch_brand_cluster.png',
        'android/app/src/main/res/drawable-hdpi/launch_brand_cluster.png',
        'android/app/src/main/res/drawable-xhdpi/launch_brand_cluster.png',
        'android/app/src/main/res/drawable-xxhdpi/launch_brand_cluster.png',
        'android/app/src/main/res/drawable-xxxhdpi/launch_brand_cluster.png',
        'android/app/src/main/res/drawable-nodpi/launch_background_full.png',
      ]) {
        expect(_appFile(path).existsSync(), isFalse, reason: path);
      }
    });

    test('Android launcher uses native startup activity before Flutter', () {
      final manifest = _readAppFile('android/app/src/main/AndroidManifest.xml');
      expect(manifest, contains('android:name=".StartupActivity"'));
      expect(manifest, contains('android:name=".MainActivity"'));
      expect(manifest, contains('android:theme="@style/FlutterStartupTheme"'));
      expect(manifest, contains('android.intent.category.LAUNCHER'));
      expect(manifest, isNot(contains('android:noHistory="true"')));
      expect(manifest, isNot(contains('android:taskAffinity=""')));
      expect(
        manifest.indexOf('android:name=".StartupActivity"'),
        lessThan(manifest.indexOf('android.intent.category.LAUNCHER')),
      );

      final startupJava = _readAppFile(
        'android/app/src/main/java/com/quwoquan/quwoquan_app/StartupActivity.java',
      );
      expect(startupJava, contains('NativeWelcomeView'));
      expect(startupJava, contains('android_startup_welcome_first_draw'));
      expect(startupJava, contains('nativeStartupStartedElapsedRealtime'));
      expect(startupJava, contains('android_startup_activity_handoff'));
      expect(startupJava, contains('overridePendingTransition(0, 0)'));
      expect(startupJava, contains('if (handedOff)'));
      expect(startupJava, contains('root.post(this::openMainActivity)'));
      expect(startupJava, contains('protected void onResume()'));
      expect(startupJava, isNot(contains('taskAffinity')));
      expect(
        startupJava.substring(
          startupJava.indexOf('private void openMainActivity()'),
        ),
        isNot(contains('finish();')),
      );
      expect(startupJava, isNot(contains('MAIN_ACTIVITY_HANDOFF_DELAY_MS')));
      expect(
        startupJava,
        isNot(contains('postDelayed(this::openMainActivity')),
      );
    });

    test(
      'Android Activity releases native overlay after Flutter UI is visible',
      () {
        final java = _readAppFile(
          'android/app/src/main/java/com/quwoquan/quwoquan_app/MainActivity.java',
        );
        expect(java, contains('FlutterFragmentActivity'));
        expect(java, contains('installStartupOverlay'));
        expect(java, contains('addContentView'));
        expect(java, contains('removeStartupOverlay'));
        expect(java, contains('tryRemoveStartupOverlay'));
        expect(java, contains('FlutterUiDisplayListener'));
        expect(java, contains('NativeWelcomeView'));
        expect(java, contains('quwoquan/startup/native'));
        expect(java, contains('nativeStartupElapsedMs'));
        expect(java, contains('flutterWelcomeReady'));
        expect(java, contains('flutterWelcomeCompleted'));
        expect(java, contains('MIN_NATIVE_WELCOME_MS = 0L'));
        expect(java, contains('MAX_FLUTTER_WELCOME_READY_WAIT_MS = 4500L'));
        expect(java, isNot(contains('MAX_NATIVE_WELCOME_MS')));
        expect(java, contains('android_native_welcome_host_installed'));
        expect(java, contains('android_flutter_welcome_ready'));
        expect(java, contains('android_native_welcome_completion_received'));
        expect(java, isNot(contains('released_before_dart_completion')));
        expect(java, contains('android_flutter_ui_displayed'));
        expect(java, isNot(contains('SplashScreen.installSplashScreen')));
        final nativeWelcome = _readAppFile(
          'android/app/src/main/java/com/quwoquan/quwoquan_app/NativeWelcomeView.java',
        );
        expect(nativeWelcome, contains('android_native_welcome_first_draw'));
      },
    );

    test(
      'Android release build patches dev-only plugins out of registrant',
      () {
        final gradle = _readAppFile('android/app/build.gradle.kts');
        expect(gradle, contains('patch_android_plugin_registrant.sh'));
        expect(gradle, contains('JavaWithJavac'));
        expect(gradle, contains('androidx.core:core-splashscreen'));

        final patchScript = _readAppFile(
          'scripts/patch_android_plugin_registrant.sh',
        );
        expect(patchScript, contains('registerOptionalDevPlugin'));
        expect(patchScript, contains('integration_test'));
        expect(patchScript, contains('patrol'));
        expect(patchScript, contains('dev-only plugin'));
      },
    );

    test(
      'Flutter welcome continues the native startup timeline instead of replaying',
      () {
        final runtime = _readAppFile('lib/app/app_startup_runtime.dart');
        expect(runtime, contains('nativeStartupElapsed'));
        expect(runtime, contains('markFlutterWelcomeReady'));
        expect(runtime, contains('completeNativeWelcomeOverlay'));
        expect(runtime, contains('nativeStartupElapsedMs'));

        final bridge = _readAppFile('lib/core/platform/native_bridge.dart');
        expect(bridge, contains('flutterWelcomeReady'));
        expect(bridge, contains('flutterWelcomeCompleted'));
        expect(bridge, contains('markFlutterWelcomeReady'));

        final welcome = _readAppFile(
          'lib/ui/welcome/pages/welcome_screen.dart',
        );
        expect(welcome, contains('initialSequenceElapsed'));
        expect(welcome, contains('sequenceEnabled'));
        expect(welcome, contains('_sequenceCompletionDuration - elapsed'));
        expect(
          welcome,
          contains('_minimumSequenceDuration = Duration(milliseconds: 1500)'),
        );
        expect(welcome, isNot(contains('nativeWelcomeCoveredDuration')));
        expect(welcome, isNot(contains('awaitedBeforeFloor')));

        final shell = _readAppFile('lib/quwoquan_app_shell.dart');
        expect(shell, contains('_startupNativeSequenceElapsed'));
        expect(shell, contains('_androidNativeWelcomeSequenceComplete'));
        expect(shell, contains('nativeStartupElapsed('));
        expect(shell, contains('attempts: 1'));
        expect(shell, contains('initialSequenceElapsed:'));
        expect(shell, contains('sequenceEnabled:'));
        expect(shell, contains('markFlutterWelcomeReady'));
        expect(shell, contains('completeNativeWelcomeOverlay'));
      },
    );

    test('startup first-frame probe launches the native startup activity', () {
      final probe = _readAppFile(
        'scripts/device/verify_startup_first_frame.py',
      );
      expect(
        probe,
        contains(
          'DEFAULT_ANDROID_ACTIVITY = "com.quwoquan.quwoquan_app/.StartupActivity"',
        ),
      );
      expect(probe, contains('android_startup_activity_handoff'));
      expect(probe, contains('android_startup_welcome_first_draw'));
      expect(probe, contains('startupWelcomeFirstDrawMs'));
      expect(probe, contains('firstFrameWithinBudget'));
      expect(probe, contains('android_native_welcome_host_installed'));
      expect(probe, contains('"install", "-r", "-d"'));
      expect(probe, contains('"uninstall", args.android_package'));
      expect(probe, contains('android-install.txt'));
      expect(probe, contains('android_flutter_welcome_ready'));
      expect(
        probe,
        contains('android_flutter_welcome_ready_sequence_elapsed_ms'),
      );
      expect(probe, contains('flutterWelcomeSequenceContinuityWithinBudget'));
      expect(probe, contains('android_native_welcome_completion_received'));
      expect(
        probe,
        contains(
          'parser.add_argument("--android-visible-by-ms", type=int, default=250)',
        ),
      );
    });

    test(
      'Flutter bootstrap installs local HTTPS trust before media clients',
      () {
        final dart = _readAppFile('lib/app_bootstrap.dart');
        final beforeRunApp = dart.substring(0, dart.indexOf('runApp('));
        expect(
          beforeRunApp,
          contains('await _installLocalDevHttpsTrustBeforeMediaClients();'),
        );
        expect(
          dart,
          contains('await LocalDevHttpsTrust.installForCurrentRuntime();'),
        );
        expect(
          dart,
          isNot(contains('_installLocalDevHttpsTrustAfterFirstFrame')),
        );
      },
    );
  });
}

String _functionBody(String source, String functionName) {
  final start = source.indexOf('def $functionName(');
  expect(start, isNonNegative, reason: functionName);
  final next = source.indexOf('\ndef ', start + 1);
  if (next == -1) {
    return source.substring(start);
  }
  return source.substring(start, next);
}

String _styleBody(String source, String styleName) {
  final start = source.indexOf('<style name="$styleName"');
  expect(start, isNonNegative, reason: styleName);
  final end = source.indexOf('</style>', start);
  expect(end, isNonNegative, reason: styleName);
  return source.substring(start, end);
}

String _readAppFile(String relativePath) =>
    _appFile(relativePath).readAsStringSync();

File _appFile(String relativePath) {
  final direct = File(relativePath);
  if (direct.existsSync()) {
    return direct;
  }
  final fromRepoRoot = File('quwoquan_app/$relativePath');
  if (fromRepoRoot.existsSync()) {
    return fromRepoRoot;
  }
  return direct;
}
