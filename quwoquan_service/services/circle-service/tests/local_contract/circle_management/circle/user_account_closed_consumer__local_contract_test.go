// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-003
// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-004
// readiness_case: recover-circle-account-closure-dead-letter-local
package local_contract

import (
	"bytes"
	"context"
	"errors"
	"log/slog"
	. "quwoquan_service/services/circle-service/internal/circle_management/circle/infrastructure/messaging"
	"strconv"
	"strings"
	"testing"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/circle-service/internal/circle_management/circle/application"
	"quwoquan_service/services/circle-service/tests/support"
)

type userAccountClosedProjectionSpy struct {
	events   []application.UserAccountClosedEvent
	result   application.UserAccountClosedApplyResult
	applyErr error
	attempts map[string]int64
	cleared  []string
	dead     map[string]bool
}

func (spy *userAccountClosedProjectionSpy) ApplyUserAccountClosed(
	_ context.Context,
	event application.UserAccountClosedEvent,
) (application.UserAccountClosedApplyResult, error) {
	spy.events = append(spy.events, event)
	return spy.result, spy.applyErr
}

func (spy *userAccountClosedProjectionSpy) RecordUserAccountClosedFailure(
	_ context.Context,
	messageID string,
	_ string,
	_ error,
) (int64, error) {
	if spy.attempts == nil {
		spy.attempts = map[string]int64{}
	}
	spy.attempts[messageID]++
	return spy.attempts[messageID], nil
}

func (spy *userAccountClosedProjectionSpy) ClearUserAccountClosedFailure(
	_ context.Context,
	messageID string,
) error {
	delete(spy.attempts, messageID)
	delete(spy.dead, messageID)
	spy.cleared = append(spy.cleared, messageID)
	return nil
}

func (spy *userAccountClosedProjectionSpy) IsUserAccountClosedDeadLettered(
	_ context.Context,
	messageID string,
) (bool, error) {
	return spy.dead[messageID], nil
}

func (spy *userAccountClosedProjectionSpy) MarkUserAccountClosedDeadLettered(
	_ context.Context,
	messageID string,
) error {
	if spy.dead == nil {
		spy.dead = map[string]bool{}
	}
	spy.dead[messageID] = true
	return nil
}

type userAccountClosedRedisSpy struct {
	rtredis.Client
	expirations map[string]time.Duration
}

func (spy *userAccountClosedRedisSpy) Expire(
	ctx context.Context,
	key string,
	ttl time.Duration,
) error {
	if spy.expirations == nil {
		spy.expirations = map[string]time.Duration{}
	}
	spy.expirations[key] = ttl
	return spy.Client.Expire(ctx, key, ttl)
}

func TestUserAccountClosedConsumerProjectsCanonicalEventAndAcks(t *testing.T) {
	ctx := t.Context()
	client := rtredis.NewMemoryClient()
	projection := &userAccountClosedProjectionSpy{}
	consumer := newUserAccountClosedTestConsumer(t, client, projection, 3)

	if _, err := client.XAdd(
		ctx,
		UserAccountEventStream,
		userAccountClosedValues("event-1", "account-1", 7),
	); err != nil {
		t.Fatal(err)
	}
	if count, err := consumer.ProcessOnce(ctx); err != nil || count != 1 {
		t.Fatalf("ProcessOnce count=%d err=%v", count, err)
	}
	if len(projection.events) != 1 {
		t.Fatalf("projection events=%d want=1", len(projection.events))
	}
	event := projection.events[0]
	if event.EventID != "event-1" ||
		event.AccountID != "account-1" ||
		event.UserID != "account-1" ||
		event.AccountVersion != 7 ||
		len(event.PersonaIDs) != 2 ||
		event.PersonaIDs[0] != "persona-a" ||
		event.PersonaIDs[1] != "persona-b" {
		t.Fatalf("typed UserAccountClosed event drift: %#v", event)
	}
	if err := consumer.Healthy(time.Second); err != nil {
		t.Fatalf("consumer must report a healthy completed scan: %v", err)
	}
}

