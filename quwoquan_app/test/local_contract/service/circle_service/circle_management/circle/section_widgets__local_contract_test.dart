import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/design_system/content/post_preview_list_tile.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/di/circle_creations_presentation_slots.dart'
    show circleCreationsParticipantSlots;
import 'package:quwoquan_app/service/circle_service/circle_management/circle/application/circle_state_provider.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle_file/application/public/circle_file_ports.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle_post_placement/application/public/circle_post_placement_commands.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle/presentation/section_creations.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle/presentation/section_chat.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle_file/presentation/section_storage.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle_membership/application/public/circle_membership_ports.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle_membership/presentation/section_members.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/user_profile_route_extra.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/service/circle_service/circle_management/circle/typed_circle_query_test_double.dart';
import '../../../../../support/service/circle_service/circle_management/circle/circle_contract_test_builders.dart';

CircleFeedPageSlice _defaultCircleFeedFixture(CircleFeedQuery query) {
  if (query.circleId == 'empty') {
    return CircleFeedPageSlice(items: const <CircleFeedItemView>[]);
  }
  return CircleFeedPageSlice(
    items: <CircleFeedItemView>[
      buildCircleFeedItemContract(
        circleId: query.circleId,
        placementId: 'fixture-placement-photo-1',
        postId: 'fixture_photo_1',
        contentType: 'image',
        contentIdentity: 'work',
        authorId: 'fixture_user_photo',
        authorDisplayName: '契约摄影师',
        body: '山路晨雾',
        coverUrl: 'media/image/fixture_photo_1.jpg',
        imageUrls: const <String>['media/image/fixture_photo_1.jpg'],
        likeCount: 12,
      ),
    ],
  );
}

CircleFeedPageSlice _articleCircleFeedFixture(CircleFeedQuery query) {
  return CircleFeedPageSlice(
    items: <CircleFeedItemView>[
      buildCircleFeedItemContract(
        circleId: query.circleId,
        placementId: 'fixture-placement-article-cover',
        postId: 'fixture_article_with_cover',
        contentType: 'article',
        contentIdentity: 'work',
        authorId: 'fixture_user_photo',
        authorDisplayName: '契约摄影师',
        title: '山路晨雾手账',
        body: '把徒步笔记做成可翻页的旅途册。',
        summary: '把徒步笔记做成可翻页的旅途册。',
        coverUrl: 'media/image/fixture_article_with_cover.jpg',
        likeCount: 164,
        commentCount: 12,
        shareCount: 11,
      ),
      buildCircleFeedItemContract(
        circleId: query.circleId,
        placementId: 'fixture-placement-article-text',
        postId: 'fixture_article_text_only',
        contentType: 'article',
        contentIdentity: 'work',
        authorId: 'fixture_user_owner',
        authorDisplayName: '纸上居',
        body: '没有标题也没封面，只保留真正想被圈友读到的正文。',
        summary: '没有标题也没封面，只保留真正想被圈友读到的正文。',
        likeCount: 88,
        commentCount: 6,
        shareCount: 4,
      ),
    ],
  );
}

Widget _wrap(
  Widget child, {
  double textScaleFactor = 1.0,
  CircleQueryReader? circleQuery,
  CircleFeedQueryReader? feedQuery,
  CirclePostPlacementCommands? placementWriter,
}) => ProviderScope(
  overrides: [
    circleDetailQueryProvider.overrideWithValue(
      circleQuery ?? CircleQueryReaderTestDouble(),
    ),
    circlesListQueryProvider.overrideWithValue(
      circleQuery ?? CircleQueryReaderTestDouble(),
    ),
    circleDetailFeedQueryProvider.overrideWithValue(
      feedQuery ?? CircleFeedQueryTestDouble(_defaultCircleFeedFixture),
    ),
    circleDetailPostPlacementCommandWriterProvider.overrideWithValue(
      placementWriter ?? _CirclePostPlacementFixture(),
    ),
    circleDetailFileCommandWriterProvider.overrideWithValue(
      _CircleFileFixture(),
    ),
    circleDetailFileQueryProvider.overrideWithValue(_CircleFileFixture()),
  ],
  child: MaterialApp.router(
    builder: (context, childWidget) {
      final mediaQuery = MediaQuery.of(context);
      return MediaQuery(
        data: mediaQuery.copyWith(
          textScaler: TextScaler.linear(textScaleFactor),
        ),
        child: childWidget ?? const SizedBox.shrink(),
      );
    },
    routerConfig: GoRouter(
      initialLocation: '/',
      routes: [
        GoRoute(
          path: '/',
          builder: (_, _) => Scaffold(body: child),
        ),
        GoRoute(
          path: '/works/browser/:workId',
          builder: (_, _) => const SizedBox(),
        ),
        GoRoute(path: '/chat/:id', builder: (_, _) => const SizedBox()),
      ],
    ),
  ),
);

