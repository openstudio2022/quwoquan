package readiness

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"io"
	"sort"
	"strings"

	"quwoquan_service/internal/metadata/graph"
)

type evaluatedResult struct {
	result ReadinessCaseResult
	valid  bool
}

// CurrentSnapshotProvider is the trust boundary for identities that cannot be
// derived from ContractGraph bytes: the checked-out commit and the current
// environment configuration/candidate/release snapshot. Bundle producers do
// not provide this authority.
type CurrentSnapshotProvider interface {
	CurrentSnapshot(context.Context, *graph.ContractGraph) (EvaluationContext, error)
}

// Evaluator is configured only with trusted runtime authorities. Canonical
// case policy is always read from the current ContractGraph; callers cannot
// smuggle a hand-authored policy alongside a result bundle.
type Evaluator struct {
	snapshots CurrentSnapshotProvider
	receipts  ReceiptResolver
	schemas   *WireSchemas
}

func NewEvaluator(
	snapshots CurrentSnapshotProvider,
	receipts ReceiptResolver,
	schemas ...*WireSchemas,
) *Evaluator {
	result := &Evaluator{
		snapshots: snapshots,
		receipts:  receipts,
	}
	if len(schemas) == 1 {
		result.schemas = schemas[0]
	}
	return result
}

// EvaluateJSON is the untrusted wire entrypoint: unknown fields and trailing
// documents are rejected before the typed, fail-closed evaluation.
func (e *Evaluator) EvaluateJSON(
	ctx context.Context,
	current *graph.ContractGraph,
	reader io.Reader,
) ClosureResult {
	if e == nil || e.schemas == nil {
		return ClosureResult{Violations: []Violation{violation(
			"READINESS.BUNDLE.SCHEMA_AUTHORITY_MISSING", "", "",
			"canonical readiness wire schemas are required",
		)}}
	}
	bundle, err := e.schemas.DecodeBundle(reader)
	if err != nil {
		return ClosureResult{
			Violations: []Violation{violation(
				"READINESS.BUNDLE.DECODE_FAILED", "", "", err.Error(),
			)},
		}
	}
	return e.Evaluate(ctx, current, bundle)
}

