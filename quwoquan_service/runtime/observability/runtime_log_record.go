package runtimeobservability

import (
	cryptorand "crypto/rand"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"sync/atomic"
	"time"
	"unicode/utf8"
)

var runtimeLogRecordSequence uint64

type runtimeLogResource struct {
	SourceType     string `json:"sourceType"`
	Service        string `json:"service"`
	Environment    string `json:"environment,omitempty"`
	Component      string `json:"component,omitempty"`
	AppVersion     string `json:"appVersion,omitempty"`
	ServiceVersion string `json:"service.version,omitempty"`
}

type runtimeLogCorrelation struct {
	RequestID        string `json:"requestId,omitempty"`
	TraceID          string `json:"traceId,omitempty"`
	SpanID           string `json:"spanId,omitempty"`
	OperationID      string `json:"operationId,omitempty"`
	PageName         string `json:"pageName,omitempty"`
	SurfaceID        string `json:"surfaceId,omitempty"`
	ExecutionID      string `json:"executionId,omitempty"`
	WorkPackageID    string `json:"workPackageId,omitempty"`
	EnvironmentRunID string `json:"environmentRunId,omitempty"`
	// ActorHash 是隐私安全的用户维度关联键（与遥测 actorHash 同派生），
	// 支持"按用户查日志"；raw userId 仍被 privacy 策略禁止。
	ActorHash string `json:"actorHash,omitempty"`
}

type runtimeLogRecord struct {
	Schema      string                 `json:"schema"`
	RecordID    string                 `json:"recordId,omitempty"`
	OccurredAt  string                 `json:"occurredAt"`
	ObservedAt  string                 `json:"observedAt"`
	LogKind     string                 `json:"logKind"`
	Severity    string                 `json:"severity"`
	Signal      string                 `json:"signal"`
	Message     string                 `json:"message"`
	Resource    runtimeLogResource     `json:"resource"`
	Correlation *runtimeLogCorrelation `json:"correlation,omitempty"`
	Step        string                 `json:"step,omitempty"`
	Event       string                 `json:"event,omitempty"`
	Result      string                 `json:"result,omitempty"`
	Method      string                 `json:"method,omitempty"`
	Route       string                 `json:"route,omitempty"`
	Status      string                 `json:"status,omitempty"`
	DurationMS  *int64                 `json:"durationMs,omitempty"`
	Action      string                 `json:"action,omitempty"`
	Target      string                 `json:"target,omitempty"`
	ErrorCode   string                 `json:"errorCode,omitempty"`
	Fingerprint string                 `json:"fingerprint,omitempty"`
	Attributes  map[string]string      `json:"attributes,omitempty"`
}

func formatCanonicalRuntimeLog(kind string, payload map[string]any) string {
	record, err := newRuntimeLogRecord(kind, payload)
	if err != nil {
		return emergencyRuntimeLog("runtime log encoding failed")
	}
	encoded, err := json.Marshal(record)
	if err != nil {
		return emergencyRuntimeLog("runtime log serialization failed")
	}
	return string(encoded)
}

