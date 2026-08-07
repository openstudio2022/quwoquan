package http

import (
	"net/http"
	"strings"

	rterr "quwoquan_service/runtime/errors"
	commenttransport "quwoquan_service/services/content-service/generated/content/comment/transport"
	behaviortransport "quwoquan_service/services/content-service/generated/content/content_behavior_fact/transport"
	reactiontransport "quwoquan_service/services/content-service/generated/content/content_reaction/transport"
	intersectionvisittransport "quwoquan_service/services/content-service/generated/content/intersection_visit_state/transport"
	outboundsharetransport "quwoquan_service/services/content-service/generated/content/outbound_share_fact/transport"
	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
	posttransport "quwoquan_service/services/content-service/generated/content/post/transport"
	profileactivitytransport "quwoquan_service/services/content-service/generated/content/profile_interaction_activity_view/transport"
	profilereadfacttransport "quwoquan_service/services/content-service/generated/content/profile_interaction_read_fact/transport"
	filtercatalogtransport "quwoquan_service/services/content-service/generated/media/filter_catalog_release/transport"
	mediaassettransport "quwoquan_service/services/content-service/generated/media/media_asset/transport"
	mediareprocesstransport "quwoquan_service/services/content-service/generated/media/media_image_reprocess_run/transport"
	originalaccessquotatransport "quwoquan_service/services/content-service/generated/media/original_access_quota/transport"
	mediauploadtransport "quwoquan_service/services/content-service/generated/media/media_upload_session/transport"
	moderationtransport "quwoquan_service/services/content-service/generated/trust_safety/post_moderation_case/transport"
	reporttransport "quwoquan_service/services/content-service/generated/trust_safety/report/transport"
)

