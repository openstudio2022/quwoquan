// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/skill-progressive-disclosure-routing/spec.md#gwt-003
// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/skill-progressive-disclosure-routing/spec.md#gwt-004
// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/skill-user-lifecycle/spec.md#gwt-001
package local_contract

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"

	"gopkg.in/yaml.v3"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_catalog/application"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_catalog/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_catalog/infrastructure/resource"
)

type catalogSourceStub struct {
	items []model.Item
	err   error
}

func (source catalogSourceStub) ListCatalogItems(
	context.Context,
) ([]model.Item, error) {
	return append([]model.Item(nil), source.items...), source.err
}

func TestListSkillsContractIsSingleTrackPrivateAccountReader(t *testing.T) {
	t.Parallel()

	root := assistantServiceRoot(t)
	var document struct {
		APIRoutes []struct {
			Operation       string   `yaml:"operation"`
			Actor           string   `yaml:"actor"`
			RequestEntity   string   `yaml:"request_entity"`
			ResponseEntity  string   `yaml:"response_entity"`
			Errors          []string `yaml:"error_codes"`
			RequestBindings struct {
				Path []struct {
					Name  string `yaml:"name"`
					Field string `yaml:"field"`
				} `yaml:"path"`
				Query []struct {
					Name  string `yaml:"name"`
					Field string `yaml:"field"`
				} `yaml:"query"`
				Injected []struct {
					Name  string `yaml:"name"`
					Field string `yaml:"field"`
				} `yaml:"injected"`
			} `yaml:"request_bindings"`
			Commercial struct {
				Status string `yaml:"status"`
			} `yaml:"commercial"`
			Privacy struct {
				Request  string `yaml:"request_classification"`
				Response string `yaml:"response_classification"`
			} `yaml:"privacy"`
			Authorization struct {
				Principal       string `yaml:"principal"`
				OwnershipPolicy string `yaml:"ownership_policy"`
			} `yaml:"authorization"`
			Security struct {
				AuthMode        string `yaml:"auth_mode"`
				Principal       string `yaml:"principal"`
				TokenTransport  string `yaml:"token_transport"`
				AnonymousPolicy string `yaml:"anonymous_policy"`
				Visibility      string `yaml:"visibility"`
			} `yaml:"security"`
		} `yaml:"api_routes"`
	}
	payload := readFile(t, filepath.Join(
		root, "contracts", "assistant", "skill_catalog", "operations.yaml",
	))
	if err := yaml.Unmarshal(payload, &document); err != nil {
		t.Fatalf("parse SkillCatalog operations: %v", err)
	}
	if len(document.APIRoutes) != 2 {
		t.Fatalf("SkillCatalog routes=%d, want 2", len(document.APIRoutes))
	}
	var route, detailRoute = document.APIRoutes[0], document.APIRoutes[0]
	for _, candidate := range document.APIRoutes {
		if candidate.Operation == "ListSkills" {
			route = candidate
		}
		if candidate.Operation == "GetSkillCatalogItem" {
			detailRoute = candidate
		}
	}
	if route.Operation != "ListSkills" || route.Actor != "account" ||
		route.Commercial.Status != "ready" ||
		route.Authorization.Principal != "account" ||
		route.Authorization.OwnershipPolicy != "requester_self" ||
		route.Security.AuthMode != "required" ||
		route.Security.Principal != "owner" ||
		route.Security.TokenTransport != "bearer" ||
		route.Security.AnonymousPolicy != "deny" ||
		route.Security.Visibility != "private" {
		t.Fatalf("ListSkills authorization/commercial drifted: %+v", route)
	}
	if route.Privacy.Request != "SENSITIVE" || route.Privacy.Response != "PUBLIC" {
		t.Fatalf("ListSkills privacy drifted: %+v", route.Privacy)
	}
	for _, code := range []string{
		"ASSISTANT.USER.skill_catalog_unauthorized",
		"ASSISTANT.USER.skill_catalog_invalid_argument",
		"ASSISTANT.SYSTEM.skill_catalog_unavailable",
	} {
		if !contains(route.Errors, code) {
			t.Fatalf("ListSkills missing object-owned error %s: %v", code, route.Errors)
		}
	}
	if detailRoute.Operation != "GetSkillCatalogItem" ||
		detailRoute.RequestEntity != "GetSkillCatalogItemQuery" ||
		detailRoute.ResponseEntity != "AssistantSkillCatalogItemDetailView" ||
		detailRoute.Commercial.Status != "ready" ||
		detailRoute.Authorization.OwnershipPolicy != "requester_self" ||
		detailRoute.Security.AnonymousPolicy != "deny" ||
		!contains(detailRoute.Errors, "ASSISTANT.USER.skill_catalog_not_found") {
		t.Fatalf("GetSkillCatalogItem contract drifted: %+v", detailRoute)
	}
	if len(detailRoute.RequestBindings.Path) != 1 ||
		detailRoute.RequestBindings.Path[0].Name != "skillId" ||
		detailRoute.RequestBindings.Path[0].Field != "skillId" ||
		len(detailRoute.RequestBindings.Query) != 0 ||
		len(detailRoute.RequestBindings.Injected) != 1 ||
		detailRoute.RequestBindings.Injected[0].Name != "accountId" ||
		detailRoute.RequestBindings.Injected[0].Field != "accountId" {
		t.Fatalf(
			"GetSkillCatalogItem request binding drifted: %+v",
			detailRoute.RequestBindings,
		)
	}

	for _, oldFile := range []string{
		filepath.Join(root, "contracts", "assistant", "assistant_run", "operations.yaml"),
		filepath.Join(root, "contracts", "assistant", "assistant_run", "fields.yaml"),
		filepath.Join(root, "contracts", "assistant", "assistant_run", "errors.yaml"),
		filepath.Join(root, "contracts", "assistant", "skill_consent", "errors.yaml"),
	} {
		oldPayload := string(readFile(t, oldFile))
		if strings.Contains(oldPayload, "ListSkills") ||
			strings.Contains(oldPayload, "AssistantSkillCatalogItemView") ||
			strings.Contains(oldPayload, "AssistantSkillCatalogListView") {
			t.Fatalf("legacy SkillCatalog ownership remains in %s", oldFile)
		}
	}
}

