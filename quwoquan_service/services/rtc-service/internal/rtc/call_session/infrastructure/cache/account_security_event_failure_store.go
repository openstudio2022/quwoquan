package cache

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	rtredis "quwoquan_service/runtime/redis"
)

const (
	accountSecurityFailurePrefix = "cache:rtc:account-security:failure:"
	accountSecurityFailureTTL    = 7 * 24 * time.Hour
)

// AccountSecurityEventFailureStore retains only irreversible digests. The
// original durable stream entry stays in its consumer-group PEL after DLQ so
// recovery can replay it without copying account/persona data into Redis.
type AccountSecurityEventFailureStore struct {
	rdb rtredis.Client
}

func NewAccountSecurityEventFailureStore(
	rdb rtredis.Client,
) *AccountSecurityEventFailureStore {
	return &AccountSecurityEventFailureStore{rdb: rdb}
}

type accountSecurityFailureState struct {
	Attempts       int64  `json:"attempts"`
	SourceStream   string `json:"sourceStream"`
	SourceStreamID string `json:"sourceStreamId"`
	EventDigest    string `json:"eventDigest"`
	ErrorClass     string `json:"errorClass"`
	ErrorDigest    string `json:"errorDigest"`
	DeadLetteredAt string `json:"deadLetteredAt,omitempty"`
}

func (store *AccountSecurityEventFailureStore) RecordAccountSecurityFailure(
	ctx context.Context,
	stream string,
	messageID string,
	eventID string,
	errorClass string,
	cause error,
) (int64, error) {
	if store == nil || store.rdb == nil {
		return 0, errors.New("rtc account security failure store unavailable")
	}
	state, found, err := store.read(ctx, stream, messageID)
	if err != nil {
		return 0, err
	}
	if !found {
		state = accountSecurityFailureState{}
	}
	if strings.TrimSpace(state.DeadLetteredAt) != "" {
		return 0, errors.New(
			"rtc account security terminal marker is held for recovery",
		)
	}
	state.Attempts++
	state.SourceStream = strings.TrimSpace(stream)
	state.SourceStreamID = strings.TrimSpace(messageID)
	state.EventDigest = accountSecurityDigest(eventID)
	state.ErrorClass = strings.TrimSpace(errorClass)
	state.ErrorDigest = accountSecurityErrorDigest(cause)
	encoded, err := json.Marshal(state)
	if err != nil {
		return 0, err
	}
	if err := store.rdb.Set(
		ctx,
		accountSecurityFailureKey(stream, messageID),
		string(encoded),
		accountSecurityFailureTTL,
	); err != nil {
		return 0, err
	}
	return state.Attempts, nil
}

func (store *AccountSecurityEventFailureStore) IsAccountSecurityDeadLettered(
	ctx context.Context,
	stream string,
	messageID string,
) (bool, error) {
	state, found, err := store.read(ctx, stream, messageID)
	if err != nil || !found {
		return false, err
	}
	return strings.TrimSpace(state.DeadLetteredAt) != "", nil
}

func (store *AccountSecurityEventFailureStore) MarkAccountSecurityDeadLettered(
	ctx context.Context,
	stream string,
	messageID string,
) error {
	state, found, err := store.read(ctx, stream, messageID)
	if err != nil {
		return err
	}
	if !found ||
		state.SourceStream != strings.TrimSpace(stream) ||
		state.SourceStreamID != strings.TrimSpace(messageID) {
		return errors.New(
			"rtc account security failure state lacks source PEL reference",
		)
	}
	state.DeadLetteredAt = time.Now().UTC().Format(time.RFC3339Nano)
	encoded, err := json.Marshal(state)
	if err != nil {
		return err
	}
	return store.rdb.Set(
		ctx,
		accountSecurityFailureKey(stream, messageID),
		string(encoded),
		// Terminal recovery state owns an unacknowledged source PEL and must
		// survive ordinary bounded-retry retention until explicitly released.
		0,
	)
}

func (store *AccountSecurityEventFailureStore) ClearAccountSecurityFailure(
	ctx context.Context,
	stream string,
	messageID string,
) error {
	if store == nil || store.rdb == nil {
		return errors.New("rtc account security failure store unavailable")
	}
	return store.rdb.Del(ctx, accountSecurityFailureKey(stream, messageID))
}

func (store *AccountSecurityEventFailureStore) read(
	ctx context.Context,
	stream string,
	messageID string,
) (accountSecurityFailureState, bool, error) {
	if store == nil || store.rdb == nil {
		return accountSecurityFailureState{}, false,
			errors.New("rtc account security failure store unavailable")
	}
	encoded, err := store.rdb.Get(ctx, accountSecurityFailureKey(stream, messageID))
	if errors.Is(err, rtredis.ErrKeyNotFound) {
		return accountSecurityFailureState{}, false, nil
	}
	if err != nil {
		return accountSecurityFailureState{}, false, err
	}
	var state accountSecurityFailureState
	if err := json.Unmarshal([]byte(encoded), &state); err != nil {
		return accountSecurityFailureState{}, false,
			fmt.Errorf("invalid rtc account security failure state")
	}
	return state, true, nil
}

func accountSecurityFailureKey(stream string, messageID string) string {
	return accountSecurityFailurePrefix + accountSecurityDigest(
		strings.TrimSpace(stream)+"\x00"+strings.TrimSpace(messageID),
	)
}

func accountSecurityDigest(value string) string {
	sum := sha256.Sum256([]byte(strings.TrimSpace(value)))
	return hex.EncodeToString(sum[:])
}

func accountSecurityErrorDigest(cause error) string {
	if cause == nil {
		return ""
	}
	return accountSecurityDigest(cause.Error())
}
