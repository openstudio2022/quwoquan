package main

import (
	"fmt"
	"path/filepath"
	"sort"
	"strings"
)

func readShared(path string) (*sharedTypes, error) {
	var parsed sharedTypes
	return &parsed, decodeMetadataDocument(path, &parsed)
}

func readFields(path string) (*fieldsFile, error) {
	var parsed fieldsFile
	if err := decodeMetadataDocument(path, &parsed); err != nil {
		return &parsed, err
	}
	if parsed.Entities == nil {
		parsed.Entities = map[string]entityDef{}
	}
	for name, definition := range parsed.Types {
		parsed.Entities[name] = definition
	}
	for name, definition := range parsed.Members {
		parsed.Entities[name] = definition
	}
	if len(parsed.Fields) > 0 {
		objectName := filepath.Base(filepath.Dir(path))
		parsed.Entities[objectTypeName(objectName)] = entityDef{
			Fields: parsed.Fields,
		}
	}
	return &parsed, nil
}

func objectTypeName(value string) string {
	parts := strings.Split(value, "_")
	for index, part := range parts {
		if part == "" {
			continue
		}
		parts[index] = strings.ToUpper(part[:1]) + part[1:]
	}
	return strings.Join(parts, "")
}

func readService(path string) (*serviceFile, error) {
	var parsed serviceFile
	return &parsed, decodeMetadataDocument(path, &parsed)
}

func readProjection(path string) (*projectionFile, error) {
	var parsed projectionFile
	if err := decodeMetadataDocument(path, &parsed); err != nil {
		return &parsed, err
	}
	parsed.clientProjectionFieldsDeclared = len(parsed.ClientProjection.Fields) > 0
	hasClientProjection :=
		strings.TrimSpace(parsed.ClientProjection.DartClass) != "" ||
			strings.TrimSpace(parsed.ClientProjection.BaseClass) != "" ||
			strings.TrimSpace(parsed.ClientProjection.OutputPath) != "" ||
			strings.TrimSpace(parsed.ClientProjection.ExternalDartPath) != "" ||
			len(parsed.ClientProjection.Fields) > 0 ||
			len(parsed.ClientProjection.ComputedGetters) > 0
	if !hasClientProjection {
		// Backend-only projections may use storage-specific field shapes. They are
		// not App DTO declarations and must not be reinterpreted by App codegen.
		return &parsed, nil
	}
	if externalPath := strings.TrimSpace(parsed.ClientProjection.ExternalDartPath); externalPath != "" {
		if strings.TrimSpace(parsed.ClientProjection.DartClass) == "" {
			return &parsed, fmt.Errorf(
				"%s client_projection.external_dart_path requires dart_class",
				path,
			)
		}
		return &parsed, nil
	}
	if len(parsed.ClientProjection.Fields) == 0 {
		parsed.ClientProjection.Fields = append(
			[]projectionFieldDef(nil),
			parsed.Fields...,
		)
		for index := range parsed.ClientProjection.Fields {
			field := &parsed.ClientProjection.Fields[index]
			field.Source = field.Name
			if strings.TrimSpace(field.DartType) == "" {
				dartType, err := projectionWireTypeToDart(field.WireType)
				if err != nil {
					return &parsed, fmt.Errorf(
						"%s field %s: %w",
						path,
						field.Name,
						err,
					)
				}
				field.DartType = dartType
			}
			inferCanonicalProjectionDecoderBinding(field)
		}
	}
	return &parsed, nil
}

// inferCanonicalProjectionDecoderBinding derives the Dart object decoder from
// the canonical projection field type. Object-local fields remain the only
// field-shape truth; client_projection carries output placement only.
func inferCanonicalProjectionDecoderBinding(field *projectionFieldDef) {
	if field == nil {
		return
	}
	dartType := normalizeDartType(field.DartType)
	if strings.HasPrefix(dartType, "List<") && strings.HasSuffix(dartType, ">") {
		element := strings.TrimSpace(strings.TrimSuffix(
			strings.TrimPrefix(dartType, "List<"),
			">",
		))
		if isDartIdentifier(element) && element != "String" {
			field.ListElementDartClass = element
		}
		return
	}
	if strings.TrimSpace(field.EnumRef) != "" {
		return
	}
	switch dartType {
	case "", "String", "DateTime", "int", "double", "bool", "Map<String, dynamic>":
		return
	}
	if isDartIdentifier(dartType) {
		field.MapFromStringKeyClass = dartType
	}
}

