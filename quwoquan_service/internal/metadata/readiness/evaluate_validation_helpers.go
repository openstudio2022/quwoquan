package readiness

import (
	"sort"
	"strings"
)

func validUserAcceptanceSourcePath(value string, identity objectPathIdentity) bool {
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
		return len(relative) >= 3 && strings.HasSuffix(parts[len(parts)-1], "_test.dart")
	}
	return len(relative) >= 5 && relative[0] == "service" &&
		relative[1] == identity.appServiceRoot && relative[2] == identity.context &&
		relative[3] == identity.object &&
		strings.HasSuffix(parts[len(parts)-1], "_test.dart")
}

func validProducerRunnerSourcePath(
	value string,
	identity objectPathIdentity,
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
	case ProducerService:
		prefix := append(append([]string(nil), identity.serviceRoot...),
			"tests", string(layer), identity.context, identity.object)
		return len(identity.serviceRoot) > 0 &&
			(layer == LayerLocalContract || layer == LayerAPIIntegration) &&
			pathHasPrefix(parts, prefix) &&
			isCanonicalServiceTestFile(parts[len(parts)-1])
	case ProducerApp:
		if layer == LayerUserAcceptance {
			return validUserAcceptanceSourcePath(value, identity)
		}
		return (layer == LayerLocalContract || layer == LayerAPIIntegration) &&
			len(parts) >= 8 && parts[0] == "quwoquan_app" && parts[1] == "test" &&
			parts[2] == string(layer) && parts[3] == "service" &&
			parts[4] == identity.appServiceRoot && parts[5] == identity.context &&
			parts[6] == identity.object &&
			strings.HasSuffix(parts[len(parts)-1], "_test.dart")
	case ProducerOps:
		return (layer == LayerEnvironmentAcceptance || layer == LayerRollback ||
			layer == LayerReplay) && len(parts) >= 8 &&
			parts[0] == "quwoquan_ops" && parts[1] == "tests" &&
			parts[2] == "acceptance" && parts[3] == string(layer) &&
			parts[4] == identity.domain && parts[5] == identity.context &&
			parts[6] == identity.object &&
			strings.HasSuffix(parts[len(parts)-1], "_test.py")
	default:
		return false
	}
}

func pathHasPrefix(parts, prefix []string) bool {
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
