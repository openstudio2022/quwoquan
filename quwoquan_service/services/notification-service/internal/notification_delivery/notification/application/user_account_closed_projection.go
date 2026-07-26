package application

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"sort"
	"strings"
	"time"
)

const UserAccountClosedEventName = "UserAccountClosed"

var ErrUserAccountClosedEventIDConflict = errors.New(
	"UserAccountClosed eventId was reused with different data",
)

// UserAccountClosedEvent 只承载 notification-service 清理所需的事件标识和
// metadata 已声明 payload；本服务不得为该投影反向读取 User 数据库。
type UserAccountClosedEvent struct {
	EventID      string
	UserID       string
	PersonaIDs   []string
	AccountState string
	UpdatedAt    time.Time
}

func (event UserAccountClosedEvent) Validate() error {
	if strings.TrimSpace(event.EventID) == "" ||
		strings.TrimSpace(event.UserID) == "" ||
		event.PersonaIDs == nil ||
		strings.TrimSpace(event.AccountState) != "closed" ||
		event.UpdatedAt.IsZero() {
		return errors.New("UserAccountClosed event is incomplete")
	}
	return nil
}

// SubjectIDs 返回需要从通知投影移除的账号和 persona 标识。
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

// Digest 用于 eventId 复用冲突检测。persona 顺序不影响同一事实的重放。
func (event UserAccountClosedEvent) Digest() string {
	sum := sha256.Sum256([]byte(strings.Join([]string{
		strings.TrimSpace(event.UserID),
		strings.Join(event.SubjectIDs(), "\x1f"),
		strings.TrimSpace(event.AccountState),
		event.UpdatedAt.UTC().Format(time.RFC3339Nano),
	}, "\x00")))
	return hex.EncodeToString(sum[:])
}

type UserAccountClosedProjectionResult struct {
	Replayed bool
}

// UserAccountClosedProjection 必须把 event inbox 与通知数据清理放在同一
// 存储事务中；相同 eventId 的不同 digest 必须失败关闭。
type UserAccountClosedProjection interface {
	ApplyUserAccountClosed(
		ctx context.Context,
		event UserAccountClosedEvent,
	) (UserAccountClosedProjectionResult, error)
}
