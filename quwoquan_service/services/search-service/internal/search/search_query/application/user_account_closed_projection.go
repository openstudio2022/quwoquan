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

	"quwoquan_service/runtime/accountrestriction"
)

const UserAccountClosedEventName = "UserAccountClosed"

var ErrUserAccountClosedEventIDConflict = errors.New(
	"UserAccountClosed eventId was reused with different data",
)

var ErrUserAccountRestrictionProjectionConflict = errors.New(
	"search user account restriction projection conflict",
)

// UserAccountClosedEvent 是 Search 清理私有查询状态所需的 canonical 公共事实。
// Search 不得反向读取 User 数据库补充身份信息。
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
		return errors.New("UserAccountClosed event is incomplete")
	}
	return nil
}

func (event UserAccountClosedEvent) SubjectIDs() []string {
	values := make([]string, 0, len(event.PersonaIDs)+1)
	values = append(values, event.UserID)
	values = append(values, event.PersonaIDs...)
	seen := make(map[string]struct{}, len(values))
	subjects := make([]string, 0, len(values))
	for _, value := range values {
		value = strings.TrimSpace(value)
		if value == "" {
			continue
		}
		if _, exists := seen[value]; exists {
			continue
		}
		seen[value] = struct{}{}
		subjects = append(subjects, value)
	}
	sort.Strings(subjects)
	return subjects
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
	Replayed bool
}

type UserAccountRestrictionProjectionResult struct {
	Replayed bool
	Stale    bool
	Terminal bool
	Affected int64
}

// UserAccountClosedProjection 必须把 inbox 与 Search 私有数据清理放在同一事务中。
type UserAccountClosedProjection interface {
	ApplyUserAccountClosed(
		ctx context.Context,
		event UserAccountClosedEvent,
	) (UserAccountClosedProjectionResult, error)
}

// UserAccountRestrictionProjection owns only the reversible suspended/active
// read model. It must never invoke the irreversible UserAccountClosed cleanup.
type UserAccountRestrictionProjection interface {
	Apply(
		ctx context.Context,
		event accountrestriction.Event,
	) (UserAccountRestrictionProjectionResult, error)
}
