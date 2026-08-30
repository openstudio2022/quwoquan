package http

import (
	"net/http"

	rtgov "quwoquan_service/runtime/governance"
	"quwoquan_service/services/search-service/internal/search/search_index_view/application"
)

// MaxInflightMiddleware is the search backpressure boundary. When concurrent
// in-flight requests exceed the limiter (a slow ES would otherwise let them pile
// up and collapse the instance), it sheds the request with a typed 503 degrade
// instead of queueing unboundedly. The ceiling is aligned with
// search_slo.yaml#load_model.max_concurrency_per_instance, and shed/inflight are
// exported as SLIs (saturation + controlled-degrade rate).
func MaxInflightMiddleware(
	limiter *rtgov.InflightLimiter,
	observer application.SearchLoadObserver,
) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if !limiter.Acquire() {
				if observer != nil {
					observer.ObserveLoadShed("inflight_full")
				}
				writeSearchUnavailable(
					w,
					requestIDFrom(r),
					"search inflight limit reached",
				)
				return
			}
			defer func() {
				limiter.Release()
				if observer != nil {
					observer.SetInflight(limiter.Inflight())
				}
			}()
			if observer != nil {
				observer.SetInflight(limiter.Inflight())
			}
			next.ServeHTTP(w, r)
		})
	}
}
