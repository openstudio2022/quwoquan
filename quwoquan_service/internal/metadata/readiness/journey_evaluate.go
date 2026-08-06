package readiness

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"io"
	"regexp"
	"sort"
	"strings"

	"quwoquan_service/internal/metadata/graph"
)

var appRootUATSpecRefPattern = regexp.MustCompile(
	`^specs/feature-tree/spec\.md#uat-[0-9]{3,}$`,
)

var journeyIDPattern = regexp.MustCompile(`^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$`)

type JourneyEvaluator struct {
	snapshots CurrentSnapshotProvider
	cases     JourneyCaseAuthority
	receipts  JourneyReceiptResolver
	schemas   *WireSchemas
}

func NewJourneyEvaluator(
	snapshots CurrentSnapshotProvider,
	cases JourneyCaseAuthority,
	receipts JourneyReceiptResolver,
	schemas ...*WireSchemas,
) *JourneyEvaluator {
	result := &JourneyEvaluator{snapshots: snapshots, cases: cases, receipts: receipts}
	if len(schemas) == 1 {
		result.schemas = schemas[0]
	}
	return result
}

func (e *JourneyEvaluator) EvaluateJSON(
	ctx context.Context,
	current *graph.ContractGraph,
	reader io.Reader,
) JourneyClosureResult {
	if e == nil || e.schemas == nil {
		return JourneyClosureResult{Violations: []JourneyViolation{journeyViolation(
			"JOURNEY_READINESS.BUNDLE.SCHEMA_AUTHORITY_MISSING", "", "",
			"canonical readiness wire schemas are required",
		)}}
	}
	bundle, err := e.schemas.DecodeJourneyBundle(reader)
	if err != nil {
		return JourneyClosureResult{
			Violations: []JourneyViolation{journeyViolation(
				"JOURNEY_READINESS.BUNDLE.DECODE_FAILED", "", "", err.Error(),
			)},
		}
	}
	return e.Evaluate(ctx, current, bundle)
}

