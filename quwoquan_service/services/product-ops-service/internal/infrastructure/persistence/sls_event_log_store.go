package persistence

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"net/http"
	"sort"
	"strconv"
	"strings"
	"time"

	sls "github.com/aliyun/aliyun-log-go-sdk"
	"quwoquan_service/services/product-ops-service/internal/application"
)

type SLSConfig struct {
	Region, Endpoint, Project, RawLogstore, StartupDiagnosticLogstore, AggregateLogstore string
	Timeout                                                                              time.Duration
}

type slsEventClient interface {
	PostLogStoreLogs(project, logstore string, group *sls.LogGroup, hashKey *string) error
	GetLogsV2(project, logstore string, request *sls.GetLogRequest) (*sls.GetLogsResponse, error)
}

func NewOfficialSLSClient(config SLSConfig, accessKeyID, accessKeySecret, securityToken string) sls.ClientInterface {
	client := sls.CreateNormalInterface(config.Endpoint, accessKeyID, accessKeySecret, securityToken)
	client.SetRegion(config.Region)
	client.SetAuthVersion(sls.AuthV4)
	client.SetHTTPClient(&http.Client{Timeout: config.Timeout})
	client.SetRetryTimeout(config.Timeout)
	return client
}

type SLSEventLogStore struct {
	client slsEventClient
	config SLSConfig
	now    func() time.Time
}

func NewSLSEventLogStore(client slsEventClient, config SLSConfig) (*SLSEventLogStore, error) {
	if client == nil || strings.TrimSpace(config.Project) == "" || strings.TrimSpace(config.RawLogstore) == "" || strings.TrimSpace(config.StartupDiagnosticLogstore) == "" || strings.TrimSpace(config.AggregateLogstore) == "" {
		return nil, fmt.Errorf("SLS telemetry configuration is incomplete")
	}
	return &SLSEventLogStore{client: client, config: config, now: time.Now}, nil
}

func (s *SLSEventLogStore) PutEventBatch(_ context.Context, batchKey string, records []application.EventRecord) error {
	logs := make([]*sls.Log, 0, len(records))
	for _, record := range records {
		logs = append(logs, slsLog(eventFields(record), record.IngestedAt))
	}
	hashKey := batchKey[:32]
	if err := s.client.PostLogStoreLogs(s.config.Project, s.config.RawLogstore, &sls.LogGroup{Logs: logs}, &hashKey); err != nil {
		return fmt.Errorf("SLS PutLogs product telemetry: %w", err)
	}
	return nil
}

func (s *SLSEventLogStore) HasEventBatch(_ context.Context, batchKey string, expected int) (bool, error) {
	response, err := s.client.GetLogsV2(s.config.Project, s.config.RawLogstore, &sls.GetLogRequest{
		From: s.now().Add(-72 * time.Hour).Unix(), To: s.now().Add(5 * time.Minute).Unix(), Lines: 1,
		Query: fmt.Sprintf(`_batchKey:%q | SELECT count(*) AS count`, escapeSLS(batchKey)),
	})
	if err != nil {
		return false, fmt.Errorf("confirm SLS telemetry batch: %w", err)
	}
	if len(response.Logs) == 0 {
		return false, nil
	}
	count, _ := strconv.Atoi(response.Logs[0]["count"])
	return count == expected, nil
}

