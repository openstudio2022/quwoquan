package persistence

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"regexp"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"quwoquan_service/services/product-ops-service/internal/product_ops/event_record/application"
)

var telemetrySchemaPattern = regexp.MustCompile(`^[a-z][a-z0-9_]{0,62}$`)

// PostgresTelemetryStore 是 beta/gamma integration 的本地遥测 composition。
//
// 它只依赖 application 层的 typed ports；不向业务层暴露 SQL、schema 或
// backend identity。每个测试/环境使用独立 schema，删除 schema 即可完整清理
// raw、startup、runtime、ledger 与 visit 数据。
type PostgresTelemetryStore struct {
	pool   *pgxpool.Pool
	schema string
}

func NewPostgresTelemetryStore(pool *pgxpool.Pool, schema string) (*PostgresTelemetryStore, error) {
	if pool == nil {
		return nil, errors.New("postgres telemetry pool is required")
	}
	schema = strings.TrimSpace(schema)
	if !telemetrySchemaPattern.MatchString(schema) {
		return nil, fmt.Errorf("invalid postgres telemetry schema %q", schema)
	}
	return &PostgresTelemetryStore{pool: pool, schema: schema}, nil
}

// EnsureSchema 创建 integration profile 的最小物理模型。
// raw 表首版不分区，以保证 (batch_key,batch_index) 的全局唯一约束；
// 到达规模门槛后再按 ingest window 迁移分区，不改变 typed port。
func (s *PostgresTelemetryStore) EnsureSchema(ctx context.Context) error {
	schema := quoteTelemetryIdentifier(s.schema)
	ddl := fmt.Sprintf(`
CREATE SCHEMA IF NOT EXISTS %s;
CREATE TABLE IF NOT EXISTS %s.telemetry_batch_ledger (
  batch_key TEXT PRIMARY KEY,
  expected_count INTEGER NOT NULL CHECK (expected_count > 0),
  status TEXT NOT NULL CHECK (status IN ('pending','accepted')),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS %s.telemetry_event_records (
  batch_key TEXT NOT NULL,
  batch_index INTEGER NOT NULL CHECK (batch_index >= 0),
  row_key TEXT NOT NULL,
  log_type TEXT NOT NULL,
  event_type TEXT NOT NULL,
  session_id TEXT NOT NULL,
  page_name TEXT NOT NULL,
  app_version TEXT NOT NULL,
  network_class TEXT NOT NULL,
  result TEXT,
  error_code TEXT,
  occurred_at TIMESTAMPTZ NOT NULL,
  ingested_at TIMESTAMPTZ NOT NULL,
  payload JSONB NOT NULL,
  PRIMARY KEY (batch_key, batch_index),
  UNIQUE (row_key)
);
ALTER TABLE %s.telemetry_event_records
  ADD COLUMN IF NOT EXISTS result TEXT;
CREATE INDEX IF NOT EXISTS telemetry_event_records_occurred_at_idx
  ON %s.telemetry_event_records (occurred_at DESC);
CREATE INDEX IF NOT EXISTS telemetry_event_records_session_idx
  ON %s.telemetry_event_records (session_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS telemetry_event_records_result_idx
  ON %s.telemetry_event_records (event_type, result, occurred_at DESC);
CREATE TABLE IF NOT EXISTS %s.telemetry_startup_records (
  batch_key TEXT NOT NULL,
  batch_index INTEGER NOT NULL CHECK (batch_index >= 0),
  row_key TEXT NOT NULL,
  occurred_at TIMESTAMPTZ NOT NULL,
  ingested_at TIMESTAMPTZ NOT NULL,
  payload JSONB NOT NULL,
  PRIMARY KEY (batch_key, batch_index),
  UNIQUE (row_key)
);
CREATE INDEX IF NOT EXISTS telemetry_startup_records_occurred_at_idx
  ON %s.telemetry_startup_records (occurred_at DESC);
CREATE TABLE IF NOT EXISTS %s.telemetry_runtime_records (
  batch_key TEXT NOT NULL,
  batch_index INTEGER NOT NULL CHECK (batch_index >= 0),
  row_key TEXT NOT NULL,
  occurred_at TIMESTAMPTZ NOT NULL,
  ingested_at TIMESTAMPTZ NOT NULL,
  fields JSONB NOT NULL,
  PRIMARY KEY (batch_key, batch_index),
  UNIQUE (row_key)
);
CREATE INDEX IF NOT EXISTS telemetry_runtime_records_occurred_at_idx
  ON %s.telemetry_runtime_records (occurred_at DESC);
CREATE TABLE IF NOT EXISTS %s.telemetry_visits (
  target_type TEXT NOT NULL,
  target_key TEXT NOT NULL,
  user_id TEXT NOT NULL,
  visit_count INTEGER NOT NULL,
  last_seen_at TIMESTAMPTZ NOT NULL,
  session_id TEXT NOT NULL DEFAULT '',
  source TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (target_type, target_key, user_id)
);
`, schema,
		schema,
		schema,
		schema, schema, schema,
		schema,
		schema,
		schema,
		schema,
		schema,
		schema,
	)
	_, err := s.pool.Exec(ctx, ddl)
	return err
}

