package compiler

import (
	"fmt"

	"quwoquan_service/internal/metadata/graph"
	"quwoquan_service/internal/metadata/load"
	"quwoquan_service/internal/metadata/validate"
)

// Build 是 metadata 到 ContractGraph 的唯一编译入口。
func Build(metadataDir string) (*graph.ContractGraph, error) {
	catalog, err := load.Load(metadataDir)
	if err != nil {
		return nil, err
	}
	contractGraph := graph.Build(catalog)
	if err := validate.ContractGraphSchema(metadataDir, contractGraph); err != nil {
		return nil, err
	}
	return contractGraph, nil
}

// Validate 在同一已编译图上执行 profile 规则，供 validate/coverage/codegen 共用。
func Validate(
	metadataDir string,
	profile validate.Profile,
) (*graph.ContractGraph, []validate.Issue, error) {
	contractGraph, err := Build(metadataDir)
	if err != nil {
		return nil, nil, err
	}
	issues, err := validate.All(contractGraph, profile, metadataDir)
	if err != nil {
		return nil, nil, err
	}
	return contractGraph, issues, nil
}

// RequireValid 是 generator 的入口：任何契约问题都阻断产物生成。
func RequireValid(
	metadataDir string,
	profile validate.Profile,
) (*graph.ContractGraph, error) {
	contractGraph, issues, err := Validate(metadataDir, profile)
	if err != nil {
		return nil, err
	}
	if len(issues) != 0 {
		return nil, fmt.Errorf(
			"ContractGraph validation failed with %d issue(s)",
			len(issues),
		)
	}
	return contractGraph, nil
}
