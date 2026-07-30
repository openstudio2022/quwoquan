// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/skill-progressive-disclosure-routing/spec.md#gwt-003
package api_integration

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/runtime/operation"
	cataloghttp "quwoquan_service/services/assistant-service/internal/assistant/skill_catalog/adapters/inbound/http"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_catalog/application"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_catalog/domain/model"
)

type apiCatalogSource struct{}

func (apiCatalogSource) ListCatalogItems(context.Context) ([]model.Item, error) {
	return []model.Item{{
		SkillID:         model.PersonalContentAccessSkillID,
		DisplayName:     "个人内容访问",
		Description:     "允许读取个人内容。",
		RequiresConsent: true,
	}}, nil
}

type apiConsentReader struct {
	err error
}

func (reader apiConsentReader) ListGrantedScopes(
	_ context.Context,
	accountID string,
) (map[string]string, error) {
	if reader.err != nil {
		return nil, reader.err
	}
	if accountID == "account-a" {
		return map[string]string{
			model.PersonalContentAccessSkillID: "read_own_content",
		}, nil
	}
	return map[string]string{}, nil
}

func TestListSkillsHTTPUsesVerifiedAccountAndFailsClosed(t *testing.T) {
	handler := cataloghttp.NewHandler(application.NewQueryService(
		apiCatalogSource{},
		apiConsentReader{},
	)).Routes()

	anonymous := requestCatalog(handler, "", false)
	assertHTTPError(
		t, anonymous, http.StatusUnauthorized,
		"ASSISTANT.USER.skill_catalog_unauthorized",
	)
	forged := requestCatalog(handler, "account-a", false)
	assertHTTPError(
		t, forged, http.StatusUnauthorized,
		"ASSISTANT.USER.skill_catalog_unauthorized",
	)

	owner := requestCatalog(handler, "account-a", true)
	if owner.Code != http.StatusOK {
		t.Fatalf("owner status=%d body=%s", owner.Code, owner.Body.String())
	}
	var view model.ListView
	if err := json.Unmarshal(owner.Body.Bytes(), &view); err != nil {
		t.Fatalf("decode catalog view: %v", err)
	}
	if len(view.Items) != 1 ||
		!strings.Contains(view.Items[0].Description, "read_own_content") {
		t.Fatalf("owner scope missing: %+v", view.Items)
	}
	for _, path := range []string{
		"/assistant/skills?limit=",
		"/assistant/skills?limit=0",
		"/assistant/skills?limit=-1",
		"/assistant/skills?limit=invalid",
		"/assistant/skills?limit=101",
		"/assistant/skills?limit=1&limit=2",
	} {
		invalid := requestCatalogAt(handler, path, "account-a", true)
		assertHTTPError(
			t, invalid, http.StatusBadRequest,
			"ASSISTANT.USER.skill_catalog_invalid_argument",
		)
	}

	unavailable := cataloghttp.NewHandler(application.NewQueryService(
		apiCatalogSource{},
		apiConsentReader{err: errors.New("consent unavailable")},
	)).Routes()
	failed := requestCatalog(unavailable, "account-a", true)
	assertHTTPError(
		t, failed, http.StatusServiceUnavailable,
		"ASSISTANT.SYSTEM.skill_catalog_consent_unavailable",
	)
}

func requestCatalog(
	handler http.Handler,
	accountID string,
	verified bool,
) *httptest.ResponseRecorder {
	return requestCatalogAt(
		handler,
		"/assistant/skills",
		accountID,
		verified,
	)
}

func requestCatalogAt(
	handler http.Handler,
	path string,
	accountID string,
	verified bool,
) *httptest.ResponseRecorder {
	request := httptest.NewRequest(http.MethodGet, path, nil)
	if accountID != "" {
		request.Header.Set("X-Client-User-Id", accountID)
	}
	if verified {
		request = request.WithContext(rtauth.WithPrincipal(
			request.Context(),
			rtauth.Principal{Actor: operation.ActorContext{AccountID: accountID}},
		))
	}
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	return recorder
}

func assertHTTPError(
	t *testing.T,
	recorder *httptest.ResponseRecorder,
	status int,
	code string,
) {
	t.Helper()
	if recorder.Code != status {
		t.Fatalf("status=%d body=%s, want %d", recorder.Code, recorder.Body.String(), status)
	}
	var response rterr.ErrorResponse
	if err := json.Unmarshal(recorder.Body.Bytes(), &response); err != nil {
		t.Fatalf("decode error response: %v", err)
	}
	if response.Code != code {
		t.Fatalf("error code=%q, want %q", response.Code, code)
	}
}