func (s *SLSEventLogStore) PutStartupDiagnostics(_ context.Context, batchKey string, records []application.StartupDiagnosticRecord) error {
	logs := make([]*sls.Log, 0, len(records))
	now := s.now().UTC()
	for index, record := range records {
		fields := map[string]string{
			"eventId": record.EventID, "attemptId": record.AttemptID, "phase": record.Phase,
			"outcome": record.Outcome, "occurredAt": record.OccurredAt, "platform": record.Platform,
			"runtimeEnv": record.RuntimeEnv, "appVersion": record.AppVersion, "networkClass": record.NetworkClass,
			"recoverySurface": record.RecoverySurface, "failureCode": record.FailureCode,
			"failureSource": record.FailureSource, "deadlineOrigin": record.DeadlineOrigin,
			"sequence": strconv.Itoa(record.Sequence), "phaseDurationMs": strconv.Itoa(record.PhaseDurationMS),
			"elapsedMs": strconv.Itoa(record.ElapsedMS), "_batchKey": batchKey,
			"_batchIndex": strconv.Itoa(index), "ingestedAt": now.Format(time.RFC3339Nano),
		}
		logs = append(logs, slsLog(fields, now))
	}
	digest := sha256.Sum256([]byte(batchKey))
	hashKey := hex.EncodeToString(digest[:16])
	if err := s.client.PostLogStoreLogs(s.config.Project, s.config.StartupDiagnosticLogstore, &sls.LogGroup{Logs: logs}, &hashKey); err != nil {
		return fmt.Errorf("SLS PutLogs startup diagnostics: %w", err)
	}
	return nil
}

func (s *SLSEventLogStore) HasStartupDiagnosticBatch(_ context.Context, batchKey string, expected int) (bool, error) {
	response, err := s.client.GetLogsV2(s.config.Project, s.config.StartupDiagnosticLogstore, &sls.GetLogRequest{
		From:  s.now().Add(-72 * time.Hour).Unix(),
		To:    s.now().Add(5 * time.Minute).Unix(),
		Lines: 1,
		Query: fmt.Sprintf(`_batchKey:%q | SELECT count(*) AS count`, escapeSLS(batchKey)),
	})
	if err != nil {
		return false, fmt.Errorf("confirm SLS startup diagnostic batch: %w", err)
	}
	if len(response.Logs) == 0 {
		return false, nil
	}
	count, _ := strconv.Atoi(response.Logs[0]["count"])
	return count == expected, nil
}

func (s *SLSEventLogStore) GetEventSummary(_ context.Context, query application.EventSummaryQuery) (application.EventSummary, error) {
	search := buildSLSFilter(query.LogType, query.EventType, query.PageName, query.AppVersion, query.NetworkClass, query.ErrorCode, "")
	sql := `SELECT logType,eventType,pageName,appVersion,networkClass,deviceManufacturer,deviceModel,errorCode,sum(CAST(count AS BIGINT)) AS count GROUP BY logType,eventType,pageName,appVersion,networkClass,deviceManufacturer,deviceModel,errorCode`
	response, err := s.client.GetLogsV2(s.config.Project, s.config.AggregateLogstore, &sls.GetLogRequest{From: query.From.Unix(), To: query.To.Unix(), Query: search + " | " + sql, Lines: 100})
	if err != nil {
		return application.EventSummary{}, fmt.Errorf("query SLS aggregate: %w", err)
	}
	out := application.EventSummary{DimensionCounters: map[string]map[string]int{}, Source: "sls_aggregate", Freshness: "closed_hour", ActualFrom: query.From.UTC().Format(time.RFC3339Nano), ActualTo: query.To.UTC().Format(time.RFC3339Nano)}
	for _, row := range response.Logs {
		count, _ := strconv.Atoi(row["count"])
		out.TotalCount += int64(count)
		for _, field := range []string{"logType", "eventType", "pageName", "appVersion", "networkClass", "deviceManufacturer", "deviceModel", "errorCode"} {
			addSLSDimension(out.DimensionCounters, field, row[field], count)
		}
	}
	sessionResponse, err := s.client.GetLogsV2(s.config.Project, s.config.AggregateLogstore, &sls.GetLogRequest{
		From: query.From.Unix(), To: query.To.Unix(), Lines: 1,
		Query: search + ` | SELECT cardinality(merge(CAST(from_base64(sessionHll) AS HyperLogLog))) AS sessionCount`,
	})
	if err != nil {
		return application.EventSummary{}, fmt.Errorf("query SLS aggregate sessions: %w", err)
	}
	if len(sessionResponse.Logs) > 0 {
		out.SessionCount, _ = strconv.ParseInt(sessionResponse.Logs[0]["sessionCount"], 10, 64)
	}
	return out, nil
}

