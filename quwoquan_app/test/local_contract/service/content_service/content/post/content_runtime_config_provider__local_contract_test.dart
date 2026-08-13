import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/content_repository_contract.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import '../../../../../support/service/content_service/content/post/content_facet_overrides.dart';
import '../../../../../support/service/content_service/content/post/content_post_typed_doubles.dart';
import '../../../../../support/service/content_service/content/post/test_content_app_config.dart';

class _RuntimeConfigRepository implements ContentConfigRepository {
  _RuntimeConfigRepository(this._config);

  AppConfigSlice _config;

  void replace(AppConfigSlice next) {
    _config = next;
  }

  @override
  Future<AppConfigSlice> getAppConfig() async => _config;

  @override
  bool get requiresResolvedPersonaForMutations => false;
}

AppConfigSlice _remoteConfig(Map<String, Object?> root) {
  final rawContent = root['content'];
  return testAppConfigSlice(
    content: rawContent is Map<String, Object?>
        ? rawContent
        : Map<String, Object?>.from(rawContent! as Map),
  );
}

ContentRuntimeConfigState _effectiveState(ProviderContainer container) {
  return container.read(appRemoteConfigProvider).pending ??
      container.read(contentRuntimeConfigProvider);
}

void main() {
  test('alpha runner 显式配置会启用内容 story runtime flags', () {
    final state = buildAlphaContentRuntimeConfigDefaults();

    expect(state.isEnabled('enable_create_action_entry'), isTrue);
    expect(state.isEnabled('enable_unified_create_editor'), isTrue);
    expect(state.isEnabled('enable_identity_based_surfaces'), isTrue);
    expect(state.isEnabled('enable_identity_share_template'), isTrue);
    expect(state.isEnabled('enable_article_book_reader'), isTrue);
    expect(state.isEnabled('enable_article_page_curl'), isTrue);
    expect(state.isEnabled('enable_assistant_content_identity_index'), isTrue);
  });

  test('remote app config 覆盖 feature flags 与 canary matrix', () async {
    final container = ProviderContainer(
      overrides: [
        ...mockContentFacetOverrides(
          store: InMemoryContentPostStore(),
          configRepository: _RuntimeConfigRepository(
            _remoteConfig({
              'content': {
                'feature_flags': {
                  'enable_create_action_entry': false,
                  'enable_unified_create_editor': true,
                  'enable_identity_based_surfaces': false,
                  'enable_identity_share_template': true,
                  'enable_article_book_reader': false,
                  'enable_article_page_curl': true,
                  'enable_assistant_content_identity_index': true,
                },
                'gray_release': {
                  'experiment_bucket': 'rollout_20',
                  'current_stage': '20%',
                  'canary_matrix': [
                    {'stage': '5%', 'rolloutPercent': 5},
                    {'stage': '20%', 'rolloutPercent': 20},
                    {'stage': '50%', 'rolloutPercent': 50},
                    {'stage': '100%', 'rolloutPercent': 100},
                  ],
                },
              },
            }),
          ),
        ),
      ],
    );
    addTearDown(container.dispose);

    container.read(contentRuntimeConfigProvider);
    await Future<void>.delayed(const Duration(milliseconds: 1));
    await Future<void>.delayed(const Duration(milliseconds: 1));

    final state = _effectiveState(container);

    expect(state.isEnabled('enable_create_action_entry'), isFalse);
    expect(state.isEnabled('enable_unified_create_editor'), isTrue);
    expect(state.isEnabled('enable_identity_based_surfaces'), isFalse);
    expect(state.isEnabled('enable_article_book_reader'), isFalse);
    expect(state.isEnabled('enable_article_page_curl'), isTrue);
    expect(state.experimentBucket, 'rollout_20');
    expect(state.currentCanaryStage, '20%');
    expect(state.canaryStages.map((stage) => stage.stage).toList(), <String>[
      '5%',
      '20%',
      '50%',
      '100%',
    ]);
    expect(state.clientStateSync.flushDelay, const Duration(seconds: 10));
    expect(state.clientStateSync.retryDelay, const Duration(minutes: 5));
    expect(state.clientStateSync.maxBatchSize, 20);
    expect(state.clientStateSync.maxPendingAge, const Duration(hours: 72));
    expect(state.clientStateSync.flushOnForegroundResume, isTrue);
    expect(state.clientStateSync.flushOnNetworkRecovered, isTrue);
  });

  test('refresh 会重新拉取远端 runtime config', () async {
    final repo = _RuntimeConfigRepository(
      _remoteConfig({
        'content': {
          'feature_flags': {
            'enable_identity_share_template': true,
            'enable_assistant_content_identity_index': true,
          },
          'gray_release': {
            'experiment_bucket': 'rollout_20',
            'current_stage': '20%',
            'canary_matrix': [
              {'stage': '5%', 'rolloutPercent': 5},
              {'stage': '20%', 'rolloutPercent': 20},
            ],
          },
        },
      }),
    );
    final container = ProviderContainer(
      overrides: [
        ...mockContentFacetOverrides(
          store: InMemoryContentPostStore(),
          configRepository: repo,
        ),
      ],
    );
    addTearDown(container.dispose);

    container.read(contentRuntimeConfigProvider);
    await Future<void>.delayed(const Duration(milliseconds: 1));
    await Future<void>.delayed(const Duration(milliseconds: 1));

    repo.replace(
      _remoteConfig({
        'content': {
          'feature_flags': {
            'enable_identity_share_template': false,
            'enable_assistant_content_identity_index': false,
          },
          'gray_release': {
            'experiment_bucket': 'rollout_50',
            'current_stage': '50%',
            'canary_matrix': [
              {'stage': '5%', 'rolloutPercent': 5},
              {'stage': '20%', 'rolloutPercent': 20},
              {'stage': '50%', 'rolloutPercent': 50},
            ],
          },
        },
      }),
    );

    await container.read(appRemoteConfigProvider.notifier).refresh();
    final state = _effectiveState(container);

    expect(state.isEnabled('enable_identity_share_template'), isFalse);
    expect(state.isEnabled('enable_assistant_content_identity_index'), isFalse);
    expect(state.experimentBucket, 'rollout_50');
    expect(state.currentCanaryStage, '50%');
    expect(state.canaryStages.map((stage) => stage.stage).toList(), <String>[
      '5%',
      '20%',
      '50%',
    ]);
  });

  test('remote app config 覆盖 client state sync 参数', () async {
    final container = ProviderContainer(
      overrides: [
        ...mockContentFacetOverrides(
          store: InMemoryContentPostStore(),
          configRepository: _RuntimeConfigRepository(
            _remoteConfig({
              'content': {
                'client_state_sync': {
                  'flush_delay_sec': 15,
                  'retry_delay_sec': 90,
                  'max_batch_size': 8,
                  'max_pending_age_sec': 3600,
                  'flush_on_foreground_resume': false,
                  'flush_on_network_recovered': true,
                },
              },
            }),
          ),
        ),
      ],
    );
    addTearDown(container.dispose);

    container.read(contentRuntimeConfigProvider);
    await Future<void>.delayed(const Duration(milliseconds: 1));
    await Future<void>.delayed(const Duration(milliseconds: 1));

    final state = _effectiveState(container);

    expect(state.clientStateSync.flushDelay, const Duration(seconds: 15));
    expect(state.clientStateSync.retryDelay, const Duration(seconds: 90));
    expect(state.clientStateSync.maxBatchSize, 8);
    expect(state.clientStateSync.maxPendingAge, const Duration(hours: 1));
    expect(state.clientStateSync.flushOnForegroundResume, isFalse);
    expect(state.clientStateSync.flushOnNetworkRecovered, isTrue);
  });

  test('persona feature flags 默认开启以保持现有管理面可用', () async {
    final container = ProviderContainer();
    addTearDown(container.dispose);

    container.read(contentRuntimeConfigProvider);
    await Future<void>.delayed(const Duration(milliseconds: 1));
    await Future<void>.delayed(const Duration(milliseconds: 1));

    expect(container.read(personaManagementFeatureFlagProvider), isTrue);
    expect(container.read(personaProfileSyncFeatureFlagProvider), isTrue);
  });

  test('Content config 拒绝跨域 persona feature flag', () {
    expect(
      () => _remoteConfig(<String, Object?>{
        'content': <String, Object?>{
          'feature_flags': <String, Object?>{
            'ops.user.persona_management': false,
            'ops.user.persona_profile_sync': false,
          },
        },
      }),
      throwsFormatException,
    );
  });
}
