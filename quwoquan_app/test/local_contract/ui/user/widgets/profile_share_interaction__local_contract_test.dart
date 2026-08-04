// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/owner-persona-homepage-unification/spec.md#gwt-001
// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/owner-persona-homepage-unification/spec.md#gwt-002
// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/owner-persona-homepage-unification/spec.md#gwt-003
// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/owner-persona-homepage-unification/spec.md#gwt-006
import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/user/generated/user_profile_ui_config.g.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/user/account/user_account/domain/profile_mode.dart';
import 'package:quwoquan_app/ui/user/models/profile_tab.dart';
import 'package:quwoquan_app/ui/user/models/share_interaction_models.dart';
import 'package:quwoquan_app/ui/user/providers/profile_state_provider.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_interaction_tab.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_secondary_tab_bar.dart';
import 'package:quwoquan_app/ui/user/widgets/share_interaction/share_empty_state.dart';
import 'package:quwoquan_app/ui/user/widgets/share_interaction/share_interaction_row.dart';
import 'package:quwoquan_app/ui/user/widgets/share_interaction/share_target_preview.dart';
import '../../../../support/cloud_services/repository_mock_reexports.dart';
import '../../../../support/fakes/test_profile_interaction_facets.dart';

void main() {
  test('互动 metadata 移除全部、点赞默认且转发仅本人可见', () {
    final tabs = UserProfileUIConfig.interactionSubTabs;
    expect(tabs.map((tab) => tab.id), <String>['likes', 'comments', 'shares']);
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
          child: ShareEmptyState(
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
          child: ShareEmptyState(
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

ShareInteractionItem _item(
  ShareInteractionDirection direction, {
  ShareTargetAvailability availability = ShareTargetAvailability.active,
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
