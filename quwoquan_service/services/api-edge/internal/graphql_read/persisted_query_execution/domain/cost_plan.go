package domain

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"math"
	"sort"
	"strings"
)

const CostModelVersionV1 = "graphql-cost-v1"

type ListMultiplier struct {
	VariablePath string `json:"variablePath"`
	Coefficient  int    `json:"coefficient"`
	DefaultValue int    `json:"defaultValue"`
	MaximumValue int    `json:"maximumValue"`
}

type CostPlan struct {
	BaseComplexity   int              `json:"baseComplexity"`
	ListMultipliers  []ListMultiplier `json:"listMultipliers"`
	MaxOwnerCalls    int              `json:"maxOwnerCalls"`
	MaxBatchKeys     int              `json:"maxBatchKeys"`
	MaxResponseBytes int              `json:"maxResponseBytes"`
}

func (plan CostPlan) Validate() error {
	if plan.BaseComplexity < 1 {
		return errors.New("baseComplexity must be positive")
	}
	if plan.ListMultipliers == nil {
		return errors.New("listMultipliers must be an explicit array")
	}
	if plan.MaxOwnerCalls < 1 || plan.MaxOwnerCalls > MaxOwnerCalls {
		return fmt.Errorf("maxOwnerCalls=%d is outside 1..%d", plan.MaxOwnerCalls, MaxOwnerCalls)
	}
	if plan.MaxBatchKeys < 1 || plan.MaxBatchKeys > MaxBatchKeys {
		return fmt.Errorf("maxBatchKeys=%d is outside 1..%d", plan.MaxBatchKeys, MaxBatchKeys)
	}
	if plan.MaxResponseBytes < 1 || plan.MaxResponseBytes > MaxResponseBytes {
		return fmt.Errorf("maxResponseBytes=%d is outside 1..%d", plan.MaxResponseBytes, MaxResponseBytes)
	}
	paths := make([]string, 0, len(plan.ListMultipliers))
	for index, multiplier := range plan.ListMultipliers {
		if !variablePath.MatchString(multiplier.VariablePath) {
			return fmt.Errorf("listMultipliers[%d].variablePath=%q is invalid", index, multiplier.VariablePath)
		}
		if multiplier.Coefficient < 1 {
			return fmt.Errorf("listMultipliers[%d].coefficient must be positive", index)
		}
		if multiplier.DefaultValue < 1 || multiplier.DefaultValue > MaxPageSize {
			return fmt.Errorf("listMultipliers[%d].defaultValue is outside 1..%d", index, MaxPageSize)
		}
		if multiplier.MaximumValue < multiplier.DefaultValue || multiplier.MaximumValue > MaxPageSize {
			return fmt.Errorf(
				"listMultipliers[%d].maximumValue is outside defaultValue..%d",
				index,
				MaxPageSize,
			)
		}
		paths = append(paths, multiplier.VariablePath)
	}
	if !sort.StringsAreSorted(paths) {
		return errors.New("listMultipliers must be sorted by variablePath")
	}
	for index := 1; index < len(paths); index++ {
		if paths[index] == paths[index-1] {
			return fmt.Errorf("listMultipliers contains duplicate variablePath %q", paths[index])
		}
	}
	if _, err := plan.WorstCaseComplexity(); err != nil {
		return err
	}
	return nil
}

func (plan CostPlan) Digest() (string, error) {
	if err := plan.Validate(); err != nil {
		return "", err
	}
	// CostPlan's field order is the canonical generator wire order. Hash the
	// typed value directly so generator and runtime can never disagree because
	// of map-key ordering.
	encoded, err := json.Marshal(plan)
	if err != nil {
		return "", fmt.Errorf("marshal canonical cost plan: %w", err)
	}
	sum := sha256.Sum256(encoded)
	return "sha256:" + hex.EncodeToString(sum[:]), nil
}

