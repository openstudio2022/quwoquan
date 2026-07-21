package main

import (
	"slices"
	"testing"
)

func TestAcceptanceSubjectDefaultsToPersona(t *testing.T) {
	subject, err := acceptanceSubject("", "account-1", "persona-1")
	if err != nil {
		t.Fatalf("acceptanceSubject: %v", err)
	}
	if subject.AccountID != "account-1" || subject.PersonaID != "persona-1" {
		t.Fatalf("persona subject mismatch: %+v", subject)
	}
	if len(subject.Roles) != 0 || len(subject.Scopes) != 0 || len(subject.Permissions) != 0 {
		t.Fatalf("persona profile must not gain operator privileges: %+v", subject)
	}
}

func TestAcceptanceSubjectReportOperatorUsesFixedLeastPrivilegeProfile(t *testing.T) {
	subject, err := acceptanceSubject(
		"content-report-operator",
		"operator-account",
		"operator-persona",
	)
	if err != nil {
		t.Fatalf("acceptanceSubject: %v", err)
	}
	if !slices.Equal(subject.Roles, []string{"operator"}) {
		t.Fatalf("operator roles mismatch: %v", subject.Roles)
	}
	if !slices.Equal(subject.Scopes, []string{"ops.case.read", "ops.case.write"}) {
		t.Fatalf("operator scopes mismatch: %v", subject.Scopes)
	}
	if !slices.Equal(
		subject.Permissions,
		[]string{
			"content.report.read",
			"content.report.review",
			"content.report.resolve",
		},
	) {
		t.Fatalf("operator permissions mismatch: %v", subject.Permissions)
	}
}

func TestAcceptanceSubjectFilterCatalogPublisherUsesServiceScopeOnly(t *testing.T) {
	subject, err := acceptanceSubject(
		"content-filter-catalog-publisher",
		"publisher-account",
		"publisher-persona",
	)
	if err != nil {
		t.Fatalf("acceptanceSubject: %v", err)
	}
	if !slices.Equal(subject.Roles, []string{"service"}) {
		t.Fatalf("publisher roles mismatch: %v", subject.Roles)
	}
	if !slices.Equal(subject.Scopes, []string{"content.filter_catalog.manage"}) {
		t.Fatalf("publisher scopes mismatch: %v", subject.Scopes)
	}
	if len(subject.Permissions) != 0 {
		t.Fatalf("publisher must not gain unrelated permissions: %v", subject.Permissions)
	}
}

func TestAcceptanceSubjectRejectsUnknownProfile(t *testing.T) {
	if _, err := acceptanceSubject(
		"arbitrary-admin",
		"account-1",
		"persona-1",
	); err == nil {
		t.Fatal("unknown acceptance profile must fail closed")
	}
}
