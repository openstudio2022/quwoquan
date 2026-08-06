package readiness

import (
	"fmt"
	"regexp"

	"quwoquan_service/internal/metadata/graph"
)

var canonicalSpecRefPattern = regexp.MustCompile(
	`^specs/feature-tree/.+/spec\.md#(?:uat|dom|sit|gwt)-[0-9]{3,}$`,
)

var canonicalCaseIDPattern = regexp.MustCompile(`^[a-z][a-z0-9_-]*$`)

func validateCaseResponsibilities(
	current *graph.ContractGraph,
	contracts []ReadinessCaseContract,
	pages pageTargetCatalog,
	violations *[]Violation,
) map[string]struct{} {
	invalid := map[string]struct{}{}
	operationsByObject := map[string][]string{}
	clientOperations := map[string]struct{}{}
	for _, operation := range current.Operations {
		operationsByObject[operation.ObjectID] = append(
			operationsByObject[operation.ObjectID], operation.ID,
		)
		if operation.ClientContract != nil {
			clientOperations[operation.ID] = struct{}{}
		}
	}
	for _, entrypoint := range current.RuntimeEntrypoints {
		if lifecycleRuntimeKind(entrypoint.RuntimeKind) {
			continue
		}
		operationsByObject[entrypoint.ObjectID] = append(
			operationsByObject[entrypoint.ObjectID], entrypoint.ID,
		)
	}

	serviceLocalCases := map[string]struct{}{}
	serviceAPICases := map[string]struct{}{}
	serviceLocalObjectCases := map[string]struct{}{}
	serviceAPIObjectCases := map[string]struct{}{}
	appLocalCases := map[string]struct{}{}
	appAPICases := map[string]struct{}{}
	uatPlatforms := map[string]map[string]struct{}{}
	environments := map[string]map[string]DigestBinding{}
	rollbacks := map[string]map[string]DigestBinding{}
	replays := map[string]map[string]DigestBinding{}
	caseIDs := map[string]struct{}{}
	for _, contract := range contracts {
		caseIdentity := contract.ObjectID + "\x00" + contract.CaseID
		if _, duplicate := caseIDs[caseIdentity]; duplicate {
			addCasePolicyViolation(
				violations, invalid, "READINESS.CASE_POLICY.CASE_ID_DUPLICATE",
				contract.ObjectID, contract.CaseID,
				"caseId must be unique within one object",
			)
		}
		caseIDs[caseIdentity] = struct{}{}
		switch {
		case contract.Producer == ProducerService && contract.Layer == LayerLocalContract:
			if contract.Target.Kind == TargetObject {
				serviceLocalObjectCases[contract.Target.ID] = struct{}{}
			} else {
				serviceLocalCases[contract.Target.ID] = struct{}{}
			}
		case contract.Producer == ProducerService && contract.Layer == LayerAPIIntegration:
			if contract.Target.Kind == TargetObject {
				serviceAPIObjectCases[contract.Target.ID] = struct{}{}
			} else {
				serviceAPICases[contract.Target.ID] = struct{}{}
			}
		case contract.Producer == ProducerApp && contract.Layer == LayerLocalContract:
			appLocalCases[contract.Target.ID] = struct{}{}
		case contract.Producer == ProducerApp && contract.Layer == LayerAPIIntegration:
			appAPICases[contract.Target.ID] = struct{}{}
		case contract.Producer == ProducerApp && contract.Layer == LayerUserAcceptance:
			key := contract.ObjectID + "\x00" + contract.Target.ID
			if uatPlatforms[key] == nil {
				uatPlatforms[key] = map[string]struct{}{}
			}
			for _, execution := range contract.Executions {
				if execution.DeviceClass == "physical" &&
					(execution.Platform == "android" || execution.Platform == "ios") {
					uatPlatforms[key][execution.Platform] = struct{}{}
				}
			}
		case contract.Producer == ProducerOps && contract.Layer == LayerEnvironmentAcceptance:
			collectEnvironmentBindings(environments, contract)
		case contract.Producer == ProducerOps && contract.Layer == LayerRollback:
			collectEnvironmentBindings(rollbacks, contract)
		case contract.Producer == ProducerOps && contract.Layer == LayerReplay:
			collectEnvironmentBindings(replays, contract)
		}
	}

	for _, object := range current.Objects {
		objectID := object.ID
		if object.Lifecycle != nil && len(object.Lifecycle.SourceEvents) > 0 {
			if _, exists := serviceLocalObjectCases[objectID]; !exists {
				addCasePolicyViolation(
					violations, invalid, "READINESS.CASE_POLICY.LIFECYCLE_LOCAL_CONTRACT_MISSING",
					objectID, "", "lifecycle event consumer has no object-targeted service local_contract case",
				)
			}
			if _, exists := serviceAPIObjectCases[objectID]; !exists {
				addCasePolicyViolation(
					violations, invalid, "READINESS.CASE_POLICY.LIFECYCLE_API_INTEGRATION_MISSING",
					objectID, "", "lifecycle event consumer has no object-targeted service api_integration case",
				)
			}
		}
		for _, operationID := range operationsByObject[objectID] {
			if _, exists := serviceLocalCases[operationID]; !exists {
				addCasePolicyViolation(
					violations, invalid, "READINESS.CASE_POLICY.SERVICE_LOCAL_CONTRACT_MISSING",
					objectID, "", "operation "+operationID+" has no canonical service local_contract case",
				)
			}
			if _, exists := serviceAPICases[operationID]; !exists {
				addCasePolicyViolation(
					violations, invalid, "READINESS.CASE_POLICY.SERVICE_API_INTEGRATION_MISSING",
					objectID, "", "operation "+operationID+" has no canonical service api_integration case",
				)
			}
			if _, clientExposed := clientOperations[operationID]; !clientExposed {
				continue
			}
			if _, exists := appLocalCases[operationID]; !exists {
				addCasePolicyViolation(
					violations, invalid, "READINESS.CASE_POLICY.APP_LOCAL_CONTRACT_MISSING",
					objectID, "", "client operation "+operationID+" has no canonical app local_contract case",
				)
			}
			if _, exists := appAPICases[operationID]; !exists {
				addCasePolicyViolation(
					violations, invalid, "READINESS.CASE_POLICY.APP_API_INTEGRATION_MISSING",
					objectID, "", "client operation "+operationID+" has no canonical app api_integration case",
				)
			}
		}
		for pageID, page := range pages {
			if page.physicalOwner != objectID {
				continue
			}
			platforms := uatPlatforms[objectID+"\x00"+pageID]
			for _, platform := range []string{"android", "ios"} {
				if _, exists := platforms[platform]; !exists {
					addCasePolicyViolation(
						violations, invalid, "READINESS.CASE_POLICY.PHYSICAL_UAT_MISSING",
						objectID, "",
						fmt.Sprintf("physical %s UAT case is missing for page %s", platform, pageID),
					)
				}
			}
		}
		requireEnvironmentBindings(
			violations, invalid, objectID, environments[objectID],
			"READINESS.CASE_POLICY.ENVIRONMENT_MISSING",
			[]environmentBindingRequirement{
				{environment: "alpha", binding: DigestCandidate},
				{environment: "beta", binding: DigestCandidate},
				{environment: "gamma", binding: DigestCandidate},
				{environment: "prod", binding: DigestRelease},
			},
		)
		recoveryRequirements := []environmentBindingRequirement{
			{environment: "gamma", binding: DigestCandidate},
			{environment: "prod", binding: DigestRelease},
		}
		requireEnvironmentBindings(
			violations, invalid, objectID, rollbacks[objectID],
			"READINESS.CASE_POLICY.ROLLBACK_MISSING", recoveryRequirements,
		)
		requireEnvironmentBindings(
			violations, invalid, objectID, replays[objectID],
			"READINESS.CASE_POLICY.REPLAY_MISSING", recoveryRequirements,
		)
	}
	return invalid
}