func readValidatedProjection(
	path string,
	canonicalEnums map[string][]string,
) (*projectionFile, error) {
	parsed, err := readProjection(path)
	if err != nil {
		return parsed, err
	}
	if err := validateClientProjectionEnums(path, parsed, canonicalEnums); err != nil {
		return parsed, err
	}
	return parsed, nil
}

// validateClientProjectionEnums prevents an explicitly typed App DTO field
// from inventing a second enum class or silently degrading to String. A field
// that intentionally remains String may still carry enum_ref as validation
// metadata, but a typed enum must be the exact _shared/types.yaml class and
// have one wire representation with no client-side default.
func validateClientProjectionEnums(
	path string,
	projection *projectionFile,
	canonicalEnums map[string][]string,
) error {
	if projection == nil || !projection.clientProjectionFieldsDeclared {
		return nil
	}
	for _, field := range projection.ClientProjection.Fields {
		enumRef := strings.TrimSpace(field.EnumRef)
		dartType := strings.TrimSuffix(strings.TrimSpace(field.DartType), "?")
		wireType := strings.TrimSpace(field.WireType)
		_, dartTypeIsCanonicalEnum := canonicalEnums[dartType]
		typedEnum := dartTypeIsCanonicalEnum || (enumRef != "" && dartType == enumRef)

		if enumRef != "" {
			if values := canonicalEnums[enumRef]; len(values) == 0 {
				return fmt.Errorf(
					"%s client_projection field %s enum_ref %s is absent from _shared/types.yaml",
					path,
					field.Name,
					enumRef,
				)
			}
		}
		if !typedEnum {
			if wireType == "enum" {
				return fmt.Errorf(
					"%s client_projection field %s type=enum must use dart_type matching enum_ref",
					path,
					field.Name,
				)
			}
			continue
		}
		if enumRef == "" || dartType != enumRef {
			return fmt.Errorf(
				"%s client_projection field %s typed enum %s must use the same enum_ref",
				path,
				field.Name,
				dartType,
			)
		}
		if wireType != "enum" {
			return fmt.Errorf(
				"%s client_projection field %s typed enum %s requires type=enum",
				path,
				field.Name,
				dartType,
			)
		}
		if strings.TrimSpace(field.Default) != "" {
			return fmt.Errorf(
				"%s client_projection field %s typed enum must not declare a default",
				path,
				field.Name,
			)
		}
	}
	return nil
}

func readProjectionBinding(path string) (*projectionBinding, error) {
	var parsed projectionBinding
	if err := decodeMetadataDocument(path, &parsed); err != nil {
		return &parsed, err
	}
	if externalPath := strings.TrimSpace(parsed.ClientProjection.ExternalDartPath); externalPath != "" &&
		strings.TrimSpace(parsed.ClientProjection.DartClass) == "" {
		return &parsed, fmt.Errorf(
			"%s client_projection.external_dart_path requires dart_class",
			path,
		)
	}
	return &parsed, nil
}

func projectionWireTypeToDart(raw string) (string, error) {
	canonical := strings.TrimSpace(raw)
	switch canonical {
	case "string", "enum", "date", "time", "tag_ref":
		return "String", nil
	case "timestamp", "datetime":
		return "DateTime", nil
	case "int", "int32", "int64":
		return "int", nil
	case "float", "float32", "float64", "double", "number":
		return "double", nil
	case "bool", "boolean":
		return "bool", nil
	case "[]string", "string[]":
		return "List<String>", nil
	case "map", "json", "object":
		return "Map<String, dynamic>", nil
	}
	if strings.HasPrefix(canonical, "[]") {
		item := strings.TrimSpace(strings.TrimPrefix(canonical, "[]"))
		if isDartIdentifier(item) {
			return "List<" + item + ">", nil
		}
	}
	if isDartIdentifier(canonical) {
		return canonical, nil
	}
	return "", fmt.Errorf("unsupported projection wire type %q", raw)
}

