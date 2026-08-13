// Command loadgen 按契约派生的负载画像执行受控压测，并输出与 SLO 对照的性能证据。
//
// 负载画像由编排层（stackctl loadtest）从 services/<svc>/contracts/**/operations.yaml
// 派生：operation、method、path 与 slo 阈值都来自契约单一真相源，本工具只负责执行
// 与统计，不承载第二套 path 或阈值清单。
//
// spec_ref: specs/feature-tree/runtime/runtime-testinfra/performance-load-harness/spec.md#gwt-001
package main

import (
	"crypto/tls"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"math"
	"net/http"
	"os"
	"sort"
	"strings"
	"sync"
	"time"
)

const (
	profileSchema = "quwoquan.loadgen.profile"
	reportSchema  = "quwoquan.loadgen.report"

	verdictPass  = "pass"
	verdictFail  = "fail"
	verdictNoSLO = "no_slo"

	maxProfileBytes = 4 << 20
)

type operationProfile struct {
	OperationID            string  `json:"operationId"`
	Method                 string  `json:"method"`
	Path                   string  `json:"path"`
	SLOLatencyP95Ms        int     `json:"sloLatencyP95Ms"`
	SLOAvailabilityPercent float64 `json:"sloAvailabilityPercent"`
}

type loadProfile struct {
	Schema         string `json:"schema"`
	BaseURL        string `json:"baseUrl"`
	Concurrency    int    `json:"concurrency"`
	RequestsPerOp  int    `json:"requestsPerOperation"`
	TimeoutMs      int    `json:"timeoutMs"`
	AllowMutations bool   `json:"allowMutations"`
	// TLSInsecureSkipVerify 仅供本地受管 TLS（*-local target 自签 CA）取证；
	// 编排层不得对远端目标设置。
	TLSInsecureSkipVerify bool               `json:"tlsInsecureSkipVerify"`
	Headers               map[string]string  `json:"headers"`
	Operations            []operationProfile `json:"operations"`
}

type operationResult struct {
	OperationID            string   `json:"operationId"`
	Method                 string   `json:"method"`
	Path                   string   `json:"path"`
	Samples                int      `json:"samples"`
	Failures               int      `json:"failures"`
	P50Ms                  float64  `json:"p50Ms"`
	P95Ms                  float64  `json:"p95Ms"`
	P99Ms                  float64  `json:"p99Ms"`
	AvailabilityPercent    float64  `json:"availabilityPercent"`
	ThroughputRps          float64  `json:"throughputRps"`
	SLOLatencyP95Ms        int      `json:"sloLatencyP95Ms"`
	SLOAvailabilityPercent float64  `json:"sloAvailabilityPercent"`
	Verdict                string   `json:"verdict"`
	FailureReasons         []string `json:"failureReasons"`
}

type loadReport struct {
	Schema      string            `json:"schema"`
	BaseURL     string            `json:"baseUrl"`
	Concurrency int               `json:"concurrency"`
	StartedAt   string            `json:"startedAt"`
	FinishedAt  string            `json:"finishedAt"`
	Operations  []operationResult `json:"operations"`
	Verdict     string            `json:"verdict"`
}

func main() {
	profilePath := flag.String("profile", "", "path to the loadgen profile JSON derived from contracts")
	flag.Parse()
	if *profilePath == "" {
		fmt.Fprintln(os.Stderr, "loadgen: --profile is required")
		os.Exit(2)
	}
	profile, err := readProfile(*profilePath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "loadgen: %v\n", err)
		os.Exit(2)
	}
	client := &http.Client{
		Timeout: time.Duration(profile.TimeoutMs) * time.Millisecond,
	}
	if profile.TLSInsecureSkipVerify {
		client.Transport = &http.Transport{
			TLSClientConfig: &tls.Config{InsecureSkipVerify: true}, // #nosec G402 本地受管 TLS 取证
		}
	}
	report, err := runProfile(profile, client)
	if err != nil {
		fmt.Fprintf(os.Stderr, "loadgen: %v\n", err)
		os.Exit(2)
	}
	encoder := json.NewEncoder(os.Stdout)
	encoder.SetIndent("", "  ")
	if err := encoder.Encode(report); err != nil {
		fmt.Fprintf(os.Stderr, "loadgen: encode report: %v\n", err)
		os.Exit(2)
	}
	if report.Verdict == verdictFail {
		os.Exit(1)
	}
}

func readProfile(path string) (loadProfile, error) {
	file, err := os.Open(path)
	if err != nil {
		return loadProfile{}, fmt.Errorf("open profile: %w", err)
	}
	defer file.Close()
	raw, err := io.ReadAll(io.LimitReader(file, maxProfileBytes))
	if err != nil {
		return loadProfile{}, fmt.Errorf("read profile: %w", err)
	}
	var profile loadProfile
	if err := json.Unmarshal(raw, &profile); err != nil {
		return loadProfile{}, fmt.Errorf("decode profile: %w", err)
	}
	return profile, nil
}

func validateProfile(profile loadProfile) error {
	if profile.Schema != profileSchema {
		return fmt.Errorf("profile schema must be %q", profileSchema)
	}
	if !strings.HasPrefix(profile.BaseURL, "http://") && !strings.HasPrefix(profile.BaseURL, "https://") {
		return errors.New("profile baseUrl must be an absolute http(s) URL")
	}
	if profile.Concurrency < 1 || profile.Concurrency > 64 {
		return errors.New("profile concurrency must be within 1..64")
	}
	if profile.RequestsPerOp < 1 || profile.RequestsPerOp > 100000 {
		return errors.New("profile requestsPerOperation must be within 1..100000")
	}
	if profile.TimeoutMs < 1 {
		return errors.New("profile timeoutMs must be positive")
	}
	if len(profile.Operations) == 0 {
		return errors.New("profile declares no operations")
	}
	for _, operation := range profile.Operations {
		if operation.OperationID == "" || operation.Method == "" || operation.Path == "" {
			return errors.New("every operation requires operationId, method and path")
		}
		method := strings.ToUpper(operation.Method)
		if !profile.AllowMutations && method != http.MethodGet && method != http.MethodHead {
			return fmt.Errorf(
				"operation %s uses %s but mutations are not allowed by this profile",
				operation.OperationID, method,
			)
		}
	}
	return nil
}

