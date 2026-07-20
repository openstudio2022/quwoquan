package runtimeobservability

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

const (
	runtimeLogSpoolMaxBatches      = CatalogServiceSpoolMaxBatches
	runtimeLogDeadLetterMaxBatches = CatalogServiceDLQMaxBatches
	runtimeLogSpoolTTL             = time.Duration(CatalogDeliveryTTLHours) * time.Hour
	runtimeLogExportInterval       = 2 * time.Second
)

var (
	runtimeLogExportTotal = promauto.NewCounterVec(prometheus.CounterOpts{
		Namespace: "runtime",
		Subsystem: "log_export",
		Name:      "batches_total",
		Help:      "Runtime log batches by service and reliable delivery result.",
	}, []string{"service", "result"})
	runtimeLogSpoolPending = promauto.NewGaugeVec(prometheus.GaugeOpts{
		Namespace: "runtime",
		Subsystem: "log_export",
		Name:      "spool_pending",
		Help:      "Pending durable runtime log spool batches by service.",
	}, []string{"service"})
	runtimeLogDeadLetterPending = promauto.NewGaugeVec(prometheus.GaugeOpts{
		Namespace: "runtime",
		Subsystem: "log_export",
		Name:      "dead_letter_pending",
		Help:      "Runtime log dead-letter batches by service.",
	}, []string{"service"})
)

type spooledRuntimeLogBatch struct {
	ID            string              `json:"id"`
	Service       string              `json:"service"`
	CreatedAt     time.Time           `json:"createdAt"`
	ExpiresAt     time.Time           `json:"expiresAt"`
	NextAttemptAt time.Time           `json:"nextAttemptAt"`
	Attempts      int                 `json:"attempts"`
	LastFailure   string              `json:"lastFailure,omitempty"`
	Records       []map[string]string `json:"records"`
}

// HTTPRuntimeLogExporter provides a bounded durable spool between service
// stdout and Product Ops. It deliberately never logs through the runtime logger
// itself, preventing an exporter feedback loop.
type HTTPRuntimeLogExporter struct {
	endpoint string
	token    string
	spoolDir string
	deadDir  string
	service  string
	client   *http.Client
	enabled  bool

	writeMu sync.Mutex
	flushMu sync.Mutex
	wake    chan struct{}
	stop    chan struct{}
	done    chan struct{}
	once    sync.Once
}

// NewHTTPRuntimeLogFieldExporter creates a reliable exporter.
//
// All-empty endpoint/token/spoolDir disables remote export for local/alpha.
// A partial configuration is rejected so production cannot silently run
// without a durable spool.
func NewHTTPRuntimeLogFieldExporter(
	endpoint string,
	token string,
	spoolDir string,
) (*HTTPRuntimeLogExporter, error) {
	endpoint = strings.TrimSpace(endpoint)
	token = strings.TrimSpace(token)
	spoolDir = strings.TrimSpace(spoolDir)
	exporter := &HTTPRuntimeLogExporter{
		endpoint: endpoint,
		token:    token,
		spoolDir: spoolDir,
		client:   &http.Client{Timeout: 3 * time.Second},
		wake:     make(chan struct{}, 1),
		stop:     make(chan struct{}),
		done:     make(chan struct{}),
	}
	if endpoint == "" && token == "" && spoolDir == "" {
		close(exporter.done)
		return exporter, nil
	}
	if endpoint == "" || token == "" || spoolDir == "" {
		return nil, errors.New("runtime log exporter endpoint, token and spool dir must be configured together")
	}
	exporter.deadDir = filepath.Join(spoolDir, "dead-letter")
	if err := os.MkdirAll(exporter.deadDir, 0o700); err != nil {
		return nil, fmt.Errorf("create runtime log spool: %w", err)
	}
	exporter.enabled = true
	go exporter.run()
	return exporter, nil
}

