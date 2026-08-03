// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/skill-user-lifecycle/spec.md#gwt-001
package api_integration

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	consenthttp "quwoquan_service/services/assistant-service/internal/assistant/skill_consent/adapters/inbound/http"
	consentapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_consent/application"
	consentmodel "quwoquan_service/services/assistant-service/internal/assistant/skill_consent/domain/model"
)

func newSkillConsentHandler() http.Handler {
	mux := http.NewServeMux()
	consenthttp.NewHandler(
		consentapplication.NewCommandFacade(skillConsentStore, nil),
		consentapplication.NewQueryFacade(skillConsentStore),
	).RegisterRoutes(mux)
	return mux
}

func skillConsentRequest(
	t *testing.T,
	handler http.Handler,
	method, path, accountID, idempotencyKey string,
	body any,
) *httptest.ResponseRecorder {
	t.Helper()
	payload, err := json.Marshal(body)
	if err != nil {
		t.Fatalf("marshal SkillConsent request: %v", err)
	}
	request := httptest.NewRequest(method, path, bytes.NewReader(payload))
	request.Header.Set("Content-Type", "application/json")
	if idempotencyKey != "" {
		request.Header.Set("Idempotency-Key", idempotencyKey)
	}
	if accountID != "" {
		request = request.WithContext(rtauth.WithPrincipal(
			request.Context(),
			rtauth.Principal{Actor: operation.ActorContext{AccountID: accountID}},
		))
	}
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	return recorder
}

func TestSkillConsentHTTPContractPersistsReceiptAndEvent(t *testing.T) {
	resetSkillConsentState(t)
	handler := newSkillConsentHandler()
	path := "/assistant/skills/personal_content_access/consent"

	granted := skillConsentRequest(
		t,
		handler,
		http.MethodPost,
		path,
		"consent-http-account",
		"consent-http-grant",
		map[string]any{"grantedScopes": []string{"personal_content_access", "travel.trip.read"}},
	)
	if granted.Code != http.StatusOK {
		t.Fatalf("grant status=%d body=%s", granted.Code, granted.Body.String())
	}
	var grantPayload struct {
		Consent struct {
			ID            string   `json:"id"`
			AccountID     string   `json:"accountId"`
			SkillID       string   `json:"skillId"`
			GrantedScopes []string `json:"grantedScopes"`
			Granted       bool     `json:"granted"`
		} `json:"consent"`
		Replayed bool `json:"replayed"`
	}
	if err := json.Unmarshal(granted.Body.Bytes(), &grantPayload); err != nil {
		t.Fatalf("decode grant response: %v", err)
	}
	if grantPayload.Consent.ID == "" ||
		grantPayload.Consent.AccountID != "consent-http-account" ||
		grantPayload.Consent.SkillID != "personal_content_access" ||
		len(grantPayload.Consent.GrantedScopes) != 2 ||
		!grantPayload.Consent.Granted || grantPayload.Replayed {
		t.Fatalf("grant response=%+v", grantPayload)
	}

	replay := skillConsentRequest(
		t,
		handler,
		http.MethodPost,
		path,
		"consent-http-account",
		"consent-http-grant",
		map[string]any{"grantedScopes": []string{"travel.trip.read", "personal_content_access"}},
	)
	if replay.Code != http.StatusOK ||
		!strings.Contains(replay.Body.String(), `"replayed":true`) {
		t.Fatalf("grant replay status=%d body=%s", replay.Code, replay.Body.String())
	}

	conflict := skillConsentRequest(
		t,
		handler,
		http.MethodPost,
		"/assistant/skills/another_skill/consent",
		"consent-http-account",
		"consent-http-grant",
		map[string]any{"grantedScopes": []string{"another_scope"}},
	)
	if conflict.Code != http.StatusConflict ||
		!strings.Contains(conflict.Body.String(), "consent_idempotency_conflict") {
		t.Fatalf("grant conflict status=%d body=%s", conflict.Code, conflict.Body.String())
	}

	list := skillConsentRequest(
		t,
		handler,
		http.MethodGet,
		"/assistant/consents",
		"consent-http-account",
		"",
		nil,
	)
	if list.Code != http.StatusOK ||
		!strings.Contains(list.Body.String(), `"granted":true`) ||
		!strings.Contains(list.Body.String(), `"grantedScopes":["personal_content_access","travel.trip.read"]`) {
		t.Fatalf("list status=%d body=%s", list.Code, list.Body.String())
	}

	scopeConflict := skillConsentRequest(
		t,
		handler,
		http.MethodPost,
		path,
		"consent-http-account",
		"consent-http-scope-conflict",
		map[string]any{"grantedScopes": []string{"personal_content_access", "travel.trip.read", "travel.stay.read"}},
	)
	if scopeConflict.Code != http.StatusConflict ||
		!strings.Contains(scopeConflict.Body.String(), "consent_scope_conflict") {
		t.Fatalf(
			"scope conflict status=%d body=%s",
			scopeConflict.Code,
			scopeConflict.Body.String(),
		)
	}

	revoked := skillConsentRequest(
		t,
		handler,
		http.MethodDelete,
		path,
		"consent-http-account",
		"consent-http-revoke",
		nil,
	)
	if revoked.Code != http.StatusOK {
		t.Fatalf("revoke status=%d body=%s", revoked.Code, revoked.Body.String())
	}

	var receipts, events int
	if err := skillConsentPool.QueryRow(
		context.Background(),
		`SELECT COUNT(*) FROM skill_consent_command_receipts`,
	).Scan(&receipts); err != nil {
		t.Fatalf("count receipts: %v", err)
	}
	if err := skillConsentPool.QueryRow(
		context.Background(),
		`SELECT COUNT(*) FROM skill_consent_events`,
	).Scan(&events); err != nil {
		t.Fatalf("count events: %v", err)
	}
	if receipts != 2 || events != 2 {
		t.Fatalf("receipt/event counts=%d/%d, want 2/2", receipts, events)
	}
}

