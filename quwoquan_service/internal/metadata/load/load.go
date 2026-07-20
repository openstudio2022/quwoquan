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
	"sort"
	"strconv"
	"strings"

	"quwoquan_service/internal/metadata/ast"

	"gopkg.in/yaml.v3"
)

var aggregateTopLevelKeys = stringSet(
	"domain", "aggregate_root", "object_kind", "aggregate_owner",
	"description", "storage_backend", "cache_layer", "cache_ttl_seconds",
	"capabilities", "taggable", "vector_enabled", "members", "ddd_layer_mapping",
	"counter_strategy", "join_paths", "livekit_integration", "seq_strategy",
	"dedup_strategy", "business_rules", "lifecycle",
	// deferred_operations 是文档性声明：登记对象显式推迟的公开命令与恢复前置条件，
	// 不进入 ContractGraph operation 集合。
	"deferred_operations",
)

var entityTopLevelKeys = stringSet(
	"domain", "entity", "entity_name", "is_aggregate", "aggregate_root",
	"object_kind", "aggregate_owner", "description", "storage_backend", "cache_layer",
	"cache_ttl_seconds", "capabilities", "taggable", "vector_enabled",
	"relation_signal", "ddd_layer_mapping", "service", "ownership", "storage",
	"business_rules", "lifecycle",
)

var serviceTopLevelKeys = stringSet(
	"aggregate", "entity", "response_list_key", "service", "api_routes",
	"consumers", "contract_test",
)

