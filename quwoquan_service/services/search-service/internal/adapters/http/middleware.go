package http

import (
	"net/http"

	rterrors "quwoquan_service/runtime/errors"
	rtgov "quwoquan_service/runtime/governance"
	"quwoquan_service/services/search-service/internal/infrastructure/searchmetrics"
)

// MaxInflightMiddleware is the search backpressure boundary. When concurrent
// in-flight requests exceed the limiter (a slow ES would otherwise let them pile
// up and collapse the instance), it sheds the request with a typed 503 degrade
// instead of queueing unboundedly. The ceiling is aligned with
// search_slo.yaml#load_model.max_concurrency_per_instance, and shed/inflight are
// exported as SLIs (saturation + controlled-degrade rate).
func MaxInflightMiddleware(limiter *rtgov.InflightLimiter) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if !limiter.Acquire() {
				searchmetrics.ObserveLoadShed("inflight_full")
				w.Header().Set("Retry-After", "1")
				writeErr(w, requestIDFrom(r), rterrors.NewUnavailable(
					moduleSearch, "搜索繁忙，请稍后再试。", "search inflight limit reached"))
				return
			}
			defer limiter.Release()
			searchmetrics.SetInflight(limiter.Inflight())
			next.ServeHTTP(w, r)
			searchmetrics.SetInflight(limiter.Inflight())
		})
	}
}
