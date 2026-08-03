package main

import (
	"crypto/tls"
	"crypto/x509"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"strings"
	"time"

	serviceclients "quwoquan_service/generated/serviceclients"
	rtauth "quwoquan_service/runtime/auth"
	runtimeconfig "quwoquan_service/runtime/config"
	rthttp "quwoquan_service/runtime/http"
	robs "quwoquan_service/runtime/observability"
	"quwoquan_service/runtime/otpseal"
	"quwoquan_service/runtime/reliabletask"
	externalprovider "quwoquan_service/services/integration-service/internal/external_integration/external_interaction/infrastructure/provider"
	integrationconfig "quwoquan_service/services/integration-service/internal/external_integration/external_interaction/infrastructure/runtimeconfig"
	pushruntime "quwoquan_service/services/integration-service/internal/external_integration/push_delivery/adapters/inbound/runtime"
	pushapp "quwoquan_service/services/integration-service/internal/external_integration/push_delivery/application"
	pushprovider "quwoquan_service/services/integration-service/internal/external_integration/push_delivery/infrastructure/provider"
)

func newExternalObservedHTTPClient(
	cfg config,
	ioLogger *robs.IOAccessLogger,
	processLogger *robs.ProcessTraceLogger,
	exceptionLogger *robs.ExceptionLogger,
) (*http.Client, error) {
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
	if caFile := strings.TrimSpace(os.Getenv("INTEGRATION_SMS_SUBSTITUTE_CA_FILE")); caFile != "" {
		caPEM, err := os.ReadFile(caFile)
		if err != nil {
			return nil, fmt.Errorf("SMS Debug substitute CA is unreadable: %w", err)
		}
		roots, err := x509.SystemCertPool()
		if err != nil || roots == nil {
			roots = x509.NewCertPool()
		}
		if !roots.AppendCertsFromPEM(caPEM) {
			return nil, fmt.Errorf("SMS Debug substitute CA has no certificate")
		}
		baseTransport.TLSClientConfig = &tls.Config{
			MinVersion: tls.VersionTLS13,
			RootCAs:    roots,
		}
	}
	client := rthttp.NewObservedHTTPClient(
		pushprovider.RedactingRoundTripper{Base: baseTransport},
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
	return client, nil
}

func externalProviderLogEndpoint(request *http.Request) string {
	return externalprovider.ObservedEndpoint(request)
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
	var err error
	cfg, err = materializeReleaseExternalInteractionBindings(
		cfg,
		runtimeconfig.EnvRuntimeConfigProvider{},
	)
	if err != nil {
		return nil, nil, err
	}
	providers := map[string]reliabletask.ExternalProvider{}
	policies := map[string]reliabletask.ProviderPolicy{}
	smsCfg := cfg.Integration.ExternalInteraction.SMS
	if smsCfg.Enabled {
		timeout := time.Duration(smsCfg.TimeoutMs) * time.Millisecond
		canonicalProviderName := ""
		switch strings.TrimSpace(smsCfg.Provider) {
		case "ext.sms.aliyun":
			canonicalProviderName = "aliyun_sms"
		case "ext.sms.local_capture":
			canonicalProviderName = "local_capture_sms"
		default:
			return nil, nil, fmt.Errorf(
				"SMS adapter %s has no canonical provider mapping",
				smsCfg.Provider,
			)
		}
		smsProvider, err := externalprovider.NewHTTPExternalProvider(
			externalprovider.HTTPExternalProviderConfig{
				Name:              canonicalProviderName,
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
	if mode := strings.TrimSpace(pushCfg.Mode); mode == "local_recorder" {
		pushProvider, err := pushruntime.NewProvider(pushapp.LocalRecorderPushProvider{})
		if err != nil {
			return nil, nil, fmt.Errorf("local push delivery adapter init failed: %w", err)
		}
		providers[pushDispatchProviderName] = pushProvider
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
	endpointClient, err := pushprovider.NewUserPushEndpointClient(
		pushprovider.UserPushEndpointClientConfig{
			BaseURL:     pushCfg.UserServiceBaseURL,
			Credentials: userCredentials,
			Timeout:     pushTimeout,
		},
		client,
	)
	if err != nil {
		return nil, nil, fmt.Errorf("user push endpoint client init failed: %w", err)
	}
	apnsProvider, err := pushprovider.NewAPNsVoIPProvider(
		pushprovider.APNsVoIPConfig{
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
	fcmProvider, err := pushprovider.NewFCMProvider(
		pushprovider.FCMConfig{
			ServiceAccountFile: pushCfg.FCM.ServiceAccountFile,
			ProjectID:          pushCfg.FCM.ProjectID,
			Timeout:            pushTimeout,
		},
		client,
	)
	if err != nil {
		return nil, nil, fmt.Errorf("FCM provider init failed: %w", err)
	}
	pushProvider, err := pushapp.NewPushDispatchProvider(
		endpointClient,
		endpointClient,
		apnsProvider,
		fcmProvider,
		slog.Default(),
	)
	if err != nil {
		return nil, nil, fmt.Errorf("push dispatch provider init failed: %w", err)
	}
	runtimePushProvider, err := pushruntime.NewProvider(pushProvider)
	if err != nil {
		return nil, nil, fmt.Errorf("push delivery adapter init failed: %w", err)
	}
	providers[pushDispatchProviderName] = runtimePushProvider
	policies[reliabletask.ExternalInteractionOperationPush] = reliabletask.ProviderPolicy{
		Providers:   []string{pushDispatchProviderName},
		Timeout:     pushTimeout,
		RetryPolicy: reliabletask.DefaultRetryPolicy(),
	}
	return providers, policies, nil
}

func materializeReleaseExternalInteractionBindings(
	cfg config,
	configProvider runtimeconfig.RuntimeConfigProvider,
) (config, error) {
	return integrationconfig.MaterializeReleaseExternalInteractionBindings(cfg, configProvider)
}
