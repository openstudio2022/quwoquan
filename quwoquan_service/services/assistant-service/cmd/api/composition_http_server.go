package bootstrap

import (
	"context"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	rthttp "quwoquan_service/runtime/http"
	rtmetrics "quwoquan_service/runtime/metrics"
	robs "quwoquan_service/runtime/observability"
	entryhttp "quwoquan_service/services/assistant-service/internal/assistant/assistant_entry_view/adapters/inbound/http"
	entryapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_entry_view/application"
	learninghttp "quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/adapters/inbound/http"
	policyreleasehttp "quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_release/adapters/inbound/http"
	policyrollouthttp "quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_rollout/adapters/inbound/http"
	preferencehttp "quwoquan_service/services/assistant-service/internal/assistant/assistant_preference/adapters/inbound/http"
	runhttp "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/adapters/inbound/http"
	httpadapter "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/adapters/inbound/http"
	taskhttp "quwoquan_service/services/assistant-service/internal/assistant/assistant_task_view/adapters/inbound/http"
	taskapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_task_view/application"
	tasksource "quwoquan_service/services/assistant-service/internal/assistant/assistant_task_view/infrastructure/source"
	turnviewhttp "quwoquan_service/services/assistant-service/internal/assistant/assistant_turn_view/adapters/inbound/http"
	turnviewapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_turn_view/application"
	pagehttp "quwoquan_service/services/assistant-service/internal/assistant/page_context/adapters/inbound/http"
	activityhttp "quwoquan_service/services/assistant-service/internal/assistant/skill_activity_view/adapters/inbound/http"
	activityapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_activity_view/application"
	activitysource "quwoquan_service/services/assistant-service/internal/assistant/skill_activity_view/infrastructure/source"
	skillcataloghttp "quwoquan_service/services/assistant-service/internal/assistant/skill_catalog/adapters/inbound/http"
	skillcatalogapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_catalog/application"
	consenthttp "quwoquan_service/services/assistant-service/internal/assistant/skill_consent/adapters/inbound/http"
	datacontrolhttp "quwoquan_service/services/assistant-service/internal/assistant/skill_data_control_request/adapters/inbound/http"
	datacontrolapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_data_control_request/application"
	skillpackagehttp "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/adapters/inbound/http"
	subscriptionhttp "quwoquan_service/services/assistant-service/internal/assistant/skill_subscription/adapters/inbound/http"
	subscriptionapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_subscription/application"
	placementhttp "quwoquan_service/services/assistant-service/internal/assistant/skill_surface_placement/adapters/inbound/http"
	settinghttp "quwoquan_service/services/assistant-service/internal/assistant/skill_user_setting/adapters/inbound/http"
)

const dependencyHealthResponseDrainLimitBytes = 4 << 10

