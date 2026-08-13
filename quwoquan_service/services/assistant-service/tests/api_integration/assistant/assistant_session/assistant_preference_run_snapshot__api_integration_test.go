// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/session-preference-memory-control/spec.md#gwt-001
// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/session-preference-memory-control/spec.md#gwt-002
// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/long-term-memory-compaction/spec.md#gwt-001.t4
package api_integration

import (
	"encoding/json"
	"net/http"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"

	preferencehttp "quwoquan_service/services/assistant-service/internal/assistant/assistant_preference/adapters/inbound/http"
	preferenceapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_preference/application"
	preferencemodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_preference/domain/model"
	assistant "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/model"
	"quwoquan_service/services/assistant-service/tests/support/assistantingress"
)

func newPreferenceIntegrationHandler() http.Handler {
	queries := preferenceapplication.NewQueryFacade(integrationPreferenceStore)
	commands := preferenceapplication.NewCommandFacade(
		integrationPreferenceStore,
		integrationSessionStore,
	)
	mux := http.NewServeMux()
	preferencehttp.NewHandler(commands, queries).RegisterRoutes(mux)
	mux.Handle("/", assistantingress.Routes(
		newIntegrationAssistantService(),
		assistantingress.WithRunPreferenceSnapshots(queries),
	))
	return mux
}

