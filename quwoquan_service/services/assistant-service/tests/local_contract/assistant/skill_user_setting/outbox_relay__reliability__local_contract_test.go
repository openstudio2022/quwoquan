// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/skill-user-lifecycle/spec.md#gwt-001
package local_contract

import (
	"context"
	"errors"
	"strings"
	"testing"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	settingapp "quwoquan_service/services/assistant-service/internal/assistant/skill_user_setting/application"
	settingmodel "quwoquan_service/services/assistant-service/internal/assistant/skill_user_setting/domain/model"
	settingports "quwoquan_service/services/assistant-service/internal/assistant/skill_user_setting/domain/ports"
	settingmessaging "quwoquan_service/services/assistant-service/internal/assistant/skill_user_setting/infrastructure/messaging"
)

type settingOutboxFixture struct {
	event      settingports.OutboxEvent
	available  bool
	marked     int
	retried    int
	claimOwner string
}

func (fixture *settingOutboxFixture) ClaimPendingOutbox(
	_ context.Context, owner string, _ time.Time, _ time.Duration,
) (settingports.OutboxEvent, bool, error) {
	fixture.claimOwner = owner
	return fixture.event, fixture.available, nil
}

func (fixture *settingOutboxFixture) MarkOutboxPublished(
	_ context.Context, _ string, owner string, _ time.Time,
) error {
	if owner != fixture.claimOwner {
		return settingports.ErrOutboxClaimLost
	}
	fixture.marked++
	fixture.available = false
	return nil
}

func (fixture *settingOutboxFixture) ScheduleOutboxRetry(
	_ context.Context, _ string, owner string, _ time.Time, _ string,
) error {
	if owner != fixture.claimOwner {
		return settingports.ErrOutboxClaimLost
	}
	fixture.retried++
	fixture.available = false
	return nil
}

type settingTransportFixture struct {
	fail      bool
	message   runtimemessaging.DurableMessage
	retention time.Duration
}

func (fixture *settingTransportFixture) AppendDurable(
	_ context.Context, message runtimemessaging.DurableMessage,
) (string, error) {
	if fixture.fail {
		return "", errors.New("transport unavailable")
	}
	fixture.message = message
	return "1-0", nil
}

func (fixture *settingTransportFixture) SetDurableRetention(
	_ context.Context, _ string, retention time.Duration,
) error {
	fixture.retention = retention
	return nil
}

func TestSettingRelayExcludesRawConfigurationAndFailsClosed(t *testing.T) {
	now := time.Date(2026, 8, 5, 11, 0, 0, 0, time.UTC)
	event := settingports.OutboxEvent{
		EventID: "setting-1:1", EventType: settingmodel.EventChanged,
		AggregateID: "setting-1", AggregateVersion: 1,
		Payload:    []byte(`{"id":"setting-1","accountId":"account-1","skillId":"weather","status":"enabled","configurationSchemaDigest":"sha256:ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad","memoryPolicy":"session","connectorConnectionRefs":[],"revision":1,"updatedAt":"2026-08-05T11:00:00Z"}`),
		OccurredAt: now, AttemptCount: 1,
	}
	outbox := &settingOutboxFixture{event: event, available: true}
	transport := &settingTransportFixture{fail: true}
	publisher, err := settingmessaging.NewEventPublisher(transport)
	if err != nil {
		t.Fatalf("NewEventPublisher() error = %v", err)
	}
	relay, err := settingapp.NewOutboxRelay(outbox, publisher)
	if err != nil {
		t.Fatalf("NewOutboxRelay() error = %v", err)
	}
	if count, err := relay.Drain(context.Background(), 1); err == nil || count != 0 {
		t.Fatalf("failed Drain() = (%d, %v), want (0, error)", count, err)
	}
	if outbox.marked != 0 || outbox.retried != 1 || relay.Healthy(context.Background(), time.Minute) == nil {
		t.Fatalf("failed delivery advanced or remained healthy: marked=%d retried=%d", outbox.marked, outbox.retried)
	}
	outbox.available = true
	transport.fail = false
	if count, err := relay.Drain(context.Background(), 1); err != nil || count != 1 {
		t.Fatalf("recovered Drain() = (%d, %v), want (1, nil)", count, err)
	}
	fields := runtimemessaging.DurableFieldMap(transport.message.Fields)
	if outbox.marked != 1 || transport.message.Stream != settingmessaging.SkillUserSettingEventStream ||
		fields["aggregateId"] != event.AggregateID || transport.retention <= 0 {
		t.Fatalf("setting delivery mismatch: marked=%d stream=%q fields=%v retention=%s", outbox.marked, transport.message.Stream, fields, transport.retention)
	}
	if strings.Contains(fields["payload"], "configurationData") || strings.Contains(fields["payload"], "secret") {
		t.Fatalf("raw setting configuration leaked: %q", fields["payload"])
	}
	if err := relay.Healthy(context.Background(), time.Minute); err != nil {
		t.Fatalf("Healthy() after recovery error = %v", err)
	}
}
