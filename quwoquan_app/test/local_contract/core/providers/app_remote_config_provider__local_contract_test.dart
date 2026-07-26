// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/app-remote-config/spec.md#gwt-001
// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/app-remote-config/spec.md#gwt-002
// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/app-remote-config/spec.md#gwt-003
// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/app-remote-config/spec.md#gwt-004
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/models/content_app_config_wire.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/di/app_data_source_mode.dart';
import '../../../support/cloud_services/content_facet_overrides.dart';
import '../../../support/cloud_services/content/mock_content_repository.dart';

class _ConfigRepo extends MockContentRepository {
  _ConfigRepo(this.config);

  final Map<String, dynamic> config;

  @override
  Future<ContentAppConfigWire> getAppConfig() async =>
      ContentAppConfigWire.fromResponseObject(config);
}

void main() {
  test('default active remains usable before remote fetch completes', () {
    final container = ProviderContainer();
    addTearDown(container.dispose);

    final state = container.read(appRemoteConfigProvider);

    expect(state.active.packageVersion, 'embedded-defaults');
    expect(state.active.comment.maxLength, 500);
    expect(state.active.comment.replyExpandPageSize, 10);
  });

  test('normal remote config is stored as pending next session', () async {
    final container = ProviderContainer(
      overrides: [
        ...mockContentFacetOverrides(
          _ConfigRepo({
            'schema': 'app_remote_config',
            'packageVersion': 'cfg_test_1',
            'configHash': 'sha256:test1',
            'maxAgeSec': 60,
            'activationPolicy': {'default': 'next_session'},
            'content': {
              'comment': {
                'max_length': 300,
                'reply_preview_count': 2,
                'reply_expand_page_size': 5,
                'attachment': {'max_images': 1},
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

    await container.read(appRemoteConfigProvider.notifier).refresh();
    final state = container.read(appRemoteConfigProvider);

    expect(state.active.packageVersion, 'embedded-defaults');
    expect(state.pending?.packageVersion, 'cfg_test_1');
    expect(state.pending?.comment.maxLength, 300);
    expect(state.pending?.comment.replyPreviewCount, 2);
    expect(state.pending?.comment.replyExpandPageSize, 5);
  });

  test(
    'immediate policy activates kill-switch style payload in current session',
    () async {
      final container = ProviderContainer(
        overrides: [
          ...mockContentFacetOverrides(
            _ConfigRepo({
              'schema': 'app_remote_config',
              'packageVersion': 'cfg_kill_switch',
              'configHash': 'sha256:kill',
              'activationPolicy': {'default': 'immediate'},
              'content': {
                'feature_flags': {'enable_article_book_reader': false},
              },
            }),
          ),
        ],
      );
      addTearDown(container.dispose);
      container
          .read(appDataSourceModeProvider.notifier)
          .setMode(AppDataSourceMode.remote);

      await container.read(appRemoteConfigProvider.notifier).refresh();
      final state = container.read(appRemoteConfigProvider);

      expect(state.pending, isNull);
      expect(state.active.packageVersion, 'cfg_kill_switch');
      expect(state.active.isEnabled('enable_article_book_reader'), isFalse);
    },
  );
}