var generatedOperationResolvers = []func(*http.Request) (string, bool){
	commenttransport.ResolveOperation,
	behaviortransport.ResolveOperation,
	reactiontransport.ResolveOperation,
	intersectionvisittransport.ResolveOperation,
	outboundsharetransport.ResolveOperation,
	posttransport.ResolveOperation,
	profileactivitytransport.ResolveOperation,
	profilereadfacttransport.ResolveOperation,
	mediaassettransport.ResolveOperation,
	filtercatalogtransport.ResolveOperation,
	mediareprocesstransport.ResolveOperation,
	originalaccessquotatransport.ResolveOperation,
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
					rterr.NewCode(rterr.ModuleGateway, rterr.KindUser, "route_not_found"),
					"接口不存在或已下线",
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
	case "AuthorizeGatheringSafetyTermination":
		h.handleAuthorizeGatheringSafetyTermination(w, r)
	case "ActivateFilterCatalogRelease":
		h.handleActivateFilterCatalogRelease(w, r)
	case "BindMediaAssetsToComment":
		h.dispatchComment(w, r, func(handler commentHTTPHandler) {
			handler.BindMediaAssetsToComment(w, r, strings.TrimSpace(r.PathValue("commentId")))
		})
	case "CompleteMediaUpload":
		h.dispatchMediaUploadSession(w, r, func(handler mediaUploadSessionHTTPHandler) {
			handler.Complete(w, r)
		})
	case "CreateComment":
		h.dispatchComment(w, r, func(handler commentHTTPHandler) {
			handler.CreateComment(w, r, strings.TrimSpace(r.PathValue("postId")))
		})
	case "AppendOutboundShareFact":
		if h.outboundShareHandler == nil {
			writeHTTPError(
				w,
				r,
				contentgenerated.AppErrorFromRequiredDependencyUnavailable("OutboundShareFact HTTP adapter is not configured"),
			)
			return
		}
		h.outboundShareHandler.AppendOutboundShareFact(w, r)
	case "CreateReport":
		h.handleCreateReport(w, r)
	case "DecidePostModeration":
		h.dispatchPostModerationCase(w, r, func(handler postModerationCaseHTTPHandler) { handler.Decide(w, r) })
	case "DeleteComment":
		h.dispatchComment(w, r, func(handler commentHTTPHandler) {
			handler.DeleteComment(
				w,
				r,
				strings.TrimSpace(r.PathValue("postId")),
				strings.TrimSpace(r.PathValue("commentId")),
			)
		})
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
		h.dispatchContentReaction(w, r, func(handler contentReactionHTTPHandler) {
			handler.GetContentReactionState(w, r, strings.TrimSpace(r.PathValue("postId")))
		})
	case "GetCounters":
		h.handleGetCounters(w, r, strings.TrimSpace(r.PathValue("postId")))
	case "GetCurrentPostModerationCase":
		h.dispatchPostModerationCase(w, r, func(handler postModerationCaseHTTPHandler) { handler.GetCurrent(w, r) })
	case "GetEntityWishlistState":
		h.handleGetEntityWishlistState(w, r)
	case "GetActiveFilterCatalog":
		h.handleGetActiveFilterCatalog(w, r)
	case "GetFeed":
		h.handleGetFeed(w, r)
	case "GetHelperRead":
		h.handleGetHelperRead(w, r)
	case "GetMediaAsset":
		h.dispatchMediaAsset(w, r, func(handler mediaAssetHTTPHandler) { handler.GetPublic(w, r) })
	case "GetMediaAssetDeliveryReference":
		h.dispatchMediaAsset(w, r, func(handler mediaAssetHTTPHandler) { handler.GetDeliveryReference(w, r) })
	case "GetMediaAssetReference":
		h.dispatchMediaAsset(w, r, func(handler mediaAssetHTTPHandler) { handler.GetReference(w, r) })
	case "GetMediaImageReprocessRun":
		h.dispatchMediaImageReprocess(w, r, func(handler mediaImageReprocessHTTPHandler) { handler.Get(w, r) })
	case "GetMediaUploadSession":
		h.dispatchMediaUploadSession(w, r, func(handler mediaUploadSessionHTTPHandler) {
			handler.Get(w, r)
		})
	case "GetMyFootprint":
		h.handleGetMyFootprint(w, r)
	case "GetMyIntersectionSummary":
		h.dispatchIntersectionVisitState(w, r, func(handler intersectionVisitStateHTTPHandler) {
			handler.GetMyIntersectionSummary(w, r)
		})
	case "GetObjectIntersections":
		h.dispatchIntersectionVisitState(w, r, func(handler intersectionVisitStateHTTPHandler) {
			handler.GetObjectIntersections(w, r)
		})
	case "GetOwnedMediaAsset":
		h.dispatchMediaAsset(w, r, func(handler mediaAssetHTTPHandler) { handler.GetOwned(w, r) })
	case "DiscardMediaAsset":
		h.dispatchMediaAsset(w, r, func(handler mediaAssetHTTPHandler) { handler.Discard(w, r) })
	case "GetPost":
		h.handleGetPost(w, r)
	case "GetPostPublicationEligibility":
		h.dispatchPostModerationCase(w, r, func(handler postModerationCaseHTTPHandler) { handler.GetPublicationEligibility(w, r) })
	case "GetReport":
		h.handleGetReport(w, r)
	case "GrantGatheringSafetyTermination":
		h.handleGrantGatheringSafetyTermination(w, r)
	case "HideComment":
		h.dispatchComment(w, r, func(handler commentHTTPHandler) {
			handler.HideComment(w, r, strings.TrimSpace(r.PathValue("commentId")))
		})
	case "InitMediaUpload":
		h.dispatchMediaUploadSession(w, r, func(handler mediaUploadSessionHTTPHandler) {
			handler.Init(w, r)
		})
	case "LikePost":
		h.dispatchContentReaction(w, r, func(handler contentReactionHTTPHandler) {
			handler.LikePost(w, r, strings.TrimSpace(r.PathValue("postId")))
		})
	case "ListAuthorImpactEvidence":
		h.handleListAuthorImpactEvidence(w, r)
	case "ListCommentReplies":
		h.dispatchComment(w, r, func(handler commentHTTPHandler) {
			handler.ListCommentReplies(
				w,
				r,
				strings.TrimSpace(r.PathValue("postId")),
				strings.TrimSpace(r.PathValue("commentId")),
			)
		})
	case "ListComments":
		h.dispatchComment(w, r, func(handler commentHTTPHandler) {
			handler.ListComments(w, r, strings.TrimSpace(r.PathValue("postId")))
		})
	case "ListCommentsByAuthor":
		h.dispatchComment(w, r, func(handler commentHTTPHandler) {
			handler.ListCommentsByAuthor(w, r)
		})
	case "ListCommentsForPostAuthor":
		h.dispatchComment(w, r, func(handler commentHTTPHandler) {
			handler.ListCommentsForPostAuthor(w, r)
		})
	case "ListMyIntersections":
		h.dispatchIntersectionVisitState(w, r, func(handler intersectionVisitStateHTTPHandler) {
			handler.ListMyIntersections(w, r)
		})
	case "ListMyReports":
		h.handleListMyReports(w, r)
	case "ListProfileInteractionActivitiesReceived":
		h.dispatchProfileInteractionActivity(w, r, func(handler profileInteractionActivityHTTPHandler) {
			handler.ListReceived(w, r)
		})
	case "ListProfileInteractionActivitiesSent":
		h.dispatchProfileInteractionActivity(w, r, func(handler profileInteractionActivityHTTPHandler) {
			handler.ListSent(w, r)
		})
	case "ListReports":
		h.handleListReports(w, r)
	case "ListUserPosts":
		h.handleListUserPosts(w, r)
	case "MarkIntersectionsVisited":
		h.dispatchIntersectionVisitState(w, r, func(handler intersectionVisitStateHTTPHandler) {
			handler.MarkVisited(w, r)
		})
	case "OpenPostModerationCase":
		h.dispatchPostModerationCase(w, r, func(handler postModerationCaseHTTPHandler) { handler.Open(w, r) })
	case "PauseMediaImageReprocessRun":
		h.dispatchMediaImageReprocess(w, r, func(handler mediaImageReprocessHTTPHandler) { handler.Pause(w, r) })
	case "PinComment":
		h.dispatchComment(w, r, func(handler commentHTTPHandler) {
			handler.SetCommentPinned(
				w,
				r,
				strings.TrimSpace(r.PathValue("postId")),
				strings.TrimSpace(r.PathValue("commentId")),
				true,
			)
		})
	case "PromotePostToWork":
		h.handlePromotePostToWork(w, r)
	case "ReactToComment":
		h.dispatchContentReaction(w, r, func(handler contentReactionHTTPHandler) {
			handler.ReactToComment(w, r, strings.TrimSpace(r.PathValue("commentId")))
		})
	case "RecordMediaProcessingResult":
		h.dispatchMediaAsset(w, r, func(handler mediaAssetHTTPHandler) { handler.RecordProcessingResult(w, r) })
	case "ReportBehaviors":
		h.dispatchContentBehavior(w, r)
	case "ReserveOriginalImageAccessGrant":
		if h.originalAccessQuotaHandler == nil {
			writeHTTPError(w, r, contentgenerated.AppErrorFromRequiredDependencyUnavailable("OriginalAccessQuota HTTP adapter is not configured"))
			return
		}
		h.originalAccessQuotaHandler.Reserve(w, r)
	case "ResolveReport":
		h.handleResolveReport(w, r)
	case "RevokeGatheringSafetyTermination":
		h.handleRevokeGatheringSafetyTermination(w, r)
	case "RestoreComment":
		h.dispatchComment(w, r, func(handler commentHTTPHandler) {
			handler.RestoreComment(w, r, strings.TrimSpace(r.PathValue("commentId")))
		})
	case "ResumeMediaImageReprocessRun":
		h.dispatchMediaImageReprocess(w, r, func(handler mediaImageReprocessHTTPHandler) { handler.Resume(w, r) })
	case "ReviewPostModerationCase":
		h.dispatchPostModerationCase(w, r, func(handler postModerationCaseHTTPHandler) { handler.Review(w, r) })
	case "RollbackMediaImageReprocessRun":
		h.dispatchMediaImageReprocess(w, r, func(handler mediaImageReprocessHTTPHandler) { handler.Rollback(w, r) })
	case "RollbackFilterCatalogRelease":
		h.handleRollbackFilterCatalogRelease(w, r)
	case "SelectAutoVideoCover":
		h.dispatchMediaAsset(w, r, func(handler mediaAssetHTTPHandler) { handler.SelectAutoCover(w, r) })
	case "SelectManualVideoCover":
		h.dispatchMediaAsset(w, r, func(handler mediaAssetHTTPHandler) { handler.SelectManualCover(w, r) })
	case "StartMediaImageReprocessRun":
		h.dispatchMediaImageReprocess(w, r, func(handler mediaImageReprocessHTTPHandler) { handler.Start(w, r) })
	case "StageFilterCatalogRelease":
		h.handleStageFilterCatalogRelease(w, r)
	case "SubmitPostPublication":
		h.handleSubmitPostPublication(w, r)
	case "SupersedePostModerationCase":
		h.dispatchPostModerationCase(w, r, func(handler postModerationCaseHTTPHandler) { handler.Supersede(w, r) })
	case "UnlikePost":
		h.dispatchContentReaction(w, r, func(handler contentReactionHTTPHandler) {
			handler.UnlikePost(w, r, strings.TrimSpace(r.PathValue("postId")))
		})
	case "UnpinComment":
		h.dispatchComment(w, r, func(handler commentHTTPHandler) {
			handler.SetCommentPinned(
				w,
				r,
				strings.TrimSpace(r.PathValue("postId")),
				strings.TrimSpace(r.PathValue("commentId")),
				false,
			)
		})
	case "UpdateMediaAssetAccessPolicy":
		h.dispatchMediaAsset(w, r, func(handler mediaAssetHTTPHandler) { handler.UpdateAccessPolicy(w, r) })
	case "UpdatePostSettings":
		h.handleUpdatePostSettings(w, r)
	case "AppendProfileInteractionReadFact":
		h.dispatchProfileInteractionReadFact(w, r, func(handler profileInteractionReadFactHTTPHandler) {
			handler.Append(w, r)
		})
	default:
		h.handleNotImplemented(w, r, operation)
	}
}

