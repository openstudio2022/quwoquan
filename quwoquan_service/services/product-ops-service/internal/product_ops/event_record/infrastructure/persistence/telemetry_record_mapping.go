package persistence

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"strconv"
	"strings"
	"time"

	"quwoquan_service/services/product-ops-service/internal/product_ops/event_record/application"
)

// eventRecordFields is the provider-neutral persisted projection for EventRecord.
// Every log sink adapter must consume this mapping so field names, privacy and
// batch identity cannot drift between Elasticsearch and SLS.
func eventRecordFields(record application.EventRecord) map[string]string {
	fields := map[string]string{
		"logType":            record.LogType,
		"eventType":          record.EventType,
		"sessionId":          record.SessionID,
		"pageName":           record.PageName,
		"occurredAt":         record.OccurredAt,
		"deviceManufacturer": record.DeviceManufacturer,
		"deviceModel":        record.DeviceModel,
		"appVersion":         record.AppVersion,
		"networkClass":       record.NetworkClass,
		"devicePlatform":     record.DevicePlatform,
		"_batchKey":          record.BatchKey,
		"_batchIndex":        strconv.Itoa(record.BatchIndex),
		"ingestedAt":         record.IngestedAt.UTC().Format(time.RFC3339Nano),
	}
	for key, value := range eventRecordExtensions(record.EventRecordInput) {
		fields[key] = value
	}
	return fields
}

func eventRecordExtensions(record application.EventRecordInput) map[string]string {
	out := map[string]string{}
	for name, value := range record.ExtensionValues() {
		switch typed := value.(type) {
		case string:
			out[name] = typed
		case int:
			out[name] = strconv.Itoa(typed)
		case float64:
			out[name] = strconv.FormatFloat(typed, 'f', -1, 64)
		case bool:
			out[name] = strconv.FormatBool(typed)
		case []string:
			encoded, _ := json.Marshal(typed)
			out[name] = string(encoded)
		}
	}
	return out
}

func rawRecordWaterline(rows []map[string]string, now time.Time) (string, int64) {
	var generatedThrough string
	var lagSeconds int64
	for _, row := range rows {
		value := strings.TrimSpace(row["ingestedAt"])
		if value == "" {
			continue
		}
		if value > generatedThrough {
			generatedThrough = value
		}
		if timestamp, err := time.Parse(time.RFC3339Nano, value); err == nil {
			lag := int64(now.Sub(timestamp).Seconds())
			if lag > lagSeconds {
				lagSeconds = lag
			}
		}
	}
	return generatedThrough, lagSeconds
}

