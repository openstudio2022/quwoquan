package main

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"reflect"
	"sort"
	"strings"

	"gopkg.in/yaml.v3"
)

const (
	appArtifactContractMetadataRelativePath = "_shared/app_artifact_manifest.yaml"
	appLaunchContractMetadataRelativePath   = "_shared/app_launch_manifest.yaml"

	appArtifactContractCanonicalPath = "quwoquan_service/contracts/metadata/_shared/app_artifact_manifest.yaml"
	appLaunchContractCanonicalPath   = "quwoquan_service/contracts/metadata/_shared/app_launch_manifest.yaml"

	appLaunchContractPythonOutput = "quwoquan_ops/cli/lib/generated/app_launch_contract.py"
	appLaunchContractJSONOutput   = "quwoquan_app/tool/app_launch_contract_codegen/app_launch_contract.generated.json"
	appLaunchContractDartOutput   = "quwoquan_app/lib/runtime/config/generated/app_launch_contract.g.dart"
	appLaunchContractSwiftOutput  = "quwoquan_app/ios/Runner/AppLaunchContract.generated.swift"
	appLaunchContractJavaOutput   = "quwoquan_app/android/app/src/runtimeConfigShared/java/com/quwoquan/quwoquan_app/AppLaunchContract.java"
)

type appLaunchCanonicalJSONContract struct {
	SortKeys    bool     `yaml:"sort_keys"`
	EnsureASCII bool     `yaml:"ensure_ascii"`
	Separators  []string `yaml:"separators"`
}

type appLaunchDigestContract struct {
	Algorithm      string                         `yaml:"algorithm"`
	InputEncoding  string                         `yaml:"input_encoding"`
	CanonicalJSON  appLaunchCanonicalJSONContract `yaml:"canonical_json"`
	IdentityFormat string                         `yaml:"identity_format"`
}

type appLaunchBuildProfileContract struct {
	Environments []string `yaml:"environments"`
	LaunchPolicy string   `yaml:"launch_policy"`
}

type appLaunchPolicyContract struct {
	Environments  []string `yaml:"environments"`
	BuildProfiles []string `yaml:"build_profiles"`
}

type appLaunchArtifactBaseApplicationID struct {
	Value      string `yaml:"value"`
	Registered bool   `yaml:"registered"`
}

type appLaunchArtifactApplicationIdentity struct {
	DisplayNameBase       string                                        `yaml:"display_name_base"`
	BaseApplicationIDs    map[string]appLaunchArtifactBaseApplicationID `yaml:"base_application_ids"`
	BuildProfileSuffixes  map[string]string                             `yaml:"build_profile_suffixes"`
	BuildProfileMarks     map[string]string                             `yaml:"build_profile_display_marks"`
	BuildModeSuffixes     map[string]string                             `yaml:"build_mode_suffixes"`
	BuildModeDisplayMarks map[string]string                             `yaml:"build_mode_display_marks"`
}

type appLaunchArtifactSchemas struct {
	AppArtifactManifest       yaml.Node `yaml:"app_artifact_manifest"`
	AppInstallReceipt         yaml.Node `yaml:"app_install_receipt"`
	AppDistributionReceipt    yaml.Node `yaml:"app_distribution_receipt"`
	ReleaseApplicationPackage yaml.Node `yaml:"release_application_package"`
}

type appLaunchArtifactMetadata struct {
	SchemaID             string                                   `yaml:"schema_id"`
	Description          string                                   `yaml:"description"`
	Owner                string                                   `yaml:"owner"`
	DigestContract       appLaunchDigestContract                  `yaml:"digest_contract"`
	Environments         []string                                 `yaml:"environments"`
	Platforms            []string                                 `yaml:"platforms"`
	BuildModes           []string                                 `yaml:"build_modes"`
	WebApplicationID     string                                   `yaml:"web_application_id"`
	ArtifactFormats      []string                                 `yaml:"artifact_formats"`
	BuildProfiles        map[string]appLaunchBuildProfileContract `yaml:"build_profiles"`
	BuildProducts        yaml.Node                                `yaml:"build_products"`
	DistributionClasses  yaml.Node                                `yaml:"distribution_classes"`
	ApplicationIdentity  appLaunchArtifactApplicationIdentity     `yaml:"application_identity"`
	LaunchProvenances    []string                                 `yaml:"launch_provenances"`
	DistributionChannels yaml.Node                                `yaml:"distribution_channels"`
	Schemas              appLaunchArtifactSchemas                 `yaml:"schemas"`
}