var readinessTopLevelKeys = stringSet(
	"object", "operations", "implementation", "tests", "environments",
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
		if entry.Name() != "aggregate.yaml" && entry.Name() != "entity.yaml" {
			return nil
		}

		object, objectErr := loadObject(metadataDir, path)
		if objectErr != nil {
			loadErrors = append(loadErrors, objectErr)
			return nil
		}
		catalog.Objects = append(catalog.Objects, object)

		objectDir := filepath.Dir(path)
		var objectOperations []ast.Operation
		servicePath := filepath.Join(objectDir, "service.yaml")
		if _, statErr := os.Stat(servicePath); statErr == nil {
			operations, serviceErr := loadService(metadataDir, servicePath, object)
			if serviceErr != nil {
				loadErrors = append(loadErrors, serviceErr)
			} else {
				objectOperations = operations
				catalog.Operations = append(catalog.Operations, operations...)
			}
		}
		readiness, readinessErr := loadReadinessEvidence(
			metadataDir,
			objectDir,
			object,
			objectOperations,
		)
		if readinessErr != nil {
			loadErrors = append(loadErrors, readinessErr)
		} else if readiness != nil {
			catalog.ReadinessEvidence = append(
				catalog.ReadinessEvidence,
				*readiness,
			)
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
	loadBusinessObjectMaps(catalog, &loadErrors)
	mergeBusinessObjectBoundaries(catalog, &loadErrors)
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
	isAggregateFile := filepath.Base(path) == "aggregate.yaml"
	allowed := entityTopLevelKeys
	if isAggregateFile {
		allowed = aggregateTopLevelKeys
	}
	if err := rejectUnknownTopLevel(path, top, allowed); err != nil {
		return ast.Object{}, err
	}

	domain := scalarString(top["domain"])
	name := scalarString(top["aggregate_root"])
	if !isAggregateFile {
		name = scalarString(top["entity"])
		if name == "" {
			name = scalarString(top["entity_name"])
		}
	}
	if domain == "" || name == "" {
		return ast.Object{}, fmt.Errorf("%s: domain and object name are required", path)
	}

	objectSegment := strings.ReplaceAll(filepath.Base(filepath.Dir(path)), "-", "_")
	id := domain + "." + objectSegment

	kind, explicit, err := resolveObjectKind(top, isAggregateFile)
	if err != nil {
		return ast.Object{}, fmt.Errorf("%s: %w", path, err)
	}
	object := ast.Object{
		ID:             id,
		Domain:         domain,
		Name:           name,
		Kind:           kind,
		KindExplicit:   explicit,
		AggregateOwner: scalarString(top["aggregate_owner"]),
		StorageBackend: scalarString(top["storage_backend"]),
		SourcePath:     relativePath(metadataDir, path),
	}
	if mappingNode := top["ddd_layer_mapping"]; mappingNode != nil {
		object.DDDLayer, err = decodeDDDLayerMapping(mappingNode)
		if err != nil {
			return ast.Object{}, fmt.Errorf("%s: ddd_layer_mapping: %w", path, err)
		}
	}
	if members := top["members"]; members != nil {
		object.Members, err = decodeMembers(members)
		if err != nil {
			return ast.Object{}, fmt.Errorf("%s: members: %w", path, err)
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

func resolveObjectKind(top map[string]*yaml.Node, isAggregateFile bool) (ast.ObjectKind, bool, error) {
	if raw := scalarString(top["object_kind"]); raw != "" {
		kind := ast.ObjectKind(raw)
		if !validObjectKind(kind) {
			return "", true, fmt.Errorf("invalid object_kind %q", raw)
		}
		return kind, true, nil
	}
	if isAggregateFile {
		return ast.ObjectKindAggregateRoot, false, nil
	}
	if scalarBool(top["is_aggregate"]) || scalarBool(top["aggregate_root"]) {
		return ast.ObjectKindAggregateRoot, false, nil
	}
	return ast.ObjectKindOwnedEntity, false, nil
}

func validObjectKind(kind ast.ObjectKind) bool {
	switch kind {
	case ast.ObjectKindAggregateRoot,
		ast.ObjectKindOwnedEntity,
		ast.ObjectKindValueObject,
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
	if node.Kind != yaml.SequenceNode {
		return nil, fmt.Errorf("must be a sequence")
	}
	members := make([]ast.Member, 0, len(node.Content))
	for _, item := range node.Content {
		mapping, err := mappingFromNode(item)
		if err != nil {
			return nil, err
		}
		member := ast.Member{
			Name:           scalarString(mapping["entity"]),
			Cardinality:    scalarString(mapping["relation"]),
			AggregateOwner: scalarString(mapping["aggregate_owner"]),
		}
		if raw := scalarString(mapping["object_kind"]); raw != "" {
			member.Kind = ast.ObjectKind(raw)
			if !validObjectKind(member.Kind) {
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
	Service struct {
		Name               string             `yaml:"name"`
		Domain             string             `yaml:"domain"`
		CommercialDefaults commercialDocument `yaml:"commercial_defaults"`
	} `yaml:"service"`
	APIRoutes []routeDocument `yaml:"api_routes"`
}

type readinessDocument struct {
	Object         string   `yaml:"object"`
	Operations     []string `yaml:"operations"`
	Implementation struct {
		DomainBehavior []string `yaml:"domain_behavior"`
		Store          []string `yaml:"store"`
		Outbox         []string `yaml:"outbox"`
		Reader         []string `yaml:"reader"`
		Transport      []string `yaml:"transport"`
		AppClient      []string `yaml:"app_client"`
		Page           []string `yaml:"page"`
	} `yaml:"implementation"`
	Tests struct {
		LocalContract  []string `yaml:"local_contract"`
		APIIntegration []string `yaml:"api_integration"`
		UserAcceptance []string `yaml:"user_acceptance"`
	} `yaml:"tests"`
	Environments []struct {
		Name     string `yaml:"name"`
		Artifact string `yaml:"artifact"`
	} `yaml:"environments"`
}

type commercialDocument struct {
	Status      string `yaml:"status"`
	BlockReason string `yaml:"block_reason"`
	GapID       string `yaml:"gap_id"`
	TargetStory string `yaml:"target_story"`
}

type routeDocument struct {
	Method           string            `yaml:"method"`
	Path             string            `yaml:"path"`
	Operation        string            `yaml:"operation"`
	RequestEntity    string            `yaml:"request_entity"`
	RequestBodyKind  string            `yaml:"request_body_kind"`
	ResponseEntity   string            `yaml:"response_entity"`
	ResponseBody     string            `yaml:"response_body"`
	ResponseBodyKind string            `yaml:"response_body_kind"`
	Actor            string            `yaml:"actor"`
	Security         map[string]string `yaml:"security"`
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
		DartImport      string            `yaml:"dart_import"`
		RequestType     string            `yaml:"request_type"`
		ResponseType    string            `yaml:"response_type"`
		RequestEncoder  string            `yaml:"request_encoder"`
		ResponseDecoder string            `yaml:"response_decoder"`
		PathBindings    map[string]string `yaml:"path_bindings"`
		QueryBindings   map[string]string `yaml:"query_bindings"`
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

func loadService(metadataDir, path string, object ast.Object) ([]ast.Operation, error) {
	top, err := loadTopLevelMapping(path)
	if err != nil {
		return nil, err
	}
	if err := rejectUnknownTopLevel(path, top, serviceTopLevelKeys); err != nil {
		return nil, err
	}
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var document serviceDocument
	if err := yaml.Unmarshal(data, &document); err != nil {
		return nil, fmt.Errorf("%s: %w", path, err)
	}
	if document.Service.Domain != "" && document.Service.Domain != object.Domain {
		return nil, fmt.Errorf("%s: service domain %q does not match object domain %q", path, document.Service.Domain, object.Domain)
	}

	operations := make([]ast.Operation, 0, len(document.APIRoutes))
	for index, route := range document.APIRoutes {
		localID := strings.TrimSpace(route.Operation)
		if localID == "" {
			return nil, fmt.Errorf("%s: api_routes[%d].operation is required", path, index)
		}
		kind, explicit, kindErr := resolveOperationKind(route.Method, route.Application.Kind)
		if kindErr != nil {
			return nil, fmt.Errorf("%s: operation %s: %w", path, localID, kindErr)
		}
		actor := strings.TrimSpace(route.Actor)
		if actor == "" {
			actor = inferActorRequirement(route.Security)
		}
		commercial := mergeCommercialBinding(
			document.Service.CommercialDefaults,
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
		if route.ClientContract != nil {
			clientContract = &ast.ClientContract{
				DartImport:      strings.TrimSpace(route.ClientContract.DartImport),
				RequestType:     strings.TrimSpace(route.ClientContract.RequestType),
				ResponseType:    strings.TrimSpace(route.ClientContract.ResponseType),
				RequestEncoder:  strings.TrimSpace(route.ClientContract.RequestEncoder),
				ResponseDecoder: strings.TrimSpace(route.ClientContract.ResponseDecoder),
				PathBindings:    route.ClientContract.PathBindings,
				QueryBindings:   route.ClientContract.QueryBindings,
			}
		}
		operations = append(operations, ast.Operation{
			ID:               object.ID + "." + localID,
			LocalID:          localID,
			Domain:           object.Domain,
			ObjectID:         object.ID,
			Method:           strings.ToUpper(strings.TrimSpace(route.Method)),
			PathTemplate:     strings.TrimSpace(route.Path),
			Kind:             kind,
			KindExplicit:     explicit,
			Facet:            strings.TrimSpace(route.Application.Facet),
			FacadeMethod:     strings.TrimSpace(route.Application.Method),
			AggregateOwner:   strings.TrimSpace(route.Application.AggregateOwner),
			AppendSink:       strings.TrimSpace(route.Application.AppendSink),
			MutationTarget:   strings.TrimSpace(route.Application.MutationTarget),
			InvariantTarget:  strings.TrimSpace(route.Application.InvariantTarget),
			SessionOwner:     strings.TrimSpace(route.Application.SessionOwner),
			Reader:           strings.TrimSpace(route.Application.Reader),
			Slice:            strings.TrimSpace(route.Application.Slice),
			ActorRequirement: actor,
			RequestEntity:    strings.TrimSpace(route.RequestEntity),
			RequestBodyKind:  strings.TrimSpace(route.RequestBodyKind),
			ResponseEntity:   strings.TrimSpace(route.ResponseEntity),
			ResponseBody:     strings.TrimSpace(route.ResponseBody),
			ResponseBodyKind: strings.TrimSpace(route.ResponseBodyKind),
			SourcePath:       relativePath(metadataDir, path),
			Security:         route.Security,
			AuthMode:         resolveAuthMode(route.Security),
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
	return operations, nil
}

func loadReadinessEvidence(
	metadataDir string,
	objectDir string,
	object ast.Object,
	operations []ast.Operation,
) (*ast.ObjectReadinessEvidence, error) {
	path := filepath.Join(objectDir, "readiness.yaml")
	if _, err := os.Stat(path); errors.Is(err, os.ErrNotExist) {
		return nil, nil
	} else if err != nil {
		return nil, err
	}
	top, err := loadTopLevelMapping(path)
	if err != nil {
		return nil, err
	}
	if err := rejectUnknownTopLevel(path, top, readinessTopLevelKeys); err != nil {
		return nil, err
	}
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var document readinessDocument
	if err := yaml.Unmarshal(data, &document); err != nil {
		return nil, fmt.Errorf("%s: %w", path, err)
	}
	if strings.TrimSpace(document.Object) != object.Name {
		return nil, fmt.Errorf(
			"%s: object %q does not match canonical object %q",
			path,
			document.Object,
			object.Name,
		)
	}
	operationIDs, err := canonicalReadinessOperationIDs(
		path,
		object,
		document.Operations,
		operations,
	)
	if err != nil {
		return nil, err
	}
	artifactList := func(values []string) ([]ast.EvidenceArtifact, error) {
		return loadEvidenceArtifacts(metadataDir, path, values)
	}
	result := &ast.ObjectReadinessEvidence{
		ObjectID:     object.ID,
		OperationIDs: operationIDs,
		SourcePath:   relativePath(metadataDir, path),
	}
	for target, values := range map[*[]ast.EvidenceArtifact][]string{
		&result.DomainBehavior: document.Implementation.DomainBehavior,
		&result.Store:          document.Implementation.Store,
		&result.Outbox:         document.Implementation.Outbox,
		&result.Reader:         document.Implementation.Reader,
		&result.Transport:      document.Implementation.Transport,
		&result.AppClient:      document.Implementation.AppClient,
		&result.Page:           document.Implementation.Page,
		&result.LocalContract:  document.Tests.LocalContract,
		&result.APIIntegration: document.Tests.APIIntegration,
		&result.UserAcceptance: document.Tests.UserAcceptance,
	} {
		artifacts, loadErr := artifactList(values)
		if loadErr != nil {
			return nil, loadErr
		}
		*target = artifacts
	}
	seenEnvironments := map[string]struct{}{}
	for index, environment := range document.Environments {
		name := strings.TrimSpace(environment.Name)
		if name != "alpha" && name != "beta" && name != "gamma" && name != "prod" {
			return nil, fmt.Errorf(
				"%s: environments[%d].name %q must be alpha, beta, gamma, or prod",
				path,
				index,
				name,
			)
		}
		if _, exists := seenEnvironments[name]; exists {
			return nil, fmt.Errorf("%s: duplicate environment %q", path, name)
		}
		seenEnvironments[name] = struct{}{}
		artifacts, loadErr := artifactList([]string{environment.Artifact})
		if loadErr != nil {
			return nil, loadErr
		}
		result.Environments = append(result.Environments, ast.EnvironmentEvidence{
			Name:     name,
			Artifact: artifacts[0],
		})
	}
	return result, nil
}

func canonicalReadinessOperationIDs(
	path string,
	object ast.Object,
	declared []string,
	operations []ast.Operation,
) ([]string, error) {
	want := make(map[string]struct{}, len(operations))
	for _, operation := range operations {
		want[operation.ID] = struct{}{}
	}
	got := make(map[string]struct{}, len(declared))
	result := make([]string, 0, len(declared))
	for _, value := range declared {
		operationID := strings.TrimSpace(value)
		if operationID != "" && !strings.Contains(operationID, ".") {
			operationID = object.ID + "." + operationID
		}
		if _, exists := want[operationID]; !exists {
			return nil, fmt.Errorf(
				"%s: readiness operation %q is not owned by %s",
				path,
				operationID,
				object.ID,
			)
		}
		if _, exists := got[operationID]; exists {
			return nil, fmt.Errorf("%s: duplicate readiness operation %q", path, operationID)
		}
		got[operationID] = struct{}{}
		result = append(result, operationID)
	}
	if len(got) != len(want) {
		var missing []string
		for operationID := range want {
			if _, exists := got[operationID]; !exists {
				missing = append(missing, operationID)
			}
		}
		sort.Strings(missing)
		return nil, fmt.Errorf(
			"%s: readiness evidence must cover every object operation; missing %s",
			path,
			strings.Join(missing, ", "),
		)
	}
	sort.Strings(result)
	return result, nil
}

func loadEvidenceArtifacts(
	metadataDir string,
	readinessPath string,
	values []string,
) ([]ast.EvidenceArtifact, error) {
	metadataRoot, err := filepath.Abs(metadataDir)
	if err != nil {
		return nil, err
	}
	repositoryRoot := filepath.Clean(filepath.Join(metadataRoot, "..", "..", ".."))
	seen := map[string]struct{}{}
	result := make([]ast.EvidenceArtifact, 0, len(values))
	for _, value := range values {
		relative := filepath.ToSlash(filepath.Clean(strings.TrimSpace(value)))
		if relative == "" || relative == "." || filepath.IsAbs(relative) || strings.HasPrefix(relative, "../") {
			return nil, fmt.Errorf("%s: invalid repository-relative evidence path %q", readinessPath, value)
		}
		if _, exists := seen[relative]; exists {
			return nil, fmt.Errorf("%s: duplicate evidence path %q", readinessPath, relative)
		}
		seen[relative] = struct{}{}
		absolute := filepath.Join(repositoryRoot, filepath.FromSlash(relative))
		withinRoot, relErr := filepath.Rel(repositoryRoot, absolute)
		if relErr != nil || withinRoot == ".." || strings.HasPrefix(withinRoot, ".."+string(filepath.Separator)) {
			return nil, fmt.Errorf("%s: evidence path escapes repository: %q", readinessPath, relative)
		}
		payload, readErr := os.ReadFile(absolute)
		if readErr != nil {
			return nil, fmt.Errorf("%s: evidence %q: %w", readinessPath, relative, readErr)
		}
		digest := sha256.Sum256(payload)
		result = append(result, ast.EvidenceArtifact{
			Path:   relative,
			SHA256: hex.EncodeToString(digest[:]),
		})
	}
	sort.Slice(result, func(i, j int) bool { return result[i].Path < result[j].Path })
	return result, nil
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
		dartClass := scalarString(top["dart_class"])
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
		projections = append(projections, ast.Projection{
			ID:         object.ID + "." + readModel,
			Domain:     object.Domain,
			ObjectID:   object.ID,
			ReadModel:  readModel,
			DartClass:  dartClass,
			SourcePath: relativePath(metadataDir, path),
		})
		projectionPaths = append(projectionPaths, path)
		return nil
	})
	return projections, projectionPaths, err
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