func (s *SLSEventLogStore) GetEventDrilldown(_ context.Context, query application.EventDrilldownQuery) (application.EventDrilldown, error) {
	filter := buildSLSFilter(query.LogType, query.EventType, query.PageName, query.AppVersion, query.NetworkClass, query.ErrorCode, query.SessionID)
	businessWindow := fmt.Sprintf(
		`SELECT * WHERE from_iso8601_timestamp(occurredAt) >= from_iso8601_timestamp('%s') AND from_iso8601_timestamp(occurredAt) < from_iso8601_timestamp('%s') ORDER BY __time__ DESC LIMIT %d`,
		escapeSLSSQLLiteral(query.From.UTC().Format(time.RFC3339Nano)),
		escapeSLSSQLLiteral(query.To.UTC().Format(time.RFC3339Nano)),
		query.Limit,
	)
	now := s.now().UTC()
	response, err := s.client.GetLogsV2(s.config.Project, s.config.RawLogstore, &sls.GetLogRequest{
		From: now.Add(-72 * time.Hour).Unix(), To: now.Add(5 * time.Minute).Unix(),
		Query: filter + " | " + businessWindow, Lines: int64(query.Limit), Reverse: true,
	})
	if err != nil {
		return application.EventDrilldown{}, fmt.Errorf("query SLS raw telemetry: %w", err)
	}
	items := make([]application.EventDrilldownItem, 0, len(response.Logs))
	for _, row := range response.Logs {
		items = append(items, decodeSLSDrilldown(row, query.RevealSession))
	}
	return application.EventDrilldown{TotalCount: response.Count, Items: items, Source: "sls_raw", Freshness: "near_realtime", ActualFrom: query.From.UTC().Format(time.RFC3339Nano), ActualTo: query.To.UTC().Format(time.RFC3339Nano)}, nil
}

func eventFields(record application.EventRecord) map[string]string {
	fields := map[string]string{
		"logType": record.LogType, "eventType": record.EventType, "sessionId": record.SessionID,
		"pageName": record.PageName, "occurredAt": record.OccurredAt,
		"deviceManufacturer": record.DeviceManufacturer, "deviceModel": record.DeviceModel,
		"appVersion": record.AppVersion, "networkClass": record.NetworkClass,
		"_batchKey": record.BatchKey, "_batchIndex": strconv.Itoa(record.BatchIndex),
		"ingestedAt": record.IngestedAt.UTC().Format(time.RFC3339Nano),
	}
	for key, value := range recordExtensions(record.EventRecordInput) {
		fields[key] = value
	}
	return fields
}

func recordExtensions(record application.EventRecordInput) map[string]string {
	out := map[string]string{}
	putInt := func(name string, value *int) {
		if value != nil {
			out[name] = strconv.Itoa(*value)
		}
	}
	putString := func(name string, value *string) {
		if value != nil {
			out[name] = *value
		}
	}
	putInt("durationMs", record.DurationMS)
	putString("result", record.Result)
	putString("failReasonCode", record.FailReasonCode)
	putString("errorCode", record.ErrorCode)
	putString("operationId", record.OperationID)
	putInt("httpStatus", record.HTTPStatus)
	if record.CallStack != nil {
		encoded, _ := json.Marshal(record.CallStack)
		out["callStack"] = string(encoded)
	}
	putInt("tClickToFirstFrameMs", record.TClickToFirstFrameMS)
	putInt("tFirstFrameToShellMs", record.TFirstFrameToShellMS)
	putInt("tShellToContentMs", record.TShellToContentMS)
	putInt("tClickToContentMs", record.TClickToContentMS)
	if record.HasError != nil {
		out["hasError"] = strconv.FormatBool(*record.HasError)
	}
	putString("journey", record.Journey)
	putString("action", record.Action)
	putInt("readyMs", record.ReadyMS)
	putInt("ttffMs", record.TTFFMS)
	putInt("rebufferCount", record.RebufferCount)
	putInt("rebufferMs", record.RebufferMS)
	putInt("seekCount", record.SeekCount)
	putInt("declaredDurationMs", record.DeclaredDurationMS)
	putInt("observedDurationMs", record.ObservedDurationMS)
	if record.DurationMismatch != nil {
		out["durationMismatch"] = strconv.FormatBool(*record.DurationMismatch)
	}
	putString("playbackMode", record.PlaybackMode)
	return out
}

