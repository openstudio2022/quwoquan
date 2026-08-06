import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/public/gathering_board_ports.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/feedback/app_request_feedback.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/l10n/copy/chat_text_constants.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_semantics.dart';

part 'gathering_board_page_widgets.dart';

/// 活动群聊内的 typed 只读看板。
///
/// 页面不注册路由，也不拥有任何业务写状态；所有数据来自注入的
/// [GatheringBoardQuery]，操作只交给 owner navigation callback。
class GatheringBoardPage extends StatefulWidget {
  const GatheringBoardPage({
    super.key,
    required this.conversationId,
    required this.query,
    required this.onBack,
    this.navigation = const GatheringBoardNavigationCallbacks(),
  });

  final String conversationId;
  final GatheringBoardQuery query;
  final VoidCallback onBack;
  final GatheringBoardNavigationCallbacks navigation;

  @override
  State<GatheringBoardPage> createState() => _GatheringBoardPageState();
}

class _GatheringBoardPageState extends State<GatheringBoardPage> {
  late Future<GatheringBoardSnapshot> _snapshot;

  GatheringBoardQueryRequest get _request =>
      GatheringBoardQueryRequest(conversationId: widget.conversationId);

  @override
  void initState() {
    super.initState();
    _snapshot = widget.query.load(_request);
  }

  @override
  void didUpdateWidget(covariant GatheringBoardPage oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (!identical(oldWidget.query, widget.query) ||
        oldWidget.conversationId != widget.conversationId) {
      _snapshot = widget.query.load(_request);
    }
  }

  void _reload() {
    setState(() => _snapshot = widget.query.load(_request));
  }

