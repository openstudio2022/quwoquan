// Package http 实现 realtime-gateway 的 HTTP transport：
// ticket 签发、LongPoll 兜底与传输配置查询。路由与错误契约唯一真相源：
// contracts/metadata/realtime/connection/{service,errors}.yaml。
package http

import (
	"context"
	"encoding/json"
	"errors"
	"log/slog"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/google/uuid"

	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	runtimemessaging "quwoquan_service/runtime/messaging"
	"quwoquan_service/services/realtime-gateway/internal/application"
	generated "quwoquan_service/services/realtime-gateway/internal/generated"
)

const (
	longPollDefaultHold = 25 * time.Second
	longPollMaxHold     = 30 * time.Second
	longPollBatchLimit  = 32
	longPollBatchWindow = 150 * time.Millisecond
)

// RealtimeTransportConfig 是 GET /config/realtime 下发的传输参数，
// 键名与 App RealtimeConfig.fromMap 同源。
type RealtimeTransportConfig struct {
	HeartbeatIntervalSec int `json:"heartbeatIntervalSec"`
	AuthAckTimeoutSec    int `json:"authAckTimeoutSec"`
	WsIdleTimeoutSec     int `json:"wsIdleTimeoutSec"`
	LongPollHoldSec      int `json:"longPollHoldSec"`
	MaxReconnectAttempts int `json:"maxReconnectAttempts"`
	ReconnectBaseDelayMs int `json:"reconnectBaseDelayMs"`
	ReconnectMaxDelayMs  int `json:"reconnectMaxDelayMs"`
}

func DefaultTransportConfig() RealtimeTransportConfig {
	return RealtimeTransportConfig{
		HeartbeatIntervalSec: 15,
		AuthAckTimeoutSec:    5,
		WsIdleTimeoutSec:     120,
		LongPollHoldSec:      25,
		MaxReconnectAttempts: 10,
		ReconnectBaseDelayMs: 1000,
		ReconnectMaxDelayMs:  30000,
	}
}

type Handler struct {
	tickets        *application.TicketService
	events         application.EventSource
	presence       application.PresenceStore
	presenceReader application.PresenceViewReader
	config         RealtimeTransportConfig
	nodeID         string
	logger         *slog.Logger
}

func NewHandler(
	tickets *application.TicketService,
	events application.EventSource,
	presence application.PresenceStore,
	presenceReader application.PresenceViewReader,
	config RealtimeTransportConfig,
	nodeID string,
	logger *slog.Logger,
) (*Handler, error) {
	if tickets == nil || events == nil || presence == nil ||
		presenceReader == nil {
		return nil, errors.New("realtime http handler requires ticket, event and presence ports")
	}
	if logger == nil {
		logger = slog.Default()
	}
	return &Handler{
		tickets:        tickets,
		events:         events,
		presence:       presence,
		presenceReader: presenceReader,
		config:         config,
		nodeID:         nodeID,
		logger:         logger,
	}, nil
}

// Routes 注册经 auth middleware + operation guard 的业务路由
// （/realtime/ws 由 ws adapter 单独挂载）。
func (h *Handler) Routes(mux *http.ServeMux) {
	mux.HandleFunc("POST /realtime/tickets", h.handleIssueTicket)
	mux.HandleFunc("GET /realtime/poll", h.handleLongPoll)
	mux.HandleFunc(
		"GET /internal/realtime/personas/{personaId}/presence",
		h.handleGetPersonaPresence,
	)
	mux.HandleFunc("GET /config/realtime", h.handleGetConfig)
}

func (h *Handler) handleIssueTicket(w http.ResponseWriter, r *http.Request) {
	principal, ok := rtauth.PrincipalFromContext(r.Context())
	identity := trustedIdentity(principal)
	if !ok || !validTrustedIdentity(identity) {
		writeError(w, r, generated.AppErrorFromUnauthorized(
			"realtime ticket requires trusted account, persona and device identities",
		))
		return
	}
	issued, err := h.tickets.Issue(
		r.Context(),
		identity,
	)
	if err != nil {
		writeError(w, r, generated.AppErrorFromInternalError(err.Error()))
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"ticket":    issued.Ticket,
		"expiresAt": issued.ExpiresAt.Format(time.RFC3339),
	})
}

