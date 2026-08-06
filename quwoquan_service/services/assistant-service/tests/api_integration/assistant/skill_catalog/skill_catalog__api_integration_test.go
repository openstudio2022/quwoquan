// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/skill-progressive-disclosure-routing/spec.md#gwt-003
// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/skill-user-lifecycle/spec.md#gwt-001
// readiness_case: get-skill-catalog-item-api
// readiness_case: list-skills-api
package api_integration

import (
	"context"
	"crypto/ed25519"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/runtime/operation"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/orchestration"
	cataloghttp "quwoquan_service/services/assistant-service/internal/assistant/skill_catalog/adapters/inbound/http"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_catalog/application"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_catalog/domain/model"
	activerelease "quwoquan_service/services/assistant-service/internal/assistant/skill_catalog/infrastructure/activerelease"
	resourcebuilder "quwoquan_service/services/assistant-service/internal/assistant/skill_catalog/infrastructure/resource"
	packageapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/application"
	packagemodel "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/domain/model"
)

type apiCatalogSource struct{ err error }

func (source apiCatalogSource) ListCatalogItems(context.Context) ([]model.Item, error) {
	if source.err != nil {
		return nil, source.err
	}
	return []model.Item{{
		PackageID:                   "assistant.session.skills",
		ReleaseDigest:               "sha256:" + strings.Repeat("2", 64),
		SkillID:                     "travel_companion",
		DomainID:                    "travel",
		DisplayName:                 "贴身旅行管家",
		Description:                 "读取用户明确授权的旅行上下文。",
		CatalogGroup:                model.SemanticLabel{ID: "travel", DisplayText: "旅行"},
		RequiresConsent:             true,
		RequiredConsentScopes:       []string{"assistant.learning.feedback_context.read"},
		ConsentScopeLabels:          []model.SemanticLabel{{ID: "assistant.learning.feedback_context.read", DisplayText: "读取脱敏反馈摘要"}},
		TargetAudiences:             []model.SemanticLabel{{ID: "trip_organizer", DisplayText: "行程组织者"}},
		DataUseSummary:              "仅在授权后读取",
		Examples:                    []model.ResolvedExample{},
		ActivationMode:              "reactive",
		SurfaceKinds:                []model.SemanticLabel{{ID: "personal", DisplayText: "个人小趣"}},
		ConfigurationSchemaDigest:   "sha256:" + strings.Repeat("1", 64),
		ConfigurationSchema:         json.RawMessage(`{"type":"object","additionalProperties":false,"properties":{}}`),
		SetupTemplateRef:            "assistant.skill.setup.none",
		ConfigurationRequiredFields: []string{},
	}}, nil
}

type activeReleaseResolver struct {
	resolved packageapplication.ResolvedRelease
}

func (resolver activeReleaseResolver) ResolveActive(
	ctx context.Context,
	packageID string,
) (packageapplication.ResolvedRelease, error) {
	if err := ctx.Err(); err != nil {
		return packageapplication.ResolvedRelease{}, err
	}
	if packageID != resolver.resolved.Release.PackageID {
		return packageapplication.ResolvedRelease{}, errors.New("active package not found")
	}
	return resolver.resolved, nil
}

func (resolver activeReleaseResolver) ResolveRelease(
	ctx context.Context,
	packageID string,
	releaseDigest string,
) (packageapplication.ResolvedRelease, error) {
	if err := ctx.Err(); err != nil {
		return packageapplication.ResolvedRelease{}, err
	}
	if packageID != resolver.resolved.Release.PackageID ||
		releaseDigest != resolver.resolved.Release.ReleaseDigest {
		return packageapplication.ResolvedRelease{}, errors.New("immutable release not found")
	}
	return resolver.resolved, nil
}

func productionCatalogSource(t *testing.T) *activerelease.CatalogSource {
	t.Helper()
	bundle, err := resourcebuilder.NewSourceBuilder().Compile(t.Context())
	if err != nil {
		t.Fatalf("compile canonical Skill package source: %v", err)
	}
	built, err := resourcebuilder.BuildPackage(bundle, resourcebuilder.PackageBuildOptions{
		PackageID:        activerelease.OfficialPackageID,
		PackageVersion:   "1.0.0",
		BuildID:          "skill-catalog-api-integration",
		SourceRepository: "quwoquan",
		SourceRevision:   "assistant-skill-catalog-readiness",
		BuiltAt:          time.Date(2026, 8, 5, 8, 0, 0, 0, time.UTC),
		RuntimeCompatibility: packagemodel.RuntimeCompatibility{
			APIVersion:            packagemodel.RuntimeAPIVersion,
			MinimumRuntimeVersion: packagemodel.RuntimeVersion,
			MaximumRuntimeVersion: packagemodel.RuntimeVersion,
		},
		CapabilityGrants: []packagemodel.CapabilityGrant{{
			CapabilityID: "assistant.skill",
			Scope:        "official",
		}},
		SigningKeyID:      "api-integration-key",
		SigningPrivateKey: ed25519.NewKeyFromSeed(make([]byte, ed25519.SeedSize)),
	})
	if err != nil {
		t.Fatalf("build immutable Skill package: %v", err)
	}
	files := make(map[string][]byte, len(built.Files))
	for _, file := range built.Files {
		files[file.RelativePath] = append([]byte(nil), file.Content...)
	}
	assets := make(map[string][]byte, len(built.Release.Assets))
	for _, asset := range built.Release.Assets {
		relative := strings.TrimPrefix(asset.Locator, "skill-package://official/")
		content, found := files[relative]
		if !found {
			t.Fatalf("built immutable asset %q is missing", asset.AssetID)
		}
		assets[asset.AssetID] = content
	}
	return activerelease.NewCatalogSource(
		activeReleaseResolver{resolved: packageapplication.ResolvedRelease{
			Release: built.Release,
			Assets:  assets,
		}},
		activerelease.OfficialPackageID,
		orchestration.ValidateAssistantDomainSkillCatalog,
	)
}

func TestListSkillsHTTPUsesVerifiedAccountAndFailsClosed(t *testing.T) {
	handler := cataloghttp.NewHandler(
		application.NewQueryService(productionCatalogSource(t)),
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
	var travel model.Item
	for _, item := range view.Items {
		if item.SkillID == "travel_companion" {
			travel = item
			break
		}
	}
	if travel.SkillID == "" ||
		travel.PackageID != activerelease.OfficialPackageID ||
		travel.ReleaseDigest == "" ||
		len(travel.RequiredConsentScopes) != 0 ||
		travel.ConfigurationSchemaDigest == "" ||
		travel.ActivationMode != "hybrid" {
		t.Fatalf("active package catalog metadata missing: %+v", view.Items)
	}
	var listWire map[string]any
	if err := json.Unmarshal(owner.Body.Bytes(), &listWire); err != nil {
		t.Fatalf("decode list wire: %v", err)
	}
	for _, raw := range listWire["items"].([]any) {
		listed := raw.(map[string]any)
		if _, leaked := listed["configurationSchema"]; leaked {
			t.Fatal("ListSkills leaked progressively disclosed configuration schema")
		}
	}

	detail := requestCatalogAt(
		handler,
		"/assistant/skills/travel_companion",
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
	if detailView.Item.SkillID != "travel_companion" ||
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
