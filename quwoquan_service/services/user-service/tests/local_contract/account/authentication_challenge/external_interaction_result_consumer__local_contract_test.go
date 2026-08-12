// spec_ref: specs/feature-tree/user-identity-profile-relationship/onboarding-and-identity-entry/four-environment-commercial-login-maturity/spec.md#gwt-011.t1
package local_contract

import (
	"context"
	"testing"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	"quwoquan_service/runtime/reliabletask"
	deliverystream "quwoquan_service/services/user-service/internal/account/authentication_challenge/adapters/inbound/stream"
	challengeapp "quwoquan_service/services/user-service/internal/account/authentication_challenge/application"
	challengemodel "quwoquan_service/services/user-service/internal/account/authentication_challenge/domain/model"
)

const deliveryResultStream = "events.integration.external_interaction"

type deliveryTransportProbe struct {
	deliverystream.DurableMessageTransport
	fresh []runtimemessaging.StreamDelivery
	acked []string
}

func (probe *deliveryTransportProbe) EnsureDurableConsumerGroup(
	context.Context,
	string,
	string,
	string,
) error {
	return nil
}

func (probe *deliveryTransportProbe) ReclaimDurable(
	context.Context,
	string,
	string,
	string,
	time.Duration,
	string,
	int64,
) ([]runtimemessaging.StreamDelivery, string, error) {
	return nil, "0-0", nil
}

func (probe *deliveryTransportProbe) ReadDurable(
	context.Context,
	runtimemessaging.StreamReadRequest,
) ([]runtimemessaging.StreamDelivery, error) {
	return probe.fresh, nil
}

func (probe *deliveryTransportProbe) AckDurable(
	_ context.Context,
	_ string,
	_ string,
	ids ...string,
) error {
	probe.acked = append(probe.acked, ids...)
	return nil
}

type deliveryCommandProbe struct {
	challengeapp.CommandFacet
	reports []challengeapp.ReportDeliveryResultCommand
	err     error
}

func (probe *deliveryCommandProbe) ReportDeliveryResult(
	_ context.Context,
	command challengeapp.ReportDeliveryResultCommand,
) (challengeapp.ChallengeCommandResult, error) {
	probe.reports = append(probe.reports, command)
	return challengeapp.ChallengeCommandResult{}, probe.err
}

func TestDeliveryResultConsumerProjectsBeforeAckAndIgnoresOtherOperations(t *testing.T) {
	t.Parallel()
	now := time.Now().UTC()
	transport := &deliveryTransportProbe{
		fresh: []runtimemessaging.StreamDelivery{
			deliveryMessage("1-0", "event-delivered", "otp_req_123", reliabletask.ExternalInteractionStatusDelivered, now),
			{
				Stream: deliveryResultStream,
				ID:     "2-0",
				Fields: []runtimemessaging.DurableField{
					{Name: "eventType", Value: "ExternalInteractionResultReported"},
					{Name: "operation", Value: "email.delivery"},
				},
			},
		},
	}
	commands := &deliveryCommandProbe{}
	consumer, err := deliverystream.NewAuthenticationChallengeDeliveryResultConsumer(
		transport,
		commands,
		"test-consumer",
		nil,
	)
	if err != nil {
		t.Fatal(err)
	}

	processed, err := consumer.ProcessOnce(context.Background())
	if err != nil {
		t.Fatalf("ProcessOnce() error = %v", err)
	}
	if processed != 2 || len(commands.reports) != 1 {
		t.Fatalf("processed=%d reports=%+v", processed, commands.reports)
	}
	report := commands.reports[0]
	if report.EventID != "event-delivered" || report.RequestID != "otp_req_123" ||
		report.Status != challengemodel.DeliveryStatusDelivered ||
		!report.OccurredAt.Equal(now) {
		t.Fatalf("unexpected report: %+v", report)
	}
	if len(transport.acked) != 2 || transport.acked[0] != "1-0" ||
		transport.acked[1] != "2-0" {
		t.Fatalf("unexpected ACKs: %v", transport.acked)
	}
}

func TestDeliveryResultConsumerDoesNotAckProjectionFailure(t *testing.T) {
	t.Parallel()
	transport := &deliveryTransportProbe{
		fresh: []runtimemessaging.StreamDelivery{
			deliveryMessage("1-0", "event-failed", "otp_req_456", reliabletask.ExternalInteractionStatusDeadLetter, time.Now().UTC()),
		},
	}
	commands := &deliveryCommandProbe{err: context.DeadlineExceeded}
	consumer, err := deliverystream.NewAuthenticationChallengeDeliveryResultConsumer(
		transport,
		commands,
		"test-consumer",
		nil,
	)
	if err != nil {
		t.Fatal(err)
	}

	processed, err := consumer.ProcessOnce(context.Background())
	if err == nil || processed != 0 {
		t.Fatalf("ProcessOnce() = %d, %v", processed, err)
	}
	if len(transport.acked) != 0 {
		t.Fatalf("projection failure was ACKed: %v", transport.acked)
	}
}

func deliveryMessage(
	id string,
	eventID string,
	requestID string,
	status string,
	occurredAt time.Time,
) runtimemessaging.StreamDelivery {
	return runtimemessaging.StreamDelivery{
		Stream: deliveryResultStream,
		ID:     id,
		Fields: []runtimemessaging.DurableField{
			{Name: "eventType", Value: "ExternalInteractionResultReported"},
			{Name: "eventId", Value: eventID},
			{Name: "operation", Value: reliabletask.ExternalInteractionOperationSmsOTP},
			{Name: "requestId", Value: requestID},
			{Name: "status", Value: status},
			{Name: "occurredAt", Value: occurredAt.Format(time.RFC3339Nano)},
		},
	}
}