func TestGetSkillCatalogItemDomainClassificationIsResponseOwned(t *testing.T) {
	t.Parallel()

	root := assistantServiceRoot(t)
	var fieldsDocument struct {
		Types map[string]struct {
			Fields []struct {
				Name        string   `yaml:"name"`
				Source      string   `yaml:"source"`
				Constraints []string `yaml:"constraints"`
			} `yaml:"fields"`
		} `yaml:"types"`
	}
	fieldsPayload := readFile(t, filepath.Join(
		root, "contracts", "assistant", "skill_catalog", "fields.yaml",
	))
	if err := yaml.Unmarshal(fieldsPayload, &fieldsDocument); err != nil {
		t.Fatalf("parse SkillCatalog fields: %v", err)
	}
	queryFields := fieldsDocument.Types["GetSkillCatalogItemQuery"].Fields
	if len(queryFields) != 2 || queryFields[0].Name != "skillId" ||
		queryFields[1].Name != "accountId" {
		t.Fatalf(
			"GetSkillCatalogItemQuery fields=%+v, want skillId/accountId only",
			queryFields,
		)
	}
	itemFields := fieldsDocument.Types["AssistantSkillCatalogItemView"].Fields
	domainFieldFound := false
	for _, field := range itemFields {
		if field.Name != "domainId" {
			continue
		}
		domainFieldFound = field.Source == "domainId" &&
			contains(field.Constraints, "NOT_NULL")
	}
	if !domainFieldFound {
		t.Fatalf(
			"AssistantSkillCatalogItemView must own required domainId: %+v",
			itemFields,
		)
	}

	var objectDocument struct {
		Identity struct {
			Fields []string `yaml:"fields"`
		} `yaml:"identity"`
		LocalIdentityReasons map[string]string `yaml:"local_identity_reasons"`
	}
	objectPayload := readFile(t, filepath.Join(
		root, "contracts", "assistant", "skill_catalog", "object.yaml",
	))
	if err := yaml.Unmarshal(objectPayload, &objectDocument); err != nil {
		t.Fatalf("parse SkillCatalog object: %v", err)
	}
	if len(objectDocument.Identity.Fields) != 1 ||
		objectDocument.Identity.Fields[0] != "skillId" ||
		strings.TrimSpace(objectDocument.LocalIdentityReasons["domainId"]) == "" {
		t.Fatalf(
			"SkillCatalog identity/domain classification drifted: %+v/%+v",
			objectDocument.Identity.Fields,
			objectDocument.LocalIdentityReasons,
		)
	}
}

