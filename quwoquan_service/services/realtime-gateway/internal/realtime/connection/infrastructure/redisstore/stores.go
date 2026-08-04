// Package redisstore 实现 Connection runtime_session 的 redis 端口：
// 一次性 ticket、逐连接 lease + fencing 与按用户订阅。
// 键契约唯一真相源：services/realtime-gateway/contracts/realtime/connection/storage.yaml。
package redisstore

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"sync"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/realtime-gateway/internal/realtime/connection/application"
)

const (
	ticketKeyPrefix     = "rt:ticket:"
	ticketUsedKeyPrefix = "rt:ticket:used:"
	accountTicketPrefix = "rt:account:tickets:"
	leaseKeyPrefix      = "rt:conn:lease:"
	fenceKeyPrefix      = "rt:conn:fence:"

	ticketUsedMarkerTTL = 60 * time.Second
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
	if err := s.client.SAdd(
		ctx,
		accountTicketKey(claims.AccountID),
		ticket,
	); err != nil {
		_ = s.client.Del(ctx, ticketKeyPrefix+ticket)
		return "", err
	}
	if err := s.client.Expire(
		ctx,
		accountTicketKey(claims.AccountID),
		ttl,
	); err != nil {
		_ = s.client.SRem(ctx, accountTicketKey(claims.AccountID), ticket)
		_ = s.client.Del(ctx, ticketKeyPrefix+ticket)
		return "", err
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
	if err := s.client.SRem(ctx, accountTicketKey(claims.AccountID), ticket); err != nil {
		return application.TicketClaims{}, err
	}
	return claims, nil
}

func (s *TicketStore) Revoke(
	ctx context.Context,
	accountID string,
	ticket string,
) error {
	accountID = strings.TrimSpace(accountID)
	ticket = strings.TrimSpace(ticket)
	if accountID == "" || ticket == "" {
		return errors.New("realtime ticket revoke requires account and ticket")
	}
	if err := s.client.Del(
		ctx,
		ticketKeyPrefix+ticket,
		ticketUsedKeyPrefix+ticket,
	); err != nil {
		return err
	}
	return s.client.SRem(ctx, accountTicketKey(accountID), ticket)
}

func accountTicketKey(accountID string) string {
	return accountTicketPrefix + strings.TrimSpace(accountID)
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

// EventSource 按可信 identity 订阅明确语义的通道；RTC 只按 persona，
// generic/recommendation 仍按 account，不订阅任何 rtc:user/account alias。
type EventSource struct {
	transport runtimemessaging.MessageTransport
}

func NewEventSource(transport runtimemessaging.MessageTransport) *EventSource {
	if transport == nil {
		panic("realtime event source requires a message transport")
	}
	return &EventSource{transport: transport}
}

func (s *EventSource) SubscribeIdentity(
	ctx context.Context,
	identity application.TrustedIdentity,
) (runtimemessaging.EphemeralSubscription, error) {
	source, err := s.transport.SubscribeEphemeral(
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
	source    runtimemessaging.EphemeralSubscription
	identity  application.TrustedIdentity
	messages  chan runtimemessaging.EphemeralDelivery
	done      chan struct{}
	closeOnce sync.Once
	closeErr  error
}

func newIdentitySubscription(
	ctx context.Context,
	source runtimemessaging.EphemeralSubscription,
	identity application.TrustedIdentity,
) *identitySubscription {
	subscription := &identitySubscription{
		source:   source,
		identity: identity,
		messages: make(chan runtimemessaging.EphemeralDelivery),
		done:     make(chan struct{}),
	}
	go subscription.forward(ctx)
	return subscription
}

func (s *identitySubscription) Channel() <-chan runtimemessaging.EphemeralDelivery {
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
			message, matches := bindRealtimeMessageToIdentity(message, s.identity)
			if !matches {
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

func bindRealtimeMessageToIdentity(
	message runtimemessaging.EphemeralDelivery,
	identity application.TrustedIdentity,
) (runtimemessaging.EphemeralDelivery, bool) {
	if !strings.HasPrefix(message.Channel, "rt:rtc:persona:") {
		return message, true
	}
	target, event, targeted, err :=
		runtimemessaging.UnwrapTargetedEphemeralPayload(message.Payload)
	if err != nil {
		return message, false
	}
	if !targeted {
		// Device/persona routing belongs only to the trusted transport wrapper.
		// A legacy flat RTC frame carrying either field must not cross the client
		// boundary.
		var top map[string]json.RawMessage
		if json.Unmarshal(message.Payload, &top) != nil {
			return message, false
		}
		if top["deviceId"] != nil || top["targetPersonaId"] != nil {
			return message, false
		}
		return message, true
	}
	if personaID := strings.TrimSpace(target.PersonaID); personaID != "" &&
		personaID != strings.TrimSpace(identity.PersonaID) {
		return message, false
	}
	if deviceID := strings.TrimSpace(target.DeviceID); deviceID != "" &&
		deviceID != strings.TrimSpace(identity.DeviceID) {
		return message, false
	}
	message.Payload = event
	return message, true
}
