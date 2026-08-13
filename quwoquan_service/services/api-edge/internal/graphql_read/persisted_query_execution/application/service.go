package application

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"strings"
	"time"

	"quwoquan_service/services/api-edge/internal/graphql_read/persisted_query_execution/domain"
)

var (
	ErrRequestRejected  = errors.New("persisted GraphQL request rejected")
	ErrUnknownQuery     = errors.New("persisted GraphQL query unknown")
	ErrForbidden        = errors.New("persisted GraphQL query forbidden")
	ErrOwnerUnavailable = errors.New("persisted GraphQL owner unavailable")
)

type QueryRequest struct {
	SHA256Hash    string
	OperationName string
	Variables     json.RawMessage
}

type ExecutionResult struct {
	Data  json.RawMessage
	Usage ExecutionUsage
}

type ExecutionUsage struct {
	OwnerCalls    int `json:"ownerCalls"`
	BatchKeys     int `json:"batchKeys"`
	ResponseBytes int `json:"responseBytes"`
}

type Authorizer interface {
	Authorize(ctx context.Context, entry domain.Entry) error
}

type Executor interface {
	Execute(ctx context.Context, entry domain.Entry, variables map[string]any) (ExecutionResult, error)
}

// EntryValidator confirms a registry entry is bound to a real owner
// composition. The binding table lives in the infrastructure layer, so the
// inbound adapter must consume it through this application port instead of
// importing infrastructure directly.
type EntryValidator func(entry domain.Entry) error

type searchSessionKey struct{}

// WithSearchSessionID binds the already-sanitized public ingress session to an
// owner request. The value never comes from GraphQL variables and therefore
// cannot be used to smuggle a different principal through a persisted query.
func WithSearchSessionID(ctx context.Context, sessionID string) context.Context {
	return context.WithValue(ctx, searchSessionKey{}, strings.TrimSpace(sessionID))
}

// SearchSessionID reads the ingress session bound by WithSearchSessionID.
func SearchSessionID(ctx context.Context) string {
	sessionID, _ := ctx.Value(searchSessionKey{}).(string)
	return sessionID
}

// RegistryLoader is the application port for loading one release-bound,
// signature-verified persisted-query registry. Concrete signature and file
// adapters are assembled only by the process composition root.
type RegistryLoader interface {
	Load(
		ctx context.Context,
		path string,
		expectedCandidateDigest string,
		expectedSchemaDigest string,
	) (*domain.Registry, error)
}

type Observer interface {
	Record(operation, outcome string, elapsed time.Duration)
}

type noopObserver struct{}

func (noopObserver) Record(string, string, time.Duration) {}

type Service struct {
	registry   *domain.Registry
	authorizer Authorizer
	executor   Executor
	observer   Observer
}

func NewService(
	environment string,
	registry *domain.Registry,
	authorizer Authorizer,
	executor Executor,
	observer Observer,
) (*Service, error) {
	environment = strings.TrimSpace(environment)
	switch environment {
	case "alpha", "beta", "gamma", "prod":
	default:
		return nil, fmt.Errorf("unsupported api-edge environment %q", environment)
	}
	if registry == nil {
		return nil, errors.New("persisted query registry is required")
	}
	if environment == "prod" && !registry.IsSignedRelease() {
		return nil, errors.New("prod requires a verified signed-release persisted query registry")
	}
	if authorizer == nil {
		return nil, errors.New("persisted query authorizer is required")
	}
	if executor == nil {
		return nil, errors.New("persisted query executor is required")
	}
	if observer == nil {
		observer = noopObserver{}
	}
	return &Service{
		registry: registry, authorizer: authorizer, executor: executor, observer: observer,
	}, nil
}

func (service *Service) Execute(ctx context.Context, request QueryRequest) (ExecutionResult, error) {
	startedAt := time.Now()
	operation := ""
	record := func(outcome string) {
		service.observer.Record(operation, outcome, time.Since(startedAt))
	}

	if !domain.ValidHash(request.SHA256Hash) {
		record("request_invalid")
		return ExecutionResult{}, fmt.Errorf("%w: malformed persisted query hash", ErrRequestRejected)
	}
	entry, found := service.registry.Lookup(request.SHA256Hash)
	if !found {
		record("query_unknown")
		return ExecutionResult{}, ErrUnknownQuery
	}
	operation = entry.CanonicalOperationID
	if request.OperationName != "" && request.OperationName != entry.OperationName {
		record("operation_name_mismatch")
		return ExecutionResult{}, fmt.Errorf("%w: operationName does not match registry", ErrRequestRejected)
	}
	variables, err := validateVariables(request.Variables, entry)
	if err != nil {
		record("cost_rejected")
		return ExecutionResult{}, fmt.Errorf("%w: %v", ErrRequestRejected, err)
	}
	if err := service.authorizer.Authorize(ctx, entry); err != nil {
		record("authorization_denied")
		return ExecutionResult{}, fmt.Errorf("%w: registry-bound authorization denied", ErrForbidden)
	}
	result, err := service.executor.Execute(ctx, entry, variables)
	if err != nil {
		record("owner_unavailable")
		return ExecutionResult{}, fmt.Errorf("%w: registered executor failed", ErrOwnerUnavailable)
	}
	if !validGraphQLData(result.Data) {
		record("owner_invalid_response")
		return ExecutionResult{}, fmt.Errorf("%w: registered executor returned invalid data", ErrOwnerUnavailable)
	}
	if err := validateExecutionUsage(result, entry); err != nil {
		record("execution_cost_rejected")
		return ExecutionResult{}, fmt.Errorf("%w: registered executor exceeded signed cost plan: %v", ErrOwnerUnavailable, err)
	}
	record("succeeded")
	return result, nil
}

