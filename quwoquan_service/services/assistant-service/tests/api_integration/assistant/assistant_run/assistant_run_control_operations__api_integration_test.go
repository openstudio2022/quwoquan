// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/durable-agent-run-orchestration/spec.md#gwt-002
// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/durable-agent-run-orchestration/spec.md#gwt-003
// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/tool-fabric-runtime/spec.md#gwt-003
// readiness_case: get-assistant-run-api
// readiness_case: pause-assistant-run-api
// readiness_case: resume-assistant-run-api
// readiness_case: steer-assistant-run-api
// readiness_case: cancel-assistant-run-api
// readiness_case: approve-assistant-tool-use-api
// readiness_case: submit-device-action-receipt-api
package assistant_run_integration

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	runhttp "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/adapters/inbound/http"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	runpersistence "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/infrastructure"
)

func TestAssistantRunControlOperationsCrossHTTPAndMongoBoundary(t *testing.T) {
	database := requirePublicWebMongo(t)
	resetAssistantRunControlState(t)
	repository := runpersistence.NewMongoRunRepository(database)
	if err := repository.EnsureIndexes(t.Context()); err != nil {
		t.Fatalf("ensure AssistantRun indexes: %v", err)
	}
	now := time.Date(2026, 8, 6, 10, 0, 0, 0, time.UTC)
	commands := newAssistantRunControlService(repository, &now)
	handler := runhttp.NewHandler(commands).Routes()

	run, err := commands.Start(t.Context(), runruntime.StartCommand{
		UserID:          "control-owner",
		PersonaID:       "control-owner:persona",
		SessionID:       "control-session",
		ClientRequestID: "control-start",
		InputText:       "执行一个可暂停的任务",
	})
	if err != nil {
		t.Fatalf("start control run: %v", err)
	}

	get := assistantRunControlRequest(
		t, handler, http.MethodGet, "/assistant/runs/"+run.RunID,
		"control-owner", "", nil,
	)
	if get.Code != http.StatusOK {
		t.Fatalf("get run status=%d body=%s", get.Code, get.Body.String())
	}
	var envelope struct {
		RunID string `json:"runId"`
	}
	if err := json.Unmarshal(get.Body.Bytes(), &envelope); err != nil ||
		envelope.RunID != run.RunID {
		t.Fatalf("get run envelope=%+v err=%v", envelope, err)
	}

	pause := assistantRunControlRequest(
		t, handler, http.MethodPost, "/assistant/runs/"+run.RunID+"/pause",
		"control-owner", "control-pause", map[string]any{"reason": "用户暂离"},
	)
	if pause.Code != http.StatusOK {
		t.Fatalf("pause run status=%d body=%s", pause.Code, pause.Body.String())
	}
	assertAssistantRunState(
		t, repository, run.RunID, generated.AssistantRunStatePaused,
	)

	resume := assistantRunControlRequest(
		t, handler, http.MethodPost, "/assistant/runs/"+run.RunID+"/resume",
		"control-owner", "control-resume", nil,
	)
	if resume.Code != http.StatusOK {
		t.Fatalf("resume run status=%d body=%s", resume.Code, resume.Body.String())
	}
	assertAssistantRunState(
		t, repository, run.RunID, generated.AssistantRunStateOrienting,
	)

	steer := assistantRunControlRequest(
		t, handler, http.MethodPost, "/assistant/runs/"+run.RunID+"/steer",
		"control-owner", "control-steer",
		map[string]any{"instruction": "只采用可回查来源"},
	)
	if steer.Code != http.StatusOK {
		t.Fatalf("steer run status=%d body=%s", steer.Code, steer.Body.String())
	}
	steered, err := repository.Load(t.Context(), run.RunID)
	if err != nil || len(steered.PendingSteer) != 1 ||
		steered.PendingSteer[0] != "只采用可回查来源" {
		t.Fatalf("steer was not persisted: run=%+v err=%v", steered, err)
	}

	cancel := assistantRunControlRequest(
		t, handler, http.MethodPost, "/assistant/runs/"+run.RunID+"/cancel",
		"control-owner", "control-cancel", nil,
	)
	if cancel.Code != http.StatusOK {
		t.Fatalf("cancel run status=%d body=%s", cancel.Code, cancel.Body.String())
	}
	cancelled, err := repository.Load(t.Context(), run.RunID)
	if err != nil || cancelled.State != generated.AssistantRunStateCancelled ||
		cancelled.CompletedAt == nil {
		t.Fatalf("cancel was not durably terminal: run=%+v err=%v", cancelled, err)
	}
}