func runProfile(profile loadProfile, client *http.Client) (loadReport, error) {
	if err := validateProfile(profile); err != nil {
		return loadReport{}, err
	}
	report := loadReport{
		Schema:      reportSchema,
		BaseURL:     profile.BaseURL,
		Concurrency: profile.Concurrency,
		StartedAt:   time.Now().UTC().Format(time.RFC3339),
	}
	for _, operation := range profile.Operations {
		result := runOperation(profile, operation, client)
		report.Operations = append(report.Operations, result)
	}
	report.FinishedAt = time.Now().UTC().Format(time.RFC3339)
	report.Verdict = overallVerdict(report.Operations)
	return report, nil
}

func runOperation(profile loadProfile, operation operationProfile, client *http.Client) operationResult {
	url := strings.TrimRight(profile.BaseURL, "/") + operation.Path
	latencies := make([]float64, 0, profile.RequestsPerOp)
	failures := 0
	var mu sync.Mutex
	var wg sync.WaitGroup
	tasks := make(chan struct{}, profile.RequestsPerOp)
	for i := 0; i < profile.RequestsPerOp; i++ {
		tasks <- struct{}{}
	}
	close(tasks)
	started := time.Now()
	for worker := 0; worker < profile.Concurrency; worker++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for range tasks {
				elapsedMs, ok := executeRequest(client, strings.ToUpper(operation.Method), url, profile.Headers)
				mu.Lock()
				if ok {
					latencies = append(latencies, elapsedMs)
				} else {
					failures++
				}
				mu.Unlock()
			}
		}()
	}
	wg.Wait()
	wall := time.Since(started).Seconds()
	samples := len(latencies) + failures
	sort.Float64s(latencies)
	availability := 0.0
	if samples > 0 {
		availability = float64(len(latencies)) / float64(samples) * 100
	}
	throughput := 0.0
	if wall > 0 {
		throughput = float64(samples) / wall
	}
	result := operationResult{
		OperationID:            operation.OperationID,
		Method:                 strings.ToUpper(operation.Method),
		Path:                   operation.Path,
		Samples:                samples,
		Failures:               failures,
		P50Ms:                  percentile(latencies, 0.50),
		P95Ms:                  percentile(latencies, 0.95),
		P99Ms:                  percentile(latencies, 0.99),
		AvailabilityPercent:    round2(availability),
		ThroughputRps:          round2(throughput),
		SLOLatencyP95Ms:        operation.SLOLatencyP95Ms,
		SLOAvailabilityPercent: operation.SLOAvailabilityPercent,
	}
	result.Verdict, result.FailureReasons = judgeOperation(result)
	return result
}

func executeRequest(client *http.Client, method, url string, headers map[string]string) (float64, bool) {
	request, err := http.NewRequest(method, url, nil)
	if err != nil {
		return 0, false
	}
	request.Header.Set("Accept", "application/json")
	for key, value := range headers {
		request.Header.Set(key, value)
	}
	started := time.Now()
	response, err := client.Do(request)
	elapsedMs := float64(time.Since(started).Microseconds()) / 1000
	if err != nil {
		return elapsedMs, false
	}
	_, _ = io.Copy(io.Discard, response.Body)
	_ = response.Body.Close()
	if response.StatusCode < 200 || response.StatusCode > 299 {
		return elapsedMs, false
	}
	return elapsedMs, true
}

// judgeOperation 只在契约声明了 SLO 时输出 pass/fail；无声明返回 no_slo，
// 不得输出伪判定（REQ-002）。
func judgeOperation(result operationResult) (string, []string) {
	if result.SLOLatencyP95Ms <= 0 && result.SLOAvailabilityPercent <= 0 {
		return verdictNoSLO, nil
	}
	reasons := make([]string, 0, 2)
	if result.SLOLatencyP95Ms > 0 && result.P95Ms > float64(result.SLOLatencyP95Ms) {
		reasons = append(reasons, fmt.Sprintf(
			"p95 %.2fms exceeds slo latency_p95_ms %d", result.P95Ms, result.SLOLatencyP95Ms,
		))
	}
	if result.SLOAvailabilityPercent > 0 && result.AvailabilityPercent < result.SLOAvailabilityPercent {
		reasons = append(reasons, fmt.Sprintf(
			"availability %.2f%% below slo availability_percent %.2f",
			result.AvailabilityPercent, result.SLOAvailabilityPercent,
		))
	}
	if len(reasons) > 0 {
		return verdictFail, reasons
	}
	return verdictPass, nil
}

func overallVerdict(results []operationResult) string {
	sawJudged := false
	for _, result := range results {
		switch result.Verdict {
		case verdictFail:
			return verdictFail
		case verdictPass:
			sawJudged = true
		}
	}
	if sawJudged {
		return verdictPass
	}
	return verdictNoSLO
}

func percentile(sorted []float64, quantile float64) float64 {
	if len(sorted) == 0 {
		return 0
	}
	index := int(math.Ceil(quantile*float64(len(sorted)))) - 1
	if index < 0 {
		index = 0
	}
	if index >= len(sorted) {
		index = len(sorted) - 1
	}
	return round2(sorted[index])
}

func round2(value float64) float64 {
	return math.Round(value*100) / 100
}