func TestUserAccountClosedConsumerRecoversTransientProjectionFailure(
	t *testing.T,
) {
	ctx := t.Context()
	client := rtredis.NewMemoryClient()
	projection := &userAccountClosedProjectionSpy{
		applyErr: errors.New("transient projection failure"),
	}
	consumer := newUserAccountClosedTestConsumer(t, client, projection, 3)
	if _, err := client.XAdd(
		ctx,
		UserAccountEventStream,
		userAccountClosedValues("event-recovery", "account-recovery", 2),
	); err != nil {
		t.Fatal(err)
	}
	if count, err := consumer.ProcessOnce(ctx); err == nil || count != 0 {
		t.Fatalf("first attempt count=%d err=%v", count, err)
	}

	projection.applyErr = nil
	if count, err := consumer.ProcessOnce(ctx); err != nil || count != 1 {
		t.Fatalf("recovery attempt count=%d err=%v", count, err)
	}
	if len(projection.events) != 2 || len(projection.cleared) != 1 {
		t.Fatalf(
			"recovery projection calls=%d clear calls=%d",
			len(projection.events),
			len(projection.cleared),
		)
	}
}

func TestUserAccountClosedConsumerHealthRedactsFailureDetails(t *testing.T) {
	ctx := t.Context()
	client := rtredis.NewMemoryClient()
	projection := &userAccountClosedProjectionSpy{}
	consumer := newUserAccountClosedTestConsumer(t, client, projection, 3)
	if count, err := consumer.ProcessOnce(ctx); err != nil || count != 0 {
		t.Fatalf("prime consumer health count=%d err=%v", count, err)
	}
	projection.applyErr = errors.New(
		"account=circle-account-secret persona=circle-persona-secret token=circle-token-secret",
	)
	if _, err := client.XAdd(
		ctx,
		UserAccountEventStream,
		userAccountClosedValues("event-health-redaction", "circle-account-secret", 2),
	); err != nil {
		t.Fatal(err)
	}
	if _, err := consumer.ProcessOnce(ctx); err == nil {
		t.Fatal("failure required to exercise health redaction")
	}
	healthErr := consumer.Healthy(time.Second)
	if healthErr == nil {
		t.Fatal("health must report the failed scan")
	}
	for _, secret := range []string{
		"circle-account-secret",
		"circle-persona-secret",
		"circle-token-secret",
	} {
		if strings.Contains(healthErr.Error(), secret) {
			t.Fatalf("health leaked %q: %v", secret, healthErr)
		}
	}
}