// Export appends a batch to the durable spool and wakes the async sender.
// It is safe to pass directly as RuntimeLogFieldBatchExporter.
func (e *HTTPRuntimeLogExporter) Export(records []map[string]string) {
	if e == nil || !e.enabled || len(records) == 0 {
		return
	}
	payload, err := json.Marshal(map[string]any{"records": records})
	if err != nil {
		return
	}
	digest := sha256.Sum256(payload)
	id := hex.EncodeToString(digest[:])
	service := runtimeLogBatchService(records)
	now := time.Now().UTC()
	batch := spooledRuntimeLogBatch{
		ID:            id,
		Service:       service,
		CreatedAt:     now,
		ExpiresAt:     now.Add(runtimeLogSpoolTTL),
		NextAttemptAt: now,
		Records:       cloneRuntimeLogFields(records),
	}

	e.writeMu.Lock()
	defer e.writeMu.Unlock()
	if e.service == "" {
		e.service = service
	}
	path := e.batchPath(id)
	if _, statErr := os.Stat(path); statErr == nil {
		return
	}
	if !e.ensureSpoolCapacityLocked(runtimeLogBatchCritical(records), now) {
		runtimeLogExportTotal.WithLabelValues(service, "dropped_capacity").Inc()
		return
	}
	if err := writeRuntimeLogBatchAtomic(path, batch); err != nil {
		runtimeLogExportTotal.WithLabelValues(service, "spool_write_failed").Inc()
		return
	}
	runtimeLogExportTotal.WithLabelValues(service, "spooled").Inc()
	e.refreshMetricsLocked()
	select {
	case e.wake <- struct{}{}:
	default:
	}
}

func (e *HTTPRuntimeLogExporter) Close() {
	if e == nil || !e.enabled {
		return
	}
	e.once.Do(func() {
		close(e.stop)
		<-e.done
	})
}

func (e *HTTPRuntimeLogExporter) run() {
	defer close(e.done)
	ticker := time.NewTicker(runtimeLogExportInterval)
	defer ticker.Stop()
	for {
		select {
		case <-e.wake:
			_ = e.FlushOnce(context.Background())
		case <-ticker.C:
			_ = e.FlushOnce(context.Background())
		case <-e.stop:
			ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
			_ = e.FlushOnce(ctx)
			cancel()
			return
		}
	}
}

// FlushOnce is exported for deterministic local-contract and health probes.
func (e *HTTPRuntimeLogExporter) FlushOnce(ctx context.Context) error {
	if e == nil || !e.enabled {
		return nil
	}
	e.flushMu.Lock()
	defer e.flushMu.Unlock()

	entries, err := os.ReadDir(e.spoolDir)
	if err != nil {
		return fmt.Errorf("read runtime log spool: %w", err)
	}
	sort.Slice(entries, func(i, j int) bool { return entries[i].Name() < entries[j].Name() })
	now := time.Now().UTC()
	for _, entry := range entries {
		if entry.IsDir() || filepath.Ext(entry.Name()) != ".json" {
			continue
		}
		path := filepath.Join(e.spoolDir, entry.Name())
		batch, readErr := readRuntimeLogBatch(path)
		if readErr != nil {
			e.moveToDeadLetter(path, spooledRuntimeLogBatch{
				ID:          strings.TrimSuffix(entry.Name(), ".json"),
				Service:     defaultRuntimeLogService(e.service),
				CreatedAt:   now,
				ExpiresAt:   now,
				LastFailure: "spool_corrupt",
			})
			continue
		}
		if batch.ExpiresAt.Before(now) {
			batch.LastFailure = "ttl_expired"
			e.moveToDeadLetter(path, batch)
			runtimeLogExportTotal.WithLabelValues(batch.Service, "dead_letter_ttl").Inc()
			continue
		}
		if batch.NextAttemptAt.After(now) {
			continue
		}
		result, sendErr := e.send(ctx, batch)
		if sendErr == nil && result == "delivered" {
			_ = os.Remove(path)
			runtimeLogExportTotal.WithLabelValues(batch.Service, "delivered").Inc()
			continue
		}
		if result == "permanent" {
			batch.LastFailure = sendErr.Error()
			e.moveToDeadLetter(path, batch)
			runtimeLogExportTotal.WithLabelValues(batch.Service, "dead_letter_permanent").Inc()
			continue
		}
		batch.Attempts++
		batch.LastFailure = runtimeLogFailureReason(sendErr)
		batch.NextAttemptAt = now.Add(runtimeLogRetryDelay(batch))
		if writeErr := writeRuntimeLogBatchAtomic(path, batch); writeErr != nil {
			return fmt.Errorf("update runtime log spool retry: %w", writeErr)
		}
		runtimeLogExportTotal.WithLabelValues(batch.Service, "retry_scheduled").Inc()
	}
	e.writeMu.Lock()
	e.refreshMetricsLocked()
	e.writeMu.Unlock()
	return nil
}

