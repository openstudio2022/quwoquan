import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle_membership/application/public/circle_membership_ports.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle_post_placement/application/public/circle_post_placement_commands.dart';
import 'package:quwoquan_app/service/content_service/content/outbound_share_fact/application/public/content_outbound_share_appender.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_surface_view.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/content_share_actions.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/content_share_sheet.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/content_share_template.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/more_action_popup/media_post_config.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/more_action_popup/more_action_popup.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';

/// Runtime composition boundary for Work Browser actions that combine several
/// business objects. Media presentation consumes only this runtime-owned API.
abstract final class WorksViewerContentActionsComposition {
  static Future<void> showShareSheet(
    BuildContext context, {
    required ContentSurfaceView surfaceView,
    required bool enableIdentityTemplate,
    required String visibility,
    required CirclePostPlacementCommands circlePostPlacementWriter,
    required CircleMembershipQueries circleMembershipQuery,
    required ContentOutboundShareAppender outboundShareWriter,
    required Future<void> Function(String actionId) onActionCompleted,
  }) {
    return ContentShareSheet.show(
      context,
      template: _shareTemplate(
        surfaceView: surfaceView,
        enableIdentityTemplate: enableIdentityTemplate,
        visibility: visibility,
      ),
      circlePostPlacementWriter: circlePostPlacementWriter,
      circleMembershipQuery: circleMembershipQuery,
      outboundShareWriter: outboundShareWriter,
      onActionCompleted: (result) => onActionCompleted(result.actionId),
    );
  }

  static Future<WorksViewerShareResult> copyLink(
    BuildContext context, {
    required ContentSurfaceView surfaceView,
    required bool enableIdentityTemplate,
    required String visibility,
  }) async {
    final result = await const DefaultContentShareActionHandler().execute(
      context,
      _shareTemplate(
        surfaceView: surfaceView,
        enableIdentityTemplate: enableIdentityTemplate,
        visibility: visibility,
      ),
      const ContentShareAction(id: 'copy_link', label: FoundationText.copyLink),
    );
    return WorksViewerShareResult(
      actionId: result.actionId,
      success: result.success,
    );
  }

  static Future<void> showMoreActions(
    BuildContext context, {
    required WorksViewerMoreActionsConfig config,
  }) {
    return MoreActionPopup.show(
      context: context,
      config: MediaPostMoreActionConfig(
        showShareAction: config.showShareAction,
        showViewOriginalAction: config.showViewOriginalAction,
        onCopyLink: config.onCopyLink,
        onViewOriginal: config.onViewOriginal,
        onThemeToggle: config.onThemeToggle,
        onNotInterested: config.onNotInterested,
        onBlockUser: config.onBlockUser,
        onBlockWords: config.onBlockWords,
        onReport: config.onReport,
        onShare: config.onShare,
        showDeleteAction: config.showDeleteAction,
        onDelete: config.onDelete,
        onActionInvoked: config.onActionInvoked,
        filterOptions: [
          for (final option in config.filterOptions)
            MoreActionFilterOption(id: option.id, label: option.label),
        ],
        selectedFilterIds: config.selectedFilterIds,
        onFilterSelectionChanged: config.onFilterSelectionChanged,
        readingOptions: [
          for (final option in config.readingOptions)
            MoreActionReadingOption(id: option.id, label: option.label),
        ],
        selectedReadingOptionId: config.selectedReadingOptionId,
        onReadingOptionChanged: config.onReadingOptionChanged,
        forceDarkAppearance: config.forceDarkAppearance,
      ),
    );
  }

  static ContentShareTemplate _shareTemplate({
    required ContentSurfaceView surfaceView,
    required bool enableIdentityTemplate,
    required String visibility,
  }) {
    return ContentShareTemplateBuilder.build(
      surfaceView: surfaceView,
      enableIdentityTemplate: enableIdentityTemplate,
      visibility: visibility,
    );
  }
}

final class WorksViewerShareResult {
  const WorksViewerShareResult({required this.actionId, required this.success});

  final String actionId;
  final bool success;
}

final class WorksViewerMoreActionOption {
  const WorksViewerMoreActionOption({required this.id, required this.label});

  final String id;
  final String label;
}

final class WorksViewerMoreActionsConfig {
  const WorksViewerMoreActionsConfig({
    this.showShareAction = false,
    this.showViewOriginalAction = false,
    this.onCopyLink,
    this.onViewOriginal,
    this.onThemeToggle,
    this.onNotInterested,
    this.onBlockUser,
    this.onBlockWords,
    this.onReport,
    this.onShare,
    this.showDeleteAction = false,
    this.onDelete,
    this.onActionInvoked,
    this.filterOptions = const <WorksViewerMoreActionOption>[],
    this.selectedFilterIds = const <String>[],
    this.onFilterSelectionChanged,
    this.readingOptions = const <WorksViewerMoreActionOption>[],
    this.selectedReadingOptionId,
    this.onReadingOptionChanged,
    this.forceDarkAppearance = false,
  });

  final bool showShareAction;
  final bool showViewOriginalAction;
  final VoidCallback? onCopyLink;
  final VoidCallback? onViewOriginal;
  final VoidCallback? onThemeToggle;
  final VoidCallback? onNotInterested;
  final VoidCallback? onBlockUser;
  final VoidCallback? onBlockWords;
  final VoidCallback? onReport;
  final VoidCallback? onShare;
  final bool showDeleteAction;
  final VoidCallback? onDelete;
  final ValueChanged<String>? onActionInvoked;
  final List<WorksViewerMoreActionOption> filterOptions;
  final List<String> selectedFilterIds;
  final ValueChanged<Set<String>>? onFilterSelectionChanged;
  final List<WorksViewerMoreActionOption> readingOptions;
  final String? selectedReadingOptionId;
  final ValueChanged<String>? onReadingOptionChanged;
  final bool forceDarkAppearance;
}
