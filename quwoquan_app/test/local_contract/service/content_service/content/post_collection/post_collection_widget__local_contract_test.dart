import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/service/content_service/content/post_collection/presentation/post_collection_editor.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart' as wire;
import 'package:quwoquan_app/runtime/di/post_collection_dependencies.dart';
import 'package:quwoquan_app/service/content_service/content/post_collection/application/post_collection_port.dart';
import 'package:quwoquan_app/service/content_service/content/post_collection/presentation/post_collection_page.dart';
import 'package:quwoquan_app/l10n/copy/post_collection_text_constants.dart';

import '../../../../../support/runtime/cloud_boundary_test_scope.dart';

// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/ordered-post-collection/spec.md#gwt-003
class _Port implements PostCollectionPort {
  bool fail = false;
  wire.SavePostCollectionCommand? saved;
  @override
  Future<wire.PostCollectionManagementView> management(
    wire.GetPostCollectionManagementQuery query,
  ) => throw UnimplementedError();
  @override
  Future<wire.AuthorPostPageSlice> authorPosts(
    wire.ContentAuthorPostsQuery query,
  ) async => const wire.AuthorPostPageSlice(items:[wire.ContentPostProjection(postId:'new',contentType:'image',title:'我的照片',mediaAssetId:'asset',likeCount:0,commentCount:0,shareCount:0)],hasMore:false);
  @override
  Future<wire.PostCollectionPage> get(wire.GetPostCollectionQuery query) async {
    if (fail) throw StateError('unavailable');
    return wire.PostCollectionPage(
      collectionId: 'c',
      ownerPersonaId: 'owner',
      name: '合集名称',
      visibility: wire.PostCollectionVisibility.public,
      version: 1,
      members: const [
        wire.PostCollectionMemberSummary(
          postId: 'p',
          contentType: 'video',
          title: '可见视频',
        ),
      ],
      visibleCount: 1,
      canManage: false,
    );
  }

  @override
  Future<wire.PostCollectionCommandResult> save(
    wire.SavePostCollectionCommand command,
  ) async {saved=command;return wire.PostCollectionCommandResult(collectionId:command.collectionId,version:command.expectedVersion+1,status:wire.PostCollectionStatus.active);}
  @override
  Future<wire.PostCollectionCommandResult> delete(
    wire.DeletePostCollectionCommand command,
  ) => throw UnimplementedError();
}

void main() {
 testWidgets('编辑器选择真实作品并保留失权引用，不显示内部标识输入', (tester) async {
 final port=_Port();
 await tester.pumpWidget(ProviderScope(overrides:sealedCloudBoundaryOverrides(),child:ScreenUtilInit(designSize:const Size(390,844),builder:(_,__)=>CupertinoApp(home:PostCollectionEditor(port:port,personaId:'owner',view:const wire.PostCollectionManagementView(collectionId:'c',name:'合集',visibility:wire.PostCollectionVisibility.public,version:5,members:[wire.PostCollectionManagedMember(postId:'hidden',readable:false)]))))));
 await tester.pumpAndSettle();
 expect(find.byType(CupertinoTextField),findsOneWidget);
 expect(find.text('hidden'),findsNothing);
 expect(find.text(PostCollectionText.unavailableMember),findsOneWidget);
 await tester.tap(find.text('我的照片'));await tester.pump();
 await tester.ensureVisible(find.text(PostCollectionText.cover));await tester.tap(find.text(PostCollectionText.cover));await tester.pump();
 await tester.ensureVisible(find.text(PostCollectionText.save));await tester.tap(find.text(PostCollectionText.save));await tester.pumpAndSettle();
 expect(port.saved?.postIds,['hidden','new']);expect(port.saved?.coverAssetId,'asset');expect(port.saved?.expectedVersion,5);
 });
  testWidgets('合集读取并导航独立 Post，不向非 owner 展示管理', (tester) async {
    final port = _Port();
    String? opened;
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          ...sealedCloudBoundaryOverrides(),
          postCollectionPortProvider.overrideWithValue(port),
        ],
        child: ScreenUtilInit(
          designSize: const Size(390, 844),
          builder: (_, __) => CupertinoApp(
            home: PostCollectionPage(
              collectionId: 'c',
              openPost: (id) => opened = id,
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('可见视频'), findsOneWidget);
    expect(find.text(PostCollectionText.edit), findsNothing);
    await tester.tap(find.text('可见视频'));
    expect(opened, 'p');
  });
}