func (e *Evaluator) Evaluate(
	ctx context.Context,
	current *graph.ContractGraph,
	bundle ReadinessResultBundle,
) ClosureResult {
	closure := ClosureResult{}
	if current == nil {
		closure.Violations = append(closure.Violations, violation(
			"READINESS.GRAPH.MISSING", "", "", "current ContractGraph is required",
		))
		return closure
	}
	evaluation := EvaluationContext{}
	if e == nil || e.snapshots == nil {
		closure.Violations = append(closure.Violations, violation(
			"READINESS.SNAPSHOT.PROVIDER_MISSING", "", "",
			"trusted current snapshot provider is required",
		))
	} else {
		resolved, err := e.snapshots.CurrentSnapshot(ctx, current)
		if err != nil {
			closure.Violations = append(closure.Violations, violation(
				"READINESS.SNAPSHOT.UNAVAILABLE", "", "",
				"trusted current snapshot cannot be resolved",
			))
		} else {
			evaluation = resolved
		}
	}
	caseContracts := current.ReadinessCases
	var receipts ReceiptResolver
	if e != nil {
		receipts = e.receipts
	}

	objects := map[string]struct{}{}
	lifecycleConsumerObjects := map[string]struct{}{}
	readinessByObject := map[string]graph.ObjectReadiness{}
	operationsByObject := map[string][]string{}
	operationOwners := map[string]string{}
	sourcePaths := map[string]struct{}{}
	operationPolicyReady := map[string]bool{}
	for _, object := range current.Objects {
		objects[object.ID] = struct{}{}
		if object.Lifecycle != nil && len(object.Lifecycle.SourceEvents) > 0 {
			lifecycleConsumerObjects[object.ID] = struct{}{}
		}
	}
	for _, readiness := range current.ObjectReadiness {
		readinessByObject[readiness.ObjectID] = readiness
	}
	for _, source := range current.Sources {
		sourcePaths[source.Path] = struct{}{}
	}
	for _, operation := range current.Operations {
		operationsByObject[operation.ObjectID] = append(
			operationsByObject[operation.ObjectID], operation.LocalID,
		)
		operationOwners[operation.ID] = operation.ObjectID
		if _, exists := operationPolicyReady[operation.ObjectID]; !exists {
			operationPolicyReady[operation.ObjectID] = true
		}
		if operation.Commercial.Status != "ready" {
			operationPolicyReady[operation.ObjectID] = false
		}
	}
	for _, entrypoint := range current.RuntimeEntrypoints {
		// Event consumers are object lifecycle responsibilities. Even when a
		// no-HTTP object retains its one production runtime entrypoint, dynamic
		// evidence must target the canonical object rather than inventing an
		// operation identity for the internal consumer.
		if lifecycleRuntimeKind(entrypoint.RuntimeKind) {
			continue
		}
		operationsByObject[entrypoint.ObjectID] = append(
			operationsByObject[entrypoint.ObjectID], entrypoint.LocalID,
		)
		operationOwners[entrypoint.ID] = entrypoint.ObjectID
	}

	globalContextValid := validateEvaluationContext(evaluation, &closure.Violations)
	pageTargets, pageTargetErr := currentPageTargets(current)
	if pageTargetErr != nil {
		closure.Violations = append(closure.Violations, violation(
			"READINESS.GRAPH.PAGE_TARGETS_INVALID", "", "", pageTargetErr.Error(),
		))
		globalContextValid = false
	}
	currentSourceHash, sourceHashErr := ContractGraphSourceHash(current)
	if sourceHashErr != nil {
		closure.Violations = append(closure.Violations, violation(
			"READINESS.GRAPH.SOURCE_IDENTITY_INVALID", "", "", sourceHashErr.Error(),
		))
		globalContextValid = false
	}
	if bundle.GeneratedAt.IsZero() {
		closure.Violations = append(closure.Violations, violation(
			"READINESS.BUNDLE.GENERATED_AT_MISSING", "", "",
			"generatedAt is required as the bundle identity",
		))
		globalContextValid = false
	}

	contractsByKey := map[string]ReadinessCaseContract{}
	contractsByObject := map[string][]ReadinessCaseContract{}
	contractSlots := map[string]ExecutionRequirement{}
	invalidObjects := map[string]struct{}{}
	for _, contract := range caseContracts {
		valid := validateCaseContract(
			contract, objects, operationOwners, lifecycleConsumerObjects, pageTargets, sourcePaths,
			&closure.Violations,
		)
		key := caseContractKey(
			contract.ObjectID, contract.SpecRef, contract.CaseID,
			contract.Producer, contract.Layer, contract.Target,
		)
		if _, duplicate := contractsByKey[key]; duplicate {
			closure.Violations = append(closure.Violations, violation(
				"READINESS.CASE_CONTRACT.DUPLICATE",
				contract.ObjectID, contract.CaseID, "duplicate case contract identity",
			))
			valid = false
		}
		contractsByKey[key] = contract
		contractsByObject[contract.ObjectID] = append(
			contractsByObject[contract.ObjectID], contract,
		)
		seenExecutions := map[string]struct{}{}
		for _, execution := range contract.Executions {
			slot := resultSlotKey(key, execution)
			if _, duplicate := seenExecutions[slot]; duplicate {
				closure.Violations = append(closure.Violations, violation(
					"READINESS.CASE_CONTRACT.EXECUTION_DUPLICATE",
					contract.ObjectID, contract.CaseID,
					"duplicate execution requirement",
				))
				valid = false
			}
			seenExecutions[slot] = struct{}{}
			contractSlots[slot] = execution
		}
		if !valid {
			invalidObjects[contract.ObjectID] = struct{}{}
		}
	}
	for objectID := range validateCaseResponsibilities(
		current, caseContracts, pageTargets, &closure.Violations,
	) {
		invalidObjects[objectID] = struct{}{}
	}

	grouped := map[string][]evaluatedResult{}
	for _, result := range bundle.Results {
		key := caseContractKey(
			result.ObjectID, result.SpecRef, result.CaseID,
			result.Producer, result.Layer, result.Target,
		)
		contract, known := contractsByKey[key]
		if !known {
			closure.Violations = append(closure.Violations, violation(
				"READINESS.RESULT.UNKNOWN_CASE", result.ObjectID, result.CaseID,
				"result does not match a canonical case contract",
			))
			invalidObjects[result.ObjectID] = struct{}{}
			continue
		}
		execution := ExecutionRequirement{
			Environment: result.Environment,
			Platform:    result.Platform,
			DeviceClass: result.DeviceClass,
			Provider:    result.Provider,
		}
		slot := resultSlotKey(key, execution)
		requirement, required := contractSlots[slot]
		valid := required
		if !required {
			closure.Violations = append(closure.Violations, violation(
				"READINESS.RESULT.EXECUTION_MISMATCH", result.ObjectID, result.CaseID,
				"environment/platform/device/provider do not match the case contract",
			))
		}
		if !validateResult(
			ctx, result, contract, requirement, evaluation, currentSourceHash, receipts,
			&closure.Violations,
		) {
			valid = false
		}
		grouped[slot] = append(grouped[slot], evaluatedResult{result: result, valid: valid})
	}

	satisfied := map[string]struct{}{}
	for slot, results := range grouped {
		if len(results) != 1 {
			first := results[0].result
			closure.Violations = append(closure.Violations, violation(
				"READINESS.RESULT.DUPLICATE", first.ObjectID, first.CaseID,
				"duplicate or conflicting results for one execution requirement",
			))
			invalidObjects[first.ObjectID] = struct{}{}
			continue
		}
		if results[0].valid {
			satisfied[slot] = struct{}{}
		} else {
			invalidObjects[results[0].result.ObjectID] = struct{}{}
		}
	}

	objectIDs := make([]string, 0, len(objects))
	for objectID := range objects {
		objectIDs = append(objectIDs, objectID)
	}
	sort.Strings(objectIDs)
	closure.CommercialReady = globalContextValid && len(closure.Violations) == 0
	for _, objectID := range objectIDs {
		static := readinessByObject[objectID]
		missing := map[string]struct{}{}
		if !static.Implemented {
			missing["commercial.implemented"] = struct{}{}
		}
		if ready, exists := operationPolicyReady[objectID]; exists && !ready {
			for _, localID := range operationsByObject[objectID] {
				for _, operation := range current.Operations {
					if operation.ObjectID == objectID && operation.LocalID == localID &&
						operation.Commercial.Status != "ready" {
						missing["commercial.operation."+localID] = struct{}{}
					}
				}
			}
		}
		contracts := contractsByObject[objectID]
		if len(contracts) == 0 {
			missing["commercial.case_contract"] = struct{}{}
		}
		for _, contract := range contracts {
			key := caseContractKey(
				contract.ObjectID, contract.SpecRef, contract.CaseID,
				contract.Producer, contract.Layer, contract.Target,
			)
			for _, execution := range contract.Executions {
				if _, ok := satisfied[resultSlotKey(key, execution)]; !ok {
					missing["commercial.case."+contract.CaseID] = struct{}{}
				}
			}
		}
		if !globalContextValid {
			missing["commercial.evaluation_context"] = struct{}{}
		}
		if _, invalid := invalidObjects[objectID]; invalid {
			missing["commercial.result_invalid"] = struct{}{}
		}
		missingList := keys(missing)
		objectReady := static.Implemented && len(missingList) == 0
		closure.Objects = append(closure.Objects, ObjectClosure{
			ObjectID:        objectID,
			Implemented:     static.Implemented,
			CommercialReady: objectReady,
			Missing:         missingList,
		})
		closure.CommercialReady = closure.CommercialReady && objectReady
	}
	sortViolations(closure.Violations)
	return closure
}