type appLaunchRuntimeConfigSourceIdentity struct {
	GitSHAFormat        string   `yaml:"git_sha_format"`
	TreeDigestFormats   []string `yaml:"tree_digest_formats"`
	AcceptedAuthorities []string `yaml:"accepted_authorities"`
}

type appLaunchRuntimeConfigPackageContract struct {
	SignatureAlgorithm         string                               `yaml:"signature_algorithm"`
	MaxLifetimeSeconds         int                                  `yaml:"max_lifetime_seconds"`
	MaxFutureSkewSeconds       int                                  `yaml:"max_future_skew_seconds"`
	SignedPayloadExcludes      []string                             `yaml:"signed_payload_excludes"`
	SourceIdentity             appLaunchRuntimeConfigSourceIdentity `yaml:"source_identity"`
	ForbiddenRuntimeCategories []string                             `yaml:"forbidden_runtime_categories"`
}

type appLaunchRuntimeConfigTrustContract struct {
	SignatureAlgorithm string   `yaml:"signature_algorithm"`
	BuildProfiles      []string `yaml:"build_profiles"`
}

type appLaunchRuntimeValueKey struct {
	Type     string `yaml:"type"`
	Category string `yaml:"category"`
	Required bool   `yaml:"required"`
}

type appLaunchSchemaField struct {
	Type             string                          `yaml:"type"`
	Const            string                          `yaml:"const"`
	AllowedValues    []string                        `yaml:"allowed_values"`
	AllowedValuesRef string                          `yaml:"allowed_values_ref"`
	AllowEmpty       bool                            `yaml:"allow_empty"`
	Format           string                          `yaml:"format"`
	MinLength        int                             `yaml:"min_length"`
	Items            *appLaunchSchemaField           `yaml:"items"`
	ValueType        string                          `yaml:"value_type"`
	SchemaRef        string                          `yaml:"schema_ref"`
	Source           string                          `yaml:"source"`
	AdditionalFields *bool                           `yaml:"additional_fields"`
	RequiredFields   []string                        `yaml:"required_fields"`
	Fields           map[string]appLaunchSchemaField `yaml:"fields"`
}

type appLaunchSchemaContract struct {
	SchemaValue           string                          `yaml:"schema_value"`
	AdditionalFields      *bool                           `yaml:"additional_fields"`
	AppendOnlyTransitions *bool                           `yaml:"append_only_transitions"`
	RequiredFields        []string                        `yaml:"required_fields"`
	Fields                map[string]appLaunchSchemaField `yaml:"fields"`
	Constraints           []string                        `yaml:"constraints"`
}

type appLaunchSchemas struct {
	RuntimeConfigTrustEnvelope     appLaunchSchemaContract `yaml:"runtime_config_trust_envelope"`
	RuntimeConfigPackage           appLaunchSchemaContract `yaml:"runtime_config_package"`
	RuntimeConfigActivationRequest appLaunchSchemaContract `yaml:"runtime_config_activation_request"`
	RuntimeConfigActivationReceipt appLaunchSchemaContract `yaml:"runtime_config_activation_receipt"`
	AppLaunchAttempt               appLaunchSchemaContract `yaml:"app_launch_attempt"`
	AppEffectiveLaunchManifest     appLaunchSchemaContract `yaml:"app_effective_launch_manifest"`
	AppLauncherHandoff             appLaunchSchemaContract `yaml:"app_launcher_handoff"`
	AppManagedPreparation          appLaunchSchemaContract `yaml:"app_managed_preparation"`
}

type appLaunchMetadata struct {
	SchemaID                      string                                `yaml:"schema_id"`
	Description                   string                                `yaml:"description"`
	Owner                         string                                `yaml:"owner"`
	DigestContract                appLaunchDigestContract               `yaml:"digest_contract"`
	TargetEnvironment             map[string]string                     `yaml:"target_environment"`
	LocalTransportTargets         []string                              `yaml:"local_transport_targets"`
	LaunchPolicies                map[string]appLaunchPolicyContract    `yaml:"launch_policies"`
	RuntimeConfigPackage          appLaunchRuntimeConfigPackageContract `yaml:"runtime_config_package"`
	RuntimeConfigTrust            appLaunchRuntimeConfigTrustContract   `yaml:"runtime_config_trust"`
	RuntimeConfigSupplyModes      []string                              `yaml:"runtime_config_supply_modes"`
	AppLaunchAttemptStatuses      []string                              `yaml:"app_launch_attempt_statuses"`
	AppLaunchAttemptForwardStates []string                              `yaml:"app_launch_attempt_forward_states"`
	RuntimeValueKeys              map[string]appLaunchRuntimeValueKey   `yaml:"runtime_value_keys"`
	LaunchBlockers                map[string]string                     `yaml:"launch_blockers"`
	RuntimeConfigErrorCodes       map[string]string                     `yaml:"runtime_config_error_codes"`
	Schemas                       appLaunchSchemas                      `yaml:"schemas"`
}

