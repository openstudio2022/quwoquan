package main

import (
	"bytes"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"

	contractcodegen "quwoquan_service/internal/metadata/codegen"
	metavalidate "quwoquan_service/internal/metadata/validate"
)

type kindFields struct {
	Ordered  []string `yaml:"ordered"`
	Required []string `yaml:"required"`
}

type envelope struct {
	Required            []string `yaml:"required"`
	Optional            []string `yaml:"optional"`
	ResourceRequired    []string `yaml:"resource_required"`
	ResourceOptional    []string `yaml:"resource_optional"`
	CorrelationOptional []string `yaml:"correlation_optional"`
}

type limits struct {
	MaxBatchItems           int `yaml:"max_batch_items"`
	MaxCanonicalBodyBytes   int `yaml:"max_canonical_body_bytes"`
	MaxMessageBytes         int `yaml:"max_message_bytes"`
	MaxAttributes           int `yaml:"max_attributes"`
	MaxAttributesBytes      int `yaml:"max_attributes_bytes"`
	MaxAttributeKeyLength   int `yaml:"max_attribute_key_length"`
	MaxAttributeValueLength int `yaml:"max_attribute_value_length"`
	RawRetentionDays        int `yaml:"raw_retention_days"`
}

type privacy struct {
	ForbiddenAttributeKeys    []string `yaml:"forbidden_attribute_keys"`
	HighCardinalityMetricKeys []string `yaml:"high_cardinality_metric_keys"`
}

// fieldPrivacyPolicy is derived exclusively from object-local privacy.yaml.
// It deliberately does not have yaml tags: runtime_observability.yaml owns the
// shared envelope, while each business object owns its field-level policy.
type fieldPrivacyPolicy struct {
	ObjectID       string
	Field          string
	Classification string
	Action         string
	MaskStrategy   string
	TruncateChars  int
	Explicit       bool
	Visibility     []string
}

type delivery struct {
	AppBufferCapacity      int `yaml:"app_buffer_capacity"`
	AppDeadLetterCapacity  int `yaml:"app_dead_letter_capacity"`
	ServiceSpoolMaxBatches int `yaml:"service_spool_max_batches"`
	ServiceDLQMaxBatches   int `yaml:"service_dlq_max_batches"`
	TTLHours               int `yaml:"ttl_hours"`
	RetryBaseSeconds       int `yaml:"retry_base_seconds"`
	RetryMaxSeconds        int `yaml:"retry_max_seconds"`
	RetryMaxExponent       int `yaml:"retry_max_exponent"`
	RetryJitterPercent     int `yaml:"retry_jitter_percent"`
}

type signal struct {
	ID                 string   `yaml:"id"`
	Owner              string   `yaml:"owner"`
	Producers          []string `yaml:"producers"`
	LogKind            string   `yaml:"log_kind"`
	DefaultSeverity    string   `yaml:"default_severity"`
	Environments       []string `yaml:"environments"`
	AttributeAllowlist []string `yaml:"attribute_allowlist"`
	CorrelationKeys    []string `yaml:"correlation_keys"`
	Backend            string   `yaml:"backend"`
	RetentionDays      int      `yaml:"retention_days"`
	Sampling           string   `yaml:"sampling"`
	Alert              string   `yaml:"alert"`
	Runbook            string   `yaml:"runbook"`
	PIIClassification  string   `yaml:"pii_classification"`
}

type catalog struct {
	Schema                string                `yaml:"schema"`
	LogKinds              []string              `yaml:"log_kinds"`
	SeverityLevels        []string              `yaml:"severity_levels"`
	ResourceVersionFields []string              `yaml:"resource_version_fields"`
	ForbiddenFields       []string              `yaml:"forbidden_fields"`
	FailureCodes          map[string]string     `yaml:"failure_codes"`
	Envelope              envelope              `yaml:"envelope"`
	KindFields            map[string]kindFields `yaml:"kind_fields"`
	Limits                limits                `yaml:"limits"`
	Privacy               privacy               `yaml:"privacy"`
	FieldPrivacyPolicies  []fieldPrivacyPolicy  `yaml:"-"`
	Delivery              delivery              `yaml:"delivery"`
	Signals               []signal              `yaml:"signals"`
}

