package main

import (
	"context"
	"fmt"
	"strings"

	"github.com/jackc/pgx/v5/pgxpool"

	useraccountapp "quwoquan_service/services/user-service/internal/account/user_account/application/account_orchestration"
	usermodel "quwoquan_service/services/user-service/internal/account/user_account/domain/user/model"
	useraccountpersistence "quwoquan_service/services/user-service/internal/account/user_account/infrastructure/persistence"
	userpersistence "quwoquan_service/services/user-service/internal/account/user_account/infrastructure/user/persistence"
	personaports "quwoquan_service/services/user-service/internal/persona_management/persona/domain/persona/ports"
	personapersistence "quwoquan_service/services/user-service/internal/persona_management/persona/infrastructure/persona/persistence"
	releaseimport "quwoquan_service/services/user-service/internal/profile_projection/creator_runtime_profile/infrastructure/releaseimport"
)

type creatorPersonaMaterializer struct {
	reader    *userpersistence.PgPersonaStore
	commands  personaports.PersonaCommandStore
	projector *useraccountapp.PersonaProfileProjector
}

var _ releaseimport.CreatorPersonaMaterializer = (*creatorPersonaMaterializer)(nil)

func newCreatorPersonaMaterializer(
	pool *pgxpool.Pool,
) (releaseimport.CreatorPersonaMaterializer, error) {
	commands, err := personapersistence.NewPersonaCommandPostgresStore(pool)
	if err != nil {
		return nil, err
	}
	projectionStore, err := useraccountpersistence.NewPersonaProfileProjector(pool)
	if err != nil {
		return nil, err
	}
	projector, err := useraccountapp.NewPersonaProfileProjector(projectionStore)
	if err != nil {
		return nil, err
	}
	return &creatorPersonaMaterializer{
		reader:    userpersistence.NewPgPersonaStore(pool),
		commands:  commands,
		projector: projector,
	}, nil
}

func (materializer *creatorPersonaMaterializer) UpsertAndProject(
	ctx context.Context,
	state releaseimport.CreatorPersonaState,
	importRunID string,
) error {
	persona, err := materializer.reader.FindByPersonaID(ctx, state.PersonaID)
	if err != nil {
		return err
	}
	eventType := personaports.PersonaUpdatedEvent
	if persona == nil {
		persona = &usermodel.Persona{
			PersonaID: state.PersonaID,
			UserID:    state.UserID,
		}
		eventType = personaports.PersonaCreatedEvent
	}
	if strings.TrimSpace(persona.UserID) != strings.TrimSpace(state.UserID) {
		return fmt.Errorf("creator Persona owner collision: %s", state.PersonaID)
	}
	persona.DisplayName = state.DisplayName
	persona.NicknameCustomized = false
	persona.UserHandle = state.UserHandle
	persona.Bio = state.Bio
	persona.IdentityTags = append([]string(nil), state.IdentityTags...)
	persona.AvatarMediaAssetID = state.AvatarMediaAssetID
	persona.AvatarURL = state.AvatarURL
	persona.AvatarVersion = state.AvatarVersion
	persona.IsPrimary = true
	persona.IsPrivate = false
	persona.IsActive = true
	persona.IsolationLevel = "open"
	persona.Status = "active"
	persona.InheritsProfileFromOwner = false
	persona.OverriddenProfileFields = []string{}
	persona.LastProfileSyncSource = "manual_sync"

	meta, err := releaseimport.CreatorPersonaCommandMeta(state, importRunID)
	if err != nil {
		return err
	}
	var result personaports.PersonaCommandResult
	if eventType == personaports.PersonaCreatedEvent {
		result, err = materializer.commands.CommitCreate(ctx, persona, meta)
	} else {
		result, err = materializer.commands.CommitMutation(ctx, persona, eventType, meta)
	}
	if err != nil {
		return err
	}
	_, err = materializer.projector.Project(ctx, result.PersonaID, result.Version)
	return err
}
