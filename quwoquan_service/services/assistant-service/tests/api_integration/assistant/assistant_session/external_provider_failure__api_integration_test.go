package api_integration

import (
	"context"
	"encoding/json"
	"net/http"
	"strings"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/orchestration"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	toolpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/tool"
	assistant "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/ports"
	assistanthttp "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/adapters/inbound/http"
	sessionmodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/model"
	skillpkg "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/application/packageasset"
	modeldouble "quwoquan_service/services/assistant-service/tests/support/modeldouble"
	"quwoquan_service/services/assistant-service/tests/support/promptassets"
	"quwoquan_service/services/assistant-service/tests/support/skillfixture"
)

func TestExternalProviderFailureApiIntegrationUsesStructuredRuntimeCode(t *testing.T) {
	resetIntegrationState(t)
	registry := toolpkg.BaseRegistry()
	registry.Register(
		toolpkg.WeatherLookupMetadata(),
		orchestration.NewWeatherLookupHandler(apiUnavailableWeatherProvider{}),
	)
	model := modeldouble.DeterministicModelProvider{}
	loop := orchestration.NewAgentLoop(
		apiWeatherSkillRuntime{},
		orchestration.ReactRuntime{
			Model: model,
			Tools: orchestration.DefaultToolCoordinator{Registry: registry},
		},
		nil,
	)
	loop.PromptAssets = promptassets.MustResolver(t)
	loop.Catalog = skillfixture.StaticLoader{Manifests: []skillpkg.Manifest{{
		SkillID:     "fallback_general_search",
		DomainID:    "fallback_general_search",
		DisplayName: "通用搜索助手",
		ToolPolicy: skillpkg.ToolPolicy{
			AllowedTools: []string{"weather_lookup"},
			MaxToolCalls: 2,
		},
	}}}
	handler := assistanthttp.NewHandler(
		newIntegrationAssistantService(),
	).Routes()
	create := assistantAPIRequest(
		t,
		handler,
		http.MethodPost,
		"/assistant/sessions",
		"provider-error-user",
		map[string]string{
			"summary": "provider error", "clientRequestId": "provider-error-session",
		},
	)
	if create.Code != http.StatusCreated {
		t.Fatalf("create status=%d body=%s", create.Code, create.Body.String())
	}
	var session sessionmodel.AssistantSession
	if err := json.Unmarshal(create.Body.Bytes(), &session); err != nil {
		t.Fatalf("decode session: %v", err)
	}
	start := assistantAPIRequest(
		t,
		handler,
		http.MethodPost,
		"/assistant/sessions/"+session.SessionID+"/runs",
		"provider-error-user",
		map[string]any{
			"intent": map[string]any{
				"kind": "answer", "answer": map[string]any{"text": "杭州明天天气"},
			},
			"clientRequestId": "provider-error-run",
		},
	)
	if start.Code != http.StatusCreated {
		t.Fatalf("start status=%d body=%s", start.Code, start.Body.String())
	}
	var run assistantRunEnvelope
	if err := json.Unmarshal(start.Body.Bytes(), &run); err != nil {
		t.Fatalf("decode run: %v", err)
	}
	worker := runruntime.NewDurableWorker(
		integrationRunRepository,
		integrationRunRepository,
		orchestration.NewDurableRunExecutor(loop),
		"external-provider-failure-worker",
	)
	worked, err := worker.ProcessNext(t.Context())
	if err != nil || !worked {
		t.Fatalf("process provider failure run: worked=%t err=%v", worked, err)
	}
	stream := assistantAPIRequest(
		t,
		handler,
		http.MethodGet,
		"/assistant/runs/"+run.RunID+"/events",
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
		"/assistant/runs/"+run.RunID,
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
	assertAssistantRunEnvelopePublicKeys(t, failedEnvelope)
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
		bson.M{"runId": run.RunID},
	); err != nil {
		t.Fatalf("expire failed run journal: %v", err)
	}
	restarted := assistanthttp.NewHandler(
		newIntegrationAssistantService(),
	).Routes()
	replayedFailure := assistantAPIRequest(
		t,
		restarted,
		http.MethodGet,
		"/assistant/runs/"+run.RunID+"/events",
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
) (orchestration.SkillSelection, error) {
	return orchestration.SkillSelection{
		SkillID:    "fallback_general_search",
		DomainID:   "fallback_general_search",
		ToolPolicy: []string{"weather_lookup"},
	}, nil
}

type apiUnavailableWeatherProvider struct{}

func (apiUnavailableWeatherProvider) Lookup(
	context.Context,
	ports.ExternalSearchRequest,
) (ports.ExternalSearchResult, error) {
	return ports.ExternalSearchResult{}, ports.ProviderFailure{
		Capability: "weather",
		Reason:     ports.ProviderFailureUnavailable,
	}
}
