package main

import (
	"encoding/json"
	"math"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"

	contractcodegen "quwoquan_service/internal/metadata/codegen"
	"quwoquan_service/internal/testsupport/contractsview"
)

func responsiveGridPolicy(surface string) surfaceLayoutPolicyDef {
	return surfaceLayoutPolicyDef{
		Surface:        surface,
		LayoutKind:     "responsive_grid",
		CompactColumns: 1,
		ChromeFamily:   "feed_presentation_recipe",
		ResponsiveGrid: &surfaceResponsiveGridDef{
			ExpandedBreakpointDP: 600,
			MinColumns:           2,
			MaxColumns:           4,
			IdealColumnWidthDP:   220,
		},
	}
}

func objectShellPolicy(surface string) surfaceLayoutPolicyDef {
	return surfaceLayoutPolicyDef{
		Surface:        surface,
		LayoutKind:     "object_shell",
		CompactColumns: 1,
		ChromeFamily:   surface + "_object_shell",
	}
}

func focusedPagerPolicy(surface string) surfaceLayoutPolicyDef {
	policy := objectShellPolicy(surface)
	policy.LayoutKind = "full_bleed_pager"
	return policy
}

// spec_ref: specs/feature-tree/discovery-content/content-type-framework/spec.md#req-003
func TestCollectSurfaceLayoutPoliciesFailsClosedOnCoverageGapsWithInvalidGeometry(t *testing.T) {
	cases := []struct {
		name   string
		policy surfaceLayoutPolicyDef
		mutate func(*surfaceLayoutPolicyDef)
	}{
		{"pager multiple columns", focusedPagerPolicy("media_immersive"), func(p *surfaceLayoutPolicyDef) { p.CompactColumns = 2 }},
		{"object shell multiple columns", objectShellPolicy("homepage_detail"), func(p *surfaceLayoutPolicyDef) { p.CompactColumns = 2 }},
		{"compact exceeds expanded maximum", responsiveGridPolicy("home_feed"), func(p *surfaceLayoutPolicyDef) { p.CompactColumns = 5 }},
		{"nonfinite breakpoint", responsiveGridPolicy("home_feed"), func(p *surfaceLayoutPolicyDef) { p.ResponsiveGrid.ExpandedBreakpointDP = math.Inf(1) }},
		{"nan ideal width", responsiveGridPolicy("profile_works"), func(p *surfaceLayoutPolicyDef) { p.ResponsiveGrid.IdealColumnWidthDP = math.NaN() }},
		{"pager responsive grid", focusedPagerPolicy("article_reader"), func(p *surfaceLayoutPolicyDef) { p.ResponsiveGrid = responsiveGridPolicy("home_feed").ResponsiveGrid }},
		{"kind whitespace alias", focusedPagerPolicy("article_reader"), func(p *surfaceLayoutPolicyDef) { p.LayoutKind = " full_bleed_pager " }},
		{"zero breakpoint", responsiveGridPolicy("home_feed"), func(p *surfaceLayoutPolicyDef) { p.ResponsiveGrid.ExpandedBreakpointDP = 0 }},
		{"inverted limits", responsiveGridPolicy("home_feed"), func(p *surfaceLayoutPolicyDef) { p.ResponsiveGrid.MinColumns = 5 }},
		{"missing grid", responsiveGridPolicy("home_feed"), func(p *surfaceLayoutPolicyDef) { p.ResponsiveGrid = nil }},
		{"missing chrome", focusedPagerPolicy("article_reader"), func(p *surfaceLayoutPolicyDef) { p.ChromeFamily = "" }},
		{"zero compact columns", responsiveGridPolicy("home_feed"), func(p *surfaceLayoutPolicyDef) { p.CompactColumns = 0 }},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			tc.mutate(&tc.policy)
			if err := validateSurfaceLayoutPolicy("test/ui_config.yaml", tc.policy); err == nil {
				t.Fatal("invalid layout geometry was accepted")
			}
		})
	}
}