func (e *HTTPRuntimeLogExporter) send(
	ctx context.Context,
	batch spooledRuntimeLogBatch,
) (string, error) {
	body, err := json.Marshal(map[string]any{"records": batch.Records})
	if err != nil {
		return "permanent", fmt.Errorf("encode batch: %w", err)
	}
	request, err := http.NewRequestWithContext(ctx, http.MethodPost, e.endpoint, bytes.NewReader(body))
	if err != nil {
		return "permanent", fmt.Errorf("build request: %w", err)
	}
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Idempotency-Key", batch.ID)
	request.Header.Set("X-Runtime-Log-Ingest-Token", e.token)
	response, err := e.client.Do(request)
	if err != nil {
		return "transient", fmt.Errorf("request: %w", err)
	}
	defer response.Body.Close()
	_, _ = io.Copy(io.Discard, io.LimitReader(response.Body, 64*1024))
	if response.StatusCode >= 200 && response.StatusCode < 300 {
		return "delivered", nil
	}
	if response.StatusCode == http.StatusUnauthorized ||
		response.StatusCode == http.StatusRequestTimeout ||
		response.StatusCode == http.StatusTooEarly ||
		response.StatusCode == http.StatusTooManyRequests ||
		response.StatusCode >= 500 {
		return "transient", fmt.Errorf("http_%d", response.StatusCode)
	}
	return "permanent", fmt.Errorf("http_%d", response.StatusCode)
}

func (e *HTTPRuntimeLogExporter) ensureSpoolCapacityLocked(critical bool, now time.Time) bool {
	files, _ := runtimeLogJSONFiles(e.spoolDir)
	if len(files) < runtimeLogSpoolMaxBatches {
		return true
	}
	for _, path := range files {
		batch, err := readRuntimeLogBatch(path)
		if err != nil || !runtimeLogBatchCritical(batch.Records) {
			if err == nil {
				batch.LastFailure = "capacity_evicted"
			} else {
				batch = spooledRuntimeLogBatch{
					ID:          strings.TrimSuffix(filepath.Base(path), ".json"),
					Service:     defaultRuntimeLogService(e.service),
					CreatedAt:   now,
					ExpiresAt:   now,
					LastFailure: "spool_corrupt",
				}
			}
			e.moveToDeadLetter(path, batch)
			return true
		}
	}
	if !critical {
		return false
	}
	// 全部为关键日志时仍保持有界：最旧关键批进入 DLQ，并显式计数。
	oldest := files[0]
	batch, _ := readRuntimeLogBatch(oldest)
	batch.LastFailure = "capacity_evicted_critical"
	e.moveToDeadLetter(oldest, batch)
	runtimeLogExportTotal.WithLabelValues(batch.Service, "critical_capacity_evicted").Inc()
	return true
}

func (e *HTTPRuntimeLogExporter) moveToDeadLetter(path string, batch spooledRuntimeLogBatch) {
	if batch.ID == "" {
		batch.ID = strings.TrimSuffix(filepath.Base(path), ".json")
	}
	deadPath := filepath.Join(e.deadDir, batch.ID+".json")
	_ = writeRuntimeLogBatchAtomic(deadPath, batch)
	_ = os.Remove(path)
	deadFiles, _ := runtimeLogJSONFiles(e.deadDir)
	for len(deadFiles) > runtimeLogDeadLetterMaxBatches {
		_ = os.Remove(deadFiles[0])
		deadFiles = deadFiles[1:]
	}
}

