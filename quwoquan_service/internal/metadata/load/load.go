package load

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"strconv"
	"strings"

	"quwoquan_service/internal/metadata/ast"

	"gopkg.in/yaml.v3"
)

var objectTopLevelKeys = stringSet(
	"kind", "description", "identity", "access", "relationships",
	"capabilities", "taggable", "vector_enabled", "members",
	"counter_strategy", "relation_signal", "business_rules", "lifecycle",
	"local_identity_reasons",
	// deferred_operations 是文档性声明：登记对象显式推迟的公开命令与恢复前置条件，
	// 不进入 ContractGraph operation 集合。
	"deferred_operations",
)

var operationsTopLevelKeys = stringSet(
	"api_routes", "runtime_entrypoints", "commercial_defaults", "consumers", "contract_test",
	"delivery_slo", "description", "incoming_call_slo", "privacy_contract",
	"response_list_key", "upstreams", "externalDependencies",
)

// Load 将 metadata 规范化为单一 AST。它只读取业务对象目录，不把控制面域清单计入业务对象。
func Load(metadataDir string) (*ast.Catalog, error) {
	catalog := &ast.Catalog{}
	var loadErrors []error

	err := filepath.WalkDir(metadataDir, func(path string, entry fs.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if entry.IsDir() {
			name := entry.Name()
			if name == ".git" || name == "test_fixtures" {
				return filepath.SkipDir
			}
			if path != metadataDir && strings.HasPrefix(name, "_") {
				return filepath.SkipDir
			}
			return nil
		}
		if entry.Name() != "object.yaml" {
			return nil
		}

		object, objectErr := loadObject(metadataDir, path)
		if objectErr != nil {
			loadErrors = append(loadErrors, objectErr)
			return nil
		}
		catalog.Objects = append(catalog.Objects, object)

		objectDir := filepath.Dir(path)
		operationsPath := filepath.Join(objectDir, "operations.yaml")
		if _, statErr := os.Stat(operationsPath); statErr == nil {
			operations, runtimeEntrypoints, serviceErr := loadService(
				metadataDir,
				operationsPath,
				object,
			)
			if serviceErr != nil {
				loadErrors = append(loadErrors, serviceErr)
			} else {
				catalog.Operations = append(catalog.Operations, operations...)
				catalog.RuntimeEntrypoints = append(
					catalog.RuntimeEntrypoints,
					runtimeEntrypoints...,
				)
			}
		}
		projections, _, projectionErr := loadProjections(metadataDir, objectDir, object)
		if projectionErr != nil {
			loadErrors = append(loadErrors, projectionErr)
		} else {
			catalog.Projections = append(catalog.Projections, projections...)
		}
		return nil
	})
	if err != nil {
		loadErrors = append(loadErrors, err)
	}
	collectSourceDigests(catalog, metadataDir, &loadErrors)
	deriveBusinessObjectMaps(catalog, &loadErrors)
	if governanceErr := loadMetadataGovernance(metadataDir, catalog); governanceErr != nil {
		loadErrors = append(loadErrors, governanceErr)
	}
	if len(loadErrors) > 0 {
		return nil, errors.Join(loadErrors...)
	}
	return catalog, nil
}

func collectSourceDigests(catalog *ast.Catalog, metadataDir string, errs *[]error) {
	err := filepath.WalkDir(metadataDir, func(path string, entry fs.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if entry.IsDir() {
			if entry.Name() == ".git" {
				return filepath.SkipDir
			}
			return nil
		}
		switch strings.ToLower(filepath.Ext(entry.Name())) {
		case ".yaml", ".yml", ".json":
			addSourceDocument(catalog, metadataDir, path, errs)
		}
		return nil
	})
	if err != nil {
		*errs = append(*errs, err)
	}
}

