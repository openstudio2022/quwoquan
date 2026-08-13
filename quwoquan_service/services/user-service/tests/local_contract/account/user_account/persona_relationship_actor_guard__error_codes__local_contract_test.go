package local_contract

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"quwoquan_service/runtime/operation"
	bindingapp "quwoquan_service/services/user-service/internal/account/credential_binding/application"
	bindingmodel "quwoquan_service/services/user-service/internal/account/credential_binding/domain/model"
	bindingports "quwoquan_service/services/user-service/internal/account/credential_binding/domain/ports"
	userhttp "quwoquan_service/services/user-service/internal/account/user_account/adapters/inbound/http"
	application "quwoquan_service/services/user-service/internal/account/user_account/application/account_orchestration"
)

type actorGuardCredentialStore struct{}

func (actorGuardCredentialStore) Bind(
	context.Context,
	bindingmodel.ChangeSet,
) (bindingports.BindResult, error) {
	return bindingports.BindResult{}, nil
}

func (actorGuardCredentialStore) LoadByOwnerAndType(
	context.Context,
	string,
	bindingmodel.CredentialType,
) (bindingmodel.CredentialBinding, bool, error) {
	return bindingmodel.CredentialBinding{}, false, nil
}

func (actorGuardCredentialStore) FindByTypeAndKey(
	context.Context,
	bindingmodel.CredentialType,
	string,
) (bindingmodel.CredentialBinding, bool, error) {
	return bindingmodel.CredentialBinding{}, false, nil
}

func (actorGuardCredentialStore) MarkUsed(
	context.Context,
	string,
	time.Time,
) error {
	return nil
}

func (actorGuardCredentialStore) ListByOwner(
	context.Context,
	string,
) ([]bindingmodel.CredentialBinding, error) {
	return nil, nil
}

func (actorGuardCredentialStore) CommitRevoke(
	context.Context,
	int64,
	bindingmodel.ChangeSet,
) error {
	return nil
}

func TestFollowWithForeignActorPersonaReturnsActorForbidden(t *testing.T) {
	t.Parallel()
	profiles, personas := profileErrCodeFixture()
	personaService := application.NewPersonaService(
		personas,
		profileErrCodeConflictCommands{},
		profileErrCodeProjector{},
		profiles,
		profileErrCodeCache{},
	)
	handler, err := userhttp.NewUserHandler(
		nil,
		nil,
		nil,
		nil,
		nil,
		bindingapp.NewCredentialQueryFacade(actorGuardCredentialStore{}),
		personaService,
		nil,
	)
	if err != nil {
		t.Fatalf("construct UserHandler: %v", err)
	}
	mux := http.NewServeMux()
	handler.RegisterRoutes(mux)

	// body 中的 actorPersonaId 与认证 principal 不一致,且不归属当前账号:
	// 必须以 actor_forbidden 拒绝伪造他人 persona 的关系命令。
	request := httptest.NewRequest(
		http.MethodPost,
		"/user/personas/target-persona/follow",
		strings.NewReader(`{"actorPersonaId":"foreign-persona"}`),
	)
	request.Header.Set("Content-Type", "application/json")
	request = request.WithContext(operation.WithContext(
		request.Context(),
		operation.Context{
			OperationID: "user.persona_relationship.FollowUser",
			RequestID:   "request-actor-guard",
			TraceID:     "trace-actor-guard",
			Actor: operation.ActorContext{
				AccountID: "owner-1",
				PersonaID: "persona-1",
			},
		},
	))
	recorder := httptest.NewRecorder()
	mux.ServeHTTP(recorder, request)

	var wire struct {
		Code string `json:"code"`
	}
	if err := json.Unmarshal(recorder.Body.Bytes(), &wire); err != nil {
		t.Fatalf("decode error response %q: %v", recorder.Body.String(), err)
	}
	if wire.Code != "USER.RELATIONSHIP.actor_forbidden" {
		t.Fatalf(
			"expected USER.RELATIONSHIP.actor_forbidden, got %s (status=%d body=%s)",
			wire.Code, recorder.Code, recorder.Body.String(),
		)
	}
}