// TestCollectSurfaceLayoutPoliciesFailsClosedOnCoverageGaps 直接驱动闭集覆盖判定。
// 覆盖判据必须在缺成员、重复 owner 与未知成员三种破口上都返回 error；否则少一个
// Surface 的布局策略会一路生成到端上退化成默认卡。
func TestCollectSurfaceLayoutPoliciesFailsClosedOnCoverageGaps(t *testing.T) {
	surfaces := []string{
		"home_feed",
		"profile_works",
		"media_immersive",
		"article_reader",
		"homepage_detail",
	}
	content := &uiConfigFile{SurfaceLayoutPolicies: []surfaceLayoutPolicyDef{
		responsiveGridPolicy("home_feed"),
		focusedPagerPolicy("media_immersive"),
		focusedPagerPolicy("article_reader"),
	}}
	user := &uiConfigFile{SurfaceLayoutPolicies: []surfaceLayoutPolicyDef{
		responsiveGridPolicy("profile_works"),
	}}
	homepage := &uiConfigFile{SurfaceLayoutPolicies: []surfaceLayoutPolicyDef{
		objectShellPolicy("homepage_detail"),
	}}
	complete := map[string]*uiConfigFile{
		contentSurfaceLayoutOrigin:  content,
		profileSurfaceLayoutOrigin:  user,
		homepageSurfaceLayoutOrigin: homepage,
	}

	ordered, err := collectSurfaceLayoutPolicies(surfaces, complete)
	if err != nil {
		t.Fatalf("complete coverage must resolve: %v", err)
	}
	if len(ordered) != len(surfaces) {
		t.Fatalf("resolved policies = %d, want %d", len(ordered), len(surfaces))
	}
	for index, surface := range surfaces {
		if ordered[index].Policy.Surface != surface {
			t.Fatalf(
				"policy %d is %q, want canonical enum order %q",
				index,
				ordered[index].Policy.Surface,
				surface,
			)
		}
		if strings.TrimSpace(ordered[index].Origin) == "" {
			t.Fatalf("policy %q resolved without a declaring origin", surface)
		}
	}

	for _, negative := range []struct {
		name         string
		declarations map[string]*uiConfigFile
		wantContains string
	}{
		{
			name: "homepage_detail 的策略被摔掉",
			declarations: map[string]*uiConfigFile{
				contentSurfaceLayoutOrigin:  content,
				profileSurfaceLayoutOrigin:  user,
				homepageSurfaceLayoutOrigin: {},
			},
			wantContains: "homepage_detail",
		},
		{
			name: "homepage_detail 的 owner 文件整体缺席",
			declarations: map[string]*uiConfigFile{
				contentSurfaceLayoutOrigin: content,
				profileSurfaceLayoutOrigin: user,
			},
			wantContains: "homepage_detail",
		},
		{
			name: "同一个面被两个 owner 声明",
			declarations: map[string]*uiConfigFile{
				contentSurfaceLayoutOrigin: content,
				profileSurfaceLayoutOrigin: user,
				homepageSurfaceLayoutOrigin: {SurfaceLayoutPolicies: []surfaceLayoutPolicyDef{
					objectShellPolicy("homepage_detail"),
					responsiveGridPolicy("home_feed"),
				}},
			},
			wantContains: "exactly one layout owner",
		},
		{
			name: "声明了闭集外的面",
			declarations: map[string]*uiConfigFile{
				contentSurfaceLayoutOrigin: content,
				profileSurfaceLayoutOrigin: user,
				homepageSurfaceLayoutOrigin: {SurfaceLayoutPolicies: []surfaceLayoutPolicyDef{
					objectShellPolicy("homepage_detail"),
					objectShellPolicy("search_results"),
				}},
			},
			wantContains: "not a ContentUiSurface member",
		},
	} {
		t.Run(negative.name, func(t *testing.T) {
			_, err := collectSurfaceLayoutPolicies(surfaces, negative.declarations)
			if err == nil {
				t.Fatal("coverage gap resolved without error")
			}
			if !strings.Contains(err.Error(), negative.wantContains) {
				t.Fatalf("error %q does not name %q", err, negative.wantContains)
			}
		})
	}

	for _, invalid := range [][]string{nil, {""}, {" home_feed "}, {"home_feed", "home_feed"}, {"home_feed", "home-feed"}} {
		if _, err := collectSurfaceLayoutPolicies(invalid, complete); err == nil {
			t.Fatalf("invalid ContentUiSurface enum %v resolved without error", invalid)
		}
	}
}

