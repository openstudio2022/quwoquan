import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/models/media_viewer_extra.dart';

void main() {
  test('MediaViewerPostWireRow round-trip 保持键与标量', () {
    const original = <String, dynamic>{
      'postId': 'p1',
      'title': 't',
      'likeCount': 3,
    };
    final row = MediaViewerPostWireRow.fromDynamicMap(original);
    expect(row.toDynamicMap()['title'], 't');
    expect(row.toDynamicMap()['likeCount'], 3);
    expect(row.feedItem.id, 'p1');
    final back = row.toDynamicMap();
    expect(back['postId'], 'p1');
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
