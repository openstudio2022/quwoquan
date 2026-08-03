package main

import (
	"context"
	"errors"
	"fmt"
	"io"
	"log"
	"log/slog"
	"net/http"
	"os"
	"strings"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	runtimeconfig "quwoquan_service/runtime/config"
	"quwoquan_service/runtime/controlplane"
	rtgov "quwoquan_service/runtime/governance"
	rthealth "quwoquan_service/runtime/health"
	rthttp "quwoquan_service/runtime/http"
	rtmetrics "quwoquan_service/runtime/metrics"
	robs "quwoquan_service/runtime/observability"
	rtotel "quwoquan_service/runtime/otel"
	runerrors "quwoquan_service/services/assistant-service/generated/assistant/assistant_run"
	consenterrors "quwoquan_service/services/assistant-service/generated/assistant/skill_consent"
	entryhttp "quwoquan_service/services/assistant-service/internal/assistant/assistant_entry_view/adapters/inbound/http"
	entryapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_entry_view/application"
	learninghttp "quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/adapters/inbound/http"
	learningapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/application"
	learningmodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/domain/model"
	learningmessaging "quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/infrastructure/messaging"
	learningprojection "quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/infrastructure/projection"
	policyreleasehttp "quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_release/adapters/inbound/http"
	policyreleaseapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_release/application"
	policymessaging "quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_release/infrastructure/messaging"
	policyrollouthttp "quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_rollout/adapters/inbound/http"
	policyrolloutapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_rollout/application"
	preferencehttp "quwoquan_service/services/assistant-service/internal/assistant/assistant_preference/adapters/inbound/http"
	preferencefact "quwoquan_service/services/assistant-service/internal/assistant/assistant_preference/application"
	runapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/toolaccess"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/infrastructure/connectorgateway"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/infrastructure/domainreader"
	httpadapter "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/adapters/inbound/http"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/orchestration"
	toolpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/tool"
	assistantdomain "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/assistant"
	sessionports "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/ports"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/infrastructure/chatclient"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/infrastructure/intersectionclient"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/infrastructure/messaging"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/infrastructure/notificationclient"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/infrastructure/scheduling"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/infrastructure/searchclient"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/infrastructure/userprofile"
	taskhttp "quwoquan_service/services/assistant-service/internal/assistant/assistant_task_view/adapters/inbound/http"
	taskapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_task_view/application"
	turnviewhttp "quwoquan_service/services/assistant-service/internal/assistant/assistant_turn_view/adapters/inbound/http"
	turnviewapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_turn_view/application"
	pagehttp "quwoquan_service/services/assistant-service/internal/assistant/page_context/adapters/inbound/http"
	pageapplication "quwoquan_service/services/assistant-service/internal/assistant/page_context/application"
	pagepersistence "quwoquan_service/services/assistant-service/internal/assistant/page_context/infrastructure/persistence"
	skillcataloghttp "quwoquan_service/services/assistant-service/internal/assistant/skill_catalog/adapters/inbound/http"
	skillcatalogapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_catalog/application"
	skillcatalogmodel "quwoquan_service/services/assistant-service/internal/assistant/skill_catalog/domain/model"
	skillcatalogactive "quwoquan_service/services/assistant-service/internal/assistant/skill_catalog/infrastructure/activerelease"
	consenthttp "quwoquan_service/services/assistant-service/internal/assistant/skill_consent/adapters/inbound/http"
	consentapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_consent/application"
	consentmodel "quwoquan_service/services/assistant-service/internal/assistant/skill_consent/domain/model"
	skillpackagehttp "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/adapters/inbound/http"
	skillpackageapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/application"
	skillpackagemodel "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/domain/model"
	skillpackageartifact "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/infrastructure/artifact"
	subscriptionhttp "quwoquan_service/services/assistant-service/internal/assistant/skill_subscription/adapters/inbound/http"
	subscriptionapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_subscription/application"
	placementhttp "quwoquan_service/services/assistant-service/internal/assistant/skill_surface_placement/adapters/inbound/http"
	placementapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_surface_placement/application"
	placementmodel "quwoquan_service/services/assistant-service/internal/assistant/skill_surface_placement/domain/model"
	placementauthority "quwoquan_service/services/assistant-service/internal/assistant/skill_surface_placement/infrastructure/authority"
	placementmessaging "quwoquan_service/services/assistant-service/internal/assistant/skill_surface_placement/infrastructure/messaging"
	settinghttp "quwoquan_service/services/assistant-service/internal/assistant/skill_user_setting/adapters/inbound/http"
	settingapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_user_setting/application"
)

const (
	dependencyHealthResponseDrainLimitBytes = 4 << 10
	skillSubscriptionCronInterval           = time.Minute
	learningProjectionInterval              = time.Second
	learningOutboxRelayInterval             = time.Second
)

func main() {
	if err := run(); err != nil {
		logStartupFailure(err)
		os.Exit(1)
	}
}

