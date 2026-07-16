package http

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"quwoquan_service/runtime/operation"
	proposalapp "quwoquan_service/services/user-service/internal/application/persona/profile_update_proposal"
	personaports "quwoquan_service/services/user-service/internal/domain/persona/persona/ports"
	proposalmodel "quwoquan_service/services/user-service/internal/domain/persona/profile_update_proposal/model"
	proposalports "quwoquan_service/services/user-service/internal/domain/persona/profile_update_proposal/ports"
)

type handlerProposalStore struct {
	proposal proposalmodel.ProfileUpdateProposal
}

func (s *handlerProposalStore) Load(_ context.Context, id string) (proposalmodel.ProfileUpdateProposal, error) {
	if s.proposal.ID != id {
		return proposalmodel.ProfileUpdateProposal{}, proposalmodel.ErrNotFound
	}
	return s.proposal, nil
}

func (s *handlerProposalStore) Get(ctx context.Context, id string) (proposalmodel.ProfileUpdateProposal, error) {
	return s.Load(ctx, id)
}

func (s *handlerProposalStore) ListByPersona(_ context.Context, personaID string, _ *proposalports.Cursor, _ int) (proposalports.Slice, error) {
	if s.proposal.PersonaID != personaID {
		return proposalports.Slice{}, nil
	}
	return proposalports.Slice{Items: []proposalmodel.ProfileUpdateProposal{s.proposal}}, nil
}

func (*handlerProposalStore) Replay(context.Context, string, string, string) (proposalports.CommitReceipt, bool, error) {
	return proposalports.CommitReceipt{}, false, nil
}

func (s *handlerProposalStore) Commit(_ context.Context, _ int64, changes proposalports.ChangeSet) (proposalports.CommitReceipt, error) {
	s.proposal = changes.Proposal
	return proposalports.CommitReceipt{
		ProposalID: changes.Proposal.ID,
		Version:    changes.Proposal.Version,
		Status:     string(changes.Proposal.Status),
	}, nil
}

type handlerPersonaWriter struct{}

func (handlerPersonaWriter) ApplyProfileProposal(context.Context, personaports.ApplyProfileProposalCommand) error {
	return nil
}

func (handlerPersonaWriter) CurrentVersion(context.Context, string) (int64, error) {
	return 1, nil
}

func newProfileProposalHandlerForTest(t *testing.T, store *handlerProposalStore) *UserHandler {
	t.Helper()
	facade, err := proposalapp.NewFacade(
		store,
		store,
		handlerPersonaWriter{},
		handlerPersonaWriter{},
	)
	if err != nil {
		t.Fatalf("new facade: %v", err)
	}
	return &UserHandler{profileProposal: facade}
}

func profileProposalRequest(method, target, body, operationID, actor, idempotencyKey string) *http.Request {
	request := httptest.NewRequest(method, target, strings.NewReader(body))
	request.Header.Set("Content-Type", "application/json")
	return request.WithContext(operation.WithContext(request.Context(), operation.Context{
		OperationID: operationID, RequestID: "request-1", TraceID: "trace-1",
		IdempotencyKey: idempotencyKey,
		Actor:          operation.ActorContext{PersonaID: actor},
	}))
}

func responseCode(t *testing.T, recorder *httptest.ResponseRecorder) string {
	t.Helper()
	var body struct {
		Code string `json:"code"`
	}
	if err := json.Unmarshal(recorder.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode error response: %v body=%s", err, recorder.Body.String())
	}
	return body.Code
}

func TestProfileProposalHTTPRequiresTrustedInvocationAndIdempotency(t *testing.T) {
	t.Parallel()
	handler := newProfileProposalHandlerForTest(t, &handlerProposalStore{})

	request := httptest.NewRequest(http.MethodPost, "/v1/user/personas/persona-1/profile-proposals", strings.NewReader(`{}`))
	request.SetPathValue("personaId", "persona-1")
	recorder := httptest.NewRecorder()
	handler.handleCreateProfileProposal(recorder, request)
	if recorder.Code != http.StatusUnauthorized || responseCode(t, recorder) != "USER.USER.unauthorized" {
		t.Fatalf("missing trusted invocation was not denied: status=%d body=%s", recorder.Code, recorder.Body.String())
	}

	request = profileProposalRequest(
		http.MethodPost,
		"/v1/user/personas/persona-1/profile-proposals",
		`{"proposalId":"proposal-1","source":"persona","displayName":"new name"}`,
		createProfileProposalOperation,
		"persona-1",
		"",
	)
	request.SetPathValue("personaId", "persona-1")
	recorder = httptest.NewRecorder()
	handler.handleCreateProfileProposal(recorder, request)
	if recorder.Code != http.StatusBadRequest || responseCode(t, recorder) != "USER.PROFILE_PROPOSAL.invalid_argument" {
		t.Fatalf("missing idempotency key was not rejected: status=%d body=%s", recorder.Code, recorder.Body.String())
	}
}

