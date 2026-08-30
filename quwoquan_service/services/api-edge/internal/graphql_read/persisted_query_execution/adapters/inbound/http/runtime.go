package httpadapter

import (
	"context"
	"crypto/sha256"
	"errors"
	"fmt"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"time"

	operationsecurity "quwoquan_service/generated/operationsecurity"
	rtauth "quwoquan_service/runtime/auth"
	admissionapp "quwoquan_service/services/api-edge/internal/edge_security/rate_limit_bucket/application"
	admissiondomain "quwoquan_service/services/api-edge/internal/edge_security/rate_limit_bucket/domain"
	rolloutapp "quwoquan_service/services/api-edge/internal/edge_security/rollout_assignment/application"
	graphapp "quwoquan_service/services/api-edge/internal/graphql_read/persisted_query_execution/application"
	graphdomain "quwoquan_service/services/api-edge/internal/graphql_read/persisted_query_execution/domain"
)

var sha256ReferencePattern = regexp.MustCompile(`^sha256:[0-9a-f]{64}$`)

const executePersistedGraphQLQueryOperationID = "gateway.persisted_query_execution.ExecutePersistedGraphQLQuery"

// Config is the release-bound GraphQL read configuration owned by the
// persisted-query execution object. The API process only composes this facet;
// it does not duplicate registry or schema validation.
type Config struct {
	Enabled               bool   `yaml:"enabled"`
	RegistryFile          string `yaml:"registry_file"`
	CandidateDigest       string `yaml:"candidate_digest"`
	SchemaFile            string `yaml:"schema_file"`
	SchemaDigest          string `yaml:"schema_digest"`
	TrustedPublicKeysJSON string `yaml:"trusted_public_keys_json"`
	OwnerTimeoutMS        int    `yaml:"owner_timeout_ms"`
}

// Options supplies the already-validated process dependencies without making
// cmd/api a test owner for the GraphQL object.
type Options struct {
	Environment     string
	Config          Config
	RegistryLoader  graphapp.RegistryLoader
	OwnerExecutor   graphapp.Executor
	EntryValidator  graphapp.EntryValidator
	Admission       *admissionapp.Service
	Rollout         *rolloutapp.Evaluator
	RolloutObserver rolloutapp.Observer
}

type Runtime struct {
	handler  http.Handler
	registry *graphdomain.Registry
}

func ValidateAndResolveConfig(
	config *Config,
	runtimeConfigPath string,
	rolloutEnabled bool,
	rolloutCandidateDigest string,
) error {
	if config == nil {
		return errors.New("GraphQL read config is required")
	}
	config.RegistryFile = strings.TrimSpace(config.RegistryFile)
	config.CandidateDigest = strings.ToLower(strings.TrimSpace(config.CandidateDigest))
	config.SchemaFile = strings.TrimSpace(config.SchemaFile)
	config.SchemaDigest = strings.ToLower(strings.TrimSpace(config.SchemaDigest))
	config.TrustedPublicKeysJSON = strings.TrimSpace(config.TrustedPublicKeysJSON)
	if !config.Enabled {
		if config.RegistryFile != "" || config.CandidateDigest != "" ||
			config.SchemaFile != "" || config.SchemaDigest != "" ||
			config.TrustedPublicKeysJSON != "" || config.OwnerTimeoutMS != 0 {
			return errors.New("disabled GraphQL read must not declare release inputs")
		}
		return nil
	}
	if !sha256ReferencePattern.MatchString(config.CandidateDigest) {
		return errors.New("GraphQL read candidate digest is invalid")
	}
	if !sha256ReferencePattern.MatchString(config.SchemaDigest) {
		return errors.New("GraphQL read schema digest is invalid")
	}
	if config.RegistryFile == "" || config.SchemaFile == "" ||
		config.TrustedPublicKeysJSON == "" {
		return errors.New("GraphQL read registry, schema, and trusted public keys are required")
	}
	// ExecutePersistedGraphQLQuery owns 3000ms while the SearchPage owner
	// operation owns 1500ms. The HTTP client is the single 2000ms transport
	// boundary between them; an arbitrary environment value recreates the
	// equal-deadline race that discarded a valid owner response at the edge.
	if config.OwnerTimeoutMS != 2000 {
		return errors.New("GraphQL owner timeout must be exactly 2000ms")
	}
	if rolloutEnabled && config.CandidateDigest != strings.ToLower(strings.TrimSpace(rolloutCandidateDigest)) {
		return errors.New("GraphQL registry candidate digest must match rollout candidate")
	}
	baseDirectory := filepath.Dir(runtimeConfigPath)
	if !filepath.IsAbs(config.RegistryFile) {
		config.RegistryFile = filepath.Join(baseDirectory, config.RegistryFile)
	}
	if !filepath.IsAbs(config.SchemaFile) {
		config.SchemaFile = filepath.Join(baseDirectory, config.SchemaFile)
	}
	schema, err := os.ReadFile(config.SchemaFile)
	if err != nil {
		return fmt.Errorf("read GraphQL schema: %w", err)
	}
	actualSchemaDigest := fmt.Sprintf("sha256:%x", sha256.Sum256(schema))
	if actualSchemaDigest != config.SchemaDigest {
		return fmt.Errorf("GraphQL schema digest mismatch: got %s", actualSchemaDigest)
	}
	if _, err := os.Stat(config.RegistryFile); err != nil {
		return fmt.Errorf("read GraphQL registry: %w", err)
	}
	return nil
}