type appLaunchContractSource struct {
	Path    string `json:"path"`
	SHA256  string `json:"sha256"`
	payload []byte
}

type appLaunchContract struct {
	SourceDigest                       string
	Sources                            []appLaunchContractSource
	Environments                       []string
	TargetEnvironment                  map[string]string
	LocalTransportTargets              []string
	BuildProfileEnvironments           map[string][]string
	BuildProfileLaunchPolicies         map[string]string
	LaunchProvenances                  []string
	RuntimeConfigSupplyModes           []string
	RuntimeValueKeys                   []string
	LaunchBlockers                     map[string]string
	RuntimeConfigErrorCodes            map[string]string
	SchemaValues                       map[string]string
	SchemaRequiredFields               map[string][]string
	RuntimePackageRuntimeFields        []string
	EffectiveManifestTransportFields   []string
	EffectiveManifestEntrypoint        string
	RuntimePackageSignatureAlgorithm   string
	RuntimePackageMaxLifetimeSeconds   int
	RuntimePackageMaxFutureSkewSeconds int
	ActivationReceiptStatuses          []string
	AttemptRequiredFields              []string
	AttemptStatuses                    []string
	AttemptForwardStates               []string
	AttemptTerminalStates              []string
	NormalizedAppLaunchManifest        map[string]any
	NormalizedAppArtifactContract      map[string]any
}

type appLaunchContractArtifact struct {
	RelativePath string
	Content      []byte
}

type appLaunchContractManifestOutput struct {
	Path   string `json:"path"`
	SHA256 string `json:"sha256"`
	Bytes  int    `json:"bytes"`
}

type appLaunchContractGeneratedManifest struct {
	Schema       string                            `json:"schema"`
	Generator    string                            `json:"generator"`
	SourceDigest string                            `json:"sourceDigest"`
	Inputs       []appLaunchContractSource         `json:"inputs"`
	Outputs      []appLaunchContractManifestOutput `json:"outputs"`
}

type appLaunchContractGeneratedDocument struct {
	Schema                                            string                    `json:"schema"`
	SourceDigest                                      string                    `json:"sourceDigest"`
	Sources                                           []appLaunchContractSource `json:"sources"`
	Environments                                      []string                  `json:"environments"`
	TargetEnvironment                                 map[string]string         `json:"targetEnvironment"`
	LocalTransportTargets                             []string                  `json:"localTransportTargets"`
	BuildProfileEnvironments                          map[string][]string       `json:"buildProfileEnvironments"`
	BuildProfileLaunchPolicies                        map[string]string         `json:"buildProfileLaunchPolicies"`
	LaunchProvenances                                 []string                  `json:"launchProvenances"`
	RuntimeConfigSupplyModes                          []string                  `json:"runtimeConfigSupplyModes"`
	RuntimeValueKeys                                  []string                  `json:"runtimeValueKeys"`
	LaunchBlockers                                    map[string]string         `json:"launchBlockers"`
	RuntimeConfigErrorCodes                           map[string]string         `json:"runtimeConfigErrorCodes"`
	SchemaValues                                      map[string]string         `json:"schemaValues"`
	SchemaRequiredFields                              map[string][]string       `json:"schemaRequiredFields"`
	RuntimeConfigPackageRuntimeRequiredFields         []string                  `json:"runtimeConfigPackageRuntimeRequiredFields"`
	AppEffectiveLaunchManifestTransportRequiredFields []string                  `json:"appEffectiveLaunchManifestTransportRequiredFields"`
	AppEffectiveLaunchManifestEntrypoint              string                    `json:"appEffectiveLaunchManifestEntrypoint"`
	RuntimeConfigPackageSignatureAlgorithm            string                    `json:"runtimeConfigPackageSignatureAlgorithm"`
	RuntimeConfigPackageMaxLifetimeSeconds            int                       `json:"runtimeConfigPackageMaxLifetimeSeconds"`
	RuntimeConfigPackageMaxFutureSkewSeconds          int                       `json:"runtimeConfigPackageMaxFutureSkewSeconds"`
	RuntimeConfigActivationReceiptStatuses            []string                  `json:"runtimeConfigActivationReceiptStatuses"`
	AppLaunchAttemptRequiredFields                    []string                  `json:"appLaunchAttemptRequiredFields"`
	AppLaunchAttemptStatuses                          []string                  `json:"appLaunchAttemptStatuses"`
	AppLaunchAttemptForwardStates                     []string                  `json:"appLaunchAttemptForwardStates"`
	AppLaunchAttemptTerminalStates                    []string                  `json:"appLaunchAttemptTerminalStates"`
	AppLaunchManifest                                 map[string]any            `json:"appLaunchManifest"`
	AppArtifactContract                               map[string]any            `json:"appArtifactContract"`
}

