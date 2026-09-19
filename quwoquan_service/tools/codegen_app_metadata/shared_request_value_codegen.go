package main

import "fmt"

// mergeCanonicalRequestValues 把请求依赖纳入现有 response/shared owner 归并，
// 请求根仍由各 operation part 拥有；仅共享 canonical 值可跨请求/响应复用。
func mergeCanonicalRequestValues(specs map[string]*domainOperationContractSpec, groups map[string][]appExposedOperation) error {
	canonical, err := loadCanonicalSharedValueModels()
	if err != nil {
		return err
	}
	for owner, operations := range groups {
		for _, operation := range operations {
			_, dependencies, err := loadOperationRequestModel(operation, operation.RequestEntity)
			if err != nil {
				return fmt.Errorf("%s shared request dependencies: %w", operation.CanonicalOperationID, err)
			}
			if err := mergeRequestValueDependencies(specs[owner], dependencies, canonical); err != nil {
				return fmt.Errorf("%s shared request owner: %w", operation.CanonicalOperationID, err)
			}
		}
	}
	return nil
}

func mergeRequestValueDependencies(spec *domainOperationContractSpec, dependencies, canonical map[string]requestModelSpec) error {
	for name, dependency := range dependencies {
		definition, shared := canonical[name]
		if !shared {
			continue
		}
		if responseModelFingerprint(dependency) != responseModelFingerprint(definition) {
			return fmt.Errorf("request value %s in %s conflicts with canonical _shared/types.yaml", name, spec.OwnerImport)
		}
		if err := mergeDomainResponseModel(spec.Models, definition); err != nil {
			return fmt.Errorf("%s shared request value %s: %w", spec.OwnerImport, name, err)
		}
	}
	return nil
}

// includeSharedProvidedModels 告诉 request emitter：owner 已 import/re-export 的共享
// 值具有可见的唯一实现，禁止在每个 request part 再造同名但不同身份的 Dart 类。
func includeSharedProvidedModels(provided map[string]map[string]struct{}, specs map[string]*domainOperationContractSpec) {
	shared := specs[sharedDomainOperationTypesImport]
	if shared == nil {
		return
	}
	for owner, spec := range specs {
		if _, imports := spec.ExternalImports[sharedDomainOperationTypesImport]; !imports {
			continue
		}
		for name := range shared.Models {
			provided[owner][name] = struct{}{}
		}
	}
}