func newRuntimeLogRecord(kind string, payload map[string]any) (runtimeLogRecord, error) {
	if _, ok := CatalogLogKinds[kind]; !ok {
		return runtimeLogRecord{}, fmt.Errorf("unknown runtime log kind %q", kind)
	}
	occurredAt := firstNonEmpty(stringValue(payload["occurredAt"]), stringValue(payload["ts"]))
	if occurredAt == "" {
		occurredAt = time.Now().UTC().Format(time.RFC3339Nano)
	}
	observedAt := firstNonEmpty(stringValue(payload["observedAt"]), occurredAt)
	resource := runtimeLogResourceFrom(payload["resource"])
	correlationValue := runtimeLogCorrelationFrom(payload["correlation"])
	if correlationValue.RequestID == "" {
		correlationValue.RequestID = stringValue(payload["req"])
	}
	if correlationValue.TraceID == "" {
		correlationValue.TraceID = stringValue(payload["trace"])
	}
	signal := firstNonEmpty(stringValue(payload["signal"]), defaultServiceSignal(kind))
	signalContract, registered := CatalogSignalRegistry[signal]
	if !registered {
		return runtimeLogRecord{}, fmt.Errorf("unregistered runtime log signal %q", signal)
	}
	if signalContract.LogKind != kind {
		return runtimeLogRecord{}, fmt.Errorf("runtime log signal %q does not match kind %q", signal, kind)
	}
	var correlation *runtimeLogCorrelation
	if !correlationValue.empty() {
		if err := validateRuntimeLogCorrelation(correlationValue, signalContract.CorrelationKeys); err != nil {
			return runtimeLogRecord{}, err
		}
		correlation = &correlationValue
	}
	durationMS := optionalInt64Value(payload["durationMs"], payload["durMs"])
	attributes, err := runtimeLogAttributes(
		mapValue(payload["attrs"], payload["attributes"]),
		signalContract.AttributeAllowlist,
		runtimeLogObjectID(correlationValue.OperationID),
	)
	if err != nil {
		return runtimeLogRecord{}, err
	}
	recordID := stringValue(payload["recordId"])
	if recordID == "" {
		recordID = nextRuntimeLogRecordID()
	}
	record := runtimeLogRecord{
		Schema:      ObservabilitySchema,
		RecordID:    recordID,
		OccurredAt:  occurredAt,
		ObservedAt:  observedAt,
		LogKind:     kind,
		Severity:    strings.ToUpper(firstNonEmpty(stringValue(payload["severity"]), stringValue(payload["level"]), "INFO")),
		Signal:      signal,
		Message:     boundedRuntimeLogText(firstNonEmpty(stringValue(payload["message"]), stringValue(payload["msg"]), kind), CatalogMaxMessageBytes),
		Resource:    resource,
		Correlation: correlation,
		Step:        stringValue(payload["step"]),
		Event:       stringValue(payload["event"]),
		Result:      stringValue(payload["result"]),
		Method:      stringValue(payload["method"]),
		Route:       stringValue(payload["route"]),
		Status:      stringValue(payload["status"]),
		DurationMS:  durationMS,
		Action:      stringValue(payload["action"]),
		Target:      stringValue(payload["target"]),
		ErrorCode:   firstNonEmpty(stringValue(payload["errorCode"]), stringValue(payload["err"])),
		Fingerprint: stringValue(payload["fingerprint"]),
		Attributes:  attributes,
	}
	if _, ok := CatalogSeverityLevels[record.Severity]; !ok {
		return runtimeLogRecord{}, fmt.Errorf("invalid runtime log severity %q", record.Severity)
	}
	if record.Resource.SourceType == "" || record.Resource.Service == "" {
		return runtimeLogRecord{}, fmt.Errorf("runtime log resource is incomplete")
	}
	for field := range CatalogRequiredFields[kind] {
		if !runtimeLogFieldPresent(record, field) {
			return runtimeLogRecord{}, fmt.Errorf("runtime log %s is missing %s", kind, field)
		}
	}
	return record, nil
}

