package auth

import (
	"context"
	"fmt"
	"net/http"
	"regexp"
	"strings"
	"time"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/runtime/operation"
)

type operationDescriptorContextKey struct{}

// OperationSecurityDescriptor is generated from one ContractGraph operation.
// CommercialStatus != ready and AuthMode=deny are intentionally executable:
// the route remains fail-closed until its object packet is signed.
type OperationSecurityDescriptor struct {
	CanonicalOperationID string
	ContractGraphSHA256  string
	Method               string
	PathTemplate         string
	OperationKind        string
	MutationTarget       string
	InvariantTarget      string
	AuthMode             string
	ActorRequirement     string
	Principal            string
	Scopes               []string
	Permissions          []string
	OwnershipPolicy      string
	TimeoutMilliseconds  int
	StreamBudget         *OperationStreamBudget
	Idempotency          string
	VersionPrecondition  string
	CommercialStatus     string
}

// OperationStreamBudget is the generated reliability.stream_budget of one
// streaming operation. A long-lived connection needs three independent bounds
// and TimeoutMilliseconds can only carry one of them, so a streaming
// descriptor derives TimeoutMilliseconds from MaxDurationMilliseconds and
// keeps the handshake and idle bounds here for the stream writer to enforce.
type OperationStreamBudget struct {
	HandshakeMilliseconds   int
	IdleMilliseconds        int
	MaxDurationMilliseconds int
}

// Handshake bounds admission until the first flushed byte of the stream.
func (budget OperationStreamBudget) Handshake() time.Duration {
	return time.Duration(budget.HandshakeMilliseconds) * time.Millisecond
}

// Idle bounds the gap between two consecutive payload frames.
func (budget OperationStreamBudget) Idle() time.Duration {
	return time.Duration(budget.IdleMilliseconds) * time.Millisecond
}

// MaxDuration bounds admission until the connection is closed regardless of
// how healthy it is. Clients resume through the declared streaming resume
// field, so this is a connection lifetime, not a work deadline.
func (budget OperationStreamBudget) MaxDuration() time.Duration {
	return time.Duration(budget.MaxDurationMilliseconds) * time.Millisecond
}

// StreamBudgetForOperation returns the declared stream budget of one canonical
// operation ID. It panics when the operation is absent or non-streaming: a
// stream handler that cannot find its own contract must fail at wiring time
// rather than fall back to a hand-written duration, which is how the transport
// becomes a second truth source.
func StreamBudgetForOperation(
	descriptors []OperationSecurityDescriptor,
	canonicalOperationID string,
) OperationStreamBudget {
	for _, descriptor := range descriptors {
		if descriptor.CanonicalOperationID != canonicalOperationID {
			continue
		}
		if descriptor.StreamBudget == nil {
			panic(
				"operation declares no reliability.stream_budget: " +
					canonicalOperationID,
			)
		}
		return *descriptor.StreamBudget
	}
	panic(
		"operation missing from the generated descriptor table: " +
			canonicalOperationID,
	)
}

type compiledOperationDescriptor struct {
	OperationSecurityDescriptor
	pathPattern     *regexp.Regexp
	pathSpecificity int
}

// OperationDescriptorFromContext exposes the authenticated operation contract
// to application-level owner/member/BOLA checks.
func OperationDescriptorFromContext(
	ctx context.Context,
) (OperationSecurityDescriptor, bool) {
	descriptor, ok := ctx.Value(operationDescriptorContextKey{}).(OperationSecurityDescriptor)
	return descriptor, ok
}

// NewOperationPathTemplateResolver returns the bounded canonical route label
// for observability middleware. Unknown paths collapse to one sentinel instead
// of leaking object IDs, query targets, or other unbounded URL segments.
func NewOperationPathTemplateResolver(
	descriptors []OperationSecurityDescriptor,
) func(*http.Request) string {
	compiled := mustCompileOperationDescriptors(descriptors)
	return func(request *http.Request) string {
		if request == nil {
			return "/_unmatched"
		}
		descriptor, ok := matchOperation(
			compiled,
			request.Method,
			request.URL.Path,
		)
		if !ok {
			return "/_unmatched"
		}
		return descriptor.PathTemplate
	}
}

