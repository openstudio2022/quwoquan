package main

import (
	"context"
	"errors"
	"log"
	"log/slog"
	"net/http"
	"strings"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	rtgov "quwoquan_service/runtime/governance"
	rthttp "quwoquan_service/runtime/http"
	runports "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/ports"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/infrastructure/connectorgateway"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/infrastructure/domainreader"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/infrastructure/intersectionclient"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/infrastructure/searchclient"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/infrastructure/userprofile"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/orchestration"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/infrastructure/chatclient"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/infrastructure/notificationclient"
	readerports "quwoquan_service/services/assistant-service/internal/assistant/domain_reader_descriptor/domain/ports"
	skillcatalogactive "quwoquan_service/services/assistant-service/internal/assistant/skill_catalog/infrastructure/activerelease"
	placementapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_surface_placement/application"
	placementauthority "quwoquan_service/services/assistant-service/internal/assistant/skill_surface_placement/infrastructure/authority"
)

type observedEgressClientFactory func(sourceID string, timeoutMs int) *http.Client

func (runtime *assistantAPIRuntime) newObservedEgressClient(
	sourceID string,
	timeoutMs int,
) *http.Client {
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
			ServiceInstanceID: runtime.instanceID,
		},
		runtime.ioLogger,
		runtime.processLogger,
		runtime.exceptionLogger,
	)
	return rtgov.WrapClientWithCB(
		observed,
		rtgov.NewCircuitBreaker(5, 15*time.Second, slog.Default()),
	)
}

type assistantExternalClients struct {
	notificationWriter     *notificationclient.Client
	deliveryPolicyReader   *orchestration.UserDeliveryPolicyClient
	canonicalSearch        *searchclient.Client
	intersectionEvidence   runports.IntersectionEvidenceReader
	canonicalDomainReaders domainreader.CanonicalReaders
	connectorGrantGateway  *connectorgateway.Client
	interestReader         runports.ProactiveInterestReader
	egressClient           observedEgressClientFactory
}

