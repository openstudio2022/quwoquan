// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/session-preference-memory-control/spec.md#gwt-001
// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/session-preference-memory-control/spec.md#gwt-002
package api_integration

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/internal/platform/testinfra"
	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	preferencehttp "quwoquan_service/services/assistant-service/internal/assistant/assistant_preference/adapters/inbound/http"
	preferenceapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_preference/application"
	preferencemodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_preference/domain/model"
	preferencepersistence "quwoquan_service/services/assistant-service/internal/assistant/assistant_preference/infrastructure/persistence"
)

func TestAssistantPreferencePersistsOwnerScopedLifecycle(t *testing.T) {
	testinfra.ConfigureLocalContainerRuntime()
	startupCtx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()
	runtime, err := testinfra.StartRealMongo(startupCtx, "assistant_preference_api_integration")
	if err != nil {
		t.Fatalf("start real MongoDB: %v", err)
	}
	t.Cleanup(func() {
		closeCtx, closeCancel := context.WithTimeout(context.Background(), 30*time.Second)
		defer closeCancel()
		if closeErr := runtime.Close(closeCtx); closeErr != nil {
			t.Errorf("close real MongoDB: %v", closeErr)
		}
	})

	store := preferencepersistence.NewMongoStore(runtime.Database)
	if err := store.EnsureIndexes(startupCtx); err != nil {
		t.Fatalf("ensure AssistantPreference indexes: %v", err)
	}
	mux := http.NewServeMux()
	preferencehttp.NewHandler(
		preferenceapplication.NewCommandFacade(store, nil),
		preferenceapplication.NewQueryFacade(store),
	).RegisterRoutes(mux)

	created := preferenceRequest(t, mux, http.MethodPost, "/assistant/preferences", "preference-owner", map[string]any{
		"scope": "long_term", "kind": "tone", "value": "warm", "sourceType": "management",
	})
	if created.Code != http.StatusOK {
		t.Fatalf("create status=%d body=%s", created.Code, created.Body.String())
	}
	var preference preferencemodel.AssistantPreference
	if err := json.Unmarshal(created.Body.Bytes(), &preference); err != nil {
		t.Fatalf("decode preference: %v", err)
	}
	if preference.PreferenceID == "" || preference.UserID != "preference-owner" || preference.Status != preferencemodel.StatusActive || preference.Version != 1 {
		t.Fatalf("unexpected preference: %+v", preference)
	}
	count, err := runtime.Database.Collection("assistant_preferences").CountDocuments(startupCtx, bson.M{"userId": "preference-owner"})
	if err != nil || count != 1 {
		t.Fatalf("preference count=%d err=%v", count, err)
	}

	foreign := preferenceRequest(t, mux, http.MethodPost, "/assistant/preferences/"+preference.PreferenceID+"/revoke", "preference-other", nil)
	if foreign.Code != http.StatusNotFound {
		t.Fatalf("foreign revoke status=%d body=%s", foreign.Code, foreign.Body.String())
	}
	revoked := preferenceRequest(t, mux, http.MethodPost, "/assistant/preferences/"+preference.PreferenceID+"/revoke", "preference-owner", nil)
	if revoked.Code != http.StatusOK {
		t.Fatalf("revoke status=%d body=%s", revoked.Code, revoked.Body.String())
	}
	var revokedPreference preferencemodel.AssistantPreference
	if err := json.Unmarshal(revoked.Body.Bytes(), &revokedPreference); err != nil {
		t.Fatalf("decode revoked preference: %v", err)
	}
	if revokedPreference.Status != preferencemodel.StatusRevoked || revokedPreference.Version != 2 || revokedPreference.RevocationDeadline == nil {
		t.Fatalf("unexpected revoked preference: %+v", revokedPreference)
	}
	restored := preferenceRequest(t, mux, http.MethodPost, "/assistant/preferences/"+preference.PreferenceID+"/restore", "preference-owner", nil)
	if restored.Code != http.StatusOK {
		t.Fatalf("restore status=%d body=%s", restored.Code, restored.Body.String())
	}
	var restoredPreference preferencemodel.AssistantPreference
	if err := json.Unmarshal(restored.Body.Bytes(), &restoredPreference); err != nil {
		t.Fatalf("decode restored preference: %v", err)
	}
	if restoredPreference.Status != preferencemodel.StatusActive || restoredPreference.Version != 3 || restoredPreference.RevokedAt != nil || restoredPreference.RevocationDeadline != nil {
		t.Fatalf("unexpected restored preference: %+v", restoredPreference)
	}

	listed := preferenceRequest(t, mux, http.MethodGet, "/assistant/preferences?scope=long_term", "preference-owner", nil)
	if listed.Code != http.StatusOK {
		t.Fatalf("list status=%d body=%s", listed.Code, listed.Body.String())
	}
	var view preferenceapplication.AssistantPreferenceListView
	if err := json.Unmarshal(listed.Body.Bytes(), &view); err != nil {
		t.Fatalf("decode preference list: %v", err)
	}
	if len(view.Items) != 1 || view.Items[0].PreferenceID != preference.PreferenceID || view.Items[0].Version != 3 {
		t.Fatalf("unexpected preference list: %+v", view.Items)
	}
}

func preferenceRequest(t *testing.T, handler http.Handler, method, path, accountID string, body any) *httptest.ResponseRecorder {
	t.Helper()
	var payload []byte
	if body != nil {
		var err error
		payload, err = json.Marshal(body)
		if err != nil {
			t.Fatalf("marshal preference request: %v", err)
		}
	}
	request := httptest.NewRequest(method, path, bytes.NewReader(payload))
	if body != nil {
		request.Header.Set("Content-Type", "application/json")
	}
	request = request.WithContext(rtauth.WithPrincipal(request.Context(), rtauth.Principal{
		Actor: operation.ActorContext{AccountID: accountID, PersonaID: accountID + ":persona"},
	}))
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	return recorder
}
