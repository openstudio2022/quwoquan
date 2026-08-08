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

	"go.mongodb.org/mongo-driver/v2/mongo"

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
	receiptBody := map[string]any{
		"installationId": permit.InstallationID,
		"deviceId":       permit.DeviceID,
		"capability":     permit.Capability,
		"inputDigest":    permit.InputDigest,
		"permit":         permit.Permit,
		"idempotencyKey": permit.IdempotencyKey,
		"outcome":        "completed",
		"executedAt":     now.Add(time.Second).Format(time.RFC3339Nano),
		"deviceObjectId": "calendar-event-api-1",
	}
	beforeInvalid := assistantRunControlFactCounts(
		t,
		database,
		repository,
		run.RunID,
	)
	invalidBody := cloneAssistantRunControlBody(receiptBody)
	invalidBody["inputDigest"] = "sha256:" + strings.Repeat("b", 64)
	invalid := assistantRunControlRequest(
		t,
		handler,
		http.MethodPost,
		"/assistant/runs/"+run.RunID+"/tool-invocations/"+toolUseID+"/device-action-receipt",
		"device-owner",
		toolUseID,
		invalidBody,
	)
	assertAssistantRunControlError(
		t,
		invalid,
		http.StatusForbidden,
		"ASSISTANT.USER.device_action_permit_invalid",
	)
	assertAssistantRunControlFactCounts(
		t,
		database,
		repository,
		run.RunID,
		beforeInvalid,
	)

	receipt := assistantRunControlRequest(
		t,
		handler,
		http.MethodPost,
		"/assistant/runs/"+run.RunID+"/tool-invocations/"+toolUseID+"/device-action-receipt",
		"device-owner",
		toolUseID,
		receiptBody,
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
	acceptedFacts := assistantRunControlFactCounts(
		t,
		database,
		repository,
		run.RunID,
	)
	exactReplay := assistantRunControlRequest(
		t,
		handler,
		http.MethodPost,
		"/assistant/runs/"+run.RunID+"/tool-invocations/"+toolUseID+"/device-action-receipt",
		"device-owner",
		toolUseID,
		receiptBody,
	)
	if exactReplay.Code != http.StatusOK {
		t.Fatalf("exact receipt replay status=%d body=%s", exactReplay.Code, exactReplay.Body)
	}
	assertAssistantRunControlFactCounts(
		t,
		database,
		repository,
		run.RunID,
		acceptedFacts,
	)

	changedBody := cloneAssistantRunControlBody(receiptBody)
	changedBody["deviceObjectId"] = "different-calendar-event"
	changedReplay := assistantRunControlRequest(
		t,
		handler,
		http.MethodPost,
		"/assistant/runs/"+run.RunID+"/tool-invocations/"+toolUseID+"/device-action-receipt",
		"device-owner",
		toolUseID,
		changedBody,
	)
	assertAssistantRunControlError(
		t,
		changedReplay,
		http.StatusConflict,
		"ASSISTANT.USER.device_action_permit_replayed",
	)
	newIdentityReplay := assistantRunControlRequest(
		t,
		handler,
		http.MethodPost,
		"/assistant/runs/"+run.RunID+"/tool-invocations/"+toolUseID+"/device-action-receipt",
		"device-owner",
		"new-device-receipt-command",
		receiptBody,
	)
	assertAssistantRunControlError(
		t,
		newIdentityReplay,
		http.StatusConflict,
		"ASSISTANT.USER.device_action_permit_replayed",
	)
	assertAssistantRunControlFactCounts(
		t,
		database,
		repository,
		run.RunID,
		acceptedFacts,
	)
}

