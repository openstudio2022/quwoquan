package main

import (
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
	"quwoquan_service/internal/metadata/validate"
)

type eventCatalogFile struct {
	LogTypes          []string                     `yaml:"log_types"`
	NetworkClasses    []string                     `yaml:"network_classes"`
	CommonFields      []string                     `yaml:"common_fields"`
	ContextExtensions []string                     `yaml:"context_extensions"`
	ExtensionFields   map[string]eventExtensionDef `yaml:"extension_fields"`
	Events            []eventCatalogEntry          `yaml:"events"`
}

type eventExtensionDef struct {
	Type          string   `yaml:"type"`
	Minimum       *int     `yaml:"minimum"`
	Maximum       *int     `yaml:"maximum"`
	MaxLength     int      `yaml:"max_length"`
	MaxItems      int      `yaml:"max_items"`
	ItemMaxLength int      `yaml:"item_max_length"`
	Sensitive     bool     `yaml:"sensitive"`
	Enum          []string `yaml:"enum"`
}

type eventCatalogEntry struct {
	EventType          string   `yaml:"event_type"`
	LogType            string   `yaml:"log_type"`
	RequiredExtensions []string `yaml:"required_extensions"`
	OptionalExtensions []string `yaml:"optional_extensions"`
	NormalSampleRate   float64  `yaml:"normal_sample_rate"`
	SlowThresholdMS    int      `yaml:"slow_threshold_ms"`
	AlwaysKeepResults  []string `yaml:"always_keep_results"`
	InternalPriority   string   `yaml:"internal_priority"`
}

type eventRecordFieldsFile struct {
	Fields          []eventRecordField    `yaml:"fields"`
	TypedExtensions typedExtensionBinding `yaml:"typed_extensions"`
}

type eventRecordField struct {
	Name string `yaml:"name"`
}

type typedExtensionBinding struct {
	Catalog            string `yaml:"catalog"`
	Discriminator      string `yaml:"discriminator"`
	DefinitionsKey     string `yaml:"definitions_key"`
	RequiredByEventKey string `yaml:"required_by_event_key"`
	OptionalByEventKey string `yaml:"optional_by_event_key"`
	WireEncoding       string `yaml:"wire_encoding"`
	UnknownFieldPolicy string `yaml:"unknown_field_policy"`
}

type appPagesFile struct {
	Pages            []appPageEntry `yaml:"pages"`
	InternalPages    []appPageEntry `yaml:"internal_pages"`
	FallbackContexts []string       `yaml:"fallback_contexts"`
}

type appPageEntry struct {
	PageName string `yaml:"page_name"`
}

type goldenMetricCatalogFile struct {
	Metrics []goldenMetricEntry `yaml:"metrics"`
}

type rollupCatalogFile struct {
	Jobs        []rollupJobEntry `yaml:"jobs"`
	LateArrival struct {
		AcceptedWindowHours int    `yaml:"accepted_window_hours"`
		Policy              string `yaml:"policy"`
	} `yaml:"late_arrival"`
}

type rollupJobEntry struct {
	RowKind    string               `yaml:"row_kind"`
	Source     string               `yaml:"source"`
	Filter     string               `yaml:"filter"`
	Dimensions []string             `yaml:"dimensions"`
	Measures   []rollupMeasureEntry `yaml:"measures"`
}

type rollupMeasureEntry struct {
	Name      string `yaml:"name"`
	Algebra   string `yaml:"algebra"`
	BucketsMS []int  `yaml:"buckets_ms"`
}

