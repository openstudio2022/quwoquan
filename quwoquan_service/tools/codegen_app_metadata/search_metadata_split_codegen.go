package main

import (
	"fmt"
	"path/filepath"
	"strings"
)

const searchContractVocabularyImport = "../generated/search/search_contract_vocabulary.g.dart"

func writeCanonicalSearchMetadata(
	appDir string,
	contract *searchContractFile,
	objects *searchObjectsFile,
) error {
	if err := validateCanonicalSearchMetadata(contract, objects); err != nil {
		return err
	}
	writeFile(
		filepath.Join(
			appDir,
			"packages",
			"quwoquan_cloud_contracts",
			"lib",
			"src",
			"generated",
			"search",
			"search_contract_vocabulary.g.dart",
		),
		renderSearchContractVocabularyDart(contract, objects),
	)
	writeFile(
		searchIndexViewApplicationOutputPath(
			appDir,
			"search_execution_policy.g.dart",
		),
		renderSearchExecutionPolicyDart(contract, objects),
	)
	writeFile(
		searchIndexViewPresentationOutputPath(
			appDir,
			"search_display_metadata.g.dart",
		),
		renderSearchDisplayMetadataDart(objects),
	)
	return nil
}

func validateCanonicalSearchMetadata(
	contract *searchContractFile,
	objects *searchObjectsFile,
) error {
	if contract == nil || objects == nil {
		return fmt.Errorf("canonical Search metadata requires contract and objects")
	}
	if contract.Defaults.SuggestLimit <= 0 ||
		contract.Defaults.ResultLimit <= 0 ||
		contract.Defaults.AssistantLimit <= 0 {
		return fmt.Errorf("canonical Search limits must be positive")
	}
	strategies, err := uniqueSearchIDs(
		"execution strategy",
		contract.ExecutionStrategies,
	)
	if err != nil {
		return err
	}
	if _, err := uniqueSearchIDs(
		"conversation type",
		contract.ConversationTypes,
	); err != nil {
		return err
	}
	if err := uniqueSearchStrings(
		"retrieve forbidden field",
		contract.RetrieveContract.ForbiddenFields,
	); err != nil {
		return err
	}

	objectTypes := map[string]struct{}{}
	dartObjectTypes := map[string]string{}
	for _, item := range objects.ObjectTypes {
		id := strings.TrimSpace(item.ID)
		if id == "" {
			return fmt.Errorf("Search object type has an empty id")
		}
		if _, exists := objectTypes[id]; exists {
			return fmt.Errorf("duplicate Search object type %q", id)
		}
		objectTypes[id] = struct{}{}
		dartName := toDartValueName(id)
		if previous, exists := dartObjectTypes[dartName]; exists {
			return fmt.Errorf(
				"Search object types %q and %q map to the same Dart member %q",
				previous,
				id,
				dartName,
			)
		}
		dartObjectTypes[dartName] = id
		if strings.TrimSpace(item.Label) == "" ||
			strings.TrimSpace(item.Domain) == "" ||
			strings.TrimSpace(item.Provider) == "" {
			return fmt.Errorf(
				"Search object type %q requires label, domain, and provider",
				id,
			)
		}
		if _, exists := strategies[strings.TrimSpace(item.ExecutionStrategy)]; !exists {
			return fmt.Errorf(
				"Search object type %q references unknown execution strategy %q",
				id,
				item.ExecutionStrategy,
			)
		}
	}
	if len(objectTypes) == 0 {
		return fmt.Errorf("canonical Search object type vocabulary is empty")
	}

	targets := map[string]struct{}{}
	dartTargets := map[string]string{}
	for _, item := range objects.AITargets {
		id := strings.TrimSpace(item.ID)
		if id == "" {
			return fmt.Errorf("Search retrieve target has an empty id")
		}
		if _, exists := targets[id]; exists {
			return fmt.Errorf("duplicate Search retrieve target %q", id)
		}
		targets[id] = struct{}{}
		dartName := toDartValueName(id)
		if previous, exists := dartTargets[dartName]; exists {
			return fmt.Errorf(
				"Search retrieve targets %q and %q map to the same Dart member %q",
				previous,
				id,
				dartName,
			)
		}
		dartTargets[dartName] = id
		if strings.TrimSpace(item.Label) == "" {
			return fmt.Errorf("Search retrieve target %q has an empty label", id)
		}
		if _, exists := objectTypes[strings.TrimSpace(item.ObjectType)]; !exists {
			return fmt.Errorf(
				"Search retrieve target %q references unknown object type %q",
				id,
				item.ObjectType,
			)
		}
	}
	if len(targets) == 0 {
		return fmt.Errorf("canonical Search retrieve target vocabulary is empty")
	}

	sections := map[string]struct{}{}
	for _, item := range objects.SectionKinds {
		id := strings.TrimSpace(item.ID)
		if id == "" {
			return fmt.Errorf("Search display section has an empty id")
		}
		if _, exists := sections[id]; exists {
			return fmt.Errorf("duplicate Search display section %q", id)
		}
		sections[id] = struct{}{}
		if strings.TrimSpace(item.Title) == "" {
			return fmt.Errorf("Search display section %q has an empty title", id)
		}
		for _, objectType := range item.DefaultObjectTypes {
			if _, exists := objectTypes[strings.TrimSpace(objectType)]; !exists {
				return fmt.Errorf(
					"Search display section %q references unknown object type %q",
					id,
					objectType,
				)
			}
		}
	}
	return nil
}

