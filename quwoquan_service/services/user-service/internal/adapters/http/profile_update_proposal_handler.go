package http

import (
	"encoding/base64"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"strconv"
	"strings"
	"time"

	"quwoquan_service/runtime/operation"
	proposalapp "quwoquan_service/services/user-service/internal/application/persona/profile_update_proposal"
	personamodel "quwoquan_service/services/user-service/internal/domain/persona/model"
	proposalmodel "quwoquan_service/services/user-service/internal/domain/persona/profile_update_proposal/model"
	proposalports "quwoquan_service/services/user-service/internal/domain/persona/profile_update_proposal/ports"
	"quwoquan_service/services/user-service/internal/generated"
)

const (
	createProfileProposalOperation  = "user.profile_update_proposal.CreateProfileUpdateProposal"
	confirmProfileProposalOperation = "user.profile_update_proposal.ConfirmProposal"
	applyProfileProposalOperation   = "user.profile_update_proposal.ApplyProposal"
	rejectProfileProposalOperation  = "user.profile_update_proposal.RejectProposal"
	getProfileProposalOperation     = "user.profile_update_proposal.GetProfileUpdateProposal"
	listProfileProposalOperation    = "user.profile_update_proposal.ListProfileUpdateProposals"
)

func (h *UserHandler) registerProfileProposalRoutes(mux *http.ServeMux) {
	mux.HandleFunc("POST /user/personas/{personaId}/profile-proposals", h.handleCreateProfileProposal)
	mux.HandleFunc("POST /user/profile/proposals/{id}/confirm", h.handleConfirmProfileProposal)
	mux.HandleFunc("POST /user/profile/proposals/{id}/apply", h.handleApplyProfileProposal)
	mux.HandleFunc("POST /user/profile/proposals/{id}/reject", h.handleRejectProfileProposal)
	mux.HandleFunc("GET /user/profile/proposals/{id}", h.handleGetProfileProposal)
	mux.HandleFunc("GET /user/personas/{personaId}/profile-proposals", h.handleListProfileProposals)
}

type profileProposalChangeRequest struct {
	DisplayName            *string `json:"displayName"`
	Bio                    *string `json:"bio"`
	AvatarMediaAssetID     *string `json:"avatarMediaAssetId"`
	BackgroundMediaAssetID *string `json:"backgroundMediaAssetId"`
	IsPrivate              *bool   `json:"isPrivate"`
	IsolationLevel         *string `json:"isolationLevel"`
	PurposeHint            *string `json:"purposeHint"`
}

func (r profileProposalChangeRequest) value() personamodel.ProfileChangeSet {
	return personamodel.ProfileChangeSet{
		DisplayName: r.DisplayName, Bio: r.Bio,
		AvatarMediaAssetID:     r.AvatarMediaAssetID,
		BackgroundMediaAssetID: r.BackgroundMediaAssetID,
		IsPrivate:              r.IsPrivate, IsolationLevel: r.IsolationLevel, PurposeHint: r.PurposeHint,
	}
}

type createProfileProposalRequest struct {
	ProposalID string `json:"proposalId"`
	Source     string `json:"source"`
	profileProposalChangeRequest
}

func (h *UserHandler) handleCreateProfileProposal(w http.ResponseWriter, r *http.Request) {
	invocation, ok := profileProposalInvocation(w, r, createProfileProposalOperation, true)
	if !ok {
		return
	}
	personaID := strings.TrimSpace(r.PathValue("personaId"))
	var request createProfileProposalRequest
	if err := decodeStrictJSON(r, &request); err != nil {
		writeHTTPError(w, r, generated.AppErrorFromProfileProposalInvalidArgument(err.Error()))
		return
	}
	receipt, err := h.profileProposal.Create(r.Context(), proposalapp.CreateCommand{
		ProposalID: strings.TrimSpace(request.ProposalID), ActorPersonaID: invocation.Actor.PersonaID,
		TargetPersonaID: personaID, Source: proposalmodel.Source(strings.TrimSpace(request.Source)),
		Changes: request.profileProposalChangeRequest.value(), IdempotencyKey: invocation.IdempotencyKey,
	})
	if err != nil {
		writeProfileProposalError(w, r, err)
		return
	}
	writeJSON(w, http.StatusCreated, receipt)
}

func (h *UserHandler) handleConfirmProfileProposal(w http.ResponseWriter, r *http.Request) {
	invocation, ok := profileProposalInvocation(w, r, confirmProfileProposalOperation, true)
	if !ok {
		return
	}
	if err := requireEmptyProfileProposalBody(r); err != nil {
		writeHTTPError(w, r, generated.AppErrorFromProfileProposalInvalidArgument(err.Error()))
		return
	}
	receipt, err := h.profileProposal.Confirm(r.Context(), proposalapp.ConfirmCommand{
		ProposalID: strings.TrimSpace(r.PathValue("id")), ActorPersonaID: invocation.Actor.PersonaID,
		IdempotencyKey: invocation.IdempotencyKey,
	})
	if err != nil {
		writeProfileProposalError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, receipt)
}