func (h *ContentHandler) dispatchComment(
	writer http.ResponseWriter,
	request *http.Request,
	dispatch func(commentHTTPHandler),
) {
	if h.commentHandler == nil {
		writeHTTPError(
			writer,
			request,
			contentgenerated.AppErrorFromRequiredDependencyUnavailable("Comment HTTP adapter is not configured"),
		)
		return
	}
	dispatch(h.commentHandler)
}

func (h *ContentHandler) dispatchContentReaction(
	writer http.ResponseWriter,
	request *http.Request,
	dispatch func(contentReactionHTTPHandler),
) {
	if h.reactionHandler == nil {
		writeHTTPError(
			writer,
			request,
			contentgenerated.AppErrorFromRequiredDependencyUnavailable("ContentReaction HTTP adapter is not configured"),
		)
		return
	}
	dispatch(h.reactionHandler)
}

func (h *ContentHandler) dispatchContentBehavior(
	writer http.ResponseWriter,
	request *http.Request,
) {
	if h.behaviorHandler == nil {
		writeHTTPError(writer, request, contentgenerated.AppErrorFromRequiredDependencyUnavailable("ContentBehaviorFact HTTP adapter is not configured"))
		return
	}
	h.behaviorHandler.Report(writer, request)
}

func (h *ContentHandler) dispatchIntersectionVisitState(
	writer http.ResponseWriter,
	request *http.Request,
	dispatch func(intersectionVisitStateHTTPHandler),
) {
	if h.intersectionVisitHandler == nil {
		writeHTTPError(writer, request, contentgenerated.AppErrorFromRequiredDependencyUnavailable("IntersectionVisitState HTTP adapter is not configured"))
		return
	}
	dispatch(h.intersectionVisitHandler)
}

