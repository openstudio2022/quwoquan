// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-003
// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-004
// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-suspension-and-appeal-lifecycle/spec.md#gwt-003
package api_integration

import (
	"context"
	"errors"
	"strings"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/runtime/accountrestriction"
	streamadapter "quwoquan_service/services/notification-service/internal/notification_delivery/notification/adapters/inbound/stream"
	"quwoquan_service/services/notification-service/internal/notification_delivery/notification/application"
	"quwoquan_service/services/notification-service/internal/notification_delivery/notification/infrastructure/persistence"
)

func TestUserAccountClosedConsumerAtomicallyCleansOwnedNotificationData(
	t *testing.T,
) {
	resetNotificationCollections(t)
	seedAccountClosureOwnedData(t)
	suspension := accountrestriction.Event{
		EventID:        "evt-account-owner-suspended",
		EventName:      accountrestriction.UserSuspendedEventName,
		AccountID:      "account-owner",
		AccountVersion: 10,
		UserID:         "account-owner",
		PersonaIDs:     []string{"persona-owner"},
		AccountState:   "suspended",
		AuthEpoch:      10,
		DecisionRef:    "decision-account-owner-suspended",
		OccurredAt:     accountClosureContractTime.Add(-time.Minute),
	}
	if result, err := notificationRestriction.Apply(
		context.Background(),
		suspension,
	); err != nil || result.Replayed {
		t.Fatalf("apply Notification suspension: result=%+v err=%v", result, err)
	}
	sameVersionConflict := suspension
	sameVersionConflict.EventID = "evt-account-owner-suspended-conflict"
	sameVersionConflict.DecisionRef = "decision-account-owner-suspended-conflict"
	if _, err := notificationRestriction.Apply(
		context.Background(),
		sameVersionConflict,
	); !errors.Is(err, application.ErrUserAccountRestrictionProjectionConflict) {
		t.Fatalf("same-version Notification restriction conflict err=%v", err)
	}
	// Closure also erases legacy rows from the superseded generic adapter.
	if _, err := notificationMongoDB.Collection(
		"notification_user_account_restrictions",
	).InsertOne(context.Background(), bson.M{
		"_id": "account-owner", "subjects": []string{"account-owner", "persona-owner"},
		"restricted": true, "accountVersion": int64(9),
	}); err != nil {
		t.Fatal(err)
	}
	if _, err := notificationMongoDB.Collection(
		"notification_user_account_restriction_inbox",
	).InsertOne(context.Background(), bson.M{
		"_id": "evt-account-owner-legacy-suspended", "accountId": "account-owner",
		"accountVersion": int64(9),
	}); err != nil {
		t.Fatal(err)
	}
	consumer := newAccountClosureIntegrationConsumer(t, 3)
	appendAccountClosureIntegrationEvent(
		t,
		"evt-account-owner-closed",
		"account-owner",
		[]string{"persona-owner"},
	)

	processed, err := consumer.ProcessOnce(context.Background())
	if err != nil {
		t.Fatalf("process UserAccountClosed integration event: %v", err)
	}
	if processed != 1 {
		t.Fatalf("processed=%d want=1", processed)
	}
	if count := countAccountClosureDocuments(
		t,
		"app_messages",
		bson.M{"_id": bson.M{"$in": bson.A{
			"msg-account-owner",
			"msg-persona-owner",
		}}},
	); count != 0 {
		t.Fatalf("closed-account app messages remaining=%d", count)
	}
	if count := countAccountClosureDocuments(
		t,
		"app_messages",
		bson.M{"_id": "msg-unrelated"},
	); count != 1 {
		t.Fatalf("unrelated app message count=%d want=1", count)
	}
	if count := countAccountClosureDocuments(
		t,
		"notification_delivery_jobs",
		bson.M{"_id": bson.M{"$in": bson.A{
			"job-account-owner",
			"job-persona-owner",
		}}},
	); count != 0 {
		t.Fatalf("closed-account delivery jobs remaining=%d", count)
	}
	if count := countAccountClosureDocuments(
		t,
		"notification_delivery_jobs",
		bson.M{"_id": "job-unrelated"},
	); count != 1 {
		t.Fatalf("unrelated delivery job count=%d want=1", count)
	}
	if count := countAccountClosureDocuments(
		t,
		"notification_delivery_job_recipients",
		bson.M{"recipientId": "account-owner"},
	); count != 0 {
		t.Fatalf("closed-account recipient records remaining=%d", count)
	}
	if count := countAccountClosureDocuments(
		t,
		"notification_user_account_restrictions",
		bson.M{},
	); count != 0 {
		t.Fatalf("closed-account restriction state remaining=%d", count)
	}
	if count := countAccountClosureDocuments(
		t,
		"notification_user_account_restriction_inbox",
		bson.M{},
	); count != 0 {
		t.Fatalf("closed-account restriction inbox remaining=%d", count)
	}
	lateRestore := suspension
	lateRestore.EventID = "evt-account-owner-restore-after-close"
	lateRestore.EventName = accountrestriction.UserRestoredEventName
	lateRestore.AccountVersion = 12
	lateRestore.AccountState = "active"
	lateRestore.AuthEpoch = 12
	lateRestore.DecisionRef = "decision-account-owner-restore-after-close"
	lateRestore.OccurredAt = accountClosureContractTime.Add(time.Minute)
	if late, err := notificationRestriction.Apply(
		context.Background(),
		lateRestore,
	); err != nil || !late.Replayed || !late.Stale || !late.Terminal || late.Affected != 0 {
		t.Fatalf("late Notification restore after closure: result=%+v err=%v", late, err)
	}
	delayedSuspend := suspension
	delayedSuspend.EventID = "evt-account-owner-delayed-suspend"
	delayedSuspend.AccountVersion = 9
	delayedSuspend.AuthEpoch = 9
	delayedSuspend.DecisionRef = "decision-account-owner-delayed-suspend"
	delayedSuspend.OccurredAt = accountClosureContractTime.Add(-2 * time.Minute)
	if late, err := notificationRestriction.Apply(
		context.Background(),
		delayedSuspend,
	); err != nil || !late.Replayed || !late.Stale || !late.Terminal || late.Affected != 0 {
		t.Fatalf("delayed Notification suspend after closure: result=%+v err=%v", late, err)
	}
	if count := countAccountClosureDocuments(
		t,
		"notification_user_account_restrictions",
		bson.M{},
	); count != 0 {
		t.Fatalf("late events recreated Notification restriction state=%d", count)
	}
	if count := countAccountClosureDocuments(
		t,
		"notification_user_account_restriction_inbox",
		bson.M{},
	); count != 0 {
		t.Fatalf("late events recreated Notification restriction inbox=%d", count)
	}
	var terminalWatermark bson.M
	if err := notificationMongoDB.Collection(
		"notification_user_account_restriction_watermarks",
	).FindOne(
		context.Background(),
		bson.M{"terminal": true, "accountVersion": int64(11)},
	).Decode(&terminalWatermark); err != nil {
		t.Fatalf("read Notification terminal restriction watermark: %v", err)
	}
	encodedWatermark, err := bson.MarshalExtJSON(terminalWatermark, false, false)
	if err != nil {
		t.Fatal(err)
	}
	for _, rawID := range []string{"account-owner", "persona-owner"} {
		if strings.Contains(string(encodedWatermark), rawID) {
			t.Fatalf("Notification terminal watermark retained raw identity %q: %s", rawID, encodedWatermark)
		}
	}

	var outbox struct {
		AggregateID string            `bson:"aggregateId"`
		Payload     map[string]string `bson:"payload"`
	}
	if err := notificationMongoDB.Collection(
		"notification_delivery_jobs_outbox",
	).FindOne(
		context.Background(),
		bson.M{"_id": "job-persona-owner:1:created"},
	).Decode(&outbox); err != nil {
		t.Fatalf("read anonymized delivery outbox: %v", err)
	}
	if outbox.AggregateID == "job-persona-owner" ||
		outbox.Payload["notificationId"] == "rtc-event-persona-owner" ||
		outbox.Payload["callId"] == "call-persona-owner" ||
		outbox.Payload["deviceId"] == "device-persona-owner" ||
		outbox.Payload["deliveryKey"] == "delivery-persona-owner" {
		t.Fatalf("delivery audit retained direct account references: %v", outbox)
	}

	var receipt struct {
		CommandDigest string `bson:"commandDigest"`
		Result        struct {
			JobID          string `bson:"jobId"`
			NotificationID string `bson:"notificationId"`
		} `bson:"result"`
	}
	if err := notificationMongoDB.Collection(
		"notification_delivery_jobs_command_receipts",
	).FindOne(
		context.Background(),
		bson.M{"_id": "receipt-account-owner"},
	).Decode(&receipt); err != nil {
		t.Fatalf("read anonymized command receipt: %v", err)
	}
	if receipt.CommandDigest == "digest-job-account-owner" ||
		receipt.Result.JobID == "job-account-owner" ||
		receipt.Result.NotificationID == "msg-account-owner" {
		t.Fatalf("command receipt retained direct account references: %v", receipt)
	}

	var attempt struct {
		TaskID            string `bson:"taskId"`
		RequestID         string `bson:"requestId"`
		ProviderRequestID string `bson:"providerRequestId"`
		MaskedRecipient   string `bson:"maskedRecipient"`
	}
	if err := notificationMongoDB.Collection(
		"external_provider_attempt_ledger",
	).FindOne(
		context.Background(),
		bson.M{"_id": "attempt-account-owner"},
	).Decode(&attempt); err != nil {
		t.Fatalf("read anonymized provider attempt: %v", err)
	}
	if attempt.TaskID == "job-account-owner" ||
		attempt.RequestID == "request-account-owner" ||
		attempt.ProviderRequestID == "provider-request-owner" ||
		attempt.MaskedRecipient != "" {
		t.Fatalf("provider attempt retained direct account references: %v", attempt)
	}

	var inbox bson.M
	if err := notificationMongoDB.Collection(
		persistence.UserAccountClosedInboxCollection,
	).FindOne(
		context.Background(),
		bson.M{"_id": "evt-account-owner-closed"},
	).Decode(&inbox); err != nil {
		t.Fatalf("read UserAccountClosed inbox: %v", err)
	}
	if inbox["eventDigest"] == "" {
		t.Fatal("UserAccountClosed inbox must retain event digest")
	}
	for _, forbidden := range []string{"userId", "personaIds", "payload"} {
		if _, exists := inbox[forbidden]; exists {
			t.Fatalf(
				"UserAccountClosed inbox must not retain %s: %v",
				forbidden,
				inbox,
			)
		}
	}

	appendAccountClosureIntegrationEvent(
		t,
		"evt-account-owner-closed",
		"account-owner",
		[]string{"persona-owner"},
	)
	if _, err := consumer.ProcessOnce(context.Background()); err != nil {
		t.Fatalf("process UserAccountClosed replay: %v", err)
	}
	if count := countAccountClosureDocuments(
		t,
		persistence.UserAccountClosedInboxCollection,
		bson.M{"_id": "evt-account-owner-closed"},
	); count != 1 {
		t.Fatalf("UserAccountClosed inbox replay count=%d want=1", count)
	}
}

