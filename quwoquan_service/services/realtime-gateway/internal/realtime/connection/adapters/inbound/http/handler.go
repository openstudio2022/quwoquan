// Package http 实现 realtime-gateway 的 HTTP transport：
// ticket 签发、LongPoll 兜底与传输配置查询。路由与错误契约唯一真相源：
// services/realtime-gateway/contracts/realtime/connection/{service,errors}.yaml。
package http

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/google/uuid"

	operationsecurity "quwoquan_service/generated/operationsecurity"
	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	runtimemessaging "quwoquan_service/runtime/messaging"
	generated "quwoquan_service/services/realtime-gateway/generated/realtime/connection"
	"quwoquan_service/services/realtime-gateway/internal/realtime/connection/application"
)

const (
	// longPollResponseReserve 是从 operation 预算里留给收集与序列化响应的时间：
	// hold 必须在 reliability.timeout_ms 触发前结束，否则客户端拿到的是被取消的
	// 请求而不是可持久化的 cursor envelope。
	longPollResponseReserve = 5 * time.Second
	longPollBatchLimit      = 32
	longPollBatchWindow     = 150 * time.Millisecond
	longPollOperationID     = "realtime.connection.LongPoll"
)

// longPollHoldCeiling 由 ContractGraph 中 realtime.connection.LongPoll 的
// reliability.timeout_ms 派生。手写第二个 30s 会让 hold 与 operation guard 施加
// 的截止时间同时到期，谁先赢取决于调度。
var longPollHoldCeiling = contractLongPollHoldCeiling()

func contractLongPollHoldCeiling() time.Duration {
	for _, descriptor := range operationsecurity.ForDomain("realtime") {
		if descriptor.CanonicalOperationID != longPollOperationID {
			continue
		}
		budget := time.Duration(descriptor.TimeoutMilliseconds) * time.Millisecond
		hold := budget - longPollResponseReserve
		if hold <= 0 {
			panic(longPollOperationID + " budget cannot hold a poll")
		}
		return hold
	}
	panic(longPollOperationID + " missing from the generated descriptor table")
}

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
		LongPollHoldSec:      int(longPollHoldCeiling.Seconds()),
		MaxReconnectAttempts: 10,
		ReconnectBaseDelayMs: 1000,
		ReconnectMaxDelayMs:  30000,
	}
}

type Handler struct {
	tickets      *application.TicketService
	hub          *application.Hub
	resumeReader application.ResumableEventReader
	config       RealtimeTransportConfig
}

func NewHandler(
	tickets *application.TicketService,
	hub *application.Hub,
	resumeReader application.ResumableEventReader,
	config RealtimeTransportConfig,
) (*Handler, error) {
	if tickets == nil || hub == nil || resumeReader == nil {
		return nil, errors.New("realtime http handler requires ticket, hub and resume reader")
	}
	return &Handler{
		tickets:      tickets,
		hub:          hub,
		resumeReader: resumeReader,
		config:       config,
	}, nil
}

// Routes 注册经 auth middleware + operation guard 的业务路由
// （/realtime/ws 由 ws adapter 单独挂载）。
func (h *Handler) Routes(mux *http.ServeMux) {
	mux.HandleFunc("POST /realtime/tickets", h.handleIssueTicket)
	mux.HandleFunc("GET /realtime/poll", h.handleLongPoll)
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
		principal.AuthEpoch,
	)
	if err != nil {
		writeTicketSecurityError(w, r, err)
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
	rawCursor := strings.TrimSpace(r.URL.Query().Get("cursor"))
	cursor := rawCursor
	if cursor == "" {
		cursor = "0-0"
	} else if !runtimemessaging.IsCanonicalStreamCursor(cursor) {
		writeError(w, r, generated.AppErrorFromInvalidArgument(
			"realtime poll cursor must be a canonical stream coordinate",
		))
		return
	}
	pollCtx, cancel := context.WithCancel(r.Context())
	defer cancel()
	connID := "poll-" + uuid.NewString()
	sink := newLongPollSink(pollCtx, cancel)
	detach, err := h.hub.Attach(
		pollCtx,
		identity,
		principal.AuthEpoch,
		connID,
		"long_poll",
		sink,
	)
	if err != nil {
		writeTicketSecurityError(w, r, err)
		return
	}
	defer detach()

	readResult := make(chan resumableEventReadResult, 1)
	go func() {
		events, readErr := h.resumeReader.ReadAfter(
			pollCtx,
			identity,
			cursor,
			longPollBatchLimit,
			hold,
		)
		readResult <- resumableEventReadResult{events: events, err: readErr}
	}()
	events, nextCursor, readErr := collectLongPollEvents(
		pollCtx,
		sink.Events(),
		readResult,
		cursor,
		hold,
	)
	if sink.Kicked() {
		writeError(w, r, generated.AppErrorFromUnauthorized(
			"realtime account security rejected the session",
		))
		return
	}
	if readErr != nil {
		writeError(w, r, generated.AppErrorFromInternalError(
			"realtime durable cursor read failed",
		))
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"events":           events,
		"nextCursor":       nextCursor,
		"transportResumed": rawCursor != "",
	})
}