func uniqueSearchIDs(
	kind string,
	values []searchNamedValueDef,
) (map[string]struct{}, error) {
	result := make(map[string]struct{}, len(values))
	dartNames := make(map[string]string, len(values))
	for _, value := range values {
		id := strings.TrimSpace(value.ID)
		if id == "" {
			return nil, fmt.Errorf("Search %s has an empty id", kind)
		}
		if _, exists := result[id]; exists {
			return nil, fmt.Errorf("duplicate Search %s %q", kind, id)
		}
		result[id] = struct{}{}
		dartName := toDartValueName(id)
		if previous, exists := dartNames[dartName]; exists {
			return nil, fmt.Errorf(
				"Search %s values %q and %q map to the same Dart member %q",
				kind,
				previous,
				id,
				dartName,
			)
		}
		dartNames[dartName] = id
	}
	if len(result) == 0 {
		return nil, fmt.Errorf("canonical Search %s vocabulary is empty", kind)
	}
	return result, nil
}

func uniqueSearchStrings(kind string, values []string) error {
	seen := make(map[string]struct{}, len(values))
	for _, value := range values {
		value = strings.TrimSpace(value)
		if value == "" {
			return fmt.Errorf("Search %s is empty", kind)
		}
		if _, exists := seen[value]; exists {
			return fmt.Errorf("duplicate Search %s %q", kind, value)
		}
		seen[value] = struct{}{}
	}
	if len(seen) == 0 {
		return fmt.Errorf("canonical Search %s vocabulary is empty", kind)
	}
	return nil
}

func renderSearchContractVocabularyDart(
	contract *searchContractFile,
	objects *searchObjectsFile,
) string {
	var b strings.Builder
	b.WriteString("// Code generated from canonical Search metadata. DO NOT EDIT.\n")
	b.WriteString("// Sources: _shared/search_contract.yaml, _shared/search_objects.yaml\n\n")
	b.WriteString("library;\n\n")
	renderSearchWireEnum(&b, "SearchObjectType", searchObjectTypeIDs(objects))
	renderSearchWireEnum(&b, "RetrieveTarget", searchRetrieveTargetIDs(objects))
	renderSearchWireEnum(
		&b,
		"SearchConversationType",
		searchNamedValueIDs(contract.ConversationTypes),
	)
	b.WriteString("// ignore: avoid_classes_with_only_static_members\n")
	b.WriteString("final class RetrieveToolContract {\n")
	b.WriteString("  const RetrieveToolContract._();\n\n")
	b.WriteString(fmt.Sprintf(
		"  static const List<String> forbiddenFields = %s;\n",
		renderStringListLiteral(contract.RetrieveContract.ForbiddenFields),
	))
	b.WriteString("}\n")
	return b.String()
}