func loadObject(metadataDir, path string) (ast.Object, error) {
	top, err := loadTopLevelMapping(path)
	if err != nil {
		return ast.Object{}, err
	}
	if err := rejectUnknownTopLevel(path, top, objectTopLevelKeys); err != nil {
		return ast.Object{}, err
	}

	relative := relativePath(metadataDir, path)
	segments := strings.Split(relative, "/")
	if len(segments) != 4 || segments[3] != "object.yaml" {
		return ast.Object{}, fmt.Errorf(
			"%s: object metadata path must be <domain>/<context>/<object>/object.yaml",
			path,
		)
	}
	domain := segments[0]
	objectSegment := strings.ReplaceAll(segments[2], "-", "_")
	name := pascalCaseIdentifier(objectSegment)
	id := domain + "." + objectSegment

	kind, explicit, err := resolveObjectKind(top)
	if err != nil {
		return ast.Object{}, fmt.Errorf("%s: %w", path, err)
	}
	object := ast.Object{
		ID:             id,
		Domain:         domain,
		Name:           name,
		Kind:           kind,
		KindExplicit:   explicit,
		AggregateOwner: "",
		SourcePath:     relativePath(metadataDir, path),
	}
	if storageTop, storageErr := loadOptionalTopLevelMapping(filepath.Join(filepath.Dir(path), "storage.yaml")); storageErr != nil {
		return ast.Object{}, storageErr
	} else if storageTop != nil {
		object.StorageBackend = scalarString(storageTop["backend"])
	}
	if members := top["members"]; members != nil {
		object.Members, err = decodeMembers(members)
		if err != nil {
			return ast.Object{}, fmt.Errorf("%s: members: %w", path, err)
		}
		for index := range object.Members {
			object.Members[index].AggregateOwner = object.Name
		}
	}
	if deferred := top["deferred_operations"]; deferred != nil {
		mapping, err := mappingFromNode(deferred)
		if err != nil {
			return ast.Object{}, fmt.Errorf("%s: deferred_operations: %w", path, err)
		}
		if operations := mapping["operations"]; operations != nil {
			if operations.Kind != yaml.SequenceNode {
				return ast.Object{}, fmt.Errorf(
					"%s: deferred_operations.operations must be a sequence",
					path,
				)
			}
			for _, item := range operations.Content {
				if name := strings.TrimSpace(item.Value); name != "" {
					object.DeferredOperations = append(object.DeferredOperations, name)
				}
			}
		}
		if strings.TrimSpace(scalarString(mapping["reason"])) == "" ||
			len(object.DeferredOperations) == 0 {
			return ast.Object{}, fmt.Errorf(
				"%s: deferred_operations requires a non-empty reason and operations",
				path,
			)
		}
	}
	return object, nil
}

func decodeDDDLayerMapping(node *yaml.Node) (ast.DDDLayerMapping, error) {
	mapping, err := mappingFromNode(node)
	if err != nil {
		return ast.DDDLayerMapping{}, err
	}
	return ast.DDDLayerMapping{
		DomainModel:  scalarString(mapping["domain_model"]),
		Ports:        scalarString(mapping["ports"]),
		Application:  scalarString(mapping["application"]),
		Persistence:  scalarString(mapping["persistence"]),
		AdapterREST:  scalarString(mapping["adapter_rest"]),
		AdapterEvent: scalarString(mapping["adapter_event"]),
	}, nil
}

func resolveObjectKind(top map[string]*yaml.Node) (ast.ObjectKind, bool, error) {
	if raw := scalarString(top["kind"]); raw != "" {
		kind := ast.ObjectKind(raw)
		if !validObjectKind(kind) {
			return "", true, fmt.Errorf("invalid object_kind %q", raw)
		}
		return kind, true, nil
	}
	return "", false, fmt.Errorf("kind is required")
}

func validObjectKind(kind ast.ObjectKind) bool {
	switch kind {
	case ast.ObjectKindAggregateRoot,
		ast.ObjectKindProjection,
		ast.ObjectKindExternalReference,
		ast.ObjectKindAppendOnlyFact,
		ast.ObjectKindRuntimeSession:
		return true
	default:
		return false
	}
}

func decodeMembers(node *yaml.Node) ([]ast.Member, error) {
	if node.Kind == yaml.ScalarNode && node.Tag == "!!null" {
		return nil, nil
	}
	if node.Kind != yaml.MappingNode {
		return nil, fmt.Errorf("must be a mapping keyed by member name")
	}
	members := make([]ast.Member, 0, len(node.Content)/2)
	for index := 0; index < len(node.Content); index += 2 {
		name := strings.TrimSpace(node.Content[index].Value)
		mapping, err := mappingFromNode(node.Content[index+1])
		if err != nil {
			return nil, err
		}
		member := ast.Member{
			Name:        name,
			Cardinality: scalarString(mapping["cardinality"]),
		}
		if raw := scalarString(mapping["kind"]); raw != "" {
			member.Kind = ast.ObjectKind(raw)
			if member.Kind != ast.ObjectKindOwnedEntity && member.Kind != ast.ObjectKindValueObject {
				return nil, fmt.Errorf("member %q has invalid object_kind %q", member.Name, raw)
			}
		}
		if raw := scalarString(mapping["max_cardinality"]); raw != "" {
			value, parseErr := strconv.Atoi(raw)
			if parseErr != nil {
				return nil, fmt.Errorf("member %q max_cardinality: %w", member.Name, parseErr)
			}
			member.MaxCardinality = value
		}
		if member.Name == "" {
			return nil, fmt.Errorf("member entity is required")
		}
		members = append(members, member)
	}
	return members, nil
}

