// Package httpadapter owns ExperimentAssignmentFact HTTP routes.
package httpadapter

import "net/http"

func Register(mux *http.ServeMux, handler http.Handler) {
	mux.Handle("GET /ops/experiments/{experimentId}/assignment", handler)
	mux.Handle("GET /ops/experiments/{experimentId}/stats", handler)
}
