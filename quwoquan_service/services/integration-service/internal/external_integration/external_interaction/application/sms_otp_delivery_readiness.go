package application

import (
	"context"
	"time"
)

const smsOtpReadinessRetryAfterSeconds = 5

type SmsOtpProviderReadinessPort interface {
	CheckSMSOTPProviderReadiness(context.Context) error
}

type SmsOtpResultRelayReadinessPort interface {
	CheckSMSOTPResultRelayReadiness(context.Context) error
}

type SmsOtpDeliveryReadiness struct {
	Availability      string `json:"availability"`
	RetryAfterSeconds int    `json:"retryAfterSeconds"`
}

type SmsOtpDeliveryReadinessQueryFacade struct {
	provider SmsOtpProviderReadinessPort
	relay    SmsOtpResultRelayReadinessPort
}

func NewSmsOtpDeliveryReadinessQueryFacade(
	provider SmsOtpProviderReadinessPort,
	relay SmsOtpResultRelayReadinessPort,
) *SmsOtpDeliveryReadinessQueryFacade {
	return &SmsOtpDeliveryReadinessQueryFacade{provider: provider, relay: relay}
}

func (facade *SmsOtpDeliveryReadinessQueryFacade) GetSmsOtpDeliveryReadiness(
	ctx context.Context,
) SmsOtpDeliveryReadiness {
	if facade == nil || isNilDependency(facade.provider) || isNilDependency(facade.relay) {
		return unavailableSmsOtpDeliveryReadiness()
	}
	probeCtx, cancel := context.WithTimeout(ctx, 700*time.Millisecond)
	defer cancel()
	if err := facade.provider.CheckSMSOTPProviderReadiness(probeCtx); err != nil {
		return unavailableSmsOtpDeliveryReadiness()
	}
	if err := facade.relay.CheckSMSOTPResultRelayReadiness(probeCtx); err != nil {
		return unavailableSmsOtpDeliveryReadiness()
	}
	return SmsOtpDeliveryReadiness{Availability: "ready"}
}

func unavailableSmsOtpDeliveryReadiness() SmsOtpDeliveryReadiness {
	return SmsOtpDeliveryReadiness{
		Availability:      "temporarily_unavailable",
		RetryAfterSeconds: smsOtpReadinessRetryAfterSeconds,
	}
}
