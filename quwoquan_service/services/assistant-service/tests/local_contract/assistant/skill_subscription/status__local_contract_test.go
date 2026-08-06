// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-001
// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/skill-user-lifecycle/spec.md#gwt-002
// readiness_case: list-skill-subscriptions-local
// readiness_case: create-skill-subscription-local
// readiness_case: get-skill-subscription-local
// readiness_case: update-skill-subscription-status-local
// readiness_case: tick-skill-subscription-cron-local
package skill_subscription_test

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	subscriptionhttp "quwoquan_service/services/assistant-service/internal/assistant/skill_subscription/adapters/inbound/http"
	subscriptionapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_subscription/application"
	skillmodel "quwoquan_service/services/assistant-service/internal/assistant/skill_subscription/domain/model"
	subscriptionpersistence "quwoquan_service/services/assistant-service/internal/assistant/skill_subscription/infrastructure/persistence"
)

type localSubscriptionTicker struct {
	calls int
	input skillmodel.SkillSubscriptionCronTickInput
}

func (ticker *localSubscriptionTicker) TickSkillSubscriptionCron(
	_ context.Context,
	input skillmodel.SkillSubscriptionCronTickInput,
) (skillmodel.SkillSubscriptionCronTickResult, error) {
	ticker.calls++
	ticker.input = input
	return skillmodel.SkillSubscriptionCronTickResult{
		ProcessedCount:    1,
		CreatedTurnIDs:    []string{"turn-local"},
		CreatedMessageIDs: []string{"message-local"},
	}, nil
}

func TestSkillSubscriptionTriggerTimezoneIsDeclaredByObjectLocalContracts(t *testing.T) {
	root := filepath.Join(
		"..", "..", "..", "..", "contracts", "assistant", "skill_subscription",
	)
	for _, fileName := range []string{"fields.yaml", "schema.yaml"} {
		raw, err := os.ReadFile(filepath.Join(root, fileName))
		if err != nil {
			t.Fatalf("read %s: %v", fileName, err)
		}
		if !strings.Contains(string(raw), "timezone") {
			t.Fatalf("%s does not expose canonical trigger timezone", fileName)
		}
	}
}

// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/skill-user-lifecycle/spec.md#gwt-003
func TestListSkillSubscriptionsKeepsMultipleStableIDsForOneSkill(t *testing.T) {
	t.Parallel()
	store := subscriptionpersistence.NewMemoryStore()
	now := time.Date(2026, 8, 4, 11, 0, 0, 0, time.UTC)
	for index, id := range []string{"subscription-a", "subscription-b"} {
		store.SeedSkillSubscription(skillmodel.SkillSubscription{
			SubscriptionID: id,
			Version:        1,
			Owner: skillmodel.SkillSubscriptionOwner{
				OwnerType: "user",
				OwnerID:   "account-a",
			},
			CreatedByUserID: "account-a",
			SkillID:         "travel_companion",
			DomainID:        "travel",
			Status:          skillmodel.SkillSubscriptionStatusActive,
			CreatedAt:       now.Add(time.Duration(index) * time.Minute),
			UpdatedAt:       now.Add(time.Duration(index) * time.Minute),
		})
	}
	view, err := subscriptionapplication.NewUseCases(
		store, nil, nil, func() time.Time { return now },
	).List(context.Background(), "account-a", "", 20)
	if err != nil {
		t.Fatalf("List() error=%v", err)
	}
	if len(view.Items) != 2 ||
		view.Items[0].SubscriptionID != "subscription-b" ||
		view.Items[1].SubscriptionID != "subscription-a" ||
		view.Items[0].SkillID != view.Items[1].SkillID {
		t.Fatalf("List() collapsed or reordered identities: %+v", view.Items)
	}
}

func TestSkillSubscriptionArchivedIsTerminal(t *testing.T) {
	for _, transition := range [][2]string{
		{"active", "paused"}, {"active", "archived"},
		{"paused", "active"}, {"paused", "archived"},
		{"active", "active"}, {"archived", "archived"},
	} {
		if err := skillmodel.ValidateTransition(transition[0], transition[1]); err != nil {
			t.Fatalf("transition=%v err=%v", transition, err)
		}
	}
	for _, target := range []string{"active", "paused"} {
		if err := skillmodel.ValidateTransition("archived", target); !errors.Is(err, skillmodel.ErrInvalidTransition) {
			t.Fatalf("archived -> %s err=%v", target, err)
		}
	}
}

