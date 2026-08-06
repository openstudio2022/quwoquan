// spec_ref: specs/feature-tree/product-ops-growth/event-ingestion-and-analytics/spec.md#sit-001
// readiness_case: report-event-batch-local
package local_contract

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"strconv"
	"strings"
	"testing"
	"time"

	"quwoquan_service/services/product-ops-service/internal/product_ops/event_record/application"
	telemetrypersistence "quwoquan_service/services/product-ops-service/internal/product_ops/event_record/infrastructure/persistence"
)

func TestTelemetryServiceAcceptsStrictBatchAndMasksSession(t *testing.T) {
	store := telemetrypersistence.NewMemoryTelemetryStore()
	service := application.NewTelemetryService(store, store)
	now := time.Now().UTC().Add(-2 * time.Minute)
	events := []application.EventRecordInput{
		validEvent("page_open", "event", now),
		validEvent("page_return", "event", now.Add(time.Second)),
	}
	events[0].NetworkClass = "5g"
	events[1].NetworkClass = "4g"
	duration := 1200
	events[1].DurationMS = &duration
	batchKey := digestKey("strict-batch")

	ack, err := service.ReportEventBatch(context.Background(), batchKey, events)
	if err != nil || ack.AcceptedCount != 2 || ack.DuplicateBatch {
		t.Fatalf("first batch ack=%+v err=%v", ack, err)
	}
	duplicate, err := service.ReportEventBatch(context.Background(), batchKey, events)
	if err != nil || !duplicate.DuplicateBatch || duplicate.AcceptedCount != 2 {
		t.Fatalf("duplicate batch ack=%+v err=%v", duplicate, err)
	}

	drilldown, err := service.GetEventDrilldown(context.Background(), application.EventDrilldownQuery{
		From:  now.Add(-time.Minute),
		To:    now.Add(time.Minute),
		Limit: 10,
	})
	if err != nil {
		t.Fatalf("drilldown: %v", err)
	}
	if drilldown.TotalCount != 2 || len(drilldown.Items) != 2 {
		t.Fatalf("drilldown=%+v", drilldown)
	}
	if !strings.HasPrefix(drilldown.Items[0].SessionID, "s.***.") {
		t.Fatalf("sessionId must be masked: %q", drilldown.Items[0].SessionID)
	}
}

func TestTrustedRuntimeLogBatchUsesTheSameDurableIdempotencyLedger(t *testing.T) {
	store := telemetrypersistence.NewMemoryTelemetryStore()
	service := application.NewRuntimeLogService(store, store)
	occurredAt := time.Now().UTC().Add(-time.Minute)
	fields := map[string]string{
		"schema":             "observability.slim",
		"recordId":           "runtime-log-ledger-test",
		"occurredAt":         occurredAt.Format(time.RFC3339Nano),
		"observedAt":         occurredAt.Format(time.RFC3339Nano),
		"logKind":            "exception",
		"severity":           "ERROR",
		"signal":             "service.exception.runtime",
		"message":            "dependency failure",
		"resourceSourceType": "service",
		"resourceService":    "product-ops-service",
	}
	batchKey := digestKey("trusted-runtime-log-batch")
	ack, err := service.ReportTrustedRuntimeLogBatch(
		context.Background(),
		batchKey,
		[]map[string]string{fields},
	)
	if err != nil || ack.AcceptedCount != 1 || ack.DuplicateBatch {
		t.Fatalf("first trusted runtime batch ack=%+v err=%v", ack, err)
	}
	replayed, err := service.ReportTrustedRuntimeLogBatch(
		context.Background(),
		batchKey,
		[]map[string]string{fields},
	)
	if err != nil || replayed.AcceptedCount != 1 || !replayed.DuplicateBatch {
		t.Fatalf("replayed trusted runtime batch ack=%+v err=%v", replayed, err)
	}
	summary, err := service.GetRuntimeLogSummary(
		context.Background(),
		application.RuntimeLogSummaryQuery{
			From: occurredAt.Add(-time.Minute),
			To:   occurredAt.Add(time.Minute),
		},
	)
	if err != nil || summary.TotalCount != 1 {
		t.Fatalf("trusted runtime batch must write one record: summary=%+v err=%v", summary, err)
	}
}

