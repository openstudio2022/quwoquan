package main

import (
	"context"
	"fmt"
	"net/http"
	"strings"

	runtimeconfig "quwoquan_service/runtime/config"
	publicwebtool "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/adapters/outbound/tool"
	skillcontextapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/skillcontext"
	publicwebpersistence "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/infrastructure/publicweb"
	skillcontextinfra "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/infrastructure/skillcontext"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/orchestration"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/tool"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/ports"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/infrastructure/assets"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/infrastructure/finance"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/infrastructure/modelprovider"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/infrastructure/providerbinding"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/infrastructure/publicsearch"
	serviceruntimeconfig "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/infrastructure/runtimeconfig"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/infrastructure/searchclient"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/infrastructure/weather"
	consentports "quwoquan_service/services/assistant-service/internal/assistant/skill_consent/domain/ports"
)

func buildAgentLoop(
	appEnv string,
	internalSearch *searchclient.Client,
	modelConfig serviceruntimeconfig.ModelConfig,
	configProvider runtimeconfig.RuntimeConfigProvider,
	newEgressClient func(sourceID string, timeoutMs int) *http.Client,
	publicWebEvidence *publicwebpersistence.MongoEvidenceStore,
	publicWebBudget *publicwebpersistence.MongoRunBudgetGate,
	runs ports.SessionRunStore,
	subscriptions ports.SkillSubscriptionStore,
	interests ports.ProactiveInterestReader,
	consents consentports.Reader,
) (*orchestration.AgentLoop, error) {
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
	)
	if err != nil {
		return nil, fmt.Errorf("search provider binding invalid: %w", err)
	}
	promptAssets, err := assets.NewDefaultPromptAssetLoader()
	if err != nil {
		return nil, fmt.Errorf("prompt asset loader unavailable: %w", err)
	}
	loop := orchestration.NewAgentLoop(orchestration.ModelDrivenSkillRuntime{
		Model: model,
	}, orchestration.ReactRuntime{
		Model: model,
		Tools: orchestration.DefaultToolCoordinator{
			Registry: registry,
		},
	}, nil)
	loop.PromptAssets = promptAssets
	loop.Subagents = orchestration.ModelSubagentPlanner{Model: model}
	contextResolvers, err := skillcontextinfra.NewRuntimeRegistry(
		runs,
		subscriptions,
		interests,
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
					granted[strings.TrimSpace(consent.GrantedScope)] = struct{}{}
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
	apiKey, ok := binding.Secret("ASSISTANT_MODEL_API_KEY")
	if !ok {
		return nil, fmt.Errorf("model binding has no API key material")
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
) (tool.Registry, error) {
	registry := tool.BaseRegistry()
	if internalSearch == nil {
		return tool.Registry{}, fmt.Errorf("canonical search client is required")
	}
	public := buildPublicSearchProvider(appEnv, configProvider, newEgressClient)
	weatherProvider := buildWeatherProvider(appEnv, configProvider, newEgressClient)
	financeProvider := buildFinanceProvider(appEnv, configProvider, newEgressClient)
	handlers := map[string]tool.Handler{
		"app_search": internalSearch.Handler(),
		"web_search": orchestration.NewExternalWebSearchHandler(public, weatherProvider, financeProvider),
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
	handlers["web_search"] = publicwebtool.SearchHandler(
		handlers["web_search"],
		publicWebEvidence,
	)
	if err := tool.RegisterCanonical(&registry, handlers); err != nil {
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
	geocodingURL, geocodingOK := binding.Endpoint("geocoding")
	forecastURL, forecastOK := binding.Endpoint("forecast")
	if !geocodingOK || !forecastOK {
		return providerbinding.UnavailableSearchProvider{Capability: "weather"}
	}
	provider, err := weather.New(
		weather.Config{
			GeocodingURL: geocodingURL,
			ForecastURL:  forecastURL,
		},
		newEgressClient(binding.AdapterID, int(binding.Timeout.Milliseconds())),
	)
	if err != nil {
		return providerbinding.UnavailableSearchProvider{Capability: "weather"}
	}
	return provider
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
