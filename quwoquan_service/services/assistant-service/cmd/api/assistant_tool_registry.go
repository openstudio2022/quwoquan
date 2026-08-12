package main

import (
	"context"
	"fmt"
	"net/http"
	"os"
	"strings"
	"time"

	runtimeconfig "quwoquan_service/runtime/config"
	publicwebtool "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/adapters/outbound/tool"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/orchestration"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	skillcontextapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/skillcontext"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/tool"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/ports"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/infrastructure/domainreader"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/infrastructure/finance"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/infrastructure/modelprovider"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/infrastructure/providerbinding"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/infrastructure/publicsearch"
	publicwebpersistence "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/infrastructure/publicweb"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/infrastructure/searchclient"
	skillcontextinfra "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/infrastructure/skillcontext"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/infrastructure/weather"
	serviceruntimeconfig "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/infrastructure/runtimeconfig"
	readerports "quwoquan_service/services/assistant-service/internal/assistant/domain_reader_descriptor/domain/ports"
	consentports "quwoquan_service/services/assistant-service/internal/assistant/skill_consent/domain/ports"
	skillpkg "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/application/packageasset"
	subscriptionports "quwoquan_service/services/assistant-service/internal/assistant/skill_subscription/domain/ports"
)

const (
	assistantDurableSubtaskLeaseTTL          = 15 * time.Second
	assistantDurableSubtaskHeartbeatInterval = 3 * time.Second
)

func buildAgentLoop(
	appEnv string,
	internalSearch *searchclient.Client,
	modelConfig serviceruntimeconfig.ModelConfig,
	configProvider runtimeconfig.RuntimeConfigProvider,
	newEgressClient func(sourceID string, timeoutMs int) *http.Client,
	publicWebEvidence *publicwebpersistence.MongoEvidenceStore,
	publicWebBudget *publicwebpersistence.MongoRunBudgetGate,
	runs runruntime.Repository,
	workerID string,
	subscriptions subscriptionports.Store,
	interests ports.ProactiveInterestReader,
	consents consentports.Reader,
	canonicalDomainReaders domainreader.CanonicalReaders,
	descriptorCatalog readerports.Catalog,
	skillCatalog skillpkg.Loader,
	promptAssets ports.PromptAssetResolver,
	gatheringHandlers map[string]tool.Handler,
) (*orchestration.AgentLoop, error) {
	if runs == nil {
		return nil, fmt.Errorf("assistant run repository is required")
	}
	workerID = strings.TrimSpace(workerID)
	if workerID == "" {
		return nil, fmt.Errorf("assistant durable subtask worker ID is required")
	}
	model, err := buildModelProvider(
		appEnv,
		modelConfig,
		configProvider,
		newEgressClient,
	)
	if err != nil {
		return nil, fmt.Errorf("model provider binding invalid: %w", err)
	}
	registry, err := buildToolRegistry(
		internalSearch,
		appEnv,
		configProvider,
		newEgressClient,
		publicWebEvidence,
		publicWebBudget,
		gatheringHandlers,
	)
	if err != nil {
		return nil, fmt.Errorf("search provider binding invalid: %w", err)
	}
	if promptAssets == nil {
		return nil, fmt.Errorf("frozen Skill package prompt resolver is required")
	}
	loop := orchestration.NewAgentLoop(orchestration.ModelDrivenSkillRuntime{
		Model:  model,
		Loader: skillCatalog,
	}, orchestration.ReactRuntime{
		Model: model,
		Tools: orchestration.DefaultToolCoordinator{
			Registry:               registry,
			RuntimeCandidateDigest: strings.TrimSpace(os.Getenv("QWQ_RELEASE_CANDIDATE_DIGEST")),
		},
	}, nil)
	loop.DurableSubtasks = orchestration.NewDurableSubtaskCoordinator(
		orchestration.NewRepositoryDurableSubtaskStore(runs, nil),
		workerID,
		assistantDurableSubtaskLeaseTTL,
		assistantDurableSubtaskHeartbeatInterval,
	)
	loop.Catalog = skillCatalog
	loop.PromptAssets = promptAssets
	loop.Subagents = orchestration.ModelSubagentPlanner{Model: model, Loader: skillCatalog}
	if descriptorCatalog == nil {
		return nil, fmt.Errorf("domain reader descriptor catalog is required")
	}
	contextResolvers, err := skillcontextinfra.NewRuntimeRegistryWithCanonicalReaders(
		descriptorCatalog,
		runs,
		subscriptions,
		interests,
		canonicalDomainReaders,
	)
	if err != nil {
		return nil, fmt.Errorf("skill context resolver registry unavailable: %w", err)
	}
	loop.SkillContexts = skillcontextapplication.NewAssembler(
		contextResolvers,
		skillcontextapplication.ConsentReaderFunc(func(
			ctx context.Context,
			ownerID string,
			skillID string,
			requiredScopes []string,
		) (bool, error) {
			if consents == nil {
				return false, skillcontextapplication.ErrConsentUnavailable
			}
			active, readErr := consents.ListActiveConsents(ctx, ownerID)
			if readErr != nil {
				return false, readErr
			}
			granted := map[string]struct{}{}
			for _, consent := range active {
				if consent.SkillID == skillID && consent.IsGranted() {
					for _, rawScope := range consent.GrantedScopes {
						scope := strings.TrimSpace(rawScope)
						if scope != "" {
							granted[scope] = struct{}{}
						}
					}
				}
			}
			for _, scope := range requiredScopes {
				if _, ok := granted[strings.TrimSpace(scope)]; !ok {
					return false, nil
				}
			}
			return true, nil
		}),
	)
	return loop, nil
}

