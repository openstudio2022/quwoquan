package main

import (
	"fmt"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
)

type domainOperationContractSpec struct {
	Domain                   string
	OwnerImport              string
	HasRequestPart           bool
	Models                   map[string]requestModelSpec
	ResponseEntities         map[string]struct{}
	HasEmptyResponse         bool
	ExternalResponseEntities map[string]struct{}
	ExternalImports          map[string]struct{}
	ExternalExports          map[string]struct{}
	EnumMembers              map[string][]canonicalRequestEnumMember
	EnumUnknownMembers       map[string]string
}

// generateDomainOperationContracts emits the response side of every generic
// domain operation owner. The request part is generated separately, but both
// artifacts are one Dart library and therefore share response value objects
// and canonical enums without redeclaring them.
func generateDomainOperationContracts(
	metadataDir string,
	appDir string,
	lock appContractLock,
) (map[string]map[string]struct{}, error) {
	_ = metadataDir
	groups := map[string][]appExposedOperation{}
	for _, operation := range lock.AppExposedOperations {
		client := operation.ClientContract
		if client == nil || operation.Domain == "assistant" {
			continue
		}
		ownerImport := generatedDomainOperationOwnerImport(operation.Domain)
		if client.DartImport != ownerImport {
			continue
		}
		responseBodyKind := strings.TrimSpace(operation.ResponseBodyKind)
		emptyResponse := client.ResponseType == "void" &&
			client.ResponseDecoder == "decodeEmptyResponse" &&
			strings.TrimSpace(operation.ResponseEntity) == "" &&
			(responseBodyKind == "ack" || responseBodyKind == "upgrade")
		if !emptyResponse && (client.ResponseType != operation.ResponseEntity ||
			client.ResponseDecoder != "decode"+client.ResponseType) {
			return nil, fmt.Errorf(
				"%s generic client ABI must follow response_entity exactly",
				operation.CanonicalOperationID,
			)
		}
		groups[ownerImport] = append(groups[ownerImport], operation)
	}

	provided := map[string]map[string]struct{}{}
	specs := map[string]*domainOperationContractSpec{}
	owners := make([]string, 0, len(groups))
	for owner := range groups {
		owners = append(owners, owner)
	}
	sort.Strings(owners)
	for _, owner := range owners {
		spec, err := loadDomainOperationContractSpec(owner, groups[owner])
		if err != nil {
			return nil, err
		}
		spec.HasRequestPart = true
		specs[owner] = &spec
	}
	if err := externalizeCanonicalDomainModels(specs); err != nil {
		return nil, err
	}
	if err := externalizeSharedDomainModels(specs); err != nil {
		return nil, err
	}
	owners = owners[:0]
	for owner := range specs {
		owners = append(owners, owner)
	}
	sort.Strings(owners)
	for _, owner := range owners {
		if err := finalizeDomainOperationContractSpec(specs[owner]); err != nil {
			return nil, err
		}
	}
	if err := externalizeSharedDomainEnums(specs, appDir); err != nil {
		return nil, err
	}
	for _, owner := range owners {
		spec := specs[owner]
		content, err := renderDomainOperationContract(*spec)
		if err != nil {
			return nil, err
		}
		ownerRelative := strings.TrimPrefix(owner, "../")
		writeFile(filepath.Join(
			appDir,
			"packages",
			"quwoquan_cloud_contracts",
			"lib",
			"src",
			filepath.FromSlash(ownerRelative),
		), content)
		provided[owner] = make(map[string]struct{}, len(spec.Models))
		for name := range spec.Models {
			provided[owner][name] = struct{}{}
		}
	}
	return provided, nil
}

const sharedDomainOperationEnumsImport = "../generated/shared_operation_enums.g.dart"

const sharedDomainOperationTypesImport = "../generated/shared_operation_types.g.dart"

const sharedRealtimeEventCatalogImport = "../generated/realtime/realtime_event_catalog.g.dart"

