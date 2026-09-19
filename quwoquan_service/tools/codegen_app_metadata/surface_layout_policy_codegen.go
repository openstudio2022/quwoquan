package main

import (
	"fmt"
	"math"
	"path/filepath"
	"sort"
	"strings"
)

const (
	contentSurfaceLayoutOrigin  = "content/content/post/ui_config.yaml"
	profileSurfaceLayoutOrigin  = "user/account/user_account/ui_config.yaml"
	homepageSurfaceLayoutOrigin = "entity/entity_homepage/homepage/ui_config.yaml"
)

// generateSurfaceLayoutPolicies 是 CLI 的布局生成入口；校验失败不产生输出。
func generateSurfaceLayoutPolicies(
	metadataDir, appDir string,
	surfaces []string,
	contentUI, userUI *uiConfigFile,
) {
	if err := writeSurfaceLayoutPolicies(metadataDir, appDir, surfaces, contentUI, userUI); err != nil {
		exitErr(err)
	}
}

// writeSurfaceLayoutPolicies 在公开信封已把 ContentUiSurface 暴露到 contracts 包后调用。
// 输出通过既有 writeFile 自动登记到本轮 App generated manifest，不另建登记表。
func writeSurfaceLayoutPolicies(
	metadataDir, appDir string,
	surfaces []string,
	contentUI, userUI *uiConfigFile,
) error {
	policies, err := loadSurfaceLayoutPolicies(metadataDir, surfaces, contentUI, userUI)
	if err != nil {
		return err
	}
	writeFile(
		contentPostPresentationOutputPath(appDir, "surface_layout_policy.g.dart"),
		renderSurfaceLayoutPolicies(policies),
	)
	return nil
}

func loadSurfaceLayoutPolicies(
	metadataDir string,
	surfaces []string,
	contentUI, userUI *uiConfigFile,
) ([]surfaceLayoutPolicySource, error) {
	homepageUI, err := readUIConfig(
		filepath.Join(metadataDir, "entity", "entity_homepage", "homepage", "ui_config.yaml"),
		false,
	)
	if err != nil {
		return nil, fmt.Errorf("read %s: %w", homepageSurfaceLayoutOrigin, err)
	}
	declarations := map[string]*uiConfigFile{
		contentSurfaceLayoutOrigin:  contentUI,
		profileSurfaceLayoutOrigin:  userUI,
		homepageSurfaceLayoutOrigin: homepageUI,
	}
	policies, err := collectSurfaceLayoutPolicies(surfaces, declarations)
	if err != nil {
		return nil, fmt.Errorf("surface layout policies: %w", err)
	}
	return policies, nil
}

func renderSurfaceLayoutPolicies(policies []surfaceLayoutPolicySource) string {
	var b strings.Builder
	b.WriteString("// GENERATED FILE — DO NOT EDIT BY HAND.\n")
	b.WriteString("// Sources: 各 Surface owner 的 ui_config.yaml（逐项来源见下方）。\n")
	b.WriteString("// Regenerate: make codegen-app\n\n")
	b.WriteString("import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'\n    show ContentUiSurface;\n\n")
	b.WriteString(surfaceLayoutPolicyDartModel)
	b.WriteString("  /// 穷尽 canonical Surface；新增枚举成员而未重生成将编译失败。\n")
	b.WriteString("  static SurfaceLayoutPolicy forSurface(ContentUiSurface surface) =>\n      switch (surface) {\n")
	for _, source := range policies {
		policy := source.Policy
		fmt.Fprintf(&b, "        // Source: %s\n", source.Origin)
		fmt.Fprintf(&b, "        ContentUiSurface.%s => const SurfaceLayoutPolicy._(\n", canonicalDartEnumMemberName("ContentUiSurface", policy.Surface))
		fmt.Fprintf(&b, "          layoutKind: SurfaceLayoutKind.%s,\n", surfaceLayoutKinds[policy.LayoutKind])
		fmt.Fprintf(&b, "          compactColumns: %d,\n", policy.CompactColumns)
		fmt.Fprintf(&b, "          chromeFamily: %s,\n", strings.ReplaceAll(dartStringLiteral(policy.ChromeFamily), "$", "\\$"))
		fmt.Fprintf(&b, "          recipeDrivenChrome: %t,\n", policy.RecipeDrivenChrome)
		if grid := policy.ResponsiveGrid; grid != nil {
			fmt.Fprintf(&b, "          responsiveGrid: SurfaceResponsiveGrid(\n            expandedBreakpointDp: %s,\n            minColumns: %d,\n            maxColumns: %d,\n            idealColumnWidthDp: %s,\n          ),\n",
				dartDoubleLiteral(grid.ExpandedBreakpointDP, 0), grid.MinColumns, grid.MaxColumns, dartDoubleLiteral(grid.IdealColumnWidthDP, 0))
		}
		b.WriteString("        ),\n")
	}
	b.WriteString("      };\n}\n")
	return b.String()
}