func buildAssistantExternalClients(
	runtime *assistantAPIRuntime,
	infrastructure *assistantInfrastructure,
	descriptorCatalog readerports.Catalog,
) (*assistantExternalClients, error) {
	newObservedEgressClient := observedEgressClientFactory(runtime.newObservedEgressClient)
	notificationCredentials, err := rtauth.NewHS256ServiceAuthorizationProvider(
		runtime.accessTokenConfig,
		"assistant-service",
		[]string{"notification.app_message.create"},
	)
	if err != nil {
		return nil, dependencyError("notification-service", "credentials", err)
	}
	notificationHTTPConfig := rthttp.DefaultHTTPClientFactoryConfig()
	notificationHTTPConfig.Timeout = providerTimeout(
		runtime.config.NotificationService.TimeoutMs,
	)
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
			ServiceInstanceID: runtime.instanceID,
		},
		runtime.ioLogger,
		runtime.processLogger,
		runtime.exceptionLogger,
	)
	notificationWriter, err := notificationclient.NewClient(
		rtgov.WrapClientWithCB(
			notificationObservedClient,
			rtgov.NewCircuitBreaker(5, 15*time.Second, slog.Default()),
		),
		runtime.config.NotificationService.BaseURL,
		notificationCredentials,
	)
	if err != nil {
		return nil, dependencyError("notification-service", "initialization", err)
	}
	infrastructure.healthChecker.Register("notification_service", func(ctx context.Context) error {
		return checkServiceHealth(
			ctx,
			notificationObservedClient,
			runtime.config.NotificationService.BaseURL,
		)
	})

	deliveryPolicyAuthorization, err := rtauth.NewHS256ServiceAuthorizationProvider(
		runtime.accessTokenConfig,
		"assistant-service",
		[]string{"user.assistant_delivery_policy.read"},
	)
	if err != nil {
		return nil, dependencyError("user-service", "credentials", err)
	}
	deliveryPolicyHTTPClient := newObservedEgressClient(
		"assistant-service.user-delivery-policy",
		runtime.config.UserService.TimeoutMs,
	)
	deliveryPolicyReader, err := orchestration.NewUserDeliveryPolicyClient(
		runtime.config.UserService.BaseURL,
		deliveryPolicyAuthorization,
		deliveryPolicyHTTPClient,
	)
	if err != nil {
		return nil, dependencyError("user-service", "delivery-policy-reader", err)
	}
	infrastructure.healthChecker.Register("user_service", func(ctx context.Context) error {
		return checkServiceHealth(
			ctx,
			deliveryPolicyHTTPClient,
			runtime.config.UserService.BaseURL,
		)
	})
	canonicalSearch, err := searchclient.New(
		runtime.config.SearchService.BaseURL,
		newObservedEgressClient(
			"assistant-service.search-query",
			runtime.config.SearchService.TimeoutMs,
		),
	)
	if err != nil {
		return nil, dependencyError("search-service", "initialization", err)
	}
	intersectionEvidenceAuthorization, err := rtauth.NewHS256DelegatedPersonaAuthorizationProvider(
		runtime.accessTokenConfig,
		"assistant-service",
		[]string{"content.my_intersections.read"},
	)
	if err != nil {
		return nil, dependencyError("content-service", "credentials", err)
	}
	intersectionEvidence, err := intersectionclient.New(intersectionclient.Config{
		BaseURL: runtime.config.ContentService.BaseURL,
		HTTPClient: newObservedEgressClient(
			"assistant-service.content-intersections",
			runtime.config.ContentService.TimeoutMs,
		),
		Authorization: intersectionEvidenceAuthorization,
	})
	if err != nil {
		return nil, dependencyError("content-service", "intersection-reader", err)
	}
	canonicalDomainTransports := map[string]domainreader.ReaderTransport{
		"circle-service": {
			BaseURL: runtime.config.CircleService.BaseURL,
			HTTPClient: newObservedEgressClient(
				"assistant-service.circle-context",
				runtime.config.CircleService.TimeoutMs,
			),
		},
		"content-service": {
			BaseURL: runtime.config.ContentService.BaseURL,
			HTTPClient: newObservedEgressClient(
				"assistant-service.content-context",
				runtime.config.ContentService.TimeoutMs,
			),
		},
		"entity-service": {
			BaseURL: runtime.config.EntityService.BaseURL,
			HTTPClient: newObservedEgressClient(
				"assistant-service.entity-context",
				runtime.config.EntityService.TimeoutMs,
			),
		},
	}
	canonicalDomainReaders, err := domainreader.NewCanonicalReaders(
		domainreader.CanonicalReadersConfig{
			Descriptors:       descriptorCatalog,
			Definitions:       domainreader.ProductionReaderDefinitions(),
			ServiceTransports: canonicalDomainTransports,
		},
	)
	if err != nil {
		return nil, dependencyError("assistant-domain-reader", "canonical-readers", err)
	}
	for _, ownerService := range canonicalDomainReaders.OwnerServices() {
		ownerService := ownerService
		transport := canonicalDomainTransports[ownerService]
		healthName := strings.ReplaceAll(
			strings.TrimSuffix(ownerService, "-service"),
			"-",
			"_",
		) + "_context_reader"
		infrastructure.healthChecker.Register(healthName, func(ctx context.Context) error {
			return checkServiceHealth(
				ctx,
				transport.HTTPClient,
				transport.BaseURL,
			)
		})
	}
	connectorGrantScope, err := connectorgateway.RequiredScope()
	if err != nil {
		return nil, dependencyError("integration-service", "operation-contract", err)
	}
	connectorGrantAuthorization, err := rtauth.NewHS256ServiceAccountAuthorizationProvider(
		runtime.accessTokenConfig,
		"assistant-service",
		[]string{connectorGrantScope},
	)
	if err != nil {
		return nil, dependencyError("integration-service", "credentials", err)
	}
	connectorGrantHTTPClient := newObservedEgressClient(
		"assistant-service.connector-capability-grant",
		runtime.config.IntegrationService.TimeoutMs,
	)
	connectorGrantGateway, err := connectorgateway.New(
		runtime.config.IntegrationService.BaseURL,
		connectorGrantHTTPClient,
		connectorGrantAuthorization,
	)
	if err != nil {
		return nil, dependencyError(
			"integration-service",
			"connector-capability-gateway",
			err,
		)
	}
	infrastructure.healthChecker.Register("integration_service", func(ctx context.Context) error {
		return checkServiceHealth(
			ctx,
			connectorGrantHTTPClient,
			runtime.config.IntegrationService.BaseURL,
		)
	})
	var interestReader runports.ProactiveInterestReader
	if userProfileBase := strings.TrimSpace(runtime.config.UserProfile.BaseURL); userProfileBase != "" {
		interestReader = userprofile.NewClient(
			searchHTTPClient(runtime.config.UserProfile.TimeoutMs),
			userProfileBase,
		)
		log.Printf("assistant-service context interest resolver enabled base=%s", userProfileBase)
	} else {
		log.Printf("assistant-service context interest resolver disabled (no user_profile.base_url)")
	}
	return &assistantExternalClients{
		notificationWriter:     notificationWriter,
		deliveryPolicyReader:   deliveryPolicyReader,
		canonicalSearch:        canonicalSearch,
		intersectionEvidence:   intersectionEvidence,
		canonicalDomainReaders: canonicalDomainReaders,
		connectorGrantGateway:  connectorGrantGateway,
		interestReader:         interestReader,
		egressClient:           newObservedEgressClient,
	}, nil
}

