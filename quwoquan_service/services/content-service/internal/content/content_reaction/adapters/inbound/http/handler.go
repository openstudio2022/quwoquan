package http

import (
	"net/http"
	"strings"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/commandmeta"
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
	var body struct {
		MutationBasis   string `json:"mutationBasis"`
		ExpectedVersion *int64 `json:"expectedVersion"`
	}
	if err := httpcodec.DecodeStrictJSON(request, &body); err != nil || strings.TrimSpace(body.MutationBasis) == "" || body.ExpectedVersion == nil || *body.ExpectedVersion < 0 {
		writeHTTPError(writer, request, rterr.NewInvalidArgument(rterr.ModuleContent, "请求体解析失败", "mutationBasis and expectedVersion are required"))
		return
	}
	result, err := handler.reactions.LikePost(
		request.Context(),
		reactionapp.LikePostCommand{PostID: strings.TrimSpace(postID), Actor: actor, Evidence: reactionapp.MutationEvidence{MutationBasis: strings.TrimSpace(body.MutationBasis), ExpectedVersion: *body.ExpectedVersion}},
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
	var body struct {
		MutationBasis   string `json:"mutationBasis"`
		ExpectedVersion *int64 `json:"expectedVersion"`
	}
	if err := httpcodec.DecodeStrictJSON(request, &body); err != nil || strings.TrimSpace(body.MutationBasis) == "" || body.ExpectedVersion == nil || *body.ExpectedVersion < 0 {
		writeHTTPError(writer, request, rterr.NewInvalidArgument(rterr.ModuleContent, "请求体解析失败", "mutationBasis and expectedVersion are required"))
		return
	}
	result, err := handler.reactions.UnlikePost(
		request.Context(),
		reactionapp.UnlikePostCommand{PostID: strings.TrimSpace(postID), Actor: actor, Evidence: reactionapp.MutationEvidence{MutationBasis: strings.TrimSpace(body.MutationBasis), ExpectedVersion: *body.ExpectedVersion}},
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
		"found":         slice.Found,
		"postId":        slice.PostID,
		"liked":         slice.Liked,
		"version":       slice.Version,
		"mutationBasis": slice.MutationBasis,
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
		Reaction        string `json:"reaction"`
		MutationBasis   string `json:"mutationBasis"`
		ExpectedVersion *int64 `json:"expectedVersion"`
	}
	if err := httpcodec.DecodeStrictJSON(request, &body); err != nil || strings.TrimSpace(body.MutationBasis) == "" || body.ExpectedVersion == nil || *body.ExpectedVersion < 0 {
		writeHTTPError(writer, request, rterr.NewInvalidArgument(rterr.ModuleContent, "请求体解析失败", "reaction, mutationBasis and expectedVersion are required"))
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
			Evidence:  reactionapp.MutationEvidence{MutationBasis: strings.TrimSpace(body.MutationBasis), ExpectedVersion: derefVersion(body.ExpectedVersion)},
		},
	)
	if err != nil {
		writeHTTPError(writer, request, err)
		return
	}
	writeJSON(writer, http.StatusOK, result)
}

func derefVersion(value *int64) int64 {
	if value == nil {
		return -1
	}
	return *value
}

