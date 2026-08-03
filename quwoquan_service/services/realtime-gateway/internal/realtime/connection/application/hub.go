package application

import (
	"context"
	"errors"
	"log/slog"
	"sort"
	"strings"
	"sync"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	runtimemessaging "quwoquan_service/runtime/messaging"
	connectionmodel "quwoquan_service/services/realtime-gateway/internal/realtime/connection/domain/model"
)

const (
	defaultLeaseTTL          = connectionmodel.SessionTTL
	defaultHeartbeatInterval = 20 * time.Second
	// A disconnected relay never weakens the durable gate or periodic
	// authority check, but must recover promptly so cross-node eviction keeps
	// its low-latency path.
	accountSecurityRelayReconnectDelay = time.Second
	// 超过 per-persona 上限时直接踢掉本节点最早连接。Connection 是运行时会话，
	// 该替换动作没有跨服务领域消费者，因此不发布伪领域事件。
	defaultMaxConnectionsPerPersona = 5
)

// ConnectionSink 是 transport 无关的下发端口（WS 连接或 LongPoll 等待者）。
type ConnectionSink interface {
	Deliver(payload string) bool
	Kick(reason string)
}

type activeConnection struct {
	session   *connectionmodel.Session
	sink      ConnectionSink
	cancel    context.CancelFunc
	onClose   func()
	closeOnce sync.Once
}

func (connection *activeConnection) close() {
	if connection == nil {
		return
	}
	connection.finalize("")
}

func (connection *activeConnection) terminate(reason string) {
	if connection == nil {
		return
	}
	connection.finalize(reason)
}

func (connection *activeConnection) finalize(reason string) {
	if connection == nil {
		return
	}
	connection.closeOnce.Do(func() {
		if strings.TrimSpace(reason) != "" {
			connection.sink.Kick(reason)
		}
		if connection.onClose != nil {
			connection.onClose()
		}
	})
}

// Hub 管理本节点的活跃连接：按可信 account/persona/device 订阅 redis 通道并路由推送，
// 维护 lease/fencing 与 presence 投影。
type Hub struct {
	leases        LeaseStore
	presence      PresenceProjector
	events        EventSource
	authority     rtauth.AccountSecurityAuthority
	security      AccountSecurityGate
	relay         AccountSecurityRelay
	nodeID        string
	maxPerPersona int
	leaseTTL      time.Duration
	logger        *slog.Logger
	mu            sync.Mutex
	connections   map[string]map[string]*activeConnection
	relayMu       sync.Mutex
	relaySub      AccountSecurityRelaySubscription
	relayCtx      context.Context
	relayCancel   context.CancelFunc
}

func NewHub(
	leases LeaseStore,
	presence PresenceProjector,
	events EventSource,
	authority rtauth.AccountSecurityAuthority,
	security AccountSecurityGate,
	relay AccountSecurityRelay,
	nodeID string,
	logger *slog.Logger,
) (*Hub, error) {
	if leases == nil || presence == nil || events == nil ||
		authority == nil || security == nil || relay == nil {
		return nil, errors.New(
			"realtime hub requires lease, presence, event, authority, gate and relay ports",
		)
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
		authority:     authority,
		security:      security,
		relay:         relay,
		nodeID:        nodeID,
		maxPerPersona: defaultMaxConnectionsPerPersona,
		leaseTTL:      defaultLeaseTTL,
		logger:        logger,
		connections:   map[string]map[string]*activeConnection{},
	}, nil
}

// StartAccountSecurityRelay subscribes before this node becomes ready. The
// durable Redis gate remains the admission truth; this relay only shortens
// terminal-event eviction to all in-process sockets.
func (h *Hub) StartAccountSecurityRelay(ctx context.Context) error {
	if h == nil || h.relay == nil {
		return errors.New("realtime account security relay is not configured")
	}
	if ctx == nil {
		ctx = context.Background()
	}
	h.relayMu.Lock()
	defer h.relayMu.Unlock()
	if h.relayCancel != nil {
		return nil
	}
	subscription, err := h.relay.SubscribeAccountSecurity(ctx)
	if err != nil {
		return err
	}
	relayCtx, relayCancel := context.WithCancel(ctx)
	h.relaySub = subscription
	h.relayCtx = relayCtx
	h.relayCancel = relayCancel
	go h.consumeAccountSecurityRelay(relayCtx, subscription)
	return nil
}

func (h *Hub) CloseAccountSecurityRelay() {
	if h == nil {
		return
	}
	h.relayMu.Lock()
	subscription := h.relaySub
	cancel := h.relayCancel
	h.relaySub = nil
	h.relayCtx = nil
	h.relayCancel = nil
	h.relayMu.Unlock()
	if cancel != nil {
		cancel()
	}
	if subscription != nil {
		_ = subscription.Close()
	}
}

