import 'package:quwoquan_app/cloud/remote/circle/behavior_fact/behavior_fact_remote.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/application/travel/trip_guide_assignment_facet.dart';
import 'package:quwoquan_app/application/travel/trip_collaboration_facet.dart';
import 'package:quwoquan_app/application/travel/trip_content_link_facet.dart';
import 'package:quwoquan_app/application/travel/trip_journey_query.dart';
import 'package:quwoquan_app/application/travel/trip_moment_facet.dart';
import 'package:quwoquan_app/application/travel/trip_plan_creation_facet.dart';
import 'package:quwoquan_app/application/travel/trip_plan_directory.dart';
import 'package:quwoquan_app/application/travel/trip_plan_revision_facet.dart';
import 'package:quwoquan_app/application/travel/trip_share_facet.dart';
import 'package:quwoquan_app/application/travel/trip_template_facet.dart';
import 'package:quwoquan_app/cloud/remote/circle/circle/circle_lifecycle_remote.dart';
import 'package:quwoquan_app/cloud/remote/circle/circle/circle_query_remote.dart';
import 'package:quwoquan_app/cloud/remote/circle/file/file_remote.dart';
import 'package:quwoquan_app/cloud/remote/circle/group/group_remote.dart';
import 'package:quwoquan_app/cloud/remote/circle/membership/membership_remote.dart';
import 'package:quwoquan_app/cloud/remote/circle/post_placement/post_placement_remote.dart';
import 'package:quwoquan_app/cloud/remote/content/filter_catalog/filter_catalog_remote.dart';
import 'package:quwoquan_app/cloud/remote/content/media/content_media_remote.dart';
import 'package:quwoquan_app/cloud/remote/content/media/content_media_object_uploader.dart';
import 'package:quwoquan_app/cloud/remote/content/outbound_share/outbound_share_remote.dart';
import 'package:quwoquan_app/cloud/remote/content/post/author_impact_remote.dart';
import 'package:quwoquan_app/cloud/remote/content/post/content_app_config_remote.dart';
import 'package:quwoquan_app/cloud/remote/content/post/content_behavior_remote.dart';
import 'package:quwoquan_app/cloud/remote/content/post/post_delete_remote.dart';
import 'package:quwoquan_app/cloud/remote/content/post/post_publication_remote.dart';
import 'package:quwoquan_app/cloud/remote/content/profile_interaction/profile_interaction_remote.dart';
import 'package:quwoquan_app/cloud/remote/content/report/report_query_remote.dart';
import 'package:quwoquan_app/cloud/remote/entity/homepage/homepage_command_remote.dart';
import 'package:quwoquan_app/cloud/remote/entity/homepage_review/homepage_review_remote.dart';
import 'package:quwoquan_app/cloud/remote/notification/incoming_call/incoming_call_presentation_remote.dart';
import 'package:quwoquan_app/cloud/remote/rtc/call_session/call_lifecycle_remote.dart';
import 'package:quwoquan_app/cloud/remote/rtc/call_session/call_media_control_remote.dart';
import 'package:quwoquan_app/cloud/remote/rtc/call_session/call_participant_remote.dart';
import 'package:quwoquan_app/cloud/remote/rtc/call_session/call_query_remote.dart';
import 'package:quwoquan_app/cloud/remote/rtc/call_session/call_screen_share_remote.dart';
import 'package:quwoquan_app/cloud/remote/search/hot_query_remote.dart';
import 'package:quwoquan_app/cloud/remote/search/recent_search_remote.dart';
import 'package:quwoquan_app/cloud/remote/search/search_feedback_remote.dart';
import 'package:quwoquan_app/cloud/remote/search/search_query_remote.dart';
import 'package:quwoquan_app/cloud/remote/tag/tag_feedback_fact_remote.dart';
import 'package:quwoquan_app/cloud/remote/travel/trip_guide_assignment_remote.dart';
import 'package:quwoquan_app/cloud/remote/travel/trip_collaboration_remote.dart';
import 'package:quwoquan_app/cloud/remote/travel/trip_content_link_remote.dart';
import 'package:quwoquan_app/cloud/remote/travel/trip_journey_query_remote.dart';
import 'package:quwoquan_app/cloud/remote/travel/trip_moment_remote.dart';
import 'package:quwoquan_app/cloud/remote/travel/trip_plan_creation_remote.dart';
import 'package:quwoquan_app/cloud/remote/travel/trip_plan_directory_remote.dart';
import 'package:quwoquan_app/cloud/remote/travel/trip_plan_revision_remote.dart';
import 'package:quwoquan_app/cloud/remote/travel/trip_share_remote.dart';
import 'package:quwoquan_app/cloud/remote/travel/trip_template_remote.dart';
import 'package:quwoquan_app/cloud/remote/user/account/account_lifecycle_remote.dart';
import 'package:quwoquan_app/cloud/remote/user/account_session/account_session_remote.dart';
import 'package:quwoquan_app/cloud/remote/user/authentication_challenge/authentication_challenge_remote.dart';
import 'package:quwoquan_app/cloud/remote/user/credential_binding/credential_binding_remote.dart';
import 'package:quwoquan_app/cloud/remote/user/device_registration/device_push_endpoint_remote.dart';
import 'package:quwoquan_app/cloud/remote/user/following_subject/following_subject_remote.dart';
import 'package:quwoquan_app/cloud/remote/user/greeting_request/greeting_request_remote.dart';
import 'package:quwoquan_app/cloud/remote/user/persona/persona_query_remote.dart';
import 'package:quwoquan_app/cloud/remote/user/persona/persona_remote.dart';
import 'package:quwoquan_app/cloud/remote/user/persona_relationship/persona_relationship_follow_remote.dart';
import 'package:quwoquan_app/cloud/remote/user/persona_relationship/persona_relationship_remote.dart';
import 'package:quwoquan_app/cloud/remote/user/profile/profile_edit_query_remote.dart';
import 'package:quwoquan_app/cloud/remote/user/profile/profile_query_remote.dart';
import 'package:quwoquan_app/cloud/remote/user/profile/user_profile_query_remote.dart';
import 'package:quwoquan_app/cloud/remote/user/profile_update_proposal/profile_update_proposal_remote.dart';
import 'package:quwoquan_app/cloud/remote/user/subject_follow/subject_follow_remote.dart';
import 'package:quwoquan_app/cloud/remote/user/user_settings/user_settings_remote.dart';
import 'package:quwoquan_app/cloud/remote/user/user_account/user_sync_remote.dart';
import 'package:quwoquan_app/cloud/services/content/remote/comment_facets_remote.dart';
import 'package:quwoquan_app/cloud/services/content/remote/discovery_feed_query_remote.dart';
import 'package:quwoquan_app/cloud/services/content/remote/footprint_query_remote.dart';
import 'package:quwoquan_app/cloud/services/content/remote/post_reader_remote.dart';
import 'package:quwoquan_app/cloud/services/content/remote/post_reaction_facets_remote.dart';
import 'package:quwoquan_app/cloud/services/content/remote/report_command_remote.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/cloud/services/entity/remote/homepage_query_remote.dart';
import 'package:quwoquan_app/cloud/services/integration/remote/location_query_remote.dart';
import 'package:quwoquan_app/cloud/services/integration/remote/connector_management_remote.dart';
import 'package:quwoquan_app/cloud/services/notification/remote/app_message_facets_remote.dart';
import 'package:quwoquan_app/cloud/services/ops/ops_visit_append_writer.dart';
import 'package:quwoquan_app/application/content/media/content_media_upload_coordinator.dart';
import 'package:quwoquan_app/application/content/post/post_publication_status_reader.dart';
import 'package:quwoquan_app/core/services/cache/cache_telemetry_sink.dart';
import 'package:quwoquan_app/core/services/cache/cached_content_post_reader.dart';
import 'package:quwoquan_app/core/services/cache/cached_content_repository.dart';
import 'package:quwoquan_app/core/services/cache/content_cache_services.dart';
import 'package:quwoquan_app/core/services/cache/user_profile_cache_service.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// Production Remote adapter kinds owned by the sole application composition
/// root. Provider libraries select a typed port only; they never name or
/// construct an adapter implementation.
enum AppProductionAdapter {
  appMessage,
  accountLifecycle,
  accountSession,
  authenticationChallenge,
  authorImpact,
  circleBehaviorFact,
  circleFile,
  circleGroup,
  circleLifecycle,
  circleMembership,
  circlePostPlacement,
  circleQuery,
  contentAppConfigQuery,
  contentComment,
  contentFootprint,
  contentMedia,
  contentOutboundShare,
  contentPostPublication,
  contentPostReader,
  contentPostReaction,
  contentProfileInteraction,
  contentBehaviorCommand,
  contentReportCommand,
  contentReportQuery,
  connectorManagement,
  credentialBindingCommand,
  credentialBindingQuery,
  devicePushEndpoint,
  filterCatalog,
  greetingRequest,
  homepageCommand,
  homepageQuery,
  homepageReview,
  incomingCallPresentation,
  locationQuery,
  opsVisitAppend,
  personaCommand,
  personaQuery,
  personaRelationship,
  personaRelationshipFollow,
  profileEditQuery,
  profileQuery,
  profileUpdateProposal,
  recentSearch,
  rtcCallLifecycle,
  rtcCallMediaControl,
  rtcCallParticipant,
  rtcCallQuery,
  rtcCallScreenShare,
  searchFeedback,
  searchHotQuery,
  searchQuery,
  followingSubject,
  subjectFollow,
  tagFeedback,
  userProfileQuery,
  userSettingsCommand,
  userSettingsQuery,
  userSync,
}

