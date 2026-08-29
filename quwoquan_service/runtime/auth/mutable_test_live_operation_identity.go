package auth

import (
	"fmt"
	"net/http"
	"regexp"
	"strings"
)

const MutableTestLiveOperationIdentitySchema = "stackctl.mutable_test_live_runtime"

const (
	runtimeIdentitySchemaEnv              = "QWQ_RUNTIME_IDENTITY_SCHEMA"
	runtimeLaunchPolicyEnv                = "QWQ_RUNTIME_LAUNCH_POLICY"
	runtimeNonPromotableEnv               = "QWQ_RUNTIME_NON_PROMOTABLE"
	runtimeDeclaredEnvironmentEnv         = "QWQ_RUNTIME_ENVIRONMENT"
	runtimeTargetEnv                      = "QWQ_RUNTIME_TARGET"
	runtimeMutableStateDigestEnv          = "QWQ_RUNTIME_MUTABLE_STATE_DIGEST"
	runtimeConfigurationDigestEnv         = "QWQ_RUNTIME_CONFIGURATION_DIGEST"
	runtimeImageVersionEnv                = "IMAGE_VERSION"
	runtimeServiceConfigurationVersionEnv = "CONFIG_VERSION"
)

var mutableTestLiveDigestPattern = regexp.MustCompile(`^sha256:[0-9a-f]{64}$`)

var mutableTestLiveIdentityEnvironment = []string{
	runtimeIdentitySchemaEnv,
	runtimeLaunchPolicyEnv,
	runtimeNonPromotableEnv,
	runtimeDeclaredEnvironmentEnv,
	runtimeTargetEnv,
	runtimeMutableStateDigestEnv,
	runtimeConfigurationDigestEnv,
}

var mutableTestLiveExclusiveIdentityEnvironment = []string{
	runtimeLaunchPolicyEnv,
	runtimeNonPromotableEnv,
	runtimeMutableStateDigestEnv,
}

// LookupEnvironment resolves one process environment value without coupling
// the authorization boundary to a concrete process-global lookup in tests.
type LookupEnvironment func(string) (string, bool)

// MutableTestLiveOperationIdentity is the composition-owned identity required
// before api-edge may exercise generated operations that are not commercially
// enabled. It is intentionally non-promotable and target-bound; it is not a
// release candidate or a commercial readiness receipt.
type MutableTestLiveOperationIdentity struct {
	Schema               string
	LaunchPolicy         string
	NonPromotable        bool
	Environment          string
	DeclaredEnvironment  string
	Target               string
	MutableStateDigest   string
	ImageVersion         string
	ConfigurationDigest  string
	RuntimeConfigVersion string
}

// Validate rejects partial, forged, cross-target and production identities.
// Every digest is checked against the value consumed by the running process so
// an old mutable identity cannot authorize a newly built image or config.
func (identity MutableTestLiveOperationIdentity) Validate() error {
	if strings.TrimSpace(identity.Schema) != MutableTestLiveOperationIdentitySchema {
		return fmt.Errorf("auth: mutable test-live operation identity schema is invalid")
	}
	if strings.TrimSpace(identity.LaunchPolicy) != "test_live" {
		return fmt.Errorf("auth: mutable test-live launch policy is invalid")
	}
	if !identity.NonPromotable {
		return fmt.Errorf("auth: mutable test-live identity must be non-promotable")
	}
	environment := strings.TrimSpace(identity.Environment)
	if environment != "alpha" && environment != "beta" && environment != "gamma" {
		return fmt.Errorf("auth: mutable test-live environment is invalid")
	}
	if strings.TrimSpace(identity.DeclaredEnvironment) != environment {
		return fmt.Errorf("auth: mutable test-live environment identity drifted")
	}
	if strings.TrimSpace(identity.Target) != environment+"-local" {
		return fmt.Errorf("auth: mutable test-live target identity drifted")
	}
	mutableDigest := strings.TrimSpace(identity.MutableStateDigest)
	if !mutableTestLiveDigestPattern.MatchString(mutableDigest) {
		return fmt.Errorf("auth: mutable test-live state digest is invalid")
	}
	if strings.TrimSpace(identity.ImageVersion) != mutableDigest {
		return fmt.Errorf("auth: mutable test-live image identity drifted")
	}
	configurationDigest := strings.TrimSpace(identity.ConfigurationDigest)
	if !mutableTestLiveDigestPattern.MatchString(configurationDigest) {
		return fmt.Errorf("auth: mutable test-live configuration digest is invalid")
	}
	if strings.TrimSpace(identity.RuntimeConfigVersion) != configurationDigest {
		return fmt.Errorf("auth: mutable test-live config identity drifted")
	}
	return nil
}

