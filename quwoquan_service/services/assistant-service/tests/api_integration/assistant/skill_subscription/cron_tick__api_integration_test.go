// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/skill-user-lifecycle/spec.md#gwt-002
// readiness_case: tick-skill-subscription-cron-api
package api_integration

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/generated/serviceclients"
	platformredis "quwoquan_service/internal/platform/redis"
	"quwoquan_service/internal/platform/testinfra"
	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	rtredis "quwoquan_service/runtime/redis"
	runorchestration "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/orchestration"
	runruntime "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	assistant "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
	runpersistence "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/infrastructure"
	sessionorchestration "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/orchestration"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/infrastructure/notificationclient"
	sessionpersistence "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/infrastructure/persistence"
	consentapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_consent/application"
	consentpersistence "quwoquan_service/services/assistant-service/internal/assistant/skill_consent/infrastructure/persistence"
	skillpkg "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/application/packageasset"
	subscriptionhttp "quwoquan_service/services/assistant-service/internal/assistant/skill_subscription/adapters/inbound/http"
	subscriptionapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_subscription/application"
	skillmodel "quwoquan_service/services/assistant-service/internal/assistant/skill_subscription/domain/model"
	subscriptionpersistence "quwoquan_service/services/assistant-service/internal/assistant/skill_subscription/infrastructure/persistence"
	"quwoquan_service/services/assistant-service/tests/support/skillfixture"
)

const subscriptionTickDigest = "sha256:dda18a0e21ae47c53b4309434cbc02ae8bf764fa83a6defbb719431242722aa7"

type subscriptionTickServiceCredentials string

func (credentials subscriptionTickServiceCredentials) AuthorizationHeader(
	context.Context,
) (string, error) {
	return "Bearer " + string(credentials), nil
}

type subscriptionTickSkillRuntime struct{}

func (subscriptionTickSkillRuntime) SelectSkill(
	context.Context,
	assistant.AssistantTurn,
) (runorchestration.SkillSelection, error) {
	return runorchestration.SkillSelection{
		SkillID:     "news_briefing",
		DomainID:    "assistant",
		DisplayName: "资讯简报",
	}, nil
}

type subscriptionTickModel struct{}

func (subscriptionTickModel) ModelExecutionCapabilities() runorchestration.ModelExecutionCapabilities {
	return runorchestration.ModelExecutionCapabilities{
		ToolCalling:     true,
		ParallelTools:   true,
		ReasoningEffort: true,
	}
}

func (subscriptionTickModel) Complete(
	context.Context,
	runorchestration.ModelRequest,
) (runorchestration.ModelResponse, error) {
	return runorchestration.ModelResponse{Text: "本期资讯简报已生成"}, nil
}