// CanonicalRuntimeLogFields 严格验证外部 runtime log wire 后返回适合写入
// append-only logstore 的扁平字段。它是 Product Ops ingestion 与服务侧日志
// exporter 共用的唯一解析边界，禁止各调用方自行接受自由 JSON。
func CanonicalRuntimeLogFields(payload map[string]any) (map[string]string, error) {
	if err := validateCanonicalRuntimeLogWire(payload); err != nil {
		return nil, err
	}
	kind := stringValue(payload["logKind"])
	record, err := newRuntimeLogRecord(kind, payload)
	if err != nil {
		return nil, err
	}
	fields := map[string]string{
		"schema":             record.Schema,
		"recordId":           record.RecordID,
		"occurredAt":         record.OccurredAt,
		"observedAt":         record.ObservedAt,
		"logKind":            record.LogKind,
		"severity":           record.Severity,
		"signal":             record.Signal,
		"message":            record.Message,
		"resourceSourceType": record.Resource.SourceType,
		"resourceService":    record.Resource.Service,
	}
	for key, value := range map[string]string{
		"resourceEnvironment":    record.Resource.Environment,
		"resourceComponent":      record.Resource.Component,
		"resourceAppVersion":     record.Resource.AppVersion,
		"resourceServiceVersion": record.Resource.ServiceVersion,
		"step":                   record.Step,
		"event":                  record.Event,
		"result":                 record.Result,
		"method":                 record.Method,
		"route":                  record.Route,
		"status":                 record.Status,
		"action":                 record.Action,
		"target":                 record.Target,
		"errorCode":              record.ErrorCode,
		"fingerprint":            record.Fingerprint,
	} {
		if value != "" {
			fields[key] = value
		}
	}
	if record.DurationMS != nil {
		fields["durationMs"] = strconv.FormatInt(*record.DurationMS, 10)
	}
	if record.Correlation != nil {
		for key, value := range map[string]string{
			"requestId":        record.Correlation.RequestID,
			"traceId":          record.Correlation.TraceID,
			"spanId":           record.Correlation.SpanID,
			"operationId":      record.Correlation.OperationID,
			"pageName":         record.Correlation.PageName,
			"surfaceId":        record.Correlation.SurfaceID,
			"executionId":      record.Correlation.ExecutionID,
			"workPackageId":    record.Correlation.WorkPackageID,
			"environmentRunId": record.Correlation.EnvironmentRunID,
			"actorHash":        record.Correlation.ActorHash,
		} {
			if value != "" {
				fields[key] = value
			}
		}
	}
	if len(record.Attributes) > 0 {
		encoded, _ := json.Marshal(record.Attributes)
		fields["attributes"] = string(encoded)
	}
	return fields, nil
}

