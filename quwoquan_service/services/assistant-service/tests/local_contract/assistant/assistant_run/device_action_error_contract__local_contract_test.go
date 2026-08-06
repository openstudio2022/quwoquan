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
}{
	"ASSISTANT.SYSTEM.device_action_unavailable": {
		reason:          "device_action_unavailable",
		httpStatus:      503,
		recoveryAction:  "fallback",
		disruptionLevel: "inlineCard",
		dartConst:       "deviceActionUnavailable",
		goConst:         "ErrDeviceActionUnavailable",
	},
	"ASSISTANT.USER.device_action_permission_denied": {
		reason:          "device_action_permission_denied",
		httpStatus:      403,
		recoveryAction:  "surface",
		disruptionLevel: "permissionCard",
		dartConst:       "deviceActionPermissionDenied",
		goConst:         "ErrDeviceActionPermissionDenied",
	},
	"ASSISTANT.SYSTEM.device_action_failed": {
		reason:          "device_action_failed",
		httpStatus:      500,
		recoveryAction:  "retry",
		disruptionLevel: "snackbar",
		dartConst:       "deviceActionFailed",
		goConst:         "ErrDeviceActionFailed",
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
	EmittedBy []struct {
		Surface    string   `yaml:"surface"`
		Operations []string `yaml:"operations"`
	} `yaml:"emitted_by"`
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
		if len(definition.EmittedBy) != 1 ||
			definition.EmittedBy[0].Surface != "http" ||
			len(definition.EmittedBy[0].Operations) != 1 ||
			definition.EmittedBy[0].Operations[0] != "SubmitDeviceActionReceipt" {
			t.Fatalf("canonical device action error %s is not owned only by SubmitDeviceActionReceipt: %#v", code, definition.EmittedBy)
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
		for code := range canonicalDeviceActionFailureCodes {
			if counts[code] != 1 {
				t.Fatalf("SubmitDeviceActionReceipt binds %s %d times", code, counts[code])
			}
		}
	}
	if !foundSubmitReceipt {
		t.Fatal("SubmitDeviceActionReceipt operation is missing")
	}
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
