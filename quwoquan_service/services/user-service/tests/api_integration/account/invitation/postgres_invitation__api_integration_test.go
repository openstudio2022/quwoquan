// spec_ref: specs/feature-tree/user-identity-profile-relationship/spec.md#dom-001
// readiness_case: generate-invitation-api
// readiness_case: list-invitations-api
// readiness_case: get-invitation-by-code-api
// readiness_case: accept-invitation-api
package api_integration

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/jackc/pgx/v5/pgxpool"
	"quwoquan_service/runtime/operation"
	invitationhttp "quwoquan_service/services/user-service/internal/account/invitation/adapters/inbound/http"
	invitationapp "quwoquan_service/services/user-service/internal/account/invitation/application"
	invitationpersistence "quwoquan_service/services/user-service/internal/account/invitation/infrastructure/persistence"
	personapersistence "quwoquan_service/services/user-service/internal/persona_management/persona/infrastructure/persona/persistence"
	usersupport "quwoquan_service/services/user-service/tests/support"
)

func TestInvitationPostgresLifecycleUsesPersonaAuthority(t *testing.T) {
	usersupport.WithUserPostgres(t, func(ctx context.Context, pool *pgxpool.Pool) {
		if err := usersupport.SeedAccountPersona(ctx, pool, "invitation-owner", "invitation-persona"); err != nil {
			t.Fatal(err)
		}
		store, err := invitationpersistence.NewPostgresStore(pool)
		if err != nil {
			t.Fatal(err)
		}
		facade, err := invitationapp.NewFacade(store, personapersistence.NewOwnerReader(pool))
		if err != nil {
			t.Fatal(err)
		}
		created, err := facade.Generate(
			ctx, "invitation-owner", "invitation-persona", "link", "", "generate-invitation-1",
		)
		if err != nil || created.LinkCode == "" {
			t.Fatalf("generate Invitation: value=%+v err=%v", created, err)
		}
		replayed, err := facade.Generate(
			ctx, "invitation-owner", "invitation-persona", "link", "", "generate-invitation-1",
		)
		if err != nil || replayed.ID != created.ID || replayed.LinkCode != created.LinkCode {
			t.Fatalf("replay Invitation: value=%+v original=%+v err=%v", replayed, created, err)
		}
		if _, err := facade.Generate(
			ctx, "invitation-owner", "invitation-persona", "direct", "", "generate-invitation-1",
		); err == nil {
			t.Fatal("same idempotency key with a different command must conflict")
		}
		delivered, err := facade.GetByCode(ctx, created.LinkCode)
		if err != nil || delivered.Status != "delivered" {
			t.Fatalf("deliver Invitation: value=%+v err=%v", delivered, err)
		}
		var count int
		if err := pool.QueryRow(ctx, `SELECT COUNT(*) FROM invite_records WHERE inviter_persona_id=$1`, "invitation-persona").Scan(&count); err != nil || count != 1 {
			t.Fatalf("Invitation rows=%d err=%v", count, err)
		}
		if err := pool.QueryRow(ctx, `SELECT COUNT(*) FROM invitation_command_receipts WHERE owner_account_id=$1`, "invitation-owner").Scan(&count); err != nil || count != 1 {
			t.Fatalf("Invitation command receipts=%d err=%v", count, err)
		}

		handler, err := invitationhttp.NewHandler(facade)
		if err != nil {
			t.Fatal(err)
		}
		mux := http.NewServeMux()
		handler.RegisterRoutes(mux)
		withActor := func(request *http.Request, operationID, accountID, idempotencyKey string) *http.Request {
			return request.WithContext(operation.WithContext(request.Context(), operation.Context{
				OperationID: operationID, RequestID: "invitation-api-integration",
				TraceID: "invitation-api-integration", IdempotencyKey: idempotencyKey,
				Actor: operation.ActorContext{AccountID: accountID},
			}))
		}

		generateRequest := httptest.NewRequest(
			http.MethodPost,
			"/user/invites",
			bytes.NewBufferString(`{"personaId":"invitation-persona","channel":"link"}`),
		)
		generateRequest.Header.Set("Content-Type", "application/json")
		generateResponse := httptest.NewRecorder()
		mux.ServeHTTP(generateResponse, withActor(
			generateRequest,
			"user.invitation.GenerateInvitation",
			"invitation-owner",
			"generate-invitation-http",
		))
		if generateResponse.Code != http.StatusCreated {
			t.Fatalf("production GenerateInvitation HTTP status=%d body=%s", generateResponse.Code, generateResponse.Body.String())
		}
		var generated struct {
			LinkCode string `json:"linkCode"`
		}
		if err := json.Unmarshal(generateResponse.Body.Bytes(), &generated); err != nil || generated.LinkCode == "" {
			t.Fatalf("decode production invitation: value=%+v err=%v", generated, err)
		}

		listRequest := httptest.NewRequest(
			http.MethodGet,
			"/user/invites?personaId=invitation-persona&limit=20&offset=0",
			nil,
		)
		listResponse := httptest.NewRecorder()
		mux.ServeHTTP(listResponse, withActor(
			listRequest,
			"user.invitation.ListInvitations",
			"invitation-owner",
			"",
		))
		if listResponse.Code != http.StatusOK || !bytes.Contains(listResponse.Body.Bytes(), []byte(generated.LinkCode)) {
			t.Fatalf("production ListInvitations HTTP status=%d body=%s", listResponse.Code, listResponse.Body.String())
		}

		getResponse := httptest.NewRecorder()
		mux.ServeHTTP(getResponse, httptest.NewRequest(
			http.MethodGet,
			"/invites/"+generated.LinkCode,
			nil,
		))
		if getResponse.Code != http.StatusOK {
			t.Fatalf("production GetInvitationByCode HTTP status=%d body=%s", getResponse.Code, getResponse.Body.String())
		}

		acceptRequest := httptest.NewRequest(
			http.MethodPost,
			"/invites/"+generated.LinkCode+"/accept",
			nil,
		)
		acceptResponse := httptest.NewRecorder()
		mux.ServeHTTP(acceptResponse, withActor(
			acceptRequest,
			"user.invitation.AcceptInvitation",
			"invitation-recipient",
			"accept-invitation-http",
		))
		if acceptResponse.Code != http.StatusOK {
			t.Fatalf("production AcceptInvitation HTTP status=%d body=%s", acceptResponse.Code, acceptResponse.Body.String())
		}
		var acceptedStatus string
		if err := pool.QueryRow(
			ctx,
			`SELECT status FROM invite_records WHERE link_code=$1`,
			generated.LinkCode,
		).Scan(&acceptedStatus); err != nil || acceptedStatus != "accepted" {
			t.Fatalf("production HTTP invitation state=%q err=%v", acceptedStatus, err)
		}
	})
}