// TestRepositorySurfaceLayoutPoliciesCoverContentUiSurface 把闭集覆盖绑定到仓内
// 真实 ui_config authoring source。codegen-app 主流程在 handoff 前置断时不会跑到
// verifySurfaceLayoutPolicies，所以覆盖判定必须自己有一条可独立执行的 gate。
func TestRepositorySurfaceLayoutPoliciesCoverContentUiSurface(t *testing.T) {
	metadataDir := contractsview.Build(t)
	// 该生成器只读四份声明；独立证据不把无关 operation readiness 当作布局前置条件。
	source, err := contractcodegen.NewDocumentSource(metadataDir, []string{
		"_shared/types.yaml", contentSurfaceLayoutOrigin, profileSurfaceLayoutOrigin, homepageSurfaceLayoutOrigin,
	})
	if err != nil {
		t.Fatal(err)
	}
	previousSource, previousRoot := activeMetadataSource, activeMetadataRoot
	activeMetadataSource = source
	activeMetadataRoot = metadataDir
	t.Cleanup(func() { activeMetadataSource, activeMetadataRoot = previousSource, previousRoot })

	shared, err := readShared(filepath.Join(metadataDir, "_shared", "types.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	surfaces := shared.Enums["ContentUiSurface"]
	if len(surfaces) == 0 {
		t.Fatal("_shared/types.yaml declares no ContentUiSurface members")
	}

	declarations := map[string]*uiConfigFile{}
	for origin, relative := range map[string][]string{
		contentSurfaceLayoutOrigin:  {"content", "content", "post", "ui_config.yaml"},
		profileSurfaceLayoutOrigin:  {"user", "account", "user_account", "ui_config.yaml"},
		homepageSurfaceLayoutOrigin: {"entity", "entity_homepage", "homepage", "ui_config.yaml"},
	} {
		ui, readErr := readUIConfig(
			filepath.Join(append([]string{metadataDir}, relative...)...),
			false,
		)
		if readErr != nil {
			t.Fatalf("read %s: %v", origin, readErr)
		}
		declarations[origin] = ui
	}

	policies, err := collectSurfaceLayoutPolicies(surfaces, declarations)
	if err != nil {
		t.Fatalf("surface layout policies: %v", err)
	}
	// spec_ref: specs/feature-tree/discovery-content/content-type-framework/spec.md#req-003
	want := map[string]struct {
		kind    string
		compact int
		recipe  bool
	}{
		"home_feed":       {"responsive_grid", 1, true},
		"profile_works":   {"responsive_grid", 2, false},
		"media_immersive": {"full_bleed_pager", 1, false},
		"article_reader":  {"full_bleed_pager", 1, false},
		"homepage_detail": {"object_shell", 1, false},
	}
	for _, item := range policies {
		policy := item.Policy
		expected, exists := want[policy.Surface]
		if !exists {
			t.Fatalf("new surface %q requires an explicit layout acceptance", policy.Surface)
		}
		if policy.LayoutKind != expected.kind || policy.CompactColumns != expected.compact || policy.RecipeDrivenChrome != expected.recipe {
			t.Errorf("surface %s matrix drift: %+v", policy.Surface, policy)
		}
		if grid := policy.ResponsiveGrid; grid != nil {
			if grid.MinColumns != 2 || grid.MaxColumns != 4 || grid.ExpandedBreakpointDP != 600 || grid.IdealColumnWidthDP != 220 {
				t.Errorf("surface %s expanded layout drift: %+v", policy.Surface, grid)
			}
		}
	}
	t.Run("temporary App output and manifest", func(t *testing.T) {
		appDir := t.TempDir()
		oldRoot, oldGraph, oldOutputs := generatedManifestAppRoot, generatedManifestGraph, generatedManifestOutputs
		generatedManifestAppRoot, generatedManifestGraph = appDir, "surface-layout-test"
		generatedManifestOutputs = map[string]generatedOutput{}
		t.Cleanup(func() {
			generatedManifestAppRoot, generatedManifestGraph, generatedManifestOutputs = oldRoot, oldGraph, oldOutputs
		})
		if err := writeSurfaceLayoutPolicies(metadataDir, appDir, surfaces, declarations[contentSurfaceLayoutOrigin], declarations[profileSurfaceLayoutOrigin]); err != nil {
			t.Fatal(err)
		}
		output := contentPostPresentationOutputPath(appDir, "surface_layout_policy.g.dart")
		data, err := os.ReadFile(output)
		if err != nil {
			t.Fatal(err)
		}
		relative, err := filepath.Rel(appDir, output)
		if err != nil {
			t.Fatal(err)
		}
		entry, ok := generatedManifestOutputs[filepath.ToSlash(relative)]
		if !ok || entry.Bytes != len(data) || entry.ContractGraphSHA256 != "surface-layout-test" || entry.Owner != appOnlyEmitter {
			t.Fatalf("output missing existing manifest provenance: %+v", entry)
		}
		assertSurfaceLayoutDart(t, string(data), surfaces)
		runSurfaceLayoutDart(t, appDir, output, surfaces, policies)
	})
}

// spec_ref: specs/feature-tree/discovery-content/content-type-framework/spec.md#req-003
func assertSurfaceLayoutDart(t *testing.T, output string, surfaces []string) {
	t.Helper()
	for _, want := range []string{
		"package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart",
		"show ContentUiSurface;", "final class SurfaceLayoutPolicy",
		"switch (surface)", "int columnsForWidth(double widthDp)",
	} {
		if !strings.Contains(output, want) {
			t.Errorf("generated Dart missing %q", want)
		}
	}
	for _, forbidden := range []string{"enum ContentUiSurface", "_ =>", "default:", "Map<String", "contentType", "presentationRecipe"} {
		if strings.Contains(output, forbidden) {
			t.Errorf("generated Dart contains forbidden fallback or alternate axis %q", forbidden)
		}
	}
	if got := strings.Count(output, "=> const SurfaceLayoutPolicy._("); got != len(surfaces) {
		t.Fatalf("surface switch has %d entries, want %d", got, len(surfaces))
	}
	for _, surface := range surfaces {
		member := canonicalDartEnumMemberName("ContentUiSurface", surface)
		if strings.Count(output, "ContentUiSurface."+member+" =>") != 1 {
			t.Errorf("surface %s does not have exactly one typed entry", surface)
		}
	}
}

func writeSurfaceLayoutTestFile(t *testing.T, path, content string) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(path), 0755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, []byte(content), 0644); err != nil {
		t.Fatal(err)
	}
}

