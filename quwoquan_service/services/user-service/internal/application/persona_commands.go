package application

import (
	"crypto/sha256"
	"fmt"

	personaports "quwoquan_service/services/user-service/internal/domain/persona/persona/ports"
)

// PersonaCommandMeta 是 Persona 聚合命令的业务重放身份（幂等键 + 命令摘要）。
type PersonaCommandMeta = personaports.PersonaCommandMeta

// CreatePersonaCommand 对齐 contracts/metadata/user/persona/service.yaml 的
// CreatePersona request_fields。
type CreatePersonaCommand struct {
	DisplayName    string
	AvatarURL      string
	IsolationLevel string
	PurposeHint    string
}

// PersonaProfileSyncOptions 承载分身资料同步范围与字段掩码。
type PersonaProfileSyncOptions struct {
	ApplyScope    string
	SyncTargetIDs []string
	FieldsMask    []string
}

// UpdatePersonaCommand 对齐 UpdatePersona request_fields（PATCH 语义，
// nil 表示未提供该字段）。
type UpdatePersonaCommand struct {
	DisplayName    *string
	Phone          *string
	Email          *string
	AvatarURL      *string
	BackgroundURL  *string
	IsolationLevel *string
	PurposeHint    *string
	Sync           PersonaProfileSyncOptions
}

// ProfileUpdateCommand 对齐 UpdateUserProfile request_fields（PATCH /user/profile）。
// aggregate 规则禁止动态 Map patch；nil 表示未提供该字段。
type ProfileUpdateCommand struct {
	Nickname          *string
	DisplayName       *string
	AvatarAssetID     *string
	AvatarURL         *string
	BackgroundAssetID *string
	BackgroundURL     *string
	Bio               *string
	Gender            *string
	BirthDate         *string
	RegionTagRef      *string
	Region            *string
	OccupationTagRef  *string
	InterestTagRefs   []string
	IdentityTags      []string
	ProfileVisibility *string
	Sync              PersonaProfileSyncOptions
}

// derivePersonaSyncMeta 为 profile sync fan-out 的每个目标 Persona 派生
// 独立幂等键：personas_command_receipts.idempotency_key 全局唯一，
// 同一命令扇出到多个聚合时每个提交必须有自己的重放身份。
func derivePersonaSyncMeta(meta PersonaCommandMeta, subAccountID string) PersonaCommandMeta {
	digest := sha256.Sum256([]byte(meta.IdempotencyKey + "\x00sync\x00" + subAccountID))
	return PersonaCommandMeta{
		IdempotencyKey: fmt.Sprintf("persona-sync-%x", digest[:16]),
		CommandDigest:  meta.CommandDigest,
	}
}

func shouldApplyPersonaSyncScope(options PersonaProfileSyncOptions) bool {
	switch options.ApplyScope {
	case "", "current_subject_only":
		return false
	default:
		return true
	}
}
