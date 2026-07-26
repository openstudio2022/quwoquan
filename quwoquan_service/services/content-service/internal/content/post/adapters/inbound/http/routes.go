package http

import (
	"net/http"
	"strings"

	rterr "quwoquan_service/runtime/errors"
	commenttransport "quwoquan_service/services/content-service/generated/content/comment/transport"
	reactiontransport "quwoquan_service/services/content-service/generated/content/content_reaction/transport"
	intersectionvisittransport "quwoquan_service/services/content-service/generated/content/intersection_visit_state/transport"
	outboundsharetransport "quwoquan_service/services/content-service/generated/content/outbound_share_fact/transport"
	posttransport "quwoquan_service/services/content-service/generated/content/post/transport"
	profileactivitytransport "quwoquan_service/services/content-service/generated/content/profile_interaction_activity_view/transport"
	profilereadfacttransport "quwoquan_service/services/content-service/generated/content/profile_interaction_read_fact/transport"
	filtercatalogtransport "quwoquan_service/services/content-service/generated/media/filter_catalog_release/transport"
	mediaassettransport "quwoquan_service/services/content-service/generated/media/media_asset/transport"
	mediareprocesstransport "quwoquan_service/services/content-service/generated/media/media_image_reprocess_run/transport"
	mediaoriginaltransport "quwoquan_service/services/content-service/generated/media/media_original_access_fact/transport"
	mediauploadtransport "quwoquan_service/services/content-service/generated/media/media_upload_session/transport"
	moderationtransport "quwoquan_service/services/content-service/generated/trust_safety/post_moderation_case/transport"
	reporttransport "quwoquan_service/services/content-service/generated/trust_safety/report/transport"
)

var generatedOperationResolvers = []func(*http.Request) (string, bool){
	commenttransport.ResolveOperation,
	reactiontransport.ResolveOperation,
	intersectionvisittransport.ResolveOperation,
	outboundsharetransport.ResolveOperation,
	posttransport.ResolveOperation,
	profileactivitytransport.ResolveOperation,
	profilereadfacttransport.ResolveOperation,
	mediaassettransport.ResolveOperation,
	filtercatalogtransport.ResolveOperation,
	mediareprocesstransport.ResolveOperation,
	mediaoriginaltransport.ResolveOperation,
	mediauploadtransport.ResolveOperation,
	moderationtransport.ResolveOperation,
	reporttransport.ResolveOperation,
}

func resolveGeneratedOperation(r *http.Request) (string, bool) {
	for _, resolve := range generatedOperationResolvers {
		if operation, ok := resolve(r); ok {
			return operation, true
		}
	}
	return "", false
}

func RegisterGeneratedRoutes(mux *http.ServeMux, h *ContentHandler) {
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		op, ok := resolveGeneratedOperation(r)
		if !ok {
			rterr.WriteHTTPError(
				w,
				rterr.NewAppError(
					rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "route_not_found"),
					"接口不存在",
					"generated content route not found",
				),
				rterr.HTTPWriteOptionsFromRequest(r),
			)
			return
		}
		dispatchGeneratedOperation(h, op, w, r)
	})
}