func (h *ContentHandler) dispatchProfileInteractionActivity(
	writer http.ResponseWriter,
	request *http.Request,
	dispatch func(profileInteractionActivityHTTPHandler),
) {
	if h.profileInteractionHandler == nil {
		writeHTTPError(writer, request, contentgenerated.AppErrorFromRequiredDependencyUnavailable("ProfileInteractionActivityView HTTP adapter is not configured"))
		return
	}
	dispatch(h.profileInteractionHandler)
}

func (h *ContentHandler) dispatchProfileInteractionReadFact(
	writer http.ResponseWriter,
	request *http.Request,
	dispatch func(profileInteractionReadFactHTTPHandler),
) {
	if h.profileReadFactHandler == nil {
		writeHTTPError(writer, request, contentgenerated.AppErrorFromRequiredDependencyUnavailable("ProfileInteractionReadFact HTTP adapter is not configured"))
		return
	}
	dispatch(h.profileReadFactHandler)
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
			contentgenerated.AppErrorFromRequiredDependencyUnavailable("MediaUploadSession HTTP adapter is required"),
		)
		return
	}
	dispatch(h.mediaUploadSessionHandler)
}

func (h *ContentHandler) dispatchMediaAsset(
	w http.ResponseWriter,
	r *http.Request,
	dispatch func(mediaAssetHTTPHandler),
) {
	if h.mediaAssetHandler == nil {
		writeHTTPError(w, r, contentgenerated.AppErrorFromRequiredDependencyUnavailable("MediaAsset HTTP adapter is required"))
		return
	}
	dispatch(h.mediaAssetHandler)
}

func (h *ContentHandler) dispatchPostModerationCase(
	w http.ResponseWriter,
	r *http.Request,
	dispatch func(postModerationCaseHTTPHandler),
) {
	if h.moderationHandler == nil {
		writeHTTPError(w, r, contentgenerated.AppErrorFromRequiredDependencyUnavailable("PostModerationCase HTTP adapter is required"))
		return
	}
	dispatch(h.moderationHandler)
}

func (h *ContentHandler) dispatchMediaImageReprocess(
	w http.ResponseWriter,
	r *http.Request,
	dispatch func(mediaImageReprocessHTTPHandler),
) {
	if h.mediaImageReprocessHandler == nil {
		writeHTTPError(w, r, contentgenerated.AppErrorFromRequiredDependencyUnavailable("MediaImageReprocessRun HTTP adapter is required"))
		return
	}
	dispatch(h.mediaImageReprocessHandler)
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
			contentgenerated.AppErrorFromRequiredDependencyUnavailable("FilterCatalogRelease HTTP adapter is required"),
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

func BindGeneratedGetFeedParams(r *http.Request) (GeneratedGetFeedParams, error) {
	return posttransport.BindGeneratedGetFeedParams(r)
}

func BindGeneratedRequestBodyFromRequest(r *http.Request, operation string) (map[string]any, error) {
	return posttransport.BindGeneratedRequestBodyFromRequest(r, operation)
}
