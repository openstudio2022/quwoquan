// spec_ref: specs/feature-tree/assistant-run-learning/assistant-runtime-foundation/assistant-object-runtime/spec.md#gwt-002
// spec_ref: specs/feature-tree/assistant-run-learning/assistant-runtime-foundation/assistant-object-runtime/spec.md#gwt-002.t1
// spec_ref: specs/feature-tree/assistant-run-learning/assistant-runtime-foundation/assistant-object-runtime/spec.md#gwt-002.t2
// spec_ref: specs/feature-tree/assistant-run-learning/assistant-runtime-foundation/assistant-object-runtime/spec.md#gwt-002.t3
// readiness_case: list-assistant-tasks-api
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

	"quwoquan_service/internal/platform/testinfra"
	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	runorchestration "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/orchestration"
	taskhttp "quwoquan_service/services/assistant-service/internal/assistant/assistant_task_view/adapters/inbound/http"
	taskapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_task_view/application"
	taskmodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_task_view/domain/model"
	tasksource "quwoquan_service/services/assistant-service/internal/assistant/assistant_task_view/infrastructure/source"
	catalogapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_catalog/application"
	catalogactive "quwoquan_service/services/assistant-service/internal/assistant/skill_catalog/infrastructure/activerelease"
	catalogresource "quwoquan_service/services/assistant-service/internal/assistant/skill_catalog/infrastructure/resource"
	packageapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/application"
	packagemodel "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/domain/model"
	subscriptionapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_subscription/application"
	subscriptionmodel "quwoquan_service/services/assistant-service/internal/assistant/skill_subscription/domain/model"
	subscriptionpersistence "quwoquan_service/services/assistant-service/internal/assistant/skill_subscription/infrastructure/persistence"
)

func TestAssistantTaskViewFederatesRealSubscriptionsAndActiveCatalog(t *testing.T) {
	testinfra.ConfigureLocalContainerRuntime()
	startupCtx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()
	runtime, err := testinfra.StartRealMongo(startupCtx, "assistant_task_view_api_integration")
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

	store := subscriptionpersistence.NewMongoStore(runtime.Database)
	if err := store.EnsureIndexes(startupCtx); err != nil {
		t.Fatalf("ensure subscription indexes: %v", err)
	}
	catalogQueries := catalogapplication.NewQueryService(productionCatalogSource(t))
	catalog, err := catalogQueries.ListSkills(startupCtx, catalogapplication.ListSkillsQuery{
		AccountID: "task-owner",
		Limit:     100,
	})
	if err != nil || len(catalog.Items) < 2 {
		t.Fatalf("load active immutable Skill catalog: items=%d err=%v", len(catalog.Items), err)
	}

	now := time.Date(2026, 8, 10, 3, 0, 0, 0, time.UTC)
	clock := now
	commands := subscriptionapplication.NewUseCases(
		store,
		nil,
		nil,
		func() time.Time { return clock },
	)
	active := createSubscription(t, commands, "task-owner", catalog.Items[0].SkillID, catalog.Items[0].DomainID, "active")
	clock = clock.Add(time.Minute)
	paused := createSubscription(t, commands, "task-owner", catalog.Items[1].SkillID, catalog.Items[1].DomainID, "paused")
	paused, err = commands.UpdateStatus(startupCtx, "task-owner", paused.SubscriptionID, subscriptionmodel.UpdateSkillSubscriptionStatusInput{
		Status:          subscriptionmodel.SkillSubscriptionStatusPaused,
		ClientRequestID: "pause-task-subscription",
	})
	if err != nil {
		t.Fatalf("pause subscription: %v", err)
	}
	_ = createSubscription(t, commands, "other-owner", catalog.Items[0].SkillID, catalog.Items[0].DomainID, "other")

	mux := http.NewServeMux()
	taskhttp.NewHandler(taskapplication.NewQueryFacade(
		tasksource.NewSubscriptionTaskReader(store, catalogQueries),
	)).RegisterRoutes(mux)

	response := requestTasks(mux, "/assistant/tasks?limit=10", "task-owner")
	if response.Code != http.StatusOK {
		t.Fatalf("task query status=%d body=%s", response.Code, response.Body.String())
	}
	var view taskmodel.Slice
	if err := json.Unmarshal(response.Body.Bytes(), &view); err != nil {
		t.Fatalf("decode task view: %v", err)
	}
	if len(view.Items) != 2 {
		t.Fatalf("task view count=%d items=%+v", len(view.Items), view.Items)
	}
	byID := make(map[string]taskmodel.Item, len(view.Items))
	for _, item := range view.Items {
		byID[item.TaskID] = item
		if item.AccountID != "" || item.Title == "" || item.TaskID == "" || item.TaskID == "other" {
			t.Fatalf("task projection leaked owner or raw identity: %+v", item)
		}
	}
	if byID[active.SubscriptionID].Status != "in_progress" || byID[active.SubscriptionID].DueAt == nil ||
		byID[paused.SubscriptionID].Status != "pending" || byID[paused.SubscriptionID].DueAt != nil {
		t.Fatalf("task state mapping drifted: %+v", byID)
	}
	if view.Items[0].TaskID != paused.SubscriptionID || view.Items[1].TaskID != active.SubscriptionID {
		t.Fatalf("task ordering drifted: %+v", view.Items)
	}

	filtered := requestTasks(mux, "/assistant/tasks?status=in_progress&limit=10", "task-owner")
	if filtered.Code != http.StatusOK {
		t.Fatalf("filtered task query status=%d body=%s", filtered.Code, filtered.Body.String())
	}
	view = taskmodel.Slice{}
	if err := json.Unmarshal(filtered.Body.Bytes(), &view); err != nil ||
		len(view.Items) != 1 || view.Items[0].TaskID != active.SubscriptionID {
		t.Fatalf("filtered task view=%+v err=%v", view, err)
	}

	clock = clock.Add(time.Minute)
	paused, err = commands.UpdateStatus(startupCtx, "task-owner", paused.SubscriptionID, subscriptionmodel.UpdateSkillSubscriptionStatusInput{
		Status:          subscriptionmodel.SkillSubscriptionStatusArchived,
		ClientRequestID: "archive-task-subscription",
	})
	if err != nil {
		t.Fatalf("archive subscription: %v", err)
	}
	completed := requestTasks(mux, "/assistant/tasks?status=completed&limit=10", "task-owner")
	if completed.Code != http.StatusOK {
		t.Fatalf("completed task query status=%d body=%s", completed.Code, completed.Body.String())
	}
	view = taskmodel.Slice{}
	if err := json.Unmarshal(completed.Body.Bytes(), &view); err != nil ||
		len(view.Items) != 1 || view.Items[0].TaskID != paused.SubscriptionID ||
		view.Items[0].Status != "completed" || view.Items[0].DueAt != nil {
		t.Fatalf("completed task view=%+v err=%v", view, err)
	}

	unauthorized := requestTasks(mux, "/assistant/tasks", "")
	if unauthorized.Code != http.StatusUnauthorized {
		t.Fatalf("untrusted request status=%d body=%s", unauthorized.Code, unauthorized.Body.String())
	}

	clock = clock.Add(time.Minute)
	_ = createSubscription(t, commands, "task-owner", "missing_active_skill", "test", "missing")
	unavailable := requestTasks(mux, "/assistant/tasks", "task-owner")
	if unavailable.Code != http.StatusServiceUnavailable ||
		!strings.Contains(unavailable.Body.String(), "ASSISTANT.SYSTEM.task_projection_unavailable") {
		t.Fatalf("catalog drift status=%d body=%s", unavailable.Code, unavailable.Body.String())
	}
}