func (e *JourneyEvaluator) Evaluate(
	ctx context.Context,
	current *graph.ContractGraph,
	bundle JourneyReadinessResultBundle,
) JourneyClosureResult {
	closure := JourneyClosureResult{}
	if current == nil {
		closure.Violations = append(closure.Violations, journeyViolation(
			"JOURNEY_READINESS.GRAPH.MISSING", "", "", "current ContractGraph is required",
		))
		return closure
	}

	evaluation := EvaluationContext{}
	globalValid := true
	if e == nil || e.snapshots == nil {
		addJourneyGlobalViolation(
			&closure, "JOURNEY_READINESS.SNAPSHOT.PROVIDER_MISSING",
			"trusted current snapshot provider is required",
		)
		globalValid = false
	} else {
		resolved, err := e.snapshots.CurrentSnapshot(ctx, current)
		if err != nil {
			addJourneyGlobalViolation(
				&closure, "JOURNEY_READINESS.SNAPSHOT.UNAVAILABLE",
				"trusted current snapshot cannot be resolved",
			)
			globalValid = false
		} else {
			evaluation = resolved
		}
	}
	if !validateJourneyEvaluationContext(evaluation, &closure.Violations) {
		globalValid = false
	}

	catalog := JourneyCaseCatalog{}
	if e == nil || e.cases == nil {
		addJourneyGlobalViolation(
			&closure, "JOURNEY_READINESS.CASE_AUTHORITY.MISSING",
			"trusted current Journey case authority is required",
		)
		globalValid = false
	} else {
		resolved, err := e.cases.CurrentJourneyCatalog(ctx, current)
		if err != nil {
			addJourneyGlobalViolation(
				&closure, "JOURNEY_READINESS.CASE_AUTHORITY.UNAVAILABLE",
				"canonical Journey case catalog cannot be resolved",
			)
			globalValid = false
		} else {
			catalog = resolved
		}
	}
	if len(catalog.Journeys) == 0 {
		addJourneyGlobalViolation(
			&closure, "JOURNEY_READINESS.CATALOG.EMPTY",
			"canonical AppRoot Journey catalog must not be empty",
		)
		globalValid = false
	}

	pageTargets, err := currentPageTargets(current)
	if err != nil {
		addJourneyGlobalViolation(
			&closure, "JOURNEY_READINESS.GRAPH.PAGE_TARGETS_INVALID", err.Error(),
		)
		globalValid = false
	}
	currentSourceHash, err := ContractGraphSourceHash(current)
	if err != nil {
		addJourneyGlobalViolation(
			&closure, "JOURNEY_READINESS.GRAPH.SOURCE_IDENTITY_INVALID", err.Error(),
		)
		globalValid = false
	}
	if bundle.GeneratedAt.IsZero() {
		addJourneyGlobalViolation(
			&closure, "JOURNEY_READINESS.BUNDLE.GENERATED_AT_MISSING",
			"generatedAt is required as bundle identity",
		)
		globalValid = false
	}

	definitions := map[string]JourneyDefinition{}
	invalidJourneys := map[string]struct{}{}
	for _, definition := range catalog.Journeys {
		valid := validJourneyID(definition.JourneyID) &&
			appRootUATSpecRefPattern.MatchString(definition.SpecRef)
		if !valid {
			addJourneyViolation(
				&closure, invalidJourneys, "JOURNEY_READINESS.DEFINITION.INVALID",
				definition.JourneyID, "", "journeyId and AppRoot UAT specRef are required",
			)
		}
		if _, duplicate := definitions[definition.JourneyID]; duplicate {
			addJourneyViolation(
				&closure, invalidJourneys, "JOURNEY_READINESS.DEFINITION.DUPLICATE",
				definition.JourneyID, "", "duplicate canonical Journey definition",
			)
		}
		definitions[definition.JourneyID] = definition
	}

	contractsByKey := map[string]JourneyCaseContract{}
	contractsByJourney := map[string][]JourneyCaseContract{}
	contractSlots := map[string]ExecutionRequirement{}
	caseIDs := map[string]struct{}{}
	for _, contract := range catalog.Cases {
		valid := validateJourneyCaseContract(
			contract, definitions, pageTargets, &closure.Violations,
		)
		caseIDKey := contract.JourneyID + "\x00" + contract.CaseID
		if _, duplicate := caseIDs[caseIDKey]; duplicate {
			closure.Violations = append(closure.Violations, journeyViolation(
				"JOURNEY_READINESS.CASE_CONTRACT.CASE_ID_DUPLICATE",
				contract.JourneyID, contract.CaseID,
				"caseId must be unique within one Journey",
			))
			valid = false
		}
		caseIDs[caseIDKey] = struct{}{}
		key := journeyCaseKey(contract)
		if _, duplicate := contractsByKey[key]; duplicate {
			closure.Violations = append(closure.Violations, journeyViolation(
				"JOURNEY_READINESS.CASE_CONTRACT.DUPLICATE",
				contract.JourneyID, contract.CaseID,
				"duplicate Journey case contract identity",
			))
			valid = false
		}
		contractsByKey[key] = contract
		contractsByJourney[contract.JourneyID] = append(
			contractsByJourney[contract.JourneyID], contract,
		)
		seenExecutions := map[string]struct{}{}
		for _, execution := range contract.Executions {
			slot := journeyResultSlotKey(key, execution)
			if _, duplicate := seenExecutions[slot]; duplicate {
				closure.Violations = append(closure.Violations, journeyViolation(
					"JOURNEY_READINESS.CASE_CONTRACT.EXECUTION_DUPLICATE",
					contract.JourneyID, contract.CaseID,
					"duplicate Journey execution requirement",
				))
				valid = false
			}
			seenExecutions[slot] = struct{}{}
			contractSlots[slot] = execution
		}
		if !valid {
			invalidJourneys[contract.JourneyID] = struct{}{}
		}
	}
	for journeyID := range validateJourneyPolicy(
		definitions, catalog.Cases, &closure.Violations,
	) {
		invalidJourneys[journeyID] = struct{}{}
	}

	grouped := map[string][]journeyEvaluatedResult{}
	for _, result := range bundle.Results {
		key := journeyResultCaseKey(result)
		contract, known := contractsByKey[key]
		if !known {
			closure.Violations = append(closure.Violations, journeyViolation(
				"JOURNEY_READINESS.RESULT.UNKNOWN_CASE", result.JourneyID, result.CaseID,
				"result does not match a canonical Journey case contract",
			))
			invalidJourneys[result.JourneyID] = struct{}{}
			continue
		}
		execution := ExecutionRequirement{
			Environment: result.Environment,
			Platform:    result.Platform,
			DeviceClass: result.DeviceClass,
			Provider:    result.Provider,
		}
		slot := journeyResultSlotKey(key, execution)
		requirement, required := contractSlots[slot]
		valid := required
		if !required {
			closure.Violations = append(closure.Violations, journeyViolation(
				"JOURNEY_READINESS.RESULT.EXECUTION_MISMATCH",
				result.JourneyID, result.CaseID,
				"environment/platform/device/provider do not match the Journey case contract",
			))
		}
		var receipts JourneyReceiptResolver
		if e != nil {
			receipts = e.receipts
		}
		if !validateJourneyResult(
			ctx, result, contract, requirement, evaluation, currentSourceHash,
			receipts, &closure.Violations,
		) {
			valid = false
		}
		grouped[slot] = append(grouped[slot], journeyEvaluatedResult{result: result, valid: valid})
	}

	satisfied := map[string]struct{}{}
	for slot, results := range grouped {
		if len(results) != 1 {
			first := results[0].result
			closure.Violations = append(closure.Violations, journeyViolation(
				"JOURNEY_READINESS.RESULT.DUPLICATE", first.JourneyID, first.CaseID,
				"duplicate or conflicting results for one Journey execution requirement",
			))
			invalidJourneys[first.JourneyID] = struct{}{}
			continue
		}
		if results[0].valid {
			satisfied[slot] = struct{}{}
		} else {
			invalidJourneys[results[0].result.JourneyID] = struct{}{}
		}
	}

	journeyIDs := make([]string, 0, len(definitions))
	for journeyID := range definitions {
		journeyIDs = append(journeyIDs, journeyID)
	}
	sort.Strings(journeyIDs)
	closure.CommercialReady = globalValid && len(journeyIDs) > 0 && len(closure.Violations) == 0
	for _, journeyID := range journeyIDs {
		missing := map[string]struct{}{}
		contracts := contractsByJourney[journeyID]
		if len(contracts) == 0 {
			missing["commercial.case_contract"] = struct{}{}
		}
		for _, contract := range contracts {
			key := journeyCaseKey(contract)
			for _, execution := range contract.Executions {
				if _, exists := satisfied[journeyResultSlotKey(key, execution)]; !exists {
					missing["commercial.case."+contract.CaseID] = struct{}{}
				}
			}
		}
		if !globalValid {
			missing["commercial.evaluation_context"] = struct{}{}
		}
		if _, invalid := invalidJourneys[journeyID]; invalid {
			missing["commercial.result_invalid"] = struct{}{}
		}
		missingList := keys(missing)
		ready := len(missingList) == 0
		closure.Journeys = append(closure.Journeys, JourneyClosure{
			JourneyID: journeyID, CommercialReady: ready, Missing: missingList,
		})
		closure.CommercialReady = closure.CommercialReady && ready
	}
	sortJourneyViolations(closure.Violations)
	return closure
}