  void _open(
    GatheringBoardTargetNavigation? navigation,
    GatheringBoardSnapshot snapshot,
  ) {
    if (navigation != null) {
      unawaited(
        navigation(
          GatheringBoardNavigationTarget(
            gatheringId: snapshot.activity.gatheringId,
            conversationId: widget.conversationId,
          ),
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final pageBackground = AppColorsFunctional.getColor(
      isDark,
      ColorType.pageBackground,
    );

    return CupertinoPageScaffold(
      backgroundColor: pageBackground,
      navigationBar: CupertinoNavigationBar(
        backgroundColor: AppColorsFunctional.getColor(
          isDark,
          ColorType.surfaceElevated,
        ),
        border: Border(
          bottom: BorderSide(
            color: AppColorsFunctional.getColor(
              isDark,
              ColorType.separatorSubtle,
            ),
            width: AppSpacing.hairline,
          ),
        ),
        leading: CupertinoButton(
          padding: EdgeInsets.zero,
          minimumSize: const Size(
            AppSpacing.minInteractiveSize,
            AppSpacing.minInteractiveSize,
          ),
          onPressed: widget.onBack,
          child: const Icon(CupertinoIcons.chevron_back),
        ),
        middle: Text(ChatText.groupCapabilityActivity),
      ),
      child: SafeArea(
        top: false,
        child: FutureBuilder<GatheringBoardSnapshot>(
          future: _snapshot,
          builder: (context, snapshot) {
            if (snapshot.connectionState != ConnectionState.done) {
              return Center(child: AppRequestFeedback.section());
            }
            if (snapshot.hasError) {
              return AppPageErrorState(
                semantic: runtimeErrorSemantic(
                  context,
                  error: snapshot.error!,
                  category: UiErrorCategory.pageLoad,
                  scope: UiErrorScope.page,
                ),
                onRecovery: (action) async {
                  if (action.type == UiErrorActionType.retry ||
                      action.type == UiErrorActionType.resubmit) {
                    _reload();
                    return UiRecoveryOutcome.superseded;
                  }
                  return UiRecoveryOutcome.cancelled;
                },
              );
            }
            if (!snapshot.hasData) {
              return Center(child: AppRequestFeedback.section());
            }
            return _buildBoard(context, isDark, snapshot.requireData);
          },
        ),
      ),
    );
  }

  Widget _buildBoard(
    BuildContext context,
    bool isDark,
    GatheringBoardSnapshot snapshot,
  ) {
    final activity = snapshot.activity;
    final chat = snapshot.chat;
    final announcement = chat.pinnedAnnouncement;
    final foregroundSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );

    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(
          maxWidth: AppSpacing.feedMaxContentWidth,
        ),
        child: ListView(
          key: const ValueKey<String>('gathering-board-sections'),
          padding: EdgeInsets.all(AppSpacing.containerMd),
          children: [
            _GatheringBoardActivityHeader(
              activity: activity,
              access: chat.access,
              foregroundSecondary: foregroundSecondary,
              isDark: isDark,
            ),
            SizedBox(height: AppSpacing.interGroupMd),
            _GatheringBoardSectionCard(
              sectionKey: const ValueKey<String>(
                'gathering-board-announcement',
              ),
              title: ChatText.groupAnnouncement,
              icon: CupertinoIcons.speaker_2,
              isDark: isDark,
              onOpen: widget.navigation.openAnnouncement == null
                  ? null
                  : () => _open(widget.navigation.openAnnouncement, snapshot),
              children: [
                Text(
                  announcement?.content ?? ChatText.groupAnnouncementEmpty,
                  style: _boardBodyStyle(isDark),
                ),
                if (announcement != null &&
                    announcement.updatedBy.trim().isNotEmpty) ...[
                  SizedBox(height: AppSpacing.intraGroupSm),
                  Text(
                    announcement.updatedBy,
                    style: _boardSecondaryStyle(isDark),
                  ),
                ],
              ],
            ),
            SizedBox(height: AppSpacing.interGroupMd),
            _GatheringBoardSectionCard(
              sectionKey: const ValueKey<String>('gathering-board-plan'),
              title: CreationText.homepageTypeRoute,
              icon: CupertinoIcons.map,
              isDark: isDark,
              children: [
                _GatheringBoardCapabilityRow(
                  capability: snapshot.plan.capability,
                  icon: CupertinoIcons.list_bullet,
                  isDark: isDark,
                  onOpen:
                      snapshot.plan.capability.isAvailable &&
                          widget.navigation.openPlan != null
                      ? () => _open(widget.navigation.openPlan, snapshot)
                      : null,
                ),
                for (final item in snapshot.plan.items)
                  _GatheringBoardPlanItemRow(item: item, isDark: isDark),
                _GatheringBoardCapabilityRow(
                  capability: snapshot.mapCapability,
                  icon: CupertinoIcons.location,
                  isDark: isDark,
                  onOpen:
                      snapshot.mapCapability.isAvailable &&
                          widget.navigation.openMap != null
                      ? () => _open(widget.navigation.openMap, snapshot)
                      : null,
                ),
              ],
            ),
            SizedBox(height: AppSpacing.interGroupMd),
            _GatheringBoardSectionCard(
              sectionKey: const ValueKey<String>('gathering-board-calendar'),
              title: snapshot.calendarCapability.summaryLabel,
              icon: CupertinoIcons.calendar,
              isDark: isDark,
              children: [
                _GatheringBoardCapabilityRow(
                  capability: snapshot.calendarCapability,
                  icon: CupertinoIcons.check_mark_circled,
                  isDark: isDark,
                  onOpen:
                      snapshot.calendarCapability.isAvailable &&
                          widget.navigation.openCalendar != null
                      ? () => _open(widget.navigation.openCalendar, snapshot)
                      : null,
                ),
              ],
            ),
            SizedBox(height: AppSpacing.interGroupMd),
            _GatheringBoardAssetsSection(
              assets: chat.assets,
              isDark: isDark,
              onOpenAsset: widget.navigation.openAsset,
            ),
            SizedBox(height: AppSpacing.interGroupMd),
            _GatheringBoardSectionCard(
              sectionKey: const ValueKey<String>('gathering-board-members'),
              title: ChatText.groupCapabilityMembers,
              icon: CupertinoIcons.person_3,
              isDark: isDark,
              onOpen: widget.navigation.openMembers == null
                  ? null
                  : () => _open(widget.navigation.openMembers, snapshot),
              children: [
                Text(
                  snapshot.participation.summaryLabel,
                  style: _boardBodyStyle(isDark),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
