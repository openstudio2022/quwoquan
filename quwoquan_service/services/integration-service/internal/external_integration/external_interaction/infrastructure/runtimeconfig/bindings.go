package runtimeconfig

import (
	"errors"
	"fmt"

	platformconfig "quwoquan_service/runtime/config"
	"quwoquan_service/services/integration-service/internal/external_integration/external_interaction/infrastructure/providerbinding"
)

// MaterializeReleaseExternalInteractionBindings resolves the current release
// bindings into one runtime configuration. A capability explicitly blocked by
// policy is disabled; malformed or incomplete bindings fail closed.
func MaterializeReleaseExternalInteractionBindings(
	cfg Config,
	configProvider platformconfig.RuntimeConfigProvider,
) (Config, error) {
	smsBinding, err := providerbinding.ResolveSMSBinding(cfg.Environment, configProvider)
	switch {
	case err == nil:
		smsEndpoint, ok := smsBinding.Endpoint("endpoint")
		if !ok {
			return Config{}, fmt.Errorf("SMS provider binding has no endpoint")
		}
		smsToken, ok := smsBinding.Secret("INTEGRATION_SMS_TOKEN")
		if !ok {
			return Config{}, fmt.Errorf("SMS provider binding has no bearer token")
		}
		caFile, _ := configProvider.GetString("INTEGRATION_SMS_SUBSTITUTE_CA_FILE")
		cfg.Integration.ExternalInteraction.SMS = ExternalProviderConfig{
			Enabled:   true,
			Provider:  smsBinding.AdapterID,
			Endpoint:  smsEndpoint,
			Token:     smsToken,
			CAFile:    caFile,
			TimeoutMs: int(smsBinding.Timeout.Milliseconds()),
		}
	case errors.Is(err, providerbinding.ErrExternalInteractionCapabilityBlocked):
		cfg.Integration.ExternalInteraction.SMS = ExternalProviderConfig{}
	default:
		return Config{}, fmt.Errorf("SMS provider binding invalid: %w", err)
	}

	pushBinding, err := providerbinding.ResolvePushBinding(cfg.Environment, configProvider)
	if errors.Is(err, providerbinding.ErrExternalInteractionCapabilityBlocked) {
		cfg.Integration.ExternalInteraction.Push = PushDeliveryProviderConfig{}
		return cfg, nil
	}
	if err != nil {
		return Config{}, fmt.Errorf("Push provider binding invalid: %w", err)
	}
	if pushBinding.AdapterID == providerbinding.PushAdapterProtocolSubstitute {
		endpoint, ok := pushBinding.Endpoint("endpoint")
		if !ok {
			return Config{}, fmt.Errorf(
				"Push protocol substitute binding has no endpoint material",
			)
		}
		cfg.Integration.ExternalInteraction.Push = PushDeliveryProviderConfig{
			Enabled:   true,
			Mode:      "protocol_substitute",
			Endpoint:  endpoint,
			TimeoutMs: int(pushBinding.Timeout.Milliseconds()),
		}
		return cfg, nil
	}

	apnsKeyFile, ok := pushBinding.Secret("INTEGRATION_PUSH_APNS_KEY_FILE")
	if !ok {
		return Config{}, fmt.Errorf("Push provider binding has no APNs key material")
	}
	fcmServiceAccountFile, ok := pushBinding.Secret("INTEGRATION_PUSH_FCM_SERVICE_ACCOUNT_FILE")
	if !ok {
		return Config{}, fmt.Errorf("Push provider binding has no FCM credential material")
	}
	requiredEndpoint := func(role string) (string, error) {
		value, found := pushBinding.Endpoint(role)
		if !found {
			return "", fmt.Errorf("Push provider binding has no %s material", role)
		}
		return value, nil
	}
	userServiceBaseURL, err := requiredEndpoint("user_service_base_url")
	if err != nil {
		return Config{}, err
	}
	apnsEnvironment, err := requiredEndpoint("apns_environment")
	if err != nil {
		return Config{}, err
	}
	apnsKeyID, err := requiredEndpoint("apns_key_id")
	if err != nil {
		return Config{}, err
	}
	apnsTeamID, err := requiredEndpoint("apns_team_id")
	if err != nil {
		return Config{}, err
	}
	apnsTopic, err := requiredEndpoint("apns_topic")
	if err != nil {
		return Config{}, err
	}
	fcmProjectID, err := requiredEndpoint("fcm_project_id")
	if err != nil {
		return Config{}, err
	}
	cfg.Integration.ExternalInteraction.Push = PushDeliveryProviderConfig{
		Enabled: true, Mode: "remote", TimeoutMs: int(pushBinding.Timeout.Milliseconds()),
		UserServiceBaseURL: userServiceBaseURL,
	}
	cfg.Integration.ExternalInteraction.Push.APNs.Environment = apnsEnvironment
	cfg.Integration.ExternalInteraction.Push.APNs.KeyFile = apnsKeyFile
	cfg.Integration.ExternalInteraction.Push.APNs.KeyID = apnsKeyID
	cfg.Integration.ExternalInteraction.Push.APNs.TeamID = apnsTeamID
	cfg.Integration.ExternalInteraction.Push.APNs.Topic = apnsTopic
	cfg.Integration.ExternalInteraction.Push.FCM.ServiceAccountFile = fcmServiceAccountFile
	cfg.Integration.ExternalInteraction.Push.FCM.ProjectID = fcmProjectID
	return cfg, nil
}
