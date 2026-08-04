package authbinding

import (
	"errors"
	"fmt"
	"os"
	"strings"

	runtimeconfig "quwoquan_service/runtime/config"
	usergenerated "quwoquan_service/services/user-service/generated/account/user_account"
)

var (
	// ErrAuthRuntimeCapabilityBlocked indicates that metadata disables the
	// external authentication capability for the current composition.
	ErrAuthRuntimeCapabilityBlocked = errors.New(
		"user authentication external capability is blocked",
	)
	// ErrAuthRuntimeCapabilityUnavailable indicates that an optional binding
	// lacks protected runtime material.
	ErrAuthRuntimeCapabilityUnavailable = errors.New(
		"user authentication external capability is unavailable",
	)
)

const NonPromotablePrevalidationEnv = "QWQ_NONPROMOTABLE_PREVALIDATION"

// RuntimeBinding is the validated composition input for one authentication
// capability. Endpoint and secret values remain accessible only by explicit
// role or environment-key lookup.
type RuntimeBinding struct {
	adapterID string
	endpoints map[string]string
	secrets   map[string]string
}

func (binding RuntimeBinding) AdapterID() string {
	return binding.adapterID
}

func (binding RuntimeBinding) Endpoint(role string) string {
	return strings.TrimSpace(binding.endpoints[role])
}

func (binding RuntimeBinding) Secret(environmentKey string) string {
	return strings.TrimSpace(binding.secrets[environmentKey])
}

func ContentSliceExternalAuthDisabled() bool {
	switch strings.ToLower(strings.TrimSpace(os.Getenv("QWQ_WORKLOAD"))) {
	case "content-release", "content-commercial":
		return true
	default:
		return false
	}
}

func ResolveCarrierOneTapBinding() (RuntimeBinding, error) {
	return resolveRuntimeBinding(
		"identity.carrier.one_tap",
		[]string{
			CarrierOneTapAdapterID,
			CarrierOneTapProtocolFixtureAdapterID,
		},
	)
}

func ResolveFederatedIdentityBinding() (RuntimeBinding, error) {
	return resolveRuntimeBinding(
		"identity.social.login",
		[]string{
			FederatedIdentityAdapterID,
			FederatedIdentityProtocolFixtureAdapterID,
		},
	)
}

func resolveRuntimeBinding(
	capabilityID string,
	allowedAdapterIDs []string,
) (RuntimeBinding, error) {
	appEnv := strings.TrimSpace(os.Getenv("APP_ENV"))
	if appEnv == "" {
		appEnv = "alpha"
	}
	if ContentSliceExternalAuthDisabled() {
		return RuntimeBinding{}, fmt.Errorf(
			"%w: %s is outside the bounded content workload",
			ErrAuthRuntimeCapabilityBlocked,
			capabilityID,
		)
	}
	if nonPromotableFirstPartyPrevalidation(appEnv) {
		return RuntimeBinding{}, fmt.Errorf(
			"%w: %s for non-promotable first-party prevalidation",
			ErrAuthRuntimeCapabilityBlocked,
			capabilityID,
		)
	}
	descriptor, found := usergenerated.ExternalProviderBindingFor(appEnv, capabilityID)
	if !found {
		return RuntimeBinding{}, fmt.Errorf(
			"%s binding is missing for environment=%s",
			capabilityID,
			appEnv,
		)
	}
	if descriptor.State != "enabled" {
		return RuntimeBinding{}, fmt.Errorf(
			"%w: %s for environment=%s",
			ErrAuthRuntimeCapabilityBlocked,
			capabilityID,
			appEnv,
		)
	}
	allowed := false
	for _, adapterID := range allowedAdapterIDs {
		if descriptor.AdapterID == adapterID {
			allowed = true
			break
		}
	}
	if !allowed {
		return RuntimeBinding{}, fmt.Errorf(
			"%s binding selects an unexpected adapter for environment=%s",
			capabilityID,
			appEnv,
		)
	}
	configProvider := runtimeconfig.EnvRuntimeConfigProvider{}
	binding := RuntimeBinding{
		adapterID: descriptor.AdapterID,
		endpoints: make(map[string]string, len(descriptor.EndpointEnvironmentKeys)),
		secrets:   make(map[string]string, len(descriptor.SecretEnvironmentKeys)),
	}
	for role, environmentKey := range descriptor.EndpointEnvironmentKeys {
		value, ok := configProvider.GetString(environmentKey)
		if !ok {
			return RuntimeBinding{}, fmt.Errorf(
				"%w: %s endpoint material is unavailable for role=%s",
				ErrAuthRuntimeCapabilityUnavailable,
				capabilityID,
				role,
			)
		}
		binding.endpoints[role] = value
	}
	for _, environmentKey := range descriptor.SecretEnvironmentKeys {
		value, ok := configProvider.GetString(environmentKey)
		if !ok {
			return RuntimeBinding{}, fmt.Errorf(
				"%w: %s secret material is unavailable",
				ErrAuthRuntimeCapabilityUnavailable,
				capabilityID,
			)
		}
		binding.secrets[environmentKey] = value
	}
	if descriptor.TimeoutMilliseconds <= 0 {
		return RuntimeBinding{}, fmt.Errorf(
			"%s binding timeout is invalid",
			capabilityID,
		)
	}
	return binding, nil
}

func nonPromotableFirstPartyPrevalidation(appEnv string) bool {
	return strings.EqualFold(strings.TrimSpace(appEnv), "prod") &&
		strings.TrimSpace(os.Getenv(NonPromotablePrevalidationEnv)) == "first-party"
}