func (e *HTTPRuntimeLogExporter) refreshMetricsLocked() {
	service := defaultRuntimeLogService(e.service)
	pending, _ := runtimeLogJSONFiles(e.spoolDir)
	dead, _ := runtimeLogJSONFiles(e.deadDir)
	runtimeLogSpoolPending.WithLabelValues(service).Set(float64(len(pending)))
	runtimeLogDeadLetterPending.WithLabelValues(service).Set(float64(len(dead)))
}

func (e *HTTPRuntimeLogExporter) batchPath(id string) string {
	return filepath.Join(e.spoolDir, id+".json")
}

func writeRuntimeLogBatchAtomic(path string, batch spooledRuntimeLogBatch) error {
	payload, err := json.Marshal(batch)
	if err != nil {
		return err
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		return err
	}
	tmp, err := os.CreateTemp(filepath.Dir(path), ".runtime-log-*.tmp")
	if err != nil {
		return err
	}
	tmpPath := tmp.Name()
	defer os.Remove(tmpPath)
	if err := tmp.Chmod(0o600); err != nil {
		_ = tmp.Close()
		return err
	}
	if _, err := tmp.Write(payload); err != nil {
		_ = tmp.Close()
		return err
	}
	if err := tmp.Sync(); err != nil {
		_ = tmp.Close()
		return err
	}
	if err := tmp.Close(); err != nil {
		return err
	}
	return os.Rename(tmpPath, path)
}

func readRuntimeLogBatch(path string) (spooledRuntimeLogBatch, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return spooledRuntimeLogBatch{}, err
	}
	var batch spooledRuntimeLogBatch
	if err := json.Unmarshal(raw, &batch); err != nil {
		return spooledRuntimeLogBatch{}, err
	}
	if len(batch.ID) != 64 || batch.Service == "" || len(batch.Records) == 0 ||
		batch.CreatedAt.IsZero() || batch.ExpiresAt.IsZero() {
		return spooledRuntimeLogBatch{}, errors.New("runtime log spool batch is incomplete")
	}
	return batch, nil
}

func runtimeLogJSONFiles(dir string) ([]string, error) {
	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil, err
	}
	files := make([]string, 0, len(entries))
	for _, entry := range entries {
		if !entry.IsDir() && filepath.Ext(entry.Name()) == ".json" {
			files = append(files, filepath.Join(dir, entry.Name()))
		}
	}
	sort.Strings(files)
	return files, nil
}

func runtimeLogBatchService(records []map[string]string) string {
	for _, record := range records {
		if service := strings.TrimSpace(record["resourceService"]); service != "" {
			return service
		}
	}
	return "unknown"
}

func defaultRuntimeLogService(value string) string {
	if value = strings.TrimSpace(value); value != "" {
		return value
	}
	return "unknown"
}

func runtimeLogBatchCritical(records []map[string]string) bool {
	for _, record := range records {
		switch strings.ToUpper(strings.TrimSpace(record["severity"])) {
		case "WARN", "ERROR":
			return true
		}
	}
	return false
}

func cloneRuntimeLogFields(records []map[string]string) []map[string]string {
	out := make([]map[string]string, 0, len(records))
	for _, record := range records {
		clone := make(map[string]string, len(record))
		for key, value := range record {
			clone[key] = value
		}
		out = append(out, clone)
	}
	return out
}

func runtimeLogRetryDelay(batch spooledRuntimeLogBatch) time.Duration {
	exponent := batch.Attempts - 1
	if exponent < 0 {
		exponent = 0
	}
	if exponent > CatalogRetryMaxExponent {
		exponent = CatalogRetryMaxExponent
	}
	base := CatalogRetryBaseSeconds * (1 << exponent)
	if base > CatalogRetryMaxSeconds {
		base = CatalogRetryMaxSeconds
	}
	jitterSeed, _ := strconv.ParseInt(batch.ID[:8], 16, 64)
	jitter := time.Duration(int64(base)*int64(jitterSeed%int64(CatalogRetryJitterPercent))) * time.Second / 100
	return time.Duration(base)*time.Second + jitter
}

func runtimeLogFailureReason(err error) string {
	if err == nil {
		return "unknown"
	}
	value := err.Error()
	if len(value) > 128 {
		return value[:128]
	}
	return value
}
