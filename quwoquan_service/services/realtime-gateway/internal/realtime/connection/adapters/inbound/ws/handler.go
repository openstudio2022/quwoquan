// Package ws 实现 /realtime/ws 的 WebSocket 升级：query 只携带一次性
// ticket，服务端消费 ticket 派生可信身份后下发 auth_ack 帧，再经 Hub
// 订阅该用户全部实时通道。协议帧与 App WebSocketTransport 同源：
// 入站 ping/subscribe/unsubscribe（订阅由身份派生，subscribe 帧仅确认
// 不改变服务端路由），出站 auth_ack/pong/业务事件透传。
package ws

import (
	"context"
	"encoding/json"
	"errors"
	"log/slog"
	"net/http"
	"strings"
	"sync"

	"github.com/coder/websocket"
	"github.com/google/uuid"

	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/runtime/operation"
	"quwoquan_service/runtime/streaming"
	generated "quwoquan_service/services/realtime-gateway/generated/realtime/connection"
	"quwoquan_service/services/realtime-gateway/internal/realtime/connection/application"
)

const webSocketUpgradeOperationID = "realtime.connection.WebSocketUpgrade"

type Handler struct {
	tickets              *application.TicketService
	hub                  *application.Hub
	logger               *slog.Logger
	operationDescriptors []rtauth.OperationSecurityDescriptor
	streamBudget         rtauth.OperationStreamBudget
}

func NewHandler(
	tickets *application.TicketService,
	hub *application.Hub,
	logger *slog.Logger,
	operationDescriptors []rtauth.OperationSecurityDescriptor,
) (*Handler, error) {
	if tickets == nil || hub == nil {
		return nil, errors.New("realtime ws handler requires ticket service and hub")
	}
	streamBudget, err := webSocketStreamBudget(operationDescriptors)
	if err != nil {
		return nil, err
	}
	if logger == nil {
		logger = slog.Default()
	}
	return &Handler{
		tickets:              tickets,
		hub:                  hub,
		logger:               logger,
		operationDescriptors: append([]rtauth.OperationSecurityDescriptor(nil), operationDescriptors...),
		streamBudget:         streamBudget,
	}, nil
}

func (h *Handler) HandleUpgrade(w http.ResponseWriter, r *http.Request) {
	if !strings.EqualFold(strings.TrimSpace(r.Header.Get("Upgrade")), "websocket") {
		writeError(w, r, generated.AppErrorFromTicketInvalid("websocket upgrade required"))
		return
	}
	// The handshake clock starts before the one-shot ticket is consumed. A
	// stalled identity dependency therefore cannot outlive the operation's
	// generated admission budget or fall back to a transport timeout.
	budgetGuard := streaming.NewBudgetGuard(r.Context(), h.streamBudget)
	defer budgetGuard.Stop()
	claims, err := h.tickets.Consume(
		budgetGuard.Context(),
		r.URL.Query().Get("ticket"),
	)
	if err != nil {
		if budgetGuard.Limit() == streaming.BudgetLimitHandshake {
			writeError(w, r, generated.AppErrorFromInternalError(
				"realtime websocket admission exceeded its declared handshake budget",
			))
			return
		}
		writeError(w, r, ticketError(err))
		return
	}

	identity := claims.TrustedIdentity
	principal := rtauth.Principal{
		Claims: rtauth.Claims{
			Subject:       identity.AccountID,
			Persona:       identity.PersonaID,
			DeviceActorID: identity.DeviceID,
			AuthEpoch:     claims.AuthEpoch,
		},
		Actor: operation.ActorContext{
			AccountID:     identity.AccountID,
			PersonaID:     identity.PersonaID,
			DeviceActorID: identity.DeviceID,
		},
	}
	authorizedRequest := r.WithContext(rtauth.WithPrincipal(
		budgetGuard.Context(),
		principal,
	))
	rtauth.EnforceRuntimeOperationContract(h.operationDescriptors)(
		http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
			h.handleAuthorizedUpgrade(writer, request, claims, budgetGuard)
		}),
	).ServeHTTP(w, authorizedRequest)
}

func (h *Handler) handleAuthorizedUpgrade(
	w http.ResponseWriter,
	r *http.Request,
	claims application.TicketClaims,
	budgetGuard *streaming.BudgetGuard,
) {
	// A server-level write deadline would preempt the generated max-duration
	// budget after hijack. Clearing it here is safe because every read and write
	// below uses the BudgetGuard context.
	if err := streaming.ReleaseTransportWriteDeadline(w); err != nil {
		h.logger.Debug(
			"realtime websocket transport has no write deadline to release",
			"errorDigest",
			application.ErrorDigest(err),
		)
	}

	conn, err := websocket.Accept(w, r, nil)
	if err != nil {
		h.logger.Warn(
			"realtime websocket accept failed",
			"errorDigest",
			application.ErrorDigest(err),
		)
		return
	}

	identity := claims.TrustedIdentity
	connID := "ws-" + uuid.NewString()
	connCtx := r.Context()
	sink := newConnectionSink(connCtx, conn, h.logger, budgetGuard)

	detach, err := h.hub.Attach(
		connCtx,
		identity,
		claims.AuthEpoch,
		connID,
		"websocket",
		sink,
	)
	if err != nil {
		h.logger.Warn(
			"realtime attach failed",
			"errorDigest",
			application.ErrorDigest(err),
		)
		status := websocket.StatusPolicyViolation
		reason := "account security rejected"
		if errors.Is(err, application.ErrAccountSecurityUnavailable) {
			status = websocket.StatusTryAgainLater
			reason = "account security unavailable"
		}
		_ = conn.Close(status, reason)
		return
	}
	defer detach()

	if !sink.CompleteHandshake(`{"type":"auth_ack","authenticated":true}`) {
		return
	}

	h.readLoop(connCtx, conn, sink)
	status, reason := boundedCloseStatus(budgetGuard.Limit())
	_ = conn.Close(status, reason)
}