// operationBoundary selects which contract clauses one guard mount enforces.
// The public boundary is the only place that may refuse traffic for commercial
// status, because that status is release evidence about an object, not a
// property of the request.
type operationBoundary int

const (
	// publicOperationBoundary is api-edge: the single externally reachable
	// boundary. Blocked operations must fail closed here.
	publicOperationBoundary operationBoundary = iota
	// runtimeOperationBoundary is an owner service process. It enforces the
	// request-level contract (authn/authz/idempotency/precondition/deadline)
	// and deliberately lets blocked operations through, so the candidate
	// evidence that turns them ready can still be produced against a real
	// service.
	runtimeOperationBoundary
)

// RequireGeneratedOperationAuthorization applies a generated, default-deny
// route table. Unknown, blocked, or malformed operations never reach handlers.
func RequireGeneratedOperationAuthorization(
	descriptors []OperationSecurityDescriptor,
) func(http.Handler) http.Handler {
	compiled := mustCompileOperationDescriptors(descriptors)
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			descriptor, ok := matchOperation(compiled, r.Method, r.URL.Path)
			if !ok {
				writeOperationGuardError(
					w,
					r,
					"route_not_found",
					"operation is not registered in ContractGraph",
				)
				return
			}
			authorizeGeneratedOperation(
				w,
				r,
				descriptor,
				publicOperationBoundary,
				next,
			)
		})
	}
}

// EnforceRuntimeOperationContract applies the generated descriptor table on an
// owner service's own inbound boundary: verified principal, scopes and
// permissions, Idempotency-Key, If-Match and the declared
// reliability.timeout_ms deadline.
//
// It differs from RequireGeneratedOperationAuthorization in exactly two ways,
// both required for an internal boundary:
//   - commercial status is not a gate here (see runtimeOperationBoundary);
//   - unmatched paths pass through, because this middleware is not the routing
//     authority for probes or for object routes that are still migrating.
//
// api-edge must keep using RequireGeneratedOperationAuthorization: it is the
// public boundary and stays default-deny plus commercial fail-closed.
func EnforceRuntimeOperationContract(
	descriptors []OperationSecurityDescriptor,
) func(http.Handler) http.Handler {
	compiled := mustCompileOperationDescriptors(descriptors)
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			descriptor, ok := matchOperation(compiled, r.Method, r.URL.Path)
			if !ok {
				next.ServeHTTP(w, r)
				return
			}
			authorizeGeneratedOperation(
				w,
				r,
				descriptor,
				runtimeOperationBoundary,
				next,
			)
		})
	}
}

// RequireGeneratedOperationAuthorizationForRoute applies the generated
// descriptor for one already-routed boundary. It keeps incremental service
// migrations fail-closed without inventing a second authorization table.
func RequireGeneratedOperationAuthorizationForRoute(
	descriptors []OperationSecurityDescriptor,
	method string,
	pathTemplate string,
) func(http.Handler) http.Handler {
	normalizedMethod := strings.ToUpper(strings.TrimSpace(method))
	normalizedPath := strings.TrimSpace(pathTemplate)
	matched := make([]OperationSecurityDescriptor, 0, 1)
	for _, descriptor := range descriptors {
		if strings.ToUpper(strings.TrimSpace(descriptor.Method)) != normalizedMethod ||
			strings.TrimSpace(descriptor.PathTemplate) != normalizedPath {
			continue
		}
		matched = append(matched, descriptor)
	}
	if len(matched) != 1 {
		panic(fmt.Sprintf(
			"generated operation descriptor not unique for %s %s: %d",
			normalizedMethod,
			normalizedPath,
			len(matched),
		))
	}
	return RequireGeneratedOperationAuthorization(matched)
}

