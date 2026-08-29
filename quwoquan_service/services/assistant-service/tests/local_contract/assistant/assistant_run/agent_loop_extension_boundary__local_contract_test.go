// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/skill-context-proactive-runtime/spec.md#gwt-001
// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/tool-fabric-runtime/spec.md#gwt-001
package assistant_run_test

import (
	"fmt"
	"go/ast"
	"go/parser"
	"go/token"
	"io/fs"
	"os"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
	"testing"
	"unicode"
)

type agentLoopBoundaryFinding struct {
	position token.Position
	rule     string
	detail   string
}

func (f agentLoopBoundaryFinding) String() string {
	return fmt.Sprintf(
		"%s:%d:%d: %s: %s",
		f.position.Filename,
		f.position.Line,
		f.position.Column,
		f.rule,
		f.detail,
	)
}

func TestProductionAgentLoopDoesNotBranchOnExtensionIdentity(t *testing.T) {
	t.Parallel()

	good := `package sample
import "strings"
func route(req Request, selectedSkillID, toolName, text string, failure Failure) {
	if strings.TrimSpace(req.ToolName) == "" {}
	if req.SkillID != selectedSkillID {}
	if strings.TrimSpace(req.ToolName) == strings.TrimSpace(toolName) {}
	switch failure.Category { case ProviderFailureCategoryRetryable: }
	if strings.EqualFold(text, "null") {}
}`
	if findings := agentLoopIdentityFindingsFromSource(
		t,
		"snippet/good.go",
		good,
	); len(findings) != 0 {
		t.Fatalf("allowed metadata/empty checks were rejected:\n%s", formatAgentLoopFindings(findings))
	}

	bad := []struct {
		name     string
		source   string
		identity string
	}{
		{
			name:     "tool name if",
			identity: "toolName",
			source: `package sample
func route(req Request) {
	if req.ToolName == "weather" {}
}`,
		},
		{
			name:     "skill id switch",
			identity: "skillId",
			source: `package sample
func route(skillID string) {
	switch skillID { case "travel_companion": }
}`,
		},
		{
			name:     "provider equal fold",
			identity: "provider",
			source: `package sample
import "strings"
func route(req Request) {
	if strings.EqualFold(req.Provider, "openai") {}
}`,
		},
		{
			name:     "domain id reversed comparison",
			identity: "domainId",
			source: `package sample
func route(req Request) {
	if "assistant.travel" != req.DomainID {}
}`,
		},
	}
	for _, test := range bad {
		t.Run(test.name, func(t *testing.T) {
			findings := agentLoopIdentityFindingsFromSource(
				t,
				"snippet/bad.go",
				test.source,
			)
			if len(findings) != 1 {
				t.Fatalf("findings=%d, want 1:\n%s", len(findings), formatAgentLoopFindings(findings))
			}
			if !strings.Contains(findings[0].detail, test.identity) ||
				findings[0].position.Line <= 0 {
				t.Fatalf("finding does not expose identity and path:line: %s", findings[0])
			}
		})
	}

	root := agentLoopBoundaryServiceRoot(t)
	var findings []agentLoopBoundaryFinding
	for _, relative := range []string{
		"internal/assistant/assistant_run/application/orchestration",
		"internal/assistant/assistant_run/application/reasoning",
		"internal/assistant/assistant_run/application/triggerruntime",
	} {
		found, err := agentLoopIdentityFindingsInTree(root, relative)
		if err != nil {
			t.Fatalf("scan %s: %v", relative, err)
		}
		findings = append(findings, found...)
	}
	if len(findings) != 0 {
		t.Fatalf(
			"production AgentLoop contains extension-identity routing branches:\n%s",
			formatAgentLoopFindings(findings),
		)
	}
}