func renderSearchExecutionPolicyDart(
	contract *searchContractFile,
	objects *searchObjectsFile,
) string {
	var b strings.Builder
	b.WriteString("// Code generated from canonical Search metadata. DO NOT EDIT.\n")
	b.WriteString("// Sources: _shared/search_contract.yaml, _shared/search_objects.yaml\n\n")
	b.WriteString("import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'\n")
	b.WriteString("    show RetrieveTarget, SearchObjectType;\n\n")
	renderSearchWireEnum(
		&b,
		"SearchExecutionStrategy",
		searchNamedValueIDs(contract.ExecutionStrategies),
	)
	b.WriteString("// ignore: avoid_classes_with_only_static_members\n")
	b.WriteString("final class SearchContractDefaults {\n")
	b.WriteString("  const SearchContractDefaults._();\n\n")
	b.WriteString(fmt.Sprintf("  static const int suggestLimit = %d;\n", contract.Defaults.SuggestLimit))
	b.WriteString(fmt.Sprintf("  static const int resultLimit = %d;\n", contract.Defaults.ResultLimit))
	b.WriteString(fmt.Sprintf("  static const int assistantLimit = %d;\n", contract.Defaults.AssistantLimit))
	b.WriteString("}\n\n")
	b.WriteString("final class SearchObjectExecutionPolicy {\n")
	b.WriteString("  const SearchObjectExecutionPolicy({\n")
	b.WriteString("    required this.type,\n")
	b.WriteString("    required this.domain,\n")
	b.WriteString("    required this.strategy,\n")
	b.WriteString("    required this.provider,\n")
	b.WriteString("  });\n\n")
	b.WriteString("  final SearchObjectType type;\n")
	b.WriteString("  final String domain;\n")
	b.WriteString("  final SearchExecutionStrategy strategy;\n")
	b.WriteString("  final String provider;\n")
	b.WriteString("}\n\n")
	b.WriteString("final class SearchRetrieveTargetPolicy {\n")
	b.WriteString("  const SearchRetrieveTargetPolicy({\n")
	b.WriteString("    required this.target,\n")
	b.WriteString("    required this.objectType,\n")
	b.WriteString("    required this.contentType,\n")
	b.WriteString("  });\n\n")
	b.WriteString("  final RetrieveTarget target;\n")
	b.WriteString("  final SearchObjectType objectType;\n")
	b.WriteString("  final String contentType;\n")
	b.WriteString("}\n\n")
	b.WriteString("// ignore: avoid_classes_with_only_static_members\n")
	b.WriteString("final class SearchExecutionPolicy {\n")
	b.WriteString("  const SearchExecutionPolicy._();\n\n")
	b.WriteString("  static const List<SearchObjectExecutionPolicy> objectTypes =\n")
	b.WriteString("      <SearchObjectExecutionPolicy>[\n")
	for _, item := range objects.ObjectTypes {
		b.WriteString("    SearchObjectExecutionPolicy(\n")
		b.WriteString(fmt.Sprintf("      type: SearchObjectType.%s,\n", toDartValueName(item.ID)))
		b.WriteString(fmt.Sprintf("      domain: '%s',\n", escapeDartString(item.Domain)))
		b.WriteString(fmt.Sprintf("      strategy: SearchExecutionStrategy.%s,\n", toDartValueName(item.ExecutionStrategy)))
		b.WriteString(fmt.Sprintf("      provider: '%s',\n", escapeDartString(item.Provider)))
		b.WriteString("    ),\n")
	}
	b.WriteString("  ];\n\n")
	b.WriteString("  static const List<SearchRetrieveTargetPolicy> retrieveTargets =\n")
	b.WriteString("      <SearchRetrieveTargetPolicy>[\n")
	for _, item := range objects.AITargets {
		b.WriteString("    SearchRetrieveTargetPolicy(\n")
		b.WriteString(fmt.Sprintf("      target: RetrieveTarget.%s,\n", toDartValueName(item.ID)))
		b.WriteString(fmt.Sprintf("      objectType: SearchObjectType.%s,\n", toDartValueName(item.ObjectType)))
		b.WriteString(fmt.Sprintf("      contentType: '%s',\n", escapeDartString(item.ContentType)))
		b.WriteString("    ),\n")
	}
	b.WriteString("  ];\n\n")
	b.WriteString("  static SearchObjectExecutionPolicy? objectPolicyFor(\n")
	b.WriteString("    SearchObjectType type,\n")
	b.WriteString("  ) {\n")
	b.WriteString("    for (final policy in objectTypes) {\n")
	b.WriteString("      if (policy.type == type) return policy;\n")
	b.WriteString("    }\n")
	b.WriteString("    return null;\n")
	b.WriteString("  }\n\n")
	b.WriteString("  static SearchRetrieveTargetPolicy? retrievePolicyFor(\n")
	b.WriteString("    RetrieveTarget target,\n")
	b.WriteString("  ) {\n")
	b.WriteString("    for (final policy in retrieveTargets) {\n")
	b.WriteString("      if (policy.target == target) return policy;\n")
	b.WriteString("    }\n")
	b.WriteString("    return null;\n")
	b.WriteString("  }\n")
	b.WriteString("}\n")
	return b.String()
}