func TestAssistantPreferencePersistenceRunSnapshotAndRestore(t *testing.T) {
	resetIntegrationState(t)
	handler := newPreferenceIntegrationHandler()

	create := assistantAPIRequest(
		t,
		handler,
		http.MethodPost,
		"/assistant/sessions",
		"preference-owner",
		map[string]any{
			"summary": "偏好闭环", "clientRequestId": "preference-preference-session",
		},
	)
	if create.Code != http.StatusCreated {
		t.Fatalf("create session status=%d body=%s", create.Code, create.Body.String())
	}
	var session assistant.AssistantSession
	if err := json.Unmarshal(create.Body.Bytes(), &session); err != nil {
		t.Fatalf("decode session: %v", err)
	}
	createOtherSession := assistantAPIRequest(
		t,
		handler,
		http.MethodPost,
		"/assistant/sessions",
		"preference-owner",
		map[string]any{
			"summary": "偏好隔离", "clientRequestId": "preference-preference-session-other",
		},
	)
	if createOtherSession.Code != http.StatusCreated {
		t.Fatalf(
			"create other session status=%d body=%s",
			createOtherSession.Code,
			createOtherSession.Body.String(),
		)
	}
	var otherSession assistant.AssistantSession
	if err := json.Unmarshal(createOtherSession.Body.Bytes(), &otherSession); err != nil {
		t.Fatalf("decode other session: %v", err)
	}

	setBody := map[string]any{
		"scope":      "session",
		"sessionId":  session.SessionID,
		"kind":       "reply_length",
		"value":      "concise",
		"sourceType": "explicit_rewrite",
	}
	set := assistantAPIRequest(
		t,
		handler,
		http.MethodPost,
		"/assistant/preferences",
		"preference-owner",
		setBody,
	)
	if set.Code != http.StatusOK {
		t.Fatalf("set preference status=%d body=%s", set.Code, set.Body.String())
	}
	var preference preferencemodel.AssistantPreference
	if err := json.Unmarshal(set.Body.Bytes(), &preference); err != nil {
		t.Fatalf("decode preference: %v", err)
	}
	if preference.PreferenceID == "" || preference.Status != preferencemodel.StatusActive {
		t.Fatalf("preference = %#v", preference)
	}
	foreignSet := assistantAPIRequest(
		t,
		handler,
		http.MethodPost,
		"/assistant/preferences",
		"preference-intruder",
		setBody,
	)
	if foreignSet.Code != http.StatusNotFound {
		t.Fatalf(
			"foreign session preference set status=%d body=%s",
			foreignSet.Code,
			foreignSet.Body.String(),
		)
	}

	replayed := assistantAPIRequest(
		t,
		handler,
		http.MethodPost,
		"/assistant/preferences",
		"preference-owner",
		setBody,
	)
	var replayedPreference preferencemodel.AssistantPreference
	if err := json.Unmarshal(replayed.Body.Bytes(), &replayedPreference); err != nil {
		t.Fatalf("decode replayed preference: %v", err)
	}
	if replayedPreference.PreferenceID != preference.PreferenceID {
		t.Fatalf(
			"natural identity changed: first=%s replay=%s",
			preference.PreferenceID,
			replayedPreference.PreferenceID,
		)
	}
	count, err := integrationMongoDB.Collection(
		"assistant_preferences",
	).CountDocuments(t.Context(), bson.M{"userId": "preference-owner"})
	if err != nil || count != 1 {
		t.Fatalf("preference count=%d err=%v", count, err)
	}

	start := assistantAPIRequest(
		t,
		handler,
		http.MethodPost,
		"/assistant/sessions/"+session.SessionID+"/runs",
		"preference-owner",
		map[string]any{
			"intent": map[string]any{
				"kind":   "answer",
				"answer": map[string]any{"text": "保持原问题"},
			},
			"clientRequestId": "preference-run",
		},
	)
	if start.Code != http.StatusCreated {
		t.Fatalf("start run status=%d body=%s", start.Code, start.Body.String())
	}
	var startEnvelope map[string]any
	if err := json.Unmarshal(start.Body.Bytes(), &startEnvelope); err != nil {
		t.Fatalf("decode start envelope: %v", err)
	}
	if _, leaked := startEnvelope["sessionPreferences"]; leaked {
		t.Fatalf("start envelope leaked internal session preferences: %#v", startEnvelope)
	}
	startRunID, _ := startEnvelope["runId"].(string)
	startedRun, err := integrationRunRepository.Load(t.Context(), startRunID)
	if err != nil {
		t.Fatalf("load started preference run err=%v", err)
	}
	if startedRun.InputText != "保持原问题" ||
		len(startedRun.SessionPreferences) != 1 ||
		startedRun.SessionPreferences[0].PreferenceID != preference.PreferenceID {
		t.Fatalf("run preference snapshot = %#v", startedRun)
	}
	otherStart := assistantAPIRequest(
		t,
		handler,
		http.MethodPost,
		"/assistant/sessions/"+otherSession.SessionID+"/runs",
		"preference-owner",
		map[string]any{
			"intent": map[string]any{
				"kind":   "answer",
				"answer": map[string]any{"text": "另一个会话保持原问题"},
			},
			"clientRequestId": "preference-run-other-session",
		},
	)
	if otherStart.Code != http.StatusCreated {
		t.Fatalf(
			"start other session run status=%d body=%s",
			otherStart.Code,
			otherStart.Body.String(),
		)
	}
	var otherEnvelope map[string]any
	if err := json.Unmarshal(otherStart.Body.Bytes(), &otherEnvelope); err != nil {
		t.Fatalf("decode other start envelope: %v", err)
	}
	otherRunID, _ := otherEnvelope["runId"].(string)
	otherRun, err := integrationRunRepository.Load(t.Context(), otherRunID)
	if err != nil {
		t.Fatalf("load other preference run err=%v", err)
	}
	if otherRun.InputText != "另一个会话保持原问题" ||
		len(otherRun.SessionPreferences) != 0 {
		t.Fatalf(
			"other session inherited session preference: %#v",
			otherRun,
		)
	}

	foreign := assistantAPIRequest(
		t,
		handler,
		http.MethodPost,
		"/assistant/preferences/"+preference.PreferenceID+"/revoke",
		"preference-intruder",
		nil,
	)
	if foreign.Code != http.StatusNotFound {
		t.Fatalf("foreign revoke status=%d body=%s", foreign.Code, foreign.Body.String())
	}
	foreignRestore := assistantAPIRequest(
		t,
		handler,
		http.MethodPost,
		"/assistant/preferences/"+preference.PreferenceID+"/restore",
		"preference-intruder",
		nil,
	)
	if foreignRestore.Code != http.StatusNotFound {
		t.Fatalf(
			"foreign restore status=%d body=%s",
			foreignRestore.Code,
			foreignRestore.Body.String(),
		)
	}
	for _, operation := range []string{"revoke", "restore"} {
		missing := assistantAPIRequest(
			t,
			handler,
			http.MethodPost,
			"/assistant/preferences/apf_missing/"+operation,
			"preference-owner",
			nil,
		)
		if missing.Code != http.StatusNotFound {
			t.Fatalf(
				"missing preference %s status=%d body=%s",
				operation,
				missing.Code,
				missing.Body.String(),
			)
		}
	}

	revoke := assistantAPIRequest(
		t,
		handler,
		http.MethodPost,
		"/assistant/preferences/"+preference.PreferenceID+"/revoke",
		"preference-owner",
		nil,
	)
	if revoke.Code != http.StatusOK {
		t.Fatalf("revoke status=%d body=%s", revoke.Code, revoke.Body.String())
	}
	listActive := assistantAPIRequest(
		t,
		handler,
		http.MethodGet,
		"/assistant/preferences?scope=session&sessionId="+session.SessionID,
		"preference-owner",
		nil,
	)
	var activeView preferenceapplication.AssistantPreferenceListView
	if err := json.Unmarshal(listActive.Body.Bytes(), &activeView); err != nil {
		t.Fatalf("decode active preferences: %v", err)
	}
	if len(activeView.Items) != 0 {
		t.Fatalf("revoked preference leaked into active list: %#v", activeView.Items)
	}
	revokedRun := assistantAPIRequest(
		t,
		handler,
		http.MethodPost,
		"/assistant/sessions/"+session.SessionID+"/runs",
		"preference-owner",
		map[string]any{
			"intent": map[string]any{
				"kind":   "answer",
				"answer": map[string]any{"text": "撤销后不应注入"},
			},
			"clientRequestId": "preference-run-revoked",
		},
	)
	if revokedRun.Code != http.StatusCreated {
		t.Fatalf(
			"start revoked-preference run status=%d body=%s",
			revokedRun.Code,
			revokedRun.Body.String(),
		)
	}
	var revokedEnvelope map[string]any
	if err := json.Unmarshal(revokedRun.Body.Bytes(), &revokedEnvelope); err != nil {
		t.Fatalf("decode revoked-preference envelope: %v", err)
	}
	revokedRunID, _ := revokedEnvelope["runId"].(string)
	revokedSnapshot, err := integrationRunRepository.Load(
		t.Context(),
		revokedRunID,
	)
	if err != nil {
		t.Fatalf("load revoked preference run err=%v", err)
	}
	if len(revokedSnapshot.SessionPreferences) != 0 {
		t.Fatalf(
			"revoked preference leaked into run snapshot: %#v",
			revokedSnapshot.SessionPreferences,
		)
	}

	restore := assistantAPIRequest(
		t,
		handler,
		http.MethodPost,
		"/assistant/preferences/"+preference.PreferenceID+"/restore",
		"preference-owner",
		nil,
	)
	if restore.Code != http.StatusOK {
		t.Fatalf("restore status=%d body=%s", restore.Code, restore.Body.String())
	}
	restarted := newPreferenceIntegrationHandler()
	listAfterRestart := assistantAPIRequest(
		t,
		restarted,
		http.MethodGet,
		"/assistant/preferences?status=active",
		"preference-owner",
		nil,
	)
	if err := json.Unmarshal(listAfterRestart.Body.Bytes(), &activeView); err != nil {
		t.Fatalf("decode restarted preferences: %v", err)
	}
	if len(activeView.Items) != 1 ||
		activeView.Items[0].PreferenceID != preference.PreferenceID {
		t.Fatalf("restored preference did not survive restart: %#v", activeView.Items)
	}
	restoredRun := assistantAPIRequest(
		t,
		restarted,
		http.MethodPost,
		"/assistant/sessions/"+session.SessionID+"/runs",
		"preference-owner",
		map[string]any{
			"intent": map[string]any{
				"kind":   "answer",
				"answer": map[string]any{"text": "恢复后重新注入"},
			},
			"clientRequestId": "preference-run-restored",
		},
	)
	if restoredRun.Code != http.StatusCreated {
		t.Fatalf(
			"start restored-preference run status=%d body=%s",
			restoredRun.Code,
			restoredRun.Body.String(),
		)
	}
	var restoredEnvelope map[string]any
	if err := json.Unmarshal(restoredRun.Body.Bytes(), &restoredEnvelope); err != nil {
		t.Fatalf("decode restored-preference envelope: %v", err)
	}
	restoredRunID, _ := restoredEnvelope["runId"].(string)
	restoredSnapshot, err := integrationRunRepository.Load(
		t.Context(),
		restoredRunID,
	)
	if err != nil {
		t.Fatalf("load restored preference run err=%v", err)
	}
	if len(restoredSnapshot.SessionPreferences) != 1 ||
		restoredSnapshot.SessionPreferences[0].PreferenceID != preference.PreferenceID {
		t.Fatalf(
			"restored preference missing from run snapshot: %#v",
			restoredSnapshot.SessionPreferences,
		)
	}
}
