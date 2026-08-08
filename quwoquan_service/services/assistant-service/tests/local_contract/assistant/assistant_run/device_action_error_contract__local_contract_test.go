// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/tool-fabric-runtime/spec.md#gwt-003
package assistant_run_test

import (
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"

	"gopkg.in/yaml.v3"
)

var canonicalDeviceActionFailureCodes = map[string]struct {
	reason          string
	httpStatus      int
	recoveryAction  string
	disruptionLevel string
	dartConst       string
	goConst         string
	emitter         string
}{
	"ASSISTANT.SYSTEM.device_action_unavailable": {
		reason:          "device_action_unavailable",
		recoveryAction:  "fallback",
		disruptionLevel: "inlineCard",
		dartConst:       "deviceActionUnavailable",
		goConst:         "ErrDeviceActionUnavailable",
		emitter:         "app",
	},
	"ASSISTANT.USER.device_action_permission_denied": {
		reason:          "device_action_permission_denied",
		recoveryAction:  "surface",
		disruptionLevel: "permissionCard",
		dartConst:       "deviceActionPermissionDenied",
		goConst:         "ErrDeviceActionPermissionDenied",
		emitter:         "app",
	},
	"ASSISTANT.SYSTEM.device_action_failed": {
		reason:          "device_action_failed",
		recoveryAction:  "retry",
		disruptionLevel: "snackbar",
		dartConst:       "deviceActionFailed",
		goConst:         "ErrDeviceActionFailed",
		emitter:         "app",
	},
	"ASSISTANT.USER.device_action_permit_invalid": {
		reason:          "device_action_permit_invalid",
		httpStatus:      403,
		recoveryAction:  "surface",
		disruptionLevel: "inlineCard",
		dartConst:       "deviceActionPermitInvalid",
		goConst:         "ErrDeviceActionPermitInvalid",
		emitter:         "SubmitDeviceActionReceipt",
	},
	"ASSISTANT.USER.device_action_permit_expired": {
		reason:          "device_action_permit_expired",
		httpStatus:      410,
		recoveryAction:  "surface",
		disruptionLevel: "inlineCard",
		dartConst:       "deviceActionPermitExpired",
		goConst:         "ErrDeviceActionPermitExpired",
		emitter:         "SubmitDeviceActionReceipt",
	},
	"ASSISTANT.USER.device_action_permit_replayed": {
		reason:          "device_action_permit_replayed",
		httpStatus:      409,
		recoveryAction:  "surface",
		disruptionLevel: "inlineCard",
		dartConst:       "deviceActionPermitReplayed",
		goConst:         "ErrDeviceActionPermitReplayed",
		emitter:         "SubmitDeviceActionReceipt",
	},
}

type deviceActionErrorDefinition struct {
	Code            string `yaml:"code"`
	Reason          string `yaml:"reason"`
	HTTPStatus      int    `yaml:"http_status"`
	RecoveryAction  string `yaml:"recovery_action"`
	DisruptionLevel string `yaml:"disruption_level"`
	DartConst       string `yaml:"dart_const"`
	GoConst         string `yaml:"go_const"`
	UserMessage     struct {
		ZH string `yaml:"zh"`
		EN string `yaml:"en"`
	} `yaml:"user_message"`
	EmittedBy yaml.Node `yaml:"emitted_by"`
}

type deviceActionOperationDefinition struct {
	Operation  string   `yaml:"operation"`
	ErrorCodes []string `yaml:"error_codes"`
}