type journeyEvaluatedResult struct {
	result JourneyReadinessCaseResult
	valid  bool
}

func validateJourneyEvaluationContext(
	value EvaluationContext,
	violations *[]JourneyViolation,
) bool {
	valid := true
	for name, item := range map[string]string{
		"candidateDigest": value.CandidateDigest,
		"releaseDigest":   value.ReleaseDigest,
	} {
		if !isDigest(item) {
			*violations = append(*violations, journeyViolation(
				"JOURNEY_READINESS.CONTEXT.INVALID_DIGEST", "", "",
				name+" must be sha256",
			))
			valid = false
		}
	}
	var candidatePackage string
	var candidateManifest string
	for _, environment := range []string{"alpha", "beta", "gamma", "prod"} {
		deployment, exists := value.Deployments[environment]
		if !exists || !validDeploymentBinding(deployment) {
			*violations = append(*violations, journeyViolation(
				"JOURNEY_READINESS.CONTEXT.INVALID_DIGEST", "", "",
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
			*violations = append(*violations, journeyViolation(
				"JOURNEY_READINESS.CONTEXT.CANDIDATE_PACKAGE_MISMATCH", "", "",
				"all environments must bind one candidate package and manifest",
			))
			valid = false
		}
	}
	if !isCommitSHA(value.CommitSHA) {
		*violations = append(*violations, journeyViolation(
			"JOURNEY_READINESS.CONTEXT.INVALID_COMMIT", "", "",
			"commitSha must be a Git SHA",
		))
		valid = false
	}
	if len(value.Deployments) != 4 {
		*violations = append(*violations, journeyViolation(
			"JOURNEY_READINESS.CONTEXT.DEPLOYMENT_SET_INVALID", "", "",
			"deployment snapshot must contain exactly alpha, beta, gamma and prod",
		))
		valid = false
	}
	return valid
}

func validateJourneyCaseContract(
	contract JourneyCaseContract,
	definitions map[string]JourneyDefinition,
	pages pageTargetCatalog,
	violations *[]JourneyViolation,
) bool {
	valid := true
	definition, exists := definitions[contract.JourneyID]
	if !exists || definition.SpecRef != contract.SpecRef {
		*violations = append(*violations, journeyViolation(
			"JOURNEY_READINESS.CASE_CONTRACT.UNKNOWN_JOURNEY",
			contract.JourneyID, contract.CaseID,
			"case contract does not match a canonical Journey definition",
		))
		valid = false
	}
	if !validJourneyID(contract.JourneyID) ||
		!appRootUATSpecRefPattern.MatchString(contract.SpecRef) ||
		!validCaseID(contract.CaseID) || !validJourneyProducerLayer(contract.Producer, contract.Layer) ||
		!validJourneyTarget(contract.Target) || len(contract.Executions) == 0 ||
		!validJourneyRunnerSourcePath(
			contract.RunnerSourcePath, contract.JourneyID, contract.Producer, contract.Layer,
		) {
		*violations = append(*violations, journeyViolation(
			"JOURNEY_READINESS.CASE_CONTRACT.INVALID",
			contract.JourneyID, contract.CaseID,
			"Journey identity, AppRoot UAT, producer/layer, target, runner source and executions are required",
		))
		valid = false
	}
	switch contract.Target.Kind {
	case JourneyTargetJourney:
		if contract.Target.ID != contract.JourneyID {
			*violations = append(*violations, journeyViolation(
				"JOURNEY_READINESS.CASE_CONTRACT.TARGET_MISMATCH",
				contract.JourneyID, contract.CaseID,
				"journey target must equal journeyId",
			))
			valid = false
		}
	case JourneyTargetPage:
		if _, exists := pages[contract.Target.ID]; !exists {
			*violations = append(*violations, journeyViolation(
				"JOURNEY_READINESS.CASE_CONTRACT.TARGET_MISMATCH",
				contract.JourneyID, contract.CaseID,
				"page target is not present in the current ContractGraph page contract",
			))
			valid = false
		}
	}
	for _, execution := range contract.Executions {
		if !validExecution(execution) {
			*violations = append(*violations, journeyViolation(
				"JOURNEY_READINESS.CASE_CONTRACT.EXECUTION_INVALID",
				contract.JourneyID, contract.CaseID,
				"Journey execution requirement is incomplete or invalid",
			))
			valid = false
		}
	}
	return valid
}

func validateJourneyPolicy(
	definitions map[string]JourneyDefinition,
	contracts []JourneyCaseContract,
	violations *[]JourneyViolation,
) map[string]struct{} {
	invalid := map[string]struct{}{}
	matrices := map[string]map[string]map[DigestBinding]struct{}{}
	for _, contract := range contracts {
		if contract.Target.Kind != JourneyTargetJourney || contract.Target.ID != contract.JourneyID {
			continue
		}
		for _, execution := range contract.Executions {
			key := ""
			switch {
			case contract.Producer == ProducerApp && contract.Layer == LayerUserAcceptance &&
				execution.DeviceClass == "physical" &&
				(execution.Platform == "android" || execution.Platform == "ios"):
				key = "uat\x00" + execution.Environment + "\x00" + execution.Platform
			case contract.Producer == ProducerOps &&
				(contract.Layer == LayerEnvironmentAcceptance ||
					contract.Layer == LayerRollback || contract.Layer == LayerReplay):
				key = string(contract.Layer) + "\x00" + execution.Environment
			}
			if key == "" {
				continue
			}
			if matrices[contract.JourneyID] == nil {
				matrices[contract.JourneyID] = map[string]map[DigestBinding]struct{}{}
			}
			if matrices[contract.JourneyID][key] == nil {
				matrices[contract.JourneyID][key] = map[DigestBinding]struct{}{}
			}
			matrices[contract.JourneyID][key][execution.DigestBinding] = struct{}{}
		}
	}
	for journeyID := range definitions {
		for _, environment := range []string{"alpha", "beta", "gamma", "prod"} {
			binding := DigestCandidate
			if environment == "prod" {
				binding = DigestRelease
			}
			for _, platform := range []string{"android", "ios"} {
				requireJourneyMatrixSlot(
					violations, invalid, matrices, journeyID,
					"uat\x00"+environment+"\x00"+platform, binding,
					"JOURNEY_READINESS.CASE_POLICY.PHYSICAL_UAT_MISSING",
					fmt.Sprintf("%s physical %s Remote UAT requires %s binding", environment, platform, binding),
				)
			}
			for _, layer := range []Layer{
				LayerEnvironmentAcceptance, LayerRollback, LayerReplay,
			} {
				requireJourneyMatrixSlot(
					violations, invalid, matrices, journeyID,
					string(layer)+"\x00"+environment, binding,
					"JOURNEY_READINESS.CASE_POLICY."+strings.ToUpper(string(layer))+"_MISSING",
					fmt.Sprintf("%s %s requires %s binding", environment, layer, binding),
				)
			}
		}
	}
	return invalid
}

func requireJourneyMatrixSlot(
	violations *[]JourneyViolation,
	invalid map[string]struct{},
	matrices map[string]map[string]map[DigestBinding]struct{},
	journeyID string,
	key string,
	binding DigestBinding,
	code string,
	message string,
) {
	if _, exists := matrices[journeyID][key][binding]; exists {
		return
	}
	*violations = append(*violations, journeyViolation(code, journeyID, "", message))
	invalid[journeyID] = struct{}{}
}

func validateJourneyResult(
	ctx context.Context,
	result JourneyReadinessCaseResult,
	contract JourneyCaseContract,
	requirement ExecutionRequirement,
	evaluation EvaluationContext,
	currentSourceHash string,
	receipts JourneyReceiptResolver,
	violations *[]JourneyViolation,
) bool {
	valid := true
	add := func(code, message string) {
		*violations = append(*violations, journeyViolation(
			code, result.JourneyID, result.CaseID, message,
		))
		valid = false
	}
	if result.Status != StatusPassed {
		add("JOURNEY_READINESS.RESULT.NOT_PASSED", "failed, blocked and skipped results never close Journey readiness")
	}
	if !validStatus(result.Status) || !validJourneyProducerLayer(result.Producer, result.Layer) ||
		!validJourneyTarget(result.Target) {
		add("JOURNEY_READINESS.RESULT.INVALID_ENUM", "unknown status, producer/layer or target")
	}
	if result.JourneyID != contract.JourneyID || result.SpecRef != contract.SpecRef ||
		result.CaseID != contract.CaseID || result.Producer != contract.Producer ||
		result.Layer != contract.Layer || result.Target != contract.Target {
		add("JOURNEY_READINESS.RESULT.IDENTITY_MISMATCH", "result identity does not match Journey case contract")
	}
	deployment := evaluation.Deployments[result.Environment]
	if result.CommitSHA != evaluation.CommitSHA ||
		result.ContractGraphSourceHash != currentSourceHash ||
		result.DeploymentTarget != deployment.DeploymentTarget ||
		result.BaselineID != deployment.BaselineID ||
		result.PackageDigest != deployment.PackageDigest ||
		result.ConfigurationDigest != deployment.ConfigurationDigest ||
		result.CandidateManifestSHA256 != deployment.CandidateManifestSHA256 {
		add("JOURNEY_READINESS.RESULT.STALE_IDENTITY", "commit, ContractGraph source or package-bound deployment identity is stale")
	}
	if !isCommitSHA(result.CommitSHA) || !isSHA256(result.ContractGraphSourceHash) ||
		!validNonSecretIdentity(result.DeploymentTarget) ||
		!validNonSecretIdentity(result.BaselineID) ||
		!isDigest(result.PackageDigest) || !isDigest(result.ConfigurationDigest) ||
		!isSHA256(result.CandidateManifestSHA256) || !isSHA256(result.ArtifactSHA256) {
		add("JOURNEY_READINESS.RESULT.INVALID_DIGEST", "result identity and artifact digests must be canonical hashes")
	}
	if result.CandidateDigest != "" &&
		(!isDigest(result.CandidateDigest) || result.CandidateDigest != evaluation.CandidateDigest) {
		add("JOURNEY_READINESS.RESULT.STALE_CANDIDATE", "candidateDigest does not bind the current candidate")
	}
	if result.ReleaseDigest != "" &&
		(!isDigest(result.ReleaseDigest) || result.ReleaseDigest != evaluation.ReleaseDigest) {
		add("JOURNEY_READINESS.RESULT.STALE_RELEASE", "releaseDigest does not bind the current release")
	}
	switch requirement.DigestBinding {
	case DigestCandidate:
		if result.CandidateDigest != evaluation.CandidateDigest {
			add("JOURNEY_READINESS.RESULT.CANDIDATE_REQUIRED", "case requires current candidateDigest")
		}
	case DigestRelease:
		if result.ReleaseDigest != evaluation.ReleaseDigest {
			add("JOURNEY_READINESS.RESULT.RELEASE_REQUIRED", "case requires current releaseDigest")
		}
		if result.CandidateDigest != evaluation.CandidateDigest {
			add("JOURNEY_READINESS.RESULT.CANDIDATE_REQUIRED", "release acceptance must bind the shared candidate")
		}
	default:
		add("JOURNEY_READINESS.RESULT.DIGEST_POLICY_UNKNOWN", "Journey cases require candidate or release binding")
	}
	if result.Environment == "prod" && result.ReleaseDigest != evaluation.ReleaseDigest {
		add("JOURNEY_READINESS.RESULT.PROD_RELEASE_REQUIRED", "Prod Journey result must bind releaseDigest")
	}
	if !validNonSecretIdentity(result.RunnerIdentity) ||
		!validNonSecretIdentity(result.Platform) ||
		!validNonSecretIdentity(result.DeviceClass) ||
		!validNonSecretIdentity(result.Provider) {
		add("JOURNEY_READINESS.RESULT.EXECUTION_IDENTITY_INVALID", "runner, platform, device and Provider identities are required")
	}
	if !result.StartedAt.Before(result.CompletedAt) {
		add("JOURNEY_READINESS.RESULT.TIME_INVALID", "startedAt must be before completedAt")
	}
	if (strings.TrimSpace(result.ArtifactPath) == "") ==
		(strings.TrimSpace(result.ReceiptRef) == "") {
		add("JOURNEY_READINESS.RESULT.RECEIPT_REFERENCE_INVALID", "exactly one artifactPath or receiptRef is required")
	} else if (result.ArtifactPath != "" && !validRelativeArtifactPath(result.ArtifactPath)) ||
		(result.ReceiptRef != "" && !validReceiptReference(result.ReceiptRef)) {
		add("JOURNEY_READINESS.RESULT.RECEIPT_REFERENCE_INVALID", "receipt references must be non-secret local or opaque identities")
	}
	if receipts == nil {
		add("JOURNEY_READINESS.RESULT.RECEIPT_RESOLVER_MISSING", "Journey receipt resolver is required")
		return valid
	}
	receipt, err := receipts.ResolveJourney(ctx, result)
	if err != nil {
		add("JOURNEY_READINESS.RESULT.RECEIPT_UNAVAILABLE", "Journey receipt bytes cannot be resolved")
		return valid
	}
	if len(receipt.Bytes) == 0 {
		add("JOURNEY_READINESS.RESULT.RECEIPT_EMPTY", "Journey receipt bytes must not be empty")
		return valid
	}
	if !receipt.Trusted {
		add("JOURNEY_READINESS.RESULT.RECEIPT_UNTRUSTED", "receipt attestation is not trusted")
	}
	if !journeyReceiptBindingMatchesResult(receipt.Binding, result) {
		add("JOURNEY_READINESS.RESULT.RECEIPT_IDENTITY_MISMATCH", "receipt identity does not attest the Journey result")
	}
	if receipt.Binding.RunnerSourcePath != contract.RunnerSourcePath ||
		!validJourneyRunnerSourcePath(
			receipt.Binding.RunnerSourcePath, result.JourneyID, result.Producer, result.Layer,
		) {
		add("JOURNEY_READINESS.RESULT.RUNNER_SOURCE_INVALID", "receipt runner source must exactly match the canonical Journey case contract")
	}
	if !receipt.Binding.RemoteComposition {
		add("JOURNEY_READINESS.RESULT.REMOTE_COMPOSITION_REQUIRED", "Journey evidence must attest production Remote composition")
	}
	if !receipt.Binding.FixtureFree {
		add("JOURNEY_READINESS.RESULT.FIXTURE_FORBIDDEN", "fixture or seed evidence cannot close Journey readiness")
	}
	if !receipt.Binding.DependenciesReady {
		add("JOURNEY_READINESS.RESULT.DEPENDENCY_NOT_READY", "Journey evidence requires all dependencies ready")
	}
	if !receipt.Binding.ProviderVerified {
		add("JOURNEY_READINESS.RESULT.PROVIDER_UNVERIFIED", "Provider identity must come from verified environment evidence")
	}
	if result.Producer == ProducerApp && result.Layer == LayerUserAcceptance {
		if result.DeviceClass != "physical" ||
			(result.Platform != "android" && result.Platform != "ios") ||
			!receipt.Binding.PhysicalDevice {
			add("JOURNEY_READINESS.RESULT.PHYSICAL_DEVICE_REQUIRED", "App Journey UAT requires attested physical Android or iPhone execution")
		}
	}
	digest := sha256.Sum256(receipt.Bytes)
	if hex.EncodeToString(digest[:]) != result.ArtifactSHA256 {
		add("JOURNEY_READINESS.RESULT.ARTIFACT_DIGEST_MISMATCH", "artifactSha256 does not match Journey receipt bytes")
	}
	return valid
}

func journeyReceiptBindingForResult(result JourneyReadinessCaseResult) JourneyReceiptBinding {
	return JourneyReceiptBinding{
		JourneyID: result.JourneyID, SpecRef: result.SpecRef, CaseID: result.CaseID,
		Producer: result.Producer, Layer: result.Layer, Status: result.Status, Target: result.Target,
		CommitSHA: result.CommitSHA, ContractGraphSourceHash: result.ContractGraphSourceHash,
		DeploymentTarget: result.DeploymentTarget, BaselineID: result.BaselineID,
		PackageDigest: result.PackageDigest, ConfigurationDigest: result.ConfigurationDigest,
		CandidateManifestSHA256: result.CandidateManifestSHA256,
		CandidateDigest:         result.CandidateDigest, ReleaseDigest: result.ReleaseDigest,
		Environment: result.Environment, Platform: result.Platform,
		DeviceClass: result.DeviceClass, Provider: result.Provider,
		StartedAt: result.StartedAt, CompletedAt: result.CompletedAt,
		RunnerIdentity: result.RunnerIdentity,
	}
}

func journeyReceiptBindingMatchesResult(
	binding JourneyReceiptBinding,
	result JourneyReadinessCaseResult,
) bool {
	binding.RunnerSourcePath = ""
	binding.RemoteComposition = false
	binding.FixtureFree = false
	binding.DependenciesReady = false
	binding.ProviderVerified = false
	binding.PhysicalDevice = false
	return binding == journeyReceiptBindingForResult(result)
}

func validJourneyRunnerSourcePath(
	value string,
	journeyID string,
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
	switch producer {
	case ProducerApp:
		return layer == LayerUserAcceptance && len(parts) >= 6 &&
			parts[0] == "quwoquan_app" && parts[1] == "test" &&
			parts[2] == "user_acceptance" && parts[3] == "journeys" &&
			parts[4] == journeyID && strings.HasSuffix(parts[len(parts)-1], "_test.dart")
	case ProducerOps:
		return (layer == LayerEnvironmentAcceptance || layer == LayerRollback ||
			layer == LayerReplay) && len(parts) >= 7 &&
			parts[0] == "quwoquan_ops" && parts[1] == "tests" &&
			parts[2] == "acceptance" && parts[3] == string(layer) &&
			parts[4] == "journeys" && parts[5] == journeyID &&
			strings.HasSuffix(parts[len(parts)-1], "_test.py")
	default:
		return false
	}
}

func validJourneyProducerLayer(producer Producer, layer Layer) bool {
	return (producer == ProducerApp && layer == LayerUserAcceptance) ||
		(producer == ProducerOps &&
			(layer == LayerEnvironmentAcceptance || layer == LayerRollback || layer == LayerReplay))
}

func validJourneyTarget(target JourneyTarget) bool {
	return validNonSecretIdentity(target.ID) &&
		(target.Kind == JourneyTargetPage || target.Kind == JourneyTargetJourney)
}

func validJourneyID(value string) bool {
	return len(value) <= 128 && journeyIDPattern.MatchString(value)
}

func journeyCaseKey(contract JourneyCaseContract) string {
	return strings.Join([]string{
		contract.JourneyID, contract.SpecRef, contract.CaseID,
		string(contract.Producer), string(contract.Layer),
		string(contract.Target.Kind), contract.Target.ID,
	}, "\x00")
}

func journeyResultCaseKey(result JourneyReadinessCaseResult) string {
	return strings.Join([]string{
		result.JourneyID, result.SpecRef, result.CaseID,
		string(result.Producer), string(result.Layer),
		string(result.Target.Kind), result.Target.ID,
	}, "\x00")
}

func journeyResultSlotKey(key string, execution ExecutionRequirement) string {
	return strings.Join([]string{
		key, execution.Environment, execution.Platform,
		execution.DeviceClass, execution.Provider,
	}, "\x00")
}

func journeyViolation(code, journeyID, caseID, message string) JourneyViolation {
	return JourneyViolation{Code: code, JourneyID: journeyID, CaseID: caseID, Message: message}
}

func addJourneyGlobalViolation(closure *JourneyClosureResult, code, message string) {
	closure.Violations = append(closure.Violations, journeyViolation(code, "", "", message))
}

func addJourneyViolation(
	closure *JourneyClosureResult,
	invalid map[string]struct{},
	code, journeyID, caseID, message string,
) {
	closure.Violations = append(closure.Violations, journeyViolation(code, journeyID, caseID, message))
	invalid[journeyID] = struct{}{}
}

func sortJourneyViolations(values []JourneyViolation) {
	sort.Slice(values, func(i, j int) bool {
		if values[i].Code != values[j].Code {
			return values[i].Code < values[j].Code
		}
		if values[i].JourneyID != values[j].JourneyID {
			return values[i].JourneyID < values[j].JourneyID
		}
		if values[i].CaseID != values[j].CaseID {
			return values[i].CaseID < values[j].CaseID
		}
		return values[i].Message < values[j].Message
	})
}