const packageInternalIntersectionContractVocabularyImport = "../generated/recommendation/intersection_contract_vocabulary.g.dart"

func loadCanonicalSharedValueModels() (map[string]requestModelSpec, error) {
	if activeMetadataSource == nil {
		return nil, fmt.Errorf("ContractGraph is not initialized")
	}
	const ownerPath = "_shared/types.yaml"
	if !activeMetadataSource.Has(ownerPath) {
		return nil, fmt.Errorf("canonical shared value owner %s is missing", ownerPath)
	}
	var document fieldsFile
	if err := activeMetadataSource.Decode(ownerPath, &document); err != nil {
		return nil, fmt.Errorf("decode canonical shared value owner %s: %w", ownerPath, err)
	}
	result := make(map[string]requestModelSpec, len(document.Types))
	for name, definition := range document.Types {
		if len(definition.Fields) == 0 {
			continue
		}
		result[name] = requestModelSpec{
			Name:   name,
			Fields: append([]fieldDef(nil), definition.Fields...),
		}
	}
	return result, nil
}

// externalizeSharedDomainModels gives a cross-domain value object one Dart
// owner only when _shared/types.yaml owns the concept and every domain model is
// byte-shape equivalent to that canonical definition. Identical local names
// without a shared source owner fail closed instead of being merged by chance.
func externalizeSharedDomainModels(
	specs map[string]*domainOperationContractSpec,
) error {
	canonical, err := loadCanonicalSharedValueModels()
	if err != nil {
		return err
	}
	ownersByModel := map[string][]string{}
	for owner, spec := range specs {
		for name := range spec.Models {
			ownersByModel[name] = append(ownersByModel[name], owner)
		}
	}
	sharedModels := map[string]requestModelSpec{}
	for name, owners := range ownersByModel {
		if len(owners) < 2 {
			continue
		}
		canonicalModel, exists := canonical[name]
		if !exists {
			return fmt.Errorf(
				"cross-domain response model %s has no canonical _shared/types.yaml owner",
				name,
			)
		}
		canonicalFingerprint := responseModelFingerprint(canonicalModel)
		sort.Strings(owners)
		for _, owner := range owners {
			model := specs[owner].Models[name]
			if responseModelFingerprint(model) != canonicalFingerprint {
				return fmt.Errorf(
					"cross-domain response model %s in %s conflicts with canonical _shared/types.yaml",
					name,
					owner,
				)
			}
		}
		sharedModels[name] = canonicalModel
		for _, owner := range owners {
			spec := specs[owner]
			spec.ExternalImports[sharedDomainOperationTypesImport] = struct{}{}
			spec.ExternalExports[sharedDomainOperationTypesImport] = struct{}{}
			delete(spec.Models, name)
		}
	}
	if len(sharedModels) == 0 {
		return nil
	}
	specs[sharedDomainOperationTypesImport] = &domainOperationContractSpec{
		Domain:                   "shared",
		OwnerImport:              sharedDomainOperationTypesImport,
		Models:                   sharedModels,
		ResponseEntities:         map[string]struct{}{},
		ExternalResponseEntities: map[string]struct{}{},
		ExternalImports:          map[string]struct{}{},
		ExternalExports:          map[string]struct{}{},
		EnumMembers:              map[string][]canonicalRequestEnumMember{},
		EnumUnknownMembers:       map[string]string{},
	}
	return nil
}

func loadCanonicalSharedEnumValues() (map[string][]string, error) {
	if activeMetadataSource == nil {
		return nil, fmt.Errorf("ContractGraph is not initialized")
	}
	const ownerPath = "_shared/types.yaml"
	if !activeMetadataSource.Has(ownerPath) {
		return nil, fmt.Errorf("canonical shared enum owner %s is missing", ownerPath)
	}
	var document struct {
		Enums any `yaml:"enums"`
	}
	if err := activeMetadataSource.Decode(ownerPath, &document); err != nil {
		return nil, fmt.Errorf("decode canonical shared enum owner %s: %w", ownerPath, err)
	}
	result := map[string][]string{}
	for name, raw := range normalizeRequestEnumCatalog(document.Enums) {
		values := normalizeRequestEnumValues(raw)
		if len(values) == 0 {
			continue
		}
		result[name] = values
	}
	return result, nil
}

