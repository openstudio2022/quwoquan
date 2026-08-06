// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/skill-user-lifecycle/spec.md#gwt-001
// readiness_case: list-skill-user-settings-api
// readiness_case: get-skill-user-setting-api
// readiness_case: put-skill-user-setting-api
package api_integration

import (
	"bytes"
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
	"quwoquan_service/runtime/operation"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/orchestration"
	activerelease "quwoquan_service/services/assistant-service/internal/assistant/skill_catalog/infrastructure/activerelease"
	resourcebuilder "quwoquan_service/services/assistant-service/internal/assistant/skill_catalog/infrastructure/resource"
	packageapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/application"
	packagemodel "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/domain/model"
	settinghttp "quwoquan_service/services/assistant-service/internal/assistant/skill_user_setting/adapters/inbound/http"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_user_setting/application"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_user_setting/domain/model"
)

type allowConfiguration struct{}

func (allowConfiguration) ValidateConfiguration(context.Context, string, string, json.RawMessage) error {
	return nil
}

type settingActiveReleaseResolver struct {
	resolved packageapplication.ResolvedRelease
}

func (resolver settingActiveReleaseResolver) ResolveActive(
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

func (resolver settingActiveReleaseResolver) ResolveRelease(
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

func productionSettingCatalogSource(t *testing.T) *activerelease.CatalogSource {
	t.Helper()
	bundle, err := resourcebuilder.NewSourceBuilder().Compile(t.Context())
	if err != nil {
		t.Fatalf("compile canonical Skill package source: %v", err)
	}
	built, err := resourcebuilder.BuildPackage(bundle, resourcebuilder.PackageBuildOptions{
		PackageID:        activerelease.OfficialPackageID,
		PackageVersion:   "1.0.0",
		BuildID:          "skill-user-setting-api-integration",
		SourceRepository: "quwoquan",
		SourceRevision:   "assistant-skill-user-setting-readiness",
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
		SigningKeyID:      "skill-user-setting-api-integration-key",
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
		settingActiveReleaseResolver{resolved: packageapplication.ResolvedRelease{
			Release: built.Release,
			Assets:  assets,
		}},
		activerelease.OfficialPackageID,
		orchestration.ValidateAssistantDomainSkillCatalog,
	)
}

func TestSkillUserSettingPostgresCommitsCASReceiptAndOutboxAtomically(t *testing.T) {
	resetSettingState(t)
	now := time.Date(2026, 8, 2, 11, 0, 0, 0, time.UTC)
	commands := application.NewCommandFacade(
		settingStore,
		allowConfiguration{},
		func() time.Time { return now },
	)
	input := model.PutInput{
		AccountID:                 "account-a",
		SkillID:                   "travel_companion",
		Status:                    model.StatusEnabled,
		ConfigurationData:         json.RawMessage(`{}`),
		ConfigurationSchemaDigest: "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
		MemoryPolicy:              model.MemoryConfirmBeforeSave,
		ConnectorConnectionRefs:   []string{"calendar-a"},
		ExpectedRevision:          0,
		IdempotencyKey:            "setting-command-create",
	}
	created, err := commands.Put(context.Background(), input)
	if err != nil || !created.Changed || created.Setting.Revision != 1 {
		t.Fatalf("create result=%+v error=%v", created, err)
	}
	replayed, err := commands.Put(context.Background(), input)
	if err != nil || !replayed.Replayed || replayed.Setting.ID != created.Setting.ID {
		t.Fatalf("replay result=%+v error=%v", replayed, err)
	}
	input.Status = model.StatusDisabled
	if _, err := commands.Put(context.Background(), input); !errors.Is(err, model.ErrIdempotencyConflict) {
		t.Fatalf("idempotency conflict error=%v", err)
	}
	input.IdempotencyKey = "setting-command-update"
	input.ExpectedRevision = 1
	updated, err := commands.Put(context.Background(), input)
	if err != nil || updated.Setting.Revision != 2 || updated.Setting.Status != model.StatusDisabled {
		t.Fatalf("update result=%+v error=%v", updated, err)
	}
	queries := application.NewQueryFacade(settingStore)
	enabled, err := queries.IsEnabled(context.Background(), "account-a", "travel_companion")
	if err != nil || enabled {
		t.Fatalf("effective enabled=%v error=%v", enabled, err)
	}
	listed, err := queries.List(context.Background(), "account-a", 64)
	if err != nil || len(listed) != 1 || listed[0].Revision != 2 {
		t.Fatalf("list explicit settings=%+v error=%v", listed, err)
	}
	empty, err := queries.List(context.Background(), "account-b", 64)
	if err != nil || len(empty) != 0 {
		t.Fatalf("list default-only account=%+v error=%v", empty, err)
	}
	var settings, receipts, outbox int
	if err := settingPool.QueryRow(context.Background(), `
SELECT
  (SELECT COUNT(*) FROM skill_user_settings),
  (SELECT COUNT(*) FROM skill_user_setting_command_receipts),
  (SELECT COUNT(*) FROM skill_user_setting_outbox)`).Scan(&settings, &receipts, &outbox); err != nil {
		t.Fatal(err)
	}
	if settings != 1 || receipts != 2 || outbox != 2 {
		t.Fatalf("setting/receipt/outbox=%d/%d/%d, want 1/2/2", settings, receipts, outbox)
	}
}

func TestSkillUserSettingHTTPUsesPostgresAndImmutablePackage(t *testing.T) {
	resetSettingState(t)
	catalog := productionSettingCatalogSource(t)
	items, err := catalog.ListCatalogItems(t.Context())
	if err != nil {
		t.Fatalf("read active immutable Skill catalog: %v", err)
	}
	var schemaDigest string
	for _, item := range items {
		if item.SkillID == "travel_companion" {
			schemaDigest = item.ConfigurationSchemaDigest
			break
		}
	}
	if schemaDigest == "" {
		t.Fatal("active immutable Skill package does not contain travel_companion schema")
	}

	mux := http.NewServeMux()
	settinghttp.NewHandler(
		application.NewCommandFacade(settingStore, catalog, func() time.Time {
			return time.Date(2026, 8, 5, 9, 0, 0, 0, time.UTC)
		}),
		application.NewQueryFacade(settingStore),
	).RegisterRoutes(mux)

	anonymous := skillSettingRequest(
		t, mux, http.MethodGet, "/assistant/skill-settings", "", "", nil,
	)
	if anonymous.Code != http.StatusUnauthorized {
		t.Fatalf("anonymous list status=%d body=%s", anonymous.Code, anonymous.Body.String())
	}

	put := skillSettingRequest(
		t,
		mux,
		http.MethodPut,
		"/assistant/skills/travel_companion/setting",
		"setting-http-account",
		"setting-http-put",
		map[string]any{
			"status":                    model.StatusEnabled,
			"configurationData":         map[string]any{},
			"configurationSchemaDigest": schemaDigest,
			"memoryPolicy":              model.MemoryConfirmBeforeSave,
			"connectorConnectionRefs":   []string{},
			"expectedRevision":          0,
		},
	)
	if put.Code != http.StatusOK {
		t.Fatalf("put status=%d body=%s", put.Code, put.Body.String())
	}
	var receipt struct {
		Setting  model.Setting `json:"setting"`
		Changed  bool          `json:"changed"`
		Replayed bool          `json:"replayed"`
	}
	if err := json.Unmarshal(put.Body.Bytes(), &receipt); err != nil {
		t.Fatalf("decode PUT receipt: %v", err)
	}
	if !receipt.Changed || receipt.Replayed ||
		receipt.Setting.AccountID != "setting-http-account" ||
		receipt.Setting.SkillID != "travel_companion" ||
		receipt.Setting.ConfigurationSchemaDigest != schemaDigest ||
		receipt.Setting.Revision != 1 {
		t.Fatalf("unexpected PUT receipt: %+v", receipt)
	}

	get := skillSettingRequest(
		t,
		mux,
		http.MethodGet,
		"/assistant/skills/travel_companion/setting",
		"setting-http-account",
		"",
		nil,
	)
	if get.Code != http.StatusOK {
		t.Fatalf("get status=%d body=%s", get.Code, get.Body.String())
	}
	var stored model.Setting
	if err := json.Unmarshal(get.Body.Bytes(), &stored); err != nil {
		t.Fatalf("decode GET setting: %v", err)
	}
	if stored.ID != receipt.Setting.ID || stored.ConfigurationSchemaDigest != schemaDigest {
		t.Fatalf("GET setting drifted: %+v", stored)
	}

	list := skillSettingRequest(
		t, mux, http.MethodGet, "/assistant/skill-settings?limit=64",
		"setting-http-account", "", nil,
	)
	if list.Code != http.StatusOK {
		t.Fatalf("list status=%d body=%s", list.Code, list.Body.String())
	}
	var listed struct {
		Items []model.Setting `json:"items"`
	}
	if err := json.Unmarshal(list.Body.Bytes(), &listed); err != nil {
		t.Fatalf("decode setting list: %v", err)
	}
	if len(listed.Items) != 1 || listed.Items[0].ID != receipt.Setting.ID {
		t.Fatalf("unexpected setting list: %+v", listed.Items)
	}

	foreign := skillSettingRequest(
		t,
		mux,
		http.MethodGet,
		"/assistant/skills/travel_companion/setting",
		"setting-http-other",
		"",
		nil,
	)
	if foreign.Code != http.StatusNotFound {
		t.Fatalf("foreign get status=%d body=%s", foreign.Code, foreign.Body.String())
	}

	var settings, receipts, outbox int
	if err := settingPool.QueryRow(t.Context(), `
SELECT
  (SELECT COUNT(*) FROM skill_user_settings),
  (SELECT COUNT(*) FROM skill_user_setting_command_receipts),
  (SELECT COUNT(*) FROM skill_user_setting_outbox)`).Scan(&settings, &receipts, &outbox); err != nil {
		t.Fatal(err)
	}
	if settings != 1 || receipts != 1 || outbox != 1 {
		t.Fatalf("HTTP setting/receipt/outbox=%d/%d/%d, want 1/1/1", settings, receipts, outbox)
	}
}

func skillSettingRequest(
	t *testing.T,
	handler http.Handler,
	method string,
	path string,
	accountID string,
	idempotencyKey string,
	body any,
) *httptest.ResponseRecorder {
	t.Helper()
	payload := []byte(nil)
	if body != nil {
		var err error
		payload, err = json.Marshal(body)
		if err != nil {
			t.Fatalf("marshal SkillUserSetting request: %v", err)
		}
	}
	request := httptest.NewRequest(method, path, bytes.NewReader(payload))
	if body != nil {
		request.Header.Set("Content-Type", "application/json")
	}
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
