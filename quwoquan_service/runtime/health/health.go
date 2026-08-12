package health

import (
	"context"
	"encoding/json"
	"net/http"
	"sort"
	"sync"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

var (
	healthCheckStatus = promauto.NewGaugeVec(prometheus.GaugeOpts{
		Namespace: "runtime",
		Subsystem: "health",
		Name:      "check_status",
		Help:      "Latest health check result (1=healthy, 0=unhealthy).",
	}, []string{"check"})
	healthCheckLastSuccess = promauto.NewGaugeVec(prometheus.GaugeOpts{
		Namespace: "runtime",
		Subsystem: "health",
		Name:      "check_last_success_timestamp_seconds",
		Help:      "Unix timestamp of the latest successful health check.",
	}, []string{"check"})
	healthCheckDuration = promauto.NewHistogramVec(prometheus.HistogramOpts{
		Namespace: "runtime",
		Subsystem: "health",
		Name:      "check_duration_seconds",
		Help:      "Health check execution duration in seconds.",
		Buckets:   []float64{0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1, 2},
	}, []string{"check"})
)

type CheckFunc func(ctx context.Context) error

type Checker struct {
	mu     sync.RWMutex
	checks map[string]CheckFunc
}

func NewChecker() *Checker {
	return &Checker{checks: make(map[string]CheckFunc)}
}

func (c *Checker) Register(name string, fn CheckFunc) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.checks[name] = fn
}

type Result struct {
	Status       string            `json:"status"`
	FailedChecks []string          `json:"failedChecks,omitempty"`
	Checks       map[string]string `json:"checks,omitempty"`
}

func (c *Checker) Check(ctx context.Context) Result {
	c.mu.RLock()
	checks := make(map[string]CheckFunc, len(c.checks))
	for k, v := range c.checks {
		checks[k] = v
	}
	c.mu.RUnlock()

	results := make(map[string]string, len(checks))
	failedChecks := make([]string, 0)
	allOK := true

	type checkResult struct {
		name     string
		duration time.Duration
		err      error
	}

	ch := make(chan checkResult, len(checks))
	for name, fn := range checks {
		go func(n string, f CheckFunc) {
			startedAt := time.Now()
			checkCtx, cancel := context.WithTimeout(ctx, 2*time.Second)
			defer cancel()
			err := f(checkCtx)
			ch <- checkResult{
				name:     n,
				duration: time.Since(startedAt),
				err:      err,
			}
		}(name, fn)
	}

	for range checks {
		r := <-ch
		healthCheckDuration.WithLabelValues(r.name).Observe(r.duration.Seconds())
		if r.err != nil {
			results[r.name] = r.err.Error()
			failedChecks = append(failedChecks, r.name)
			healthCheckStatus.WithLabelValues(r.name).Set(0)
			allOK = false
		} else {
			results[r.name] = "ok"
			healthCheckStatus.WithLabelValues(r.name).Set(1)
			healthCheckLastSuccess.WithLabelValues(r.name).Set(
				float64(time.Now().UTC().Unix()),
			)
		}
	}

	status := "ok"
	if !allOK {
		status = "degraded"
	}
	sort.Strings(failedChecks)
	return Result{Status: status, FailedChecks: failedChecks, Checks: results}
}

func (c *Checker) Handler() http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		result := c.Check(r.Context())
		w.Header().Set("Content-Type", "application/json")
		code := http.StatusOK
		if result.Status != "ok" {
			code = http.StatusServiceUnavailable
		}
		w.WriteHeader(code)
		_ = json.NewEncoder(w).Encode(result)
	}
}
