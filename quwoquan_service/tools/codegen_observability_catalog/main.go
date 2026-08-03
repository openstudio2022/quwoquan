package main

import (
	"bytes"
	"flag"
	"fmt"
	"go/format"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
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
	exitIf(validate(value))

	root, err := filepath.Abs(*repoRoot)
	exitIf(err)
	outputs := []output{
		{
			Path:    filepath.Join(root, "quwoquan_service", "runtime", "observability", "catalog_generated.go"),
			Content: mustFormatGo(renderGo(value)),
		},
		{
			Path:    filepath.Join(root, "quwoquan_app", "lib", "core", "observability", "generated", "runtime_log_catalog.g.dart"),
			Content: renderDart(value),
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

func renderGo(value catalog) string {
	var b strings.Builder
	b.WriteString("// Code generated from contracts/metadata/_shared/runtime_observability.yaml. DO NOT EDIT.\n\n")
	b.WriteString("package runtimeobservability\n\n")
	b.WriteString("const ObservabilitySchema = " + strconv.Quote(value.Schema) + "\n\n")
	b.WriteString("type CatalogSignalMetadata struct {\n")
	b.WriteString("\tOwner string\n")
	b.WriteString("\tProducers []string\n")
	b.WriteString("\tLogKind string\n")
	b.WriteString("\tDefaultSeverity string\n")
	b.WriteString("\tEnvironments []string\n")
	b.WriteString("\tAttributeAllowlist []string\n")
	b.WriteString("\tCorrelationKeys []string\n")
	b.WriteString("\tBackend string\n")
	b.WriteString("\tRetentionDays int\n")
	b.WriteString("\tSampling string\n")
	b.WriteString("\tAlert string\n")
	b.WriteString("\tRunbook string\n")
	b.WriteString("\tPIIClassification string\n")
	b.WriteString("}\n\n")
	writeGoSet(&b, "CatalogLogKinds", value.LogKinds)
	writeGoSet(&b, "CatalogSeverityLevels", value.SeverityLevels)
	writeGoSet(&b, "CatalogSignals", signalIDs(value.Signals))
	writeGoSet(&b, "CatalogForbiddenFields", value.ForbiddenFields)
	writeGoStringMap(&b, "CatalogFailureCodes", value.FailureCodes)
	writeGoSet(&b, "CatalogForbiddenAttributeKeys", value.Privacy.ForbiddenAttributeKeys)
	writeGoSet(&b, "CatalogHighCardinalityMetricKeys", value.Privacy.HighCardinalityMetricKeys)
	writeGoInt(&b, "CatalogMaxBatchItems", value.Limits.MaxBatchItems)
	writeGoInt(&b, "CatalogMaxCanonicalBodyBytes", value.Limits.MaxCanonicalBodyBytes)
	writeGoInt(&b, "CatalogMaxMessageBytes", value.Limits.MaxMessageBytes)
	writeGoInt(&b, "CatalogMaxAttributes", value.Limits.MaxAttributes)
	writeGoInt(&b, "CatalogMaxAttributesBytes", value.Limits.MaxAttributesBytes)
	writeGoInt(&b, "CatalogMaxAttributeKeyLength", value.Limits.MaxAttributeKeyLength)
	writeGoInt(&b, "CatalogMaxAttributeValueLength", value.Limits.MaxAttributeValueLength)
	writeGoInt(&b, "CatalogRawRetentionDays", value.Limits.RawRetentionDays)
	writeGoInt(&b, "CatalogAppBufferCapacity", value.Delivery.AppBufferCapacity)
	writeGoInt(&b, "CatalogAppDeadLetterCapacity", value.Delivery.AppDeadLetterCapacity)
	writeGoInt(&b, "CatalogServiceSpoolMaxBatches", value.Delivery.ServiceSpoolMaxBatches)
	writeGoInt(&b, "CatalogServiceDLQMaxBatches", value.Delivery.ServiceDLQMaxBatches)
	writeGoInt(&b, "CatalogDeliveryTTLHours", value.Delivery.TTLHours)
	writeGoInt(&b, "CatalogRetryBaseSeconds", value.Delivery.RetryBaseSeconds)
	writeGoInt(&b, "CatalogRetryMaxSeconds", value.Delivery.RetryMaxSeconds)
	writeGoInt(&b, "CatalogRetryMaxExponent", value.Delivery.RetryMaxExponent)
	writeGoInt(&b, "CatalogRetryJitterPercent", value.Delivery.RetryJitterPercent)
	writeGoSlice(&b, "CatalogEnvelopeRequiredFields", value.Envelope.Required)
	writeGoSlice(&b, "CatalogEnvelopeOptionalFields", value.Envelope.Optional)
	writeGoSlice(&b, "CatalogResourceRequiredFields", value.Envelope.ResourceRequired)
	writeGoSlice(&b, "CatalogResourceOptionalFields", value.Envelope.ResourceOptional)
	writeGoSlice(&b, "CatalogCorrelationOptionalFields", value.Envelope.CorrelationOptional)
	b.WriteString("var CatalogFieldOrder = map[string][]string{\n")
	for _, kind := range value.LogKinds {
		b.WriteString("\t" + strconv.Quote(kind) + ": {")
		for index, field := range value.KindFields[kind].Ordered {
			if index > 0 {
				b.WriteString(", ")
			}
			b.WriteString(strconv.Quote(field))
		}
		b.WriteString("},\n")
	}
	b.WriteString("}\n\n")
	b.WriteString("var CatalogRequiredFields = map[string]map[string]struct{}{\n")
	for _, kind := range value.LogKinds {
		b.WriteString("\t" + strconv.Quote(kind) + ": {")
		for index, field := range value.KindFields[kind].Required {
			if index > 0 {
				b.WriteString(", ")
			}
			b.WriteString(strconv.Quote(field) + ": {}")
		}
		b.WriteString("},\n")
	}
	b.WriteString("}\n\n")
	b.WriteString("var CatalogSignalLogKinds = map[string]string{\n")
	for _, item := range sortedSignals(value.Signals) {
		b.WriteString("\t" + strconv.Quote(item.ID) + ": " + strconv.Quote(item.LogKind) + ",\n")
	}
	b.WriteString("}\n\n")
	b.WriteString("var CatalogSignalDefaultSeverities = map[string]string{\n")
	for _, item := range sortedSignals(value.Signals) {
		b.WriteString("\t" + strconv.Quote(item.ID) + ": " + strconv.Quote(item.DefaultSeverity) + ",\n")
	}
	b.WriteString("}\n")
	b.WriteString("\nvar CatalogSignalRegistry = map[string]CatalogSignalMetadata{\n")
	for _, item := range sortedSignals(value.Signals) {
		b.WriteString("\t" + strconv.Quote(item.ID) + ": {\n")
		b.WriteString("\t\tOwner: " + strconv.Quote(item.Owner) + ",\n")
		b.WriteString("\t\tProducers: " + goStringSliceLiteral(item.Producers) + ",\n")
		b.WriteString("\t\tLogKind: " + strconv.Quote(item.LogKind) + ",\n")
		b.WriteString("\t\tDefaultSeverity: " + strconv.Quote(item.DefaultSeverity) + ",\n")
		b.WriteString("\t\tEnvironments: " + goStringSliceLiteral(item.Environments) + ",\n")
		b.WriteString("\t\tAttributeAllowlist: " + goStringSliceLiteral(item.AttributeAllowlist) + ",\n")
		b.WriteString("\t\tCorrelationKeys: " + goStringSliceLiteral(item.CorrelationKeys) + ",\n")
		b.WriteString("\t\tBackend: " + strconv.Quote(item.Backend) + ",\n")
		b.WriteString("\t\tRetentionDays: " + strconv.Itoa(item.RetentionDays) + ",\n")
		b.WriteString("\t\tSampling: " + strconv.Quote(item.Sampling) + ",\n")
		b.WriteString("\t\tAlert: " + strconv.Quote(item.Alert) + ",\n")
		b.WriteString("\t\tRunbook: " + strconv.Quote(item.Runbook) + ",\n")
		b.WriteString("\t\tPIIClassification: " + strconv.Quote(item.PIIClassification) + ",\n")
		b.WriteString("\t},\n")
	}
	b.WriteString("}\n")
	return b.String()
}

func mustFormatGo(source string) string {
	formatted, err := format.Source([]byte(source))
	exitIf(err)
	return string(formatted)
}

func writeGoSet(b *strings.Builder, name string, values []string) {
	b.WriteString("var " + name + " = map[string]struct{}{\n")
	for _, value := range values {
		b.WriteString("\t" + strconv.Quote(value) + ": {},\n")
	}
	b.WriteString("}\n\n")
}

func writeGoSlice(b *strings.Builder, name string, values []string) {
	b.WriteString("var " + name + " = []string{")
	for index, value := range values {
		if index > 0 {
			b.WriteString(", ")
		}
		b.WriteString(strconv.Quote(value))
	}
	b.WriteString("}\n\n")
}

func writeGoInt(b *strings.Builder, name string, value int) {
	b.WriteString("const " + name + " = " + strconv.Itoa(value) + "\n\n")
}

func writeGoStringMap(b *strings.Builder, name string, values map[string]string) {
	b.WriteString("var " + name + " = map[string]string{\n")
	for _, key := range sortedKeys(values) {
		b.WriteString("\t" + strconv.Quote(key) + ": " + strconv.Quote(values[key]) + ",\n")
	}
	b.WriteString("}\n\n")
}

func goStringSliceLiteral(values []string) string {
	if len(values) == 0 {
		return "nil"
	}
	return "[]string{" + joinQuoted(values, strconv.Quote) + "}"
}

func renderDart(value catalog) string {
	var b strings.Builder
	b.WriteString("// Code generated from contracts/metadata/_shared/runtime_observability.yaml. DO NOT EDIT.\n\n")
	b.WriteString("final class RuntimeLogSignalMetadata {\n")
	b.WriteString("  const RuntimeLogSignalMetadata({required this.owner, required this.producers, required this.logKind, required this.defaultSeverity, required this.environments, required this.attributeAllowlist, required this.correlationKeys, required this.backend, required this.retentionDays, required this.sampling, required this.alert, required this.runbook, required this.piiClassification});\n")
	b.WriteString("  final String owner;\n")
	b.WriteString("  final List<String> producers;\n")
	b.WriteString("  final String logKind;\n")
	b.WriteString("  final String defaultSeverity;\n")
	b.WriteString("  final List<String> environments;\n")
	b.WriteString("  final List<String> attributeAllowlist;\n")
	b.WriteString("  final List<String> correlationKeys;\n")
	b.WriteString("  final String backend;\n")
	b.WriteString("  final int retentionDays;\n")
	b.WriteString("  final String sampling;\n")
	b.WriteString("  final String alert;\n")
	b.WriteString("  final String runbook;\n")
	b.WriteString("  final String piiClassification;\n")
	b.WriteString("}\n\n")
	b.WriteString("abstract final class RuntimeLogCatalog {\n")
	b.WriteString("  static const String schema = " + dartQuote(value.Schema) + ";\n")
	b.WriteString("  static const Set<String> logKinds = <String>{" + joinQuoted(value.LogKinds, dartQuote) + "};\n")
	b.WriteString("  static const Set<String> severityLevels = <String>{" + joinQuoted(value.SeverityLevels, dartQuote) + "};\n")
	b.WriteString("  static const Set<String> signals = <String>{" + joinQuoted(signalIDs(value.Signals), dartQuote) + "};\n")
	b.WriteString("  static const Set<String> forbiddenFields = <String>{" + joinQuoted(value.ForbiddenFields, dartQuote) + "};\n")
	b.WriteString("  static const Map<String, String> failureCodes = <String, String>{\n")
	for _, key := range sortedKeys(value.FailureCodes) {
		b.WriteString("    " + dartQuote(key) + ": " + dartQuote(value.FailureCodes[key]) + ",\n")
	}
	b.WriteString("  };\n")
	b.WriteString("  static const Set<String> forbiddenAttributeKeys = <String>{" + joinQuoted(value.Privacy.ForbiddenAttributeKeys, dartQuote) + "};\n")
	b.WriteString("  static const Set<String> highCardinalityMetricKeys = <String>{" + joinQuoted(value.Privacy.HighCardinalityMetricKeys, dartQuote) + "};\n")
	b.WriteString("  static const Set<String> resourceVersionFields = <String>{" + joinQuoted(value.ResourceVersionFields, dartQuote) + "};\n")
	b.WriteString("  static const int maxBatchItems = " + strconv.Itoa(value.Limits.MaxBatchItems) + ";\n")
	b.WriteString("  static const int maxCanonicalBodyBytes = " + strconv.Itoa(value.Limits.MaxCanonicalBodyBytes) + ";\n")
	b.WriteString("  static const int maxMessageBytes = " + strconv.Itoa(value.Limits.MaxMessageBytes) + ";\n")
	b.WriteString("  static const int maxAttributes = " + strconv.Itoa(value.Limits.MaxAttributes) + ";\n")
	b.WriteString("  static const int maxAttributesBytes = " + strconv.Itoa(value.Limits.MaxAttributesBytes) + ";\n")
	b.WriteString("  static const int maxAttributeKeyLength = " + strconv.Itoa(value.Limits.MaxAttributeKeyLength) + ";\n")
	b.WriteString("  static const int maxAttributeValueLength = " + strconv.Itoa(value.Limits.MaxAttributeValueLength) + ";\n")
	b.WriteString("  static const int rawRetentionDays = " + strconv.Itoa(value.Limits.RawRetentionDays) + ";\n")
	b.WriteString("  static const int appBufferCapacity = " + strconv.Itoa(value.Delivery.AppBufferCapacity) + ";\n")
	b.WriteString("  static const int appDeadLetterCapacity = " + strconv.Itoa(value.Delivery.AppDeadLetterCapacity) + ";\n")
	b.WriteString("  static const int serviceSpoolMaxBatches = " + strconv.Itoa(value.Delivery.ServiceSpoolMaxBatches) + ";\n")
	b.WriteString("  static const int serviceDlqMaxBatches = " + strconv.Itoa(value.Delivery.ServiceDLQMaxBatches) + ";\n")
	b.WriteString("  static const int deliveryTtlHours = " + strconv.Itoa(value.Delivery.TTLHours) + ";\n")
	b.WriteString("  static const int retryBaseSeconds = " + strconv.Itoa(value.Delivery.RetryBaseSeconds) + ";\n")
	b.WriteString("  static const int retryMaxSeconds = " + strconv.Itoa(value.Delivery.RetryMaxSeconds) + ";\n")
	b.WriteString("  static const int retryMaxExponent = " + strconv.Itoa(value.Delivery.RetryMaxExponent) + ";\n")
	b.WriteString("  static const int retryJitterPercent = " + strconv.Itoa(value.Delivery.RetryJitterPercent) + ";\n")
	b.WriteString("  static const List<String> envelopeRequiredFields = <String>[" + joinQuoted(value.Envelope.Required, dartQuote) + "];\n")
	b.WriteString("  static const Set<String> envelopeOptionalFields = <String>{" + joinQuoted(value.Envelope.Optional, dartQuote) + "};\n")
	b.WriteString("  static const List<String> resourceRequiredFields = <String>[" + joinQuoted(value.Envelope.ResourceRequired, dartQuote) + "];\n")
	b.WriteString("  static const Set<String> resourceOptionalFields = <String>{" + joinQuoted(value.Envelope.ResourceOptional, dartQuote) + "};\n")
	b.WriteString("  static const Set<String> correlationOptionalFields = <String>{" + joinQuoted(value.Envelope.CorrelationOptional, dartQuote) + "};\n")
	b.WriteString("  static const Map<String, List<String>> fieldOrder = <String, List<String>>{\n")
	for _, kind := range value.LogKinds {
		b.WriteString("    " + dartQuote(kind) + ": <String>[" + joinQuoted(value.KindFields[kind].Ordered, dartQuote) + "],\n")
	}
	b.WriteString("  };\n")
	b.WriteString("  static const Map<String, String> signalKinds = <String, String>{\n")
	for _, item := range sortedSignals(value.Signals) {
		b.WriteString("    " + dartQuote(item.ID) + ": " + dartQuote(item.LogKind) + ",\n")
	}
	b.WriteString("  };\n")
	b.WriteString("  static const Map<String, String> signalDefaultSeverities = <String, String>{\n")
	for _, item := range sortedSignals(value.Signals) {
		b.WriteString("    " + dartQuote(item.ID) + ": " + dartQuote(item.DefaultSeverity) + ",\n")
	}
	b.WriteString("  };\n")
	b.WriteString("  static const Map<String, RuntimeLogSignalMetadata> signalRegistry = <String, RuntimeLogSignalMetadata>{\n")
	for _, item := range sortedSignals(value.Signals) {
		b.WriteString("    " + dartQuote(item.ID) + ": RuntimeLogSignalMetadata(owner: " + dartQuote(item.Owner) + ", producers: <String>[" + joinQuoted(item.Producers, dartQuote) + "], logKind: " + dartQuote(item.LogKind) + ", defaultSeverity: " + dartQuote(item.DefaultSeverity) + ", environments: <String>[" + joinQuoted(item.Environments, dartQuote) + "], attributeAllowlist: <String>[" + joinQuoted(item.AttributeAllowlist, dartQuote) + "], correlationKeys: <String>[" + joinQuoted(item.CorrelationKeys, dartQuote) + "], backend: " + dartQuote(item.Backend) + ", retentionDays: " + strconv.Itoa(item.RetentionDays) + ", sampling: " + dartQuote(item.Sampling) + ", alert: " + dartQuote(item.Alert) + ", runbook: " + dartQuote(item.Runbook) + ", piiClassification: " + dartQuote(item.PIIClassification) + "),\n")
	}
	b.WriteString("  };\n")
	b.WriteString("}\n")
	return b.String()
}

func renderPython(value catalog) string {
	var b strings.Builder
	b.WriteString("# Code generated from contracts/metadata/_shared/runtime_observability.yaml. DO NOT EDIT.\n\n")
	b.WriteString("OBSERVABILITY_SCHEMA = " + strconv.Quote(value.Schema) + "\n")
	b.WriteString("LOG_KINDS = frozenset((" + joinQuoted(value.LogKinds, strconv.Quote) + ",))\n")
	b.WriteString("LEVELS = frozenset((" + joinQuoted(value.SeverityLevels, strconv.Quote) + ",))\n")
	b.WriteString("SIGNALS = frozenset((" + joinQuoted(signalIDs(value.Signals), strconv.Quote) + ",))\n")
	b.WriteString("FORBIDDEN_FIELDS = frozenset((" + joinQuoted(value.ForbiddenFields, strconv.Quote) + ",))\n")
	b.WriteString("FAILURE_CODES = {\n")
	for _, key := range sortedKeys(value.FailureCodes) {
		b.WriteString("    " + strconv.Quote(key) + ": " + strconv.Quote(value.FailureCodes[key]) + ",\n")
	}
	b.WriteString("}\n")
	b.WriteString("FORBIDDEN_ATTRIBUTE_KEYS = frozenset((" + joinQuoted(value.Privacy.ForbiddenAttributeKeys, strconv.Quote) + ",))\n")
	b.WriteString("HIGH_CARDINALITY_METRIC_KEYS = frozenset((" + joinQuoted(value.Privacy.HighCardinalityMetricKeys, strconv.Quote) + ",))\n")
	b.WriteString("RESOURCE_VERSION_FIELDS = frozenset((" + joinQuoted(value.ResourceVersionFields, strconv.Quote) + ",))\n")
	b.WriteString("MAX_BATCH_ITEMS = " + strconv.Itoa(value.Limits.MaxBatchItems) + "\n")
	b.WriteString("MAX_CANONICAL_BODY_BYTES = " + strconv.Itoa(value.Limits.MaxCanonicalBodyBytes) + "\n")
	b.WriteString("MAX_MESSAGE_BYTES = " + strconv.Itoa(value.Limits.MaxMessageBytes) + "\n")
	b.WriteString("MAX_ATTRIBUTES = " + strconv.Itoa(value.Limits.MaxAttributes) + "\n")
	b.WriteString("MAX_ATTRIBUTES_BYTES = " + strconv.Itoa(value.Limits.MaxAttributesBytes) + "\n")
	b.WriteString("MAX_ATTRIBUTE_KEY_LENGTH = " + strconv.Itoa(value.Limits.MaxAttributeKeyLength) + "\n")
	b.WriteString("MAX_ATTRIBUTE_VALUE_LENGTH = " + strconv.Itoa(value.Limits.MaxAttributeValueLength) + "\n")
	b.WriteString("RAW_RETENTION_DAYS = " + strconv.Itoa(value.Limits.RawRetentionDays) + "\n")
	b.WriteString("APP_BUFFER_CAPACITY = " + strconv.Itoa(value.Delivery.AppBufferCapacity) + "\n")
	b.WriteString("APP_DEAD_LETTER_CAPACITY = " + strconv.Itoa(value.Delivery.AppDeadLetterCapacity) + "\n")
	b.WriteString("SERVICE_SPOOL_MAX_BATCHES = " + strconv.Itoa(value.Delivery.ServiceSpoolMaxBatches) + "\n")
	b.WriteString("SERVICE_DLQ_MAX_BATCHES = " + strconv.Itoa(value.Delivery.ServiceDLQMaxBatches) + "\n")
	b.WriteString("DELIVERY_TTL_HOURS = " + strconv.Itoa(value.Delivery.TTLHours) + "\n")
	b.WriteString("RETRY_BASE_SECONDS = " + strconv.Itoa(value.Delivery.RetryBaseSeconds) + "\n")
	b.WriteString("RETRY_MAX_SECONDS = " + strconv.Itoa(value.Delivery.RetryMaxSeconds) + "\n")
	b.WriteString("RETRY_MAX_EXPONENT = " + strconv.Itoa(value.Delivery.RetryMaxExponent) + "\n")
	b.WriteString("RETRY_JITTER_PERCENT = " + strconv.Itoa(value.Delivery.RetryJitterPercent) + "\n")
	b.WriteString("ENVELOPE_REQUIRED_FIELDS = (" + joinQuoted(value.Envelope.Required, strconv.Quote) + ",)\n")
	b.WriteString("ENVELOPE_OPTIONAL_FIELDS = frozenset((" + joinQuoted(value.Envelope.Optional, strconv.Quote) + ",))\n")
	b.WriteString("RESOURCE_REQUIRED_FIELDS = (" + joinQuoted(value.Envelope.ResourceRequired, strconv.Quote) + ",)\n")
	b.WriteString("RESOURCE_OPTIONAL_FIELDS = frozenset((" + joinQuoted(value.Envelope.ResourceOptional, strconv.Quote) + ",))\n")
	b.WriteString("CORRELATION_OPTIONAL_FIELDS = frozenset((" + joinQuoted(value.Envelope.CorrelationOptional, strconv.Quote) + ",))\n")
	b.WriteString("LOG_FIELD_ORDER = {\n")
	for _, kind := range value.LogKinds {
		b.WriteString("    " + strconv.Quote(kind) + ": (" + joinQuoted(value.KindFields[kind].Ordered, strconv.Quote) + ",),\n")
	}
	b.WriteString("}\n")
	b.WriteString("REQUIRED_KIND_FIELDS = {\n")
	for _, kind := range value.LogKinds {
		b.WriteString("    " + strconv.Quote(kind) + ": frozenset((" + joinQuoted(value.KindFields[kind].Required, strconv.Quote) + ",)),\n")
	}
	b.WriteString("}\n")
	b.WriteString("SIGNAL_LOG_KINDS = {\n")
	for _, item := range sortedSignals(value.Signals) {
		b.WriteString("    " + strconv.Quote(item.ID) + ": " + strconv.Quote(item.LogKind) + ",\n")
	}
	b.WriteString("}\n")
	b.WriteString("SIGNAL_DEFAULT_SEVERITIES = {\n")
	for _, item := range sortedSignals(value.Signals) {
		b.WriteString("    " + strconv.Quote(item.ID) + ": " + strconv.Quote(item.DefaultSeverity) + ",\n")
	}
	b.WriteString("}\n")
	b.WriteString("SIGNAL_REGISTRY = {\n")
	for _, item := range sortedSignals(value.Signals) {
		b.WriteString("    " + strconv.Quote(item.ID) + ": {\n")
		b.WriteString("        \"owner\": " + strconv.Quote(item.Owner) + ",\n")
		b.WriteString("        \"producers\": (" + joinQuoted(item.Producers, strconv.Quote) + ",),\n")
		b.WriteString("        \"logKind\": " + strconv.Quote(item.LogKind) + ",\n")
		b.WriteString("        \"defaultSeverity\": " + strconv.Quote(item.DefaultSeverity) + ",\n")
		b.WriteString("        \"environments\": (" + joinQuoted(item.Environments, strconv.Quote) + ",),\n")
		b.WriteString("        \"attributeAllowlist\": (" + joinQuoted(item.AttributeAllowlist, strconv.Quote) + ",),\n")
		b.WriteString("        \"correlationKeys\": (" + joinQuoted(item.CorrelationKeys, strconv.Quote) + ",),\n")
		b.WriteString("        \"backend\": " + strconv.Quote(item.Backend) + ",\n")
		b.WriteString("        \"retentionDays\": " + strconv.Itoa(item.RetentionDays) + ",\n")
		b.WriteString("        \"sampling\": " + strconv.Quote(item.Sampling) + ",\n")
		b.WriteString("        \"alert\": " + strconv.Quote(item.Alert) + ",\n")
		b.WriteString("        \"runbook\": " + strconv.Quote(item.Runbook) + ",\n")
		b.WriteString("        \"piiClassification\": " + strconv.Quote(item.PIIClassification) + ",\n")
		b.WriteString("    },\n")
	}
	b.WriteString("}\n")
	return b.String()
}

func renderTypeScript(value catalog) string {
	return strings.Join([]string{
		"// Code generated from contracts/metadata/_shared/runtime_observability.yaml. DO NOT EDIT.",
		"",
		"export const runtimeLogCatalog = {",
		"  schema: " + strconv.Quote(value.Schema) + ",",
		"  logKinds: [" + joinQuoted(value.LogKinds, strconv.Quote) + "] as const,",
		"  severityLevels: [" + joinQuoted(value.SeverityLevels, strconv.Quote) + "] as const,",
		"  signals: [" + joinQuoted(signalIDs(value.Signals), strconv.Quote) + "] as const,",
		"  forbiddenFields: [" + joinQuoted(value.ForbiddenFields, strconv.Quote) + "] as const,",
		"  failureCodes: {",
		renderTypeScriptStringMap(value.FailureCodes),
		"  } as const,",
		"  forbiddenAttributeKeys: [" + joinQuoted(value.Privacy.ForbiddenAttributeKeys, strconv.Quote) + "] as const,",
		"  highCardinalityMetricKeys: [" + joinQuoted(value.Privacy.HighCardinalityMetricKeys, strconv.Quote) + "] as const,",
		"  resourceVersionFields: [" + joinQuoted(value.ResourceVersionFields, strconv.Quote) + "] as const,",
		"  maxBatchItems: " + strconv.Itoa(value.Limits.MaxBatchItems) + ",",
		"  maxCanonicalBodyBytes: " + strconv.Itoa(value.Limits.MaxCanonicalBodyBytes) + ",",
		"  maxMessageBytes: " + strconv.Itoa(value.Limits.MaxMessageBytes) + ",",
		"  maxAttributes: " + strconv.Itoa(value.Limits.MaxAttributes) + ",",
		"  maxAttributesBytes: " + strconv.Itoa(value.Limits.MaxAttributesBytes) + ",",
		"  maxAttributeKeyLength: " + strconv.Itoa(value.Limits.MaxAttributeKeyLength) + ",",
		"  maxAttributeValueLength: " + strconv.Itoa(value.Limits.MaxAttributeValueLength) + ",",
		"  rawRetentionDays: " + strconv.Itoa(value.Limits.RawRetentionDays) + ",",
		"  appBufferCapacity: " + strconv.Itoa(value.Delivery.AppBufferCapacity) + ",",
		"  appDeadLetterCapacity: " + strconv.Itoa(value.Delivery.AppDeadLetterCapacity) + ",",
		"  serviceSpoolMaxBatches: " + strconv.Itoa(value.Delivery.ServiceSpoolMaxBatches) + ",",
		"  serviceDlqMaxBatches: " + strconv.Itoa(value.Delivery.ServiceDLQMaxBatches) + ",",
		"  deliveryTtlHours: " + strconv.Itoa(value.Delivery.TTLHours) + ",",
		"  retryBaseSeconds: " + strconv.Itoa(value.Delivery.RetryBaseSeconds) + ",",
		"  retryMaxSeconds: " + strconv.Itoa(value.Delivery.RetryMaxSeconds) + ",",
		"  retryMaxExponent: " + strconv.Itoa(value.Delivery.RetryMaxExponent) + ",",
		"  retryJitterPercent: " + strconv.Itoa(value.Delivery.RetryJitterPercent) + ",",
		"  envelopeRequiredFields: [" + joinQuoted(value.Envelope.Required, strconv.Quote) + "] as const,",
		"  envelopeOptionalFields: [" + joinQuoted(value.Envelope.Optional, strconv.Quote) + "] as const,",
		"  resourceRequiredFields: [" + joinQuoted(value.Envelope.ResourceRequired, strconv.Quote) + "] as const,",
		"  resourceOptionalFields: [" + joinQuoted(value.Envelope.ResourceOptional, strconv.Quote) + "] as const,",
		"  correlationOptionalFields: [" + joinQuoted(value.Envelope.CorrelationOptional, strconv.Quote) + "] as const,",
		"  fieldOrder: {",
		renderTypeScriptFieldOrders(value),
		"  } as const,",
		"  signalKinds: {",
		renderTypeScriptSignalKinds(value),
		"  } as const,",
		"  signalDefaultSeverities: {",
		renderTypeScriptSignalDefaultSeverities(value),
		"  } as const,",
		"  signalRegistry: {",
		renderTypeScriptSignalRegistry(value),
		"  } as const,",
		"} as const;",
		"",
		"export type RuntimeLogKind = (typeof runtimeLogCatalog.logKinds)[number];",
		"export type RuntimeLogSeverity = (typeof runtimeLogCatalog.severityLevels)[number];",
		"export type RuntimeLogSignal = (typeof runtimeLogCatalog.signals)[number];",
		"",
	}, "\n")
}

func renderTypeScriptFieldOrders(value catalog) string {
	var b strings.Builder
	for _, kind := range value.LogKinds {
		b.WriteString("    " + strconv.Quote(kind) + ": [" + joinQuoted(value.KindFields[kind].Ordered, strconv.Quote) + "],\n")
	}
	return strings.TrimSuffix(b.String(), "\n")
}

func renderTypeScriptSignalKinds(value catalog) string {
	var b strings.Builder
	for _, item := range sortedSignals(value.Signals) {
		b.WriteString("    " + strconv.Quote(item.ID) + ": " + strconv.Quote(item.LogKind) + ",\n")
	}
	return strings.TrimSuffix(b.String(), "\n")
}

func renderTypeScriptSignalDefaultSeverities(value catalog) string {
	var b strings.Builder
	for _, item := range sortedSignals(value.Signals) {
		b.WriteString("    " + strconv.Quote(item.ID) + ": " + strconv.Quote(item.DefaultSeverity) + ",\n")
	}
	return strings.TrimSuffix(b.String(), "\n")
}

func renderTypeScriptStringMap(values map[string]string) string {
	var b strings.Builder
	for _, key := range sortedKeys(values) {
		b.WriteString("    " + strconv.Quote(key) + ": " + strconv.Quote(values[key]) + ",\n")
	}
	return strings.TrimSuffix(b.String(), "\n")
}

func renderTypeScriptSignalRegistry(value catalog) string {
	var b strings.Builder
	for _, item := range sortedSignals(value.Signals) {
		b.WriteString("    " + strconv.Quote(item.ID) + ": {\n")
		b.WriteString("      owner: " + strconv.Quote(item.Owner) + ",\n")
		b.WriteString("      producers: [" + joinQuoted(item.Producers, strconv.Quote) + "],\n")
		b.WriteString("      logKind: " + strconv.Quote(item.LogKind) + ",\n")
		b.WriteString("      defaultSeverity: " + strconv.Quote(item.DefaultSeverity) + ",\n")
		b.WriteString("      environments: [" + joinQuoted(item.Environments, strconv.Quote) + "],\n")
		b.WriteString("      attributeAllowlist: [" + joinQuoted(item.AttributeAllowlist, strconv.Quote) + "],\n")
		b.WriteString("      correlationKeys: [" + joinQuoted(item.CorrelationKeys, strconv.Quote) + "],\n")
		b.WriteString("      backend: " + strconv.Quote(item.Backend) + ",\n")
		b.WriteString("      retentionDays: " + strconv.Itoa(item.RetentionDays) + ",\n")
		b.WriteString("      sampling: " + strconv.Quote(item.Sampling) + ",\n")
		b.WriteString("      alert: " + strconv.Quote(item.Alert) + ",\n")
		b.WriteString("      runbook: " + strconv.Quote(item.Runbook) + ",\n")
		b.WriteString("      piiClassification: " + strconv.Quote(item.PIIClassification) + ",\n")
		b.WriteString("    },\n")
	}
	return strings.TrimSuffix(b.String(), "\n")
}

func signalIDs(values []signal) []string {
	out := make([]string, 0, len(values))
	for _, item := range values {
		out = append(out, item.ID)
	}
	sort.Strings(out)
	return out
}

func sortedSignals(values []signal) []signal {
	out := append([]signal(nil), values...)
	sort.Slice(out, func(left, right int) bool {
		return out[left].ID < out[right].ID
	})
	return out
}

func sortedKeys(values map[string]string) []string {
	keys := make([]string, 0, len(values))
	for key := range values {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	return keys
}

func joinQuoted(values []string, quote func(string) string) string {
	out := make([]string, 0, len(values))
	for _, value := range values {
		out = append(out, quote(value))
	}
	return strings.Join(out, ", ")
}

func dartQuote(value string) string {
	return "'" + strings.ReplaceAll(strings.ReplaceAll(value, `\`, `\\`), "'", `\'`) + "'"
}

func exitIf(err error) {
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
