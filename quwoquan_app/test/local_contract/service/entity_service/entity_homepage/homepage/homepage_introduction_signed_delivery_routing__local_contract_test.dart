// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-016

import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/design_system/media/app_media_image.dart';
import 'package:quwoquan_app/design_system/media/app_cached_network_image.dart'
    show appImageLoadErrorKey;
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart' show MediaText;
import 'package:quwoquan_app/service/content_service/media/original_access_quota/presentation/media_delivery_failure_state.dart';
import 'package:quwoquan_app/runtime/di/app_providers_entity_extras.dart'
    show homepageIntroductionRepositoryProvider;
import 'package:quwoquan_app/runtime/di/signed_media_delivery_dependencies.dart';
import 'package:quwoquan_app/runtime/observability/trackers/journey_event_tracker.dart';
import 'package:quwoquan_app/runtime/transport/media/media_delivery_reference.dart'
    show MediaDeliveryKind;
import 'package:quwoquan_app/service/content_service/media/original_access_quota/application/signed_media_delivery_coordinator.dart';
import 'package:quwoquan_app/service/content_service/media/original_access_quota/presentation/signed_grant_image.dart';
import 'package:quwoquan_app/service/content_service/media/original_access_quota/application/original_access_quota_gateway.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/application/homepage_introduction_repository.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/presentation/homepage_introduction_page.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show
        CloudOperationCancellationSignal,
        HomepageIntroduction,
        HomepageIntroductionAsset,
        HomepageIntroductionSection,
        MediaDeliveryAccessMode,
        MediaOriginalAccessGrant,
        RequestContentMediaOriginalAccessCommand;

import '../../../../../support/runtime/observability/recording_app_telemetry_recorder.dart';

/// 对象级 typed double：grant 兑换永挂起，让 SignedGrantImage 停在占位态。
/// 接线测试只断言「typed 声明分流到桥接原子」，不消费兑换结果。
final class _HangingOriginalAccessGateway
    implements OriginalAccessQuotaGateway {
  final Completer<MediaOriginalAccessGrant> _never =
      Completer<MediaOriginalAccessGrant>();

  @override
  Future<MediaOriginalAccessGrant> requestOriginalAccess(
    RequestContentMediaOriginalAccessCommand command,
  ) => _never.future;
}

final class _FailingOriginalAccessGateway
    implements OriginalAccessQuotaGateway {
  int attempts = 0;

  @override
  Future<MediaOriginalAccessGrant> requestOriginalAccess(
    RequestContentMediaOriginalAccessCommand command,
  ) async {
    attempts += 1;
    throw StateError('signed homepage media unavailable');
  }
}

class _IntroRepository implements HomepageIntroductionRepository {
  _IntroRepository(this.introduction);

  final HomepageIntroduction introduction;

  @override
  Future<HomepageIntroduction?> getHomepageIntroduction(
    String homepageId, {
    CloudOperationCancellationSignal? cancellation,
  }) async => introduction;
}

Widget _host(
  HomepageIntroduction introduction, {
  OriginalAccessQuotaGateway? gateway,
}) {
  return ProviderScope(
    overrides: [
      homepageIntroductionRepositoryProvider.overrideWithValue(
        _IntroRepository(introduction),
      ),
      signedMediaDeliveryCoordinatorProvider.overrideWithValue(
        SignedMediaDeliveryCoordinator(
          gateway: gateway ?? _HangingOriginalAccessGateway(),
        ),
      ),
    ],
    child: CupertinoApp(
      home: HomepageIntroductionPage(
        homepageId: 'homepage_sight_signed_routing',
        journeyTracker: JourneyEventTracker(
          telemetryReporter: RecordingAppTelemetryRecorder(),
        ),
      ),
    ),
  );
}

/// 最小非空正文段：introduction 页在无任何 section 时进入空态、不渲染 hero，
/// 接线用例需要页面进入正常内容态。
const List<HomepageIntroductionSection> _minimalBodySections =
    <HomepageIntroductionSection>[
      HomepageIntroductionSection(
        kind: 'body',
        title: '概况',
        bodyMarkdown: '接线验证正文段落。',
        assets: <HomepageIntroductionAsset>[],
        timelineItems: [],
      ),
    ];

