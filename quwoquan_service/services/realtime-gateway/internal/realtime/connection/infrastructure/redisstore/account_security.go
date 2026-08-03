package redisstore

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"sync"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/realtime-gateway/internal/realtime/connection/application"
)

const (
	accountSecurityStatePrefix       = "rt:account:security:"
	accountSecuritySessionIndexPref  = "rt:account:sessions:"
	accountSecuritySessionRecordPref = "rt:account:session:"
	accountSecurityEventHistoryPref  = "rt:account:security-events:"
	accountSecurityFailurePrefix     = "rt:account:security-failure:"
	accountSecurityRelayChannel      = "rt:account:security-relay"

	accountSecurityEventHistoryTTL = 30 * 24 * time.Hour
	accountSecurityFailureTTL      = 30 * 24 * time.Hour
)

// AccountSecurityStateStore owns Redis-only admission fences and account
// session indexes. It does not mirror UserAccount data: the synchronous
// UserAccount authority remains the security truth, while this state closes
// the asynchronous event/connection race.
type AccountSecurityStateStore struct {
	client  rtredis.Client
	revoker application.PresenceRevoker
}

var _ application.AccountSecurityGate = (*AccountSecurityStateStore)(nil)

func NewAccountSecurityStateStore(
	client rtredis.Client,
	revoker application.PresenceRevoker,
) *AccountSecurityStateStore {
	if revoker == nil {
		panic("realtime account security store requires presence revoker")
	}
	return &AccountSecurityStateStore{client: client, revoker: revoker}
}

type accountSecurityState struct {
	AccountState string `json:"accountState"`
	AuthEpoch    int64  `json:"authEpoch"`
	UpdatedAt    string `json:"updatedAt"`
}

type accountSecuritySessionRecord struct {
	AccountID    string `json:"accountId"`
	PersonaID    string `json:"personaId"`
	DeviceID     string `json:"deviceId"`
	ConnectionID string `json:"connectionId"`
}

func (s *AccountSecurityStateStore) Admit(
	ctx context.Context,
	identity application.TrustedIdentity,
	authEpoch int64,
) error {
	if s == nil || s.client == nil || strings.TrimSpace(identity.AccountID) == "" ||
		authEpoch <= 0 {
		return application.ErrAccountSecurityUnavailable
	}
	state, found, err := s.readState(ctx, identity.AccountID)
	if err != nil {
		return application.ErrAccountSecurityUnavailable
	}
	if !found {
		return nil
	}
	switch state.AccountState {
	case "closed", "suspended":
		return application.ErrAccountSecurityDenied
	case "active":
		if state.AuthEpoch > 0 && state.AuthEpoch != authEpoch {
			return application.ErrAccountSecurityDenied
		}
		return nil
	default:
		return application.ErrAccountSecurityUnavailable
	}
}

func (s *AccountSecurityStateStore) RegisterSession(
	ctx context.Context,
	identity application.TrustedIdentity,
	connID string,
) error {
	if s == nil || s.client == nil {
		return application.ErrAccountSecurityUnavailable
	}
	// RegisterSession is called after an epoch-specific Admit. It must not
	// invent an epoch, but it still rejects an already terminal state.
	state, found, err := s.readState(ctx, identity.AccountID)
	if err != nil {
		return application.ErrAccountSecurityUnavailable
	}
	if found && (state.AccountState == "closed" || state.AccountState == "suspended") {
		return application.ErrAccountSecurityDenied
	}
	record := accountSecuritySessionRecord{
		AccountID:    strings.TrimSpace(identity.AccountID),
		PersonaID:    strings.TrimSpace(identity.PersonaID),
		DeviceID:     strings.TrimSpace(identity.DeviceID),
		ConnectionID: strings.TrimSpace(connID),
	}
	if record.AccountID == "" || record.PersonaID == "" ||
		record.DeviceID == "" || record.ConnectionID == "" {
		return application.ErrAccountSecurityUnavailable
	}
	payload, err := json.Marshal(record)
	if err != nil {
		return application.ErrAccountSecurityUnavailable
	}
	if err := s.client.Set(
		ctx,
		accountSecuritySessionRecordKey(record.AccountID, record.ConnectionID),
		string(payload),
		0,
	); err != nil {
		return application.ErrAccountSecurityUnavailable
	}
	if err := s.client.SAdd(
		ctx,
		accountSecuritySessionIndexKey(record.AccountID),
		record.ConnectionID,
	); err != nil {
		_ = s.client.Del(
			ctx,
			accountSecuritySessionRecordKey(record.AccountID, record.ConnectionID),
		)
		return application.ErrAccountSecurityUnavailable
	}
	return nil
}