func createSubscription(
	t *testing.T,
	commands *subscriptionapplication.UseCases,
	ownerID string,
	skillID string,
	domainID string,
	requestSuffix string,
) subscriptionmodel.SkillSubscription {
	t.Helper()
	created, err := commands.Create(t.Context(), ownerID, subscriptionmodel.CreateSkillSubscriptionInput{
		SkillID:  skillID,
		DomainID: domainID,
		SearchQueryPlan: subscriptionmodel.SkillSubscriptionSearchQueryPlan{
			RawText: "task projection source",
			Queries: []string{"task projection source"},
		},
		Trigger: subscriptionmodel.SkillSubscriptionTrigger{
			Type: "cron", Cron: "0 8 * * *", Timezone: "UTC",
		},
		Destination: subscriptionmodel.SkillSubscriptionDestination{
			DestinationType: subscriptionmodel.SkillSubscriptionDestinationUser,
			DestinationID:   ownerID,
		},
		ClientRequestID: "create-task-subscription-" + requestSuffix,
	})
	if err != nil {
		t.Fatalf("create subscription %q: %v", requestSuffix, err)
	}
	return created
}

func requestTasks(handler http.Handler, path string, accountID string) *httptest.ResponseRecorder {
	request := httptest.NewRequest(http.MethodGet, path, nil)
	if accountID != "" {
		request = request.WithContext(rtauth.WithPrincipal(request.Context(), rtauth.Principal{
			Actor: operation.ActorContext{AccountID: accountID, PersonaID: accountID + ":persona"},
		}))
	}
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	return recorder
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

func productionCatalogSource(t *testing.T) *catalogactive.CatalogSource {
	t.Helper()
	bundle, err := catalogresource.NewSourceBuilder().Compile(t.Context())
	if err != nil {
		t.Fatalf("compile canonical Skill package source: %v", err)
	}
	built, err := catalogresource.BuildPackage(bundle, catalogresource.PackageBuildOptions{
		PackageID:        catalogactive.OfficialPackageID,
		PackageVersion:   "1.0.0",
		BuildID:          "assistant-task-view-api-integration",
		SourceRepository: "quwoquan",
		SourceRevision:   "assistant-task-view-federated-source",
		BuiltAt:          time.Date(2026, 8, 10, 3, 0, 0, 0, time.UTC),
		RuntimeCompatibility: packagemodel.RuntimeCompatibility{
			APIVersion:            packagemodel.RuntimeAPIVersion,
			MinimumRuntimeVersion: packagemodel.RuntimeVersion,
			MaximumRuntimeVersion: packagemodel.RuntimeVersion,
		},
		CapabilityGrants: []packagemodel.CapabilityGrant{{
			CapabilityID: "assistant.skill",
			Scope:        "official",
		}},
		SigningKeyID:      "assistant-task-view-api-key",
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
	return catalogactive.NewCatalogSource(
		activeReleaseResolver{resolved: packageapplication.ResolvedRelease{
			Release: built.Release,
			Assets:  assets,
		}},
		catalogactive.OfficialPackageID,
		runorchestration.ValidateAssistantDomainSkillCatalog,
	)
}