type serviceDocument struct {
	CommercialDefaults commercialDocument          `yaml:"commercial_defaults"`
	APIRoutes          []routeDocument             `yaml:"api_routes"`
	RuntimeEntrypoints []runtimeEntrypointDocument `yaml:"runtime_entrypoints"`
}

type commercialDocument struct {
	Status      string `yaml:"status"`
	BlockReason string `yaml:"block_reason"`
	GapID       string `yaml:"gap_id"`
	TargetStory string `yaml:"target_story"`
}

type runtimeEntrypointDocument struct {
	Name        string `yaml:"name"`
	RuntimeKind string `yaml:"kind"`
	Phase       string `yaml:"phase"`
	Application struct {
		Kind         string `yaml:"kind"`
		Facet        string `yaml:"facet"`
		Method       string `yaml:"method"`
		SessionOwner string `yaml:"session_owner"`
	} `yaml:"application"`
}

type routeDocument struct {
	Method           string                    `yaml:"method"`
	Path             string                    `yaml:"path"`
	Operation        string                    `yaml:"operation"`
	RequestEntity    string                    `yaml:"request_entity"`
	RequestBodyKind  string                    `yaml:"request_body_kind"`
	RequestBindings  *requestBindingsDocument  `yaml:"request_bindings"`
	RequestConstants *requestConstantsDocument `yaml:"request_constants"`
	PathParams       any                       `yaml:"path_params"`
	QueryParams      any                       `yaml:"query_params"`
	RequestFields    any                       `yaml:"request_fields"`
	Headers          any                       `yaml:"headers"`
	ResponseEntity   string                    `yaml:"response_entity"`
	ResponseBody     string                    `yaml:"response_body"`
	ResponseBodyKind string                    `yaml:"response_body_kind"`
	Actor            string                    `yaml:"actor"`
	Security         map[string]string         `yaml:"security"`
	Authorization    struct {
		Principal       string   `yaml:"principal"`
		Scopes          []string `yaml:"scopes"`
		Permissions     []string `yaml:"permissions"`
		OwnershipPolicy string   `yaml:"ownership_policy"`
	} `yaml:"authorization"`
	Commercial  commercialDocument `yaml:"commercial"`
	Reliability struct {
		TimeoutMilliseconds int    `yaml:"timeout_ms"`
		Cancellation        string `yaml:"cancellation"`
		RetryMode           string `yaml:"retry_mode"`
		MaxAttempts         int    `yaml:"max_attempts"`
		Idempotency         string `yaml:"idempotency"`
	} `yaml:"reliability"`
	Pagination *struct {
		DefaultItems int `yaml:"default_items"`
		MaximumItems int `yaml:"maximum_items"`
	} `yaml:"pagination"`
	ResponseAdmission *struct {
		MaximumBodyBytes int `yaml:"maximum_body_bytes"`
	} `yaml:"response_admission"`
	Concurrency struct {
		VersionPrecondition string `yaml:"version_precondition"`
	} `yaml:"concurrency"`
	ErrorCodes []string `yaml:"error_codes"`
	Privacy    struct {
		RequestClassification  string `yaml:"request_classification"`
		ResponseClassification string `yaml:"response_classification"`
		LogPolicy              string `yaml:"log_policy"`
	} `yaml:"privacy"`
	Telemetry struct {
		Metric     string   `yaml:"metric"`
		Trace      bool     `yaml:"trace"`
		Attributes []string `yaml:"attributes"`
	} `yaml:"telemetry"`
	SLO struct {
		LatencyP95Milliseconds int     `yaml:"latency_p95_ms"`
		AvailabilityPercent    float64 `yaml:"availability_percent"`
	} `yaml:"slo"`
	ClientContract *struct {
		DartImport      string `yaml:"dart_import"`
		ResponseType    string `yaml:"response_type"`
		ResponseDecoder string `yaml:"response_decoder"`
		RequestType     any    `yaml:"request_type"`
		RequestEncoder  any    `yaml:"request_encoder"`
		PathBindings    any    `yaml:"path_bindings"`
		QueryBindings   any    `yaml:"query_bindings"`
		HeaderBindings  any    `yaml:"header_bindings"`
	} `yaml:"client_contract"`
	Application struct {
		Kind            string `yaml:"kind"`
		Facet           string `yaml:"facet"`
		Method          string `yaml:"method"`
		AggregateOwner  string `yaml:"aggregate_owner"`
		AppendSink      string `yaml:"append_sink"`
		MutationTarget  string `yaml:"mutation_target"`
		InvariantTarget string `yaml:"invariant_target"`
		SessionOwner    string `yaml:"session_owner"`
		Reader          string `yaml:"reader"`
		Slice           string `yaml:"slice"`
	} `yaml:"application"`
}

