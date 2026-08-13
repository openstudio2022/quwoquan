package local_contract

import (
	"context"
	"errors"
	"testing"
	"time"

	runtimeerrors "quwoquan_service/runtime/errors"
	application "quwoquan_service/services/user-service/internal/account/user_account/application/account_orchestration"
	usermodel "quwoquan_service/services/user-service/internal/account/user_account/domain/user/model"
	userports "quwoquan_service/services/user-service/internal/account/user_account/domain/user/ports"
	personaports "quwoquan_service/services/user-service/internal/persona_management/persona/domain/persona/ports"
)

func assertPersonaErrorCode(t *testing.T, err error, wantCode string) {
	t.Helper()
	var appErr *runtimeerrors.AppError
	if !errors.As(err, &appErr) || appErr.Code.String() != wantCode {
		t.Fatalf("expected %s, got %T: %v", wantCode, err, err)
	}
}

func newPersonaErrorCodeService(
	runtime *readinessPersonaRuntime,
) *application.PersonaService {
	return application.NewPersonaService(
		runtime,
		readinessPersonaCommands{runtime: runtime},
		readinessPersonaProjector{runtime: runtime},
		readinessProfileStore{runtime: runtime},
		readinessPersonaCache{},
	)
}

// handleConflictPersonaCommands 让创建提交撞上 user_handle 唯一约束。
type handleConflictPersonaCommands struct {
	readinessPersonaCommands
}

func (handleConflictPersonaCommands) CommitCreate(
	context.Context,
	*usermodel.Persona,
	personaports.PersonaCommandMeta,
) (personaports.PersonaCommandResult, error) {
	return personaports.PersonaCommandResult{}, userports.ErrPersonaHandleConflict
}

func TestUpdatePersonaSurfacesNotFoundForForeignOrMissingPersona(t *testing.T) {
	runtime, ownerID, _ := newReadinessPersonaRuntime(t)
	service := newPersonaErrorCodeService(runtime)

	_, err := service.UpdatePersona(
		t.Context(),
		ownerID,
		"missing-persona-id",
		application.UpdatePersonaCommand{},
		readinessPersonaMeta("update-missing"),
	)
	assertPersonaErrorCode(t, err, "USER.PERSONA.not_found")
}

func TestUpdatePersonaRejectsSystemAssignedHandleSync(t *testing.T) {
	runtime, ownerID, primaryID := newReadinessPersonaRuntime(t)
	service := newPersonaErrorCodeService(runtime)

	_, err := service.UpdatePersona(
		t.Context(),
		ownerID,
		primaryID,
		application.UpdatePersonaCommand{
			Sync: application.PersonaProfileSyncOptions{
				ApplyScope: "all_personas",
				FieldsMask: []string{"userHandle"},
			},
		},
		readinessPersonaMeta("update-handle"),
	)
	assertPersonaErrorCode(t, err, "USER.PERSONA.handle_readonly")
}

func TestCreatePersonaSurfacesHandleTakenOnUniqueConflict(t *testing.T) {
	runtime, ownerID, _ := newReadinessPersonaRuntime(t)
	service := application.NewPersonaService(
		runtime,
		handleConflictPersonaCommands{readinessPersonaCommands{runtime: runtime}},
		readinessPersonaProjector{runtime: runtime},
		readinessProfileStore{runtime: runtime},
		readinessPersonaCache{},
	)

	_, err := service.CreatePersona(
		t.Context(),
		ownerID,
		application.CreatePersonaCommand{DisplayName: "Conflicted Handle"},
		readinessPersonaMeta("create-handle-conflict"),
	)
	assertPersonaErrorCode(t, err, "USER.PERSONA.handle_taken")
}

func TestUpdatePersonaRejectsRetiredPersona(t *testing.T) {
	runtime, ownerID, _ := newReadinessPersonaRuntime(t)
	retiredAt := time.Now().UTC()
	runtime.personas["retired-persona"] = &usermodel.Persona{
		UserID:    ownerID,
		PersonaID: "retired-persona",
		Status:    "retired",
		RetiredAt: &retiredAt,
		Version:   1,
	}
	service := newPersonaErrorCodeService(runtime)

	name := "Renamed Retired"
	_, err := service.UpdatePersona(
		t.Context(),
		ownerID,
		"retired-persona",
		application.UpdatePersonaCommand{DisplayName: &name},
		readinessPersonaMeta("update-retired"),
	)
	assertPersonaErrorCode(t, err, "USER.PERSONA.retired_guard")
}

func TestRetirePersonaRejectsActivePersona(t *testing.T) {
	runtime, ownerID, _ := newReadinessPersonaRuntime(t)
	runtime.personas["active-secondary"] = &usermodel.Persona{
		UserID:    ownerID,
		PersonaID: "active-secondary",
		Status:    "active",
		IsActive:  true,
		Version:   1,
	}
	service := newPersonaErrorCodeService(runtime)

	_, err := service.RetirePersona(
		t.Context(),
		ownerID,
		"active-secondary",
		readinessPersonaMeta("retire-active"),
	)
	assertPersonaErrorCode(t, err, "USER.PERSONA.active_guard")
}

func TestRetirePersonaRejectsLastRemainingPersona(t *testing.T) {
	runtime, ownerID, primaryID := newReadinessPersonaRuntime(t)
	// primary 已退役,secondary 是唯一存续分身:禁止再退役最后一个。
	retiredAt := time.Now().UTC()
	primary := runtime.personas[primaryID]
	primary.Status = "retired"
	primary.IsActive = false
	primary.IsPrimary = false
	primary.RetiredAt = &retiredAt
	runtime.personas["last-secondary"] = &usermodel.Persona{
		UserID:    ownerID,
		PersonaID: "last-secondary",
		Status:    "active",
		IsActive:  false,
		Version:   1,
	}
	service := newPersonaErrorCodeService(runtime)

	_, err := service.RetirePersona(
		t.Context(),
		ownerID,
		"last-secondary",
		readinessPersonaMeta("retire-last"),
	)
	assertPersonaErrorCode(t, err, "USER.PERSONA.last_persona")
}
