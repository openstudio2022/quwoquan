// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-suspension-and-appeal-lifecycle/spec.md#gwt-003
// readiness_case: apply-notification-account-restriction-api
package api_integration

import (
	"testing"
	"time"

	"quwoquan_service/runtime/accountrestriction"
	"quwoquan_service/runtime/reliabletask"
)

func TestSuspendedRecipientSuppressesNewDeliveryWithoutBackfillAfterRestore(
	t *testing.T,
) {
	resetNotificationCollections(t)
	ctx := t.Context()
	projection := notificationRestrictionFacet
	now := time.Date(2026, time.July, 28, 10, 0, 0, 0, time.UTC)
	suspended := accountrestriction.Event{
		EventID:        "notification-suspend-11",
		EventName:      accountrestriction.UserSuspendedEventName,
		AccountID:      "notification-recipient-restricted",
		AccountVersion: 11,
		UserID:         "notification-recipient-restricted",
		PersonaIDs:     []string{},
		AccountState:   "suspended",
		AuthEpoch:      11,
		DecisionRef:    "notification-decision-11",
		OccurredAt:     now,
	}
	if _, err := projection.Apply(ctx, suspended); err != nil {
		t.Fatal(err)
	}
	restrictedJob, err := notificationReliableStore.CreateNotification(
		ctx,
		reliabletask.NotificationOutboxRecord{
			NotificationID:        "notification-restricted-job",
			SubjectNotificationID: "notification-restricted-subject",
			DedupeKey:             "restriction:notification-restricted-job",
			EventType:             "push",
			AggregateType:         "NotificationDeliveryJob",
			AggregateID:           "notification-restricted-subject",
			RecipientIDs:          []string{suspended.AccountID},
			NextAttemptAt:         now,
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	if restrictedJob.Status != reliabletask.NotificationStatusCancelled ||
		!restrictedJob.AccountRestricted ||
		!restrictedJob.RestrictionSuppressed {
		t.Fatalf("restricted delivery job=%+v", restrictedJob)
	}
	claimed, err := notificationReliableStore.ClaimNotification(
		ctx,
		nil,
		"restriction-test-worker",
		time.Minute,
		now.Add(time.Minute),
	)
	if err != nil || claimed != nil {
		t.Fatalf("restricted delivery claimed=%+v err=%v", claimed, err)
	}

	restored := suspended
	restored.EventID = "notification-restore-12"
	restored.EventName = accountrestriction.UserRestoredEventName
	restored.AccountVersion = 12
	restored.AccountState = "active"
	restored.AuthEpoch = 12
	restored.DecisionRef = "notification-decision-12"
	restored.OccurredAt = now.Add(time.Hour)
	if _, err := projection.Apply(ctx, restored); err != nil {
		t.Fatal(err)
	}
	claimed, err = notificationReliableStore.ClaimNotification(
		ctx,
		nil,
		"restriction-test-worker",
		time.Minute,
		now.Add(2*time.Hour),
	)
	if err != nil || claimed != nil {
		t.Fatalf("restore must not backfill old notification claimed=%+v err=%v", claimed, err)
	}
	activeJob, err := notificationReliableStore.CreateNotification(
		ctx,
		reliabletask.NotificationOutboxRecord{
			NotificationID:        "notification-restored-job",
			SubjectNotificationID: "notification-restored-subject",
			DedupeKey:             "restriction:notification-restored-job",
			EventType:             "push",
			AggregateType:         "NotificationDeliveryJob",
			AggregateID:           "notification-restored-subject",
			RecipientIDs:          []string{restored.AccountID},
			NextAttemptAt:         now.Add(2 * time.Hour),
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	if activeJob.Status == reliabletask.NotificationStatusCancelled ||
		activeJob.AccountRestricted || activeJob.RestrictionSuppressed {
		t.Fatalf("restored delivery job=%+v", activeJob)
	}
}