func lifecycleRuntimeKind(kind string) bool {
	return kind == "projector" || kind == "event_handler" || kind == "subscription"
}

func collectEnvironmentBindings(
	target map[string]map[string]DigestBinding,
	contract ReadinessCaseContract,
) {
	if target[contract.ObjectID] == nil {
		target[contract.ObjectID] = map[string]DigestBinding{}
	}
	for _, execution := range contract.Executions {
		target[contract.ObjectID][execution.Environment] = execution.DigestBinding
	}
}

type environmentBindingRequirement struct {
	environment string
	binding     DigestBinding
}

func requireEnvironmentBindings(
	violations *[]Violation,
	invalid map[string]struct{},
	objectID string,
	actual map[string]DigestBinding,
	code string,
	requirements []environmentBindingRequirement,
) {
	for _, requirement := range requirements {
		if actual[requirement.environment] == requirement.binding {
			continue
		}
		addCasePolicyViolation(
			violations, invalid, code, objectID, "",
			fmt.Sprintf(
				"%s requires %s digest binding", requirement.environment,
				requirement.binding,
			),
		)
	}
}

func addCasePolicyViolation(
	violations *[]Violation,
	invalid map[string]struct{},
	code string,
	objectID string,
	caseID string,
	message string,
) {
	*violations = append(*violations, violation(code, objectID, caseID, message))
	invalid[objectID] = struct{}{}
}

func validCaseID(value string) bool {
	return canonicalCaseIDPattern.MatchString(value)
}