func validateEvaluationContext(
	value EvaluationContext,
	violations *[]Violation,
) bool {
	valid := true
	for name, item := range map[string]string{
		"candidateDigest": value.CandidateDigest,
		"releaseDigest":   value.ReleaseDigest,
	} {
		if !isDigest(item) {
			*violations = append(*violations, violation(
				"READINESS.CONTEXT.INVALID_DIGEST", "", "", name+" must be sha256",
			))
			valid = false
		}
	}
	var candidatePackage string
	var candidateManifest string
	for _, environment := range []string{"alpha", "beta", "gamma", "prod"} {
		deployment, exists := value.Deployments[environment]
		if !exists || !validDeploymentBinding(deployment) {
			*violations = append(*violations, violation(
				"READINESS.CONTEXT.INVALID_DIGEST", "", "",
				"package-bound deployment for "+environment+" is required",
			))
			valid = false
			continue
		}
		if candidatePackage == "" {
			candidatePackage = deployment.PackageDigest
			candidateManifest = deployment.CandidateManifestSHA256
		} else if deployment.PackageDigest != candidatePackage ||
			deployment.CandidateManifestSHA256 != candidateManifest {
			*violations = append(*violations, violation(
				"READINESS.CONTEXT.CANDIDATE_PACKAGE_MISMATCH", "", "",
				"all environments must bind one candidate package and manifest",
			))
			valid = false
		}
	}
	if !isCommitSHA(value.CommitSHA) {
		*violations = append(*violations, violation(
			"READINESS.CONTEXT.INVALID_COMMIT", "", "", "commitSha must be a Git SHA",
		))
		valid = false
	}
	if len(value.Deployments) != 4 {
		*violations = append(*violations, violation(
			"READINESS.CONTEXT.DEPLOYMENT_SET_INVALID", "", "",
			"deployment snapshot must contain exactly alpha, beta, gamma and prod",
		))
		valid = false
	}
	return valid
}

func validDeploymentBinding(value DeploymentBinding) bool {
	return validNonSecretIdentity(value.DeploymentTarget) &&
		validNonSecretIdentity(value.BaselineID) &&
		isDigest(value.PackageDigest) &&
		isDigest(value.ConfigurationDigest) &&
		isSHA256(value.CandidateManifestSHA256)
}