func TestUserAccountClosedConflictStaysPendingThenDLQCanBeRecovered(
	t *testing.T,
) {
	resetNotificationCollections(t)
	firstEvent := application.UserAccountClosedEvent{
		EventID:        "evt-account-conflict",
		AccountVersion: 1,
		UserID:         "account-first",
		PersonaIDs:     []string{},
		AccountState:   "closed",
		UpdatedAt:      accountClosureContractTime,
		OccurredAt:     accountClosureContractTime,
	}
	if _, err := notificationAccountClosure.ApplyUserAccountClosed(
		context.Background(),
		firstEvent,
	); err != nil {
		t.Fatalf("seed first UserAccountClosed inbox record: %v", err)
	}
	if _, err := notificationMongoDB.Collection("app_messages").InsertOne(
		context.Background(),
		bson.M{
			"_id":            "msg-conflicting-account",
			"idempotencyKey": "idem-conflicting-account",
			"userId":         "account-conflicting",
			"destination": bson.M{
				"type": "user",
				"id":   "account-conflicting",
			},
			"createdAt": accountClosureContractTime,
		},
	); err != nil {
		t.Fatalf("seed conflicting account message: %v", err)
	}
	consumer := newAccountClosureIntegrationConsumer(t, 2)
	sourceStreamID := appendAccountClosureIntegrationEvent(
		t,
		"evt-account-conflict",
		"account-conflicting",
		[]string{},
	)

	if _, err := consumer.ProcessOnce(context.Background()); err == nil {
		t.Fatal("eventId reuse conflict must fail closed")
	}
	pending, _, err := notificationRedisClient.XAutoClaim(
		context.Background(),
		streamadapter.UserAccountEventStream,
		streamadapter.UserAccountClosedConsumerGroup,
		"account-closure-pending-inspector",
		0,
		"0-0",
		10,
	)
	if err != nil {
		t.Fatalf("inspect conflict pending state: %v", err)
	}
	if len(pending) != 1 {
		t.Fatalf("pending conflict messages=%d want=1", len(pending))
	}
	if count := countAccountClosureDocuments(
		t,
		"app_messages",
		bson.M{"_id": "msg-conflicting-account"},
	); count != 1 {
		t.Fatalf("conflict must not clean second account, count=%d", count)
	}
	var failure bson.M
	if err := notificationMongoDB.Collection(
		persistence.UserAccountClosedFailureCollection,
	).FindOne(context.Background(), bson.M{}).Decode(&failure); err != nil {
		t.Fatalf("read UserAccountClosed failure state: %v", err)
	}
	if failure["eventDigest"] == "" ||
		failure["errorClass"] != "identity_conflict" ||
		failure["errorDigest"] == "" {
		t.Fatalf("failure state must retain only digests: %v", failure)
	}
	for _, forbidden := range []string{
		"eventId",
		"accountId",
		"personaIds",
		"payload",
		"lastError",
	} {
		if _, exists := failure[forbidden]; exists {
			t.Fatalf("failure state leaked %s: %v", forbidden, failure)
		}
	}

	if _, err := consumer.ProcessOnce(context.Background()); err != nil {
		t.Fatalf("second conflict attempt should move to DLQ: %v", err)
	}
	pending, _, err = notificationRedisClient.XAutoClaim(
		context.Background(),
		streamadapter.UserAccountEventStream,
		streamadapter.UserAccountClosedConsumerGroup,
		"account-closure-post-dlq-inspector",
		0,
		"0-0",
		10,
	)
	if err != nil {
		t.Fatalf("inspect pending state after DLQ: %v", err)
	}
	if len(pending) != 1 {
		t.Fatalf("pending after DLQ=%d want=1", len(pending))
	}
	if pending[0].ID != sourceStreamID || pending[0].Values["payload"] == "" {
		t.Fatalf(
			"source PEL must retain original recovery payload: %+v",
			pending[0],
		)
	}
	failure = nil
	if err := notificationMongoDB.Collection(
		persistence.UserAccountClosedFailureCollection,
	).FindOne(context.Background(), bson.M{}).Decode(&failure); err != nil {
		t.Fatalf("read terminal UserAccountClosed failure state: %v", err)
	}
	if failure["deadLetteredAt"] == nil {
		t.Fatalf("terminal failure state must hold source PEL for recovery: %v", failure)
	}
	if failure["sourceStream"] != streamadapter.UserAccountEventStream ||
		failure["sourceStreamId"] != sourceStreamID {
		t.Fatalf(
			"terminal failure marker lost source PEL reference: %v",
			failure,
		)
	}
	if _, exists := failure["expireAt"]; exists {
		t.Fatalf(
			"terminal failure marker must not use transient retry TTL: %v",
			failure,
		)
	}
	if _, err := notificationAccountClosure.RecordUserAccountClosedFailure(
		context.Background(),
		streamadapter.UserAccountEventStream,
		sourceStreamID,
		"evt-account-conflict",
		"identity_conflict",
		errors.New("late failure after terminal marker"),
	); err == nil {
		t.Fatal("late failure must not restore terminal retry TTL")
	}
	if err := notificationRedisClient.XGroupCreateMkStream(
		context.Background(),
		streamadapter.UserAccountClosedDeadLetterStream,
		"account-closure-dlq-recovery",
		"0",
	); err != nil {
		t.Fatalf("create account-closure DLQ recovery group: %v", err)
	}
	deadLetters, err := notificationRedisClient.XReadGroup(
		context.Background(),
		"account-closure-dlq-recovery",
		"recovery",
		map[string]string{
			streamadapter.UserAccountClosedDeadLetterStream: ">",
		},
		10,
		100*time.Millisecond,
	)
	if err != nil {
		t.Fatalf("read account-closure DLQ: %v", err)
	}
	if len(deadLetters) != 1 {
		t.Fatalf("account-closure DLQ entries=%d want=1", len(deadLetters))
	}
	for _, forbidden := range []string{
		"eventId",
		"accountId",
		"accountVersion",
		"payload",
		"personaIds",
		"userId",
		"occurredAt",
		"error",
	} {
		if _, exists := deadLetters[0].Values[forbidden]; exists {
			t.Fatalf("DLQ leaked %s: %v", forbidden, deadLetters[0].Values)
		}
	}
	for _, required := range []string{
		"deadLetterId",
		"sourceStream",
		"sourceStreamId",
		"eventClass",
		"eventDigest",
		"contentDigest",
		"attempts",
		"errorClass",
		"errorDigest",
		"deadLetteredAt",
	} {
		if deadLetters[0].Values[required] == "" {
			t.Fatalf("DLQ missing %s: %v", required, deadLetters[0].Values)
		}
	}
	if deadLetters[0].Values["sourceStream"] !=
		streamadapter.UserAccountEventStream ||
		deadLetters[0].Values["sourceStreamId"] != sourceStreamID ||
		deadLetters[0].Values["eventClass"] != "user_account_closed" ||
		deadLetters[0].Values["errorClass"] != "identity_conflict" ||
		deadLetters[0].Values["attempts"] != "2" {
		t.Fatalf("DLQ reference drifted: %v", deadLetters[0].Values)
	}
	failureID, failureIDOK := failure["_id"].(string)
	if !failureIDOK ||
		deadLetters[0].Values["deadLetterId"] != failureID {
		t.Fatalf(
			"DLQ must correlate to failure state by irreversible ID: failure=%v dlq=%v",
			failure,
			deadLetters[0].Values,
		)
	}

	if _, err := notificationMongoDB.Collection(
		persistence.UserAccountClosedInboxCollection,
	).DeleteOne(
		context.Background(),
		bson.M{"_id": firstEvent.EventID},
	); err != nil {
		t.Fatalf("repair conflicting inbox record before recovery: %v", err)
	}
	if err := consumer.RecoverDeadLetter(context.Background(), sourceStreamID); err != nil {
		t.Fatalf("release source PEL for account-closure recovery: %v", err)
	}
	if _, err := consumer.ProcessOnce(context.Background()); err != nil {
		t.Fatalf("recover original source account-closure event: %v", err)
	}
	if count := countAccountClosureDocuments(
		t,
		"app_messages",
		bson.M{"_id": "msg-conflicting-account"},
	); count != 0 {
		t.Fatalf("recovered cleanup left app messages=%d", count)
	}
	if count := countAccountClosureDocuments(
		t,
		persistence.UserAccountClosedInboxCollection,
		bson.M{},
	); count != 1 {
		t.Fatalf("account-closure inbox records=%d want=1", count)
	}
}
