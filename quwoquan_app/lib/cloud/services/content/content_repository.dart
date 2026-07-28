import 'package:quwoquan_app/cloud/content/models/content_behavior_batch_event_dto.dart';
import 'package:quwoquan_app/cloud/runtime/codec/cloud_response_decoder.dart';
import 'package:quwoquan_app/cloud/runtime/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/feed_object_card_dto.g.dart';

export 'package:quwoquan_app/cloud/content/models/content_behavior_batch_event_dto.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/runtime/models/content_app_config_wire.dart';
import 'package:quwoquan_app/cloud/runtime/models/content_post_detail_payload.dart';
import 'package:quwoquan_app/cloud/runtime/models/cursor_page.dart';
import 'package:quwoquan_app/cloud/runtime/models/discovery_feed_page.dart';
import 'package:quwoquan_app/cloud/runtime/models/post_engagement_counters.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository_contract.dart'
    show
        ContentReadRepository,
        ContentWriteRepository,
        ContentEngagementRepository,
        ContentConfigRepository,
        kFeedSortRecommend;

export 'package:quwoquan_app/cloud/runtime/models/discovery_presentation_wire.dart'
    show DiscoveryPresentationWire;
export 'package:quwoquan_app/cloud/runtime/models/discovery_feed_page.dart'
    show DiscoveryFeedPage;
export 'package:quwoquan_app/cloud/services/content/content_repository_contract.dart'
    show
        ContentDiscoveryFeedQuery,
        ContentReadRepository,
        ContentPostDetailReader,
        ContentEntityWishlistStateReader,
        ContentAuthorPostsReader,
        ContentWriteRepository,
        ContentEngagementRepository,
        ContentConfigRepository,
        kFeedSortRecommend;
export 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show
        ChangeContentCommentPinCommand,
        BindContentCommentAttachmentsCommand,
        ContentAuthorCommentPageSlice,
        ContentCommentAttachment,
        ContentCommentCommandResult,
        ContentCommentCommandWriter,
        ContentCommentFacet,
        ContentCommentListItem,
        ContentCommentMention,
        ContentCommentPageSlice,
        ContentCommentReactionCommandResult,
        ContentCommentReactionValue,
        ContentCommentReplyPageSlice,
        ContentCommentSort,
        ContentCommentViewerRelation,
        ContentPostReactionFacet,
        ContentCommentQuery,
        ContentCommentReactionWriter,
        ContentCommentStatus,
        ContentReceivedCommentPageSlice,
        CreateContentCommentCommand,
        DeleteContentCommentCommand,
        ReactToContentCommentCommand;

// 生产组合根 Remote-only：Mock 聚合替身已物理迁至
// test/support/cloud_services/content/mock_content_repository.dart（测试），
// 四环境 production lib 不包含 fixture 回放。
part 'content_repository_remote.dart';