func validateCaseContract(
	contract ReadinessCaseContract,
	objects map[string]struct{},
	operationOwners map[string]string,
	lifecycleConsumerObjects map[string]struct{},
	pageTargets pageTargetCatalog,
	sourcePaths map[string]struct{},
	violations *[]Violation,
) bool {
	valid := true
	if _, exists := objects[contract.ObjectID]; !exists {
		*violations = append(*violations, violation(
			"READINESS.CASE_CONTRACT.UNKNOWN_OBJECT", contract.ObjectID, contract.CaseID,
			"case contract object is not in ContractGraph",
		))
		valid = false
	}
	if !canonicalSpecRefPattern.MatchString(contract.SpecRef) || !validCaseID(contract.CaseID) ||
		!validProducer(contract.Producer) || !validLayer(contract.Layer) ||
		!producerOwnsLayer(contract.Producer, contract.Layer) || !validTarget(contract.Target) ||
		len(contract.Executions) == 0 || strings.TrimSpace(contract.SourcePath) == "" ||
		strings.TrimSpace(contract.RunnerSourcePath) == "" {
		*violations = append(*violations, violation(
			"READINESS.CASE_CONTRACT.INVALID", contract.ObjectID, contract.CaseID,
			"case contract identity, producer, layer, target, runner source and executions are required and producer must own the layer",
		))
		valid = false
	}
	if !validProducerRunnerSourcePath(
		contract.RunnerSourcePath, contract.ObjectID, contract.SourcePath,
		contract.Producer, contract.Layer,
	) {
		*violations = append(*violations, violation(
			"READINESS.CASE_CONTRACT.RUNNER_SOURCE_INVALID",
			contract.ObjectID, contract.CaseID,
			"authored runner source is not canonical for its producer, layer and object",
		))
		valid = false
	}
	if _, exists := sourcePaths[contract.SourcePath]; !exists {
		*violations = append(*violations, violation(
			"READINESS.CASE_CONTRACT.UNKNOWN_SOURCE", contract.ObjectID, contract.CaseID,
			"case contract sourcePath is not part of the current ContractGraph sources",
		))
		valid = false
	}
	switch contract.Target.Kind {
	case TargetOperation:
		if operationOwners[contract.Target.ID] != contract.ObjectID {
			*violations = append(*violations, violation(
				"READINESS.CASE_CONTRACT.TARGET_MISMATCH", contract.ObjectID, contract.CaseID,
				"operation target is unknown or owned by another object",
			))
			valid = false
		}
	case TargetObject:
		if contract.Target.ID != contract.ObjectID {
			*violations = append(*violations, violation(
				"READINESS.CASE_CONTRACT.TARGET_MISMATCH", contract.ObjectID, contract.CaseID,
				"object target must equal objectId",
			))
			valid = false
		}
	case TargetPage:
		page, exists := pageTargets[contract.Target.ID]
		_, participates := page.participants[contract.ObjectID]
		owns := page.physicalOwner == contract.ObjectID
		if !exists || (!participates && !owns) {
			*violations = append(*violations, violation(
				"READINESS.CASE_CONTRACT.TARGET_MISMATCH", contract.ObjectID, contract.CaseID,
				"page target is unknown and the object is neither participant nor physical owner",
			))
			valid = false
		}
	}
	switch {
	case (contract.Producer == ProducerService || contract.Producer == ProducerApp) &&
		(contract.Layer == LayerLocalContract || contract.Layer == LayerAPIIntegration):
		_, lifecycleTarget := lifecycleConsumerObjects[contract.ObjectID]
		validServiceLifecycleTarget := contract.Producer == ProducerService &&
			contract.Target.Kind == TargetObject && lifecycleTarget
		if contract.Target.Kind != TargetOperation && !validServiceLifecycleTarget {
			*violations = append(*violations, violation(
				"READINESS.CASE_CONTRACT.RESPONSIBILITY_MISMATCH", contract.ObjectID, contract.CaseID,
				"local_contract and api_integration cases must target one operation; service lifecycle consumer cases may target their owning object",
			))
			valid = false
		}
	case contract.Producer == ProducerApp && contract.Layer == LayerUserAcceptance:
		if contract.Target.Kind != TargetPage {
			*violations = append(*violations, violation(
				"READINESS.CASE_CONTRACT.RESPONSIBILITY_MISMATCH", contract.ObjectID, contract.CaseID,
				"user_acceptance cases must target one canonical page",
			))
			valid = false
		}
	case contract.Producer == ProducerOps &&
		(contract.Layer == LayerEnvironmentAcceptance ||
			contract.Layer == LayerRollback || contract.Layer == LayerReplay):
		if contract.Target.Kind != TargetObject {
			*violations = append(*violations, violation(
				"READINESS.CASE_CONTRACT.RESPONSIBILITY_MISMATCH", contract.ObjectID, contract.CaseID,
				"environment, rollback and replay cases must target their object",
			))
			valid = false
		}
	}
	for _, execution := range contract.Executions {
		if !validExecution(execution) {
			*violations = append(*violations, violation(
				"READINESS.CASE_CONTRACT.EXECUTION_INVALID", contract.ObjectID, contract.CaseID,
				"execution requirement is incomplete or invalid",
			))
			valid = false
		}
	}
	return valid
}