func buildModelProvider(
	appEnv string,
	modelConfig serviceruntimeconfig.ModelConfig,
	configProvider runtimeconfig.RuntimeConfigProvider,
	newEgressClient func(sourceID string, timeoutMs int) *http.Client,
) (orchestration.ModelProvider, error) {
	binding, err := resolveAssistantBinding(
		appEnv,
		"assistant.model.generation",
		providerbinding.ModelAdapterIDs(),
		configProvider,
	)
	if err != nil {
		return nil, err
	}
	completionURL, ok := binding.Endpoint("completion")
	if !ok {
		return nil, fmt.Errorf("model binding has no completion endpoint")
	}
	apiKey := ""
	if binding.AdapterID == providerbinding.ModelAdapterProtocolFixture {
		apiKey = "nonprod-protocol-substitute"
	} else {
		var ok bool
		apiKey, ok = binding.Secret("ASSISTANT_MODEL_API_KEY")
		if !ok {
			return nil, fmt.Errorf("model binding has no API key material")
		}
	}
	backend, err := modelprovider.New(
		modelprovider.Config{
			CompletionURL: completionURL,
			APIKey:        apiKey,
			Models: modelprovider.TierModels{
				Fast:      modelConfig.Tier.Fast,
				Balanced:  modelConfig.Tier.Balanced,
				Reasoning: modelConfig.Tier.Reasoning,
			},
			NativeToolCalling: modelConfig.NativeToolCalling,
		},
		newEgressClient(binding.AdapterID, int(binding.Timeout.Milliseconds())),
	)
	if err != nil {
		return nil, err
	}
	return orchestration.ProviderBackedModelProvider{
		Backend: orchestration.TierDegradingModelProvider{Backend: backend},
	}, nil
}

func buildToolRegistry(
	internalSearch *searchclient.Client,
	appEnv string,
	configProvider runtimeconfig.RuntimeConfigProvider,
	newEgressClient func(sourceID string, timeoutMs int) *http.Client,
	publicWebEvidence *publicwebpersistence.MongoEvidenceStore,
	publicWebBudget *publicwebpersistence.MongoRunBudgetGate,
	gatheringHandlers map[string]tool.Handler,
) (tool.Registry, error) {
	registry := tool.BaseRegistry()
	if internalSearch == nil {
		return tool.Registry{}, fmt.Errorf("canonical search client is required")
	}
	public := buildPublicSearchProvider(appEnv, configProvider, newEgressClient)
	weatherProvider := buildWeatherProvider(appEnv, configProvider, newEgressClient)
	financeProvider := buildFinanceProvider(appEnv, configProvider, newEgressClient)
	handlers := map[string]tool.Handler{
		"app_search":     internalSearch.Handler(),
		"web_search":     orchestration.NewPublicWebSearchHandler(public),
		"weather_lookup": orchestration.NewWeatherLookupHandler(weatherProvider),
		"finance_quote":  orchestration.NewFinanceQuoteHandler(financeProvider),
	}
	publicWebHandlers, err := buildPublicWebToolHandlers(
		publicWebEvidence,
		publicWebBudget,
	)
	if err != nil {
		return tool.Registry{}, err
	}
	for name, handler := range publicWebHandlers {
		handlers[name] = handler
	}
	for _, toolName := range []string{
		"web_search",
		"weather_lookup",
		"finance_quote",
	} {
		handlers[toolName] = publicwebtool.SearchHandler(
			handlers[toolName],
			publicWebEvidence,
		)
	}
	for name, handler := range gatheringHandlers {
		if _, duplicated := handlers[name]; duplicated {
			return tool.Registry{}, fmt.Errorf(
				"tool handler %q is registered more than once",
				name,
			)
		}
		handlers[name] = handler
	}
	if err := tool.RegisterCanonical(
		&registry,
		handlers,
		canonicalToolUnavailability(appEnv, configProvider),
	); err != nil {
		return tool.Registry{}, err
	}
	return registry, nil
}

