package application

import (
	"context"
	"errors"
	"log/slog"
	"sort"
	"strings"
	"sync"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
)

const (
	defaultLeaseTTL          = 60 * time.Second
	defaultHeartbeatInterval = 20 * time.Second
	// defaultMaxConnectionsPerPersona 对齐 events.yaml ConnectionReplaced：
	// 超过 per-persona 上限时踢掉最早连接（当前为单节点内语义；跨节点扩容时
	// 需经 redis 通知对端节点，见 readiness 备注）。
	defaultMaxConnectionsPerPersona = 5
)

// ConnectionSink 是 transport 无关的下发端口（WS 连接或 LongPoll 等待者）。
type ConnectionSink interface {
	Deliver(payload string) bool
	Kick(reason string)
}

type activeConnection struct {
	connID      string
	identity    TrustedIdentity
	transport   string
	fence       int64
	sink        ConnectionSink
	connectedAt time.Time
	cancel      context.CancelFunc
}

// Hub 管理本节点的活跃连接：按可信 account/persona/device 订阅 redis 通道并路由推送，
// 维护 lease/fencing 与 presence 投影。
type Hub struct {
	leases        LeaseStore
	presence      PresenceStore
	events        EventSource
	nodeID        string
	maxPerPersona int
	leaseTTL      time.Duration
	logger        *slog.Logger
	mu            sync.Mutex
	connections   map[string]map[string]*activeConnection
}

func NewHub(
	leases LeaseStore,
	presence PresenceStore,
	events EventSource,
	nodeID string,
	logger *slog.Logger,
) (*Hub, error) {
	if leases == nil || presence == nil || events == nil {
		return nil, errors.New("realtime hub requires lease, presence and event ports")
	}
	if strings.TrimSpace(nodeID) == "" {
		return nil, errors.New("realtime hub requires a node id")
	}
	if logger == nil {
		logger = slog.Default()
	}
	return &Hub{
		leases:        leases,
		presence:      presence,
		events:        events,
		nodeID:        nodeID,
		maxPerPersona: defaultMaxConnectionsPerPersona,
		leaseTTL:      defaultLeaseTTL,
		logger:        logger,
		connections:   map[string]map[string]*activeConnection{},
	}, nil
}

// Attach 注册连接：取号 fencing token、写租约与 presence、订阅该身份
// 全部实时通道并把事件透传给 sink。返回用于停止该连接的 detach 函数。
func (h *Hub) Attach(
	ctx context.Context,
	identity TrustedIdentity,
	connID string,
	transport string,
	sink ConnectionSink,
) (func(), error) {
	identity.AccountID = strings.TrimSpace(identity.AccountID)
	identity.PersonaID = strings.TrimSpace(identity.PersonaID)
	identity.DeviceID = strings.TrimSpace(identity.DeviceID)
	connID = strings.TrimSpace(connID)
	if identity.AccountID == "" ||
		identity.PersonaID == "" ||
		identity.DeviceID == "" ||
		connID == "" ||
		sink == nil {
		return nil, errors.New(
			"realtime attach requires account, persona, device, connection id and sink",
		)
	}
	fence, err := h.leases.Acquire(ctx, identity, connID, h.leaseTTL)
	if err != nil {
		return nil, err
	}
	if err := h.presence.Attach(
		ctx,
		identity,
		connID,
		h.nodeID,
		transport,
	); err != nil {
		_ = h.leases.Release(ctx, identity, connID)
		return nil, err
	}
	subscription, err := h.events.SubscribeIdentity(ctx, identity)
	if err != nil {
		_ = h.presence.Detach(ctx, identity, connID)
		_ = h.leases.Release(ctx, identity, connID)
		return nil, err
	}

	connCtx, cancel := context.WithCancel(ctx)
	connection := &activeConnection{
		connID:      connID,
		identity:    identity,
		transport:   transport,
		fence:       fence,
		sink:        sink,
		connectedAt: time.Now().UTC(),
		cancel:      cancel,
	}
	replaced := h.register(connection)
	if replaced != nil {
		replaced.sink.Kick("connection_replaced")
		replaced.cancel()
	}

	detach := func() {
		cancel()
		_ = subscription.Close()
		h.unregister(connection)
		background, cancelCleanup := context.WithTimeout(context.Background(), 3*time.Second)
		defer cancelCleanup()
		_ = h.presence.Detach(background, identity, connID)
		_ = h.leases.Release(background, identity, connID)
	}

	go h.pumpEvents(connCtx, connection, subscription.Channel())
	go h.keepAlive(connCtx, connection)
	return detach, nil
}

