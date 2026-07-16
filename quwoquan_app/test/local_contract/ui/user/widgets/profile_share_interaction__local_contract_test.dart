import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/services/user/user_profile_repository.dart';
import 'package:quwoquan_app/cloud/user/generated/user_profile_ui_config.g.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/user/models/profile_mode.dart';
import 'package:quwoquan_app/ui/user/models/profile_tab.dart';
import 'package:quwoquan_app/ui/user/models/share_interaction_models.dart';
import 'package:quwoquan_app/ui/user/providers/profile_state_provider.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_interaction_tab.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_secondary_tab_bar.dart';
import 'package:quwoquan_app/ui/user/widgets/share_interaction/share_empty_state.dart';
import 'package:quwoquan_app/ui/user/widgets/share_interaction/share_interaction_row.dart';
import 'package:quwoquan_app/ui/user/widgets/share_interaction/share_target_preview.dart';

void main() {
  test('互动 metadata 移除全部、点赞默认且转发仅本人可见', () {
    final tabs = UserProfileUIConfig.interactionSubTabs;
    expect(tabs.map((tab) => tab.id), <String>[
      'likes',
      'comments',
      'shares',
      'views',
    ]);
    expect(tabs.singleWhere((tab) => tab.id == 'likes').isDefault, isTrue);
    final shares = tabs.singleWhere((tab) => tab.id == 'shares');
    expect(shares.visibleInMode('mine'), isTrue);
    expect(shares.visibleInMode('other'), isFalse);
  });

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
          userProfileRepositoryProvider.overrideWithValue(
            const MockUserProfileRepository(),
          ),
        ],
        child: const CupertinoApp(
          home: CupertinoPageScaffold(
            child: ProfileInteractionTab(
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
      tester.element(find.byType(ProfileInteractionTab)),
    );
    container
        .read(profileNotifierProvider('fixture_user_current').notifier)
        .setInteractionSubTab(InteractionSubTab.shares);
    await tester.pump();

    expect(find.text(UITextConstants.interactionSubAll), findsNothing);
    expect(find.text(UITextConstants.interactionSubShares), findsOneWidget);
    expect(
      find.text(UITextConstants.profileInteractionDirectionReceived),
      findsOneWidget,
    );
    expect(
      find.text(UITextConstants.profileInteractionDirectionSent),
      findsOneWidget,
    );
    final switchFinder = find.byKey(
      const ValueKey<String>('profile-interaction-direction-switch'),
    );
    expect(switchFinder, findsOneWidget);
    expect(
      find.ancestor(
        of: switchFinder,
        matching: find.byType(ProfileSecondaryTabBar),
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
      find.text(UITextConstants.profileShareReceivedRecordAction),
      findsOneWidget,
    );
    expect(
      find.text(
        '${UITextConstants.profileShareInitiatedRecordPrefix} 纸上旅行${UITextConstants.profileShareInitiatedRecordSuffix}',
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
          child: ShareEmptyState(
            direction: ShareInteractionDirection.received,
            onAction: () {},
          ),
        ),
      ),
    );
    expect(
      find.text(UITextConstants.profileShareReceivedEmptyTitle),
      findsOneWidget,
    );

    await tester.pumpWidget(
      CupertinoApp(
        home: CupertinoPageScaffold(
          child: ShareEmptyState(
            direction: ShareInteractionDirection.initiated,
            onAction: () {},
          ),
        ),
      ),
    );
    expect(
      find.text(UITextConstants.profileShareInitiatedEmptyTitle),
      findsOneWidget,
    );
    expect(find.text(UITextConstants.profileInteractionEmpty), findsNothing);
  });

  testWidgets('四种目标失效状态均降级为明确文本', (tester) async {
    const cases = <ShareTargetAvailability, String>{
      ShareTargetAvailability.deleted: UITextConstants.profileShareDeleted,
      ShareTargetAvailability.private: UITextConstants.profileSharePrivate,
      ShareTargetAvailability.reviewing: UITextConstants.profileShareReviewing,
      ShareTargetAvailability.authorDeactivated:
          UITextConstants.profileShareAuthorDeactivated,
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

ShareInteractionItem _item(
  ShareInteractionDirection direction, {
  ShareTargetAvailability availability = ShareTargetAvailability.active,
}) {
  return ShareInteractionItem(
    interactionId: direction == ShareInteractionDirection.received
        ? 'share-received'
        : 'share-initiated',
    direction: direction,
    displaySubAccountId: 'fixture_user_photo',
    displayName: '纸上旅行',
    displayAvatarUrl: '',
    targetSubAccountId: 'fixture_user_current',
    targetContentId: 'fixture_photo_001',
    targetContentType: 'image',
    targetSummary: '川西晨光',
    targetKind: ShareTargetKind.record,
    targetAvailability: availability,
    targetReplyCount: 0,
    previewKind: availability == ShareTargetAvailability.active
        ? SharePreviewKind.text
        : SharePreviewKind.unavailable,
    previewImageUrl: '',
    previewText: '川西晨光',
    outboundShareEventId: 'outbound-event-${direction.name}',
    shareText: '读完想再走一次。',
    impactPrimaryText: direction == ShareInteractionDirection.received
        ? '带来 3 次新浏览'
        : '',
    impactDeepLink: direction == ShareInteractionDirection.received
        ? 'myIntersections'
        : '',
    occurredAt: DateTime(2026, 7, 12, 8),
  );
}