func TestSkillSubscriptionCronHTTPUsesMongoRedisAndTypedDeliveryClients(
	t *testing.T,
) {
	testinfra.ConfigureLocalContainerRuntime()
	startupCtx, cancelStartup := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancelStartup()
	mongoRuntime, err := testinfra.StartRealMongo(
		startupCtx,
		"assistant_skill_subscription_cron_api_integration",
	)
	if err != nil {
		t.Fatalf("start real MongoDB replica set: %v", err)
	}
	redisRuntime, err := testinfra.StartRealRedis(startupCtx)
	if err != nil {
		closeCtx, closeCancel := context.WithTimeout(context.Background(), 30*time.Second)
		defer closeCancel()
		_ = mongoRuntime.Close(closeCtx)
		t.Fatalf("start real Redis: %v", err)
	}
	if err := redisRuntime.FlushDBs(startupCtx, 0); err != nil {
		t.Fatalf("flush real Redis: %v", err)
	}
	postgresFixture, err := testinfra.StartPostgresFixture(t.TempDir(), 0)
	if err != nil {
		t.Fatalf("start real PostgreSQL: %v", err)
	}
	t.Cleanup(func() {
		if closeErr := postgresFixture.Close(); closeErr != nil {
			t.Errorf("close real PostgreSQL: %v", closeErr)
		}
	})
	consentPool, err := pgxpool.New(startupCtx, postgresFixture.DSN())
	if err != nil {
		t.Fatalf("connect real PostgreSQL: %v", err)
	}
	t.Cleanup(consentPool.Close)
	if err := consentPool.Ping(startupCtx); err != nil {
		t.Fatalf("ping real PostgreSQL: %v", err)
	}
	consents := consentpersistence.NewPgStore(consentPool)
	if err := consents.EnsureSchema(startupCtx); err != nil {
		t.Fatalf("ensure SkillConsent schema: %v", err)
	}
	redisRouter, err := platformredis.NewRouter(rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"general": {
				Mode:     "standalone",
				Addr:     redisRuntime.Addr,
				Password: redisRuntime.Password,
				DB:       0,
				TLS:      redisRuntime.TLS,
			},
		},
		DefaultScene: "general",
	})
	if err != nil {
		t.Fatalf("construct production Redis adapter: %v", err)
	}
	t.Cleanup(func() {
		closeCtx, closeCancel := context.WithTimeout(context.Background(), 30*time.Second)
		defer closeCancel()
		if closeErr := redisRouter.Close(); closeErr != nil {
			t.Errorf("close Redis router: %v", closeErr)
		}
		if closeErr := redisRuntime.Close(closeCtx); closeErr != nil {
			t.Errorf("close real Redis: %v", closeErr)
		}
		if closeErr := mongoRuntime.Close(closeCtx); closeErr != nil {
			t.Errorf("close real MongoDB: %v", closeErr)
		}
	})

	subscriptions := subscriptionpersistence.NewMongoStore(mongoRuntime.Database)
	if err := subscriptions.EnsureIndexes(startupCtx); err != nil {
		t.Fatalf("ensure SkillSubscription indexes: %v", err)
	}
	sessions := sessionpersistence.NewMongoSessionStore(mongoRuntime.Database)
	if err := sessions.EnsureIndexes(startupCtx); err != nil {
		t.Fatalf("ensure AssistantSession indexes: %v", err)
	}
	runs := runpersistence.NewMongoRunRepository(mongoRuntime.Database)
	if err := runs.EnsureIndexes(startupCtx); err != nil {
		t.Fatalf("ensure AssistantRun indexes: %v", err)
	}

	const userID = "subscription-tick-user"
	policyRequests := 0
	policyServer := httptest.NewServer(http.HandlerFunc(func(
		writer http.ResponseWriter,
		request *http.Request,
	) {
		if request.Method != http.MethodGet ||
			request.URL.Path != serviceclients.UserResolveAssistantDeliveryPolicyPath(userID) {
			http.NotFound(writer, request)
			return
		}
		if request.Header.Get("Authorization") != "Bearer delivery-policy-token" {
			http.Error(writer, "missing service authorization", http.StatusUnauthorized)
			return
		}
		policyRequests++
		writer.Header().Set("Content-Type", "application/json")
		_, _ = writer.Write([]byte(`{"userId":"subscription-tick-user","assistantEnabled":true,"version":1,"updatedAt":"2026-08-05T08:00:00Z"}`))
	}))
	defer policyServer.Close()
	deliveryPolicies, err := sessionorchestration.NewUserDeliveryPolicyClient(
		policyServer.URL,
		subscriptionTickServiceCredentials("delivery-policy-token"),
		policyServer.Client(),
	)
	if err != nil {
		t.Fatalf("construct production delivery policy client: %v", err)
	}

	notificationRequests := 0
	notificationServer := httptest.NewServer(http.HandlerFunc(func(
		writer http.ResponseWriter,
		request *http.Request,
	) {
		if request.Method != http.MethodPost ||
			request.URL.Path != serviceclients.NotificationCreateAppMessagePath {
			http.NotFound(writer, request)
			return
		}
		if request.Header.Get("Authorization") != "Bearer notification-token" ||
			strings.TrimSpace(request.Header.Get("Idempotency-Key")) == "" {
			http.Error(writer, "missing trusted command identity", http.StatusUnauthorized)
			return
		}
		notificationRequests++
		writer.Header().Set("Content-Type", "application/json")
		writer.WriteHeader(http.StatusCreated)
		_ = json.NewEncoder(writer).Encode(map[string]any{
			"messageId": "message-" + request.Header.Get("Idempotency-Key"),
		})
	}))
	defer notificationServer.Close()
	notifications, err := notificationclient.NewClient(
		notificationServer.Client(),
		notificationServer.URL,
		subscriptionTickServiceCredentials("notification-token"),
	)
	if err != nil {
		t.Fatalf("construct production notification command client: %v", err)
	}

	catalog := skillfixture.StaticLoader{Manifests: []skillpkg.Manifest{{
		SkillID:     "news_briefing",
		DomainID:    "assistant",
		DisplayName: "资讯简报",
		Activation:  skillpkg.ActivationProactive,
		ContextProfile: skillpkg.ContextProfile{
			ProfileID: "context.news_briefing.api_integration",
			Requirements: []skillpkg.ContextRequirement{{
				SlotID:        "news_sources",
				Required:      true,
				ConsentScopes: []string{"assistant.news.read"},
			}},
		},
	}}}
	if _, err := consentapplication.NewCommandFacade(consents, time.Now).Grant(
		startupCtx,
		"grant-news-briefing-consent-api",
		userID,
		"news_briefing",
		[]string{"assistant.news.read"},
	); err != nil {
		t.Fatalf("grant real SkillConsent: %v", err)
	}
	loop := runorchestration.NewAgentLoop(
		subscriptionTickSkillRuntime{},
		runorchestration.ReactRuntime{Model: subscriptionTickModel{}},
		nil,
	)
	loop.Catalog = catalog
	runCommands := runruntime.NewCommandService(
		runs,
		runruntime.SessionResolverFunc(func(
			context.Context,
			string,
			string,
		) (runruntime.SessionContinuity, error) {
			return runruntime.SessionContinuity{}, nil
		}),
		runruntime.StaticSkillPackageIdentityResolver{
			PackageID:     "assistant.session.skills",
			ReleaseDigest: subscriptionTickDigest,
		},
		runruntime.AllowAllStartAccessPolicy{},
		time.Now,
		nil,
		runruntime.WithPolicyResolver(runruntime.PolicyResolverFunc(func(
			_ context.Context,
			policyID string,
			_ string,
			skillID string,
			domainID string,
		) (runruntime.FrozenPolicySelection, error) {
			if strings.TrimSpace(policyID) == "" {
				policyID = "assistant-default"
			}
			return runruntime.FrozenPolicySelection{
				PolicyID:        policyID,
				ReleaseDigest:   subscriptionTickDigest,
				Cohort:          "control",
				RolloutRevision: 1,
				RuleID:          "subscription-tick-api",
				Template: runruntime.FrozenPolicyTemplate{
					TemplateID:      "subscription-tick-api",
					SkillID:         skillID,
					DomainID:        domainID,
					PromptPolicy:    "generate the subscribed briefing",
					AllowedTools:    []string{},
					SearchIntensity: "medium",
				},
			}, nil
		})),
	)
	worker := runruntime.NewDurableWorker(
		runs,
		runs,
		runorchestration.NewDurableRunExecutor(loop),
		"subscription-tick-api-worker",
	)
	workerCtx, cancelWorker := context.WithCancel(context.Background())
	workerDone := make(chan struct{})
	go func() {
		defer close(workerDone)
		worker.Run(workerCtx)
	}()
	t.Cleanup(func() {
		cancelWorker()
		select {
		case <-workerDone:
		case <-time.After(5 * time.Second):
			t.Error("AssistantRun worker did not stop")
		}
	})

	deliveryService := sessionorchestration.NewAssistantService(
		consents,
		redisRouter.Scene("general"),
		sessionorchestration.WithSkillSubscriptionStore(subscriptions),
		sessionorchestration.WithSessionStore(sessions),
		sessionorchestration.WithRunCommandService(runCommands),
		sessionorchestration.WithAssistantDeliveryPolicyReader(deliveryPolicies),
		sessionorchestration.WithNotificationAppMessageCommandWriter(notifications),
		sessionorchestration.WithSkillCatalog(catalog),
	)
	mux := http.NewServeMux()
	subscriptionhttp.NewHandler(subscriptionapplication.NewUseCases(
		subscriptions,
		nil,
		deliveryService,
		time.Now,
	)).RegisterRoutes(mux)

	created := skillSubscriptionRequest(
		t,
		mux,
		http.MethodPost,
		"/assistant/skill-subscriptions",
		userID,
		"create-cron-subscription-api",
		map[string]any{
			"skillId":  "news_briefing",
			"domainId": "assistant",
			"searchQueryPlan": map[string]any{
				"rawText": "生成本期资讯简报",
				"queries": []string{},
			},
			"trigger": map[string]any{
				"type":     "cron",
				"cron":     "30 8 * * *",
				"timezone": "UTC",
			},
			"destination": map[string]any{
				"destinationType":  "user",
				"maxPerDay":        1,
				"cooldownMinutes":  60,
				"quietHoursPolicy": "inherit_user_setting",
			},
			"clientRequestId": "create-cron-subscription-api",
		},
	)
	if created.Code != http.StatusCreated {
		t.Fatalf("create cron subscription status=%d body=%s", created.Code, created.Body.String())
	}
	var subscription skillmodel.SkillSubscription
	if err := json.Unmarshal(created.Body.Bytes(), &subscription); err != nil {
		t.Fatalf("decode cron subscription: %v", err)
	}
	if subscription.DeliveryState.NextAttemptAt == nil {
		t.Fatalf("cron subscription has no nextAttemptAt: %+v", subscription)
	}
	tickAt := subscription.DeliveryState.NextAttemptAt.UTC().Format(time.RFC3339)
	first := skillSubscriptionCronRequest(t, mux, "tick-cron-api-first", tickAt)
	if first.Code != http.StatusOK {
		t.Fatalf("first cron tick status=%d body=%s", first.Code, first.Body.String())
	}
	var firstResult skillmodel.SkillSubscriptionCronTickResult
	if err := json.Unmarshal(first.Body.Bytes(), &firstResult); err != nil {
		t.Fatalf("decode first cron tick: %v", err)
	}
	if firstResult.ProcessedCount != 1 || len(firstResult.CreatedTurnIDs) != 1 ||
		len(firstResult.CreatedMessageIDs) != 1 {
		t.Fatalf("first cron tick result=%+v", firstResult)
	}
	second := skillSubscriptionCronRequest(t, mux, "tick-cron-api-second", tickAt)
	if second.Code != http.StatusOK {
		t.Fatalf("second cron tick status=%d body=%s", second.Code, second.Body.String())
	}
	var secondResult skillmodel.SkillSubscriptionCronTickResult
	if err := json.Unmarshal(second.Body.Bytes(), &secondResult); err != nil {
		t.Fatalf("decode second cron tick: %v", err)
	}
	if secondResult.ProcessedCount != 0 || len(secondResult.CreatedTurnIDs) != 0 ||
		len(secondResult.CreatedMessageIDs) != 0 {
		t.Fatalf("same-window cron tick was not deduplicated: %+v", secondResult)
	}
	if policyRequests != 1 || notificationRequests != 1 {
		t.Fatalf("typed delivery calls policy=%d notification=%d, want 1/1", policyRequests, notificationRequests)
	}
	assertMongoCount(
		t,
		mongoRuntime.Database.Collection("assistant_runs"),
		bson.M{"clientRequestId": bson.M{"$regex": ":run$"}},
		1,
	)
	assertMongoCount(
		t,
		mongoRuntime.Database.Collection("assistant_sessions"),
		bson.M{"userId": userID},
		1,
	)
	stored, err := subscriptions.GetSkillSubscription(
		t.Context(),
		userID,
		subscription.SubscriptionID,
	)
	if err != nil || stored.DeliveryState.LastDeliveredAt == nil ||
		stored.DeliveryState.NextAttemptAt == nil ||
		stored.DeliveryState.PendingDeliveryID != "" ||
		stored.DeliveryState.ConsecutiveFailures != 0 {
		t.Fatalf("durable delivery audit=%+v error=%v", stored.DeliveryState, err)
	}
}

func skillSubscriptionCronRequest(
	t *testing.T,
	handler http.Handler,
	commandID string,
	now string,
) *httptest.ResponseRecorder {
	t.Helper()
	payload, err := json.Marshal(map[string]any{"now": now})
	if err != nil {
		t.Fatalf("marshal cron tick request: %v", err)
	}
	request := httptest.NewRequest(
		http.MethodPost,
		"/internal/assistant/skill-subscriptions:tick",
		bytes.NewReader(payload),
	)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Idempotency-Key", commandID)
	request = request.WithContext(rtauth.WithPrincipal(
		request.Context(),
		rtauth.Principal{
			Claims: rtauth.Claims{Subject: "assistant-subscription-scheduler"},
			Actor: operation.ActorContext{
				AccountID: "assistant-service",
			},
		},
	))
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	return recorder
}
