/// 通用图片原子获取 CDN 变体 URL 的端口。
///
/// 通用组件只声明「需要按变体拿到投递 URL」这一能力，具体 CDN 处理参数、可信
/// host 判定与变体策略属于 content 域；实现由组合根 `lib/runtime/di/**` 注入，
/// 因此本文件不得 import 任何 domain 实现。
abstract interface class CdnImageUrlPort {
  String thumbnail(String url);

  String cover(String url);

  String display(String url);

  String avatar(String url, {required int size});

  String full(String url);
}