func quoteTelemetryIdentifier(value string) string {
	return `"` + strings.ReplaceAll(value, `"`, `""`) + `"`
}

func (s *PostgresTelemetryStore) table(name string) string {
	return quoteTelemetryIdentifier(s.schema) + "." + quoteTelemetryIdentifier(name)
}

func (s *PostgresTelemetryStore) RecordVisit(
	ctx context.Context,
	input application.VisitInput,
) (application.VisitRecord, error) {
	targetType := strings.TrimSpace(input.TargetType)
	targetKey := strings.TrimSpace(input.TargetKey)
	userID := strings.TrimSpace(input.UserID)
	if targetType == "" || targetKey == "" {
		return application.VisitRecord{}, errors.New("visit target is required")
	}
	if userID == "" {
		userID = "anonymous"
	}
	const query = `
INSERT INTO %s (target_type,target_key,user_id,visit_count,last_seen_at,session_id,source)
VALUES ($1,$2,$3,1,NOW(),$4,$5)
ON CONFLICT (target_type,target_key,user_id)
DO UPDATE SET
  visit_count = %s.visit_count + 1,
  last_seen_at = NOW(),
  session_id = EXCLUDED.session_id,
  source = EXCLUDED.source
RETURNING visit_count,last_seen_at,session_id,source`
	stmt := fmt.Sprintf(query, s.table("telemetry_visits"), s.table("telemetry_visits"))
	var record application.VisitRecord
	var lastSeen time.Time
	if err := s.pool.QueryRow(ctx, stmt, targetType, targetKey, userID,
		strings.TrimSpace(input.SessionID), strings.TrimSpace(input.Source)).
		Scan(&record.VisitCount, &lastSeen, &record.SessionID, &record.Source); err != nil {
		return application.VisitRecord{}, err
	}
	record.TargetType = targetType
	record.TargetKey = targetKey
	record.UserID = userID
	record.LastSeenAt = lastSeen.UTC().Format(time.RFC3339Nano)
	return record, nil
}

func (s *PostgresTelemetryStore) GetVisit(
	ctx context.Context,
	userID, targetType, targetKey string,
) (application.VisitRecord, bool, error) {
	var record application.VisitRecord
	var lastSeen time.Time
	err := s.pool.QueryRow(ctx, fmt.Sprintf(`
SELECT target_type,target_key,user_id,visit_count,last_seen_at,session_id,source
FROM %s
WHERE user_id=$1 AND target_type=$2 AND target_key=$3`, s.table("telemetry_visits")),
		strings.TrimSpace(userID), strings.TrimSpace(targetType), strings.TrimSpace(targetKey)).
		Scan(&record.TargetType, &record.TargetKey, &record.UserID,
			&record.VisitCount, &lastSeen, &record.SessionID, &record.Source)
	if errors.Is(err, pgx.ErrNoRows) {
		return application.VisitRecord{}, false, nil
	}
	if err != nil {
		return application.VisitRecord{}, false, err
	}
	record.LastSeenAt = lastSeen.UTC().Format(time.RFC3339Nano)
	return record, true, nil
}

