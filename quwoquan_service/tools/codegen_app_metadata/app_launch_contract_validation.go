package main

import (
	"fmt"
	"strings"
)

func validateAppLaunchContractMetadata(
	artifact appLaunchArtifactMetadata,
	launch appLaunchMetadata,
) error {
	if artifact.SchemaID != "app_artifact_manifest" {
		return fmt.Errorf("App artifact contract schema_id = %q, want app_artifact_manifest", artifact.SchemaID)
	}
	if launch.SchemaID != "app_launch_manifest" {
		return fmt.Errorf("App launch contract schema_id = %q, want app_launch_manifest", launch.SchemaID)
	}
	if artifact.Owner != "runtime" || launch.Owner != "runtime" {
		return fmt.Errorf("App artifact and launch contracts must both be owned by runtime")
	}
	if strings.TrimSpace(artifact.Description) == "" || strings.TrimSpace(launch.Description) == "" {
		return fmt.Errorf("App artifact and launch contract descriptions are required")
	}
	if err := validateAppLaunchDigestContract("app_artifact_manifest", artifact.DigestContract); err != nil {
		return err
	}
	if err := validateAppLaunchDigestContract("app_launch_manifest", launch.DigestContract); err != nil {
		return err
	}
	for name, values := range map[string][]string{
		"app_artifact_manifest.environments":       artifact.Environments,
		"app_artifact_manifest.platforms":          artifact.Platforms,
		"app_artifact_manifest.build_modes":        artifact.BuildModes,
		"app_artifact_manifest.launch_provenances": artifact.LaunchProvenances,
		"runtime_config_supply_modes":              launch.RuntimeConfigSupplyModes,
		"app_launch_attempt_statuses":              launch.AppLaunchAttemptStatuses,
		"app_launch_attempt_forward_states":        launch.AppLaunchAttemptForwardStates,
		"local_transport_targets":                  launch.LocalTransportTargets,
	} {
		if len(values) == 0 {
			return fmt.Errorf("%s is empty", name)
		}
		if err := requireUniqueNonEmptyStrings(name, values); err != nil {
			return err
		}
	}
	if len(launch.TargetEnvironment) == 0 {
		return fmt.Errorf("target_environment is empty")
	}
	declaredEnvironments := stringSet(artifact.Environments)
	for target, environment := range launch.TargetEnvironment {
		if strings.TrimSpace(target) == "" || strings.TrimSpace(environment) == "" {
			return fmt.Errorf("target_environment contains an empty target or environment")
		}
		if _, exists := declaredEnvironments[environment]; !exists {
			return fmt.Errorf("target_environment.%s references undeclared environment %q", target, environment)
		}
	}
	for _, target := range launch.LocalTransportTargets {
		if _, exists := launch.TargetEnvironment[target]; !exists {
			return fmt.Errorf("local_transport_targets references undeclared target %q", target)
		}
	}
	statusSet := stringSet(launch.AppLaunchAttemptStatuses)
	if len(launch.AppLaunchAttemptForwardStates) >= len(launch.AppLaunchAttemptStatuses) {
		return fmt.Errorf("app_launch_attempt_statuses must declare at least one terminal state after forward_states")
	}
	for index, state := range launch.AppLaunchAttemptForwardStates {
		if _, exists := statusSet[state]; !exists {
			return fmt.Errorf("app_launch_attempt_forward_states[%d] references undeclared status %q", index, state)
		}
		if launch.AppLaunchAttemptStatuses[index] != state {
			return fmt.Errorf("app_launch_attempt_forward_states must be an ordered prefix of app_launch_attempt_statuses")
		}
	}
	if err := requireNonEmptyStringMap("launch_blockers", launch.LaunchBlockers); err != nil {
		return err
	}
	if err := requireNonEmptyStringMap("runtime_config_error_codes", launch.RuntimeConfigErrorCodes); err != nil {
		return err
	}
	if err := validateAppLaunchBuildProfiles(artifact, launch); err != nil {
		return err
	}
	if err := validateAppLaunchApplicationIdentity(artifact); err != nil {
		return err
	}
	if err := validateAppLaunchRuntimeConfigContracts(artifact, launch); err != nil {
		return err
	}
	if err := validateAppLaunchSchemas(artifact, launch); err != nil {
		return err
	}
	return nil
}