func runAppLaunchContractMode(metadataDir, appDir, manifestPath string, check bool) error {
	contract, err := loadAppLaunchContract(metadataDir)
	if err != nil {
		return err
	}
	artifacts, err := renderAppLaunchContractArtifacts(contract)
	if err != nil {
		return err
	}
	manifest := buildAppLaunchContractGeneratedManifest(contract, artifacts)
	if strings.TrimSpace(manifestPath) == "" {
		manifestPath = filepath.Join(
			appDir,
			"tool",
			"app_launch_contract_codegen",
			"generated_manifest.json",
		)
	}
	if check {
		return checkAppLaunchContractArtifacts(appDir, manifestPath, artifacts, manifest)
	}
	return writeAppLaunchContractArtifacts(appDir, manifestPath, artifacts, manifest)
}

func loadAppLaunchContract(metadataDir string) (appLaunchContract, error) {
	artifactPath := filepath.Join(
		metadataDir,
		filepath.FromSlash(appArtifactContractMetadataRelativePath),
	)
	artifactPayload, err := os.ReadFile(artifactPath)
	if err != nil {
		return appLaunchContract{}, fmt.Errorf("read App artifact contract metadata: %w", err)
	}
	launchPath := filepath.Join(
		metadataDir,
		filepath.FromSlash(appLaunchContractMetadataRelativePath),
	)
	launchPayload, err := os.ReadFile(launchPath)
	if err != nil {
		return appLaunchContract{}, fmt.Errorf("read App launch contract metadata: %w", err)
	}

	var artifactMetadata appLaunchArtifactMetadata
	normalizedArtifact, err := decodeStrictAppLaunchYAML(
		artifactPayload,
		appArtifactContractCanonicalPath,
		&artifactMetadata,
	)
	if err != nil {
		return appLaunchContract{}, err
	}
	var launchMetadata appLaunchMetadata
	normalizedLaunch, err := decodeStrictAppLaunchYAML(
		launchPayload,
		appLaunchContractCanonicalPath,
		&launchMetadata,
	)
	if err != nil {
		return appLaunchContract{}, err
	}
	if err := validateAppLaunchContractMetadata(artifactMetadata, launchMetadata); err != nil {
		return appLaunchContract{}, err
	}

	sources := []appLaunchContractSource{
		{Path: appArtifactContractCanonicalPath, payload: artifactPayload},
		{Path: appLaunchContractCanonicalPath, payload: launchPayload},
	}
	sort.Slice(sources, func(i, j int) bool { return sources[i].Path < sources[j].Path })
	jointDigest := sha256.New()
	for index := range sources {
		sum := sha256.Sum256(sources[index].payload)
		rawSHA := hex.EncodeToString(sum[:])
		sources[index].SHA256 = "sha256:" + rawSHA
		_, _ = jointDigest.Write([]byte(sources[index].Path))
		_, _ = jointDigest.Write([]byte{0})
		_, _ = jointDigest.Write([]byte(rawSHA))
		_, _ = jointDigest.Write([]byte{'\n'})
	}
	terminalStates := append(
		[]string(nil),
		launchMetadata.AppLaunchAttemptStatuses[len(launchMetadata.AppLaunchAttemptForwardStates):]...,
	)
	return appLaunchContract{
		SourceDigest:                       "sha256:" + hex.EncodeToString(jointDigest.Sum(nil)),
		Sources:                            sources,
		Environments:                       append([]string(nil), artifactMetadata.Environments...),
		TargetEnvironment:                  cloneStringMap(launchMetadata.TargetEnvironment),
		LocalTransportTargets:              append([]string(nil), launchMetadata.LocalTransportTargets...),
		BuildProfileEnvironments:           appLaunchBuildProfileEnvironments(artifactMetadata.BuildProfiles),
		BuildProfileLaunchPolicies:         appLaunchBuildProfileLaunchPolicies(artifactMetadata.BuildProfiles),
		LaunchProvenances:                  append([]string(nil), artifactMetadata.LaunchProvenances...),
		RuntimeConfigSupplyModes:           append([]string(nil), launchMetadata.RuntimeConfigSupplyModes...),
		RuntimeValueKeys:                   sortedRuntimeValueKeys(launchMetadata.RuntimeValueKeys),
		LaunchBlockers:                     cloneStringMap(launchMetadata.LaunchBlockers),
		RuntimeConfigErrorCodes:            cloneStringMap(launchMetadata.RuntimeConfigErrorCodes),
		SchemaValues:                       appLaunchSchemaValues(launchMetadata.Schemas),
		SchemaRequiredFields:               appLaunchSchemaRequiredFields(launchMetadata.Schemas),
		RuntimePackageRuntimeFields:        append([]string(nil), launchMetadata.Schemas.RuntimeConfigPackage.Fields["runtime"].RequiredFields...),
		EffectiveManifestTransportFields:   append([]string(nil), launchMetadata.Schemas.AppEffectiveLaunchManifest.Fields["transport"].RequiredFields...),
		EffectiveManifestEntrypoint:        launchMetadata.Schemas.AppEffectiveLaunchManifest.Fields["entrypoint"].Const,
		RuntimePackageSignatureAlgorithm:   launchMetadata.RuntimeConfigPackage.SignatureAlgorithm,
		RuntimePackageMaxLifetimeSeconds:   launchMetadata.RuntimeConfigPackage.MaxLifetimeSeconds,
		RuntimePackageMaxFutureSkewSeconds: launchMetadata.RuntimeConfigPackage.MaxFutureSkewSeconds,
		ActivationReceiptStatuses:          append([]string(nil), launchMetadata.Schemas.RuntimeConfigActivationReceipt.Fields["status"].AllowedValues...),
		AttemptRequiredFields:              append([]string(nil), launchMetadata.Schemas.AppLaunchAttempt.RequiredFields...),
		AttemptStatuses:                    append([]string(nil), launchMetadata.AppLaunchAttemptStatuses...),
		AttemptForwardStates:               append([]string(nil), launchMetadata.AppLaunchAttemptForwardStates...),
		AttemptTerminalStates:              terminalStates,
		NormalizedAppLaunchManifest:        normalizedLaunch,
		NormalizedAppArtifactContract:      normalizedArtifact,
	}, nil
}