func (s *PostgresTelemetryStore) GetVisitStats(
	ctx context.Context,
	query application.VisitStatsQuery,
) (application.VisitStats, error) {
	rows, err := s.pool.Query(ctx, fmt.Sprintf(`
SELECT target_type,target_key,user_id,visit_count,last_seen_at,session_id,source
FROM %s
WHERE target_type=$1 AND target_key=$2
ORDER BY last_seen_at DESC`, s.table("telemetry_visits")),
		strings.TrimSpace(query.TargetType), strings.TrimSpace(query.TargetKey))
	if err != nil {
		return application.VisitStats{}, err
	}
	defer rows.Close()
	out := application.VisitStats{Items: make([]application.VisitRecord, 0)}
	for rows.Next() {
		var item application.VisitRecord
		var lastSeen time.Time
		if err := rows.Scan(
			&item.TargetType, &item.TargetKey, &item.UserID, &item.VisitCount,
			&lastSeen, &item.SessionID, &item.Source,
		); err != nil {
			return application.VisitStats{}, err
		}
		item.LastSeenAt = lastSeen.UTC().Format(time.RFC3339Nano)
		out.TotalVisits += item.VisitCount
		out.Items = append(out.Items, item)
	}
	return out, rows.Err()
}

func (s *PostgresTelemetryStore) Begin(
	ctx context.Context,
	batchKey string,
	count int,
) (application.BatchLedgerState, error) {
	if strings.TrimSpace(batchKey) == "" || count <= 0 {
		return "", errors.New("invalid telemetry batch ledger key or count")
	}
	var inserted bool
	if err := s.pool.QueryRow(ctx, fmt.Sprintf(`
INSERT INTO %s (batch_key,expected_count,status)
VALUES ($1,$2,'pending')
ON CONFLICT (batch_key) DO NOTHING
RETURNING TRUE`, s.table("telemetry_batch_ledger")), batchKey, count).
		Scan(&inserted); err == nil && inserted {
		return application.BatchLedgerNew, nil
	} else if err != nil && !errors.Is(err, pgx.ErrNoRows) {
		return "", err
	}
	var expected int
	var status string
	if err := s.pool.QueryRow(ctx, fmt.Sprintf(`
SELECT expected_count,status FROM %s WHERE batch_key=$1`,
		s.table("telemetry_batch_ledger")), batchKey).Scan(&expected, &status); err != nil {
		return "", err
	}
	if expected != count {
		return "", fmt.Errorf("telemetry batch %q count conflict: got %d want %d", batchKey, count, expected)
	}
	switch status {
	case "pending":
		return application.BatchLedgerPending, nil
	case "accepted":
		return application.BatchLedgerAccepted, nil
	default:
		return "", fmt.Errorf("unknown telemetry batch ledger status %q", status)
	}
}

func (s *PostgresTelemetryStore) MarkAccepted(
	ctx context.Context,
	batchKey string,
	count int,
) error {
	tag, err := s.pool.Exec(ctx, fmt.Sprintf(`
UPDATE %s SET status='accepted',expected_count=$2,updated_at=NOW()
WHERE batch_key=$1`, s.table("telemetry_batch_ledger")), batchKey, count)
	if err != nil {
		return err
	}
	if tag.RowsAffected() != 1 {
		return fmt.Errorf("telemetry batch %q does not exist", batchKey)
	}
	return nil
}

func (s *PostgresTelemetryStore) PutEventBatch(
	ctx context.Context,
	batchKey string,
	records []application.EventRecord,
) error {
	if len(records) == 0 {
		return nil
	}
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)
	stmt := fmt.Sprintf(`
INSERT INTO %s (
 batch_key,batch_index,row_key,log_type,event_type,session_id,page_name,
 app_version,network_class,result,error_code,occurred_at,ingested_at,payload
) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)
ON CONFLICT (batch_key,batch_index) DO NOTHING`, s.table("telemetry_event_records"))
	for index, record := range records {
		occurredAt, err := time.Parse(time.RFC3339Nano, record.OccurredAt)
		if err != nil {
			return fmt.Errorf("event[%d] occurredAt: %w", index, err)
		}
		payload, err := json.Marshal(record.EventRecordInput)
		if err != nil {
			return err
		}
		errorCode := ""
		if record.ErrorCode != nil {
			errorCode = strings.TrimSpace(*record.ErrorCode)
		}
		result := ""
		if record.Result != nil {
			result = strings.TrimSpace(*record.Result)
		}
		if _, err := tx.Exec(ctx, stmt,
			batchKey, index, telemetryRowKey(batchKey, index),
			record.LogType, record.EventType, record.SessionID, record.PageName,
			record.AppVersion, record.NetworkClass, nullableText(result), nullableText(errorCode),
			occurredAt.UTC(), record.IngestedAt.UTC(), payload,
		); err != nil {
			return err
		}
	}
	return tx.Commit(ctx)
}

