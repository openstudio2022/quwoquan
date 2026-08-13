package load

import (
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"

	"quwoquan_service/internal/metadata/ast"

	"gopkg.in/yaml.v3"
)

var (
	readinessCaseIDPattern  = regexp.MustCompile(`^[a-z][a-z0-9_-]*$`)
	readinessSpecRefPattern = regexp.MustCompile(
		`^(specs/feature-tree/(?:[A-Za-z0-9_.-]+/)*spec\.md)#((?:uat|dom|sit|gwt)-[0-9]{3,})$`,
	)
	readinessOperationIDPattern = regexp.MustCompile(`^[A-Z][A-Za-z0-9]+$`)
	readinessPageIDPattern      = regexp.MustCompile(
		`^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$`,
	)
)

// loadReadinessCases reads only the object-local operations source. It does
// not discover cases from tests, generated output, or a central registry.
func loadReadinessCases(
	metadataDir,
	path string,
	object ast.Object,
	operations []ast.Operation,
	runtimeEntrypoints []ast.RuntimeEntrypoint,
	repoRoot string,
	contractView *contractViewProvenance,
) ([]ast.ReadinessCaseContract, error) {
	top, err := loadTopLevelMapping(path)
	if err != nil {
		return nil, err
	}
	node := top["readiness_cases"]
	if node == nil {
		return nil, nil
	}
	if node.Kind != yaml.SequenceNode || len(node.Content) == 0 {
		return nil, fmt.Errorf("%s: readiness_cases must be a non-empty sequence", path)
	}

	operationIDs := make(map[string]struct{}, len(operations)+len(runtimeEntrypoints))
	for _, operation := range operations {
		if err := addReadinessOperationTarget(operationIDs, operation.LocalID); err != nil {
			return nil, fmt.Errorf("%s: %w", path, err)
		}
	}
	for _, entrypoint := range runtimeEntrypoints {
		if err := addReadinessOperationTarget(operationIDs, entrypoint.LocalID); err != nil {
			return nil, fmt.Errorf("%s: %w", path, err)
		}
	}
	seenCases := make(map[string]struct{}, len(node.Content))
	result := make([]ast.ReadinessCaseContract, 0, len(node.Content))
	for index, item := range node.Content {
		context := fmt.Sprintf("readiness_cases[%d]", index)
		mapping, mappingErr := readinessMapping(path, context, item)
		if mappingErr != nil {
			return nil, mappingErr
		}
		if unknownErr := rejectUnknownReadinessFields(
			path, context, mapping,
			stringSet("case_id", "spec_ref", "producer", "layer", "target", "runner_source_path", "executions"),
		); unknownErr != nil {
			return nil, unknownErr
		}

		caseID, scalarErr := requiredReadinessScalar(path, context, mapping, "case_id")
		if scalarErr != nil {
			return nil, scalarErr
		}
		if !readinessCaseIDPattern.MatchString(caseID) {
			return nil, fmt.Errorf("%s: %s.case_id %q is not canonical", path, context, caseID)
		}
		if _, duplicate := seenCases[caseID]; duplicate {
			return nil, fmt.Errorf("%s: duplicate readiness case_id %q", path, caseID)
		}
		seenCases[caseID] = struct{}{}

		specRef, scalarErr := requiredReadinessScalar(path, context, mapping, "spec_ref")
		if scalarErr != nil {
			return nil, scalarErr
		}
		if !readinessSpecRefPattern.MatchString(specRef) {
			return nil, fmt.Errorf(
				"%s: %s.spec_ref %q must name a feature-tree spec.md acceptance anchor",
				path, context, specRef,
			)
		}
		if strings.TrimSpace(repoRoot) != "" {
			if specErr := validateReadinessSpecRef(repoRoot, specRef); specErr != nil {
				return nil, fmt.Errorf("%s: %s.spec_ref: %w", path, context, specErr)
			}
		}

		producerValue, scalarErr := requiredReadinessScalar(
			path, context, mapping, "producer",
		)
		if scalarErr != nil {
			return nil, scalarErr
		}
		producer := ast.ReadinessProducer(producerValue)
		if !validReadinessProducer(producer) {
			return nil, fmt.Errorf(
				"%s: %s.producer %q is unknown", path, context, producerValue,
			)
		}

		layerValue, scalarErr := requiredReadinessScalar(path, context, mapping, "layer")
		if scalarErr != nil {
			return nil, scalarErr
		}
		layer := ast.ReadinessLayer(layerValue)
		if !validReadinessLayer(layer) {
			return nil, fmt.Errorf("%s: %s.layer %q is unknown", path, context, layerValue)
		}
		if !readinessProducerOwnsLayer(producer, layer) {
			return nil, fmt.Errorf(
				"%s: %s producer %q cannot own layer %q",
				path, context, producerValue, layerValue,
			)
		}
		target, targetErr := parseReadinessTarget(
			path, context+".target", mapping["target"], object, operationIDs,
		)
		if targetErr != nil {
			return nil, targetErr
		}
		if !readinessResponsibilityOwnsTarget(producer, layer, target.Kind) {
			return nil, fmt.Errorf(
				"%s: %s producer %q layer %q cannot own target kind %q",
				path, context, producer, layer, target.Kind,
			)
		}
		runnerSourcePath, scalarErr := requiredReadinessScalar(
			path, context, mapping, "runner_source_path",
		)
		if scalarErr != nil {
			return nil, scalarErr
		}
		if runnerErr := validateReadinessRunnerSource(
			repoRoot, path, runnerSourcePath, object, producer, layer, specRef, caseID,
			contractView,
		); runnerErr != nil {
			return nil, fmt.Errorf("%s: %s.runner_source_path: %w", path, context, runnerErr)
		}
		executions, executionsErr := parseReadinessExecutions(
			path, context+".executions", mapping["executions"],
		)
		if executionsErr != nil {
			return nil, executionsErr
		}

		result = append(result, ast.ReadinessCaseContract{
			ObjectID:         object.ID,
			SpecRef:          specRef,
			CaseID:           caseID,
			Producer:         producer,
			Layer:            layer,
			Target:           target,
			RunnerSourcePath: runnerSourcePath,
			Executions:       executions,
			SourcePath:       relativePath(metadataDir, path),
		})
	}
	return result, nil
}