func NewRuntime(ctx context.Context, options Options) (*Runtime, error) {
	config := options.Config
	if !config.Enabled {
		return nil, errors.New("GraphQL read runtime is disabled")
	}
	if options.RegistryLoader == nil {
		return nil, errors.New("GraphQL signed registry loader is required")
	}
	if options.OwnerExecutor == nil {
		return nil, errors.New("GraphQL owner executor is required")
	}
	if options.EntryValidator == nil {
		return nil, errors.New("GraphQL entry validator is required")
	}
	registry, err := options.RegistryLoader.Load(
		ctx,
		config.RegistryFile,
		config.CandidateDigest,
		config.SchemaDigest,
	)
	if err != nil {
		return nil, err
	}
	if registry == nil || !registry.IsSignedRelease() {
		return nil, errors.New("GraphQL registry loader returned an unverified release")
	}
	authorizer, err := newRegistryAuthorizer(
		graphQLReadOperationDescriptors(),
		registry,
		options.EntryValidator,
	)
	if err != nil {
		return nil, fmt.Errorf("GraphQL registry authorization invalid: %w", err)
	}
	executor, err := newAdmissionExecutor(
		options.Admission,
		options.Rollout,
		options.RolloutObserver,
		authorizer.descriptors,
		options.OwnerExecutor,
	)
	if err != nil {
		return nil, err
	}
	service, err := graphapp.NewService(
		options.Environment,
		registry,
		authorizer,
		executor,
		nil,
	)
	if err != nil {
		return nil, fmt.Errorf("GraphQL application service invalid: %w", err)
	}
	requestTimeout, err := canonicalGraphQLRequestTimeout()
	if err != nil {
		return nil, err
	}
	return &Runtime{
		handler:  withGraphQLRequestDeadline(NewHandler(service), requestTimeout),
		registry: registry,
	}, nil
}

func canonicalGraphQLRequestTimeout() (time.Duration, error) {
	for _, descriptor := range operationsecurity.ForDomain("gateway") {
		if descriptor.CanonicalOperationID != executePersistedGraphQLQueryOperationID {
			continue
		}
		if descriptor.Method != http.MethodPost || descriptor.PathTemplate != "/graphql" ||
			descriptor.OperationKind != "query" || descriptor.TimeoutMilliseconds <= 0 {
			return 0, errors.New("canonical GraphQL request descriptor is invalid")
		}
		return time.Duration(descriptor.TimeoutMilliseconds) * time.Millisecond, nil
	}
	return 0, errors.New("canonical GraphQL request descriptor is unavailable")
}