func (s *PostgresTelemetryStore) HasEventBatch(
	ctx context.Context,
	batchKey string,
	expected int,
) (bool, error) {
	var count int
	if err := s.pool.QueryRow(ctx, fmt.Sprintf(`
SELECT COUNT(*) FROM %s WHERE batch_key=$1`,
		s.table("telemetry_event_records")), batchKey).Scan(&count); err != nil {
		return false, err
	}
	return count == expected, nil
}

func (s *PostgresTelemetryStore) PutStartupDiagnostics(
	ctx context.Context,
	batchKey string,
	records []application.StartupDiagnosticRecord,
) error {
	if len(records) == 0 {
		return nil
	}
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)
	stmt := fmt.Sprintf(`
INSERT INTO %s (batch_key,batch_index,row_key,occurred_at,ingested_at,payload)
VALUES ($1,$2,$3,$4,NOW(),$5)
ON CONFLICT (batch_key,batch_index) DO NOTHING`, s.table("telemetry_startup_records"))
	for index, record := range records {
		occurredAt, err := time.Parse(time.RFC3339Nano, record.OccurredAt)
		if err != nil {
			return fmt.Errorf("startup record[%d] occurredAt: %w", index, err)
		}
		payload, err := json.Marshal(record)
		if err != nil {
			return err
		}
		if _, err := tx.Exec(ctx, stmt, batchKey, index,
			telemetryRowKey(batchKey, index), occurredAt.UTC(), payload); err != nil {
			return err
		}
	}
	return tx.Commit(ctx)
}

func (s *PostgresTelemetryStore) HasStartupDiagnosticBatch(
	ctx context.Context,
	batchKey string,
	expected int,
) (bool, error) {
	var count int
	if err := s.pool.QueryRow(ctx, fmt.Sprintf(`
SELECT COUNT(*) FROM %s WHERE batch_key=$1`,
		s.table("telemetry_startup_records")), batchKey).Scan(&count); err != nil {
		return false, err
	}
	return count == expected, nil
}

func (s *PostgresTelemetryStore) PutRuntimeLogBatch(
	ctx context.Context,
	batchKey string,
	records []application.RuntimeLogRecord,
) error {
	if len(records) == 0 {
		return nil
	}
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)
	stmt := fmt.Sprintf(`
INSERT INTO %s (batch_key,batch_index,row_key,occurred_at,ingested_at,fields)
VALUES ($1,$2,$3,$4,$5,$6)
ON CONFLICT (batch_key,batch_index) DO NOTHING`, s.table("telemetry_runtime_records"))
	for index, record := range records {
		occurredAt, err := time.Parse(time.RFC3339Nano, record.Fields["occurredAt"])
		if err != nil {
			return fmt.Errorf("runtime record[%d] occurredAt: %w", index, err)
		}
		fields, err := json.Marshal(record.Fields)
		if err != nil {
			return err
		}
		if _, err := tx.Exec(ctx, stmt, batchKey, index,
			telemetryRowKey(batchKey, index), occurredAt.UTC(), record.IngestedAt.UTC(), fields); err != nil {
			return err
		}
	}
	return tx.Commit(ctx)
}

func (s *PostgresTelemetryStore) HasRuntimeLogBatch(
	ctx context.Context,
	batchKey string,
	expected int,
) (bool, error) {
	var count int
	if err := s.pool.QueryRow(ctx, fmt.Sprintf(`
SELECT COUNT(*) FROM %s WHERE batch_key=$1`,
		s.table("telemetry_runtime_records")), batchKey).Scan(&count); err != nil {
		return false, err
	}
	return count == expected, nil
}

func telemetryRowKey(batchKey string, index int) string {
	return fmt.Sprintf("%s:%06d", batchKey, index)
}

func nullableText(value string) any {
	if strings.TrimSpace(value) == "" {
		return nil
	}
	return value
}

