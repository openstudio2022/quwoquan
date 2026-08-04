import 'package:quwoquan_app/cloud/runtime/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/models/content_post_view_data.dart';

import 'package:quwoquan_app/cloud/runtime/models/content_post_detail_payload.dart';
import 'package:quwoquan_app/cloud/runtime/models/cursor_page.dart';
import 'package:quwoquan_app/cloud/runtime/models/discovery_feed_page.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    hide ContentDiscoveryFeedQuery;
import 'package:quwoquan_app/cloud/services/content/content_repository_contract.dart'
    show
        ContentDiscoveryFeedQuery,
        ContentReadRepository,
        kFeedSortRecommend;

export 'package:quwoquan_app/cloud/runtime/models/discovery_feed_page.dart'
    show DiscoveryFeedPage;
export 'package:quwoquan_app/cloud/services/content/content_repository_contract.dart'
    show
        ContentDiscoveryFeedQuery,
        ContentReadRepository,
        ContentPostDetailReader,
        ContentEntityWishlistStateReader,
        ContentAuthorPostsReader,
        ContentPostDeleteCommandWriter,
        ContentConfigRepository,
        kFeedSortRecommend;
export 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show
        ChangeContentCommentPinCommand,
        BindContentCommentAttachmentsCommand,
        AuthorCommentPageSlice,
        CommentAttachmentSlice,
        CommentCommandResult,
        ContentCommentCommandWriter,
        ContentCommentFacet,
        CommentListItem,
        CommentMention,
        CommentPageSlice,
        ContentCommentReactionCommandResult,
        CommentReactionType,
        ReplyPageSlice,
        CommentSort,
        CommentViewerRelation,
        ContentPostReactionFacet,
        ContentCommentQuery,
        ContentCommentReactionWriter,
        ReceivedCommentPageSlice,
        CreateContentCommentCommand,
        DeleteContentCommentCommand,
        ReactToContentCommentCommand;

// 生产组合根 Remote-only：Mock 聚合替身已物理迁至
// test/support/cloud_services/content/mock_content_repository.dart（测试），
// 四环境 production lib 不包含 fixture 回放。
part 'content_repository_remote.dart';