// 测试包的枚举同样由 canonical emitter 生成，不手写第二份 Surface 闭集。
func surfaceLayoutTestContracts(t *testing.T, surfaces []string) string {
	t.Helper()
	members, err := canonicalRequestEnumMembers(fieldDef{EnumRef: "ContentUiSurface"}, surfaces)
	if err != nil {
		t.Fatal(err)
	}
	var output strings.Builder
	renderDomainWireEnum(&output, "ContentUiSurface", members, "")
	return output.String()
}

func runSurfaceLayoutDart(t *testing.T, appDir, output string, surfaces []string, policies []surfaceLayoutPolicySource) {
	t.Helper()
	dart, err := exec.LookPath("dart")
	if err != nil {
		t.Skip("Dart SDK unavailable; generated output assertions completed")
	}
	contracts := filepath.Join(appDir, "packages", "quwoquan_cloud_contracts", "lib", "quwoquan_cloud_contracts.dart")
	writeSurfaceLayoutTestFile(t, contracts, surfaceLayoutTestContracts(t, surfaces))
	writeSurfaceLayoutTestFile(t, filepath.Join(appDir, ".dart_tool", "package_config.json"), `{"configVersion":2,"packages":[{"name":"quwoquan_cloud_contracts","rootUri":"../packages/quwoquan_cloud_contracts","packageUri":"lib/","languageVersion":"3.6"}]}`)
	runner := filepath.Join(filepath.Dir(output), "surface_layout_test.dart")
	writeSurfaceLayoutTestFile(t, runner, surfaceLayoutDartAcceptance)
	cmd := exec.Command(dart, runner)
	cmd.Dir = appDir
	result, err := cmd.CombinedOutput()
	if err != nil {
		t.Fatalf("generated Dart layout runtime failed: %v\n%s", err, result)
	}
	var got map[string][]int
	if err := json.Unmarshal(result, &got); err != nil {
		t.Fatalf("decode Dart geometry: %v\n%s", err, result)
	}
	for _, surface := range surfaces {
		want := []int{1, 1, 1, 1, 1, 1, 1, 1, 1}
		if surface == "home_feed" {
			want = []int{1, 1, 2, 2, 3, 3, 4, 4, 4}
		} else if surface == "profile_works" {
			want = []int{2, 2, 2, 2, 3, 3, 4, 4, 4}
		}
		actual := got[surface]
		if len(actual) != len(want) {
			t.Fatalf("surface %s widths = %v", surface, actual)
		}
		for index, columns := range want {
			if actual[index] != columns {
				t.Errorf("surface %s width index %d got %d want %d", surface, index, actual[index], columns)
			}
		}
	}
	// 改变声明后直接运行新产物，证明公式未硬编码当前 600/220/2–4 配置。
	custom := append([]surfaceLayoutPolicySource{}, policies...)
	for index := range custom {
		if custom[index].Policy.ResponsiveGrid != nil {
			custom[index].Policy.CompactColumns = 3
			custom[index].Policy.ChromeFamily = "literal_$chrome"
			custom[index].Policy.ResponsiveGrid = &surfaceResponsiveGridDef{
				ExpandedBreakpointDP: 960, IdealColumnWidthDP: 300, MinColumns: 1, MaxColumns: 5,
			}
		}
	}
	writeSurfaceLayoutTestFile(t, output, renderSurfaceLayoutPolicies(custom))
	customRunner := `import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'surface_layout_policy.g.dart';
void main() {
  for (final surface in ContentUiSurface.values) {
    final policy = SurfaceLayoutPolicy.forSurface(surface);
    if (policy.responsiveGrid == null) continue;
    final actual = [for (final w in [959.999, 960.0, 1199.999, 1200.0, 1500.0]) policy.columnsForWidth(w)];
    if (actual.join(',') != '3,3,3,4,5') throw StateError('$actual');
    if (policy.chromeFamily != r'literal_$chrome') throw StateError('chrome interpolation');
  }
}
`
	writeSurfaceLayoutTestFile(t, runner, customRunner)
	cmd = exec.Command(dart, runner)
	cmd.Dir = appDir
	if result, err := cmd.CombinedOutput(); err != nil {
		t.Fatalf("custom responsive configuration failed: %v\n%s", err, result)
	}
	// 模拟只更新 contracts 枚举而漏重生成登记表：总 switch 必须编译失败。
	writeSurfaceLayoutTestFile(t, contracts, surfaceLayoutTestContracts(t, append(append([]string{}, surfaces...), "test_new_surface")))
	cmd = exec.Command(dart, runner)
	cmd.Dir = appDir
	result, err = cmd.CombinedOutput()
	if err == nil || !strings.Contains(string(result), "not exhaustively matched") {
		t.Fatalf("new canonical member did not break exhaustive switch: %v\n%s", err, result)
	}
}

const surfaceLayoutDartAcceptance = `import 'dart:convert';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'surface_layout_policy.g.dart';

void main() {
  final result = <String, List<int>>{};
  for (final surface in ContentUiSurface.values) {
    final policy = SurfaceLayoutPolicy.forSurface(surface);
    result[surface.wireName] = [
      for (final width in [0.0, 599.999, 600.0, 659.999, 660.0, 879.999, 880.0, 960.0, double.maxFinite])
        policy.columnsForWidth(width),
    ];
    for (final width in [-1.0, double.nan, double.infinity, double.negativeInfinity]) {
      var rejected = false;
      try {
        policy.columnsForWidth(width);
      } on ArgumentError {
        rejected = true;
      }
      if (!rejected) throw StateError('invalid width accepted: $width');
    }
  }
  print(jsonEncode(result));
}
`