func buildAssistantHTTPServer(
	runtime *assistantAPIRuntime,
	infrastructure *assistantInfrastructure,
	assistant *assistantComponents,
) *http.Server {
	deps := infrastructure.dependencies
	baseHandler := httpadapter.NewHandler(assistant.service).Routes()
	skillCatalogQueries := skillcatalogapplication.NewQueryService(
		assistant.activeSkillCatalog,
	)
	serviceMux := http.NewServeMux()
	runhttp.NewHandler(
		assistant.runCommands,
		runhttp.WithPreferenceSnapshots(assistant.preferenceQueries),
		runhttp.WithContextResolver(assistant.runContextResolver),
	).RegisterRoutes(serviceMux)
	subscriptionUseCases := subscriptionapplication.NewUseCases(
		deps.subscriptionStore,
		assistant.chatGroundingClient,
		assistant.service,
		time.Now,
	)
	entryhttp.NewHandler(entryapplication.NewQueryFacade(
		deps.entryViewReader,
		assistant.pageContextFacade,
	)).RegisterRoutes(serviceMux)
	taskhttp.NewHandler(
		taskapplication.NewQueryFacade(tasksource.NewSubscriptionTaskReader(
			deps.subscriptionReader,
			skillCatalogQueries,
		)),
	).RegisterRoutes(serviceMux)
	pagehttp.NewHandler(assistant.pageContextFacade).RegisterRoutes(serviceMux)
	subscriptionhttp.NewHandler(
		subscriptionUseCases,
	).RegisterRoutes(serviceMux)
	preferencehttp.NewHandler(
		assistant.preferenceCommands,
		assistant.preferenceQueries,
	).RegisterRoutes(serviceMux)
	consenthttp.NewHandler(
		assistant.consentCommands,
		assistant.consentQueries,
	).RegisterRoutes(serviceMux)
	activityQueries := activityapplication.NewQueryFacade(
		deps.skillActivityStore,
		activitysource.NewRunSource(deps.runRepository),
		activitysource.NewConsentSource(deps.consentActivity),
		activitysource.NewSubscriptionSource(deps.subscriptionReader),
		activitysource.NewDataControlSource(deps.dataControlStore),
	)
	activityhttp.NewHandler(activityQueries).RegisterRoutes(serviceMux)
	datacontrolhttp.NewHandler(datacontrolapplication.NewService(
		deps.dataControlStore,
		time.Now,
		nil,
	)).RegisterRoutes(serviceMux)
	settinghttp.NewHandler(
		assistant.settingCommands,
		assistant.settingQueries,
	).RegisterRoutes(serviceMux)
	placementhttp.NewHandler(
		assistant.placementCommands,
		assistant.placementQueries,
	).RegisterRoutes(serviceMux)
	policyreleasehttp.NewHandler(
		assistant.policyReleaseService,
	).RegisterRoutes(serviceMux)
	policyrollouthttp.NewHandler(
		assistant.policyRolloutService,
	).RegisterRoutes(serviceMux)
	skillpackagehttp.NewHandler(
		assistant.skillPackageService,
	).RegisterRoutes(serviceMux)
	turnviewhttp.NewHandler(
		turnviewapplication.NewQueryFacade(
			deps.turnViewReader,
			deps.sessionStore,
			deps.turnViewProjector,
		),
	).RegisterRoutes(serviceMux)
	learninghttp.NewHandler(
		assistant.learningFactService,
		assistant.learningOpsQueries,
	).RegisterRoutes(serviceMux)
	assistant.domainReaderHandler.RegisterRoutes(serviceMux)
	skillcataloghttp.NewHandler(skillCatalogQueries).RegisterRoutes(serviceMux)
	serviceMux.Handle("/", baseHandler)
	baseHandler = serviceMux
	outerMux := http.NewServeMux()
	// Compose / k8s liveness stays shallow: process is up. Deep dependency and
	// worker probes belong on /readyz so a slow first worker/external scan
	// cannot keep the container unhealthy for the full start_period window.
	outerMux.HandleFunc("/healthz", func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"status":"ok"}`))
	})
	outerMux.HandleFunc("/readyz", infrastructure.healthChecker.Handler())
	outerMux.Handle("/metrics", rtmetrics.Handler())
	outerMux.Handle("/", httpadapter.GeneratedOperationContractHandler(baseHandler))
	observedHandler := rthttp.NewHTTPServerMiddleware(
		outerMux,
		rthttp.HTTPServerMiddlewareConfig{
			Service:           "assistant-service",
			ServiceName:       "assistant-service",
			ServiceInstanceID: runtime.instanceID,
			Origin:            "service.http",
			Direction:         robs.DirectionInbound,
			SourceID:          "assistant-service",
			Src:               "assistant-service",
			EndpointResolver:  httpadapter.GeneratedOperationPathTemplateResolver(),
		},
		runtime.ioLogger,
		runtime.processLogger,
		runtime.exceptionLogger,
	)
	corsHandler := rthttp.WithCORS(observedHandler, rthttp.CORSOptionsFromEnv())
	timeouts := rtauth.ContractHTTPServerTimeouts(
		httpadapter.AssistantOperationDescriptors(),
	)
	return &http.Server{
		Addr: runtime.addr,
		Handler: withAssistantAccessMiddleware(
			corsHandler,
			runtime.accessVerifier,
			runtime.accountSecurityAuthority,
		),
		ReadHeaderTimeout: timeouts.ReadHeader,
		WriteTimeout:      timeouts.Write,
		IdleTimeout:       timeouts.Idle,
	}
}

func checkServiceHealth(
	ctx context.Context,
	client *http.Client,
	baseURL string,
) error {
	request, err := http.NewRequestWithContext(
		ctx,
		http.MethodGet,
		strings.TrimRight(strings.TrimSpace(baseURL), "/")+"/healthz",
		nil,
	)
	if err != nil {
		return err
	}
	response, err := client.Do(request)
	if err != nil {
		return err
	}
	defer response.Body.Close()
	if _, err := io.Copy(
		io.Discard,
		io.LimitReader(response.Body, dependencyHealthResponseDrainLimitBytes),
	); err != nil {
		return fmt.Errorf("read dependency health response: %w", err)
	}
	if response.StatusCode != http.StatusOK {
		return fmt.Errorf("dependency health status=%d", response.StatusCode)
	}
	return nil
}