func validateCanonicalRuntimeLogWire(payload map[string]any) error {
	if len(payload) == 0 {
		return fmt.Errorf("runtime log payload is empty")
	}
	allowed := make(map[string]struct{}, len(CatalogEnvelopeRequiredFields)+len(CatalogEnvelopeOptionalFields))
	for _, key := range CatalogEnvelopeRequiredFields {
		allowed[key] = struct{}{}
	}
	for _, key := range CatalogEnvelopeOptionalFields {
		allowed[key] = struct{}{}
	}
	for key := range payload {
		if _, ok := allowed[key]; !ok {
			return fmt.Errorf("runtime log has unregistered field %q", key)
		}
		if _, forbidden := CatalogForbiddenFields[key]; forbidden {
			return fmt.Errorf("runtime log has forbidden field %q", key)
		}
	}
	if stringValue(payload["schema"]) != ObservabilitySchema {
		return fmt.Errorf("runtime log schema is invalid")
	}
	for _, key := range CatalogEnvelopeRequiredFields {
		if key == "resource" {
			continue
		}
		if stringValue(payload[key]) == "" {
			return fmt.Errorf("runtime log misses required %s", key)
		}
	}
	if _, err := time.Parse(time.RFC3339Nano, stringValue(payload["occurredAt"])); err != nil {
		return fmt.Errorf("runtime log occurredAt is invalid: %w", err)
	}
	if _, err := time.Parse(time.RFC3339Nano, stringValue(payload["observedAt"])); err != nil {
		return fmt.Errorf("runtime log observedAt is invalid: %w", err)
	}
	if utf8.RuneCountInString(stringValue(payload["message"])) == 0 ||
		len(stringValue(payload["message"])) > CatalogMaxMessageBytes {
		return fmt.Errorf("runtime log message exceeds limit")
	}
	resource, ok := payload["resource"].(map[string]any)
	if !ok {
		return fmt.Errorf("runtime log resource must be an object")
	}
	if err := validateRuntimeLogObject(resource, CatalogResourceRequiredFields, CatalogResourceOptionalFields); err != nil {
		return fmt.Errorf("runtime log resource: %w", err)
	}
	if correlationValue, present := payload["correlation"]; present {
		correlation, ok := correlationValue.(map[string]any)
		if !ok {
			return fmt.Errorf("runtime log correlation must be an object")
		}
		if err := validateRuntimeLogObject(correlation, nil, CatalogCorrelationOptionalFields); err != nil {
			return fmt.Errorf("runtime log correlation: %w", err)
		}
	}
	signal := stringValue(payload["signal"])
	contract, registered := CatalogSignalRegistry[signal]
	if !registered {
		return fmt.Errorf("runtime log signal %q is not registered", signal)
	}
	if contract.LogKind != stringValue(payload["logKind"]) {
		return fmt.Errorf("runtime log signal %q does not match log kind", signal)
	}
	if attributesValue, present := payload["attributes"]; present {
		attributes, ok := attributesValue.(map[string]any)
		if !ok {
			return fmt.Errorf("runtime log attributes must be an object")
		}
		if len(attributes) > CatalogMaxAttributes {
			return fmt.Errorf("runtime log has too many attributes")
		}
		allowlist := make(map[string]struct{}, len(contract.AttributeAllowlist))
		for _, key := range contract.AttributeAllowlist {
			allowlist[key] = struct{}{}
		}
		for key, value := range attributes {
			if _, allowed := allowlist[key]; !allowed {
				return fmt.Errorf("runtime log attribute %q is not registered for signal", key)
			}
			if _, forbidden := CatalogForbiddenFields[key]; forbidden || forbiddenRuntimeLogAttributeKey(key) {
				return fmt.Errorf("runtime log attribute %q is forbidden", key)
			}
			text, isString := value.(string)
			if !isString || len(text) > CatalogMaxAttributeValueLength {
				return fmt.Errorf("runtime log attribute %q must be bounded string", key)
			}
		}
		if runtimeLogAttributesSize(stringMapFromAny(attributes)) > CatalogMaxAttributesBytes {
			return fmt.Errorf("runtime log attributes exceed size limit")
		}
	}
	if correlationValue, present := payload["correlation"]; present {
		correlation := correlationValue.(map[string]any)
		allowed := make(map[string]struct{}, len(contract.CorrelationKeys))
		for _, key := range contract.CorrelationKeys {
			allowed[key] = struct{}{}
		}
		for key := range correlation {
			if _, ok := allowed[key]; !ok {
				return fmt.Errorf("runtime log correlation key %q is not registered for signal", key)
			}
		}
	}
	return nil
}

func validateRuntimeLogObject(value map[string]any, required, optional []string) error {
	allowed := make(map[string]struct{}, len(required)+len(optional))
	for _, key := range required {
		allowed[key] = struct{}{}
	}
	for _, key := range optional {
		allowed[key] = struct{}{}
	}
	for key, item := range value {
		if _, ok := allowed[key]; !ok {
			return fmt.Errorf("unregistered field %q", key)
		}
		if _, forbidden := CatalogForbiddenFields[key]; forbidden {
			return fmt.Errorf("forbidden field %q", key)
		}
		if _, ok := item.(string); !ok {
			return fmt.Errorf("field %q must be a string", key)
		}
	}
	for _, key := range required {
		if stringValue(value[key]) == "" {
			return fmt.Errorf("required field %q is empty", key)
		}
	}
	return nil
}

func stringMapFromAny(value map[string]any) map[string]string {
	out := make(map[string]string, len(value))
	for key, item := range value {
		out[key], _ = item.(string)
	}
	return out
}