func (s *AccountSecurityStateStore) UnregisterSession(
	ctx context.Context,
	identity application.TrustedIdentity,
	connID string,
) error {
	if s == nil || s.client == nil {
		return application.ErrAccountSecurityUnavailable
	}
	accountID := strings.TrimSpace(identity.AccountID)
	connID = strings.TrimSpace(connID)
	if accountID == "" || connID == "" {
		return application.ErrAccountSecurityUnavailable
	}
	if err := s.client.SRem(
		ctx,
		accountSecuritySessionIndexKey(accountID),
		connID,
	); err != nil {
		return application.ErrAccountSecurityUnavailable
	}
	if err := s.client.Del(
		ctx,
		accountSecuritySessionRecordKey(accountID, connID),
	); err != nil {
		return application.ErrAccountSecurityUnavailable
	}
	return nil
}

func (s *AccountSecurityStateStore) ApplyAccountSecurityEvent(
	ctx context.Context,
	event application.AccountSecurityEvent,
) (application.AccountSecurityApplyResult, error) {
	if s == nil || s.client == nil {
		return application.AccountSecurityApplyResult{},
			application.ErrAccountSecurityUnavailable
	}
	if err := event.Validate(); err != nil {
		return application.AccountSecurityApplyResult{}, err
	}
	evict, err := s.applyState(ctx, event)
	if err != nil {
		return application.AccountSecurityApplyResult{},
			application.ErrAccountSecurityUnavailable
	}
	replayed, err := s.client.SIsMember(
		ctx,
		accountSecurityEventHistoryKey(event.AccountID),
		accountSecurityDigest(event.EventID),
	)
	if err != nil {
		return application.AccountSecurityApplyResult{},
			application.ErrAccountSecurityUnavailable
	}
	if evict {
		if err := s.clearAccountTickets(ctx, event.AccountID); err != nil {
			return application.AccountSecurityApplyResult{},
				application.ErrAccountSecurityUnavailable
		}
		if err := s.clearAccountSessions(ctx, event.AccountID); err != nil {
			return application.AccountSecurityApplyResult{},
				application.ErrAccountSecurityUnavailable
		}
		if err := s.clearResidualPresence(
			ctx,
			event.AccountID,
			event.PersonaIDs,
		); err != nil {
			return application.AccountSecurityApplyResult{},
				application.ErrAccountSecurityUnavailable
		}
	}
	if replayed {
		return application.AccountSecurityApplyResult{
			Replayed: true,
			Evict:    evict,
		}, nil
	}
	if err := s.client.SAdd(
		ctx,
		accountSecurityEventHistoryKey(event.AccountID),
		accountSecurityDigest(event.EventID),
	); err != nil {
		return application.AccountSecurityApplyResult{},
			application.ErrAccountSecurityUnavailable
	}
	if err := s.client.Expire(
		ctx,
		accountSecurityEventHistoryKey(event.AccountID),
		accountSecurityEventHistoryTTL,
	); err != nil {
		return application.AccountSecurityApplyResult{},
			application.ErrAccountSecurityUnavailable
	}
	return application.AccountSecurityApplyResult{Evict: evict}, nil
}