func TestAssistantRunApprovalAndDeviceReceiptCrossHTTPAndMongoBoundary(t *testing.T) {
	database := requirePublicWebMongo(t)
	resetAssistantRunControlState(t)
	repository := runpersistence.NewMongoRunRepository(database)
	if err := repository.EnsureIndexes(t.Context()); err != nil {
		t.Fatalf("ensure AssistantRun indexes: %v", err)
	}
	now := time.Date(2026, 8, 6, 11, 0, 0, 0, time.UTC)
	commands := newAssistantRunControlService(repository, &now)
	handler := runhttp.NewHandler(commands).Routes()

	run, err := commands.Start(t.Context(), runruntime.StartCommand{
		UserID:          "device-owner",
		PersonaID:       "device-owner:persona",
		SessionID:       "device-session",
		ClientRequestID: "device-start",
		InputText:       "创建明早九点的提醒",
	})
	if err != nil {
		t.Fatalf("start device-action run: %v", err)
	}
	const toolUseID = "tool-use-calendar-api"
	continuationToken := assistantRunControlContinuationToken(
		run.RunID,
		toolUseID,
	)
	persistAssistantRunWaitingApproval(
		t,
		repository,
		run,
		toolUseID,
		continuationToken,
		&now,
	)

	approved := assistantRunControlRequest(
		t,
		handler,
		http.MethodPost,
		"/assistant/runs/"+run.RunID+"/tool-invocations/"+toolUseID+"/approval",
		"device-owner",
		"approve-device-action",
		map[string]any{
			"decision":       "approved",
			"approvalPermit": continuationToken,
			"installationId": "installation-api-1",
			"deviceId":       "device-api-1",
		},
	)
	if approved.Code != http.StatusOK {
		t.Fatalf(
			"approve tool use status=%d body=%s",
			approved.Code,
			approved.Body.String(),
		)
	}
	var approval struct {
		RunID              string                         `json:"runId"`
		State              string                         `json:"state"`
		DeviceActionPermit *runruntime.DeviceActionPermit `json:"deviceActionPermit"`
	}
	if err := json.Unmarshal(approved.Body.Bytes(), &approval); err != nil ||
		approval.RunID != run.RunID ||
		approval.State != string(generated.AssistantRunStateWaitingExternal) ||
		approval.DeviceActionPermit == nil {
		t.Fatalf("approval response=%+v err=%v", approval, err)
	}
	permit := approval.DeviceActionPermit
	receipt := assistantRunControlRequest(
		t,
		handler,
		http.MethodPost,
		"/assistant/runs/"+run.RunID+"/tool-invocations/"+toolUseID+"/device-action-receipt",
		"device-owner",
		toolUseID,
		map[string]any{
			"installationId": permit.InstallationID,
			"deviceId":       permit.DeviceID,
			"capability":     permit.Capability,
			"inputDigest":    permit.InputDigest,
			"permit":         permit.Permit,
			"idempotencyKey": permit.IdempotencyKey,
			"outcome":        "completed",
			"executedAt":     now.Add(time.Second).Format(time.RFC3339Nano),
			"deviceObjectId": "calendar-event-api-1",
		},
	)
	if receipt.Code != http.StatusOK {
		t.Fatalf(
			"submit device receipt status=%d body=%s",
			receipt.Code,
			receipt.Body.String(),
		)
	}
	stored, err := repository.Load(t.Context(), run.RunID)
	if err != nil || stored.State != generated.AssistantRunStateExecuting ||
		stored.Checkpoint == nil || stored.Checkpoint.PendingApprovalRef != "" ||
		len(stored.Checkpoint.DeviceActionReceipts) != 1 ||
		stored.Checkpoint.DeviceActionReceipts[0].DeviceObjectID !=
			"calendar-event-api-1" {
		t.Fatalf("device receipt was not durably persisted: run=%+v err=%v", stored, err)
	}
}

func newAssistantRunControlService(
	repository runruntime.Repository,
	now *time.Time,
) *runruntime.CommandService {
	return runruntime.NewCommandService(
		repository,
		runruntime.SessionResolverFunc(func(
			context.Context,
			string,
			string,
		) (runruntime.SessionContinuity, error) {
			return runruntime.SessionContinuity{}, nil
		}),
		runruntime.StaticSkillPackageIdentityResolver{
			PackageID: "assistant.session.skills",
			ReleaseDigest: "sha256:" +
				"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
		},
		runruntime.AllowAllStartAccessPolicy{},
		func() time.Time {
			*now = now.Add(time.Second)
			return *now
		},
		nil,
		runruntime.WithPolicyResolver(runruntime.PolicyResolverFunc(func(
			context.Context,
			string,
			string,
			string,
			string,
		) (runruntime.FrozenPolicySelection, error) {
			return runruntime.FrozenPolicySelection{
				PolicyID: "assistant-control-api",
				ReleaseDigest: "sha256:" +
					"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
				Cohort:          "control",
				RolloutRevision: 1,
				RuleID:          "assistant-control-api",
				Template: runruntime.FrozenPolicyTemplate{
					TemplateID: "assistant-control-api",
					SkillID:    "assistant",
					DomainID:   "assistant",
				},
			}, nil
		})),
	)
}

