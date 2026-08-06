// spec_ref: specs/feature-tree/assistant-run-learning/assistant-runtime-foundation/assistant-object-runtime/spec.md#gwt-001
// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-001
// readiness_case: get-assistant-entry-api
package api_integration

import (
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
	entryhttp "quwoquan_service/services/assistant-service/internal/assistant/assistant_entry_view/adapters/inbound/http"
	entryapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_entry_view/application"
	entrymodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_entry_view/domain/model"
	entrypersistence "quwoquan_service/services/assistant-service/internal/assistant/assistant_entry_view/infrastructure/persistence"
)

func TestAssistantEntryViewReadsOnlyTheTrustedAccountsProjection(t *testing.T) {
	testinfra.ConfigureLocalContainerRuntime()
	startupCtx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()
	runtime, err := testinfra.StartRealMongo(startupCtx, "assistant_entry_view_api_integration")
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

	collection := runtime.Database.Collection("rm_assistant_entry")
	_, err = collection.InsertMany(startupCtx, []any{
		bson.M{
			"accountId": "entry-owner", "welcomeMessage": "owner welcome",
			"suggestionLines": bson.A{"owner suggestion"}, "chips": bson.A{},
			"actions": bson.A{}, "personalized": true, "checkpoint": int64(11),
		},
		bson.M{
			"accountId": "entry-other", "welcomeMessage": "other secret",
			"suggestionLines": bson.A{"other suggestion"}, "chips": bson.A{},
			"actions": bson.A{}, "personalized": true, "checkpoint": int64(12),
		},
	})
	if err != nil {
		t.Fatalf("seed entry projections: %v", err)
	}

	mux := http.NewServeMux()
	entryhttp.NewHandler(entryapplication.NewQueryFacade(
		entrypersistence.NewMongoReader(runtime.Database), nil,
	)).RegisterRoutes(mux)

	owner := entryRequest(mux, "entry-owner")
	if owner.Code != http.StatusOK {
		t.Fatalf("owner status=%d body=%s", owner.Code, owner.Body.String())
	}
	var view entrymodel.View
	if err := json.Unmarshal(owner.Body.Bytes(), &view); err != nil {
		t.Fatalf("decode entry view: %v", err)
	}
	if view.WelcomeMessage != "owner welcome" || !view.Personalized {
		t.Fatalf("unexpected owner projection: %+v", view)
	}
	if view.AccountID != "" {
		t.Fatalf("wire response leaked internal accountId: %+v", view)
	}
	if body := owner.Body.String(); contains(body, "other secret") || contains(body, "entry-other") {
		t.Fatalf("cross-account projection leaked: %s", body)
	}

	unauthorized := httptest.NewRecorder()
	mux.ServeHTTP(unauthorized, httptest.NewRequest(http.MethodGet, "/assistant/entry", nil))
	if unauthorized.Code != http.StatusUnauthorized {
		t.Fatalf("untrusted request status=%d body=%s", unauthorized.Code, unauthorized.Body.String())
	}
}

func entryRequest(handler http.Handler, accountID string) *httptest.ResponseRecorder {
	request := httptest.NewRequest(http.MethodGet, "/assistant/entry", nil)
	request = request.WithContext(rtauth.WithPrincipal(request.Context(), rtauth.Principal{
		Actor: operation.ActorContext{AccountID: accountID, PersonaID: accountID + ":persona"},
	}))
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	return recorder
}

func contains(value, fragment string) bool {
	for index := 0; index+len(fragment) <= len(value); index++ {
		if value[index:index+len(fragment)] == fragment {
			return true
		}
	}
	return false
}