func buildPublicSearchProvider(
	appEnv string,
	configProvider runtimeconfig.RuntimeConfigProvider,
	newEgressClient func(sourceID string, timeoutMs int) *http.Client,
) ports.PublicSearchProvider {
	binding, err := resolveAssistantBinding(
		appEnv,
		"assistant.public.search",
		[]string{
			providerbinding.SearchAdapterDuckDuckGoHTML,
			providerbinding.SearchAdapterProtocolFixture,
		},
		configProvider,
	)
	if err != nil {
		return providerbinding.UnavailableSearchProvider{Capability: "public_search"}
	}
	searchURL, ok := binding.Endpoint("search")
	if !ok {
		return providerbinding.UnavailableSearchProvider{Capability: "public_search"}
	}
	provider, err := publicsearch.New(
		publicsearch.Config{SearchURL: searchURL},
		newEgressClient(binding.AdapterID, int(binding.Timeout.Milliseconds())),
	)
	if err != nil {
		return providerbinding.UnavailableSearchProvider{Capability: "public_search"}
	}
	return provider
}

func buildWeatherProvider(
	appEnv string,
	configProvider runtimeconfig.RuntimeConfigProvider,
	newEgressClient func(sourceID string, timeoutMs int) *http.Client,
) ports.WeatherProvider {
	binding, err := resolveAssistantBinding(
		appEnv,
		"assistant.weather.forecast",
		[]string{
			providerbinding.WeatherAdapterOpenMeteo,
			providerbinding.WeatherAdapterProtocolFixture,
		},
		configProvider,
	)
	if err != nil {
		return providerbinding.UnavailableSearchProvider{Capability: "weather"}
	}
	config, err := weatherProviderConfig(binding)
	if err != nil {
		return providerbinding.UnavailableSearchProvider{Capability: "weather"}
	}
	provider, err := weather.New(
		config,
		newEgressClient(binding.AdapterID, int(binding.Timeout.Milliseconds())),
	)
	if err != nil {
		return providerbinding.UnavailableSearchProvider{Capability: "weather"}
	}
	return provider
}

func weatherProviderConfig(
	binding providerbinding.ResolvedBinding,
) (weather.Config, error) {
	geocodingURL, geocodingOK := binding.Endpoint("geocoding")
	forecastURL, forecastOK := binding.Endpoint("forecast")
	if !geocodingOK || !forecastOK {
		return weather.Config{}, fmt.Errorf(
			"weather binding has no geocoding or forecast endpoint",
		)
	}
	resilience := tool.WeatherLookupMetadata().Resilience
	config := weather.Config{
		GeocodingURL: geocodingURL,
		ForecastURL:  forecastURL,
		AllowInsecure: binding.AdapterID ==
			providerbinding.WeatherAdapterProtocolFixture,
		MaxAttempts: resilience.MaxAttempts,
		RetryBackoff: time.Duration(resilience.RetryBackoffMs) *
			time.Millisecond,
	}
	if _, err := weather.New(config, &http.Client{}); err != nil {
		return weather.Config{}, err
	}
	return config, nil
}

func buildFinanceProvider(
	appEnv string,
	configProvider runtimeconfig.RuntimeConfigProvider,
	newEgressClient func(sourceID string, timeoutMs int) *http.Client,
) ports.FinanceProvider {
	binding, err := resolveAssistantBinding(
		appEnv,
		"assistant.finance.quote",
		[]string{
			providerbinding.FinanceAdapterYahooChart,
			providerbinding.FinanceAdapterProtocolFixture,
		},
		configProvider,
	)
	if err != nil {
		return providerbinding.UnavailableSearchProvider{Capability: "finance"}
	}
	chartURL, ok := binding.Endpoint("chart")
	if !ok {
		return providerbinding.UnavailableSearchProvider{Capability: "finance"}
	}
	provider, err := finance.New(
		finance.Config{ChartURL: chartURL},
		newEgressClient(binding.AdapterID, int(binding.Timeout.Milliseconds())),
	)
	if err != nil {
		return providerbinding.UnavailableSearchProvider{Capability: "finance"}
	}
	return provider
}

func resolveAssistantBinding(
	appEnv string,
	capabilityID string,
	allowedAdapterIDs []string,
	configProvider runtimeconfig.RuntimeConfigProvider,
) (providerbinding.ResolvedBinding, error) {
	binding, err := providerbinding.Resolve(appEnv, capabilityID, configProvider)
	if err != nil {
		return providerbinding.ResolvedBinding{}, err
	}
	for _, allowed := range allowedAdapterIDs {
		if binding.AdapterID == allowed {
			return binding, nil
		}
	}
	return providerbinding.ResolvedBinding{}, fmt.Errorf(
		"provider binding adapter mismatch for capability=%s",
		capabilityID,
	)
}
