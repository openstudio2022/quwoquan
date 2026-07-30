// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/skill-progressive-disclosure-routing/spec.md#gwt-003
// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/skill-progressive-disclosure-routing/spec.md#gwt-004
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

type consentReaderStub struct {
	read func(string) (map[string]string, error)
}

func (reader consentReaderStub) ListGrantedScopes(
	_ context.Context,
	accountID string,
) (map[string]string, error) {
	return reader.read(accountID)
}

func TestListSkillsContractIsSingleTrackPrivateAccountReader(t *testing.T) {
	t.Parallel()

	root := assistantServiceRoot(t)
	var document struct {
		APIRoutes []struct {
			Operation  string   `yaml:"operation"`
			Actor      string   `yaml:"actor"`
			Errors     []string `yaml:"error_codes"`
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
	if len(document.APIRoutes) != 1 {
		t.Fatalf("SkillCatalog routes=%d, want 1", len(document.APIRoutes))
	}
	route := document.APIRoutes[0]
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
	if route.Privacy.Request != "SENSITIVE" || route.Privacy.Response != "SENSITIVE" {
		t.Fatalf("ListSkills privacy drifted: %+v", route.Privacy)
	}
	for _, code := range []string{
		"ASSISTANT.USER.skill_catalog_unauthorized",
		"ASSISTANT.USER.skill_catalog_invalid_argument",
		"ASSISTANT.SYSTEM.skill_catalog_consent_unavailable",
		"ASSISTANT.SYSTEM.skill_catalog_unavailable",
	} {
		if !contains(route.Errors, code) {
			t.Fatalf("ListSkills missing object-owned error %s: %v", code, route.Errors)
		}
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

func TestListSkillsFailsClosedForIdentitySourceAndConsentFailures(t *testing.T) {
	t.Parallel()
	items := []model.Item{{SkillID: "weather", DisplayName: "天气助手"}}
	workingConsent := consentReaderStub{read: func(string) (map[string]string, error) {
		return map[string]string{}, nil
	}}

	service := application.NewQueryService(catalogSourceStub{items: items}, workingConsent)
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

	_, err = application.NewQueryService(nil, workingConsent).ListSkills(
		t.Context(), application.ListSkillsQuery{AccountID: "account-a", Limit: 64},
	)
	assertCatalogError(t, err, "ASSISTANT.SYSTEM.skill_catalog_unavailable", 503)

	_, err = application.NewQueryService(
		catalogSourceStub{items: items, err: errors.New("manifest unavailable")},
		workingConsent,
	).ListSkills(t.Context(), application.ListSkillsQuery{AccountID: "account-a", Limit: 64})
	assertCatalogError(t, err, "ASSISTANT.SYSTEM.skill_catalog_unavailable", 503)

	_, err = application.NewQueryService(catalogSourceStub{items: items}, nil).ListSkills(
		t.Context(), application.ListSkillsQuery{AccountID: "account-a", Limit: 64},
	)
	assertCatalogError(t, err, "ASSISTANT.SYSTEM.skill_catalog_consent_unavailable", 503)

	_, err = application.NewQueryService(
		catalogSourceStub{items: items},
		consentReaderStub{read: func(string) (map[string]string, error) {
			return nil, errors.New("consent unavailable")
		}},
	).ListSkills(t.Context(), application.ListSkillsQuery{AccountID: "account-a", Limit: 64})
	assertCatalogError(t, err, "ASSISTANT.SYSTEM.skill_catalog_consent_unavailable", 503)
}

func TestListSkillsUsesOnlyRequestingAccountConsent(t *testing.T) {
	t.Parallel()
	items := []model.Item{{
		SkillID:         model.PersonalContentAccessSkillID,
		DisplayName:     "个人内容访问",
		Description:     "允许读取个人内容。",
		RequiresConsent: true,
	}}
	service := application.NewQueryService(
		catalogSourceStub{items: items},
		consentReaderStub{read: func(accountID string) (map[string]string, error) {
			if accountID == "account-a" {
				return map[string]string{
					model.PersonalContentAccessSkillID: "read_own_content",
				}, nil
			}
			return map[string]string{}, nil
		}},
	)

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
	if !strings.Contains(owner.Items[0].Description, "read_own_content") {
		t.Fatalf("owner scope missing: %+v", owner.Items[0])
	}
	if strings.Contains(foreign.Items[0].Description, "read_own_content") {
		t.Fatalf("foreign account observed owner scope: %+v", foreign.Items[0])
	}
}

func TestCanonicalCatalogSourceOwnsManifestAndBuiltInEntries(t *testing.T) {
	items, err := resource.NewCatalogSource().ListCatalogItems(t.Context())
	if err != nil {
		t.Fatalf("read canonical SkillCatalog source: %v", err)
	}
	for _, skillID := range []string{
		"fallback_general_search",
		model.PersonalContentAccessSkillID,
		"assistant_learning",
		"assistant_navigation",
	} {
		if !hasSkill(items, skillID) {
			t.Fatalf("canonical SkillCatalog missing %q", skillID)
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