// EnforceGeneratedOperationAuthorization 为对象原子迁移提供唯一过渡边界：
// ContractGraph 已登记的精确 method+path 一律执行 generated authorization，
// 因而 blocked/deny operation 必须 fail-closed，绝不能到达未授权的 owner handler。
// 尚未登记的旧对象路径只允许在该对象迁移期间继续由其原 owner 消费；完成迁移后
// composition root 必须切换到 RequireGeneratedOperationAuthorization。
func EnforceGeneratedOperationAuthorization(
	descriptors []OperationSecurityDescriptor,
) func(http.Handler) http.Handler {
	compiled := mustCompileOperationDescriptors(descriptors)
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			descriptor, ok := matchOperation(compiled, r.Method, r.URL.Path)
			if !ok {
				next.ServeHTTP(w, r)
				return
			}
			authorizeGeneratedOperation(
				w,
				r,
				descriptor,
				publicOperationBoundary,
				next,
			)
		})
	}
}

func mustCompileOperationDescriptors(
	descriptors []OperationSecurityDescriptor,
) []compiledOperationDescriptor {
	if len(descriptors) == 0 {
		panic("generated operation descriptor set is empty")
	}
	compiled := make([]compiledOperationDescriptor, 0, len(descriptors))
	seen := make(map[string]struct{}, len(descriptors))
	contractGraphSHA256 := ""
	for _, descriptor := range descriptors {
		descriptor.OperationKind = strings.TrimSpace(descriptor.OperationKind)
		descriptor.MutationTarget = strings.TrimSpace(descriptor.MutationTarget)
		descriptor.InvariantTarget = strings.TrimSpace(descriptor.InvariantTarget)
		descriptor.Idempotency = strings.TrimSpace(descriptor.Idempotency)
		descriptor.VersionPrecondition = strings.TrimSpace(
			descriptor.VersionPrecondition,
		)
		switch descriptor.OperationKind {
		case "command":
			if descriptor.MutationTarget == "" ||
				descriptor.InvariantTarget == "" ||
				descriptor.MutationTarget != descriptor.InvariantTarget {
				panic(
					"generated command descriptor has invalid semantic target: " +
						descriptor.CanonicalOperationID,
				)
			}
		case "query", "session":
			if descriptor.MutationTarget != "" || descriptor.InvariantTarget != "" {
				panic(
					"generated non-command descriptor declares semantic target: " +
						descriptor.CanonicalOperationID,
				)
			}
		default:
			panic(
				"generated operation descriptor has invalid operation kind: " +
					descriptor.CanonicalOperationID,
			)
		}
		switch descriptor.Idempotency {
		case "", "none", "optional", "required", "payload_digest_server_side":
		default:
			panic(
				"generated operation descriptor has invalid idempotency policy: " +
					descriptor.CanonicalOperationID,
			)
		}
		switch descriptor.VersionPrecondition {
		case "":
		case "if_match":
			if descriptor.OperationKind != "command" {
				panic(
					"generated non-command descriptor requires If-Match: " +
						descriptor.CanonicalOperationID,
				)
			}
		default:
			panic(
				"generated operation descriptor has invalid version precondition: " +
					descriptor.CanonicalOperationID,
			)
		}
		descriptor.ContractGraphSHA256 = strings.TrimSpace(
			descriptor.ContractGraphSHA256,
		)
		if descriptor.ContractGraphSHA256 == "" {
			panic(
				"generated operation descriptor missing ContractGraphSHA256: " +
					descriptor.CanonicalOperationID,
			)
		}
		if contractGraphSHA256 == "" {
			contractGraphSHA256 = descriptor.ContractGraphSHA256
		} else if contractGraphSHA256 != descriptor.ContractGraphSHA256 {
			panic("generated operation descriptors use multiple ContractGraph hashes")
		}
		pattern, err := compilePathTemplate(descriptor.PathTemplate)
		if err != nil {
			panic(fmt.Sprintf(
				"invalid generated operation descriptor %s: %v",
				descriptor.CanonicalOperationID,
				err,
			))
		}
		key := strings.ToUpper(strings.TrimSpace(descriptor.Method)) + " " + pattern.String()
		if _, ok := seen[key]; ok {
			panic("duplicate generated operation route: " + key)
		}
		seen[key] = struct{}{}
		descriptor.Method = strings.ToUpper(strings.TrimSpace(descriptor.Method))
		compiled = append(compiled, compiledOperationDescriptor{
			OperationSecurityDescriptor: descriptor,
			pathPattern:                 pattern,
			pathSpecificity:             operationPathSpecificity(descriptor.PathTemplate),
		})
	}
	return compiled
}

