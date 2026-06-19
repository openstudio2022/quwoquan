package es

import (
	rtsearch "quwoquan_service/runtime/search"
)

// NewRecallBackend assembles the production recall backend: ES as primary with a
// transparent fallback to the native store backend on any ES error. This keeps
// ES outages from breaking the search path (degrade to native), matching
// backend_select.FallbackBackend semantics. Selection stays transparent to all
// callers of rtsearch.Retrieve.
func NewRecallBackend(client *Client, native rtsearch.RecallBackend) rtsearch.RecallBackend {
	return rtsearch.FallbackBackend{
		Primary:  NewBackend(client, client.IndexName()),
		Fallback: native,
	}
}
