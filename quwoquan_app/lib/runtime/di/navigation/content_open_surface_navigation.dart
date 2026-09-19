import 'package:quwoquan_app/runtime/errors/generated/content/content_errors.g.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/runtime/transport/generated/client_content_presentation_contract.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show ContentUiSurface;
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

/// 云物化目的面 → App 路由的唯一映射。
///
/// 端侧只读列表信封的 `openSurface` 决定去哪；内容类型只在目的面内部选媒体槽或
/// 渲染分支，不参与目的地选择。目的面没有兼容替换：本端闭集外的面只能进入
/// typed 升级终态。
abstract final class ContentOpenSurfaceNavigation {
  /// 目的面在本端编译期闭集内且是可跳转的目的地。
  static bool canOpen(ContentUiSurface? openSurface) =>
      openSurface != null &&
      compiledContentPresentationContract.openSurfaces.contains(openSurface) &&
      _isDestination(openSurface);

  /// 返回该目的面的路由路径；`null` 表示这不是可跳转目的地。
  static String? pathFor({
    required ContentUiSurface openSurface,
    required String objectId,
    String? source,
    String? index,
    String? sourceTheme,
  }) => switch (openSurface) {
    // 侵入式浏览器与文章阅读共用同一路由壳，typed mode 在面内解析。
    ContentUiSurface.mediaImmersive || ContentUiSurface.articleReader =>
      AppRoutePaths.workBrowser(
        workId: objectId,
        source: source,
        index: index,
        sourceTheme: sourceTheme,
      ),
    ContentUiSurface.homepageDetail => AppRoutePaths.homepageDetail(
      id: objectId,
      sourceTheme: sourceTheme,
    ),
    // collection 面自身不是某一项的目的地。
    ContentUiSurface.homeFeed || ContentUiSurface.profileWorks => null,
  };

  /// 目的面缺席或不可消费时的 typed 终态。
  ///
  /// [contractChanged] 区分「本端不认识这个面」（需升级）与「信封没带目的面」
  /// （能力声明与交付不一致，刷新列表）。
  static RuntimeFailure unsupportedFailure({
    required bool contractChanged,
    required String objectId,
    ContentUiSurface? openSurface,
  }) {
    final code = contractChanged
        ? ContentErrorCode.presentationContractChanged
        : ContentErrorCode.presentationUnsupported;
    return RuntimeFailure(
      code: code.code,
      semanticReason: 'presentation_open_surface_unavailable',
      transportStatus: code.httpStatus,
      origin: RuntimeFailureOrigin.localClient,
      kind: RuntimeFailureKind.contract,
      nature: RuntimeFailureNature.permanent,
      location: const RuntimeFailureLocation(
        businessObject: 'content.post',
        functionModule: 'content_presentation',
      ),
      context: RuntimeFailureContext(
        attributes: <RuntimeContextAttribute>[
          RuntimeContextAttribute(key: 'objectId', value: objectId),
          RuntimeContextAttribute(
            key: 'openSurface',
            value: openSurface?.wireName ?? '',
          ),
        ],
      ),
      recovery: RuntimeRecoveryDirective(
        action: code.recoveryAction,
        afterSeconds: code.recoveryAfterSeconds,
      ),
    );
  }

  static bool _isDestination(ContentUiSurface surface) => switch (surface) {
    ContentUiSurface.mediaImmersive ||
    ContentUiSurface.articleReader ||
    ContentUiSurface.homepageDetail => true,
    ContentUiSurface.homeFeed || ContentUiSurface.profileWorks => false,
  };
}
