package health

import (
	"context"
	"encoding/json"
	"net/http"
	"sync"
	"time"
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
	Status string            `json:"status"`
	Checks map[string]string `json:"checks,omitempty"`
}

func (c *Checker) Check(ctx context.Context) Result {
	c.mu.RLock()
	checks := make(map[string]CheckFunc, len(c.checks))
	for k, v := range c.checks {
		checks[k] = v
	}
	c.mu.RUnlock()

	results := make(map[string]string, len(checks))
	allOK := true

	type checkResult struct {
		name string
		err  error
	}

	ch := make(chan checkResult, len(checks))
	for name, fn := range checks {
		go func(n string, f CheckFunc) {
			checkCtx, cancel := context.WithTimeout(ctx, 2*time.Second)
			defer cancel()
			ch <- checkResult{name: n, err: f(checkCtx)}
		}(name, fn)
	}

	for range checks {
		r := <-ch
		if r.err != nil {
			results[r.name] = r.err.Error()
			allOK = false
		} else {
			results[r.name] = "ok"
		}
	}

	status := "ok"
	if !allOK {
		status = "degraded"
	}
	return Result{Status: status, Checks: results}
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
