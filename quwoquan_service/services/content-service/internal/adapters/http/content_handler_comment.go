package http

import (
	"encoding/json"
	"io"
	"net/http"
	"strconv"
	"strings"

	rterr "quwoquan_service/runtime/errors"
	commentapp "quwoquan_service/services/content-service/internal/application/comment"
	reactionapp "quwoquan_service/services/content-service/internal/application/reaction"
	commentmodel "quwoquan_service/services/content-service/internal/domain/comment/model"
	reactiondomain "quwoquan_service/services/content-service/internal/domain/reaction"
	contentgenerated "quwoquan_service/services/content-service/internal/generated"
)

func (h *ContentHandler) handleCreateComment(w http.ResponseWriter, r *http.Request, postID string) {
	var body struct {
		Content                   string                 `json:"content"`
		ReplyToCommentID          string                 `json:"replyToCommentId"`
		PersonaContextVersion     int64                  `json:"personaContextVersion"`
		AttachmentMediaIDs        []string               `json:"attachmentMediaIds"`
		Mentions                  []commentmodel.Mention `json:"mentions"`
		AuthorDisplayNameSnapshot string                 `json:"authorDisplayNameSnapshot"`
		AuthorAvatarURLSnapshot   string                 `json:"authorAvatarUrlSnapshot"`
	}
	decoder := json.NewDecoder(r.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&body); err != nil {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "请求体解析失败", err.Error()))
		return
	}
	if err := requireJSONEOF(decoder); err != nil {
		writeHTTPError(w, r, err)
		return
	}
	actorID, err := requiredCommentPersona(r)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	result, err := h.commentService.CreateComment(r.Context(), commentapp.CreateCommentCommand{
		PostID:                    postID,
		ActorID:                   actorID,
		AuthorDisplayNameSnapshot: body.AuthorDisplayNameSnapshot,
		AuthorAvatarURLSnapshot:   body.AuthorAvatarURLSnapshot,
		PersonaContextVersion:     body.PersonaContextVersion,
		Content:                   body.Content,
		ReplyToCommentID:          body.ReplyToCommentID,
		AttachmentMediaIDs:        body.AttachmentMediaIDs,
		Mentions:                  body.Mentions,
	})
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusCreated, result)
}

func (h *ContentHandler) handleListComments(w http.ResponseWriter, r *http.Request, postID string) {
	cursor := strings.TrimSpace(r.URL.Query().Get("cursor"))
	limit := 20
	if raw := r.URL.Query().Get("limit"); raw != "" {
		if n, err := strconv.Atoi(raw); err == nil && n > 0 {
			limit = n
		}
	}
	page, err := h.commentService.ListComments(r.Context(), commentapp.ListCommentsQuery{
		PostID:  postID,
		ActorID: optionalCommentPersona(r),
		Cursor:  cursor,
		Limit:   limit,
	})
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, page)
}

func (h *ContentHandler) handleListCommentReplies(
	w http.ResponseWriter,
	r *http.Request,
	postID string,
	commentID string,
) {
	// /content/posts/{postId}/comments/{commentId}/replies
	if postID == "" || commentID == "" {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "invalid path", "missing postId/commentId"))
		return
	}
	cursor := strings.TrimSpace(r.URL.Query().Get("cursor"))
	limit := 10
	if raw := r.URL.Query().Get("limit"); raw != "" {
		if n, err := strconv.Atoi(raw); err == nil && n > 0 {
			limit = n
		}
	}
	page, err := h.commentService.ListReplies(r.Context(), commentapp.ListCommentRepliesQuery{
		PostID:          postID,
		ParentCommentID: commentID,
		ActorID:         optionalCommentPersona(r),
		Cursor:          cursor,
		Limit:           limit,
	})
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, page)
}

