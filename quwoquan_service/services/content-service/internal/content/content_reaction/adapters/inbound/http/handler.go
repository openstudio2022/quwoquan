package http

import (
	"net/http"
	"strings"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/runtime/httpcodec"
	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
	reactionapp "quwoquan_service/services/content-service/internal/content/content_reaction/application/reaction"
	reactiondomain "quwoquan_service/services/content-service/internal/content/content_reaction/domain/reaction"
)

// Handler owns the ContentReaction HTTP boundary. The Post adapter only
// dispatches the generated route to this object-local adapter.
type Handler struct {
	reactions *reactionapp.Facades
}

func NewHandler(reactions *reactionapp.Facades) *Handler {
	if reactions == nil {
		panic("ContentReaction HTTP Handler requires object facades")
	}
	return &Handler{reactions: reactions}
}

func (handler *Handler) LikePost(writer http.ResponseWriter, request *http.Request, postID string) {
	actor, err := resolveActor(request)
	if err != nil {
		writeHTTPError(writer, request, err)
		return
	}
	result, err := handler.reactions.LikePost(
		request.Context(),
		reactionapp.LikePostCommand{PostID: strings.TrimSpace(postID), Actor: actor},
	)
	if err != nil {
		writeHTTPError(writer, request, err)
		return
	}
	writeJSON(writer, http.StatusOK, map[string]any{
		"reactionId": result.ReactionID,
		"postId":     strings.TrimSpace(postID),
		"version":    result.Version,
		"liked":      result.Liked,
		"changed":    result.Changed,
		"replayed":   result.Replayed,
	})
}

func (handler *Handler) UnlikePost(writer http.ResponseWriter, request *http.Request, postID string) {
	actor, err := resolveActor(request)
	if err != nil {
		writeHTTPError(writer, request, err)
		return
	}
	result, err := handler.reactions.UnlikePost(
		request.Context(),
		reactionapp.UnlikePostCommand{PostID: strings.TrimSpace(postID), Actor: actor},
	)
	if err != nil {
		writeHTTPError(writer, request, err)
		return
	}
	writeJSON(writer, http.StatusOK, map[string]any{
		"reactionId": result.ReactionID,
		"postId":     strings.TrimSpace(postID),
		"version":    result.Version,
		"liked":      result.Liked,
		"changed":    result.Changed,
		"replayed":   result.Replayed,
	})
}

func (handler *Handler) GetContentReactionState(
	writer http.ResponseWriter,
	request *http.Request,
	postID string,
) {
	actor, err := resolveActor(request)
	if err != nil {
		writeHTTPError(writer, request, err)
		return
	}
	slice, err := handler.reactions.GetContentReactionState(
		request.Context(),
		reactionapp.GetContentReactionStateQuery{PostID: strings.TrimSpace(postID), Actor: actor},
	)
	if err != nil {
		writeHTTPError(writer, request, err)
		return
	}
	payload := map[string]any{
		"found":   slice.Found,
		"postId":  slice.PostID,
		"liked":   slice.Liked,
		"version": slice.Version,
	}
	if !slice.UpdatedAt.IsZero() {
		payload["updatedAt"] = slice.UpdatedAt.UTC().Format(time.RFC3339Nano)
	}
	writeJSON(writer, http.StatusOK, payload)
}

func (handler *Handler) ReactToComment(
	writer http.ResponseWriter,
	request *http.Request,
	commentID string,
) {
	var body struct {
		Reaction string `json:"reaction"`
	}
	if err := httpcodec.DecodeStrictJSON(request, &body); err != nil {
		writeHTTPError(writer, request, rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"请求体解析失败",
			err.Error(),
		))
		return
	}
	actor, err := resolvePersonaActor(request)
	if err != nil {
		writeHTTPError(writer, request, err)
		return
	}
	result, err := handler.reactions.ReactToComment(
		request.Context(),
		reactionapp.ReactToCommentCommand{
			CommentID: strings.TrimSpace(commentID),
			Actor:     actor,
			Reaction:  reactiondomain.Value(strings.TrimSpace(body.Reaction)),
		},
	)
	if err != nil {
		writeHTTPError(writer, request, err)
		return
	}
	writeJSON(writer, http.StatusOK, result)
}

func resolveActor(request *http.Request) (reactiondomain.Actor, error) {
	principal, ok := rtauth.PrincipalFromContext(request.Context())
	if !ok {
		return reactiondomain.Actor{}, contentgenerated.AppErrorFromUnauthorized(
			"ContentReaction requires a verified persona or device principal",
		)
	}
	if personaID := strings.TrimSpace(principal.Actor.PersonaID); personaID != "" {
		return reactiondomain.NewActor(reactiondomain.ActorDimensionPersona, personaID)
	}
	if deviceActorID := strings.TrimSpace(principal.Actor.DeviceActorID); deviceActorID != "" {
		return reactiondomain.NewActor(reactiondomain.ActorDimensionDevice, deviceActorID)
	}
	return reactiondomain.Actor{}, contentgenerated.AppErrorFromUnauthorized(
		"ContentReaction principal has no persona or device actor",
	)
}

func resolvePersonaActor(request *http.Request) (reactiondomain.Actor, error) {
	principal, ok := rtauth.PrincipalFromContext(request.Context())
	if !ok || strings.TrimSpace(principal.Actor.PersonaID) == "" {
		return reactiondomain.Actor{}, contentgenerated.AppErrorFromUnauthorized(
			"Comment reaction requires a verified persona principal",
		)
	}
	return reactiondomain.NewActor(
		reactiondomain.ActorDimensionPersona,
		strings.TrimSpace(principal.Actor.PersonaID),
	)
}

func writeJSON(writer http.ResponseWriter, status int, payload any) {
	httpcodec.WriteJSON(writer, status, payload, "content_reaction")
}

func writeHTTPError(writer http.ResponseWriter, request *http.Request, err error) {
	rterr.WriteHTTPError(writer, err, rterr.HTTPWriteOptionsFromRequest(request))
}
