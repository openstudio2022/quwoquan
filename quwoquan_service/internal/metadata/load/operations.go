package load

import (
	"fmt"
	"os"
	"strings"

	"quwoquan_service/internal/metadata/ast"

	"gopkg.in/yaml.v3"
)

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
	Name          string   `yaml:"name"`
	RuntimeKind   string   `yaml:"kind"`
	Phase         string   `yaml:"phase"`
	SourceObjects []string `yaml:"source_objects"`
	Idempotency   string   `yaml:"idempotency"`
	Application   struct {
		Kind        string `yaml:"kind"`
		Facet       string `yaml:"facet"`
		Method      string `yaml:"method"`
		ObjectOwner string `yaml:"object_owner"`
	} `yaml:"application"`
	Telemetry struct {
		Metric     string   `yaml:"metric"`
		Trace      bool     `yaml:"trace"`
		Attributes []string `yaml:"attributes"`
	} `yaml:"telemetry"`
	SLO struct {
		LatencyP95Milliseconds int     `yaml:"latency_p95_ms"`
		FailureRatioPercent    float64 `yaml:"failure_ratio_percent"`
		FreshnessP95Seconds    int     `yaml:"freshness_p95_seconds"`
		BacklogMaxEvents       int     `yaml:"backlog_max_events"`
		DeadLetterRatioPercent float64 `yaml:"dead_letter_ratio_percent"`
	} `yaml:"slo"`
}