type postgresEventRow struct {
	rowKey     string
	payload    []byte
	ingestedAt time.Time
}

func (s *PostgresTelemetryStore) queryEventRows(
	ctx context.Context,
	query application.EventSummaryQuery,
	includeSession string,
) ([]postgresEventRow, error) {
	conditions := []string{"occurred_at >= $1", "occurred_at < $2"}
	args := []any{query.From.UTC(), query.To.UTC()}
	add := func(column, value string) {
		if strings.TrimSpace(value) == "" {
			return
		}
		args = append(args, value)
		conditions = append(conditions, fmt.Sprintf("%s = $%d", column, len(args)))
	}
	add("log_type", query.LogType)
	add("event_type", query.EventType)
	add("page_name", query.PageName)
	add("app_version", query.AppVersion)
	add("network_class", query.NetworkClass)
	add("result", query.Result)
	add("error_code", query.ErrorCode)
	if strings.TrimSpace(includeSession) != "" {
		add("session_id", includeSession)
	}
	rows, err := s.pool.Query(ctx, fmt.Sprintf(`
SELECT row_key,payload,ingested_at FROM %s
WHERE %s
ORDER BY occurred_at DESC,row_key DESC`,
		s.table("telemetry_event_records"), strings.Join(conditions, " AND ")), args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := make([]postgresEventRow, 0)
	for rows.Next() {
		var item postgresEventRow
		if err := rows.Scan(&item.rowKey, &item.payload, &item.ingestedAt); err != nil {
			return nil, err
		}
		out = append(out, item)
	}
	return out, rows.Err()
}

// ReadRtcMediaQoeSummary 为 beta/gamma Postgres telemetry composition 提供与
// production SLS 相同的 raw-event 口径；缺表/坏数据直接返回错误，不回退 fixture。
func (s *PostgresTelemetryStore) ReadRtcMediaQoeSummary(
	ctx context.Context,
	query application.RtcMediaQoeSummaryQuery,
) (application.RtcMediaQoeSummarySlice, error) {
	rows, err := s.pool.Query(
		ctx,
		postgresRtcMediaQoeHourlySQL(s.table("telemetry_event_records")),
		query.From.UTC(),
		query.To.UTC(),
	)
	if err != nil {
		return application.RtcMediaQoeSummarySlice{}, fmt.Errorf(
			"query postgres rtc_media_qoe hourly raw: %w",
			err,
		)
	}
	hourly := make([]application.RtcMediaQoeAggregate, 0, 24)
	for rows.Next() {
		var item application.RtcMediaQoeAggregate
		if err := rows.Scan(
			&item.BucketStart,
			&item.EffectiveSampleCount,
			&item.MediaConnectedCount,
			&item.ConnectP95MS,
			&item.ConnectionLostCount,
			&item.ReconnectCount,
			&item.GeneratedThrough,
		); err != nil {
			rows.Close()
			return application.RtcMediaQoeSummarySlice{}, fmt.Errorf(
				"scan postgres rtc_media_qoe hourly raw: %w",
				err,
			)
		}
		hourly = append(hourly, item)
	}
	if err := rows.Err(); err != nil {
		rows.Close()
		return application.RtcMediaQoeSummarySlice{}, fmt.Errorf(
			"iterate postgres rtc_media_qoe hourly raw: %w",
			err,
		)
	}
	rows.Close()

	total := application.RtcMediaQoeAggregate{}
	if err := s.pool.QueryRow(
		ctx,
		postgresRtcMediaQoeTotalSQL(s.table("telemetry_event_records")),
		query.From.UTC(),
		query.To.UTC(),
	).Scan(
		&total.EffectiveSampleCount,
		&total.MediaConnectedCount,
		&total.ConnectP95MS,
		&total.ConnectionLostCount,
		&total.ReconnectCount,
		&total.GeneratedThrough,
	); err != nil {
		return application.RtcMediaQoeSummarySlice{}, fmt.Errorf(
			"query postgres rtc_media_qoe total raw: %w",
			err,
		)
	}
	return application.BuildRtcMediaQoeSummary(
		query,
		hourly,
		total,
		"raw_records",
	), nil
}

func postgresRtcMediaQoeHourlySQL(table string) string {
	return fmt.Sprintf(`
WITH valid_rtc_media_qoe AS (
  SELECT
    date_trunc('hour', occurred_at) AS bucket_start,
    (payload->>'mediaConnected')::BOOLEAN AS media_connected,
    (payload->>'connectTimeMs')::DOUBLE PRECISION AS connect_time_ms,
    payload->>'result' AS result,
    (payload->>'reconnectCount')::BIGINT AS reconnect_count,
    ingested_at
  FROM %s
  WHERE event_type = 'rtc_media_qoe'
    AND occurred_at >= $1
    AND occurred_at < $2
    AND payload ? 'result'
    AND payload->>'result' <> ''
    AND payload->>'result' <> 'abandoned'
)
SELECT
  bucket_start,
  COUNT(*)::BIGINT AS effective_sample_count,
  COUNT(*) FILTER (WHERE media_connected)::BIGINT AS media_connected_count,
  percentile_cont(0.95) WITHIN GROUP (ORDER BY connect_time_ms)
    FILTER (WHERE media_connected AND connect_time_ms IS NOT NULL) AS connect_p95_ms,
  COUNT(*) FILTER (
    WHERE media_connected AND result = 'connection_lost'
  )::BIGINT AS connection_lost_count,
  COALESCE(SUM(reconnect_count), 0)::BIGINT AS reconnect_count,
  MAX(ingested_at) AS generated_through
FROM valid_rtc_media_qoe
GROUP BY bucket_start
ORDER BY bucket_start`, table)
}

func postgresRtcMediaQoeTotalSQL(table string) string {
	return fmt.Sprintf(`
WITH valid_rtc_media_qoe AS (
  SELECT
    (payload->>'mediaConnected')::BOOLEAN AS media_connected,
    (payload->>'connectTimeMs')::DOUBLE PRECISION AS connect_time_ms,
    payload->>'result' AS result,
    (payload->>'reconnectCount')::BIGINT AS reconnect_count,
    ingested_at
  FROM %s
  WHERE event_type = 'rtc_media_qoe'
    AND occurred_at >= $1
    AND occurred_at < $2
    AND payload ? 'result'
    AND payload->>'result' <> ''
    AND payload->>'result' <> 'abandoned'
)
SELECT
  COUNT(*)::BIGINT AS effective_sample_count,
  COUNT(*) FILTER (WHERE media_connected)::BIGINT AS media_connected_count,
  percentile_cont(0.95) WITHIN GROUP (ORDER BY connect_time_ms)
    FILTER (WHERE media_connected AND connect_time_ms IS NOT NULL) AS connect_p95_ms,
  COUNT(*) FILTER (
    WHERE media_connected AND result = 'connection_lost'
  )::BIGINT AS connection_lost_count,
  COALESCE(SUM(reconnect_count), 0)::BIGINT AS reconnect_count,
  MAX(ingested_at) AS generated_through
FROM valid_rtc_media_qoe`, table)
}

// GetPageExperienceStats 按 pageName 聚合页面体验事实（热力图数据源）。
func (s *PostgresTelemetryStore) GetPageExperienceStats(
	ctx context.Context,
	query application.PageExperienceQuery,
) ([]application.PageExperienceStat, error) {
	rows, err := s.pool.Query(ctx, fmt.Sprintf(`
SELECT page_name,
  COUNT(*) FILTER (WHERE event_type = 'page_open') AS opens,
  COALESCE(AVG((payload->>'readyMs')::BIGINT) FILTER (WHERE event_type = 'page_open' AND payload ? 'readyMs'), 0) AS avg_ready_ms,
  COUNT(*) FILTER (WHERE event_type = 'page_open' AND payload ? 'readyMs') AS ready_samples,
  COALESCE(AVG((payload->>'durationMs')::BIGINT) FILTER (WHERE event_type = 'page_return' AND payload ? 'durationMs'), 0) AS avg_stay_ms,
  COUNT(*) FILTER (WHERE event_type = 'page_return' AND payload ? 'durationMs') AS stay_samples,
  COUNT(*) FILTER (WHERE event_type = 'runtime_exception') AS runtime_errors
FROM %s
WHERE occurred_at >= $1 AND occurred_at < $2 AND page_name <> ''
GROUP BY page_name
ORDER BY opens DESC
LIMIT 500`, s.table("telemetry_event_records")), query.From, query.To)
	if err != nil {
		return nil, fmt.Errorf("query page experience stats: %w", err)
	}
	defer rows.Close()
	items := make([]application.PageExperienceStat, 0)
	for rows.Next() {
		var item application.PageExperienceStat
		if err := rows.Scan(
			&item.PageName, &item.Opens, &item.AvgReadyMs, &item.ReadySamples,
			&item.AvgStayMs, &item.StaySamples, &item.RuntimeErrors,
		); err != nil {
			return nil, err
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

// ListDistinctSessions 返回窗口内 distinct sessionId 与事件总数（增长聚合用）。
func (s *PostgresTelemetryStore) ListDistinctSessions(
	ctx context.Context,
	from, to time.Time,
	limit int,
) ([]string, int64, error) {
	var totalEvents int64
	if err := s.pool.QueryRow(ctx, fmt.Sprintf(
		`SELECT COUNT(*) FROM %s WHERE occurred_at >= $1 AND occurred_at < $2`,
		s.table("telemetry_event_records"),
	), from, to).Scan(&totalEvents); err != nil {
		return nil, 0, fmt.Errorf("count telemetry events: %w", err)
	}
	rows, err := s.pool.Query(ctx, fmt.Sprintf(
		`SELECT DISTINCT session_id FROM %s WHERE occurred_at >= $1 AND occurred_at < $2 LIMIT $3`,
		s.table("telemetry_event_records"),
	), from, to, limit)
	if err != nil {
		return nil, 0, fmt.Errorf("list distinct telemetry sessions: %w", err)
	}
	defer rows.Close()
	sessions := make([]string, 0)
	for rows.Next() {
		var sessionID string
		if err := rows.Scan(&sessionID); err != nil {
			return nil, 0, err
		}
		sessions = append(sessions, sessionID)
	}
	return sessions, totalEvents, rows.Err()
}

func (s *PostgresTelemetryStore) GetEventSummary(
	ctx context.Context,
	query application.EventSummaryQuery,
) (application.EventSummary, error) {
	rows, err := s.queryEventRows(ctx, query, "")
	if err != nil {
		return application.EventSummary{}, err
	}
	out := application.EventSummary{
		TotalCount:        int64(len(rows)),
		DimensionCounters: map[string]map[string]int{},
		SourceKind:        "raw_records",
		Freshness:         "near_realtime",
		GeneratedThrough:  query.To.UTC().Format(time.RFC3339Nano),
		ActualFrom:        query.From.UTC().Format(time.RFC3339Nano),
		ActualTo:          query.To.UTC().Format(time.RFC3339Nano),
	}
	sessions := map[string]struct{}{}
	for _, row := range rows {
		var input application.EventRecordInput
		if err := json.Unmarshal(row.payload, &input); err != nil {
			return application.EventSummary{}, err
		}
		if input.SessionID != "" {
			sessions[input.SessionID] = struct{}{}
		}
		for dimension, value := range map[string]string{
			"logType": input.LogType, "eventType": input.EventType,
			"pageName": input.PageName, "appVersion": input.AppVersion,
			"networkClass": input.NetworkClass,
		} {
			if strings.TrimSpace(value) == "" {
				continue
			}
			if out.DimensionCounters[dimension] == nil {
				out.DimensionCounters[dimension] = map[string]int{}
			}
			out.DimensionCounters[dimension][value]++
		}
		if input.Journey != nil {
			addDimension(out.DimensionCounters, "journey", *input.Journey)
		}
		if input.Action != nil {
			addDimension(out.DimensionCounters, "action", *input.Action)
		}
		if input.Result != nil {
			addDimension(out.DimensionCounters, "result", *input.Result)
		}
	}
	out.SessionCount = int64(len(sessions))
	return out, nil
}

func (s *PostgresTelemetryStore) GetEventDrilldown(
	ctx context.Context,
	query application.EventDrilldownQuery,
) (application.EventDrilldown, error) {
	summaryQuery := application.EventSummaryQuery{
		LogType: query.LogType, EventType: query.EventType, PageName: query.PageName,
		AppVersion: query.AppVersion, NetworkClass: query.NetworkClass, Result: query.Result, ErrorCode: query.ErrorCode,
		From: query.From, To: query.To,
	}
	rows, err := s.queryEventRows(ctx, summaryQuery, query.SessionID)
	if err != nil {
		return application.EventDrilldown{}, err
	}
	out := application.EventDrilldown{
		TotalCount:       int64(len(rows)),
		Items:            make([]application.EventDrilldownItem, 0, minTelemetryInt(query.Limit, len(rows))),
		SourceKind:       "raw_records",
		Freshness:        "near_realtime",
		GeneratedThrough: query.To.UTC().Format(time.RFC3339Nano),
		ActualFrom:       query.From.UTC().Format(time.RFC3339Nano),
		ActualTo:         query.To.UTC().Format(time.RFC3339Nano),
	}
	limit := query.Limit
	if limit <= 0 || limit > 100 {
		limit = 50
	}
	for _, row := range rows {
		if len(out.Items) >= limit {
			break
		}
		var input application.EventRecordInput
		if err := json.Unmarshal(row.payload, &input); err != nil {
			return application.EventDrilldown{}, err
		}
		out.Items = append(out.Items, eventDrilldownItemFromInput(row.rowKey, row.ingestedAt, input))
	}
	return out, nil
}

func eventDrilldownItemFromInput(
	rowKey string,
	ingestedAt time.Time,
	input application.EventRecordInput,
) application.EventDrilldownItem {
	return application.EventDrilldownItem{
		RowKey: rowKey, LogType: input.LogType, EventType: input.EventType,
		SessionID: input.SessionID, PageName: input.PageName, OccurredAt: input.OccurredAt,
		DeviceManufacturer: input.DeviceManufacturer, DeviceModel: input.DeviceModel,
		AppVersion: input.AppVersion, NetworkClass: input.NetworkClass,
		DevicePlatform: input.DevicePlatform,
		DurationMS:     input.DurationMS, Result: input.Result, FailReasonCode: input.FailReasonCode,
		ErrorCode: input.ErrorCode, OperationID: input.OperationID,
		RequestID: input.RequestID, TraceID: input.TraceID,
		RecoveryAction: input.RecoveryAction, SurfaceID: input.SurfaceID,
		DetectionSource: input.DetectionSource, TerminalState: input.TerminalState,
		HTTPStatus: input.HTTPStatus,
		CallStack:  input.CallStack, TClickToFirstFrameMS: input.TClickToFirstFrameMS,
		TFirstFrameToShellMS: input.TFirstFrameToShellMS, TShellToContentMS: input.TShellToContentMS,
		TClickToContentMS: input.TClickToContentMS, HasError: input.HasError,
		Journey: input.Journey, Action: input.Action, ReadyMS: input.ReadyMS, TTFFMS: input.TTFFMS,
		RebufferCount: input.RebufferCount, RebufferMS: input.RebufferMS,
		SeekCount: input.SeekCount, SeekFailureCount: input.SeekFailureCount,
		SeekCommandMaxMS: input.SeekCommandMaxMS, SeekSettleMaxMS: input.SeekSettleMaxMS,
		DroppedFrames: input.DroppedFrames, ProcessedVideoFrames: input.ProcessedVideoFrames,
		AudioUnderrunCount: input.AudioUnderrunCount, RendererMode: input.RendererMode,
		DecoderQueueMode: input.DecoderQueueMode, DecoderFallbackEnabled: input.DecoderFallbackEnabled,
		SeekEvidenceSource: input.SeekEvidenceSource, DeclaredDurationMS: input.DeclaredDurationMS,
		ObservedDurationMS: input.ObservedDurationMS, DurationMismatch: input.DurationMismatch,
		PlaybackMode: input.PlaybackMode, IngestedAt: ingestedAt.UTC().Format(time.RFC3339Nano),
	}
}

func minTelemetryInt(a, b int) int {
	if a <= 0 || a > b {
		return b
	}
	return a
}

// Ensure the single integration composition satisfies every typed telemetry port.
var _ application.VisitTelemetryStore = (*PostgresTelemetryStore)(nil)
var _ application.EventLogStore = (*PostgresTelemetryStore)(nil)
var _ application.EventBatchLedger = (*PostgresTelemetryStore)(nil)
var _ application.RuntimeLogStore = (*PostgresTelemetryStore)(nil)
