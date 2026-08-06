// spec_ref: specs/feature-tree/assistant-run-learning/profile-proposal-apply-loop/proposal-confirm-reject/spec.md#gwt-001
// spec_ref: specs/feature-tree/assistant-run-learning/profile-proposal-apply-loop/proposal-create-review/spec.md#gwt-001
// spec_ref: specs/feature-tree/assistant-run-learning/profile-proposal-apply-loop/proposal-apply-audit/spec.md#gwt-001
// readiness_case: create-profile-update-proposal-api
// readiness_case: confirm-profile-update-proposal-api
// readiness_case: apply-profile-update-proposal-api
// readiness_case: reject-profile-update-proposal-api
// readiness_case: rollback-profile-update-proposal-api
// readiness_case: get-profile-update-proposal-api
// readiness_case: list-profile-update-proposals-api
package api_integration

import (
	"bytes"
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/jackc/pgx/v5/pgxpool"
	"quwoquan_service/runtime/operation"
	personaapp "quwoquan_service/services/user-service/internal/persona_management/persona/application/persona"
	personamodel "quwoquan_service/services/user-service/internal/persona_management/persona/domain/model"
	personapersistence "quwoquan_service/services/user-service/internal/persona_management/persona/infrastructure/persona/persistence"
	proposalhttp "quwoquan_service/services/user-service/internal/persona_management/profile_update_proposal/adapters/inbound/http"
	proposalapp "quwoquan_service/services/user-service/internal/persona_management/profile_update_proposal/application"
	proposalmodel "quwoquan_service/services/user-service/internal/persona_management/profile_update_proposal/domain/model"
	proposalpersistence "quwoquan_service/services/user-service/internal/persona_management/profile_update_proposal/infrastructure/persistence"
	usersupport "quwoquan_service/services/user-service/tests/support"
)

