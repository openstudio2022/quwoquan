package api_integration

import (
	"context"
	"encoding/json"
	"net/http"
	"strings"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"

	assistanthttp "quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/adapters/inbound/http"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/application"
	toolpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/application/tool"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/domain/assistant"
)

func TestExternalProviderFailureApiIntegrationUsesStructuredRuntimeCode(t *testing.T) {
	resetIntegrationState(t)
	registry := toolpkg.BaseRegistry()
	registry.Register(
		toolpkg.WebSearchMetadata(),
		application.NewExternalWebSearchHandler(
			nil,
			apiUnavailableWeatherProvider{},
			nil,
		),
	)
	model := application.DeterministicModelProvider{}
	loop := application.NewAgentLoop(
		apiWeatherSkillRuntime{},
		application.ReactRuntime{
			Model: model,
			Tools: application.DefaultToolCoordinator{Registry: registry},
		},
		nil,
	)
	handler := assistanthttp.NewHandler(
		newIntegrationAssistantService(
			application.WithAgentLoop(loop),
			weatherFrozenPolicyOption(),
		),
	).Routes()
	create := assistantAPIRequest(
		t,
		handler,
		http.MethodPost,
		"/assistant/conversations",
		"provider-error-user",
		map[string]string{
			"summary": "provider error", "clientRequestId": "provider-error-conversation",
		},
	)
	if create.Code != http.StatusCreated {
		t.Fatalf("create status=%d body=%s", create.Code, create.Body.String())
	}
	var conversation assistant.AssistantConversation
	if err := json.Unmarshal(create.Body.Bytes(), &conversation); err != nil {
		t.Fatalf("decode conversation: %v", err)
	}
	start := assistantAPIRequest(
		t,
		handler,
		http.MethodPost,
		"/assistant/conversations/"+conversation.ConversationID+"/runs",
		"provider-error-user",
		map[string]any{
			"input":           map[string]string{"text": "杭州明天天气"},
			"clientRequestId": "provider-error-run",
		},
	)
	if start.Code != http.StatusCreated {
		t.Fatalf("start status=%d body=%s", start.Code, start.Body.String())
	}
	var run assistant.AssistantTurn
	if err := json.Unmarshal(start.Body.Bytes(), &run); err != nil {
		t.Fatalf("decode run: %v", err)
	}
	stream := assistantAPIRequest(
		t,
		handler,
		http.MethodGet,
		"/assistant/runs/"+run.TurnID+"/events",
		"provider-error-user",
		nil,
	)
	if stream.Code != http.StatusOK {
		t.Fatalf("stream status=%d body=%s", stream.Code, stream.Body.String())
	}
	if !strings.Contains(
		stream.Body.String(),
		"ASSISTANT.MIDDLEWARE.weather_provider_unavailable",
	) {
		t.Fatalf("stream must expose metadata-derived runtime code: %s", stream.Body.String())
	}
	assertNoExternalProviderMaterial(t, stream.Body.String())

	runResponse := assistantAPIRequest(
		t,
		handler,
		http.MethodGet,
		"/assistant/runs/"+run.TurnID,
		"provider-error-user",
		nil,
	)
	if runResponse.Code != http.StatusOK {
		t.Fatalf("run status=%d body=%s", runResponse.Code, runResponse.Body.String())
	}
	var failedEnvelope map[string]any
	if err := json.Unmarshal(runResponse.Body.Bytes(), &failedEnvelope); err != nil {
		t.Fatalf("decode failed run envelope: %v", err)
	}
	assertAssistantTurnEnvelopePublicKeys(t, failedEnvelope)
	terminalSnapshot := assertAssistantTerminalSnapshotPublicShape(
		t,
		failedEnvelope["terminalSnapshot"],
	)
	failure, ok := terminalSnapshot["failure"].(map[string]any)
	if failedEnvelope["status"] != "failed" ||
		!ok ||
		failure["code"] != "ASSISTANT.MIDDLEWARE.weather_provider_unavailable" {
		t.Fatalf("failed run terminal snapshot=%#v", failedEnvelope)
	}
	assertNoExternalProviderMaterial(t, runResponse.Body.String())

	if _, err := integrationMongoDB.Collection("assistant_run_events").DeleteMany(
		context.Background(),
		bson.M{"runId": run.TurnID},
	); err != nil {
		t.Fatalf("expire failed run journal: %v", err)
	}
	restarted := assistanthttp.NewHandler(
		newIntegrationAssistantService(
			application.WithAgentLoop(loop),
			weatherFrozenPolicyOption(),
		),
	).Routes()
	replayedFailure := assistantAPIRequest(
		t,
		restarted,
		http.MethodGet,
		"/assistant/runs/"+run.TurnID+"/events",
		"provider-error-user",
		nil,
	)
	if replayedFailure.Code != http.StatusOK ||
		!strings.Contains(
			replayedFailure.Body.String(),
			"ASSISTANT.MIDDLEWARE.weather_provider_unavailable",
		) {
		t.Fatalf(
			"failed run must replay from terminal snapshot after journal expiry: status=%d body=%s",
			replayedFailure.Code,
			replayedFailure.Body.String(),
		)
	}
	assertNoExternalProviderMaterial(t, replayedFailure.Body.String())
}

func weatherFrozenPolicyOption() application.AssistantServiceOption {
	return application.WithFrozenPolicyResolver(
		application.FrozenPolicyResolverFunc(
			func(
				_ context.Context,
				policyID string,
				_ string,
				_ string,
				_ string,
			) (assistant.AssistantFrozenPolicySelection, error) {
				return assistant.AssistantFrozenPolicySelection{
					PolicyID:        policyID,
					ReleaseVersion:  "test-weather-release",
					Cohort:          "control",
					RolloutRevision: 1,
					RuleID:          "test-weather",
					Template: assistant.AssistantFrozenPolicyTemplate{
						TemplateID:      "test-weather-template",
						SkillID:         "weather",
						DomainID:        "weather",
						PromptPolicy:    "weather provider failure test",
						AllowedTools:    []string{"web_search"},
						SearchIntensity: "balanced",
					},
				}, nil
			},
		),
	)
}

func assertNoExternalProviderMaterial(t *testing.T, payload string) {
	t.Helper()
	for _, forbidden := range []string{
		"endpoint",
		"credential",
		"api_key",
		"secret",
		"open_meteo",
		"duckduckgo",
		"yahoo",
		"xiaomi",
	} {
		if strings.Contains(strings.ToLower(payload), forbidden) {
			t.Fatalf("external payload leaks provider material %q: %s", forbidden, payload)
		}
	}
}

type apiWeatherSkillRuntime struct{}

func (apiWeatherSkillRuntime) SelectSkill(
	context.Context,
	assistant.AssistantTurn,
) (application.SkillSelection, error) {
	return application.SkillSelection{
		SkillID:    "weather",
		DomainID:   "weather",
		ToolPolicy: []string{"web_search"},
	}, nil
}

type apiUnavailableWeatherProvider struct{}

func (apiUnavailableWeatherProvider) Lookup(
	context.Context,
	application.ExternalSearchRequest,
) (application.ExternalSearchResult, error) {
	return application.ExternalSearchResult{}, application.ProviderFailure{
		Capability: "weather",
		Reason:     application.ProviderFailureUnavailable,
	}
}
