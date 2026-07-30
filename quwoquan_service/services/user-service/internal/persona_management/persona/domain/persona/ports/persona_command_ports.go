package ports

import (
	"context"
	"errors"

	usermodel "quwoquan_service/services/user-service/internal/account/user_account/domain/user/model"
)

// Persona 命令事件类型：与 services/user-service/contracts/persona_management/persona/events.yaml 对齐。
const (
	PersonaCreatedEvent   = "PersonaCreated"
	PersonaUpdatedEvent   = "PersonaUpdated"
	PersonaRetiredEvent   = "PersonaRetired"
	PersonaActivatedEvent = "PersonaActivated"
)

var (
	// ErrPersonaCommandMetaRequired 表示命令缺少幂等键或摘要。
	ErrPersonaCommandMetaRequired = errors.New("persona command requires idempotency key and digest")
	// ErrPersonaIdempotencyConflict 表示同一幂等键被复用于不同命令。
	ErrPersonaIdempotencyConflict = errors.New("persona idempotency key was reused with a different command")
	// ErrPersonaVersionConflict 表示提交与并发变更冲突（锁行 CAS 失败）。
	ErrPersonaVersionConflict = errors.New("persona version conflict")
)

// PersonaCommandMeta 承载一次命令的业务重放身份。
// IdempotencyKey 来自传输层 Idempotency-Key（operation.Context），
// CommandDigest 是命令负载的稳定摘要；二者共同保证同键同命令重放原结果。
type PersonaCommandMeta struct {
	IdempotencyKey string
	CommandDigest  string
}

// PersonaCommandResult 是命令的稳定回执。
type PersonaCommandResult struct {
	PersonaID string `json:"personaId"`
	Version   int64  `json:"version"`
	Replayed  bool   `json:"replayed,omitempty"`
}

// PersonaCommandStore 是 Persona 聚合的对象专属命令提交端口。
// 每个提交在同一 PostgreSQL 事务内原子写入 state、personas_command_receipts
// 与 personas_outbox；同一幂等键重放返回首次结果。
type PersonaCommandStore interface {
	// CommitCreate 插入新 Persona（version=1）。
	CommitCreate(
		ctx context.Context,
		persona *usermodel.Persona,
		meta PersonaCommandMeta,
	) (PersonaCommandResult, error)
	// CommitMutation 锁行读取当前 version 后以内部 CAS 全列更新。
	CommitMutation(
		ctx context.Context,
		persona *usermodel.Persona,
		eventType string,
		meta PersonaCommandMeta,
	) (PersonaCommandResult, error)
	// CommitActivation 原子切换 owner 的激活 Persona（排他）。
	CommitActivation(
		ctx context.Context,
		ownerID string,
		personaID string,
		meta PersonaCommandMeta,
	) (PersonaCommandResult, error)
}
