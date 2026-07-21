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
	Region, Endpoint, Project, RawLogstore, StartupDiagnosticLogstore, RuntimeLogstore, AggregateLogstore string
	Timeout                                                                                               time.Duration
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

var _ application.ObservabilityLogSink = (*SLSEventLogStore)(nil)

func NewSLSEventLogStore(client slsEventClient, config SLSConfig) (*SLSEventLogStore, error) {
	if client == nil || strings.TrimSpace(config.Project) == "" || strings.TrimSpace(config.RawLogstore) == "" || strings.TrimSpace(config.StartupDiagnosticLogstore) == "" || strings.TrimSpace(config.RuntimeLogstore) == "" || strings.TrimSpace(config.AggregateLogstore) == "" {
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

func (s *SLSEventLogStore) PutRuntimeLogBatch(_ context.Context, batchKey string, records []application.RuntimeLogRecord) error {
	logs := make([]*sls.Log, 0, len(records))
	for _, record := range records {
		fields := make(map[string]string, len(record.Fields)+3)
		for key, value := range record.Fields {
			if value != "" {
				fields[key] = value
			}
		}
		fields["_batchKey"] = batchKey
		fields["_batchIndex"] = strconv.Itoa(record.BatchIndex)
		fields["ingestedAt"] = record.IngestedAt.UTC().Format(time.RFC3339Nano)
		logs = append(logs, slsLog(fields, record.IngestedAt))
	}
	hashKey := batchKey[:32]
	if err := s.client.PostLogStoreLogs(s.config.Project, s.config.RuntimeLogstore, &sls.LogGroup{Logs: logs}, &hashKey); err != nil {
		return fmt.Errorf("SLS PutLogs runtime diagnostics: %w", err)
	}
	return nil
}

func (s *SLSEventLogStore) HasRuntimeLogBatch(_ context.Context, batchKey string, expected int) (bool, error) {
	response, err := s.client.GetLogsV2(s.config.Project, s.config.RuntimeLogstore, &sls.GetLogRequest{
		From:  s.now().Add(-72 * time.Hour).Unix(),
		To:    s.now().Add(5 * time.Minute).Unix(),
		Lines: 1,
		Query: fmt.Sprintf(`_batchKey:%q | SELECT count(*) AS count`, escapeSLS(batchKey)),
	})
	if err != nil {
		return false, fmt.Errorf("confirm SLS runtime diagnostic batch: %w", err)
	}
	if len(response.Logs) == 0 {
		return false, nil
	}
	count, _ := strconv.Atoi(response.Logs[0]["count"])
	return count == expected, nil
}

func (s *SLSEventLogStore) GetRuntimeLogSummary(_ context.Context, query application.RuntimeLogSummaryQuery) (application.RuntimeLogSummary, error) {
	filter := buildSLSRuntimeLogFilter(query.Signal, query.Severity, query.ErrorCode, query.Fingerprint, query.SourceType, query.Service, query.AppVersion, "runtime_diagnostics")
	sql := `SELECT logKind,severity,signal,errorCode,fingerprint,resourceSourceType,resourceService,resourceAppVersion,sum(CAST(count AS BIGINT)) AS count,max(freshness) AS freshness,max(generatedThrough) AS generatedThrough,max(lagSeconds) AS lagSeconds GROUP BY logKind,severity,signal,errorCode,fingerprint,resourceSourceType,resourceService,resourceAppVersion`
	response, err := s.client.GetLogsV2(s.config.Project, s.config.AggregateLogstore, &sls.GetLogRequest{
		From:  query.From.Unix(),
		To:    query.To.Unix(),
		Query: filter + " | " + sql,
		Lines: 100,
	})
	if err != nil {
		return application.RuntimeLogSummary{}, fmt.Errorf("query SLS runtime diagnostic aggregate: %w", err)
	}
	out := application.RuntimeLogSummary{
		DimensionCounters: map[string]map[string]int{},
		SourceKind:        "hourly_rollup",
		Freshness:         "closed_hour",
		ActualFrom:        query.From.UTC().Format(time.RFC3339Nano),
		ActualTo:          query.To.UTC().Format(time.RFC3339Nano),
	}
	for _, row := range response.Logs {
		count, _ := strconv.Atoi(row["count"])
		out.TotalCount += int64(count)
		applyWaterline(&out.Freshness, &out.GeneratedThrough, &out.LagSeconds, row)
		for _, field := range []string{"logKind", "severity", "signal", "errorCode", "fingerprint", "resourceSourceType", "resourceService", "resourceAppVersion"} {
			addSLSDimension(out.DimensionCounters, field, row[field], count)
		}
	}
	return out, nil
}

func (s *SLSEventLogStore) GetRuntimeLogDrilldown(_ context.Context, query application.RuntimeLogDrilldownQuery) (application.RuntimeLogDrilldown, error) {
	filter := buildSLSRuntimeLogFilter(query.Signal, query.Severity, query.ErrorCode, query.Fingerprint, query.SourceType, query.Service, query.AppVersion, "")
	if query.ActorHash != "" {
		filter += fmt.Sprintf(` AND actorHash:%q`, escapeSLS(query.ActorHash))
	}
	if query.MessageContains != "" {
		// SLS 全文索引短语匹配；logstore 索引须开启 message 字段分词（IaC 声明）。
		filter += fmt.Sprintf(` AND message:%q`, escapeSLS(query.MessageContains))
	}
	businessWindow := fmt.Sprintf(
		`SELECT * WHERE from_iso8601_timestamp(occurredAt) >= from_iso8601_timestamp('%s') AND from_iso8601_timestamp(occurredAt) < from_iso8601_timestamp('%s') ORDER BY __time__ DESC LIMIT %d`,
		escapeSLSSQLLiteral(query.From.UTC().Format(time.RFC3339Nano)),
		escapeSLSSQLLiteral(query.To.UTC().Format(time.RFC3339Nano)),
		query.Limit,
	)
	now := s.now().UTC()
	response, err := s.client.GetLogsV2(s.config.Project, s.config.RuntimeLogstore, &sls.GetLogRequest{
		From:    now.Add(-72 * time.Hour).Unix(),
		To:      now.Add(5 * time.Minute).Unix(),
		Query:   filter + " | " + businessWindow,
		Lines:   int64(query.Limit),
		Reverse: true,
	})
	if err != nil {
		return application.RuntimeLogDrilldown{}, fmt.Errorf("query SLS runtime diagnostic raw: %w", err)
	}
	items := make([]application.RuntimeLogDrilldownItem, 0, len(response.Logs))
	for _, row := range response.Logs {
		items = append(items, decodeSLSRuntimeLogDrilldown(row, query.RevealCorrelation))
	}
	generatedThrough, lagSeconds := rawWaterline(response.Logs, now)
	return application.RuntimeLogDrilldown{
		TotalCount:       response.Count,
		Items:            items,
		SourceKind:       "raw_records",
		Freshness:        "near_realtime",
		GeneratedThrough: generatedThrough,
		LagSeconds:       lagSeconds,
		ActualFrom:       query.From.UTC().Format(time.RFC3339Nano),
		ActualTo:         query.To.UTC().Format(time.RFC3339Nano),
	}, nil
}

func (s *SLSEventLogStore) GetEventSummary(_ context.Context, query application.EventSummaryQuery) (application.EventSummary, error) {
	search := buildSLSFilter(query.LogType, query.EventType, query.PageName, query.AppVersion, query.NetworkClass, query.Result, query.ErrorCode, "", "event_dimensions")
	sql := `SELECT logType,eventType,pageName,appVersion,networkClass,deviceManufacturer,deviceModel,journey,action,result,errorCode,sum(CAST(count AS BIGINT)) AS count,max(freshness) AS freshness,max(generatedThrough) AS generatedThrough,max(lagSeconds) AS lagSeconds GROUP BY logType,eventType,pageName,appVersion,networkClass,deviceManufacturer,deviceModel,journey,action,result,errorCode`
	response, err := s.client.GetLogsV2(s.config.Project, s.config.AggregateLogstore, &sls.GetLogRequest{From: query.From.Unix(), To: query.To.Unix(), Query: search + " | " + sql, Lines: 100})
	if err != nil {
		return application.EventSummary{}, fmt.Errorf("query SLS aggregate: %w", err)
	}
	out := application.EventSummary{DimensionCounters: map[string]map[string]int{}, SourceKind: "hourly_rollup", Freshness: "closed_hour", ActualFrom: query.From.UTC().Format(time.RFC3339Nano), ActualTo: query.To.UTC().Format(time.RFC3339Nano)}
	for _, row := range response.Logs {
		count, _ := strconv.Atoi(row["count"])
		out.TotalCount += int64(count)
		applyWaterline(&out.Freshness, &out.GeneratedThrough, &out.LagSeconds, row)
		for _, field := range []string{"logType", "eventType", "pageName", "appVersion", "networkClass", "deviceManufacturer", "deviceModel", "journey", "action", "result", "errorCode"} {
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

// ReadRtcMediaQoeSummary 直接查询 rtc_media_qoe raw。generic event summary 不含
// connectTimeMs 分布，小时 P95 也不能二次合成整体 P95，因此这里分别执行小时聚合与
// 全窗口聚合，二者都由 SLS approx_percentile 读取真实 connected 样本。
func (s *SLSEventLogStore) ReadRtcMediaQoeSummary(
	_ context.Context,
	query application.RtcMediaQoeSummaryQuery,
) (application.RtcMediaQoeSummarySlice, error) {
	from := query.From.UTC()
	to := query.To.UTC()
	hourlyResponse, err := s.client.GetLogsV2(
		s.config.Project,
		s.config.RawLogstore,
		&sls.GetLogRequest{
			From:  from.Add(-5 * time.Minute).Unix(),
			To:    to.Add(5 * time.Minute).Unix(),
			Query: buildSLSRtcMediaQoeHourlyQuery(query),
			Lines: 24,
		},
	)
	if err != nil {
		return application.RtcMediaQoeSummarySlice{}, fmt.Errorf(
			"query SLS rtc_media_qoe hourly raw: %w",
			err,
		)
	}
	hourly := make([]application.RtcMediaQoeAggregate, 0, len(hourlyResponse.Logs))
	for _, row := range hourlyResponse.Logs {
		item, err := decodeSLSRtcMediaQoeAggregate(row, true)
		if err != nil {
			return application.RtcMediaQoeSummarySlice{}, fmt.Errorf(
				"decode SLS rtc_media_qoe hourly row: %w",
				err,
			)
		}
		hourly = append(hourly, item)
	}

	totalResponse, err := s.client.GetLogsV2(
		s.config.Project,
		s.config.RawLogstore,
		&sls.GetLogRequest{
			From:  from.Add(-5 * time.Minute).Unix(),
			To:    to.Add(5 * time.Minute).Unix(),
			Query: buildSLSRtcMediaQoeTotalQuery(query),
			Lines: 1,
		},
	)
	if err != nil {
		return application.RtcMediaQoeSummarySlice{}, fmt.Errorf(
			"query SLS rtc_media_qoe total raw: %w",
			err,
		)
	}
	total := application.RtcMediaQoeAggregate{}
	if len(totalResponse.Logs) > 0 {
		total, err = decodeSLSRtcMediaQoeAggregate(totalResponse.Logs[0], false)
		if err != nil {
			return application.RtcMediaQoeSummarySlice{}, fmt.Errorf(
				"decode SLS rtc_media_qoe total row: %w",
				err,
			)
		}
	}
	return application.BuildRtcMediaQoeSummary(
		query,
		hourly,
		total,
		"raw_records",
	), nil
}

func buildSLSRtcMediaQoeHourlyQuery(
	query application.RtcMediaQoeSummaryQuery,
) string {
	return buildSLSRtcMediaQoeBaseQuery(query) + `
SELECT
  cast(to_unixtime(date_trunc('hour', from_iso8601_timestamp(occurredAt))) AS BIGINT) AS bucketEpoch,
  count(*) AS effectiveSampleCount,
  count_if(mediaConnected='true') AS mediaConnectedCount,
  approx_percentile(try_cast(connectTimeMs AS DOUBLE), 0.95)
    FILTER (WHERE mediaConnected='true' AND connectTimeMs IS NOT NULL) AS connectP95Ms,
  count_if(mediaConnected='true' AND result='connection_lost') AS connectionLostCount,
  coalesce(sum(try_cast(reconnectCount AS BIGINT)), 0) AS reconnectCount,
  max(ingestedAt) AS generatedThrough
WHERE result IS NOT NULL AND result <> '' AND result <> 'abandoned'
  AND from_iso8601_timestamp(occurredAt) >= from_iso8601_timestamp('` +
		escapeSLSSQLLiteral(query.From.UTC().Format(time.RFC3339Nano)) + `')
  AND from_iso8601_timestamp(occurredAt) < from_iso8601_timestamp('` +
		escapeSLSSQLLiteral(query.To.UTC().Format(time.RFC3339Nano)) + `')
GROUP BY date_trunc('hour', from_iso8601_timestamp(occurredAt))
ORDER BY bucketEpoch`
}

func buildSLSRtcMediaQoeTotalQuery(
	query application.RtcMediaQoeSummaryQuery,
) string {
	return buildSLSRtcMediaQoeBaseQuery(query) + `
SELECT
  count(*) AS effectiveSampleCount,
  count_if(mediaConnected='true') AS mediaConnectedCount,
  approx_percentile(try_cast(connectTimeMs AS DOUBLE), 0.95)
    FILTER (WHERE mediaConnected='true' AND connectTimeMs IS NOT NULL) AS connectP95Ms,
  count_if(mediaConnected='true' AND result='connection_lost') AS connectionLostCount,
  coalesce(sum(try_cast(reconnectCount AS BIGINT)), 0) AS reconnectCount,
  max(ingestedAt) AS generatedThrough
WHERE result IS NOT NULL AND result <> '' AND result <> 'abandoned'
  AND from_iso8601_timestamp(occurredAt) >= from_iso8601_timestamp('` +
		escapeSLSSQLLiteral(query.From.UTC().Format(time.RFC3339Nano)) + `')
  AND from_iso8601_timestamp(occurredAt) < from_iso8601_timestamp('` +
		escapeSLSSQLLiteral(query.To.UTC().Format(time.RFC3339Nano)) + `')`
}

func buildSLSRtcMediaQoeBaseQuery(
	_ application.RtcMediaQoeSummaryQuery,
) string {
	return `eventType:"rtc_media_qoe" | `
}

func decodeSLSRtcMediaQoeAggregate(
	row map[string]string,
	withBucket bool,
) (application.RtcMediaQoeAggregate, error) {
	effective, err := parseRequiredNonNegativeInt64(row, "effectiveSampleCount")
	if err != nil {
		return application.RtcMediaQoeAggregate{}, err
	}
	connected, err := parseRequiredNonNegativeInt64(row, "mediaConnectedCount")
	if err != nil {
		return application.RtcMediaQoeAggregate{}, err
	}
	lost, err := parseRequiredNonNegativeInt64(row, "connectionLostCount")
	if err != nil {
		return application.RtcMediaQoeAggregate{}, err
	}
	reconnect, err := parseRequiredNonNegativeInt64(row, "reconnectCount")
	if err != nil {
		return application.RtcMediaQoeAggregate{}, err
	}
	if connected > effective || lost > connected {
		return application.RtcMediaQoeAggregate{}, fmt.Errorf(
			"invalid counts effective=%d connected=%d connection_lost=%d",
			effective,
			connected,
			lost,
		)
	}
	out := application.RtcMediaQoeAggregate{
		EffectiveSampleCount: effective,
		MediaConnectedCount:  connected,
		ConnectionLostCount:  lost,
		ReconnectCount:       reconnect,
	}
	if withBucket {
		epoch, err := parseRequiredNonNegativeInt64(row, "bucketEpoch")
		if err != nil {
			return application.RtcMediaQoeAggregate{}, err
		}
		out.BucketStart = time.Unix(epoch, 0).UTC()
	}
	if raw := strings.TrimSpace(row["connectP95Ms"]); raw != "" &&
		!strings.EqualFold(raw, "null") {
		value, err := strconv.ParseFloat(raw, 64)
		if err != nil || value < 0 {
			return application.RtcMediaQoeAggregate{}, fmt.Errorf(
				"invalid connectP95Ms %q",
				raw,
			)
		}
		out.ConnectP95MS = &value
	}
	if raw := strings.TrimSpace(row["generatedThrough"]); raw != "" &&
		!strings.EqualFold(raw, "null") {
		value, err := time.Parse(time.RFC3339Nano, raw)
		if err != nil {
			return application.RtcMediaQoeAggregate{}, fmt.Errorf(
				"invalid generatedThrough %q",
				raw,
			)
		}
		value = value.UTC()
		out.GeneratedThrough = &value
	}
	return out, nil
}

func parseRequiredNonNegativeInt64(
	row map[string]string,
	field string,
) (int64, error) {
	raw := strings.TrimSpace(row[field])
	value, err := strconv.ParseInt(raw, 10, 64)
	if err != nil || value < 0 {
		return 0, fmt.Errorf("invalid %s %q", field, raw)
	}
	return value, nil
}

// GetPageExperienceStats 用 SLS SQL 按 pageName 聚合页面体验事实（热力图数据源）。
func (s *SLSEventLogStore) GetPageExperienceStats(
	_ context.Context,
	query application.PageExperienceQuery,
) ([]application.PageExperienceStat, error) {
	sql := `* | SELECT pageName,
  count_if(eventType='page_open') AS opens,
  avg(try_cast(readyMs AS BIGINT)) FILTER (WHERE eventType='page_open' AND readyMs IS NOT NULL) AS avgReadyMs,
  count_if(eventType='page_open' AND readyMs IS NOT NULL) AS readySamples,
  avg(try_cast(durationMs AS BIGINT)) FILTER (WHERE eventType='page_return') AS avgStayMs,
  count_if(eventType='page_return') AS staySamples,
  count_if(eventType='runtime_exception') AS runtimeErrors
  WHERE pageName != '' GROUP BY pageName LIMIT 500`
	response, err := s.client.GetLogsV2(s.config.Project, s.config.RawLogstore, &sls.GetLogRequest{
		From: query.From.Unix(), To: query.To.Unix(), Query: sql, Lines: 500,
	})
	if err != nil {
		return nil, fmt.Errorf("query SLS page experience: %w", err)
	}
	items := make([]application.PageExperienceStat, 0, len(response.Logs))
	for _, row := range response.Logs {
		opens, _ := strconv.ParseInt(row["opens"], 10, 64)
		readySamples, _ := strconv.ParseInt(row["readySamples"], 10, 64)
		staySamples, _ := strconv.ParseInt(row["staySamples"], 10, 64)
		runtimeErrors, _ := strconv.ParseInt(row["runtimeErrors"], 10, 64)
		avgReady, _ := strconv.ParseFloat(row["avgReadyMs"], 64)
		avgStay, _ := strconv.ParseFloat(row["avgStayMs"], 64)
		items = append(items, application.PageExperienceStat{
			PageName:      row["pageName"],
			Opens:         opens,
			AvgReadyMs:    avgReady,
			ReadySamples:  readySamples,
			AvgStayMs:     avgStay,
			StaySamples:   staySamples,
			RuntimeErrors: runtimeErrors,
		})
	}
	return items, nil
}

// ListDistinctSessions 用 SLS SQL 聚合窗口内 distinct sessionId 与事件总数
// （user_activity_daily 增长聚合的数据源；raw logstore 3 天滚动内）。
func (s *SLSEventLogStore) ListDistinctSessions(
	_ context.Context,
	from, to time.Time,
	limit int,
) ([]string, int64, error) {
	countResponse, err := s.client.GetLogsV2(s.config.Project, s.config.RawLogstore, &sls.GetLogRequest{
		From: from.Unix(), To: to.Unix(), Lines: 1,
		Query: `* | SELECT count(*) AS total`,
	})
	if err != nil {
		return nil, 0, fmt.Errorf("count SLS events: %w", err)
	}
	var totalEvents int64
	if len(countResponse.Logs) > 0 {
		totalEvents, _ = strconv.ParseInt(countResponse.Logs[0]["total"], 10, 64)
	}
	sessionResponse, err := s.client.GetLogsV2(s.config.Project, s.config.RawLogstore, &sls.GetLogRequest{
		From: from.Unix(), To: to.Unix(), Lines: int64(limit),
		Query: fmt.Sprintf(`* | SELECT DISTINCT sessionId LIMIT %d`, limit),
	})
	if err != nil {
		return nil, 0, fmt.Errorf("list SLS distinct sessions: %w", err)
	}
	sessions := make([]string, 0, len(sessionResponse.Logs))
	for _, row := range sessionResponse.Logs {
		if sessionID := row["sessionId"]; sessionID != "" {
			sessions = append(sessions, sessionID)
		}
	}
	return sessions, totalEvents, nil
}

func (s *SLSEventLogStore) GetEventDrilldown(_ context.Context, query application.EventDrilldownQuery) (application.EventDrilldown, error) {
	filter := buildSLSFilter(query.LogType, query.EventType, query.PageName, query.AppVersion, query.NetworkClass, query.Result, query.ErrorCode, query.SessionID, "")
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
	generatedThrough, lagSeconds := rawWaterline(response.Logs, s.now().UTC())
	return application.EventDrilldown{TotalCount: response.Count, Items: items, SourceKind: "raw_records", Freshness: "near_realtime", GeneratedThrough: generatedThrough, LagSeconds: lagSeconds, ActualFrom: query.From.UTC().Format(time.RFC3339Nano), ActualTo: query.To.UTC().Format(time.RFC3339Nano)}, nil
}

func eventFields(record application.EventRecord) map[string]string {
	fields := map[string]string{
		"logType": record.LogType, "eventType": record.EventType, "sessionId": record.SessionID,
		"pageName": record.PageName, "occurredAt": record.OccurredAt,
		"deviceManufacturer": record.DeviceManufacturer, "deviceModel": record.DeviceModel,
		"appVersion": record.AppVersion, "networkClass": record.NetworkClass,
		"devicePlatform": record.DevicePlatform,
		"_batchKey":      record.BatchKey, "_batchIndex": strconv.Itoa(record.BatchIndex),
		"ingestedAt": record.IngestedAt.UTC().Format(time.RFC3339Nano),
	}
	for key, value := range recordExtensions(record.EventRecordInput) {
		fields[key] = value
	}
	return fields
}

func recordExtensions(record application.EventRecordInput) map[string]string {
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

func buildSLSFilter(logType, eventType, pageName, appVersion, networkClass, result, errorCode, sessionID, rowKind string) string {
	clauses := []string{"*"}
	for _, item := range []struct{ name, value string }{{"logType", logType}, {"eventType", eventType}, {"pageName", pageName}, {"appVersion", appVersion}, {"networkClass", networkClass}, {"result", result}, {"errorCode", errorCode}, {"sessionId", sessionID}, {"rowKind", rowKind}} {
		if item.value != "" {
			clauses = append(clauses, fmt.Sprintf(`%s:%q`, item.name, escapeSLS(item.value)))
		}
	}
	return strings.Join(clauses, " AND ")
}

func buildSLSRuntimeLogFilter(signal, severity, errorCode, fingerprint, sourceType, service, appVersion, rowKind string) string {
	clauses := []string{"signal:*"}
	for _, item := range []struct{ name, value string }{
		{"signal", signal},
		{"severity", severity},
		{"errorCode", errorCode},
		{"fingerprint", fingerprint},
		{"resourceSourceType", sourceType},
		{"resourceService", service},
		{"resourceAppVersion", appVersion},
		{"rowKind", rowKind},
	} {
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

func applyWaterline(freshness *string, generatedThrough *string, lagSeconds *int64, row map[string]string) {
	if value := strings.TrimSpace(row["freshness"]); value != "" {
		*freshness = value
	}
	if value := strings.TrimSpace(row["generatedThrough"]); value != "" &&
		value > *generatedThrough {
		*generatedThrough = value
	}
	if value, err := strconv.ParseInt(strings.TrimSpace(row["lagSeconds"]), 10, 64); err == nil && value > *lagSeconds {
		*lagSeconds = value
	}
}

func rawWaterline(rows []map[string]string, now time.Time) (string, int64) {
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
		PageName: row["pageName"], OccurredAt: row["occurredAt"], DeviceManufacturer: row["deviceManufacturer"], DeviceModel: row["deviceModel"], AppVersion: row["appVersion"], NetworkClass: row["networkClass"], DevicePlatform: row["devicePlatform"],
		DurationMS: parseInt("durationMs"), Result: parseString("result"), FailReasonCode: parseString("failReasonCode"), ErrorCode: parseString("errorCode"), OperationID: parseString("operationId"), RequestID: parseString("requestId"), TraceID: parseString("traceId"), RecoveryAction: parseString("recoveryAction"), SurfaceID: parseString("surfaceId"), DetectionSource: parseString("detectionSource"), TerminalState: parseString("terminalState"), HTTPStatus: parseInt("httpStatus"), CallStack: stack,
		TClickToFirstFrameMS: parseInt("tClickToFirstFrameMs"), TFirstFrameToShellMS: parseInt("tFirstFrameToShellMs"), TShellToContentMS: parseInt("tShellToContentMs"), TClickToContentMS: parseInt("tClickToContentMs"), HasError: parseBool("hasError"), Journey: parseString("journey"), Action: parseString("action"), IngestedAt: row["ingestedAt"],
		ReadyMS: parseInt("readyMs"), TTFFMS: parseInt("ttffMs"), RebufferCount: parseInt("rebufferCount"), RebufferMS: parseInt("rebufferMs"), EffectivePlaybackMS: parseInt("effectivePlaybackMs"), SeekCount: parseInt("seekCount"), SeekFailureCount: parseInt("seekFailureCount"), SeekCommandMaxMS: parseInt("seekCommandMaxMs"), SeekSettleMaxMS: parseInt("seekSettleMaxMs"), DroppedFrames: parseInt("droppedFrames"), ProcessedVideoFrames: parseInt("processedVideoFrames"), AudioUnderrunCount: parseInt("audioUnderrunCount"), RendererMode: parseString("rendererMode"), DecoderQueueMode: parseString("decoderQueueMode"), DecoderFallbackEnabled: parseBool("decoderFallbackEnabled"), SeekEvidenceSource: parseString("seekEvidenceSource"), DeclaredDurationMS: parseInt("declaredDurationMs"), ObservedDurationMS: parseInt("observedDurationMs"), DurationMismatch: parseBool("durationMismatch"), PlaybackMode: parseString("playbackMode"),
	}
}

func decodeSLSRuntimeLogDrilldown(row map[string]string, revealCorrelation bool) application.RuntimeLogDrilldownItem {
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
		for _, key := range []string{"requestId", "traceId", "spanId", "operationId", "pageName", "surfaceId", "executionId", "workPackageId", "environmentRunId"} {
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

var _ application.EventLogStore = (*SLSEventLogStore)(nil)
var _ application.RuntimeLogStore = (*SLSEventLogStore)(nil)