func TestAssistantRunExpiredDevicePermitCrossesHTTPAndMongoWithoutFacts(t *testing.T) {
	database := requirePublicWebMongo(t)
	resetAssistantRunControlState(t)
	repository := runpersistence.NewMongoRunRepository(database)
	if err := repository.EnsureIndexes(t.Context()); err != nil {
		t.Fatalf("ensure AssistantRun indexes: %v", err)
	}
	now := time.Date(2026, 8, 6, 12, 0, 0, 0, time.UTC)
	commands := newAssistantRunControlService(repository, &now)
	handler := runhttp.NewHandler(commands).Routes()
	run, err := commands.Start(t.Context(), runruntime.StartCommand{
		UserID:          "expired-device-owner",
		PersonaID:       "expired-device-owner:persona",
		SessionID:       "expired-device-session",
		ClientRequestID: "expired-device-start",
		InputText:       "创建一个到期边界提醒",
	})
	if err != nil {
		t.Fatalf("start expired permit Run: %v", err)
	}
	const toolUseID = "tool-use-expired-device"
	continuationToken := assistantRunControlContinuationToken(run.RunID, toolUseID)
	persistAssistantRunWaitingApproval(
		t,
		repository,
		run,
		toolUseID,
		continuationToken,
		&now,
	)
	_, permit, err := commands.ApproveToolUse(
		t.Context(),
		runruntime.ApproveToolUseCommand{
			UserID:           run.UserID,
			RunID:            run.RunID,
			ToolInvocationID: toolUseID,
			CommandID:        "approve-expired-device",
			Decision:         "approved",
			ApprovalPermit:   continuationToken,
			InstallationID:   "expired-installation",
			DeviceID:         "expired-device",
		},
	)
	if err != nil || permit == nil {
		t.Fatalf("approve expired permit fixture: permit=%+v err=%v", permit, err)
	}
	// newAssistantRunControlService advances one second for the next command;
	// place the clock exactly one second before expiry to exercise equality.
	now = permit.ExpiresAt.Add(-time.Second)
	baseline := assistantRunControlFactCounts(
		t,
		database,
		repository,
		run.RunID,
	)
	expired := assistantRunControlRequest(
		t,
		handler,
		http.MethodPost,
		"/assistant/runs/"+run.RunID+"/tool-invocations/"+toolUseID+"/device-action-receipt",
		run.UserID,
		permit.IdempotencyKey,
		map[string]any{
			"installationId": permit.InstallationID,
			"deviceId":       permit.DeviceID,
			"capability":     permit.Capability,
			"inputDigest":    permit.InputDigest,
			"permit":         permit.Permit,
			"idempotencyKey": permit.IdempotencyKey,
			"outcome":        "completed",
			"executedAt":     permit.ExpiresAt.Add(-time.Second).Format(time.RFC3339Nano),
			"deviceObjectId": "expired-calendar-event",
		},
	)
	assertAssistantRunControlError(
		t,
		expired,
		http.StatusGone,
		"ASSISTANT.USER.device_action_permit_expired",
	)
	assertAssistantRunControlFactCounts(
		t,
		database,
		repository,
		run.RunID,
		baseline,
	)
}

type assistantRunControlFacts struct {
	journalEvents   int
	commandReceipts int64
	deviceReceipts  int
	revision        int64
}

func assistantRunControlFactCounts(
	t *testing.T,
	database *mongo.Database,
	repository runruntime.Repository,
	runID string,
) assistantRunControlFacts {
	t.Helper()
	events, err := repository.EventsAfter(t.Context(), runID, 0, 1000)
	if err != nil {
		t.Fatalf("load AssistantRun journal facts: %v", err)
	}
	receiptCount, err := database.Collection(
		"assistant_run_command_receipts",
	).CountDocuments(t.Context(), map[string]any{"runId": runID})
	if err != nil {
		t.Fatalf("count AssistantRun command receipts: %v", err)
	}
	run, err := repository.Load(t.Context(), runID)
	if err != nil {
		t.Fatalf("load AssistantRun facts: %v", err)
	}
	deviceReceipts := 0
	if run.Checkpoint != nil {
		deviceReceipts = len(run.Checkpoint.DeviceActionReceipts)
	}
	return assistantRunControlFacts{
		journalEvents:   len(events),
		commandReceipts: receiptCount,
		deviceReceipts:  deviceReceipts,
		revision:        run.Revision,
	}
}

func assertAssistantRunControlFactCounts(
	t *testing.T,
	database *mongo.Database,
	repository runruntime.Repository,
	runID string,
	want assistantRunControlFacts,
) {
	t.Helper()
	if got := assistantRunControlFactCounts(t, database, repository, runID); got != want {
		t.Fatalf("rejected HTTP command wrote facts: got=%+v want=%+v", got, want)
	}
}

func assertAssistantRunControlError(
	t *testing.T,
	recorder *httptest.ResponseRecorder,
	wantStatus int,
	wantCode string,
) {
	t.Helper()
	var failure struct {
		Code string `json:"code"`
	}
	if err := json.Unmarshal(recorder.Body.Bytes(), &failure); err != nil {
		t.Fatalf("decode AssistantRun failure: %v body=%s", err, recorder.Body)
	}
	if recorder.Code != wantStatus || failure.Code != wantCode {
		t.Fatalf(
			"AssistantRun failure status/code=%d/%s want=%d/%s body=%s",
			recorder.Code,
			failure.Code,
			wantStatus,
			wantCode,
			recorder.Body,
		)
	}
}

func cloneAssistantRunControlBody(value map[string]any) map[string]any {
	clone := make(map[string]any, len(value))
	for key, item := range value {
		clone[key] = item
	}
	return clone
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
		"assistant_run_hook_outbox",
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