func validateReadinessRunnerSource(
	repoRoot,
	contractPath,
	runnerSourcePath string,
	object ast.Object,
	producer ast.ReadinessProducer,
	layer ast.ReadinessLayer,
	specRef,
	caseID string,
	contractView *contractViewProvenance,
) error {
	if runnerSourcePath == "" || strings.Contains(runnerSourcePath, "\\") ||
		filepath.IsAbs(runnerSourcePath) {
		return fmt.Errorf("runner path must be a repository-relative canonical path")
	}
	parts := strings.Split(runnerSourcePath, "/")
	for _, part := range parts {
		if part == "" || part == "." || part == ".." {
			return fmt.Errorf("runner path contains an invalid component")
		}
	}

	resolvedContractPath := ""
	var err error
	if contractView != nil {
		canonicalSource, provenanceErr := contractView.canonicalSourceFor(contractPath)
		if provenanceErr != nil {
			return provenanceErr
		}
		if !isCanonicalObjectLocalOperationsSource(canonicalSource) {
			return fmt.Errorf(
				"owning operations provenance is not a canonical object-local Cloud contract: %s",
				canonicalSource,
			)
		}
		resolvedContractPath, err = filepath.EvalSymlinks(filepath.Join(
			contractView.repositoryRoot,
			filepath.FromSlash(canonicalSource),
		))
		if err != nil {
			return fmt.Errorf("resolve canonical owning operations source: %w", err)
		}
		if strings.TrimSpace(repoRoot) == "" {
			repoRoot = contractView.repositoryRoot
		} else if !samePhysicalPath(repoRoot, contractView.repositoryRoot) {
			return fmt.Errorf("repository root does not match contract view provenance")
		}
	} else {
		resolvedContractPath, err = filepath.EvalSymlinks(contractPath)
		if err != nil {
			return fmt.Errorf("resolve owning operations source: %w", err)
		}
		if strings.TrimSpace(repoRoot) == "" {
			repoRoot, err = inferReadinessRepositoryRoot(resolvedContractPath)
			if err != nil {
				return err
			}
		}
	}
	resolvedRoot, err := filepath.EvalSymlinks(repoRoot)
	if err != nil {
		return fmt.Errorf("resolve repository root: %w", err)
	}
	contractRelative, err := filepath.Rel(resolvedRoot, resolvedContractPath)
	if err != nil || contractRelative == ".." || strings.HasPrefix(contractRelative, ".."+string(filepath.Separator)) {
		return fmt.Errorf("owning operations source is outside the repository root")
	}
	contractParts := strings.Split(filepath.ToSlash(contractRelative), "/")
	contractsIndex := -1
	for index, part := range contractParts {
		if part == "contracts" {
			contractsIndex = index
			break
		}
	}
	if contractsIndex < 3 || len(contractParts) < contractsIndex+4 ||
		contractParts[len(contractParts)-1] != "operations.yaml" {
		return fmt.Errorf("owning operations source is not an object-local Cloud contract")
	}
	contextName := contractParts[len(contractParts)-3]
	objectName := contractParts[len(contractParts)-2]
	objectIDSegment := strings.TrimPrefix(object.ID, object.Domain+".")
	if objectIDSegment == object.ID || objectIDSegment != objectName {
		return fmt.Errorf("owning operations path does not match object %q", object.ID)
	}

	prefixMatches := func(prefix []string) bool {
		if len(parts) < len(prefix)+1 {
			return false
		}
		for index, want := range prefix {
			if parts[index] != want {
				return false
			}
		}
		return true
	}
	canonical := false
	switch producer {
	case ast.ReadinessProducerService:
		cloudRoot := append([]string(nil), contractParts[:contractsIndex]...)
		canonical = (layer == ast.ReadinessLayerLocalContract ||
			layer == ast.ReadinessLayerAPIIntegration) &&
			prefixMatches(append(cloudRoot, "tests", string(layer), contextName, objectName)) &&
			isCanonicalServiceTestFile(parts[len(parts)-1])
	case ast.ReadinessProducerApp:
		if layer == ast.ReadinessLayerUserAcceptance && len(parts) >= 6 &&
			prefixMatches([]string{"quwoquan_app", "test", "user_acceptance", "journeys"}) {
			canonical = strings.HasSuffix(parts[len(parts)-1], "_test.dart")
		} else {
			cloudRoot := contractParts[:contractsIndex]
			serviceSegment := appServiceSegment(
				filepath.FromSlash(strings.Join(cloudRoot, "/")),
			)
			canonical = (layer == ast.ReadinessLayerLocalContract ||
				layer == ast.ReadinessLayerAPIIntegration ||
				layer == ast.ReadinessLayerUserAcceptance) &&
				prefixMatches([]string{
					"quwoquan_app", "test", string(layer), "service", serviceSegment,
					contextName, objectName,
				}) && strings.HasSuffix(parts[len(parts)-1], "_test.dart")
		}
	case ast.ReadinessProducerOps:
		// 跨环境验收脚本的唯一物理位置是
		// quwoquan_ops/tests/acceptance/user_acceptance/service_ops/<service>
		// （仓库根 AGENTS.md 治理规则）；conformance 控制面脚本不带 _test 后缀。
		serviceSegment := contractParts[contractsIndex-1]
		canonical = (layer == ast.ReadinessLayerEnvironmentAcceptance ||
			layer == ast.ReadinessLayerRollback || layer == ast.ReadinessLayerReplay) &&
			prefixMatches([]string{
				"quwoquan_ops", "tests", "acceptance", "user_acceptance", "service_ops", serviceSegment,
			}) && strings.HasSuffix(parts[len(parts)-1], ".py")
	}
	if !canonical {
		return fmt.Errorf("runner path is not canonical for producer %q, layer %q and object %q", producer, layer, object.ID)
	}

	resolved := filepath.Join(repoRoot, filepath.FromSlash(runnerSourcePath))
	resolvedTarget, err := filepath.EvalSymlinks(resolved)
	if err != nil {
		return fmt.Errorf("runner file is unavailable: %w", err)
	}
	contained, err := filepath.Rel(resolvedRoot, resolvedTarget)
	if err != nil || contained == ".." || strings.HasPrefix(contained, ".."+string(filepath.Separator)) {
		return fmt.Errorf("runner file resolves outside the repository root")
	}
	info, err := os.Lstat(resolved)
	if err != nil {
		return fmt.Errorf("runner file is unavailable: %w", err)
	}
	if !info.Mode().IsRegular() {
		return fmt.Errorf("runner must be a regular file, not a symlink or directory")
	}
	if info.Size() > 8<<20 {
		return fmt.Errorf("runner file exceeds the 8 MiB contract-source limit")
	}
	content, err := os.ReadFile(resolved)
	if err != nil {
		return fmt.Errorf("read runner file: %w", err)
	}
	if !hasReadinessSourceMarker(string(content), "spec_ref", specRef) {
		return fmt.Errorf("runner does not declare exact spec_ref %q", specRef)
	}
	if !hasReadinessSourceMarker(string(content), "readiness_case", caseID) {
		return fmt.Errorf("runner does not declare exact readiness_case %q", caseID)
	}
	return nil
}