func withGraphQLRequestDeadline(next http.Handler, timeout time.Duration) http.Handler {
	return http.HandlerFunc(func(response http.ResponseWriter, request *http.Request) {
		ctx, cancel := context.WithTimeout(request.Context(), timeout)
		defer cancel()
		next.ServeHTTP(response, request.WithContext(ctx))
	})
}

func (runtime *Runtime) Handler() http.Handler {
	if runtime == nil {
		return nil
	}
	return runtime.handler
}

func (runtime *Runtime) Ready(context.Context) error {
	if runtime == nil || runtime.handler == nil || runtime.registry == nil ||
		!runtime.registry.IsSignedRelease() {
		return errors.New("signed GraphQL registry is not ready")
	}
	return nil
}

func graphQLReadOperationDescriptors() []rtauth.OperationSecurityDescriptor {
	descriptors := admissionapp.AllOperationDescriptors()
	// Gateway-owned persisted queries terminate at api-edge and deliberately do
	// not participate in the generic REST owner-upstream catalog.  The signed
	// GraphQL registry still has to authorize them against the deployed Graph,
	// so the specialized boundary consumes the gateway descriptors directly.
	return append(descriptors, operationsecurity.ForDomain("gateway")...)
}

type registryAuthorizer struct {
	descriptors    map[string]rtauth.OperationSecurityDescriptor
	entryValidator graphapp.EntryValidator
}

func newRegistryAuthorizer(
	descriptors []rtauth.OperationSecurityDescriptor,
	registry *graphdomain.Registry,
	entryValidator graphapp.EntryValidator,
) (*registryAuthorizer, error) {
	authorizer := &registryAuthorizer{
		descriptors:    make(map[string]rtauth.OperationSecurityDescriptor, len(descriptors)),
		entryValidator: entryValidator,
	}
	for _, descriptor := range descriptors {
		authorizer.descriptors[descriptor.CanonicalOperationID] = descriptor
	}
	for _, entry := range registry.Entries() {
		if err := authorizer.validateEntry(entry); err != nil {
			return nil, err
		}
	}
	return authorizer, nil
}

func (authorizer *registryAuthorizer) Authorize(ctx context.Context, entry graphdomain.Entry) error {
	if err := authorizer.validateEntry(entry); err != nil {
		return err
	}
	binding := entry.Authorization
	if binding.Principal == "public" {
		return nil
	}
	principal, ok := rtauth.PrincipalFromContext(ctx)
	if !ok || !principalSatisfied(binding.Principal, principal) ||
		!containsAllScopes(strings.Fields(principal.Scope), binding.Scopes) {
		return errors.New("verified principal does not satisfy signed registry binding")
	}
	return nil
}

func (authorizer *registryAuthorizer) validateEntry(entry graphdomain.Entry) error {
	descriptor, exists := authorizer.descriptors[entry.CanonicalOperationID]
	if !exists || descriptor.ContractGraphSHA256 != operationsecurity.ContractGraphSHA256 {
		return fmt.Errorf("operation %s is absent from the deployed ContractGraph", entry.CanonicalOperationID)
	}
	if descriptor.OperationKind != "query" ||
		descriptor.CommercialStatus != "ready" {
		return fmt.Errorf("operation %s is not a commercially ready read", entry.CanonicalOperationID)
	}
	if descriptor.Principal != entry.Authorization.Principal ||
		descriptor.OwnershipPolicy != entry.Authorization.OwnershipPolicy ||
		!sameStringSet(descriptor.Scopes, entry.Authorization.Scopes) {
		return fmt.Errorf("operation %s authorization binding drifted", entry.CanonicalOperationID)
	}
	if err := authorizer.entryValidator(entry); err != nil {
		return fmt.Errorf(
			"registry executor %s composition binding is invalid: %w",
			entry.ExecutorKey,
			err,
		)
	}
	return nil
}

