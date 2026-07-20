// Package redisstore 实现 Connection runtime_session 的 redis 端口：
// 一次性 ticket、逐连接 lease + fencing、presence 投影与按用户订阅。
// 键契约唯一真相源：contracts/metadata/realtime/connection/storage.yaml。
package redisstore

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"sort"
	"strings"
	"sync"
	"time"

	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"

	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/realtime-gateway/internal/application"
)

var (
	presenceStaleFieldsRemovedTotal = promauto.NewCounter(
		prometheus.CounterOpts{
			Name: "realtime_presence_stale_fields_removed_total",
			Help: "Stale persona-device presence hash fields removed by the named reader.",
		},
	)
	presenceViewDeviceCount = promauto.NewHistogram(
		prometheus.HistogramOpts{
			Name:    "realtime_presence_view_device_count",
			Help:    "Fresh device count returned by PresenceView.",
			Buckets: []float64{0, 1, 2, 3, 5, 8, 16},
		},
	)
)

const (
	ticketKeyPrefix     = "rt:ticket:"
	ticketUsedKeyPrefix = "rt:ticket:used:"
	leaseKeyPrefix      = "rt:conn:lease:"
	fenceKeyPrefix      = "rt:conn:fence:"
	presenceKeyPrefix   = "presence:persona:"

	ticketUsedMarkerTTL = 60 * time.Second
	presenceTTL         = 120 * time.Second
	presenceStaleAfter  = 60 * time.Second
	fenceCounterTTL     = 24 * time.Hour
)

type TicketStore struct {
	client rtredis.Client
}

func NewTicketStore(client rtredis.Client) *TicketStore {
	return &TicketStore{client: client}
}

func (s *TicketStore) Issue(
	ctx context.Context,
	claims application.TicketClaims,
	ttl time.Duration,
) (string, error) {
	payload, err := json.Marshal(claims)
	if err != nil {
		return "", err
	}
	raw := make([]byte, 32)
	if _, err := rand.Read(raw); err != nil {
		return "", err
	}
	ticket := hex.EncodeToString(raw)
	inserted, err := s.client.SetNX(ctx, ticketKeyPrefix+ticket, string(payload), ttl)
	if err != nil {
		return "", err
	}
	if !inserted {
		return "", errors.New("realtime ticket collision")
	}
	return ticket, nil
}

func (s *TicketStore) Consume(
	ctx context.Context,
	ticket string,
) (application.TicketClaims, error) {
	payload, err := s.client.GetDel(ctx, ticketKeyPrefix+ticket)
	if errors.Is(err, rtredis.ErrKeyNotFound) {
		if _, usedErr := s.client.Get(ctx, ticketUsedKeyPrefix+ticket); usedErr == nil {
			return application.TicketClaims{}, application.ErrTicketReplayed
		}
		return application.TicketClaims{}, application.ErrTicketInvalid
	}
	if err != nil {
		return application.TicketClaims{}, err
	}
	if err := s.client.Set(
		ctx,
		ticketUsedKeyPrefix+ticket,
		"1",
		ticketUsedMarkerTTL,
	); err != nil {
		return application.TicketClaims{}, err
	}
	var claims application.TicketClaims
	if err := json.Unmarshal([]byte(payload), &claims); err != nil {
		return application.TicketClaims{}, application.ErrTicketInvalid
	}
	return claims, nil
}

type LeaseStore struct {
	client rtredis.Client
}

func NewLeaseStore(client rtredis.Client) *LeaseStore {
	return &LeaseStore{client: client}
}

func (s *LeaseStore) Acquire(
	ctx context.Context,
	identity application.TrustedIdentity,
	connID string,
	ttl time.Duration,
) (int64, error) {
	fence, err := s.client.Incr(ctx, fenceKey(identity))
	if err != nil {
		return 0, err
	}
	if err := s.client.Expire(ctx, fenceKey(identity), fenceCounterTTL); err != nil {
		return 0, err
	}
	if err := s.client.Set(
		ctx,
		leaseKey(identity, connID),
		fmt.Sprintf("%d", fence),
		ttl,
	); err != nil {
		return 0, err
	}
	return fence, nil
}

func (s *LeaseStore) Renew(
	ctx context.Context,
	identity application.TrustedIdentity,
	connID string,
	ttl time.Duration,
) error {
	return s.client.Expire(ctx, leaseKey(identity, connID), ttl)
}

func (s *LeaseStore) Release(
	ctx context.Context,
	identity application.TrustedIdentity,
	connID string,
) error {
	return s.client.Del(ctx, leaseKey(identity, connID))
}