func TestProductionProactiveDeliveryUsesCanonicalRunTerminalAnswer(t *testing.T) {
	t.Parallel()
	root := agentLoopBoundaryServiceRoot(t)
	backgroundPath := "cmd/api/composition_background_workers.go"
	backgroundSet, backgroundFile := agentLoopParseProductionFile(t, root, backgroundPath)
	background := agentLoopRequiredFunction(t, backgroundFile, "startAssistantBackgroundWorkers")
	agentLoopRequireCallArgumentPath(
		t,
		backgroundSet,
		background.Body,
		"scheduling.NewSkillSubscriptionScheduler",
		0,
		"assistant.service",
	)
	runtimePath := "cmd/api/composition_assistant_runtime.go"
	runtimeSet, runtimeFile := agentLoopParseProductionFile(t, root, runtimePath)
	wiring := agentLoopRequiredFunction(t, runtimeFile, "wireAssistantRuntime")
	agentLoopRequireCallArgumentPath(
		t,
		runtimeSet,
		wiring.Body,
		"sessionorchestration.WithRunCommandService",
		0,
		"runCommands",
	)

	canonicalPath := "internal/assistant/assistant_session/application/orchestration/canonical_run_dispatch.go"
	canonicalSet, canonicalFile := agentLoopParseProductionFile(t, root, canonicalPath)
	start := agentLoopRequiredFunction(t, canonicalFile, "startCanonicalRunAndWait")
	agentLoopRequireCallCount(t, canonicalSet, start.Body, "s.runCommands.Start", 1)
	agentLoopRequireCallCount(t, canonicalSet, start.Body, "s.runCommands.Get", 1)
	agentLoopRequireCallCount(t, canonicalSet, start.Body, "terminalCanonicalRun", 1)

	subscriptionPath := "internal/assistant/assistant_session/application/orchestration/skill_subscription_service.go"
	subscriptionSet, subscriptionFile := agentLoopParseProductionFile(t, root, subscriptionPath)
	deliver := agentLoopRequiredFunction(t, subscriptionFile, "createProactiveTurnMessage")
	agentLoopRequireCallCount(t, subscriptionSet, deliver.Body, "s.startCanonicalRunAndWait", 1)
	if !agentLoopContainsSelector(deliver.Body, "run.TerminalSnapshot.AnswerText") {
		t.Fatalf(
			"%s: createProactiveTurnMessage must read the canonical terminal snapshot answer",
			subscriptionPath,
		)
	}

	var bypasses []agentLoopBoundaryFinding
	bypasses = append(
		bypasses,
		agentLoopProactiveBypassFindings(canonicalSet, start.Body)...,
	)
	bypasses = append(
		bypasses,
		agentLoopProactiveBypassFindings(subscriptionSet, deliver.Body)...,
	)

	triggerRoot := "internal/assistant/assistant_run/application/triggerruntime"
	err := filepath.WalkDir(filepath.Join(root, triggerRoot), func(
		path string,
		entry fs.DirEntry,
		walkErr error,
	) error {
		if walkErr != nil {
			return walkErr
		}
		if entry.IsDir() || !strings.HasSuffix(entry.Name(), ".go") ||
			strings.HasSuffix(entry.Name(), "_test.go") {
			return nil
		}
		relative, err := filepath.Rel(root, path)
		if err != nil {
			return err
		}
		set, file, err := agentLoopParseFile(root, filepath.ToSlash(relative))
		if err != nil {
			return err
		}
		bypasses = append(bypasses, agentLoopProactiveBypassFindings(set, file)...)
		return nil
	})
	if err != nil {
		t.Fatalf("scan proactive trigger runtime: %v", err)
	}

	dispatchPath := filepath.Join(triggerRoot, "dispatcher.go")
	dispatchSet, dispatchFile := agentLoopParseProductionFile(t, root, dispatchPath)
	dispatch := agentLoopRequiredFunction(t, dispatchFile, "Dispatch")
	agentLoopRequireCallCount(t, dispatchSet, dispatch.Body, "d.runs.StartRun", 1)

	badSet, badFile := agentLoopParseSource(t, "snippet/proactive_bad.go", `package sample
func deliver(loop AgentLoop, model Model, tool ToolExecutor, answerQueue AnswerQueue) {
	loop.RunTurn()
	model.Complete()
	tool.Execute()
	answerQueue.Enqueue()
}`)
	badFindings := agentLoopProactiveBypassFindings(badSet, badFile)
	if len(badFindings) < 4 {
		t.Fatalf(
			"proactive bypass detector missed direct execution/queue snippets:\n%s",
			formatAgentLoopFindings(badFindings),
		)
	}
	if len(bypasses) != 0 {
		t.Fatalf(
			"proactive production bypasses canonical AssistantRun or terminal answer:\n%s",
			formatAgentLoopFindings(bypasses),
		)
	}
	queues, err := agentLoopRunAnswerQueueLiterals(root)
	if err != nil {
		t.Fatalf("scan AssistantRun answer queues: %v", err)
	}
	if len(queues) != 1 || queues[0].detail != `queue literal "assistant_run_work_queue"` {
		t.Fatalf(
			"AssistantRun must own exactly one canonical work queue:\n%s",
			formatAgentLoopFindings(queues),
		)
	}
}