/// The only production owner for the content read/write/cache graph.
final class AppProductionContentFacets {
  const AppProductionContentFacets({
    required this.read,
    required this.postDeleteWriter,
    required this.behaviorWriter,
  });

  final ContentReadRepository read;
  final ContentPostDeleteCommandWriter postDeleteWriter;
  final ContentBehaviorCommandWriter behaviorWriter;
}

/// Read-only content facets sharing one generated adapter and its cache layer.
final class AppProductionContentPostReaderFacets {
  const AppProductionContentPostReaderFacets({
    required this.detail,
    required this.authorPosts,
    required this.publicationStatus,
    required this.wishlistState,
  });

  final ContentPostDetailReader detail;
  final ContentAuthorPostsReader authorPosts;
  final ContentPostPublicationStatusReader publicationStatus;
  final ContentEntityWishlistStateReader wishlistState;
}

/// Object-level FollowingSubject ports sharing one generated-client adapter.
final class AppProductionFollowingSubjectFacets {
  const AppProductionFollowingSubjectFacets({
    required this.query,
    required this.visitWriter,
  });

  final FollowingSubjectQuery query;
  final FollowedSubjectVisitCommandWriter visitWriter;
}

/// Centralizes every generated-client adapter construction. The `Object`
/// callback is intentionally unwrapped only inside this composition root:
/// every public caller has a typed port as its generic return type.
final class AppProductionComposition {
  const AppProductionComposition._();

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

