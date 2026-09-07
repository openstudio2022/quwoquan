// Package redisstore 实现 Connection runtime_session 的 redis 端口：
// 一次性 ticket、逐连接 lease + fencing 与按用户订阅。
// 键契约唯一真相源：services/realtime-gateway/contracts/realtime/connection/storage.yaml。
package redisstore

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
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
	fenceKey, leaseKey, err := leaseFenceKeys(identity, connID)
	if err != nil {
		return 0, err
	}
	owner, err := leaseOwnerDigest(connID)
	if err != nil {
		return 0, err
	}
	return rtredis.AcquireLeaseFenceAtomic(
		ctx,
		s.client,
		fenceKey,
		leaseKey,
		owner,
		ttl,
	)
}

// ReleasePreFenceLease deletes only the pre-fencing lease shape named by a pre-fence
// account-session record. It is intentionally separate from Release: callers
// must never synthesize a current fencing token for migrated records.
func (s *LeaseStore) ReleasePreFenceLease(
	ctx context.Context,
	identity application.TrustedIdentity,
	connID string,
) error {
	key, err := preFenceLeaseKey(identity, connID)
	if err != nil {
		return err
	}
	return s.client.Del(ctx, key)
}

func (s *LeaseStore) Renew(
	ctx context.Context,
	identity application.TrustedIdentity,
	connID string,
	expectedFence int64,
	ttl time.Duration,
) error {
	fenceKey, leaseKey, err := leaseFenceKeys(identity, connID)
	if err != nil {
		return err
	}
	owner, err := leaseOwnerDigest(connID)
	if err != nil {
		return err
	}
	result, err := rtredis.RenewLeaseFenceAtomic(
		ctx,
		s.client,
		fenceKey,
		leaseKey,
		owner,
		expectedFence,
		ttl,
	)
	return leaseFenceError(result, err)
}

func (s *LeaseStore) Release(
	ctx context.Context,
	identity application.TrustedIdentity,
	connID string,
	expectedFence int64,
) error {
	fenceKey, leaseKey, err := leaseFenceKeys(identity, connID)
	if err != nil {
		return err
	}
	owner, err := leaseOwnerDigest(connID)
	if err != nil {
		return err
	}
	result, err := rtredis.ReleaseLeaseFenceAtomic(
		ctx,
		s.client,
		fenceKey,
		leaseKey,
		owner,
		expectedFence,
	)
	return leaseFenceError(result, err)
}

func leaseFenceError(result rtredis.LeaseFenceResult, err error) error {
	if err != nil {
		return err
	}
	switch result {
	case rtredis.LeaseFenceApplied:
		return nil
	case rtredis.LeaseFenceExpired:
		return application.ErrLeaseExpired
	case rtredis.LeaseFenceRejected:
		return application.ErrLeaseFenced
	default:
		return fmt.Errorf("realtime lease fence returned unknown result %d", result)
	}
}

func preFenceLeaseKey(
	identity application.TrustedIdentity,
	connID string,
) (string, error) {
	personaID := strings.TrimSpace(identity.PersonaID)
	deviceID := strings.TrimSpace(identity.DeviceID)
	connID = strings.TrimSpace(connID)
	if personaID == "" || deviceID == "" || connID == "" {
		return "", errors.New(
			"realtime pre-fence lease requires persona, device and connection identities",
		)
	}
	return leaseKeyPrefix + personaID + ":" + deviceID + ":" + connID, nil
}

func leaseKey(identity application.TrustedIdentity, connID string) string {
	_, key, err := leaseFenceKeys(identity, connID)
	if err != nil {
		return ""
	}
	return key
}

func fenceKey(identity application.TrustedIdentity) string {
	slot, err := leaseIdentitySlot(identity)
	if err != nil {
		return ""
	}
	return fenceKeyPrefix + "{" + slot + "}"
}

func leaseFenceKeys(
	identity application.TrustedIdentity,
	connID string,
) (string, string, error) {
	slot, err := leaseIdentitySlot(identity)
	if err != nil {
		return "", "", err
	}
	connID = strings.TrimSpace(connID)
	if connID == "" {
		return "", "", errors.New("realtime lease requires a connection id")
	}
	connectionDigest := sha256.Sum256([]byte(connID))
	hashTag := "{" + slot + "}"
	return fenceKeyPrefix + hashTag,
		leaseKeyPrefix + hashTag + ":lease:" + hex.EncodeToString(connectionDigest[:]),
		nil
}

func leaseOwnerDigest(connID string) (string, error) {
	connID = strings.TrimSpace(connID)
	if connID == "" {
		return "", errors.New("realtime lease requires a connection id")
	}
	digest := sha256.Sum256([]byte(connID))
	return hex.EncodeToString(digest[:]), nil
}

func leaseIdentitySlot(identity application.TrustedIdentity) (string, error) {
	personaID := strings.TrimSpace(identity.PersonaID)
	deviceID := strings.TrimSpace(identity.DeviceID)
	if personaID == "" || deviceID == "" {
		return "", errors.New("realtime lease requires persona and device identities")
	}
	digest := sha256.New()
	_, _ = digest.Write([]byte(personaID))
	_, _ = digest.Write([]byte{0})
	_, _ = digest.Write([]byte(deviceID))
	return hex.EncodeToString(digest.Sum(nil)), nil
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
		// A pre-envelope flat RTC frame carrying either field must not cross the client
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