func TestRtcMediaQoeDrilldownPreservesSessionScopedTerminalFacts(t *testing.T) {
	store := telemetrypersistence.NewMemoryTelemetryStore()
	service := application.NewTelemetryService(store, store)
	occurredAt := time.Now().UTC().Add(-time.Minute)
	event := validEvent("rtc_media_qoe", "event", occurredAt)
	callType, result := "video", "connection_lost"
	participantCount, connectTimeMS, reconnectCount := 2, 842, 3
	mediaConnected := true
	disconnectReason, networkQuality := "unexpected_disconnect", "good"
	event.CallType = &callType
	event.Result = &result
	event.ParticipantCount = &participantCount
	event.ConnectTimeMS = &connectTimeMS
	event.MediaConnected = &mediaConnected
	event.ReconnectCount = &reconnectCount
	event.DisconnectReason = &disconnectReason
	event.NetworkQuality = &networkQuality
	if _, err := service.ReportEventBatch(
		context.Background(),
		digestKey("rtc-media-qoe-drilldown"),
		[]application.EventRecordInput{event},
	); err != nil {
		t.Fatalf("report rtc_media_qoe: %v", err)
	}

	drilldown, err := service.GetEventDrilldown(
		context.Background(),
		application.EventDrilldownQuery{
			EventType: "rtc_media_qoe",
			SessionID: event.SessionID,
			From:      occurredAt.Add(-time.Minute),
			To:        occurredAt.Add(time.Minute),
			Limit:     1,
		},
	)
	if err != nil {
		t.Fatalf("session-scoped rtc_media_qoe drilldown: %v", err)
	}
	if len(drilldown.Items) != 1 {
		t.Fatalf("drilldown items = %d; want 1", len(drilldown.Items))
	}
	item := drilldown.Items[0]
	if item.Result == nil || *item.Result != result ||
		item.CallType == nil || *item.CallType != callType ||
		item.ParticipantCount == nil || *item.ParticipantCount != participantCount ||
		item.ConnectTimeMS == nil || *item.ConnectTimeMS != connectTimeMS ||
		item.MediaConnected == nil || *item.MediaConnected != mediaConnected ||
		item.ReconnectCount == nil || *item.ReconnectCount != reconnectCount ||
		item.DisconnectReason == nil || *item.DisconnectReason != disconnectReason ||
		item.NetworkQuality == nil || *item.NetworkQuality != networkQuality {
		t.Fatalf("rtc_media_qoe drilldown lost terminal facts: %+v", item)
	}
	if item.SessionID == event.SessionID || !strings.HasPrefix(item.SessionID, "s.***.") {
		t.Fatalf("sessionId must remain masked: %q", item.SessionID)
	}
}

func TestTelemetryServiceRejectsWholeBatchBeforeWrite(t *testing.T) {
	store := telemetrypersistence.NewMemoryTelemetryStore()
	service := application.NewTelemetryService(store, store)
	now := time.Now().UTC().Add(-time.Minute)
	valid := validEvent("page_open", "event", now)
	invalid := validEvent("page_open", "event", now)
	invalid.NetworkClass = "vpn"

	if _, err := service.ReportEventBatch(context.Background(), digestKey("invalid-batch"), []application.EventRecordInput{valid, invalid}); err == nil {
		t.Fatal("unknown networkClass must reject the whole batch")
	}
	summary, err := service.GetEventSummary(context.Background(), application.EventSummaryQuery{
		From: now.Add(-time.Hour),
		To:   time.Now().UTC(),
	})
	if err != nil {
		t.Fatalf("summary: %v", err)
	}
	if summary.TotalCount != 0 {
		t.Fatalf("invalid batch must not partially write: %+v", summary)
	}
}