const surfaceLayoutPolicyDartModel = `/// 布局家族不代表对象类型或卡片配方。
enum SurfaceLayoutKind { responsiveGrid, fullBleedPager, objectShell }

final class SurfaceResponsiveGrid {
  const SurfaceResponsiveGrid({
    required this.expandedBreakpointDp,
    required this.minColumns,
    required this.maxColumns,
    required this.idealColumnWidthDp,
  });

  final double expandedBreakpointDp;
  final int minColumns;
  final int maxColumns;
  final double idealColumnWidthDp;
}

/// 纯配置与视口函数；不接收 ContentType 或 FeedPresentationRecipe。
final class SurfaceLayoutPolicy {
  const SurfaceLayoutPolicy._({
    required this.layoutKind,
    required this.compactColumns,
    required this.chromeFamily,
    required this.recipeDrivenChrome,
    this.responsiveGrid,
  });

  final SurfaceLayoutKind layoutKind;
  final int compactColumns;
  final String chromeFamily;
  final bool recipeDrivenChrome;
  final SurfaceResponsiveGrid? responsiveGrid;

  /// widthDp 必须是扣除页面外围留白后的有限非负可用宽度。
  int columnsForWidth(double widthDp) {
    if (!widthDp.isFinite || widthDp < 0) {
      throw ArgumentError.value(widthDp, 'widthDp', '须为有限非负宽度');
    }
    final grid = responsiveGrid;
    if (grid == null || widthDp < grid.expandedBreakpointDp) {
      return compactColumns;
    }
    final idealColumns = widthDp / grid.idealColumnWidthDp;
    return idealColumns.clamp(grid.minColumns, grid.maxColumns).floor();
  }

`

// surfaceLayoutPolicySource 把一个 ContentUiSurface 的布局策略与它的声明文件绑定，
// 使「谁声明了这个面」在冲突报错里是精确的，而不是一句合并失败。
type surfaceLayoutPolicySource struct {
	Policy surfaceLayoutPolicyDef
	Origin string
}

var surfaceLayoutKinds = map[string]string{
	"responsive_grid":  "responsiveGrid",
	"full_bleed_pager": "fullBleedPager",
	"object_shell":     "objectShell",
}