type output struct {
	Path    string
	Content string
}

func main() {
	metadataDir := flag.String("metadata-dir", "contracts/metadata", "metadata root")
	repoRoot := flag.String("repo-root", "..", "repository root")
	check := flag.Bool("check", false, "verify generated files without writing")
	flag.Parse()

	source, err := contractcodegen.NewSource(
		*metadataDir,
		metavalidate.ProfileBaseline,
	)
	exitIf(err)
	var value catalog
	exitIf(source.Decode("_shared/runtime_observability.yaml", &value))
	value.FieldPrivacyPolicies = deriveFieldPrivacyPolicies(source)
	exitIf(validate(value))

	root, err := filepath.Abs(*repoRoot)
	exitIf(err)
	outputs := []output{
		{
			Path:    filepath.Join(root, "quwoquan_service", "runtime", "observability", "catalog_generated.go"),
			Content: mustFormatGo(renderGo(value)),
		},
		{
			Path:    appRuntimeLogCatalogOutputPath(root),
			Content: renderDart(value),
		},
		{
			Path:    appLogRedactorOutputPath(root),
			Content: renderAppLogRedactor(),
		},
		{
			Path:    filepath.Join(root, "quwoquan_ops", "cli", "lib", "generated", "runtime_log_catalog.py"),
			Content: renderPython(value),
		},
		{
			Path:    filepath.Join(root, "quwoquan_data", "scripts", "core", "generated", "runtime_log_catalog.py"),
			Content: renderPython(value),
		},
		{
			Path:    filepath.Join(root, "quwoquan_ops", "portal", "src", "generated", "observability", "runtimeLogCatalog.generated.ts"),
			Content: renderTypeScript(value),
		},
	}
	if *check {
		exitIf(checkRetiredAppRuntimeLogCatalogOutput(root))
	}

	for _, item := range outputs {
		if *check {
			actual, readErr := os.ReadFile(item.Path)
			if readErr != nil || !bytes.Equal(actual, []byte(item.Content)) {
				fmt.Fprintf(os.Stderr, "stale generated observability catalog: %s\n", item.Path)
				os.Exit(1)
			}
			continue
		}
		exitIf(os.MkdirAll(filepath.Dir(item.Path), 0o755))
		exitIf(os.WriteFile(item.Path, []byte(item.Content), 0o644))
	}
	if !*check {
		exitIf(removeRetiredAppRuntimeLogCatalogOutput(root))
	}
}

func appRuntimeLogCatalogOutputPath(root string) string {
	return filepath.Join(
		root,
		"quwoquan_app",
		"lib",
		"runtime",
		"observability",
		"generated",
		"runtime_log_catalog.g.dart",
	)
}

func appLogRedactorOutputPath(root string) string {
	return filepath.Join(
		root,
		"quwoquan_app",
		"lib",
		"runtime",
		"observability",
		"app_log_redactor.dart",
	)
}