func TestProfileUpdateProposalPostgresCreateReplayAndOutbox(t *testing.T) {
	usersupport.WithUserPostgres(t, func(ctx context.Context, pool *pgxpool.Pool) {
		if err := usersupport.SeedAccountPersona(ctx, pool, "proposal-owner", "proposal-persona"); err != nil {
			t.Fatal(err)
		}
		store, err := proposalpersistence.NewPostgresStore(pool)
		if err != nil {
			t.Fatal(err)
		}
		personaStore, err := personapersistence.NewProfileProposalPostgresStore(pool)
		if err != nil {
			t.Fatal(err)
		}
		personaFacade, err := personaapp.NewProfileProposalFacade(personaStore)
		if err != nil {
			t.Fatal(err)
		}
		facade, err := proposalapp.NewFacade(store, store, personaFacade, personaStore)
		if err != nil {
			t.Fatal(err)
		}
		displayName := "待确认公开名称"
		command := proposalapp.CreateCommand{
			ProposalID: "profile-proposal-1", ActorPersonaID: "proposal-persona", TargetPersonaID: "proposal-persona",
			Source: proposalmodel.SourceAssistant, Changes: personamodel.ProfileChangeSet{DisplayName: &displayName},
			Reason: "用户可审核的画像建议", EvidenceRefs: []string{"assistant-run:run-1"}, ImpactScope: []string{"displayName"},
			IdempotencyKey: "proposal-create-key", RequestID: "proposal-request", TraceID: "proposal-trace",
		}
		first, err := facade.Create(ctx, command)
		if err != nil {
			t.Fatal(err)
		}
		replayed, err := facade.Create(ctx, command)
		if err != nil || !replayed.Replayed || replayed.Version != first.Version {
			t.Fatalf("ProfileUpdateProposal replay drift: first=%+v replay=%+v err=%v", first, replayed, err)
		}
		var stateCount, outboxCount int
		if err := pool.QueryRow(ctx, `SELECT COUNT(*) FROM profile_update_proposals WHERE id=$1`, command.ProposalID).Scan(&stateCount); err != nil {
			t.Fatal(err)
		}
		if err := pool.QueryRow(ctx, `SELECT COUNT(*) FROM profile_update_proposals_outbox WHERE aggregate_id=$1`, command.ProposalID).Scan(&outboxCount); err != nil {
			t.Fatal(err)
		}
		if stateCount != 1 || outboxCount != 1 {
			t.Fatalf("ProfileUpdateProposal packet mismatch: state=%d outbox=%d", stateCount, outboxCount)
		}

		handler, err := proposalhttp.NewHandler(facade)
		if err != nil {
			t.Fatal(err)
		}
		mux := http.NewServeMux()
		handler.RegisterRoutes(mux)
		serve := func(method, path, operationID, idempotencyKey, body string) *httptest.ResponseRecorder {
			request := httptest.NewRequest(method, path, bytes.NewBufferString(body))
			request.Header.Set("Content-Type", "application/json")
			request = request.WithContext(operation.WithContext(request.Context(), operation.Context{
				OperationID:    operationID,
				RequestID:      "profile-proposal-http-request",
				TraceID:        "profile-proposal-http-trace",
				IdempotencyKey: idempotencyKey,
				Actor:          operation.ActorContext{PersonaID: "proposal-persona"},
			}))
			response := httptest.NewRecorder()
			mux.ServeHTTP(response, request)
			return response
		}
		assertStatus := func(name string, response *httptest.ResponseRecorder, want int) {
			t.Helper()
			if response.Code != want {
				t.Fatalf("production %s status=%d want=%d body=%s", name, response.Code, want, response.Body.String())
			}
		}
		create := func(id, key, displayName string) {
			response := serve(
				http.MethodPost,
				"/user/personas/proposal-persona/profile-proposals",
				"user.profile_update_proposal.CreateProfileUpdateProposal",
				key,
				`{"proposalId":"`+id+`","source":"assistant","reason":"用户审核的资料建议","evidenceRefs":["assistant-run:run-http"],"impactScope":["displayName"],"displayName":"`+displayName+`"}`,
			)
			assertStatus("CreateProfileUpdateProposal", response, http.StatusCreated)
		}

		create("profile-proposal-http-1", "profile-proposal-create-http-1", "公开名称一")
		assertStatus("GetProfileUpdateProposal", serve(
			http.MethodGet,
			"/user/profile/proposals/profile-proposal-http-1",
			"user.profile_update_proposal.GetProfileUpdateProposal",
			"",
			"",
		), http.StatusOK)
		assertStatus("ListProfileUpdateProposals", serve(
			http.MethodGet,
			"/user/personas/proposal-persona/profile-proposals?limit=20",
			"user.profile_update_proposal.ListProfileUpdateProposals",
			"",
			"",
		), http.StatusOK)
		assertStatus("ConfirmProposal", serve(
			http.MethodPost,
			"/user/profile/proposals/profile-proposal-http-1/confirm",
			"user.profile_update_proposal.ConfirmProposal",
			"profile-proposal-confirm-http-1",
			"",
		), http.StatusOK)
		assertStatus("ApplyProposal", serve(
			http.MethodPost,
			"/user/profile/proposals/profile-proposal-http-1/apply",
			"user.profile_update_proposal.ApplyProposal",
			"profile-proposal-apply-http-1",
			"",
		), http.StatusOK)
		assertStatus("RollbackProposal", serve(
			http.MethodPost,
			"/user/profile/proposals/profile-proposal-http-1/rollback",
			"user.profile_update_proposal.RollbackProposal",
			"profile-proposal-rollback-http-1",
			"",
		), http.StatusOK)

		create("profile-proposal-http-2", "profile-proposal-create-http-2", "公开名称二")
		assertStatus("RejectProposal", serve(
			http.MethodPost,
			"/user/profile/proposals/profile-proposal-http-2/reject",
			"user.profile_update_proposal.RejectProposal",
			"profile-proposal-reject-http-2",
			"",
		), http.StatusOK)

		var terminalCount int
		if err := pool.QueryRow(ctx, `
SELECT COUNT(*) FROM profile_update_proposals
WHERE id IN ('profile-proposal-http-1','profile-proposal-http-2')
  AND status IN ('rolled_back','rejected')`).Scan(&terminalCount); err != nil {
			t.Fatal(err)
		}
		rows, err := pool.Query(ctx, `
SELECT event_type, COUNT(*)
FROM profile_update_proposals_outbox
WHERE aggregate_id IN ('profile-proposal-http-1','profile-proposal-http-2')
GROUP BY event_type`)
		if err != nil {
			t.Fatal(err)
		}
		defer rows.Close()
		actualEvents := map[string]int{}
		for rows.Next() {
			var eventType string
			var count int
			if err := rows.Scan(&eventType, &count); err != nil {
				t.Fatal(err)
			}
			actualEvents[eventType] = count
		}
		if err := rows.Err(); err != nil {
			t.Fatal(err)
		}
		expectedEvents := map[string]int{
			"ProfileUpdateProposalCreated":         2,
			"ProfileUpdateProposalConfirmed":       1,
			"ProfileUpdateProposalApplyStarted":    1,
			"ProfileUpdateProposalApplied":         1,
			"ProfileUpdateProposalRollbackStarted": 1,
			"ProfileUpdateProposalRolledBack":      1,
			"ProfileUpdateProposalRejected":        1,
		}
		if terminalCount != 2 || len(actualEvents) != len(expectedEvents) {
			t.Fatalf("production ProfileUpdateProposal HTTP packet: terminal=%d events=%v", terminalCount, actualEvents)
		}
		for eventType, want := range expectedEvents {
			if got := actualEvents[eventType]; got != want {
				t.Fatalf("production ProfileUpdateProposal event %s count=%d want=%d; all=%v", eventType, got, want, actualEvents)
			}
		}
	})
}
