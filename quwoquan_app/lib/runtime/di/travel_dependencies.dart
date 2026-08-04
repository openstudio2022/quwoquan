import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/application/travel/trip_collaboration_facet.dart';
import 'package:quwoquan_app/application/travel/trip_content_link_facet.dart';
import 'package:quwoquan_app/application/travel/trip_guide_assignment_facet.dart';
import 'package:quwoquan_app/application/travel/trip_journey_query.dart';
import 'package:quwoquan_app/application/travel/trip_moment_facet.dart';
import 'package:quwoquan_app/application/travel/trip_plan_creation_facet.dart';
import 'package:quwoquan_app/application/travel/trip_plan_directory.dart';
import 'package:quwoquan_app/application/travel/trip_plan_revision_facet.dart';
import 'package:quwoquan_app/application/travel/trip_share_facet.dart';
import 'package:quwoquan_app/application/travel/trip_template_facet.dart';
import 'package:quwoquan_app/cloud/remote/travel/trip_collaboration_remote.dart';
import 'package:quwoquan_app/cloud/remote/travel/trip_content_link_remote.dart';
import 'package:quwoquan_app/cloud/remote/travel/trip_guide_assignment_remote.dart';
import 'package:quwoquan_app/cloud/remote/travel/trip_journey_query_remote.dart';
import 'package:quwoquan_app/cloud/remote/travel/trip_moment_remote.dart';
import 'package:quwoquan_app/cloud/remote/travel/trip_plan_creation_remote.dart';
import 'package:quwoquan_app/cloud/remote/travel/trip_plan_directory_remote.dart';
import 'package:quwoquan_app/cloud/remote/travel/trip_plan_revision_remote.dart';
import 'package:quwoquan_app/cloud/remote/travel/trip_share_remote.dart';
import 'package:quwoquan_app/cloud/remote/travel/trip_template_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// travel domain 的唯一 production 装配入口。
///
/// 只有本文件可以命名 `Remote*` 实现；Provider 侧只声明 typed port 返回值。
final class TravelProductionComposition {
  const TravelProductionComposition._();

  static TripGuideAssignmentFacet tripGuideAssignmentFacet({
    required GeneratedCloudOperationClient client,
    required TripGuideInvocationContextFactory invocationContext,
  }) {
    return RemoteTripGuideAssignmentFacet(
      client: client,
      invocationContext: invocationContext,
    );
  }

  static TripCollaborationFacet tripCollaborationFacet({
    required GeneratedCloudOperationClient client,
    required TripShareInvocationContextFactory invocationContext,
  }) {
    return RemoteTripCollaborationFacet(
      client: client,
      invocationContext: invocationContext,
    );
  }

  static TripContentLinkFacet tripContentLinkFacet({
    required GeneratedCloudOperationClient client,
    required TripShareInvocationContextFactory invocationContext,
  }) {
    return RemoteTripContentLinkFacet(
      client: client,
      invocationContext: invocationContext,
    );
  }

  static TripPlanDirectory tripPlanDirectory({
    required GeneratedCloudOperationClient client,
    required TravelInvocationContextFactory invocationContext,
  }) {
    return RemoteTripPlanDirectory(
      client: client,
      invocationContext: invocationContext,
    );
  }

  static TripPlanCreationFacet tripPlanCreationFacet({
    required GeneratedCloudOperationClient client,
    required TripShareInvocationContextFactory invocationContext,
  }) {
    return RemoteTripPlanCreationFacet(
      client: client,
      invocationContext: invocationContext,
    );
  }

  static TripPlanRevisionFacet tripPlanRevisionFacet({
    required GeneratedCloudOperationClient client,
    required TripShareInvocationContextFactory invocationContext,
  }) {
    return RemoteTripPlanRevisionFacet(
      client: client,
      invocationContext: invocationContext,
    );
  }

  static TripMomentFacet tripMomentFacet({
    required GeneratedCloudOperationClient client,
    required TripMomentInvocationContextFactory invocationContext,
  }) {
    return RemoteTripMomentFacet(
      client: client,
      invocationContext: invocationContext,
    );
  }

  static TripJourneyQuery travelJourneyQuery({
    required GeneratedCloudOperationClient client,
    required AppUiSurface surface,
    required TravelInvocationContextFactory invocationContext,
  }) {
    return RemoteTripJourneyQuery(
      client: client,
      surface: surface,
      invocationContext: invocationContext,
    );
  }

  static TripShareFacet tripShareFacet({
    required GeneratedCloudOperationClient client,
    required TripShareInvocationContextFactory invocationContext,
  }) {
    return RemoteTripShareFacet(
      client: client,
      invocationContext: invocationContext,
    );
  }

  static TripTemplateFacet tripTemplateFacet({
    required GeneratedCloudOperationClient client,
    required TripShareInvocationContextFactory invocationContext,
  }) {
    return RemoteTripTemplateFacet(
      client: client,
      invocationContext: invocationContext,
    );
  }
}
