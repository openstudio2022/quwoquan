package domain

import "context"

// Owner is the trusted AssistantRun ownership projection exposed to sibling
// application services. The authoritative record remains inside AssistantRun.
type Owner struct {
	UserID           string
	PersonaID        string
	TriggerMessageID string
}

// OwnerReader is the only typed port for resolving AssistantRun ownership.
// Consumers must not read assistant_runs directly.
type OwnerReader interface {
	ResolveRunOwner(context.Context, string) (Owner, bool, error)
}