void main() {
  group('SectionCreations — Widget 契约', () {
    testWidgets('正常渲染', (tester) async {
      await tester.pumpWidget(
        _wrap(
          const SizedBox(
            height: 800,
            child: SectionCreations(
              circleId: 'fixture_circle_photo',
              isDark: false,
              role: CircleRole.owner,
              participantSlots: circleCreationsParticipantSlots,
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.byType(SectionCreations), findsOneWidget);
      // 二级过滤改回横向胶囊条：全部子页签直接平铺可见（默认「全部」选中）。
      expect(
        find.byKey(const ValueKey<String>('circle-creations-filter-bar')),
        findsOneWidget,
      );
      expect(
        find.byKey(
          const ValueKey<String>('circle-creations-filter-option-image'),
        ),
        findsOneWidget,
      );
      expect(
        find.byKey(
          const ValueKey<String>('circle-creations-filter-option-video'),
        ),
        findsOneWidget,
      );
      expect(
        find.byKey(
          const ValueKey<String>('circle-creations-filter-option-article'),
        ),
        findsOneWidget,
      );
      expect(find.text('全部'), findsAtLeastNWidgets(1));
      expect(find.text('图片'), findsWidgets);
      expect(find.text('视频'), findsWidgets);
      // 「长文」是与用户主页同源的 metadata 子页签 creation_sub_text 文案
      // （UserProfileUIConfig.creationSubTabs），与作者主页保持一致。
      expect(find.text('长文'), findsWidgets);
    });

    testWidgets('owner 长按创作可置顶并从同一 placement 投影显示徽标', (tester) async {
      var pinned = false;
      final placementWriter = _CirclePostPlacementFixture(
        onPin: (command) => pinned = command.enabled,
      );
      final feedQuery = CircleFeedQueryTestDouble(
        (query) => CircleFeedPageSlice(
          items: <CircleFeedItemView>[
            buildCircleFeedItemContract(
              circleId: query.circleId,
              placementId: 'fixture-placement-photo-1',
              pinned: pinned,
              postId: 'fixture_photo_1',
              contentType: 'image',
              contentIdentity: 'work',
              body: '山路晨雾',
            ),
          ],
        ),
      );
      await tester.pumpWidget(
        _wrap(
          const SizedBox(
            height: 800,
            child: SectionCreations(
              circleId: 'fixture_circle_photo',
              isDark: false,
              role: CircleRole.owner,
              participantSlots: circleCreationsParticipantSlots,
            ),
          ),
          feedQuery: feedQuery,
          placementWriter: placementWriter,
        ),
      );
      await tester.pumpAndSettle();

      await tester.longPress(
        find.byKey(
          const ValueKey<String>('circle-record-grid-fixture_photo_1'),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text(CommunityText.circlePostPinAction), findsOneWidget);

      await tester.tap(find.text(CommunityText.circlePostPinAction));
      await tester.pumpAndSettle();
      expect(placementWriter.lastPin?.placementId, 'fixture-placement-photo-1');
      expect(placementWriter.lastPin?.enabled, isTrue);
      expect(
        find.byKey(
          const ValueKey<String>('circle-post-presentation-fixture_photo_1-置顶'),
        ),
        findsOneWidget,
      );
      await tester.pump(const Duration(seconds: 4));
      await tester.pumpAndSettle();
    });

    testWidgets('空数据安全渲染', (tester) async {
      await tester.pumpWidget(
        _wrap(
          const SizedBox(
            height: 800,
            child: SectionCreations(
              circleId: 'empty',
              isDark: false,
              role: CircleRole.member,
              participantSlots: circleCreationsParticipantSlots,
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.byType(SectionCreations), findsOneWidget);
    });

    testWidgets('窄高容器空态不溢出', (tester) async {
      tester.view.physicalSize = const Size(320, 560);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      final capturedErrors = <FlutterErrorDetails>[];
      final originalOnError = FlutterError.onError;
      FlutterError.onError = (details) {
        capturedErrors.add(details);
      };
      try {
        await tester.pumpWidget(
          _wrap(
            const SizedBox(
              height: 220,
              child: SectionCreations(
                circleId: 'empty',
                isDark: false,
                role: CircleRole.owner,
                participantSlots: circleCreationsParticipantSlots,
              ),
            ),
            textScaleFactor: 1.3,
          ),
        );
        await tester.pumpAndSettle();
      } finally {
        FlutterError.onError = originalOnError;
      }

      final overflowErrors = capturedErrors
          .map((details) => details.exceptionAsString())
          .where((message) => message.contains('A RenderFlex overflowed'))
          .toList(growable: false);

      expect(overflowErrors, isEmpty);
    });

    testWidgets('owner 模式可切换列表视图', (tester) async {
      final circleQuery = _ArticleFixtureCircleQuery();
      await tester.pumpWidget(
        _wrap(
          const SizedBox(
            height: 800,
            child: SectionCreations(
              circleId: 'fixture_circle_photo',
              isDark: false,
              role: CircleRole.owner,
              participantSlots: circleCreationsParticipantSlots,
            ),
          ),
          circleQuery: circleQuery,
          feedQuery: CircleFeedQueryTestDouble(_articleCircleFeedFixture),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.byTooltip('列表视图'));
      await tester.pumpAndSettle();

      expect(find.byType(PostPreviewListTile), findsWidgets);
    });

    testWidgets('窄屏大字号下网格卡片不溢出', (tester) async {
      tester.view.physicalSize = const Size(320, 690);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      final capturedErrors = <FlutterErrorDetails>[];
      final originalOnError = FlutterError.onError;
      FlutterError.onError = (details) {
        capturedErrors.add(details);
      };
      try {
        await tester.pumpWidget(
          _wrap(
            const SizedBox(
              height: 800,
              child: SectionCreations(
                circleId: 'fixture_circle_photo',
                isDark: false,
                role: CircleRole.owner,
                participantSlots: circleCreationsParticipantSlots,
              ),
            ),
            textScaleFactor: 1.4,
          ),
        );
        await tester.pumpAndSettle();
      } finally {
        FlutterError.onError = originalOnError;
      }

      final overflowErrors = capturedErrors
          .map((details) => details.exceptionAsString())
          .where((message) => message.contains('A RenderFlex overflowed'))
          .toList(growable: false);

      expect(overflowErrors, isEmpty);
    });

    testWidgets('笔记双列区分封面卡与文字卡并展示频道推荐', (tester) async {
      final circleQuery = _ArticleFixtureCircleQuery();
      await tester.pumpWidget(
        _wrap(
          const SizedBox(
            height: 800,
            child: SectionCreations(
              circleId: 'fixture_circle_photo',
              isDark: false,
              role: CircleRole.owner,
              participantSlots: circleCreationsParticipantSlots,
            ),
          ),
          circleQuery: circleQuery,
          feedQuery: CircleFeedQueryTestDouble(_articleCircleFeedFixture),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(
        find.byKey(
          const ValueKey<String>('circle-creations-filter-option-article'),
        ),
      );
      await tester.pumpAndSettle();

      expect(
        find.byKey(
          const ValueKey<String>(
            'circle-article-grid-fixture_article_with_cover',
          ),
        ),
        findsOneWidget,
      );
      await tester.drag(find.byType(Scrollable).first, const Offset(0, -320));
      await tester.pumpAndSettle();
      expect(
        find.byKey(
          const ValueKey<String>(
            'circle-article-grid-fixture_article_text_only',
          ),
        ),
        findsOneWidget,
      );
      expect(find.textContaining('讨论推荐'), findsWidgets);
    });
  });

  group('SectionChat — Widget 契约', () {
    testWidgets('正常渲染', (tester) async {
      await tester.pumpWidget(
        _wrap(
          SectionChat(
            circleId: 'fixture_circle_photo',
            conversationId: 'conv_fixture_circle_photo',
            isDark: false,
          ),
        ),
      );
      await tester.pump();
      expect(find.byType(SectionChat), findsOneWidget);
    });

    testWidgets('空数据安全渲染', (tester) async {
      await tester.pumpWidget(
        _wrap(
          SectionChat(circleId: 'empty', conversationId: null, isDark: false),
        ),
      );
      await tester.pump();
      expect(find.byType(SectionChat), findsOneWidget);
      expect(find.text(CommunityText.circleNoChatEnabled), findsOneWidget);
    });

    testWidgets('有默认群但绑定未就绪时展示开通中与重试', (tester) async {
      var retried = 0;
      await tester.pumpWidget(
        _wrap(
          SectionChat(
            circleId: 'fixture_circle_photo',
            conversationId: null,
            hasDefaultGroup: true,
            isDark: false,
            onRefresh: () => retried += 1,
          ),
        ),
      );
      await tester.pump();
      expect(
        find.byKey(const ValueKey<String>('circle-chat-binding-pending')),
        findsOneWidget,
      );
      expect(
        find.text(CommunityText.circleChatBindingPendingTitle),
        findsOneWidget,
      );
      await tester.tap(
        find.byKey(const ValueKey<String>('circle-chat-binding-retry')),
      );
      expect(retried, 1);
    });
  });

  group('SectionMembers — Widget 契约', () {
    testWidgets('成员行点击进入用户主页（建联承接）', (tester) async {
      String? navigatedHandle;
      Object? capturedExtra;
      final app = ProviderScope(
        overrides: [
          circleDetailMembershipQueryProvider.overrideWithValue(
            _SectionMembersQueryFixture(),
          ),
        ],
        child: MaterialApp.router(
          routerConfig: GoRouter(
            initialLocation: '/',
            routes: [
              GoRoute(
                path: '/',
                builder: (_, _) => Scaffold(
                  body: SectionMembers(
                    circleId: 'fixture_circle_photo',
                    isDark: false,
                  ),
                ),
              ),
              GoRoute(
                path: '/user/:userHandle',
                builder: (_, state) {
                  navigatedHandle = state.pathParameters['userHandle'];
                  capturedExtra = state.extra;
                  return const SizedBox();
                },
              ),
            ],
          ),
        ),
      );
      await tester.pumpWidget(app);
      await tester.pumpAndSettle();

      await tester.tap(
        find.byKey(const ValueKey<String>('circle-member-row-fixture_persona')),
      );
      await tester.pumpAndSettle();

      expect(navigatedHandle, 'fixture_persona');
      expect(
        (capturedExtra as UserProfileRouteExtra?)?.safePersonaId,
        'fixture_persona',
      );
    });
  });

  group('SectionStorage — Widget 契约', () {
    testWidgets('正常渲染', (tester) async {
      await tester.pumpWidget(
        _wrap(
          SectionStorage(
            circleId: 'fixture_circle_photo',
            isDark: false,
            storageUsedBytes: 52428800,
            storageQuotaBytes: 1073741824,
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.byType(SectionStorage), findsOneWidget);
      expect(find.text('真实契约文件.pdf'), findsOneWidget);
    });

    testWidgets('空数据安全渲染', (tester) async {
      await tester.pumpWidget(
        _wrap(
          SectionStorage(
            circleId: 'empty',
            isDark: false,
            storageUsedBytes: 0,
            storageQuotaBytes: 1073741824,
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.byType(SectionStorage), findsOneWidget);
      expect(find.text(CommunityText.noData), findsOneWidget);
    });
  });
}

final class _CirclePostPlacementFixture implements CirclePostPlacementCommands {
  _CirclePostPlacementFixture({this.onPin});

  final void Function(PinCirclePostCommand command)? onPin;
  PinCirclePostCommand? lastPin;

  @override
  Future<CirclePostPlacementCommandResult> setPinned(
    PinCirclePostCommand command,
  ) async {
    lastPin = command;
    onPin?.call(command);
    return CirclePostPlacementCommandResult(
      placementId: command.placementId,
      version: 2,
      state: 'active',
      idempotentReplay: false,
    );
  }

  @override
  Future<CirclePostPlacementCommandResult> setFeatured(
    FeatureCirclePostCommand command,
  ) async => CirclePostPlacementCommandResult(
    placementId: command.placementId,
    version: 2,
    state: 'active',
    idempotentReplay: false,
  );

  @override
  Future<CirclePostPlacementCommandResult> placePost(
    PlaceCirclePostCommand command,
  ) async => CirclePostPlacementCommandResult(
    placementId: 'fixture-placement-created',
    version: 1,
    state: 'active',
    idempotentReplay: false,
  );

  @override
  Future<CirclePostPlacementCommandResult> removePost(
    RemoveCirclePostCommand command,
  ) async => CirclePostPlacementCommandResult(
    placementId: command.placementId,
    version: 2,
    state: 'removed',
    idempotentReplay: false,
  );
}

final class _CircleFileFixture implements CircleFileWriter, CircleFileReader {
  @override
  Future<CircleFileCommandResult> create(CreateCircleFileCommand command) =>
      throw UnimplementedError();

  @override
  Future<CircleFileCommandResult> delete(DeleteCircleFileCommand command) =>
      throw UnimplementedError();

  @override
  Future<CircleFileSlice> get(CircleFileQuery query) =>
      throw UnimplementedError();

  @override
  Future<CircleFilePageSlice> list(CircleFileListQuery query) async {
    if (query.circleId == 'empty') {
      return CircleFilePageSlice(items: <CircleFileSlice>[]);
    }
    return CircleFilePageSlice(
      items: <CircleFileSlice>[
        CircleFileSlice(
          fileId: 'file-1',
          version: 1,
          circleId: query.circleId,
          groupId: null,
          parentFolderId: query.parentFolderId,
          name: '真实契约文件.pdf',
          fileType: CircleFileType.file,
          assetId: 'asset-1',
          mimeType: 'application/pdf',
          sizeBytes: 1024,
          uploaderPersonaId: 'persona-1',
          status: CircleFileStatus.active,
          createdAt: DateTime.utc(2026, 7, 14),
          updatedAt: DateTime.utc(2026, 7, 14),
        ),
      ],
    );
  }

  @override
  Future<CircleFileCommandResult> update(UpdateCircleFileCommand command) =>
      throw UnimplementedError();
}

class _ArticleFixtureCircleQuery extends CircleQueryReaderTestDouble {
  @override
  Future<Circle> get(CircleDetailQuery query) async => buildCircleContract(
    circleId: query.circleId,
    name: '契约摄影社',
    ownerId: 'fixture_user_owner',
    category: 'photography',
    visibility: CircleVisibility.public,
    joinPolicy: CircleJoinPolicy.approval,
    createdAt: DateTime.utc(2026, 5, 6),
    updatedAt: DateTime.utc(2026, 5, 6),
  );
}

final class _SectionMembersQueryFixture implements CircleMembershipQueries {
  @override
  Future<CircleMembershipSlice> getMyMembership(
    MyCircleMembershipQuery query,
  ) => throw UnsupportedError('getMyMembership is outside this section');

  @override
  Future<CircleMembershipPageSlice> listMemberships(
    CircleMembershipListQuery query,
  ) async {
    final now = DateTime.utc(2026, 8, 6);
    return CircleMembershipPageSlice(
      items: <CircleMembershipSlice>[
        CircleMembershipSlice(
          membershipId: 'membership-001',
          version: 1,
          circleId: query.circleId,
          personaId: 'fixture_persona',
          role: CircleMemberRole.member,
          state: CircleMembershipState.active,
          joinedAt: now,
          lastActiveAt: now,
          contribution: 0,
          createdAt: now,
          updatedAt: now,
        ),
      ],
    );
  }

  @override
  Future<PersonaCirclePageSlice> listPersonaCircles(
    PersonaCircleListQuery query,
  ) => throw UnsupportedError('listPersonaCircles is outside this section');
}
