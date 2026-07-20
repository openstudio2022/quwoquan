// Package model 定义 CredentialBinding 聚合及 active -> revoked 单向生命周期。
// CredentialKey 是不可逆凭证引用，只存在于对象专属持久化状态，不进入 Snapshot、
// 事件 payload 或 transport DTO。
package model

import (
	"errors"
	"fmt"
	"strings"
	"time"
)

var (
	ErrInvalidCredentialBinding = errors.New("credential binding is invalid")
	ErrVersionConflict          = errors.New("credential binding version conflict")
)

type CredentialType string

const (
	CredentialTypePhone           CredentialType = "phone"
	CredentialTypeCarrierPhone    CredentialType = "carrier_phone"
	CredentialTypeWechat          CredentialType = "wechat"
	CredentialTypeAlipay          CredentialType = "alipay"
	CredentialTypeQQ              CredentialType = "qq"
	CredentialTypeApple           CredentialType = "apple"
	CredentialTypePasskey         CredentialType = "passkey"
	CredentialTypeAnonymousDevice CredentialType = "anonymous_device"
)

func (credentialType CredentialType) Valid() bool {
	switch credentialType {
	case CredentialTypePhone,
		CredentialTypeCarrierPhone,
		CredentialTypeWechat,
		CredentialTypeAlipay,
		CredentialTypeQQ,
		CredentialTypeApple,
		CredentialTypePasskey,
		CredentialTypeAnonymousDevice:
		return true
	default:
		return false
	}
}

// Recoverable 表示该凭证能否独立恢复账号。匿名设备只提供游客连续性，
// 不能满足“账号至少保留一种可恢复凭证”的安全不变量。
func (credentialType CredentialType) Recoverable() bool {
	return credentialType.Valid() &&
		credentialType != CredentialTypeAnonymousDevice
}

type Status string

const (
	StatusActive  Status = "active"
	StatusRevoked Status = "revoked"
)

func (status Status) Valid() bool {
	return status == StatusActive || status == StatusRevoked
}

const (
	CredentialBoundEvent   = "CredentialBound"
	CredentialRevokedEvent = "CredentialRevoked"
)

// State 是 CredentialBinding 对象专属 Store 的持久化形态。
// 禁止给 CredentialKey 增加 JSON tag 或将 State 暴露给 transport。
type State struct {
	ID             string
	OwnerID        string
	CredentialType CredentialType
	CredentialKey  string
	DisplayLabel   string
	Status         Status
	BoundAt        time.Time
	LastUsedAt     *time.Time
	Version        int64
}

// Snapshot 是 application 可返回的脱敏快照，刻意排除 OwnerID、CredentialKey
// 与 LastUsedAt。
type Snapshot struct {
	ID             string
	CredentialType CredentialType
	DisplayLabel   string
	Status         Status
	BoundAt        time.Time
	Version        int64
}

func (snapshot Snapshot) IsActive() bool {
	return snapshot.Status == StatusActive
}

type Event struct {
	ID               string
	Type             string
	AggregateID      string
	AggregateVersion int64
	OccurredAt       time.Time
}

type ChangeSet struct {
	Aggregate CredentialBinding
	Events    []Event
	Changed   bool
}

type BindParams struct {
	ID             string
	OwnerID        string
	CredentialType CredentialType
	CredentialKey  string
	DisplayLabel   string
	EventID        string
	BoundAt        time.Time
}

type CredentialBinding struct {
	state State
}

func Bind(params BindParams) (ChangeSet, error) {
	state := State{
		ID:             strings.TrimSpace(params.ID),
		OwnerID:        strings.TrimSpace(params.OwnerID),
		CredentialType: params.CredentialType,
		CredentialKey:  strings.TrimSpace(params.CredentialKey),
		DisplayLabel:   strings.TrimSpace(params.DisplayLabel),
		Status:         StatusActive,
		BoundAt:        params.BoundAt.UTC(),
		Version:        1,
	}
	aggregate, err := Restore(state)
	if err != nil {
		return ChangeSet{}, err
	}
	event := Event{
		ID:               strings.TrimSpace(params.EventID),
		Type:             CredentialBoundEvent,
		AggregateID:      state.ID,
		AggregateVersion: state.Version,
		OccurredAt:       state.BoundAt,
	}
	if err := validateEvent(event, aggregate); err != nil {
		return ChangeSet{}, err
	}
	return ChangeSet{
		Aggregate: aggregate,
		Events:    []Event{event},
		Changed:   true,
	}, nil
}

