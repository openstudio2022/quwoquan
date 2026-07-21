package main

import (
	"fmt"
	"net/http"

	runtimeconfig "quwoquan_service/runtime/config"
	"quwoquan_service/services/assistant-service/internal/application"
	"quwoquan_service/services/assistant-service/internal/application/tool"
	"quwoquan_service/services/assistant-service/internal/infrastructure/finance"
	"quwoquan_service/services/assistant-service/internal/infrastructure/modelprovider"
	"quwoquan_service/services/assistant-service/internal/infrastructure/providerbinding"
	"quwoquan_service/services/assistant-service/internal/infrastructure/publicsearch"
	"quwoquan_service/services/assistant-service/internal/infrastructure/searchclient"
	"quwoquan_service/services/assistant-service/internal/infrastructure/weather"
)

func buildAgentLoop(
	appEnv string,
	internalSearch *searchclient.Client,
	configProvider runtimeconfig.RuntimeConfigProvider,
	newEgressClient func(sourceID string, timeoutMs int) *http.Client,
) (*application.AgentLoop, error) {
	model, err := buildModelProvider(
		appEnv,
		configProvider,
		newEgressClient,
	)
	if err != nil {
		return nil, fmt.Errorf("model provider binding invalid: %w", err)
	}
	registry, err := buildSearchRegistry(
		internalSearch,
		appEnv,
		configProvider,
		newEgressClient,
	)
	if err != nil {
		return nil, fmt.Errorf("search provider binding invalid: %w", err)
	}
	return application.NewAgentLoop(application.ModelDrivenSkillRuntime{
		Model: model,
	}, application.ReactRuntime{
		Model: model,
		Tools: application.DefaultToolCoordinator{
			Registry: registry,
		},
	}, nil), nil
}

func buildModelProvider(
	appEnv string,
	configProvider runtimeconfig.RuntimeConfigProvider,
	newEgressClient func(sourceID string, timeoutMs int) *http.Client,
) (application.ModelProvider, error) {
	binding, err := resolveAssistantBinding(
		appEnv,
		"assistant.model.generation",
		"ext.llm.xiaomi_mimo",
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
		},
		newEgressClient(binding.AdapterID, int(binding.Timeout.Milliseconds())),
	)
	if err != nil {
		return nil, err
	}
	return application.ProviderBackedModelProvider{Backend: backend}, nil
}

func buildSearchRegistry(
	internalSearch *searchclient.Client,
	appEnv string,
	configProvider runtimeconfig.RuntimeConfigProvider,
	newEgressClient func(sourceID string, timeoutMs int) *http.Client,
) (tool.Registry, error) {
	registry := tool.BaseRegistry()
	if internalSearch == nil {
		return tool.Registry{}, fmt.Errorf("canonical search client is required")
	}
	registry.Register(tool.AppSearchMetadata(), internalSearch.Handler())

	public := buildPublicSearchProvider(appEnv, configProvider, newEgressClient)
	weatherProvider := buildWeatherProvider(appEnv, configProvider, newEgressClient)
	financeProvider := buildFinanceProvider(appEnv, configProvider, newEgressClient)
	registry.Register(
		tool.WebSearchMetadata(),
		application.NewExternalWebSearchHandler(public, weatherProvider, financeProvider),
	)
	return registry, nil
}

func buildPublicSearchProvider(
	appEnv string,
	configProvider runtimeconfig.RuntimeConfigProvider,
	newEgressClient func(sourceID string, timeoutMs int) *http.Client,
) application.PublicSearchProvider {
	binding, err := resolveAssistantBinding(
		appEnv,
		"assistant.public.search",
		"ext.search.duckduckgo_html",
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
) application.WeatherProvider {
	binding, err := resolveAssistantBinding(
		appEnv,
		"assistant.weather.forecast",
		"ext.weather.open_meteo",
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
) application.FinanceProvider {
	binding, err := resolveAssistantBinding(
		appEnv,
		"assistant.finance.quote",
		"ext.finance.yahoo_chart",
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
	expectedAdapterID string,
	configProvider runtimeconfig.RuntimeConfigProvider,
) (providerbinding.ResolvedBinding, error) {
	binding, err := providerbinding.Resolve(appEnv, capabilityID, configProvider)
	if err != nil {
		return providerbinding.ResolvedBinding{}, err
	}
	if binding.AdapterID != expectedAdapterID {
		return providerbinding.ResolvedBinding{}, fmt.Errorf(
			"provider binding adapter mismatch for capability=%s",
			capabilityID,
		)
	}
	return binding, nil
}
