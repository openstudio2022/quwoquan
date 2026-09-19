// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-009
// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-009.t1
// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-009.t2
// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-009.t3
// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-009.t4
// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-009.t5
// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-009.t6
// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-009.t7
// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-009.t8
// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-009.t9
// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-009.t10
// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-009.t11
// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-009.t12
import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/runtime/di/alpha_dependencies.dart';
import 'package:quwoquan_app/runtime/shell/startup/app_bootstrap.dart';
import 'package:quwoquan_app/runtime/shell/startup/app_startup_runtime.dart';
import 'package:quwoquan_app/runtime/platform/startup_native_bridge.dart';
import 'package:quwoquan_app/runtime/config/generated/app_launch_contract.g.dart';
import 'package:quwoquan_cloud_contracts/generated/values/user/account/authentication_challenge.values.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/auth/auth_gate.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/config/rehearsal_storage_namespace.dart';
import 'package:quwoquan_app/service/user_service/account/account_session/presentation/login_page.dart';

import 'auth/auth_session_store__local_contract_test.dart' as auth_fixture;

import 'dart:ui' as ui;

import 'package:quwoquan_app/runtime/di/alpha_content_composition.dart';
import 'package:quwoquan_app/runtime/platform/media/bundled_public_media_delivery.dart';

import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:flutter/material.dart';
import 'package:quwoquan_app/runtime/shell/recovery/runtime_recovery_host.dart';
import 'package:quwoquan_app/runtime/config/offline_content_failure.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_config.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/runtime/config/offline_content_bundle.dart';
import 'package:quwoquan_app/runtime/di/user_dependencies.dart';
import 'package:quwoquan_app/runtime/di/content_dependencies.dart';
import 'package:quwoquan_app/runtime/di/login_dependencies.dart';
import 'package:quwoquan_app/runtime/transport/executor/unavailable_cloud_operation_executor.dart';
import 'package:quwoquan_app/runtime/platform/storage/cache/cache_telemetry_sink.dart';
import 'package:quwoquan_app/service/content_service/content/post/adapters/content_cache_services.dart';
import 'package:quwoquan_app/service/content_service/content/post/adapters/post_reader_bundled.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/adapters/user_profile_cache_service.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/adapters/profile_query_bundled.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/profile_query.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/persona_query.dart';

import '../../support/runtime/cloud_boundary_test_scope.dart';

import 'package:quwoquan_app/runtime/di/public_media_delivery_dependencies.dart';
import 'package:quwoquan_app/runtime/platform/media/bundled_image_provider.dart';
import 'package:quwoquan_app/runtime/transport/media/media_delivery_reference.dart';

