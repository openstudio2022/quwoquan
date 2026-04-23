import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/models/content_app_config_wire.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/services/app_content_repository.dart';

class _RuntimeConfigRepository extends MockContentRepository {
  _RuntimeConfigRepository(this._config);

  Map<String, dynamic> _config;

  void replace(Map<String, dynamic> next) {
    _config = next;
  }

  @override
  Future<ContentAppConfigWire> getAppConfig() async =>
      ContentAppConfigWire.fromResponseObject(_config);
}

void main() {
  test('mock mode 会刷新出文章阅读相关 runtime flags', () async {
    final container = ProviderContainer();
    addTearDown(container.dispose);

    container.read(contentRuntimeConfigProvider);
    await Future<void>.delayed(const Duration(milliseconds: 1));
    await Future<void>.delayed(const Duration(milliseconds: 1));
    final state = container.read(contentRuntimeConfigProvider);

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
        contentRepositoryProvider.overrideWithValue(
          _RuntimeConfigRepository({
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
      ],
    );
    addTearDown(container.dispose);

    container
        .read(appDataSourceModeProvider.notifier)
        .setMode(AppDataSourceMode.remote);
    container.read(contentRuntimeConfigProvider);
    await Future<void>.delayed(const Duration(milliseconds: 1));
    await Future<void>.delayed(const Duration(milliseconds: 1));

    final state = container.read(contentRuntimeConfigProvider);

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
    final repo = _RuntimeConfigRepository({
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
    });
    final container = ProviderContainer(
      overrides: [contentRepositoryProvider.overrideWithValue(repo)],
    );
    addTearDown(container.dispose);

    container
        .read(appDataSourceModeProvider.notifier)
        .setMode(AppDataSourceMode.remote);
    container.read(contentRuntimeConfigProvider);
    await Future<void>.delayed(const Duration(milliseconds: 1));
    await Future<void>.delayed(const Duration(milliseconds: 1));

    repo.replace({
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
    });

    await container.read(contentRuntimeConfigProvider.notifier).refresh();
    final state = container.read(contentRuntimeConfigProvider);

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
        contentRepositoryProvider.overrideWithValue(
          _RuntimeConfigRepository({
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
      ],
    );
    addTearDown(container.dispose);

    container
        .read(appDataSourceModeProvider.notifier)
        .setMode(AppDataSourceMode.remote);
    container.read(contentRuntimeConfigProvider);
    await Future<void>.delayed(const Duration(milliseconds: 1));
    await Future<void>.delayed(const Duration(milliseconds: 1));

    final state = container.read(contentRuntimeConfigProvider);

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

  test('remote app config 可关闭 persona management 与 sync flags', () async {
    final container = ProviderContainer(
      overrides: [
        contentRepositoryProvider.overrideWithValue(
          _RuntimeConfigRepository({
            'content': {
              'feature_flags': {
                'ops.user.persona_management_v1': false,
                'ops.user.persona_profile_sync_v1': false,
              },
            },
          }),
        ),
      ],
    );
    addTearDown(container.dispose);

    container
        .read(appDataSourceModeProvider.notifier)
        .setMode(AppDataSourceMode.remote);
    container.read(contentRuntimeConfigProvider);
    await Future<void>.delayed(const Duration(milliseconds: 1));
    await Future<void>.delayed(const Duration(milliseconds: 1));

    expect(container.read(personaManagementFeatureFlagProvider), isFalse);
    expect(container.read(personaProfileSyncFeatureFlagProvider), isFalse);
  });
}