type assistantPlacementComponents struct {
	commands *placementapplication.CommandFacade
	queries  *placementapplication.QueryFacade
}

func wireAssistantSurfacePlacement(
	runtime *assistantAPIRuntime,
	infrastructure *assistantInfrastructure,
	activeSkillCatalog *skillcatalogactive.CatalogSource,
	egressClient observedEgressClientFactory,
) (*assistantPlacementComponents, error) {
	surfaceAuthorization, err := rtauth.NewHS256DelegatedPersonaAuthorizationProvider(
		runtime.accessTokenConfig,
		"assistant-service",
		[]string{"chat.member.list", "circle.members.self"},
	)
	if err != nil {
		return nil, dependencyError("skill-surface-authority", "credentials", err)
	}
	if err := placementauthority.RequireEnvironmentBindings(runtime.appEnv); err != nil {
		return nil, dependencyError("skill-surface-authority", "provider-binding", err)
	}
	surfaceChatHTTPClient := egressClient(
		"assistant-service.skill-surface-chat-authority",
		runtime.config.ChatService.TimeoutMs,
	)
	surfaceCircleHTTPClient := egressClient(
		"assistant-service.skill-surface-circle-authority",
		runtime.config.CircleService.TimeoutMs,
	)
	placementAuthority, err := placementauthority.NewClient(
		runtime.config.ChatService.BaseURL,
		runtime.config.CircleService.BaseURL,
		surfaceChatHTTPClient,
		surfaceCircleHTTPClient,
		surfaceAuthorization,
	)
	if err != nil {
		return nil, dependencyError("skill-surface-authority", "initialization", err)
	}
	infrastructure.healthChecker.Register("circle_service", func(ctx context.Context) error {
		return checkServiceHealth(
			ctx,
			surfaceCircleHTTPClient,
			runtime.config.CircleService.BaseURL,
		)
	})
	return &assistantPlacementComponents{
		commands: placementapplication.NewCommandFacade(
			infrastructure.dependencies.placementStore,
			placementAuthority,
			activeSkillCatalog,
			func() time.Time { return time.Now().UTC() },
		),
		queries: placementapplication.NewQueryFacade(
			infrastructure.dependencies.placementStore,
			placementAuthority,
		),
	}, nil
}

func buildAssistantChatGroundingClient(
	runtime *assistantAPIRuntime,
	infrastructure *assistantInfrastructure,
	egressClient observedEgressClientFactory,
) (*chatclient.Client, error) {
	chatBase := strings.TrimSpace(runtime.config.ChatService.BaseURL)
	if chatBase == "" {
		return nil, dependencyError(
			"chat-service",
			"configuration",
			errors.New("chat_service.base_url is required"),
		)
	}
	chatHTTPClient := egressClient(
		"assistant-service.chat-grounding",
		runtime.config.ChatService.TimeoutMs,
	)
	chatAuthorization, err := rtauth.NewHS256ServiceAuthorizationProvider(
		runtime.accessTokenConfig,
		"assistant-service",
		[]string{
			"chat.assistant_delivery_membership.read",
			"chat.assistant_grounding.read",
			"chat.assistant_delivery_message.send",
		},
	)
	if err != nil {
		return nil, dependencyError("chat-service", "credentials", err)
	}
	chatGroundingClient, err := chatclient.NewClient(
		chatHTTPClient,
		chatBase,
		chatAuthorization,
	)
	if err != nil {
		return nil, dependencyError("chat-service", "initialization", err)
	}
	infrastructure.healthChecker.Register("chat_service", func(ctx context.Context) error {
		return checkServiceHealth(ctx, chatHTTPClient, chatBase)
	})
	log.Printf("assistant-service chat grounding client enabled base=%s", chatBase)
	return chatGroundingClient, nil
}