func validateAppLaunchDigestContract(name string, contract appLaunchDigestContract) error {
	if contract.Algorithm != "sha256" || contract.InputEncoding != "utf-8" ||
		!contract.CanonicalJSON.SortKeys || contract.CanonicalJSON.EnsureASCII ||
		len(contract.CanonicalJSON.Separators) != 2 ||
		contract.CanonicalJSON.Separators[0] != "," ||
		contract.CanonicalJSON.Separators[1] != ":" ||
		contract.IdentityFormat != "sha256:<64-lowercase-hex>" {
		return fmt.Errorf("%s.digest_contract differs from the canonical sha256 contract", name)
	}
	return nil
}

func validateAppLaunchBuildProfiles(
	artifact appLaunchArtifactMetadata,
	launch appLaunchMetadata,
) error {
	if len(artifact.BuildProfiles) == 0 || len(launch.LaunchPolicies) == 0 {
		return fmt.Errorf("build_profiles and launch_policies must be non-empty")
	}
	declaredEnvironments := stringSet(artifact.Environments)
	profilesByPolicy := map[string][]string{}
	for profile, artifactProfile := range artifact.BuildProfiles {
		if strings.TrimSpace(profile) == "" || strings.TrimSpace(artifactProfile.LaunchPolicy) == "" {
			return fmt.Errorf("build profile name and launch_policy are required")
		}
		if len(artifactProfile.Environments) == 0 {
			return fmt.Errorf("build_profiles.%s.environments is empty", profile)
		}
		if err := requireUniqueNonEmptyStrings("build_profiles."+profile+".environments", artifactProfile.Environments); err != nil {
			return err
		}
		for _, environment := range artifactProfile.Environments {
			if _, exists := declaredEnvironments[environment]; !exists {
				return fmt.Errorf("build_profiles.%s references undeclared environment %q", profile, environment)
			}
		}
		launchPolicy, exists := launch.LaunchPolicies[artifactProfile.LaunchPolicy]
		if !exists {
			return fmt.Errorf(
				"build_profiles.%s launch_policy %q has no launch_policies owner",
				profile,
				artifactProfile.LaunchPolicy,
			)
		}
		if err := requireExactStringSet("build profile "+profile+" environments", artifactProfile.Environments, launchPolicy.Environments); err != nil {
			return err
		}
		profilesByPolicy[artifactProfile.LaunchPolicy] = append(profilesByPolicy[artifactProfile.LaunchPolicy], profile)
	}
	for policy, contract := range launch.LaunchPolicies {
		if strings.TrimSpace(policy) == "" || len(contract.Environments) == 0 || len(contract.BuildProfiles) == 0 {
			return fmt.Errorf("launch_policies.%s is incomplete", policy)
		}
		if err := requireUniqueNonEmptyStrings("launch_policies."+policy+".environments", contract.Environments); err != nil {
			return err
		}
		if err := requireUniqueNonEmptyStrings("launch_policies."+policy+".build_profiles", contract.BuildProfiles); err != nil {
			return err
		}
		if err := requireExactStringSet("launch policy "+policy+" build_profiles", contract.BuildProfiles, profilesByPolicy[policy]); err != nil {
			return err
		}
	}
	return nil
}

func validateAppLaunchApplicationIdentity(artifact appLaunchArtifactMetadata) error {
	identity := artifact.ApplicationIdentity
	if strings.TrimSpace(identity.DisplayNameBase) == "" {
		return fmt.Errorf("application_identity.display_name_base is required")
	}
	if len(identity.BaseApplicationIDs) == 0 {
		return fmt.Errorf("application_identity.base_application_ids is empty")
	}
	for platform, base := range identity.BaseApplicationIDs {
		if strings.TrimSpace(base.Value) == "" {
			return fmt.Errorf("application_identity base ID is empty for %s", platform)
		}
	}
	for name, values := range map[string]map[string]string{
		"build_profile_suffixes":      identity.BuildProfileSuffixes,
		"build_profile_display_marks": identity.BuildProfileMarks,
		"build_mode_suffixes":         identity.BuildModeSuffixes,
		"build_mode_display_marks":    identity.BuildModeDisplayMarks,
	} {
		expected := mapBuildProfileKeys(artifact.BuildProfiles)
		if strings.HasPrefix(name, "build_mode") {
			expected = append([]string(nil), artifact.BuildModes...)
		}
		if err := requireExactStringSet("application_identity."+name, mapStringKeys(values), expected); err != nil {
			return err
		}
	}
	return nil
}