func slsLog(fields map[string]string, ingestedAt time.Time) *sls.Log {
	keys := make([]string, 0, len(fields))
	for key := range fields {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	contents := make([]*sls.LogContent, 0, len(keys))
	for _, key := range keys {
		keyCopy, valueCopy := key, fields[key]
		contents = append(contents, &sls.LogContent{Key: &keyCopy, Value: &valueCopy})
	}
	seconds, nanos := uint32(ingestedAt.Unix()), uint32(ingestedAt.Nanosecond())
	return &sls.Log{Time: &seconds, TimeNs: &nanos, Contents: contents}
}

func buildSLSFilter(logType, eventType, pageName, appVersion, networkClass, errorCode, sessionID string) string {
	clauses := []string{"*"}
	for _, item := range []struct{ name, value string }{{"logType", logType}, {"eventType", eventType}, {"pageName", pageName}, {"appVersion", appVersion}, {"networkClass", networkClass}, {"errorCode", errorCode}, {"sessionId", sessionID}} {
		if item.value != "" {
			clauses = append(clauses, fmt.Sprintf(`%s:%q`, item.name, escapeSLS(item.value)))
		}
	}
	return strings.Join(clauses, " AND ")
}

func escapeSLS(value string) string           { return strings.NewReplacer(`\`, `\\`, `"`, `\"`).Replace(value) }
func escapeSLSSQLLiteral(value string) string { return strings.ReplaceAll(value, "'", "''") }
func addSLSDimension(out map[string]map[string]int, field, value string, count int) {
	if value == "" || count <= 0 {
		return
	}
	if out[field] == nil {
		out[field] = map[string]int{}
	}
	out[field][value] += count
}

func decodeSLSDrilldown(row map[string]string, revealSession bool) application.EventDrilldownItem {
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
		RowKey: hex.EncodeToString(digest[:8]), LogType: row["logType"], EventType: row["eventType"], SessionID: sessionID,
		PageName: row["pageName"], OccurredAt: row["occurredAt"], DeviceManufacturer: row["deviceManufacturer"], DeviceModel: row["deviceModel"], AppVersion: row["appVersion"], NetworkClass: row["networkClass"],
		DurationMS: parseInt("durationMs"), Result: parseString("result"), FailReasonCode: parseString("failReasonCode"), ErrorCode: parseString("errorCode"), OperationID: parseString("operationId"), HTTPStatus: parseInt("httpStatus"), CallStack: stack,
		TClickToFirstFrameMS: parseInt("tClickToFirstFrameMs"), TFirstFrameToShellMS: parseInt("tFirstFrameToShellMs"), TShellToContentMS: parseInt("tShellToContentMs"), TClickToContentMS: parseInt("tClickToContentMs"), HasError: parseBool("hasError"), Journey: parseString("journey"), Action: parseString("action"), IngestedAt: row["ingestedAt"],
		ReadyMS: parseInt("readyMs"), TTFFMS: parseInt("ttffMs"), RebufferCount: parseInt("rebufferCount"), RebufferMS: parseInt("rebufferMs"), SeekCount: parseInt("seekCount"), DeclaredDurationMS: parseInt("declaredDurationMs"), ObservedDurationMS: parseInt("observedDurationMs"), DurationMismatch: parseBool("durationMismatch"), PlaybackMode: parseString("playbackMode"),
	}
}

var _ application.EventLogStore = (*SLSEventLogStore)(nil)
