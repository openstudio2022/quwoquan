package main

import (
	"fmt"
	"log/slog"
	"net/http"
	"strings"
	"time"

	serviceclients "quwoquan_service/generated/serviceclients"
	rtauth "quwoquan_service/runtime/auth"
	rthttp "quwoquan_service/runtime/http"
	robs "quwoquan_service/runtime/observability"
	"quwoquan_service/runtime/otpseal"
	"quwoquan_service/runtime/reliabletask"
	"quwoquan_service/services/integration-service/internal/application"
	"quwoquan_service/services/integration-service/internal/infrastructure/provider"
)

func newExternalObservedHTTPClient(
	cfg config,
	ioLogger *robs.IOAccessLogger,
	processLogger *robs.ProcessTraceLogger,
	exceptionLogger *robs.ExceptionLogger,
) *http.Client {
	timeout := 2 * time.Second
	for _, providerCfg := range []externalProviderConfig{
		cfg.Integration.ExternalInteraction.SMS,
	} {
		if providerCfg.Enabled && time.Duration(providerCfg.TimeoutMs)*time.Millisecond > timeout {
			timeout = time.Duration(providerCfg.TimeoutMs) * time.Millisecond
		}
	}
	pushCfg := cfg.Integration.ExternalInteraction.Push
	if pushCfg.Enabled && time.Duration(pushCfg.TimeoutMs)*time.Millisecond > timeout {
		timeout = time.Duration(pushCfg.TimeoutMs) * time.Millisecond
	}
	factoryCfg := rthttp.DefaultHTTPClientFactoryConfig()
	factoryCfg.Timeout = timeout
	factoryCfg.MaxRetries = -1
	factoryCfg.RetryBackoff = -1
	factoryCfg.RetryOnCodes = map[int]struct{}{}
	logCfg := rthttp.HTTPClientMiddlewareConfig{
		Service:           "integration-service",
		Origin:            "cloud",
		Direction:         "outbound",
		SourceID:          "integration-service.external-provider",
		Src:               "integration-service",
		ServiceName:       "integration-service",
		ServiceInstanceID: "local",
		EndpointResolver:  externalProviderLogEndpoint,
	}
	baseTransport := http.DefaultTransport.(*http.Transport).Clone()
	baseTransport.ForceAttemptHTTP2 = true
	client := rthttp.NewObservedHTTPClient(
		provider.RedactingRoundTripper{Base: baseTransport},
		factoryCfg,
		logCfg,
		ioLogger,
		processLogger,
		exceptionLogger,
	)
	client.CheckRedirect = func(
		_ *http.Request,
		_ []*http.Request,
	) error {
		return http.ErrUseLastResponse
	}
	return client
}

func externalProviderLogEndpoint(request *http.Request) string {
	path := request.URL.Path
	switch {
	case strings.HasPrefix(path, "/3/device/"):
		return "/3/device/{token}"
	case matchesEndpointPathTemplate(
		path,
		serviceclients.UserPushEndpointSecretPathTemplate,
	):
		return serviceclients.UserPushEndpointSecretPathTemplate
	case matchesEndpointPathTemplate(
		path,
		serviceclients.UserPushEndpointInvalidatePathTemplate,
	):
		return serviceclients.UserPushEndpointInvalidatePathTemplate
	case strings.HasPrefix(path, "/v1/projects/") &&
		strings.HasSuffix(path, "/messages:send"):
		return "/v1/projects/{projectId}/messages:send"
	default:
		return path
	}
}

func matchesEndpointPathTemplate(path string, template string) bool {
	parts := strings.Split(template, "{endpointRef}")
	return len(parts) == 2 &&
		strings.HasPrefix(path, parts[0]) &&
		strings.HasSuffix(path, parts[1])
}