type goldenMetricEntry struct {
	MetricID string `yaml:"metric_id"`
	Business string `yaml:"business"`
	Tier     string `yaml:"tier"`
	Owner    string `yaml:"owner"`
	Source   struct {
		Track                 string            `yaml:"track"`
		EventType             string            `yaml:"event_type"`
		NumeratorEventType    string            `yaml:"numerator_event_type"`
		DenominatorEventType  string            `yaml:"denominator_event_type"`
		NumeratorFilters      map[string]string `yaml:"numerator_filters"`
		DenominatorFilters    map[string]string `yaml:"denominator_filters"`
		NumeratorValueField   string            `yaml:"numerator_value_field"`
		DenominatorValueField string            `yaml:"denominator_value_field"`
		ValueField            string            `yaml:"value_field"`
		NumeratorSeries       string            `yaml:"numerator_series"`
		NumeratorSeriesLabels map[string]string `yaml:"numerator_series_labels"`
		DenominatorSeries     string            `yaml:"denominator_series"`
		Aggregation           string            `yaml:"aggregation"`
	} `yaml:"source"`
	Target struct {
		Operator string  `yaml:"operator"`
		Value    float64 `yaml:"value"`
	} `yaml:"target"`
	Alerting *struct {
		Policy    string  `yaml:"policy"`
		AlertName string  `yaml:"alert_name"`
		Threshold float64 `yaml:"threshold"`
	} `yaml:"alerting"`
	Display *struct {
		PortalLevel string `yaml:"portal_level"`
		Label       string `yaml:"label"`
	} `yaml:"display"`
	FreshnessSeconds int `yaml:"freshness_seconds"`
}

func main() {
	var metadataDir string
	var outputDir string
	flag.StringVar(&metadataDir, "metadata-dir", "contracts/metadata", "metadata root directory")
	flag.StringVar(&outputDir, "output-dir", "services/product-ops-service/generated", "product-ops generated root directory")
	flag.Parse()

	source, err := contractcodegen.NewSource(metadataDir, validate.ProfileBaseline)
	if err != nil {
		exitErr(fmt.Errorf("compile ContractGraph: %w", err))
	}
	errorPaths, err := productOpsObjectErrorPaths(
		source.Paths("ops/product_ops/", "/errors.yaml"),
	)
	if err != nil {
		exitErr(err)
	}
	totalErrors := 0
	for _, sourcePath := range errorPaths {
		parts := strings.Split(sourcePath, "/")
		var errorsFile contractcodegen.ErrorsFile
		if err := source.Decode(sourcePath, &errorsFile); err != nil {
			exitErr(fmt.Errorf("load %s: %w", sourcePath, err))
		}
		rendered := contractcodegen.RenderGoErrorsFile(&errorsFile, contractcodegen.GoErrorsFileOptions{
			Generator:    "tools/codegen_product_ops_service",
			SourcePath:   sourcePath,
			CommentLines: []string{"Object-owned ProductOps errors. Transport semantics come from errors.yaml."},
		})
		formatted, err := format.Source([]byte(rendered))
		if err != nil {
			exitErr(fmt.Errorf("gofmt generated errors from %s: %w", sourcePath, err))
		}
		outPath := filepath.Join(outputDir, parts[1], parts[2], "errors.go")
		if err := os.MkdirAll(filepath.Dir(outPath), 0o755); err != nil {
			exitErr(err)
		}
		if err := os.WriteFile(outPath, formatted, 0o644); err != nil {
			exitErr(err)
		}
		totalErrors += len(errorsFile.Errors)
	}

	var catalog eventCatalogFile
	const eventCatalogPath = "ops/product_ops/event_record/event_catalog.yaml"
	if err := source.Decode(eventCatalogPath, &catalog); err != nil {
		exitErr(fmt.Errorf("load %s: %w", eventCatalogPath, err))
	}
	if err := validateEventCatalog(catalog); err != nil {
		exitErr(err)
	}
	var eventFields eventRecordFieldsFile
	const eventFieldsPath = "ops/product_ops/event_record/fields.yaml"
	if err := source.Decode(eventFieldsPath, &eventFields); err != nil {
		exitErr(fmt.Errorf("load %s: %w", eventFieldsPath, err))
	}
	if err := validateEventRecordFields(eventFields, catalog); err != nil {
		exitErr(err)
	}
	var pages appPagesFile
	const appPagesPath = "_shared/app_pages.yaml"
	if err := source.Decode(appPagesPath, &pages); err != nil {
		exitErr(fmt.Errorf("load %s: %w", appPagesPath, err))
	}
	catalogRendered := renderEventCatalogGo(catalog, pages)
	catalogFormatted, err := format.Source([]byte(catalogRendered))
	if err != nil {
		exitErr(fmt.Errorf("gofmt generated event catalog: %w", err))
	}
	catalogOutPath := filepath.Join(outputDir, "product_ops", "event_record", "event_catalog.go")
	if err := os.MkdirAll(filepath.Dir(catalogOutPath), 0o755); err != nil {
		exitErr(err)
	}
	if err := os.WriteFile(catalogOutPath, catalogFormatted, 0o644); err != nil {
		exitErr(err)
	}

	var goldenCatalog goldenMetricCatalogFile
	const goldenCatalogPath = "ops/product_ops/event_record/golden_metric_catalog.yaml"
	if err := source.Decode(goldenCatalogPath, &goldenCatalog); err != nil {
		exitErr(fmt.Errorf("load %s: %w", goldenCatalogPath, err))
	}
	if err := validateGoldenMetricCatalog(goldenCatalog, catalog); err != nil {
		exitErr(err)
	}
	goldenRendered := renderGoldenMetricCatalogGo(goldenCatalog)
	goldenFormatted, err := format.Source([]byte(goldenRendered))
	if err != nil {
		exitErr(fmt.Errorf("gofmt generated golden metric catalog: %w", err))
	}
	goldenOutPath := filepath.Join(outputDir, "product_ops", "event_record", "golden_metric_catalog.go")
	if err := os.WriteFile(goldenOutPath, goldenFormatted, 0o644); err != nil {
		exitErr(err)
	}

	var rollupCatalog rollupCatalogFile
	const rollupCatalogPath = "ops/product_ops/event_record/rollups.yaml"
	if err := source.Decode(rollupCatalogPath, &rollupCatalog); err != nil {
		exitErr(fmt.Errorf("load %s: %w", rollupCatalogPath, err))
	}
	if err := validateRollupCatalog(rollupCatalog); err != nil {
		exitErr(err)
	}
	rollupRendered := renderRollupCatalogGo(rollupCatalog)
	rollupFormatted, err := format.Source([]byte(rollupRendered))
	if err != nil {
		exitErr(fmt.Errorf("gofmt generated rollup catalog: %w", err))
	}
	rollupOutPath := filepath.Join(outputDir, "product_ops", "event_record", "rollup_catalog.go")
	if err := os.WriteFile(rollupOutPath, rollupFormatted, 0o644); err != nil {
		exitErr(err)
	}
	fmt.Printf(
		"codegen_product_ops_service: wrote %d errors, %d telemetry events, %d golden metrics and %d rollup jobs\n",
		totalErrors, len(catalog.Events), len(goldenCatalog.Metrics), len(rollupCatalog.Jobs),
	)
}