func (plan CostPlan) WorstCaseComplexity() (int, error) {
	complexity := int64(plan.BaseComplexity)
	for index, multiplier := range plan.ListMultipliers {
		delta := int64(multiplier.MaximumValue) - int64(multiplier.DefaultValue)
		increment, ok := checkedMultiply(int64(multiplier.Coefficient), delta)
		if !ok {
			return 0, fmt.Errorf("listMultipliers[%d] worst-case complexity overflows", index)
		}
		var added bool
		complexity, added = checkedAdd(complexity, increment)
		if !added || complexity > int64(math.MaxInt) {
			return 0, errors.New("worst-case complexity overflows")
		}
	}
	if complexity < 1 {
		return 0, errors.New("worst-case complexity must be positive")
	}
	return int(complexity), nil
}

func (plan CostPlan) Evaluate(variables map[string]any) (int, error) {
	if err := plan.Validate(); err != nil {
		return 0, err
	}
	complexity := int64(plan.BaseComplexity)
	for _, multiplier := range plan.ListMultipliers {
		value, exists, err := costValueAtPath(variables, multiplier.VariablePath)
		if err != nil {
			return 0, err
		}
		actual := int64(multiplier.DefaultValue)
		if exists {
			actual, err = costInteger(value)
			if err != nil {
				return 0, fmt.Errorf("cost variable %s: %w", multiplier.VariablePath, err)
			}
		}
		if actual < 1 || actual > int64(multiplier.MaximumValue) {
			return 0, fmt.Errorf(
				"cost variable %s=%d is outside 1..%d",
				multiplier.VariablePath,
				actual,
				multiplier.MaximumValue,
			)
		}
		delta := actual - int64(multiplier.DefaultValue)
		increment, ok := checkedMultiply(int64(multiplier.Coefficient), delta)
		if !ok {
			return 0, fmt.Errorf("cost variable %s complexity overflows", multiplier.VariablePath)
		}
		complexity, ok = checkedAdd(complexity, increment)
		if !ok || complexity > int64(math.MaxInt) {
			return 0, errors.New("actual complexity overflows")
		}
	}
	if complexity < 1 {
		return 0, errors.New("actual complexity must be positive")
	}
	worstCase, err := plan.WorstCaseComplexity()
	if err != nil {
		return 0, err
	}
	if complexity > int64(worstCase) {
		return 0, errors.New("actual complexity exceeds the signed worst case")
	}
	return int(complexity), nil
}

func costValueAtPath(root map[string]any, path string) (any, bool, error) {
	var current any = root
	for _, segment := range strings.Split(path, ".") {
		object, ok := current.(map[string]any)
		if !ok {
			return nil, false, fmt.Errorf("cost variable path %s crosses a non-object value", path)
		}
		current, ok = object[segment]
		if !ok {
			return nil, false, nil
		}
	}
	return current, true, nil
}

func costInteger(value any) (int64, error) {
	switch number := value.(type) {
	case json.Number:
		parsed, err := number.Int64()
		if err != nil {
			return 0, errors.New("must be an integer")
		}
		return parsed, nil
	case int:
		return int64(number), nil
	case int8:
		return int64(number), nil
	case int16:
		return int64(number), nil
	case int32:
		return int64(number), nil
	case int64:
		return number, nil
	case uint:
		if uint64(number) > math.MaxInt64 {
			return 0, errors.New("integer overflows")
		}
		return int64(number), nil
	case uint8:
		return int64(number), nil
	case uint16:
		return int64(number), nil
	case uint32:
		return int64(number), nil
	case uint64:
		if number > math.MaxInt64 {
			return 0, errors.New("integer overflows")
		}
		return int64(number), nil
	default:
		return 0, errors.New("must be an integer")
	}
}

func checkedMultiply(left, right int64) (int64, bool) {
	if left == 0 || right == 0 {
		return 0, true
	}
	if left == -1 && right == math.MinInt64 || right == -1 && left == math.MinInt64 {
		return 0, false
	}
	product := left * right
	return product, product/right == left
}

func checkedAdd(left, right int64) (int64, bool) {
	if right > 0 && left > math.MaxInt64-right || right < 0 && left < math.MinInt64-right {
		return 0, false
	}
	return left + right, true
}