func (s *AccountSecurityStateStore) applyState(
	ctx context.Context,
	event application.AccountSecurityEvent,
) (bool, error) {
	current, found, err := s.readState(ctx, event.AccountID)
	if err != nil {
		return false, err
	}
	next := accountSecurityState{
		AccountState: event.AccountState,
		AuthEpoch:    event.AuthEpoch,
		UpdatedAt:    event.OccurredAt.UTC().Format(time.RFC3339Nano),
	}
	write := !found
	if found {
		switch {
		case current.AccountState == "closed":
			write = false
		case event.AccountState == "closed":
			write = true
		case event.AccountState == "suspended":
			write = event.AuthEpoch > current.AuthEpoch ||
				(event.AuthEpoch == current.AuthEpoch &&
					current.AccountState != "suspended")
		case event.AccountState == "active":
			// A restore must advance the security epoch. It never recreates a
			// closed account or allows a same-epoch suspension to revive old
			// tickets/sockets.
			write = event.AuthEpoch > current.AuthEpoch ||
				(event.AuthEpoch == current.AuthEpoch &&
					current.AccountState == "active")
		}
	}
	if write {
		payload, marshalErr := json.Marshal(next)
		if marshalErr != nil {
			return false, marshalErr
		}
		if err := s.client.Set(
			ctx,
			accountSecurityStateKey(event.AccountID),
			string(payload),
			0,
		); err != nil {
			return false, err
		}
		current = next
	}
	switch event.AccountState {
	case "closed":
		return current.AccountState == "closed", nil
	case "suspended":
		return current.AccountState == "suspended" &&
			current.AuthEpoch == event.AuthEpoch, nil
	default:
		return false, nil
	}
}

func (s *AccountSecurityStateStore) readState(
	ctx context.Context,
	accountID string,
) (accountSecurityState, bool, error) {
	payload, err := s.client.Get(ctx, accountSecurityStateKey(accountID))
	if errors.Is(err, rtredis.ErrKeyNotFound) {
		return accountSecurityState{}, false, nil
	}
	if err != nil {
		return accountSecurityState{}, false, err
	}
	var state accountSecurityState
	if err := json.Unmarshal([]byte(payload), &state); err != nil ||
		(state.AccountState != "active" &&
			state.AccountState != "suspended" &&
			state.AccountState != "closed") {
		return accountSecurityState{}, false,
			errors.New("invalid realtime account security state")
	}
	return state, true, nil
}

func (s *AccountSecurityStateStore) clearAccountTickets(
	ctx context.Context,
	accountID string,
) error {
	tickets, err := s.client.SMembers(ctx, accountTicketKey(accountID))
	if err != nil {
		return err
	}
	for _, ticket := range tickets {
		ticket = strings.TrimSpace(ticket)
		if ticket == "" {
			continue
		}
		if err := s.client.Del(
			ctx,
			ticketKeyPrefix+ticket,
			ticketUsedKeyPrefix+ticket,
		); err != nil {
			return err
		}
	}
	return s.client.Del(ctx, accountTicketKey(accountID))
}

func (s *AccountSecurityStateStore) clearAccountSessions(
	ctx context.Context,
	accountID string,
) error {
	connIDs, err := s.client.SMembers(
		ctx,
		accountSecuritySessionIndexKey(accountID),
	)
	if err != nil {
		return err
	}
	for _, connID := range connIDs {
		connID = strings.TrimSpace(connID)
		if connID == "" {
			continue
		}
		recordKey := accountSecuritySessionRecordKey(accountID, connID)
		payload, getErr := s.client.Get(ctx, recordKey)
		if getErr != nil && !errors.Is(getErr, rtredis.ErrKeyNotFound) {
			return getErr
		}
		if getErr == nil {
			var record accountSecuritySessionRecord
			if json.Unmarshal([]byte(payload), &record) == nil &&
				record.AccountID == strings.TrimSpace(accountID) &&
				record.ConnectionID == connID {
				if err := s.client.Del(
					ctx,
					leaseKey(application.TrustedIdentity{
						PersonaID: record.PersonaID,
						DeviceID:  record.DeviceID,
					}, record.ConnectionID),
				); err != nil {
					return err
				}
				if err := s.revoker.RemoveConnection(
					ctx,
					record.AccountID,
					record.PersonaID,
					record.DeviceID,
					record.ConnectionID,
				); err != nil {
					return err
				}
			}
		}
		if err := s.client.Del(ctx, recordKey); err != nil {
			return err
		}
	}
	return s.client.Del(ctx, accountSecuritySessionIndexKey(accountID))
}

func (s *AccountSecurityStateStore) clearResidualPresence(
	ctx context.Context,
	accountID string,
	personaIDs []string,
) error {
	return s.revoker.RemoveAccount(ctx, accountID, personaIDs)
}

func accountSecurityStateKey(accountID string) string {
	return accountSecurityStatePrefix + strings.TrimSpace(accountID)
}

func accountSecuritySessionIndexKey(accountID string) string {
	return accountSecuritySessionIndexPref + strings.TrimSpace(accountID)
}