func authorizeGeneratedOperation(
	w http.ResponseWriter,
	r *http.Request,
	descriptor compiledOperationDescriptor,
	boundary operationBoundary,
	next http.Handler,
) {
	if descriptor.AuthMode == "deny" {
		writeOperationGuardError(
			w,
			r,
			"forbidden",
			"operation denies all callers",
		)
		return
	}
	if boundary == publicOperationBoundary &&
		descriptor.CommercialStatus != "ready" {
		writeOperationGuardError(
			w,
			r,
			"forbidden",
			"operation is not commercially enabled",
		)
		return
	}
	principal, hasPrincipal := PrincipalFromContext(r.Context())
	if descriptor.AuthMode == "required" && !hasPrincipal {
		writeOperationGuardError(
			w,
			r,
			"unauthorized",
			"verified principal is required",
		)
		return
	}
	if hasPrincipal &&
		!isSafeReadMethod(r.Method) &&
		principal.TokenType == TokenTypeAccess &&
		strings.TrimSpace(principal.Actor.PersonaID) != "" &&
		(strings.HasPrefix(
			strings.TrimSpace(principal.Actor.AccountID),
			"service:",
		) || containsAny(principal.Roles, []string{"service"})) {
		writeOperationGuardError(
			w,
			r,
			"forbidden",
			"legacy delegated persona credentials are read-only",
		)
		return
	}
	if hasPrincipal &&
		(!actorRequirementSatisfied(descriptor.ActorRequirement, principal.Actor) ||
			!principalRequirementSatisfied(descriptor.Principal, principal) ||
			!claimsContainAllScopes(principal, descriptor.Scopes) ||
			!claimsContainAllPermissions(principal, descriptor.Permissions)) {
		writeOperationGuardError(
			w,
			r,
			"forbidden",
			"principal does not satisfy operation authorization",
		)
		return
	}
	if !hasPrincipal &&
		(descriptor.AuthMode != "public" &&
			descriptor.AuthMode != "optional" ||
			descriptor.ActorRequirement != "" &&
				descriptor.ActorRequirement != "none" ||
			descriptor.Principal != "" &&
				descriptor.Principal != "public") {
		writeOperationGuardError(
			w,
			r,
			"unauthorized",
			"verified principal is required",
		)
		return
	}
	idempotencyKey := strings.TrimSpace(r.Header.Get("Idempotency-Key"))
	if descriptor.Idempotency == "required" && idempotencyKey == "" {
		writeOperationRequestError(
			w,
			r,
			"stable Idempotency-Key is required by the operation contract",
		)
		return
	}
	ifMatch := strings.TrimSpace(r.Header.Get("If-Match"))
	if descriptor.VersionPrecondition == "if_match" {
		if !validIfMatchVersion(ifMatch) {
			writeOperationRequestError(
				w,
				r,
				"quoted non-negative If-Match aggregate version is required",
			)
			return
		}
	} else if ifMatch != "" {
		writeOperationRequestError(
			w,
			r,
			"If-Match is forbidden for a server-owned concurrency operation",
		)
		return
	}
	if err := consumePendingDelegatedCommand(r.Context()); err != nil {
		writeOperationGuardError(
			w,
			r,
			"forbidden",
			"delegated command grant cannot be consumed: "+err.Error(),
		)
		return
	}
	ctx := context.WithValue(
		r.Context(),
		operationDescriptorContextKey{},
		descriptor.OperationSecurityDescriptor,
	)
	current, _ := operation.FromContext(ctx)
	current.OperationID = descriptor.CanonicalOperationID
	current.IdempotencyKey = idempotencyKey
	if hasPrincipal {
		current.Actor = principal.Actor
	} else {
		current.Actor = operation.ActorContext{}
	}
	ctx = operation.WithContext(ctx, current)
	// For a unary operation this is the whole-request budget. For a streaming
	// operation TimeoutMilliseconds is the derived connection lifetime
	// (stream_budget.max_duration_ms), so the same deadline closes a stream
	// whose underlying work never terminates. The handshake and idle bounds
	// cannot be expressed as a request deadline and are enforced by the stream
	// writer from the same descriptor.
	if descriptor.TimeoutMilliseconds > 0 {
		var cancel context.CancelFunc
		ctx, cancel = context.WithTimeout(
			ctx,
			time.Duration(descriptor.TimeoutMilliseconds)*time.Millisecond,
		)
		defer cancel()
	}
	next.ServeHTTP(w, r.WithContext(ctx))
}

