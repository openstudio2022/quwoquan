package local_contract

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"quwoquan_service/runtime/operation"
	personamodel "quwoquan_service/services/user-service/internal/persona_management/persona/domain/model"
	proposalhttp "quwoquan_service/services/user-service/internal/persona_management/profile_update_proposal/adapters/inbound/http"
	proposalapp "quwoquan_service/services/user-service/internal/persona_management/profile_update_proposal/application"
)

type proposalErrorCodeRuntime struct {
	store  *migratedFacadeMemoryProposalStore
	writer *migratedFacadeRecordingPersonaWriter
	facade *proposalapp.Facade
	mux    *http.ServeMux
}

func newProposalErrorCodeRuntime(t *testing.T) *proposalErrorCodeRuntime {
	t.Helper()
	store := migratedFacadeNewMemoryProposalStore()
	writer := migratedFacadeNewPersonaWriter(8)
	facade, err := proposalapp.NewFacade(store, store, writer, writer)
	if err != nil {
		t.Fatalf("new facade: %v", err)
	}
	handler, err := proposalhttp.NewHandler(facade)
	if err != nil {
		t.Fatalf("new handler: %v", err)
	}
	mux := http.NewServeMux()
	handler.RegisterRoutes(mux)
	return &proposalErrorCodeRuntime{
		store:  store,
		writer: writer,
		facade: facade,
		mux:    mux,
	}
}

func (runtime *proposalErrorCodeRuntime) do(
	t *testing.T,
	method string,
	path string,
	operationID string,
	idempotencyKey string,
	body string,
) *httptest.ResponseRecorder {
	t.Helper()
	request := httptest.NewRequest(method, path, strings.NewReader(body))
	request = request.WithContext(operation.WithContext(
		request.Context(),
		operation.Context{
			OperationID:    operationID,
			RequestID:      "request-" + idempotencyKey,
			TraceID:        "trace-" + idempotencyKey,
			IdempotencyKey: idempotencyKey,
			Actor:          operation.ActorContext{PersonaID: "persona-1"},
		},
	))
	recorder := httptest.NewRecorder()
	runtime.mux.ServeHTTP(recorder, request)
	return recorder
}

func (runtime *proposalErrorCodeRuntime) mustReachAppliedState(
	t *testing.T,
	proposalID string,
	suffix string,
) {
	t.Helper()
	displayName := "applied " + suffix
	if _, err := runtime.facade.Create(context.Background(), migratedFacadeCreateCommand(
		proposalID,
		"persona-1",
		personamodel.ProfileChangeSet{DisplayName: &displayName},
		"create-"+suffix,
	)); err != nil {
		t.Fatalf("create %s: %v", proposalID, err)
	}
	if _, err := runtime.facade.Confirm(context.Background(), proposalapp.ConfirmCommand{
		ProposalID: proposalID, ActorPersonaID: "persona-1",
		IdempotencyKey: "confirm-" + suffix,
	}); err != nil {
		t.Fatalf("confirm %s: %v", proposalID, err)
	}
	if _, err := runtime.facade.Apply(context.Background(), proposalapp.ApplyCommand{
		ProposalID: proposalID, ActorPersonaID: "persona-1",
		IdempotencyKey: "apply-" + suffix,
		RequestID:      "request-apply-" + suffix, TraceID: "trace-apply-" + suffix,
	}); err != nil {
		t.Fatalf("apply %s: %v", proposalID, err)
	}
}

func assertProposalHTTPErrorCode(
	t *testing.T,
	recorder *httptest.ResponseRecorder,
	wantCode string,
) {
	t.Helper()
	var wire struct {
		Code string `json:"code"`
	}
	if err := json.Unmarshal(recorder.Body.Bytes(), &wire); err != nil {
		t.Fatalf("decode error response %q: %v", recorder.Body.String(), err)
	}
	if wire.Code != wantCode {
		t.Fatalf(
			"expected code %s, got %s (status=%d body=%s)",
			wantCode, wire.Code, recorder.Code, recorder.Body.String(),
		)
	}
}

func TestProfileProposalConfirmWithoutIdempotencyKeyReturnsInvalidArgument(
	t *testing.T,
) {
	t.Parallel()
	runtime := newProposalErrorCodeRuntime(t)

	recorder := runtime.do(
		t, http.MethodPost, "/user/profile/proposals/proposal-x/confirm",
		"user.profile_update_proposal.ConfirmProposal", "", "",
	)
	assertProposalHTTPErrorCode(
		t, recorder, "USER.PROFILE_PROPOSAL.invalid_argument",
	)
}

