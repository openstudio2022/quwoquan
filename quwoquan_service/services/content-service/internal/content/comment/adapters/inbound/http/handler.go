package http

import (
	"encoding/json"
	"io"
	"net/http"
	"strconv"
	"strings"

	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/runtime/httpcodec"
	commenterrors "quwoquan_service/services/content-service/generated/content/comment"
	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
	commentapp "quwoquan_service/services/content-service/internal/content/comment/application"
	"quwoquan_service/services/content-service/internal/content/comment/application/iplocation"
	commentmodel "quwoquan_service/services/content-service/internal/content/comment/domain/model"
)

type Handler struct {
	comments *commentapp.Facades
}

func NewHandler(comments *commentapp.Facades) *Handler {
	if comments == nil {
		panic("Comment HTTP Handler requires object facades")
	}
	return &Handler{comments: comments}
}

func (handler *Handler) CreateComment(w http.ResponseWriter, r *http.Request, postID string) {
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
	// 属地快照：从受信代理头解析客户端 IP 注入 context，创建路径一次解析落库。
	ctx := iplocation.WithClientIP(r.Context(), iplocation.ParseTrustedClientIP(
		r.Header.Get("X-Forwarded-For"),
		r.Header.Get("X-Real-IP"),
		r.RemoteAddr,
	))
	result, err := handler.comments.CreateComment(ctx, commentapp.CreateCommentCommand{
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

func (handler *Handler) ListComments(w http.ResponseWriter, r *http.Request, postID string) {
	cursor := strings.TrimSpace(r.URL.Query().Get("cursor"))
	limit := 20
	if raw := r.URL.Query().Get("limit"); raw != "" {
		if n, err := strconv.Atoi(raw); err == nil && n > 0 {
			limit = n
		}
	}
	page, err := handler.comments.ListComments(r.Context(), commentapp.ListCommentsQuery{
		PostID:  postID,
		ActorID: optionalCommentPersona(r),
		Cursor:  cursor,
		Limit:   limit,
		Sort:    strings.TrimSpace(r.URL.Query().Get("sort")),
	})
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, page)
}

func (handler *Handler) ListCommentReplies(
	w http.ResponseWriter,
	r *http.Request,
	postID string,
	commentID string,
) {
	// /content/content/posts/{postId}/comments/{commentId}/replies
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
	page, err := handler.comments.ListReplies(r.Context(), commentapp.ListCommentRepliesQuery{
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

func (handler *Handler) DeleteComment(
	w http.ResponseWriter,
	r *http.Request,
	postID string,
	commentID string,
) {
	// /content/content/posts/{postId}/comments/{commentId}
	if postID == "" || commentID == "" {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "invalid path", "missing commentId"))
		return
	}
	actorID, err := requiredCommentPersona(r)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	result, err := handler.comments.DeleteComment(r.Context(), commentapp.DeleteCommentCommand{
		PostID: postID, CommentID: commentID, ActorID: actorID,
	})
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (handler *Handler) SetCommentPinned(
	w http.ResponseWriter,
	r *http.Request,
	postID string,
	commentID string,
	pinned bool,
) {
	// /content/content/posts/{postId}/comments/{commentId}/pin
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
		result, err = handler.comments.PinComment(r.Context(), command)
	} else {
		result, err = handler.comments.UnpinComment(r.Context(), command)
	}
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (handler *Handler) BindMediaAssetsToComment(w http.ResponseWriter, r *http.Request, commentID string) {
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
	result, err := handler.comments.BindAttachments(r.Context(), commentapp.BindCommentAttachmentsCommand{
		CommentID: commentID, ActorID: actorID,
		AttachmentMediaIDs: body.AttachmentMediaIDs,
	})
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (handler *Handler) ListCommentsByAuthor(w http.ResponseWriter, r *http.Request) {
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
	page, err := handler.comments.ListByAuthor(r.Context(), commentapp.ListCommentsByAuthorQuery{
		ActorID: actorID, Cursor: cursor, Limit: limit,
	})
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, page)
}

func (handler *Handler) ListCommentsForPostAuthor(w http.ResponseWriter, r *http.Request) {
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
	page, err := handler.comments.ListReceivedByPostAuthor(r.Context(), commentapp.ListReceivedCommentsQuery{
		ActorID: actorID, Cursor: cursor, Limit: limit,
	})
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, page)
}

func (handler *Handler) HideComment(
	w http.ResponseWriter,
	r *http.Request,
	commentID string,
) {
	handler.moderateComment(w, r, commentID, true)
}

func (handler *Handler) RestoreComment(
	w http.ResponseWriter,
	r *http.Request,
	commentID string,
) {
	handler.moderateComment(w, r, commentID, false)
}

func (handler *Handler) moderateComment(
	w http.ResponseWriter,
	r *http.Request,
	commentID string,
	hide bool,
) {
	if handler.comments == nil {
		writeHTTPError(
			w,
			r,
			contentgenerated.AppErrorFromStorageWriteFailed(
				"Comment command facades are not configured",
			),
		)
		return
	}
	commentID = strings.TrimSpace(commentID)
	if commentID == "" {
		writeHTTPError(
			w,
			r,
			contentgenerated.AppErrorFromInvalidArgument(
				"Comment moderation requires commentId",
			),
		)
		return
	}
	operatorID, ok := verifiedCommentOperatorAccountID(w, r)
	if !ok {
		return
	}
	var body struct {
		Reason string `json:"reason"`
	}
	if err := decodeRequiredJSONBody(r, &body); err != nil {
		writeHTTPError(w, r, err)
		return
	}
	var (
		result commentapp.CommentCommandResult
		err    error
	)
	if hide {
		result, err = handler.comments.HideComment(
			r.Context(),
			commentapp.HideCommentCommand{
				CommentID:  commentID,
				OperatorID: operatorID,
				Reason:     body.Reason,
			},
		)
	} else {
		result, err = handler.comments.RestoreComment(
			r.Context(),
			commentapp.RestoreCommentCommand{
				CommentID:  commentID,
				OperatorID: operatorID,
				Reason:     body.Reason,
			},
		)
	}
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func verifiedCommentOperatorAccountID(
	w http.ResponseWriter,
	r *http.Request,
) (string, bool) {
	principal, principalOK := rtauth.PrincipalFromContext(r.Context())
	descriptor, descriptorOK := rtauth.OperationDescriptorFromContext(r.Context())
	accountID := strings.TrimSpace(principal.Actor.AccountID)
	if principalOK &&
		accountID != "" &&
		descriptorOK &&
		descriptor.Principal == "operator" &&
		descriptor.CommercialStatus == "ready" &&
		(descriptor.CanonicalOperationID == "content.comment.HideComment" ||
			descriptor.CanonicalOperationID == "content.comment.RestoreComment") {
		return accountID, true
	}
	writeHTTPError(
		w,
		r,
		commenterrors.AppErrorFromCommentModerationForbidden(
			"verified ready operator operation principal is required for Comment moderation",
		),
	)
	return "", false
}

func requireJSONEOF(decoder *json.Decoder) error {
	var trailing any
	if err := decoder.Decode(&trailing); err != nil {
		if err == io.EOF {
			return nil
		}
		return rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"请求体必须只包含一个 JSON 对象",
			"request contains trailing JSON values",
		)
	}
	return rterr.NewInvalidArgument(
		rterr.ModuleContent,
		"请求体必须只包含一个 JSON 对象",
		"request contains trailing JSON values",
	)
}

func decodeRequiredJSONBody(request *http.Request, target any) error {
	if err := httpcodec.DecodeStrictJSON(request, target); err != nil {
		return rterr.NewInvalidArgument(rterr.ModuleContent, "请求体解析失败", err.Error())
	}
	return nil
}

func requiredCommentPersona(request *http.Request) (string, error) {
	principal, ok := rtauth.PrincipalFromContext(request.Context())
	if !ok || strings.TrimSpace(principal.Actor.PersonaID) == "" {
		return "", contentgenerated.AppErrorFromUnauthorized(
			"Comment operation requires verified persona principal",
		)
	}
	return strings.TrimSpace(principal.Actor.PersonaID), nil
}

func optionalCommentPersona(request *http.Request) string {
	if request == nil {
		return ""
	}
	principal, ok := rtauth.PrincipalFromContext(request.Context())
	if !ok {
		return ""
	}
	return strings.TrimSpace(principal.Actor.PersonaID)
}

func writeJSON(writer http.ResponseWriter, status int, payload any) {
	httpcodec.WriteJSON(writer, status, payload, "content_comment")
}

func writeHTTPError(writer http.ResponseWriter, request *http.Request, err error) {
	rterr.WriteHTTPError(writer, err, rterr.HTTPWriteOptionsFromRequest(request))
}
