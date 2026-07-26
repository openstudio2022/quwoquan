package httpadapter

import (
	"encoding/json"
	"errors"
	"io"
	"net"
	"net/http"
	"strings"
	"sync"
	"time"

	"quwoquan_service/services/product-ops-service/internal/product_ops/recovery_failure/application"
)

const maxRecoveryFailureBytes = 40 << 10

type ErrorWriter func(http.ResponseWriter, *http.Request, int, string, string)

type Handler struct {
	service    *application.Service
	writeError ErrorWriter
	limiter    *sourceLimiter
}

func NewHandler(service *application.Service, writeError ErrorWriter) *Handler {
	return &Handler{service: service, writeError: writeError, limiter: newSourceLimiter()}
}

func (h *Handler) Register(mux *http.ServeMux) {
	mux.HandleFunc("/ops/recovery-failures", h.report)
}

func (h *Handler) report(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		h.writeError(w, r, http.StatusNotFound, "接口不存在", "route not found")
		return
	}
	if h.service == nil {
		h.writeError(w, r, http.StatusServiceUnavailable, "异常记录暂未接收", "recovery failure service unavailable")
		return
	}
	if !h.limiter.allow(sourceAddress(r), time.Now()) {
		h.writeError(w, r, http.StatusServiceUnavailable, "异常记录暂未接收", "recovery failure rate limit exceeded")
		return
	}
	var failure application.Failure
	decoder := json.NewDecoder(io.LimitReader(r.Body, maxRecoveryFailureBytes+1))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&failure); err != nil {
		h.writeError(w, r, http.StatusBadRequest, "异常记录无效", err.Error())
		return
	}
	var trailing any
	if err := decoder.Decode(&trailing); err != io.EOF {
		h.writeError(w, r, http.StatusBadRequest, "异常记录无效", "request body must contain exactly one JSON object")
		return
	}
	if err := h.service.Report(r.Context(), failure); err != nil {
		if errors.Is(err, application.ErrInvalidRecoveryFailure) {
			h.writeError(w, r, http.StatusBadRequest, "异常记录无效", err.Error())
			return
		}
		h.writeError(w, r, http.StatusServiceUnavailable, "异常记录暂未接收", err.Error())
		return
	}
	w.Header().Set("Cache-Control", "no-store")
	w.WriteHeader(http.StatusNoContent)
}

type rateWindow struct {
	startedAt time.Time
	count     int
}

type sourceLimiter struct {
	mu      sync.Mutex
	windows map[string]rateWindow
}

func newSourceLimiter() *sourceLimiter {
	return &sourceLimiter{windows: map[string]rateWindow{}}
}

func (l *sourceLimiter) allow(key string, now time.Time) bool {
	l.mu.Lock()
	defer l.mu.Unlock()
	window := l.windows[key]
	if window.startedAt.IsZero() || now.Sub(window.startedAt) >= time.Minute {
		window = rateWindow{startedAt: now}
	}
	if window.count >= 20 {
		return false
	}
	window.count++
	l.windows[key] = window
	if len(l.windows) > 2048 {
		var oldestKey string
		var oldestAt time.Time
		for existing, candidate := range l.windows {
			if now.Sub(candidate.startedAt) >= time.Minute {
				delete(l.windows, existing)
				continue
			}
			if oldestKey == "" || candidate.startedAt.Before(oldestAt) {
				oldestKey = existing
				oldestAt = candidate.startedAt
			}
		}
		if len(l.windows) > 2048 && oldestKey != "" {
			delete(l.windows, oldestKey)
		}
	}
	return true
}

func sourceAddress(r *http.Request) string {
	host, _, err := net.SplitHostPort(strings.TrimSpace(r.RemoteAddr))
	if err == nil && host != "" {
		return host
	}
	return strings.TrimSpace(r.RemoteAddr)
}