func deriveFieldPrivacyPolicies(source *contractcodegen.Source) []fieldPrivacyPolicy {
	var result []fieldPrivacyPolicy
	objectNames := map[string]string{}
	for _, object := range source.Graph().Objects {
		objectNames[object.ID] = object.Name
	}
	rootFields := map[string]map[string]fieldPrivacyPolicy{}
	for _, field := range source.Graph().Governance.Fields {
		if field.Entity != objectNames[field.ObjectID] {
			continue
		}
		if rootFields[field.ObjectID] == nil {
			rootFields[field.ObjectID] = map[string]fieldPrivacyPolicy{}
		}
		rootFields[field.ObjectID][field.Name] = fieldPrivacyPolicy{
			ObjectID:       strings.TrimSpace(field.ObjectID),
			Field:          strings.TrimSpace(field.Name),
			Classification: strings.TrimSpace(field.Classification),
			Action:         "drop",
		}
	}
	for _, object := range source.Graph().Governance.Objects {
		if object.Privacy == nil {
			continue
		}
		policies := rootFields[object.ObjectID]
		if policies == nil {
			policies = map[string]fieldPrivacyPolicy{}
		}
		visibilityByField := map[string][]string{}
		for _, visibility := range object.Privacy.Document.FieldVisibility {
			audiences := append([]string(nil), visibility.Visibility...)
			for index := range audiences {
				audiences[index] = strings.TrimSpace(audiences[index])
			}
			sort.Strings(audiences)
			visibilityByField[strings.TrimSpace(visibility.Field)] = audiences
		}
		for field, policy := range policies {
			policy.Visibility = append([]string(nil), visibilityByField[field]...)
			policies[field] = policy
		}
		for _, policy := range object.Privacy.Document.AppLogPolicy {
			truncateChars := 0
			if policy.TruncateChars != nil {
				truncateChars = *policy.TruncateChars
			}
			policies[policy.Field] = fieldPrivacyPolicy{
				ObjectID:       strings.TrimSpace(object.ObjectID),
				Field:          strings.TrimSpace(policy.Field),
				Classification: strings.TrimSpace(string(policy.Classification)),
				Action:         strings.TrimSpace(string(policy.AppLog)),
				MaskStrategy:   strings.TrimSpace(policy.MaskStrategy),
				TruncateChars:  truncateChars,
				Explicit:       true,
				Visibility:     append([]string(nil), visibilityByField[strings.TrimSpace(policy.Field)]...),
			}
		}
		for _, policy := range policies {
			result = append(result, policy)
		}
	}
	sort.Slice(result, func(left, right int) bool {
		return strings.Join([]string{
			result[left].ObjectID,
			result[left].Field,
		}, "\x00") < strings.Join([]string{
			result[right].ObjectID,
			result[right].Field,
		}, "\x00")
	})
	return result
}

func retiredAppRuntimeLogCatalogOutputPath(root string) string {
	return filepath.Join(
		root,
		"quwoquan_app",
		"lib",
		"core",
		"observability",
		"generated",
		"runtime_log_catalog.g.dart",
	)
}

func checkRetiredAppRuntimeLogCatalogOutput(root string) error {
	path := retiredAppRuntimeLogCatalogOutputPath(root)
	if _, err := os.Lstat(path); err == nil {
		return fmt.Errorf("retired generated observability catalog still exists: %s", path)
	} else if !os.IsNotExist(err) {
		return fmt.Errorf("inspect retired generated observability catalog %s: %w", path, err)
	}
	return nil
}

func removeRetiredAppRuntimeLogCatalogOutput(root string) error {
	path := retiredAppRuntimeLogCatalogOutputPath(root)
	info, err := os.Lstat(path)
	if os.IsNotExist(err) {
		return nil
	}
	if err != nil {
		return fmt.Errorf("inspect retired generated observability catalog %s: %w", path, err)
	}
	if info.IsDir() {
		return fmt.Errorf("retired generated observability catalog path is a directory: %s", path)
	}
	if err := os.Remove(path); err != nil {
		return fmt.Errorf("remove retired generated observability catalog %s: %w", path, err)
	}
	return nil
}