type requestBindingsDocument struct {
	Path     []requestBindingDocument `yaml:"path"`
	Query    []requestBindingDocument `yaml:"query"`
	Header   []requestBindingDocument `yaml:"header"`
	Injected []requestBindingDocument `yaml:"injected"`
}

type requestBindingDocument struct {
	Name     string `yaml:"name"`
	Field    string `yaml:"field"`
	Required *bool  `yaml:"required"`
}

type requestConstantsDocument struct {
	Body []requestConstantDocument `yaml:"body"`
}

type requestConstantDocument struct {
	Name  string `yaml:"name"`
	Value any    `yaml:"value"`
}

func loadService(
	metadataDir,
	path string,
	object ast.Object,
) ([]ast.Operation, []ast.RuntimeEntrypoint, error) {
	top, err := loadTopLevelMapping(path)
	if err != nil {
		return nil, nil, err
	}
	if err := rejectUnknownTopLevel(path, top, operationsTopLevelKeys); err != nil {
		return nil, nil, err
	}
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, nil, err
	}
	var document serviceDocument
	if err := yaml.Unmarshal(data, &document); err != nil {
		return nil, nil, fmt.Errorf("%s: %w", path, err)
	}
	operations := make([]ast.Operation, 0, len(document.APIRoutes))
	for index, route := range document.APIRoutes {
		localID := strings.TrimSpace(route.Operation)
		if localID == "" {
			return nil, nil, fmt.Errorf("%s: api_routes[%d].operation is required", path, index)
		}
		kind, explicit, kindErr := resolveOperationKind(route.Method, route.Application.Kind)
		if kindErr != nil {
			return nil, nil, fmt.Errorf("%s: operation %s: %w", path, localID, kindErr)
		}
		actor := strings.TrimSpace(route.Actor)
		if actor == "" {
			actor = inferActorRequirement(route.Security)
		}
		commercial := mergeCommercialBinding(
			document.CommercialDefaults,
			route.Commercial,
		)
		commercialStatus := strings.TrimSpace(commercial.Status)
		commercialExplicit := commercialStatus != ""
		commercialBlockReason := strings.TrimSpace(commercial.BlockReason)
		if commercialStatus == "" {
			commercialStatus = "blocked"
			commercialBlockReason = "missing commercial operation binding"
		}
		var clientContract *ast.ClientContract
		var clientBindingOverrides []string
		if route.ClientContract != nil {
			if route.ClientContract.PathBindings != nil {
				clientBindingOverrides = append(clientBindingOverrides, "path_bindings")
			}
			if route.ClientContract.QueryBindings != nil {
				clientBindingOverrides = append(clientBindingOverrides, "query_bindings")
			}
			if route.ClientContract.HeaderBindings != nil {
				clientBindingOverrides = append(clientBindingOverrides, "header_bindings")
			}
			if route.ClientContract.RequestType != nil {
				clientBindingOverrides = append(clientBindingOverrides, "request_type")
			}
			if route.ClientContract.RequestEncoder != nil {
				clientBindingOverrides = append(clientBindingOverrides, "request_encoder")
			}
			clientContract = &ast.ClientContract{
				DartImport:      strings.TrimSpace(route.ClientContract.DartImport),
				ResponseType:    strings.TrimSpace(route.ClientContract.ResponseType),
				ResponseDecoder: strings.TrimSpace(route.ClientContract.ResponseDecoder),
			}
		}
		var requestBindings *ast.RequestBindings
		if route.RequestBindings != nil {
			requestBindings = &ast.RequestBindings{
				Path:  normalizeRequestBindings(route.RequestBindings.Path),
				Query: normalizeRequestBindings(route.RequestBindings.Query),
				Header: normalizeRequestBindings(
					route.RequestBindings.Header,
				),
				Injected: normalizeRequestBindings(
					route.RequestBindings.Injected,
				),
			}
		}
		var requestConstants *ast.RequestConstants
		if route.RequestConstants != nil {
			requestConstants = &ast.RequestConstants{
				Body: normalizeRequestConstants(route.RequestConstants.Body),
			}
		}
		legacyRequestKeys := make([]string, 0, 4)
		if route.PathParams != nil {
			legacyRequestKeys = append(legacyRequestKeys, "path_params")
		}
		if route.QueryParams != nil {
			legacyRequestKeys = append(legacyRequestKeys, "query_params")
		}
		if route.RequestFields != nil {
			legacyRequestKeys = append(legacyRequestKeys, "request_fields")
		}
		if route.Headers != nil {
			legacyRequestKeys = append(legacyRequestKeys, "headers")
		}
		var pagination *ast.PaginationPolicy
		if route.Pagination != nil {
			pagination = &ast.PaginationPolicy{
				DefaultItems: route.Pagination.DefaultItems,
				MaximumItems: route.Pagination.MaximumItems,
			}
		}
		var responseAdmission *ast.ResponseAdmissionPolicy
		if route.ResponseAdmission != nil {
			responseAdmission = &ast.ResponseAdmissionPolicy{
				MaximumBodyBytes: route.ResponseAdmission.MaximumBodyBytes,
			}
		}
		operations = append(operations, ast.Operation{
			ID:                     object.ID + "." + localID,
			LocalID:                localID,
			Domain:                 object.Domain,
			ObjectID:               object.ID,
			Method:                 strings.ToUpper(strings.TrimSpace(route.Method)),
			PathTemplate:           strings.TrimSpace(route.Path),
			Kind:                   kind,
			KindExplicit:           explicit,
			Facet:                  strings.TrimSpace(route.Application.Facet),
			FacadeMethod:           strings.TrimSpace(route.Application.Method),
			AggregateOwner:         strings.TrimSpace(route.Application.AggregateOwner),
			AppendSink:             strings.TrimSpace(route.Application.AppendSink),
			MutationTarget:         strings.TrimSpace(route.Application.MutationTarget),
			InvariantTarget:        strings.TrimSpace(route.Application.InvariantTarget),
			SessionOwner:           strings.TrimSpace(route.Application.SessionOwner),
			Reader:                 strings.TrimSpace(route.Application.Reader),
			Slice:                  strings.TrimSpace(route.Application.Slice),
			ActorRequirement:       actor,
			RequestEntity:          strings.TrimSpace(route.RequestEntity),
			RequestBodyKind:        strings.TrimSpace(route.RequestBodyKind),
			RequestBindings:        requestBindings,
			RequestConstants:       requestConstants,
			LegacyRequestKeys:      legacyRequestKeys,
			ClientBindingOverrides: clientBindingOverrides,
			ResponseEntity:         strings.TrimSpace(route.ResponseEntity),
			ResponseBody:           strings.TrimSpace(route.ResponseBody),
			ResponseBodyKind:       strings.TrimSpace(route.ResponseBodyKind),
			SourcePath:             relativePath(metadataDir, path),
			Security:               route.Security,
			AuthMode:               resolveAuthMode(route.Security),
			Principal: strings.TrimSpace(
				route.Authorization.Principal,
			),
			Scopes:      trimStrings(route.Authorization.Scopes),
			Permissions: trimStrings(route.Authorization.Permissions),
			OwnershipPolicy: strings.TrimSpace(
				route.Authorization.OwnershipPolicy,
			),
			Commercial: ast.CommercialBinding{
				Status:      commercialStatus,
				Explicit:    commercialExplicit,
				BlockReason: commercialBlockReason,
				GapID:       strings.TrimSpace(commercial.GapID),
				TargetStory: strings.TrimSpace(commercial.TargetStory),
			},
			Reliability: ast.ReliabilityPolicy{
				TimeoutMilliseconds: route.Reliability.TimeoutMilliseconds,
				Cancellation: strings.TrimSpace(
					route.Reliability.Cancellation,
				),
				RetryMode:   strings.TrimSpace(route.Reliability.RetryMode),
				MaxAttempts: route.Reliability.MaxAttempts,
				Idempotency: strings.TrimSpace(
					route.Reliability.Idempotency,
				),
			},
			Pagination:        pagination,
			ResponseAdmission: responseAdmission,
			Concurrency: ast.ConcurrencyPolicy{
				VersionPrecondition: ast.VersionPrecondition(strings.TrimSpace(
					route.Concurrency.VersionPrecondition,
				)),
			},
			ErrorCodes: trimStrings(route.ErrorCodes),
			Privacy: ast.PrivacyPolicy{
				RequestClassification: strings.TrimSpace(
					route.Privacy.RequestClassification,
				),
				ResponseClassification: strings.TrimSpace(
					route.Privacy.ResponseClassification,
				),
				LogPolicy: strings.TrimSpace(route.Privacy.LogPolicy),
			},
			Telemetry: ast.TelemetryPolicy{
				Metric:     strings.TrimSpace(route.Telemetry.Metric),
				Trace:      route.Telemetry.Trace,
				Attributes: trimStrings(route.Telemetry.Attributes),
			},
			SLO: ast.SLOPolicy{
				LatencyP95Milliseconds: route.SLO.LatencyP95Milliseconds,
				AvailabilityPercent:    route.SLO.AvailabilityPercent,
			},
			ClientContract: clientContract,
		})
	}
	runtimeEntrypoints := make(
		[]ast.RuntimeEntrypoint,
		0,
		len(document.RuntimeEntrypoints),
	)
	for index, entrypoint := range document.RuntimeEntrypoints {
		localID := strings.TrimSpace(entrypoint.Name)
		if localID == "" {
			return nil, nil, fmt.Errorf(
				"%s: runtime_entrypoints[%d].name is required",
				path,
				index,
			)
		}
		applicationKind, _, kindErr := resolveOperationKind(
			"",
			strings.TrimSpace(entrypoint.Application.Kind),
		)
		if kindErr != nil {
			return nil, nil, fmt.Errorf(
				"%s: runtime entrypoint %s: %w",
				path,
				localID,
				kindErr,
			)
		}
		runtimeEntrypoints = append(runtimeEntrypoints, ast.RuntimeEntrypoint{
			ID:              object.ID + "." + localID,
			LocalID:         localID,
			Domain:          object.Domain,
			ObjectID:        object.ID,
			RuntimeKind:     strings.TrimSpace(entrypoint.RuntimeKind),
			Phase:           strings.TrimSpace(entrypoint.Phase),
			ApplicationKind: applicationKind,
			Facet:           strings.TrimSpace(entrypoint.Application.Facet),
			FacadeMethod:    strings.TrimSpace(entrypoint.Application.Method),
			SessionOwner:    strings.TrimSpace(entrypoint.Application.SessionOwner),
			SourcePath:      relativePath(metadataDir, path),
		})
	}
	return operations, runtimeEntrypoints, nil
}