func validateResult(
	ctx context.Context,
	result ReadinessCaseResult,
	contract ReadinessCaseContract,
	requirement ExecutionRequirement,
	evaluation EvaluationContext,
	currentSourceHash string,
	receipts ReceiptResolver,
	violations *[]Violation,
) bool {
	valid := true
	add := func(code, message string) {
		*violations = append(*violations, violation(
			code, result.ObjectID, result.CaseID, message,
		))
		valid = false
	}
	if result.Status != StatusPassed {
		add("READINESS.RESULT.NOT_PASSED", "failed, blocked and skipped results never close readiness")
	}
	if !validStatus(result.Status) || !validProducer(result.Producer) ||
		!validLayer(result.Layer) || !producerOwnsLayer(result.Producer, result.Layer) ||
		!validTarget(result.Target) {
		add("READINESS.RESULT.INVALID_ENUM", "unknown status, producer, layer or target, or producer does not own layer")
	}
	if result.ObjectID != contract.ObjectID || result.SpecRef != contract.SpecRef ||
		result.CaseID != contract.CaseID || result.Producer != contract.Producer ||
		result.Layer != contract.Layer ||
		result.Target != contract.Target {
		add("READINESS.RESULT.IDENTITY_MISMATCH", "result identity does not match case contract")
	}
	deployment := evaluation.Deployments[result.Environment]
	if result.CommitSHA != evaluation.CommitSHA ||
		result.ContractGraphSourceHash != currentSourceHash ||
		result.DeploymentTarget != deployment.DeploymentTarget ||
		result.BaselineID != deployment.BaselineID ||
		result.PackageDigest != deployment.PackageDigest ||
		result.ConfigurationDigest != deployment.ConfigurationDigest ||
		result.CandidateManifestSHA256 != deployment.CandidateManifestSHA256 {
		add("READINESS.RESULT.STALE_IDENTITY", "commit, ContractGraph source or package-bound deployment identity is stale")
	}
	if !isCommitSHA(result.CommitSHA) || !isSHA256(result.ContractGraphSourceHash) ||
		!validNonSecretIdentity(result.DeploymentTarget) ||
		!validNonSecretIdentity(result.BaselineID) ||
		!isDigest(result.PackageDigest) || !isDigest(result.ConfigurationDigest) ||
		!isSHA256(result.CandidateManifestSHA256) || !isSHA256(result.ArtifactSHA256) {
		add("READINESS.RESULT.INVALID_DIGEST", "result identity and artifact digests must be canonical hashes")
	}
	if result.CandidateDigest != "" {
		if !isDigest(result.CandidateDigest) || result.CandidateDigest != evaluation.CandidateDigest {
			add("READINESS.RESULT.STALE_CANDIDATE", "candidateDigest does not bind the current candidate")
		}
	}
	if result.ReleaseDigest != "" {
		if !isDigest(result.ReleaseDigest) || result.ReleaseDigest != evaluation.ReleaseDigest {
			add("READINESS.RESULT.STALE_RELEASE", "releaseDigest does not bind the current release")
		}
	}
	switch requirement.DigestBinding {
	case DigestCandidate:
		if result.CandidateDigest != evaluation.CandidateDigest {
			add("READINESS.RESULT.CANDIDATE_REQUIRED", "case requires candidateDigest")
		}
	case DigestRelease:
		if result.ReleaseDigest != evaluation.ReleaseDigest {
			add("READINESS.RESULT.RELEASE_REQUIRED", "case requires releaseDigest")
		}
		if evaluation.CandidateDigest != "" && result.CandidateDigest != evaluation.CandidateDigest {
			add("READINESS.RESULT.CANDIDATE_REQUIRED", "release acceptance must also bind the shared candidate")
		}
	case DigestEither:
		if result.CandidateDigest != evaluation.CandidateDigest &&
			result.ReleaseDigest != evaluation.ReleaseDigest {
			add("READINESS.RESULT.DIGEST_REQUIRED", "case requires the current candidate or release digest")
		}
	default:
		add("READINESS.RESULT.DIGEST_POLICY_UNKNOWN", "case digest binding is unknown")
	}
	if result.Environment == "prod" && result.ReleaseDigest != evaluation.ReleaseDigest {
		add("READINESS.RESULT.PROD_RELEASE_REQUIRED", "Prod result must bind releaseDigest")
	}
	if !validNonSecretIdentity(result.RunnerIdentity) ||
		!validNonSecretIdentity(result.Platform) ||
		!validNonSecretIdentity(result.DeviceClass) ||
		!validNonSecretIdentity(result.Provider) {
		add("READINESS.RESULT.EXECUTION_IDENTITY_INVALID", "runner, platform, device and non-secret provider identities are required")
	}
	if !result.StartedAt.Before(result.CompletedAt) {
		add("READINESS.RESULT.TIME_INVALID", "startedAt must be before completedAt")
	}
	if (strings.TrimSpace(result.ArtifactPath) == "") ==
		(strings.TrimSpace(result.ReceiptRef) == "") {
		add("READINESS.RESULT.RECEIPT_REFERENCE_INVALID", "exactly one artifactPath or receiptRef is required")
	} else if (result.ArtifactPath != "" && !validRelativeArtifactPath(result.ArtifactPath)) ||
		(result.ReceiptRef != "" && !validReceiptReference(result.ReceiptRef)) {
		add("READINESS.RESULT.RECEIPT_REFERENCE_INVALID", "receipt references must be opaque identities or local artifact paths, never endpoints")
	}
	if receipts == nil {
		add("READINESS.RESULT.RECEIPT_RESOLVER_MISSING", "receipt resolver is required")
		return valid
	}
	receipt, err := receipts.Resolve(ctx, result)
	if err != nil {
		add("READINESS.RESULT.RECEIPT_UNAVAILABLE", "receipt bytes cannot be resolved")
		return valid
	}
	if len(receipt.Bytes) == 0 {
		add("READINESS.RESULT.RECEIPT_EMPTY", "receipt bytes must not be empty")
		return valid
	}
	if !receipt.Trusted {
		add("READINESS.RESULT.RECEIPT_UNTRUSTED", "receipt resolver did not verify the runner and evidence attestation")
	}
	if !receiptBindingMatchesResult(receipt.Binding, result) {
		add("READINESS.RESULT.RECEIPT_IDENTITY_MISMATCH", "receipt identity does not attest the bundle result")
	}
	if !validateRunnerProvenance(result, contract, receipt.Binding, add) {
		valid = false
	}
	digest := sha256.Sum256(receipt.Bytes)
	if hex.EncodeToString(digest[:]) != result.ArtifactSHA256 {
		add("READINESS.RESULT.ARTIFACT_DIGEST_MISMATCH", "artifactSha256 does not match receipt bytes")
	}
	return valid
}

