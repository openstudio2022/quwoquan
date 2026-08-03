package application

import (
	"context"
	"errors"
	"strings"
	"time"

	catalogmodel "quwoquan_service/services/assistant-service/internal/assistant/skill_catalog/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_surface_placement/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_surface_placement/domain/ports"
)

type SurfaceAuthority interface {
	RequireMember(context.Context, string, string, string) error
	RequireAdmin(context.Context, string, string, string) error
}

type SharedSkillValidator interface {
	ValidateSharedSkillIDs(context.Context, string, []string) error
}

// FailClosedSurfaceAuthority keeps the route explicit while Chat/Circle typed
// authority readers are not wired. It must never be treated as an allow-all
// development fallback.
type FailClosedSurfaceAuthority struct{}

func (FailClosedSurfaceAuthority) RequireMember(
	context.Context,
	string,
	string,
	string,
) error {
	return model.ErrAuthorityUnavailable
}

func (FailClosedSurfaceAuthority) RequireAdmin(
	context.Context,
	string,
	string,
	string,
) error {
	return model.ErrAuthorityUnavailable
}

type CommandFacade struct {
	store     ports.Store
	authority SurfaceAuthority
	catalog   SharedSkillValidator
	now       func() time.Time
}

type QueryFacade struct {
	reader    ports.Reader
	authority SurfaceAuthority
}

func NewCommandFacade(
	store ports.Store,
	authority SurfaceAuthority,
	catalog SharedSkillValidator,
	now func() time.Time,
) *CommandFacade {
	if now == nil {
		now = func() time.Time { return time.Now().UTC() }
	}
	return &CommandFacade{store: store, authority: authority, catalog: catalog, now: now}
}

func NewQueryFacade(reader ports.Reader, authority SurfaceAuthority) *QueryFacade {
	return &QueryFacade{reader: reader, authority: authority}
}

func (facade *QueryFacade) Get(
	ctx context.Context,
	accountID string,
	personaID string,
	surfaceKind string,
	surfaceID string,
) (model.Placement, error) {
	if facade == nil || facade.reader == nil {
		return model.Placement{}, model.ErrStorageUnavailable
	}
	if facade.authority == nil {
		return model.Placement{}, model.ErrAuthorityUnavailable
	}
	accountID = strings.TrimSpace(accountID)
	personaID = strings.TrimSpace(personaID)
	surfaceKind = strings.TrimSpace(surfaceKind)
	surfaceID = strings.TrimSpace(surfaceID)
	if accountID == "" || personaID == "" || surfaceKind == "" || surfaceID == "" {
		return model.Placement{}, model.ErrInvalidArgument
	}
	if err := facade.authority.RequireMember(ctx, personaID, surfaceKind, surfaceID); err != nil {
		return model.Placement{}, normalizeAuthorityError(err)
	}
	return facade.reader.Get(ctx, surfaceKind, surfaceID)
}

// AllowsSkill is the internal dynamic policy boundary consumed after the
// invoking Conversation/Circle has already been authenticated by its owner.
func (facade *QueryFacade) AllowsSkill(
	ctx context.Context,
	surfaceKind string,
	surfaceID string,
	skillID string,
) (bool, error) {
	if facade == nil || facade.reader == nil {
		return false, model.ErrStorageUnavailable
	}
	placement, err := facade.reader.Get(ctx, strings.TrimSpace(surfaceKind), strings.TrimSpace(surfaceID))
	if err != nil {
		return false, err
	}
	return placement.Allows(skillID), nil
}

func (facade *CommandFacade) Put(
	ctx context.Context,
	input model.PutInput,
) (model.MutationResult, error) {
	if facade == nil || facade.store == nil {
		return model.MutationResult{}, model.ErrStorageUnavailable
	}
	if facade.authority == nil {
		return model.MutationResult{}, model.ErrAuthorityUnavailable
	}
	if facade.catalog == nil {
		return model.MutationResult{}, model.ErrPackageUnavailable
	}
	input.OccurredAt = facade.now()
	command, err := model.NewPutCommand(input)
	if err != nil {
		return model.MutationResult{}, err
	}
	if err := facade.authority.RequireAdmin(
		ctx,
		command.ActorPersonaID,
		command.SurfaceKind,
		command.SurfaceID,
	); err != nil {
		return model.MutationResult{}, normalizeAuthorityError(err)
	}
	if err := facade.catalog.ValidateSharedSkillIDs(
		ctx,
		command.SurfaceKind,
		command.DisabledSkillIDs,
	); err != nil {
		if errors.Is(err, catalogmodel.ErrSkillNotShared) {
			return model.MutationResult{}, model.ErrUnknownSkill
		}
		return model.MutationResult{}, model.ErrPackageUnavailable
	}
	return facade.store.Apply(ctx, command)
}

func normalizeAuthorityError(err error) error {
	if errors.Is(err, model.ErrForbidden) {
		return model.ErrForbidden
	}
	return model.ErrAuthorityUnavailable
}