func isCanonicalObjectLocalOperationsSource(path string) bool {
	parts := strings.Split(path, "/")
	return len(parts) == 7 &&
		parts[0] == "quwoquan_service" &&
		(parts[1] == "services" || parts[1] == "control-plane") &&
		parts[2] != "" && parts[3] == "contracts" &&
		parts[4] != "" && parts[5] != "" && parts[6] == "operations.yaml"
}

func samePhysicalPath(left, right string) bool {
	resolvedLeft, leftErr := filepath.EvalSymlinks(left)
	resolvedRight, rightErr := filepath.EvalSymlinks(right)
	return leftErr == nil && rightErr == nil && filepath.Clean(resolvedLeft) == filepath.Clean(resolvedRight)
}

func isCanonicalServiceTestFile(name string) bool {
	return strings.HasSuffix(name, "_test.go") || strings.HasSuffix(name, "_test.py")
}

// inferReadinessRepositoryRoot keeps YAML-only loads honest without turning on
// physical evidence derivation. Contract views are symlinks to the owning
// service/control-plane source, so the canonical repository root can be
// recovered from that resolved source solely for runner/spec provenance.
func inferReadinessRepositoryRoot(resolvedContractPath string) (string, error) {
	absolute, err := filepath.Abs(resolvedContractPath)
	if err != nil {
		return "", fmt.Errorf("resolve owning operations absolute path: %w", err)
	}
	parts := strings.Split(filepath.ToSlash(filepath.Clean(absolute)), "/")
	for index := 0; index+2 < len(parts); index++ {
		if parts[index] != "quwoquan_service" ||
			(parts[index+1] != "services" && parts[index+1] != "control-plane") {
			continue
		}
		root := filepath.FromSlash(strings.Join(parts[:index], "/"))
		if root == "" {
			root = string(filepath.Separator)
		}
		return filepath.Clean(root), nil
	}
	return "", fmt.Errorf(
		"repository root is required to verify the authored runner: owning operations source is not under quwoquan_service/services or quwoquan_service/control-plane",
	)
}

