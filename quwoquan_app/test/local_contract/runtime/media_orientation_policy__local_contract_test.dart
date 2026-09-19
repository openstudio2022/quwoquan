// spec_ref: specs/feature-tree/runtime/spec.md#dom-002
// spec_ref: specs/feature-tree/runtime/spec.md#dom-003
import 'dart:async';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/platform/media/media_orientation_policy.dart';

const _portraitUp = [DeviceOrientation.portraitUp];

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('真实SystemChrome通道只发送固定portraitUp且不捕获原生方向', () async {
    final calls = <MethodCall>[];
    final messenger =
        TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    messenger.setMockMethodCallHandler(SystemChannels.platform, (call) async {
      calls.add(call);
      return null;
    });
    addTearDown(() {
      messenger.setMockMethodCallHandler(SystemChannels.platform, null);
    });

    final owner = MediaOrientationPolicy();
    await owner.enforcePortraitUp();
    await owner.enforcePortraitUp();

    expect(calls, hasLength(2));
    for (final call in calls) {
      expect(call.method, 'SystemChrome.setPreferredOrientations');
      expect(call.arguments, ['DeviceOrientation.portraitUp']);
    }
  });

  test('传给平台的方向集合不可变', () async {
    final owner = MediaOrientationPolicy(
      apply: (values) async {
        expect(values, _portraitUp);
        expect(values.clear, throwsUnsupportedError);
      },
    );
    await owner.enforcePortraitUp();
  });

  test('新请求不等待旧完成且迟到完成不重放释放租约', () async {
    final pending = Completer<void>();
    final writes = <List<DeviceOrientation>>[];
    final owner = MediaOrientationPolicy(
      apply: (values) {
        writes.add(List.of(values));
        return writes.length == 1 ? pending.future : Future<void>.value();
      },
    );
    final first = owner.enforcePortraitUp();
    await owner.enforcePortraitUp();
    expect(writes, [_portraitUp, _portraitUp]);
    pending.complete();
    await first;
    await Future<void>.delayed(Duration.zero);
    expect(writes, [_portraitUp, _portraitUp]);
  });

  testWidgets('两秒超时保留失败且迟到完成不追加任何方向写入', (tester) async {
    final pending = Completer<void>();
    final writes = <List<DeviceOrientation>>[];
    final owner = MediaOrientationPolicy(
      apply: (values) {
        writes.add(List.of(values));
        return writes.length == 1 ? pending.future : Future<void>.value();
      },
    );
    final failure = expectLater(
      owner.enforcePortraitUp(),
      throwsA(isA<TimeoutException>()),
    );
    await tester.pump(const Duration(seconds: 2));
    await failure;
    await owner.enforcePortraitUp();
    pending.complete();
    await tester.pump();
    expect(writes, [_portraitUp, _portraitUp]);
  });

  test('平台异常不变成confirmed且后续重试仍只请求portraitUp', () async {
    final failure = PlatformException(code: 'orientation_unavailable');
    final writes = <List<DeviceOrientation>>[];
    final owner = MediaOrientationPolicy(
      apply: (values) async {
        writes.add(List.of(values));
        if (writes.length == 1) throw failure;
      },
    );
    await expectLater(owner.enforcePortraitUp(), throwsA(same(failure)));
    await owner.enforcePortraitUp();
    expect(writes, [_portraitUp, _portraitUp]);
  });

  testWidgets('真实前后台生命周期只在resumed重申固定方向', (tester) async {
    final writes = <List<DeviceOrientation>>[];
    final owner = MediaOrientationPolicy(
      apply: (values) async => writes.add(List.of(values)),
    );
    tester.binding.addObserver(owner);
    addTearDown(() => tester.binding.removeObserver(owner));
    await owner.enforcePortraitUp();

    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.inactive);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
    await tester.pump();
    expect(writes, [_portraitUp]);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    await tester.pump();
    expect(writes, [_portraitUp, _portraitUp]);
  });

  testWidgets('resumed失败交给Flutter错误边界且下一次恢复仍可重试', (tester) async {
    final failure = PlatformException(code: 'orientation_unavailable');
    var attempts = 0;
    final owner = MediaOrientationPolicy(
      apply: (_) async {
        if (++attempts == 1) throw failure;
      },
    );
    tester.binding.addObserver(owner);
    addTearDown(() => tester.binding.removeObserver(owner));
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    await tester.pump();
    expect(tester.takeException(), same(failure));
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    await tester.pump();
    expect(attempts, 2);
    expect(tester.takeException(), isNull);
  });

  test('Android原生启动门主Activity锁正向竖屏且透明回调继承后方', () {
    final manifest = File('android/app/src/main/AndroidManifest.xml')
        .readAsStringSync();
    String activity(String name) =>
        RegExp('<activity\\s[^>]*android:name="${RegExp.escape(name)}"[^>]*>')
            .firstMatch(manifest)!
            .group(0)!;

    expect(
      activity('.StartupGateActivity'),
      contains('android:screenOrientation="portrait"'),
    );
    expect(
      activity('.MainActivity'),
      contains('android:screenOrientation="portrait"'),
    );
    expect(
      activity('com.leadwise.quwoquan.wxapi.WXEntryActivity'),
      contains('android:screenOrientation="behind"'),
    );
  });

  test('iPhone原生支持方向仅正向竖屏且不擅自禁用iPad多任务', () {
    final plist = File('ios/Runner/Info.plist').readAsStringSync();
    String orientations(String key) => RegExp(
      '<key>${RegExp.escape(key)}</key>\\s*<array>(.*?)</array>',
      dotAll: true,
    ).firstMatch(plist)!.group(1)!;
    final phone = orientations('UISupportedInterfaceOrientations');
    expect(
      RegExp('<string>(.*?)</string>')
          .allMatches(phone)
          .map((match) => match.group(1)),
      ['UIInterfaceOrientationPortrait'],
    );
    final ipad = orientations('UISupportedInterfaceOrientations~ipad');
    expect(ipad, contains('UIInterfaceOrientationLandscapeLeft'));
    expect(ipad, contains('UIInterfaceOrientationLandscapeRight'));
    expect(plist, isNot(contains('<key>UIRequiresFullScreen</key>')));
  });

  test('启动和热重启接线在水合之前等待固定方向并只登记一次observer', () {
    final source = File('lib/runtime/shell/startup/app_bootstrap.dart')
        .readAsStringSync();
    final request = source.indexOf(
      'await MediaOrientationPolicy.instance.enforcePortraitUp();',
    );
    expect(
      request,
      greaterThan(source.indexOf('WidgetsFlutterBinding.ensureInitialized();')),
    );
    expect(
      request,
      lessThan(
        source.indexOf(
          'await CloudRuntimeConfig.hydrateFromNativeRuntimePackage(',
        ),
      ),
    );
    expect(
      request,
      lessThan(
        source.indexOf('AppStartupRuntime.instance.markRunAppCalled();'),
      ),
    );
    final registration = source.indexOf(
      'addObserver(MediaOrientationPolicy.instance)',
    );
    expect(
      registration,
      greaterThan(source.indexOf('if (!_bootstrapLifecycleObserverInstalled)')),
    );
    expect(registration, lessThan(request));
    expect(source, isNot(contains('DeviceOrientation.')));
    expect(
      source,
      isNot(contains('MediaOrientationPolicy.instance.configure(')),
    );
  });

  test('方向写owner不再存在传感器捕获历史策略或媒体租约轨道', () {
    final source = File(
      'lib/runtime/platform/media/media_orientation_policy.dart',
    ).readAsStringSync();
    for (final retired in [
      'NativeOrientationReader',
      'MediaOrientationLease',
      'MediaOrientationResult',
      'mediaOrientationPolicyProvider',
      'capture(',
      'configure(',
      'DeviceOrientation.landscape',
      'DeviceOrientation.portraitDown',
      'lockCaptureOrientation',
    ]) {
      expect(source, isNot(contains(retired)), reason: retired);
    }
  });
}
