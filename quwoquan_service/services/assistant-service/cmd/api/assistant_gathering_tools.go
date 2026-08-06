package main

import (
	"fmt"
	"strings"

	"quwoquan_service/generated/operationsecurity"
	rtauth "quwoquan_service/runtime/auth"
	runtimeconfig "quwoquan_service/runtime/config"
	assistantgenerated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/tool"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/tooling"
	gatheringinfrastructure "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/infrastructure/gathering"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/infrastructure/providerbinding"
)

func buildGatheringToolHandlers(
	runtime *assistantAPIRuntime,
	infrastructure *assistantInfrastructure,
) (map[string]tool.Handler, error) {
	if runtime == nil || runtime.accountSecurityAuthority == nil {
		return nil, fmt.Errorf("gathering delegated grant authority is required")
	}
	if infrastructure == nil || infrastructure.router == nil {
		return nil, fmt.Errorf("gathering delegated grant JTI router is required")
	}
	generalRedis, found := infrastructure.router.LookupScene("general")
	if !found || generalRedis == nil {
		return nil, fmt.Errorf("gathering delegated grant JTI Redis scene general is required")
	}
	catalog, err := tooling.ParseGatheringBindingCatalog(
		[]byte(assistantgenerated.AssistantToolCatalogJSON),
	)
	if err != nil {
		return nil, fmt.Errorf("gathering canonical tool catalog invalid: %w", err)
	}
	verifier, err := rtauth.NewHS256DelegatedGrantVerifier(
		rtauth.DelegatedGrantVerifierConfig{
			Secret:                   runtime.accessTokenConfig.Secret,
			Issuer:                   runtime.accessTokenConfig.Issuer,
			ClockSkew:                runtime.accessTokenConfig.ClockSkew,
			AccountSecurityAuthority: runtime.accountSecurityAuthority,
		},
	)
	if err != nil {
		return nil, fmt.Errorf("gathering delegated grant verifier invalid: %w", err)
	}
	jtiStore, err := gatheringinfrastructure.NewRedisDelegatedGrantJTIStore(generalRedis)
	if err != nil {
		return nil, fmt.Errorf("gathering delegated grant JTI store invalid: %w", err)
	}
	commandConsumer, err := rtauth.NewDelegatedCommandGrantConsumer(verifier, jtiStore)
	if err != nil {
		return nil, fmt.Errorf("gathering delegated command consumer invalid: %w", err)
	}
	circleBinding := gatheringinfrastructure.NewCircleGatheringDomainOperationBinding()
	executor := tooling.NewGatheringExecutor(
		catalog,
		verifier,
		commandConsumer,
		circleBinding,
	)
	dispatcher, err := tooling.NewGatheringDispatcher(
		catalog,
		tooling.GatheringDispatcherDependencies{
			Executor: executor,
			ProviderState: gatheringOptionalProviderState(
				runtime.appEnv,
				runtimeconfig.EnvRuntimeConfigProvider{},
			),
			Availability: generatedGatheringToolAvailability(catalog),
		},
	)
	if err != nil {
		return nil, fmt.Errorf("gathering shared dispatcher invalid: %w", err)
	}
	return dispatcher.Handlers(), nil
}

func gatheringOptionalProviderState(
	appEnv string,
	configProvider runtimeconfig.RuntimeConfigProvider,
) tooling.GatheringOptionalProviderState {
	state := tooling.GatheringOptionalProviderState{}
	binding, err := resolveAssistantBinding(
		appEnv,
		"assistant.weather.forecast",
		[]string{
			providerbinding.WeatherAdapterOpenMeteo,
			providerbinding.WeatherAdapterProtocolFixture,
		},
		configProvider,
	)
	if err == nil {
		_, err = weatherProviderConfig(binding)
	}
	if err == nil {
		state.WeatherAvailable = true
		state.Evidence = append(
			state.Evidence,
			tooling.GatheringProviderBindingEvidence{
				CapabilityKey: "weather.forecast.read",
				BindingKind:   "public_provider",
				BindingRef:    "environment_binding:assistant.weather.forecast",
			},
		)
	}
	// location.poi.search/location.route.read remain unavailable until
	// integration-service activates their generated binding and remote probe.
	// Absence is intentional degradation, not a synthetic map fallback.
	return state
}

func generatedGatheringToolAvailability(
	catalog tooling.GatheringBindingCatalog,
) map[string]tooling.GatheringToolAvailability {
	descriptors := operationsecurity.ForDomain("circle")
	byOperation := make(map[string]string, len(descriptors))
	for _, descriptor := range descriptors {
		byOperation[strings.TrimSpace(descriptor.CanonicalOperationID)] =
			strings.TrimSpace(descriptor.CommercialStatus)
	}
	availability := make(map[string]tooling.GatheringToolAvailability, len(tooling.GatheringToolNames()))
	for _, toolName := range tooling.GatheringToolNames() {
		definition, found := catalog.Definition(toolName)
		if !found {
			availability[toolName] = tooling.GatheringToolAvailability{
				Blocked: true,
				Reason:  "canonical_definition_unavailable",
			}
			continue
		}
		status, found := byOperation[strings.TrimSpace(definition.OwnerOperationID)]
		if !found || status != "ready" {
			if status == "" {
				status = "generated_operation_unavailable"
			}
			availability[toolName] = tooling.GatheringToolAvailability{
				Blocked: true,
				Reason:  status,
			}
			continue
		}
		availability[toolName] = tooling.GatheringToolAvailability{Enabled: true}
	}
	return availability
}