func (s *LeaseStore) CurrentFence(
	ctx context.Context,
	identity application.TrustedIdentity,
) (int64, error) {
	value, err := s.client.Get(ctx, fenceKey(identity))
	if errors.Is(err, rtredis.ErrKeyNotFound) {
		return 0, nil
	}
	if err != nil {
		return 0, err
	}
	var fence int64
	if _, err := fmt.Sscanf(value, "%d", &fence); err != nil {
		return 0, err
	}
	return fence, nil
}

func leaseKey(identity application.TrustedIdentity, connID string) string {
	return leaseKeyPrefix +
		strings.TrimSpace(identity.PersonaID) + ":" +
		strings.TrimSpace(identity.DeviceID) + ":" +
		strings.TrimSpace(connID)
}

func fenceKey(identity application.TrustedIdentity) string {
	return fenceKeyPrefix +
		strings.TrimSpace(identity.PersonaID) + ":" +
		strings.TrimSpace(identity.DeviceID)
}

type PresenceStore struct {
	client rtredis.Client
}

func NewPresenceStore(client rtredis.Client) *PresenceStore {
	return &PresenceStore{client: client}
}

type presenceEntry struct {
	AccountID       string `json:"accountId"`
	PersonaID       string `json:"personaId"`
	DeviceID        string `json:"deviceId"`
	ConnectionID    string `json:"connId"`
	NodeID          string `json:"nodeId"`
	Transport       string `json:"transport"`
	LastHeartbeatAt string `json:"lastHeartbeatAt"`
}

func (s *PresenceStore) Attach(
	ctx context.Context,
	identity application.TrustedIdentity,
	connID string,
	nodeID string,
	transport string,
) error {
	return s.writeEntry(ctx, identity, connID, nodeID, transport)
}

func (s *PresenceStore) Heartbeat(
	ctx context.Context,
	identity application.TrustedIdentity,
	connID string,
	nodeID string,
	transport string,
) error {
	return s.writeEntry(ctx, identity, connID, nodeID, transport)
}

func (s *PresenceStore) Detach(
	ctx context.Context,
	identity application.TrustedIdentity,
	connID string,
) error {
	key := presenceKeyPrefix + strings.TrimSpace(identity.PersonaID)
	field := strings.TrimSpace(identity.DeviceID)
	current, err := s.client.HGet(ctx, key, field)
	if errors.Is(err, rtredis.ErrKeyNotFound) {
		return nil
	}
	if err != nil {
		return err
	}
	var entry presenceEntry
	if json.Unmarshal([]byte(current), &entry) != nil ||
		entry.ConnectionID != strings.TrimSpace(connID) {
		return nil
	}
	return s.client.HDel(ctx, key, field)
}

func (s *PresenceStore) writeEntry(
	ctx context.Context,
	identity application.TrustedIdentity,
	connID string,
	nodeID string,
	transport string,
) error {
	payload, err := json.Marshal(presenceEntry{
		AccountID:       strings.TrimSpace(identity.AccountID),
		PersonaID:       strings.TrimSpace(identity.PersonaID),
		DeviceID:        strings.TrimSpace(identity.DeviceID),
		ConnectionID:    strings.TrimSpace(connID),
		NodeID:          nodeID,
		Transport:       transport,
		LastHeartbeatAt: time.Now().UTC().Format(time.RFC3339),
	})
	if err != nil {
		return err
	}
	key := presenceKeyPrefix + strings.TrimSpace(identity.PersonaID)
	if err := s.client.HSet(
		ctx,
		key,
		strings.TrimSpace(identity.DeviceID),
		string(payload),
	); err != nil {
		return err
	}
	return s.client.Expire(ctx, key, presenceTTL)
}

func (s *PresenceStore) ReadPresence(
	ctx context.Context,
	personaID string,
	now time.Time,
) (application.PresenceView, error) {
	personaID = strings.TrimSpace(personaID)
	view := application.PresenceView{
		PersonaID: personaID,
		Devices:   []application.PresenceDevice{},
	}
	entries, err := s.client.HGetAll(ctx, presenceKeyPrefix+personaID)
	if err != nil && !errors.Is(err, rtredis.ErrKeyNotFound) {
		return view, err
	}
	now = now.UTC()
	for field, encoded := range entries {
		var entry presenceEntry
		heartbeat, valid := parsePresenceEntry(encoded, personaID, field, &entry)
		if !valid || now.Sub(heartbeat) > presenceStaleAfter {
			if err := s.client.HDel(
				ctx,
				presenceKeyPrefix+personaID,
				field,
			); err != nil {
				return view, err
			}
			presenceStaleFieldsRemovedTotal.Inc()
			continue
		}
		view.Devices = append(view.Devices, application.PresenceDevice{
			AccountID:       entry.AccountID,
			PersonaID:       entry.PersonaID,
			DeviceID:        entry.DeviceID,
			ConnectionID:    entry.ConnectionID,
			NodeID:          entry.NodeID,
			Transport:       entry.Transport,
			LastHeartbeatAt: heartbeat,
		})
	}
	sort.Slice(view.Devices, func(i, j int) bool {
		return view.Devices[i].DeviceID < view.Devices[j].DeviceID
	})
	presenceViewDeviceCount.Observe(float64(len(view.Devices)))
	return view, nil
}