func TestSkillSubscriptionHTTPRoutesShareOneObjectApplicationBoundary(t *testing.T) {
	t.Parallel()
	store := subscriptionpersistence.NewMemoryStore()
	ticker := &localSubscriptionTicker{}
	mux := http.NewServeMux()
	subscriptionhttp.NewHandler(subscriptionapplication.NewUseCases(
		store,
		nil,
		ticker,
		func() time.Time { return time.Date(2026, 8, 5, 9, 0, 0, 0, time.UTC) },
	)).RegisterRoutes(mux)

	created := localSkillSubscriptionRequest(
		t,
		mux,
		http.MethodPost,
		"/assistant/skill-subscriptions",
		"account-local",
		"create-subscription-local",
		map[string]any{
			"skillId":  "news_briefing",
			"domainId": "news",
			"tagRefs":  []string{"daily"},
			"searchQueryPlan": map[string]any{
				"rawText": "daily news",
				"queries": []string{"daily news"},
			},
			"trigger": map[string]any{
				"type":     "cron",
				"cron":     "30 8 * * *",
				"timezone": "Asia/Shanghai",
			},
			"destination": map[string]any{
				"destinationType":  "user",
				"maxPerDay":        1,
				"cooldownMinutes":  60,
				"quietHoursPolicy": "inherit_user_setting",
			},
			"clientRequestId": "create-subscription-local",
		},
	)
	if created.Code != http.StatusCreated {
		t.Fatalf("create status=%d body=%s", created.Code, created.Body.String())
	}
	var item skillmodel.SkillSubscription
	if err := json.Unmarshal(created.Body.Bytes(), &item); err != nil {
		t.Fatalf("decode create response: %v", err)
	}
	if item.SubscriptionID == "" || item.Status != skillmodel.SkillSubscriptionStatusActive {
		t.Fatalf("created subscription=%+v", item)
	}

	listed := localSkillSubscriptionRequest(
		t,
		mux,
		http.MethodGet,
		"/assistant/skill-subscriptions?limit=20",
		"account-local",
		"",
		nil,
	)
	if listed.Code != http.StatusOK {
		t.Fatalf("list status=%d body=%s", listed.Code, listed.Body.String())
	}
	var listView skillmodel.SkillSubscriptionListView
	if err := json.Unmarshal(listed.Body.Bytes(), &listView); err != nil {
		t.Fatalf("decode list response: %v", err)
	}
	if len(listView.Items) != 1 || listView.Items[0].SubscriptionID != item.SubscriptionID {
		t.Fatalf("list response=%+v", listView)
	}

	loaded := localSkillSubscriptionRequest(
		t,
		mux,
		http.MethodGet,
		"/assistant/skill-subscriptions/"+item.SubscriptionID,
		"account-local",
		"",
		nil,
	)
	if loaded.Code != http.StatusOK {
		t.Fatalf("get status=%d body=%s", loaded.Code, loaded.Body.String())
	}
	var loadedItem skillmodel.SkillSubscription
	if err := json.Unmarshal(loaded.Body.Bytes(), &loadedItem); err != nil {
		t.Fatalf("decode get response: %v", err)
	}
	if loadedItem.SubscriptionID != item.SubscriptionID {
		t.Fatalf("get response=%+v", loadedItem)
	}

	paused := localSkillSubscriptionRequest(
		t,
		mux,
		http.MethodPatch,
		"/assistant/skill-subscriptions/"+item.SubscriptionID+"/status",
		"account-local",
		"pause-subscription-local",
		map[string]any{
			"status":          skillmodel.SkillSubscriptionStatusPaused,
			"clientRequestId": "pause-subscription-local",
		},
	)
	if paused.Code != http.StatusOK {
		t.Fatalf("update status=%d body=%s", paused.Code, paused.Body.String())
	}
	var pausedItem skillmodel.SkillSubscription
	if err := json.Unmarshal(paused.Body.Bytes(), &pausedItem); err != nil {
		t.Fatalf("decode update response: %v", err)
	}
	if pausedItem.Status != skillmodel.SkillSubscriptionStatusPaused ||
		pausedItem.Version != item.Version+1 {
		t.Fatalf("updated subscription=%+v", pausedItem)
	}

	tick := localSkillSubscriptionServiceRequest(
		t,
		mux,
		"tick-subscription-local",
		map[string]any{"now": "2026-08-05T09:00:00Z"},
	)
	if tick.Code != http.StatusOK {
		t.Fatalf("tick status=%d body=%s", tick.Code, tick.Body.String())
	}
	var tickResult skillmodel.SkillSubscriptionCronTickResult
	if err := json.Unmarshal(tick.Body.Bytes(), &tickResult); err != nil {
		t.Fatalf("decode tick response: %v", err)
	}
	if ticker.calls != 1 || ticker.input.Now != "2026-08-05T09:00:00Z" ||
		tickResult.ProcessedCount != 1 || len(tickResult.CreatedTurnIDs) != 1 ||
		len(tickResult.CreatedMessageIDs) != 1 {
		t.Fatalf("tick route/use-case drifted: calls=%d input=%+v result=%+v", ticker.calls, ticker.input, tickResult)
	}
}

func localSkillSubscriptionRequest(
	t *testing.T,
	handler http.Handler,
	method string,
	path string,
	accountID string,
	idempotencyKey string,
	body any,
) *httptest.ResponseRecorder {
	t.Helper()
	var payload []byte
	if body != nil {
		var err error
		payload, err = json.Marshal(body)
		if err != nil {
			t.Fatalf("marshal SkillSubscription request: %v", err)
		}
	}
	request := httptest.NewRequest(method, path, bytes.NewReader(payload))
	if body != nil {
		request.Header.Set("Content-Type", "application/json")
	}
	if idempotencyKey != "" {
		request.Header.Set("Idempotency-Key", idempotencyKey)
	}
	request = request.WithContext(rtauth.WithPrincipal(
		request.Context(),
		rtauth.Principal{Actor: operation.ActorContext{
			AccountID: accountID,
			PersonaID: accountID + ":persona",
		}},
	))
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	return recorder
}

func localSkillSubscriptionServiceRequest(
	t *testing.T,
	handler http.Handler,
	idempotencyKey string,
	body any,
) *httptest.ResponseRecorder {
	t.Helper()
	payload, err := json.Marshal(body)
	if err != nil {
		t.Fatalf("marshal SkillSubscription service request: %v", err)
	}
	request := httptest.NewRequest(
		http.MethodPost,
		"/internal/assistant/skill-subscriptions:tick",
		bytes.NewReader(payload),
	)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Idempotency-Key", idempotencyKey)
	request = request.WithContext(rtauth.WithPrincipal(
		request.Context(),
		rtauth.Principal{Claims: rtauth.Claims{Subject: "assistant-scheduler"}},
	))
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	return recorder
}