  static AppProductionContentFacets contentFacets({
    required GeneratedCloudOperationClient client,
    required ContentDiscoveryFeedInvocationContextFactory invocationContext,
    required ContentPostDeleteInvocationContextFactory deleteInvocationContext,
    required Future<List<String>> Function() blockedKeywordsLoader,
    required PostObjectCacheService postCache,
    required ContentQuerySnapshotStore querySnapshotStore,
    required UserProfileCacheService userProfileCache,
    required CacheTelemetrySink telemetrySink,
  }) {
    final discoveryFeed = RemoteContentDiscoveryFeedQuery(
      client: client,
      invocationContext: invocationContext,
      blockedKeywordsLoader: blockedKeywordsLoader,
    );
    final remote = RemoteContentRepository(discoveryFeedQuery: discoveryFeed);
    final deleteWriter = RemoteContentPostDeleteCommandWriter(
      client: client,
      invocationContext: deleteInvocationContext,
    );
    final behavior = RemoteContentBehaviorCommandAdapter(
      client: client,
      invocationContext: invocationContext,
    );
    final cached = CachedContentRepository(
      readDelegate: remote,
      deleteDelegate: deleteWriter,
      postCache: postCache,
      querySnapshotStore: querySnapshotStore,
      blockedKeywordsLoader: blockedKeywordsLoader,
      userProfileCache: userProfileCache,
      telemetrySink: telemetrySink,
    );
    return AppProductionContentFacets(
      read: cached,
      postDeleteWriter: cached,
      behaviorWriter: behavior,
    );
  }

