package domain

import (
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"strings"
	"time"
)

const (
	MaxLimit         = 1_000_000
	MaxWindow        = 24 * time.Hour
	MaxAdmissionKey  = 192
	admissionKeyRoot = "edge:rate"
)

type FailurePolicy string

const (
	FailurePolicyFailClosed FailurePolicy = "fail_closed"
	FailurePolicyFailOpen   FailurePolicy = "fail_open"
)

type Policy struct {
	Limit        int64
	Window       time.Duration
	StateFailure FailurePolicy
}

func (policy Policy) Validate() error {
	if policy.Limit <= 0 || policy.Limit > MaxLimit {
		return fmt.Errorf("rate limit must be within 1..%d", MaxLimit)
	}
	if policy.Window <= 0 || policy.Window > MaxWindow {
		return fmt.Errorf("rate limit window must be within 1ms..%s", MaxWindow)
	}
	switch policy.StateFailure {
	case FailurePolicyFailClosed, FailurePolicyFailOpen:
		return nil
	default:
		return fmt.Errorf("unsupported shared-state failure policy %q", policy.StateFailure)
	}
}

type Subject struct {
	Kind string
	ID   string
}

func (subject Subject) Validate() error {
	switch strings.TrimSpace(subject.Kind) {
	case "persona", "account", "device", "service", "operator", "network":
	default:
		return fmt.Errorf("unsupported admission subject kind %q", subject.Kind)
	}
	if strings.TrimSpace(subject.ID) == "" {
		return errors.New("admission subject id is required")
	}
	return nil
}

// BucketKey hashes both variable identifiers in full. It never stores a raw
// user, device, network, service, or operation identifier in Redis.
func BucketKey(environment string, subject Subject, canonicalOperationID string) (string, error) {
	environment = strings.TrimSpace(environment)
	if environment != "alpha" && environment != "beta" && environment != "gamma" && environment != "prod" {
		return "", fmt.Errorf("unsupported admission environment %q", environment)
	}
	if err := subject.Validate(); err != nil {
		return "", err
	}
	canonicalOperationID = strings.TrimSpace(canonicalOperationID)
	if canonicalOperationID == "" {
		return "", errors.New("canonical operation id is required")
	}
	subjectDigest := sha256.Sum256([]byte(strings.TrimSpace(subject.Kind) + "\x00" + strings.TrimSpace(subject.ID)))
	operationDigest := sha256.Sum256([]byte(canonicalOperationID))
	key := strings.Join([]string{
		admissionKeyRoot,
		environment,
		hex.EncodeToString(subjectDigest[:]),
		hex.EncodeToString(operationDigest[:]),
	}, ":")
	if len(key) > MaxAdmissionKey {
		return "", fmt.Errorf("admission key length %d exceeds %d", len(key), MaxAdmissionKey)
	}
	return key, nil
}