func normalizeRequestBindings(values []requestBindingDocument) []ast.RequestBinding {
	result := make([]ast.RequestBinding, 0, len(values))
	for _, value := range values {
		result = append(result, ast.RequestBinding{
			Name:     strings.TrimSpace(value.Name),
			Field:    strings.TrimSpace(value.Field),
			Required: value.Required,
		})
	}
	return result
}

func normalizeRequestConstants(values []requestConstantDocument) []ast.RequestConstant {
	result := make([]ast.RequestConstant, 0, len(values))
	for _, value := range values {
		result = append(result, ast.RequestConstant{
			Name:  strings.TrimSpace(value.Name),
			Value: value.Value,
		})
	}
	return result
}

func mergeCommercialBinding(
	defaults commercialDocument,
	override commercialDocument,
) commercialDocument {
	result := defaults
	if strings.TrimSpace(override.Status) != "" {
		result.Status = override.Status
		result.BlockReason = override.BlockReason
		result.GapID = override.GapID
		result.TargetStory = override.TargetStory
	}
	return result
}

func resolveOperationKind(method, explicit string) (ast.OperationKind, bool, error) {
	if explicit != "" {
		kind := ast.OperationKind(explicit)
		if kind != ast.OperationKindCommand &&
			kind != ast.OperationKindQuery &&
			kind != ast.OperationKindSession {
			return "", true, fmt.Errorf("invalid application.kind %q", explicit)
		}
		return kind, true, nil
	}
	if strings.EqualFold(strings.TrimSpace(method), "GET") {
		return ast.OperationKindQuery, false, nil
	}
	return ast.OperationKindCommand, false, nil
}

