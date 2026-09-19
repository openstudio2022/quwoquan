package main

import (
	"bytes"
	"flag"
	"fmt"
	"go/format"
	"os"
	"path"
	"path/filepath"
	"sort"
	"strings"
	"text/template"

	contractcodegen "quwoquan_service/internal/metadata/codegen"
	"quwoquan_service/internal/metadata/validate"
)

func main() {
	var metadataDir string
	var outputRoot string
	var aggregate string
	var routeService string
	var check bool
	flag.StringVar(&metadataDir, "metadata-dir", "contracts/metadata", "metadata root directory")
	flag.StringVar(&outputRoot, "output-dir", "services/content-service/generated", "content-service generated root directory")
	flag.StringVar(&aggregate, "aggregate", "Post", "aggregate name to generate")
	flag.StringVar(
		&routeService,
		"route-service",
		"content-service",
		"service.name whose complete object route union is generated",
	)
	flag.BoolVar(&check, "check", false, "fail when generated outputs are stale")
	flag.Parse()
	originalOutputRoot := filepath.Clean(outputRoot)
	if check {
		temporaryRoot, err := os.MkdirTemp("", "content-service-codegen-check-")
		if err != nil {
			exitErr(err)
		}
		defer os.RemoveAll(temporaryRoot)
		outputRoot = temporaryRoot
	}

	source, err := contractcodegen.NewSource(metadataDir, validate.ProfileBaseline)
	if err != nil {
		exitErr(fmt.Errorf("compile ContractGraph: %w", err))
	}
	postOutputDir := filepath.Join(outputRoot, "content", "post")
	generator := contractcodegen.NewDomainGenerator(
		source,
		filepath.Clean(postOutputDir),
		contractcodegen.WithObjectFirstRoot(),
		contractcodegen.WithSliceEntityRefs(),
	)
	if err := generator.GenerateDomainModel(aggregate); err != nil {
		exitErr(fmt.Errorf("generate model %s: %w", aggregate, err))
	}
	if err := generator.GenerateDomainEvents(aggregate); err != nil {
		exitErr(fmt.Errorf("generate events %s: %w", aggregate, err))
	}
	routeGroups, err := loadServiceRoutes(source, routeService)
	if err != nil {
		exitErr(fmt.Errorf("load routes for service %s: %w", routeService, err))
	}
	if err := generateContracts(source, routeGroups, outputRoot); err != nil {
		exitErr(fmt.Errorf("generate contracts for service routes %s: %w", routeService, err))
	}
	if err := generatePostPublicationPolicy(source, postOutputDir); err != nil {
		exitErr(fmt.Errorf("generate Post publication policy: %w", err))
	}
	if err := generateOnboardingInterestCatalog(source, postOutputDir); err != nil {
		exitErr(fmt.Errorf("generate onboarding interest catalog: %w", err))
	}
	if err := generateContentMediaUploadPolicy(source, filepath.Join(outputRoot, "media", "media_upload_session")); err != nil {
		exitErr(fmt.Errorf("generate content media upload policy: %w", err))
	}
	if err := generateContentImageVariantPolicy(source, filepath.Join(outputRoot, "media", "media_asset")); err != nil {
		exitErr(fmt.Errorf("generate content image variant policy: %w", err))
	}
	if err := generateContentMediaOriginalAccessPolicy(source, filepath.Join(outputRoot, "media", "original_access_quota")); err != nil {
		exitErr(fmt.Errorf("generate content media original access policy: %w", err))
	}
	if err := generateHTTPScaffold(routeGroups, outputRoot); err != nil {
		exitErr(fmt.Errorf("generate http scaffold for service routes %s: %w", routeService, err))
	}
	if err := generateErrorConstants(source, outputRoot); err != nil {
		exitErr(fmt.Errorf("generate error constants for %s: %w", aggregate, err))
	}
	if check {
		if err := verifyGeneratedTree(outputRoot, originalOutputRoot); err != nil {
			exitErr(err)
		}
		fmt.Printf("verified content-service generated outputs at %s\n", originalOutputRoot)
		return
	}
	fmt.Printf(
		"generated content-service domain for aggregate=%s route-service=%s at %s\n",
		aggregate,
		routeService,
		outputRoot,
	)
}

