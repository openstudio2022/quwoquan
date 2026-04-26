package streaming

import (
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"sync"
	"time"

	rerrors "quwoquan_service/runtime/errors"
)

// SSEEvent represents a server-sent event.
type SSEEvent struct {
	ID    string `json:"id,omitempty"`
	Event string `json:"event,omitempty"`
	Data  any    `json:"data"`
}

// SSEClient represents a connected SSE client.
type SSEClient struct {
	ID        string
	UserID    string
	Events    chan SSEEvent
	Done      chan struct{}
	closeOnce sync.Once
}

func newSSEClient(id, userID string, bufSize int) *SSEClient {
	return &SSEClient{
		ID:     id,
		UserID: userID,
		Events: make(chan SSEEvent, bufSize),
		Done:   make(chan struct{}),
	}
}

// Close shuts down the client channel.
func (c *SSEClient) Close() {
	c.closeOnce.Do(func() {
		close(c.Done)
	})
}

// SSEServer manages SSE connections and broadcasts events.
type SSEServer struct {
	mu      sync.RWMutex
	clients map[string]*SSEClient
	logger  *slog.Logger
	bufSize int
}

func NewSSEServer(logger *slog.Logger) *SSEServer {
	return &SSEServer{
		clients: make(map[string]*SSEClient),
		logger:  logger,
		bufSize: 64,
	}
}

// Handler returns an http.HandlerFunc for SSE connections.
func (s *SSEServer) Handler() http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		flusher, ok := w.(http.Flusher)
		if !ok {
			rerrors.WriteHTTPError(
				w,
				rerrors.NewUnavailable(rerrors.ModuleGateway, "当前连接不支持实时流", "streaming not supported"),
				rerrors.HTTPWriteOptionsFromRequest(r),
			)
			return
		}

		userID := r.URL.Query().Get("userId")
		clientID := fmt.Sprintf("%s-%d", userID, time.Now().UnixNano())

		client := newSSEClient(clientID, userID, s.bufSize)
		s.addClient(client)
		defer s.removeClient(clientID)

		w.Header().Set("Content-Type", "text/event-stream")
		w.Header().Set("Cache-Control", "no-cache")
		w.Header().Set("Connection", "keep-alive")
		w.Header().Set("X-Accel-Buffering", "no")
		flusher.Flush()

		s.logger.Info("sse.connected", slog.String("clientId", clientID), slog.String("userId", userID))

		ctx := r.Context()
		for {
			select {
			case <-ctx.Done():
				return
			case <-client.Done:
				return
			case event := <-client.Events:
				if err := writeSSE(w, event); err != nil {
					return
				}
				flusher.Flush()
			}
		}
	}
}

// SendToUser sends an event to all connections for a user.
func (s *SSEServer) SendToUser(userID string, event SSEEvent) int {
	s.mu.RLock()
	defer s.mu.RUnlock()

	sent := 0
	for _, client := range s.clients {
		if client.UserID == userID {
			select {
			case client.Events <- event:
				sent++
			default:
				s.logger.Warn("sse.dropped", slog.String("clientId", client.ID))
			}
		}
	}
	return sent
}

// Broadcast sends an event to all connected clients.
func (s *SSEServer) Broadcast(event SSEEvent) int {
	s.mu.RLock()
	defer s.mu.RUnlock()

	sent := 0
	for _, client := range s.clients {
		select {
		case client.Events <- event:
			sent++
		default:
		}
	}
	return sent
}

// ConnectedCount returns the number of active connections.
func (s *SSEServer) ConnectedCount() int {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return len(s.clients)
}

func (s *SSEServer) addClient(client *SSEClient) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.clients[client.ID] = client
}

func (s *SSEServer) removeClient(clientID string) {
	s.mu.Lock()
	defer s.mu.Unlock()

	if client, ok := s.clients[clientID]; ok {
		client.Close()
		delete(s.clients, clientID)
		s.logger.Info("sse.disconnected", slog.String("clientId", clientID))
	}
}

func writeSSE(w http.ResponseWriter, event SSEEvent) error {
	if event.ID != "" {
		if _, err := fmt.Fprintf(w, "id: %s\n", event.ID); err != nil {
			return err
		}
	}
	if event.Event != "" {
		if _, err := fmt.Fprintf(w, "event: %s\n", event.Event); err != nil {
			return err
		}
	}

	data, err := json.Marshal(event.Data)
	if err != nil {
		return err
	}
	if _, err := fmt.Fprintf(w, "data: %s\n\n", data); err != nil {
		return err
	}
	return nil
}