func buildExternalProviders(
	cfg config,
	client *http.Client,
	accessTokenConfig rtauth.TokenConfig,
	otpCodeSealer *otpseal.Sealer,
	otpCodeReferences otpseal.ReferenceStore,
) (
	map[string]reliabletask.ExternalProvider,
	map[string]reliabletask.ProviderPolicy,
	error,
) {
	providers := map[string]reliabletask.ExternalProvider{}
	policies := map[string]reliabletask.ProviderPolicy{}
	smsCfg := cfg.Integration.ExternalInteraction.SMS
	if smsCfg.Enabled {
		timeout := time.Duration(smsCfg.TimeoutMs) * time.Millisecond
		smsProvider, err := provider.NewHTTPExternalProvider(
			provider.HTTPExternalProviderConfig{
				Name:              smsCfg.Provider,
				Operation:         reliabletask.ExternalInteractionOperationSmsOTP,
				Endpoint:          smsCfg.Endpoint,
				BearerToken:       smsCfg.Token,
				Timeout:           timeout,
				OTPCodeSealer:     otpCodeSealer,
				OTPCodeReferences: otpCodeReferences,
			},
			client,
		)
		if err != nil {
			return nil, nil, fmt.Errorf(
				"external provider init failed for %s: %w",
				reliabletask.ExternalInteractionOperationSmsOTP,
				err,
			)
		}
		providers[smsCfg.Provider] = smsProvider
		policies[reliabletask.ExternalInteractionOperationSmsOTP] = reliabletask.ProviderPolicy{
			Providers:   []string{smsCfg.Provider},
			Timeout:     timeout,
			RetryPolicy: reliabletask.DefaultRetryPolicy(),
		}
	}

	pushCfg := cfg.Integration.ExternalInteraction.Push
	if !pushCfg.Enabled {
		return providers, policies, nil
	}
	pushTimeout := time.Duration(pushCfg.TimeoutMs) * time.Millisecond
	const pushDispatchProviderName = "push_dispatch"
	if strings.TrimSpace(pushCfg.Mode) == "fake" {
		providers[pushDispatchProviderName] = application.AlphaFakePushProvider{}
		policies[reliabletask.ExternalInteractionOperationPush] = reliabletask.ProviderPolicy{
			Providers:   []string{pushDispatchProviderName},
			Timeout:     pushTimeout,
			RetryPolicy: reliabletask.DefaultRetryPolicy(),
		}
		return providers, policies, nil
	}

	userCredentials, err := rtauth.NewHS256ServiceAuthorizationProvider(
		accessTokenConfig,
		"integration-service",
		[]string{
			serviceclients.UserPushEndpointSecretScope,
			serviceclients.UserPushEndpointInvalidateScope,
		},
	)
	if err != nil {
		return nil, nil, fmt.Errorf("user push endpoint credentials invalid: %w", err)
	}
	endpointClient, err := provider.NewUserPushEndpointClient(
		provider.UserPushEndpointClientConfig{
			BaseURL:     pushCfg.UserServiceBaseURL,
			Credentials: userCredentials,
			Timeout:     pushTimeout,
		},
		client,
	)
	if err != nil {
		return nil, nil, fmt.Errorf("user push endpoint client init failed: %w", err)
	}
	apnsProvider, err := provider.NewAPNsVoIPProvider(
		provider.APNsVoIPConfig{
			Environment: pushCfg.APNs.Environment,
			KeyFile:     pushCfg.APNs.KeyFile,
			KeyID:       pushCfg.APNs.KeyID,
			TeamID:      pushCfg.APNs.TeamID,
			Topic:       pushCfg.APNs.Topic,
			Timeout:     pushTimeout,
		},
		client,
	)
	if err != nil {
		return nil, nil, fmt.Errorf("APNs VoIP provider init failed: %w", err)
	}
	fcmProvider, err := provider.NewFCMProvider(
		provider.FCMConfig{
			ServiceAccountFile: pushCfg.FCM.ServiceAccountFile,
			ProjectID:          pushCfg.FCM.ProjectID,
			Timeout:            pushTimeout,
		},
		client,
	)
	if err != nil {
		return nil, nil, fmt.Errorf("FCM provider init failed: %w", err)
	}
	pushProvider, err := application.NewPushDispatchProvider(
		endpointClient,
		endpointClient,
		apnsProvider,
		fcmProvider,
		slog.Default(),
	)
	if err != nil {
		return nil, nil, fmt.Errorf("push dispatch provider init failed: %w", err)
	}
	providers[pushDispatchProviderName] = pushProvider
	policies[reliabletask.ExternalInteractionOperationPush] = reliabletask.ProviderPolicy{
		Providers:   []string{pushDispatchProviderName},
		Timeout:     pushTimeout,
		RetryPolicy: reliabletask.DefaultRetryPolicy(),
	}
	return providers, policies, nil
}