func renderSearchDisplayMetadataDart(objects *searchObjectsFile) string {
	var b strings.Builder
	b.WriteString("// Code generated from canonical Search metadata. DO NOT EDIT.\n")
	b.WriteString("// Source: _shared/search_objects.yaml\n\n")
	b.WriteString("import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'\n")
	b.WriteString("    show RetrieveTarget, SearchObjectType;\n\n")
	b.WriteString("final class SearchObjectDisplayMetadata {\n")
	b.WriteString("  const SearchObjectDisplayMetadata({required this.type, required this.label});\n\n")
	b.WriteString("  final SearchObjectType type;\n")
	b.WriteString("  final String label;\n")
	b.WriteString("}\n\n")
	b.WriteString("final class SearchSectionDisplayMetadata {\n")
	b.WriteString("  const SearchSectionDisplayMetadata({\n")
	b.WriteString("    required this.id,\n")
	b.WriteString("    required this.title,\n")
	b.WriteString("    required this.defaultObjectTypes,\n")
	b.WriteString("  });\n\n")
	b.WriteString("  final String id;\n")
	b.WriteString("  final String title;\n")
	b.WriteString("  final List<SearchObjectType> defaultObjectTypes;\n")
	b.WriteString("}\n\n")
	b.WriteString("final class SearchRetrieveTargetDisplayMetadata {\n")
	b.WriteString("  const SearchRetrieveTargetDisplayMetadata({\n")
	b.WriteString("    required this.target,\n")
	b.WriteString("    required this.label,\n")
	b.WriteString("  });\n\n")
	b.WriteString("  final RetrieveTarget target;\n")
	b.WriteString("  final String label;\n")
	b.WriteString("}\n\n")
	b.WriteString("// ignore: avoid_classes_with_only_static_members\n")
	b.WriteString("final class SearchDisplayMetadata {\n")
	b.WriteString("  const SearchDisplayMetadata._();\n\n")
	b.WriteString("  static const List<SearchObjectDisplayMetadata> objectTypes =\n")
	b.WriteString("      <SearchObjectDisplayMetadata>[\n")
	for _, item := range objects.ObjectTypes {
		b.WriteString("    SearchObjectDisplayMetadata(\n")
		b.WriteString(fmt.Sprintf("      type: SearchObjectType.%s,\n", toDartValueName(item.ID)))
		b.WriteString(fmt.Sprintf("      label: '%s',\n", escapeDartString(item.Label)))
		b.WriteString("    ),\n")
	}
	b.WriteString("  ];\n\n")
	b.WriteString("  static const List<SearchSectionDisplayMetadata> sections =\n")
	b.WriteString("      <SearchSectionDisplayMetadata>[\n")
	for _, item := range objects.SectionKinds {
		b.WriteString("    SearchSectionDisplayMetadata(\n")
		b.WriteString(fmt.Sprintf("      id: '%s',\n", escapeDartString(item.ID)))
		b.WriteString(fmt.Sprintf("      title: '%s',\n", escapeDartString(item.Title)))
		b.WriteString(fmt.Sprintf("      defaultObjectTypes: %s,\n", renderSearchObjectTypesLiteral(item.DefaultObjectTypes)))
		b.WriteString("    ),\n")
	}
	b.WriteString("  ];\n\n")
	b.WriteString("  static const List<SearchRetrieveTargetDisplayMetadata> retrieveTargets =\n")
	b.WriteString("      <SearchRetrieveTargetDisplayMetadata>[\n")
	for _, item := range objects.AITargets {
		b.WriteString("    SearchRetrieveTargetDisplayMetadata(\n")
		b.WriteString(fmt.Sprintf("      target: RetrieveTarget.%s,\n", toDartValueName(item.ID)))
		b.WriteString(fmt.Sprintf("      label: '%s',\n", escapeDartString(item.Label)))
		b.WriteString("    ),\n")
	}
	b.WriteString("  ];\n\n")
	b.WriteString("  static SearchObjectDisplayMetadata? objectFor(SearchObjectType type) {\n")
	b.WriteString("    for (final item in objectTypes) {\n")
	b.WriteString("      if (item.type == type) return item;\n")
	b.WriteString("    }\n")
	b.WriteString("    return null;\n")
	b.WriteString("  }\n\n")
	b.WriteString("  static SearchSectionDisplayMetadata? sectionFor(String id) {\n")
	b.WriteString("    for (final item in sections) {\n")
	b.WriteString("      if (item.id == id) return item;\n")
	b.WriteString("    }\n")
	b.WriteString("    return null;\n")
	b.WriteString("  }\n")
	b.WriteString("}\n")
	return b.String()
}