type routeDocument struct {
	Method          string `yaml:"method"`
	Path            string `yaml:"path"`
	Operation       string `yaml:"operation"`
	RequestEntity   string `yaml:"request_entity"`
	RequestBodyKind string `yaml:"request_body_kind"`
	Transport       string `yaml:"transport"`
	Streaming       *struct {
		ResumeRequestField  string   `yaml:"resume_request_field"`
		ResumeResponseField string   `yaml:"resume_response_field"`
		TerminalField       string   `yaml:"terminal_field"`
		TerminalValues      []string `yaml:"terminal_values"`
	} `yaml:"streaming"`
	RequestBindings   *requestBindingsDocument  `yaml:"request_bindings"`
	RequestConstants  *requestConstantsDocument `yaml:"request_constants"`
	PathParams        any                       `yaml:"path_params"`
	QueryParams       any                       `yaml:"query_params"`
	RequestFields     any                       `yaml:"request_fields"`
	Headers           any                       `yaml:"headers"`
	ResponseEntity    string                    `yaml:"response_entity"`
	ResponseEntityRef string                    `yaml:"response_entity_ref"`
	ResponseBody      string                    `yaml:"response_body"`
	ResponseBodyKind  string                    `yaml:"response_body_kind"`
	SuccessStatus     int                       `yaml:"success_status"`
	Actor             string                    `yaml:"actor"`
	Security          map[string]string         `yaml:"security"`
	Authorization     struct {
		Principal       string   `yaml:"principal"`
		Scopes          []string `yaml:"scopes"`
		Permissions     []string `yaml:"permissions"`
		OwnershipPolicy string   `yaml:"ownership_policy"`
	} `yaml:"authorization"`
	Commercial  commercialDocument `yaml:"commercial"`
	Reliability struct {
		TimeoutMilliseconds *int `yaml:"timeout_ms"`
		StreamBudget        *struct {
			HandshakeMilliseconds   int `yaml:"handshake_ms"`
			IdleMilliseconds        int `yaml:"idle_ms"`
			MaxDurationMilliseconds int `yaml:"max_duration_ms"`
		} `yaml:"stream_budget"`
		Cancellation string `yaml:"cancellation"`
		RetryMode    string `yaml:"retry_mode"`
		MaxAttempts  int    `yaml:"max_attempts"`
		Idempotency  string `yaml:"idempotency"`
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
		LifecycleOwner  string `yaml:"lifecycle_owner"`
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
		transport := strings.ToLower(strings.TrimSpace(route.Transport))
		if transport == "" {
			transport = "json"
		}
		var streaming *ast.StreamingPolicy
		if route.Streaming != nil {
			streaming = &ast.StreamingPolicy{
				ResumeRequestField:  strings.TrimSpace(route.Streaming.ResumeRequestField),
				ResumeResponseField: strings.TrimSpace(route.Streaming.ResumeResponseField),
				TerminalField:       strings.TrimSpace(route.Streaming.TerminalField),
				TerminalValues:      trimStrings(route.Streaming.TerminalValues),
			}
		}
		reliability := ast.ReliabilityPolicy{
			Cancellation: strings.TrimSpace(route.Reliability.Cancellation),
			RetryMode:    strings.TrimSpace(route.Reliability.RetryMode),
			MaxAttempts:  route.Reliability.MaxAttempts,
			Idempotency:  strings.TrimSpace(route.Reliability.Idempotency),
		}
		if route.Reliability.TimeoutMilliseconds != nil {
			reliability.TimeoutMilliseconds = *route.Reliability.TimeoutMilliseconds
			reliability.TimeoutExplicit = true
		}
		if budget := route.Reliability.StreamBudget; budget != nil {
			reliability.StreamBudget = &ast.StreamBudgetPolicy{
				HandshakeMilliseconds:   budget.HandshakeMilliseconds,
				IdleMilliseconds:        budget.IdleMilliseconds,
				MaxDurationMilliseconds: budget.MaxDurationMilliseconds,
			}
			// The connection ceiling is the streaming form of the whole-request
			// budget, so every existing timeout consumer keeps reading one
			// number instead of learning a streaming special case. Authoring
			// timeout_ms next to a stream_budget is rejected by validate.
			if !reliability.TimeoutExplicit {
				reliability.TimeoutMilliseconds = budget.MaxDurationMilliseconds
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
			LifecycleOwner:         strings.TrimSpace(route.Application.LifecycleOwner),
			MutationTarget:         strings.TrimSpace(route.Application.MutationTarget),
			InvariantTarget:        strings.TrimSpace(route.Application.InvariantTarget),
			SessionOwner:           strings.TrimSpace(route.Application.SessionOwner),
			Reader:                 strings.TrimSpace(route.Application.Reader),
			Slice:                  strings.TrimSpace(route.Application.Slice),
			ActorRequirement:       actor,
			RequestEntity:          strings.TrimSpace(route.RequestEntity),
			RequestBodyKind:        strings.TrimSpace(route.RequestBodyKind),
			Transport:              transport,
			Streaming:              streaming,
			RequestBindings:        requestBindings,
			RequestConstants:       requestConstants,
			LegacyRequestKeys:      legacyRequestKeys,
			ClientBindingOverrides: clientBindingOverrides,
			ResponseEntity:         strings.TrimSpace(route.ResponseEntity),
			ResponseEntityRef:      strings.TrimSpace(route.ResponseEntityRef),
			ResponseBody:           strings.TrimSpace(route.ResponseBody),
			ResponseBodyKind:       strings.TrimSpace(route.ResponseBodyKind),
			SuccessStatus:          route.SuccessStatus,
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
			Reliability:       reliability,
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
			ClientContract:         clientContract,
			ClientContractExplicit: route.ClientContract != nil,
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
			ObjectOwner:     strings.TrimSpace(entrypoint.Application.ObjectOwner),
			SourceObjects:   trimStrings(entrypoint.SourceObjects),
			Idempotency:     strings.TrimSpace(entrypoint.Idempotency),
			Telemetry: ast.TelemetryPolicy{
				Metric:     strings.TrimSpace(entrypoint.Telemetry.Metric),
				Trace:      entrypoint.Telemetry.Trace,
				Attributes: trimStrings(entrypoint.Telemetry.Attributes),
			},
			SLO: ast.RuntimeEntrypointSLO{
				LatencyP95Milliseconds: entrypoint.SLO.LatencyP95Milliseconds,
				FailureRatioPercent:    entrypoint.SLO.FailureRatioPercent,
				FreshnessP95Seconds:    entrypoint.SLO.FreshnessP95Seconds,
				BacklogMaxEvents:       entrypoint.SLO.BacklogMaxEvents,
				DeadLetterRatioPercent: entrypoint.SLO.DeadLetterRatioPercent,
			},
			SourcePath: relativePath(metadataDir, path),
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