func (handler *Handler) GetPresentation(w http.ResponseWriter, r *http.Request, targetKind, targetID string) {
	actor, err := resolveActor(r)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	identity, err := reactionIdentity(targetKind, targetID, actor)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	result, err := handler.reactions.GetContentReactionPresentation(r.Context(), identity)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	stats := map[string]any{"targetKind": string(result.Target.Kind), "targetId": result.Target.ID, "state": string(result.Statistics.State)}
	if x := result.Statistics.Snapshot; x != nil {
		stats["snapshot"] = map[string]any{"generation": x.Generation, "statsVersion": x.StatsVersion, "likeCount": x.LikeCount, "dislikeCount": x.DislikeCount, "sourceCheckpoint": x.SourceCheckpoint, "asOf": x.AsOf.UTC().Format(time.RFC3339Nano), "expiresAt": x.ExpiresAt.UTC().Format(time.RFC3339Nano)}
	}
	attachment := map[string]any{"targetKind": string(result.Target.Kind), "targetId": result.Target.ID, "state": result.ViewerAttachment.State}
	if result.ViewerAttachment.Reaction != nil {
		attachment["reaction"] = string(*result.ViewerAttachment.Reaction)
		attachment["version"] = *result.ViewerAttachment.Version
	}
	writeJSON(w, http.StatusOK, map[string]any{"targetKind": string(result.Target.Kind), "targetId": result.Target.ID, "statistics": stats, "viewerAttachment": attachment})
}

func (handler *Handler) GetMutationBasis(w http.ResponseWriter, r *http.Request, targetKind, targetID string) {
	actor, err := resolveActor(r)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	identity, err := reactionIdentity(targetKind, targetID, actor)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	result, err := handler.reactions.GetContentReactionMutationBasis(r.Context(), reactionapp.GetContentReactionMutationBasisQuery{Identity: identity})
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"targetKind": result.TargetKind, "targetId": result.TargetID, "mutationBasis": result.MutationBasis, "expectedVersion": result.ExpectedVersion})
}

func (handler *Handler) RecoverCommand(w http.ResponseWriter, r *http.Request, targetKind, targetID, operation string) {
	actor, err := resolveActor(r)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	identity, err := reactionIdentity(targetKind, targetID, actor)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	result, err := handler.reactions.RecoverCommand(r.Context(), reactionapp.RecoverContentReactionCommand{Identity: identity, CommandName: operation, IdempotencyKey: commandmeta.IdempotencyKey(r.Context())})
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, recoveryPayload(result))
}
func (handler *Handler) FinalizeExpiredCommand(w http.ResponseWriter, r *http.Request, targetKind, targetID, operation string) {
	actor, err := resolveActor(r)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	var body struct {
		MutationBasis   string `json:"mutationBasis"`
		ExpectedVersion *int64 `json:"expectedVersion"`
	}
	if err := httpcodec.DecodeStrictJSON(r, &body); err != nil || body.ExpectedVersion == nil {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleContent, "请求体解析失败", "mutation evidence required"))
		return
	}
	identity, err := reactionIdentity(targetKind, targetID, actor)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	desired := reactiondomain.ValueNone
	if operation == "LikePost" {
		desired = reactiondomain.ValueLike
	}
	result, err := handler.reactions.FinalizeExpiredCommand(r.Context(), reactionapp.FinalizeExpiredContentReactionCommand{Identity: identity, CommandName: operation, Desired: desired, IdempotencyKey: commandmeta.IdempotencyKey(r.Context()), Evidence: reactionapp.MutationEvidence{MutationBasis: body.MutationBasis, ExpectedVersion: *body.ExpectedVersion}})
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, recoveryPayload(result))
}
func reactionIdentity(kind, id string, actor reactiondomain.Actor) (reactiondomain.Identity, error) {
	if kind == "post" {
		return reactiondomain.NewPostIdentity(id, actor)
	}
	if kind == "comment" {
		return reactiondomain.NewCommentIdentity(id, actor)
	}
	return reactiondomain.Identity{}, rterr.NewInvalidArgument(rterr.ModuleContent, "互动目标无效", "unknown reaction target kind")
}
func recoveryPayload(r reactionapp.ContentReactionCommandRecoveryResult) map[string]any {
	p := map[string]any{"idempotencyKey": r.IdempotencyKey, "outcome": r.Outcome, "replayed": r.Replayed}
	if r.CommittedVersion != nil {
		p["committedVersion"] = *r.CommittedVersion
	}
	if r.Changed != nil {
		p["changed"] = *r.Changed
	}
	return p
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
