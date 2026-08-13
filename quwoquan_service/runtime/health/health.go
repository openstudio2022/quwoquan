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

const defaultCheckTimeout = 2 * time.Second

type checkDefinition struct {
	fn      CheckFunc
	timeout time.Duration
}

type Checker struct {
	mu     sync.RWMutex
	checks map[string]checkDefinition
}

func NewChecker() *Checker {
	return &Checker{checks: make(map[string]checkDefinition)}
}

func (c *Checker) Register(name string, fn CheckFunc) {
	c.RegisterWithTimeout(name, defaultCheckTimeout, fn)
}

// RegisterWithTimeout keeps dependency-specific readiness budgets explicit.
// The caller must align this timeout with the dependency client's own bounded
// selection/connect policy so the checker does not cancel a valid recovery
// attempt before that policy can complete.
func (c *Checker) RegisterWithTimeout(
	name string,
	timeout time.Duration,
	fn CheckFunc,
) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.checks[name] = checkDefinition{fn: fn, timeout: timeout}
}

type Result struct {
	Status       string            `json:"status"`
	FailedChecks []string          `json:"failedChecks,omitempty"`
	Checks       map[string]string `json:"checks,omitempty"`
}

func (c *Checker) Check(ctx context.Context) Result {
	c.mu.RLock()
	checks := make(map[string]checkDefinition, len(c.checks))
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
	for name, definition := range checks {
		go func(n string, check checkDefinition) {
			startedAt := time.Now()
			checkCtx, cancel := context.WithTimeout(ctx, check.timeout)
			defer cancel()
			err := check.fn(checkCtx)
			ch <- checkResult{
				name:     n,
				duration: time.Since(startedAt),
				err:      err,
			}
		}(name, definition)
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