// externalizeSharedDomainEnums gives every enum used by more than one domain
// one generated Dart owner, but only when _shared/types.yaml owns that enum.
// Matching local names are never treated as proof of shared semantics.
// Re-exporting the same generated library from each domain keeps the public
// barrel unambiguous without renaming or duplicating the business concept.
func externalizeSharedDomainEnums(
	specs map[string]*domainOperationContractSpec,
	appDir string,
) error {
	canonicalSharedEnums, err := loadCanonicalSharedEnumValues()
	if err != nil {
		return err
	}
	type enumOwner struct {
		owner         string
		members       []canonicalRequestEnumMember
		unknownMember string
	}
	ownersByEnum := map[string][]enumOwner{}
	for owner, spec := range specs {
		for name, members := range spec.EnumMembers {
			ownersByEnum[name] = append(ownersByEnum[name], enumOwner{
				owner:         owner,
				members:       members,
				unknownMember: spec.EnumUnknownMembers[name],
			})
		}
	}

	shared := map[string][]canonicalRequestEnumMember{}
	sharedUnknownMembers := map[string]string{}
	for name, enumOwners := range ownersByEnum {
		if len(enumOwners) < 2 {
			continue
		}
		canonicalValues, canonical := canonicalSharedEnums[name]
		if !canonical {
			return fmt.Errorf(
				"cross-domain enum %s has no canonical _shared/types.yaml owner",
				name,
			)
		}
		sort.Slice(enumOwners, func(left, right int) bool {
			return enumOwners[left].owner < enumOwners[right].owner
		})
		fingerprint := domainEnumFingerprint(enumOwners[0].members)
		unknownMember := enumOwners[0].unknownMember
		for _, candidate := range enumOwners[1:] {
			if domainEnumFingerprint(candidate.members) != fingerprint {
				return fmt.Errorf(
					"shared enum %s has conflicting domain member mappings",
					name,
				)
			}
			if candidate.unknownMember != unknownMember {
				return fmt.Errorf(
					"shared enum %s has conflicting client_unknown_member declarations",
					name,
				)
			}
		}
		if domainEnumWireFingerprint(enumOwners[0].members) !=
			strings.Join(canonicalValues, "\x00") {
			return fmt.Errorf(
				"shared enum %s does not match canonical _shared/types.yaml values",
				name,
			)
		}
		shared[name] = enumOwners[0].members
		if unknownMember != "" {
			sharedUnknownMembers[name] = unknownMember
		}
		for _, enumOwner := range enumOwners {
			spec := specs[enumOwner.owner]
			spec.ExternalImports[sharedDomainOperationEnumsImport] = struct{}{}
			spec.ExternalExports[sharedDomainOperationEnumsImport] = struct{}{}
			delete(spec.EnumMembers, name)
			delete(spec.EnumUnknownMembers, name)
		}
	}

	var output strings.Builder
	output.WriteString("// Code generated from canonical cross-domain enums. DO NOT EDIT.\n")
	output.WriteString("// ContractGraph SHA256: ")
	output.WriteString(activeContractSHA256)
	output.WriteString("\n\nlibrary;\n\n")
	names := make([]string, 0, len(shared))
	for name := range shared {
		names = append(names, name)
	}
	sort.Strings(names)
	for _, name := range names {
		renderDomainWireEnum(&output, name, shared[name], sharedUnknownMembers[name])
	}
	writeFile(filepath.Join(
		appDir,
		"packages",
		"quwoquan_cloud_contracts",
		"lib",
		"src",
		"generated",
		"shared_operation_enums.g.dart",
	), output.String())
	return nil
}

func generatedDomainOperationOwnerImport(domain string) string {
	return "../" + domain + "/" + domain + "_operation_contracts.g.dart"
}

