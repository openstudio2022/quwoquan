import 'package:flutter_riverpod/flutter_riverpod.dart';

/// 登录后续接（post-login continuation）的统一真相源。
///
/// 受限「动作门」入口在拦截游客时，先把「用户原本想做的事」登记为一个
/// [AuthContinuation]，登录成功后由对应表面消费并续接，避免「登录回来后什么都没发生」。
///
/// 设计取舍（遵循抽象克制军规 R24）：
/// - 单槽位、强类型、显式 take：同一时刻只承接一个待续接动作，避免多通路状态。
/// - 不在 continuation 里捕获 BuildContext / 闭包：登录期间原表面可能重建，
///   消费方按类型取出后在自己的 context 内执行，杜绝跨页悬垂引用。
sealed class AuthContinuation {
  const AuthContinuation();
}

/// 续接「提交评论」：登录成功后按账号自动发出游客已输入的评论。
class SubmitCommentContinuation extends AuthContinuation {
  const SubmitCommentContinuation({
    required this.content,
    this.postId,
    this.replyToCommentId,
    this.attachmentMediaIds = const <String>[],
    this.mentions = const <Map<String, dynamic>>[],
  });

  final String content;
  final String? postId;
  final String? replyToCommentId;
  final List<String> attachmentMediaIds;
  final List<Map<String, dynamic>> mentions;
}

/// 续接「关注用户主页」。
class FollowProfileContinuation extends AuthContinuation {
  const FollowProfileContinuation({required this.subAccountId});

  final String subAccountId;
}

/// 续接「向用户主页打招呼」。
class GreetProfileContinuation extends AuthContinuation {
  const GreetProfileContinuation({required this.subAccountId});

  final String subAccountId;
}

/// 续接「打开或创建与用户的正式私信会话」。
class OpenDirectConversationContinuation extends AuthContinuation {
  const OpenDirectConversationContinuation({required this.subAccountId});

  final String subAccountId;
}

/// 续接「从用户主页发起 1v1 通话」。
class StartDirectCallContinuation extends AuthContinuation {
  const StartDirectCallContinuation({
    required this.targetUserId,
    required this.callType,
  });

  final String targetUserId;
  final String callType;
}

/// 续接「加入/关注圈子」。
class JoinCircleContinuation extends AuthContinuation {
  const JoinCircleContinuation({required this.circleId});

  final String circleId;
}

/// 续接「打开某个动作面板/流程」（添加联系人、发起群聊、建圈子等非路由动作）。
enum AuthContinuationSheet { addContact, startGroupChat, createCircle }

class OpenSheetContinuation extends AuthContinuation {
  const OpenSheetContinuation(this.sheet);

  final AuthContinuationSheet sheet;
}

/// 续接「打开首页内部频道」。用于关注频道这类不是独立稳定路由的内部状态：
/// 关闭登录页回安全首页，登录成功后再明确切到目标频道，避免 pop 回原触发点形成回环。
class OpenHomeChannelContinuation extends AuthContinuation {
  const OpenHomeChannelContinuation({required this.channelId});

  final String channelId;
}

/// 单槽位续接控制器：set 登记、take 按类型取出并清空。
class AuthContinuationController extends Notifier<AuthContinuation?> {
  @override
  AuthContinuation? build() => null;

  void set(AuthContinuation continuation) => state = continuation;

  void clear() => state = null;

  /// 取出并清空与 [T] 匹配的待续接动作；类型不匹配则返回 null 且不清空。
  T? take<T extends AuthContinuation>() {
    final current = state;
    if (current is T) {
      state = null;
      return current;
    }
    return null;
  }
}

final authContinuationProvider =
    NotifierProvider<AuthContinuationController, AuthContinuation?>(
      AuthContinuationController.new,
    );
