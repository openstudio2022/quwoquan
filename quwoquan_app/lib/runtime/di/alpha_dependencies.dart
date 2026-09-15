import 'package:quwoquan_app/runtime/config/app_content_source.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_config.dart';
import 'package:quwoquan_app/runtime/di/alpha_content_composition.dart';
import 'package:quwoquan_app/runtime/di/public_media_delivery_dependencies.dart';
import 'package:quwoquan_app/runtime/platform/media/bundled_public_media_delivery.dart';
import 'package:quwoquan_app/runtime/shell/startup/app_bootstrap.dart';

/// Alpha 制品的唯一装配入口；校验 source 后才安装真实包内读取器。
void configureAlphaDependencies() {
  configureAppContentComposition(() {
    if (CloudRuntimeConfig.contentSource != AppContentSource.bundledSnapshot) {
      throw StateError('Alpha composition requires a verified bundled source');
    }
    installAlphaContentComposition();
    installPublicMediaDelivery(BundledPublicMediaDelivery());
  });
}
