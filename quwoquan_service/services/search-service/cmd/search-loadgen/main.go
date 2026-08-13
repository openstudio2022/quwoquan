// Command search-loadgen measures the search-service retrieve core against a
// real Elasticsearch (search_slo.yaml#load_model calibration).
//
// Scope: the measured path is the canonical query facade
// (SearchService.Execute -> ES recall with function_score pushdown -> filter /
// permission gate -> cursor), i.e. the `search_retrieve_duration_seconds`
// server-side latency. HTTP/gateway/App legs are excluded and belong to the
// e2e P95 budget.
//
// Results are written under .qwq_output/env/repo/runs/search-load/ (deletable,
// rebuildable). local single-node numbers calibrate methodology only and never
// close the real-cluster capacity OPEN
// (search-storage-topology-and-elasticity REQ-003 / GWT-003).
//
// Usage:
//
//	SEARCH_ES_ENDPOINTS=http://localhost:19299 \
//	  go run ./services/search-service/cmd/search-loadgen --seed 5000 \
//	  --stages baseline:30:20s,peak:120:30s,spike:300:20s
package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"math/rand"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	rtsearch "quwoquan_service/runtime/search"
	"quwoquan_service/runtime/search/es"
	"quwoquan_service/services/search-service/internal/search/search_index_view/application"
)

var queryMix = []string{
	"大理", "大理 古城", "旅游 攻略", "环洱海一日路线", "美食 探店",
	"徒步 路线", "摄影师", "dali", "洱海 骑行", "丽江 古城",
}

var seedTitles = []string{
	"大理古城旅游攻略", "环洱海骑行路线", "丽江古城徒步", "苍山索道一日游", "洱海日出摄影点",
	"人民路美食探店", "才村码头日落", "喜洲古镇甜品", "双廊民宿推荐", "沙溪古镇周末",
}

type stage struct {
	name     string
	rps      int
	duration time.Duration
}

type stageResult struct {
	Name        string  `json:"name"`
	TargetRPS   int     `json:"targetRps"`
	DurationS   float64 `json:"durationSeconds"`
	Requests    int64   `json:"requests"`
	Errors      int64   `json:"errors"`
	MeasuredRPS float64 `json:"measuredRps"`
	P50Ms       float64 `json:"p50Ms"`
	P95Ms       float64 `json:"p95Ms"`
	P99Ms       float64 `json:"p99Ms"`
	ErrorRate   float64 `json:"errorRate"`
}

func main() {
	seed := flag.Int("seed", 0, "seed N synthetic documents before the run (0 = reuse existing corpus)")
	stagesFlag := flag.String("stages", "baseline:30:20s,peak:120:30s,spike:300:20s", "name:rps:duration stages")
	esIndex := flag.String("es-index", "", "read alias (default quwoquan_objects)")
	output := flag.String("output", "", "report path (default .qwq_output/env/repo/runs/search-load/<ts>.json)")
	flag.Parse()

	endpoints := splitList(os.Getenv("SEARCH_ES_ENDPOINTS"))
	if len(endpoints) == 0 {
		log.Fatal("[search-loadgen] set SEARCH_ES_ENDPOINTS")
	}
	client, err := es.NewClient(es.Config{
		Endpoints:      endpoints,
		Index:          strings.TrimSpace(*esIndex),
		RequestTimeout: 5 * time.Second,
	})
	if err != nil {
		log.Fatalf("[search-loadgen] es client: %v", err)
	}
	ctx := context.Background()
	if err := client.EnsureIndex(ctx); err != nil {
		log.Fatalf("[search-loadgen] EnsureIndex: %v", err)
	}
	if *seed > 0 {
		seedCorpus(ctx, client, *seed)
	}
	codec, err := application.NewSearchCursorCodec([]byte("search-loadgen-calibration-secret-32b"))
	if err != nil {
		log.Fatalf("[search-loadgen] codec: %v", err)
	}
	service := application.NewSearchService(
		es.NewBackend(client, client.IndexName()),
		application.WithSearchCursorCodec(codec),
	)

	stages, err := parseStages(*stagesFlag)
	if err != nil {
		log.Fatalf("[search-loadgen] stages: %v", err)
	}
	results := make([]stageResult, 0, len(stages))
	for _, st := range stages {
		result := runStage(ctx, service, st)
		results = append(results, result)
		log.Printf("[search-loadgen] %s target=%d rps measured=%.1f rps p50=%.1fms p95=%.1fms p99=%.1fms errors=%.4f",
			result.Name, result.TargetRPS, result.MeasuredRPS, result.P50Ms, result.P95Ms, result.P99Ms, result.ErrorRate)
	}

	report := map[string]any{
		"generatedAt": time.Now().UTC().Format(time.RFC3339),
		"scope":       "search-service retrieve core (SearchService.Execute over real ES); excludes HTTP/gateway/App legs",
		"esEndpoints": endpoints,
		"queryMix":    queryMix,
		"stages":      results,
		// local 单节点结果只校准方法学，不关闭真集群容量阻断（REQ-003）。
		"r_s06_s1_closed_by_local_gamma": false,
	}
	target := strings.TrimSpace(*output)
	if target == "" {
		target = filepath.Join(repoRootQwqOutput(), "env/repo/runs/search-load",
			time.Now().UTC().Format("20060102T150405Z")+".json")
	}
	if err := os.MkdirAll(filepath.Dir(target), 0o755); err != nil {
		log.Fatalf("[search-loadgen] mkdir: %v", err)
	}
	encoded, _ := json.MarshalIndent(report, "", "  ")
	if err := os.WriteFile(target, encoded, 0o644); err != nil {
		log.Fatalf("[search-loadgen] write report: %v", err)
	}
	log.Printf("[search-loadgen] report -> %s", target)
}

