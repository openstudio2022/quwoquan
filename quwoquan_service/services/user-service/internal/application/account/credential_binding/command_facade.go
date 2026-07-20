// Package credential_binding 提供 CredentialBinding 对象专属强类型 command Facet。
package credential_binding

import (
	"context"
	"errors"
	"strings"
	"time"

	"github.com/google/uuid"

	"quwoquan_service/runtime/operation"
	bindingmodel "quwoquan_service/services/user-service/internal/domain/account/credential_binding/model"
	bindingports "quwoquan_service/services/user-service/internal/domain/account/credential_binding/ports"
	"quwoquan_service/services/user-service/internal/generated"
)

const credentialBindingCommitAttempts = 3

type CommandFacet interface {
	BindVerifiedCredential(
		context.Context,
		string,
		BindCredentialCommand,
	) (CommandResult, error)
	UnbindCredential(context.Context, UnbindCredentialCommand) (CommandResult, error)
}

type CredentialCommandFacade struct {
	store      bindingports.AggregateStore
	now        func() time.Time
	generateID func() string
}

type Option func(*CredentialCommandFacade)

func WithClock(now func() time.Time) Option {
	return func(facade *CredentialCommandFacade) {
		if now != nil {
			facade.now = now
		}
	}
}

func WithIDGenerator(generateID func() string) Option {
	return func(facade *CredentialCommandFacade) {
		if generateID != nil {
			facade.generateID = generateID
		}
	}
}

func NewCredentialCommandFacade(
	store bindingports.AggregateStore,
	options ...Option,
) *CredentialCommandFacade {
	if store == nil {
		panic("CredentialCommandFacade requires an object-specific AggregateStore")
	}
	facade := &CredentialCommandFacade{
		store:      store,
		now:        time.Now,
		generateID: uuid.NewString,
	}
	for _, option := range options {
		if option != nil {
			option(facade)
		}
	}
	return facade
}

var _ CommandFacet = (*CredentialCommandFacade)(nil)

// BindVerifiedCredential 只供登录/挑战协调器在 provider/OTP 已验证后调用。
// credentialKey 必须是不可逆、服务端解析得到的稳定身份，不得传入 provider
// token、OTP 或客户端自声明 actor。
func (facade *CredentialCommandFacade) BindVerifiedCredential(
	ctx context.Context,
	ownerID string,
	command BindCredentialCommand,
) (CommandResult, error) {
	ownerID = strings.TrimSpace(ownerID)
	if ownerID == "" {
		return CommandResult{}, generated.AppErrorFromUnauthorized(
			"CredentialBinding requires a verified account owner",
		)
	}
	aggregateID := strings.TrimSpace(facade.generateID())
	eventID := strings.TrimSpace(facade.generateID())
	if aggregateID == "" || eventID == "" {
		return CommandResult{}, generated.AppErrorFromInternalError(
			"CredentialBinding id generator returned an empty identity",
		)
	}
	change, err := bindingmodel.Bind(bindingmodel.BindParams{
		ID:             aggregateID,
		OwnerID:        ownerID,
		CredentialType: command.CredentialType,
		CredentialKey:  command.CredentialKey,
		DisplayLabel:   command.DisplayLabel,
		EventID:        eventID,
		BoundAt:        facade.now().UTC(),
	})
	if err != nil {
		return CommandResult{}, mapCredentialMutationError(err)
	}
	result, err := facade.store.Bind(ctx, change)
	if err != nil {
		return CommandResult{}, mapCredentialCommitError(err)
	}
	if err := result.Aggregate.Validate(); err != nil {
		return CommandResult{}, generated.AppErrorFromInternalError(
			"CredentialBinding store returned invalid aggregate state",
		)
	}
	resultState := result.Aggregate.State()
	if resultState.OwnerID != ownerID ||
		resultState.CredentialType != command.CredentialType ||
		resultState.CredentialKey != strings.TrimSpace(command.CredentialKey) ||
		resultState.Status != bindingmodel.StatusActive {
		return CommandResult{}, generated.AppErrorFromInternalError(
			"CredentialBinding store returned an aggregate outside the command identity",
		)
	}
	return commandResult(result.Aggregate, result.Replayed), nil
}