func agentLoopBoundaryServiceRoot(t *testing.T) string {
	t.Helper()
	_, file, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("resolve AgentLoop extension boundary test path")
	}
	root := filepath.Clean(filepath.Join(filepath.Dir(file), "..", "..", "..", ".."))
	if _, err := os.Stat(filepath.Join(root, "cmd", "api", "bootstrap.go")); err != nil {
		t.Fatalf("resolve assistant-service root: %v", err)
	}
	return root
}

func agentLoopIdentityFindingsInTree(
	root string,
	relative string,
) ([]agentLoopBoundaryFinding, error) {
	var findings []agentLoopBoundaryFinding
	err := filepath.WalkDir(filepath.Join(root, relative), func(
		path string,
		entry fs.DirEntry,
		walkErr error,
	) error {
		if walkErr != nil {
			return walkErr
		}
		if entry.IsDir() || !strings.HasSuffix(entry.Name(), ".go") ||
			strings.HasSuffix(entry.Name(), "_test.go") {
			return nil
		}
		filePath, err := filepath.Rel(root, path)
		if err != nil {
			return err
		}
		set, file, err := agentLoopParseFile(root, filepath.ToSlash(filePath))
		if err != nil {
			return err
		}
		findings = append(findings, agentLoopIdentityFindings(set, file)...)
		return nil
	})
	return findings, err
}

func agentLoopIdentityFindingsFromSource(
	t *testing.T,
	path string,
	source string,
) []agentLoopBoundaryFinding {
	t.Helper()
	set, file := agentLoopParseSource(t, path, source)
	return agentLoopIdentityFindings(set, file)
}