func verifyGeneratedTree(actualRoot, expectedRoot string) error {
	return filepath.WalkDir(actualRoot, func(path string, entry os.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if entry.IsDir() {
			return nil
		}
		relativePath, err := filepath.Rel(actualRoot, path)
		if err != nil {
			return err
		}
		actual, err := os.ReadFile(path)
		if err != nil {
			return err
		}
		expectedPath := filepath.Join(expectedRoot, relativePath)
		expected, err := os.ReadFile(expectedPath)
		if err != nil {
			return fmt.Errorf("read generated output %s: %w", expectedPath, err)
		}
		if !bytes.Equal(actual, expected) {
			return fmt.Errorf("generated content-service output is stale: %s", expectedPath)
		}
		return nil
	})
}

type contractData struct {
	PackageName    string
	Aggregate      string
	Routes         []routeData
	ContentType    []string
	ListObjectKind []string
	// ContentTypeOwner marks the one object that owns ContentType. The retired
	// projection is emitted only there, so objects unrelated to that enum never
	// carry a retired-value surface.
	ContentTypeOwner   bool
	RetiredContentType []retiredEnumValueData
}

// retiredEnumValueData mirrors one `_shared/types.yaml` retired_enum_values record
// so the projection keeps the retired member bound to the enum it left.
type retiredEnumValueData struct {
	Enum         string
	RetiredValue string
}

type routeData struct {
	ConstName string
	Method    string
	Path      string
	Operation string
}

type operationsYAML struct {
	APIRoutes []serviceRouteYAML `yaml:"api_routes"`
}

type serviceRouteYAML struct {
	Method            string              `yaml:"method"`
	Path              string              `yaml:"path"`
	Operation         string              `yaml:"operation"`
	RequestEntity     string              `yaml:"request_entity"`
	RequestBodyKind   string              `yaml:"request_body_kind"`
	RequestBindings   requestBindingsYAML `yaml:"request_bindings"`
	Pagination        paginationYAML      `yaml:"pagination"`
	RequestBodyFields []string            `yaml:"-"`
	JSONQueries       []jsonQuerySpec     `yaml:"-"`
}

type paginationYAML struct {
	DefaultItems int `yaml:"default_items"`
	MaximumItems int `yaml:"maximum_items"`
}

type requestBindingsYAML struct {
	Path     []requestBindingYAML `yaml:"path"`
	Query    []requestBindingYAML `yaml:"query"`
	Header   []requestBindingYAML `yaml:"header"`
	Injected []requestBindingYAML `yaml:"injected"`
}

type requestBindingYAML struct {
	Name     string `yaml:"name"`
	Field    string `yaml:"field"`
	Required *bool  `yaml:"required"`
	Encoding string `yaml:"encoding"`
	MaxBytes int    `yaml:"max_bytes"`
}

type serviceRequestFieldYAML struct {
	Name           string `yaml:"name"`
	ClientWireName string `yaml:"client_wire_name"`
}

type serviceRequestEntityYAML struct {
	Fields []serviceRequestFieldYAML `yaml:"fields"`
}

type serviceFieldsYAML struct {
	Entity       string                              `yaml:"entity"`
	Fields       []serviceRequestFieldYAML           `yaml:"fields"`
	Entities     map[string]serviceRequestEntityYAML `yaml:"entities"`
	Types        map[string]serviceRequestEntityYAML `yaml:"types"`
	ValueObjects map[string]serviceRequestEntityYAML `yaml:"value_objects"`
	Members      map[string]serviceRequestEntityYAML `yaml:"members"`
}

type objectRouteGroup struct {
	Context    string
	Object     string
	SourcePath string
	Routes     []serviceRouteYAML
}

