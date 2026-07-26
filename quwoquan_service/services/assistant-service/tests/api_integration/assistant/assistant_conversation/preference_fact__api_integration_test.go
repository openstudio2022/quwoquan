// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/session-preference-memory-control/spec.md#gwt-001
// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/session-preference-memory-control/spec.md#gwt-002
package api_integration

import (
	"encoding/json"
	"net/http"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"

	assistanthttp "quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/adapters/inbound/http"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/domain/assistant"
	preferencefact "quwoquan_service/services/assistant-service/internal/assistant/assistant_preference_fact/application"
	preferencemodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_preference_fact/domain/model"
)

func newPreferenceIntegrationHandler() http.Handler {
	queries := preferencefact.NewQueryFacade(integrationPreferenceStore)
	commands := preferencefact.NewCommandFacade(
		integrationPreferenceStore,
		integrationConversationRunStore,
	)
	return assistanthttp.NewHandler(
		newIntegrationAssistantService(),
		assistanthttp.WithPreferenceFacades(commands, queries),
	).Routes()
}

func TestAssistantPreferencePersistenceRunSnapshotAndRestore(t *testing.T) {
	resetIntegrationState(t)
	handler := newPreferenceIntegrationHandler()

	create := assistantAPIRequest(
		t,
		handler,
		http.MethodPost,
		"/assistant/conversations",
		"preference-owner",
		map[string]any{
			"summary": "偏好闭环", "clientRequestId": "preference-fact-conversation",
		},
	)
	if create.Code != http.StatusCreated {
		t.Fatalf("create conversation status=%d body=%s", create.Code, create.Body.String())
	}
	var conversation assistant.AssistantConversation
	if err := json.Unmarshal(create.Body.Bytes(), &conversation); err != nil {
		t.Fatalf("decode conversation: %v", err)
	}
	createOtherConversation := assistantAPIRequest(
		t,
		handler,
		http.MethodPost,
		"/assistant/conversations",
		"preference-owner",
		map[string]any{
			"summary": "偏好隔离", "clientRequestId": "preference-fact-conversation-other",
		},
	)
	if createOtherConversation.Code != http.StatusCreated {
		t.Fatalf(
			"create other conversation status=%d body=%s",
			createOtherConversation.Code,
			createOtherConversation.Body.String(),
		)
	}
	var otherConversation assistant.AssistantConversation
	if err := json.Unmarshal(createOtherConversation.Body.Bytes(), &otherConversation); err != nil {
		t.Fatalf("decode other conversation: %v", err)
	}

	setBody := map[string]any{
		"scope":          "session",
		"conversationId": conversation.ConversationID,
		"kind":           "reply_length",
		"value":          "concise",
		"sourceType":     "explicit_rewrite",
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
	var fact preferencemodel.Fact
	if err := json.Unmarshal(set.Body.Bytes(), &fact); err != nil {
		t.Fatalf("decode preference: %v", err)
	}
	if fact.PreferenceID == "" || fact.Status != preferencemodel.StatusActive {
		t.Fatalf("preference = %#v", fact)
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
	var replayedFact preferencemodel.Fact
	if err := json.Unmarshal(replayed.Body.Bytes(), &replayedFact); err != nil {
		t.Fatalf("decode replayed preference: %v", err)
	}
	if replayedFact.PreferenceID != fact.PreferenceID {
		t.Fatalf(
			"natural identity changed: first=%s replay=%s",
			fact.PreferenceID,
			replayedFact.PreferenceID,
		)
	}
	count, err := integrationMongoDB.Collection(
		"assistant_preference_facts",
	).CountDocuments(t.Context(), bson.M{"userId": "preference-owner"})
	if err != nil || count != 1 {
		t.Fatalf("preference count=%d err=%v", count, err)
	}

	start := assistantAPIRequest(
		t,
		handler,
		http.MethodPost,
		"/assistant/conversations/"+conversation.ConversationID+"/runs",
		"preference-owner",
		map[string]any{
			"input":           map[string]any{"text": "保持原问题"},
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
	if _, leaked := startEnvelope["sessionPreferenceFacts"]; leaked {
		t.Fatalf("start envelope leaked internal session preferences: %#v", startEnvelope)
	}
	startTurnID, _ := startEnvelope["turnId"].(string)
	startedTurn, found, err := integrationConversationRunStore.GetTurn(
		t.Context(),
		startTurnID,
	)
	if err != nil || !found {
		t.Fatalf("load started preference run found=%v err=%v", found, err)
	}
	if startedTurn.Input.Text != "保持原问题" ||
		len(startedTurn.SessionPreferenceFacts) != 1 ||
		startedTurn.SessionPreferenceFacts[0].PreferenceID != fact.PreferenceID {
		t.Fatalf("run preference snapshot = %#v", startedTurn)
	}
	otherStart := assistantAPIRequest(
		t,
		handler,
		http.MethodPost,
		"/assistant/conversations/"+otherConversation.ConversationID+"/runs",
		"preference-owner",
		map[string]any{
			"input":           map[string]any{"text": "另一个会话保持原问题"},
			"clientRequestId": "preference-run-other-conversation",
		},
	)
	if otherStart.Code != http.StatusCreated {
		t.Fatalf(
			"start other conversation run status=%d body=%s",
			otherStart.Code,
			otherStart.Body.String(),
		)
	}
	var otherEnvelope map[string]any
	if err := json.Unmarshal(otherStart.Body.Bytes(), &otherEnvelope); err != nil {
		t.Fatalf("decode other start envelope: %v", err)
	}
	otherTurnID, _ := otherEnvelope["turnId"].(string)
	otherTurn, found, err := integrationConversationRunStore.GetTurn(
		t.Context(),
		otherTurnID,
	)
	if err != nil || !found {
		t.Fatalf("load other preference run found=%v err=%v", found, err)
	}
	if otherTurn.Input.Text != "另一个会话保持原问题" ||
		len(otherTurn.SessionPreferenceFacts) != 0 {
		t.Fatalf(
			"other conversation inherited session preference: %#v",
			otherTurn,
		)
	}

	foreign := assistantAPIRequest(
		t,
		handler,
		http.MethodPost,
		"/assistant/preferences/"+fact.PreferenceID+"/revoke",
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
		"/assistant/preferences/"+fact.PreferenceID+"/restore",
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
		"/assistant/preferences/"+fact.PreferenceID+"/revoke",
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
		"/assistant/preferences?scope=session&conversationId="+conversation.ConversationID,
		"preference-owner",
		nil,
	)
	var activeView preferencefact.PreferenceFactListView
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
		"/assistant/conversations/"+conversation.ConversationID+"/runs",
		"preference-owner",
		map[string]any{
			"input":           map[string]any{"text": "撤销后不应注入"},
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
	revokedTurnID, _ := revokedEnvelope["turnId"].(string)
	revokedTurn, found, err := integrationConversationRunStore.GetTurn(
		t.Context(),
		revokedTurnID,
	)
	if err != nil || !found {
		t.Fatalf("load revoked preference run found=%v err=%v", found, err)
	}
	if len(revokedTurn.SessionPreferenceFacts) != 0 {
		t.Fatalf(
			"revoked preference leaked into run snapshot: %#v",
			revokedTurn.SessionPreferenceFacts,
		)
	}

	restore := assistantAPIRequest(
		t,
		handler,
		http.MethodPost,
		"/assistant/preferences/"+fact.PreferenceID+"/restore",
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
		activeView.Items[0].PreferenceID != fact.PreferenceID {
		t.Fatalf("restored preference did not survive restart: %#v", activeView.Items)
	}
	restoredRun := assistantAPIRequest(
		t,
		restarted,
		http.MethodPost,
		"/assistant/conversations/"+conversation.ConversationID+"/runs",
		"preference-owner",
		map[string]any{
			"input":           map[string]any{"text": "恢复后重新注入"},
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
	restoredTurnID, _ := restoredEnvelope["turnId"].(string)
	restoredTurn, found, err := integrationConversationRunStore.GetTurn(
		t.Context(),
		restoredTurnID,
	)
	if err != nil || !found {
		t.Fatalf("load restored preference run found=%v err=%v", found, err)
	}
	if len(restoredTurn.SessionPreferenceFacts) != 1 ||
		restoredTurn.SessionPreferenceFacts[0].PreferenceID != fact.PreferenceID {
		t.Fatalf(
			"restored preference missing from run snapshot: %#v",
			restoredTurn.SessionPreferenceFacts,
		)
	}
}