// collectSurfaceLayoutPolicies 要求 ContentUiSurface 闭集被各服务 ui_config 恰好覆盖一次。
// 缺成员、重复声明、未知成员都 fail-closed：列数与 chrome 家族是单字段登记表，
// 少一个成员必须在生成期就断，而不是在端上退化成默认卡。
func collectSurfaceLayoutPolicies(
	surfaces []string,
	declarations map[string]*uiConfigFile,
) ([]surfaceLayoutPolicySource, error) {
	if len(surfaces) == 0 {
		return nil, fmt.Errorf("canonical ContentUiSurface enum is empty")
	}
	canonical := make(map[string]struct{}, len(surfaces))
	for _, surface := range surfaces {
		if surface == "" || surface != strings.TrimSpace(surface) {
			return nil, fmt.Errorf("invalid canonical ContentUiSurface member %q", surface)
		}
		if _, exists := canonical[surface]; exists {
			return nil, fmt.Errorf("duplicate canonical ContentUiSurface member %q", surface)
		}
		canonical[surface] = struct{}{}
	}
	if _, err := canonicalRequestEnumMembers(fieldDef{EnumRef: "ContentUiSurface"}, surfaces); err != nil {
		return nil, err
	}

	origins := make([]string, 0, len(declarations))
	for origin := range declarations {
		origins = append(origins, origin)
	}
	sort.Strings(origins)

	collected := map[string]surfaceLayoutPolicySource{}
	for _, origin := range origins {
		ui := declarations[origin]
		if ui == nil {
			continue
		}
		for _, policy := range ui.SurfaceLayoutPolicies {
			surface := policy.Surface
			if _, ok := canonical[surface]; !ok {
				return nil, fmt.Errorf(
					"%s declares surface_layout_policy for %q which is not a ContentUiSurface member",
					origin,
					surface,
				)
			}
			if previous, exists := collected[surface]; exists {
				return nil, fmt.Errorf(
					"surface_layout_policy for %q is declared by both %s and %s; a Surface has exactly one layout owner",
					surface,
					previous.Origin,
					origin,
				)
			}
			if err := validateSurfaceLayoutPolicy(origin, policy); err != nil {
				return nil, err
			}
			collected[surface] = surfaceLayoutPolicySource{Policy: policy, Origin: origin}
		}
	}

	missing := make([]string, 0)
	for _, surface := range surfaces {
		if _, ok := collected[surface]; !ok {
			missing = append(missing, surface)
		}
	}
	if len(missing) > 0 {
		return nil, fmt.Errorf(
			"ContentUiSurface members without a surface_layout_policy: %s",
			strings.Join(missing, ", "),
		)
	}

	ordered := make([]surfaceLayoutPolicySource, 0, len(surfaces))
	for _, surface := range surfaces {
		ordered = append(ordered, collected[surface])
	}
	return ordered, nil
}

func positiveFiniteLayoutDimension(value float64) bool {
	return value > 0 && !math.IsNaN(value) && !math.IsInf(value, 0)
}

func validateSurfaceLayoutPolicy(origin string, policy surfaceLayoutPolicyDef) error {
	kind := policy.LayoutKind
	if _, ok := surfaceLayoutKinds[kind]; !ok {
		return fmt.Errorf(
			"%s surface_layout_policy %q has unknown layout_kind %q",
			origin,
			policy.Surface,
			kind,
		)
	}
	if policy.CompactColumns < 1 {
		return fmt.Errorf(
			"%s surface_layout_policy %q requires a positive compact_columns",
			origin,
			policy.Surface,
		)
	}
	if strings.TrimSpace(policy.ChromeFamily) == "" {
		return fmt.Errorf(
			"%s surface_layout_policy %q requires chrome_family",
			origin,
			policy.Surface,
		)
	}
	if kind == "responsive_grid" {
		grid := policy.ResponsiveGrid
		if grid == nil {
			return fmt.Errorf(
				"%s surface_layout_policy %q is responsive_grid and must declare responsive_grid",
				origin,
				policy.Surface,
			)
		}
		if !positiveFiniteLayoutDimension(grid.ExpandedBreakpointDP) ||
			!positiveFiniteLayoutDimension(grid.IdealColumnWidthDP) ||
			grid.MinColumns < 1 ||
			grid.MaxColumns < grid.MinColumns ||
			policy.CompactColumns > grid.MaxColumns {
			return fmt.Errorf(
				"%s surface_layout_policy %q has an incomplete responsive_grid",
				origin,
				policy.Surface,
			)
		}
		return nil
	}
	if policy.CompactColumns != 1 {
		return fmt.Errorf(
			"%s surface_layout_policy %q is %s and requires exactly one compact column",
			origin, policy.Surface, kind,
		)
	}
	if policy.ResponsiveGrid != nil {
		return fmt.Errorf(
			"%s surface_layout_policy %q is %s and must not declare responsive_grid",
			origin,
			policy.Surface,
			kind,
		)
	}
	return nil
}