// validIfMatchVersion 校验带引号的非负十进制聚合版本。
// `"0"` 表示「期望目标尚不存在」（首次创建，如 ConfigLayer 的 lazy create）；
// 正整数表示快照覆盖所基于的版本。是否允许 0 由各对象 handler 按语义收紧
// （如 UpdateExperimentRollout 要求 >0）。
func validIfMatchVersion(value string) bool {
	if len(value) < 3 || value[0] != '"' || value[len(value)-1] != '"' {
		return false
	}
	digits := value[1 : len(value)-1]
	if digits == "" {
		return false
	}
	if digits != "0" && digits[0] == '0' {
		return false
	}
	for _, digit := range digits {
		if digit < '0' || digit > '9' {
			return false
		}
	}
	return true
}

func compilePathTemplate(template string) (*regexp.Regexp, error) {
	template = strings.TrimSpace(template)
	if template == "" || !strings.HasPrefix(template, "/") ||
		strings.ContainsAny(template, "?#") {
		return nil, fmt.Errorf("invalid path template %q", template)
	}
	var pattern strings.Builder
	pattern.WriteString("^")
	for index := 0; index < len(template); {
		if template[index] == '}' {
			return nil, fmt.Errorf("invalid path template %q", template)
		}
		if template[index] != '{' {
			next := strings.IndexByte(template[index:], '{')
			if next < 0 {
				pattern.WriteString(regexp.QuoteMeta(template[index:]))
				index = len(template)
				continue
			}
			pattern.WriteString(regexp.QuoteMeta(template[index : index+next]))
			index += next
			continue
		}
		end := strings.IndexByte(template[index:], '}')
		if end <= 1 {
			return nil, fmt.Errorf("invalid path template %q", template)
		}
		placeholder := template[index+1 : index+end]
		if strings.ContainsAny(placeholder, "{} /") {
			return nil, fmt.Errorf("invalid path template %q", template)
		}
		pattern.WriteString("[^/]+")
		index += end + 1
	}
	pattern.WriteString("$")
	return regexp.Compile(pattern.String())
}

func matchOperation(
	descriptors []compiledOperationDescriptor,
	method string,
	path string,
) (compiledOperationDescriptor, bool) {
	best := compiledOperationDescriptor{}
	found := false
	for _, descriptor := range descriptors {
		if descriptor.Method != method || !descriptor.pathPattern.MatchString(path) {
			continue
		}
		if found && descriptor.pathSpecificity == best.pathSpecificity &&
			descriptor.CanonicalOperationID != best.CanonicalOperationID {
			return compiledOperationDescriptor{}, false
		}
		if !found || descriptor.pathSpecificity > best.pathSpecificity {
			best = descriptor
			found = true
		}
	}
	return best, found
}