func accountSecuritySessionRecordKey(accountID, connID string) string {
	return accountSecuritySessionRecordPref +
		strings.TrimSpace(accountID) + ":" + strings.TrimSpace(connID)
}

func accountSecurityEventHistoryKey(accountID string) string {
	return accountSecurityEventHistoryPref + strings.TrimSpace(accountID)
}

// AccountSecurityRelay is the cluster-local low-latency eviction path. It
// carries a minimal internal event and deliberately writes no logs.
type AccountSecurityRelay struct {
	client rtredis.Client
}

var _ application.AccountSecurityRelay = (*AccountSecurityRelay)(nil)

func NewAccountSecurityRelay(client rtredis.Client) *AccountSecurityRelay {
	return &AccountSecurityRelay{client: client}
}

func (relay *AccountSecurityRelay) PublishAccountSecurity(
	ctx context.Context,
	event application.AccountSecurityEvent,
) error {
	if relay == nil || relay.client == nil {
		return application.ErrAccountSecurityUnavailable
	}
	if err := event.Validate(); err != nil {
		return err
	}
	payload, err := json.Marshal(event)
	if err != nil {
		return application.ErrAccountSecurityUnavailable
	}
	if err := relay.client.Publish(
		ctx,
		accountSecurityRelayChannel,
		string(payload),
	); err != nil {
		return application.ErrAccountSecurityUnavailable
	}
	return nil
}

func (relay *AccountSecurityRelay) SubscribeAccountSecurity(
	ctx context.Context,
) (application.AccountSecurityRelaySubscription, error) {
	if relay == nil || relay.client == nil {
		return nil, application.ErrAccountSecurityUnavailable
	}
	source, err := relay.client.Subscribe(ctx, accountSecurityRelayChannel)
	if err != nil {
		return nil, application.ErrAccountSecurityUnavailable
	}
	return newAccountSecurityRelaySubscription(ctx, source), nil
}

type accountSecurityRelaySubscription struct {
	source    rtredis.Subscription
	events    chan application.AccountSecurityEvent
	done      chan struct{}
	closeOnce sync.Once
	closeErr  error
}

func newAccountSecurityRelaySubscription(
	ctx context.Context,
	source rtredis.Subscription,
) *accountSecurityRelaySubscription {
	subscription := &accountSecurityRelaySubscription{
		source: source,
		events: make(chan application.AccountSecurityEvent),
		done:   make(chan struct{}),
	}
	go subscription.forward(ctx)
	return subscription
}

func (s *accountSecurityRelaySubscription) Events() <-chan application.AccountSecurityEvent {
	return s.events
}

func (s *accountSecurityRelaySubscription) Close() error {
	s.closeSource()
	return s.closeErr
}

func (s *accountSecurityRelaySubscription) closeSource() {
	s.closeOnce.Do(func() {
		close(s.done)
		s.closeErr = s.source.Close()
	})
}

func (s *accountSecurityRelaySubscription) forward(ctx context.Context) {
	defer close(s.events)
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
			var event application.AccountSecurityEvent
			if json.Unmarshal([]byte(message.Payload), &event) != nil ||
				event.Validate() != nil {
				continue
			}
			select {
			case <-ctx.Done():
				return
			case <-s.done:
				return
			case s.events <- event:
			}
		}
	}
}

// AccountSecurityEventFailureStore retains only irreversible digests. The
// source PEL remains unacknowledged after DLQ so recovery replays its original
// payload without putting account/persona data in a dead-letter record.
type AccountSecurityEventFailureStore struct {
	client rtredis.Client
}

func NewAccountSecurityEventFailureStore(
	client rtredis.Client,
) *AccountSecurityEventFailureStore {
	return &AccountSecurityEventFailureStore{client: client}
}

type accountSecurityFailure struct {
	Attempts       int64  `json:"attempts"`
	SourceStream   string `json:"sourceStream"`
	SourceStreamID string `json:"sourceStreamId"`
	EventDigest    string `json:"eventDigest"`
	ErrorClass     string `json:"errorClass"`
	ErrorDigest    string `json:"errorDigest"`
	DeadLetteredAt string `json:"deadLetteredAt,omitempty"`
}