func (h *UserHandler) handleApplyProfileProposal(w http.ResponseWriter, r *http.Request) {
	invocation, ok := profileProposalInvocation(w, r, applyProfileProposalOperation, true)
	if !ok {
		return
	}
	if err := requireEmptyProfileProposalBody(r); err != nil {
		writeHTTPError(w, r, generated.AppErrorFromProfileProposalInvalidArgument(err.Error()))
		return
	}
	receipt, err := h.profileProposal.Apply(r.Context(), proposalapp.ApplyCommand{
		ProposalID: strings.TrimSpace(r.PathValue("id")), ActorPersonaID: invocation.Actor.PersonaID,
		IdempotencyKey: invocation.IdempotencyKey,
	})
	if err != nil {
		writeProfileProposalError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, receipt)
}

func (h *UserHandler) handleRejectProfileProposal(w http.ResponseWriter, r *http.Request) {
	invocation, ok := profileProposalInvocation(w, r, rejectProfileProposalOperation, true)
	if !ok {
		return
	}
	if err := requireEmptyProfileProposalBody(r); err != nil {
		writeHTTPError(w, r, generated.AppErrorFromProfileProposalInvalidArgument(err.Error()))
		return
	}
	receipt, err := h.profileProposal.Reject(r.Context(), proposalapp.RejectCommand{
		ProposalID: strings.TrimSpace(r.PathValue("id")), ActorPersonaID: invocation.Actor.PersonaID,
		IdempotencyKey: invocation.IdempotencyKey,
	})
	if err != nil {
		writeProfileProposalError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, receipt)
}

func (h *UserHandler) handleGetProfileProposal(w http.ResponseWriter, r *http.Request) {
	invocation, ok := profileProposalInvocation(w, r, getProfileProposalOperation, false)
	if !ok {
		return
	}
	proposal, err := h.profileProposal.Get(
		r.Context(),
		strings.TrimSpace(r.PathValue("id")),
		invocation.Actor.PersonaID,
	)
	if err != nil {
		writeProfileProposalError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, profileProposalViewFromModel(proposal))
}

func (h *UserHandler) handleListProfileProposals(w http.ResponseWriter, r *http.Request) {
	invocation, ok := profileProposalInvocation(w, r, listProfileProposalOperation, false)
	if !ok {
		return
	}
	limit, err := strictProfileProposalLimit(r)
	if err != nil {
		writeHTTPError(w, r, generated.AppErrorFromProfileProposalInvalidArgument(err.Error()))
		return
	}
	cursor, err := decodeProfileProposalCursor(r.URL.Query().Get("cursor"))
	if err != nil {
		writeHTTPError(w, r, generated.AppErrorFromProfileProposalInvalidArgument(err.Error()))
		return
	}
	slice, err := h.profileProposal.ListByPersona(
		r.Context(),
		strings.TrimSpace(r.PathValue("personaId")),
		invocation.Actor.PersonaID,
		cursor,
		limit,
	)
	if err != nil {
		writeProfileProposalError(w, r, err)
		return
	}
	items := make([]profileProposalView, 0, len(slice.Items))
	for _, proposal := range slice.Items {
		items = append(items, profileProposalViewFromModel(proposal))
	}
	var nextCursor *string
	if slice.NextCursor != nil {
		encoded := encodeProfileProposalCursor(*slice.NextCursor)
		nextCursor = &encoded
	}
	writeJSON(w, http.StatusOK, struct {
		Items      []profileProposalView `json:"items"`
		NextCursor *string               `json:"nextCursor,omitempty"`
	}{Items: items, NextCursor: nextCursor})
}

func profileProposalInvocation(
	w http.ResponseWriter,
	r *http.Request,
	expectedOperationID string,
	requireIdempotency bool,
) (operation.Context, bool) {
	invocation, ok := operation.FromContext(r.Context())
	if !ok || invocation.OperationID != expectedOperationID || strings.TrimSpace(invocation.Actor.PersonaID) == "" {
		writeHTTPError(w, r, generated.AppErrorFromUnauthorized("trusted Persona operation context is required"))
		return operation.Context{}, false
	}
	if requireIdempotency && strings.TrimSpace(invocation.IdempotencyKey) == "" {
		writeHTTPError(w, r, generated.AppErrorFromProfileProposalInvalidArgument("Idempotency-Key is required"))
		return operation.Context{}, false
	}
	return invocation, true
}

func decodeStrictJSON(r *http.Request, target any) error {
	decoder := json.NewDecoder(io.LimitReader(r.Body, 64*1024))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(target); err != nil {
		return err
	}
	if err := decoder.Decode(&struct{}{}); !errors.Is(err, io.EOF) {
		if err == nil {
			return errors.New("request body contains multiple JSON values")
		}
		return err
	}
	return nil
}

func requireEmptyProfileProposalBody(r *http.Request) error {
	body, err := io.ReadAll(io.LimitReader(r.Body, 64*1024))
	if err != nil {
		return err
	}
	if strings.TrimSpace(string(body)) != "" {
		return errors.New("request body must be empty")
	}
	return nil
}

