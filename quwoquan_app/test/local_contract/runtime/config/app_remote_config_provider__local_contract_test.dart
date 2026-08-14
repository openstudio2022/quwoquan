// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/app-remote-config/spec.md#gwt-001
// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/app-remote-config/spec.md#gwt-001.t1
// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/app-remote-config/spec.md#gwt-001.t2
// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/app-remote-config/spec.md#gwt-001.t3
// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/app-remote-config/spec.md#gwt-002
// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/app-remote-config/spec.md#gwt-002.t1
// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/app-remote-config/spec.md#gwt-002.t2
// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/app-remote-config/spec.md#gwt-002.t3
// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/app-remote-config/spec.md#gwt-003
// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/app-remote-config/spec.md#gwt-003.t1
// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/app-remote-config/spec.md#gwt-003.t2
// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/app-remote-config/spec.md#gwt-004
// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/app-remote-config/spec.md#gwt-004.t4
import 'dart:io';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/config/app_remote_config_snapshot.dart';
import 'package:quwoquan_app/runtime/config/app_remote_config_store.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/content_repository_contract.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/generated/content_ui_config.g.dart';
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/application/public/intersection_display_config.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import '../../../support/service/content_service/content/post/content_facet_overrides.dart';
import '../../../support/service/content_service/content/post/content_post_typed_doubles.dart';
import '../../../support/service/content_service/content/post/test_content_app_config.dart';

class _ConfigRepo implements ContentConfigRepository {
  _ConfigRepo(this.config);

  final AppConfigSlice config;

  @override
  Future<AppConfigSlice> getAppConfig() async => config;

  @override
  bool get requiresResolvedPersonaForMutations => false;
}

class _ThrowingConfigRepo implements ContentConfigRepository {
  @override
  Future<AppConfigSlice> getAppConfig() async {
    throw const FormatException('generated app config decoder rejected input');
  }

  @override
  bool get requiresResolvedPersonaForMutations => false;
}

final class _MemoryAppRemoteConfigStore implements AppRemoteConfigStore {
  AppRemoteConfigSnapshot? activeSnapshot;

  @override
  Future<AppRemoteConfigSnapshot?> readActiveSnapshot() async => activeSnapshot;

  @override
  Future<void> writeActiveSnapshot(AppRemoteConfigSnapshot snapshot) async {
    activeSnapshot = snapshot;
  }
}

Map<String, Object?> _signedRemoteConfig(
  Map<String, Object?> content, {
  String activationPolicy = 'next_session',
}) {
  return testSignedAppConfigRoot(
    content: content,
    defaultActivation: activationPolicy,
  );
}