// rollupAlgebraPattern 解析 `name(args)` 形态：fixed_histogram(durationMs)、
// count_distinct_where(requestId, eventType = search_query_submit)、
// count_distinct_row_identity_where(hasError = true) 等。
var rollupAlgebraPattern = regexp.MustCompile(`^([a-z_]+)(?:\((.*)\))?$`)

func splitRollupAlgebra(raw string) (kind, field, where string, err error) {
	matches := rollupAlgebraPattern.FindStringSubmatch(strings.TrimSpace(raw))
	if matches == nil {
		return "", "", "", fmt.Errorf("unparseable rollup algebra %q", raw)
	}
	kind = matches[1]
	arguments := strings.TrimSpace(matches[2])
	switch kind {
	case "count_distinct_row_identity":
		if arguments != "" {
			return "", "", "", fmt.Errorf("%s takes no arguments: %q", kind, raw)
		}
	case "count_distinct_row_identity_where":
		where = arguments
	case "mergeable_hll", "sum", "fixed_histogram":
		field = arguments
	case "count_distinct_where", "fixed_histogram_where":
		separator := strings.Index(arguments, ",")
		if separator < 0 {
			return "", "", "", fmt.Errorf("%s requires field and condition: %q", kind, raw)
		}
		field = strings.TrimSpace(arguments[:separator])
		where = strings.TrimSpace(arguments[separator+1:])
	default:
		return "", "", "", fmt.Errorf("unsupported rollup algebra %q", raw)
	}
	if kind != "count_distinct_row_identity" &&
		kind != "count_distinct_row_identity_where" &&
		field == "" {
		return "", "", "", fmt.Errorf("rollup algebra %q misses its field", raw)
	}
	return kind, field, where, nil
}