func generateDomainOperationPublicBarrels(
	appDir string,
	lock appContractLock,
) error {
	domains := map[string]struct{}{}
	for _, operation := range lock.AppExposedOperations {
		if operation.ClientContract == nil {
			continue
		}
		domain := strings.TrimSpace(operation.Domain)
		if domain == "" {
			return fmt.Errorf(
				"%s App operation has no domain owner",
				operation.CanonicalOperationID,
			)
		}
		wantOwner := generatedDomainOperationOwnerImport(domain)
		if operation.ClientContract.DartImport != wantOwner {
			return fmt.Errorf(
				"%s App operation owner = %q, want %q",
				operation.CanonicalOperationID,
				operation.ClientContract.DartImport,
				wantOwner,
			)
		}
		domains[domain] = struct{}{}
	}
	names := make([]string, 0, len(domains))
	for domain := range domains {
		names = append(names, domain)
	}
	sort.Strings(names)
	for _, domain := range names {
		extraExports := ""
		switch domain {
		case "recommendation":
			extraExports = "export '../src/generated/recommendation/intersection_contract_vocabulary.g.dart';\n"
		case "search":
			extraExports = "export '../src/generated/search/search_contract_vocabulary.g.dart';\n"
		}
		content := "// Code generated from the canonical " + domain +
			" operation owner. DO NOT EDIT.\n" +
			"// ContractGraph SHA256: " + activeContractSHA256 + "\n\n" +
			"library;\n\n" +
			"export '../src/" + domain + "/" + domain +
			"_operation_contracts.g.dart';\n" + extraExports
		writeFile(filepath.Join(
			appDir,
			"packages",
			"quwoquan_cloud_contracts",
			"lib",
			"generated",
			domain+"_contracts.dart",
		), content)
	}
	return nil
}

func loadDomainOperationContractSpec(
	ownerImport string,
	operations []appExposedOperation,
) (domainOperationContractSpec, error) {
	if len(operations) == 0 {
		return domainOperationContractSpec{}, fmt.Errorf(
			"empty-green: %s has no App operations",
			ownerImport,
		)
	}
	domain := operations[0].Domain
	spec := domainOperationContractSpec{
		Domain:                   domain,
		OwnerImport:              ownerImport,
		Models:                   map[string]requestModelSpec{},
		ResponseEntities:         map[string]struct{}{},
		ExternalResponseEntities: map[string]struct{}{},
		ExternalImports:          map[string]struct{}{},
		ExternalExports:          map[string]struct{}{},
		EnumMembers:              map[string][]canonicalRequestEnumMember{},
		EnumUnknownMembers:       map[string]string{},
	}
	enumValues, err := loadCanonicalRequestEnumValues()
	if err != nil {
		return domainOperationContractSpec{}, err
	}
	for _, operation := range operations {
		if operation.Domain != domain {
			return domainOperationContractSpec{}, fmt.Errorf(
				"%s mixes domain %s with %s",
				ownerImport,
				domain,
				operation.Domain,
			)
		}
		responseBodyKind := strings.TrimSpace(operation.ResponseBodyKind)
		emptyResponse := operation.ClientContract != nil &&
			operation.ClientContract.ResponseType == "void" &&
			operation.ClientContract.ResponseDecoder == "decodeEmptyResponse" &&
			strings.TrimSpace(operation.ResponseEntity) == "" &&
			(responseBodyKind == "ack" || responseBodyKind == "upgrade")
		if emptyResponse {
			spec.HasEmptyResponse = true
		} else if externalImport := generatedExternalResponseImport(
			operation.Domain,
			operation.ResponseEntity,
		); externalImport != "" {
			spec.ExternalExports[externalImport] = struct{}{}
			spec.ExternalResponseEntities[operation.ResponseEntity] = struct{}{}
		} else {
			response, dependencies, responseErr := loadOperationResponseModel(
				operation,
				operation.ResponseEntity,
			)
			if responseErr != nil {
				return domainOperationContractSpec{}, responseErr
			}
			if err := mergeDomainResponseModel(spec.Models, response); err != nil {
				return domainOperationContractSpec{}, err
			}
			for _, dependency := range dependencies {
				if externalImport := generatedExternalResponseValueImport(dependency.Name); externalImport != "" {
					spec.ExternalImports[externalImport] = struct{}{}
					spec.ExternalExports[externalImport] = struct{}{}
					continue
				}
				if err := mergeDomainResponseModel(spec.Models, dependency); err != nil {
					return domainOperationContractSpec{}, err
				}
			}
		}
		if !emptyResponse {
			spec.ResponseEntities[operation.ResponseEntity] = struct{}{}
		}

		request, requestDependencies, err := loadOperationRequestModel(
			operation,
			operation.RequestEntity,
		)
		if err != nil {
			return domainOperationContractSpec{}, err
		}
		for _, model := range append(
			[]requestModelSpec{request},
			mapRequestModels(requestDependencies)...,
		) {
			if err := collectDomainEnumMembers(
				spec.EnumMembers,
				model,
				enumValues,
			); err != nil {
				return domainOperationContractSpec{}, fmt.Errorf(
					"%s: %w",
					operation.CanonicalOperationID,
					err,
				)
			}
		}
	}
	return spec, nil
}

