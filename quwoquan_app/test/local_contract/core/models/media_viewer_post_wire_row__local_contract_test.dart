import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/models/content_post_view_data.dart';
import 'package:quwoquan_app/core/models/media_viewer_extra.dart';

void main() {
  test('MediaViewerPostWireRow 从 typed ViewData 只输出 canonical Post 键', () {
    final row = MediaViewerPostWireRow.fromViewData(
      ContentPostViewData(
        id: 'p1',
        type: 'micro',
        identity: 'moment',
        displayFormat: 'note',
        assistantUsePolicy: 'inherit',
        authorId: 'author-1',
        displayName: '作者',
        avatarUrl: '',
        authorRoleLabel: '',
        authorIdentityTags: const <String>[],
        authorVerified: false,
        title: 't',
        likeCount: 3,
        commentCount: 0,
        shareCount: 0,
        createdAt: DateTime.utc(2026),
      ),
    );
    expect(row.toDynamicMap()['title'], 't');
    expect(row.toDynamicMap()['likeCount'], 3);
    final back = row.toDynamicMap();
    expect(back['postId'], 'p1');
    expect(back['contentType'], 'micro');
    expect(back, isNot(contains('id')));
    expect(back, isNot(contains('type')));
    expect(back['title'], 't');
    expect(back['likeCount'], 3);
  });

  test('fromObjectEntries 与 toObjectMap 为防御性拷贝', () {
    final inner = <String, Object?>{'k': 1};
    final row = MediaViewerPostWireRow.fromObjectEntries(inner);
    inner['k'] = 2;
    expect(row.toObjectMap()['k'], 1);
    final mut = row.toObjectMap();
    mut['k'] = 3;
    expect(row.toObjectMap()['k'], 1);
  });
}
