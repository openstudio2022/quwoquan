// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/skill-user-lifecycle/spec.md#gwt-002
package skill_subscription_test

import (
	"testing"
	"time"

	subscriptionapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_subscription/application"
)

func TestDailyCronUsesSubscriptionTimezoneAndPersistsUTCInstant(t *testing.T) {
	after := time.Date(2026, 8, 1, 23, 30, 0, 0, time.UTC)

	next, ok := subscriptionapplication.NextCronTrigger(
		"0 8 * * *",
		"Asia/Shanghai",
		after,
	)
	if !ok {
		t.Fatal("expected a next trigger in Asia/Shanghai")
	}
	want := time.Date(2026, 8, 2, 0, 0, 0, 0, time.UTC)
	if !next.Equal(want) {
		t.Fatalf("next=%s want=%s", next, want)
	}
	if !subscriptionapplication.CronMatchesMinute(
		"0 8 * * *",
		"Asia/Shanghai",
		want,
	) {
		t.Fatal("08:00 Asia/Shanghai must match 00:00 UTC")
	}
}

func TestDailyCronRejectsImplicitOrInvalidTimezone(t *testing.T) {
	for _, timezone := range []string{"", "Local", "CST", "Mars/Olympus"} {
		if subscriptionapplication.TimezoneSupported(timezone) {
			t.Fatalf("timezone %q unexpectedly supported", timezone)
		}
		if _, ok := subscriptionapplication.NextCronTrigger(
			"0 8 * * *",
			timezone,
			time.Now().UTC(),
		); ok {
			t.Fatalf("timezone %q unexpectedly scheduled", timezone)
		}
	}
}