func receiptBindingForResult(result ReadinessCaseResult) ReceiptBinding {
	binding := ReceiptBinding{
		ObjectID: result.ObjectID, SpecRef: result.SpecRef, CaseID: result.CaseID,
		Producer: result.Producer, Layer: result.Layer, Status: result.Status, Target: result.Target,
		CommitSHA:               result.CommitSHA,
		ContractGraphSourceHash: result.ContractGraphSourceHash,
		DeploymentTarget:        result.DeploymentTarget,
		BaselineID:              result.BaselineID,
		PackageDigest:           result.PackageDigest,
		ConfigurationDigest:     result.ConfigurationDigest,
		CandidateManifestSHA256: result.CandidateManifestSHA256,
		CandidateDigest:         result.CandidateDigest, ReleaseDigest: result.ReleaseDigest,
		Environment: result.Environment, Platform: result.Platform,
		DeviceClass: result.DeviceClass, Provider: result.Provider,
		StartedAt: result.StartedAt, CompletedAt: result.CompletedAt,
		RunnerIdentity: result.RunnerIdentity, FixtureFree: true, DependenciesReady: true,
		ProviderVerified: true,
	}
	if result.Layer == LayerUserAcceptance {
		parts := strings.Split(result.ObjectID, ".")
		if len(parts) == 2 {
			binding.RunnerSourcePath = strings.Join([]string{
				"quwoquan_app", "test", "user_acceptance", "service",
				parts[0] + "_service", parts[0], parts[1], "readiness_case_test.dart",
			}, "/")
		}
		binding.RemoteComposition = true
		binding.PhysicalDevice = result.DeviceClass == "physical"
	} else if parts := strings.Split(result.ObjectID, "."); len(parts) == 2 {
		switch result.Producer {
		case ProducerService:
			binding.RunnerSourcePath = strings.Join([]string{
				"quwoquan_service", "services", parts[0] + "-service", "tests",
				string(result.Layer), parts[0], parts[1], "readiness_case_test.go",
			}, "/")
		case ProducerApp:
			binding.RunnerSourcePath = strings.Join([]string{
				"quwoquan_app", "test", string(result.Layer), "service",
				parts[0] + "_service", parts[0], parts[1], "readiness_case_test.dart",
			}, "/")
		case ProducerOps:
			binding.RunnerSourcePath = strings.Join([]string{
				"quwoquan_ops", "tests", "acceptance", string(result.Layer), parts[0],
				parts[0], parts[1], "readiness_case_test.py",
			}, "/")
		}
	}
	return binding
}

func receiptBindingMatchesResult(binding ReceiptBinding, result ReadinessCaseResult) bool {
	provenance := binding
	provenance.RunnerSourcePath = ""
	provenance.RemoteComposition = false
	provenance.FixtureFree = false
	provenance.DependenciesReady = false
	provenance.ProviderVerified = false
	provenance.PhysicalDevice = false
	expected := receiptBindingForResult(result)
	expected.RunnerSourcePath = ""
	expected.RemoteComposition = false
	expected.FixtureFree = false
	expected.DependenciesReady = false
	expected.ProviderVerified = false
	expected.PhysicalDevice = false
	return provenance == expected
}

func validateRunnerProvenance(
	result ReadinessCaseResult,
	contract ReadinessCaseContract,
	binding ReceiptBinding,
	add func(code, message string),
) bool {
	valid := true
	require := func(condition bool, code, message string) {
		if condition {
			return
		}
		add(code, message)
		valid = false
	}
	require(
		binding.RunnerSourcePath == contract.RunnerSourcePath &&
			validProducerRunnerSourcePath(
				binding.RunnerSourcePath, result.ObjectID, contract.SourcePath,
				result.Producer, result.Layer,
			),
		"READINESS.RESULT.RUNNER_SOURCE_INVALID",
		"receipt runner source must exactly match the canonical case contract",
	)
	require(
		binding.ProviderVerified,
		"READINESS.RESULT.PROVIDER_UNVERIFIED",
		"Provider identity must come from verified runner evidence",
	)
	switch {
	case result.Producer == ProducerApp && result.Layer == LayerUserAcceptance:
		require(
			validUserAcceptanceSourcePath(
				binding.RunnerSourcePath, result.ObjectID, contract.SourcePath,
			),
			"READINESS.RESULT.UAT_RUNNER_SOURCE_INVALID",
			"user acceptance receipt must attest an object-shaped or journey runner source",
		)
		require(
			binding.RemoteComposition,
			"READINESS.RESULT.UAT_REMOTE_COMPOSITION_REQUIRED",
			"user acceptance receipt must attest Remote composition",
		)
		require(
			binding.FixtureFree,
			"READINESS.RESULT.UAT_FIXTURE_FORBIDDEN",
			"fixture-only user acceptance cannot close readiness",
		)
		require(
			binding.DependenciesReady,
			"READINESS.RESULT.UAT_DEPENDENCY_NOT_READY",
			"user acceptance cannot pass while required dependencies are unavailable",
		)
		require(
			result.DeviceClass == "physical" &&
				(result.Platform == "android" || result.Platform == "ios") &&
				binding.PhysicalDevice,
			"READINESS.RESULT.PHYSICAL_DEVICE_REQUIRED",
			"App user acceptance requires attested physical Android or iPhone execution",
		)
	case result.Producer == ProducerOps &&
		(result.Layer == LayerEnvironmentAcceptance ||
			result.Layer == LayerRollback || result.Layer == LayerReplay):
		require(
			binding.FixtureFree,
			"READINESS.RESULT.ENVIRONMENT_FIXTURE_FORBIDDEN",
			"environment, rollback and replay evidence must be fixture-free",
		)
		require(
			binding.DependenciesReady,
			"READINESS.RESULT.ENVIRONMENT_DEPENDENCY_NOT_READY",
			"environment, rollback and replay evidence requires ready dependencies",
		)
	}
	return valid
}