func generateContracts(
	source *contractcodegen.Source,
	groups []objectRouteGroup,
	outputRoot string,
) error {
	for _, group := range groups {
		if len(group.Routes) == 0 {
			continue
		}
		routes := make([]routeData, 0, len(group.Routes))
		for _, r := range group.Routes {
			if strings.TrimSpace(r.Path) == "" || strings.TrimSpace(r.Method) == "" {
				continue
			}
			routes = append(routes, routeData{
				ConstName: "Route" + toPascal(r.Operation),
				Method:    strings.ToUpper(r.Method),
				Path:      r.Path,
				Operation: r.Operation,
			})
		}
		sort.Slice(routes, func(i, j int) bool { return routes[i].ConstName < routes[j].ConstName })
		var contentTypes []string
		var listObjectKinds []string
		var retiredContentTypes []retiredEnumValueData
		contentTypeOwner := group.Context == "content" && group.Object == "post"
		if contentTypeOwner {
			var shared struct {
				Enums             map[string][]string    `yaml:"enums"`
				RetiredEnumValues []retiredEnumValueYAML `yaml:"retired_enum_values"`
			}
			if err := source.Decode("_shared/types.yaml", &shared); err != nil {
				return err
			}
			contentTypes = shared.Enums["ContentType"]
			listObjectKinds = shared.Enums["ListObjectKind"]
			retiredContentTypes = retiredValuesForEnum(shared.RetiredEnumValues, "ContentType")
		}
		data := contractData{
			PackageName:        "generated",
			Aggregate:          group.Object,
			Routes:             routes,
			ContentType:        contentTypes,
			ListObjectKind:     listObjectKinds,
			ContentTypeOwner:   contentTypeOwner,
			RetiredContentType: retiredContentTypes,
		}
		const tmpl = `// Code generated by tools/codegen_content_service from {{.SourcePath}}. DO NOT EDIT.
package {{.PackageName}}

const (
{{- range .Routes }}
	{{ .ConstName }}Method = "{{ .Method }}"
	{{ .ConstName }}Path = "{{ .Path }}"
{{- end }}
)

var AllowedContentTypes = map[string]struct{}{
{{- range .ContentType }}
	"{{ . }}": {},
{{- end }}
}

// AllowedListObjectKinds 是混排列表信封 objectKind 的 canonical 闭集。读侧按它
// 判定一项是什么对象；未登记的成员必须 fail-closed，不得回落成 post。
var AllowedListObjectKinds = map[string]struct{}{
{{- range .ListObjectKind }}
	"{{ . }}": {},
{{- end }}
}
{{ if .ContentTypeOwner }}
// RetiredEnumValue 把一个退役取值与它离开的 enum 绑定在同一条记录里，退役取值
// 因此不会单独作为字面量存在。
type RetiredEnumValue struct {
	Enum         string
	RetiredValue string
}

// RetiredContentTypeValues 是 _shared/types.yaml retired_enum_values 里 ContentType
// 的 canonical 投影：这些取值曾被持久化、现已不在 AllowedContentTypes 内，只供一次性
// 存量迁移识别 exact 退役输入，不是 wire 兼容通道。
var RetiredContentTypeValues = []RetiredEnumValue{
{{- range .RetiredContentType }}
	{Enum: "{{ .Enum }}", RetiredValue: "{{ .RetiredValue }}"},
{{- end }}
}

// IsRetiredContentType 判定 value 是否为已声明退役的 ContentType 取值。未声明的
// 取值一律不是退役输入，调用方必须按未知类型 fail-closed，不得按媒体猜测。
func IsRetiredContentType(value string) bool {
	for _, declared := range RetiredContentTypeValues {
		if declared.RetiredValue == value {
			return true
		}
	}
	return false
}
{{ end }}`
		t, err := template.New("contracts").Parse(tmpl)
		if err != nil {
			return err
		}
		dataWithSource := struct {
			contractData
			SourcePath string
		}{contractData: data, SourcePath: group.SourcePath}
		var buf bytes.Buffer
		if err := t.Execute(&buf, dataWithSource); err != nil {
			return err
		}
		out := buf.Bytes()
		if formatted, err := format.Source(out); err == nil {
			out = formatted
		}
		targetDir := filepath.Join(outputRoot, group.Context, group.Object)
		if err := os.MkdirAll(targetDir, 0o755); err != nil {
			return err
		}
		if err := os.WriteFile(filepath.Join(targetDir, "contracts.go"), out, 0o644); err != nil {
			return err
		}
	}
	return nil
}

type retiredEnumValueYAML struct {
	Enum         string `yaml:"enum"`
	RetiredValue string `yaml:"retired_value"`
}

// retiredValuesForEnum projects only the records the requested enum owns. A record
// missing either half is dropped rather than half-rendered: the generated set must
// never carry a retired value that no enum claims.
func retiredValuesForEnum(
	records []retiredEnumValueYAML,
	enum string,
) []retiredEnumValueData {
	var result []retiredEnumValueData
	for _, record := range records {
		name := strings.TrimSpace(record.Enum)
		value := strings.TrimSpace(record.RetiredValue)
		if name != enum || value == "" {
			continue
		}
		result = append(result, retiredEnumValueData{Enum: name, RetiredValue: value})
	}
	sort.Slice(result, func(i, j int) bool {
		return result[i].RetiredValue < result[j].RetiredValue
	})
	return result
}

