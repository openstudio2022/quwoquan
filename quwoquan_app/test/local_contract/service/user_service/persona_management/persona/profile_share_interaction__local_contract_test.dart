// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/owner-persona-homepage-unification/spec.md#gwt-001
// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/owner-persona-homepage-unification/spec.md#gwt-001.t1
// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/owner-persona-homepage-unification/spec.md#gwt-001.t2
// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/owner-persona-homepage-unification/spec.md#gwt-001.t3
// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/owner-persona-homepage-unification/spec.md#gwt-002
// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/owner-persona-homepage-unification/spec.md#gwt-002.t1
// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/owner-persona-homepage-unification/spec.md#gwt-002.t2
// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/owner-persona-homepage-unification/spec.md#gwt-002.t3
// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/owner-persona-homepage-unification/spec.md#gwt-003
// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/owner-persona-homepage-unification/spec.md#gwt-003.t1
// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/owner-persona-homepage-unification/spec.md#gwt-003.t2
// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/owner-persona-homepage-unification/spec.md#gwt-003.t3
// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/owner-persona-homepage-unification/spec.md#gwt-006
// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/owner-persona-homepage-unification/spec.md#gwt-006.t1
// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/owner-persona-homepage-unification/spec.md#gwt-006.t2
// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/owner-persona-homepage-unification/spec.md#gwt-006.t3
// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/owner-persona-homepage-unification/spec.md#gwt-006.t4
// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/model-attribute-semantics/spec.md#gwt-003
// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/model-attribute-semantics/spec.md#gwt-003.t1
import 'dart:io';

import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/design_system/media/app_cached_network_image.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/application/public/generated/user_profile_ui_config.g.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/application/public/profile_mode.dart';
import 'package:quwoquan_app/service/content_service/content/profile_interaction_activity_view/application/public/profile_interaction_selection.dart';
import 'package:quwoquan_app/service/content_service/content/profile_interaction_activity_view/application/public/profile_interaction_activity_view_data.dart';
import 'package:quwoquan_app/service/content_service/content/profile_interaction_activity_view/application/public/share_interaction_models.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/presentation/profile_state_provider.dart';
import 'package:quwoquan_app/runtime/di/profile_presentation_slots.dart'
    show profileParticipantSlots;
import 'package:quwoquan_app/service/user_service/persona_management/persona/presentation/profile_interaction_tab_host.dart';
import 'package:quwoquan_app/design_system/navigation/secondary_tab_bar.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/presentation/share_interaction/share_empty_state.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/presentation/share_interaction/share_interaction_row.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/presentation/share_interaction/share_target_preview.dart';
import '../../../../../support/service/content_service/content/profile_interaction_activity_view/test_profile_interaction_facets.dart';
import '../../../../../support/service/content_service/content/post/content_facet_overrides.dart';
import '../../../../../support/service/content_service/content/post/content_post_typed_doubles.dart';
import '../../../../../support/service/user_service/account/user_account/user_account_profile_typed_double.dart';