func run() error {
	serviceName, appEnv, configRoot, configVersion, imageVersion, err := resolveRuntimeIdentity()
	if err != nil {
		return fmt.Errorf("runtime identity invalid: %w", err)
	}
	runtimeConfigProvider := runtimeconfig.EnvRuntimeConfigProvider{}
	cfg, err := loadRuntimeConfig(serviceName, appEnv, configRoot, configVersion)
	if err != nil {
		return fmt.Errorf("config load failed: %w", err)
	}
	if err := applyEnvOverrides(&cfg); err != nil {
		return fmt.Errorf("environment override invalid: %w", err)
	}
	if err := validateRuntimeConfigurationIdentity(cfg, configVersion); err != nil {
		return fmt.Errorf("config identity failed: %w", err)
	}
	if err := validateRuntimeDependenciesConfig(cfg); err != nil {
		return err
	}
	controlplane.StartReleaseConfigAttestation(
		serviceName, appEnv, configRoot, configVersion, imageVersion,
	)
	accessTokenConfig, err := rtauth.LoadAccessTokenConfig(
		runtimeConfigProvider,
	)
	if err != nil {
		return fmt.Errorf("access token config invalid: %w", err)
	}
	accessVerifier, err := rtauth.NewHS256Verifier(accessTokenConfig)
	if err != nil {
		return fmt.Errorf("access token verifier invalid: %w", err)
	}
	accountSecurityAuthorityCredentials, err := rtauth.NewHS256ServiceAuthorizationProvider(
		accessTokenConfig,
		"assistant-service",
		[]string{"user.account.security.read"},
	)
	if err != nil {
		return fmt.Errorf("account security authority credential init failed: %w", err)
	}
	accountSecurityAuthorityTimeout := time.Duration(
		cfg.AccountSecurityAuthority.TimeoutMs,
	) * time.Millisecond
	accountSecurityAuthority, err := rtauth.NewHTTPAccountSecurityAuthority(
		rtauth.HTTPAccountSecurityAuthorityConfig{
			BaseURL:     cfg.AccountSecurityAuthority.BaseURL,
			HTTPClient:  &http.Client{Timeout: accountSecurityAuthorityTimeout},
			Credentials: accountSecurityAuthorityCredentials,
			Timeout:     accountSecurityAuthorityTimeout,
		},
	)
	if err != nil {
		return fmt.Errorf("account security authority config invalid: %w", err)
	}
	addr := getenvOrDefault("ASSISTANT_SERVICE_ADDR", cfg.Service.HTTP.Addr)
	if addr == "" {
		addr = ":18087"
	}
	instanceID := getenvOrDefault("SERVICE_INSTANCE_ID", hostname())
	// 服务日志上云：stdout/stderr 镜像推送到 Product Ops 内部 runtime log
	// ingest（机器凭据）；未配置时仅 stdout，推送失败静默降级。
	runtimeLogExporter, err := robs.NewHTTPRuntimeLogFieldExporter(
		strings.TrimSpace(os.Getenv("RUNTIME_LOG_INGEST_URL")),
		strings.TrimSpace(os.Getenv("RUNTIME_LOG_INGEST_TOKEN")),
		strings.TrimSpace(os.Getenv("RUNTIME_LOG_SPOOL_DIR")),
	)
	if err != nil {
		return fmt.Errorf("runtime log exporter init failed: %w", err)
	}
	defer runtimeLogExporter.Close()
	standardLogWriter := robs.NewRuntimeLogExportWriter(os.Stdout, 512, runtimeLogExporter.Export)
	errorLogWriter := robs.NewRuntimeLogExportWriter(os.Stderr, 512, runtimeLogExporter.Export)
	defer standardLogWriter.Close()
	defer errorLogWriter.Close()
	ioLogger := robs.NewIOAccessLogger(standardLogWriter)
	processLogger, err := robs.NewProcessTraceLogger(standardLogWriter, errorLogWriter, robs.TraceLogLevelInfo, nil)
	if err != nil {
		return fmt.Errorf("process logger init failed: %w", err)
	}
	exceptionLogger, err := robs.NewExceptionLogger(standardLogWriter, errorLogWriter, nil)
	if err != nil {
		return fmt.Errorf("exception logger init failed: %w", err)
	}
	ctx := context.Background()
	router, err := buildRedisRouter(cfg)
	if err != nil {
		return err
	}
	defer func() {
		if err := router.Close(); err != nil {
			log.Printf("WARN: assistant-service redis close: %v", err)
		}
	}()
	redisProbeCtx, redisProbeCancel := context.WithTimeout(ctx, dependencyProbeTimeout)
	if err := router.PingAll(redisProbeCtx); err != nil {
		redisProbeCancel()
		return dependencyError("redis", "connectivity", err)
	}
	redisProbeCancel()
	messageTransport, err := requireAssistantAPIMessageTransport(
		ctx,
		appEnv,
		router,
		map[string]string{
			"general": cfg.Redis.General.Mode,
		},
	)
	if err != nil {
		return dependencyError("runtime.message.transport", "preflight", err)
	}
	otelShutdown := rtotel.MustInit(rtotel.Config{ServiceName: "assistant-service", SamplingRatio: 0.1})
	defer otelShutdown()

	healthChecker := rthealth.NewChecker()
	healthChecker.Register("account_security_authority", func(hctx context.Context) error {
		return accountSecurityAuthority.CheckAccountSecurityAuthority(hctx)
	})
	healthChecker.Register("redis", func(ctx context.Context) error {
		return router.PingAll(ctx)
	})

	deps, err := openPersistentDependencies(ctx, cfg)
	if err != nil {
		return err
	}
	defer func() {
		closeCtx, cancel := context.WithTimeout(context.Background(), dependencyProbeTimeout)
		defer cancel()
		if err := deps.Close(closeCtx); err != nil {
			log.Printf("WARN: assistant-service persistent dependency close: %v", err)
		}
	}()
	healthChecker.Register("mongodb", func(ctx context.Context) error {
		return deps.mongoClient.Ping(ctx, nil)
	})
	healthChecker.Register("postgres", func(ctx context.Context) error {
		return deps.postgresPool.Ping(ctx)
	})
	log.Printf("assistant-service events storage=mongodb db=%s", cfg.MongoDB.Database)
	log.Printf("assistant-service learning projection storage=mongodb db=%s", cfg.MongoDB.Database)
	log.Printf("assistant-service skill subscription storage=mongodb db=%s", cfg.MongoDB.Database)
	log.Printf("assistant-service consent storage=postgres")
	log.Printf("assistant-service Skill setting/placement storage=postgres")
	trustedSkillPackageKeys, err := skillpackageapplication.DecodeTrustedPublicKeys(
		cfg.SkillPackage.TrustedPublicKeysJSON,
	)
	if err != nil {
		return dependencyError("assistant-skill-package", "trusted-keys", err)
	}
	skillPackageAssets, err := skillpackageartifact.NewResourceReader(
		cfg.SkillPackage.AssetRoot,
	)
	if err != nil {
		return dependencyError("assistant-skill-package", "asset-reader", err)
	}
	skillPackageService := skillpackageapplication.NewService(
		deps.skillPackageStore,
		deps.skillPackageStore,
		skillPackageAssets,
		skillpackageapplication.NewEd25519Verifier(trustedSkillPackageKeys),
		skillpackageapplication.RuntimeIdentity{
			APIVersion: skillpackagemodel.RuntimeAPIVersion,
			Version:    skillpackagemodel.RuntimeVersion,
		},
		time.Now,
	)
	activeSkillCatalog := skillcatalogactive.NewCatalogSource(
		skillPackageService,
		skillcatalogactive.OfficialPackageID,
		orchestration.ValidateAssistantDomainSkillCatalog,
	)
	activeSkillPrompts := skillcatalogactive.NewPromptResolver(
		skillPackageService,
		skillcatalogactive.OfficialPackageID,
	)
	settingQueries := settingapplication.NewQueryFacade(deps.settingStore)
	healthChecker.Register("assistant_skill_package", func(ctx context.Context) error {
		_, resolveErr := activeSkillCatalog.ResolveSnapshot(ctx)
		return resolveErr
	})

	notificationCredentials, err := rtauth.NewHS256ServiceAuthorizationProvider(
		accessTokenConfig,
		"assistant-service",
		[]string{"notification.app_message.create"},
	)
	if err != nil {
		return dependencyError("notification-service", "credentials", err)
	}
	notificationHTTPConfig := rthttp.DefaultHTTPClientFactoryConfig()
	notificationHTTPConfig.Timeout = providerTimeout(cfg.NotificationService.TimeoutMs)
	notificationHTTPConfig.MaxRetries = 0
	notificationHTTPConfig.RetryBackoff = 0
	notificationHTTPConfig.RetryOnCodes = map[int]struct{}{}
	notificationObservedClient := rthttp.NewObservedHTTPClient(
		nil,
		notificationHTTPConfig,
		rthttp.HTTPClientMiddlewareConfig{
			Service:           "assistant-service",
			Origin:            "cloud",
			Direction:         "outbound",
			SourceID:          "assistant-service.notification-command",
			Src:               "assistant-service",
			ServiceName:       "assistant-service",
			ServiceInstanceID: instanceID,
		},
		ioLogger,
		processLogger,
		exceptionLogger,
	)
	notificationWriter, err := notificationclient.NewClient(
		rtgov.WrapClientWithCB(
			notificationObservedClient,
			rtgov.NewCircuitBreaker(5, 15*time.Second, slog.Default()),
		),
		cfg.NotificationService.BaseURL,
		notificationCredentials,
	)
	if err != nil {
		return dependencyError("notification-service", "initialization", err)
	}
	healthChecker.Register("notification_service", func(ctx context.Context) error {
		return checkServiceHealth(
			ctx,
			notificationObservedClient,
			cfg.NotificationService.BaseURL,
		)
	})

	newObservedEgressClient := func(sourceID string, timeoutMs int) *http.Client {
		httpConfig := rthttp.DefaultHTTPClientFactoryConfig()
		httpConfig.Timeout = providerTimeout(timeoutMs)
		observed := rthttp.NewObservedHTTPClient(
			nil,
			httpConfig,
			rthttp.HTTPClientMiddlewareConfig{
				Service:           "assistant-service",
				Origin:            "cloud",
				Direction:         "outbound",
				SourceID:          sourceID,
				Src:               "assistant-service",
				ServiceName:       "assistant-service",
				ServiceInstanceID: instanceID,
			},
			ioLogger,
			processLogger,
			exceptionLogger,
		)
		return rtgov.WrapClientWithCB(
			observed,
			rtgov.NewCircuitBreaker(5, 15*time.Second, slog.Default()),
		)
	}
	deliveryPolicyAuthorization, err :=
		rtauth.NewHS256ServiceAuthorizationProvider(
			accessTokenConfig,
			"assistant-service",
			[]string{"user.assistant_delivery_policy.read"},
		)
	if err != nil {
		return dependencyError("user-service", "credentials", err)
	}
	deliveryPolicyHTTPClient := newObservedEgressClient(
		"assistant-service.user-delivery-policy",
		cfg.UserService.TimeoutMs,
	)
	deliveryPolicyReader, err := orchestration.NewUserDeliveryPolicyClient(
		cfg.UserService.BaseURL,
		deliveryPolicyAuthorization,
		deliveryPolicyHTTPClient,
	)
	if err != nil {
		return dependencyError("user-service", "delivery-policy-reader", err)
	}
	healthChecker.Register("user_service", func(ctx context.Context) error {
		return checkServiceHealth(
			ctx,
			deliveryPolicyHTTPClient,
			cfg.UserService.BaseURL,
		)
	})
	canonicalSearch, err := searchclient.New(
		cfg.SearchService.BaseURL,
		newObservedEgressClient(
			"assistant-service.search-query",
			cfg.SearchService.TimeoutMs,
		),
	)
	if err != nil {
		return dependencyError("search-service", "initialization", err)
	}
	intersectionAuthorization, err := rtauth.NewHS256DelegatedPersonaAuthorizationProvider(
		accessTokenConfig,
		"assistant-service",
		[]string{"content.my_intersections.read"},
	)
	if err != nil {
		return dependencyError("content-service", "credentials", err)
	}
	intersectionInbox, err := intersectionclient.New(intersectionclient.Config{
		BaseURL: cfg.ContentService.BaseURL,
		HTTPClient: newObservedEgressClient(
			"assistant-service.content-intersections",
			cfg.ContentService.TimeoutMs,
		),
		Authorization: intersectionAuthorization,
	})
	if err != nil {
		return dependencyError("content-service", "intersection-reader", err)
	}
	travelAuthorization, err := rtauth.NewHS256DelegatedPersonaAuthorizationProvider(
		accessTokenConfig,
		"assistant-service",
		[]string{"travel.trip.read"},
	)
	if err != nil {
		return dependencyError("travel-service", "credentials", err)
	}
	travelHTTPClient := newObservedEgressClient(
		"assistant-service.travel-context",
		cfg.TravelService.TimeoutMs,
	)
	travelContextReader, err := domainreader.NewTravelClient(
		cfg.TravelService.BaseURL,
		travelHTTPClient,
		travelAuthorization,
	)
	if err != nil {
		return dependencyError("travel-service", "context-reader", err)
	}
	healthChecker.Register("travel_service", func(ctx context.Context) error {
		return checkServiceHealth(ctx, travelHTTPClient, cfg.TravelService.BaseURL)
	})
	connectorGrantScope, err := connectorgateway.RequiredScope()
	if err != nil {
		return dependencyError("integration-service", "operation-contract", err)
	}
	connectorGrantAuthorization, err := rtauth.NewHS256ServiceAuthorizationProvider(
		accessTokenConfig,
		"assistant-service",
		[]string{connectorGrantScope},
	)
	if err != nil {
		return dependencyError("integration-service", "credentials", err)
	}
	connectorGrantHTTPClient := newObservedEgressClient(
		"assistant-service.connector-capability-grant",
		cfg.IntegrationService.TimeoutMs,
	)
	connectorGrantGateway, err := connectorgateway.New(
		cfg.IntegrationService.BaseURL,
		connectorGrantHTTPClient,
		connectorGrantAuthorization,
	)
	if err != nil {
		return dependencyError("integration-service", "connector-capability-gateway", err)
	}
	healthChecker.Register("integration_service", func(ctx context.Context) error {
		return checkServiceHealth(
			ctx,
			connectorGrantHTTPClient,
			cfg.IntegrationService.BaseURL,
		)
	})
	var interestReader sessionports.ProactiveInterestReader
	if userProfileBase := strings.TrimSpace(cfg.UserProfile.BaseURL); userProfileBase != "" {
		interestReader = userprofile.NewClient(
			searchHTTPClient(cfg.UserProfile.TimeoutMs),
			userProfileBase,
		)
		log.Printf("assistant-service context interest resolver enabled base=%s", userProfileBase)
	} else {
		log.Printf("assistant-service context interest resolver disabled (no user_profile.base_url)")
	}
	agentLoop, err := buildAgentLoop(
		appEnv,
		canonicalSearch,
		cfg.Model,
		runtimeconfig.EnvRuntimeConfigProvider{},
		newObservedEgressClient,
		deps.publicWebEvidence,
		deps.publicWebBudget,
		deps.runRepository,
		deps.subscriptionStore,
		interestReader,
		deps.consentStore,
		travelContextReader,
		activeSkillCatalog,
		activeSkillPrompts,
	)
	if err != nil {
		return dependencyError("assistant-agent-loop", "initialization", err)
	}
	surfaceAuthorization, err := rtauth.NewHS256DelegatedPersonaAuthorizationProvider(
		accessTokenConfig,
		"assistant-service",
		[]string{"chat.member.list", "circle.members.self"},
	)
	if err != nil {
		return dependencyError("skill-surface-authority", "credentials", err)
	}
	if err := placementauthority.RequireEnvironmentBindings(appEnv); err != nil {
		return dependencyError("skill-surface-authority", "provider-binding", err)
	}
	surfaceChatHTTPClient := newObservedEgressClient(
		"assistant-service.skill-surface-chat-authority",
		cfg.ChatService.TimeoutMs,
	)
	surfaceCircleHTTPClient := newObservedEgressClient(
		"assistant-service.skill-surface-circle-authority",
		cfg.CircleService.TimeoutMs,
	)
	placementAuthority, err := placementauthority.NewClient(
		cfg.ChatService.BaseURL,
		cfg.CircleService.BaseURL,
		surfaceChatHTTPClient,
		surfaceCircleHTTPClient,
		surfaceAuthorization,
	)
	if err != nil {
		return dependencyError("skill-surface-authority", "initialization", err)
	}
	placementCommands := placementapplication.NewCommandFacade(
		deps.placementStore,
		placementAuthority,
		activeSkillCatalog,
		func() time.Time { return time.Now().UTC() },
	)
	placementQueries := placementapplication.NewQueryFacade(
		deps.placementStore,
		placementAuthority,
	)
	healthChecker.Register("circle_service", func(ctx context.Context) error {
		return checkServiceHealth(ctx, surfaceCircleHTTPClient, cfg.CircleService.BaseURL)
	})

	if deps.preferenceStore == nil || deps.preferenceReader == nil {
		return dependencyError(
			"mongodb.assistant_preferences",
			"wiring",
			errors.New("preference store and reader are required"),
		)
	}
	sessionOwnerReader, ok := deps.sessionStore.(preferencefact.SessionOwnerReader)
	if !ok {
		return dependencyError(
			"mongodb.assistant_sessions",
			"wiring",
			errors.New("session owner reader is required"),
		)
	}
	preferenceCommands := preferencefact.NewCommandFacade(
		deps.preferenceStore,
		sessionOwnerReader,
	)
	preferenceQueries := preferencefact.NewQueryFacade(deps.preferenceReader)
	policyReleaseService := policyreleaseapplication.NewService(
		deps.policyReleaseStore,
		nil,
	)
	policyRolloutService := policyrolloutapplication.NewService(
		deps.policyRolloutStore,
		policyReleaseService,
		nil,
	)
	frozenPolicyResolver := runruntime.PolicyResolverFunc(
		func(
			ctx context.Context,
			policyID string,
			personaID string,
			skillID string,
			domainID string,
		) (runruntime.FrozenPolicySelection, error) {
			resolved, resolveErr := policyRolloutService.ResolveFrozenSelection(
				ctx,
				policyID,
				personaID,
				skillID,
				domainID,
			)
			if resolveErr != nil {
				return runruntime.FrozenPolicySelection{}, resolveErr
			}
			return projectRunFrozenPolicySelection(resolved), nil
		},
	)
	durableExecutor := runruntime.NewManagedRunExecutor(
		orchestration.NewDurableRunExecutor(agentLoop),
	)
	runCancellation := runruntime.NewCancellationCoordinator(
		durableExecutor,
		10*time.Second,
	)
	consentQueries := consentapplication.NewQueryFacade(deps.consentStore)
	authorizeSkillAccess := func(
		ctx context.Context,
		accountID string,
		skillID string,
		surfaceKind string,
		surfaceID string,
	) error {
		accountID = strings.TrimSpace(accountID)
		skillID = strings.TrimSpace(skillID)
		surfaceKind = strings.TrimSpace(surfaceKind)
		surfaceID = strings.TrimSpace(surfaceID)
		if surfaceKind == "" {
			enabled, settingErr := settingQueries.IsEnabled(ctx, accountID, skillID)
			if settingErr != nil {
				return runruntime.ErrSkillSettingUnavailable
			}
			if !enabled {
				return runruntime.ErrSkillDisabled
			}
			consentErr := consentQueries.Require(ctx, accountID, skillID)
			switch {
			case errors.Is(consentErr, consentmodel.ErrConsentRequired):
				return runerrors.AppErrorFromSkillConsentRequired(
					"active consent is required for skill " + skillID,
				)
			case errors.Is(consentErr, consentmodel.ErrStorageUnavailable):
				return consenterrors.AppErrorFromConsentUnavailable(
					"skill consent reader is unavailable",
				)
			default:
				return consentErr
			}
		}
		if surfaceID == "" ||
			(surfaceKind != placementmodel.SurfaceConversation &&
				surfaceKind != placementmodel.SurfaceCircle) {
			return runruntime.ErrSkillDisabled
		}
		if sharedErr := activeSkillCatalog.ValidateSharedSkillIDs(
			ctx,
			surfaceKind,
			[]string{skillID},
		); sharedErr != nil {
			if errors.Is(sharedErr, skillcatalogmodel.ErrSkillNotShared) {
				return runruntime.ErrSkillDisabled
			}
			return runruntime.ErrSkillPackageUnavailable
		}
		allowed, placementErr := placementQueries.AllowsSkill(
			ctx,
			surfaceKind,
			surfaceID,
			skillID,
		)
		if placementErr != nil {
			if errors.Is(placementErr, placementmodel.ErrNotFound) {
				return runruntime.ErrSkillDisabled
			}
			return runruntime.ErrSkillSettingUnavailable
		}
		if !allowed {
			return runruntime.ErrSkillDisabled
		}
		return nil
	}
	agentLoop.SkillCandidates = orchestration.SkillCandidateAccessPolicyFunc(func(
		ctx context.Context,
		turn assistantdomain.AssistantTurn,
	) ([]string, error) {
		manifests, loadErr := activeSkillCatalog.Load(ctx)
		if loadErr != nil {
			return nil, runruntime.ErrSkillPackageUnavailable
		}
		surfaceKind := strings.TrimSpace(turn.RequestContext.SurfaceKind)
		surfaceID := strings.TrimSpace(turn.RequestContext.SurfaceID)
		allowed := make([]string, 0, len(manifests))
		if surfaceKind == "" {
			for _, manifest := range manifests {
				if !manifest.IsReactive() {
					continue
				}
				enabled, settingErr := settingQueries.IsEnabled(
					ctx,
					turn.UserID,
					manifest.SkillID,
				)
				if settingErr != nil {
					return nil, runruntime.ErrSkillSettingUnavailable
				}
				if enabled {
					allowed = append(allowed, manifest.SkillID)
				}
			}
			return allowed, nil
		}
		if surfaceID == "" ||
			(surfaceKind != placementmodel.SurfaceConversation &&
				surfaceKind != placementmodel.SurfaceCircle) {
			return []string{}, nil
		}
		placement, placementErr := placementQueries.Get(
			ctx,
			turn.UserID,
			turn.RequestContext.PersonaID,
			surfaceKind,
			surfaceID,
		)
		if placementErr != nil {
			if errors.Is(placementErr, placementmodel.ErrNotFound) ||
				errors.Is(placementErr, placementmodel.ErrForbidden) {
				return []string{}, nil
			}
			return nil, runruntime.ErrSkillSettingUnavailable
		}
		for _, manifest := range manifests {
			if !manifest.IsReactive() || !placement.Allows(manifest.SkillID) {
				continue
			}
			for _, allowedSurfaceKind := range manifest.ActivationProfile.AllowedSurfaceKinds {
				if strings.TrimSpace(allowedSurfaceKind) == surfaceKind {
					allowed = append(allowed, manifest.SkillID)
					break
				}
			}
		}
		return allowed, nil
	})
	agentLoop.SkillAccess = orchestration.SkillExecutionAccessPolicyFunc(func(
		ctx context.Context,
		turn assistantdomain.AssistantTurn,
		skillID string,
	) error {
		return authorizeSkillAccess(
			ctx,
			turn.UserID,
			skillID,
			turn.RequestContext.SurfaceKind,
			turn.RequestContext.SurfaceID,
		)
	})
	toolCapabilityPolicy := toolaccess.NewPolicy(
		deps.settingStore,
		deps.consentStore,
		connectorGrantGateway,
	)
	agentLoop.ToolAccess = orchestration.ToolExecutionAccessPolicyFunc(func(
		ctx context.Context,
		turn assistantdomain.AssistantTurn,
		skill orchestration.SkillSelection,
		toolName string,
		metadata toolpkg.Metadata,
	) error {
		requirement := metadata.Capability
		if strings.TrimSpace(requirement.CapabilityKey) == "" &&
			strings.TrimSpace(requirement.ConnectorRequirement) == "" &&
			len(requirement.ConsentScopes) == 0 &&
			len(requirement.AllowedSurfaceKinds) == 0 &&
			!requirement.RecheckAtExecution {
			return nil
		}
		decision, authorizeErr := toolCapabilityPolicy.Authorize(
			ctx,
			toolaccess.Request{
				AccountID:   turn.UserID,
				SkillID:     skill.SkillID,
				SurfaceKind: turn.RequestContext.SurfaceKind,
				Requirement: toolaccess.Requirement{
					CapabilityKey:        requirement.CapabilityKey,
					ConnectorRequirement: requirement.ConnectorRequirement,
					ConsentScopes:        requirement.ConsentScopes,
					AllowedSurfaceKinds:  requirement.AllowedSurfaceKinds,
					RecheckAtExecution:   requirement.RecheckAtExecution,
				},
			},
		)
		log.Printf(
			"assistant tool capability_decision turnId=%s skillId=%s toolName=%s capability=%s surface=%s allowed=%t reason=%s",
			turn.TurnID,
			skill.SkillID,
			strings.TrimSpace(toolName),
			strings.TrimSpace(requirement.CapabilityKey),
			decision.SurfaceKind,
			decision.Allowed,
			decision.Reason,
		)
		switch {
		case authorizeErr == nil:
			return nil
		case errors.Is(authorizeErr, toolaccess.ErrConsentRequired):
			return runerrors.AppErrorFromSkillConsentRequired(
				"tool capability consent is not active",
			)
		case errors.Is(authorizeErr, toolaccess.ErrConnectorRequired),
			errors.Is(authorizeErr, toolaccess.ErrSurfaceDenied):
			return runerrors.AppErrorFromConnectorCapabilityRequired(
				"required connector capability is not active for this surface",
			)
		default:
			return runerrors.AppErrorFromConnectorGatewayUnavailable(
				"connector capability policy could not be evaluated",
			)
		}
	})
	runCommands := runruntime.NewCommandService(
		deps.runRepository,
		runruntime.SessionAuthorizerFunc(func(
			ctx context.Context,
			userID string,
			sessionID string,
		) error {
			session, found, readErr := deps.sessionStore.GetSession(
				ctx,
				sessionID,
			)
			if readErr != nil {
				return readErr
			}
			if !found || session.UserID != strings.TrimSpace(userID) {
				return runruntime.ErrRunNotFound
			}
			return nil
		}),
		activeSkillCatalog,
		runruntime.StartAccessPolicyFunc(func(
			ctx context.Context,
			request runruntime.StartAccessRequest,
		) error {
			return authorizeSkillAccess(
				ctx,
				request.AccountID,
				request.SkillID,
				request.SurfaceKind,
				request.SurfaceID,
			)
		}),
		time.Now,
		runCancellation,
		frozenPolicyResolver,
	)
	pageContextFacade := pageapplication.NewFacade(
		pagepersistence.NewRedisStore(router.Scene("general")),
		func() time.Time { return time.Now().UTC() },
	)
	runContextResolver := runapplication.NewContextResolver(
		runapplication.CurrentPageContextReaderFunc(func(
			ctx context.Context,
			accountID string,
		) (map[string]any, bool, error) {
			current, readErr := pageContextFacade.Current(ctx, accountID)
			if readErr != nil || current == nil {
				return nil, false, readErr
			}
			objects := make([]any, 0, len(current.Snapshot.PageObjects))
			for _, object := range current.Snapshot.PageObjects {
				objects = append(objects, map[string]any{
					"objectTypeRef": object.ObjectTypeRef,
					"objectId":      object.ObjectID,
				})
			}
			actions := make([]any, 0, len(current.Snapshot.UserActions))
			for _, action := range current.Snapshot.UserActions {
				actions = append(actions, map[string]any{
					"action":        action.ActionType,
					"objectTypeRef": action.ObjectTypeRef,
					"objectId":      action.ObjectID,
				})
			}
			return map[string]any{
				"capturedAt":  current.CapturedAt.UTC(),
				"pageType":    current.Snapshot.PageType,
				"pageObjects": objects,
				"userActions": actions,
				"consentMatrix": map[string]any{
					"canReadCurrentPage": current.Snapshot.ConsentGranted,
				},
			}, true, nil
		}),
		runapplication.IntersectionEvidenceAuthorizerFunc(func(
			ctx context.Context,
			personaID string,
			references []runapplication.IntersectionEvidenceRef,
		) ([]runapplication.AuthorizedIntersectionEvidence, error) {
			requested := make([]assistantdomain.AssistantIntersectionEvidenceRef, 0, len(references))
			for _, reference := range references {
				requested = append(requested, assistantdomain.AssistantIntersectionEvidenceRef{
					IntersectionID: reference.IntersectionID,
					EvidenceID:     reference.EvidenceID,
					SourceRef:      reference.SourceRef,
					ObjectTypeRef:  reference.ObjectTypeRef,
					ObjectID:       reference.ObjectID,
				})
			}
			authorized, authorizeErr := intersectionInbox.ResolveAuthorizedIntersectionEvidence(
				ctx,
				personaID,
				requested,
			)
			if authorizeErr != nil {
				if errors.Is(authorizeErr, runapplication.ErrIntersectionEvidenceNotFound) {
					return nil, runapplication.ErrIntersectionEvidenceNotFound
				}
				return nil, authorizeErr
			}
			result := make([]runapplication.AuthorizedIntersectionEvidence, 0, len(authorized))
			for _, evidence := range authorized {
				result = append(result, runapplication.AuthorizedIntersectionEvidence{
					IntersectionID: evidence.IntersectionID,
					EvidenceID:     evidence.EvidenceID,
					SourceRef:      evidence.SourceRef,
					ObjectTypeRef:  evidence.ObjectTypeRef,
					ObjectID:       evidence.ObjectID,
					PrimaryText:    evidence.PrimaryText,
					Dimension:      evidence.Dimension,
					VerifiedAt:     evidence.VerifiedAt,
				})
			}
			return result, nil
		}),
	)
	assistantOpts := []orchestration.AssistantServiceOption{
		orchestration.WithLearningProjectionReader(deps.learningProjection),
		orchestration.WithNotificationAppMessageCommandWriter(notificationWriter),
		orchestration.WithSkillSubscriptionStore(deps.subscriptionStore),
		orchestration.WithAssistantDeliveryPolicyReader(deliveryPolicyReader),
		orchestration.WithSessionStore(deps.sessionStore),
		orchestration.WithPreferenceSnapshotReader(preferenceQueries),
		orchestration.WithIntersectionInboxReader(intersectionInbox),
		orchestration.WithAgentLoop(agentLoop),
		orchestration.WithRunCommandService(runCommands),
		orchestration.WithSkillCatalog(activeSkillCatalog),
	}
	chatBase := strings.TrimSpace(cfg.ChatService.BaseURL)
	if chatBase == "" {
		return dependencyError(
			"chat-service",
			"configuration",
			errors.New("chat_service.base_url is required"),
		)
	}
	chatHTTPClient := newObservedEgressClient(
		"assistant-service.chat-grounding",
		cfg.ChatService.TimeoutMs,
	)
	chatAuthorization, err := rtauth.NewHS256ServiceAuthorizationProvider(
		accessTokenConfig,
		"assistant-service",
		[]string{
			"chat.assistant_delivery_membership.read",
			"chat.assistant_grounding.read",
			"chat.assistant_delivery_message.send",
		},
	)
	if err != nil {
		return dependencyError("chat-service", "credentials", err)
	}
	chatGroundingClient, err := chatclient.NewClient(
		chatHTTPClient,
		chatBase,
		chatAuthorization,
	)
	if err != nil {
		return dependencyError("chat-service", "initialization", err)
	}
	assistantOpts = append(
		assistantOpts,
		orchestration.WithChatGroundingClient(
			chatGroundingClient,
		),
	)
	healthChecker.Register("chat_service", func(ctx context.Context) error {
		return checkServiceHealth(ctx, chatHTTPClient, chatBase)
	})
	log.Printf("assistant-service chat grounding client enabled base=%s", chatBase)
	learningFactService := learningapplication.NewService(
		deps.learningFactStore,
		deps.learningRunOwners,
		nil,
	)
	learningOpsQueries := learningapplication.NewOpsQueryService(
		deps.learningProjection,
	)
	service := orchestration.NewAssistantService(
		deps.consentStore,
		router.Scene("general"),
		assistantOpts...,
	)
	consentCommands := consentapplication.NewCommandFacade(
		deps.consentStore,
		func() time.Time { return time.Now().UTC() },
	)
	settingCommands := settingapplication.NewCommandFacade(
		deps.settingStore,
		activeSkillCatalog,
		func() time.Time { return time.Now().UTC() },
	)
	serviceCtx, serviceCancel := context.WithCancel(context.Background())
	defer serviceCancel()
	runTerminalLearningRelay := runruntime.NewTerminalLearningRelay(
		deps.runRepository,
		runruntime.ServiceScorecardAppenderFunc(func(
			ctx context.Context,
			command runruntime.ServiceScorecardCommand,
		) error {
			_, appendErr := learningFactService.AppendServiceFact(
				ctx,
				learningmodel.AppendCommand{
					EventID:          command.EventID,
					FactType:         learningmodel.FactTypeServiceScorecard,
					AssistantTurnID:  command.AssistantRunID,
					ReferralSource:   "service",
					DomainID:         command.DomainID,
					MetricID:         command.MetricID,
					MetricValue:      command.MetricValue,
					MetricSource:     command.MetricSource,
					TrainingEligible: false,
					OccurredAt:       command.OccurredAt,
				},
			)
			return appendErr
		}),
		instanceID+":assistant-run-terminal-learning",
		learningOutboxRelayInterval,
		128,
	)
	go runTerminalLearningRelay.Run(serviceCtx)
	log.Printf(
		"assistant-service run terminal learning relay enabled interval=%s",
		learningOutboxRelayInterval,
	)
	subscriptionScheduler, err := scheduling.NewSkillSubscriptionScheduler(
		service,
		skillSubscriptionCronInterval,
		slog.Default(),
	)
	if err != nil {
		return dependencyError(
			"skill-subscription-scheduler",
			"initialization",
			err,
		)
	}
	go subscriptionScheduler.Run(serviceCtx)
	log.Printf(
		"assistant-service skill subscription scheduler enabled interval=%s",
		skillSubscriptionCronInterval,
	)
	if deps.learningProjection == nil {
		return dependencyError(
			"mongodb.rm_assistant_learning_projection",
			"wiring",
			errors.New("assistant learning projection is required"),
		)
	}
	learningProjectionScheduler, err := learningprojection.NewScheduler(
		deps.learningProjection,
		learningProjectionInterval,
		256,
		slog.Default(),
	)
	if err != nil {
		return dependencyError(
			"assistant-learning-projection-scheduler",
			"initialization",
			err,
		)
	}
	if err := messageTransport.SetDurableRetention(
		serviceCtx,
		learningmessaging.LearningFactStream,
		learningmessaging.LearningFactStreamRetention,
	); err != nil {
		return dependencyError(
			"assistant-learning-fact-event-stream",
			"retention",
			err,
		)
	}
	healthChecker.Register(
		"assistant_learning_projection_scheduler",
		func(ctx context.Context) error {
			return learningProjectionScheduler.Healthy(
				ctx,
				3*learningProjectionInterval,
			)
		},
	)
	go learningProjectionScheduler.Run(serviceCtx)
	log.Printf(
		"assistant-service learning projection scheduler enabled interval=%s",
		learningProjectionInterval,
	)
	learningOutboxRelay, err := learningmessaging.NewOutboxRelay(
		deps.learningFactStore,
		messageTransport,
		learningOutboxRelayInterval,
		128,
		slog.Default(),
	)
	if err != nil {
		return dependencyError(
			"assistant-learning-fact-outbox-relay",
			"initialization",
			err,
		)
	}
	healthChecker.Register(
		"assistant_learning_fact_outbox_relay",
		func(ctx context.Context) error {
			return learningOutboxRelay.Healthy(
				ctx,
				3*learningOutboxRelayInterval,
			)
		},
	)
	go learningOutboxRelay.Run(serviceCtx)
	log.Printf(
		"assistant-service learning fact outbox relay enabled interval=%s",
		learningOutboxRelayInterval,
	)
	policyReleaseOutboxRelay, err := policymessaging.NewOutboxRelay(
		"release",
		deps.policyReleaseStore,
		messageTransport,
		learningOutboxRelayInterval,
		128,
		slog.Default(),
	)
	if err != nil {
		return dependencyError(
			"assistant-policy-release-outbox-relay",
			"initialization",
			err,
		)
	}
	policyRolloutOutboxRelay, err := policymessaging.NewOutboxRelay(
		"rollout",
		deps.policyRolloutStore,
		messageTransport,
		learningOutboxRelayInterval,
		128,
		slog.Default(),
	)
	if err != nil {
		return dependencyError(
			"assistant-policy-rollout-outbox-relay",
			"initialization",
			err,
		)
	}
	healthChecker.Register(
		"assistant_policy_release_outbox_relay",
		func(ctx context.Context) error {
			return policyReleaseOutboxRelay.Healthy(
				ctx,
				3*learningOutboxRelayInterval,
			)
		},
	)
	healthChecker.Register(
		"assistant_policy_rollout_outbox_relay",
		func(ctx context.Context) error {
			return policyRolloutOutboxRelay.Healthy(
				ctx,
				3*learningOutboxRelayInterval,
			)
		},
	)
	go policyReleaseOutboxRelay.Run(serviceCtx)
	go policyRolloutOutboxRelay.Run(serviceCtx)
	log.Printf(
		"assistant-service policy outbox relays enabled interval=%s",
		learningOutboxRelayInterval,
	)
	consumer := messaging.NewAssistantMentionedConsumerWithTransport(
		messageTransport,
		service,
		instanceID,
		slog.Default(),
	)
	go consumer.Run(serviceCtx, 500*time.Millisecond)
	log.Printf("assistant-service assistant mentioned consumer enabled stream=%s group=%s", messaging.AssistantMentionedStream, messaging.AssistantMentionedConsumerGroup)
	placementProjector := placementapplication.NewMembershipProjector(
		deps.placementStore,
		func() time.Time { return time.Now().UTC() },
	)
	placementConsumer := placementmessaging.NewAssistantMembershipConsumer(
		messageTransport,
		placementProjector,
		instanceID,
		slog.Default(),
	)
	go placementConsumer.Run(serviceCtx, 500*time.Millisecond)
	log.Printf(
		"assistant-service assistant membership consumer enabled stream=%s group=%s",
		placementmessaging.AssistantMembershipStream,
		placementmessaging.AssistantMembershipConsumerGroup,
	)
	runWorker := runruntime.NewDurableWorker(
		deps.runRepository,
		deps.runRepository,
		durableExecutor,
		instanceID,
	)
	go runWorker.Run(serviceCtx)
	log.Printf(
		"assistant-service durable AssistantRun worker enabled workerId=%s",
		instanceID,
	)
	baseHandler := httpadapter.NewHandler(
		service,
		httpadapter.WithRunCommandService(runCommands),
		httpadapter.WithRunPreferenceSnapshots(preferenceQueries),
		httpadapter.WithRunContextResolver(runContextResolver),
	).Routes()
	skillCatalogQueries := skillcatalogapplication.NewQueryService(activeSkillCatalog)
	serviceMux := http.NewServeMux()
	entryhttp.NewHandler(entryapplication.NewQueryFacade(
		deps.entryViewReader,
		pageContextFacade,
	)).RegisterRoutes(serviceMux)
	taskhttp.NewHandler(
		taskapplication.NewQueryFacade(deps.taskViewReader),
	).RegisterRoutes(serviceMux)
	pagehttp.NewHandler(pageContextFacade).RegisterRoutes(serviceMux)
	subscriptionhttp.NewHandler(
		subscriptionapplication.NewUseCases(
			deps.subscriptionStore,
			chatGroundingClient,
			service,
			time.Now,
		),
	).RegisterRoutes(serviceMux)
	preferencehttp.NewHandler(
		preferenceCommands,
		preferenceQueries,
	).RegisterRoutes(serviceMux)
	consenthttp.NewHandler(consentCommands, consentQueries).RegisterRoutes(serviceMux)
	settinghttp.NewHandler(settingCommands, settingQueries).RegisterRoutes(serviceMux)
	placementhttp.NewHandler(placementCommands, placementQueries).RegisterRoutes(serviceMux)
	policyreleasehttp.NewHandler(policyReleaseService).RegisterRoutes(serviceMux)
	policyrollouthttp.NewHandler(policyRolloutService).RegisterRoutes(serviceMux)
	skillpackagehttp.NewHandler(skillPackageService).RegisterRoutes(serviceMux)
	turnviewhttp.NewHandler(
		turnviewapplication.NewQueryFacade(
			deps.turnViewReader,
			deps.sessionStore,
			deps.turnViewProjector,
		),
	).RegisterRoutes(serviceMux)
	learninghttp.NewHandler(
		learningFactService,
		learningOpsQueries,
	).RegisterRoutes(serviceMux)
	skillcataloghttp.NewHandler(skillCatalogQueries).RegisterRoutes(serviceMux)
	serviceMux.Handle("/", baseHandler)
	baseHandler = serviceMux
	outerMux := http.NewServeMux()
	outerMux.HandleFunc("/healthz", healthChecker.Handler())
	outerMux.Handle("/metrics", rtmetrics.Handler())
	outerMux.Handle("/", httpadapter.GeneratedPrivilegedOperationHandler(baseHandler))
	observedHandler := rthttp.NewHTTPServerMiddleware(outerMux, rthttp.HTTPServerMiddlewareConfig{
		Service:           "assistant-service",
		ServiceName:       "assistant-service",
		ServiceInstanceID: instanceID,
		Origin:            "service.http",
		Direction:         robs.DirectionInbound,
		SourceID:          "assistant-service",
		Src:               "assistant-service",
		EndpointResolver:  httpadapter.GeneratedOperationPathTemplateResolver(),
	}, ioLogger, processLogger, exceptionLogger)
	corsHandler := rthttp.WithCORS(observedHandler, rthttp.CORSOptionsFromEnv())
	server := &http.Server{
		Addr: addr,
		Handler: rtauth.Middleware(rtauth.MiddlewareConfig{
			AccessTokenVerifier:      accessVerifier,
			AccountSecurityAuthority: accountSecurityAuthority,
		})(corsHandler),
		ReadHeaderTimeout: 5 * time.Second,
		WriteTimeout:      assistantHTTPWriteTimeout(),
		IdleTimeout:       60 * time.Second,
	}
	log.Printf("assistant-service listening on %s env=%s", addr, appEnv)
	if err := rthttp.ListenAndServeGraceful(server, assistantShutdownTimeout()); err != nil {
		return fmt.Errorf("listen failed: %w", err)
	}
	return nil
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
		return fmt.Errorf(
			"dependency health status=%d",
			response.StatusCode,
		)
	}
	return nil
}

