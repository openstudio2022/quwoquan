package http

import (
	"net/http"
	rterr "quwoquan_service/runtime/errors"
)

func (h *ContentHandler) handleNotImplemented(w http.ResponseWriter, r *http.Request, operation string) {
	switch operation {
	case "LikePost":
		h.handleLikePost(w, r, postIDFromPath(r.URL.Path))
		return
	case "UnlikePost":
		h.handleUnlikePost(w, r, postIDFromPath(r.URL.Path))
		return
	case "SharePost":
		h.handleSharePost(w, r, postIDFromPath(r.URL.Path))
		return
	case "UnsharePost":
		h.handleUnsharePost(w, r, postIDFromPath(r.URL.Path))
		return
	case "GetReactionState":
		h.handleGetReactionState(w, r, postIDFromPath(r.URL.Path))
		return
	case "GetMyFootprint":
		h.handleGetMyFootprint(w, r)
		return
	case "CreateComment":
		h.handleCreateComment(w, r, postIDFromPath(r.URL.Path))
		return
	case "PublishPost":
		h.handlePublishPost(w, r)
		return
	case "UpdatePostSettings":
		h.handleUpdatePostSettings(w, r)
		return
	case "PromotePostToWork":
		h.handlePromotePostToWork(w, r)
		return
	case "DeletePost":
		h.handleDeletePost(w, r)
		return
	case "UpdatePostCircles":
		h.handleUpdatePostCircles(w, r)
		return
	case "RepostToCircle":
		h.handleRepostToCircle(w, r)
		return
	case "QuoteToCircle":
		h.handleQuoteToCircle(w, r)
		return
	case "InitMediaUpload":
		h.handleInitMediaUpload(w, r)
		return
	case "CompleteMediaUpload":
		h.handleCompleteMediaUpload(w, r)
		return
	case "AbortMediaUpload":
		h.handleAbortMediaUpload(w, r)
		return
	case "GetMediaAsset":
		h.handleGetMediaAsset(w, r)
		return
	case "BindMediaAssetsToPost":
		h.handleBindMediaAssetsToPost(w, r)
		return
	case "RequestOriginalImageAccess":
		h.handleRequestOriginalImageAccess(w, r)
		return
	case "SelectAutoVideoCover":
		h.handleSelectAutoVideoCover(w, r)
		return
	case "SelectManualVideoCover":
		h.handleSelectManualVideoCover(w, r)
		return
	case "GenerateArticleSummary":
		h.handleGenerateArticleSummary(w, r)
		return
	case "ListComments":
		h.handleListComments(w, r, postIDFromPath(r.URL.Path))
		return
	case "ListCommentReplies":
		h.handleListCommentReplies(w, r)
		return
	case "ReactToComment":
		h.handleReactToComment(w, r, commentIDFromPath(r.URL.Path))
		return
	case "BindMediaAssetsToComment":
		h.handleBindMediaAssetsToComment(w, r, commentIDFromPath(r.URL.Path))
		return
	case "DeleteComment":
		h.handleDeleteComment(w, r)
		return
	case "PinComment":
		h.handleSetCommentPinned(w, r, true)
		return
	case "UnpinComment":
		h.handleSetCommentPinned(w, r, false)
		return
	case "GetCounters":
		h.handleGetCounters(w, r, postIDFromPath(r.URL.Path))
		return
	case "GetCommentCountsDelta":
		h.handleGetCommentCountsDelta(w, r, postIDFromPath(r.URL.Path))
		return
	case "GetHelperRead":
		h.handleGetHelperRead(w, r)
		return
	case "ListUserPosts":
		h.handleListUserPosts(w, r)
		return
	case "ListCommentsByAuthor":
		h.handleListCommentsByAuthor(w, r)
		return
	case "ListCommentsForPostAuthor":
		h.handleListCommentsForPostAuthor(w, r)
		return
	case "GetAppConfig":
		h.handleGetAppConfig(w, r)
		return
	}
	writeHTTPError(w, r, rterr.NewAppError(
		rterr.NewCode(rterr.ModuleContent, rterr.KindSystem, "unavailable"),
		"接口暂未开放",
		"operation not implemented: "+operation+" "+r.Method+" "+r.URL.Path,
	))
}
