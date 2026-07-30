package application

import "context"

// AccountRestrictionReader is the NotificationDeliveryJob read-side port.
// Storage failures must be returned so job creation can fail closed.
type AccountRestrictionReader interface {
	RestrictedSubjects(
		ctx context.Context,
		subjects []string,
	) (map[string]bool, error)
}