import '../../support/runtime/config/runtime_package_test_hydration.dart';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/config/generated/offline_content_bundle_identity.g.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_detail_payload.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-007.t1
// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-007.t2
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  installCanonicalOfflineAssetsForTests();

  for (final confirmed in [false, true]) {
    testWidgets('实际startup observer纯内存读取与rehearsal成功IO confirmed=$confirmed', (
      tester,
    ) async {
      final runtime = AppStartupRuntime.instance;
      runtime.resetForTesting();
      runtime.markBootstrapStarted();
      final bridge = _ObservedStartupBridge();
      AppStartupRuntime.overrideNativeTimingsBridgeForTesting(bridge);
      if (confirmed) await tester.runAsync(runtime.beginNativeStartupAttempt);
      await tester.runAsync(
        () => auth_fixture.hydrateIsolatedStorageRuntime(
          instance: 'observation-private',
        ),
      );
      final directory = (await tester.runAsync(
        () => Directory.systemTemp.createTemp('qwq-observation-'),
      ))!;
      var pathCalls = 0;
      const channel = MethodChannel('plugins.flutter.io/path_provider');
      final messenger =
          TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
      messenger.setMockMethodCallHandler(channel, (_) async {
        pathCalls++;
        return directory.path;
      });
      configureAlphaDependencies();
      late RehearsalStorageObservation Function() read;
      late SyntheticLoginCapability capability;
      try {
        await tester.pumpWidget(
          AppStartupScope(
            runtimeIdentity: CloudRuntimeConfig.runtimeConfigPackageDigest,
            childBuilder: (overrides) => ProviderScope(
              overrides: mergeStartupScopeOverrides(
                sealedCloudBoundaryOverrides(),
                overrides,
              ),
              child: Consumer(
                builder: (context, ref, _) {
                  read = ref.read(alphaStorageObservationReaderProvider);
                  capability = ref.read(syntheticLoginCapabilityProvider)!;
                  return const SizedBox.shrink();
                },
              ),
            ),
          ),
        );
        expect(installingStartupScopeLifecycle, isNull);
        final before = pathCalls;
        final constructed = read();
        for (var i = 0; i < 3; i++) {
          expect(read().toWire(), constructed.toWire());
        }
        expect(pathCalls, before);
        expect(
          constructed.status,
          confirmed
              ? RehearsalObservationStatus.available
              : RehearsalObservationStatus.unavailable,
        );
        expect(
          constructed.auth.state,
          RehearsalConsumerObservationState.notObserved,
        );
        expect(
          constructed.installId.state,
          RehearsalConsumerObservationState.notObserved,
        );
        expect(
          constructed.pending.state,
          RehearsalConsumerObservationState.notObserved,
        );
        expect(
          constructed.rehearsal.state,
          confirmed
              ? RehearsalConsumerObservationState.constructed
              : RehearsalConsumerObservationState.notObserved,
        );
        await tester.runAsync(
          () => capability.challengePort.begin(
            BeginSyntheticChallenge(
              identity: capability.createIdentityLabel(),
              requestKey: capability.createRequestKey(),
            ),
          ),
        );
        final afterIO = pathCalls;
        final used = read();
        expect(pathCalls, afterIO);
        if (confirmed) {
          expect(
            used.startupAttemptId,
            runtime.confirmedStartupAttempt!.attemptId,
          );
          expect(used.generation, matches(RegExp(r'^[1-9][0-9]*$')));
          expect(
            used.rehearsal.state,
            RehearsalConsumerObservationState.ioObserved,
          );
          expect(
            used.rehearsal.successfulOperations,
            contains(RehearsalSuccessfulOperation.write),
          );
        } else {
          expect(used.startupAttemptId, isEmpty);
          expect(used.generation, isEmpty);
          expect(used.bindingDigest, isEmpty);
          await tester.runAsync(runtime.beginNativeStartupAttempt);
          expect(runtime.confirmedStartupAttempt, isNotNull);
          expect(
            read().status,
            RehearsalObservationStatus.unavailable,
            reason: '固定绑定observer不从迟到确认回填历史IO',
          );
          capability.createIdentityLabel();
        }
        await tester.pumpWidget(const SizedBox.shrink());
        final disposed = read();
        expect(disposed.status, RehearsalObservationStatus.unavailable);
        expect(
          disposed.configurationState,
          RehearsalConfigurationObservationState.invalidated,
        );
        expect(disposed.bindingDigest, isEmpty);
        expect(pathCalls, afterIO);
      } finally {
        await tester.pumpWidget(const SizedBox.shrink());
        messenger.setMockMethodCallHandler(channel, null);
        await tester.runAsync(() => directory.delete(recursive: true));
        runtime.resetForTesting();
        AppStartupRuntime.resetNativeTimingsBridgeForTesting();
        await tester.runAsync(
          () => hydrateRuntimePackageForTests(environment: 'beta'),
        );
      }
    });
  }

  testWidgets('正式Alpha启动scope注入isolated登录并跨R0R1复用至根释放', (tester) async {
    await tester.runAsync(
      () => auth_fixture.hydrateIsolatedStorageRuntime(
        instance: 'startup-private',
      ),
    );
    final space = CloudRuntimeConfig.rehearsalSpace!;
    final directory = (await tester.runAsync(
      () => Directory.systemTemp.createTemp('qwq-startup-synthetic-'),
    ))!;
    const paths = MethodChannel('plugins.flutter.io/path_provider');
    final messenger =
        TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    messenger.setMockMethodCallHandler(paths, (_) async => directory.path);
    final secure = auth_fixture.PrivateAuthStorage();
    final pendingCalls = <String>[];
    const secureChannel = MethodChannel(
      'plugins.it_nomads.com/flutter_secure_storage',
    );
    messenger.setMockMethodCallHandler(secureChannel, (call) async {
      final args = call.arguments as Map;
      final key = args['key'] as String;
      pendingCalls.add('${call.method}:$key');
      return null;
    });
    final store = AuthSessionStore.isolated(
      namespace: RehearsalStorageNamespace(space),
      currentSpace: () => CloudRuntimeConfig.rehearsalSpace,
      secureStorage: secure,
    );
    configureAlphaDependencies();
    final capabilities = <SyntheticLoginCapability>[];
    var completed = 0;
    try {
      await tester.pumpWidget(
        AppStartupScope(
          runtimeIdentity: CloudRuntimeConfig.runtimeConfigPackageDigest,
          childBuilder: (overrides) => RuntimeRecoveryHost(
            childBuilder: (key, _) => ProviderScope(
              key: key,
              overrides: mergeStartupScopeOverrides([
                ...sealedCloudBoundaryOverrides(),
                authSessionStoreProvider.overrideWith((ref) {
                  final generationStore = AuthSessionStore.isolated(
                    namespace: RehearsalStorageNamespace(space),
                    currentSpace: () => CloudRuntimeConfig.rehearsalSpace,
                    secureStorage: secure,
                  );
                  ref.onDispose(generationStore.dispose);
                  return generationStore;
                }),
              ], overrides),
              child: CupertinoApp(
                home: Consumer(
                  builder: (context, ref, _) {
                    final capability = ref.watch(
                      syntheticLoginCapabilityProvider,
                    );
                    expect(capability, isNotNull);
                    if (capabilities.isEmpty ||
                        !identical(capabilities.last, capability)) {
                      capabilities.add(capability!);
                    }
                    return LoginFrameHost(
                      dismissPolicy: LoginDismissPolicy.hostControlledClose,
                      onLoggedIn: () => completed++,
                      onDismiss: () {},
                    );
                  },
                ),
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('loginPhoneField')), findsNothing);
      final loginContainer = ProviderScope.containerOf(
        tester.element(find.byType(LoginFrameHost)),
      );
      await tester.runAsync(
        () => loginContainer.read(pendingOtpAttemptStoreProvider).read(),
      );
      expect(pendingCalls, [
        'read:${RehearsalStorageNamespace(space).pendingOtpKey}',
      ]);
      await tester.tap(find.byKey(const ValueKey('syntheticLoginSubmit')));
      await tester.pump();
      // 实际IO在runAsync中推进，不触摸系统Keychain或真实用户目录。
      for (
        var i = 0;
        i < 40 &&
            find.byKey(const ValueKey('syntheticLoginHint')).evaluate().isEmpty;
        i++
      ) {
        await tester.runAsync(
          () => Future<void>.delayed(const Duration(milliseconds: 25)),
        );
        await tester.pump();
      }
      final hint = tester
          .widget<Text>(find.byKey(const ValueKey('syntheticLoginHint')))
          .data!;
      await tester.enterText(
        find.byKey(const ValueKey('syntheticLoginConfirmation')),
        hint,
      );
      secure.failWrite = true;
      await tester.tap(find.byKey(const ValueKey('syntheticLoginSubmit')));
      for (var i = 0; i < 40; i++) {
        await tester.runAsync(
          () => Future<void>.delayed(const Duration(milliseconds: 25)),
        );
        await tester.pump();
        if (find
            .text(FoundationText.syntheticLoginStorageFailed)
            .evaluate()
            .isNotEmpty) {
          break;
        }
      }
      expect(completed, 0);
      expect(
        find.text(FoundationText.syntheticLoginStorageFailed),
        findsOneWidget,
      );
      final beforeRetry = (await tester.runAsync(
        () => directory
            .list(recursive: true)
            .where((entry) => entry is File && entry.path.endsWith('.json'))
            .cast<File>()
            .toList(),
      ))!;
      expect(beforeRetry, hasLength(1));
      final expectedFile =
          '${offlineContentManifestDigest.replaceAll(':', '_')}_${space.instanceId}.json';
      expect(beforeRetry.single.path, endsWith(expectedFile));
      final committedBeforeRetry = await tester.runAsync(
        beforeRetry.single.readAsString,
      );
      secure.failWrite = false;
      await tester.tap(find.byKey(const ValueKey('syntheticLoginSubmit')));
      for (var i = 0; i < 80 && completed == 0; i++) {
        await tester.runAsync(
          () => Future<void>.delayed(const Duration(milliseconds: 25)),
        );
        await tester.pump();
      }
      expect(completed, 1);
      expect(
        await tester.runAsync(beforeRetry.single.readAsString),
        committedBeforeRetry,
        reason: 'auth失败同意图重试不得新建挑战或重复synthetic提交',
      );
      final state = await tester.runAsync(store.read);
      expect(state!.ownerId, startsWith('alpha-account:'));
      expect(secure.calls, isNot(contains('auth.install_id')));
      expect(
        secure.calls,
        isNot(contains('auth.alpha-local%7Calpha.access_token')),
      );
      await tester.runAsync(
        () => loginContainer
            .read(authSessionControllerProvider.notifier)
            .hardLogout(),
      );
      expect((await tester.runAsync(store.read))!.ownerId, isEmpty);
      RuntimeRecoveryCoordinator.instance.enter(
        error: StateError('read-reentry'),
        stack: StackTrace.current,
        source: 'startup-scope-test',
      );
      await tester.pump();
      capabilities.single.requireCurrent();
      await tester.tap(find.text('重新进入应用'));
      await tester.pump();
      RuntimeRecoveryCoordinator.instance.markSafeShellReady();
      await tester.pumpAndSettle();
      expect(capabilities, hasLength(1));
      expect(
        (await tester.runAsync(store.read))!.ownerId,
        isEmpty,
        reason: 'R1不得synthetic.restore补写auth复活logout',
      );
      final capability = capabilities.single;
      await tester.pumpWidget(const SizedBox.shrink());
      expect(capability.requireCurrent, throwsA(isA<Object>()));
      expect(capability.createIdentityLabel, throwsA(isA<Object>()));
    } finally {
      await tester.pumpWidget(const SizedBox.shrink());
      store.dispose();
      messenger.setMockMethodCallHandler(paths, null);
      messenger.setMockMethodCallHandler(secureChannel, null);
      await tester.runAsync(() => directory.delete(recursive: true));
      await tester.runAsync(
        () => hydrateRuntimePackageForTests(environment: 'beta'),
      );
    }
  });

  testWidgets('启动scope standard不注入synthetic且runtime切换撤销旧capability', (
    tester,
  ) async {
    configureAlphaDependencies();
    SyntheticLoginCapability? current;
    Widget root() => AppStartupScope(
      runtimeIdentity: CloudRuntimeConfig.runtimeConfigPackageDigest,
      childBuilder: (overrides) => ProviderScope(
        overrides: mergeStartupScopeOverrides(
          sealedCloudBoundaryOverrides(),
          overrides,
        ),
        child: Consumer(
          builder: (context, ref, _) {
            current = ref.watch(syntheticLoginCapabilityProvider);
            return const SizedBox.shrink();
          },
        ),
      ),
    );
    await tester.runAsync(
      () => hydrateRuntimePackageForTests(environment: 'alpha'),
    );
    await tester.pumpWidget(root());
    expect(current, isNull);
    await tester.runAsync(
      () => auth_fixture.hydrateIsolatedStorageRuntime(
        instance: 'startup-switch',
      ),
    );
    await tester.pumpWidget(root());
    expect(current, isNotNull);
    final old = current!;
    await tester.runAsync(
      () => hydrateRuntimePackageForTests(environment: 'beta'),
    );
    await tester.pumpWidget(root());
    expect(current, isNull);
    expect(old.requireCurrent, throwsA(isA<Object>()));
    expect(old.createRequestKey, throwsA(isA<Object>()));
    await tester.pumpWidget(const SizedBox.shrink());
  });

  test('图片真实ImageCache同scope命中但不同scope同引用隔离', () async {
    final scope = OfflineContentReadScope();
    final bundle = await scope.load();
    final ref = bundle.media.byAssetId.values
        .firstWhere((a) => a.kind == 'image')
        .canonicalReference;
    final first = BundledPublicMediaDelivery(
      loadBundle: scope.load,
      checkScope: scope.check,
    );
    final secondScope = OfflineContentReadScope();
    final second = BundledPublicMediaDelivery(
      loadBundle: secondScope.load,
      checkScope: secondScope.check,
    );
    final a = first.imageProvider(ref);
    final b = first.imageProvider(ref);
    expect(a, b);
    expect(a, isNot(second.imageProvider(ref)));
    final image = await _decodeImage(a);
    final again = await _decodeImage(b);
    expect(image.image.isCloneOf(again.image), isTrue);
    image.dispose();
    again.dispose();
    scope.dispose();
    await expectLater(_decodeImage(b), throwsA(isA<OfflineContentFailure>()));
    final independent = await _decodeImage(second.imageProvider(ref));
    independent.dispose();
    secondScope.dispose();
    PaintingBinding.instance.imageCache.clear();
    PaintingBinding.instance.imageCache.clearLiveImages();
  });

  test('图片四重身份runtime pin AssetBundle generation均隔离', () async {
    await hydrateRuntimePackageForTests(environment: 'alpha');
    final assets = _MutableCanonicalAssets();
    final first = OfflineContentReadScope(assets: assets);
    final bundle = await first.load();
    final ref = bundle.media.byAssetId.values
        .firstWhere((a) => a.kind == 'image')
        .canonicalReference;
    final a = BundledPublicMediaDelivery(
      loadBundle: first.load,
      checkScope: first.check,
    ).imageProvider(ref);
    (await _decodeImage(a)).dispose();
    final otherAssets = OfflineContentReadScope(
      assets: _MutableCanonicalAssets(),
    );
    final b = BundledPublicMediaDelivery(
      loadBundle: otherAssets.load,
      checkScope: otherAssets.check,
    ).imageProvider(ref);
    expect(a, isNot(b));
    (await _decodeImage(b)).dispose();
    final otherGeneration = OfflineContentReadScope(assets: assets);
    final c = BundledPublicMediaDelivery(
      loadBundle: otherGeneration.load,
      checkScope: otherGeneration.check,
    ).imageProvider(ref);
    expect(a, isNot(c));
    (await _decodeImage(c)).dispose();
    final badPin = OfflineContentReadScope(
      assets: assets,
      expectedDigest: 'sha256:${'0' * 64}',
    );
    await expectLater(
      _decodeImage(
        BundledPublicMediaDelivery(
          loadBundle: badPin.load,
          checkScope: badPin.check,
        ).imageProvider(ref),
      ),
      throwsA(isA<OfflineContentFailure>()),
    );
    await hydrateRuntimePackageForTests(environment: 'beta');
    await expectLater(_decodeImage(a), throwsA(isA<OfflineContentFailure>()));
    final newRuntime = OfflineContentReadScope(assets: assets);
    (await _decodeImage(
      BundledPublicMediaDelivery(
        loadBundle: newRuntime.load,
        checkScope: newRuntime.check,
      ).imageProvider(ref),
    )).dispose();
    for (final scope in [
      first,
      otherAssets,
      otherGeneration,
      badPin,
      newRuntime,
    ]) {
      scope.dispose();
    }
    PaintingBinding.instance.imageCache.clear();
    PaintingBinding.instance.imageCache.clearLiveImages();
  });

  test('图片catalog与ImageCache命中后来源篡改删除仍失败', () async {
    final assets = _MutableCanonicalAssets();
    final scope = OfflineContentReadScope(assets: assets);
    final bundle = await scope.load();
    final asset = bundle.media.byAssetId.values.firstWhere(
      (a) => a.kind == 'image',
    );
    final delivery = BundledPublicMediaDelivery(
      loadBundle: scope.load,
      checkScope: scope.check,
    );
    final provider = delivery.imageProvider(asset.canonicalReference);
    (await _decodeImage(provider)).dispose();
    assets.corruptPath = asset.assetPath;
    await expectLater(
      _decodeImage(delivery.imageProvider(asset.canonicalReference)),
      throwsA(isA<OfflineContentFailure>()),
    );
    assets.corruptPath = null;
    assets.missingPath = asset.assetPath;
    await expectLater(
      _decodeImage(delivery.imageProvider(asset.canonicalReference)),
      throwsA(isA<FileSystemException>()),
    );
    assets.missingPath = null;
    (await _decodeImage(delivery.imageProvider(asset.canonicalReference)))
        .dispose();
    scope.dispose();
    PaintingBinding.instance.imageCache.clear();
    PaintingBinding.instance.imageCache.clearLiveImages();
  });

  test('图片decode迟到codec在scope失效后拒绝且释放', () async {
    final scope = OfflineContentReadScope();
    final bundle = await scope.load();
    final ref = bundle.media.byAssetId.values
        .firstWhere((a) => a.kind == 'image')
        .canonicalReference;
    final provider = BundledPublicMediaDelivery(
      loadBundle: scope.load,
      checkScope: scope.check,
    ).imageProvider(ref) as BundledImageProvider;
    final started = Completer<void>();
    final finish = Completer<void>();
    late _ObservedCodec observed;
    Future<ui.Codec> decode(
      ui.ImmutableBuffer buffer, {
      ui.TargetImageSize Function(int, int)? getTargetSize,
    }) async {
      final codec = await ui.instantiateImageCodecWithSize(
        buffer,
        getTargetSize: getTargetSize,
      );
      observed = _ObservedCodec(codec);
      started.complete();
      await finish.future;
      return observed;
    }

    final completer = provider.loadImage(provider, decode);
    final result = Completer<ImageInfo>();
    final listener = ImageStreamListener(
      (image, _) => result.complete(image),
      onError: (Object error, StackTrace? stack) =>
          result.completeError(error, stack),
    );
    completer.addListener(listener);
    final expectation = expectLater(
      result.future,
      throwsA(isA<OfflineContentFailure>()),
    );
    await started.future;
    scope.dispose();
    finish.complete();
    await expectation;
    expect(observed.disposed, isTrue);
    completer.removeListener(listener);
  });

  test('媒体安装token：两代逆序卸载与重复卸载不影响新安装', () async {
    await hydrateRuntimePackageForTests(environment: 'beta');
    final first = BundledPublicMediaDelivery();
    final second = BundledPublicMediaDelivery();
    final disposeFirst = installPublicMediaDelivery(first);
    final disposeSecond = installPublicMediaDelivery(second);
    expect(publicMediaDelivery, same(second));
    disposeFirst();
    expect(publicMediaDelivery, same(second));
    disposeSecond();
    final remote = publicMediaDelivery;
    expect(remote, isA<RemotePublicMediaDelivery>());
    disposeSecond();
    disposeFirst();
    expect(publicMediaDelivery, same(remote));
    await hydrateRuntimePackageForTests(environment: 'beta');
  });

  test('媒体安装token：同对象同digest重复安装仍是独立代际', () async {
    await hydrateRuntimePackageForTests(environment: 'beta');
    final delivery = BundledPublicMediaDelivery();
    final oldDispose = installPublicMediaDelivery(delivery);
    final currentDispose = installPublicMediaDelivery(delivery);
    oldDispose();
    expect(publicMediaDelivery, same(delivery));
    currentDispose();
    expect(publicMediaDelivery, isA<RemotePublicMediaDelivery>());
    final thirdDispose = installPublicMediaDelivery(delivery);
    currentDispose();
    expect(publicMediaDelivery, same(delivery));
    thirdDispose();
    await hydrateRuntimePackageForTests(environment: 'beta');
  });

  test('媒体安装token：Alpha卸载不放宽网络禁止', () async {
    await hydrateRuntimePackageForTests(environment: 'alpha');
    final dispose = installPublicMediaDelivery(BundledPublicMediaDelivery());
    dispose();
    expect(
      () => publicMediaDelivery,
      throwsA(isA<CloudRuntimeConfigurationException>()),
    );
    dispose();
    expect(
      () => publicMediaDelivery,
      throwsA(isA<CloudRuntimeConfigurationException>()),
    );
    await hydrateRuntimePackageForTests(environment: 'beta');
  });

  test('媒体安装token：runtime换源后的旧卸载不清getter新状态', () async {
    await hydrateRuntimePackageForTests(environment: 'alpha');
    final oldDispose = installPublicMediaDelivery(BundledPublicMediaDelivery());
    await hydrateRuntimePackageForTests(environment: 'beta');
    final remote = publicMediaDelivery;
    expect(remote, isA<RemotePublicMediaDelivery>());
    oldDispose();
    expect(publicMediaDelivery, same(remote));
    final replacement = BundledPublicMediaDelivery();
    final disposeReplacement = installPublicMediaDelivery(replacement);
    oldDispose();
    expect(publicMediaDelivery, same(replacement));
    disposeReplacement();
    expect(publicMediaDelivery, isA<RemotePublicMediaDelivery>());
  });

  testWidgets('读取generation切源只重建读取factory且旧disposer不伤新代', (tester) async {
    var creates = 0;
    var releases = 0;
    final oldDisposers = <VoidCallback>[];
    final client = GeneratedCloudOperationClient(
      const UnavailableCloudOperationExecutor(),
    );
    ProfileQuery resolve() =>
        UserProductionComposition.generatedAdapter<ProfileQuery>(
          UserProductionAdapter.profileQuery,
          client: client,
          invocationContext: (String _, String _) =>
              throw StateError('no remote'),
        );
    Widget root(String identity) => RuntimeRecoveryHost(
      readSourceIdentity: identity,
      createReadGeneration: () {
        creates++;
        final dispose = installAlphaContentComposition();
        oldDisposers.add(dispose);
        return () {
          releases++;
          dispose();
        };
      },
      childBuilder: (_, _) => const MaterialApp(home: SizedBox.shrink()),
    );
    await tester.pumpWidget(root('source-a'));
    final first = resolve();
    await tester.pumpWidget(root('source-b'));
    final second = resolve();
    expect(identical(first, second), isFalse);
    expect(creates, 2);
    expect(releases, 1);
    oldDisposers.first();
    expect(resolve(), same(second));
    await tester.pumpWidget(const SizedBox.shrink());
    expect(releases, 2);
    expect(resolve(), isNot(same(second)));
  });

  testWidgets('生命周期结构Red：真实R0与根dispose不能遗留静态adapter', (tester) async {
    final client = GeneratedCloudOperationClient(
      const UnavailableCloudOperationExecutor(),
    );
    ProfileQuery resolve() =>
        UserProductionComposition.generatedAdapter<ProfileQuery>(
          UserProductionAdapter.profileQuery,
          client: client,
          invocationContext: (String _, String _) =>
              throw StateError('不请求Remote'),
        );
    late ProfileQuery first;
    final disposed = <int>[];
    final stages = <String>[];
    var generation = 0;
    try {
      await tester.pumpWidget(
        RuntimeRecoveryHost(
          createReadGeneration: () => installAlphaContentComposition(),
          childBuilder: (_, reentry) {
            if (!reentry) first = resolve();
            final current = ++generation;
            if (reentry && identical(resolve(), first)) {
              stages.add('R1-old-static-adapter');
            }
            return _CompositionLifetimeProbe(
              onDispose: () => disposed.add(current),
            );
          },
        ),
      );
      RuntimeRecoveryCoordinator.instance.enter(
        error: StateError('scope-probe'),
        stack: StackTrace.current,
        source: 'lifecycle_contract',
      );
      await tester.pump();
      expect(disposed, [1]);
      if (identical(resolve(), first)) stages.add('R0-static-not-released');
      await tester.tap(find.text('重新进入应用'));
      await tester.pump();
      RuntimeRecoveryCoordinator.instance.markSafeShellReady();
      await tester.pump();
      await tester.pumpWidget(const SizedBox.shrink());
      expect(disposed, [1, 2]);
      if (identical(resolve(), first)) stages.add('root-static-not-released');
      // ignore: avoid_print
      print('SOURCE_LIFECYCLE_STRUCTURE_RED=${jsonEncode(stages)}');
      expect(stages, isEmpty);
    } finally {
      await tester.pumpWidget(const SizedBox.shrink());
      ContentProductionComposition.useRemoteReadComposition();
      UserProductionComposition.useRemoteReadComposition();
    }
  });

  testWidgets('生命周期Red：R0/R1与根销毁必须释放旧composition读取权', (tester) async {
    final client = GeneratedCloudOperationClient(
      const UnavailableCloudOperationExecutor(),
    );
    await tester.runAsync(
      () => hydrateRuntimePackageForTests(environment: 'alpha'),
    );
    final generations = <bool>[];
    final disposed = <int>[];
    final exposed = <String>[];
    final identities = <ProfileQuery>[];
    ProfileQuery resolve() =>
        UserProductionComposition.generatedAdapter<ProfileQuery>(
          UserProductionAdapter.profileQuery,
          client: client,
          invocationContext: (String _, String _) =>
              throw StateError('不应请求Remote'),
        );
    Future<void> checkRevoked(ProfileQuery old, String id, String stage) async {
      try {
        await old.getUserProfile(id);
        exposed.add(stage);
      } on OfflineContentFailure {
        // 只有明确失效才满足此Red，不用Timeout或任意异常冒充释放。
      }
    }

    try {
      // 这里只取测试寻址字段；随后真实adapter仍用canonical pin完整验包。
      final raw = jsonDecode(
        (await tester.runAsync(
          () => File(offlineContentManifestAssetPath).readAsString(),
        ))!,
      ) as Map<String, dynamic>;
      final creator = PersonaProfileView.fromWire(
        raw['creators'][0]['projection'] as Map<String, Object?>,
      );
      await tester.pumpWidget(
        RuntimeRecoveryHost(
          createReadGeneration: () => installAlphaContentComposition(),
          childBuilder: (_, reentry) {
            generations.add(reentry);
            identities.add(resolve());
            final generation = generations.length;
            return _CompositionLifetimeProbe(
              onDispose: () => disposed.add(generation),
            );
          },
        ),
      );
      final first = identities.first;
      final primed = await tester.runAsync(
        () => first.getUserProfile(creator.personaId),
      );
      expect(primed, isNotNull, reason: '首次完整验证失败不能冒缓存成功');
      RuntimeRecoveryCoordinator.instance.enter(
        error: const UnrecoverableRuntimeException(
          cause: 'diagnostic',
          source: 'lifecycle_contract',
        ),
        stack: StackTrace.current,
        source: 'lifecycle_contract',
      );
      await tester.pump();
      expect(disposed, [1]);
      await tester.runAsync(
        () => checkRevoked(first, creator.personaId, 'R0-old-adapter'),
      );
      await tester.tap(find.text('重新进入应用'));
      await tester.pump();
      expect(generations, [false, true]);
      if (identical(identities.first, identities.last)) {
        exposed.add('R1-reused-static-adapter');
      }
      RuntimeRecoveryCoordinator.instance.markSafeShellReady();
      await tester.pump();
      final last = identities.last;
      await tester.runAsync(() => last.getUserProfile(creator.personaId));
      await tester.pumpWidget(const SizedBox.shrink());
      expect(disposed, [1, 2]);
      await tester.runAsync(
        () => checkRevoked(last, creator.personaId, 'root-dispose-old-adapter'),
      );
      // ignore: avoid_print
      print(
        'SOURCE_LIFECYCLE_RED=${jsonEncode({'generations': generations, 'disposed': disposed, 'staleReads': exposed})}',
      );
      expect(exposed, isEmpty, reason: '业务树已销毁不等于静态composition或adapter缓存已释放');
    } finally {
      await tester.pumpWidget(const SizedBox.shrink());
      ContentProductionComposition.useRemoteReadComposition();
      UserProductionComposition.useRemoteReadComposition();
      await tester.runAsync(
        () => hydrateRuntimePackageForTests(environment: 'beta'),
      );
    }
  });

  test('Alpha 组合根选择 creator 与作者作品，Beta 不复用离线 adapter', () async {
    final client = GeneratedCloudOperationClient(
      const UnavailableCloudOperationExecutor(),
    );
    CloudOperationInvocationContext context(String _, String _) =>
        throw StateError('离线不得构造调用上下文');
    await hydrateRuntimePackageForTests(environment: 'alpha');
    installPublicMediaDelivery(BundledPublicMediaDelivery());
    installAlphaContentComposition();
    final container = ProviderContainer(
      overrides: sealedCloudBoundaryOverrides(),
    );
    try {
      expect(container.read(loginCapabilityFailureProvider), isNotNull);
      final profile = UserProductionComposition.generatedAdapter<ProfileQuery>(
        UserProductionAdapter.profileQuery,
        client: client,
        invocationContext: context,
      );
      final persona = UserProductionComposition.generatedAdapter<PersonaQuery>(
        UserProductionAdapter.personaQuery,
        client: client,
        invocationContext: context,
      );
      expect(profile, isA<BundledProfileQuery>());
      expect(persona, isA<BundledProfileQuery>());
      final facets = ContentProductionComposition.contentPostReaderFacets(
        client: client,
        invocationContext: (String _) => throw StateError('离线不得请求 Remote'),
        postCache: PostObjectCacheService(),
        querySnapshotStore: ContentQuerySnapshotStore(),
        currentCacheIdentity: () => null,
        userProfileCache: UserProfileCacheService(),
        telemetrySink: const SilentCacheTelemetrySink(),
      );
      expect(facets.authorPosts, isA<BundledContentPostReader>());
      expect(facets.detail, same(facets.authorPosts));
      final bundle = await OfflineContentBundle.load();
      final actualIds = <String>{};
      final expectedPosts = bundle
          .rows('posts')
          .map(
            (row) => ContentPostProjection.fromWire(
              row['projection']! as Map<String, Object?>,
            ),
          )
          .toList();
      for (final row in bundle.rows('creators')) {
        final creator = PersonaProfileView.fromWire(
          row['projection']! as Map<String, Object?>,
        );
        final homepage = await profile.getUserHomepageBundle(creator.personaId);
        expect(homepage.profile.displayName, creator.displayName);
        final expected = expectedPosts
            .where((post) => post.authorId == creator.personaId)
            .toList();
        final ids = <String>[];
        final seenCursors = <String>{};
        String? cursor;
        do {
          final page = await facets.authorPosts.listUserPosts(
            userId: creator.personaId,
            limit: 5,
            cursor: cursor,
          );
          for (final post in page.items) {
            expect(post.authorId, creator.personaId);
            expect(ids, isNot(contains(post.id)));
            expect(actualIds.add(post.id), isTrue);
            ids.add(post.id);
          }
          cursor = page.nextCursor;
          if (cursor != null) {
            expect(page.items, isNotEmpty);
            expect(seenCursors.add(cursor), isTrue);
          }
        } while (cursor != null);
        expect(ids, orderedEquals(expected.map((post) => post.postId)));
        expect(homepage.stats.postCount, expected.length);
        expect(creator.postCount, expected.length);
        if (expected.isEmpty) expect(ids, isEmpty);
      }
      expect(actualIds, expectedPosts.map((post) => post.postId).toSet());
    } finally {
      container.dispose();
      await hydrateRuntimePackageForTests(environment: 'beta');
      ContentProductionComposition.useRemoteReadComposition();
      UserProductionComposition.useRemoteReadComposition();
    }
    final remote = UserProductionComposition.generatedAdapter<ProfileQuery>(
      UserProductionAdapter.profileQuery,
      client: client,
      invocationContext: context,
    );
    expect(remote, isNot(isA<BundledProfileQuery>()));
    final onlineContainer = ProviderContainer(
      overrides: sealedCloudBoundaryOverrides(),
    );
    expect(onlineContainer.read(loginCapabilityFailureProvider), isNull);
    onlineContainer.dispose();
  });

  test('真实包内内容通过制品 pin 和现役 Dart 生成 decoder', () async {
    final bytes = await rootBundle.load(offlineContentManifestAssetPath);
    final raw = bytes.buffer.asUint8List(
      bytes.offsetInBytes,
      bytes.lengthInBytes,
    );
    expect('sha256:${sha256.convert(raw)}', offlineContentManifestDigest);
    final manifest = jsonDecode(utf8.decode(raw)) as Map<String, dynamic>;
    expect(manifest['schema'], 'quwoquan.offline_content_bundle');
    final posts = manifest['posts'] as List<dynamic>;
    final ids = <String>{};
    for (final value in posts) {
      final row = value as Map<String, dynamic>;
      final projection = ContentPostProjection.fromWire(row['projection']);
      final detail = ContentPostDetailSlice.fromWire(row['detail']);
      final card = ContentPostViewData.fromWire(projection);
      final detailView = ContentPostDetailPayload.fromWire(detail);
      expect(card.id, detailView.post.id);
      expect(card.type, detailView.post.type);
      expect(ids.add(card.id), isTrue);
      if (card.type == 'article') {
        expect(detail.articleMarkdown, isNotEmpty);
      }
    }
    expect(ids, hasLength(posts.length));
    for (final channel in manifest['channels'] as List<dynamic>) {
      final selected = (channel['orderedPostIds'] as List<dynamic>)
          .cast<String>();
      expect(selected.every(ids.contains), isTrue);
      if (channel['channelId'] == 'premium') expect(selected, isNotEmpty);
    }
    ContentAppConfig.fromWire(manifest['configuration']['content']);
    for (final creator in manifest['creators'] as List<dynamic>) {
      PersonaProfileView.fromWire(creator['projection']);
    }
    for (final homepage in manifest['homepages'] as List<dynamic>) {
      HomepageIntroduction.fromWire(homepage['projection']);
    }
  });

  test('Alpha 公开图片由实际包内字节解码，缺媒体拒绝且换文档不复用旧来源', () async {
    await hydrateRuntimePackageForTests(environment: 'alpha');
    installPublicMediaDelivery(BundledPublicMediaDelivery());
    installAlphaContentComposition();
    final offline = publicMediaDelivery;
    try {
      expect(offline.endpoints, isNull);
      final manifest = jsonDecode(
        await rootBundle.loadString(offlineContentManifestAssetPath),
      ) as Map<String, dynamic>;
      final media = (manifest['media'] as List<dynamic>)
          .cast<Map<String, dynamic>>();
      for (final row in media.where((row) => row['kind'] != 'video')) {
        final provider = offline.imageProvider(
          row['canonicalReference'] as String,
        );
        expect(provider, isA<BundledImageProvider>());
        final image = await _decodeImage(provider);
        expect(image.image.width, greaterThan(0));
        expect(image.image.height, greaterThan(0));
        image.dispose();
      }
      await expectLater(
        _decodeImage(offline.imageProvider('media/image/missing.png')),
        throwsA(isA<OfflineContentFailure>()),
      );
      await expectLater(
        offline.playableSources('media/video/missing.mp4'),
        throwsA(isA<OfflineContentFailure>()),
      );
      await hydrateRuntimePackageForTests(environment: 'beta');
      ContentProductionComposition.useRemoteReadComposition();
      UserProductionComposition.useRemoteReadComposition();
      final remote = publicMediaDelivery;
      expect(identical(remote, offline), isFalse);
      expect(remote.endpoints, isNotNull);
      expect(remote, isA<RemotePublicMediaDelivery>());
      expect(
        remote.candidates(
          'https://untrusted.invalid/image.png',
          MediaDeliveryKind.image,
        ),
        isEmpty,
      );
      await hydrateRuntimePackageForTests(environment: 'alpha');
      installPublicMediaDelivery(BundledPublicMediaDelivery());
      installAlphaContentComposition();
      expect(identical(publicMediaDelivery, offline), isFalse);
    } finally {
      await hydrateRuntimePackageForTests(environment: 'beta');
      ContentProductionComposition.useRemoteReadComposition();
      UserProductionComposition.useRemoteReadComposition();
    }
  });

  test('Alpha 视频物化来自完整快照并保持摘要，缺媒体不创建网络候选', () async {
    final directory = await Directory.systemTemp.createTemp(
      'qwq-offline-video-',
    );
    const channel = MethodChannel('plugins.flutter.io/path_provider');
    final messenger =
        TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    messenger.setMockMethodCallHandler(channel, (_) async => directory.path);
    await hydrateRuntimePackageForTests(environment: 'alpha');
    installPublicMediaDelivery(BundledPublicMediaDelivery());
    installAlphaContentComposition();
    try {
      final manifest = jsonDecode(
        await rootBundle.loadString(offlineContentManifestAssetPath),
      ) as Map<String, dynamic>;
      final video = (manifest['media'] as List<dynamic>)
          .cast<Map<String, dynamic>>()
          .firstWhere((row) => row['kind'] == 'video');
      final delivery = publicMediaDelivery;
      final sources = await delivery.playableSources(
        video['canonicalReference'] as String,
      );
      final handle = sources.single.createController();
      final path = Uri.parse(handle.controller.dataSource).toFilePath();
      addTearDown(handle.controller.dispose);
      expect(path, startsWith(directory.path));
      final bytes = await File(path).readAsBytes();
      expect(bytes.length, video['byteLength']);
      expect('sha256:${sha256.convert(bytes)}', video['sha256']);
      final repeated = (await delivery.playableSources(
        video['canonicalReference'] as String,
      )).single.createController();
      addTearDown(repeated.controller.dispose);
      expect(Uri.parse(repeated.controller.dataSource).toFilePath(), path);
      await File(path).writeAsBytes([0, 1, 2], flush: true);
      await expectLater(
        delivery.playableSources(video['canonicalReference'] as String),
        throwsA(isA<OfflineContentFailure>()),
      );
      // 仅删除测试私有物化文件，恢复仍从canonical真实字节重验物化。
      await File(path).delete();
      final repaired = (await delivery.playableSources(
        video['canonicalReference'] as String,
      )).single.createController();
      addTearDown(repaired.controller.dispose);
      expect(
        'sha256:${sha256.convert(await File(path).readAsBytes())}',
        video['sha256'],
      );
    } finally {
      messenger.setMockMethodCallHandler(channel, null);
      await hydrateRuntimePackageForTests(environment: 'beta');
      ContentProductionComposition.useRemoteReadComposition();
      UserProductionComposition.useRemoteReadComposition();
      await directory.delete(recursive: true);
    }
  });

  test('真实包内全部媒体均有完整字节，摘要及总量匹配', () async {
    final manifest = jsonDecode(
      await rootBundle.loadString(offlineContentManifestAssetPath),
    ) as Map<String, dynamic>;
    final media = manifest['media'] as List<dynamic>;
    var total = 0;
    for (final value in media) {
      final row = value as Map<String, dynamic>;
      final data = await rootBundle.load(row['assetPath'] as String);
      final bytes = data.buffer.asUint8List(
        data.offsetInBytes,
        data.lengthInBytes,
      );
      expect(bytes.length, row['byteLength']);
      expect('sha256:${sha256.convert(bytes)}', row['sha256']);
      total += bytes.length;
    }
    expect(media, isNotEmpty);
    expect(total, manifest['counts']['mediaBytes']);
  });
}

final class _ObservedStartupBridge implements StartupTimingsNativeBridge {
  @override
  Future<NativeStartupProcessSegments?> beginStartupAttempt(
    String attemptId,
  ) async => NativeStartupProcessSegments(
    startupAttemptId: attemptId,
    attemptKind: 'cold',
    deadlineOrigin: 'nativeProcess',
    elapsedSinceProcessStartMs: 1,
    elapsedSinceAttemptStartMs: 1,
  );
}

final class _MutableCanonicalAssets extends AssetBundle {
  String? corruptPath;
  String? missingPath;
  @override
  Future<ByteData> load(String key) async {
    if (key == missingPath) {
      throw FileSystemException('injected missing canonical media', key);
    }
    if (key == corruptPath) return ByteData(1);
    return ByteData.sublistView(await File(key).readAsBytes());
  }
}

final class _ObservedCodec implements ui.Codec {
  _ObservedCodec(this.delegate);
  final ui.Codec delegate;
  bool disposed = false;
  @override
  int get frameCount => delegate.frameCount;
  @override
  int get repetitionCount => delegate.repetitionCount;
  @override
  Future<ui.FrameInfo> getNextFrame() => delegate.getNextFrame();
  @override
  void dispose() {
    disposed = true;
    delegate.dispose();
  }
}

final class _CompositionLifetimeProbe extends StatefulWidget {
  const _CompositionLifetimeProbe({required this.onDispose});
  final VoidCallback onDispose;
  @override
  State<_CompositionLifetimeProbe> createState() =>
      _CompositionLifetimeProbeState();
}

final class _CompositionLifetimeProbeState
    extends State<_CompositionLifetimeProbe> {
  @override
  Widget build(BuildContext context) =>
      const MaterialApp(home: SizedBox.shrink());
  @override
  void dispose() {
    widget.onDispose();
    super.dispose();
  }
}

Future<ImageInfo> _decodeImage(ImageProvider<Object> provider) async {
  final stream = provider.resolve(ImageConfiguration.empty);
  final result = Completer<ImageInfo>();
  final listener = ImageStreamListener(
    (image, synchronous) {
      if (!result.isCompleted) result.complete(image);
    },
    onError: (Object error, StackTrace? stack) {
      if (!result.isCompleted) result.completeError(error, stack);
    },
  );
  stream.addListener(listener);
  try {
    return await result.future.timeout(const Duration(seconds: 10));
  } finally {
    stream.removeListener(listener);
  }
}
