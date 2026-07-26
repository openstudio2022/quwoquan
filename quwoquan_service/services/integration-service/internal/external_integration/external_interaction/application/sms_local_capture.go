package application

import (
	"context"
	"time"

	"quwoquan_service/runtime/reliabletask"
)

// LocalCaptureSMSProvider is the non-prod SmsDeliveryPort substitute.
// It accepts OTP send requests without contacting a vendor.
type LocalCaptureSMSProvider struct{}

func (LocalCaptureSMSProvider) Send(
	_ context.Context,
	request reliabletask.ExternalInteractionRequest,
	_ reliabletask.ReliableAsyncTask,
) (reliabletask.ExternalInteractionResult, error) {
	return reliabletask.ExternalInteractionResult{
		RequestID:         request.RequestID,
		Operation:         request.Operation,
		Status:            reliabletask.ExternalInteractionStatusSentUnconfirmed,
		Provider:          "ext.sms.local_capture",
		ProviderRequestID: "local-capture-" + request.RequestID,
		OccurredAt:        time.Now().UTC(),
	}, nil
}
