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
		emptyResponse := client.ResponseType == "void" &&
			client.ResponseDecoder == "decodeEmptyResponse" &&
			strings.TrimSpace(operation.ResponseEntity) == "" &&
			strings.TrimSpace(operation.ResponseBodyKind) == "ack"
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
		owner   string
		members []canonicalRequestEnumMember
	}
	ownersByEnum := map[string][]enumOwner{}
	for owner, spec := range specs {
		for name, members := range spec.EnumMembers {
			ownersByEnum[name] = append(ownersByEnum[name], enumOwner{
				owner:   owner,
				members: members,
			})
		}
	}

	shared := map[string][]canonicalRequestEnumMember{}
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
		for _, candidate := range enumOwners[1:] {
			if domainEnumFingerprint(candidate.members) != fingerprint {
				return fmt.Errorf(
					"shared enum %s has conflicting domain member mappings",
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
		for _, enumOwner := range enumOwners {
			spec := specs[enumOwner.owner]
			spec.ExternalImports[sharedDomainOperationEnumsImport] = struct{}{}
			spec.ExternalExports[sharedDomainOperationEnumsImport] = struct{}{}
			delete(spec.EnumMembers, name)
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
		renderDomainWireEnum(&output, name, shared[name])
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
		content := "// Code generated from the canonical " + domain +
			" operation owner. DO NOT EDIT.\n" +
			"// ContractGraph SHA256: " + activeContractSHA256 + "\n\n" +
			"library;\n\n" +
			"export '../src/" + domain + "/" + domain +
			"_operation_contracts.g.dart';\n"
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
		emptyResponse := operation.ClientContract != nil &&
			operation.ClientContract.ResponseType == "void" &&
			operation.ClientContract.ResponseDecoder == "decodeEmptyResponse" &&
			strings.TrimSpace(operation.ResponseEntity) == "" &&
			strings.TrimSpace(operation.ResponseBodyKind) == "ack"
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
	enumValues, err := loadCanonicalRequestEnumValues()
	if err != nil {
		return err
	}
	for _, model := range spec.Models {
		if err := collectDomainEnumMembers(spec.EnumMembers, model, enumValues); err != nil {
			return err
		}
	}
	for enumRef := range spec.EnumMembers {
		if externalImport := generatedExternalEnumImport(spec.Domain, enumRef); externalImport != "" {
			spec.ExternalImports[externalImport] = struct{}{}
			spec.ExternalExports[externalImport] = struct{}{}
			delete(spec.EnumMembers, enumRef)
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
		}, "\x00"))
	}
	return strings.Join(parts, "\x01")
}

func loadOperationResponseModel(
	operation appExposedOperation,
	responseType string,
) (requestModelSpec, map[string]requestModelSpec, error) {
	fieldsPath := filepath.Join(
		filepath.Dir(operation.SourcePath),
		"fields.yaml",
	)
	var document fieldsFile
	if err := decodeMetadataDocument(filepath.Join(
		activeMetadataRoot,
		filepath.FromSlash(fieldsPath),
	), &document); err != nil {
		return requestModelSpec{}, nil, fmt.Errorf(
			"%s load response model %s: %w",
			operation.CanonicalOperationID,
			responseType,
			err,
		)
	}
	entities := map[string]entityDef{}
	for name, entity := range document.Entities {
		entities[name] = entity
	}
	for name, entity := range document.Types {
		entities[name] = entity
	}
	for name, entity := range document.ValueObjects {
		entities[name] = entity
	}
	for name, entity := range document.Members {
		entities[name] = entity
	}
	projectionPaths, err := filepath.Glob(filepath.Join(
		activeMetadataRoot,
		filepath.FromSlash(filepath.Dir(operation.SourcePath)),
		"projections",
		"*.yaml",
	))
	if err != nil {
		return requestModelSpec{}, nil, fmt.Errorf(
			"%s list object-local response projections: %w",
			operation.CanonicalOperationID,
			err,
		)
	}
	for _, projectionPath := range projectionPaths {
		projection, projectionErr := readProjection(projectionPath)
		if projectionErr != nil {
			return requestModelSpec{}, nil, fmt.Errorf(
				"%s load object-local response projection %s: %w",
				operation.CanonicalOperationID,
				filepath.Base(projectionPath),
				projectionErr,
			)
		}
		name := strings.TrimSpace(projection.ReadModel)
		if name == "" || len(projection.Fields) == 0 {
			continue
		}
		fields, projectionErr := canonicalProjectionResponseFields(
			projection.Fields,
		)
		if projectionErr != nil {
			return requestModelSpec{}, nil, fmt.Errorf(
				"%s projection %s: %w",
				operation.CanonicalOperationID,
				name,
				projectionErr,
			)
		}
		definition := entityDef{Fields: fields}
		if existing, declared := entities[name]; declared {
			definition = existing
		} else {
			entities[name] = definition
		}
		if dartClass := strings.TrimSpace(projection.ClientProjection.DartClass); dartClass != "" {
			entities[dartClass] = definition
		}
	}
	rootName := toDartExportedName(
		operation.ObjectID[strings.LastIndex(operation.ObjectID, ".")+1:],
	)
	root := entityDef{Fields: append([]fieldDef(nil), document.Fields...)}
	entities[rootName] = root
	if declared := strings.TrimSpace(document.Entity); declared != "" {
		entities[declared] = root
	}
	sharedTypes, err := loadCanonicalSharedValueTypes(operation)
	if err != nil {
		return requestModelSpec{}, nil, err
	}
	for name, entity := range sharedTypes {
		if local, exists := entities[name]; exists {
			if responseModelFingerprint(requestModelSpec{Name: name, Fields: local.Fields}) !=
				responseModelFingerprint(requestModelSpec{Name: name, Fields: entity.Fields}) {
				return requestModelSpec{}, nil, fmt.Errorf(
					"%s response type %s conflicts with canonical _shared/types.yaml",
					operation.CanonicalOperationID,
					name,
				)
			}
			continue
		}
		entities[name] = entity
	}
	entity, exists := entities[responseType]
	if !exists {
		var resolveErr error
		entity, resolveErr = canonicalProjectionResponseDefinition(responseType)
		if resolveErr != nil {
			return requestModelSpec{}, nil, fmt.Errorf(
				"%s response_entity %s has no unique canonical owner: %w",
				operation.CanonicalOperationID,
				responseType,
				resolveErr,
			)
		}
		entities[responseType] = entity
	}
	model := requestModelSpec{
		Name:   responseType,
		Fields: append([]fieldDef(nil), entity.Fields...),
	}
	dependencies := map[string]requestModelSpec{}
	visiting := map[string]bool{responseType: true}
	var collect func(requestModelSpec) error
	collect = func(current requestModelSpec) error {
		for _, field := range current.Fields {
			name := responseFieldReference(field)
			if name == "" || name == responseType || name == current.Name {
				continue
			}
			definition, found := entities[name]
			if !found {
				var resolveErr error
				definition, resolveErr = canonicalProjectionResponseDefinition(name)
				if resolveErr != nil {
					return fmt.Errorf(
						"%s response field %s.%s references undeclared type %s: %w",
						operation.CanonicalOperationID,
						current.Name,
						field.Name,
						name,
						resolveErr,
					)
				}
				entities[name] = definition
			}
			if visiting[name] {
				return fmt.Errorf(
					"%s response value object cycle includes %s",
					operation.CanonicalOperationID,
					name,
				)
			}
			if _, found := dependencies[name]; found {
				continue
			}
			dependency := requestModelSpec{
				Name:   name,
				Fields: append([]fieldDef(nil), definition.Fields...),
			}
			dependencies[name] = dependency
			visiting[name] = true
			if err := collect(dependency); err != nil {
				return err
			}
			delete(visiting, name)
		}
		return nil
	}
	if err := collect(model); err != nil {
		return requestModelSpec{}, nil, err
	}
	return model, dependencies, nil
}

// canonicalProjectionResponseDefinition resolves a response root or nested
// response value from its unique canonical fields/projection owner. This
// permits an explicit composition response to reuse another object's named
// packet while rejecting ambiguous or unowned types.
func canonicalProjectionResponseDefinition(name string) (entityDef, error) {
	definition, _, err := canonicalProjectionResponseDefinitionWithOwner(name)
	return definition, err
}

func canonicalProjectionResponseDefinitionWithOwner(
	name string,
) (entityDef, string, error) {
	name = strings.TrimSpace(name)
	if name == "" {
		return entityDef{}, "", fmt.Errorf("canonical response type is required")
	}
	matchedPath := ""
	matchedDefinition := entityDef{}
	register := func(path string, definition entityDef) error {
		if len(definition.Fields) == 0 {
			return nil
		}
		if matchedPath != "" && matchedPath != path {
			first, _ := filepath.Rel(activeMetadataRoot, matchedPath)
			second, _ := filepath.Rel(activeMetadataRoot, path)
			return fmt.Errorf(
				"canonical response type %s has multiple owners: %s, %s",
				name,
				filepath.ToSlash(first),
				filepath.ToSlash(second),
			)
		}
		matchedPath = path
		matchedDefinition = definition
		return nil
	}
	for _, path := range metadataDocumentPaths("", ".yaml") {
		if filepath.Base(filepath.Dir(path)) != "projections" {
			continue
		}
		binding, err := readProjectionBinding(path)
		if err != nil {
			continue
		}
		readModel := strings.TrimSpace(binding.ReadModel)
		if name != readModel {
			continue
		}
		projection, err := readProjection(path)
		if err != nil {
			return entityDef{}, "", err
		}
		if len(projection.Fields) == 0 {
			relative, _ := filepath.Rel(activeMetadataRoot, path)
			return entityDef{}, "", fmt.Errorf(
				"canonical projection owner %s has no top-level fields",
				filepath.ToSlash(relative),
			)
		}
		fields, err := canonicalProjectionResponseFields(projection.Fields)
		if err != nil {
			return entityDef{}, "", err
		}
		if err := register(path, entityDef{Fields: fields}); err != nil {
			return entityDef{}, "", err
		}
	}
	for _, path := range metadataDocumentPaths("", "fields.yaml") {
		var document fieldsFile
		if err := decodeMetadataDocument(path, &document); err != nil {
			return entityDef{}, "", err
		}
		definitions := map[string]entityDef{}
		for key, definition := range document.Entities {
			definitions[key] = definition
		}
		for key, definition := range document.Types {
			definitions[key] = definition
		}
		for key, definition := range document.ValueObjects {
			definitions[key] = definition
		}
		for key, definition := range document.Members {
			definitions[key] = definition
		}
		rootName := strings.TrimSpace(document.Entity)
		if rootName == "" {
			rootName = toDartExportedName(filepath.Base(filepath.Dir(path)))
		}
		if len(document.Fields) > 0 {
			definitions[rootName] = entityDef{Fields: document.Fields}
		}
		definition, exists := definitions[name]
		if !exists {
			continue
		}
		if err := register(path, definition); err != nil {
			return entityDef{}, "", err
		}
	}
	if matchedPath == "" {
		return entityDef{}, "", fmt.Errorf("canonical response type has no owner")
	}
	return matchedDefinition, matchedPath, nil
}

func canonicalProjectionResponseFields(
	fields []projectionFieldDef,
) ([]fieldDef, error) {
	result := make([]fieldDef, 0, len(fields))
	for _, field := range fields {
		name := strings.TrimSpace(field.Name)
		fieldType := strings.TrimSpace(field.WireType)
		if name == "" || fieldType == "" {
			return nil, fmt.Errorf("canonical projection field requires name and type")
		}
		constraints := []string{"NOT_NULL"}
		if field.Nullable {
			constraints = []string{"NULLABLE"}
		}
		result = append(result, fieldDef{
			Name:           name,
			Type:           fieldType,
			EnumRef:        strings.TrimSpace(field.EnumRef),
			Constraints:    constraints,
			ClientWireName: strings.TrimSpace(field.WireName),
		})
	}
	return result, nil
}

func responseFieldReference(field fieldDef) string {
	if reference := strings.TrimSpace(field.ObjectRef); reference != "" {
		return reference
	}
	typeName := strings.TrimPrefix(strings.TrimSpace(field.Type), "[]")
	switch typeName {
	case "", "string", "tag_ref", "time", "url", "ObjectId", "uuid", "identifier",
		"int", "int32", "int64", "long",
		"float", "float32", "float64", "double",
		"bool", "boolean", "timestamp", "datetime", "date",
		"enum", "object", "json", "jsonb":
		return ""
	default:
		return typeName
	}
}

func collectDomainEnumMembers(
	target map[string][]canonicalRequestEnumMember,
	model requestModelSpec,
	enumValues map[string][]string,
) error {
	for _, field := range model.Fields {
		enumRef := strings.TrimSpace(field.EnumRef)
		if enumRef == "" {
			continue
		}
		values := enumValues[enumRef]
		if len(values) == 0 {
			return fmt.Errorf(
				"%s.%s enum_ref %s has no canonical values",
				model.Name,
				field.Name,
				enumRef,
			)
		}
		members, err := canonicalRequestEnumMembers(field, values)
		if err != nil {
			return err
		}
		if previous, exists := target[enumRef]; exists {
			if domainEnumFingerprint(previous) != domainEnumFingerprint(members) {
				return fmt.Errorf(
					"enum %s has conflicting Dart member mappings",
					enumRef,
				)
			}
			continue
		}
		target[enumRef] = members
	}
	return nil
}

func domainEnumFingerprint(values []canonicalRequestEnumMember) string {
	parts := make([]string, 0, len(values))
	for _, value := range values {
		parts = append(parts, value.WireValue+"="+value.DartMember)
	}
	return strings.Join(parts, ",")
}

func domainEnumWireFingerprint(values []canonicalRequestEnumMember) string {
	parts := make([]string, 0, len(values))
	for _, value := range values {
		parts = append(parts, value.WireValue)
	}
	return strings.Join(parts, "\x00")
}

func renderDomainOperationContract(
	spec domainOperationContractSpec,
) (string, error) {
	var output strings.Builder
	output.WriteString("// Code generated from canonical domain contracts. DO NOT EDIT.\n")
	output.WriteString("// ContractGraph SHA256: ")
	output.WriteString(activeContractSHA256)
	output.WriteString("\n\nlibrary;\n\n")
	if spec.HasRequestPart {
		output.WriteString("import '../operation_request_payload.dart';\n")
	}
	externalImports := make([]string, 0, len(spec.ExternalImports))
	for path := range spec.ExternalImports {
		externalImports = append(externalImports, path)
	}
	sort.Strings(externalImports)
	for _, path := range externalImports {
		fmt.Fprintf(&output, "import %q;\n", path)
	}
	output.WriteString("\n")
	externalExports := make([]string, 0, len(spec.ExternalExports))
	for path := range spec.ExternalExports {
		externalExports = append(externalExports, path)
	}
	sort.Strings(externalExports)
	for _, path := range externalExports {
		fmt.Fprintf(&output, "export %q;\n", path)
	}
	if len(externalExports) > 0 {
		output.WriteString("\n")
	}
	if spec.HasRequestPart {
		output.WriteString("part '../generated/requests/")
		output.WriteString(spec.Domain)
		output.WriteString("/")
		output.WriteString(spec.Domain)
		output.WriteString("_operation_contracts.g.requests.g.dart';\n\n")
	}

	enumNames := make([]string, 0, len(spec.EnumMembers))
	for name := range spec.EnumMembers {
		enumNames = append(enumNames, name)
	}
	sort.Strings(enumNames)
	for _, name := range enumNames {
		renderDomainWireEnum(&output, name, spec.EnumMembers[name])
	}

	modelNames := make([]string, 0, len(spec.Models))
	for name := range spec.Models {
		modelNames = append(modelNames, name)
	}
	sort.Strings(modelNames)
	for _, name := range modelNames {
		if err := renderDomainResponseModel(&output, spec.Models[name]); err != nil {
			return "", err
		}
	}

	responseNames := make([]string, 0, len(spec.ResponseEntities))
	for name := range spec.ResponseEntities {
		responseNames = append(responseNames, name)
	}
	sort.Strings(responseNames)
	for _, name := range responseNames {
		if _, external := spec.ExternalResponseEntities[name]; external {
			continue
		}
		fmt.Fprintf(
			&output,
			"%s decode%s(Object? response) =>\n    %s.fromWire(_requiredObject(response, %q), %q);\n\n",
			name,
			name,
			name,
			name,
			name,
		)
	}
	if spec.HasEmptyResponse {
		output.WriteString("void decodeEmptyResponse(Object? response) {\n")
		output.WriteString("  if (response != null) {\n")
		output.WriteString("    throw const FormatException('empty response must not contain a body');\n")
		output.WriteString("  }\n")
		output.WriteString("}\n\n")
	}
	renderDomainDecoderHelpers(&output, spec.Models)
	return output.String(), nil
}

func renderDomainWireEnum(
	output *strings.Builder,
	name string,
	members []canonicalRequestEnumMember,
) {
	fmt.Fprintf(output, "enum %s {\n", name)
	for index, member := range members {
		terminator := ","
		if index == len(members)-1 {
			terminator = ";"
		}
		fmt.Fprintf(
			output,
			"  %s(%q)%s\n",
			member.DartMember,
			member.WireValue,
			terminator,
		)
	}
	fmt.Fprintf(output, "\n  const %s(this.wireName);\n\n", name)
	output.WriteString("  final String wireName;\n\n")
	fmt.Fprintf(output, "  static %s fromWire(Object? value, String path) {\n", name)
	output.WriteString("    return switch (value) {\n")
	for _, member := range members {
		fmt.Fprintf(
			output,
			"      %q => %s.%s,\n",
			member.WireValue,
			name,
			member.DartMember,
		)
	}
	output.WriteString(
		"      _ => throw FormatException('$path has an invalid enum value'),\n" +
			"    };\n" +
			"  }\n" +
			"}\n\n",
	)
}

func renderDomainResponseModel(
	output *strings.Builder,
	model requestModelSpec,
) error {
	fmt.Fprintf(output, "final class %s {\n", model.Name)
	fmt.Fprintf(output, "  const %s({\n", model.Name)
	for _, field := range model.Fields {
		typeName, nullable, err := responseFieldDartType(field)
		if err != nil {
			return fmt.Errorf("%s.%s: %w", model.Name, field.Name, err)
		}
		name := responseFieldDartName(field)
		if nullable {
			fmt.Fprintf(output, "    this.%s,\n", name)
		} else {
			fmt.Fprintf(output, "    required this.%s,\n", name)
		}
		_ = typeName
	}
	output.WriteString("  });\n\n")
	for _, field := range model.Fields {
		typeName, _, err := responseFieldDartType(field)
		if err != nil {
			return err
		}
		fmt.Fprintf(
			output,
			"  final %s %s;\n",
			typeName,
			responseFieldDartName(field),
		)
	}
	output.WriteString("\n  factory ")
	output.WriteString(model.Name)
	output.WriteString(".fromWire(Map<String, Object?> map, [String path = ")
	output.WriteString(strconv.Quote(model.Name))
	output.WriteString("]) {\n")
	output.WriteString("    _rejectUnknown")
	output.WriteString("Fields(map, const <String>{")
	for index, field := range model.Fields {
		if index > 0 {
			output.WriteString(", ")
		}
		output.WriteString(strconv.Quote(responseFieldWireName(field)))
	}
	output.WriteString("}, path);\n")
	fmt.Fprintf(output, "    return %s(\n", model.Name)
	for _, field := range model.Fields {
		expression, err := responseFieldDecodeExpression(
			field,
			"map["+strconv.Quote(responseFieldWireName(field))+"]",
			"'$path."+responseFieldWireName(field)+"'",
		)
		if err != nil {
			return fmt.Errorf("%s.%s: %w", model.Name, field.Name, err)
		}
		fmt.Fprintf(
			output,
			"      %s: %s,\n",
			responseFieldDartName(field),
			expression,
		)
	}
	output.WriteString("    );\n  }\n\n")
	output.WriteString("  Map<String, Object?> toWire() => <String, Object?>{\n")
	for _, field := range model.Fields {
		name := responseFieldDartName(field)
		wire := responseFieldWireName(field)
		expression, err := responseFieldEncodeExpression(field, name)
		if err != nil {
			return fmt.Errorf("%s.%s: %w", model.Name, field.Name, err)
		}
		if isResponseFieldNullable(field) {
			fmt.Fprintf(
				output,
				"    if (%s != null) %q: %s,\n",
				name,
				wire,
				expression,
			)
		} else {
			fmt.Fprintf(output, "    %q: %s,\n", wire, expression)
		}
	}
	output.WriteString("  };\n}\n\n")
	return nil
}

func responseFieldDartType(field fieldDef) (string, bool, error) {
	nullable := isResponseFieldNullable(field)
	metaType := strings.TrimSpace(field.Type)
	var result string
	switch metaType {
	case "string", "tag_ref", "time", "ObjectId", "uuid", "identifier":
		result = "String"
	case "url":
		result = "Uri"
	case "timestamp", "datetime", "date":
		result = "DateTime"
	case "int", "int32", "int64", "long":
		result = "int"
	case "float", "float32", "float64", "double":
		result = "double"
	case "bool", "boolean":
		result = "bool"
	case "enum":
		result = strings.TrimSpace(field.EnumRef)
	case "object":
		result = strings.TrimSpace(field.ObjectRef)
		if result == "" {
			result = "Map<String, Object?>"
		}
	case "json", "jsonb":
		result = "Map<String, Object?>"
	default:
		if strings.HasPrefix(metaType, "[]") {
			item := field
			item.Type = strings.TrimPrefix(metaType, "[]")
			item.Constraints = nil
			itemType, _, err := responseFieldDartType(item)
			if err != nil {
				return "", false, err
			}
			result = "List<" + strings.TrimSuffix(itemType, "?") + ">"
		} else {
			result = metaType
		}
	}
	if result == "" {
		return "", false, fmt.Errorf("metadata type is empty")
	}
	if nullable {
		result += "?"
	}
	return result, nullable, nil
}

func isResponseFieldNullable(field fieldDef) bool {
	return hasRequestConstraint(field, "NULLABLE")
}

func responseFieldDartName(field fieldDef) string {
	if field.Name == "_id" {
		return "id"
	}
	return toDartFieldName(field.Name)
}

func responseFieldWireName(field fieldDef) string {
	if value := strings.TrimSpace(field.ClientWireName); value != "" {
		return value
	}
	if field.Name == "_id" {
		return "id"
	}
	return field.Name
}

func responseFieldDecodeExpression(
	field fieldDef,
	access string,
	path string,
) (string, error) {
	if isResponseFieldNullable(field) {
		nonNull := field
		nonNull.Constraints = responseConstraintsWithoutNullable(
			field.Constraints,
		)
		expression, err := responseFieldDecodeExpression(nonNull, access, path)
		if err != nil {
			return "", err
		}
		return access + " == null ? null : " + expression, nil
	}
	metaType := strings.TrimSpace(field.Type)
	switch metaType {
	case "string", "tag_ref", "time", "ObjectId", "uuid", "identifier":
		if hasRequestConstraint(field, "NOT_BLANK") {
			return "_requiredNonBlankString(" + access + ", " + path + ")", nil
		}
		return "_requiredString(" + access + ", " + path + ")", nil
	case "url":
		return "_requiredUri(" + access + ", " + path + ")", nil
	case "timestamp", "datetime", "date":
		return "_requiredTimestamp(" + access + ", " + path + ")", nil
	case "int", "int32", "int64", "long":
		minimum, maximum, err := responseIntegerBounds(field)
		if err != nil {
			return "", err
		}
		if maximum != nil || (minimum != nil && *minimum > 1) {
			arguments := ""
			if minimum != nil {
				arguments += fmt.Sprintf(", min: %d", *minimum)
			}
			if maximum != nil {
				arguments += fmt.Sprintf(", max: %d", *maximum)
			}
			return "_requiredBoundedInt(" + access + ", " + path +
				arguments + ")", nil
		}
		if hasRequestConstraint(field, "NON_NEGATIVE") {
			return "_requiredNonNegativeInt(" + access + ", " + path + ")", nil
		}
		if hasRequestConstraint(field, "MIN_1") {
			return "_requiredPositiveInt(" + access + ", " + path + ")", nil
		}
		return "_requiredInt(" + access + ", " + path + ")", nil
	case "float", "float32", "float64", "double":
		return "_requiredDouble(" + access + ", " + path + ")", nil
	case "bool", "boolean":
		return "_requiredBool(" + access + ", " + path + ")", nil
	case "enum":
		return strings.TrimSpace(field.EnumRef) +
			".fromWire(" + access + ", " + path + ")", nil
	case "object":
		if reference := strings.TrimSpace(field.ObjectRef); reference != "" {
			return reference + ".fromWire(_requiredObject(" + access + ", " +
				path + "), " + path + ")", nil
		}
		return "_requiredObject(" + access + ", " + path + ")", nil
	case "json", "jsonb":
		return "_requiredObject(" + access + ", " + path + ")", nil
	default:
		if strings.HasPrefix(metaType, "[]") {
			item := field
			item.Type = strings.TrimPrefix(metaType, "[]")
			item.Constraints = nil
			itemExpression, err := responseFieldDecodeExpression(
				item,
				"entry.value",
				path+" + '[${entry.key}]'",
			)
			if err != nil {
				return "", err
			}
			itemType, _, err := responseFieldDartType(item)
			if err != nil {
				return "", err
			}
			return "List<" + strings.TrimSuffix(itemType, "?") +
				">.unmodifiable(_requiredList(" + access + ", " + path +
				").asMap().entries.map((entry) => " + itemExpression + "))", nil
		}
		return metaType + ".fromWire(_requiredObject(" + access + ", " +
			path + "), " + path + ")", nil
	}
}

func responseIntegerBounds(field fieldDef) (*int, *int, error) {
	var minimum *int
	var maximum *int
	for _, raw := range field.Constraints {
		constraint := strings.TrimSpace(raw)
		switch {
		case constraint == "NON_NEGATIVE":
			minimum = stricterMinimum(minimum, 0)
		case constraint == "POSITIVE" || constraint == "MIN_1":
			minimum = stricterMinimum(minimum, 1)
		case strings.HasPrefix(constraint, "MIN_"):
			value, err := strconv.Atoi(strings.TrimPrefix(constraint, "MIN_"))
			if err != nil {
				return nil, nil, fmt.Errorf(
					"field %s has invalid integer constraint %q",
					field.Name,
					constraint,
				)
			}
			minimum = stricterMinimum(minimum, value)
		case strings.HasPrefix(constraint, "MAX_"):
			value, err := strconv.Atoi(strings.TrimPrefix(constraint, "MAX_"))
			if err != nil {
				return nil, nil, fmt.Errorf(
					"field %s has invalid integer constraint %q",
					field.Name,
					constraint,
				)
			}
			maximum = stricterMaximum(maximum, value)
		}
	}
	if minimum != nil && maximum != nil && *minimum > *maximum {
		return nil, nil, fmt.Errorf(
			"field %s has impossible integer bounds %d..%d",
			field.Name,
			*minimum,
			*maximum,
		)
	}
	return minimum, maximum, nil
}

func stricterMinimum(current *int, candidate int) *int {
	if current != nil && *current >= candidate {
		return current
	}
	value := candidate
	return &value
}

func stricterMaximum(current *int, candidate int) *int {
	if current != nil && *current <= candidate {
		return current
	}
	value := candidate
	return &value
}

func responseIntegerUsesBoundedDecoder(field fieldDef) bool {
	minimum, maximum, err := responseIntegerBounds(field)
	if err != nil {
		return false
	}
	return maximum != nil || (minimum != nil && *minimum > 1)
}

func responseConstraintsWithoutNullable(values []string) []string {
	result := make([]string, 0, len(values))
	for _, value := range values {
		if strings.TrimSpace(value) == "NULLABLE" {
			continue
		}
		result = append(result, value)
	}
	return result
}

func responseFieldEncodeExpression(field fieldDef, access string) (string, error) {
	nonNullAccess := access
	if isResponseFieldNullable(field) {
		nonNullAccess += "!"
	}
	metaType := strings.TrimSpace(field.Type)
	switch metaType {
	case "string", "tag_ref", "time", "ObjectId", "uuid", "identifier",
		"int", "int32", "int64", "long",
		"float", "float32", "float64", "double", "bool", "boolean",
		"json", "jsonb":
		return nonNullAccess, nil
	case "url":
		return nonNullAccess + ".toString()", nil
	case "timestamp", "datetime", "date":
		return nonNullAccess + ".toUtc().toIso8601String()", nil
	case "enum":
		return nonNullAccess + ".wireName", nil
	case "object":
		if strings.TrimSpace(field.ObjectRef) == "" {
			return nonNullAccess, nil
		}
		return nonNullAccess + ".toWire()", nil
	default:
		if strings.HasPrefix(metaType, "[]") {
			item := field
			item.Type = strings.TrimPrefix(metaType, "[]")
			item.Constraints = nil
			itemExpression, err := responseFieldEncodeExpression(item, "value")
			if err != nil {
				return "", err
			}
			return nonNullAccess + ".map((value) => " + itemExpression +
				").toList(growable: false)", nil
		}
		return nonNullAccess + ".toWire()", nil
	}
}

func renderDomainDecoderHelpers(
	output *strings.Builder,
	models map[string]requestModelSpec,
) {
	used := map[string]bool{}
	var record func(field fieldDef)
	record = func(field fieldDef) {
		metaType := strings.TrimSpace(field.Type)
		if strings.HasPrefix(metaType, "[]") {
			used["list"] = true
			item := field
			item.Type = strings.TrimPrefix(metaType, "[]")
			record(item)
			return
		}
		switch metaType {
		case "string", "tag_ref", "time", "ObjectId", "uuid", "identifier":
			used["string"] = true
			if hasRequestConstraint(field, "NOT_BLANK") {
				used["nonBlankString"] = true
			}
		case "url":
			used["string"] = true
			used["nonBlankString"] = true
			used["url"] = true
		case "timestamp", "datetime", "date":
			used["string"] = true
			used["timestamp"] = true
		case "int", "int32", "int64", "long":
			used["int"] = true
			if responseIntegerUsesBoundedDecoder(field) {
				used["boundedInt"] = true
				break
			}
			if hasRequestConstraint(field, "NON_NEGATIVE") {
				used["nonNegativeInt"] = true
			}
			if hasRequestConstraint(field, "MIN_1") {
				used["positiveInt"] = true
			}
		case "float", "float32", "float64", "double":
			used["double"] = true
		case "bool", "boolean":
			used["bool"] = true
		case "object", "json", "jsonb":
			used["object"] = true
		default:
			if metaType != "" && metaType != "enum" {
				used["object"] = true
			}
		}
	}
	for _, model := range models {
		for _, field := range model.Fields {
			record(field)
		}
	}
	output.WriteString(`Map<String, Object?> _requiredObject(Object? value, String path) {
  if (value is! Map<Object?, Object?>) {
    throw FormatException('$path must be an object');
  }
  final result = <String, Object?>{};
  for (final entry in value.entries) {
    final key = entry.key;
    if (key is! String) {
      throw FormatException('$path contains a non-string field name');
    }
    result[key] = entry.value;
  }
  return result;
}

void _rejectUnknownFields(
  Map<String, Object?> value,
  Set<String> allowed,
  String path,
) {
  final unknown = value.keys.where((key) => !allowed.contains(key)).toList()
    ..sort();
  if (unknown.isNotEmpty) {
    throw FormatException('$path contains unknown fields: ${unknown.join(', ')}');
  }
}
`)

	if used["string"] {
		output.WriteString(`
String _requiredString(Object? value, String path) {
  if (value is! String) throw FormatException('$path must be a string');
  return value;
}
`)
	}

	if used["nonBlankString"] {
		output.WriteString(`
String _requiredNonBlankString(Object? value, String path) {
  final result = _requiredString(value, path);
  if (result.trim().isEmpty) {
    throw FormatException('$path must not be blank');
  }
  return result;
}
`)
	}

	if used["url"] {
		output.WriteString(`
Uri _requiredUri(Object? value, String path) {
  final raw = _requiredNonBlankString(value, path);
  final parsed = Uri.tryParse(raw);
  if (parsed == null || !parsed.hasScheme) {
    throw FormatException('$path must be an absolute URI');
  }
  return parsed;
}
`)
	}

	if used["timestamp"] {
		output.WriteString(`
DateTime _requiredTimestamp(Object? value, String path) {
  final result = _requiredString(value, path);
  final parsed = DateTime.tryParse(result);
  if (parsed == null) {
    throw FormatException('$path must be an ISO-8601 timestamp');
  }
  return parsed;
}
`)
	}

	if used["int"] {
		output.WriteString(`
int _requiredInt(Object? value, String path) {
  if (value is! int) throw FormatException('$path must be an int');
  return value;
}
`)
	}

	if used["nonNegativeInt"] {
		output.WriteString(`
int _requiredNonNegativeInt(Object? value, String path) {
  final result = _requiredInt(value, path);
  if (result < 0) {
    throw FormatException('$path must not be negative');
  }
  return result;
}
`)
	}

	if used["positiveInt"] {
		output.WriteString(`
int _requiredPositiveInt(Object? value, String path) {
  final result = _requiredInt(value, path);
  if (result < 1) {
    throw FormatException('$path must be positive');
  }
  return result;
}
`)
	}

	if used["boundedInt"] {
		output.WriteString(`
int _requiredBoundedInt(
  Object? value,
  String path, {
  int? min,
  int? max,
}) {
  final result = _requiredInt(value, path);
  if (min != null && result < min) {
    throw FormatException('$path must be at least $min');
  }
  if (max != null && result > max) {
    throw FormatException('$path must not exceed $max');
  }
  return result;
}
`)
	}

	if used["double"] {
		output.WriteString(`
double _requiredDouble(Object? value, String path) {
  if (value is! num) throw FormatException('$path must be a number');
  return value.toDouble();
}
`)
	}

	if used["bool"] {
		output.WriteString(`
bool _requiredBool(Object? value, String path) {
  if (value is! bool) throw FormatException('$path must be a bool');
  return value;
}
`)
	}

	if used["list"] {
		output.WriteString(`
List<Object?> _requiredList(Object? value, String path) {
  if (value is! List<Object?>) {
    throw FormatException('$path must be a list');
  }
  return value;
}
`)
	}
}
