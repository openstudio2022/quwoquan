/// Chat 域 pure Dart contract 的窄入口。
///
/// Alpha/test chat fixture 只依赖此入口，避免把其他领域 contract 拉入编译图。
library;

export 'src/chat/message_contracts.dart';