func hasReadinessSourceMarker(content, key, value string) bool {
	want := key + ": " + value
	for _, line := range strings.Split(content, "\n") {
		line = strings.TrimSpace(line)
		switch {
		case strings.HasPrefix(line, "//"):
			line = strings.TrimSpace(strings.TrimPrefix(line, "//"))
		case strings.HasPrefix(line, "#"):
			line = strings.TrimSpace(strings.TrimPrefix(line, "#"))
		default:
			continue
		}
		if line == want {
			return true
		}
	}
	return false
}

func addReadinessOperationTarget(operationIDs map[string]struct{}, localID string) error {
	if _, duplicate := operationIDs[localID]; duplicate {
		return fmt.Errorf(
			"readiness operation target %q is declared more than once across api_routes and runtime_entrypoints",
			localID,
		)
	}
	operationIDs[localID] = struct{}{}
	return nil
}

func parseReadinessTarget(
	path,
	context string,
	node *yaml.Node,
	object ast.Object,
	operationIDs map[string]struct{},
) (ast.ReadinessCaseTarget, error) {
	mapping, err := readinessMapping(path, context, node)
	if err != nil {
		return ast.ReadinessCaseTarget{}, err
	}
	if err := rejectUnknownReadinessFields(
		path, context, mapping, stringSet("kind", "id"),
	); err != nil {
		return ast.ReadinessCaseTarget{}, err
	}
	kindValue, err := requiredReadinessScalar(path, context, mapping, "kind")
	if err != nil {
		return ast.ReadinessCaseTarget{}, err
	}
	targetID, err := requiredReadinessScalar(path, context, mapping, "id")
	if err != nil {
		return ast.ReadinessCaseTarget{}, err
	}

	kind := ast.ReadinessTargetKind(kindValue)
	switch kind {
	case ast.ReadinessTargetOperation:
		prefix := object.ID + "."
		localID := targetID
		if strings.Contains(targetID, ".") {
			if !strings.HasPrefix(targetID, prefix) {
				return ast.ReadinessCaseTarget{}, fmt.Errorf(
					"%s: %s.id %q is not owned by %s",
					path, context, targetID, object.ID,
				)
			}
			localID = strings.TrimPrefix(targetID, prefix)
		}
		if !readinessOperationIDPattern.MatchString(localID) {
			return ast.ReadinessCaseTarget{}, fmt.Errorf(
				"%s: %s.id %q is not a canonical operation ID", path, context, targetID,
			)
		}
		if _, exists := operationIDs[localID]; !exists {
			return ast.ReadinessCaseTarget{}, fmt.Errorf(
				"%s: %s.id %q is not declared by this object's api_routes or runtime_entrypoints",
				path, context, targetID,
			)
		}
		targetID = prefix + localID
	case ast.ReadinessTargetObject:
		if targetID != object.ID {
			return ast.ReadinessCaseTarget{}, fmt.Errorf(
				"%s: %s.id must equal owning object %q", path, context, object.ID,
			)
		}
	case ast.ReadinessTargetPage:
		if !readinessPageIDPattern.MatchString(targetID) {
			return ast.ReadinessCaseTarget{}, fmt.Errorf(
				"%s: %s.id %q is not a canonical page ID", path, context, targetID,
			)
		}
	default:
		return ast.ReadinessCaseTarget{}, fmt.Errorf(
			"%s: %s.kind %q is unknown", path, context, kindValue,
		)
	}
	return ast.ReadinessCaseTarget{Kind: kind, ID: targetID}, nil
}