// projectionPathByReadModel resolves a projection from the compiled
// ContractGraph Source instead of reconstructing its owner directory. Moving a
// projection between business objects therefore changes only canonical
// metadata; the App emitter follows the read_model identity and fails on
// duplicates rather than silently reading a stale path.
func projectionPathByReadModel(metadataDir, readModel string) (string, error) {
	readModel = strings.TrimSpace(readModel)
	if readModel == "" {
		return "", fmt.Errorf("projection read_model is required")
	}
	var matched string
	for _, path := range metadataDocumentPaths("", ".yaml") {
		if filepath.Base(filepath.Dir(path)) != "projections" {
			continue
		}
		projection, err := readProjectionBinding(path)
		if err != nil || strings.TrimSpace(projection.ReadModel) != readModel {
			continue
		}
		if matched != "" {
			first, _ := filepath.Rel(metadataDir, matched)
			second, _ := filepath.Rel(metadataDir, path)
			return "", fmt.Errorf(
				"projection read_model %q is ambiguous: %s, %s",
				readModel,
				filepath.ToSlash(first),
				filepath.ToSlash(second),
			)
		}
		matched = path
	}
	if matched == "" {
		return "", fmt.Errorf("projection read_model %q is absent", readModel)
	}
	return matched, nil
}

// ── builders ──────────────────────────────────────────────────────────────────

func collectDomainServiceRoutes(metadataDir string) (map[string][]routeDef, error) {
	grouped := map[string][]routeDef{}
	seen := map[string]bool{}
	for _, path := range metadataDocumentPaths("", "/operations.yaml") {
		service, readErr := readService(path)
		if readErr != nil {
			return nil, readErr
		}
		relative, relErr := filepath.Rel(metadataDir, path)
		if relErr != nil || len(strings.Split(filepath.ToSlash(relative), "/")) < 4 {
			continue
		}
		domain := strings.Split(filepath.ToSlash(relative), "/")[0]
		for _, route := range service.APIRoutes {
			if strings.TrimSpace(route.Operation) == "" || strings.TrimSpace(route.Path) == "" {
				continue
			}
			key := domain + ":" + route.Operation
			if seen[key] {
				continue
			}
			seen[key] = true
			grouped[domain] = append(grouped[domain], route)
		}
	}
	for domain := range grouped {
		sort.Slice(grouped[domain], func(i, j int) bool {
			return grouped[domain][i].Operation < grouped[domain][j].Operation
		})
	}
	return grouped, nil
}

func readErrors(path string) (*errorsFile, error) {
	var parsed errorsFile
	return &parsed, decodeMetadataDocument(path, &parsed)
}

func readMergedErrors(paths []string) (*errorsFile, error) {
	merged := &errorsFile{}
	for _, path := range paths {
		ef, err := readErrors(path)
		if err != nil {
			return nil, err
		}
		if merged.Domain == "" {
			merged.Domain = ef.Domain
		}
		merged.Errors = append(merged.Errors, ef.Errors...)
	}
	return merged, nil
}

func readUserDomainErrors(metadataDir string) (*errorsFile, error) {
	root := filepath.Join(metadataDir, "user")
	paths := metadataDocumentPaths("user", "/errors.yaml")
	sort.Strings(paths)
	if len(paths) == 0 {
		return nil, fmt.Errorf("no user errors metadata found under %s", root)
	}
	return readMergedErrors(paths)
}