func TestDeviceActionFailuresHaveOneCanonicalOperationOwner(t *testing.T) {
	t.Parallel()
	root := deviceActionAssistantServiceRoot(t)

	var errorDocument struct {
		Errors []deviceActionErrorDefinition `yaml:"errors"`
	}
	deviceActionReadYAML(t, filepath.Join(
		root, "contracts", "assistant", "assistant_run", "errors.yaml",
	), &errorDocument)

	definitions := make(map[string][]deviceActionErrorDefinition)
	for _, definition := range errorDocument.Errors {
		if _, required := canonicalDeviceActionFailureCodes[definition.Code]; required {
			definitions[definition.Code] = append(definitions[definition.Code], definition)
		}
	}
	for code, expected := range canonicalDeviceActionFailureCodes {
		matches := definitions[code]
		if len(matches) != 1 {
			t.Fatalf("canonical device action error %s has %d definitions", code, len(matches))
		}
		definition := matches[0]
		if definition.Reason != expected.reason ||
			definition.HTTPStatus != expected.httpStatus ||
			definition.RecoveryAction != expected.recoveryAction ||
			definition.DisruptionLevel != expected.disruptionLevel ||
			definition.DartConst != expected.dartConst ||
			definition.GoConst != expected.goConst {
			t.Fatalf("canonical device action error %s drifted: %#v", code, definition)
		}
		if strings.TrimSpace(definition.UserMessage.ZH) == "" ||
			strings.TrimSpace(definition.UserMessage.EN) == "" {
			t.Fatalf("canonical device action error %s lacks generated App semantics", code)
		}
		if !deviceActionEmitterMatches(definition.EmittedBy, expected.emitter) {
			t.Fatalf("canonical device action error %s has the wrong emitter: %#v", code, definition.EmittedBy)
		}
	}

	var operationDocument struct {
		APIRoutes []deviceActionOperationDefinition `yaml:"api_routes"`
	}
	deviceActionReadYAML(t, filepath.Join(
		root, "contracts", "assistant", "assistant_run", "operations.yaml",
	), &operationDocument)
	foundSubmitReceipt := false
	for _, route := range operationDocument.APIRoutes {
		counts := map[string]int{}
		for _, code := range route.ErrorCodes {
			if _, required := canonicalDeviceActionFailureCodes[code]; required {
				counts[code]++
			}
		}
		if route.Operation != "SubmitDeviceActionReceipt" {
			if len(counts) != 0 {
				t.Fatalf("operation %s also claims device action errors: %#v", route.Operation, counts)
			}
			continue
		}
		foundSubmitReceipt = true
		for code, expected := range canonicalDeviceActionFailureCodes {
			want := 0
			if expected.emitter == "SubmitDeviceActionReceipt" {
				want = 1
			}
			if counts[code] != want {
				t.Fatalf("SubmitDeviceActionReceipt binds %s %d times, want %d", code, counts[code], want)
			}
		}
	}
	if !foundSubmitReceipt {
		t.Fatal("SubmitDeviceActionReceipt operation is missing")
	}
}

func deviceActionEmitterMatches(node yaml.Node, expected string) bool {
	if node.Kind != yaml.SequenceNode || len(node.Content) != 1 {
		return false
	}
	emitter := node.Content[0]
	if expected == "app" {
		return emitter.Kind == yaml.ScalarNode && emitter.Value == "app"
	}
	if emitter.Kind != yaml.MappingNode {
		return false
	}
	var surface string
	var operations []string
	for index := 0; index+1 < len(emitter.Content); index += 2 {
		switch emitter.Content[index].Value {
		case "surface":
			surface = emitter.Content[index+1].Value
		case "operations":
			for _, operation := range emitter.Content[index+1].Content {
				operations = append(operations, operation.Value)
			}
		}
	}
	return surface == "http" && len(operations) == 1 && operations[0] == expected
}

func TestDeviceActionFailureCodeKeepsErrorsYAMLAsSingleTypedOwner(t *testing.T) {
	t.Parallel()
	root := deviceActionAssistantServiceRoot(t)
	var fieldsDocument struct {
		Types map[string]struct {
			Fields []struct {
				Name        string `yaml:"name"`
				Type        string `yaml:"type"`
				EnumRef     string `yaml:"enum_ref"`
				Description string `yaml:"description"`
			} `yaml:"fields"`
		} `yaml:"types"`
	}
	deviceActionReadYAML(t, filepath.Join(
		root, "contracts", "assistant", "assistant_run", "fields.yaml",
	), &fieldsDocument)
	receipt, ok := fieldsDocument.Types["AssistantDeviceActionExecutionReceipt"]
	if !ok {
		t.Fatal("AssistantDeviceActionExecutionReceipt type is missing")
	}
	for _, field := range receipt.Fields {
		if field.Name != "failureCode" {
			continue
		}
		if field.Type != "string" || strings.TrimSpace(field.EnumRef) != "" {
			t.Fatalf("failureCode duplicated errors.yaml through a fields enum: type=%q enum_ref=%q", field.Type, field.EnumRef)
		}
		if !strings.Contains(field.Description, "assistant_run/errors.yaml") ||
			!strings.Contains(field.Description, "端侧强类型") {
			t.Fatalf("failureCode does not document its generated typed owner: %q", field.Description)
		}
		return
	}
	t.Fatal("AssistantDeviceActionExecutionReceipt.failureCode is missing")
}

func deviceActionAssistantServiceRoot(t *testing.T) string {
	t.Helper()
	_, file, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("resolve device action contract test path")
	}
	root := filepath.Clean(filepath.Join(filepath.Dir(file), "..", "..", "..", ".."))
	if _, err := os.Stat(filepath.Join(root, "contracts", "assistant", "assistant_run", "errors.yaml")); err != nil {
		t.Fatalf("resolve assistant-service root: %v", err)
	}
	return root
}

func deviceActionReadYAML(t *testing.T, path string, target any) {
	t.Helper()
	payload, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read %s: %v", path, err)
	}
	if err := yaml.Unmarshal(payload, target); err != nil {
		t.Fatalf("decode %s: %v", path, err)
	}
}