func inferActorRequirement(security map[string]string) string {
	authMode := resolveAuthMode(security)
	switch authMode {
	case "required":
		return "persona"
	case "optional":
		return "persona_or_device"
	default:
		return "unspecified"
	}
}

func resolveAuthMode(security map[string]string) string {
	authMode := strings.TrimSpace(security["auth_mode"])
	switch strings.ToLower(authMode) {
	case "public", "optional", "required":
		return strings.ToLower(authMode)
	default:
		return "deny"
	}
}

func trimStrings(values []string) []string {
	result := make([]string, 0, len(values))
	for _, value := range values {
		if trimmed := strings.TrimSpace(value); trimmed != "" {
			result = append(result, trimmed)
		}
	}
	return result
}

func loadProjections(metadataDir, objectDir string, object ast.Object) ([]ast.Projection, []string, error) {
	projectionDir := filepath.Join(objectDir, "projections")
	info, err := os.Stat(projectionDir)
	if errors.Is(err, os.ErrNotExist) {
		return nil, nil, nil
	}
	if err != nil {
		return nil, nil, err
	}
	if !info.IsDir() {
		return nil, nil, fmt.Errorf("%s: projections must be a directory", projectionDir)
	}

	var projections []ast.Projection
	var projectionPaths []string
	err = filepath.WalkDir(projectionDir, func(path string, entry fs.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if entry.IsDir() || filepath.Ext(entry.Name()) != ".yaml" {
			return nil
		}
		top, loadErr := loadTopLevelMapping(path)
		if loadErr != nil {
			return loadErr
		}
		readModel := scalarString(top["read_model"])
		readModelExplicit := strings.TrimSpace(readModel) != ""
		dartClass := scalarString(top["dart_class"])
		outputPath := scalarString(top["output_path"])
		var clientProjection struct {
			DartClass        string `yaml:"dart_class"`
			OutputPath       string `yaml:"output_path"`
			ExternalDartPath string `yaml:"external_dart_path"`
			Fields           []struct {
				Name string `yaml:"name"`
			} `yaml:"fields"`
		}
		if node := top["client_projection"]; node != nil {
			if decodeErr := node.Decode(&clientProjection); decodeErr != nil {
				return fmt.Errorf("%s: client_projection: %w", path, decodeErr)
			}
			if dartClass == "" {
				dartClass = strings.TrimSpace(clientProjection.DartClass)
			}
			if outputPath == "" {
				outputPath = strings.TrimSpace(clientProjection.OutputPath)
			}
		}
		projectionName := scalarString(top["projection"])
		if readModel == "" {
			readModel = dartClass
		}
		if readModel == "" {
			readModel = projectionName
		}
		if readModel == "" {
			// projections/ 也承载紧邻对象的客户端配置文档；没有任何投影身份时不进入图。
			return nil
		}
		fieldNames := projectionFieldNames(top["fields"])
		if len(fieldNames) == 0 {
			for _, field := range clientProjection.Fields {
				if name := strings.TrimSpace(field.Name); name != "" {
					fieldNames = append(fieldNames, name)
				}
			}
		}
		projections = append(projections, ast.Projection{
			ID:                object.ID + "." + readModel,
			Domain:            object.Domain,
			ObjectID:          object.ID,
			ReadModel:         readModel,
			ReadModelExplicit: readModelExplicit,
			DartClass:         dartClass,
			OutputPath:        outputPath,
			ExternalDartPath:  strings.TrimSpace(clientProjection.ExternalDartPath),
			FieldNames:        fieldNames,
			SourceEntities:    stringSequence(top["source_entities"]),
			SourceEvents:      stringSequence(top["source_events"]),
			SourcePath:        relativePath(metadataDir, path),
		})
		projectionPaths = append(projectionPaths, path)
		return nil
	})
	return projections, projectionPaths, err
}