func TestSkillCatalogStorageIsCanonicalResourceReaderProjection(t *testing.T) {
	t.Parallel()

	root := assistantServiceRoot(t)
	var storage struct {
		Backend     string         `yaml:"backend"`
		Role        string         `yaml:"role"`
		Tables      map[string]any `yaml:"tables"`
		Collections map[string]any `yaml:"collections"`
		Codegen     map[string]any `yaml:"codegen"`
	}
	payload := readFile(t, filepath.Join(
		root, "contracts", "assistant", "skill_catalog", "storage.yaml",
	))
	if err := yaml.Unmarshal(payload, &storage); err != nil {
		t.Fatalf("parse SkillCatalog storage: %v", err)
	}
	if storage.Backend != "service_resource" || storage.Role != "projection" {
		t.Fatalf(
			"SkillCatalog storage=%s/%s, want service_resource/projection",
			storage.Backend,
			storage.Role,
		)
	}
	if len(storage.Tables) != 0 ||
		len(storage.Collections) != 0 ||
		len(storage.Codegen) != 0 {
		t.Fatalf(
			"SkillCatalog must not invent a store or generated persistence: tables=%v collections=%v codegen=%v",
			storage.Tables,
			storage.Collections,
			storage.Codegen,
		)
	}
}

func TestListSkillsFailsClosedForIdentityAndSourceFailures(t *testing.T) {
	t.Parallel()
	items := []model.Item{{SkillID: "weather", DisplayName: "天气助手"}}

	service := application.NewQueryService(catalogSourceStub{items: items})
	_, err := service.ListSkills(t.Context(), application.ListSkillsQuery{})
	assertCatalogError(t, err, "ASSISTANT.USER.skill_catalog_unauthorized", 401)
	for _, limit := range []int{0, -1, 101} {
		_, err = service.ListSkills(
			t.Context(),
			application.ListSkillsQuery{AccountID: "account-a", Limit: limit},
		)
		assertCatalogError(
			t,
			err,
			"ASSISTANT.USER.skill_catalog_invalid_argument",
			400,
		)
	}

	_, err = application.NewQueryService(nil).ListSkills(
		t.Context(), application.ListSkillsQuery{AccountID: "account-a", Limit: 64},
	)
	assertCatalogError(t, err, "ASSISTANT.SYSTEM.skill_catalog_unavailable", 503)

	_, err = application.NewQueryService(
		catalogSourceStub{items: items, err: errors.New("manifest unavailable")},
	).ListSkills(t.Context(), application.ListSkillsQuery{AccountID: "account-a", Limit: 64})
	assertCatalogError(t, err, "ASSISTANT.SYSTEM.skill_catalog_unavailable", 503)
}

func TestGetSkillCatalogItemProgressivelyDisclosesActivePackageSchema(t *testing.T) {
	t.Parallel()
	items := []model.Item{{
		SkillID:             "travel_companion",
		DomainID:            "travel",
		DisplayName:         "贴身旅行管家",
		ConfigurationSchema: []byte(`{"type":"object","additionalProperties":false}`),
	}}
	service := application.NewQueryService(catalogSourceStub{items: items})

	detail, err := service.GetSkillCatalogItem(
		t.Context(),
		application.GetSkillCatalogItemQuery{
			AccountID: "account-a",
			SkillID:   "travel_companion",
		},
	)
	if err != nil || detail.Item.SkillID != "travel_companion" ||
		detail.Item.DomainID != "travel" ||
		len(detail.ConfigurationSchema) == 0 {
		t.Fatalf("GetSkillCatalogItem detail=%+v err=%v", detail, err)
	}
	_, err = service.GetSkillCatalogItem(
		t.Context(),
		application.GetSkillCatalogItemQuery{AccountID: "account-a", SkillID: "missing"},
	)
	assertCatalogError(t, err, "ASSISTANT.USER.skill_catalog_not_found", 404)
}