  static ContentMediaStreamObjectUpload contentMediaObjectUpload({
    required void Function(void Function()) onDispose,
  }) {
    final uploader = RemoteContentMediaObjectUploader();
    onDispose(uploader.dispose);
    return uploader.uploadStream;
  }

  static AppProductionContentPostReaderFacets contentPostReaderFacets({
    required GeneratedCloudOperationClient client,
    required Object invocationContext,
    required PostObjectCacheService postCache,
    required ContentQuerySnapshotStore querySnapshotStore,
    required UserProfileCacheService userProfileCache,
    required CacheTelemetrySink telemetrySink,
  }) {
    final remote = RemoteContentPostReaderAdapter(
      client: client,
      invocationContext: invocationContext as dynamic,
    );
    final cached = CachedContentPostReader(
      detailDelegate: remote,
      authorPostsDelegate: remote,
      postCache: postCache,
      querySnapshotStore: querySnapshotStore,
      userProfileCache: userProfileCache,
      telemetrySink: telemetrySink,
    );
    return AppProductionContentPostReaderFacets(
      detail: cached,
      authorPosts: cached,
      publicationStatus: remote,
      wishlistState: remote,
    );
  }

  static AppProductionFollowingSubjectFacets followingSubjectFacets({
    required GeneratedCloudOperationClient client,
    required FollowingSubjectInvocationContextFactory invocationContext,
  }) {
    final remote = generatedAdapter<RemoteFollowingSubjectFacet>(
      AppProductionAdapter.followingSubject,
      client: client,
      invocationContext: invocationContext,
    );
    return AppProductionFollowingSubjectFacets(
      query: remote,
      visitWriter: remote,
    );
  }