func TestTelemetryGeneratedInputAcceptsCataloguedProductAndChatExtensions(t *testing.T) {
	store := telemetrypersistence.NewMemoryTelemetryStore()
	service := application.NewTelemetryService(store, store)
	now := time.Now().UTC().Add(-time.Minute)
	productAction := validEvent("product_action", "event", now)
	journey, action := "chat_group", "create"
	objectType, objectID := "conversation", "opaque-object-id"
	targetType, targetID := "conversation", "opaque-target-id"
	productAction.Journey = &journey
	productAction.Action = &action
	productAction.ObjectType = &objectType
	productAction.ObjectID = &objectID
	productAction.TargetType = &targetType
	productAction.TargetID = &targetID

	chatOutcome := validEvent("chat_interaction_outcome", "event", now)
	chatAction, outcome := "group_create", "succeeded"
	source, memberBucket := "circle", "two_to_five"
	chatOutcome.ChatAction = &chatAction
	chatOutcome.ChatOutcome = &outcome
	chatOutcome.ChatSource = &source
	chatOutcome.MemberCountBucket = &memberBucket

	ack, err := service.ReportEventBatch(
		context.Background(),
		digestKey("generated-event-input-catalog"),
		[]application.EventRecordInput{productAction, chatOutcome},
	)
	if err != nil || ack.AcceptedCount != 2 {
		t.Fatalf("catalogued product/chat extensions must be accepted: ack=%+v err=%v", ack, err)
	}
}

func TestTelemetryGeneratedInputAcceptsLoginFunnelAndOperationExtensions(t *testing.T) {
	store := telemetrypersistence.NewMemoryTelemetryStore()
	service := application.NewTelemetryService(store, store)
	now := time.Now().UTC().Add(-time.Minute)

	flowID, step, result := "login-flow-1", "otp", "failure"
	action, entryMode := "otp_verify", "required"
	fromStep, toStep := "phoneEntry", "otp"
	provider, otpPurpose := "wechat", "login"
	consentState, countdownBucket := "accepted", "one_to_thirty"
	dismissPolicy := "return_to_origin"
	durationMS, attemptIndex, motionReduced := 850, 1, false
	funnel := validEvent("login_funnel", "event", now)
	funnel.PageName = "login"
	funnel.FlowID = &flowID
	funnel.Step = &step
	funnel.Result = &result
	funnel.Action = &action
	funnel.EntryMode = &entryMode
	funnel.FromStep = &fromStep
	funnel.ToStep = &toStep
	funnel.Provider = &provider
	funnel.OtpPurpose = &otpPurpose
	funnel.ConsentState = &consentState
	funnel.CountdownBucket = &countdownBucket
	funnel.DismissPolicy = &dismissPolicy
	funnel.DurationMS = &durationMS
	funnel.AttemptIndex = &attemptIndex
	funnel.MotionReduced = &motionReduced

	operationID, surfaceID := "otp_verify", "login_otp"
	failureKind, recoveryAction := "network", "retry_verify"
	copyKey, feedbackSurface := "otpVerifyUnavailable", "inline"
	requestID, traceID := "request-1", "trace-1"
	operation := validEvent("login_operation", "event", now.Add(time.Second))
	operation.PageName = "login"
	operation.OperationID = &operationID
	operation.SurfaceID = &surfaceID
	operation.Result = &result
	operation.FlowID = &flowID
	operation.Step = &step
	operation.Provider = &provider
	operation.OtpPurpose = &otpPurpose
	operation.FailureKind = &failureKind
	operation.RecoveryAction = &recoveryAction
	operation.CopyKey = &copyKey
	operation.FeedbackSurface = &feedbackSurface
	operation.DurationMS = &durationMS
	operation.AttemptIndex = &attemptIndex
	operation.RequestID = &requestID
	operation.TraceID = &traceID

	body, err := json.Marshal(struct {
		Events []application.EventRecordInput `json:"events"`
	}{Events: []application.EventRecordInput{funnel, operation}})
	if err != nil {
		t.Fatalf("encode login event batch: %v", err)
	}
	var decoded struct {
		Events []application.EventRecordInput `json:"events"`
	}
	decoder := json.NewDecoder(bytes.NewReader(body))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&decoded); err != nil {
		t.Fatalf("strict login event decode: %v", err)
	}

	ack, err := service.ReportEventBatch(
		context.Background(),
		digestKey("generated-login-event-input-catalog"),
		decoded.Events,
	)
	if err != nil || ack.AcceptedCount != 2 {
		t.Fatalf("catalogued login extensions must be accepted: ack=%+v err=%v", ack, err)
	}

	extensions := operation.ExtensionValues()
	if extensions["copyKey"] != copyKey || extensions["feedbackSurface"] != feedbackSurface {
		t.Fatalf("login operation lost observable feedback identity: %+v", extensions)
	}
	for _, forbidden := range []string{"phone", "phoneNumber", "otp", "bindingTicket", "providerTicket", "token"} {
		if _, ok := extensions[forbidden]; ok {
			t.Fatalf("login telemetry must not contain sensitive field %q", forbidden)
		}
	}
}