func (h *Handler) readLoop(
	ctx context.Context,
	conn *websocket.Conn,
	sink *connectionSink,
) {
	for {
		_, payload, err := conn.Read(ctx)
		if err != nil {
			return
		}
		var frame struct {
			Type string `json:"type"`
		}
		if err := json.Unmarshal(payload, &frame); err != nil {
			continue
		}
		switch frame.Type {
		case "ping":
			if !sink.DeliverKeepAlive(`{"type":"pong"}`) {
				return
			}
		case "subscribe", "unsubscribe":
			// 订阅由可信身份在服务端派生
			//（rt:user:{account}/rt:rtc:persona:{persona}/rt:rec:feed:user:{account}），
			// 客户端 topic 声明不改变路由，仅保持协议兼容。
		default:
		}
	}
}

// connectionSink 串行化对同一 WS 连接的写入。
type connectionSink struct {
	ctx         context.Context
	conn        *websocket.Conn
	logger      *slog.Logger
	budgetGuard *streaming.BudgetGuard
	ready       chan struct{}
	readyOnce   sync.Once
	mu          sync.Mutex
	closed      bool
}

func newConnectionSink(
	ctx context.Context,
	conn *websocket.Conn,
	logger *slog.Logger,
	budgetGuard *streaming.BudgetGuard,
) *connectionSink {
	return &connectionSink{
		ctx:         ctx,
		conn:        conn,
		logger:      logger,
		budgetGuard: budgetGuard,
		ready:       make(chan struct{}),
	}
}

func (s *connectionSink) Deliver(payload string) bool {
	select {
	case <-s.ready:
	case <-s.ctx.Done():
		return false
	}
	return s.write(payload, true)
}

func (s *connectionSink) CompleteHandshake(payload string) bool {
	if !s.write(payload, false) {
		return false
	}
	s.budgetGuard.HandshakeCompleted()
	s.readyOnce.Do(func() { close(s.ready) })
	return true
}

func (s *connectionSink) DeliverKeepAlive(payload string) bool {
	return s.write(payload, false)
}

func (s *connectionSink) write(payload string, businessProgress bool) bool {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.closed {
		return false
	}
	if err := s.conn.Write(s.ctx, websocket.MessageText, []byte(payload)); err != nil {
		s.closed = true
		return false
	}
	if businessProgress {
		s.budgetGuard.FrameEmitted()
	}
	return true
}

func (s *connectionSink) Kick(reason string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.closed {
		return
	}
	s.closed = true
	s.readyOnce.Do(func() { close(s.ready) })
	_ = s.conn.Close(websocket.StatusPolicyViolation, reason)
}

func webSocketStreamBudget(
	descriptors []rtauth.OperationSecurityDescriptor,
) (rtauth.OperationStreamBudget, error) {
	for _, descriptor := range descriptors {
		if descriptor.CanonicalOperationID != webSocketUpgradeOperationID {
			continue
		}
		if descriptor.Method != http.MethodGet ||
			descriptor.PathTemplate != "/realtime/ws" ||
			descriptor.StreamBudget == nil {
			return rtauth.OperationStreamBudget{}, errors.New(
				"realtime WebSocketUpgrade descriptor is missing its canonical route or stream budget",
			)
		}
		budget := *descriptor.StreamBudget
		if budget.HandshakeMilliseconds <= 0 ||
			budget.IdleMilliseconds <= 0 ||
			budget.MaxDurationMilliseconds <= 0 ||
			budget.HandshakeMilliseconds >= budget.MaxDurationMilliseconds ||
			budget.IdleMilliseconds >= budget.MaxDurationMilliseconds {
			return rtauth.OperationStreamBudget{}, errors.New(
				"realtime WebSocketUpgrade descriptor has an invalid stream budget",
			)
		}
		return budget, nil
	}
	return rtauth.OperationStreamBudget{}, errors.New(
		"realtime WebSocketUpgrade descriptor is missing",
	)
}

func boundedCloseStatus(limit streaming.BudgetLimit) (websocket.StatusCode, string) {
	if limit == streaming.BudgetLimitNone {
		return websocket.StatusNormalClosure, "bye"
	}
	return websocket.StatusGoingAway, "stream budget reached"
}

func ticketError(err error) error {
	switch {
	case errors.Is(err, application.ErrTicketReplayed):
		return generated.AppErrorFromTicketReplayed("realtime ticket already consumed")
	case errors.Is(err, application.ErrAccountSecurityUnavailable):
		return generated.AppErrorFromAccountSecurityAuthorityUnavailable(
			"realtime account security authority unavailable",
		)
	case errors.Is(err, application.ErrAccountSecurityDenied):
		return generated.AppErrorFromTicketInvalid(
			"realtime account security rejected the ticket",
		)
	default:
		return generated.AppErrorFromTicketInvalid("realtime ticket invalid or expired")
	}
}

func writeError(w http.ResponseWriter, r *http.Request, err error) {
	rterr.WriteHTTPError(w, err, rterr.HTTPWriteOptions{
		RequestID: r.Header.Get("X-Request-Id"),
	})
}
