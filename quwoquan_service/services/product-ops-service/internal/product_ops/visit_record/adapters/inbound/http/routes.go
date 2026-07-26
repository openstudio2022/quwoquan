// Package httpadapter owns VisitRecord HTTP routes and method rejection behavior.
package httpadapter

import "net/http"

type Handlers struct {
	Record   http.HandlerFunc
	Stats    http.HandlerFunc
	NotFound http.HandlerFunc
}

func Register(mux *http.ServeMux, handlers Handlers) {
	mux.HandleFunc("/ops/visits", requireMethod(http.MethodPost, handlers.Record, handlers.NotFound))
	mux.HandleFunc("/ops/visits/stats", requireMethod(http.MethodGet, handlers.Stats, handlers.NotFound))
}

func requireMethod(method string, handler, notFound http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != method {
			notFound(w, r)
			return
		}
		handler(w, r)
	}
}