// repoRootQwqOutput resolves the repo-root .qwq_output regardless of the
// working directory the tool is launched from (search_slo.yaml benchmark_source
// references the repo-root path). Falls back to CWD-relative when no repo
// marker is found upwards.
func repoRootQwqOutput() string {
	dir, err := os.Getwd()
	if err != nil {
		return ".qwq_output"
	}
	for probe := dir; ; probe = filepath.Dir(probe) {
		if info, err := os.Stat(filepath.Join(probe, "quwoquan_ops")); err == nil && info.IsDir() {
			return filepath.Join(probe, ".qwq_output")
		}
		if filepath.Dir(probe) == probe {
			return ".qwq_output"
		}
	}
}

func runStage(ctx context.Context, service *application.SearchService, st stage) stageResult {
	interval := time.Second / time.Duration(st.rps)
	deadline := time.Now().Add(st.duration)
	var requests, errors int64
	var mu sync.Mutex
	latencies := make([]float64, 0, st.rps*int(st.duration.Seconds())+16)
	var wg sync.WaitGroup
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	random := rand.New(rand.NewSource(42))
	identity := application.QueryExecutionIdentity{
		CandidateDigest: "sha256:" + strings.Repeat("a", 64),
		PolicyDigest:    "sha256:" + strings.Repeat("b", 64),
	}
	for time.Now().Before(deadline) {
		<-ticker.C
		query := queryMix[random.Intn(len(queryMix))]
		wg.Add(1)
		go func(query string) {
			defer wg.Done()
			started := time.Now()
			_, err := service.Execute(ctx, application.QueryInput{
				Query: query, Mode: "result", Limit: 12,
			}, rtsearch.Viewer{}, application.QueryCaller{PrincipalKey: "session:loadgen"}, identity)
			elapsed := float64(time.Since(started).Microseconds()) / 1000.0
			atomic.AddInt64(&requests, 1)
			if err != nil {
				atomic.AddInt64(&errors, 1)
				return
			}
			mu.Lock()
			latencies = append(latencies, elapsed)
			mu.Unlock()
		}(query)
	}
	wg.Wait()
	sort.Float64s(latencies)
	result := stageResult{
		Name: st.name, TargetRPS: st.rps, DurationS: st.duration.Seconds(),
		Requests: requests, Errors: errors,
		MeasuredRPS: float64(requests) / st.duration.Seconds(),
	}
	if requests > 0 {
		result.ErrorRate = float64(errors) / float64(requests)
	}
	result.P50Ms = percentile(latencies, 0.50)
	result.P95Ms = percentile(latencies, 0.95)
	result.P99Ms = percentile(latencies, 0.99)
	return result
}

func percentile(sorted []float64, q float64) float64 {
	if len(sorted) == 0 {
		return 0
	}
	index := int(float64(len(sorted)-1) * q)
	return sorted[index]
}

func seedCorpus(ctx context.Context, client *es.Client, count int) {
	random := rand.New(rand.NewSource(7))
	events := make([]es.ChangeEvent, 0, 500)
	flush := func() {
		if len(events) == 0 {
			return
		}
		if err := client.Bulk(ctx, client.WriteIndexName(), events); err != nil {
			log.Fatalf("[search-loadgen] bulk seed: %v", err)
		}
		events = events[:0]
	}
	contentTypes := []string{"article", "image", "video"}
	buckets := []string{"苍山", "洱海", "古城", "民宿", "徒步", "骑行", "美食", "日落", "甜品", "周末"}
	for index := 0; index < count; index++ {
		bucket := buckets[index%len(buckets)]
		title := bucket + seedTitles[random.Intn(len(seedTitles))] + " 第" + strconv.Itoa(index) + "篇"
		events = append(events, es.ChangeEvent{Op: es.OpUpsert, Doc: rtsearch.Document{
			ObjectType:  "content.post",
			ObjectID:    fmt.Sprintf("loadgen-%06d", index),
			Title:       title,
			Summary:     "压测语料：" + title,
			Body:        strings.Repeat(title+"。", 4),
			ContentType: contentTypes[random.Intn(len(contentTypes))],
			Visibility:  "public",
			Popularity:  float64(random.Intn(5)),
			Freshness:   time.Now().Add(-time.Duration(random.Intn(720)) * time.Hour),
			DeepLink:    "quwoquan://content/posts/loadgen-" + strconv.Itoa(index),
		}})
		if len(events) >= 500 {
			flush()
		}
	}
	flush()
	if err := client.Refresh(ctx); err != nil {
		log.Fatalf("[search-loadgen] refresh: %v", err)
	}
	log.Printf("[search-loadgen] seeded %d documents", count)
}

func parseStages(raw string) ([]stage, error) {
	parts := strings.Split(raw, ",")
	out := make([]stage, 0, len(parts))
	for _, part := range parts {
		fields := strings.Split(strings.TrimSpace(part), ":")
		if len(fields) != 3 {
			return nil, fmt.Errorf("stage %q must be name:rps:duration", part)
		}
		rps, err := strconv.Atoi(fields[1])
		if err != nil || rps <= 0 {
			return nil, fmt.Errorf("stage %q rps invalid", part)
		}
		duration, err := time.ParseDuration(fields[2])
		if err != nil || duration <= 0 {
			return nil, fmt.Errorf("stage %q duration invalid", part)
		}
		out = append(out, stage{name: fields[0], rps: rps, duration: duration})
	}
	return out, nil
}

func splitList(raw string) []string {
	parts := strings.Split(raw, ",")
	out := make([]string, 0, len(parts))
	for _, part := range parts {
		if part = strings.TrimSpace(part); part != "" {
			out = append(out, part)
		}
	}
	return out
}
