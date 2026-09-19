package persona_relationship

import (
	"context"
	"fmt"
	"strings"

	relationshipgenerated "quwoquan_service/services/user-service/generated/relationship/persona_relationship"
	userrepo "quwoquan_service/services/user-service/internal/account/user_account/domain/user/ports"
)

// TargetKind 是关系目标的身份语义闭集。它由解析结果证明，不从入口路由、
// 显示名或 ID 前缀推断。
type TargetKind string

const (
	// TargetKindPersona 是普通可登录 Persona。
	TargetKindPersona TargetKind = "persona"
	// TargetKindCreator 是已发布 Creator 的公开身份。只能被关注，不能作为主体。
	TargetKindCreator TargetKind = "creator"
)

// ResolvedTarget 是一次目标解析的唯一结果。PersonaID 始终是 canonical 不可变
// 关系身份；入口传入的 handle 等 alias 必须先在此换成它才能入队。
type ResolvedTarget struct {
	PersonaID string
	Kind      TargetKind
}

// RelationshipTargetResolver 是关系目标身份的唯一解析面。
// 普通 Persona 按其不可变 ID/handle 读取；已发布 Creator 只经现役 exact
// Content fence 与其 canonical persona 映射验证。两类身份都不改写 Pair 输入
// 字节：Creator 的关系身份就是它已发布的 persona ID。
type RelationshipTargetResolver struct {
	personas     userrepo.PersonaReader
	creators     userrepo.CreatorRuntimeProfileReader
	contentFence userrepo.ContentReleaseFenceReader
}

func NewRelationshipTargetResolver(
	personas userrepo.PersonaReader,
	creators userrepo.CreatorRuntimeProfileReader,
	contentFence userrepo.ContentReleaseFenceReader,
) *RelationshipTargetResolver {
	return &RelationshipTargetResolver{
		personas:     personas,
		creators:     creators,
		contentFence: contentFence,
	}
}

// ResolveTarget 返回可被关注的唯一 canonical 目标。
// 未解析、失权、退役与跨类型歧义都返回 canonical failure，绝不返回猜测身份。
func (r *RelationshipTargetResolver) ResolveTarget(
	ctx context.Context,
	identity string,
) (ResolvedTarget, error) {
	identity = strings.TrimSpace(identity)
	if identity == "" {
		return ResolvedTarget{}, relationshipgenerated.AppErrorFromRelationshipInvalidPair(
			"relationship target identity is required",
		)
	}
	persona, err := r.lookupPersona(ctx, identity)
	if err != nil {
		return ResolvedTarget{}, err
	}
	creator, err := r.lookupCreator(ctx, identity)
	if err != nil {
		return ResolvedTarget{}, err
	}

	switch {
	case persona != nil && creator != nil:
		// 同一字节同时命中普通 Persona 与 Creator 公开身份。只有二者指向同一个
		// canonical persona 才是同一主体的两种视图；否则拒绝准入，不任选一方。
		if creator.PersonaID != persona.PersonaID {
			return ResolvedTarget{}, relationshipgenerated.AppErrorFromRelationshipInvalidPair(
				"relationship target identity resolves to two different subjects",
			)
		}
		return ResolvedTarget{PersonaID: persona.PersonaID, Kind: TargetKindPersona}, nil
	case persona != nil:
		return ResolvedTarget{PersonaID: persona.PersonaID, Kind: TargetKindPersona}, nil
	case creator != nil:
		return ResolvedTarget{PersonaID: creator.PersonaID, Kind: TargetKindCreator}, nil
	default:
		return ResolvedTarget{}, relationshipgenerated.AppErrorFromRelationshipTargetNotFound(
			"relationship target is missing, retired or no longer published",
		)
	}
}

// ResolveActor 只接受真实可登录 Persona 作为命令主体。
// Creator 公开身份即使可被关注也不得发起关系命令。
func (r *RelationshipTargetResolver) ResolveActor(
	ctx context.Context,
	personaID string,
) (string, error) {
	personaID = strings.TrimSpace(personaID)
	if personaID == "" {
		return "", relationshipgenerated.AppErrorFromRelationshipInvalidPair(
			"relationship actor identity is required",
		)
	}
	persona, err := r.lookupPersona(ctx, personaID)
	if err != nil {
		return "", err
	}
	if persona == nil {
		return "", relationshipgenerated.AppErrorFromRelationshipActorForbidden(
			"relationship actor must be a live persona",
		)
	}
	if persona.PersonaID != personaID {
		// 主体只以不可变 ID 提交；alias 不得成为写入身份。
		return "", relationshipgenerated.AppErrorFromRelationshipActorForbidden(
			"relationship actor must be submitted as its immutable persona id",
		)
	}
	return persona.PersonaID, nil
}

// lookupPersona 返回仍可作为公开关系端点的 Persona；退役即视为不存在。
func (r *RelationshipTargetResolver) lookupPersona(
	ctx context.Context,
	identity string,
) (*personaIdentityView, error) {
	if r.personas == nil {
		return nil, nil
	}
	persona, err := r.personas.FindByPersonaID(ctx, identity)
	if err != nil {
		return nil, err
	}
	if persona == nil {
		persona, err = r.personas.FindByUserHandle(ctx, identity)
		if err != nil {
			return nil, err
		}
	}
	if persona == nil || strings.EqualFold(strings.TrimSpace(persona.Status), "retired") {
		return nil, nil
	}
	return &personaIdentityView{PersonaID: strings.TrimSpace(persona.PersonaID)}, nil
}

// lookupCreator 只在现役 exact Content fence 下读取已发布 Creator 公开身份。
// 缺 fence、缺 reader 或缺 canonical persona 映射都视为不可作为目标。
func (r *RelationshipTargetResolver) lookupCreator(
	ctx context.Context,
	identity string,
) (*personaIdentityView, error) {
	if r.creators == nil || r.contentFence == nil {
		return nil, nil
	}
	fence, found, err := r.contentFence.ActiveContentReleaseFence(ctx)
	if err != nil {
		return nil, fmt.Errorf("read active Content release fence: %w", err)
	}
	if !found {
		return nil, nil
	}
	creator, found, err := r.creators.FindByExactContentFence(ctx, fence, identity)
	if err != nil {
		return nil, fmt.Errorf("read Creator public identity: %w", err)
	}
	if !found || creator == nil {
		return nil, nil
	}
	canonicalPersonaID := strings.TrimSpace(creator.PersonaID)
	if canonicalPersonaID == "" {
		// 已发布作者缺 canonical 身份映射时阻断该入口，不以隐藏按钮当修复。
		return nil, relationshipgenerated.AppErrorFromRelationshipTargetNotFound(
			"published Creator has no canonical persona identity",
		)
	}
	return &personaIdentityView{PersonaID: canonicalPersonaID}, nil
}

// personaIdentityView 只携带解析所需的 canonical 关系身份，避免把 Persona
// 或 Creator 的私有字段带进关系对象。
type personaIdentityView struct {
	PersonaID string
}