func Restore(state State) (CredentialBinding, error) {
	state.ID = strings.TrimSpace(state.ID)
	state.OwnerID = strings.TrimSpace(state.OwnerID)
	state.CredentialKey = strings.TrimSpace(state.CredentialKey)
	state.DisplayLabel = strings.TrimSpace(state.DisplayLabel)
	state.BoundAt = state.BoundAt.UTC()
	state.LastUsedAt = cloneTime(state.LastUsedAt)
	if err := validateState(state); err != nil {
		return CredentialBinding{}, err
	}
	return CredentialBinding{state: state}, nil
}

func (binding CredentialBinding) State() State {
	state := binding.state
	state.LastUsedAt = cloneTime(binding.state.LastUsedAt)
	return state
}

func (binding CredentialBinding) Snapshot() Snapshot {
	state := binding.State()
	return Snapshot{
		ID:             state.ID,
		CredentialType: state.CredentialType,
		DisplayLabel:   state.DisplayLabel,
		Status:         state.Status,
		BoundAt:        state.BoundAt,
		Version:        state.Version,
	}
}

func (binding CredentialBinding) Validate() error {
	return validateState(binding.state)
}

// Revoke 是唯一状态迁移。revoked 是终态，重复调用返回稳定 no-op；
// 聚合不存在任何重新激活入口。
func (binding CredentialBinding) Revoke(
	eventID string,
	occurredAt time.Time,
) (ChangeSet, error) {
	if err := binding.Validate(); err != nil {
		return ChangeSet{}, err
	}
	if binding.state.Status == StatusRevoked {
		return ChangeSet{Aggregate: binding}, nil
	}
	if occurredAt.IsZero() || occurredAt.Before(binding.state.BoundAt) {
		return ChangeSet{}, fmt.Errorf(
			"%w: revoke clock must not precede boundAt",
			ErrInvalidCredentialBinding,
		)
	}
	next := binding.State()
	next.Status = StatusRevoked
	next.Version++
	revoked, err := Restore(next)
	if err != nil {
		return ChangeSet{}, err
	}
	event := Event{
		ID:               strings.TrimSpace(eventID),
		Type:             CredentialRevokedEvent,
		AggregateID:      next.ID,
		AggregateVersion: next.Version,
		OccurredAt:       occurredAt.UTC(),
	}
	if err := validateEvent(event, revoked); err != nil {
		return ChangeSet{}, err
	}
	return ChangeSet{
		Aggregate: revoked,
		Events:    []Event{event},
		Changed:   true,
	}, nil
}

func validateState(state State) error {
	if invalidText(state.ID, 64) ||
		invalidText(state.OwnerID, 96) ||
		invalidText(state.CredentialKey, 256) ||
		invalidOptionalText(state.DisplayLabel, 32) {
		return fmt.Errorf(
			"%w: identity or credential attributes are invalid",
			ErrInvalidCredentialBinding,
		)
	}
	if !state.CredentialType.Valid() ||
		!state.Status.Valid() ||
		state.BoundAt.IsZero() ||
		state.Version < 1 {
		return fmt.Errorf(
			"%w: lifecycle attributes are invalid",
			ErrInvalidCredentialBinding,
		)
	}
	if state.Status == StatusRevoked && state.Version < 2 {
		return fmt.Errorf(
			"%w: revoked binding must advance its version",
			ErrInvalidCredentialBinding,
		)
	}
	if state.LastUsedAt != nil && state.LastUsedAt.Before(state.BoundAt) {
		return fmt.Errorf(
			"%w: lastUsedAt cannot precede boundAt",
			ErrInvalidCredentialBinding,
		)
	}
	return nil
}

func validateEvent(event Event, aggregate CredentialBinding) error {
	state := aggregate.State()
	if invalidText(event.ID, 64) ||
		(event.Type != CredentialBoundEvent &&
			event.Type != CredentialRevokedEvent) ||
		event.AggregateID != state.ID ||
		event.AggregateVersion != state.Version ||
		event.OccurredAt.IsZero() {
		return fmt.Errorf(
			"%w: security outbox event is not aligned with aggregate state",
			ErrInvalidCredentialBinding,
		)
	}
	return nil
}

func invalidText(value string, maxLength int) bool {
	return value == "" ||
		strings.TrimSpace(value) != value ||
		len(value) > maxLength
}

func invalidOptionalText(value string, maxLength int) bool {
	return value != "" &&
		(strings.TrimSpace(value) != value || len(value) > maxLength)
}

func cloneTime(value *time.Time) *time.Time {
	if value == nil {
		return nil
	}
	cloned := value.UTC()
	return &cloned
}
