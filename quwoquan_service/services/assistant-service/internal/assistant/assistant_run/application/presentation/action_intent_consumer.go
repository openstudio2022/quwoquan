package presentation

import (
	"context"
	"errors"
	"strings"
	"time"
)

var (
	ErrActionIntentExpired        = errors.New("assistant action intent expired")
	ErrActionIntentDigestMismatch = errors.New("assistant action intent digest mismatch")
	ErrActionIntentTargetMismatch = errors.New("assistant action intent target mismatch")
	ErrActionIntentReplay         = errors.New("assistant action intent replay")
)

// ActionIntentJTIStore atomically consumes an intent JTI until expiry.
// Production composition must supply a durable shared implementation;
// in-memory stores belong only in local_contract tests.
type ActionIntentJTIStore interface {
	ConsumeActionIntent(
		ctx context.Context,
		jti string,
		expiresAt time.Time,
	) (bool, error)
}

type ActionIntentExpectation struct {
	IntentID         string
	Kind             ActionIntentKind
	RequestDigest    string
	RunID            string
	ToolInvocationID string
}

type ActionIntentConsumer struct {
	store ActionIntentJTIStore
	now   func() time.Time
}

func NewActionIntentConsumer(
	store ActionIntentJTIStore,
) (*ActionIntentConsumer, error) {
	if store == nil {
		return nil, errors.New("assistant action intent JTI store is required")
	}
	return &ActionIntentConsumer{store: store, now: time.Now}, nil
}

// Consume verifies the closed typed intent and atomically marks its JTI before
// the caller executes any navigation, approval, device action or input.
func (c *ActionIntentConsumer) Consume(
	ctx context.Context,
	intent ActionIntent,
	expected ActionIntentExpectation,
) error {
	allowed := map[string]bool{string(intent.Kind): true}
	if err := validateActionIntent(intent, allowed); err != nil {
		return ErrActionRejected
	}
	now := c.now().UTC()
	if intent.IssuedAt.After(now) || !now.Before(intent.ExpiresAt) {
		return ErrActionIntentExpired
	}
	if intent.RequestDigest != strings.TrimSpace(expected.RequestDigest) {
		return ErrActionIntentDigestMismatch
	}
	if intent.IntentID != strings.TrimSpace(expected.IntentID) ||
		intent.Kind != expected.Kind {
		return ErrActionIntentTargetMismatch
	}
	runID, toolInvocationID := actionIntentTarget(intent)
	if runID != strings.TrimSpace(expected.RunID) ||
		toolInvocationID != strings.TrimSpace(expected.ToolInvocationID) {
		return ErrActionIntentTargetMismatch
	}
	consumed, err := c.store.ConsumeActionIntent(
		ctx,
		intent.JTI,
		intent.ExpiresAt.UTC(),
	)
	if err != nil {
		return err
	}
	if !consumed {
		return ErrActionIntentReplay
	}
	return nil
}

func actionIntentTarget(intent ActionIntent) (string, string) {
	switch intent.Kind {
	case ActionIntentApproveTool:
		if intent.ApproveTool != nil {
			return intent.ApproveTool.RunID, intent.ApproveTool.ToolInvocationID
		}
	case ActionIntentExecuteDeviceAction:
		if intent.ExecuteDeviceAction != nil {
			return intent.ExecuteDeviceAction.RunID,
				intent.ExecuteDeviceAction.ToolInvocationID
		}
	case ActionIntentProvideInput:
		if intent.ProvideInput != nil {
			return intent.ProvideInput.RunID, intent.ProvideInput.ToolInvocationID
		}
	}
	return "", ""
}