func runtimeLogResourceFrom(value any) runtimeLogResource {
	resource := runtimeLogResource{SourceType: "service", Service: "runtime-observability"}
	switch typed := value.(type) {
	case runtimeLogResource:
		resource = typed
	case map[string]string:
		resource.SourceType = firstNonEmpty(typed["sourceType"], resource.SourceType)
		resource.Service = firstNonEmpty(typed["service"], resource.Service)
		resource.Environment = typed["environment"]
		resource.Component = typed["component"]
		resource.AppVersion = typed["appVersion"]
		resource.ServiceVersion = typed["service.version"]
	case map[string]any:
		resource.SourceType = firstNonEmpty(stringValue(typed["sourceType"]), resource.SourceType)
		resource.Service = firstNonEmpty(stringValue(typed["service"]), resource.Service)
		resource.Environment = stringValue(typed["environment"])
		resource.Component = stringValue(typed["component"])
		resource.AppVersion = stringValue(typed["appVersion"])
		resource.ServiceVersion = stringValue(typed["service.version"])
	}
	return resource
}

func runtimeLogCorrelationFrom(value any) runtimeLogCorrelation {
	switch typed := value.(type) {
	case runtimeLogCorrelation:
		return typed
	case map[string]string:
		return runtimeLogCorrelation{
			RequestID:        typed["requestId"],
			TraceID:          typed["traceId"],
			SpanID:           typed["spanId"],
			OperationID:      typed["operationId"],
			PageName:         typed["pageName"],
			SurfaceID:        typed["surfaceId"],
			ExecutionID:      typed["executionId"],
			WorkPackageID:    typed["workPackageId"],
			EnvironmentRunID: typed["environmentRunId"],
			ActorHash:        typed["actorHash"],
		}
	case map[string]any:
		return runtimeLogCorrelation{
			RequestID:        stringValue(typed["requestId"]),
			TraceID:          stringValue(typed["traceId"]),
			SpanID:           stringValue(typed["spanId"]),
			OperationID:      stringValue(typed["operationId"]),
			PageName:         stringValue(typed["pageName"]),
			SurfaceID:        stringValue(typed["surfaceId"]),
			ExecutionID:      stringValue(typed["executionId"]),
			WorkPackageID:    stringValue(typed["workPackageId"]),
			EnvironmentRunID: stringValue(typed["environmentRunId"]),
			ActorHash:        stringValue(typed["actorHash"]),
		}
	default:
		return runtimeLogCorrelation{}
	}
}

func runtimeLogFieldPresent(record runtimeLogRecord, field string) bool {
	switch field {
	case "step":
		return record.Step != ""
	case "event":
		return record.Event != ""
	case "result":
		return record.Result != ""
	case "method":
		return record.Method != ""
	case "route":
		return record.Route != ""
	case "status":
		return record.Status != ""
	case "durationMs":
		return record.DurationMS != nil && *record.DurationMS >= 0
	case "action":
		return record.Action != ""
	case "target":
		return record.Target != ""
	case "errorCode":
		return record.ErrorCode != ""
	default:
		return false
	}
}

func defaultServiceSignal(kind string) string {
	switch kind {
	case "access":
		return "service.access.http"
	case "exception":
		return "service.exception.runtime"
	case "audit":
		return "service.audit.control"
	default:
		return "service.runtime.process"
	}
}

func stringValue(value any) string {
	if value == nil {
		return ""
	}
	return strings.TrimSpace(fmt.Sprint(value))
}

func optionalInt64Value(values ...any) *int64 {
	for _, value := range values {
		switch typed := value.(type) {
		case int:
			converted := int64(typed)
			return &converted
		case int64:
			return &typed
		case float64:
			converted := int64(typed)
			return &converted
		}
	}
	return nil
}

func mapValue(values ...any) map[string]any {
	for _, value := range values {
		switch typed := value.(type) {
		case map[string]any:
			if len(typed) > 0 {
				return typed
			}
		case map[string]string:
			if len(typed) > 0 {
				result := make(map[string]any, len(typed))
				for key, item := range typed {
					result[key] = item
				}
				return result
			}
		}
	}
	return nil
}