func renderSearchWireEnum(
	b *strings.Builder,
	name string,
	values []string,
) {
	b.WriteString("enum " + name + " {\n")
	for _, value := range values {
		b.WriteString(fmt.Sprintf("  %s('%s'),\n", toDartValueName(value), escapeDartString(value)))
	}
	b.WriteString("  ;\n\n")
	b.WriteString("  const " + name + "(this.wireValue);\n\n")
	b.WriteString("  final String wireValue;\n\n")
	b.WriteString("  static " + name + "? fromWire(String? value) {\n")
	b.WriteString("    switch ((value ?? '').trim()) {\n")
	for _, value := range values {
		b.WriteString(fmt.Sprintf("      case '%s':\n", escapeDartString(value)))
		b.WriteString(fmt.Sprintf("        return %s.%s;\n", name, toDartValueName(value)))
	}
	b.WriteString("      default:\n")
	b.WriteString("        return null;\n")
	b.WriteString("    }\n")
	b.WriteString("  }\n")
	b.WriteString("}\n\n")
}

func searchNamedValueIDs(values []searchNamedValueDef) []string {
	result := make([]string, 0, len(values))
	for _, value := range values {
		result = append(result, value.ID)
	}
	return result
}

func searchObjectTypeIDs(objects *searchObjectsFile) []string {
	result := make([]string, 0, len(objects.ObjectTypes))
	for _, value := range objects.ObjectTypes {
		result = append(result, value.ID)
	}
	return result
}

func searchRetrieveTargetIDs(objects *searchObjectsFile) []string {
	result := make([]string, 0, len(objects.AITargets))
	for _, value := range objects.AITargets {
		result = append(result, value.ID)
	}
	return result
}
