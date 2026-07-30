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

var (
	ErrInvalidUserAccountClosedEvent  = errors.New("invalid UserAccountClosed event")
	ErrUserAccountClosedEventConflict = errors.New("UserAccountClosed eventId conflict")
)

// UserAccountClosedEvent 是 metadata 所有的 events.user.account /
// UserAccountClosed 唯一事件契约在 Circle application 边界的强类型投影输入，
// 不是第二套 wire schema。
type UserAccountClosedEvent struct {
	EventID        string
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
		strings.TrimSpace(event.AccountID) == "" ||
		strings.TrimSpace(event.UserID) != strings.TrimSpace(event.AccountID) ||
		event.AccountVersion <= 0 ||
		event.PersonaIDs == nil ||
		event.AccountState != "closed" ||
		event.UpdatedAt.IsZero() ||
		event.OccurredAt.IsZero() {
		return ErrInvalidUserAccountClosedEvent
	}
	return nil
}

func (event UserAccountClosedEvent) SubjectIDs() []string {
	seen := make(map[string]struct{}, len(event.PersonaIDs)+2)
	subjects := make([]string, 0, len(event.PersonaIDs)+2)
	for _, value := range append(
		[]string{event.AccountID, event.UserID},
		event.PersonaIDs...,
	) {
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

// Digest 用 canonical 排序后的字段检测 eventId 被不同事件内容复用。
func (event UserAccountClosedEvent) Digest() string {
	personaIDs := append([]string(nil), event.PersonaIDs...)
	for index := range personaIDs {
		personaIDs[index] = strings.TrimSpace(personaIDs[index])
	}
	sort.Strings(personaIDs)
	canonical := strings.Join([]string{
		strings.TrimSpace(event.EventID),
		UserAccountClosedEventName,
		strings.TrimSpace(event.AccountID),
		strconv.FormatInt(event.AccountVersion, 10),
		strings.Join(personaIDs, "\x1f"),
		strings.TrimSpace(event.AccountState),
		event.UpdatedAt.UTC().Format(time.RFC3339Nano),
		event.OccurredAt.UTC().Format(time.RFC3339Nano),
	}, "\x00")
	sum := sha256.Sum256([]byte(canonical))
	return hex.EncodeToString(sum[:])
}

// UserAccountClosedSubjectID 生成 Circle 存储侧关闭主体的不可逆查询键。
// 该键不含原始 account/persona id，可供迟到事件做 fail-closed 判定。
func UserAccountClosedSubjectID(subject string) string {
	sum := sha256.Sum256([]byte(
		"circle-closed-subject\x00" + strings.TrimSpace(subject),
	))
	return hex.EncodeToString(sum[:])
}

type UserAccountClosedApplyResult struct {
	Replayed bool
}

var ErrUserAccountRestrictionProjectionConflict = errors.New(
	"circle user account restriction projection conflict",
)

type UserAccountRestrictionProjectionResult struct {
	Replayed bool
	Stale    bool
	Terminal bool
	Affected int64
}

// UserAccountClosedProjection 的注销规则：
//   - Circle/Group membership（含 pending 申请）保留最小审计壳，主体 ID
//     不可逆匿名化，角色降为 member，状态置 removed，活跃度与贡献归零；
//   - active owner 先按管理员角色、加入时间、personaId、membershipId
//     确定性选继任者；无继任者则归档聚合，默认公开群失去 owner 时同时归档圈子；
//   - 行为事实及其未投递 outbox 物理删除，Post 派生视图删除，Placement
//     置 removed 并取消 pin/featured；
//   - Group/File 等共享资产继续保留，但创建者、上传者和审批人不可逆匿名化；
//   - 历史 receipt/outbox 同步收敛状态并擦除主体，避免重放重新暴露身份。
//
// inbox、owner 治理、清理和 outbox 必须在同一 Mongo 事务提交；任何 owner
// 不变量校验失败都整体回滚（fail closed）。缓存失效在事务后重试，成功后才 ACK。
type UserAccountClosedProjection interface {
	ApplyUserAccountClosed(
		ctx context.Context,
		event UserAccountClosedEvent,
	) (UserAccountClosedApplyResult, error)
}

type UserAccountRestrictionProjection interface {
	Apply(
		ctx context.Context,
		event accountrestriction.Event,
	) (UserAccountRestrictionProjectionResult, error)
}