func agentLoopIdentityFindings(
	set *token.FileSet,
	file *ast.File,
) []agentLoopBoundaryFinding {
	findings := []agentLoopBoundaryFinding{}
	add := func(node ast.Node, rule, identity, literal string) {
		findings = append(findings, agentLoopBoundaryFinding{
			position: set.Position(node.Pos()),
			rule:     rule,
			detail:   fmt.Sprintf("%s branches on non-empty literal %q", identity, literal),
		})
	}
	ast.Inspect(file, func(node ast.Node) bool {
		switch current := node.(type) {
		case *ast.BinaryExpr:
			if current.Op != token.EQL && current.Op != token.NEQ {
				return true
			}
			if identity, ok := agentLoopIdentity(current.X); ok {
				if literal, ok := agentLoopNonEmptyLiteral(current.Y); ok {
					add(current, "identity comparison", identity, literal)
				}
			}
			if identity, ok := agentLoopIdentity(current.Y); ok {
				if literal, ok := agentLoopNonEmptyLiteral(current.X); ok {
					add(current, "identity comparison", identity, literal)
				}
			}
		case *ast.SwitchStmt:
			identity, ok := agentLoopIdentity(current.Tag)
			if !ok {
				return true
			}
			for _, statement := range current.Body.List {
				clause, ok := statement.(*ast.CaseClause)
				if !ok {
					continue
				}
				for _, expression := range clause.List {
					if literal, ok := agentLoopNonEmptyLiteral(expression); ok {
						add(expression, "identity switch", identity, literal)
					}
				}
			}
		case *ast.CallExpr:
			if !agentLoopIsEqualFold(current.Fun) || len(current.Args) != 2 {
				return true
			}
			if identity, ok := agentLoopIdentity(current.Args[0]); ok {
				if literal, ok := agentLoopNonEmptyLiteral(current.Args[1]); ok {
					add(current, "identity EqualFold", identity, literal)
				}
			}
			if identity, ok := agentLoopIdentity(current.Args[1]); ok {
				if literal, ok := agentLoopNonEmptyLiteral(current.Args[0]); ok {
					add(current, "identity EqualFold", identity, literal)
				}
			}
		}
		return true
	})
	return findings
}

func agentLoopIdentity(expression ast.Expr) (string, bool) {
	switch current := expression.(type) {
	case nil:
		return "", false
	case *ast.ParenExpr:
		return agentLoopIdentity(current.X)
	case *ast.Ident:
		return agentLoopIdentityName(current.Name)
	case *ast.SelectorExpr:
		if identity, ok := agentLoopIdentityName(current.Sel.Name); ok {
			return identity, true
		}
	case *ast.CallExpr:
		for _, argument := range current.Args {
			if identity, ok := agentLoopIdentity(argument); ok {
				return identity, true
			}
		}
	case *ast.IndexExpr:
		if literal, ok := agentLoopStringLiteral(current.Index); ok {
			if identity, ok := agentLoopIdentityName(literal); ok {
				return identity, true
			}
		}
		return agentLoopIdentity(current.Index)
	}
	return "", false
}

func agentLoopIdentityName(name string) (string, bool) {
	normalized := agentLoopNormalizedName(name)
	switch {
	case strings.HasSuffix(normalized, "toolname") ||
		normalized == "requestedtool" || strings.HasSuffix(normalized, "requestedtool"):
		return "toolName", true
	case strings.HasSuffix(normalized, "skillid"):
		return "skillId", true
	case strings.HasSuffix(normalized, "domainid"):
		return "domainId", true
	case normalized == "provider" || strings.HasSuffix(normalized, "provider") ||
		strings.HasSuffix(normalized, "providerid") || strings.HasSuffix(normalized, "providername"):
		return "provider", true
	default:
		return "", false
	}
}

func agentLoopNormalizedName(value string) string {
	return strings.Map(func(current rune) rune {
		if unicode.IsLetter(current) || unicode.IsDigit(current) {
			return unicode.ToLower(current)
		}
		return -1
	}, value)
}

func agentLoopNonEmptyLiteral(expression ast.Expr) (string, bool) {
	value, ok := agentLoopStringLiteral(expression)
	return value, ok && strings.TrimSpace(value) != ""
}

func agentLoopStringLiteral(expression ast.Expr) (string, bool) {
	literal, ok := expression.(*ast.BasicLit)
	if !ok || literal.Kind != token.STRING {
		return "", false
	}
	value, err := strconv.Unquote(literal.Value)
	return value, err == nil
}

func agentLoopIsEqualFold(expression ast.Expr) bool {
	switch current := expression.(type) {
	case *ast.Ident:
		return current.Name == "EqualFold"
	case *ast.SelectorExpr:
		return current.Sel.Name == "EqualFold"
	default:
		return false
	}
}