  static T generatedAdapter<T>(
    AppProductionAdapter adapter, {
    required GeneratedCloudOperationClient client,
    required Object invocationContext,
    Object? clientContextSnapshot,
  }) {
    final dynamic context = invocationContext;
    final dynamic snapshot = clientContextSnapshot;
    final Object result = switch (adapter) {
      AppProductionAdapter.appMessage => RemoteAppMessageAdapter(
        client: client,
        invocationContext: context,
      ),
      AppProductionAdapter.accountLifecycle =>
        RemoteAccountLifecycleCommandWriter(
          client: client,
          invocationContext: context,
        ),
      AppProductionAdapter.accountSession => RemoteAccountSessionCommandWriter(
        client: client,
        invocationContext: context,
      ),
      AppProductionAdapter.authenticationChallenge =>
        RemoteAuthenticationChallengeCommandWriter(
          client: client,
          invocationContext: context,
        ),
      AppProductionAdapter.authorImpact => RemoteAuthorImpactQuery(
        client: client,
        invocationContext: context,
      ),
      AppProductionAdapter.circleBehaviorFact => RemoteCircleBehaviorFactWriter(
        client: client,
        invocationContext: context,
      ),
      AppProductionAdapter.circleFile => RemoteCircleFileFacet(
        client: client,
        invocationContext: context,
      ),
      AppProductionAdapter.circleGroup => RemoteCircleGroupFacet(
        client: client,
        invocationContext: context,
      ),
      AppProductionAdapter.circleLifecycle => RemoteCircleLifecycleFacet(
        client: client,
        invocationContext: context,
      ),
      AppProductionAdapter.circleMembership => RemoteCircleMembershipFacet(
        client: client,
        invocationContext: context,
      ),
      AppProductionAdapter.circlePostPlacement =>
        RemoteCirclePostPlacementCommandWriter(
          client: client,
          invocationContext: context,
        ),
      AppProductionAdapter.circleQuery => RemoteCircleQueryReader(
        client: client,
        invocationContext: context,
      ),
      AppProductionAdapter.contentAppConfigQuery => RemoteContentAppConfigQuery(
        client: client,
        invocationContext: context,
      ),
      AppProductionAdapter.contentComment => RemoteContentCommentFacet(
        client: client,
        invocationContext: context,
      ),
      AppProductionAdapter.contentFootprint => RemoteFootprintRepository(
        client: client,
        invocationContext: context,
      ),
      AppProductionAdapter.contentMedia => RemoteContentMediaFacet(
        client: client,
        invocationContext: context,
      ),
      AppProductionAdapter.contentOutboundShare =>
        RemoteContentOutboundShareAppendWriter(
          client: client,
          invocationContext: context,
        ),
      AppProductionAdapter.contentPostPublication =>
        RemoteContentPostPublicationWriter(
          client: client,
          invocationContext: context,
        ),
      AppProductionAdapter.contentPostReader => RemoteContentPostReaderAdapter(
        client: client,
        invocationContext: context,
      ),
      AppProductionAdapter.contentPostReaction =>
        RemoteContentPostReactionFacet(
          client: client,
          invocationContext: context,
        ),
      AppProductionAdapter.contentProfileInteraction =>
        RemoteProfileInteractionAdapter(
          client: client,
          invocationContext: context,
        ),
      AppProductionAdapter.contentBehaviorCommand =>
        RemoteContentBehaviorCommandAdapter(
          client: client,
          invocationContext: context,
        ),
      AppProductionAdapter.contentReportCommand => RemoteContentReportAdapter(
        client: client,
        invocationContext: context,
      ),
      AppProductionAdapter.contentReportQuery =>
        RemoteContentReportQueryAdapter(
          client: client,
          invocationContext: context,
        ),
      AppProductionAdapter.connectorManagement =>
        RemoteConnectorManagementFacet(
          client: client,
          invocationContext: context,
        ),
      AppProductionAdapter.credentialBindingCommand =>
        RemoteAppCredentialBindingCommandWriter(
          client: client,
          invocationContext: context,
        ),
      AppProductionAdapter.credentialBindingQuery =>
        RemoteCredentialBindingQuery(
          client: client,
          invocationContext: context,
        ),
      AppProductionAdapter.devicePushEndpoint => RemoteDevicePushEndpointWriter(
        client: client,
        clientContextSnapshot: snapshot,
        invocationContext: context,
      ),
      AppProductionAdapter.filterCatalog => RemoteFilterCatalogQuery(
        client: client,
        invocationContext: context,
      ),
      AppProductionAdapter.greetingRequest => RemoteGreetingRequestFacet(
        client: client,
        invocationContext: context,
      ),
      AppProductionAdapter.homepageCommand => RemoteHomepageCommandWriter(
        client: client,
        invocationContext: context,
      ),
      AppProductionAdapter.homepageQuery => RemoteHomepageQueryAdapter(
        client: client,
        invocationContext: context,
      ),
      AppProductionAdapter.homepageReview => RemoteHomepageReviewFacet(
        client: client,
        invocationContext: context,
      ),
      AppProductionAdapter.incomingCallPresentation =>
        RemoteIncomingCallPresentationAcknowledger(
          client: client,
          invocationContext: context,
        ),
      AppProductionAdapter.locationQuery => RemoteLocationQueryAdapter(
        client: client,
        invocationContext: context,
      ),
      AppProductionAdapter.opsVisitAppend => RemoteOpsVisitAppendWriter(
        client: client,
        invocationContext: context,
      ),
      AppProductionAdapter.personaCommand => RemotePersonaCommandWriter(
        client: client,
        invocationContext: context,
      ),
      AppProductionAdapter.personaQuery => RemotePersonaQuery(
        managementQuery: RemoteUserProfileQueryFacet(
          client: client,
          invocationContext: context,
        ),
        publicProfileQuery: RemoteUserProfileQueryFacet(
          client: client,
          invocationContext: context,
        ),
      ),
      AppProductionAdapter.personaRelationship =>
        RemotePersonaRelationshipFacet(
          client: client,
          invocationContext: context,
        ),
      AppProductionAdapter.personaRelationshipFollow =>
        RemotePersonaRelationshipFollowAdapter(
          client: client,
          invocationContext: context,
        ),
      AppProductionAdapter.profileEditQuery => RemoteProfileEditQuery(
        editSnapshotQuery: RemoteUserProfileQueryFacet(
          client: client,
          invocationContext: context,
        ),
        publicProfileQuery: RemoteUserProfileQueryFacet(
          client: client,
          invocationContext: context,
        ),
      ),
      AppProductionAdapter.profileQuery => RemoteProfileQuery(
        publicProfileQuery: RemoteUserProfileQueryFacet(
          client: client,
          invocationContext: context,
        ),
        userHomepageQuery: RemoteUserProfileQueryFacet(
          client: client,
          invocationContext: context,
        ),
      ),
      AppProductionAdapter.profileUpdateProposal =>
        RemoteProfileUpdateProposalFacet(
          client: client,
          invocationContext: context,
        ),
      AppProductionAdapter.recentSearch => RemoteRecentSearchAdapter(
        client: client,
        invocationContext: context,
      ),
      AppProductionAdapter.rtcCallLifecycle => RemoteCallLifecycleCommandWriter(
        client: client,
        invocationContext: context,
      ),
      AppProductionAdapter.rtcCallMediaControl => RemoteCallMediaControlWriter(
        client: client,
        invocationContext: context,
      ),
      AppProductionAdapter.rtcCallParticipant =>
        RemoteCallParticipantCommandWriter(
          client: client,
          invocationContext: context,
        ),
      AppProductionAdapter.rtcCallQuery => RemoteCallQuery(
        client: client,
        invocationContext: context,
      ),
      AppProductionAdapter.rtcCallScreenShare => RemoteCallScreenShareWriter(
        client: client,
        invocationContext: context,
      ),
      AppProductionAdapter.searchFeedback => RemoteSearchFeedbackAdapter(
        client: client,
        invocationContext: context,
      ),
      AppProductionAdapter.searchHotQuery => RemoteSearchHotQueryReader(
        client: client,
        invocationContext: context,
      ),
      AppProductionAdapter.searchQuery => RemoteCanonicalSearchQuery(
        client: client,
        invocationContext: context,
      ),
      AppProductionAdapter.followingSubject => RemoteFollowingSubjectFacet(
        client: client,
        invocationContext: context,
      ),
      AppProductionAdapter.subjectFollow => RemoteSubjectFollowFacet(
        client: client,
        invocationContext: context,
      ),
      AppProductionAdapter.tagFeedback => RemoteTagFeedbackAdapter(
        client: client,
        invocationContext: context,
      ),
      AppProductionAdapter.userProfileQuery => RemoteUserProfileQueryFacet(
        client: client,
        invocationContext: context,
      ),
      AppProductionAdapter.userSettingsCommand =>
        RemoteUserSettingsCommandWriter(
          client: client,
          invocationContext: context,
        ),
      AppProductionAdapter.userSettingsQuery => RemoteUserSettingsQueryReader(
        client: client,
        invocationContext: context,
      ),
      AppProductionAdapter.userSync => RemoteUserSyncRepository(
        client: client,
        invocationContext: context,
      ),
    };
    return result as T;
  }
}