func TestTelemetryGeneratedInputStrictlyRejectsUndeclaredExtensions(t *testing.T) {
	validBody := []byte(`{"events":[{"logType":"event","eventType":"chat_interaction_outcome","sessionId":"s.Z3Vlc3RfdGVzdA.1","pageName":"chat_detail","occurredAt":"2026-07-21T01:00:00Z","deviceManufacturer":"Apple","deviceModel":"iPhone","appVersion":"1.0.0","networkClass":"wifi","devicePlatform":"ios","chatAction":"mention_send","chatOutcome":"succeeded","mentionScope":"member"}]}`)
	var accepted struct {
		Events []application.EventRecordInput `json:"events"`
	}
	decoder := json.NewDecoder(bytes.NewReader(validBody))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&accepted); err != nil {
		t.Fatalf("catalogued chat event must decode: %v", err)
	}
	if len(accepted.Events) != 1 || accepted.Events[0].ChatAction == nil {
		t.Fatalf("decoded chat event lost typed extension: %+v", accepted.Events)
	}

	invalidBody := []byte(`{"events":[{"logType":"event","eventType":"chat_interaction_outcome","sessionId":"s.Z3Vlc3RfdGVzdA.1","pageName":"chat_detail","occurredAt":"2026-07-21T01:00:00Z","deviceManufacturer":"Apple","deviceModel":"iPhone","appVersion":"1.0.0","networkClass":"wifi","devicePlatform":"ios","chatAction":"mention_send","chatOutcome":"succeeded","conversationId":"forbidden"}]}`)
	decoder = json.NewDecoder(bytes.NewReader(invalidBody))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&accepted); err == nil {
		t.Fatal("undeclared conversationId must fail strict event decoding")
	}
}

func TestTelemetryIngestionAcceptsCellularGenerationsAndRejectsRemovedVPNValue(t *testing.T) {
	store := telemetrypersistence.NewMemoryTelemetryStore()
	service := application.NewTelemetryService(store, store)
	occurredAt := time.Now().UTC().Add(-time.Minute)
	event := application.EventRecordInput{
		LogType:            "event",
		EventType:          "page_open",
		SessionID:          "s.Z3Vlc3RfaW50ZWdyYXRpb24." + strconv.FormatInt(occurredAt.UnixMilli(), 10),
		PageName:           "home",
		OccurredAt:         occurredAt.Format(time.RFC3339Nano),
		DeviceManufacturer: "Apple",
		DeviceModel:        "iPhone",
		AppVersion:         "1.0.0",
		NetworkClass:       "5g",
		DevicePlatform:     "ios",
	}
	if _, err := service.ReportEventBatch(
		context.Background(),
		digestKey("cellular-generation"),
		[]application.EventRecordInput{event},
	); err != nil {
		t.Fatalf("5g telemetry event must be accepted: %v", err)
	}

	event.NetworkClass = "vpn"
	if _, err := service.ReportEventBatch(
		context.Background(),
		digestKey("removed-vpn"),
		[]application.EventRecordInput{event},
	); err == nil {
		t.Fatal("removed networkClass vpn must be rejected")
	}
}

func TestTelemetryServiceRejectsCatalogSessionTimeAndRequiredExtensionViolations(t *testing.T) {
	now := time.Now().UTC()
	tests := map[string]application.EventRecordInput{
		"unknown event": func() application.EventRecordInput {
			event := validEvent("not_registered", "event", now)
			return event
		}(),
		"unknown page": func() application.EventRecordInput {
			event := validEvent("page_open", "event", now)
			event.PageName = "not_registered"
			return event
		}(),
		"unknown device platform": func() application.EventRecordInput {
			event := validEvent("page_open", "event", now)
			event.DevicePlatform = "phone_brand"
			return event
		}(),
		"invalid session": func() application.EventRecordInput {
			event := validEvent("page_open", "event", now)
			event.SessionID = "s.raw.user.1"
			return event
		}(),
		"expired event": func() application.EventRecordInput {
			return validEvent("page_open", "event", now.Add(-73*time.Hour))
		}(),
		"missing errorCode": func() application.EventRecordInput {
			return validEvent("runtime_exception", "error", now)
		}(),
	}
	for name, event := range tests {
		t.Run(name, func(t *testing.T) {
			store := telemetrypersistence.NewMemoryTelemetryStore()
			service := application.NewTelemetryService(store, store)
			if _, err := service.ReportEventBatch(context.Background(), digestKey(name), []application.EventRecordInput{event}); err == nil {
				t.Fatalf("%s must be rejected", name)
			}
		})
	}
}