func principalSatisfied(required string, principal rtauth.Principal) bool {
	switch required {
	case "account":
		return strings.TrimSpace(principal.Actor.AccountID) != ""
	case "persona":
		return strings.TrimSpace(principal.Actor.PersonaID) != ""
	case "device":
		return strings.TrimSpace(principal.Actor.DeviceActorID) != ""
	case "service", "operator", "admin":
		for _, role := range principal.Roles {
			if strings.TrimSpace(role) == required {
				return true
			}
		}
	}
	return false
}

func containsAllScopes(available, required []string) bool {
	values := make(map[string]struct{}, len(available))
	for _, value := range available {
		values[value] = struct{}{}
	}
	for _, value := range required {
		if _, exists := values[value]; !exists {
			return false
		}
	}
	return true
}

func sameStringSet(left, right []string) bool {
	leftCopy := append([]string(nil), left...)
	rightCopy := append([]string(nil), right...)
	sort.Strings(leftCopy)
	sort.Strings(rightCopy)
	return strings.Join(leftCopy, "\x00") == strings.Join(rightCopy, "\x00")
}

type requestMetadata struct {
	Platform       string
	AppVersion     string
	AppBuild       string
	SessionID      string
	NetworkSubject string
	Region         string
	Carrier        string
}

type requestMetadataKey struct{}

func RequestMetadataMiddleware(
	trustedNetworkHeader string,
	networkResolver rolloutapp.NetworkAttributeResolver,
	next http.Handler,
) http.Handler {
	return http.HandlerFunc(func(response http.ResponseWriter, request *http.Request) {
		request.Header.Del("X-Client-Region-Code")
		request.Header.Del("X-Client-Carrier")
		networkSubject := strings.TrimSpace(request.Header.Get(trustedNetworkHeader))
		attributes := rolloutapp.NetworkAttributes{Region: "unknown", Carrier: "unknown"}
		if networkResolver != nil {
			if clientIP := trustedIP(networkSubject); clientIP != nil {
				attributes = networkResolver.Resolve(clientIP)
			}
		}
		attributes.Region = normalizedNetworkAttribute(attributes.Region)
		attributes.Carrier = normalizedNetworkAttribute(attributes.Carrier)
		metadata := requestMetadata{
			Platform:       strings.TrimSpace(request.Header.Get("X-Client-Device-Platform")),
			AppVersion:     strings.TrimSpace(request.Header.Get("X-Client-App-Version")),
			AppBuild:       strings.TrimSpace(request.Header.Get("X-Client-App-Build")),
			SessionID:      strings.TrimSpace(request.Header.Get("X-Session-Id")),
			NetworkSubject: networkSubject,
			Region:         attributes.Region,
			Carrier:        attributes.Carrier,
		}
		ctx := context.WithValue(request.Context(), requestMetadataKey{}, metadata)
		next.ServeHTTP(response, request.WithContext(ctx))
	})
}

type admissionExecutor struct {
	admission   *admissionapp.Service
	rollout     *rolloutapp.Evaluator
	observer    rolloutapp.Observer
	descriptors map[string]rtauth.OperationSecurityDescriptor
	next        graphapp.Executor
}

func newAdmissionExecutor(
	admission *admissionapp.Service,
	rollout *rolloutapp.Evaluator,
	observer rolloutapp.Observer,
	descriptors map[string]rtauth.OperationSecurityDescriptor,
	next graphapp.Executor,
) (*admissionExecutor, error) {
	if admission == nil || rollout == nil || next == nil || len(descriptors) == 0 {
		return nil, errors.New("GraphQL admission, rollout, descriptors, and owner executor are required")
	}
	return &admissionExecutor{
		admission: admission, rollout: rollout, observer: observer,
		descriptors: descriptors, next: next,
	}, nil
}

