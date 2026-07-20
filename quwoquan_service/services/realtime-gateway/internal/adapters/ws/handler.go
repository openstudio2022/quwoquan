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
	"time"

	"github.com/coder/websocket"
	"github.com/google/uuid"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/services/realtime-gateway/internal/application"
	generated "quwoquan_service/services/realtime-gateway/internal/generated"
)

const (
	writeTimeout   = 5 * time.Second
	readIdleWindow = 90 * time.Second
)

type Handler struct {
	tickets *application.TicketService
	hub     *application.Hub
	logger  *slog.Logger
}

func NewHandler(
	tickets *application.TicketService,
	hub *application.Hub,
	logger *slog.Logger,
) (*Handler, error) {
	if tickets == nil || hub == nil {
		return nil, errors.New("realtime ws handler requires ticket service and hub")
	}
	if logger == nil {
		logger = slog.Default()
	}
	return &Handler{tickets: tickets, hub: hub, logger: logger}, nil
}

func (h *Handler) HandleUpgrade(w http.ResponseWriter, r *http.Request) {
	if !strings.EqualFold(strings.TrimSpace(r.Header.Get("Upgrade")), "websocket") {
		writeError(w, r, generated.AppErrorFromTicketInvalid("websocket upgrade required"))
		return
	}
	claims, err := h.tickets.Consume(r.Context(), r.URL.Query().Get("ticket"))
	if err != nil {
		writeError(w, r, ticketError(err))
		return
	}

	conn, err := websocket.Accept(w, r, nil)
	if err != nil {
		h.logger.Warn("realtime websocket accept failed", "error", err)
		return
	}

	identity := claims.TrustedIdentity
	connID := "ws-" + uuid.NewString()
	// 连接生命周期不绑定 upgrade 请求的 ctx（请求返回即取消），使用独立 ctx。
	connCtx, cancel := context.WithCancel(context.Background())
	sink := newConnectionSink(connCtx, conn, h.logger)

	detach, err := h.hub.Attach(
		connCtx,
		identity,
		connID,
		"websocket",
		sink,
	)
	if err != nil {
		h.logger.Warn(
			"realtime attach failed",
			"personaId",
			identity.PersonaID,
			"deviceId",
			identity.DeviceID,
			"error",
			err,
		)
		_ = conn.Close(websocket.StatusInternalError, "attach failed")
		cancel()
		return
	}

	if !sink.Deliver(`{"type":"auth_ack","authenticated":true}`) {
		detach()
		cancel()
		return
	}

	h.readLoop(connCtx, conn, sink)
	detach()
	cancel()
	_ = conn.Close(websocket.StatusNormalClosure, "bye")
}

func (h *Handler) readLoop(
	ctx context.Context,
	conn *websocket.Conn,
	sink *connectionSink,
) {
	for {
		readCtx, cancelRead := context.WithTimeout(ctx, readIdleWindowFor(ctx))
		_, payload, err := conn.Read(readCtx)
		cancelRead()
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
			if !sink.Deliver(`{"type":"pong"}`) {
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

func readIdleWindowFor(ctx context.Context) time.Duration {
	if deadline, ok := ctx.Deadline(); ok {
		remaining := time.Until(deadline)
		if remaining < readIdleWindow {
			return remaining
		}
	}
	return readIdleWindow
}

// connectionSink 串行化对同一 WS 连接的写入。
type connectionSink struct {
	ctx    context.Context
	conn   *websocket.Conn
	logger *slog.Logger
	mu     sync.Mutex
	closed bool
}

func newConnectionSink(
	ctx context.Context,
	conn *websocket.Conn,
	logger *slog.Logger,
) *connectionSink {
	return &connectionSink{ctx: ctx, conn: conn, logger: logger}
}

func (s *connectionSink) Deliver(payload string) bool {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.closed {
		return false
	}
	writeCtx, cancel := context.WithTimeout(s.ctx, writeTimeout)
	defer cancel()
	if err := s.conn.Write(writeCtx, websocket.MessageText, []byte(payload)); err != nil {
		s.closed = true
		return false
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
	_ = s.conn.Close(websocket.StatusPolicyViolation, reason)
}

func ticketError(err error) error {
	switch {
	case errors.Is(err, application.ErrTicketReplayed):
		return generated.AppErrorFromTicketReplayed("realtime ticket already consumed")
	default:
		return generated.AppErrorFromTicketInvalid("realtime ticket invalid or expired")
	}
}

func writeError(w http.ResponseWriter, r *http.Request, err error) {
	rterr.WriteHTTPError(w, err, rterr.HTTPWriteOptions{
		RequestID: r.Header.Get("X-Request-Id"),
	})
}
