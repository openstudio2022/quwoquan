package failures

type RecoveryAction string
type UserDisruptionLevel string

const (
	RecoveryActionAbsorb     RecoveryAction = "absorb"
	RecoveryActionRetry      RecoveryAction = "retry"
	RecoveryActionFallback   RecoveryAction = "fallback"
	RecoveryActionSurface    RecoveryAction = "surface"
	RecoveryActionEscalate   RecoveryAction = "escalate"
	RecoveryActionCompensate RecoveryAction = "compensate"
)

const (
	DisruptionSilent           UserDisruptionLevel = "silent"
	DisruptionPassiveIndicator UserDisruptionLevel = "passiveIndicator"
	DisruptionSnackbar         UserDisruptionLevel = "snackbar"
	DisruptionInlineCard       UserDisruptionLevel = "inlineCard"
	DisruptionPermissionCard   UserDisruptionLevel = "permissionCard"
)

type EntryContext struct {
	Kind      string
	EntryID   string
	ActorType string
	ActorID   string
	SurfaceID string
	SessionID string
}

type BoundaryContext struct {
	Boundary        string
	Stage           string
	RemainingBudget int
}

type RecoveryDecision struct {
	Action          RecoveryAction
	DisruptionLevel UserDisruptionLevel
	PolicyID        string
}

type RecoveryPolicy interface {
	Decide(FailureBase, EntryContext, BoundaryContext) RecoveryDecision
}

type DefaultRecoveryPolicy struct{}

func (DefaultRecoveryPolicy) Decide(
	failure FailureBase,
	_ EntryContext,
	boundary BoundaryContext,
) RecoveryDecision {
	if failure.RuntimeNature() == NatureTransient && boundary.RemainingBudget > 0 {
		return RecoveryDecision{
			Action:          RecoveryActionRetry,
			DisruptionLevel: DisruptionSilent,
			PolicyID:        "default.transient.retry",
		}
	}
	if failure.RuntimeNature() == NatureRequiresPermission {
		return RecoveryDecision{
			Action:          RecoveryActionSurface,
			DisruptionLevel: DisruptionPermissionCard,
			PolicyID:        "default.permission.surface",
		}
	}
	return RecoveryDecision{
		Action:          RecoveryActionSurface,
		DisruptionLevel: DisruptionInlineCard,
		PolicyID:        "default.surface",
	}
}