func parsePresenceEntry(
	encoded string,
	personaID string,
	field string,
	entry *presenceEntry,
) (time.Time, bool) {
	if json.Unmarshal([]byte(encoded), entry) != nil ||
		strings.TrimSpace(entry.PersonaID) != personaID ||
		strings.TrimSpace(entry.DeviceID) != strings.TrimSpace(field) ||
		strings.TrimSpace(entry.AccountID) == "" ||
		strings.TrimSpace(entry.ConnectionID) == "" {
		return time.Time{}, false
	}
	heartbeat, err := time.Parse(
		time.RFC3339Nano,
		strings.TrimSpace(entry.LastHeartbeatAt),
	)
	if err != nil {
		return time.Time{}, false
	}
	return heartbeat.UTC(), true
}

// EventSource 按可信 identity 订阅明确语义的通道；RTC 只按 persona，
// generic/recommendation 仍按 account，不订阅任何 rtc:user/account alias。
type EventSource struct {
	client rtredis.Client
}

func NewEventSource(client rtredis.Client) *EventSource {
	return &EventSource{client: client}
}

func (s *EventSource) SubscribeIdentity(
	ctx context.Context,
	identity application.TrustedIdentity,
) (rtredis.Subscription, error) {
	source, err := s.client.Subscribe(
		ctx,
		"rt:user:"+strings.TrimSpace(identity.AccountID),
		"rt:rtc:persona:"+strings.TrimSpace(identity.PersonaID),
		"rt:rec:feed:user:"+strings.TrimSpace(identity.AccountID),
	)
	if err != nil {
		return nil, err
	}
	return newIdentitySubscription(ctx, source, identity), nil
}

type identitySubscription struct {
	source    rtredis.Subscription
	identity  application.TrustedIdentity
	messages  chan rtredis.Message
	done      chan struct{}
	closeOnce sync.Once
	closeErr  error
}

func newIdentitySubscription(
	ctx context.Context,
	source rtredis.Subscription,
	identity application.TrustedIdentity,
) *identitySubscription {
	subscription := &identitySubscription{
		source:   source,
		identity: identity,
		messages: make(chan rtredis.Message),
		done:     make(chan struct{}),
	}
	go subscription.forward(ctx)
	return subscription
}

func (s *identitySubscription) Channel() <-chan rtredis.Message {
	return s.messages
}

func (s *identitySubscription) Close() error {
	s.closeSource()
	return s.closeErr
}

func (s *identitySubscription) closeSource() {
	s.closeOnce.Do(func() {
		close(s.done)
		s.closeErr = s.source.Close()
	})
}

func (s *identitySubscription) forward(ctx context.Context) {
	defer close(s.messages)
	defer s.closeSource()
	for {
		select {
		case <-ctx.Done():
			return
		case <-s.done:
			return
		case message, ok := <-s.source.Channel():
			if !ok {
				return
			}
			if !realtimeMessageMatchesIdentity(message, s.identity) {
				continue
			}
			select {
			case <-ctx.Done():
				return
			case <-s.done:
				return
			case s.messages <- message:
			}
		}
	}
}

func realtimeMessageMatchesIdentity(
	message rtredis.Message,
	identity application.TrustedIdentity,
) bool {
	if !strings.HasPrefix(message.Channel, "rt:rtc:persona:") {
		return true
	}
	var target struct {
		TargetPersonaID string `json:"targetPersonaId"`
		DeviceID        string `json:"deviceId"`
	}
	if json.Unmarshal([]byte(message.Payload), &target) != nil {
		return true
	}
	if personaID := strings.TrimSpace(target.TargetPersonaID); personaID != "" &&
		personaID != strings.TrimSpace(identity.PersonaID) {
		return false
	}
	if deviceID := strings.TrimSpace(target.DeviceID); deviceID != "" &&
		deviceID != strings.TrimSpace(identity.DeviceID) {
		return false
	}
	return true
}