void main() {
  test('default active remains usable before remote fetch completes', () {
    final store = _MemoryAppRemoteConfigStore();
    final container = ProviderContainer(
      overrides: [appRemoteConfigStoreProvider.overrideWithValue(store)],
    );
    addTearDown(container.dispose);

    final state = container.read(appRemoteConfigProvider);

    expect(state.active.configHash, isNull);
    expect(state.active.comment.maxLength, 500);
    expect(state.active.comment.replyExpandPageSize, 10);
    // 首帧同步可读：首页频道、feature flag 都来自 codegen defaults。
    expect(state.active.source, AppRemoteConfigSource.defaults);
    expect(state.active.homeChannels, ContentUIConfig.homeChannels);
    expect(state.active.featureFlags, ContentUIConfig.featureFlags);
  });

  test('normal remote config is stored as pending next session', () async {
    final store = _MemoryAppRemoteConfigStore();
    final container = ProviderContainer(
      overrides: [
        appRemoteConfigStoreProvider.overrideWithValue(store),
        ...mockContentFacetOverrides(
          store: InMemoryContentPostStore(),
          configRepository: _ConfigRepo(
            AppConfigSlice.fromWire(
              _signedRemoteConfig({
                'comment': {
                  'max_length': 300,
                  'reply_preview_count': 2,
                  'reply_expand_page_size': 5,
                  'attachment': {'max_images': 1},
                },
                'home_channels': [
                  {'id': 'ops_takeover_channel', 'order': 1},
                ],
              }),
            ),
          ),
        ),
      ],
    );
    addTearDown(container.dispose);

    await container.read(appRemoteConfigProvider.notifier).refresh();
    final state = container.read(appRemoteConfigProvider);

    expect(state.active.configHash, isNull);
    expect(state.pending?.configHash, startsWith('sha256:'));
    expect(state.pending?.comment.maxLength, 300);
    expect(state.pending?.comment.replyPreviewCount, 2);
    expect(state.pending?.comment.replyExpandPageSize, 5);
    expect(store.activeSnapshot?.configHash, state.pending?.configHash);
    // 当前会话首页频道结构不跳变：新频道结构只进入 pending。
    expect(state.active.homeChannels, ContentUIConfig.homeChannels);
    expect(
      state.pending?.homeChannels.map((channel) => channel.id),
      <String>['ops_takeover_channel'],
    );
  });

  test('startup activates the last-known-good snapshot from disk', () async {
    final lkg = AppRemoteConfigSnapshot.fromRoot(
      _signedRemoteConfig({
        'comment': {
          'max_length': 320,
          'reply_preview_count': 2,
          'reply_expand_page_size': 5,
          'attachment': {'max_images': 1},
        },
      }),
    );
    final store = _MemoryAppRemoteConfigStore()..activeSnapshot = lkg;
    final container = ProviderContainer(
      overrides: [
        appRemoteConfigStoreProvider.overrideWithValue(store),
        ...mockContentFacetOverrides(
          store: InMemoryContentPostStore(),
          // 远端不可用也不能阻止 LKG 激活。
          configRepository: _ThrowingConfigRepo(),
        ),
      ],
    );
    addTearDown(container.dispose);

    container.read(appRemoteConfigProvider);
    await pumpEventQueue();
    final state = container.read(appRemoteConfigProvider);

    expect(state.active.configHash, lkg.configHash);
    expect(state.active.comment.maxLength, 320);
    expect(state.isHydrating, isFalse);
  });

  test(
    'immediate policy activates kill-switch style payload in current session',
    () async {
      final store = _MemoryAppRemoteConfigStore();
      final container = ProviderContainer(
        overrides: [
          appRemoteConfigStoreProvider.overrideWithValue(store),
          ...mockContentFacetOverrides(
            store: InMemoryContentPostStore(),
            configRepository: _ConfigRepo(
              AppConfigSlice.fromWire(
                _signedRemoteConfig({
                  'feature_flags': {'enable_article_book_reader': false},
                }, activationPolicy: 'immediate'),
              ),
            ),
          ),
        ],
      );
      addTearDown(container.dispose);

      await container.read(appRemoteConfigProvider.notifier).refresh();
      final state = container.read(appRemoteConfigProvider);

      expect(state.pending, isNull);
      expect(state.active.configHash, startsWith('sha256:'));
      expect(state.active.isEnabled('enable_article_book_reader'), isFalse);
      expect(store.activeSnapshot?.configHash, state.active.configHash);
    },
  );

  test('components read config through the contentRuntime facade', () async {
    final store = _MemoryAppRemoteConfigStore();
    final container = ProviderContainer(
      overrides: [
        appRemoteConfigStoreProvider.overrideWithValue(store),
        ...mockContentFacetOverrides(
          store: InMemoryContentPostStore(),
          configRepository: _ConfigRepo(
            AppConfigSlice.fromWire(
              _signedRemoteConfig({
                'feature_flags': {'enable_article_book_reader': false},
              }, activationPolicy: 'immediate'),
            ),
          ),
        ),
      ],
    );
    addTearDown(container.dispose);

    await container.read(appRemoteConfigProvider.notifier).refresh();
    final active = container.read(appRemoteConfigProvider).active;

    // facade provider 与 active 同源，不存在第二条配置读取轨道。
    expect(container.read(contentRuntimeConfigProvider), same(active));
    expect(container.read(commentRemoteConfigProvider), same(active.comment));
    expect(container.read(homeChannelsProvider), same(active.homeChannels));
    expect(
      container.read(contentFeatureFlagProvider('enable_article_book_reader')),
      isFalse,
    );
  });

  test('components must not fetch /config/app outside the facade', () {
    const allowedCaller = 'lib/runtime/di/app_providers_content_runtime.dart';
    final offenders = <String>[];
    for (final entity in Directory('lib').listSync(recursive: true)) {
      if (entity is! File || !entity.path.endsWith('.dart')) {
        continue;
      }
      final normalized = entity.path.replaceAll(r'\', '/');
      if (normalized == allowedCaller) {
        continue;
      }
      if (entity.readAsStringSync().contains('.getAppConfig(')) {
        offenders.add(normalized);
      }
    }
    expect(
      offenders,
      isEmpty,
      reason: '组件不得直接重复拉取 /config/app；'
          '唯一调用点是 $allowedCaller 的 AppRemoteConfigNotifier',
    );
  });

  test('retired packageVersion is rejected instead of dual-read', () {
    final root = _signedRemoteConfig(const <String, dynamic>{});
    root['packageVersion'] = 'retired';

    expect(() => AppRemoteConfigSnapshot.fromRoot(root), throwsFormatException);
  });

  test('configHash must match the canonical payload', () {
    final root = _signedRemoteConfig(const <String, dynamic>{});
    root['content'] = <String, dynamic>{
      'feature_flags': <String, bool>{'tampered': true},
    };

    expect(() => AppRemoteConfigSnapshot.fromRoot(root), throwsFormatException);
  });

  test('disk cache persists the same canonical wire without an envelope', () {
    final root = _signedRemoteConfig(const <String, dynamic>{});
    final network = AppRemoteConfigSnapshot.fromRoot(root);
    final persisted = network.toPersistedMap();
    final disk = AppRemoteConfigSnapshot.fromPersistedMap(persisted);

    expect(persisted.containsKey('wireRoot'), isFalse);
    expect(disk.configHash, network.configHash);
    expect(disk.wire.toWire(), network.wire.toWire());
  });

  test('retired disk wrapper is rejected instead of migrated', () {
    final root = _signedRemoteConfig(const <String, dynamic>{});

    expect(
      () => AppRemoteConfigSnapshot.fromPersistedMap(<String, dynamic>{
        'wireRoot': root,
      }),
      throwsFormatException,
    );
  });

  test('wire metadata accepts one exact JSON type shape', () {
    final stringTtl = _signedRemoteConfig(const <String, dynamic>{});
    stringTtl['maxAgeSec'] = '60';
    stringTtl['configHash'] = AppRemoteConfigSnapshot.calculateConfigHash(
      stringTtl,
    );

    expect(
      () => AppRemoteConfigSnapshot.fromRoot(stringTtl),
      throwsFormatException,
    );
  });

  test('intersection config only reads content.intersection', () {
    expect(
      () => ContentAppConfig.fromWire(<String, Object?>{
        'feature_flags': const <String, Object?>{},
        'gray_release': const <String, Object?>{
          'experiment_bucket': 'control',
          'current_stage': 'control',
          'canary_matrix': <Object?>[],
        },
        'intersection': const <String, Object?>{
          'inlineExpandCount': 9,
          'maxCandidateWindow': 99,
        },
      }),
      throwsFormatException,
    );
    final canonical = IntersectionDisplayConfig.fromAppConfig(
      ContentAppConfig.fromWire(<String, Object?>{
        'feature_flags': const <String, Object?>{},
        'gray_release': const <String, Object?>{
          'experiment_bucket': 'control',
          'current_stage': 'control',
          'canary_matrix': <Object?>[],
        },
        'intersection': const <String, Object?>{
          'inline_expand_count': 4,
          'max_candidate_window': 24,
        },
      }),
    );
    expect(canonical.inlineExpandCount, 4);
    expect(canonical.maxCandidateWindow, 24);
  });

  test('invalid nested JSON types reject the whole remote snapshot', () async {
    final store = _MemoryAppRemoteConfigStore();
    final container = ProviderContainer(
      overrides: [
        appRemoteConfigStoreProvider.overrideWithValue(store),
        ...mockContentFacetOverrides(
          store: InMemoryContentPostStore(),
          configRepository: _ThrowingConfigRepo(),
        ),
      ],
    );
    addTearDown(container.dispose);

    await container.read(appRemoteConfigProvider.notifier).refresh();
    final state = container.read(appRemoteConfigProvider);

    expect(state.active.source, AppRemoteConfigSource.defaults);
    expect(state.active.configHash, isNull);
    expect(state.pending, isNull);
    expect(state.errorMessage, isNotNull);
    expect(store.activeSnapshot, isNull);
  });
}