func parseReadinessExecutions(
	path,
	context string,
	node *yaml.Node,
) ([]ast.ReadinessExecutionRequirement, error) {
	if node == nil || node.Kind != yaml.SequenceNode || len(node.Content) == 0 {
		return nil, fmt.Errorf("%s: %s must be a non-empty sequence", path, context)
	}
	result := make([]ast.ReadinessExecutionRequirement, 0, len(node.Content))
	seen := make(map[string]struct{}, len(node.Content))
	for index, item := range node.Content {
		itemContext := fmt.Sprintf("%s[%d]", context, index)
		mapping, err := readinessMapping(path, itemContext, item)
		if err != nil {
			return nil, err
		}
		if err := rejectUnknownReadinessFields(
			path, itemContext, mapping,
			stringSet("env", "platform", "device", "provider", "digest_binding"),
		); err != nil {
			return nil, err
		}
		environment, err := requiredReadinessScalar(path, itemContext, mapping, "env")
		if err != nil {
			return nil, err
		}
		if !validReadinessEnvironment(environment) {
			return nil, fmt.Errorf("%s: %s.env %q is unknown", path, itemContext, environment)
		}
		platform, err := requiredReadinessScalar(path, itemContext, mapping, "platform")
		if err != nil {
			return nil, err
		}
		device, err := requiredReadinessScalar(path, itemContext, mapping, "device")
		if err != nil {
			return nil, err
		}
		provider, err := requiredReadinessScalar(path, itemContext, mapping, "provider")
		if err != nil {
			return nil, err
		}
		for field, value := range map[string]string{
			"platform": platform,
			"device":   device,
			"provider": provider,
		} {
			if !validReadinessIdentity(value) {
				return nil, fmt.Errorf(
					"%s: %s.%s must be a non-secret identity, never an endpoint",
					path, itemContext, field,
				)
			}
		}
		digestValue, err := requiredReadinessScalar(
			path, itemContext, mapping, "digest_binding",
		)
		if err != nil {
			return nil, err
		}
		digestBinding := ast.ReadinessDigestBinding(digestValue)
		if !validReadinessDigestBinding(digestBinding) {
			return nil, fmt.Errorf(
				"%s: %s.digest_binding %q is unknown", path, itemContext, digestValue,
			)
		}
		if environment == "prod" && digestBinding != ast.ReadinessDigestRelease {
			return nil, fmt.Errorf(
				"%s: %s Prod execution must bind release", path, itemContext,
			)
		}

		execution := ast.ReadinessExecutionRequirement{
			Environment:   environment,
			Platform:      platform,
			DeviceClass:   device,
			Provider:      provider,
			DigestBinding: digestBinding,
		}
		identity := strings.Join(
			[]string{environment, platform, device, provider, digestValue}, "\x00",
		)
		if _, duplicate := seen[identity]; duplicate {
			return nil, fmt.Errorf("%s: duplicate execution requirement in %s", path, context)
		}
		seen[identity] = struct{}{}
		result = append(result, execution)
	}
	return result, nil
}

