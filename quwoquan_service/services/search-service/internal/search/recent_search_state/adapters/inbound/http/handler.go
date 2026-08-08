package httpadapter

import (
	"encoding/json"
	"net/http"
	"strings"
	"time"

	rterrors "quwoquan_service/runtime/errors"
	recentsearch "quwoquan_service/services/search-service/internal/search/recent_search_state/application"
	"quwoquan_service/services/search-service/internal/search/recent_search_state/domain/model"
)

// RecentSearchHandler 承载 RecentSearchState 的 4 条 canonical 路由。
// actor 为网关注入的 persona（X-Client-Persona-Id / X-Client-User-Id），
// auth_mode required：缺失身份返回结构化 401。
type RecentSearchHandler struct {
	facade   *recentsearch.Facade
	observer recentsearch.Observer
}

func NewRecentSearchHandler(
	facade *recentsearch.Facade,
	observers ...recentsearch.Observer,
) *RecentSearchHandler {
	handler := &RecentSearchHandler{facade: facade}
	if len(observers) > 0 {
		handler.observer = observers[0]
	}
	return handler
}

// Register 挂载路由到既有 mux。
func (h *RecentSearchHandler) Register(mux *http.ServeMux) {
	Register(mux, Handlers{
		List: h.handleList, Upsert: h.handleUpsert,
		Delete: h.handleDelete, Clear: h.handleClear,
	})
}

type recentEntryWire struct {
	EntryID   string `json:"entryId"`
	Query     string `json:"query"`
	Scope     string `json:"scope"`
	Facet     string `json:"facet,omitempty"`
	UpdatedAt string `json:"updatedAt"`
}

func recentEntryToWire(entry model.Entry) recentEntryWire {
	wire := recentEntryWire{
		EntryID: entry.EntryID,
		Query:   entry.Query,
		Scope:   entry.Scope,
		Facet:   entry.Facet,
	}
	if !entry.UpdatedAt.IsZero() {
		wire.UpdatedAt = entry.UpdatedAt.UTC().Format("2006-01-02T15:04:05.000Z07:00")
	}
	return wire
}

func (h *RecentSearchHandler) handleList(w http.ResponseWriter, r *http.Request) {
	started := time.Now()
	status := "error"
	defer func() { h.observe("list", status, started) }()
	requestID := requestIDFrom(r)
	personaID, ok := requiredPersona(w, r, requestID)
	if !ok {
		status = "unauthorized"
		return
	}
	entries, err := h.facade.List(r.Context(), personaID, r.URL.Query().Get("scope"))
	if err != nil {
		writeErr(w, requestID, err)
		return
	}
	items := make([]recentEntryWire, 0, len(entries))
	for _, entry := range entries {
		items = append(items, recentEntryToWire(entry))
	}
	status = "ok"
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}

func (h *RecentSearchHandler) handleUpsert(w http.ResponseWriter, r *http.Request) {
	started := time.Now()
	status := "error"
	defer func() { h.observe("upsert", status, started) }()
	requestID := requestIDFrom(r)
	personaID, ok := requiredPersona(w, r, requestID)
	if !ok {
		status = "unauthorized"
		return
	}
	r.Body = http.MaxBytesReader(w, r.Body, recentSearchMaxRequestBodyBytes)
	var body struct {
		Query string `json:"query"`
		Scope string `json:"scope"`
		Facet string `json:"facet"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		status = "invalid"
		writeErr(w, requestID, recentInvalidArgument("decode recent upsert body: "+err.Error()))
		return
	}
	result, err := h.facade.Upsert(r.Context(), recentsearch.UpsertCommand{
		PersonaID:      personaID,
		Scope:          body.Scope,
		Facet:          body.Facet,
		Query:          body.Query,
		IdempotencyKey: idempotencyKeyFrom(r),
	})
	if err != nil {
		writeErr(w, requestID, err)
		return
	}
	status = "ok"
	writeJSON(w, http.StatusOK, recentEntryToWire(result.Entry))
}

func (h *RecentSearchHandler) handleDelete(w http.ResponseWriter, r *http.Request) {
	started := time.Now()
	status := "error"
	defer func() { h.observe("delete", status, started) }()
	requestID := requestIDFrom(r)
	personaID, ok := requiredPersona(w, r, requestID)
	if !ok {
		status = "unauthorized"
		return
	}
	_, err := h.facade.Delete(r.Context(), recentsearch.DeleteCommand{
		PersonaID:      personaID,
		EntryID:        r.PathValue("entryId"),
		IdempotencyKey: idempotencyKeyFrom(r),
	})
	if err != nil {
		writeErr(w, requestID, err)
		return
	}
	status = "ok"
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok"})
}

func (h *RecentSearchHandler) handleClear(w http.ResponseWriter, r *http.Request) {
	started := time.Now()
	status := "error"
	defer func() { h.observe("clear", status, started) }()
	requestID := requestIDFrom(r)
	personaID, ok := requiredPersona(w, r, requestID)
	if !ok {
		status = "unauthorized"
		return
	}
	_, err := h.facade.Clear(r.Context(), recentsearch.ClearCommand{
		PersonaID:      personaID,
		Scope:          r.URL.Query().Get("scope"),
		IdempotencyKey: idempotencyKeyFrom(r),
	})
	if err != nil {
		writeErr(w, requestID, err)
		return
	}
	status = "ok"
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok"})
}

func (h *RecentSearchHandler) observe(operation, status string, started time.Time) {
	if h.observer == nil {
		return
	}
	h.observer.ObserveRecentSearch(recentsearch.Observation{
		Operation: operation,
		Status:    status,
		Seconds:   time.Since(started).Seconds(),
	})
}

// requiredPersona 提取网关注入的 persona 身份；persona 优先（persona 语义），
// 回退 user id。缺失时按 auth_mode=required 返回结构化 401。
func requiredPersona(w http.ResponseWriter, r *http.Request, requestID string) (string, bool) {
	personaID := strings.TrimSpace(r.Header.Get("X-Client-Persona-Id"))
	if personaID == "" {
		personaID = strings.TrimSpace(r.Header.Get("X-Client-User-Id"))
	}
	if personaID == "" {
		appErr := rterrors.NewAppError(
			rterrors.NewCode(rterrors.ModuleGateway, rterrors.KindUser, "unauthorized"),
			"请先登录后再继续", "recent search requires an authenticated persona actor")
		appErr.HTTPStatus = http.StatusUnauthorized
		writeErr(w, requestID, appErr)
		return "", false
	}
	return personaID, true
}

func idempotencyKeyFrom(r *http.Request) string {
	return strings.TrimSpace(r.Header.Get("Idempotency-Key"))
}

func recentInvalidArgument(debug string) error {
	return rterrors.NewAppError(
		rterrors.NewCode(moduleSearch, rterrors.KindUser, "recent_invalid_argument"),
		"最近搜索请求格式不正确。",
		debug,
	).WithMetadata("recent_invalid_argument", http.StatusBadRequest).
		WithRecoveryDirective("surface", "inlineCard", 0)
}