func validUserAcceptanceSourcePath(value, objectID, contractSourcePath string) bool {
	if value == "" || strings.Contains(value, "\\") || strings.HasPrefix(value, "/") {
		return false
	}
	parts := strings.Split(value, "/")
	for _, part := range parts {
		if part == "" || part == "." || part == ".." {
			return false
		}
	}
	prefix := []string{"quwoquan_app", "test", "user_acceptance"}
	if len(parts) < len(prefix)+3 {
		return false
	}
	for index, want := range prefix {
		if parts[index] != want {
			return false
		}
	}
	relative := parts[len(prefix):]
	if relative[0] == "journeys" {
		return len(relative) >= 3
	}
	objectParts := strings.Split(objectID, ".")
	contractParts := strings.Split(strings.Trim(contractSourcePath, "/"), "/")
	if len(objectParts) != 2 || len(contractParts) < 3 ||
		contractParts[len(contractParts)-1] != "operations.yaml" {
		return false
	}
	context := objectParts[0]
	if len(contractParts) >= 4 {
		context = contractParts[len(contractParts)-3]
	}
	return len(relative) >= 5 && relative[0] == "service" &&
		relative[1] != "" && relative[2] == context &&
		relative[3] == objectParts[1]
}

func validProducerRunnerSourcePath(
	value string,
	objectID string,
	contractSourcePath string,
	producer Producer,
	layer Layer,
) bool {
	if value == "" || strings.Contains(value, "\\") || strings.HasPrefix(value, "/") {
		return false
	}
	parts := strings.Split(value, "/")
	for _, part := range parts {
		if part == "" || part == "." || part == ".." {
			return false
		}
	}
	objectParts := strings.Split(objectID, ".")
	if len(objectParts) != 2 {
		return false
	}
	contractParts := strings.Split(strings.Trim(contractSourcePath, "/"), "/")
	if len(contractParts) < 3 || contractParts[len(contractParts)-1] != "operations.yaml" {
		return false
	}
	object := contractParts[len(contractParts)-2]
	domain := contractParts[0]
	context := domain
	if len(contractParts) >= 4 {
		context = contractParts[len(contractParts)-3]
	}
	if domain != objectParts[0] || object != objectParts[1] {
		return false
	}

	switch producer {
	case ProducerService:
		return (layer == LayerLocalContract || layer == LayerAPIIntegration) &&
			len(parts) >= 8 && parts[0] == "quwoquan_service" &&
			parts[1] == "services" && parts[2] != "" && parts[3] == "tests" &&
			parts[4] == string(layer) && parts[5] == context && parts[6] == object &&
			isCanonicalServiceTestFile(parts[len(parts)-1])
	case ProducerApp:
		if layer == LayerUserAcceptance {
			return validUserAcceptanceSourcePath(value, objectID, contractSourcePath)
		}
		return (layer == LayerLocalContract || layer == LayerAPIIntegration) &&
			len(parts) >= 8 && parts[0] == "quwoquan_app" && parts[1] == "test" &&
			parts[2] == string(layer) && parts[3] == "service" &&
			parts[4] != "" && parts[5] == context && parts[6] == object
	case ProducerOps:
		return (layer == LayerEnvironmentAcceptance || layer == LayerRollback ||
			layer == LayerReplay) && len(parts) >= 8 &&
			parts[0] == "quwoquan_ops" && parts[1] == "tests" &&
			parts[2] == "acceptance" && parts[3] == string(layer) &&
			parts[4] == objectParts[0] && parts[5] == context && parts[6] == object
	default:
		return false
	}
}

func isCanonicalServiceTestFile(name string) bool {
	return strings.HasSuffix(name, "_test.go") || strings.HasSuffix(name, "_test.py")
}