void main() {
  // GWT-001.t1：一级恰好三项，且足迹只对 owner 开放。
  test('一级导航保持记录、互动、足迹三项', () {
    final tabs = UserProfileUIConfig.profileTabs;
    expect(tabs.map((tab) => tab.id), <String>[
      'creations',
      'interaction',
      'footprint',
    ]);
    expect(
      tabs.singleWhere((tab) => tab.id == 'creations').isDefault,
      isTrue,
      reason: '默认落在记录',
    );
    final footprint = tabs.singleWhere((tab) => tab.id == 'footprint');
    expect(footprint.visibleInMode('mine'), isTrue);
    expect(footprint.visibleInMode('other'), isFalse);
  });

  // GWT-001.t2：二级项与方向项都以 user-service 的 ui_config.yaml 为准。
  // 断言逐字段对照契约而不是复制一份清单，否则规格、契约、端侧会各存一份。
  test('互动二级与方向项与服务端契约同源', () {
    final contract = File(
      '${_repositoryRoot()}/quwoquan_service/services/user-service/contracts/account/user_account/ui_config.yaml',
    ).readAsStringSync();
    for (final labelKey in <String>[
      'interaction_sub_likes',
      'interaction_sub_comments',
      'interaction_sub_shares',
    ]) {
      expect(
        contract,
        contains(labelKey),
        reason: '端侧二级项必须在服务端契约里有对应声明',
      );
    }
    expect(
      contract,
      isNot(contains('interaction_sub_views')),
      reason: '浏览不在互动二级；契约一旦重新引入，这条断言先失败',
    );

    final tabs = UserProfileUIConfig.interactionSubTabs;
    expect(tabs.map((tab) => tab.id), <String>['likes', 'comments', 'shares']);
    expect(tabs.singleWhere((tab) => tab.id == 'likes').isDefault, isTrue);
    final shares = tabs.singleWhere((tab) => tab.id == 'shares');
    expect(shares.visibleInMode('mine'), isTrue);
    expect(shares.visibleInMode('other'), isFalse);
    expect(UserProfileUIConfig.interactionDirectionFiltersByMode['mine'], <
      String
    >['received', 'sent']);
    expect(UserProfileUIConfig.interactionDirectionFiltersByMode['other'], <
      String
    >['received']);
  });

  // GWT-001.t3：独立转发页与第三行导航都不存在。
  // 只在渲染后断言「看不见」挡不住有人另建一个路由；这里连生产树里的路由与文件
  // 一起扫，任何一条重新出现都会失败。
  test('没有独立转发页、互动明细页或第三行导航', () {
    final root = _repositoryRoot();
    final links = File(
      '$root/quwoquan_app/lib/runtime/shell/navigation/generated/link_templates.g.dart',
    ).readAsStringSync();
    for (final forbidden in <String>[
      'shareInteraction',
      'share_interaction',
      'interactionDetail',
      'interaction_detail',
    ]) {
      expect(
        links,
        isNot(contains(forbidden)),
        reason: '$forbidden 会把转发列表拆成可深链的独立页面',
      );
    }
    final shareDir = Directory(
      '$root/quwoquan_app/lib/service/user_service/persona_management/persona/presentation/share_interaction',
    );
    final pageFiles = shareDir
        .listSync()
        .whereType<File>()
        .map((file) => file.uri.pathSegments.last)
        .where((name) => name.endsWith('_page.dart'))
        .toList();
    expect(pageFiles, isEmpty, reason: '转发互动只有行与列表，不得有页面');
    expect(
      UserProfileUIConfig.lifestyleSubTabs,
      isEmpty,
      reason: '第三行导航为空，一旦被填就是新增了一层',
    );
  });

  // GWT-006.t1：解析枚举只有原目标与失效两态。
  // 逐 availability 穷举而不是挑两个样例：新增一个可跳转态却忘了给它接路由时，
  // 这里会立刻发现多出来的解析结果。
  test('四种 availability 只解析出原目标或失效两种结果', () {
    expect(ShareTargetNavigationResolution.values, <
      ShareTargetNavigationResolution
    >[
      ShareTargetNavigationResolution.originalTarget,
      ShareTargetNavigationResolution.unavailable,
    ], reason: '出现第三种解析就等于同一行有了第二条跳转路径');

    for (final availability in ShareTargetAvailability.values) {
      final item = _item(
        ShareInteractionDirection.received,
        availability: availability,
      );
      final expected = availability == ShareTargetAvailability.active
          ? ShareTargetNavigationResolution.originalTarget
          : ShareTargetNavigationResolution.unavailable;
      expect(
        item.targetNavigationResolution,
        expected,
        reason: '$availability 的解析结果与 canOpenTarget 必须一致',
      );
      expect(item.canOpenTarget, availability == ShareTargetAvailability.active);
    }

    final list = File(
      '${_repositoryRoot()}/quwoquan_app/lib/service/user_service/persona_management/persona/presentation/share_interaction/share_interaction_list.dart',
    ).readAsStringSync();
    expect(
      list,
      isNot(contains('outboundShareEventId')),
      reason: '站外分享事实只作观测，列表不得拿它当路由目标',
    );
    final row = File(
      '${_repositoryRoot()}/quwoquan_app/lib/service/user_service/persona_management/persona/presentation/share_interaction/share_interaction_row.dart',
    ).readAsStringSync();
    expect(
      row,
      isNot(contains('targetNavigationResolution')),
      reason: '行不得自己再解析一次，只消费列表传下来的回调',
    );
    expect(
      RegExp('onTap: onOpenTarget').allMatches(row).length,
      2,
      reason: '行与预览各绑一次，但绑的是同一个回调',
    );
  });

  // GWT-006.t3：头像与昵称按方向进入 actor 或 counterpart。
  test('头像昵称按方向解析到 actor 或 counterpart', () {
    final received = ShareInteractionItem.fromActivity(
      _activity(),
      ShareInteractionDirection.received,
    );
    expect(received.displayPersonaId, 'actor-persona');

    final initiated = ShareInteractionItem.fromActivity(
      _activity(),
      ShareInteractionDirection.initiated,
    );
    expect(initiated.displayPersonaId, 'counterpart-persona');

    final withoutCounterpart = ShareInteractionItem.fromActivity(
      _activity(counterpartPersonaId: ''),
      ShareInteractionDirection.initiated,
    );
    expect(
      withoutCounterpart.displayPersonaId,
      'target-persona',
      reason: 'counterpart 缺席时回落到被转发内容的作者，而不是留空',
    );
  });

  // GWT-003.t3：本端未声明的取值落显式未知态、不可打开、文案不替云侧断言内容状态。
  // 同时承载治理节点 model-attribute-semantics 的 GWT-003.t1（入站取值到未知成员的映射）。
  test('本端闭集外的可用性取值落显式未知成员且不可打开', () {
    // 经公开工厂观察，而不是直接构造 enum——直接给 enum 会绕开这段解析，
    // 那样测的是断言自己而不是入站取值的去向。
    for (final offContract in <String>[
      'available', // 形近 active，最容易被当成同义词放行
      'AUTHOR_DEACTIVATED', // 大小写变体不构成闭集成员
      'archived', // 云侧将来新增的取值
      '', // NOT_NULL 字段的零值同样不是闭集成员
    ]) {
      final item = ShareInteractionItem.fromActivity(
        _activity(targetAvailability: offContract),
        ShareInteractionDirection.received,
      );
      expect(
        item.targetAvailability,
        ShareTargetAvailability.unknown,
        reason: '`$offContract` 不在本端闭集内，必须落未知成员而不是被就近归并',
      );
      expect(
        item.canOpenTarget,
        isFalse,
        reason: '`$offContract` 被当成可打开时，用户要点进去才发现打不开',
      );
      expect(
        item.targetNavigationResolution,
        ShareTargetNavigationResolution.unavailable,
        reason: '未知取值的跳转解析必须与 canOpenTarget 同向',
      );
    }

    // 未知态的文案不得复用断言性措辞：把「本端没声明这个取值」说成「内容已删除」，
    // 会把客户端版本落后谎报成内容发生了变化。
    expect(
      ProfileText.profileShareUnsupportedAvailability,
      isNot(anyOf(contains('已删除'), contains('已注销'), contains('私密'))),
      reason: '未知取值只能说本端打不开，不能替云侧断言内容出了什么事',
    );
  });

  // GWT-006.t4：影响结果只进入 metadata 声明的 myIntersections。
  test('影响结果只跳 metadata 枚举的传播来源明细', () {
    final routes = File(
      '${_repositoryRoot()}/quwoquan_service/contracts/metadata/_shared/app_routes.yaml',
    ).readAsStringSync();
    expect(
      routes,
      contains('id: myIntersections'),
      reason: '影响结果的落点必须在 metadata 路由表里声明',
    );

    final navigable = _item(
      ShareInteractionDirection.received,
      impactPrimaryText: '3 位好友因此看到',
      impactDeepLink: 'myIntersections',
    );
    expect(navigable.hasImpact, isTrue);
    expect(navigable.impactIsNavigable, isTrue);

    final unknownTarget = _item(
      ShareInteractionDirection.received,
      impactPrimaryText: '3 位好友因此看到',
      impactDeepLink: 'objectIntersections',
    );
    expect(
      unknownTarget.hasImpact,
      isTrue,
      reason: '文案仍展示，只是不可点',
    );
    expect(unknownTarget.impactIsNavigable, isFalse);

    final textOnly = _item(
      ShareInteractionDirection.received,
      impactPrimaryText: '3 位好友因此看到',
      impactDeepLink: '',
    );
    expect(textOnly.impactIsNavigable, isFalse, reason: '缺 deepLink 不得可点');

    final initiated = _item(
      ShareInteractionDirection.initiated,
      impactPrimaryText: '3 位好友因此看到',
      impactDeepLink: 'myIntersections',
    );
    expect(initiated.hasImpact, isFalse, reason: 'initiated 不展示影响数据');
  });

  // GWT-006.t2
  test('站外分享事实只用于观测，行和预览只导航到原始目标', () {
    final record = _item(ShareInteractionDirection.received);
    expect(record.outboundShareEventId, 'outbound-event-received');
    final original = _item(ShareInteractionDirection.received);
    expect(
      original.targetNavigationResolution,
      ShareTargetNavigationResolution.originalTarget,
    );
    final unavailable = _item(
      ShareInteractionDirection.received,
      availability: ShareTargetAvailability.deleted,
    );
    expect(
      unavailable.targetNavigationResolution,
      ShareTargetNavigationResolution.unavailable,
    );
  });

  testWidgets('方向选择器与互动筛选位于同一二级控制行', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          ...mockContentFacetOverrides(store: InMemoryContentPostStore()),
          profileQueryProvider.overrideWith(
            (ref, surface) => const MockUserProfileRepository(),
          ),
          profileInteractionQueryFacetProvider.overrideWithValue(
            const TestProfileInteractionFacets(),
          ),
          profileInteractionReadFactAppendFacetProvider.overrideWithValue(
            const TestProfileInteractionFacets(),
          ),
        ],
        child: CupertinoApp(
          home: CupertinoPageScaffold(
            child: ProfileInteractionTabHost(
              participantSlots: profileParticipantSlots,
              mode: ProfileMode.mine,
              userId: 'fixture_user_current',
              isDark: false,
            ),
          ),
        ),
      ),
    );
    await tester.pump();

    final container = ProviderScope.containerOf(
      tester.element(find.byType(ProfileInteractionTabHost)),
    );
    container
        .read(profileNotifierProvider('fixture_user_current').notifier)
        .setInteractionSubTab(InteractionSubTab.shares);
    await tester.pump();

    expect(find.text(ProfileText.interactionSubAll), findsNothing);
    expect(find.text(ProfileText.interactionSubShares), findsOneWidget);
    expect(
      find.text(ProfileText.profileInteractionDirectionReceived),
      findsOneWidget,
    );
    expect(
      find.text(ProfileText.profileInteractionDirectionSent),
      findsOneWidget,
    );
    final switchFinder = find.byKey(
      const ValueKey<String>('profile-interaction-direction-switch'),
    );
    expect(switchFinder, findsOneWidget);
    expect(
      find.ancestor(
        of: switchFinder,
        matching: find.byType(AppSecondaryTabBar),
      ),
      findsOneWidget,
    );
  });

  testWidgets('received 与 initiated 行遵守专属文案、尺寸和边界', (tester) async {
    final received = _item(ShareInteractionDirection.received);
    final initiated = _item(ShareInteractionDirection.initiated);
    await tester.pumpWidget(
      CupertinoApp(
        home: CupertinoPageScaffold(
          child: Column(
            children: <Widget>[
              ShareInteractionRow(item: received, isLast: false),
              ShareInteractionRow(item: initiated, isLast: true),
            ],
          ),
        ),
      ),
    );
    await tester.pump();

    expect(
      find.text(ProfileText.profileShareReceivedRecordAction),
      findsOneWidget,
    );
    expect(
      find.text(
        '${ProfileText.profileShareInitiatedRecordPrefix} 纸上旅行${ProfileText.profileShareInitiatedRecordSuffix}',
      ),
      findsOneWidget,
    );
    expect(find.text('带来 3 次新浏览'), findsOneWidget);
    final previews = find.byKey(
      const ValueKey<String>('share-target-preview-share-received'),
    );
    expect(previews, findsOneWidget);
    expect(
      tester.getSize(previews).height,
      AppSpacing.profileShareInteractionPreviewSize,
    );
  });

  testWidgets('两个方向使用独立空态且不自动切换', (tester) async {
    await tester.pumpWidget(
      CupertinoApp(
        home: CupertinoPageScaffold(
          child: shareInteractionEmptyState(
            direction: ShareInteractionDirection.received,
            onAction: () {},
          ),
        ),
      ),
    );
    expect(
      find.text(ProfileText.profileShareReceivedEmptyTitle),
      findsOneWidget,
    );

    await tester.pumpWidget(
      CupertinoApp(
        home: CupertinoPageScaffold(
          child: shareInteractionEmptyState(
            direction: ShareInteractionDirection.initiated,
            onAction: () {},
          ),
        ),
      ),
    );
    expect(
      find.text(ProfileText.profileShareInitiatedEmptyTitle),
      findsOneWidget,
    );
    expect(find.text(ProfileText.profileInteractionEmpty), findsNothing);
  });

  // GWT-002.t1 / GWT-002.t2：两个方向各自的记录与讨论文案都必须成立。
  // 只测记录一种目标类型时，讨论分支写错了也照样绿。
  testWidgets('记录与讨论在两个方向各有专属文案', (tester) async {
    await tester.pumpWidget(
      CupertinoApp(
        home: CupertinoPageScaffold(
          child: Column(
            children: <Widget>[
              ShareInteractionRow(
                item: _item(
                  ShareInteractionDirection.received,
                  targetKind: ShareTargetKind.discussion,
                ),
                isLast: false,
              ),
              ShareInteractionRow(
                item: _item(
                  ShareInteractionDirection.initiated,
                  targetKind: ShareTargetKind.discussion,
                ),
                isLast: true,
              ),
            ],
          ),
        ),
      ),
    );
    await tester.pump();

    expect(
      find.text(ProfileText.profileShareReceivedDiscussionAction),
      findsOneWidget,
    );
    expect(
      find.text(
        '${ProfileText.profileShareInitiatedRecordPrefix} 纸上旅行${ProfileText.profileShareInitiatedDiscussionSuffix}',
      ),
      findsOneWidget,
    );
    expect(
      find.text(ProfileText.profileShareReceivedRecordAction),
      findsNothing,
    );
  });

  // GWT-002.t3：附言最多两行；每次转发独立成行，同一目标被转发两次不合并。
  testWidgets('附言截断在两行且每次转发独立成行', (tester) async {
    final first = _item(ShareInteractionDirection.received);
    final second = ShareInteractionItem(
      interactionId: 'share-received-2',
      direction: ShareInteractionDirection.received,
      displayPersonaId: first.displayPersonaId,
      displayName: first.displayName,
      displayAvatarUrl: first.displayAvatarUrl,
      targetPersonaId: first.targetPersonaId,
      targetContentId: first.targetContentId,
      targetContentType: first.targetContentType,
      targetSummary: first.targetSummary,
      targetKind: first.targetKind,
      targetAvailability: first.targetAvailability,
      targetReplyCount: first.targetReplyCount,
      previewKind: first.previewKind,
      previewImageUrl: first.previewImageUrl,
      previewText: first.previewText,
      outboundShareEventId: 'outbound-event-received-2',
      shareText: '第二次转发同一条记录。',
      impactPrimaryText: '',
      impactDeepLink: '',
      occurredAt: DateTime(2026, 7, 12, 9),
    );
    await tester.pumpWidget(
      CupertinoApp(
        home: CupertinoPageScaffold(
          child: Column(
            children: <Widget>[
              ShareInteractionRow(item: first, isLast: false),
              ShareInteractionRow(item: second, isLast: true),
            ],
          ),
        ),
      ),
    );
    await tester.pump();

    expect(find.byType(ShareInteractionRow), findsNWidgets(2));
    expect(find.text(first.shareText), findsOneWidget);
    expect(find.text(second.shareText), findsOneWidget);
    expect(
      tester.widget<Text>(find.text(first.shareText)).maxLines,
      2,
      reason: '附言必须截断在两行',
    );
  });

  // GWT-003.t1：图片 aspectFill、视频封面加播放图标、文本与讨论最多两行。
  testWidgets('三类可用预览各自遵守自己的呈现契约', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        child: CupertinoApp(
          home: CupertinoPageScaffold(
            child: Column(
              children: <Widget>[
                ShareTargetPreview(
                  item: _item(
                    ShareInteractionDirection.received,
                    previewKind: SharePreviewKind.image,
                    previewImageUrl: 'https://example.invalid/cover.webp',
                  ),
                ),
                ShareTargetPreview(
                  item: _item(
                    ShareInteractionDirection.initiated,
                    previewKind: SharePreviewKind.video,
                    previewImageUrl: 'https://example.invalid/poster.webp',
                  ),
                ),
                ShareTargetPreview(
                  item: _item(
                    ShareInteractionDirection.received,
                    targetKind: ShareTargetKind.discussion,
                    previewKind: SharePreviewKind.discussion,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
    await tester.pump();

    final images = tester.widgetList<AppCachedNetworkImage>(
      find.byType(AppCachedNetworkImage),
    );
    expect(images, hasLength(2));
    for (final image in images) {
      expect(image.fit, BoxFit.cover, reason: '预览必须 aspectFill 而不是拉伸');
    }
    expect(find.byIcon(CupertinoIcons.play_fill), findsOneWidget);
    final discussion = tester.widget<Text>(find.text('川西晨光'));
    expect(discussion.maxLines, 2);
  });

  // GWT-003.t2
  testWidgets('四种目标失效状态均降级为明确文本', (tester) async {
    const cases = <ShareTargetAvailability, String>{
      ShareTargetAvailability.deleted: ProfileText.profileShareDeleted,
      ShareTargetAvailability.private: ProfileText.profileSharePrivate,
      ShareTargetAvailability.reviewing: ProfileText.profileShareReviewing,
      ShareTargetAvailability.authorDeactivated:
          ProfileText.profileShareAuthorDeactivated,
    };
    await tester.pumpWidget(
      CupertinoApp(
        home: CupertinoPageScaffold(
          child: Column(
            children: cases.keys
                .map(
                  (availability) => ShareTargetPreview(
                    item: _item(
                      ShareInteractionDirection.received,
                      availability: availability,
                    ),
                  ),
                )
                .toList(growable: false),
          ),
        ),
      ),
    );
    for (final text in cases.values) {
      expect(find.text(text), findsOneWidget);
    }
  });
}

String _repositoryRoot() {
  final cwd = Directory.current;
  return cwd.path.endsWith('quwoquan_app') ? cwd.parent.path : cwd.path;
}

ShareInteractionItem _item(
  ShareInteractionDirection direction, {
  ShareTargetAvailability availability = ShareTargetAvailability.active,
  ShareTargetKind targetKind = ShareTargetKind.record,
  SharePreviewKind? previewKind,
  String previewImageUrl = '',
  String? impactPrimaryText,
  String? impactDeepLink,
}) {
  return ShareInteractionItem(
    interactionId: direction == ShareInteractionDirection.received
        ? 'share-received'
        : 'share-initiated',
    direction: direction,
    displayPersonaId: 'fixture_user_photo',
    displayName: '纸上旅行',
    displayAvatarUrl: '',
    targetPersonaId: 'fixture_user_current',
    targetContentId: 'fixture_photo_001',
    targetContentType: 'image',
    targetSummary: '川西晨光',
    targetKind: targetKind,
    targetAvailability: availability,
    targetReplyCount: 0,
    previewKind:
        previewKind ??
        (availability == ShareTargetAvailability.active
            ? SharePreviewKind.text
            : SharePreviewKind.unavailable),
    previewImageUrl: previewImageUrl,
    previewText: '川西晨光',
    outboundShareEventId: 'outbound-event-${direction.name}',
    shareText: '读完想再走一次。',
    impactPrimaryText: impactPrimaryText ?? '带来 3 次新浏览',
    impactDeepLink: impactDeepLink ?? 'myIntersections',
    occurredAt: DateTime(2026, 7, 12, 8),
  );
}

/// 服务端投影的最小 fixture：只固定 `fromActivity` 按方向解析身份所需的三个字段，
/// 其余取契约允许的空值，免得断言被无关字段的默认值带偏。
ProfileInteractionActivityViewData _activity({
  String counterpartPersonaId = 'counterpart-persona',
  String targetAvailability = 'active',
}) {
  return ProfileInteractionActivityViewData(
    activityId: 'activity-1',
    activityType: 'share',
    direction: 'received',
    commentKind: 'none',
    commentId: '',
    parentCommentId: '',
    actorPersonaId: 'actor-persona',
    actorDisplayName: '纸上旅行',
    actorAvatarUrl: '',
    counterpartPersonaId: counterpartPersonaId,
    targetPersonaId: 'target-persona',
    targetContentId: 'target-content',
    targetContentType: 'image',
    targetContentSummary: '川西晨光',
    targetAvailability: targetAvailability,
    displayPersonaId: 'ignored-by-fromactivity',
    displayName: '纸上旅行',
    displayAvatarUrl: '',
    displayUserRouteId: 'userProfile',
    primaryText: '转发互动',
    contextText: '读完想再走一次。',
    previewMediaKind: 'text',
    previewImageUrl: '',
    previewText: '川西晨光',
    previewUnavailable: false,
    previewObjectId: 'target-content',
    previewRouteId: 'workBrowser',
    shareText: '读完想再走一次。',
    filterKeys: const <String>['shares'],
    createdAt: DateTime.utc(2026, 7, 12),
    occurredAt: DateTime.utc(2026, 7, 12),
  );
}
