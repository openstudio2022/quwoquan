// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/skill-progressive-disclosure-routing/spec.md#gwt-003
// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/skill-user-lifecycle/spec.md#gwt-001
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

type apiCatalogSource struct{ err error }

func (source apiCatalogSource) ListCatalogItems(context.Context) ([]model.Item, error) {
	if source.err != nil {
		return nil, source.err
	}
	return []model.Item{{
		PackageID:                   "assistant.session.skills",
		ReleaseDigest:               "sha256:" + strings.Repeat("2", 64),
		SkillID:                     model.PersonalContentAccessSkillID,
		DisplayName:                 "个人内容访问",
		Description:                 "允许读取个人内容。",
		RequiresConsent:             true,
		RequiredConsentScopes:       []string{"assistant.personal_content.read"},
		TargetUsers:                 []string{"all_users"},
		DataUseSummary:              "仅在授权后读取",
		ExampleRefs:                 []string{},
		ActivationMode:              "reactive",
		AllowedSurfaceKinds:         []string{"personal"},
		ConfigurationSchemaDigest:   "sha256:" + strings.Repeat("1", 64),
		ConfigurationSchema:         json.RawMessage(`{"type":"object","additionalProperties":false,"properties":{}}`),
		SetupTemplateRef:            "assistant.skill.setup.none",
		ConfigurationRequiredFields: []string{},
	}}, nil
}

func TestListSkillsHTTPUsesVerifiedAccountAndFailsClosed(t *testing.T) {
	handler := cataloghttp.NewHandler(
		application.NewQueryService(apiCatalogSource{}),
	).Routes()

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
		view.Items[0].PackageID != "assistant.session.skills" ||
		view.Items[0].ReleaseDigest == "" ||
		len(view.Items[0].RequiredConsentScopes) != 1 ||
		view.Items[0].ConfigurationSchemaDigest == "" ||
		view.Items[0].ActivationMode != "reactive" {
		t.Fatalf("active package catalog metadata missing: %+v", view.Items)
	}
	var listWire map[string]any
	if err := json.Unmarshal(owner.Body.Bytes(), &listWire); err != nil {
		t.Fatalf("decode list wire: %v", err)
	}
	listed := listWire["items"].([]any)[0].(map[string]any)
	if _, leaked := listed["configurationSchema"]; leaked {
		t.Fatal("ListSkills leaked progressively disclosed configuration schema")
	}

	detail := requestCatalogAt(
		handler,
		"/assistant/skills/"+model.PersonalContentAccessSkillID,
		"account-a",
		true,
	)
	if detail.Code != http.StatusOK {
		t.Fatalf("detail status=%d body=%s", detail.Code, detail.Body.String())
	}
	var detailView model.DetailView
	if err := json.Unmarshal(detail.Body.Bytes(), &detailView); err != nil {
		t.Fatalf("decode detail view: %v", err)
	}
	if detailView.Item.SkillID != model.PersonalContentAccessSkillID ||
		len(detailView.ConfigurationSchema) == 0 {
		t.Fatalf("active package catalog detail missing: %+v", detailView)
	}
	missing := requestCatalogAt(
		handler,
		"/assistant/skills/missing",
		"account-a",
		true,
	)
	assertHTTPError(
		t,
		missing,
		http.StatusNotFound,
		"ASSISTANT.USER.skill_catalog_not_found",
	)
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
		apiCatalogSource{err: errors.New("catalog unavailable")},
	)).Routes()
	failed := requestCatalog(unavailable, "account-a", true)
	assertHTTPError(
		t, failed, http.StatusServiceUnavailable,
		"ASSISTANT.SYSTEM.skill_catalog_unavailable",
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