func decodeEventDrilldownFields(
	row map[string]string,
	revealSession bool,
) application.EventDrilldownItem {
	parseInt := func(name string) *int {
		value, err := strconv.Atoi(row[name])
		if err != nil {
			return nil
		}
		return &value
	}
	parseString := func(name string) *string {
		value := row[name]
		if value == "" {
			return nil
		}
		return &value
	}
	parseBool := func(name string) *bool {
		value, err := strconv.ParseBool(row[name])
		if err != nil {
			return nil
		}
		return &value
	}
	stack := []string(nil)
	if raw := row["callStack"]; raw != "" {
		_ = json.Unmarshal([]byte(raw), &stack)
	}
	sessionID := row["sessionId"]
	if !revealSession {
		sessionID = maskSessionID(sessionID)
	}
	digest := sha256.Sum256([]byte(row["_batchKey"] + ":" + row["_batchIndex"]))
	return application.EventDrilldownItem{
		RowKey:                 hex.EncodeToString(digest[:8]),
		LogType:                row["logType"],
		EventType:              row["eventType"],
		SessionID:              sessionID,
		PageName:               row["pageName"],
		OccurredAt:             row["occurredAt"],
		DeviceManufacturer:     row["deviceManufacturer"],
		DeviceModel:            row["deviceModel"],
		AppVersion:             row["appVersion"],
		NetworkClass:           row["networkClass"],
		DevicePlatform:         row["devicePlatform"],
		DurationMS:             parseInt("durationMs"),
		Result:                 parseString("result"),
		FailReasonCode:         parseString("failReasonCode"),
		ErrorCode:              parseString("errorCode"),
		OperationID:            parseString("operationId"),
		RequestID:              parseString("requestId"),
		TraceID:                parseString("traceId"),
		RecoveryAction:         parseString("recoveryAction"),
		SurfaceID:              parseString("surfaceId"),
		DetectionSource:        parseString("detectionSource"),
		TerminalState:          parseString("terminalState"),
		HTTPStatus:             parseInt("httpStatus"),
		CallStack:              stack,
		TClickToFirstFrameMS:   parseInt("tClickToFirstFrameMs"),
		TFirstFrameToShellMS:   parseInt("tFirstFrameToShellMs"),
		TShellToContentMS:      parseInt("tShellToContentMs"),
		TClickToContentMS:      parseInt("tClickToContentMs"),
		HasError:               parseBool("hasError"),
		Journey:                parseString("journey"),
		Action:                 parseString("action"),
		ReadyMS:                parseInt("readyMs"),
		TTFFMS:                 parseInt("ttffMs"),
		RebufferCount:          parseInt("rebufferCount"),
		RebufferMS:             parseInt("rebufferMs"),
		EffectivePlaybackMS:    parseInt("effectivePlaybackMs"),
		SeekCount:              parseInt("seekCount"),
		SeekFailureCount:       parseInt("seekFailureCount"),
		SeekCommandMaxMS:       parseInt("seekCommandMaxMs"),
		SeekSettleMaxMS:        parseInt("seekSettleMaxMs"),
		DroppedFrames:          parseInt("droppedFrames"),
		ProcessedVideoFrames:   parseInt("processedVideoFrames"),
		AudioUnderrunCount:     parseInt("audioUnderrunCount"),
		RendererMode:           parseString("rendererMode"),
		DecoderQueueMode:       parseString("decoderQueueMode"),
		DecoderFallbackEnabled: parseBool("decoderFallbackEnabled"),
		SeekEvidenceSource:     parseString("seekEvidenceSource"),
		DeclaredDurationMS:     parseInt("declaredDurationMs"),
		ObservedDurationMS:     parseInt("observedDurationMs"),
		DurationMismatch:       parseBool("durationMismatch"),
		PlaybackMode:           parseString("playbackMode"),
		IngestedAt:             row["ingestedAt"],
	}
}

func decodeRuntimeLogDrilldownFields(
	row map[string]string,
	revealCorrelation bool,
) application.RuntimeLogDrilldownItem {
	digest := sha256.Sum256([]byte(row["_batchKey"] + ":" + row["_batchIndex"]))
	resource := map[string]string{
		"sourceType": row["resourceSourceType"],
		"service":    row["resourceService"],
	}
	for raw, key := range map[string]string{
		"resourceEnvironment":    "environment",
		"resourceComponent":      "component",
		"resourceAppVersion":     "appVersion",
		"resourceServiceVersion": "service.version",
	} {
		if row[raw] != "" {
			resource[key] = row[raw]
		}
	}
	correlation := map[string]string{}
	if revealCorrelation {
		for _, key := range []string{
			"requestId",
			"traceId",
			"spanId",
			"operationId",
			"pageName",
			"surfaceId",
			"executionId",
			"workPackageId",
			"environmentRunId",
		} {
			if row[key] != "" {
				correlation[key] = row[key]
			}
		}
	}
	attributes := map[string]string{}
	if raw := row["attributes"]; raw != "" {
		_ = json.Unmarshal([]byte(raw), &attributes)
	}
	return application.RuntimeLogDrilldownItem{
		RowKey:      hex.EncodeToString(digest[:8]),
		RecordID:    row["recordId"],
		OccurredAt:  row["occurredAt"],
		ObservedAt:  row["observedAt"],
		LogKind:     row["logKind"],
		Severity:    row["severity"],
		Signal:      row["signal"],
		Message:     row["message"],
		ErrorCode:   row["errorCode"],
		Fingerprint: row["fingerprint"],
		Resource:    resource,
		Correlation: correlation,
		Attributes:  attributes,
		IngestedAt:  row["ingestedAt"],
	}
}