func readinessMapping(path, context string, node *yaml.Node) (map[string]*yaml.Node, error) {
	if node == nil {
		return nil, fmt.Errorf("%s: %s is required", path, context)
	}
	mapping, err := mappingFromNode(node)
	if err != nil {
		return nil, fmt.Errorf("%s: %s: %w", path, context, err)
	}
	return mapping, nil
}

func requiredReadinessScalar(
	path,
	context string,
	mapping map[string]*yaml.Node,
	field string,
) (string, error) {
	node := mapping[field]
	if node == nil || node.Kind != yaml.ScalarNode || node.Tag != "!!str" {
		return "", fmt.Errorf("%s: %s.%s must be a non-empty string", path, context, field)
	}
	value := strings.TrimSpace(node.Value)
	if value == "" {
		return "", fmt.Errorf("%s: %s.%s must be a non-empty string", path, context, field)
	}
	return value, nil
}

func rejectUnknownReadinessFields(
	path,
	context string,
	mapping map[string]*yaml.Node,
	allowed map[string]struct{},
) error {
	unknown := make([]string, 0)
	for key := range mapping {
		if _, exists := allowed[key]; !exists {
			unknown = append(unknown, key)
		}
	}
	if len(unknown) == 0 {
		return nil
	}
	sort.Strings(unknown)
	return fmt.Errorf(
		"%s: %s has unknown fields: %s", path, context, strings.Join(unknown, ", "),
	)
}

func validateReadinessSpecRef(repoRoot, specRef string) error {
	match := readinessSpecRefPattern.FindStringSubmatch(specRef)
	if len(match) != 3 {
		return fmt.Errorf("%q is not a canonical acceptance reference", specRef)
	}

	absoluteRoot, err := filepath.Abs(repoRoot)
	if err != nil {
		return fmt.Errorf("resolve repo root: %w", err)
	}
	featureTreeRoot := filepath.Join(absoluteRoot, "specs", "feature-tree")
	target := filepath.Join(absoluteRoot, filepath.FromSlash(match[1]))
	if err := requirePathWithin(featureTreeRoot, target); err != nil {
		return fmt.Errorf("escapes feature tree: %s", specRef)
	}
	if info, statErr := os.Stat(target); statErr != nil {
		if os.IsNotExist(statErr) {
			return fmt.Errorf("target does not exist: %s", specRef)
		}
		return fmt.Errorf("stat target: %w", statErr)
	} else if !info.Mode().IsRegular() {
		return fmt.Errorf("target is not a regular file: %s", specRef)
	}

	resolvedRoot, err := filepath.EvalSymlinks(featureTreeRoot)
	if err != nil {
		return fmt.Errorf("resolve feature tree: %w", err)
	}
	resolvedTarget, err := filepath.EvalSymlinks(target)
	if err != nil {
		return fmt.Errorf("resolve target: %w", err)
	}
	if err := requirePathWithin(resolvedRoot, resolvedTarget); err != nil {
		return fmt.Errorf("target resolves outside feature tree: %s", specRef)
	}

	data, err := os.ReadFile(resolvedTarget)
	if err != nil {
		return fmt.Errorf("read target: %w", err)
	}
	anchor := `<a id="` + match[2] + `"></a>`
	if !strings.Contains(strings.ToLower(string(data)), anchor) {
		return fmt.Errorf("acceptance anchor does not exist: %s", specRef)
	}
	return nil
}