func operationPathSpecificity(templatePath string) int {
	score := 0
	inParameter := false
	for _, char := range templatePath {
		switch char {
		case '{':
			inParameter = true
		case '}':
			inParameter = false
		default:
			if !inParameter {
				score++
			}
		}
	}
	return score
}

func actorRequirementSatisfied(
	requirement string,
	actor operation.ActorContext,
) bool {
	normalized := operation.ActorRequirement(strings.TrimSpace(requirement))
	if normalized == "" {
		normalized = operation.ActorNone
	}
	return actor.Validate(normalized) == nil
}

func principalRequirementSatisfied(principal string, current Principal) bool {
	switch principal {
	case "", "public":
		return true
	case "account":
		return strings.TrimSpace(current.Actor.AccountID) != ""
	case "persona":
		return strings.TrimSpace(current.Actor.PersonaID) != ""
	case "device":
		return strings.TrimSpace(current.Actor.DeviceActorID) != ""
	case "operator_or_service":
		return containsAny(current.Roles, []string{"operator", "service"})
	case "service", "admin", "operator":
		return containsAll(current.Roles, []string{principal})
	default:
		return false
	}
}

func claimsContainAllScopes(current Principal, required []string) bool {
	return containsAll(strings.Fields(current.Scope), required)
}

func claimsContainAllPermissions(current Principal, required []string) bool {
	return containsAll(current.Permissions, required)
}

func containsAll(availableValues []string, required []string) bool {
	if len(required) == 0 {
		return true
	}
	available := map[string]struct{}{}
	for _, value := range availableValues {
		available[value] = struct{}{}
	}
	for _, value := range required {
		if _, ok := available[value]; !ok {
			return false
		}
	}
	return true
}

func containsAny(availableValues []string, expectedValues []string) bool {
	available := map[string]struct{}{}
	for _, value := range availableValues {
		available[value] = struct{}{}
	}
	for _, expected := range expectedValues {
		if _, ok := available[expected]; ok {
			return true
		}
	}
	return false
}

// operationGuardUserMessages mirrors the baseline user_message of the gateway
// admission errors declared in
// services/api-edge/contracts/edge_security/operation_admission_decision/errors.yaml.
// The guard runs in runtime and is mounted by every service, so it cannot
// import one service's generated error package; the contract remains the
// declaring authority and TestOperationGuardUserMessagesMatchContract fails the
// build as soon as the two drift.
//
//nolint:gochecknoglobals
var operationGuardUserMessages = map[string]string{
	"route_not_found":  "接口不存在或已下线",
	"unauthorized":     "请先登录后再继续",
	"forbidden":        "当前账号没有该操作权限",
	"invalid_argument": "请求参数不完整，请重试",
}

func writeOperationGuardError(
	w http.ResponseWriter,
	r *http.Request,
	reason string,
	debugMessage string,
) {
	userMessage, declared := operationGuardUserMessages[reason]
	if !declared {
		panic("operation guard rejection reason has no declared user message: " + reason)
	}
	rterr.WriteHTTPError(
		w,
		rterr.NewAppError(
			rterr.NewCode(rterr.ModuleGateway, rterr.KindUser, reason),
			userMessage,
			debugMessage,
		),
		rterr.HTTPWriteOptionsFromRequest(r),
	)
}

func writeOperationRequestError(
	w http.ResponseWriter,
	r *http.Request,
	debugMessage string,
) {
	rterr.WriteHTTPError(
		w,
		rterr.NewInvalidArgument(
			rterr.ModuleGateway,
			operationGuardUserMessages["invalid_argument"],
			debugMessage,
		),
		rterr.HTTPWriteOptionsFromRequest(r),
	)
}
