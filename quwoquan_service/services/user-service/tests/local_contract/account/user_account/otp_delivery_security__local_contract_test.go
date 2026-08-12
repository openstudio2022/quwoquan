package local_contract

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"regexp"
	"strings"
	"testing"

	runtimeerrors "quwoquan_service/runtime/errors"
	"quwoquan_service/runtime/otpseal"
	challengeapp "quwoquan_service/services/user-service/internal/account/authentication_challenge/application"
	challengemodel "quwoquan_service/services/user-service/internal/account/authentication_challenge/domain/model"
	accountorchestration "quwoquan_service/services/user-service/internal/account/user_account/application/account_orchestration"
)

// spec_ref: four-environment-commercial-login-maturity/spec.md#GWT-009

type otpRateLimitProbe struct {
	phones []string
	err    error
}

func (probe *otpRateLimitProbe) AllowSend(
	_ context.Context,
	phone string,
	_ string,
	_ string,
) (accountorchestration.OtpSendAdmission, error) {
	probe.phones = append(probe.phones, phone)
	return accountorchestration.OtpSendAdmission{
		Allowed:           probe.err == nil,
		RetryAfterSeconds: 60,
	}, probe.err
}

type authenticationChallengeProbe struct {
	creates []challengeapp.CreateChallengeCommand
	cancels []challengeapp.CancelChallengeCommand
	reports []challengeapp.ReportDeliveryResultCommand
}

func (probe *authenticationChallengeProbe) CreateChallenge(
	_ context.Context,
	command challengeapp.CreateChallengeCommand,
) (challengeapp.ChallengeCommandResult, error) {
	probe.creates = append(probe.creates, command)
	return challengeapp.ChallengeCommandResult{
		Challenge: challengemodel.Snapshot{
			ID:                command.ID,
			ExpiresAt:         command.ExpiresAt,
			DeliveryRequestID: command.DeliveryRequestID,
			DeliveryStatus:    command.DeliveryStatus,
		},
	}, nil
}

func (probe *authenticationChallengeProbe) ReportDeliveryResult(
	_ context.Context,
	command challengeapp.ReportDeliveryResultCommand,
) (challengeapp.ChallengeCommandResult, error) {
	probe.reports = append(probe.reports, command)
	return challengeapp.ChallengeCommandResult{}, nil
}

func (probe *authenticationChallengeProbe) VerifyChallenge(
	_ context.Context,
	_ challengeapp.VerifyChallengeCommand,
) (challengeapp.ChallengeCommandResult, error) {
	return challengeapp.ChallengeCommandResult{}, errors.New("unexpected verification")
}

func (probe *authenticationChallengeProbe) CancelChallenge(
	_ context.Context,
	command challengeapp.CancelChallengeCommand,
) (challengeapp.ChallengeCommandResult, error) {
	probe.cancels = append(probe.cancels, command)
	return challengeapp.ChallengeCommandResult{}, nil
}

type otpSealerProbe struct {
	secrets  []otpseal.Secret
	bindings []otpseal.Binding
}

func (probe *otpSealerProbe) Seal(
	secret otpseal.Secret,
	binding otpseal.Binding,
) (string, error) {
	probe.secrets = append(probe.secrets, secret)
	probe.bindings = append(probe.bindings, binding)
	return "otpref.test.opaque", nil
}

type externalInteractionProbe struct {
	requests []accountorchestration.SMSOTPDispatchRequest
	err      error
}

func (probe *externalInteractionProbe) SubmitSMSOTP(
	_ context.Context,
	request accountorchestration.SMSOTPDispatchRequest,
) (accountorchestration.ExternalInteractionAccepted, error) {
	probe.requests = append(probe.requests, request)
	if probe.err != nil {
		return accountorchestration.ExternalInteractionAccepted{}, probe.err
	}
	return accountorchestration.ExternalInteractionAccepted{
		RequestID: request.RequestID,
		Status:    "queued",
	}, nil
}