func validate(value catalog) error {
	if value.Schema != "observability.slim" {
		return fmt.Errorf("schema must be observability.slim")
	}
	if strings.Contains(strings.ToLower(value.Schema), ".v") {
		return fmt.Errorf("schema must not contain a protocol version")
	}
	if strings.Join(value.LogKinds, ",") != "deploy,runtime,access,event,exception,audit" {
		return fmt.Errorf("log_kinds must use the canonical order")
	}
	if strings.Join(value.SeverityLevels, ",") != "DEBUG,INFO,WARN,ERROR" {
		return fmt.Errorf("severity_levels must use the canonical order")
	}
	if strings.Join(value.ResourceVersionFields, ",") != "appVersion,service.version" {
		return fmt.Errorf("only appVersion and service.version may be version resources")
	}
	requiredForbidden := map[string]bool{
		"schemaVersion":   false,
		"eventVersion":    false,
		"contractVersion": false,
		"releaseId":       false,
		"dataReleaseId":   false,
	}
	for _, field := range value.ForbiddenFields {
		if _, ok := requiredForbidden[field]; ok {
			requiredForbidden[field] = true
		}
	}
	for field, found := range requiredForbidden {
		if !found {
			return fmt.Errorf("missing forbidden field %s", field)
		}
	}
	if strings.Join(value.Envelope.Required, ",") != "schema,occurredAt,observedAt,logKind,severity,signal,message,resource" {
		return fmt.Errorf("envelope.required must use the canonical order")
	}
	if strings.Join(value.Envelope.ResourceRequired, ",") != "sourceType,service" {
		return fmt.Errorf("envelope.resource_required must use the canonical order")
	}
	if strings.Join(value.Envelope.Optional, ",") != "recordId,correlation,step,event,result,method,route,status,durationMs,action,target,errorCode,fingerprint,attributes" {
		return fmt.Errorf("envelope.optional must use the canonical order")
	}
	if strings.Join(value.Envelope.ResourceOptional, ",") != "environment,component,appVersion,service.version" {
		return fmt.Errorf("envelope.resource_optional must use the canonical order")
	}
	if strings.Join(value.Envelope.CorrelationOptional, ",") != "requestId,traceId,spanId,operationId,pageName,surfaceId,executionId,workPackageId,environmentRunId,actorHash" {
		return fmt.Errorf("envelope.correlation_optional must use the canonical order")
	}
	if value.Limits.MaxBatchItems != 50 ||
		value.Limits.MaxCanonicalBodyBytes != 131072 ||
		value.Limits.MaxMessageBytes != 2048 ||
		value.Limits.MaxAttributes != 24 ||
		value.Limits.MaxAttributesBytes != 4096 ||
		value.Limits.MaxAttributeKeyLength != 64 ||
		value.Limits.MaxAttributeValueLength != 512 ||
		value.Limits.RawRetentionDays != 3 {
		return fmt.Errorf("limits must use the canonical runtime observability values")
	}
	if len(value.Privacy.ForbiddenAttributeKeys) == 0 ||
		len(value.Privacy.HighCardinalityMetricKeys) == 0 {
		return fmt.Errorf("privacy key policies must be declared")
	}
	seenFieldPolicies := map[string]struct{}{}
	validActions := map[string]bool{
		"allow":               true,
		"mask":                true,
		"drop":                true,
		"truncate":            true,
		"count_only":          true,
		"drop_if_gt_100chars": true,
	}
	validMaskStrategies := map[string]bool{
		"":                true,
		"city_level_only": true,
		"strip_detail":    true,
	}
	for _, policy := range value.FieldPrivacyPolicies {
		identity := policy.ObjectID + "." + policy.Field
		if policy.ObjectID == "" || policy.Field == "" {
			return fmt.Errorf("field privacy policy identity must be non-empty")
		}
		if _, duplicate := seenFieldPolicies[identity]; duplicate {
			return fmt.Errorf("duplicate field privacy policy %s", identity)
		}
		seenFieldPolicies[identity] = struct{}{}
		if !validActions[policy.Action] {
			return fmt.Errorf("field privacy policy %s has invalid action %q", identity, policy.Action)
		}
		if !validMaskStrategies[policy.MaskStrategy] {
			return fmt.Errorf("field privacy policy %s has invalid mask strategy %q", identity, policy.MaskStrategy)
		}
		if policy.Action == "truncate" && policy.TruncateChars <= 0 {
			return fmt.Errorf("field privacy policy %s requires truncateChars", identity)
		}
		if policy.Action != "truncate" && policy.TruncateChars != 0 {
			return fmt.Errorf("field privacy policy %s must not declare truncateChars", identity)
		}
		if policy.Action != "mask" && policy.MaskStrategy != "" {
			return fmt.Errorf("field privacy policy %s must not declare maskStrategy", identity)
		}
		if !policy.Explicit && policy.Action != "drop" {
			return fmt.Errorf("default-denied field privacy policy %s must drop", identity)
		}
		if !sort.StringsAreSorted(policy.Visibility) {
			return fmt.Errorf("field privacy policy %s visibility must be sorted", identity)
		}
		if len(policy.Visibility) > 1 &&
			(containsString(policy.Visibility, "all") ||
				containsString(policy.Visibility, "never_expose")) {
			return fmt.Errorf("field privacy policy %s has an invalid exclusive visibility", identity)
		}
	}
	if value.Delivery.AppBufferCapacity != 200 ||
		value.Delivery.AppDeadLetterCapacity != 100 ||
		value.Delivery.ServiceSpoolMaxBatches != 2000 ||
		value.Delivery.ServiceDLQMaxBatches != 500 ||
		value.Delivery.TTLHours != 72 ||
		value.Delivery.RetryBaseSeconds != 5 ||
		value.Delivery.RetryMaxSeconds != 300 ||
		value.Delivery.RetryMaxExponent != 6 ||
		value.Delivery.RetryJitterPercent != 25 {
		return fmt.Errorf("delivery must use the canonical reliable runtime log values")
	}
	requiredFailureCodes := []string{
		"app_uncaught_flutter",
		"app_uncaught_platform",
		"service_log_encoding",
	}
	for _, name := range requiredFailureCodes {
		code := value.FailureCodes[name]
		if !regexp.MustCompile(`^[A-Z]+\.[A-Z_]+\.[a-z0-9_]+$`).MatchString(code) {
			return fmt.Errorf("failure code %s is missing or invalid", name)
		}
	}
	for _, field := range append(append([]string{}, value.Envelope.Required...), value.Envelope.Optional...) {
		for _, forbidden := range value.ForbiddenFields {
			if field == forbidden {
				return fmt.Errorf("envelope field %s is forbidden", field)
			}
		}
	}
	kinds := make(map[string]bool, len(value.LogKinds))
	for _, kind := range value.LogKinds {
		kinds[kind] = true
		fields, ok := value.KindFields[kind]
		if !ok || len(fields.Ordered) == 0 || len(fields.Required) == 0 {
			return fmt.Errorf("missing field contract for log kind %s", kind)
		}
	}
	levels := make(map[string]bool, len(value.SeverityLevels))
	for _, level := range value.SeverityLevels {
		levels[level] = true
	}
	seenSignals := map[string]bool{}
	for _, item := range value.Signals {
		if strings.TrimSpace(item.ID) == "" || seenSignals[item.ID] {
			return fmt.Errorf("signal id must be non-empty and unique: %q", item.ID)
		}
		seenSignals[item.ID] = true
		if !kinds[item.LogKind] ||
			!levels[item.DefaultSeverity] ||
			item.Owner == "" ||
			len(item.Producers) == 0 ||
			len(item.AttributeAllowlist) == 0 ||
			len(item.CorrelationKeys) == 0 ||
			item.Backend != "elasticsearch" ||
			item.RetentionDays != value.Limits.RawRetentionDays ||
			item.Sampling == "" ||
			item.Alert == "" ||
			item.Runbook == "" ||
			item.PIIClassification != "redacted" {
			return fmt.Errorf("signal %s has an incomplete contract", item.ID)
		}
		if strings.Join(item.Environments, ",") != "alpha,beta,gamma,prod" {
			return fmt.Errorf("signal %s must cover alpha,beta,gamma,prod", item.ID)
		}
	}
	return nil
}