// contentDomainErrorsPaths 是 content 域错误码的固定合并顺序：
// post（域共享 + Post 自有）在前，随后按对象目录字典序。
// 与 quwoquan_app/scripts/runtime/verify_error_code_endcloud_parity.py 及
// quwoquan_service/scripts/verify/consistency/verify_error_recovery_alignment.py 的列表保持一致。
func contentDomainErrorsPaths(metadataDir string) []string {
	return []string{
		filepath.Join(metadataDir, "content", "content", "post", "errors.yaml"),
		filepath.Join(metadataDir, "content", "content", "comment", "errors.yaml"),
		filepath.Join(metadataDir, "content", "content", "content_reaction", "errors.yaml"),
		filepath.Join(metadataDir, "content", "content", "deleted_post_tombstone", "errors.yaml"),
		filepath.Join(metadataDir, "content", "content", "profile_interaction_activity_view", "errors.yaml"),
		filepath.Join(metadataDir, "content", "content", "profile_interaction_read_fact", "errors.yaml"),
		filepath.Join(metadataDir, "content", "media", "filter_catalog_release", "errors.yaml"),
		filepath.Join(metadataDir, "content", "media", "media_asset", "errors.yaml"),
		filepath.Join(metadataDir, "content", "media", "original_access_quota", "errors.yaml"),
		filepath.Join(metadataDir, "content", "media", "media_upload_session", "errors.yaml"),
		filepath.Join(metadataDir, "content", "content", "outbound_share_fact", "errors.yaml"),
		filepath.Join(metadataDir, "content", "trust_safety", "post_moderation_case", "errors.yaml"),
		filepath.Join(metadataDir, "content", "trust_safety", "report", "errors.yaml"),
	}
}

func readUIConfig(
	path string,
	requireOnboardingInterestCatalog bool,
) (*uiConfigFile, error) {
	var parsed uiConfigFile
	if err := decodeMetadataDocument(path, &parsed); err != nil {
		return nil, err
	}
	catalog := parsed.OnboardingInterestCatalog
	if !requireOnboardingInterestCatalog &&
		catalog.MinSelectionCount == 0 &&
		catalog.MaxSelectionCount == 0 &&
		len(catalog.Dimensions) == 0 {
		return &parsed, nil
	}
	if catalog.MinSelectionCount <= 0 ||
		catalog.MaxSelectionCount < catalog.MinSelectionCount ||
		len(catalog.Dimensions) == 0 {
		return nil, fmt.Errorf(
			"onboarding_interest_catalog requires valid selection bounds and dimensions",
		)
	}
	dimensionIDs := make(map[string]struct{}, len(catalog.Dimensions))
	for _, dimension := range catalog.Dimensions {
		if strings.TrimSpace(dimension.ID) == "" ||
			strings.TrimSpace(dimension.TagRef) == "" ||
			dimension.MinSelections < 0 ||
			dimension.MaxSelections < dimension.MinSelections {
			return nil, fmt.Errorf(
				"onboarding_interest_catalog dimension requires id/tag_ref and valid selection bounds",
			)
		}
		if _, exists := dimensionIDs[dimension.ID]; exists {
			return nil, fmt.Errorf(
				"onboarding_interest_catalog dimension id %q is duplicated",
				dimension.ID,
			)
		}
		dimensionIDs[dimension.ID] = struct{}{}
	}
	return &parsed, nil
}

func readContentPublicationPolicy(
	path string,
) (*contentPublicationPolicyFile, error) {
	var parsed contentPublicationPolicyFile
	if err := decodeMetadataDocument(path, &parsed); err != nil {
		return nil, err
	}
	if parsed.Schema != "content_post_publication_policy" {
		return nil, fmt.Errorf("publication policy schema must be content_post_publication_policy")
	}
	limits := parsed.TextLimits
	if limits.TitleMaxRunes <= 0 ||
		limits.MicroBodyMaxRunes <= 0 ||
		limits.ArticleMarkdownMaxRunes <= 0 ||
		limits.SummaryMaxRunes <= 0 ||
		limits.SemanticMentionsMaxItems <= 0 {
		return nil, fmt.Errorf("publication policy text limits must be positive")
	}
	if parsed.RateLimit.PersonaWindowSeconds <= 0 ||
		parsed.RateLimit.PersonaMaxPublications <= 0 ||
		parsed.RateLimit.DependencyFailure != "fail_closed" {
		return nil, fmt.Errorf("publication rate limit must be positive and fail_closed")
	}
	if !parsed.Safety.Required ||
		parsed.Safety.DependencyFailure != "fail_closed" ||
		parsed.Safety.UnavailableAction != "review" ||
		len(parsed.Safety.Decisions) != 4 {
		return nil, fmt.Errorf("publication safety gate must be required and fail_closed")
	}
	return &parsed, nil
}

