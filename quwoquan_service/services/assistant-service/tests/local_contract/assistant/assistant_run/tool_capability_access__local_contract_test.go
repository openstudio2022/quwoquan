// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/domain-reader-connector-grant/spec.md#gwt-001
package assistant_run_test

import (
	"context"
	"errors"
	"testing"
	"time"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/toolaccess"
	consentmodel "quwoquan_service/services/assistant-service/internal/assistant/skill_consent/domain/model"
	settingmodel "quwoquan_service/services/assistant-service/internal/assistant/skill_user_setting/domain/model"
)

type toolAccessSettingReader struct {
	setting settingmodel.Setting
	err     error
}

func (reader toolAccessSettingReader) Get(
	context.Context,
	string,
	string,
) (settingmodel.Setting, error) {
	return reader.setting, reader.err
}

func (reader toolAccessSettingReader) List(
	context.Context,
	string,
	int,
) ([]settingmodel.Setting, error) {
	return nil, nil
}

type toolAccessConsentReader struct {
	consents []consentmodel.Consent
	err      error
}

func (reader toolAccessConsentReader) ListActiveConsents(
	context.Context,
	string,
) ([]consentmodel.Consent, error) {
	return reader.consents, reader.err
}

type toolAccessConnectorGateway struct {
	decision toolaccess.ConnectorGrantDecision
	err      error
	calls    int
}

func (gateway *toolAccessConnectorGateway) ResolveCapability(
	context.Context,
	toolaccess.ConnectorGrantRequest,
) (toolaccess.ConnectorGrantDecision, error) {
	gateway.calls++
	return gateway.decision, gateway.err
}

func TestToolCapabilityAccessRechecksConsentConnectionAndSurface(t *testing.T) {
	grantedAt := time.Now().UTC()
	settings := toolAccessSettingReader{setting: settingmodel.Setting{
		AccountID:               "account-1",
		SkillID:                 "travel_companion",
		Status:                  settingmodel.StatusEnabled,
		ConnectorConnectionRefs: []string{"connection-1"},
	}}
	consents := toolAccessConsentReader{consents: []consentmodel.Consent{{
		ID:            "consent-1",
		AccountID:     "account-1",
		SkillID:       "travel_companion",
		GrantedScopes: []string{"calendar.event.create"},
		GrantedAt:     grantedAt,
	}}}
	gateway := &toolAccessConnectorGateway{decision: toolaccess.ConnectorGrantDecision{
		Allowed:      true,
		ConnectionID: "connection-1",
		ConnectorID:  "system_calendar",
		Reason:       "active_capability_grant",
	}}
	policy := toolaccess.NewPolicy(settings, consents, gateway)
	requirement := toolaccess.Requirement{
		CapabilityKey:        "calendar.event.create",
		ConnectorRequirement: toolaccess.ConnectorRequired,
		ConsentScopes:        []string{"calendar.event.create"},
		AllowedSurfaceKinds: []string{
			toolaccess.SurfacePersonal,
			toolaccess.SurfaceCircle,
		},
		RecheckAtExecution: true,
	}

	decision, err := policy.Authorize(context.Background(), toolaccess.Request{
		AccountID: "account-1", SkillID: "travel_companion",
		SurfaceKind: toolaccess.SurfacePersonal, Requirement: requirement,
	})
	if err != nil {
		t.Fatal(err)
	}
	if !decision.Allowed || decision.ConnectionID != "connection-1" || gateway.calls != 1 {
		t.Fatalf("unexpected decision: %+v calls=%d", decision, gateway.calls)
	}

	gateway.decision = toolaccess.ConnectorGrantDecision{Allowed: false, Reason: "connection_revoked"}
	_, err = policy.Authorize(context.Background(), toolaccess.Request{
		AccountID: "account-1", SkillID: "travel_companion",
		SurfaceKind: toolaccess.SurfacePersonal, Requirement: requirement,
	})
	if !errors.Is(err, toolaccess.ErrConnectorRequired) {
		t.Fatalf("revoked connector err=%v", err)
	}

	withoutConsent := toolaccess.NewPolicy(settings, toolAccessConsentReader{}, gateway)
	_, err = withoutConsent.Authorize(context.Background(), toolaccess.Request{
		AccountID: "account-1", SkillID: "travel_companion",
		SurfaceKind: toolaccess.SurfacePersonal, Requirement: requirement,
	})
	if !errors.Is(err, toolaccess.ErrConsentRequired) {
		t.Fatalf("missing consent err=%v", err)
	}

	callsBeforeSharedSurface := gateway.calls
	_, err = policy.Authorize(context.Background(), toolaccess.Request{
		AccountID: "account-1", SkillID: "travel_companion",
		SurfaceKind: toolaccess.SurfaceCircle, Requirement: requirement,
	})
	if !errors.Is(err, toolaccess.ErrSurfaceDenied) || gateway.calls != callsBeforeSharedSurface {
		t.Fatalf("shared surface err=%v gatewayCalls=%d", err, gateway.calls)
	}

	gateway.err = errors.New("integration unavailable")
	_, err = policy.Authorize(context.Background(), toolaccess.Request{
		AccountID: "account-1", SkillID: "travel_companion",
		SurfaceKind: toolaccess.SurfacePersonal, Requirement: requirement,
	})
	if !errors.Is(err, toolaccess.ErrGatewayUnavailable) {
		t.Fatalf("gateway failure err=%v", err)
	}
}
