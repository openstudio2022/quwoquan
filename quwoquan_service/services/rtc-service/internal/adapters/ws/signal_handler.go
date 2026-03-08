package ws

import (
	"context"
	"encoding/json"
	"log/slog"
	"net/http"
	"sync"
	"time"

	"github.com/coder/websocket"
	"quwoquan_service/services/rtc-service/internal/infrastructure/cache"
)

type SignalHandler struct {
	cache       *cache.CallStateCache
	mu          sync.RWMutex
	connections map[string]*userConn
	logger      *slog.Logger
}

type userConn struct {
	conn   *websocket.Conn
	userID string
	cancel context.CancelFunc
}

func NewSignalHandler(c *cache.CallStateCache, logger *slog.Logger) *SignalHandler {
	return &SignalHandler{
		cache:       c,
		connections: make(map[string]*userConn),
		logger:      logger,
	}
}

func (h *SignalHandler) HandleSignal(w http.ResponseWriter, r *http.Request) {
	userID := r.URL.Query().Get("userId")
	if userID == "" {
		userID = r.Header.Get("X-Client-User-Id")
	}
	if userID == "" {
		http.Error(w, "userId required", http.StatusBadRequest)
		return
	}

	conn, err := websocket.Accept(w, r, &websocket.AcceptOptions{
		InsecureSkipVerify: true,
	})
	if err != nil {
		h.logger.Error("ws accept failed", "error", err)
		return
	}

	ctx, cancel := context.WithCancel(r.Context())

	uc := &userConn{conn: conn, userID: userID, cancel: cancel}
	h.registerConn(userID, uc)
	defer h.unregisterConn(userID)

	go h.writePump(ctx, uc)
	h.readPump(ctx, uc)
}

func (h *SignalHandler) readPump(ctx context.Context, uc *userConn) {
	defer uc.cancel()

	for {
		_, data, err := uc.conn.Read(ctx)
		if err != nil {
			return
		}

		var msg map[string]any
		if err := json.Unmarshal(data, &msg); err != nil {
			continue
		}

		msgType, _ := msg["type"].(string)
		switch msgType {
		case "ping":
			_ = writeJSON(ctx, uc.conn, map[string]any{"type": "pong"})
		case "auth":
			_ = writeJSON(ctx, uc.conn, map[string]any{"type": "auth_ok"})
		}
	}
}

func (h *SignalHandler) writePump(ctx context.Context, uc *userConn) {
	ticker := time.NewTicker(30 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			if err := uc.conn.Ping(ctx); err != nil {
				return
			}
		}
	}
}

func (h *SignalHandler) PushToUser(ctx context.Context, userID string, event map[string]any) {
	h.mu.RLock()
	uc, ok := h.connections[userID]
	h.mu.RUnlock()
	if !ok {
		return
	}
	_ = writeJSON(ctx, uc.conn, event)
}

func (h *SignalHandler) PushToUsers(ctx context.Context, userIDs []string, event map[string]any) {
	for _, uid := range userIDs {
		h.PushToUser(ctx, uid, event)
	}
}

func (h *SignalHandler) registerConn(userID string, uc *userConn) {
	h.mu.Lock()
	defer h.mu.Unlock()
	if old, ok := h.connections[userID]; ok {
		old.cancel()
	}
	h.connections[userID] = uc
	h.logger.Info("ws connected", "userId", userID)
}

func (h *SignalHandler) unregisterConn(userID string) {
	h.mu.Lock()
	defer h.mu.Unlock()
	if uc, ok := h.connections[userID]; ok {
		_ = uc.conn.Close(websocket.StatusNormalClosure, "bye")
		delete(h.connections, userID)
		h.logger.Info("ws disconnected", "userId", userID)
	}
}

func writeJSON(ctx context.Context, conn *websocket.Conn, v any) error {
	data, err := json.Marshal(v)
	if err != nil {
		return err
	}
	return conn.Write(ctx, websocket.MessageText, data)
}