func toPascal(s string) string {
	if strings.TrimSpace(s) == "" {
		return ""
	}
	parts := strings.FieldsFunc(s, func(r rune) bool {
		return r == '_' || r == '-' || r == ' '
	})
	var b strings.Builder
	for _, part := range parts {
		if part == "" {
			continue
		}
		b.WriteString(strings.ToUpper(part[:1]))
		if len(part) > 1 {
			b.WriteString(part[1:])
		}
	}
	return b.String()
}

type routeBindingData struct {
	Method            string
	Path              string
	Operation         string
	QueryBindingNames []string
	RequestBodyFields []string
}

type httpScaffoldData struct {
	Routes                   []routeBindingData
	DispatchOperations       []string
	BodyOperations           []string
	BodyFieldsByOperation    map[string][]string
	GetFeedRouteFound        bool
	GetFeedQueryBindingNames []string
	GetFeedJSONQueries       []jsonQuerySpec
	GetFeedLimitInQuery      bool
	GetFeedDefaultItems      int
	GetFeedMaximumItems      int
}

func findObjectDir(
	source *contractcodegen.Source,
	aggregateName string,
) (string, error) {
	for _, object := range source.Graph().Objects {
		if object.Name == aggregateName {
			return path.Dir(object.SourcePath), nil
		}
	}
	return "", fmt.Errorf("business object %q not found", aggregateName)
}

func deriveRequestBodyFields(
	route serviceRouteYAML,
	objectName string,
	fields serviceFieldsYAML,
) ([]string, error) {
	if strings.TrimSpace(route.RequestBodyKind) != "object" {
		return nil, nil
	}
	requestEntity := strings.TrimSpace(route.RequestEntity)
	if requestEntity == "" {
		return nil, fmt.Errorf(
			"operation %s request_body_kind=object requires request_entity",
			route.Operation,
		)
	}
	entity, err := findServiceRequestEntity(fields, objectName, requestEntity)
	if err != nil {
		return nil, fmt.Errorf("operation %s: %w", route.Operation, err)
	}

	boundFields := make(map[string]string)
	for _, group := range []struct {
		name   string
		values []requestBindingYAML
	}{
		{name: "path", values: route.RequestBindings.Path},
		{name: "query", values: route.RequestBindings.Query},
		{name: "header", values: route.RequestBindings.Header},
		{name: "injected", values: route.RequestBindings.Injected},
	} {
		for _, binding := range group.values {
			field := strings.TrimSpace(binding.Field)
			if field == "" {
				return nil, fmt.Errorf(
					"operation %s request_bindings.%s has an empty field",
					route.Operation,
					group.name,
				)
			}
			if previous, exists := boundFields[field]; exists {
				return nil, fmt.Errorf(
					"operation %s request field %s is bound to both %s and %s",
					route.Operation,
					field,
					previous,
					group.name,
				)
			}
			boundFields[field] = group.name
		}
	}

	bodyFields := make([]string, 0, len(entity.Fields))
	seenNames := make(map[string]struct{}, len(entity.Fields))
	seenWireNames := make(map[string]struct{}, len(entity.Fields))
	for _, field := range entity.Fields {
		name := strings.TrimSpace(field.Name)
		if name == "" {
			return nil, fmt.Errorf(
				"request_entity %s has an empty field",
				requestEntity,
			)
		}
		if _, exists := seenNames[name]; exists {
			return nil, fmt.Errorf(
				"request_entity %s repeats field %s",
				requestEntity,
				name,
			)
		}
		seenNames[name] = struct{}{}
		if _, bound := boundFields[name]; bound {
			continue
		}
		wireName := strings.TrimSpace(field.ClientWireName)
		if wireName == "" {
			wireName = name
		}
		if _, exists := seenWireNames[wireName]; exists {
			return nil, fmt.Errorf(
				"request_entity %s maps multiple body fields to wire name %s",
				requestEntity,
				wireName,
			)
		}
		seenWireNames[wireName] = struct{}{}
		bodyFields = append(bodyFields, wireName)
	}
	if len(bodyFields) == 0 {
		return nil, fmt.Errorf(
			"operation %s request_body_kind=object has no body fields after canonical bindings",
			route.Operation,
		)
	}
	return bodyFields, nil
}