// AccountSecurityRelayHealthy reports whether this node currently has the
// low-latency relay subscription required to evict in-process connections on
// a terminal account event. The durable consumer and synchronous authority
// remain fail-closed while a reconnect is in progress, but readiness must not
// claim the complete cross-node eviction path is healthy.
func (h *Hub) AccountSecurityRelayHealthy() error {
	if h == nil {
		return errors.New("realtime account security relay is not configured")
	}
	h.relayMu.Lock()
	defer h.relayMu.Unlock()
	if h.relayCtx == nil || h.relayCtx.Err() != nil {
		return errors.New("realtime account security relay is stopped")
	}
	if h.relaySub == nil {
		return errors.New("realtime account security relay is reconnecting")
	}
	return nil
}

func (h *Hub) consumeAccountSecurityRelay(
	ctx context.Context,
	subscription AccountSecurityRelaySubscription,
) {
	for subscription != nil {
		for event := range subscription.Events() {
			switch event.AccountState {
			case "closed", "suspended":
				h.EvictAccount(event)
			}
		}
		_ = subscription.Close()

		h.relayMu.Lock()
		h.relaySub = nil
		h.relayMu.Unlock()
		if ctx.Err() != nil {
			return
		}
		h.logger.Warn(
			"realtime account security relay subscription closed; reconnecting",
		)

		for {
			next, err := h.relay.SubscribeAccountSecurity(ctx)
			if err == nil {
				h.relayMu.Lock()
				if ctx.Err() != nil {
					h.relayMu.Unlock()
					_ = next.Close()
					return
				}
				h.relaySub = next
				h.relayMu.Unlock()
				subscription = next
				break
			}
			h.logger.Warn(
				"realtime account security relay reconnect failed",
				"errorDigest",
				ErrorDigest(err),
			)
			timer := time.NewTimer(accountSecurityRelayReconnectDelay)
			select {
			case <-ctx.Done():
				if !timer.Stop() {
					<-timer.C
				}
				return
			case <-timer.C:
			}
		}
	}
}

// Attach 注册连接：取号 fencing token、写租约与 presence、订阅该身份
// 全部实时通道并把事件透传给 sink。返回用于停止该连接的 detach 函数。
func (h *Hub) Attach(
	ctx context.Context,
	identity TrustedIdentity,
	authEpoch int64,
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
	if authEpoch <= 0 {
		return nil, ErrAccountSecurityDenied
	}
	if err := VerifyAccountSecurity(
		ctx,
		h.authority,
		identity.AccountID,
		authEpoch,
	); err != nil {
		return nil, err
	}
	if err := h.security.Admit(ctx, identity, authEpoch); err != nil {
		return nil, err
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
		fence,
	); err != nil {
		_ = h.leases.Release(ctx, identity, connID)
		return nil, err
	}
	session, err := connectionmodel.StartSession(
		connID,
		connectionmodel.Identity{
			AccountID: identity.AccountID,
			PersonaID: identity.PersonaID,
			DeviceID:  identity.DeviceID,
		},
		authEpoch,
		transport,
		fence,
		time.Now().UTC(),
	)
	if err != nil {
		_ = h.presence.Detach(ctx, identity, connID, fence)
		_ = h.leases.Release(ctx, identity, connID)
		return nil, err
	}
	subscription, err := h.events.SubscribeIdentity(ctx, identity)
	if err != nil {
		_ = h.presence.Detach(ctx, identity, connID, fence)
		_ = h.leases.Release(ctx, identity, connID)
		return nil, err
	}

	connCtx, cancel := context.WithCancel(ctx)
	connection := &activeConnection{
		session: session,
		sink:    sink,
		cancel:  cancel,
	}
	connection.onClose = func() {
		cancel()
		_ = subscription.Close()
		h.unregister(connection)
		background, cancelCleanup := context.WithTimeout(
			context.Background(),
			3*time.Second,
		)
		defer cancelCleanup()
		_ = h.presence.Detach(background, identity, connID, fence)
		_ = h.leases.Release(background, identity, connID)
		_ = h.security.UnregisterSession(background, identity, connID)
	}
	if err := h.security.RegisterSession(ctx, identity, connID); err != nil {
		connection.close()
		return nil, err
	}
	replaced := h.register(connection)
	if replaced != nil {
		replaced.terminate("connection_replaced")
	}
	// Registering the process-local connection before the second gate check
	// closes the only meaningful terminal-event race: an event between Redis
	// registration and local registration is caught here; an event after this
	// point sees both the Redis index and this node's map/relay listener.
	if err := h.security.Admit(ctx, identity, authEpoch); err != nil {
		connection.terminate("account_security_rejected")
		return nil, err
	}

	go h.pumpEvents(connCtx, connection, subscription.Channel())
	go h.keepAlive(connCtx, connection)
	return connection.close, nil
}