func TestOTPDeliveryPersistsOnlyIrreversibleReferenceAndSealedTransport(t *testing.T) {
	const (
		phone = "+8613800000000"
		code  = "482731"
	)
	rateLimit := &otpRateLimitProbe{}
	challenges := &authenticationChallengeProbe{}
	sealer := &otpSealerProbe{}
	external := &externalInteractionProbe{}
	service := accountorchestration.NewAuthService(
		nil,
		nil,
		nil,
		nil,
		nil,
		accountorchestration.WithOtpCodeStore(rateLimit),
		accountorchestration.WithAuthenticationChallenges(challenges),
		accountorchestration.WithOTPCodeGenerator(func() (string, error) {
			return code, nil
		}),
		accountorchestration.WithOTPCodeSealer(sealer),
		accountorchestration.WithExternalInteractionClient(external),
	)

	result, err := service.SendOtp(
		context.Background(),
		phone,
		"device-1",
		"ios",
		"1.0.0",
		"phone_login",
		"",
		"otp-delivery-security-key-000001",
	)
	if err != nil {
		t.Fatalf("send OTP: %v", err)
	}
	if len(rateLimit.phones) != 1 || rateLimit.phones[0] != phone {
		t.Fatalf("rate limit did not receive canonical E.164 phone: %#v", rateLimit.phones)
	}
	if len(challenges.creates) != 1 {
		t.Fatalf("challenge create count=%d", len(challenges.creates))
	}
	persisted := challenges.creates[0]
	if persisted.SecretRef == "" ||
		strings.Contains(persisted.SecretRef, code) ||
		strings.Contains(persisted.SecretRef, phone) {
		t.Fatalf("challenge secret reference is empty or reversible: %#v", persisted)
	}
	if len(sealer.secrets) != 1 ||
		sealer.secrets[0].Phone != phone ||
		sealer.secrets[0].Code != code {
		t.Fatalf("sealer did not receive the transient OTP secret: %#v", sealer.secrets)
	}
	if len(external.requests) != 1 {
		t.Fatalf("external request count=%d", len(external.requests))
	}
	dispatched := external.requests[0]
	if dispatched.CodeRef != "otpref.test.opaque" ||
		strings.Contains(fmt.Sprintf("%#v", dispatched), code) ||
		strings.Contains(fmt.Sprintf("%#v", dispatched), phone) {
		t.Fatalf("external request did not keep the OTP sealed: %#v", dispatched)
	}
	response, err := json.Marshal(result)
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(string(response), code) || strings.Contains(string(response), phone) {
		t.Fatalf("OTP response leaked a credential: %s", response)
	}
}

func TestOTPDeliveryRejectsNonE164BeforeStateOrProviderCalls(t *testing.T) {
	rateLimit := &otpRateLimitProbe{}
	challenges := &authenticationChallengeProbe{}
	external := &externalInteractionProbe{}
	service := accountorchestration.NewAuthService(
		nil,
		nil,
		nil,
		nil,
		nil,
		accountorchestration.WithOtpCodeStore(rateLimit),
		accountorchestration.WithAuthenticationChallenges(challenges),
		accountorchestration.WithOTPCodeSealer(&otpSealerProbe{}),
		accountorchestration.WithExternalInteractionClient(external),
	)

	for _, phone := range []string{"13800000000", "+0123456789", "+86138000000000000"} {
		if _, err := service.SendOtp(
			context.Background(),
			phone,
			"device-1",
			"ios",
			"1.0.0",
			"phone_login",
			"",
			"otp-invalid-phone-key-00000001",
		); err == nil {
			t.Fatalf("non-E.164 phone %q was accepted", phone)
		}
	}
	if len(rateLimit.phones) != 0 || len(challenges.creates) != 0 ||
		len(external.requests) != 0 {
		t.Fatalf(
			"invalid phones reached a side effect: rate=%d challenge=%d provider=%d",
			len(rateLimit.phones),
			len(challenges.creates),
			len(external.requests),
		)
	}
}

