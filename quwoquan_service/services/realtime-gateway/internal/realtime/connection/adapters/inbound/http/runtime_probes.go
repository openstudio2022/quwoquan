package http

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"

	rthealth "quwoquan_service/runtime/health"
)

// ReadinessChecker is the connection runtime's typed readiness input. The
// composition root owns which concrete dependencies participate; this adapter
// owns only the HTTP behavior declared by Connection operations.yaml.
type ReadinessChecker interface {
	Check(context.Context) rthealth.Result
}

// RegisterRuntimeProbeRoutes mounts the three Connection-owned runtime query
// operations without leaving their HTTP behavior embedded in cmd/api.
func RegisterRuntimeProbeRoutes(
	mux *http.ServeMux,
	readiness ReadinessChecker,
	metrics http.Handler,
) error {
	if mux == nil || readiness == nil || metrics == nil {
		return errors.New("runtime probes require mux, readiness checker, and metrics handler")
	}
	mux.HandleFunc("GET /healthz", func(writer http.ResponseWriter, _ *http.Request) {
		writer.Header().Set("Content-Type", "application/json")
		writer.WriteHeader(http.StatusOK)
		_ = json.NewEncoder(writer).Encode(map[string]string{"status": "ok"})
	})
	mux.HandleFunc("GET /readyz", func(writer http.ResponseWriter, request *http.Request) {
		if result := readiness.Check(request.Context()); result.Status != "ok" {
			WriteReadinessUnavailable(writer, request)
			return
		}
		writer.Header().Set("Content-Type", "application/json")
		writer.WriteHeader(http.StatusOK)
		_ = json.NewEncoder(writer).Encode(map[string]string{"status": "ready"})
	})
	mux.Handle("GET /metrics", metrics)
	return nil
}
