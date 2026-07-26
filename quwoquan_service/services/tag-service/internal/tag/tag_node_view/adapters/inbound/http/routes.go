// Package httpadapter owns TagNodeView command/query route registration.
package httpadapter

import "net/http"

type Handlers struct {
	Resolve        http.HandlerFunc
	ListChildren   http.HandlerFunc
	SharedTags     http.HandlerFunc
	Inverted       http.HandlerFunc
	ListDimensions http.HandlerFunc
	Suggest        http.HandlerFunc
	Validate       http.HandlerFunc
	Search         http.HandlerFunc
	Related        http.HandlerFunc
	SearchByTags   http.HandlerFunc
	Cooccurrence   http.HandlerFunc
	RelatedObjects http.HandlerFunc
}

func Register(mux *http.ServeMux, handlers Handlers) {
	mux.HandleFunc("GET /tag/resolve", handlers.Resolve)
	mux.HandleFunc("GET /tag/children", handlers.ListChildren)
	mux.HandleFunc("GET /tag/shared-tags", handlers.SharedTags)
	mux.HandleFunc("GET /tag/inverted", handlers.Inverted)
	mux.HandleFunc("GET /tag/dimensions", handlers.ListDimensions)
	mux.HandleFunc("GET /tag/suggest", handlers.Suggest)
	mux.HandleFunc("POST /tag/validate", handlers.Validate)
	mux.HandleFunc("GET /tag/search", handlers.Search)
	mux.HandleFunc("GET /tag/related", handlers.Related)
	mux.HandleFunc("POST /tag/search-by-tags", handlers.SearchByTags)
	mux.HandleFunc("GET /tag/graph/cooccurrence", handlers.Cooccurrence)
	mux.HandleFunc("GET /tag/related-objects", handlers.RelatedObjects)
}