type profileProposalView struct {
	ID                     string     `json:"id"`
	PersonaID              string     `json:"personaId"`
	Source                 string     `json:"source"`
	Status                 string     `json:"status"`
	DisplayName            *string    `json:"displayName,omitempty"`
	Bio                    *string    `json:"bio,omitempty"`
	AvatarMediaAssetID     *string    `json:"avatarMediaAssetId,omitempty"`
	BackgroundMediaAssetID *string    `json:"backgroundMediaAssetId,omitempty"`
	IsPrivate              *bool      `json:"isPrivate,omitempty"`
	IsolationLevel         *string    `json:"isolationLevel,omitempty"`
	PurposeHint            *string    `json:"purposeHint,omitempty"`
	ReviewedBy             *string    `json:"reviewedBy,omitempty"`
	Version                int64      `json:"version"`
	CreatedAt              time.Time  `json:"createdAt"`
	UpdatedAt              time.Time  `json:"updatedAt"`
	ResolvedAt             *time.Time `json:"resolvedAt,omitempty"`
}

func profileProposalViewFromModel(proposal proposalmodel.ProfileUpdateProposal) profileProposalView {
	var reviewedBy *string
	if proposal.ReviewedBy != "" {
		value := proposal.ReviewedBy
		reviewedBy = &value
	}
	return profileProposalView{
		ID: proposal.ID, PersonaID: proposal.PersonaID, Source: string(proposal.Source),
		Status: string(proposal.Status), DisplayName: proposal.ProposedChanges.DisplayName,
		Bio: proposal.ProposedChanges.Bio, AvatarMediaAssetID: proposal.ProposedChanges.AvatarMediaAssetID,
		BackgroundMediaAssetID: proposal.ProposedChanges.BackgroundMediaAssetID,
		IsPrivate:              proposal.ProposedChanges.IsPrivate, IsolationLevel: proposal.ProposedChanges.IsolationLevel,
		PurposeHint: proposal.ProposedChanges.PurposeHint, ReviewedBy: reviewedBy,
		Version: proposal.Version, CreatedAt: proposal.CreatedAt, UpdatedAt: proposal.UpdatedAt,
		ResolvedAt: proposal.ResolvedAt,
	}
}

type profileProposalCursorWire struct {
	CreatedAt time.Time `json:"createdAt"`
	ID        string    `json:"id"`
}

func encodeProfileProposalCursor(cursor proposalports.Cursor) string {
	payload, _ := json.Marshal(profileProposalCursorWire{CreatedAt: cursor.CreatedAt.UTC(), ID: cursor.ID})
	return base64.RawURLEncoding.EncodeToString(payload)
}

func decodeProfileProposalCursor(raw string) (*proposalports.Cursor, error) {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return nil, nil
	}
	payload, err := base64.RawURLEncoding.DecodeString(raw)
	if err != nil {
		return nil, errors.New("cursor is invalid")
	}
	var cursor profileProposalCursorWire
	decoder := json.NewDecoder(strings.NewReader(string(payload)))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&cursor); err != nil || cursor.CreatedAt.IsZero() || strings.TrimSpace(cursor.ID) == "" {
		return nil, errors.New("cursor is invalid")
	}
	return &proposalports.Cursor{CreatedAt: cursor.CreatedAt.UTC(), ID: strings.TrimSpace(cursor.ID)}, nil
}

func strictProfileProposalLimit(r *http.Request) (int, error) {
	raw := strings.TrimSpace(r.URL.Query().Get("limit"))
	if raw == "" {
		return 20, nil
	}
	limit, err := strconv.Atoi(raw)
	if err != nil || limit <= 0 || limit > 100 {
		return 0, errors.New("limit must be between 1 and 100")
	}
	return limit, nil
}

func writeProfileProposalError(w http.ResponseWriter, r *http.Request, err error) {
	switch {
	case errors.Is(err, proposalmodel.ErrNotFound), errors.Is(err, proposalmodel.ErrForbidden),
		errors.Is(err, personamodel.ErrNotFound), errors.Is(err, personamodel.ErrRetired):
		writeHTTPError(w, r, generated.AppErrorFromProfileProposalNotFound(err.Error()))
	case errors.Is(err, proposalmodel.ErrVersionConflict), errors.Is(err, personamodel.ErrVersionConflict):
		writeHTTPError(w, r, generated.AppErrorFromProfileProposalVersionConflict(err.Error()))
	case errors.Is(err, proposalmodel.ErrIdempotencyConflict), errors.Is(err, personamodel.ErrIdempotencyConflict):
		writeHTTPError(w, r, generated.AppErrorFromProfileProposalIdempotencyConflict(err.Error()))
	case errors.Is(err, proposalmodel.ErrInvalidTransition):
		writeHTTPError(w, r, generated.AppErrorFromProfileProposalInvalidTransition(err.Error()))
	case errors.Is(err, proposalmodel.ErrInvalidArgument), errors.Is(err, personamodel.ErrInvalidArgument):
		writeHTTPError(w, r, generated.AppErrorFromProfileProposalInvalidArgument(err.Error()))
	default:
		writeHTTPError(w, r, generated.AppErrorFromInternalError(err.Error()))
	}
}
