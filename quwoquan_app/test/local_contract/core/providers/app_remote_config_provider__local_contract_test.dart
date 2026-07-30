// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/app-remote-config/spec.md#gwt-001
// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/app-remote-config/spec.md#gwt-002
// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/app-remote-config/spec.md#gwt-003
// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/app-remote-config/spec.md#gwt-004
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/models/app_remote_config_snapshot.dart';
import 'package:quwoquan_app/cloud/runtime/models/content_app_config_wire.dart';
import 'package:quwoquan_app/cloud/runtime/models/intersection_display_config.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import '../../../support/cloud_services/content_facet_overrides.dart';
import '../../../support/cloud_services/content/mock_content_repository.dart';

class _ConfigRepo extends MockContentRepository {
  _ConfigRepo(this.config);

  final Map<String, dynamic> config;

  @override
  Future<ContentAppConfigWire> getAppConfig() async =>
      ContentAppConfigWire.fromResponseObject(config);
}

Map<String, dynamic> _signedRemoteConfig(
  Map<String, dynamic> content, {
  String activationPolicy = 'next_session',
}) {
  final root = <String, dynamic>{
    'schema': AppRemoteConfigSnapshot.canonicalSchema,
    'fetchedAt': '2026-07-29T00:00:00Z',
    'maxAgeSec': 60,
    'activationPolicy': <String, String>{'default': activationPolicy},
    'content': content,
  };
  root['configHash'] = AppRemoteConfigSnapshot.calculateConfigHash(root);
  return root;
}

void main() {
  test('default active remains usable before remote fetch completes', () {
    final container = ProviderContainer();
    addTearDown(container.dispose);

    final state = container.read(appRemoteConfigProvider);

    expect(state.active.configHash, isNull);
    expect(state.active.comment.maxLength, 500);
    expect(state.active.comment.replyExpandPageSize, 10);
  });

  test('normal remote config is stored as pending next session', () async {
    final container = ProviderContainer(
      overrides: [
        ...mockContentFacetOverrides(
          _ConfigRepo(
            _signedRemoteConfig({
              'comment': {
                'max_length': 300,
                'reply_preview_count': 2,
                'reply_expand_page_size': 5,
                'attachment': {'max_images': 1},
              },
            }),
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
  });

  test(
    'immediate policy activates kill-switch style payload in current session',
    () async {
      final container = ProviderContainer(
        overrides: [
          ...mockContentFacetOverrides(
            _ConfigRepo(
              _signedRemoteConfig({
                'feature_flags': {'enable_article_book_reader': false},
              }, activationPolicy: 'immediate'),
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
    },
  );

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
    expect(disk.wireRoot, network.wireRoot);
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
    final retiredRootShape = IntersectionDisplayConfig.fromAppConfigRoot(
      <String, Object?>{
        'intersection': <String, Object?>{
          'inlineExpandCount': 9,
          'maxCandidateWindow': 99,
        },
      },
    );

    expect(
      retiredRootShape.inlineExpandCount,
      IntersectionDisplayConfig.defaultInlineExpandCount,
    );
    expect(
      retiredRootShape.maxCandidateWindow,
      IntersectionDisplayConfig.defaultMaxCandidateWindow,
    );

    final canonical = IntersectionDisplayConfig.fromAppConfigRoot(
      <String, Object?>{
        'content': <String, Object?>{
          'intersection': <String, Object?>{
            'inline_expand_count': 4,
            'max_candidate_window': 24,
          },
        },
      },
    );
    expect(canonical.inlineExpandCount, 4);
    expect(canonical.maxCandidateWindow, 24);

    final retiredKeyShape = IntersectionDisplayConfig.fromAppConfigRoot(
      <String, Object?>{
        'content': <String, Object?>{
          'intersection': <String, Object?>{
            'inlineExpandCount': 9,
            'maxCandidateWindow': 99,
          },
        },
      },
    );
    expect(
      retiredKeyShape.inlineExpandCount,
      IntersectionDisplayConfig.defaultInlineExpandCount,
    );
    expect(
      retiredKeyShape.maxCandidateWindow,
      IntersectionDisplayConfig.defaultMaxCandidateWindow,
    );
  });

  test('invalid nested JSON types reject the whole remote snapshot', () async {
    final container = ProviderContainer(
      overrides: [
        ...mockContentFacetOverrides(
          _ConfigRepo(
            _signedRemoteConfig({
              'gray_release': <String, Object?>{
                'canary_matrix': <Object?>[
                  <String, Object?>{'stage': '5%', 'rolloutPercent': '5'},
                ],
              },
            }),
          ),
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
  });
}