func (h *Handler) handleLongPoll(w http.ResponseWriter, r *http.Request) {
	principal, ok := rtauth.PrincipalFromContext(r.Context())
	identity := trustedIdentity(principal)
	if !ok || !validTrustedIdentity(identity) {
		writeError(w, r, generated.AppErrorFromUnauthorized(
			"realtime poll requires trusted account, persona and device identities",
		))
		return
	}
	hold := parseHold(r.URL.Query().Get("timeout"))

	subscription, err := h.events.SubscribeIdentity(r.Context(), identity)
	if err != nil {
		writeError(w, r, generated.AppErrorFromInternalError(err.Error()))
		return
	}
	defer func() { _ = subscription.Close() }()

	connID := "poll-" + uuid.NewString()
	if err := h.presence.Attach(
		r.Context(),
		identity,
		connID,
		h.nodeID,
		"long_poll",
	); err != nil {
		writeError(w, r, generated.AppErrorFromInternalError(err.Error()))
		return
	}
	defer func() {
		detachCtx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
		defer cancel()
		_ = h.presence.Detach(detachCtx, identity, connID)
	}()

	events := collectEvents(r.Context(), subscription.Channel(), hold)
	if len(events) == 0 {
		w.WriteHeader(http.StatusNoContent)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"events": events})
}

func (h *Handler) handleGetPersonaPresence(
	w http.ResponseWriter,
	r *http.Request,
) {
	personaID := strings.TrimSpace(r.PathValue("personaId"))
	if personaID == "" {
		writeError(
			w,
			r,
			generated.AppErrorFromInternalError("personaId is required"),
		)
		return
	}
	view, err := h.presenceReader.ReadPresence(
		r.Context(),
		personaID,
		time.Now().UTC(),
	)
	if err != nil {
		writeError(w, r, generated.AppErrorFromInternalError(err.Error()))
		return
	}
	writeJSON(w, http.StatusOK, view)
}

func (h *Handler) handleGetConfig(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, h.config)
}

// collectEvents 等待首条事件；收到后再聚合一个短窗口内的后续事件，
// 减少 App 端逐条唤醒。
func collectEvents(
	ctx context.Context,
	source <-chan runtimemessaging.EphemeralDelivery,
	hold time.Duration,
) []json.RawMessage {
	events := make([]json.RawMessage, 0, 4)
	holdTimer := time.NewTimer(hold)
	defer holdTimer.Stop()
	for {
		select {
		case <-ctx.Done():
			return events
		case <-holdTimer.C:
			return events
		case message, ok := <-source:
			if !ok {
				return events
			}
			if !json.Valid(message.Payload) {
				continue
			}
			events = append(events, json.RawMessage(message.Payload))
			return append(events, drainEvents(ctx, source)...)
		}
	}
}

func drainEvents(
	ctx context.Context,
	source <-chan runtimemessaging.EphemeralDelivery,
) []json.RawMessage {
	events := make([]json.RawMessage, 0, 4)
	window := time.NewTimer(longPollBatchWindow)
	defer window.Stop()
	for {
		select {
		case <-ctx.Done():
			return events
		case <-window.C:
			return events
		case message, ok := <-source:
			if !ok {
				return events
			}
			if !json.Valid(message.Payload) {
				continue
			}
			events = append(events, json.RawMessage(message.Payload))
			if len(events) >= longPollBatchLimit {
				return events
			}
		}
	}
}

func parseHold(raw string) time.Duration {
	seconds, err := strconv.Atoi(strings.TrimSpace(raw))
	if err != nil || seconds <= 0 {
		return longPollDefaultHold
	}
	hold := time.Duration(seconds) * time.Second
	if hold > longPollMaxHold {
		return longPollMaxHold
	}
	return hold
}

func writeJSON(w http.ResponseWriter, status int, body any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(body)
}

func writeError(w http.ResponseWriter, r *http.Request, err error) {
	rterr.WriteHTTPError(w, err, rterr.HTTPWriteOptions{
		RequestID: r.Header.Get("X-Request-Id"),
	})
}

func trustedIdentity(
	principal rtauth.Principal,
) application.TrustedIdentity {
	return application.TrustedIdentity{
		AccountID: strings.TrimSpace(principal.Actor.AccountID),
		PersonaID: strings.TrimSpace(principal.Actor.PersonaID),
		DeviceID:  strings.TrimSpace(principal.Actor.DeviceActorID),
	}
}

func validTrustedIdentity(identity application.TrustedIdentity) bool {
	return identity.AccountID != "" &&
		identity.PersonaID != "" &&
		identity.DeviceID != ""
}