func externalizeCanonicalDomainModels(
	specs map[string]*domainOperationContractSpec,
) error {
	owners := make([]string, 0, len(specs))
	for owner := range specs {
		owners = append(owners, owner)
	}
	sort.Strings(owners)
	for _, owner := range owners {
		spec := specs[owner]
		names := make([]string, 0, len(spec.Models))
		for name := range spec.Models {
			names = append(names, name)
		}
		sort.Strings(names)
		for _, name := range names {
			_, ownerPath, err := canonicalProjectionResponseDefinitionWithOwner(name)
			if err != nil {
				continue
			}
			ownerDomain := canonicalMetadataDomain(ownerPath)
			if ownerDomain == "" || ownerDomain == spec.Domain {
				continue
			}
			targetImport := generatedDomainOperationOwnerImport(ownerDomain)
			target := specs[targetImport]
			if target == nil {
				target = &domainOperationContractSpec{
					Domain:                   ownerDomain,
					OwnerImport:              targetImport,
					Models:                   map[string]requestModelSpec{},
					ResponseEntities:         map[string]struct{}{},
					ExternalResponseEntities: map[string]struct{}{},
					ExternalImports:          map[string]struct{}{},
					ExternalExports:          map[string]struct{}{},
					EnumMembers:              map[string][]canonicalRequestEnumMember{},
					EnumUnknownMembers:       map[string]string{},
				}
				specs[targetImport] = target
			}
			if err := mergeDomainResponseModel(target.Models, spec.Models[name]); err != nil {
				return fmt.Errorf("canonical owner %s: %w", ownerDomain, err)
			}
			spec.ExternalImports[targetImport] = struct{}{}
			spec.ExternalExports[targetImport] = struct{}{}
			delete(spec.Models, name)
		}
	}
	return nil
}

func canonicalMetadataDomain(path string) string {
	relative, err := filepath.Rel(activeMetadataRoot, path)
	if err != nil {
		return ""
	}
	parts := strings.Split(filepath.ToSlash(relative), "/")
	if len(parts) == 0 || parts[0] == "" || strings.HasPrefix(parts[0], "_") {
		return ""
	}
	return parts[0]
}