func (value runtimeLogCorrelation) empty() bool {
	return value.RequestID == "" &&
		value.TraceID == "" &&
		value.SpanID == "" &&
		value.OperationID == "" &&
		value.PageName == "" &&
		value.SurfaceID == "" &&
		value.ExecutionID == "" &&
		value.WorkPackageID == "" &&
		value.EnvironmentRunID == "" &&
		value.ActorHash == ""
}

func emergencyRuntimeLog(message string) string {
	now := time.Now().UTC().Format(time.RFC3339Nano)
	record := runtimeLogRecord{
		Schema:     ObservabilitySchema,
		RecordID:   nextRuntimeLogRecordID(),
		OccurredAt: now,
		ObservedAt: now,
		LogKind:    "exception",
		Severity:   "ERROR",
		Signal:     "service.exception.runtime",
		Message:    message,
		Resource: runtimeLogResource{
			SourceType: "service",
			Service:    "runtime-observability",
		},
		ErrorCode: CatalogFailureCodes["service_log_encoding"],
	}
	encoded, err := json.Marshal(record)
	if err != nil {
		return `{"schema":"observability.slim","occurredAt":"1970-01-01T00:00:00Z","observedAt":"1970-01-01T00:00:00Z","logKind":"exception","severity":"ERROR","signal":"service.exception.runtime","message":"runtime log failure","resource":{"sourceType":"service","service":"runtime-observability"},"errorCode":"SERVICE.RUNTIME.log_encoding_failed"}`
	}
	return string(encoded)
}

// nextRuntimeLogRecordID 与其他运行时 producer 对齐：使用可排序的时间前缀和
// 非内容熵值。服务 stdout 记录没有 ID 时无法在 runtime logstore 中可靠关联或去重。
func nextRuntimeLogRecordID() string {
	now := time.Now().UTC()
	var entropy [8]byte
	if _, err := cryptorand.Read(entropy[:]); err == nil {
		return "r." + strconv.FormatInt(now.UnixMicro(), 36) + "." + hex.EncodeToString(entropy[:])
	}
	sequence := atomic.AddUint64(&runtimeLogRecordSequence, 1)
	return "r." + strconv.FormatInt(now.UnixMicro(), 36) + "." + strconv.FormatUint(sequence, 36)
}