func (facade *CredentialCommandFacade) UnbindCredential(
	ctx context.Context,
	command UnbindCredentialCommand,
) (CommandResult, error) {
	ownerID, err := credentialOwnerID(ctx)
	if err != nil {
		return CommandResult{}, err
	}
	if !command.CredentialType.Valid() {
		return CommandResult{}, generated.AppErrorFromInvalidArgument(
			"UnbindCredential requires a known credentialType",
		)
	}

	for attempt := 0; attempt < credentialBindingCommitAttempts; attempt++ {
		current, found, loadErr := facade.store.LoadByOwnerAndType(
			ctx,
			ownerID,
			command.CredentialType,
		)
		if loadErr != nil {
			return CommandResult{}, generated.AppErrorFromInternalError(
				"CredentialBinding load failed",
			)
		}
		if !found {
			return CommandResult{}, generated.AppErrorFromUserNotFound(
				"CredentialBinding does not exist for the requested credentialType",
			)
		}
		expectedVersion := current.Snapshot().Version
		eventID := ""
		if current.Snapshot().Status == bindingmodel.StatusActive {
			eventID = strings.TrimSpace(facade.generateID())
			if eventID == "" {
				return CommandResult{}, generated.AppErrorFromInternalError(
					"CredentialBinding id generator returned an empty event identity",
				)
			}
		}
		occurredAt := facade.now().UTC()
		if boundAt := current.State().BoundAt; occurredAt.Before(boundAt) {
			// 持久化行可能由数据库时钟写入；应用时钟轻微落后时，仍以聚合
			// 已知时间为下界，保证审计事件单调而不把合法解绑误判为参数错误。
			occurredAt = boundAt
		}
		change, mutationErr := current.Revoke(
			eventID,
			occurredAt,
		)
		if mutationErr != nil {
			return CommandResult{}, mapCredentialMutationError(mutationErr)
		}
		if !change.Changed {
			return commandResult(current, true), nil
		}
		commitErr := facade.store.CommitRevoke(ctx, expectedVersion, change)
		if errors.Is(commitErr, bindingmodel.ErrVersionConflict) &&
			attempt+1 < credentialBindingCommitAttempts {
			continue
		}
		if commitErr != nil {
			return CommandResult{}, mapCredentialCommitError(commitErr)
		}
		return commandResult(change.Aggregate, false), nil
	}
	panic("unreachable CredentialBinding CAS retry")
}

func credentialOwnerID(ctx context.Context) (string, error) {
	current, ok := operation.FromContext(ctx)
	if !ok || current.Actor.Validate(operation.ActorAccount) != nil {
		return "", generated.AppErrorFromUnauthorized(
			"CredentialBinding requires a trusted account actor",
		)
	}
	return strings.TrimSpace(current.Actor.AccountID), nil
}

func commandResult(
	aggregate bindingmodel.CredentialBinding,
	replayed bool,
) CommandResult {
	snapshot := aggregate.Snapshot()
	return CommandResult{
		OwnerID:          aggregate.State().OwnerID,
		CredentialType:   snapshot.CredentialType,
		IsActive:         snapshot.IsActive(),
		Version:          snapshot.Version,
		IdempotentReplay: replayed,
		DisplayLabel:     snapshot.DisplayLabel,
	}
}

func mapCredentialMutationError(err error) error {
	if errors.Is(err, bindingmodel.ErrInvalidCredentialBinding) {
		return generated.AppErrorFromInvalidArgument(
			"CredentialBinding command contains invalid attributes",
		)
	}
	return generated.AppErrorFromInternalError(
		"CredentialBinding state transition failed",
	)
}

func mapCredentialCommitError(err error) error {
	switch {
	case errors.Is(err, bindingports.ErrCredentialConflict):
		return generated.AppErrorFromCredentialConflict(
			"CredentialBinding unique identity is already owned",
		)
	case errors.Is(err, bindingports.ErrLastRecoverableCredential):
		return generated.AppErrorFromLastCredential(
			"CredentialBinding revoke would remove the last recoverable credential",
		)
	case errors.Is(err, bindingports.ErrCredentialBindingNotFound):
		return generated.AppErrorFromUserNotFound(
			"CredentialBinding disappeared during commit",
		)
	case errors.Is(err, bindingmodel.ErrVersionConflict):
		return generated.AppErrorFromInternalError(
			"CredentialBinding changed repeatedly during commit",
		)
	default:
		return generated.AppErrorFromInternalError(
			"CredentialBinding persistence failed",
		)
	}
}
