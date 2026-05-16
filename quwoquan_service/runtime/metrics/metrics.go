package runtimemetrics

import (
	"net/http"
	"sync"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/collectors"
	"github.com/prometheus/client_golang/prometheus/promhttp"
)

var registerOnce sync.Once

// MustRegisterRuntimeCollectors registers Go runtime (goroutines, GC, memory)
// and process (FDs, CPU, resident memory) collectors with the default registry.
// Safe to call multiple times; subsequent calls are no-ops.
func MustRegisterRuntimeCollectors() {
	registerOnce.Do(func() {
		prometheus.MustRegister(
			collectors.NewGoCollector(),
			collectors.NewProcessCollector(collectors.ProcessCollectorOpts{}),
		)
	})
}

// Handler returns a standard promhttp handler for /metrics.
func Handler() http.Handler {
	MustRegisterRuntimeCollectors()
	return promhttp.Handler()
}

// RegisterTo adds a /metrics endpoint to the given ServeMux.
func RegisterTo(mux *http.ServeMux) {
	mux.Handle("/metrics", Handler())
}