func runtimeLogAttributes(
	input map[string]any,
	allowlist []string,
	objectID string,
) (map[string]string, error) {
	if len(input) == 0 {
		return nil, nil
	}
	keys := make([]string, 0, len(input))
	for key := range input {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	result := make(map[string]string, len(input))
	allowed := make(map[string]struct{}, len(allowlist))
	for _, key := range allowlist {
		allowed[key] = struct{}{}
	}
	for _, key := range keys {
		trimmedKey := strings.TrimSpace(key)
		if trimmedKey == "" ||
			utf8.RuneCountInString(trimmedKey) > CatalogMaxAttributeKeyLength ||
			forbiddenRuntimeLogAttributeKey(trimmedKey) {
			continue
		}
		if _, ok := allowed[trimmedKey]; !ok {
			continue
		}
		redactedValue, keep := redactCatalogFieldPrivacyAttribute(
			objectID,
			trimmedKey,
			input[key],
		)
		if !keep {
			continue
		}
		text, err := runtimeLogAttributeText(redactedValue)
		if err != nil {
			return nil, err
		}
		if text == "" {
			continue
		}
		result[trimmedKey] = boundedRuntimeLogText(redactRuntimeLogText(text), CatalogMaxAttributeValueLength)
		if len(result) > CatalogMaxAttributes ||
			runtimeLogAttributesSize(result) > CatalogMaxAttributesBytes {
			delete(result, trimmedKey)
			break
		}
	}
	if len(result) == 0 {
		return nil, nil
	}
	return result, nil
}

func validateRuntimeLogCorrelation(value runtimeLogCorrelation, allowed []string) error {
	registered := make(map[string]struct{}, len(allowed))
	for _, key := range allowed {
		registered[key] = struct{}{}
	}
	for key, present := range map[string]bool{
		"requestId":        value.RequestID != "",
		"traceId":          value.TraceID != "",
		"spanId":           value.SpanID != "",
		"operationId":      value.OperationID != "",
		"pageName":         value.PageName != "",
		"surfaceId":        value.SurfaceID != "",
		"executionId":      value.ExecutionID != "",
		"workPackageId":    value.WorkPackageID != "",
		"environmentRunId": value.EnvironmentRunID != "",
		"actorHash":        value.ActorHash != "",
	} {
		if present {
			if _, ok := registered[key]; !ok {
				return fmt.Errorf("runtime log correlation key %q is not registered for signal", key)
			}
		}
	}
	return nil
}

func runtimeLogAttributeText(value any) (string, error) {
	if value == nil {
		return "", nil
	}
	if text, ok := value.(string); ok {
		return text, nil
	}
	encoded, err := json.Marshal(value)
	if err != nil {
		return "", fmt.Errorf("encode runtime log attribute: %w", err)
	}
	return string(encoded), nil
}

func runtimeLogAttributesSize(values map[string]string) int {
	encoded, err := json.Marshal(values)
	if err != nil {
		return CatalogMaxAttributesBytes + 1
	}
	return len(encoded)
}

func forbiddenRuntimeLogAttributeKey(key string) bool {
	normalized := normalizeRuntimeLogKey(key)
	for blocked := range CatalogForbiddenAttributeKeys {
		if runtimeLogKeyMatches(normalized, normalizeRuntimeLogKey(blocked)) {
			return true
		}
	}
	for blocked := range CatalogHighCardinalityMetricKeys {
		if runtimeLogKeyMatches(normalized, normalizeRuntimeLogKey(blocked)) {
			return true
		}
	}
	for blocked := range CatalogForbiddenFields {
		if runtimeLogKeyMatches(normalized, normalizeRuntimeLogKey(blocked)) {
			return true
		}
	}
	return false
}

func normalizeRuntimeLogKey(value string) string {
	var builder strings.Builder
	for _, character := range strings.ToLower(value) {
		if (character >= 'a' && character <= 'z') ||
			(character >= '0' && character <= '9') {
			builder.WriteRune(character)
		}
	}
	return builder.String()
}

func runtimeLogKeyMatches(key string, blocked string) bool {
	return key == blocked || (blocked != "ip" && strings.Contains(key, blocked))
}

var (
	runtimeLogBearerPattern = regexp.MustCompile(`(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+`)
	runtimeLogSecretPattern = regexp.MustCompile(`(?i)(access_token|token|authcode|authorization|signature|x-amz-signature|x-amz-credential|secret)=([^&#\s]+)`)
	runtimeLogEmailPattern  = regexp.MustCompile(`(?i)\b[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}\b`)
	runtimeLogPhonePattern  = regexp.MustCompile(`\b\d{3}[- ]?\d{4}[- ]?\d{4}\b`)
)

func redactRuntimeLogText(value string) string {
	value = runtimeLogBearerPattern.ReplaceAllString(value, "Bearer ***")
	value = runtimeLogSecretPattern.ReplaceAllString(value, "$1=***")
	value = runtimeLogEmailPattern.ReplaceAllString(value, "***")
	return runtimeLogPhonePattern.ReplaceAllString(value, "***")
}

func boundedRuntimeLogText(value string, maxBytes int) string {
	if len(value) <= maxBytes {
		return value
	}
	if maxBytes <= len("…") {
		return ""
	}
	for len(value) > maxBytes-len("…") {
		_, size := utf8.DecodeLastRuneInString(value)
		value = value[:len(value)-size]
	}
	return value + "…"
}