func (executor *admissionExecutor) Execute(
	ctx context.Context,
	entry graphdomain.Entry,
	variables map[string]any,
) (graphapp.ExecutionResult, error) {
	descriptor, exists := executor.descriptors[entry.CanonicalOperationID]
	if !exists {
		return graphapp.ExecutionResult{}, errors.New("GraphQL operation descriptor is unavailable")
	}
	metadata, _ := ctx.Value(requestMetadataKey{}).(requestMetadata)
	principal, _ := rtauth.PrincipalFromContext(ctx)
	admissionSubject, err := admissionSubject(principal, metadata.NetworkSubject)
	if err != nil {
		return graphapp.ExecutionResult{}, err
	}
	decision, err := executor.admission.Admit(ctx, admissionSubject, descriptor)
	if err != nil || !decision.Allowed {
		return graphapp.ExecutionResult{}, errors.New("GraphQL shared admission denied")
	}
	rolloutSubject := rolloutapp.Subject{
		DeviceActorID: principal.Actor.DeviceActorID,
		AccountID:     principal.Actor.AccountID,
		Platform:      metadata.Platform,
		AppVersion:    metadata.AppVersion,
		AppBuild:      metadata.AppBuild,
		Region:        metadata.Region,
		Carrier:       metadata.Carrier,
	}
	rolloutDecision, err := executor.rollout.Decide(ctx, rolloutSubject)
	if err != nil {
		reason := "evaluation_failure"
		if errors.Is(err, rolloutapp.ErrAssignmentStateUnavailable) {
			reason = "assignment_store_failure"
		}
		executor.observe("unavailable", rolloutSubject, reason)
		return graphapp.ExecutionResult{}, fmt.Errorf("GraphQL rollout decision: %w", err)
	}
	executor.observe(string(rolloutDecision.Target), rolloutSubject, rolloutDecision.Reason)
	ctx = graphapp.WithSearchSessionID(ctx, metadata.SessionID)
	return executor.next.Execute(
		rolloutapp.WithTarget(ctx, rolloutDecision.Target),
		entry,
		variables,
	)
}

func (executor *admissionExecutor) observe(
	target string,
	subject rolloutapp.Subject,
	reason string,
) {
	if executor.observer == nil {
		return
	}
	executor.observer.ObserveDecision(rolloutapp.DecisionObservation{
		Stage: executor.rollout.Stage(), Target: target,
		Platform: subject.Platform, AppVersion: subject.AppVersion, AppBuild: subject.AppBuild,
		Region: subject.Region, Carrier: subject.Carrier, Reason: reason,
	})
}

func admissionSubject(principal rtauth.Principal, networkSubject string) (admissiondomain.Subject, error) {
	if value := strings.TrimSpace(principal.Actor.PersonaID); value != "" {
		return admissiondomain.Subject{Kind: "persona", ID: value}, nil
	}
	if value := strings.TrimSpace(principal.Actor.AccountID); value != "" {
		kind := "account"
		if strings.HasPrefix(value, "service:") {
			kind = "service"
		}
		return admissiondomain.Subject{Kind: kind, ID: value}, nil
	}
	if value := strings.TrimSpace(principal.Actor.DeviceActorID); value != "" {
		return admissiondomain.Subject{Kind: "device", ID: value}, nil
	}
	if host, _, err := net.SplitHostPort(networkSubject); err == nil {
		networkSubject = host
	}
	if net.ParseIP(strings.TrimSpace(networkSubject)) == nil {
		return admissiondomain.Subject{}, errors.New("GraphQL trusted network subject is invalid")
	}
	return admissiondomain.Subject{Kind: "network", ID: networkSubject}, nil
}

func trustedIP(networkSubject string) net.IP {
	if host, _, err := net.SplitHostPort(strings.TrimSpace(networkSubject)); err == nil {
		networkSubject = host
	}
	return net.ParseIP(strings.TrimSpace(networkSubject))
}

func normalizedNetworkAttribute(value string) string {
	if value = strings.TrimSpace(value); value != "" {
		return value
	}
	return "unknown"
}