func TestSkillConsentConcurrentGrantKeepsOneActiveFact(t *testing.T) {
	resetSkillConsentState(t)
	commands := consentapplication.NewCommandFacade(skillConsentStore, nil)
	type commandResult struct {
		result consentmodel.MutationResult
		err    error
	}
	results := make(chan commandResult, 2)
	var wait sync.WaitGroup
	for _, key := range []string{"concurrent-grant-a", "concurrent-grant-b"} {
		key := key
		wait.Add(1)
		go func() {
			defer wait.Done()
			result, err := commands.Grant(
				context.Background(),
				key,
				"concurrent-account",
				"personal_content_access",
				[]string{"personal_content_access", "travel.trip.read"},
			)
			results <- commandResult{result: result, err: err}
		}()
	}
	wait.Wait()
	close(results)
	changed := 0
	for result := range results {
		if result.err != nil {
			t.Fatalf("concurrent grant error=%v", result.err)
		}
		if result.result.Replayed {
			t.Fatalf("distinct command was reported as replay=%+v", result.result)
		}
		if result.result.Changed {
			changed++
		}
	}
	if changed != 1 {
		t.Fatalf("concurrent changed commands=%d, want 1", changed)
	}
	var active, receipts, events int
	if err := skillConsentPool.QueryRow(context.Background(), `
SELECT
  (SELECT COUNT(*) FROM skill_consents WHERE account_id='concurrent-account' AND revoked_at IS NULL),
  (SELECT COUNT(*) FROM skill_consent_command_receipts WHERE account_id='concurrent-account'),
  (SELECT COUNT(*) FROM skill_consent_events WHERE account_id='concurrent-account')`,
	).Scan(&active, &receipts, &events); err != nil {
		t.Fatalf("count concurrent grant facts: %v", err)
	}
	if active != 1 || receipts != 2 || events != 1 {
		t.Fatalf("active/receipt/event=%d/%d/%d, want 1/2/1", active, receipts, events)
	}
}

