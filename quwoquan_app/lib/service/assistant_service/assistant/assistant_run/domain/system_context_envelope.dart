// 系统上下文信封契约由 assistant/system_context_envelope/schema.yaml 单轨拥有，
// serde 与类型定义均在生成体内；本文件只保留稳定的 library 入口。
// 历史上此处手写 fromJson 曾对 location 做 country/region/city 双键读，
// 收编进 schema 时已按契约单轨删除，wire 只认 canonical 单键。
export 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/domain/generated/system_context_envelope.g.dart';