func validateRollupCatalog(catalog rollupCatalogFile) error {
	if len(catalog.Jobs) == 0 {
		return fmt.Errorf("rollup catalog must declare at least one job")
	}
	if catalog.LateArrival.AcceptedWindowHours <= 0 ||
		catalog.LateArrival.Policy != "emit_increment_for_business_hour" {
		return fmt.Errorf("rollup catalog late arrival contract drifted")
	}
	seen := map[string]bool{}
	for _, job := range catalog.Jobs {
		if job.RowKind == "" || seen[job.RowKind] {
			return fmt.Errorf("rollup row_kind must be non-empty and unique: %q", job.RowKind)
		}
		seen[job.RowKind] = true
		if job.Source != "raw_records" && job.Source != "runtime_records" {
			return fmt.Errorf("rollup %s has unsupported source %q", job.RowKind, job.Source)
		}
		if len(job.Measures) == 0 {
			return fmt.Errorf("rollup %s declares no measures", job.RowKind)
		}
		for _, measure := range job.Measures {
			kind, _, _, err := splitRollupAlgebra(measure.Algebra)
			if err != nil {
				return fmt.Errorf("rollup %s measure %s: %w", job.RowKind, measure.Name, err)
			}
			needsBuckets := kind == "fixed_histogram" || kind == "fixed_histogram_where"
			if needsBuckets && len(measure.BucketsMS) < 2 {
				return fmt.Errorf(
					"rollup %s measure %s requires at least two histogram buckets",
					job.RowKind, measure.Name,
				)
			}
		}
	}
	return nil
}

func renderRollupCatalogGo(catalog rollupCatalogFile) string {
	var b strings.Builder
	b.WriteString("// Code generated by tools/codegen_product_ops_service from ops/product_ops/event_record/rollups.yaml. DO NOT EDIT.\n")
	b.WriteString("package generated\n\n")
	b.WriteString("type RollupMeasure struct { Name string; Kind string; Field string; Where string; BucketsMS []int }\n")
	b.WriteString("type RollupJob struct { RowKind string; Source string; Filter string; Dimensions []string; Measures []RollupMeasure }\n\n")
	b.WriteString(fmt.Sprintf("const RollupLateArrivalWindowHours = %d\n\n", catalog.LateArrival.AcceptedWindowHours))
	b.WriteString("// RollupCatalog 保持契约声明顺序；写侧聚合执行器按此遍历，禁止手写第二份聚合定义。\n")
	b.WriteString("var RollupCatalog = []RollupJob{\n")
	for _, job := range catalog.Jobs {
		b.WriteString(fmt.Sprintf(
			"{RowKind:%q,Source:%q,Filter:%q,Dimensions:[]string{",
			job.RowKind, job.Source, job.Filter,
		))
		for _, dimension := range job.Dimensions {
			b.WriteString(fmt.Sprintf("%q,", dimension))
		}
		b.WriteString("},Measures:[]RollupMeasure{\n")
		for _, measure := range job.Measures {
			kind, field, where, err := splitRollupAlgebra(measure.Algebra)
			if err != nil {
				exitErr(err)
			}
			b.WriteString(fmt.Sprintf(
				"{Name:%q,Kind:%q,Field:%q,Where:%q,BucketsMS:[]int{",
				measure.Name, kind, field, where,
			))
			for _, bucket := range measure.BucketsMS {
				b.WriteString(fmt.Sprintf("%d,", bucket))
			}
			b.WriteString("}},\n")
		}
		b.WriteString("}},\n")
	}
	b.WriteString("}\n")
	return b.String()
}

func validateGoldenMetricCatalog(golden goldenMetricCatalogFile, catalog eventCatalogFile) error {
	if len(golden.Metrics) == 0 {
		return fmt.Errorf("golden metric catalog must register at least one metric")
	}
	knownEvents := map[string]bool{}
	for _, event := range catalog.Events {
		knownEvents[event.EventType] = true
	}
	seen := map[string]bool{}
	for _, metric := range golden.Metrics {
		if metric.MetricID == "" || seen[metric.MetricID] {
			return fmt.Errorf("golden metric_id must be non-empty and unique: %q", metric.MetricID)
		}
		seen[metric.MetricID] = true
		if metric.Source.Track == "product_telemetry" {
			for _, eventType := range []string{
				metric.Source.EventType,
				metric.Source.NumeratorEventType,
				metric.Source.DenominatorEventType,
			} {
				if eventType != "" && !knownEvents[eventType] {
					return fmt.Errorf(
						"golden metric %s references unknown event %s",
						metric.MetricID, eventType,
					)
				}
			}
		}
		if metric.Display != nil {
			if metric.Display.PortalLevel != "L1" && metric.Display.PortalLevel != "L2" {
				return fmt.Errorf(
					"golden metric %s display.portal_level must be L1 or L2",
					metric.MetricID,
				)
			}
			if strings.TrimSpace(metric.Display.Label) == "" {
				return fmt.Errorf(
					"golden metric %s display.label must be non-empty",
					metric.MetricID,
				)
			}
		}
	}
	return nil
}