func decodeStrictAppLaunchYAML(
	payload []byte,
	sourcePath string,
	target any,
) (map[string]any, error) {
	node, err := decodeSingleAppLaunchYAMLNode(payload)
	if err != nil {
		return nil, fmt.Errorf("decode %s: %w", sourcePath, err)
	}
	if err := rejectDuplicateAppLaunchYAMLKeys(node, sourcePath); err != nil {
		return nil, err
	}
	decoder := yaml.NewDecoder(bytes.NewReader(payload))
	decoder.KnownFields(true)
	if err := decoder.Decode(target); err != nil {
		return nil, fmt.Errorf("strictly decode %s: %w", sourcePath, err)
	}
	var extra yaml.Node
	if err := decoder.Decode(&extra); err != io.EOF {
		if err == nil {
			return nil, fmt.Errorf("strictly decode %s: multiple YAML documents are forbidden", sourcePath)
		}
		return nil, fmt.Errorf("strictly decode %s: %w", sourcePath, err)
	}
	root := appLaunchYAMLRoot(node)
	if root == nil || root.Kind != yaml.MappingNode {
		return nil, fmt.Errorf("%s: root must be a YAML mapping", sourcePath)
	}
	if err := requireStructYAMLKeys(root, sourcePath, target); err != nil {
		return nil, err
	}
	normalized, err := normalizeAppLaunchYAMLNode(root)
	if err != nil {
		return nil, fmt.Errorf("normalize %s: %w", sourcePath, err)
	}
	mapping, ok := normalized.(map[string]any)
	if !ok {
		return nil, fmt.Errorf("normalize %s: root must be a mapping", sourcePath)
	}
	return mapping, nil
}

