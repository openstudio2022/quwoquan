package application

import (
	"context"
	"reflect"
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
	if facade == nil || isNilReadinessPort(facade.provider) || isNilReadinessPort(facade.relay) {
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

func isNilReadinessPort(value any) bool {
	if value == nil {
		return true
	}
	reflected := reflect.ValueOf(value)
	switch reflected.Kind() {
	case reflect.Chan, reflect.Func, reflect.Interface, reflect.Map, reflect.Pointer, reflect.Slice:
		return reflected.IsNil()
	default:
		return false
	}
}