func validateAppLaunchRuntimeConfigContracts(
	artifact appLaunchArtifactMetadata,
	launch appLaunchMetadata,
) error {
	packageContract := launch.RuntimeConfigPackage
	if packageContract.SignatureAlgorithm != "ed25519" ||
		packageContract.MaxLifetimeSeconds <= 0 ||
		packageContract.MaxFutureSkewSeconds < 0 ||
		len(packageContract.SignedPayloadExcludes) == 0 ||
		strings.TrimSpace(packageContract.SourceIdentity.GitSHAFormat) == "" ||
		len(packageContract.SourceIdentity.TreeDigestFormats) == 0 ||
		len(packageContract.SourceIdentity.AcceptedAuthorities) == 0 ||
		len(packageContract.ForbiddenRuntimeCategories) == 0 {
		return fmt.Errorf("runtime_config_package contract is incomplete")
	}
	if launch.RuntimeConfigTrust.SignatureAlgorithm != "ed25519" {
		return fmt.Errorf("runtime_config_trust.signature_algorithm must be ed25519")
	}
	if err := requireExactStringSet(
		"runtime_config_trust.build_profiles",
		launch.RuntimeConfigTrust.BuildProfiles,
		mapBuildProfileKeys(artifact.BuildProfiles),
	); err != nil {
		return err
	}
	if len(launch.RuntimeValueKeys) == 0 {
		return fmt.Errorf("runtime_value_keys is empty")
	}
	for key, contract := range launch.RuntimeValueKeys {
		if strings.TrimSpace(key) == "" || contract.Type != "string" ||
			strings.TrimSpace(contract.Category) == "" || !contract.Required {
			return fmt.Errorf("runtime_value_keys.%s must be a required categorized string", key)
		}
	}
	return nil
}

func validateAppLaunchSchemas(
	artifact appLaunchArtifactMetadata,
	launch appLaunchMetadata,
) error {
	attempt := launch.Schemas.AppLaunchAttempt
	schemas := appLaunchNamedSchemas(launch.Schemas)
	for name, schema := range schemas {
		if strings.TrimSpace(schema.SchemaValue) == "" || schema.AdditionalFields == nil ||
			*schema.AdditionalFields || len(schema.RequiredFields) == 0 || len(schema.Fields) == 0 {
			return fmt.Errorf("schemas.%s is incomplete or permits additional fields", name)
		}
		if err := requireUniqueNonEmptyStrings("schemas."+name+".required_fields", schema.RequiredFields); err != nil {
			return err
		}
		if err := requireExactStringSet(
			"schemas."+name+".fields",
			mapSchemaFieldKeys(schema.Fields),
			schema.RequiredFields,
		); err != nil {
			return err
		}
		for fieldName, field := range schema.Fields {
			if strings.TrimSpace(field.Type) == "" {
				return fmt.Errorf("schemas.%s.fields.%s.type is required", name, fieldName)
			}
			if err := validateNestedAppLaunchSchemaField(
				"schemas."+name+".fields."+fieldName,
				field,
			); err != nil {
				return err
			}
		}
	}
	if attempt.AppendOnlyTransitions == nil || !*attempt.AppendOnlyTransitions {
		return fmt.Errorf("schemas.app_launch_attempt append-only transition contract is invalid")
	}
	if err := requireAppLaunchFieldRef(
		attempt,
		"launchProvenance",
		"app_artifact_manifest.launch_provenances",
	); err != nil {
		return err
	}
	if err := requireAppLaunchFieldRef(attempt, "runtimeConfigSupplyMode", "runtime_config_supply_modes"); err != nil {
		return err
	}
	if err := requireAppLaunchFieldRef(attempt, "status", "app_launch_attempt_statuses"); err != nil {
		return err
	}
	if err := requireAppLaunchFieldRef(attempt, "firstBlocker", "launch_blockers"); err != nil {
		return err
	}
	if err := requireExactOrderedStrings(
		"app_launch_attempt.fields.environment.allowed_values",
		attempt.Fields["environment"].AllowedValues,
		artifact.Environments,
	); err != nil {
		return err
	}
	if err := requireExactStringSet(
		"app_launch_attempt.fields.target.allowed_values",
		attempt.Fields["target"].AllowedValues,
		mapStringKeys(launch.TargetEnvironment),
	); err != nil {
		return err
	}
	effective := launch.Schemas.AppEffectiveLaunchManifest
	entrypoint, exists := effective.Fields["entrypoint"]
	if !exists || entrypoint.Type != "string" || strings.TrimSpace(entrypoint.Const) == "" {
		return fmt.Errorf("app_effective_launch_manifest entrypoint const is invalid")
	}
	if err := requireAppLaunchFieldRef(
		effective,
		"launchProvenance",
		"app_artifact_manifest.launch_provenances",
	); err != nil {
		return err
	}
	if err := requireAppLaunchFieldRef(
		effective,
		"runtimeConfigSupplyMode",
		"runtime_config_supply_modes",
	); err != nil {
		return err
	}
	receipt := launch.Schemas.RuntimeConfigActivationReceipt
	if err := requireAppLaunchFieldRef(
		receipt,
		"launchProvenance",
		"app_artifact_manifest.launch_provenances",
	); err != nil {
		return err
	}
	if !receipt.Fields["launchProvenance"].AllowEmpty {
		return fmt.Errorf("activation receipt launchProvenance must allow empty on undecodable failure")
	}
	if err := requireAppLaunchFieldRef(
		receipt,
		"runtimeConfigSupplyMode",
		"runtime_config_supply_modes",
	); err != nil {
		return err
	}
	if !receipt.Fields["runtimeConfigSupplyMode"].AllowEmpty {
		return fmt.Errorf("activation receipt runtimeConfigSupplyMode must allow empty on undecodable failure")
	}
	statuses := launch.Schemas.RuntimeConfigActivationReceipt.Fields["status"].AllowedValues
	if len(statuses) == 0 {
		return fmt.Errorf("runtime_config_activation_receipt.fields.status.allowed_values is empty")
	}
	if err := requireUniqueNonEmptyStrings("runtime_config_activation_receipt.fields.status.allowed_values", statuses); err != nil {
		return err
	}
	return nil
}

