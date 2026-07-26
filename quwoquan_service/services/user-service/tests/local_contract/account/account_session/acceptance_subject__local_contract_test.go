package local_contract

import (
	"reflect"
	"testing"

	accountsession "quwoquan_service/services/user-service/internal/account/account_session/application"
)

func TestAcceptanceSubjectModerationOperatorUsesLeastPrivilegeClaims(t *testing.T) {
	subject, err := accountsession.Subject(
		"content-moderation-operator",
		"fixture_content_moderation_operator",
		"fixture_content_moderation_operator",
	)
	if err != nil {
		t.Fatalf("Subject returned error: %v", err)
	}
	if subject.AccountID != "fixture_content_moderation_operator" ||
		subject.PersonaID != "fixture_content_moderation_operator" {
		t.Fatalf("unexpected moderation operator identity: %#v", subject)
	}
	if !reflect.DeepEqual(subject.Scopes, []string{
		"ops.case.read",
		"ops.case.write",
	}) {
		t.Fatalf("unexpected moderation operator scopes: %#v", subject.Scopes)
	}
	if !reflect.DeepEqual(subject.Permissions, []string{
		"content.moderation.read",
		"content.moderation.review",
		"content.moderation.decide",
	}) {
		t.Fatalf(
			"unexpected moderation operator permissions: %#v",
			subject.Permissions,
		)
	}
	if !reflect.DeepEqual(subject.Roles, []string{"operator"}) {
		t.Fatalf("unexpected moderation operator roles: %#v", subject.Roles)
	}
}

func TestAcceptanceSubjectTelemetryQueryUsesReadOnlyScope(t *testing.T) {
	subject, err := accountsession.Subject(
		"product-telemetry-query",
		"fixture_telemetry_operator",
		"fixture_telemetry_operator",
	)
	if err != nil {
		t.Fatalf("Subject returned error: %v", err)
	}
	if !reflect.DeepEqual(subject.Scopes, []string{"ops.telemetry.read"}) {
		t.Fatalf("unexpected telemetry query scopes: %#v", subject.Scopes)
	}
	if !reflect.DeepEqual(subject.Permissions, []string(nil)) {
		t.Fatalf("telemetry query must not grant permissions: %#v", subject.Permissions)
	}
	if !reflect.DeepEqual(subject.Roles, []string{"operator"}) {
		t.Fatalf("unexpected telemetry query roles: %#v", subject.Roles)
	}
}

func TestAcceptanceSessionTargetsIncludeOnlyDeclaredLocalTopologies(t *testing.T) {
	want := map[string]string{
		"alpha": "alpha-local",
		"beta":  "beta-local",
		"gamma": "gamma-local",
		"prod":  "prod-sim",
	}
	if !reflect.DeepEqual(accountsession.LocalAcceptanceTargets, want) {
		t.Fatalf(
			"local acceptance targets=%#v want %#v",
			accountsession.LocalAcceptanceTargets,
			want,
		)
	}
}