func TestSkillConsentGrantRevokeGrantKeepsImmutableHistory(t *testing.T) {
	resetSkillConsentState(t)
	ctx := context.Background()
	commands := consentapplication.NewCommandFacade(skillConsentStore, nil)
	first, err := commands.Grant(
		ctx,
		"history-grant-first",
		"history-account",
		"personal_content_access",
		[]string{"personal_content_access"},
	)
	if err != nil || first.Consent == nil {
		t.Fatalf("first grant result=%+v error=%v", first, err)
	}
	if _, err := commands.Revoke(
		ctx,
		"history-revoke",
		"history-account",
		"personal_content_access",
	); err != nil {
		t.Fatalf("revoke error=%v", err)
	}
	second, err := commands.Grant(
		ctx,
		"history-grant-second",
		"history-account",
		"personal_content_access",
		[]string{"personal_content_access"},
	)
	if err != nil || second.Consent == nil {
		t.Fatalf("second grant result=%+v error=%v", second, err)
	}
	if second.Consent.ID == first.Consent.ID {
		t.Fatalf("new authorization fact reused revoked id=%s", second.Consent.ID)
	}
	var total, active, receipts, events int
	if err := skillConsentPool.QueryRow(ctx, `
SELECT
  (SELECT COUNT(*) FROM skill_consents WHERE account_id='history-account'),
  (SELECT COUNT(*) FROM skill_consents WHERE account_id='history-account' AND revoked_at IS NULL),
  (SELECT COUNT(*) FROM skill_consent_command_receipts WHERE account_id='history-account'),
  (SELECT COUNT(*) FROM skill_consent_events WHERE account_id='history-account')`,
	).Scan(&total, &active, &receipts, &events); err != nil {
		t.Fatalf("count history facts: %v", err)
	}
	if total != 2 || active != 1 || receipts != 3 || events != 3 {
		t.Fatalf(
			"total/active/receipt/event=%d/%d/%d/%d, want 2/1/3/3",
			total,
			active,
			receipts,
			events,
		)
	}
}

func TestSkillConsentHTTPRejectsMissingPrincipalAndCommandIdentity(t *testing.T) {
	resetSkillConsentState(t)
	handler := newSkillConsentHandler()
	path := "/assistant/skills/personal_content_access/consent"
	unauthorized := skillConsentRequest(
		t,
		handler,
		http.MethodPost,
		path,
		"",
		"unauthorized-command",
		map[string]any{"grantedScopes": []string{"personal_content_access"}},
	)
	if unauthorized.Code != http.StatusUnauthorized ||
		!strings.Contains(unauthorized.Body.String(), "ASSISTANT.USER.consent_unauthorized") {
		t.Fatalf("unauthorized status=%d body=%s", unauthorized.Code, unauthorized.Body.String())
	}
	missingKey := skillConsentRequest(
		t,
		handler,
		http.MethodPost,
		path,
		"identity-account",
		"",
		map[string]any{"grantedScopes": []string{"personal_content_access"}},
	)
	if missingKey.Code != http.StatusBadRequest ||
		!strings.Contains(missingKey.Body.String(), "consent_invalid_argument") {
		t.Fatalf("missing key status=%d body=%s", missingKey.Code, missingKey.Body.String())
	}
	missingScope := skillConsentRequest(
		t,
		handler,
		http.MethodPost,
		path,
		"identity-account",
		"missing-scope-command",
		map[string]any{},
	)
	if missingScope.Code != http.StatusBadRequest ||
		!strings.Contains(missingScope.Body.String(), "consent_invalid_argument") {
		t.Fatalf(
			"missing scope status=%d body=%s",
			missingScope.Code,
			missingScope.Body.String(),
		)
	}
}