func requirePathWithin(root, target string) error {
	relative, err := filepath.Rel(filepath.Clean(root), filepath.Clean(target))
	if err != nil {
		return err
	}
	if relative == ".." || strings.HasPrefix(relative, ".."+string(filepath.Separator)) {
		return fmt.Errorf("path escapes root")
	}
	return nil
}

func validReadinessLayer(value ast.ReadinessLayer) bool {
	switch value {
	case ast.ReadinessLayerLocalContract,
		ast.ReadinessLayerAPIIntegration,
		ast.ReadinessLayerUserAcceptance,
		ast.ReadinessLayerEnvironmentAcceptance,
		ast.ReadinessLayerRollback,
		ast.ReadinessLayerReplay:
		return true
	default:
		return false
	}
}

func validReadinessProducer(value ast.ReadinessProducer) bool {
	switch value {
	case ast.ReadinessProducerService,
		ast.ReadinessProducerApp,
		ast.ReadinessProducerOps:
		return true
	default:
		return false
	}
}

func readinessProducerOwnsLayer(
	producer ast.ReadinessProducer,
	layer ast.ReadinessLayer,
) bool {
	switch producer {
	case ast.ReadinessProducerService:
		return layer == ast.ReadinessLayerLocalContract ||
			layer == ast.ReadinessLayerAPIIntegration
	case ast.ReadinessProducerApp:
		return layer == ast.ReadinessLayerLocalContract ||
			layer == ast.ReadinessLayerAPIIntegration ||
			layer == ast.ReadinessLayerUserAcceptance
	case ast.ReadinessProducerOps:
		return layer == ast.ReadinessLayerEnvironmentAcceptance ||
			layer == ast.ReadinessLayerRollback ||
			layer == ast.ReadinessLayerReplay
	default:
		return false
	}
}

func readinessResponsibilityOwnsTarget(
	producer ast.ReadinessProducer,
	layer ast.ReadinessLayer,
	target ast.ReadinessTargetKind,
) bool {
	switch producer {
	case ast.ReadinessProducerService:
		return (layer == ast.ReadinessLayerLocalContract ||
			layer == ast.ReadinessLayerAPIIntegration) &&
			(target == ast.ReadinessTargetOperation || target == ast.ReadinessTargetObject)
	case ast.ReadinessProducerApp:
		if layer == ast.ReadinessLayerUserAcceptance {
			return target == ast.ReadinessTargetPage
		}
		return (layer == ast.ReadinessLayerLocalContract ||
			layer == ast.ReadinessLayerAPIIntegration) &&
			target == ast.ReadinessTargetOperation
	case ast.ReadinessProducerOps:
		return (layer == ast.ReadinessLayerEnvironmentAcceptance ||
			layer == ast.ReadinessLayerRollback ||
			layer == ast.ReadinessLayerReplay) &&
			target == ast.ReadinessTargetObject
	default:
		return false
	}
}

func validReadinessEnvironment(value string) bool {
	switch value {
	case "alpha", "beta", "gamma", "prod":
		return true
	default:
		return false
	}
}

func validReadinessDigestBinding(value ast.ReadinessDigestBinding) bool {
	switch value {
	case ast.ReadinessDigestCandidate, ast.ReadinessDigestRelease, ast.ReadinessDigestEither:
		return true
	default:
		return false
	}
}

func validReadinessIdentity(value string) bool {
	if len(value) == 0 || len(value) > 128 || strings.Contains(value, "://") {
		return false
	}
	for index, current := range value {
		if current >= 'a' && current <= 'z' ||
			current >= 'A' && current <= 'Z' ||
			current >= '0' && current <= '9' {
			continue
		}
		if index > 0 && (current == '.' || current == '_' || current == '-' || current == '/') {
			continue
		}
		return false
	}
	return true
}