func TestListSkillsDoesNotMixAccountConsentIntoCatalog(t *testing.T) {
	t.Parallel()
	items := []model.Item{{
		SkillID:         "travel_companion",
		DisplayName:     "贴身旅行管家",
		Description:     "读取用户明确授权的旅行上下文。",
		RequiresConsent: true,
	}}
	service := application.NewQueryService(catalogSourceStub{items: items})

	owner, err := service.ListSkills(
		t.Context(), application.ListSkillsQuery{AccountID: "account-a", Limit: 64},
	)
	if err != nil {
		t.Fatalf("owner ListSkills: %v", err)
	}
	foreign, err := service.ListSkills(
		t.Context(), application.ListSkillsQuery{AccountID: "account-b", Limit: 64},
	)
	if err != nil {
		t.Fatalf("foreign ListSkills: %v", err)
	}
	if owner.Items[0].SkillID != foreign.Items[0].SkillID ||
		owner.Items[0].Description != foreign.Items[0].Description ||
		owner.Items[0].Description != "读取用户明确授权的旅行上下文。" {
		t.Fatalf("catalog mixed account state: owner=%+v foreign=%+v", owner.Items[0], foreign.Items[0])
	}
}

func TestBuildSourceContainsOnlyDeclaredManifests(t *testing.T) {
	items, err := resource.NewSourceBuilder().ListCatalogItems(t.Context())
	if err != nil {
		t.Fatalf("read canonical SkillCatalog source: %v", err)
	}
	if hasSkill(items, "fallback_general_search") {
		t.Fatal("internal fallback routing Skill escaped the listed product catalog")
	}
	if !hasSkill(items, "travel_companion") {
		t.Fatal("build source misses listed travel_companion")
	}
	for _, item := range items {
		if item.SkillID == "travel_companion" &&
			(item.ConfigurationSchemaDigest == "" ||
				len(item.ConfigurationSchema) == 0 ||
				item.SetupTemplateRef == "" || item.ActivationMode != "hybrid" ||
				item.RequiresConsent || len(item.RequiredConsentScopes) != 0 ||
				!hasSemanticLabel(item.ConsentScopeLabels, "assistant.memory.preferences.read") ||
				!hasSemanticLabel(item.ConsentScopeLabels, "assistant.learning.feedback_context.read") ||
				!hasSemanticLabel(item.ConsentScopeLabels, "travel.trip.read")) {
			t.Fatalf("build source catalog metadata is incomplete: %+v", item)
		}
	}
	for _, invented := range []string{
		"assistant_learning",
		"assistant_navigation",
	} {
		if hasSkill(items, invented) {
			t.Fatalf("build source invented undeclared catalog item %q", invented)
		}
	}
}

func assertCatalogError(t *testing.T, err error, code string, status int) {
	t.Helper()
	var appErr *rterr.AppError
	if !errors.As(err, &appErr) {
		t.Fatalf("error=%T %v, want *runtimeerrors.AppError", err, err)
	}
	if appErr.Code.String() != code || appErr.HTTPStatus != status {
		t.Fatalf("error=%s/%d, want %s/%d", appErr.Code.String(), appErr.HTTPStatus, code, status)
	}
}

func assistantServiceRoot(t *testing.T) string {
	t.Helper()
	_, file, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("resolve test source path")
	}
	return filepath.Clean(filepath.Join(filepath.Dir(file), "..", "..", "..", ".."))
}

func readFile(t *testing.T, path string) []byte {
	t.Helper()
	payload, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read %s: %v", path, err)
	}
	return payload
}

func contains(values []string, wanted string) bool {
	for _, value := range values {
		if value == wanted {
			return true
		}
	}
	return false
}

func hasSkill(items []model.Item, skillID string) bool {
	for _, item := range items {
		if item.SkillID == skillID {
			return true
		}
	}
	return false
}

func hasSemanticLabel(values []model.SemanticLabel, wanted string) bool {
	for _, value := range values {
		if value.ID == wanted {
			return true
		}
	}
	return false
}