func readContentMediaUploadPolicy(
	path string,
) (*contentMediaUploadPolicyFile, error) {
	var parsed contentMediaUploadPolicyFile
	if err := decodeMetadataDocument(path, &parsed); err != nil {
		return nil, err
	}
	if parsed.Schema != "content_media_upload_policy" {
		return nil, fmt.Errorf("media upload policy schema must be content_media_upload_policy")
	}
	if !parsed.StreamingRequired {
		return nil, fmt.Errorf("media upload policy must require streaming")
	}
	for _, mediaType := range []string{"image", "video", "audio", "file"} {
		definition, ok := parsed.MediaTypes[mediaType]
		if !ok ||
			definition.MaxFileSizeBytes <= 0 ||
			len(definition.AllowedContentTypes) == 0 {
			return nil, fmt.Errorf("media upload policy %s limits and content types are required", mediaType)
		}
	}
	if parsed.Errors.FileTooLarge == "" || parsed.Errors.UnsupportedType == "" {
		return nil, fmt.Errorf("media upload policy error codes are required")
	}
	return &parsed, nil
}

func readContentImageVariantPolicy(
	path string,
) (*contentImageVariantPolicyFile, error) {
	var parsed contentImageVariantPolicyFile
	if err := decodeMetadataDocument(path, &parsed); err != nil {
		return nil, err
	}
	if parsed.Schema != "content_image_variant_policy" ||
		parsed.DerivativePolicyVersion <= 0 {
		return nil, fmt.Errorf(
			"image variant policy requires schema and positive derivative policy version",
		)
	}
	expected := map[string]struct {
		width      int
		format     string
		quality    int
		processing string
	}{
		"thumbnail": {320, "webp", 80, "image/resize,w_320/format,webp/quality,q_80"},
		"display":   {960, "webp", 82, "image/resize,w_960/format,webp/quality,q_82"},
		"cover":     {1280, "webp", 85, "image/resize,w_1280/format,webp/quality,q_85"},
		"full":      {2048, "webp", 90, "image/resize,w_2048/format,webp/quality,q_90"},
	}
	if len(parsed.Profiles) != len(expected) {
		return nil, fmt.Errorf("image variant policy has unexpected profiles")
	}
	for name, want := range expected {
		profile, ok := parsed.Profiles[name]
		if !ok ||
			profile.Width != want.width ||
			profile.Format != want.format ||
			profile.Quality != want.quality ||
			profile.Processing != want.processing ||
			strings.TrimSpace(profile.Scene) == "" {
			return nil, fmt.Errorf("image variant policy %s is invalid", name)
		}
	}
	return &parsed, nil
}

func readRequestContext(path string) (*requestContextFile, error) {
	var parsed requestContextFile
	return &parsed, decodeMetadataDocument(path, &parsed)
}

func readAppRoutes(path string) (*appRoutesFile, error) {
	var parsed appRoutesFile
	return &parsed, decodeMetadataDocument(path, &parsed)
}

func readUISurfaces(path string) (*uiSurfacesFile, error) {
	var parsed uiSurfacesFile
	return &parsed, decodeMetadataDocument(path, &parsed)
}

func readAppPages(path string) (*appPagesFile, error) {
	var parsed appPagesFile
	return &parsed, decodeMetadataDocument(path, &parsed)
}

func readTelemetryEventCatalog(path string) (*telemetryEventCatalogFile, error) {
	var parsed telemetryEventCatalogFile
	return &parsed, decodeMetadataDocument(path, &parsed)
}

func readSearchContract(path string) (*searchContractFile, error) {
	var parsed searchContractFile
	return &parsed, decodeMetadataDocument(path, &parsed)
}

func readSearchObjects(path string) (*searchObjectsFile, error) {
	var parsed searchObjectsFile
	return &parsed, decodeMetadataDocument(path, &parsed)
}

// ── new cross-cutting renderers ───────────────────────────────────────────────
