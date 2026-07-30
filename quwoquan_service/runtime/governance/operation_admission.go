package runtimegovernance

import (
	"net/http"
	"strings"

	rtauth "quwoquan_service/runtime/auth"
)

// OperationAdmissionPolicy binds owner resource concurrency to one
// ContractGraph operation. Business arrival quota is exclusively enforced by
// api-edge's shared state before the owner is reached.
type OperationAdmissionPolicy struct {
	CanonicalOperationID string
	InflightLimiter      *InflightLimiter
}

type OperationAdmissionRejection string

const OperationAdmissionInflightFull OperationAdmissionRejection = "inflight_full"

type OperationAdmissionRejectWriter func(
	http.ResponseWriter,
	*http.Request,
	OperationAdmissionRejection,
)

// OperationAdmissionMiddleware sheds route-specific excess load without an
// unbounded wait queue. The owner supplies the canonical error writer because
// error codes and recovery semantics remain service-contract-owned.
func OperationAdmissionMiddleware(
	policies []OperationAdmissionPolicy,
	reject OperationAdmissionRejectWriter,
) func(http.Handler) http.Handler {
	if reject == nil {
		panic("operation admission reject writer is required")
	}
	byOperation := make(map[string]OperationAdmissionPolicy, len(policies))
	for _, policy := range policies {
		operationID := strings.TrimSpace(policy.CanonicalOperationID)
		if operationID == "" {
			panic("operation admission canonical operation id is required")
		}
		if policy.InflightLimiter == nil {
			panic("owner operation admission requires an in-flight limiter")
		}
		if _, exists := byOperation[operationID]; exists {
			panic("duplicate operation admission policy: " + operationID)
		}
		policy.CanonicalOperationID = operationID
		byOperation[operationID] = policy
	}

	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			descriptor, ok := rtauth.OperationDescriptorFromContext(r.Context())
			if !ok {
				next.ServeHTTP(w, r)
				return
			}
			policy, ok := byOperation[descriptor.CanonicalOperationID]
			if !ok {
				next.ServeHTTP(w, r)
				return
			}
			if !policy.InflightLimiter.Acquire() {
				reject(w, r, OperationAdmissionInflightFull)
				return
			}
			defer policy.InflightLimiter.Release()
			next.ServeHTTP(w, r)
		})
	}
}