// EvictAccount immediately removes all local transports for an account. The
// shared AccountSecurityGate has already removed Redis lease/presence/ticket
// state before this method is called by the durable consumer or cross-node
// relay.
func (h *Hub) EvictAccount(event AccountSecurityEvent) {
	if h == nil || strings.TrimSpace(event.AccountID) == "" {
		return
	}
	connections := make([]*activeConnection, 0)
	h.mu.Lock()
	for _, personaConnections := range h.connections {
		for _, connection := range personaConnections {
			if connection.session.Identity.AccountID == event.AccountID {
				connections = append(connections, connection)
			}
		}
	}
	h.mu.Unlock()
	for _, connection := range connections {
		connection.terminate("account_security_rejected")
	}
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
				connection.terminate("subscription_closed")
				return
			}
			if !connection.sink.Deliver(string(message.Payload)) {
				connection.terminate("delivery_failed")
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
			// The durable gate provides immediate eviction, while this
			// synchronous recheck protects active sessions if stream delivery
			// is delayed or the authority advances an epoch first.
			if err := VerifyAccountSecurity(
				ctx,
				h.authority,
				connection.session.Identity.AccountID,
				connection.session.AuthEpoch,
			); err != nil {
				connection.terminate("account_security_rejected")
				return
			}
			if err := h.security.Admit(
				ctx,
				connection.trustedIdentity(),
				connection.session.AuthEpoch,
			); err != nil {
				connection.terminate("account_security_rejected")
				return
			}
			// fencing：新连接取号后旧 token 失效，旧连接不得继续续租/回写。
			currentFence, err := h.leases.CurrentFence(
				ctx,
				connection.trustedIdentity(),
			)
			if err == nil && currentFence > connection.session.Fence && !h.hasNewerLocal(connection) {
				// 更高 fence 属于其他节点的新连接；本连接保持只读推送，
				// 但停止续租共享状态由对端接管（单节点部署下不触发）。
				continue
			}
			if err := connection.session.Renew(time.Now().UTC()); err != nil {
				connection.terminate("session_expired")
				return
			}
			if err := h.leases.Renew(
				ctx,
				connection.trustedIdentity(),
				connection.session.ConnectionID,
				h.leaseTTL,
			); err != nil {
				h.logger.Warn("realtime lease renew failed",
					"nodeId", h.nodeID,
					"errorDigest", ErrorDigest(err))
			}
			if err := h.presence.Heartbeat(
				ctx,
				connection.trustedIdentity(),
				connection.session.ConnectionID,
				h.nodeID,
				connection.session.Transport,
				connection.session.Fence,
			); err != nil {
				h.logger.Warn("realtime presence heartbeat failed",
					"nodeId", h.nodeID,
					"errorDigest", ErrorDigest(err))
			}
		}
	}
}

// register 登记连接并按 per-persona 上限返回需要被替换的最早连接。
func (h *Hub) register(connection *activeConnection) *activeConnection {
	h.mu.Lock()
	defer h.mu.Unlock()
	personaConnections := h.connections[connection.session.Identity.PersonaID]
	if personaConnections == nil {
		personaConnections = map[string]*activeConnection{}
		h.connections[connection.session.Identity.PersonaID] = personaConnections
	}
	personaConnections[connection.session.ConnectionID] = connection
	if len(personaConnections) <= h.maxPerPersona {
		return nil
	}
	ordered := make([]*activeConnection, 0, len(personaConnections))
	for _, existing := range personaConnections {
		ordered = append(ordered, existing)
	}
	sort.Slice(ordered, func(i, j int) bool {
		return ordered[i].session.StartedAt.Before(ordered[j].session.StartedAt)
	})
	oldest := ordered[0]
	delete(personaConnections, oldest.session.ConnectionID)
	return oldest
}

func (h *Hub) unregister(connection *activeConnection) {
	h.mu.Lock()
	defer h.mu.Unlock()
	personaConnections := h.connections[connection.session.Identity.PersonaID]
	if personaConnections == nil {
		return
	}
	if current, ok := personaConnections[connection.session.ConnectionID]; ok && current == connection {
		delete(personaConnections, connection.session.ConnectionID)
	}
	if len(personaConnections) == 0 {
		delete(h.connections, connection.session.Identity.PersonaID)
	}
}

func (h *Hub) hasNewerLocal(connection *activeConnection) bool {
	h.mu.Lock()
	defer h.mu.Unlock()
	for _, existing := range h.connections[connection.session.Identity.PersonaID] {
		if existing.session.Identity.DeviceID == connection.session.Identity.DeviceID &&
			existing.session.Fence > connection.session.Fence {
			return true
		}
	}
	return false
}

func (connection *activeConnection) trustedIdentity() TrustedIdentity {
	return TrustedIdentity{
		AccountID: connection.session.Identity.AccountID,
		PersonaID: connection.session.Identity.PersonaID,
		DeviceID:  connection.session.Identity.DeviceID,
	}
}