func dispatchGeneratedOperation(h *ContentHandler, operation string, w http.ResponseWriter, r *http.Request) {
	switch operation {
	case "AbortMediaUpload":
		h.dispatchMediaUploadSession(w, r, func(handler mediaUploadSessionHTTPHandler) {
			handler.Abort(w, r)
		})
	case "BeginReportReview":
		h.handleBeginReportReview(w, r)
	case "ActivateFilterCatalogRelease":
		h.handleActivateFilterCatalogRelease(w, r)
	case "BindMediaAssetsToComment":
		h.handleBindMediaAssetsToComment(
			w,
			r,
			strings.TrimSpace(r.PathValue("commentId")),
		)
	case "CompleteMediaUpload":
		h.dispatchMediaUploadSession(w, r, func(handler mediaUploadSessionHTTPHandler) {
			handler.Complete(w, r)
		})
	case "CreateComment":
		h.handleCreateComment(w, r, strings.TrimSpace(r.PathValue("postId")))
	case "CreateOutboundShare":
		h.handleCreateOutboundShare(w, r)
	case "CreateReport":
		h.handleCreateReport(w, r)
	case "DecidePostModeration":
		h.handleDecidePostModeration(w, r)
	case "DeleteComment":
		h.handleDeleteComment(
			w,
			r,
			strings.TrimSpace(r.PathValue("postId")),
			strings.TrimSpace(r.PathValue("commentId")),
		)
	case "DeletePost":
		h.handleDeletePost(w, r)
	case "DismissReport":
		h.handleDismissReport(w, r)
	case "GenerateArticleSummary":
		h.handleGenerateArticleSummary(w, r)
	case "GetAppConfig":
		h.handleGetAppConfig(w, r)
	case "GetAuthorImpact":
		h.handleGetAuthorImpact(w, r)
	case "GetContentReactionState":
		h.handleGetReactionState(w, r, strings.TrimSpace(r.PathValue("postId")))
	case "GetCounters":
		h.handleGetCounters(w, r, strings.TrimSpace(r.PathValue("postId")))
	case "GetCurrentPostModerationCase":
		h.handleGetCurrentPostModerationCase(w, r)
	case "GetEntityWishlistState":
		h.handleGetEntityWishlistState(w, r)
	case "GetActiveFilterCatalog":
		h.handleGetActiveFilterCatalog(w, r)
	case "GetFeed":
		h.handleGetFeed(w, r)
	case "GetHelperRead":
		h.handleGetHelperRead(w, r)
	case "GetMediaAsset":
		h.handleGetMediaAsset(w, r)
	case "GetMediaAssetDeliveryReference":
		h.handleGetMediaAssetDeliveryReference(w, r)
	case "GetMediaAssetReference":
		h.handleGetMediaAssetReference(w, r)
	case "GetMediaImageReprocessRun":
		h.handleGetMediaImageReprocessRun(w, r)
	case "GetMediaUploadSession":
		h.dispatchMediaUploadSession(w, r, func(handler mediaUploadSessionHTTPHandler) {
			handler.Get(w, r)
		})
	case "GetMyFootprint":
		h.handleGetMyFootprint(w, r)
	case "GetMyIntersectionSummary":
		h.handleGetMyIntersectionSummary(w, r)
	case "GetObjectIntersections":
		h.handleGetObjectIntersections(w, r)
	case "GetOwnedMediaAsset":
		h.handleGetOwnedMediaAsset(w, r)
	case "DiscardMediaAsset":
		h.handleDiscardMediaAsset(w, r)
	case "GetPost":
		h.handleGetPost(w, r)
	case "GetPostPublicationEligibility":
		h.handleGetPostPublicationEligibility(w, r)
	case "GetReport":
		h.handleGetReport(w, r)
	case "HideComment":
		h.handleHideComment(
			w,
			r,
			strings.TrimSpace(r.PathValue("commentId")),
		)
	case "InitMediaUpload":
		h.dispatchMediaUploadSession(w, r, func(handler mediaUploadSessionHTTPHandler) {
			handler.Init(w, r)
		})
	case "LikePost":
		h.handleLikePost(w, r, strings.TrimSpace(r.PathValue("postId")))
	case "ListAuthorImpactEvidence":
		h.handleListAuthorImpactEvidence(w, r)
	case "ListCommentReplies":
		h.handleListCommentReplies(
			w,
			r,
			strings.TrimSpace(r.PathValue("postId")),
			strings.TrimSpace(r.PathValue("commentId")),
		)
	case "ListComments":
		h.handleListComments(w, r, strings.TrimSpace(r.PathValue("postId")))
	case "ListCommentsByAuthor":
		h.handleListCommentsByAuthor(w, r)
	case "ListCommentsForPostAuthor":
		h.handleListCommentsForPostAuthor(w, r)
	case "ListMyIntersections":
		h.handleListMyIntersections(w, r)
	case "ListMyReports":
		h.handleListMyReports(w, r)
	case "ListProfileInteractionActivitiesReceived":
		h.handleListProfileInteractionActivitiesReceived(w, r)
	case "ListProfileInteractionActivitiesSent":
		h.handleListProfileInteractionActivitiesSent(w, r)
	case "ListReports":
		h.handleListReports(w, r)
	case "ListUserPosts":
		h.handleListUserPosts(w, r)
	case "MarkIntersectionsVisited":
		h.handleMarkIntersectionsVisited(w, r)
	case "OpenPostModerationCase":
		h.handleOpenPostModerationCase(w, r)
	case "PauseMediaImageReprocessRun":
		h.handlePauseMediaImageReprocessRun(w, r)
	case "PinComment":
		h.handleSetCommentPinned(
			w,
			r,
			strings.TrimSpace(r.PathValue("postId")),
			strings.TrimSpace(r.PathValue("commentId")),
			true,
		)
	case "PromotePostToWork":
		h.handlePromotePostToWork(w, r)
	case "ReactToComment":
		h.handleReactToComment(w, r, strings.TrimSpace(r.PathValue("commentId")))
	case "RecordMediaProcessingResult":
		h.handleRecordMediaProcessingResult(w, r)
	case "ReportBehaviors":
		h.handleReportBehaviors(w, r)
	case "RequestOriginalImageAccess":
		h.handleRequestOriginalImageAccess(w, r)
	case "ResolveReport":
		h.handleResolveReport(w, r)
	case "RestoreComment":
		h.handleRestoreComment(
			w,
			r,
			strings.TrimSpace(r.PathValue("commentId")),
		)
	case "ResumeMediaImageReprocessRun":
		h.handleResumeMediaImageReprocessRun(w, r)
	case "ReviewPostModerationCase":
		h.handleReviewPostModerationCase(w, r)
	case "RollbackMediaImageReprocessRun":
		h.handleRollbackMediaImageReprocessRun(w, r)
	case "RollbackFilterCatalogRelease":
		h.handleRollbackFilterCatalogRelease(w, r)
	case "SelectAutoVideoCover":
		h.handleSelectAutoVideoCover(w, r)
	case "SelectManualVideoCover":
		h.handleSelectManualVideoCover(w, r)
	case "StartMediaImageReprocessRun":
		h.handleStartMediaImageReprocessRun(w, r)
	case "StageFilterCatalogRelease":
		h.handleStageFilterCatalogRelease(w, r)
	case "SubmitPostPublication":
		h.handleSubmitPostPublication(w, r)
	case "SupersedePostModerationCase":
		h.handleSupersedePostModerationCase(w, r)
	case "UnlikePost":
		h.handleUnlikePost(w, r, strings.TrimSpace(r.PathValue("postId")))
	case "UnpinComment":
		h.handleSetCommentPinned(
			w,
			r,
			strings.TrimSpace(r.PathValue("postId")),
			strings.TrimSpace(r.PathValue("commentId")),
			false,
		)
	case "UpdateMediaAssetAccessPolicy":
		h.handleUpdateMediaAssetAccessPolicy(w, r)
	case "UpdatePostSettings":
		h.handleUpdatePostSettings(w, r)
	case "UpdateProfileInteractionState":
		h.handleUpdateProfileInteractionState(w, r)
	default:
		h.handleNotImplemented(w, r, operation)
	}
}