func agentLoopParseProductionFile(
	t *testing.T,
	root string,
	relative string,
) (*token.FileSet, *ast.File) {
	t.Helper()
	set, file, err := agentLoopParseFile(root, relative)
	if err != nil {
		t.Fatalf("parse %s: %v", relative, err)
	}
	return set, file
}

func agentLoopParseFile(
	root string,
	relative string,
) (*token.FileSet, *ast.File, error) {
	payload, err := os.ReadFile(filepath.Join(root, filepath.FromSlash(relative)))
	if err != nil {
		return nil, nil, err
	}
	set := token.NewFileSet()
	file, err := parser.ParseFile(set, relative, payload, parser.AllErrors)
	return set, file, err
}

func agentLoopParseSource(
	t *testing.T,
	path string,
	source string,
) (*token.FileSet, *ast.File) {
	t.Helper()
	set := token.NewFileSet()
	file, err := parser.ParseFile(set, path, source, parser.AllErrors)
	if err != nil {
		t.Fatalf("parse %s: %v", path, err)
	}
	return set, file
}

func agentLoopRequiredFunction(
	t *testing.T,
	file *ast.File,
	name string,
) *ast.FuncDecl {
	t.Helper()
	for _, declaration := range file.Decls {
		function, ok := declaration.(*ast.FuncDecl)
		if ok && function.Name.Name == name && function.Body != nil {
			return function
		}
	}
	t.Fatalf("production function %s is missing", name)
	return nil
}

func agentLoopRequireCallCount(
	t *testing.T,
	set *token.FileSet,
	node ast.Node,
	wanted string,
	want int,
) {
	t.Helper()
	count := 0
	var positions []token.Position
	ast.Inspect(node, func(current ast.Node) bool {
		call, ok := current.(*ast.CallExpr)
		if ok && agentLoopSelectorPath(call.Fun) == wanted {
			count++
			positions = append(positions, set.Position(call.Pos()))
		}
		return true
	})
	if count != want {
		t.Fatalf("canonical call %s count=%d, want %d; positions=%v", wanted, count, want, positions)
	}
}

func agentLoopRequireCallArgumentPath(
	t *testing.T,
	set *token.FileSet,
	node ast.Node,
	wanted string,
	argumentIndex int,
	wantArgument string,
) {
	t.Helper()
	var matches []*ast.CallExpr
	ast.Inspect(node, func(current ast.Node) bool {
		call, ok := current.(*ast.CallExpr)
		if ok && agentLoopSelectorPath(call.Fun) == wanted {
			matches = append(matches, call)
		}
		return true
	})
	if len(matches) != 1 || len(matches[0].Args) <= argumentIndex ||
		agentLoopSelectorPath(matches[0].Args[argumentIndex]) != wantArgument {
		positions := make([]token.Position, 0, len(matches))
		for _, call := range matches {
			positions = append(positions, set.Position(call.Pos()))
		}
		t.Fatalf(
			"canonical call %s must receive %s at argument %d; positions=%v",
			wanted,
			wantArgument,
			argumentIndex,
			positions,
		)
	}
}

func agentLoopContainsSelector(node ast.Node, wanted string) bool {
	found := false
	ast.Inspect(node, func(current ast.Node) bool {
		if expression, ok := current.(ast.Expr); ok &&
			agentLoopSelectorPath(expression) == wanted {
			found = true
			return false
		}
		return !found
	})
	return found
}

func agentLoopSelectorPath(expression ast.Expr) string {
	switch current := expression.(type) {
	case *ast.Ident:
		return current.Name
	case *ast.SelectorExpr:
		prefix := agentLoopSelectorPath(current.X)
		if prefix == "" {
			return current.Sel.Name
		}
		return prefix + "." + current.Sel.Name
	case *ast.ParenExpr:
		return agentLoopSelectorPath(current.X)
	default:
		return ""
	}
}