func TestStartupDiagnosticsUseIndependentIdempotentBatch(t *testing.T) {
	store := telemetrypersistence.NewMemoryTelemetryStore()
	service := application.NewTelemetryService(store, store)
	records := []application.StartupDiagnosticRecord{{
		EventID: "attempt_000000000001_1", AttemptID: "attempt_000000000001",
		Phase: "router_ready", Outcome: "ready", OccurredAt: time.Now().UTC().Format(time.RFC3339Nano),
		Platform: "ios", RuntimeEnv: "alpha", Sequence: 1, PhaseDurationMS: 120, ElapsedMS: 200,
	}}
	first, err := service.ReportStartupDiagnostics(context.Background(), "proof_000000000000000001", records)
	if err != nil || first.DuplicateBatch {
		t.Fatalf("first startup batch=%+v err=%v", first, err)
	}
	second, err := service.ReportStartupDiagnostics(context.Background(), "proof_000000000000000001", records)
	if err != nil || !second.DuplicateBatch {
		t.Fatalf("duplicate startup batch=%+v err=%v", second, err)
	}
}

func TestStartupDiagnosticsSameProofDoesNotCollapseDistinctBatch(t *testing.T) {
	store := telemetrypersistence.NewMemoryTelemetryStore()
	service := application.NewTelemetryService(store, store)
	now := time.Now().UTC().Add(-time.Minute)
	firstRecord := application.StartupDiagnosticRecord{
		EventID: "attempt_000000000002_1", AttemptID: "attempt_000000000002",
		Phase: "dart_bootstrap", Outcome: "started", OccurredAt: now.Format(time.RFC3339Nano),
		Platform: "android", RuntimeEnv: "alpha", Sequence: 1,
	}
	secondRecord := firstRecord
	secondRecord.EventID = "attempt_000000000002_2"
	secondRecord.Sequence = 2
	secondRecord.Phase = "router_ready"

	first, err := service.ReportStartupDiagnostics(
		context.Background(),
		"proof_shared_across_attempt_flushes",
		[]application.StartupDiagnosticRecord{firstRecord},
	)
	if err != nil || first.DuplicateBatch {
		t.Fatalf("first batch=%+v err=%v", first, err)
	}
	second, err := service.ReportStartupDiagnostics(
		context.Background(),
		"proof_shared_across_attempt_flushes",
		[]application.StartupDiagnosticRecord{secondRecord},
	)
	if err != nil || second.DuplicateBatch {
		t.Fatalf("distinct batch must not be duplicate=%+v err=%v", second, err)
	}
}

func TestStartupDiagnosticsRecoveryDimensionsArePartOfBatchIdentity(t *testing.T) {
	store := telemetrypersistence.NewMemoryTelemetryStore()
	service := application.NewTelemetryService(store, store)
	firstRecord := application.StartupDiagnosticRecord{
		EventID: "attempt_000000000003_1", AttemptID: "attempt_000000000003",
		Phase: "recovery", Outcome: "observed", OccurredAt: time.Now().UTC().Format(time.RFC3339Nano),
		Platform: "android", RuntimeEnv: "gamma", Sequence: 1,
		RecoverySurface: "page.app.startup_recovery", RecoveryLifecycle: "phase_change",
		RecoveryMount: "bootstrap", RecoveryPhase: "startup_checking", RecoveryAction: "none",
	}
	secondRecord := firstRecord
	secondRecord.RecoveryMount = "runtime_boundary"
	secondRecord.RecoveryPhase = "runtime_version_checking"

	first, err := service.ReportStartupDiagnostics(
		context.Background(),
		"proof_shared_across_recovery_transitions",
		[]application.StartupDiagnosticRecord{firstRecord},
	)
	if err != nil || first.DuplicateBatch {
		t.Fatalf("first recovery batch=%+v err=%v", first, err)
	}
	second, err := service.ReportStartupDiagnostics(
		context.Background(),
		"proof_shared_across_recovery_transitions",
		[]application.StartupDiagnosticRecord{secondRecord},
	)
	if err != nil || second.DuplicateBatch {
		t.Fatalf("distinct recovery dimensions collapsed batch=%+v err=%v", second, err)
	}
}

