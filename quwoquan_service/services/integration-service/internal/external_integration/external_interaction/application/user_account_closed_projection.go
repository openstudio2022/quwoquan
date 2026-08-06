package application

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"sort"
	"strconv"
	"strings"
	"time"
)

const UserAccountClosedEventName = "UserAccountClosed"

var ErrUserAccountClosedEventIDConflict = errors.New(
	"integration UserAccountClosed eventId was reused with different data",
)

type UserAccountClosedEvent struct {
	EventID        string
	AccountVersion int64
	UserID         string
	PersonaIDs     []string
	AccountState   string
	UpdatedAt      time.Time
	OccurredAt     time.Time
}

func (event UserAccountClosedEvent) Validate() error {
	if strings.TrimSpace(event.EventID) == "" ||
		event.AccountVersion <= 0 ||
		strings.TrimSpace(event.UserID) == "" ||
		event.PersonaIDs == nil ||
		strings.TrimSpace(event.AccountState) != "closed" ||
		event.UpdatedAt.IsZero() ||
		event.OccurredAt.IsZero() {
		return errors.New("integration UserAccountClosed event is incomplete")
	}
	return nil
}

func (event UserAccountClosedEvent) SubjectIDs() []string {
	values := append([]string{event.UserID}, event.PersonaIDs...)
	seen := make(map[string]struct{}, len(values))
	result := make([]string, 0, len(values))
	for _, value := range values {
		value = strings.TrimSpace(value)
		if value == "" {
			continue
		}
		if _, exists := seen[value]; exists {
			continue
		}
		seen[value] = struct{}{}
		result = append(result, value)
	}
	sort.Strings(result)
	return result
}

func (event UserAccountClosedEvent) Digest() string {
	sum := sha256.Sum256([]byte(strings.Join([]string{
		strings.TrimSpace(event.UserID),
		strconv.FormatInt(event.AccountVersion, 10),
		strings.Join(event.SubjectIDs(), "\x1f"),
		strings.TrimSpace(event.AccountState),
		event.UpdatedAt.UTC().Format(time.RFC3339Nano),
		event.OccurredAt.UTC().Format(time.RFC3339Nano),
	}, "\x00")))
	return hex.EncodeToString(sum[:])
}

type UserAccountClosedProjectionResult struct {
	Replayed               bool
	DeletedRequests        int64
	DeletedTasks           int64
	DeletedAttempts        int64
	DeletedResultOutboxes  int64
	DeletedRecoveryRecords int64
}

// UserAccountClosedProjectionStore 是 ExternalInteraction lifecycle facet 的
// 持久化端口；实现负责 inbox、隐私清理与结果原子提交。
type UserAccountClosedProjectionStore interface {
	ApplyUserAccountClosed(
		context.Context,
		UserAccountClosedEvent,
	) (UserAccountClosedProjectionResult, error)
}

// UserAccountClosedProjection 是 ExternalInteraction 对 UserAccountClosed 的
// 唯一 application facet。它先校验 typed event，再进入对象自有事务端口。
type UserAccountClosedProjection struct {
	store UserAccountClosedProjectionStore
}

func NewUserAccountClosedProjection(
	store UserAccountClosedProjectionStore,
) (*UserAccountClosedProjection, error) {
	if store == nil {
		return nil, errors.New("integration account closure projection store is required")
	}
	return &UserAccountClosedProjection{store: store}, nil
}

func (projection *UserAccountClosedProjection) ApplyUserAccountClosed(
	ctx context.Context,
	event UserAccountClosedEvent,
) (UserAccountClosedProjectionResult, error) {
	if projection == nil || projection.store == nil {
		return UserAccountClosedProjectionResult{}, errors.New(
			"integration account closure projection is not configured",
		)
	}
	if err := event.Validate(); err != nil {
		return UserAccountClosedProjectionResult{}, err
	}
	return projection.store.ApplyUserAccountClosed(ctx, event)
}

// AttemptSubjectClosure is the only port through which ExternalInteraction
// may ask ExternalInteractionAttemptFact to delete privacy-bound facts.
type AttemptSubjectClosure interface {
	DeleteByPrivacyLocators(
		ctx context.Context,
		subjectDigests []string,
		taskIDs []string,
		requestIDs []string,
	) (int64, error)
}