func requireStructYAMLKeys(node *yaml.Node, path string, target any) error {
	targetType := reflect.TypeOf(target)
	if targetType == nil || targetType.Kind() != reflect.Pointer || targetType.Elem().Kind() != reflect.Struct {
		return fmt.Errorf("%s: strict YAML target must be a struct pointer", path)
	}
	expected := make([]string, 0, targetType.Elem().NumField())
	for index := 0; index < targetType.Elem().NumField(); index++ {
		tag := strings.Split(targetType.Elem().Field(index).Tag.Get("yaml"), ",")[0]
		if tag != "" && tag != "-" {
			expected = append(expected, tag)
		}
	}
	actual := make([]string, 0, len(node.Content)/2)
	for index := 0; index < len(node.Content); index += 2 {
		actual = append(actual, node.Content[index].Value)
	}
	return requireExactStringSet(path+" top-level fields", actual, expected)
}

func decodeSingleAppLaunchYAMLNode(payload []byte) (*yaml.Node, error) {
	decoder := yaml.NewDecoder(bytes.NewReader(payload))
	var node yaml.Node
	if err := decoder.Decode(&node); err != nil {
		return nil, err
	}
	var extra yaml.Node
	if err := decoder.Decode(&extra); err != io.EOF {
		if err == nil {
			return nil, fmt.Errorf("multiple YAML documents are forbidden")
		}
		return nil, err
	}
	return &node, nil
}

func appLaunchYAMLRoot(node *yaml.Node) *yaml.Node {
	if node != nil && node.Kind == yaml.DocumentNode && len(node.Content) == 1 {
		return node.Content[0]
	}
	return node
}

func rejectDuplicateAppLaunchYAMLKeys(node *yaml.Node, path string) error {
	if node == nil {
		return nil
	}
	if node.Kind == yaml.MappingNode {
		seen := map[string]struct{}{}
		for index := 0; index < len(node.Content); index += 2 {
			key := node.Content[index]
			if key.Kind != yaml.ScalarNode || key.Tag != "!!str" {
				return fmt.Errorf("%s: YAML mapping key must be a string", path)
			}
			if _, exists := seen[key.Value]; exists {
				return fmt.Errorf("%s: duplicate YAML key %q", path, key.Value)
			}
			seen[key.Value] = struct{}{}
			childPath := path + "." + key.Value
			if err := rejectDuplicateAppLaunchYAMLKeys(node.Content[index+1], childPath); err != nil {
				return err
			}
		}
		return nil
	}
	for _, child := range node.Content {
		if err := rejectDuplicateAppLaunchYAMLKeys(child, path); err != nil {
			return err
		}
	}
	return nil
}

func normalizeAppLaunchYAMLNode(node *yaml.Node) (any, error) {
	if node == nil {
		return nil, nil
	}
	switch node.Kind {
	case yaml.MappingNode:
		result := make(map[string]any, len(node.Content)/2)
		for index := 0; index < len(node.Content); index += 2 {
			key := node.Content[index]
			if key.Kind != yaml.ScalarNode || key.Tag != "!!str" {
				return nil, fmt.Errorf("mapping key must be a string")
			}
			value, err := normalizeAppLaunchYAMLNode(node.Content[index+1])
			if err != nil {
				return nil, err
			}
			result[key.Value] = value
		}
		return result, nil
	case yaml.SequenceNode:
		result := make([]any, 0, len(node.Content))
		for _, child := range node.Content {
			value, err := normalizeAppLaunchYAMLNode(child)
			if err != nil {
				return nil, err
			}
			result = append(result, value)
		}
		return result, nil
	case yaml.AliasNode:
		if node.Alias == nil {
			return nil, fmt.Errorf("YAML alias has no target")
		}
		return normalizeAppLaunchYAMLNode(node.Alias)
	case yaml.ScalarNode:
		var value any
		if err := node.Decode(&value); err != nil {
			return nil, err
		}
		switch value.(type) {
		case nil, bool, int, uint64, float64, string:
			return value, nil
		default:
			return nil, fmt.Errorf("unsupported YAML scalar type %T", value)
		}
	default:
		return nil, fmt.Errorf("unsupported YAML node kind %d", node.Kind)
	}
}