func (h *ContentHandler) handleDeleteComment(
	w http.ResponseWriter,
	r *http.Request,
	postID string,
	commentID string,
) {
	// /content/posts/{postId}/comments/{commentId}
	if postID == "" || commentID == "" {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "invalid path", "missing commentId"))
		return
	}
	actorID, err := requiredCommentPersona(r)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	result, err := h.commentService.DeleteComment(r.Context(), commentapp.DeleteCommentCommand{
		PostID: postID, CommentID: commentID, ActorID: actorID,
	})
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (h *ContentHandler) handleSetCommentPinned(
	w http.ResponseWriter,
	r *http.Request,
	postID string,
	commentID string,
	pinned bool,
) {
	// /content/posts/{postId}/comments/{commentId}/pin
	if postID == "" || commentID == "" {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "invalid path", "missing commentId for pin"))
		return
	}
	actorID, err := requiredCommentPersona(r)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	command := commentapp.ChangeCommentPinCommand{
		PostID: postID, CommentID: commentID, ActorID: actorID,
		Pinned: pinned,
	}
	var result commentapp.CommentCommandResult
	if pinned {
		result, err = h.commentService.PinComment(r.Context(), command)
	} else {
		result, err = h.commentService.UnpinComment(r.Context(), command)
	}
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (h *ContentHandler) handleReactToComment(w http.ResponseWriter, r *http.Request, commentID string) {
	var body struct {
		Reaction string `json:"reaction"`
	}
	decoder := json.NewDecoder(r.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&body); err != nil {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "请求体解析失败", err.Error()))
		return
	}
	reactionValue := reactiondomain.Value(strings.TrimSpace(body.Reaction))
	var trailing any
	if err := decoder.Decode(&trailing); err != io.EOF {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "请求体必须只包含一个 JSON 对象", "reaction request contains trailing JSON values"))
		return
	}
	actorID, err := requiredCommentPersona(r)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	actor, err := reactiondomain.NewActor(reactiondomain.ActorDimensionPersona, actorID)
	if err != nil {
		writeHTTPError(w, r, contentgenerated.AppErrorFromInvalidArgument(err.Error()))
		return
	}
	result, err := h.reactionService.ReactToComment(r.Context(), reactionapp.ReactToCommentCommand{
		CommentID: commentID,
		Actor:     actor,
		Reaction:  reactionValue,
	})
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (h *ContentHandler) handleBindMediaAssetsToComment(w http.ResponseWriter, r *http.Request, commentID string) {
	var body struct {
		AttachmentMediaIDs []string `json:"attachmentMediaIds"`
	}
	if err := decodeRequiredJSONBody(r, &body); err != nil {
		writeHTTPError(w, r, err)
		return
	}
	actorID, err := requiredCommentPersona(r)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	result, err := h.commentService.BindAttachments(r.Context(), commentapp.BindCommentAttachmentsCommand{
		CommentID: commentID, ActorID: actorID,
		AttachmentMediaIDs: body.AttachmentMediaIDs,
	})
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (h *ContentHandler) handleListCommentsByAuthor(w http.ResponseWriter, r *http.Request) {
	cursor := strings.TrimSpace(r.URL.Query().Get("cursor"))
	limit := 20
	if raw := r.URL.Query().Get("limit"); raw != "" {
		if n, err := strconv.Atoi(raw); err == nil && n > 0 {
			limit = n
		}
	}
	actorID, err := requiredCommentPersona(r)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	page, err := h.commentService.ListByAuthor(r.Context(), commentapp.ListCommentsByAuthorQuery{
		ActorID: actorID, Cursor: cursor, Limit: limit,
	})
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, page)
}

func (h *ContentHandler) handleListCommentsForPostAuthor(w http.ResponseWriter, r *http.Request) {
	cursor := strings.TrimSpace(r.URL.Query().Get("cursor"))
	limit := 20
	if raw := r.URL.Query().Get("limit"); raw != "" {
		if n, err := strconv.Atoi(raw); err == nil && n > 0 {
			limit = n
		}
	}
	actorID, err := requiredCommentPersona(r)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	page, err := h.commentService.ListReceivedByPostAuthor(r.Context(), commentapp.ListReceivedCommentsQuery{
		ActorID: actorID, Cursor: cursor, Limit: limit,
	})
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, page)
}