func validExecution(value ExecutionRequirement) bool {
	return validEnvironment(value.Environment) &&
		validNonSecretIdentity(value.Platform) &&
		validNonSecretIdentity(value.DeviceClass) &&
		validNonSecretIdentity(value.Provider) &&
		(value.DigestBinding == DigestCandidate ||
			value.DigestBinding == DigestRelease || value.DigestBinding == DigestEither)
}

func validNonSecretIdentity(value string) bool {
	if len(value) == 0 || len(value) > 128 {
		return false
	}
	for index, current := range value {
		if (current >= 'a' && current <= 'z') ||
			(current >= 'A' && current <= 'Z') ||
			(current >= '0' && current <= '9') {
			continue
		}
		if index > 0 && (current == '.' || current == '_' || current == '-' || current == '/') {
			continue
		}
		return false
	}
	return true
}

func validRelativeArtifactPath(value string) bool {
	if len(value) == 0 || len(value) > 512 || strings.HasPrefix(value, "/") ||
		strings.Contains(value, "\\") || strings.Contains(value, ":") {
		return false
	}
	for _, segment := range strings.Split(value, "/") {
		if segment == "" || segment == "." || segment == ".." ||
			!validNonSecretPathSegment(segment) {
			return false
		}
	}
	return true
}

func validReceiptReference(value string) bool {
	if !validNonSecretIdentity(value) || strings.Contains(value, ":") {
		return false
	}
	for _, segment := range strings.Split(value, "/") {
		if segment == "" || segment == "." || segment == ".." {
			return false
		}
	}
	return true
}

func validNonSecretPathSegment(value string) bool {
	for _, current := range value {
		if (current >= 'a' && current <= 'z') ||
			(current >= 'A' && current <= 'Z') ||
			(current >= '0' && current <= '9') || current == '.' ||
			current == '_' || current == '-' {
			continue
		}
		return false
	}
	return value != ""
}

func validLayer(value Layer) bool {
	switch value {
	case LayerLocalContract, LayerAPIIntegration, LayerUserAcceptance,
		LayerEnvironmentAcceptance, LayerRollback, LayerReplay:
		return true
	default:
		return false
	}
}

func validProducer(value Producer) bool {
	return value == ProducerService || value == ProducerApp || value == ProducerOps
}

func producerOwnsLayer(producer Producer, layer Layer) bool {
	switch producer {
	case ProducerService:
		return layer == LayerLocalContract || layer == LayerAPIIntegration
	case ProducerApp:
		return layer == LayerLocalContract || layer == LayerAPIIntegration ||
			layer == LayerUserAcceptance
	case ProducerOps:
		return layer == LayerEnvironmentAcceptance || layer == LayerRollback ||
			layer == LayerReplay
	default:
		return false
	}
}

func validStatus(value Status) bool {
	switch value {
	case StatusPassed, StatusFailed, StatusBlocked, StatusSkipped:
		return true
	default:
		return false
	}
}

func validTarget(value ReadinessTarget) bool {
	if strings.TrimSpace(value.ID) == "" {
		return false
	}
	return value.Kind == TargetOperation || value.Kind == TargetPage || value.Kind == TargetObject
}

func validEnvironment(value string) bool {
	return value == "alpha" || value == "beta" || value == "gamma" || value == "prod"
}

func isSHA256(value string) bool {
	return len(value) == 64 && isLowerHex(value)
}

func isDigest(value string) bool {
	return len(value) == 71 && strings.HasPrefix(value, "sha256:") &&
		isLowerHex(strings.TrimPrefix(value, "sha256:"))
}

func isCommitSHA(value string) bool {
	return (len(value) == 40 || len(value) == 64) && isLowerHex(value)
}

func isLowerHex(value string) bool {
	for _, current := range value {
		if (current < '0' || current > '9') && (current < 'a' || current > 'f') {
			return false
		}
	}
	return true
}

func caseContractKey(
	objectID string,
	specRef string,
	caseID string,
	producer Producer,
	layer Layer,
	target ReadinessTarget,
) string {
	return strings.Join([]string{
		objectID, specRef, caseID, string(producer), string(layer), string(target.Kind), target.ID,
	}, "\x00")
}

func resultSlotKey(caseKey string, execution ExecutionRequirement) string {
	return strings.Join([]string{
		caseKey,
		execution.Environment,
		execution.Platform,
		execution.DeviceClass,
		execution.Provider,
	}, "\x00")
}

func violation(code, objectID, caseID, message string) Violation {
	return Violation{Code: code, ObjectID: objectID, CaseID: caseID, Message: message}
}

func keys(values map[string]struct{}) []string {
	result := make([]string, 0, len(values))
	for value := range values {
		result = append(result, value)
	}
	sort.Strings(result)
	return result
}

func sortViolations(values []Violation) {
	sort.Slice(values, func(i, j int) bool {
		if values[i].Code != values[j].Code {
			return values[i].Code < values[j].Code
		}
		if values[i].ObjectID != values[j].ObjectID {
			return values[i].ObjectID < values[j].ObjectID
		}
		if values[i].CaseID != values[j].CaseID {
			return values[i].CaseID < values[j].CaseID
		}
		return values[i].Message < values[j].Message
	})
}