func (h *ContentHandler) dispatchMediaUploadSession(
	w http.ResponseWriter,
	r *http.Request,
	dispatch func(mediaUploadSessionHTTPHandler),
) {
	if h.mediaUploadSessionHandler == nil {
		writeHTTPError(
			w,
			r,
			rterr.NewUnavailable(
				rterr.ModuleContent,
				"媒体上传会话服务未配置",
				"MediaUploadSession HTTP adapter is required",
			),
		)
		return
	}
	dispatch(h.mediaUploadSessionHandler)
}

func (h *ContentHandler) dispatchFilterCatalogRelease(
	w http.ResponseWriter,
	r *http.Request,
	dispatch func(filterCatalogReleaseHTTPHandler),
) {
	if h.filterCatalogReleaseHandler == nil {
		writeHTTPError(
			w,
			r,
			rterr.NewUnavailable(
				rterr.ModuleContent,
				"滤镜目录服务未配置",
				"FilterCatalogRelease HTTP adapter is required",
			),
		)
		return
	}
	dispatch(h.filterCatalogReleaseHandler)
}

func (h *ContentHandler) handleStageFilterCatalogRelease(w http.ResponseWriter, r *http.Request) {
	h.dispatchFilterCatalogRelease(w, r, func(handler filterCatalogReleaseHTTPHandler) {
		handler.Stage(w, r)
	})
}

func (h *ContentHandler) handleActivateFilterCatalogRelease(w http.ResponseWriter, r *http.Request) {
	h.dispatchFilterCatalogRelease(w, r, func(handler filterCatalogReleaseHTTPHandler) {
		handler.Activate(w, r)
	})
}

func (h *ContentHandler) handleRollbackFilterCatalogRelease(w http.ResponseWriter, r *http.Request) {
	h.dispatchFilterCatalogRelease(w, r, func(handler filterCatalogReleaseHTTPHandler) {
		handler.Rollback(w, r)
	})
}

func (h *ContentHandler) handleGetActiveFilterCatalog(w http.ResponseWriter, r *http.Request) {
	h.dispatchFilterCatalogRelease(w, r, func(handler filterCatalogReleaseHTTPHandler) {
		handler.GetActive(w, r)
	})
}

type GeneratedGetFeedParams = posttransport.GeneratedGetFeedParams

func BindGeneratedGetFeedParams(r *http.Request, defaultLimit int) GeneratedGetFeedParams {
	return posttransport.BindGeneratedGetFeedParams(r, defaultLimit)
}

func BindGeneratedWritableBodyFromRequest(r *http.Request, operation string) (map[string]any, error) {
	return posttransport.BindGeneratedWritableBodyFromRequest(r, operation)
}
