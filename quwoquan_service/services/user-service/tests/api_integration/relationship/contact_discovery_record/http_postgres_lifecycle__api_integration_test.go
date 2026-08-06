// spec_ref: specs/feature-tree/user-identity-profile-relationship/spec.md#dom-001
// readiness_case: initiate-contact-discovery-api
// readiness_case: get-latest-contact-discovery-api
// readiness_case: dismiss-contact-discovery-api
package api_integration

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/jackc/pgx/v5/pgxpool"

	"quwoquan_service/runtime/operation"
	"quwoquan_service/services/user-service/internal/account/user_account/domain/user/phonematch"
	contacthttp "quwoquan_service/services/user-service/internal/relationship/contact_discovery_record/adapters/inbound/http"
	contactapp "quwoquan_service/services/user-service/internal/relationship/contact_discovery_record/application"
	contactpersistence "quwoquan_service/services/user-service/internal/relationship/contact_discovery_record/infrastructure/persistence"
	greetingapp "quwoquan_service/services/user-service/internal/relationship/greeting_request/application"
	greetingpersistence "quwoquan_service/services/user-service/internal/relationship/greeting_request/infrastructure/persistence"
	relationshipapp "quwoquan_service/services/user-service/internal/relationship/persona_relationship/application"
	relationshippersistence "quwoquan_service/services/user-service/internal/relationship/persona_relationship/infrastructure/persistence"
	usersupport "quwoquan_service/services/user-service/tests/support"
)

func TestContactDiscoveryProductionHTTPCompletesReadsAndDismissesInRealPostgres(t *testing.T) {
	usersupport.WithUserPostgres(t, func(ctx context.Context, pool *pgxpool.Pool) {
		if err := usersupport.SeedAccountPersona(
			ctx, pool, "contact-http-owner", "contact-http-persona",
		); err != nil {
			t.Fatal(err)
		}
		if err := usersupport.SeedAccountPersona(
			ctx, pool, "contact-match-owner", "contact-match-persona",
		); err != nil {
			t.Fatal(err)
		}
		const matchedPhone = "+8613800000099"
		if _, err := pool.Exec(ctx, `
			INSERT INTO credential_bindings (
			 id, owner_id, credential_type, credential_key,
			 display_label, is_active, bound_at
			) VALUES ($1,$2,'phone',$3,'',true,NOW())`,
			"contact-match-binding",
			"contact-match-owner",
			matchedPhone,
		); err != nil {
			t.Fatalf("seed matched phone CredentialBinding: %v", err)
		}

		contactStore := contactpersistence.NewPgContactDiscoveryStore(pool)
		contactService := contactapp.NewContactDiscoveryService(
			contactStore,
			contactHTTPEventPublisher{},
		)
		relationshipService := relationshipapp.NewPersonaRelationshipService(
			relationshippersistence.NewPgPersonaRelationshipStore(pool),
			nil,
			nil,
			nil,
		)
		greetingStore := greetingpersistence.NewPgGreetingStore(pool)
		greetingService := greetingapp.NewGreetingService(
			greetingStore,
			greetingStore,
			relationshipService,
			contactHTTPConversationGateway{},
			contactHTTPEventPublisher{},
			contactHTTPGreetingStream{},
			contactHTTPNotifyPolicy{},
		)
		handler, err := contacthttp.NewHandler(
			contactService,
			relationshipService,
			greetingService,
		)
		if err != nil {
			t.Fatal(err)
		}
		mux := http.NewServeMux()
		handler.RegisterRoutes(mux)

		privateHash := phonematch.Hash(matchedPhone)
		first := executeContactRequest(
			t,
			mux,
			http.MethodPost,
			"/owner/contact-discovery",
			`{"hashedPhones":["`+privateHash+`"]}`,
			"InitiateContactDiscovery",
			"initiate-contact-http-1",
			"request-initiate-1",
		)
		if first.Code != http.StatusAccepted {
			t.Fatalf("initiate status=%d body=%s", first.Code, first.Body.String())
		}
		firstPayload := decodeContactHTTPPayload(t, first)
		recordID, _ := firstPayload["id"].(string)
		if recordID == "" || firstPayload["status"] != "completed" {
			t.Fatalf("initiate result drifted: %+v", firstPayload)
		}
		assertContactHTTPMatch(t, firstPayload, privateHash, "contact-match-persona")
		if strings.Contains(first.Body.String(), matchedPhone) ||
			strings.Contains(first.Body.String(), "contact-match-owner") ||
			strings.Contains(first.Body.String(), "ownerAccountId") {
			t.Fatalf("initiate leaked private discovery state: %s", first.Body.String())
		}

		replayed := executeContactRequest(
			t,
			mux,
			http.MethodPost,
			"/owner/contact-discovery",
			`{"hashedPhones":["`+privateHash+`"]}`,
			"InitiateContactDiscovery",
			"initiate-contact-http-1",
			"request-initiate-2",
		)
		if replayed.Code != http.StatusAccepted || decodeContactHTTPPayload(t, replayed)["id"] != recordID {
			t.Fatalf("initiate replay drifted: status=%d body=%s", replayed.Code, replayed.Body.String())
		}

		latest := executeContactRequest(
			t,
			mux,
			http.MethodGet,
			"/owner/contact-discovery/latest",
			"",
			"GetLatestContactDiscovery",
			"",
			"request-latest-1",
		)
		if latest.Code != http.StatusOK || decodeContactHTTPPayload(t, latest)["id"] != recordID {
			t.Fatalf("latest drifted: status=%d body=%s", latest.Code, latest.Body.String())
		}
		assertContactHTTPMatch(t, decodeContactHTTPPayload(t, latest), privateHash, "contact-match-persona")
		if strings.Contains(latest.Body.String(), matchedPhone) ||
			strings.Contains(latest.Body.String(), "contact-match-owner") ||
			strings.Contains(latest.Body.String(), "ownerAccountId") {
			t.Fatalf("latest leaked private discovery state: %s", latest.Body.String())
		}

		dismiss := executeContactRequest(
			t,
			mux,
			http.MethodDelete,
			"/owner/contact-discovery/"+recordID,
			"",
			"DismissContactDiscovery",
			"dismiss-contact-http-1",
			"request-dismiss-1",
		)
		if dismiss.Code != http.StatusOK || decodeContactHTTPPayload(t, dismiss)["status"] != "ok" {
			t.Fatalf("dismiss drifted: status=%d body=%s", dismiss.Code, dismiss.Body.String())
		}
		dismissReplay := executeContactRequest(
			t,
			mux,
			http.MethodDelete,
			"/owner/contact-discovery/"+recordID,
			"",
			"DismissContactDiscovery",
			"dismiss-contact-http-1",
			"request-dismiss-2",
		)
		if dismissReplay.Code != http.StatusOK {
			t.Fatalf("dismiss replay status=%d body=%s", dismissReplay.Code, dismissReplay.Body.String())
		}

		latestAfterDismiss := executeContactRequest(
			t,
			mux,
			http.MethodGet,
			"/owner/contact-discovery/latest",
			"",
			"GetLatestContactDiscovery",
			"",
			"request-latest-2",
		)
		latestPayload := decodeContactHTTPPayload(t, latestAfterDismiss)
		if latestAfterDismiss.Code != http.StatusOK || latestPayload["status"] != "dismissed" {
			t.Fatalf("dismissed readback drifted: status=%d body=%s", latestAfterDismiss.Code, latestAfterDismiss.Body.String())
		}

		var recordCount, receiptCount int
		if err := pool.QueryRow(
			ctx,
			`SELECT COUNT(*) FROM contact_discovery_records WHERE owner_account_id=$1`,
			"contact-http-owner",
		).Scan(&recordCount); err != nil {
			t.Fatal(err)
		}
		if err := pool.QueryRow(
			ctx,
			`SELECT COUNT(*) FROM contact_discovery_command_receipts WHERE owner_account_id=$1`,
			"contact-http-owner",
		).Scan(&receiptCount); err != nil {
			t.Fatal(err)
		}
		if recordCount != 1 || receiptCount != 2 {
			t.Fatalf("HTTP lifecycle duplicated durable state: records=%d receipts=%d", recordCount, receiptCount)
		}
	})
}

