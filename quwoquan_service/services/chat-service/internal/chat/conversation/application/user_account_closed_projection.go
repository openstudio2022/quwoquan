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

// UserAccountClosedEvent 是 user-service 在 events.user.account 上发布的
// 注销终态事实。Chat 仅消费该事实，不反向读取 User 聚合。
type UserAccountClosedEvent struct {
	EventID        string
	EventName      string
	AccountID      string
	AccountVersion int64
	UserID         string
	PersonaIDs     []string
	AccountState   string
	UpdatedAt      time.Time
	OccurredAt     time.Time
}

func (event UserAccountClosedEvent) Validate() error {
	if strings.TrimSpace(event.EventID) == "" ||
		event.EventName != UserAccountClosedEventName ||
		strings.TrimSpace(event.AccountID) == "" ||
		event.AccountVersion <= 0 ||
		strings.TrimSpace(event.UserID) == "" ||
		event.PersonaIDs == nil ||
		event.UpdatedAt.IsZero() ||
		event.OccurredAt.IsZero() {
		return errors.New("chat UserAccountClosed event is incomplete")
	}
	if strings.TrimSpace(event.AccountID) != strings.TrimSpace(event.UserID) {
		return errors.New(
			"chat UserAccountClosed accountId does not match payload userId",
		)
	}
	if strings.TrimSpace(event.AccountState) != "closed" {
		return errors.New(
			"chat UserAccountClosed accountState must be closed",
		)
	}
	return nil
}

// SubjectIDs 返回该账号在 Chat 历史数据中可能使用过的全部身份。每个
// persona 后续都会生成独立随机匿名 ID，不能相互重绑。
func (event UserAccountClosedEvent) SubjectIDs() []string {
	values := make([]string, 0, len(event.PersonaIDs)+2)
	values = append(values, event.AccountID, event.UserID)
	values = append(values, event.PersonaIDs...)
	return normalizeUserAccountSubjectIDs(values)
}

// Digest 是 inbox 冲突检测值；只持久化摘要，不在 inbox 继续保存账号身份。
func (event UserAccountClosedEvent) Digest() string {
	personaIDs := normalizeUserAccountSubjectIDs(event.PersonaIDs)
	canonical := strings.Join([]string{
		strings.TrimSpace(event.EventID),
		event.EventName,
		strings.TrimSpace(event.AccountID),
		strconv.FormatInt(event.AccountVersion, 10),
		strings.TrimSpace(event.UserID),
		strings.Join(personaIDs, "\x1f"),
		strings.TrimSpace(event.AccountState),
		event.UpdatedAt.UTC().Format(time.RFC3339Nano),
		event.OccurredAt.UTC().Format(time.RFC3339Nano),
	}, "\x00")
	sum := sha256.Sum256([]byte(canonical))
	return hex.EncodeToString(sum[:])
}

func normalizeUserAccountSubjectIDs(values []string) []string {
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

type UserAccountClosedApplyResult struct {
	Replayed bool
}

// UserAccountClosedProjection 负责删除 Chat 账户态并不可逆匿名化必须保留的
// 会话审计事实。实现必须将 eventId inbox 与 Mongo 变更放在同一事务。
type UserAccountClosedProjection interface {
	ApplyUserAccountClosed(
		ctx context.Context,
		event UserAccountClosedEvent,
	) (UserAccountClosedApplyResult, error)
}
