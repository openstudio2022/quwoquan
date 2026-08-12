package retrievalplan

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"sort"
	"strings"
)

const maxQueriesHardLimit = 8

// Identity freezes the execution authorities that make a RetrievalPlan safe to
// replay. None of these values are authored by the model.
type Identity struct {
	RunID               string `json:"runId"`
	TurnID              string `json:"turnId"`
	ToolName            string `json:"toolName"`
	ToolCatalogDigest   string `json:"toolCatalogDigest"`
	AccessPolicyDigest  string `json:"accessPolicyDigest"`
	CandidateDigest     string `json:"candidateDigest"`
	ContractGraphDigest string `json:"contractGraphDigest"`
	MaximumToolCalls    int    `json:"maximumToolCalls"`
}

// Query is one explicitly budgeted dimension in a retrieval plan. Query order
// is semantically significant and is preserved by both execution and output.
type Query struct {
	Dimension   string   `json:"dimension"`
	Query       string   `json:"query"`
	ObjectTypes []string `json:"objectTypes"`
	Limit       int      `json:"limit"`
}

type Input struct {
	Goal             string   `json:"goal"`
	Queries          []Query  `json:"queries"`
	EvidenceCriteria []string `json:"evidenceCriteria"`
	MaximumQueries   int      `json:"maximumQueries"`
	Identity         Identity `json:"identity"`
}

// Plan is immutable-by-digest. Validate recomputes the digest so a caller
// cannot mutate the plan between planning and execution without detection.
type Plan struct {
	Goal             string   `json:"goal"`
	Queries          []Query  `json:"queries"`
	EvidenceCriteria []string `json:"evidenceCriteria"`
	MaximumQueries   int      `json:"maximumQueries"`
	Identity         Identity `json:"identity"`
	Digest           string   `json:"digest"`
}

func Freeze(input Input) (Plan, error) {
	canonical := canonicalInput(input)
	if err := validateInput(canonical); err != nil {
		return Plan{}, err
	}
	digest, err := digestInput(canonical)
	if err != nil {
		return Plan{}, err
	}
	return Plan{
		Goal:             canonical.Goal,
		Queries:          cloneQueries(canonical.Queries),
		EvidenceCriteria: append([]string(nil), canonical.EvidenceCriteria...),
		MaximumQueries:   canonical.MaximumQueries,
		Identity:         canonical.Identity,
		Digest:           digest,
	}, nil
}

func (plan Plan) Validate() error {
	canonical := canonicalInput(Input{
		Goal:             plan.Goal,
		Queries:          plan.Queries,
		EvidenceCriteria: plan.EvidenceCriteria,
		MaximumQueries:   plan.MaximumQueries,
		Identity:         plan.Identity,
	})
	if err := validateInput(canonical); err != nil {
		return err
	}
	expected, err := digestInput(canonical)
	if err != nil {
		return err
	}
	if plan.Digest != expected {
		return fmt.Errorf("retrieval plan digest mismatch: got %q want %q", plan.Digest, expected)
	}
	return nil
}

func canonicalInput(input Input) Input {
	input.Goal = strings.TrimSpace(input.Goal)
	input.Identity.RunID = strings.TrimSpace(input.Identity.RunID)
	input.Identity.TurnID = strings.TrimSpace(input.Identity.TurnID)
	input.Identity.ToolName = strings.TrimSpace(input.Identity.ToolName)
	input.Identity.ToolCatalogDigest = strings.TrimSpace(input.Identity.ToolCatalogDigest)
	input.Identity.AccessPolicyDigest = strings.TrimSpace(input.Identity.AccessPolicyDigest)
	input.Identity.CandidateDigest = strings.TrimSpace(input.Identity.CandidateDigest)
	input.Identity.ContractGraphDigest = strings.TrimSpace(input.Identity.ContractGraphDigest)
	input.Queries = cloneQueries(input.Queries)
	for index := range input.Queries {
		query := &input.Queries[index]
		query.Dimension = strings.TrimSpace(query.Dimension)
		query.Query = strings.TrimSpace(query.Query)
		values := make([]string, 0, len(query.ObjectTypes))
		seen := map[string]struct{}{}
		for _, raw := range query.ObjectTypes {
			value := strings.TrimSpace(raw)
			if value == "" {
				continue
			}
			if _, duplicated := seen[value]; duplicated {
				continue
			}
			seen[value] = struct{}{}
			values = append(values, value)
		}
		sort.Strings(values)
		query.ObjectTypes = values
	}
	criteria := make([]string, 0, len(input.EvidenceCriteria))
	for _, raw := range input.EvidenceCriteria {
		if value := strings.TrimSpace(raw); value != "" {
			criteria = append(criteria, value)
		}
	}
	input.EvidenceCriteria = criteria
	return input
}