func executeContactRequest(
	t *testing.T,
	mux *http.ServeMux,
	method string,
	path string,
	body string,
	operationID string,
	idempotencyKey string,
	requestID string,
) *httptest.ResponseRecorder {
	t.Helper()
	request := httptest.NewRequest(method, path, strings.NewReader(body))
	request.Header.Set("Content-Type", "application/json")
	request = request.WithContext(operation.WithContext(request.Context(), operation.Context{
		OperationID:    operationID,
		RequestID:      requestID,
		TraceID:        "trace-" + requestID,
		IdempotencyKey: idempotencyKey,
		Actor: operation.ActorContext{
			AccountID: "contact-http-owner",
			PersonaID: "contact-http-persona",
		},
	}))
	recorder := httptest.NewRecorder()
	mux.ServeHTTP(recorder, request)
	return recorder
}

func decodeContactHTTPPayload(
	t *testing.T,
	recorder *httptest.ResponseRecorder,
) map[string]any {
	t.Helper()
	var payload map[string]any
	if err := json.Unmarshal(recorder.Body.Bytes(), &payload); err != nil {
		t.Fatalf("decode response body %q: %v", recorder.Body.String(), err)
	}
	return payload
}

func assertContactHTTPMatch(
	t *testing.T,
	payload map[string]any,
	hashedPhone string,
	personaID string,
) {
	t.Helper()
	matchedIDs, ok := payload["matchedPersonaIds"].([]any)
	if !ok || len(matchedIDs) != 1 || matchedIDs[0] != personaID {
		t.Fatalf("matched persona IDs drifted: %+v", payload)
	}
	matches, ok := payload["matches"].([]any)
	if !ok || len(matches) != 1 {
		t.Fatalf("enriched matches drifted: %+v", payload)
	}
	match, ok := matches[0].(map[string]any)
	if !ok || match["personaId"] != personaID || match["hashedPhone"] != hashedPhone {
		t.Fatalf("enriched match identity drifted: %+v", matches[0])
	}
}

type contactHTTPConversationGateway struct{}

func (contactHTTPConversationGateway) PromoteGreetingToDirect(
	context.Context,
	string,
	string,
	greetingapp.GreetingPromotion,
) (string, error) {
	return "", nil
}

func (contactHTTPConversationGateway) HasDirectBetween(
	context.Context,
	string,
	string,
) (bool, error) {
	return false, nil
}

type contactHTTPEventPublisher struct{}

func (contactHTTPEventPublisher) PublishUserEvent(
	context.Context,
	string,
	string,
	string,
	map[string]any,
) error {
	return nil
}

type contactHTTPGreetingStream struct{}

func (contactHTTPGreetingStream) PublishGreetingEvent(
	context.Context,
	greetingapp.GreetingStreamEvent,
) error {
	return nil
}

type contactHTTPNotifyPolicy struct{}

func (contactHTTPNotifyPolicy) AllowsStrangerGreeting(
	context.Context,
	string,
) (bool, error) {
	return true, nil
}