func (s *AccountSecurityEventFailureStore) RecordAccountSecurityFailure(
	ctx context.Context,
	stream, messageID, eventID, errorClass string,
	cause error,
) (int64, error) {
	if s == nil || s.client == nil {
		return 0, application.ErrAccountSecurityUnavailable
	}
	key := accountSecurityFailureKey(stream, messageID)
	state := accountSecurityFailure{}
	if encoded, err := s.client.Get(ctx, key); err == nil {
		if json.Unmarshal([]byte(encoded), &state) != nil {
			state = accountSecurityFailure{}
		}
	} else if !errors.Is(err, rtredis.ErrKeyNotFound) {
		return 0, err
	}
	if strings.TrimSpace(state.DeadLetteredAt) != "" {
		return 0, errors.New(
			"realtime account security terminal marker is held for recovery",
		)
	}
	state.Attempts++
	state.SourceStream = strings.TrimSpace(stream)
	state.SourceStreamID = strings.TrimSpace(messageID)
	state.EventDigest = accountSecurityDigest(eventID)
	state.ErrorClass = strings.TrimSpace(errorClass)
	state.ErrorDigest = accountSecurityDigest(errorText(cause))
	encoded, err := json.Marshal(state)
	if err != nil {
		return 0, err
	}
	if err := s.client.Set(ctx, key, string(encoded), accountSecurityFailureTTL); err != nil {
		return 0, err
	}
	return state.Attempts, nil
}

func (s *AccountSecurityEventFailureStore) IsAccountSecurityDeadLettered(
	ctx context.Context,
	stream, messageID string,
) (bool, error) {
	state, found, err := s.readFailure(ctx, stream, messageID)
	if err != nil || !found {
		return false, err
	}
	return strings.TrimSpace(state.DeadLetteredAt) != "", nil
}

func (s *AccountSecurityEventFailureStore) MarkAccountSecurityDeadLettered(
	ctx context.Context,
	stream, messageID string,
) error {
	state, found, err := s.readFailure(ctx, stream, messageID)
	if err != nil {
		return err
	}
	if !found ||
		state.SourceStream != strings.TrimSpace(stream) ||
		state.SourceStreamID != strings.TrimSpace(messageID) {
		return errors.New(
			"realtime account security failure state lacks source PEL reference",
		)
	}
	state.DeadLetteredAt = time.Now().UTC().Format(time.RFC3339Nano)
	encoded, err := json.Marshal(state)
	if err != nil {
		return err
	}
	return s.client.Set(
		ctx,
		accountSecurityFailureKey(stream, messageID),
		string(encoded),
		// A terminal marker protects the unacknowledged source PEL. It may
		// only be removed through explicit recovery, never normal retry TTL.
		0,
	)
}

func (s *AccountSecurityEventFailureStore) ClearAccountSecurityFailure(
	ctx context.Context,
	stream, messageID string,
) error {
	if s == nil || s.client == nil {
		return application.ErrAccountSecurityUnavailable
	}
	return s.client.Del(ctx, accountSecurityFailureKey(stream, messageID))
}

func (s *AccountSecurityEventFailureStore) readFailure(
	ctx context.Context,
	stream, messageID string,
) (accountSecurityFailure, bool, error) {
	if s == nil || s.client == nil {
		return accountSecurityFailure{}, false,
			application.ErrAccountSecurityUnavailable
	}
	encoded, err := s.client.Get(ctx, accountSecurityFailureKey(stream, messageID))
	if errors.Is(err, rtredis.ErrKeyNotFound) {
		return accountSecurityFailure{}, false, nil
	}
	if err != nil {
		return accountSecurityFailure{}, false, err
	}
	var state accountSecurityFailure
	if json.Unmarshal([]byte(encoded), &state) != nil {
		return accountSecurityFailure{}, false,
			fmt.Errorf("invalid realtime account security failure state")
	}
	return state, true, nil
}

func accountSecurityFailureKey(stream, messageID string) string {
	return accountSecurityFailurePrefix +
		accountSecurityDigest(strings.TrimSpace(stream)+"\x00"+strings.TrimSpace(messageID))
}

func accountSecurityDigest(value string) string {
	sum := sha256.Sum256([]byte(strings.TrimSpace(value)))
	return hex.EncodeToString(sum[:])
}

func errorText(err error) string {
	if err == nil {
		return ""
	}
	return err.Error()
}
