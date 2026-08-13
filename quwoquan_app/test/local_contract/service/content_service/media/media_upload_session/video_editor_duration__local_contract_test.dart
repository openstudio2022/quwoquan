// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/post-create-update/spec.md#gwt-003
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/presentation/video_editor_page.dart';

/// 裁切导出后的时长回写合同：不得沿用原片时长造成元数据失真。
void main() {
  test('导出时长可用时优先回写导出真实时长', () {
    expect(
      resolveEditedVideoDurationMs(
        exportDurationMs: 4200,
        trimStartMs: 1000,
        trimEndMs: 6000,
        fallbackDurationMs: 10000,
      ),
      4200,
    );
  });

  test('导出时长缺失时按 trim 区间推导，不回写原片时长', () {
    expect(
      resolveEditedVideoDurationMs(
        exportDurationMs: 0,
        trimStartMs: 1000,
        trimEndMs: 6000,
        fallbackDurationMs: 10000,
      ),
      5000,
    );
  });

  test('导出时长与 trim 区间均不可用才回退原片时长', () {
    expect(
      resolveEditedVideoDurationMs(
        exportDurationMs: 0,
        trimStartMs: 0,
        trimEndMs: 0,
        fallbackDurationMs: 10000,
      ),
      10000,
    );
  });
}
