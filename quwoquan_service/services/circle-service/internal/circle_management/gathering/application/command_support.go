package gathering

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"strings"
	"time"

	"quwoquan_service/runtime/operation"
	circleerrors "quwoquan_service/services/circle-service/generated/circle_management/circle"
	ports "quwoquan_service/services/circle-service/internal/circle_management/gathering/domain/ports"
)

const receiptRetention = 7 * 24 * time.Hour

// CommandFacade owns Scope B participation commands. Lifecycle and host/outcome
// commands have dedicated facades so every generated operation has one entry.
type CommandFacade struct {
	store ports.AggregateStore
	now   func() time.Time
}

func NewCommandFacade(store ports.AggregateStore) *CommandFacade {
	if store == nil {
		panic("Gathering CommandFacade requires AggregateStore")
	}
	return &CommandFacade{store: store, now: time.Now}
}

func trustedCommandContext(
	ctx context.Context,
) (operation.Context, string, error) {
	current, ok := operation.FromContext(ctx)
	if !ok || current.Validate(operation.ActorPersona) != nil ||
		strings.TrimSpace(current.IdempotencyKey) == "" {
		return operation.Context{}, "", circleerrors.AppErrorFromInvalidArgument(
			"trusted persona and Idempotency-Key are required",
		)
	}
	return current, strings.TrimSpace(current.Actor.PersonaID), nil
}

func receiptKey(actorID, key string) string {
	return actorID + ":" + strings.TrimSpace(key)
}

func commandDigest(actorID, operationName string, payload any) (string, error) {
	encoded, err := json.Marshal(struct {
		ActorID       string `json:"actorId"`
		OperationName string `json:"operation"`
		Payload       any    `json:"payload"`
	}{actorID, operationName, payload})
	if err != nil {
		return "", err
	}
	digest := sha256.Sum256(encoded)
	return hex.EncodeToString(digest[:]), nil
}
