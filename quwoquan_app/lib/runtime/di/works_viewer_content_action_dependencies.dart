import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle_membership/application/public/circle_membership_ports.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle_post_placement/application/public/circle_post_placement_commands.dart';
import 'package:quwoquan_app/service/content_service/content/outbound_share_fact/application/public/content_outbound_share_appender.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_surface_view.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/works_viewer_content_actions.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/application/public/works_viewer_content_action_contract.dart';

/// Typed composition binding for Media actions implemented by Post.
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
    return PostWorksViewerContentActions.showShareSheet(
      context,
      surfaceView: surfaceView,
      enableIdentityTemplate: enableIdentityTemplate,
      visibility: visibility,
      circlePostPlacementWriter: circlePostPlacementWriter,
      circleMembershipQuery: circleMembershipQuery,
      outboundShareWriter: outboundShareWriter,
      onActionCompleted: onActionCompleted,
    );
  }

  static Future<WorksViewerShareResult> copyLink(
    BuildContext context, {
    required ContentSurfaceView surfaceView,
    required bool enableIdentityTemplate,
    required String visibility,
  }) {
    return PostWorksViewerContentActions.copyLink(
      context,
      surfaceView: surfaceView,
      enableIdentityTemplate: enableIdentityTemplate,
      visibility: visibility,
    );
  }

  static Future<void> showMoreActions(
    BuildContext context, {
    required WorksViewerMoreActionsConfig config,
  }) {
    return PostWorksViewerContentActions.showMoreActions(
      context,
      config: config,
    );
  }
}