func TestTelemetryServiceAcceptsTypedVideoPlaybackQoeWithoutContentAttribution(t *testing.T) {
	store := telemetrypersistence.NewMemoryTelemetryStore()
	service := application.NewTelemetryService(store, store)
	now := time.Now().UTC().Add(-time.Minute)
	readyMS, rebufferCount, rebufferMS, seekCount := 420, 1, 180, 2
	effectivePlaybackMS := 12000
	seekFailureCount, seekCommandMaxMS, seekSettleMaxMS := 0, 80, 120
	droppedFrames, processedVideoFrames, audioUnderrunCount := 2, 300, 0
	rendererMode, decoderQueueMode, decoderFallbackEnabled := "platform_view", "synchronous", true
	seekEvidenceSource, playbackMode, result := "controller_command_completion", "autoplay", "success"
	event := validEvent("video_playback_qoe", "event", now)
	event.ReadyMS = &readyMS
	event.RebufferCount = &rebufferCount
	event.RebufferMS = &rebufferMS
	event.EffectivePlaybackMS = &effectivePlaybackMS
	event.SeekCount = &seekCount
	event.SeekFailureCount = &seekFailureCount
	event.SeekCommandMaxMS = &seekCommandMaxMS
	event.SeekSettleMaxMS = &seekSettleMaxMS
	event.DroppedFrames = &droppedFrames
	event.ProcessedVideoFrames = &processedVideoFrames
	event.AudioUnderrunCount = &audioUnderrunCount
	event.RendererMode = &rendererMode
	event.DecoderQueueMode = &decoderQueueMode
	event.DecoderFallbackEnabled = &decoderFallbackEnabled
	event.SeekEvidenceSource = &seekEvidenceSource
	event.PlaybackMode = &playbackMode
	event.Result = &result

	if _, err := service.ReportEventBatch(context.Background(), digestKey("video-qoe"), []application.EventRecordInput{event}); err != nil {
		t.Fatalf("report video qoe: %v", err)
	}
}

func TestTelemetryServiceRejectsUnknownVideoSeekEvidenceSource(t *testing.T) {
	store := telemetrypersistence.NewMemoryTelemetryStore()
	service := application.NewTelemetryService(store, store)
	now := time.Now().UTC().Add(-time.Minute)
	readyMS, rebufferCount, rebufferMS, seekCount := 420, 1, 180, 2
	effectivePlaybackMS := 12000
	seekFailureCount, seekCommandMaxMS, seekSettleMaxMS := 0, 80, 0
	seekEvidenceSource, playbackMode := "unregistered_source", "autoplay"
	event := validEvent("video_playback_qoe", "event", now)
	event.ReadyMS = &readyMS
	event.RebufferCount = &rebufferCount
	event.RebufferMS = &rebufferMS
	event.EffectivePlaybackMS = &effectivePlaybackMS
	event.SeekCount = &seekCount
	event.SeekFailureCount = &seekFailureCount
	event.SeekCommandMaxMS = &seekCommandMaxMS
	event.SeekSettleMaxMS = &seekSettleMaxMS
	event.SeekEvidenceSource = &seekEvidenceSource
	event.PlaybackMode = &playbackMode

	if _, err := service.ReportEventBatch(context.Background(), digestKey("invalid-video-qoe"), []application.EventRecordInput{event}); err == nil {
		t.Fatal("unregistered seek evidence source must be rejected")
	}
}

func validEvent(eventType, logType string, occurredAt time.Time) application.EventRecordInput {
	return application.EventRecordInput{
		LogType: logType, EventType: eventType,
		SessionID: "s.Z3Vlc3RfdGVzdA." + strconv.FormatInt(occurredAt.UnixMilli(), 10),
		PageName:  "home", OccurredAt: occurredAt.Format(time.RFC3339Nano),
		DeviceManufacturer: "Apple", DeviceModel: "iPhone",
		AppVersion: "1.0.0", NetworkClass: "wifi", DevicePlatform: "android",
	}
}

func digestKey(value string) string {
	digest := sha256.Sum256([]byte(value))
	return hex.EncodeToString(digest[:])
}
