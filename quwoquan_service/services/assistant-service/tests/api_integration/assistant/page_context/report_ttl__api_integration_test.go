// spec_ref: specs/feature-tree/runtime/runtime-assistant/context-grounded-answering/spec.md#gwt-001
package api_integration

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	platformredis "quwoquan_service/internal/platform/redis"
	"quwoquan_service/internal/platform/testinfra"
	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	rtredis "quwoquan_service/runtime/redis"
	pagehttp "quwoquan_service/services/assistant-service/internal/assistant/page_context/adapters/inbound/http"
	pageapplication "quwoquan_service/services/assistant-service/internal/assistant/page_context/application"
	pagemodel "quwoquan_service/services/assistant-service/internal/assistant/page_context/domain/model"
	pagepersistence "quwoquan_service/services/assistant-service/internal/assistant/page_context/infrastructure/persistence"
)

func TestPageContextUsesBoundedRedisTTLAndTrustedIdentity(t *testing.T) {
	testinfra.ConfigureLocalContainerRuntime()
	startupCtx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()
	runtime, err := testinfra.StartRealRedis(startupCtx)
	if err != nil {
		t.Fatalf("start real Redis: %v", err)
	}
	if err := runtime.FlushDBs(startupCtx, 0, 1, 2); err != nil {
		t.Fatalf("flush real Redis: %v", err)
	}
	redisRouter, err := platformredis.NewRouter(rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"general":  {Mode: "standalone", Addr: runtime.Addr, Password: runtime.Password, DB: 1, TLS: runtime.TLS},
			"rec":      {Mode: "standalone", Addr: runtime.Addr, Password: runtime.Password, DB: 0, TLS: runtime.TLS},
			"realtime": {Mode: "standalone", Addr: runtime.Addr, Password: runtime.Password, DB: 2, TLS: runtime.TLS},
		},
		PrefixRoutes: rtredis.GeneratedPrefixRoutes(),
		DefaultScene: "general",
	})
	if err != nil {
		t.Fatalf("create Redis router: %v", err)
	}
	t.Cleanup(func() {
		_ = redisRouter.Close()
		closeCtx, closeCancel := context.WithTimeout(context.Background(), 30*time.Second)
		defer closeCancel()
		if closeErr := runtime.Close(closeCtx); closeErr != nil {
			t.Errorf("close real Redis: %v", closeErr)
		}
	})

	clock := time.Now().UTC().Truncate(time.Millisecond)
	facade := pageapplication.NewFacade(
		pagepersistence.NewRedisStore(redisRouter.Scene("general")),
		func() time.Time { return clock },
	)
	mux := http.NewServeMux()
	pagehttp.NewHandler(facade).RegisterRoutes(mux)

	payload := map[string]any{"contextSnapshot": map[string]any{
		"capturedAt": clock.Format(time.RFC3339Nano), "pageType": "article",
		"pageObjects": []map[string]any{{"objectTypeRef": "content.Post", "objectId": "post-page-context"}},
		"userActions": []map[string]any{}, "consentGranted": true,
	}}
	recorder := pageContextRequest(t, mux, "page-owner", payload)
	if recorder.Code != http.StatusOK {
		t.Fatalf("report status=%d body=%s", recorder.Code, recorder.Body.String())
	}
	var receipt pagemodel.Receipt
	if err := json.Unmarshal(recorder.Body.Bytes(), &receipt); err != nil {
		t.Fatalf("decode page receipt: %v", err)
	}
	if !receipt.Accepted || receipt.ContextKey != pagemodel.StorageKey("page-owner") || !receipt.ExpiresAt.Equal(clock.Add(pagemodel.TTL)) {
		t.Fatalf("unexpected page receipt: %+v", receipt)
	}
	ttl, err := runtime.TTL(t.Context(), 1, receipt.ContextKey)
	if err != nil || ttl <= 4*time.Minute+50*time.Second || ttl > pagemodel.TTL {
		t.Fatalf("redis ttl=%s err=%v", ttl, err)
	}
	current, err := facade.Current(t.Context(), "page-owner")
	if err != nil || current == nil || current.PersonaID != "page-owner:persona" || current.Snapshot.PageObjects[0].ObjectID != "post-page-context" {
		t.Fatalf("current context=%+v err=%v", current, err)
	}
	other, err := facade.Current(t.Context(), "page-other")
	if err != nil || other != nil {
		t.Fatalf("cross-account context=%+v err=%v", other, err)
	}

	legacy := pageContextRequest(t, mux, "page-owner", map[string]any{"pageType": "article"})
	if legacy.Code != http.StatusBadRequest {
		t.Fatalf("legacy payload status=%d body=%s", legacy.Code, legacy.Body.String())
	}
	unauthorized := httptest.NewRecorder()
	mux.ServeHTTP(unauthorized, httptest.NewRequest(http.MethodPost, "/assistant/page-context", bytes.NewReader([]byte(`{}`))))
	if unauthorized.Code != http.StatusUnauthorized {
		t.Fatalf("untrusted request status=%d body=%s", unauthorized.Code, unauthorized.Body.String())
	}
}

func pageContextRequest(t *testing.T, handler http.Handler, accountID string, body any) *httptest.ResponseRecorder {
	t.Helper()
	payload, err := json.Marshal(body)
	if err != nil {
		t.Fatalf("marshal page context request: %v", err)
	}
	request := httptest.NewRequest(http.MethodPost, "/assistant/page-context", bytes.NewReader(payload))
	request.Header.Set("Content-Type", "application/json")
	request = request.WithContext(rtauth.WithPrincipal(request.Context(), rtauth.Principal{
		Actor: operation.ActorContext{AccountID: accountID, PersonaID: accountID + ":persona"},
	}))
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	return recorder
}
