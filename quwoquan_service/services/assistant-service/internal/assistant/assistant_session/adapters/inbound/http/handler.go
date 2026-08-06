// Package http is the AssistantSession inbound adapter. AssistantRun keeps its
// own adapter under assistant_run/adapters/inbound/http; the two objects are
// only composed together in cmd/api.
package http

import (
	"bytes"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"strconv"
	"strings"

	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	sessionerrors "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/orchestration"
	sessionmodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/model"
)

const sessionRequestBodyMaxSize = 1 << 20

type Handler struct {
	service *orchestration.AssistantService
}

func NewHandler(service *orchestration.AssistantService) *Handler {
	return &Handler{service: service}
}

// RegisterRoutes binds every AssistantSession api_route declared by
// contracts/assistant/assistant_session/operations.yaml plus the service
// process probes owned by this ingress.
func (h *Handler) RegisterRoutes(mux *http.ServeMux) {
	mux.HandleFunc("GET /healthz", h.handleHealthz)
	mux.HandleFunc("GET /livez", h.handleHealthz)
	mux.HandleFunc("GET /startupz", h.handleHealthz)
	mux.HandleFunc("POST /assistant/sessions", h.handleCreateSession)
	mux.HandleFunc("GET /assistant/sessions", h.handleListSessions)
	mux.HandleFunc("GET /assistant/sessions/{sessionId}", h.handleGetSession)
}

func (h *Handler) Routes() http.Handler {
	mux := http.NewServeMux()
	h.RegisterRoutes(mux)
	return mux
}

func (h *Handler) handleHealthz(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok"})
}

// requireSessionUser 供对象公开读写路径使用：身份来自 JWT principal
// 或 auth middleware 白名单化后的可信 identity header，二者皆空时拒绝，
// 不再回退 anonymous（metadata 声明 auth_mode: required + actor persona）。
func requireSessionUser(r *http.Request) (string, error) {
	if claims, ok := rtauth.PrincipalFromContext(r.Context()); ok &&
		strings.TrimSpace(claims.Subject) != "" {
		return strings.TrimSpace(claims.Subject), nil
	}
	if uid := strings.TrimSpace(r.Header.Get("X-Client-User-Id")); uid != "" {
		return uid, nil
	}
	return "", sessionerrors.AppErrorFromSessionUnauthorized(
		"assistant object requires an identified persona",
	)
}

// requireCanonicalCommandIdentity enforces the one stable mutation identity
// declared by assistant command metadata. The body identifies the aggregate
// replay key; the HTTP header lets middleware, traces, and retrying transports
// observe the same key. Accepting either one alone would create two divergent
// idempotency paths.
func requireCanonicalCommandIdentity(
	r *http.Request,
	clientRequestID string,
) (string, error) {
	bodyID := strings.TrimSpace(clientRequestID)
	if bodyID == "" {
		return "", sessionerrors.AppErrorFromSessionInvalidArgument("missing clientRequestId")
	}
	headerID := strings.TrimSpace(r.Header.Get("Idempotency-Key"))
	if headerID == "" {
		return "", sessionerrors.AppErrorFromSessionInvalidArgument("missing Idempotency-Key")
	}
	if headerID != bodyID {
		return "", sessionerrors.AppErrorFromSessionInvalidArgument("clientRequestId does not match Idempotency-Key")
	}
	return bodyID, nil
}

func (h *Handler) handleCreateSession(w http.ResponseWriter, r *http.Request) {
	userID, err := requireSessionUser(r)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	var input sessionmodel.CreateSessionInput
	if err := readJSON(r, &input); err != nil && err != io.EOF {
		writeHTTPError(w, r, sessionerrors.AppErrorFromSessionInvalidArgument("invalid request body: "+err.Error()))
		return
	}
	input.ClientRequestID, err = requireCanonicalCommandIdentity(
		r,
		input.ClientRequestID,
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	session, err := h.service.CreateSession(r.Context(), userID, input)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusCreated, session)
}

func (h *Handler) handleGetSession(w http.ResponseWriter, r *http.Request) {
	userID, err := requireSessionUser(r)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	session, err := h.service.GetSession(r.Context(), userID, r.PathValue("sessionId"))
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, session)
}

func (h *Handler) handleListSessions(w http.ResponseWriter, r *http.Request) {
	userID, err := requireSessionUser(r)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	view, err := h.service.ListSessions(
		r.Context(),
		userID,
		parseLimit(r, 20),
		r.URL.Query().Get("cursor"),
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, view)
}

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

func writeHTTPError(w http.ResponseWriter, r *http.Request, err error) {
	rterr.WriteHTTPError(w, err, rterr.HTTPWriteOptionsFromRequest(r))
}

func parseLimit(r *http.Request, fallback int) int {
	if fallback <= 0 {
		fallback = 20
	}
	raw := strings.TrimSpace(r.URL.Query().Get("limit"))
	if raw == "" {
		return fallback
	}
	limit, err := strconv.Atoi(raw)
	if err != nil || limit <= 0 {
		return fallback
	}
	return limit
}

func readJSON(r *http.Request, v any) error {
	body, err := io.ReadAll(io.LimitReader(r.Body, sessionRequestBodyMaxSize))
	if err != nil {
		return err
	}
	if len(strings.TrimSpace(string(body))) == 0 {
		return io.EOF
	}
	decoder := json.NewDecoder(bytes.NewReader(body))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(v); err != nil {
		return err
	}
	if err := decoder.Decode(&struct{}{}); !errors.Is(err, io.EOF) {
		if err == nil {
			return errors.New("request body must contain exactly one JSON value")
		}
		return err
	}
	return nil
}