func validateVariables(raw json.RawMessage, entry domain.Entry) (map[string]any, error) {
	if len(raw) == 0 || bytes.Equal(bytes.TrimSpace(raw), []byte("null")) {
		raw = json.RawMessage(`{}`)
	}
	if len(raw) > domain.MaxVariablesBytes || len(raw) > entry.Cost.VariablesMaxBytes {
		return nil, errors.New("variables exceed the registered byte budget")
	}
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.UseNumber()
	var variables map[string]any
	if err := decoder.Decode(&variables); err != nil {
		return nil, fmt.Errorf("variables must be a JSON object: %w", err)
	}
	var trailing any
	if err := decoder.Decode(&trailing); !errors.Is(err, io.EOF) {
		return nil, errors.New("variables must contain exactly one JSON object")
	}
	if variables == nil {
		variables = map[string]any{}
	}
	if err := validateVariableTree(variables, entry.Cost.PageSizeMax); err != nil {
		return nil, err
	}
	actualComplexity, err := entry.CostPlan.Evaluate(variables)
	if err != nil {
		return nil, fmt.Errorf("cost plan variables: %w", err)
	}
	if actualComplexity > entry.Cost.Complexity || actualComplexity > domain.MaxComplexity {
		return nil, errors.New("actual complexity exceeds the registered budget")
	}
	for _, path := range entry.PaginationVariables {
		value, exists := valueAtPath(variables, path)
		if !exists || value == nil {
			continue
		}
		if err := validatePageSize(value, entry.Cost.PageSizeMax); err != nil {
			return nil, fmt.Errorf("pagination variable %s: %w", path, err)
		}
	}
	return variables, nil
}

func validateExecutionUsage(result ExecutionResult, entry domain.Entry) error {
	usage := result.Usage
	if usage.OwnerCalls < 0 || usage.BatchKeys < 0 || usage.ResponseBytes < 0 {
		return errors.New("execution usage must not be negative")
	}
	if usage.ResponseBytes != len(result.Data) {
		return fmt.Errorf("responseBytes=%d does not equal encoded data bytes=%d", usage.ResponseBytes, len(result.Data))
	}
	if usage.OwnerCalls > entry.Cost.MaxOwnerCalls || usage.OwnerCalls > entry.CostPlan.MaxOwnerCalls {
		return fmt.Errorf("ownerCalls=%d exceeds maxOwnerCalls=%d", usage.OwnerCalls, entry.Cost.MaxOwnerCalls)
	}
	if usage.BatchKeys > entry.Cost.MaxBatchKeys || usage.BatchKeys > entry.CostPlan.MaxBatchKeys {
		return fmt.Errorf("batchKeys=%d exceeds maxBatchKeys=%d", usage.BatchKeys, entry.Cost.MaxBatchKeys)
	}
	if usage.ResponseBytes > entry.Cost.MaxResponseBytes || usage.ResponseBytes > entry.CostPlan.MaxResponseBytes {
		return fmt.Errorf("responseBytes=%d exceeds maxResponseBytes=%d", usage.ResponseBytes, entry.Cost.MaxResponseBytes)
	}
	return nil
}

func validateVariableTree(root map[string]any, pageSizeMax int) error {
	type frame struct {
		value any
		depth int
	}
	stack := []frame{{value: root, depth: 1}}
	for len(stack) > 0 {
		current := stack[len(stack)-1]
		stack = stack[:len(stack)-1]
		if current.depth > 64 {
			return errors.New("variables nesting exceeds the transport safety limit")
		}
		switch value := current.value.(type) {
		case map[string]any:
			for key, child := range value {
				if isPageSizeKey(key) && child != nil {
					if err := validatePageSize(child, pageSizeMax); err != nil {
						return fmt.Errorf("pagination field %s: %w", key, err)
					}
				}
				stack = append(stack, frame{value: child, depth: current.depth + 1})
			}
		case []any:
			for _, child := range value {
				stack = append(stack, frame{value: child, depth: current.depth + 1})
			}
		}
	}
	return nil
}

func isPageSizeKey(key string) bool {
	switch strings.ToLower(strings.TrimSpace(key)) {
	case "first", "last", "limit", "pagesize", "page_size":
		return true
	default:
		return false
	}
}

func validatePageSize(value any, maximum int) error {
	number, ok := value.(json.Number)
	if !ok {
		return errors.New("must be an integer")
	}
	parsed, err := number.Int64()
	if err != nil {
		return errors.New("must be an integer")
	}
	if parsed < 1 || parsed > int64(maximum) || parsed > domain.MaxPageSize {
		return fmt.Errorf("value=%d is outside 1..%d", parsed, maximum)
	}
	return nil
}

func valueAtPath(root map[string]any, path string) (any, bool) {
	var current any = root
	for _, segment := range strings.Split(path, ".") {
		object, ok := current.(map[string]any)
		if !ok {
			return nil, false
		}
		current, ok = object[segment]
		if !ok {
			return nil, false
		}
	}
	return current, true
}

func validGraphQLData(data json.RawMessage) bool {
	trimmed := bytes.TrimSpace(data)
	return len(trimmed) > 1 && trimmed[0] == '{' && json.Valid(trimmed)
}
