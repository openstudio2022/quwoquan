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
	CommercialStatus     string
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
			authorizeGeneratedOperation(w, r, descriptor, next)
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
			authorizeGeneratedOperation(w, r, descriptor, next)
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
	next http.Handler,
) {
	if descriptor.CommercialStatus != "ready" || descriptor.AuthMode == "deny" {
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
	ctx := context.WithValue(
		r.Context(),
		operationDescriptorContextKey{},
		descriptor.OperationSecurityDescriptor,
	)
	current, _ := operation.FromContext(ctx)
	current.OperationID = descriptor.CanonicalOperationID
	current.IdempotencyKey = strings.TrimSpace(r.Header.Get("Idempotency-Key"))
	if current.IdempotencyKey == "" {
		current.IdempotencyKey = strings.TrimSpace(r.Header.Get("X-Request-Id"))
	}
	if hasPrincipal {
		current.Actor = principal.Actor
	} else {
		current.Actor = operation.ActorContext{}
	}
	ctx = operation.WithContext(ctx, current)
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

func writeOperationGuardError(
	w http.ResponseWriter,
	r *http.Request,
	reason string,
	debugMessage string,
) {
	rterr.WriteHTTPError(
		w,
		rterr.NewAppError(
			rterr.NewCode(rterr.ModuleGateway, rterr.KindUser, reason),
			"请求未获授权",
			debugMessage,
		),
		rterr.HTTPWriteOptionsFromRequest(r),
	)
}