func TestUserAccountClosedConsumerDeadLettersAfterBoundedRetriesWithoutPII(
	t *testing.T,
) {
	ctx := t.Context()
	redisSpy := &userAccountClosedRedisSpy{
		Client: rtredis.NewMemoryClient(),
	}
	projection := &userAccountClosedProjectionSpy{
		applyErr: application.ErrUserAccountClosedEventConflict,
	}
	var logs bytes.Buffer
	consumer, err := NewUserAccountClosedConsumerWithConfig(
		support.NewRedisMessageTransport(t, redisSpy),
		projection,
		projection,
		"local-contract",
		slog.New(slog.NewJSONHandler(&logs, nil)),
		UserAccountClosedConsumerConfig{
			BatchSize: 10, MaxAttempts: 3, MinIdle: 0,
			ReadBlock: 0, PollInterval: time.Millisecond,
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	values := userAccountClosedValues("event-failed", "account-secret", 4)
	sourceStreamID, err := redisSpy.XAdd(
		ctx,
		UserAccountEventStream,
		values,
	)
	if err != nil {
		t.Fatal(err)
	}

	for attempt := int64(1); attempt <= 3; attempt++ {
		count, err := consumer.ProcessOnce(ctx)
		if attempt < 3 && err == nil {
			t.Fatalf("attempt %d must remain pending", attempt)
		}
		if attempt == 3 && (err != nil || count != 1) {
			t.Fatalf(
				"dead-letter attempt count=%d err=%v",
				count,
				err,
			)
		}
		if attempt == 1 {
			if err := consumer.RecoverDeadLetter(ctx, sourceStreamID); err != nil {
				t.Fatalf("non-terminal recovery must be an idempotent no-op: %v", err)
			}
		}
	}
	if err := redisSpy.XGroupCreateMkStream(
		ctx,
		UserAccountClosedDLQ,
		"ops",
		"0",
	); err != nil {
		t.Fatal(err)
	}
	dlq, err := redisSpy.XReadGroup(
		ctx,
		"ops",
		"reader",
		map[string]string{UserAccountClosedDLQ: ">"},
		10,
		0,
	)
	if err != nil || len(dlq) != 1 {
		t.Fatalf("DLQ messages=%d err=%v", len(dlq), err)
	}
	for key, value := range dlq[0].Values {
		if strings.Contains(value, "account-secret") ||
			strings.Contains(value, "persona-a") ||
			strings.Contains(value, "persona-b") {
			t.Fatalf("DLQ leaked PII in %s", key)
		}
	}
	for _, required := range []string{
		"deadLetterId",
		"eventIdDigest",
		"accountIdDigest",
		"payloadDigest",
		"errorDigest",
	} {
		if dlq[0].Values[required] == "" {
			t.Fatalf("DLQ field %s is missing: %#v", required, dlq[0].Values)
		}
	}
	if dlq[0].Values["eventId"] != "" ||
		dlq[0].Values["accountId"] != "" ||
		dlq[0].Values["payload"] != "" {
		t.Fatalf("DLQ retained raw event identity: %#v", dlq[0].Values)
	}
	if !projection.dead[sourceStreamID] {
		t.Fatalf("terminal failure marker missing: %#v", projection.dead)
	}
	pending, _, claimErr := redisSpy.XAutoClaim(
		ctx,
		UserAccountEventStream,
		"circle-service-user-account-closed",
		"closure-pending-inspector",
		0,
		"0-0",
		10,
	)
	if claimErr != nil || len(pending) != 1 {
		t.Fatalf(
			"terminal DLQ must retain source PEL: pending=%+v err=%v",
			pending,
			claimErr,
		)
	}
	if err := consumer.RecoverDeadLetter(ctx, pending[0].ID); err != nil {
		t.Fatalf("release terminal source PEL: %v", err)
	}
	if projection.dead[pending[0].ID] {
		t.Fatal("recovery must clear terminal failure marker")
	}
	if strings.Contains(logs.String(), "account-secret") ||
		strings.Contains(logs.String(), "persona-a") ||
		strings.Contains(logs.String(), "persona-b") ||
		strings.Contains(logs.String(), "event-failed") {
		t.Fatalf("consumer log leaked event PII: %s", logs.String())
	}
}

func TestUserAccountClosedConsumerAcknowledgesUnrelatedSharedStreamEvent(
	t *testing.T,
) {
	ctx := t.Context()
	client := rtredis.NewMemoryClient()
	projection := &userAccountClosedProjectionSpy{}
	consumer := newUserAccountClosedTestConsumer(t, client, projection, 3)
	values := userAccountClosedValues("event-other", "account-other", 1)
	values["eventName"] = "UserAccountReactivated"
	if _, err := client.XAdd(ctx, UserAccountEventStream, values); err != nil {
		t.Fatal(err)
	}
	if count, err := consumer.ProcessOnce(ctx); err != nil || count != 1 {
		t.Fatalf("ignore ProcessOnce count=%d err=%v", count, err)
	}
	if len(projection.events) != 0 {
		t.Fatalf("unrelated event reached projection: %#v", projection.events)
	}
}

func newUserAccountClosedTestConsumer(
	t *testing.T,
	client rtredis.Client,
	projection *userAccountClosedProjectionSpy,
	maxAttempts int64,
) *UserAccountClosedConsumer {
	t.Helper()
	consumer, err := NewUserAccountClosedConsumerWithConfig(
		support.NewRedisMessageTransport(t, client),
		projection,
		projection,
		"local-contract",
		nil,
		UserAccountClosedConsumerConfig{
			BatchSize:    10,
			MaxAttempts:  maxAttempts,
			MinIdle:      0,
			ReadBlock:    0,
			PollInterval: time.Millisecond,
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	return consumer
}

func userAccountClosedValues(
	eventID string,
	accountID string,
	version int64,
) map[string]string {
	occurredAt := time.Date(2026, 7, 20, 8, 0, 0, 0, time.UTC)
	return map[string]string{
		"eventId":        eventID,
		"eventName":      application.UserAccountClosedEventName,
		"accountId":      accountID,
		"accountVersion": strconv.FormatInt(version, 10),
		"payload": `{"userId":"` + accountID +
			`","personaIds":["persona-b","persona-a","persona-b"],` +
			`"accountState":"closed","updatedAt":"` +
			occurredAt.Format(time.RFC3339Nano) + `"}`,
		"occurredAt": occurredAt.Format(time.RFC3339Nano),
	}
}