func TestProfileProposalHTTPStrictBodyOwnerAndCursor(t *testing.T) {
	t.Parallel()
	store := &handlerProposalStore{}
	handler := newProfileProposalHandlerForTest(t, store)

	request := profileProposalRequest(
		http.MethodPost,
		"/v1/user/personas/persona-1/profile-proposals",
		`{"proposalId":"proposal-1","source":"persona","displayName":"new name","legacyMedia":{}}`,
		createProfileProposalOperation,
		"persona-1",
		"create-1",
	)
	request.SetPathValue("personaId", "persona-1")
	recorder := httptest.NewRecorder()
	handler.handleCreateProfileProposal(recorder, request)
	if recorder.Code != http.StatusBadRequest || responseCode(t, recorder) != "USER.PROFILE_PROPOSAL.invalid_argument" {
		t.Fatalf("unknown field was accepted: status=%d body=%s", recorder.Code, recorder.Body.String())
	}

	request = profileProposalRequest(
		http.MethodPost,
		"/v1/user/profile/proposals/proposal-1/confirm",
		`{"expectedProposalVersion":1,"expectedTargetPersonaVersion":1}`,
		confirmProfileProposalOperation,
		"persona-1",
		"confirm-legacy",
	)
	request.SetPathValue("id", "proposal-1")
	recorder = httptest.NewRecorder()
	handler.handleConfirmProfileProposal(recorder, request)
	if recorder.Code != http.StatusBadRequest || responseCode(t, recorder) != "USER.PROFILE_PROPOSAL.invalid_argument" {
		t.Fatalf("retired target-version field was accepted: status=%d body=%s", recorder.Code, recorder.Body.String())
	}

	request = profileProposalRequest(
		http.MethodPost,
		"/v1/user/personas/persona-1/profile-proposals",
		`{"proposalId":"proposal-1","source":"persona","displayName":"new name"}`,
		createProfileProposalOperation,
		"persona-1",
		"create-1",
	)
	request.SetPathValue("personaId", "persona-1")
	recorder = httptest.NewRecorder()
	handler.handleCreateProfileProposal(recorder, request)
	if recorder.Code != http.StatusCreated || store.proposal.ID != "proposal-1" {
		t.Fatalf("valid create failed: status=%d body=%s", recorder.Code, recorder.Body.String())
	}

	request = profileProposalRequest(
		http.MethodGet,
		"/v1/user/profile/proposals/proposal-1",
		"",
		getProfileProposalOperation,
		"persona-2",
		"",
	)
	request.SetPathValue("id", "proposal-1")
	recorder = httptest.NewRecorder()
	handler.handleGetProfileProposal(recorder, request)
	if recorder.Code != http.StatusNotFound || responseCode(t, recorder) != "USER.PROFILE_PROPOSAL.not_found" {
		t.Fatalf("foreign actor learned proposal existence: status=%d body=%s", recorder.Code, recorder.Body.String())
	}

	wantCursor := proposalports.Cursor{CreatedAt: time.Date(2026, 7, 16, 7, 0, 0, 0, time.UTC), ID: "proposal-1"}
	gotCursor, err := decodeProfileProposalCursor(encodeProfileProposalCursor(wantCursor))
	if err != nil || gotCursor == nil || !gotCursor.CreatedAt.Equal(wantCursor.CreatedAt) || gotCursor.ID != wantCursor.ID {
		t.Fatalf("cursor round trip mismatch: got=%#v err=%v", gotCursor, err)
	}
}

func TestProfileProposalHTTPDoesNotMaskInfrastructureFailureAsClientError(t *testing.T) {
	t.Parallel()
	recorder := httptest.NewRecorder()
	request := httptest.NewRequest(http.MethodGet, "/v1/user/profile/proposals/proposal-1", nil)
	writeProfileProposalError(recorder, request, errors.New("database unavailable"))
	if recorder.Code != http.StatusInternalServerError || responseCode(t, recorder) != "USER.SYSTEM.internal_error" {
		t.Fatalf("infrastructure error was misclassified: status=%d body=%s", recorder.Code, recorder.Body.String())
	}
}