func projectionFieldNames(node *yaml.Node) []string {
	if node == nil || node.Kind != yaml.SequenceNode {
		return nil
	}
	result := make([]string, 0, len(node.Content))
	for _, item := range node.Content {
		if item.Kind == yaml.ScalarNode {
			if name := strings.TrimSpace(item.Value); name != "" {
				result = append(result, name)
			}
			continue
		}
		mapping, err := mappingFromNode(item)
		if err != nil {
			continue
		}
		if name := strings.TrimSpace(scalarString(mapping["name"])); name != "" {
			result = append(result, name)
		}
	}
	return result
}

func stringSequence(node *yaml.Node) []string {
	if node == nil || node.Kind != yaml.SequenceNode {
		return nil
	}
	result := make([]string, 0, len(node.Content))
	for _, item := range node.Content {
		if value := strings.TrimSpace(item.Value); value != "" {
			result = append(result, value)
		}
	}
	return result
}

func loadTopLevelMapping(path string) (map[string]*yaml.Node, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var document yaml.Node
	if err := yaml.Unmarshal(data, &document); err != nil {
		return nil, fmt.Errorf("%s: %w", path, err)
	}
	if len(document.Content) != 1 {
		return nil, fmt.Errorf("%s: expected one YAML document", path)
	}
	return mappingFromNode(document.Content[0])
}