// resolveMutableTestLiveBoundary decides which operationBoundary a guard
// mount must enforce for the current process composition. Absent schema
// sentinel selects the public boundary; a partial or drifted mutable identity
// fails closed before any HTTP handler is built.
func resolveMutableTestLiveBoundary(
	environment string,
	lookup LookupEnvironment,
) (operationBoundary, error) {
	if lookup == nil {
		return publicOperationBoundary, fmt.Errorf("runtime identity environment lookup is required")
	}
	schema, schemaPresent := lookup(runtimeIdentitySchemaEnv)
	schema = strings.TrimSpace(schema)
	if !schemaPresent || schema == "" {
		for _, name := range mutableTestLiveExclusiveIdentityEnvironment {
			value, _ := lookup(name)
			if strings.TrimSpace(value) != "" {
				return publicOperationBoundary, fmt.Errorf(
					"mutable test-live operation identity missing %s",
					runtimeIdentitySchemaEnv,
				)
			}
		}
		return publicOperationBoundary, nil
	}
	values := make(map[string]string, len(mutableTestLiveIdentityEnvironment))
	values[runtimeIdentitySchemaEnv] = schema
	for _, name := range mutableTestLiveIdentityEnvironment[1:] {
		value, _ := lookup(name)
		value = strings.TrimSpace(value)
		values[name] = value
	}
	for _, name := range mutableTestLiveIdentityEnvironment {
		if values[name] == "" {
			return publicOperationBoundary, fmt.Errorf(
				"mutable test-live operation identity missing %s",
				name,
			)
		}
	}
	if values[runtimeNonPromotableEnv] != "true" {
		return publicOperationBoundary, fmt.Errorf(
			"mutable test-live non-promotable identity is invalid",
		)
	}
	imageVersion, _ := lookup(runtimeImageVersionEnv)
	configVersion, _ := lookup(runtimeServiceConfigurationVersionEnv)
	identity := MutableTestLiveOperationIdentity{
		Schema:               values[runtimeIdentitySchemaEnv],
		LaunchPolicy:         values[runtimeLaunchPolicyEnv],
		NonPromotable:        true,
		Environment:          strings.TrimSpace(environment),
		DeclaredEnvironment:  values[runtimeDeclaredEnvironmentEnv],
		Target:               values[runtimeTargetEnv],
		MutableStateDigest:   values[runtimeMutableStateDigestEnv],
		ImageVersion:         strings.TrimSpace(imageVersion),
		ConfigurationDigest:  values[runtimeConfigurationDigestEnv],
		RuntimeConfigVersion: strings.TrimSpace(configVersion),
	}
	if err := identity.Validate(); err != nil {
		return publicOperationBoundary, err
	}
	return runtimeOperationBoundary, nil
}

// OperationAuthorizationForRuntime selects the ordinary commercial boundary
// unless the dedicated mutable test-live schema sentinel is present. Immutable
// release compositions legitimately carry general runtime environment, target
// and configuration identities; those values must not opt into test-live.
// Partial or drifted mutable identities fail closed before the HTTP handler is
// built.
func OperationAuthorizationForRuntime(
	descriptors []OperationSecurityDescriptor,
	environment string,
	lookup LookupEnvironment,
) (func(http.Handler) http.Handler, error) {
	boundary, err := resolveMutableTestLiveBoundary(environment, lookup)
	if err != nil {
		return nil, err
	}
	return requireGeneratedOperationAuthorization(descriptors, boundary), nil
}

// EnforceOperationAuthorizationForRuntime 是 EnforceGeneratedOperationAuthorization
// 的 runtime 身份感知版本：ContractGraph 已登记的 method+path 一律执行 generated
// authorization，未登记的迁移期路径继续 pass-through。唯一差别在 blocked operation
// 的边界选择——验证通过的 mutable test-live 身份使用 runtimeOperationBoundary，
// 让 blocked operation 到达 handler 以产生 readiness 证据；其余组合（含全部
// immutable release runtime）保持 publicOperationBoundary fail-closed。
func EnforceOperationAuthorizationForRuntime(
	descriptors []OperationSecurityDescriptor,
	environment string,
	lookup LookupEnvironment,
) (func(http.Handler) http.Handler, error) {
	boundary, err := resolveMutableTestLiveBoundary(environment, lookup)
	if err != nil {
		return nil, err
	}
	return enforceGeneratedOperationAuthorization(descriptors, boundary), nil
}