func (h *Hub) pumpEvents(
	ctx context.Context,
	connection *activeConnection,
	events <-chan runtimemessaging.EphemeralDelivery,
) {
	for {
		select {
		case <-ctx.Done():
			return
		case message, ok := <-events:
			if !ok {
				connection.sink.Kick("subscription_closed")
				return
			}
			if !connection.sink.Deliver(string(message.Payload)) {
				return
			}
		}
	}
}

func (h *Hub) keepAlive(ctx context.Context, connection *activeConnection) {
	ticker := time.NewTicker(defaultHeartbeatInterval)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			// fencing：新连接取号后旧 token 失效，旧连接不得继续续租/回写。
			currentFence, err := h.leases.CurrentFence(
				ctx,
				connection.identity,
			)
			if err == nil && currentFence > connection.fence && !h.hasNewerLocal(connection) {
				// 更高 fence 属于其他节点的新连接；本连接保持只读推送，
				// 但停止续租共享状态由对端接管（单节点部署下不触发）。
				continue
			}
			if err := h.leases.Renew(
				ctx,
				connection.identity,
				connection.connID,
				h.leaseTTL,
			); err != nil {
				h.logger.Warn("realtime lease renew failed",
					"personaId", connection.identity.PersonaID,
					"deviceId", connection.identity.DeviceID,
					"connId", connection.connID,
					"error", err)
			}
			if err := h.presence.Heartbeat(
				ctx,
				connection.identity,
				connection.connID,
				h.nodeID,
				connection.transport,
			); err != nil {
				h.logger.Warn("realtime presence heartbeat failed",
					"personaId", connection.identity.PersonaID,
					"deviceId", connection.identity.DeviceID,
					"connId", connection.connID,
					"error", err)
			}
		}
	}
}

// register 登记连接并按 per-persona 上限返回需要被替换的最早连接。
func (h *Hub) register(connection *activeConnection) *activeConnection {
	h.mu.Lock()
	defer h.mu.Unlock()
	personaConnections := h.connections[connection.identity.PersonaID]
	if personaConnections == nil {
		personaConnections = map[string]*activeConnection{}
		h.connections[connection.identity.PersonaID] = personaConnections
	}
	personaConnections[connection.connID] = connection
	if len(personaConnections) <= h.maxPerPersona {
		return nil
	}
	ordered := make([]*activeConnection, 0, len(personaConnections))
	for _, existing := range personaConnections {
		ordered = append(ordered, existing)
	}
	sort.Slice(ordered, func(i, j int) bool {
		return ordered[i].connectedAt.Before(ordered[j].connectedAt)
	})
	oldest := ordered[0]
	delete(personaConnections, oldest.connID)
	return oldest
}

func (h *Hub) unregister(connection *activeConnection) {
	h.mu.Lock()
	defer h.mu.Unlock()
	personaConnections := h.connections[connection.identity.PersonaID]
	if personaConnections == nil {
		return
	}
	if current, ok := personaConnections[connection.connID]; ok && current == connection {
		delete(personaConnections, connection.connID)
	}
	if len(personaConnections) == 0 {
		delete(h.connections, connection.identity.PersonaID)
	}
}

func (h *Hub) hasNewerLocal(connection *activeConnection) bool {
	h.mu.Lock()
	defer h.mu.Unlock()
	for _, existing := range h.connections[connection.identity.PersonaID] {
		if existing.identity.DeviceID == connection.identity.DeviceID &&
			existing.fence > connection.fence {
			return true
		}
	}
	return false
}