HomepageIntroduction _introduction({
  String? coverUrl,
  String? coverAssetId,
  MediaDeliveryAccessMode? coverAccessMode,
  List<HomepageIntroductionSection> sections = _minimalBodySections,
}) {
  return HomepageIntroduction(
    homepageId: 'homepage_sight_signed_routing',
    displayName: '签名交付景区',
    homepageType: 'sight',
    coverUrl: coverUrl,
    coverAssetId: coverAssetId,
    coverAccessMode: coverAccessMode,
    summary: '私有媒体交付接线验证摘要',
    sections: sections,
    relatedObjects: const [],
    sourceUrls: const <String>[],
    updatedAt: '2026-08-20T00:00:00Z',
  );
}

void main() {
  testWidgets('signedGrant hero cover 分流到 SignedGrantImage（kind=image）', (
    tester,
  ) async {
    await tester.pumpWidget(
      _host(
        _introduction(
          // 私有 cover 的 url 为相对 objectKey，分流只认 typed 声明。
          coverUrl: 'media/objects/private-cover.jpg',
          coverAssetId: 'asset-intro-cover-1',
          coverAccessMode: MediaDeliveryAccessMode.signedGrant,
        ),
      ),
    );
    await tester.pumpAndSettle();

    final signed = tester.widget<SignedGrantImage>(
      find.byType(SignedGrantImage),
    );
    expect(signed.assetId, 'asset-intro-cover-1');
    expect(signed.kind, MediaDeliveryKind.image);
  });

  testWidgets('signedGrant hero 缺 assetId 呈现矛盾终态且不回退 public', (tester) async {
    await tester.pumpWidget(
      _host(
        _introduction(
          coverUrl: 'https://cdn.example.test/decoy.jpg',
          coverAccessMode: MediaDeliveryAccessMode.signedGrant,
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byKey(appImageLoadErrorKey), findsOneWidget);
    expect(find.byType(AppMediaImage), findsNothing);
    expect(find.byType(MediaDeliveryFailureState), findsOneWidget);
  });

  testWidgets('inline-only signedGrant 缺 assetId 显式失败且不回退 public', (
    tester,
  ) async {
    await tester.pumpWidget(
      _host(
        _introduction(
          sections: const <HomepageIntroductionSection>[
            HomepageIntroductionSection(
              kind: 'body',
              title: '矛盾内嵌图',
              bodyMarkdown: '正文没有可引用的 asset id。',
              assets: <HomepageIntroductionAsset>[
                HomepageIntroductionAsset(
                  assetId: '',
                  url: 'https://cdn.example.test/decoy-inline.jpg',
                  accessMode: MediaDeliveryAccessMode.signedGrant,
                  caption: '矛盾私有图',
                  role: 'inline',
                ),
              ],
              timelineItems: [],
            ),
          ],
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byKey(appImageLoadErrorKey), findsOneWidget);
    expect(find.byType(MediaDeliveryFailureState), findsOneWidget);
    expect(find.byType(AppMediaImage), findsNothing);
    expect(find.text(MediaText.signedDeliveryRetryAction), findsNothing);
  });

  testWidgets('signedGrant hero 失败呈现可见重试并可再次兑换', (tester) async {
    final gateway = _FailingOriginalAccessGateway();
    await tester.pumpWidget(
      _host(
        _introduction(
          coverAssetId: 'asset-intro-cover-failed',
          coverAccessMode: MediaDeliveryAccessMode.signedGrant,
        ),
        gateway: gateway,
      ),
    );
    await tester.pump();
    await tester.pump();

    expect(find.byKey(appImageLoadErrorKey), findsOneWidget);
    expect(find.text(MediaText.signedDeliveryRetryAction), findsOneWidget);
    expect(gateway.attempts, 1);

    await tester.tap(find.byKey(appImageLoadErrorKey));
    await tester.pump();
    await tester.pump();
    expect(gateway.attempts, 2);
    expect(find.byKey(appImageLoadErrorKey), findsOneWidget);
  });

  testWidgets('public hero cover 维持既有 AppMediaImage 路径', (tester) async {
    await tester.pumpWidget(
      _host(
        _introduction(
          coverUrl: 'https://cdn.example.test/cover.jpg',
          coverAccessMode: MediaDeliveryAccessMode.public,
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byType(SignedGrantImage), findsNothing);
    expect(
      find.byType(AppMediaImage, skipOffstage: false),
      findsAtLeastNWidgets(1),
    );
  });

  testWidgets('signedGrant 内嵌图与横滑资产失败可见且重试可达', (tester) async {
    final gateway = _FailingOriginalAccessGateway();
    await tester.pumpWidget(
      _host(
        _introduction(
          sections: const <HomepageIntroductionSection>[
            HomepageIntroductionSection(
              kind: 'body',
              title: '失败正文图',
              bodyMarkdown:
                  ':::figure id="fig_failed" caption="失败内嵌图"\n'
                  'asset://inline_failed_1\n'
                  ':::',
              assets: <HomepageIntroductionAsset>[
                HomepageIntroductionAsset(
                  assetId: 'inline_failed_1',
                  url: '',
                  accessMode: MediaDeliveryAccessMode.signedGrant,
                  role: 'inline',
                ),
              ],
              timelineItems: [],
            ),
            HomepageIntroductionSection(
              kind: 'relatedImages',
              title: '失败相关图片',
              assets: <HomepageIntroductionAsset>[
                HomepageIntroductionAsset(
                  assetId: 'strip_failed_1',
                  url: '',
                  accessMode: MediaDeliveryAccessMode.signedGrant,
                  role: 'related',
                ),
              ],
              timelineItems: [],
            ),
          ],
        ),
        gateway: gateway,
      ),
    );
    await tester.pump();
    await tester.pump();

    expect(find.byKey(appImageLoadErrorKey), findsWidgets);
    final firstFailure = find.byKey(appImageLoadErrorKey).first;
    await tester.ensureVisible(firstFailure);
    await tester.pump();
    final attemptsBeforeRetry = gateway.attempts;
    await tester.tap(firstFailure);
    await tester.pump();
    await tester.pump();
    expect(gateway.attempts, attemptsBeforeRetry + 1);

    await tester.scrollUntilVisible(
      find.text('失败相关图片'),
      220,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.pump();
    await tester.pump();
    expect(find.byKey(appImageLoadErrorKey, skipOffstage: false), findsWidgets);
    expect(find.text(MediaText.signedDeliveryRetryAction), findsWidgets);
  });

  testWidgets('signedGrant 内嵌图与横滑资产按 typed 声明分流，公开资产不受影响', (tester) async {
    await tester.pumpWidget(
      _host(
        _introduction(
          sections: <HomepageIntroductionSection>[
            HomepageIntroductionSection(
              kind: 'body',
              title: '历史沿革',
              bodyMarkdown:
                  '正文段落。\n\n'
                  ':::figure id="fig_signed" caption="私有内嵌图"\n'
                  'asset://inline_signed_1\n'
                  ':::\n\n'
                  '正文继续。',
              assets: const <HomepageIntroductionAsset>[
                // 私有资产 url 缺席也必须按 typed 绑定渲染。
                HomepageIntroductionAsset(
                  assetId: 'inline_signed_1',
                  url: '',
                  accessMode: MediaDeliveryAccessMode.signedGrant,
                  caption: '私有内嵌图',
                  role: 'inline',
                ),
              ],
              timelineItems: const [],
            ),
            HomepageIntroductionSection(
              kind: 'relatedImages',
              title: '相关图片',
              assets: const <HomepageIntroductionAsset>[
                HomepageIntroductionAsset(
                  assetId: 'related_signed_1',
                  url: 'media/objects/private-related.jpg',
                  accessMode: MediaDeliveryAccessMode.signedGrant,
                  role: 'related',
                ),
                HomepageIntroductionAsset(
                  assetId: 'related_public_1',
                  url: 'https://cdn.example.test/rel-public.jpg',
                  accessMode: MediaDeliveryAccessMode.public,
                  role: 'related',
                ),
              ],
              timelineItems: const [],
            ),
          ],
        ),
      ),
    );
    await tester.pumpAndSettle();

    // 正文内嵌图：signedGrant 资产在 url 缺席时仍按 typed 绑定渲染。
    final inlineSigned = tester.widget<SignedGrantImage>(
      find.byType(SignedGrantImage),
    );
    expect(inlineSigned.assetId, 'inline_signed_1');
    expect(inlineSigned.kind, MediaDeliveryKind.image);

    // 页尾横滑资产懒构建，先滚动到可见再断言分流。
    await tester.scrollUntilVisible(
      find.text('相关图片'),
      220,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.pumpAndSettle();

    final signedAssets = tester
        .widgetList<SignedGrantImage>(
          find.byType(SignedGrantImage, skipOffstage: false),
        )
        .map((widget) => widget.assetId)
        .toSet();
    expect(signedAssets, contains('related_signed_1'));
    // 公开横滑资产维持既有 AppMediaImage 路径。
    expect(
      find.byType(AppMediaImage, skipOffstage: false),
      findsAtLeastNWidgets(1),
    );
  });
}