func finalizeDomainOperationContractSpec(
	spec *domainOperationContractSpec,
) error {
	if spec.Domain == "search" {
		spec.ExternalExports[searchContractVocabularyImport] = struct{}{}
	}
	enumValues, err := loadCanonicalRequestEnumValues()
	if err != nil {
		return err
	}
	unknownMembers, err := loadCanonicalRequestEnumUnknownMembers()
	if err != nil {
		return err
	}
	for _, model := range spec.Models {
		if err := collectDomainEnumMembers(spec.EnumMembers, model, enumValues); err != nil {
			return err
		}
	}
	if spec.EnumUnknownMembers == nil {
		spec.EnumUnknownMembers = map[string]string{}
	}
	for enumRef, members := range spec.EnumMembers {
		if unknownMember := unknownMembers[enumRef]; unknownMember != "" {
			for _, member := range members {
				if member.DartMember == unknownMember {
					return fmt.Errorf(
						"enum %s client_unknown_member %q collides with a canonical member",
						enumRef,
						unknownMember,
					)
				}
			}
			spec.EnumUnknownMembers[enumRef] = unknownMember
		}
		if enumRef == "IntersectionDimension" {
			if err := validateCanonicalIntersectionDimensionMembers(
				spec.EnumMembers[enumRef],
			); err != nil {
				return fmt.Errorf(
					"%s canonical IntersectionDimension owner: %w",
					spec.Domain,
					err,
				)
			}
			spec.ExternalImports[packageInternalIntersectionContractVocabularyImport] = struct{}{}
			spec.ExternalExports[packageInternalIntersectionContractVocabularyImport] = struct{}{}
			delete(spec.EnumMembers, enumRef)
			delete(spec.EnumUnknownMembers, enumRef)
			continue
		}
		if externalImport := generatedExternalEnumImport(spec.Domain, enumRef); externalImport != "" {
			spec.ExternalImports[externalImport] = struct{}{}
			spec.ExternalExports[externalImport] = struct{}{}
			delete(spec.EnumMembers, enumRef)
			delete(spec.EnumUnknownMembers, enumRef)
		}
	}
	return nil
}

func generatedExternalResponseImport(domain, responseType string) string {
	if strings.TrimSpace(responseType) == "RealtimeEventEnvelope" {
		return sharedRealtimeEventCatalogImport
	}
	if strings.TrimSpace(domain) == "search" &&
		strings.TrimSpace(responseType) == "SearchResponseView" {
		return "../generated/search/search_response_view.g.dart"
	}
	return ""
}

func generatedExternalResponseValueImport(responseType string) string {
	if strings.TrimSpace(responseType) == "RealtimeEventEnvelope" {
		return sharedRealtimeEventCatalogImport
	}
	return ""
}

func generatedExternalEnumImport(domain, enumRef string) string {
	domain = strings.TrimSpace(domain)
	enumRef = strings.TrimSpace(enumRef)
	if domain != "search" {
		return ""
	}
	switch enumRef {
	case "CanonicalSearchMode":
		return "../generated/search/canonical_search_mode.g.dart"
	case "SearchFeedbackEventType":
		return "../generated/search_feedback_event_type.g.dart"
	default:
		return ""
	}
}

func mapRequestModels(values map[string]requestModelSpec) []requestModelSpec {
	result := make([]requestModelSpec, 0, len(values))
	for _, value := range values {
		result = append(result, value)
	}
	return result
}

func mergeDomainResponseModel(
	models map[string]requestModelSpec,
	model requestModelSpec,
) error {
	if previous, exists := models[model.Name]; exists {
		if responseModelFingerprint(previous) != responseModelFingerprint(model) {
			return fmt.Errorf(
				"response model %s has conflicting object-local definitions",
				model.Name,
			)
		}
		return nil
	}
	models[model.Name] = model
	return nil
}

func responseModelFingerprint(model requestModelSpec) string {
	parts := make([]string, 0, len(model.Fields))
	for _, field := range model.Fields {
		parts = append(parts, strings.Join([]string{
			field.Name,
			field.Type,
			field.ObjectRef,
			field.EnumRef,
			strings.Join(field.Constraints, ","),
			field.ClientWireName,
			// 信封准入位改变 decoder ABI，必须参与同名模型的一致性指纹。
			strconv.Itoa(field.MaxItems),
			field.Format,
			strings.Join(field.CoPresentWith, ","),
		}, "\x00"))
	}
	return strings.Join(parts, "\x01")
}