type resumableEventReadResult struct {
	events []application.ResumableEvent
	err    error
}

func collectLongPollEvents(
	ctx context.Context,
	ephemeral <-chan runtimemessaging.EphemeralDelivery,
	durable <-chan resumableEventReadResult,
	cursor string,
	hold time.Duration,
) ([]json.RawMessage, string, error) {
	timer := time.NewTimer(hold)
	defer timer.Stop()
	select {
	case <-ctx.Done():
		return nil, cursor, ctx.Err()
	case <-timer.C:
		return []json.RawMessage{}, cursor, nil
	case result := <-durable:
		if result.err != nil {
			return nil, cursor, result.err
		}
		events := make([]json.RawMessage, 0, len(result.events))
		nextCursor := cursor
		for _, event := range result.events {
			if !json.Valid(event.Payload) {
				continue
			}
			events = append(events, json.RawMessage(event.Payload))
			nextCursor = event.Cursor
		}
		return events, nextCursor, nil
	case message, ok := <-ephemeral:
		if !ok {
			return []json.RawMessage{}, cursor, nil
		}
		events := make([]json.RawMessage, 0, 4)
		if json.Valid(message.Payload) {
			events = append(events, json.RawMessage(message.Payload))
		}
		events = append(events, drainEvents(ctx, ephemeral)...)
		return events, cursor, nil
	}
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
		return longPollHoldCeiling
	}
	hold := time.Duration(seconds) * time.Second
	if hold > longPollHoldCeiling {
		return longPollHoldCeiling
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

// WriteReadinessUnavailable keeps the infrastructure readiness probe on the
// same typed error boundary as the object-owned HTTP routes.
func WriteReadinessUnavailable(w http.ResponseWriter, r *http.Request) {
	writeError(
		w,
		r,
		generated.AppErrorFromReadinessUnavailable(
			"realtime readiness dependency unavailable",
		),
	)
}

func writeTicketSecurityError(w http.ResponseWriter, r *http.Request, cause error) {
	if errors.Is(cause, application.ErrAccountSecurityDenied) {
		writeError(w, r, generated.AppErrorFromUnauthorized(
			"realtime account security rejected the credential",
		))
		return
	}
	if errors.Is(cause, application.ErrAccountSecurityUnavailable) {
		writeError(w, r, generated.AppErrorFromAccountSecurityAuthorityUnavailable(
			"realtime account security authority unavailable",
		))
		return
	}
	writeError(w, r, generated.AppErrorFromInternalError(
		"realtime ticket operation failed",
	))
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

// longPollSink makes the fallback transport a first-class Hub connection, so
// UserAccountClosed/UserSuspended can cancel it through the same local and
// cross-node eviction pipeline as WebSocket.
type longPollSink struct {
	ctx    context.Context
	cancel context.CancelFunc
	events chan runtimemessaging.EphemeralDelivery
	mu     sync.RWMutex
	kicked bool
	closed bool
}

func newLongPollSink(
	ctx context.Context,
	cancel context.CancelFunc,
) *longPollSink {
	return &longPollSink{
		ctx:    ctx,
		cancel: cancel,
		events: make(chan runtimemessaging.EphemeralDelivery, longPollBatchLimit),
	}
}

func (sink *longPollSink) Events() <-chan runtimemessaging.EphemeralDelivery {
	return sink.events
}

func (sink *longPollSink) Deliver(payload string) bool {
	sink.mu.RLock()
	closed := sink.closed
	sink.mu.RUnlock()
	if closed {
		return false
	}
	select {
	case <-sink.ctx.Done():
		return false
	case sink.events <- runtimemessaging.EphemeralDelivery{
		Payload: []byte(payload),
	}:
		return true
	}
}

func (sink *longPollSink) Kick(_ string) {
	sink.mu.Lock()
	if sink.closed {
		sink.mu.Unlock()
		return
	}
	sink.closed = true
	sink.kicked = true
	sink.mu.Unlock()
	sink.cancel()
}

func (sink *longPollSink) Kicked() bool {
	sink.mu.RLock()
	defer sink.mu.RUnlock()
	return sink.kicked
}
