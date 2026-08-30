/// runtime/di 入口：统一展示模型映射器收敛为 domain 单一实现（DEC-033）。
///
/// 此前这里保留了一份与 domain 版逐字相同的拷贝，构成第二真相源，且媒体
/// 资产标识以 `dto.id`（postId）冒充。现收敛为 re-export，消费方 import
/// 路径不变，实现只存在于
/// `service/content_service/content/post/domain/content_surface_view_mapper.dart`。
library;

export 'package:quwoquan_app/service/content_service/content/post/domain/content_surface_view_mapper.dart';