func TestProfileProposalConfirmUnknownProposalReturnsNotFound(t *testing.T) {
	t.Parallel()
	runtime := newProposalErrorCodeRuntime(t)

	recorder := runtime.do(
		t, http.MethodPost, "/user/profile/proposals/missing-proposal/confirm",
		"user.profile_update_proposal.ConfirmProposal", "confirm-missing", "",
	)
	assertProposalHTTPErrorCode(t, recorder, "USER.PROFILE_PROPOSAL.not_found")
}

func TestProfileProposalCreateWithReusedKeyReturnsIdempotencyConflict(
	t *testing.T,
) {
	t.Parallel()
	runtime := newProposalErrorCodeRuntime(t)

	createBody := func(reason string) string {
		payload, err := json.Marshal(map[string]any{
			"proposalId":   "proposal-key-reuse",
			"source":       "persona",
			"reason":       reason,
			"evidenceRefs": []string{"assistant-run:run-1"},
			"impactScope":  []string{"displayName"},
			"displayName":  "new name",
		})
		if err != nil {
			t.Fatalf("marshal create body: %v", err)
		}
		return string(payload)
	}
	first := runtime.do(
		t, http.MethodPost, "/user/personas/persona-1/profile-proposals",
		"user.profile_update_proposal.CreateProfileUpdateProposal",
		"create-key-reuse", createBody("第一次意图"),
	)
	if first.Code != http.StatusCreated {
		t.Fatalf("first create failed: status=%d body=%s", first.Code, first.Body.String())
	}

	second := runtime.do(
		t, http.MethodPost, "/user/personas/persona-1/profile-proposals",
		"user.profile_update_proposal.CreateProfileUpdateProposal",
		"create-key-reuse", createBody("完全不同的意图"),
	)
	assertProposalHTTPErrorCode(
		t, second, "USER.PROFILE_PROPOSAL.idempotency_conflict",
	)
}

func TestProfileProposalRejectAppliedProposalReturnsInvalidTransition(
	t *testing.T,
) {
	t.Parallel()
	runtime := newProposalErrorCodeRuntime(t)
	runtime.mustReachAppliedState(t, "proposal-reject-applied", "reject-applied")

	recorder := runtime.do(
		t, http.MethodPost, "/user/profile/proposals/proposal-reject-applied/reject",
		"user.profile_update_proposal.RejectProposal", "reject-applied", "",
	)
	assertProposalHTTPErrorCode(
		t, recorder, "USER.PROFILE_PROPOSAL.invalid_transition",
	)
}

func TestProfileProposalRollbackAfterDeadlineReturnsRollbackExpired(
	t *testing.T,
) {
	t.Parallel()
	runtime := newProposalErrorCodeRuntime(t)
	runtime.mustReachAppliedState(t, "proposal-rollback-late", "rollback-late")

	expired := runtime.store.proposals["proposal-rollback-late"]
	pastDeadline := time.Now().UTC().Add(-time.Hour)
	expired.RollbackDeadline = &pastDeadline
	runtime.store.proposals["proposal-rollback-late"] = expired

	recorder := runtime.do(
		t, http.MethodPost, "/user/profile/proposals/proposal-rollback-late/rollback",
		"user.profile_update_proposal.RollbackProposal", "rollback-late", "",
	)
	assertProposalHTTPErrorCode(
		t, recorder, "USER.PROFILE_PROPOSAL.rollback_expired",
	)
}

func TestProfileProposalRollbackAgainstNewerPersonaReturnsVersionConflict(
	t *testing.T,
) {
	t.Parallel()
	runtime := newProposalErrorCodeRuntime(t)
	runtime.mustReachAppliedState(t, "proposal-rollback-race", "rollback-race")

	// apply 之后 Persona 又被独立命令推进,受控回滚不得覆盖新版本。
	runtime.writer.snapshot.Version++
	runtime.writer.version = runtime.writer.snapshot.Version

	recorder := runtime.do(
		t, http.MethodPost, "/user/profile/proposals/proposal-rollback-race/rollback",
		"user.profile_update_proposal.RollbackProposal", "rollback-race", "",
	)
	assertProposalHTTPErrorCode(
		t, recorder, "USER.PROFILE_PROPOSAL.version_conflict",
	)
}