func validateInput(input Input) error {
	if input.Goal == "" {
		return errors.New("retrieval plan goal is required")
	}
	if input.MaximumQueries <= 0 || input.MaximumQueries > maxQueriesHardLimit {
		return fmt.Errorf("retrieval plan maximumQueries must be in 1..%d", maxQueriesHardLimit)
	}
	if len(input.Queries) == 0 {
		return errors.New("retrieval plan requires at least one query")
	}
	if len(input.Queries) > input.MaximumQueries {
		return fmt.Errorf("retrieval plan has %d queries above maximumQueries=%d", len(input.Queries), input.MaximumQueries)
	}
	if input.MaximumQueries > input.Identity.MaximumToolCalls {
		return fmt.Errorf("retrieval plan maximumQueries=%d exceeds maximumToolCalls=%d", input.MaximumQueries, input.Identity.MaximumToolCalls)
	}
	if len(input.EvidenceCriteria) == 0 {
		return errors.New("retrieval plan evidenceCriteria is required")
	}
	seenDimensions := map[string]struct{}{}
	for index, query := range input.Queries {
		if query.Dimension == "" || query.Query == "" {
			return fmt.Errorf("retrieval plan query[%d] requires dimension and query", index)
		}
		if query.Limit <= 0 || query.Limit > 50 {
			return fmt.Errorf("retrieval plan query[%d].limit must be in 1..50", index)
		}
		if _, duplicated := seenDimensions[query.Dimension]; duplicated {
			return fmt.Errorf("retrieval plan dimension %q is duplicated", query.Dimension)
		}
		seenDimensions[query.Dimension] = struct{}{}
	}
	if input.Identity.RunID == "" {
		return errors.New("retrieval plan runId is required")
	}
	if input.Identity.TurnID == "" {
		return errors.New("retrieval plan turnId is required")
	}
	if input.Identity.ToolName == "" {
		return errors.New("retrieval plan toolName is required")
	}
	for name, value := range map[string]string{
		"toolCatalogDigest":   input.Identity.ToolCatalogDigest,
		"accessPolicyDigest":  input.Identity.AccessPolicyDigest,
		"candidateDigest":     input.Identity.CandidateDigest,
		"contractGraphDigest": input.Identity.ContractGraphDigest,
	} {
		if !validSHA256(value) {
			return fmt.Errorf("retrieval plan %s must be sha256:<64 lowercase hex>", name)
		}
	}
	if input.Identity.MaximumToolCalls <= 0 {
		return errors.New("retrieval plan maximumToolCalls must be positive")
	}
	return nil
}

func digestInput(input Input) (string, error) {
	payload, err := json.Marshal(input)
	if err != nil {
		return "", fmt.Errorf("encode retrieval plan: %w", err)
	}
	digest := sha256.Sum256(append([]byte("assistant-retrieval-plan-v1\x00"), payload...))
	return "sha256:" + hex.EncodeToString(digest[:]), nil
}

func validSHA256(value string) bool {
	if !strings.HasPrefix(value, "sha256:") || len(value) != 71 {
		return false
	}
	_, err := hex.DecodeString(strings.TrimPrefix(value, "sha256:"))
	return err == nil && strings.ToLower(value) == value
}

func cloneQueries(values []Query) []Query {
	result := make([]Query, 0, len(values))
	for _, value := range values {
		value.ObjectTypes = append([]string(nil), value.ObjectTypes...)
		result = append(result, value)
	}
	return result
}
