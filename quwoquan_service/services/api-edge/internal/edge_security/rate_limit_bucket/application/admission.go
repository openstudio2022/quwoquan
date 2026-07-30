package application

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/services/api-edge/internal/edge_security/rate_limit_bucket/domain"
)

var ErrSharedStateUnavailable = errors.New("gateway admission shared state unavailable")

type AtomicQuotaStore interface {
	Consume(
		ctx context.Context,
		key string,
		limit int64,
		window time.Duration,
	) (QuotaResult, error)
	Ping(ctx context.Context) error
	Close() error
}

type QuotaResult struct {
	Allowed    bool
	Remaining  int64
	RetryAfter time.Duration
}

type Observer interface {
	RecordDecision(environment, operation, outcome, failurePolicy string, elapsed time.Duration)
}

type noopObserver struct{}

func (noopObserver) RecordDecision(string, string, string, string, time.Duration) {}

type PolicySet struct {
	ByOperationKind map[string]domain.Policy
	ByOperationID   map[string]domain.Policy
}

func (policies PolicySet) Validate() error {
	for _, operationKind := range []string{"command", "query", "session"} {
		policy, exists := policies.ByOperationKind[operationKind]
		if !exists {
			return fmt.Errorf("admission policy for operation kind %q is required", operationKind)
		}
		if err := policy.Validate(); err != nil {
			return fmt.Errorf("%s admission policy: %w", operationKind, err)
		}
	}
	for operationID, policy := range policies.ByOperationID {
		if strings.TrimSpace(operationID) == "" {
			return errors.New("admission operation override id is required")
		}
		if err := policy.Validate(); err != nil {
			return fmt.Errorf("%s admission policy: %w", operationID, err)
		}
	}
	return nil
}

func (policies PolicySet) Resolve(descriptor rtauth.OperationSecurityDescriptor) (domain.Policy, error) {
	if policy, exists := policies.ByOperationID[descriptor.CanonicalOperationID]; exists {
		return policy, nil
	}
	policy, exists := policies.ByOperationKind[strings.TrimSpace(descriptor.OperationKind)]
	if !exists {
		return domain.Policy{}, fmt.Errorf(
			"no admission policy for operation %s kind %s",
			descriptor.CanonicalOperationID,
			descriptor.OperationKind,
		)
	}
	return policy, nil
}

type Decision struct {
	Allowed       bool
	RetryAfter    time.Duration
	FailurePolicy domain.FailurePolicy
	StateFailure  bool
}

type Service struct {
	environment string
	store       AtomicQuotaStore
	policies    PolicySet
	observer    Observer
}

func NewService(
	environment string,
	store AtomicQuotaStore,
	policies PolicySet,
	observer Observer,
) (*Service, error) {
	environment = strings.TrimSpace(environment)
	if environment != "alpha" && environment != "beta" && environment != "gamma" && environment != "prod" {
		return nil, fmt.Errorf("unsupported api-edge environment %q", environment)
	}
	if store == nil {
		return nil, errors.New("shared atomic quota store is required")
	}
	if err := policies.Validate(); err != nil {
		return nil, err
	}
	if observer == nil {
		observer = noopObserver{}
	}
	return &Service{
		environment: environment,
		store:       store,
		policies:    policies,
		observer:    observer,
	}, nil
}

func (service *Service) Admit(
	ctx context.Context,
	subject domain.Subject,
	descriptor rtauth.OperationSecurityDescriptor,
) (Decision, error) {
	startedAt := time.Now()
	policy, err := service.policies.Resolve(descriptor)
	if err != nil {
		service.observer.RecordDecision(
			service.environment,
			descriptor.CanonicalOperationID,
			"policy_invalid",
			string(domain.FailurePolicyFailClosed),
			time.Since(startedAt),
		)
		return Decision{}, err
	}
	key, err := domain.BucketKey(
		service.environment,
		subject,
		descriptor.CanonicalOperationID,
	)
	if err != nil {
		service.observer.RecordDecision(
			service.environment,
			descriptor.CanonicalOperationID,
			"subject_invalid",
			string(domain.FailurePolicyFailClosed),
			time.Since(startedAt),
		)
		return Decision{}, err
	}
	result, storeErr := service.store.Consume(ctx, key, policy.Limit, policy.Window)
	if storeErr != nil {
		outcome := "state_unavailable_denied"
		allowed := false
		if policy.StateFailure == domain.FailurePolicyFailOpen {
			outcome = "state_unavailable_allowed"
			allowed = true
		}
		service.observer.RecordDecision(
			service.environment,
			descriptor.CanonicalOperationID,
			outcome,
			string(policy.StateFailure),
			time.Since(startedAt),
		)
		decision := Decision{
			Allowed:       allowed,
			RetryAfter:    time.Second,
			FailurePolicy: policy.StateFailure,
			StateFailure:  true,
		}
		if allowed {
			return decision, nil
		}
		return decision, fmt.Errorf("%w: %v", ErrSharedStateUnavailable, storeErr)
	}
	outcome := "allowed"
	if !result.Allowed {
		outcome = "rate_limited"
	}
	service.observer.RecordDecision(
		service.environment,
		descriptor.CanonicalOperationID,
		outcome,
		string(policy.StateFailure),
		time.Since(startedAt),
	)
	return Decision{
		Allowed:       result.Allowed,
		RetryAfter:    result.RetryAfter,
		FailurePolicy: policy.StateFailure,
	}, nil
}

func (service *Service) Ready(ctx context.Context) error {
	if err := service.store.Ping(ctx); err != nil {
		return fmt.Errorf("shared admission state: %w", err)
	}
	return nil
}

func (service *Service) Close() error {
	return service.store.Close()
}