func findServiceRequestEntity(
	fields serviceFieldsYAML,
	objectName string,
	requestEntity string,
) (serviceRequestEntityYAML, error) {
	var matches []serviceRequestEntityYAML
	for _, catalog := range []map[string]serviceRequestEntityYAML{
		fields.Entities,
		fields.Types,
		fields.ValueObjects,
		fields.Members,
	} {
		if entity, exists := catalog[requestEntity]; exists {
			matches = append(matches, entity)
		}
	}
	if strings.TrimSpace(fields.Entity) == requestEntity ||
		(strings.TrimSpace(fields.Entity) == "" && toPascal(objectName) == requestEntity) {
		matches = append(matches, serviceRequestEntityYAML{Fields: fields.Fields})
	}
	if len(matches) == 0 {
		return serviceRequestEntityYAML{}, fmt.Errorf(
			"request_entity %s is absent from fields.yaml",
			requestEntity,
		)
	}
	if len(matches) > 1 {
		return serviceRequestEntityYAML{}, fmt.Errorf(
			"request_entity %s is declared more than once in fields.yaml",
			requestEntity,
		)
	}
	return matches[0], nil
}

func loadServiceRoutes(
	source *contractcodegen.Source,
	serviceName string,
) ([]objectRouteGroup, error) {
	groups := make([]objectRouteGroup, 0)
	byMethodPath := map[string]string{}
	byOperation := map[string]string{}
	serviceName = strings.TrimSpace(serviceName)
	if serviceName == "" {
		return nil, fmt.Errorf("route service name is required")
	}
	domainPrefix := strings.TrimSuffix(serviceName, "-service") + "/"
	for _, operationsPath := range source.Paths(domainPrefix, "operations.yaml") {
		parts := strings.Split(operationsPath, "/")
		if len(parts) != 4 || parts[0]+"/" != domainPrefix || parts[3] != "operations.yaml" {
			return nil, fmt.Errorf("unexpected content operations path %q", operationsPath)
		}
		var operations operationsYAML
		if err := source.Decode(operationsPath, &operations); err != nil {
			return nil, err
		}
		fieldsPath := path.Join(path.Dir(operationsPath), "fields.yaml")
		var fields serviceFieldsYAML
		if source.Has(fieldsPath) {
			if err := source.Decode(fieldsPath, &fields); err != nil {
				return nil, err
			}
		}
		group := objectRouteGroup{
			Context:    parts[1],
			Object:     parts[2],
			SourcePath: operationsPath,
			Routes:     make([]serviceRouteYAML, 0, len(operations.APIRoutes)),
		}
		for _, route := range operations.APIRoutes {
			method := strings.ToUpper(strings.TrimSpace(route.Method))
			routePath := strings.TrimSpace(route.Path)
			operation := strings.TrimSpace(route.Operation)
			if method == "" || routePath == "" || operation == "" {
				continue
			}
			key := method + " " + routePath
			if existing, exists := byMethodPath[key]; exists {
				if existing != operation {
					return nil, fmt.Errorf(
						"route %s is claimed by both %s and %s",
						key,
						existing,
						operation,
					)
				}
				continue
			}
			byMethodPath[key] = operation
			if existing, exists := byOperation[operation]; exists && existing != key {
				return nil, fmt.Errorf(
					"operation %s is bound to both %s and %s",
					operation,
					existing,
					key,
				)
			}
			byOperation[operation] = key
			route.Method = method
			route.Path = routePath
			route.Operation = operation
			requestBodyFields, err := deriveRequestBodyFields(
				route,
				group.Object,
				fields,
			)
			if err != nil {
				return nil, fmt.Errorf("%s: %w", operationsPath, err)
			}
			route.RequestBodyFields = requestBodyFields
			queries, err := resolveJSONQueries(source.Graph(), operationsPath, route)
			if err != nil {
				return nil, err
			}
			route.JSONQueries = queries
			group.Routes = append(group.Routes, route)
		}
		groups = append(groups, group)
	}
	sort.Slice(groups, func(i, j int) bool {
		left := groups[i].Context + "/" + groups[i].Object
		right := groups[j].Context + "/" + groups[j].Object
		return left < right
	})
	return groups, nil
}

func exitErr(err error) {
	fmt.Fprintf(os.Stderr, "codegen_content_service error: %v\n", err)
	os.Exit(1)
}