func agentLoopProactiveBypassFindings(
	set *token.FileSet,
	node ast.Node,
) []agentLoopBoundaryFinding {
	findings := []agentLoopBoundaryFinding{}
	ast.Inspect(node, func(current ast.Node) bool {
		switch value := current.(type) {
		case *ast.CallExpr:
			path := agentLoopSelectorPath(value.Fun)
			parts := strings.Split(path, ".")
			method := parts[len(parts)-1]
			switch method {
			case "RunTurn", "RunTurnWithSink", "RunTurnWithSinkAfterSeq",
				"RunTurnWithPreparedExecution", "Complete", "Stream", "Execute":
				findings = append(findings, agentLoopBoundaryFinding{
					position: set.Position(value.Pos()),
					rule:     "proactive direct execution",
					detail:   "forbidden call " + path,
				})
			}
		case *ast.Ident:
			normalized := agentLoopNormalizedName(value.Name)
			for _, forbidden := range []string{
				"agentloop", "toolcoordinator", "toolexecutor", "toolregistry",
				"answergenerator", "answercomposer", "answerqueue", "answerstore",
				"answerrepository", "runqueue", "workqueue",
			} {
				if strings.Contains(normalized, forbidden) {
					findings = append(findings, agentLoopBoundaryFinding{
						position: set.Position(value.Pos()),
						rule:     "proactive second execution path",
						detail:   "forbidden symbol " + value.Name,
					})
					break
				}
			}
		case *ast.BasicLit:
			literal, ok := agentLoopStringLiteral(value)
			if ok && (strings.Contains(strings.ToLower(literal), "_queue") ||
				strings.Contains(strings.ToLower(literal), "answer_queue")) {
				findings = append(findings, agentLoopBoundaryFinding{
					position: set.Position(value.Pos()),
					rule:     "proactive second queue",
					detail:   fmt.Sprintf("forbidden queue literal %q", literal),
				})
			}
		}
		return true
	})
	return findings
}

func agentLoopRunAnswerQueueLiterals(
	root string,
) ([]agentLoopBoundaryFinding, error) {
	var findings []agentLoopBoundaryFinding
	sourceRoot := filepath.Join(root, "internal", "assistant")
	err := filepath.WalkDir(sourceRoot, func(
		path string,
		entry fs.DirEntry,
		walkErr error,
	) error {
		if walkErr != nil {
			return walkErr
		}
		if entry.IsDir() || !strings.HasSuffix(entry.Name(), ".go") ||
			strings.HasSuffix(entry.Name(), "_test.go") {
			return nil
		}
		relative, err := filepath.Rel(root, path)
		if err != nil {
			return err
		}
		set, file, err := agentLoopParseFile(root, filepath.ToSlash(relative))
		if err != nil {
			return err
		}
		ast.Inspect(file, func(current ast.Node) bool {
			call, ok := current.(*ast.CallExpr)
			if !ok || len(call.Args) == 0 {
				return true
			}
			selector, ok := call.Fun.(*ast.SelectorExpr)
			if !ok || selector.Sel.Name != "Collection" {
				return true
			}
			value, ok := agentLoopStringLiteral(call.Args[0])
			if !ok {
				return true
			}
			normalized := agentLoopNormalizedName(value)
			if !strings.Contains(normalized, "answerqueue") &&
				!(strings.Contains(normalized, "assistantrun") &&
					strings.Contains(normalized, "queue")) {
				return true
			}
			findings = append(findings, agentLoopBoundaryFinding{
				position: set.Position(call.Args[0].Pos()),
				rule:     "AssistantRun queue ownership",
				detail:   fmt.Sprintf("queue literal %q", value),
			})
			return true
		})
		return nil
	})
	return findings, err
}

func formatAgentLoopFindings(findings []agentLoopBoundaryFinding) string {
	if len(findings) == 0 {
		return "(none)"
	}
	lines := make([]string, 0, len(findings))
	for _, finding := range findings {
		lines = append(lines, finding.String())
	}
	return strings.Join(lines, "\n")
}