func persistAssistantRunWaitingApproval(
	t *testing.T,
	repository runruntime.Repository,
	run runruntime.Run,
	toolUseID string,
	continuationToken string,
	now *time.Time,
) {
	t.Helper()
	expectedRevision := run.Revision
	for _, state := range []generated.AssistantRunState{
		generated.AssistantRunStateOrienting,
		generated.AssistantRunStatePlanning,
		generated.AssistantRunStateExecuting,
		generated.AssistantRunStateWaitingApproval,
	} {
		*now = now.Add(time.Second)
		if err := run.Transition(state, "", *now); err != nil {
			t.Fatalf("transition to %s: %v", state, err)
		}
	}
	run.Checkpoint = &runruntime.Checkpoint{
		CheckpointID:       "checkpoint-device-action-api",
		Revision:           run.Revision,
		PendingApprovalRef: toolUseID,
		CreatedAt:          *now,
	}
	approveTool := map[string]any{
		"runId":            run.RunID,
		"toolInvocationId": toolUseID,
		"decision":         "approved",
		"capability":       "calendar_create_reminder",
		"inputDigest": "sha256:" +
			"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
		"approvalPermit": continuationToken,
	}
	run.PresentationDocument = map[string]any{
		"revision": int64(1),
		"nodes": []map[string]any{{
			"nodeId": "device-action-confirmation",
			"kind":   "confirmation_card",
			"action": map[string]any{
				"kind":          "ApproveTool",
				"approveTool":   approveTool,
				"requestDigest": assistantRunControlActionIntentDigest(approveTool),
				"expiresAt":     now.Add(time.Minute).Format(time.RFC3339Nano),
			},
		}},
	}
	run.JournalSequence++
	if err := repository.Commit(
		t.Context(),
		expectedRevision,
		run,
		[]runruntime.JournalEvent{{
			EventID:   run.RunID + ":waiting-approval-api",
			RunID:     run.RunID,
			Sequence:  run.JournalSequence,
			Revision:  run.Revision,
			Kind:      "tool_use_waiting_approval",
			CreatedAt: *now,
		}},
		nil,
	); err != nil {
		t.Fatalf("persist waiting approval: %v", err)
	}
}

func assistantRunControlRequest(
	t *testing.T,
	handler http.Handler,
	method string,
	path string,
	accountID string,
	idempotencyKey string,
	body any,
) *httptest.ResponseRecorder {
	t.Helper()
	var payload []byte
	var err error
	if body != nil {
		payload, err = json.Marshal(body)
		if err != nil {
			t.Fatalf("marshal AssistantRun request: %v", err)
		}
	}
	request := httptest.NewRequest(method, path, bytes.NewReader(payload))
	if body != nil {
		request.Header.Set("Content-Type", "application/json")
	}
	request.Header.Set("X-Client-User-Id", accountID)
	if idempotencyKey != "" {
		request.Header.Set("Idempotency-Key", idempotencyKey)
	}
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	return recorder
}

func resetAssistantRunControlState(t *testing.T) {
	t.Helper()
	database := requirePublicWebMongo(t)
	for _, collection := range []string{
		"assistant_runs",
		"assistant_run_events",
		"assistant_run_command_receipts",
		"assistant_run_worker_leases",
		"assistant_run_work_queue",
		"assistant_run_terminal_outbox",
	} {
		if _, err := database.Collection(collection).DeleteMany(
			t.Context(),
			map[string]any{},
		); err != nil {
			t.Fatalf("reset %s: %v", collection, err)
		}
	}
}

func assertAssistantRunState(
	t *testing.T,
	repository runruntime.Repository,
	runID string,
	want generated.AssistantRunState,
) {
	t.Helper()
	run, err := repository.Load(t.Context(), runID)
	if err != nil || run.State != want {
		t.Fatalf("AssistantRun state=%s want=%s err=%v", run.State, want, err)
	}
}

func assistantRunControlContinuationToken(runID string, toolUseID string) string {
	digest := sha256.Sum256([]byte(
		strings.TrimSpace(runID) + "\x00" + strings.TrimSpace(toolUseID),
	))
	return "ct_" + hex.EncodeToString(digest[:16])
}

func assistantRunControlActionIntentDigest(value map[string]any) string {
	encoded, _ := json.Marshal(value)
	digest := sha256.Sum256(encoded)
	return "sha256:" + hex.EncodeToString(digest[:])
}
