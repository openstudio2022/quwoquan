package application

import (
	"context"
	"errors"
	"strings"
	"time"
)

var (
	ErrAccountCreationFlowConflict   = errors.New("account creation flow identity conflicts with its stored intent")
	ErrAccountCreationFlowNotFound   = errors.New("account creation flow not found")
	ErrAccountCreationCandidateStale = errors.New("account creation Persona candidate changed or was already committed")
)

// AccountCreationFlow 是 UserAccount owner 的最小持久恢复状态。
// 它只保存流程坐标、已选择的不可变身份与步骤完成状态，不复制 profile、Persona
// 或 credential 业务字段。每次恢复仍需读取各 authority 确认步骤事实。
type AccountCreationFlow struct {
	FlowID           string
	IntentDigest     string
	OwnerID          string
	PersonaID        string
	DefaultNickname  string
	IdentityOrigin   string
	AccountCommitted bool
	PersonaCommitted bool
	ProfileProjected bool
	CredentialBound  bool
	Completed        bool
	CreatedAt        time.Time
	UpdatedAt        time.Time
}

func (flow AccountCreationFlow) Validate() error {
	if strings.TrimSpace(flow.FlowID) == "" ||
		strings.TrimSpace(flow.IntentDigest) == "" ||
		strings.TrimSpace(flow.OwnerID) == "" ||
		strings.TrimSpace(flow.PersonaID) == "" ||
		strings.TrimSpace(flow.DefaultNickname) == "" ||
		strings.TrimSpace(flow.IdentityOrigin) == "" {
		return errors.New("account creation flow identity is incomplete")
	}
	return nil
}

// AccountCreationRecoveryStore 是注册恢复状态的唯一持久端口。
// Begin 使用 flowId+intentDigest 做 create-once/CAS：同一凭据重入返回首次选择的
// Account/Persona ID，不重新分配；同 flow 不同意图返回冲突。
type AccountCreationRecoveryStore interface {
	Begin(ctx context.Context, flow AccountCreationFlow) (AccountCreationFlow, error)
	Load(ctx context.Context, flowID string) (AccountCreationFlow, bool, error)
	MarkStep(ctx context.Context, flowID string, step AccountCreationStep) error
	ReplacePersonaCandidate(ctx context.Context, flowID, expectedPersonaID, nextPersonaID string) error
}

type AccountCreationStep string

const (
	AccountCreationAccountCommitted AccountCreationStep = "account_committed"
	AccountCreationPersonaCommitted AccountCreationStep = "persona_committed"
	AccountCreationProfileProjected AccountCreationStep = "profile_projected"
	AccountCreationCredentialBound  AccountCreationStep = "credential_bound"
)

func (step AccountCreationStep) ValidForPersistence() bool {
	switch step {
	case AccountCreationAccountCommitted,
		AccountCreationPersonaCommitted,
		AccountCreationProfileProjected,
		AccountCreationCredentialBound:
		return true
	default:
		return false
	}
}