func renderGoldenMetricCatalogGo(golden goldenMetricCatalogFile) string {
	var b strings.Builder
	b.WriteString("// Code generated by tools/codegen_product_ops_service from ops/product_ops/event_record/golden_metric_catalog.yaml. DO NOT EDIT.\n")
	b.WriteString("package generated\n\n")
	b.WriteString("type GoldenMetricSource struct { Track string; EventType string; NumeratorEventType string; DenominatorEventType string; NumeratorFilters map[string]string; DenominatorFilters map[string]string; NumeratorValueField string; DenominatorValueField string; ValueField string; NumeratorSeries string; NumeratorSeriesLabels map[string]string; DenominatorSeries string; Aggregation string }\n")
	b.WriteString("type GoldenMetricAlerting struct { Policy string; AlertName string; Threshold float64 }\n")
	b.WriteString("type GoldenMetricDefinition struct { MetricID string; Business string; Tier string; Owner string; Source GoldenMetricSource; TargetOperator string; TargetValue float64; Alerting *GoldenMetricAlerting; PortalLevel string; PortalLabel string; FreshnessSeconds int }\n\n")
	b.WriteString("// GoldenMetricCatalog 保持契约声明顺序；PortalLevel 非空的条目构成\n")
	b.WriteString("// Portal L1/L2 指标成员的唯一真相源。\n")
	b.WriteString("var GoldenMetricCatalog = []GoldenMetricDefinition{\n")
	for _, metric := range golden.Metrics {
		b.WriteString(fmt.Sprintf(
			"{MetricID:%q,Business:%q,Tier:%q,Owner:%q,Source:GoldenMetricSource{Track:%q,EventType:%q,NumeratorEventType:%q,DenominatorEventType:%q,NumeratorFilters:%s,DenominatorFilters:%s,NumeratorValueField:%q,DenominatorValueField:%q,ValueField:%q,NumeratorSeries:%q,NumeratorSeriesLabels:%s,DenominatorSeries:%q,Aggregation:%q},TargetOperator:%q,TargetValue:%s,",
			metric.MetricID, metric.Business, metric.Tier, metric.Owner,
			metric.Source.Track, metric.Source.EventType,
			metric.Source.NumeratorEventType, metric.Source.DenominatorEventType,
			goStringMap(metric.Source.NumeratorFilters),
			goStringMap(metric.Source.DenominatorFilters),
			metric.Source.NumeratorValueField, metric.Source.DenominatorValueField,
			metric.Source.ValueField, metric.Source.NumeratorSeries,
			goStringMap(metric.Source.NumeratorSeriesLabels),
			metric.Source.DenominatorSeries, metric.Source.Aggregation,
			metric.Target.Operator, goFloatLiteral(metric.Target.Value),
		))
		if metric.Alerting != nil {
			b.WriteString(fmt.Sprintf(
				"Alerting:&GoldenMetricAlerting{Policy:%q,AlertName:%q,Threshold:%s},",
				metric.Alerting.Policy, metric.Alerting.AlertName,
				goFloatLiteral(metric.Alerting.Threshold),
			))
		} else {
			b.WriteString("Alerting:nil,")
		}
		portalLevel, portalLabel := "", ""
		if metric.Display != nil {
			portalLevel = metric.Display.PortalLevel
			portalLabel = metric.Display.Label
		}
		b.WriteString(fmt.Sprintf(
			"PortalLevel:%q,PortalLabel:%q,FreshnessSeconds:%d},\n",
			portalLevel, portalLabel, metric.FreshnessSeconds,
		))
	}
	b.WriteString("}\n")
	return b.String()
}