func TestOTPProviderFailuresAreRedactedAndKeepChallengeRecoverable(t *testing.T) {
	const providerSecret = "provider body phone=+8613800000000 otp=482731 token=secret"
	for _, providerFailure := range []error{
		errors.New(providerSecret),
		context.DeadlineExceeded,
	} {
		challenges := &authenticationChallengeProbe{}
		service := accountorchestration.NewAuthService(
			nil,
			nil,
			nil,
			nil,
			nil,
			accountorchestration.WithOtpCodeStore(&otpRateLimitProbe{}),
			accountorchestration.WithAuthenticationChallenges(challenges),
			accountorchestration.WithOTPCodeGenerator(func() (string, error) {
				return "482731", nil
			}),
			accountorchestration.WithOTPCodeSealer(&otpSealerProbe{}),
			accountorchestration.WithExternalInteractionClient(
				&externalInteractionProbe{err: providerFailure},
			),
		)
		_, err := service.SendOtp(
			context.Background(),
			"+8613800000000",
			"device-1",
			"ios",
			"1.0.0",
			"phone_login",
			"",
			"otp-provider-failure-key-000001",
		)
		if err == nil {
			t.Fatalf("provider failure %v was accepted", providerFailure)
		}
		var appError *runtimeerrors.AppError
		if !errors.As(err, &appError) ||
			appError.Code.String() != "USER.AUTH.otp_provider_failed" {
			t.Fatalf("provider failure mapping=%T %v", err, err)
		}
		if strings.Contains(err.Error(), providerSecret) ||
			strings.Contains(err.Error(), "482731") ||
			strings.Contains(err.Error(), "+8613800000000") {
			t.Fatalf("provider failure leaked sensitive context: %v", err)
		}
		if len(challenges.cancels) != 0 {
			t.Fatalf("uncertain submit must not cancel challenge: %#v", challenges.cancels)
		}
	}
}

func TestOTPExplicitLocalDeliveryFailureReturnsRecoverableFailedState(t *testing.T) {
	challenges := &authenticationChallengeProbe{}
	service := accountorchestration.NewAuthService(
		nil,
		nil,
		nil,
		nil,
		nil,
		accountorchestration.WithOtpCodeStore(&otpRateLimitProbe{}),
		accountorchestration.WithAuthenticationChallenges(challenges),
		accountorchestration.WithOTPCodeGenerator(func() (string, error) {
			return "482731", nil
		}),
		accountorchestration.WithOTPCodeSealer(&otpSealerProbe{}),
	)

	result, err := service.SendOtp(
		context.Background(),
		"+8613800000000",
		"device-1",
		"ios",
		"1.0.0",
		"phone_login",
		"",
		"otp-explicit-failure-key-000001",
	)
	if err != nil {
		t.Fatalf("explicit failure should be a typed delivery state: %v", err)
	}
	if result.DeliveryStatus != string(challengemodel.DeliveryStatusFailed) ||
		result.RetryAfterSeconds != 60 {
		t.Fatalf("unexpected explicit failure result: %+v", result)
	}
	if len(challenges.reports) != 1 ||
		challenges.reports[0].Status != challengemodel.DeliveryStatusFailed {
		t.Fatalf("failed challenge was not projected: %#v", challenges.reports)
	}
}

func TestDefaultOTPGeneratorProducesSixDigitNonConstantCodes(t *testing.T) {
	challenges := &authenticationChallengeProbe{}
	sealer := &otpSealerProbe{}
	service := accountorchestration.NewAuthService(
		nil,
		nil,
		nil,
		nil,
		nil,
		accountorchestration.WithOtpCodeStore(&otpRateLimitProbe{}),
		accountorchestration.WithAuthenticationChallenges(challenges),
		accountorchestration.WithOTPCodeSealer(sealer),
		accountorchestration.WithExternalInteractionClient(&externalInteractionProbe{}),
	)

	for index := 0; index < 32; index++ {
		phone := fmt.Sprintf("+86138%08d", index)
		if _, err := service.SendOtp(
			context.Background(),
			phone,
			"device-1",
			"ios",
			"1.0.0",
			"phone_login",
			"",
			fmt.Sprintf("otp-random-code-key-%08d", index),
		); err != nil {
			t.Fatalf("send random OTP %d: %v", index, err)
		}
	}
	pattern := regexp.MustCompile(`^[0-9]{6}$`)
	unique := map[string]struct{}{}
	for _, secret := range sealer.secrets {
		if !pattern.MatchString(secret.Code) {
			t.Fatalf("OTP is not six digits: %q", secret.Code)
		}
		unique[secret.Code] = struct{}{}
	}
	if len(sealer.secrets) != 32 || len(unique) < 2 {
		t.Fatalf(
			"default OTP generator is absent or constant: samples=%d unique=%d",
			len(sealer.secrets),
			len(unique),
		)
	}
}