func logStartupFailure(err error) {
	logger := slog.New(slog.NewJSONHandler(os.Stderr, nil))
	attributes := []any{
		"service", "assistant-service",
		"error", err.Error(),
	}
	var dependencyFailure *startupDependencyError
	if errors.As(err, &dependencyFailure) {
		attributes = append(
			attributes,
			"dependency", dependencyFailure.Dependency,
			"stage", dependencyFailure.Stage,
		)
	}
	logger.Error("assistant-service startup failed", attributes...)
}

func projectRunFrozenPolicySelection(
	selection policyrolloutapplication.FrozenSelection,
) runruntime.FrozenPolicySelection {
	return runruntime.FrozenPolicySelection{
		PolicyID:        selection.PolicyID,
		ReleaseDigest:   selection.ReleaseDigest,
		Cohort:          selection.Cohort,
		RolloutRevision: selection.RolloutRevision,
		RuleID:          selection.RuleID,
		Template: runruntime.FrozenPolicyTemplate{
			TemplateID:      selection.Template.TemplateID,
			SkillID:         selection.Template.SkillID,
			DomainID:        selection.Template.DomainID,
			PromptPolicy:    selection.Template.PromptPolicy,
			AllowedTools:    append([]string(nil), selection.Template.AllowedTools...),
			SearchIntensity: selection.Template.SearchIntensity,
		},
		LearningContextPolicy: runruntime.FrozenLearningContextPolicy{
			Enabled:                  selection.LearningContextPolicy.Enabled,
			AllowedSignals:           append([]string(nil), selection.LearningContextPolicy.AllowedSignals...),
			AllowedMetricIDs:         append([]string(nil), selection.LearningContextPolicy.AllowedMetricIDs...),
			AllowedReasonCodes:       append([]string(nil), selection.LearningContextPolicy.AllowedReasonCodes...),
			MinimumFeedbackSamples:   selection.LearningContextPolicy.MinimumFeedbackSamples,
			WindowDays:               selection.LearningContextPolicy.WindowDays,
			SnapshotTrainingEligible: selection.LearningContextPolicy.SnapshotTrainingEligible,
		},
	}
}