func goStringMap(values map[string]string) string {
	if len(values) == 0 {
		return "nil"
	}
	keys := make([]string, 0, len(values))
	for key := range values {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	var b strings.Builder
	b.WriteString("map[string]string{")
	for _, key := range keys {
		b.WriteString(fmt.Sprintf("%q:%q,", key, values[key]))
	}
	b.WriteString("}")
	return b.String()
}

func goFloatLiteral(value float64) string {
	return strconv.FormatFloat(value, 'g', -1, 64)
}

func productOpsObjectErrorPaths(paths []string) ([]string, error) {
	if len(paths) == 0 {
		return nil, fmt.Errorf("ProductOps metadata has no object-owned errors.yaml")
	}
	result := append([]string(nil), paths...)
	sort.Strings(result)
	for _, sourcePath := range result {
		parts := strings.Split(sourcePath, "/")
		if len(parts) != 4 ||
			parts[0] != "ops" ||
			parts[1] != "product_ops" ||
			strings.TrimSpace(parts[2]) == "" ||
			parts[3] != "errors.yaml" {
			return nil, fmt.Errorf(
				"ProductOps errors must be owned by exactly one object: %q",
				sourcePath,
			)
		}
	}
	return result, nil
}

func validateEventCatalog(catalog eventCatalogFile) error {
	if strings.Join(catalog.CommonFields, ",") != "logType,eventType,sessionId,pageName,occurredAt,deviceManufacturer,deviceModel,appVersion,networkClass" {
		return fmt.Errorf("event catalog common_fields must be the frozen nine-field envelope")
	}
	if strings.Join(catalog.ContextExtensions, ",") != "devicePlatform" {
		return fmt.Errorf("event catalog context_extensions must be [devicePlatform]")
	}
	for _, field := range catalog.ContextExtensions {
		if _, ok := catalog.ExtensionFields[field]; !ok {
			return fmt.Errorf("context extension references unknown extension %s", field)
		}
	}
	seen := map[string]bool{}
	for _, event := range catalog.Events {
		if event.EventType == "" || seen[event.EventType] {
			return fmt.Errorf("event_type must be non-empty and unique: %q", event.EventType)
		}
		seen[event.EventType] = true
		declaredExtensions := map[string]bool{}
		for _, field := range append(append([]string{}, event.RequiredExtensions...), event.OptionalExtensions...) {
			if _, ok := catalog.ExtensionFields[field]; !ok {
				return fmt.Errorf("event %s references unknown extension %s", event.EventType, field)
			}
			declaredExtensions[field] = true
		}
		if len(event.AlwaysKeepResults) > 0 && !declaredExtensions["result"] {
			return fmt.Errorf("event %s always_keep_results requires the result extension", event.EventType)
		}
		seenResults := map[string]bool{}
		for _, result := range event.AlwaysKeepResults {
			if strings.TrimSpace(result) == "" || seenResults[result] {
				return fmt.Errorf("event %s always_keep_results must be non-empty and unique: %q", event.EventType, result)
			}
			seenResults[result] = true
		}
	}
	for name, definition := range catalog.ExtensionFields {
		if len(definition.Enum) == 0 {
			continue
		}
		if definition.Type != "string" {
			return fmt.Errorf("extension %s enum requires string type", name)
		}
		seenValues := map[string]struct{}{}
		for _, value := range definition.Enum {
			if strings.TrimSpace(value) == "" {
				return fmt.Errorf("extension %s enum contains empty value", name)
			}
			if _, exists := seenValues[value]; exists {
				return fmt.Errorf("extension %s enum contains duplicate value %q", name, value)
			}
			seenValues[value] = struct{}{}
		}
	}
	return nil
}

func validateEventRecordFields(fields eventRecordFieldsFile, catalog eventCatalogFile) error {
	rootNames := make([]string, 0, len(fields.Fields))
	for _, field := range fields.Fields {
		rootNames = append(rootNames, strings.TrimSpace(field.Name))
	}
	if strings.Join(rootNames, ",") != strings.Join(catalog.CommonFields, ",") {
		return fmt.Errorf("event record fields must contain only the frozen nine-field envelope in canonical order")
	}
	binding := fields.TypedExtensions
	if binding.Catalog != "event_catalog.yaml" ||
		binding.Discriminator != "eventType" ||
		binding.DefinitionsKey != "extension_fields" ||
		binding.RequiredByEventKey != "required_extensions" ||
		binding.OptionalByEventKey != "optional_extensions" ||
		binding.WireEncoding != "flattened" ||
		binding.UnknownFieldPolicy != "reject" {
		return fmt.Errorf("event record typed_extensions must bind the canonical event catalog without fallback")
	}
	return nil
}

func renderEventCatalogGo(catalog eventCatalogFile, pages appPagesFile) string {
	var b strings.Builder
	b.WriteString("// Code generated by tools/codegen_product_ops_service from ops/product_ops/event_record/event_catalog.yaml. DO NOT EDIT.\n")
	b.WriteString("package generated\n\n")
	b.WriteString("type EventExtensionDefinition struct { Type string; Minimum *int; Maximum *int; MaxLength int; MaxItems int; ItemMaxLength int; Sensitive bool; AllowedValues map[string]struct{} }\n")
	b.WriteString("type EventCatalogDefinition struct { EventType string; LogType string; RequiredExtensions map[string]struct{}; OptionalExtensions map[string]struct{}; NormalSampleRate float64; SlowThresholdMS int; AlwaysKeepResults map[string]struct{}; InternalPriority string }\n\n")
	extensionNames := make([]string, 0, len(catalog.ExtensionFields))
	for name := range catalog.ExtensionFields {
		extensionNames = append(extensionNames, name)
	}
	sort.Strings(extensionNames)
	b.WriteString("type EventRecordInput struct {\n")
	b.WriteString("LogType string `json:\"logType\"`\n")
	b.WriteString("EventType string `json:\"eventType\"`\n")
	b.WriteString("SessionID string `json:\"sessionId\"`\n")
	b.WriteString("PageName string `json:\"pageName\"`\n")
	b.WriteString("OccurredAt string `json:\"occurredAt\"`\n")
	b.WriteString("DeviceManufacturer string `json:\"deviceManufacturer\"`\n")
	b.WriteString("DeviceModel string `json:\"deviceModel\"`\n")
	b.WriteString("AppVersion string `json:\"appVersion\"`\n")
	b.WriteString("NetworkClass string `json:\"networkClass\"`\n")
	for _, name := range extensionNames {
		definition := catalog.ExtensionFields[name]
		if isEventContextExtension(name, catalog.ContextExtensions) {
			b.WriteString(
				fmt.Sprintf(
					"%s string `json:\"%s\"`\n",
					goEventExtensionFieldName(name),
					name,
				),
			)
			continue
		}
		b.WriteString(
			fmt.Sprintf(
				"%s %s `json:\"%s,omitempty\"`\n",
				goEventExtensionFieldName(name),
				goEventExtensionFieldType(definition.Type),
				name,
			),
		)
	}
	b.WriteString("}\n\n")
	b.WriteString("func (input EventRecordInput) ExtensionValues() map[string]any {\n")
	b.WriteString("out := map[string]any{}\n")
	for _, name := range extensionNames {
		field := goEventExtensionFieldName(name)
		if isEventContextExtension(name, catalog.ContextExtensions) {
			b.WriteString(fmt.Sprintf("if input.%s != \"\" { out[%q] = input.%s }\n", field, name, field))
			continue
		}
		if catalog.ExtensionFields[name].Type == "string_list" {
			b.WriteString(fmt.Sprintf("if input.%s != nil { out[%q] = input.%s }\n", field, name, field))
			continue
		}
		b.WriteString(fmt.Sprintf("if input.%s != nil { out[%q] = *input.%s }\n", field, name, field))
	}
	b.WriteString("return out\n}\n\n")
	b.WriteString("var EventCommonFields = []string{")
	for _, field := range catalog.CommonFields {
		b.WriteString(fmt.Sprintf("%q,", field))
	}
	b.WriteString("}\n")
	b.WriteString("var EventContextExtensions = map[string]struct{}{")
	for _, field := range catalog.ContextExtensions {
		b.WriteString(fmt.Sprintf("%q:{},", field))
	}
	b.WriteString("}\n")
	b.WriteString("var EventNetworkClasses = map[string]struct{}{")
	for _, value := range catalog.NetworkClasses {
		b.WriteString(fmt.Sprintf("%q:{},", value))
	}
	b.WriteString("}\n")
	b.WriteString("var EventExtensionFields = map[string]EventExtensionDefinition{\n")
	for _, name := range extensionNames {
		definition := catalog.ExtensionFields[name]
		b.WriteString(fmt.Sprintf("%q:{Type:%q,Minimum:%s,Maximum:%s,MaxLength:%d,MaxItems:%d,ItemMaxLength:%d,Sensitive:%t,AllowedValues:map[string]struct{}{", name, definition.Type, goIntPointer(definition.Minimum), goIntPointer(definition.Maximum), definition.MaxLength, definition.MaxItems, definition.ItemMaxLength, definition.Sensitive))
		for _, value := range definition.Enum {
			b.WriteString(fmt.Sprintf("%q:{},", value))
		}
		b.WriteString("}},\n")
	}
	b.WriteString("}\n")
	b.WriteString("var EventCatalog = map[string]EventCatalogDefinition{\n")
	for _, event := range catalog.Events {
		b.WriteString(fmt.Sprintf("%q:{EventType:%q,LogType:%q,RequiredExtensions:map[string]struct{}{", event.EventType, event.EventType, event.LogType))
		for _, field := range event.RequiredExtensions {
			b.WriteString(fmt.Sprintf("%q:{},", field))
		}
		b.WriteString("},OptionalExtensions:map[string]struct{}{")
		for _, field := range event.OptionalExtensions {
			b.WriteString(fmt.Sprintf("%q:{},", field))
		}
		b.WriteString(fmt.Sprintf("},NormalSampleRate:%g,SlowThresholdMS:%d,AlwaysKeepResults:map[string]struct{}{", event.NormalSampleRate, event.SlowThresholdMS))
		for _, result := range event.AlwaysKeepResults {
			b.WriteString(fmt.Sprintf("%q:{},", result))
		}
		b.WriteString(fmt.Sprintf("},InternalPriority:%q},\n", event.InternalPriority))
	}
	b.WriteString("}\n")
	pageNames := map[string]struct{}{}
	for _, page := range append(pages.Pages, pages.InternalPages...) {
		pageNames[page.PageName] = struct{}{}
	}
	for _, pageName := range pages.FallbackContexts {
		pageNames[pageName] = struct{}{}
	}
	sortedPageNames := make([]string, 0, len(pageNames))
	for pageName := range pageNames {
		sortedPageNames = append(sortedPageNames, pageName)
	}
	sort.Strings(sortedPageNames)
	b.WriteString("var AppPageNames = map[string]struct{}{\n")
	for _, pageName := range sortedPageNames {
		b.WriteString(fmt.Sprintf("%q:{},\n", pageName))
	}
	b.WriteString("}\n")
	return b.String()
}

func isEventContextExtension(name string, contextExtensions []string) bool {
	for _, contextExtension := range contextExtensions {
		if contextExtension == name {
			return true
		}
	}
	return false
}

func goEventExtensionFieldName(name string) string {
	if name == "" {
		return ""
	}
	field := strings.ToUpper(name[:1]) + name[1:]
	field = strings.ReplaceAll(field, "Id", "ID")
	field = strings.ReplaceAll(field, "Ms", "MS")
	field = strings.ReplaceAll(field, "Http", "HTTP")
	field = strings.ReplaceAll(field, "Ttff", "TTFF")
	return field
}

func goEventExtensionFieldType(kind string) string {
	switch kind {
	case "string":
		return "*string"
	case "int":
		return "*int"
	case "double":
		return "*float64"
	case "bool":
		return "*bool"
	case "string_list":
		return "[]string"
	default:
		panic(fmt.Sprintf("unsupported telemetry extension type %q", kind))
	}
}

func goIntPointer(value *int) string {
	if value == nil {
		return "nil"
	}
	return fmt.Sprintf("func(v int) *int { return &v }(%d)", *value)
}

func exitErr(err error) {
	fmt.Fprintf(os.Stderr, "codegen_product_ops_service error: %v\n", err)
	os.Exit(1)
}