func appLaunchNamedSchemas(schemas appLaunchSchemas) map[string]appLaunchSchemaContract {
	return map[string]appLaunchSchemaContract{
		"runtime_config_trust_envelope":     schemas.RuntimeConfigTrustEnvelope,
		"runtime_config_package":            schemas.RuntimeConfigPackage,
		"runtime_config_activation_request": schemas.RuntimeConfigActivationRequest,
		"runtime_config_activation_receipt": schemas.RuntimeConfigActivationReceipt,
		"app_launch_attempt":                schemas.AppLaunchAttempt,
		"app_effective_launch_manifest":     schemas.AppEffectiveLaunchManifest,
		"app_launcher_handoff":              schemas.AppLauncherHandoff,
	}
}

func appLaunchSchemaValues(schemas appLaunchSchemas) map[string]string {
	result := map[string]string{}
	for name, schema := range appLaunchNamedSchemas(schemas) {
		result[name] = schema.SchemaValue
	}
	return result
}

func appLaunchSchemaRequiredFields(schemas appLaunchSchemas) map[string][]string {
	result := map[string][]string{}
	for name, schema := range appLaunchNamedSchemas(schemas) {
		result[name] = append([]string(nil), schema.RequiredFields...)
	}
	return result
}

func stringSet(values []string) map[string]struct{} {
	result := make(map[string]struct{}, len(values))
	for _, value := range values {
		result[value] = struct{}{}
	}
	return result
}

func validateNestedAppLaunchSchemaField(path string, field appLaunchSchemaField) error {
	if field.Type == "object" && len(field.Fields) > 0 {
		if field.AdditionalFields == nil || *field.AdditionalFields {
			return fmt.Errorf("%s object must reject additional fields", path)
		}
		if err := requireUniqueNonEmptyStrings(path+".required_fields", field.RequiredFields); err != nil {
			return err
		}
		if err := requireExactStringSet(
			path+".fields",
			mapSchemaFieldKeys(field.Fields),
			field.RequiredFields,
		); err != nil {
			return err
		}
		for childName, child := range field.Fields {
			if strings.TrimSpace(child.Type) == "" {
				return fmt.Errorf("%s.fields.%s.type is required", path, childName)
			}
			if err := validateNestedAppLaunchSchemaField(path+".fields."+childName, child); err != nil {
				return err
			}
		}
	}
	if field.Type == "array" && field.Items == nil {
		return fmt.Errorf("%s array items contract is required", path)
	}
	if field.Items != nil {
		return validateNestedAppLaunchSchemaField(path+".items", *field.Items)
	}
	return nil
}

func requireAppLaunchFieldRef(schema appLaunchSchemaContract, fieldName, expected string) error {
	field, exists := schema.Fields[fieldName]
	if !exists || field.Type != "string" || field.AllowedValuesRef != expected {
		return fmt.Errorf(
			"field %s allowed_values_ref must be %s",
			fieldName,
			expected,
		)
	}
	return nil
}
