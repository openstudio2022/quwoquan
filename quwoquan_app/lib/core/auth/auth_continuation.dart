import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

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
    this.mentions = const <CommentMention>[],
  });

  final String content;
  final String? postId;
  final String? replyToCommentId;
  final List<String> attachmentMediaIds;
  final List<CommentMention> mentions;
}

/// 举报动作的原始表面；登录成功后只允许该表面消费，避免首页与沉浸浏览器抢占。
enum ContentReportContinuationSurface { homeFeed, workBrowser }

/// 续接「举报帖子」。
class SubmitContentReportContinuation extends AuthContinuation {
  const SubmitContentReportContinuation({
    required this.postId,
    required this.surface,
    required this.reason,
  });

  final String postId;
  final ContentReportContinuationSurface surface;
  final ReportReason reason;
}

/// 续接「举报评论」；由原 CommentThread surface 按 postId 消费。
class SubmitCommentReportContinuation extends AuthContinuation {
  const SubmitCommentReportContinuation({
    required this.postId,
    required this.commentId,
    required this.reason,
  });

  final String postId;
  final String commentId;
  final ReportReason reason;
}

enum ContentModerationContinuationSurface { homeFeed, workBrowser }

enum ContentModerationContinuationAction { blockAuthor, blockKeyword }

/// 更多面板账号态治理动作；登录后由原表面按 postId 恢复。
class ContentModerationContinuation extends AuthContinuation {
  const ContentModerationContinuation({
    required this.postId,
    required this.surface,
    required this.action,
    this.authorId,
    this.keyword,
  });

  final String postId;
  final ContentModerationContinuationSurface surface;
  final ContentModerationContinuationAction action;
  final String? authorId;
  final String? keyword;
}

/// 续接「请求当前图片的原图访问授权」。
class RequestOriginalImageAccessContinuation extends AuthContinuation {
  const RequestOriginalImageAccessContinuation({
    required this.postId,
    required this.mediaId,
    required this.imageIndex,
  });

  final String postId;
  final String mediaId;
  final int imageIndex;
}

/// 站内分享的目标流程。
enum ContentShareContinuationTarget {
  recentRecipient,
  circlePlacement,
  groupChat,
  directMessage,
}

/// 续接「把内容分享到站内目标」。
///
/// 最近联系人只保存稳定 recipient id；登录后由仍在前台的分享面板重新读取真实
/// 会话并匹配，避免把会话 DTO 或 Widget 闭包塞进全局续接槽位。
class ShareContentContinuation extends AuthContinuation {
  const ShareContentContinuation({
    required this.postId,
    required this.target,
    this.recipientId,
  });

  final String postId;
  final ContentShareContinuationTarget target;
  final String? recipientId;
}

/// 创作页重新鉴权后可恢复的原动作。
enum CreateActionContinuationKind { publish, pickImages, pickVideo }

class ResumeCreateActionContinuation extends AuthContinuation {
  const ResumeCreateActionContinuation({
    required this.action,
    this.closeWhenEmptyOnCancel = false,
  });

  final CreateActionContinuationKind action;
  final bool closeWhenEmptyOnCancel;
}

/// 需要登录后恢复的实体主页写动作。
enum HomepageWriteContinuationAction {
  claim,
  maintenance,
  statusReport,
  suggest,
}

/// 登录后让原实体主页表面恢复到前台，并在需要时续提已填写表单。
///
/// 表单数据仍由页面状态持有；这里只保存稳定目标身份，避免把动态载荷或闭包放入全局槽位。
class HomepageWriteContinuation extends AuthContinuation {
  const HomepageWriteContinuation({
    required this.action,
    this.homepageId = '',
    this.submitAfterLogin = false,
  });

  final HomepageWriteContinuationAction action;
  final String homepageId;
  final bool submitAfterLogin;
}

/// 续接「关注实体主页」。
class FollowHomepageContinuation extends AuthContinuation {
  const FollowHomepageContinuation({required this.homepageId});

  final String homepageId;
}

/// 续接「把可到访实体主页标记为想去」。
class WishlistHomepageContinuation extends AuthContinuation {
  const WishlistHomepageContinuation({required this.homepageId});

  final String homepageId;
}

/// 续接「打开实体主页评价编辑器」。
class OpenHomepageReviewComposerContinuation extends AuthContinuation {
  const OpenHomepageReviewComposerContinuation({required this.homepageId});

  final String homepageId;
}

/// 续接「打开实体主页已认领主体的正式私信会话」。
class OpenHomepageOwnerConversationContinuation extends AuthContinuation {
  const OpenHomepageOwnerConversationContinuation({
    required this.homepageId,
    required this.ownerPersonaId,
  });

  final String homepageId;
  final String ownerPersonaId;
}

/// 续接「关注用户主页」。
class FollowProfileContinuation extends AuthContinuation {
  const FollowProfileContinuation({required this.personaId});

  final String personaId;
}

/// 续接「向用户主页打招呼」。
class GreetProfileContinuation extends AuthContinuation {
  const GreetProfileContinuation({required this.personaId});

  final String personaId;
}

/// 续接「打开或创建与用户的正式私信会话」。
class OpenDirectConversationContinuation extends AuthContinuation {
  const OpenDirectConversationContinuation({required this.personaId});

  final String personaId;
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

/// 游客首启兴趣在登录成功后恢复同一稳定行为 intent。
class SubmitOnboardingInterestContinuation extends AuthContinuation {
  const SubmitOnboardingInterestContinuation({
    required this.taxonomyReleaseId,
    required this.clientEventId,
    required this.tagRefs,
  });

  final String taxonomyReleaseId;
  final String clientEventId;
  final List<String> tagRefs;
}

/// 单槽位续接控制器：set 登记、take 按类型取出并清空。
class AuthContinuationController extends Notifier<AuthContinuation?> {
  String? _ownerToken;

  @override
  AuthContinuation? build() => null;

  /// 已有待续接动作时拒绝被另一个入口静默覆盖。
  bool set(AuthContinuation continuation, {String? ownerToken}) {
    if (state != null) {
      return false;
    }
    _ownerToken =
        ownerToken ??
        '${continuation.runtimeType}:${DateTime.now().microsecondsSinceEpoch}';
    state = continuation;
    return true;
  }

  void clear() {
    _ownerToken = null;
    state = null;
  }

  /// 取出并清空与 [T] 匹配的待续接动作；类型不匹配则返回 null 且不清空。
  T? take<T extends AuthContinuation>() {
    final current = state;
    if (current is T) {
      _ownerToken = null;
      state = null;
      return current;
    }
    return null;
  }

  String? get ownerToken => _ownerToken;
}

final authContinuationProvider =
    NotifierProvider<AuthContinuationController, AuthContinuation?>(
      AuthContinuationController.new,
    );