func loadOptionalTopLevelMapping(path string) (map[string]*yaml.Node, error) {
	if _, err := os.Stat(path); errors.Is(err, os.ErrNotExist) {
		return nil, nil
	} else if err != nil {
		return nil, err
	}
	return loadTopLevelMapping(path)
}

func mappingFromNode(node *yaml.Node) (map[string]*yaml.Node, error) {
	if node.Kind != yaml.MappingNode {
		return nil, fmt.Errorf("expected mapping")
	}
	result := make(map[string]*yaml.Node, len(node.Content)/2)
	for index := 0; index < len(node.Content); index += 2 {
		key := node.Content[index].Value
		if _, exists := result[key]; exists {
			return nil, fmt.Errorf("duplicate key %q", key)
		}
		result[key] = node.Content[index+1]
	}
	return result, nil
}

func rejectUnknownTopLevel(path string, mapping map[string]*yaml.Node, allowed map[string]struct{}) error {
	var unknown []string
	for key := range mapping {
		if _, ok := allowed[key]; !ok {
			unknown = append(unknown, key)
		}
	}
	if len(unknown) == 0 {
		return nil
	}
	return fmt.Errorf("%s: unknown top-level fields: %s", path, strings.Join(unknown, ", "))
}

func scalarString(node *yaml.Node) string {
	if node == nil || node.Kind != yaml.ScalarNode || node.Tag == "!!null" {
		return ""
	}
	return strings.TrimSpace(node.Value)
}

func scalarBool(node *yaml.Node) bool {
	if node == nil || node.Kind != yaml.ScalarNode {
		return false
	}
	value, err := strconv.ParseBool(strings.TrimSpace(node.Value))
	return err == nil && value
}

func stringSet(values ...string) map[string]struct{} {
	result := make(map[string]struct{}, len(values))
	for _, value := range values {
		result[value] = struct{}{}
	}
	return result
}

func relativePath(root, path string) string {
	rel, err := filepath.Rel(root, path)
	if err != nil {
		return filepath.ToSlash(path)
	}
	return filepath.ToSlash(rel)
}

func pascalCaseIdentifier(value string) string {
	var result strings.Builder
	upperNext := true
	for _, current := range value {
		if current == '_' || current == '-' {
			upperNext = true
			continue
		}
		if upperNext && current >= 'a' && current <= 'z' {
			current -= 'a' - 'A'
		}
		result.WriteRune(current)
		upperNext = false
	}
	return result.String()
}

func addSourceDocument(catalog *ast.Catalog, root, path string, errs *[]error) {
	data, err := os.ReadFile(path)
	if err != nil {
		*errs = append(*errs, err)
		return
	}
	sum := sha256.Sum256(data)
	relative := relativePath(root, path)
	digest := hex.EncodeToString(sum[:])
	catalog.Sources = append(catalog.Sources, ast.SourceDigest{
		Path: relative, SHA256: digest,
	})
	if strings.HasPrefix(relative, "_schemas/") ||
		strings.Contains("/"+relative+"/", "/test_fixtures/") {
		return
	}
	var value any
	if err := yaml.Unmarshal(data, &value); err != nil {
		*errs = append(*errs, fmt.Errorf("%s: parse source document: %w", path, err))
		return
	}
	content, err := json.Marshal(value)
	if err != nil {
		*errs = append(*errs, fmt.Errorf("%s: normalize source document: %w", path, err))
		return
	}
	mediaType := "application/yaml"
	if strings.EqualFold(filepath.Ext(path), ".json") {
		mediaType = "application/json"
	}
	catalog.Documents = append(catalog.Documents, ast.SourceDocument{
		Path: relative, SHA256: digest, MediaType: mediaType, Content: content,
	})
}
