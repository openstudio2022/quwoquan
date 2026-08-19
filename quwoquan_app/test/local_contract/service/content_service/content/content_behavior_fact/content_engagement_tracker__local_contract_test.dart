import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_repository.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_engagement_tracker.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show BehaviorEventType, ContentType;

import '../../../../../support/service/content_service/content/content_behavior_fact/recording_content_behavior_repository.dart';

void main() {
  test('图片与视频退出按真实进度计算深度、比例和总量', () async {
    final reporter = RecordingContentBehaviorRepository();
    final tracker = ContentEngagementTracker(reporter: reporter);
    addTearDown(tracker.dispose);

    tracker.trackContentEnter(
      'image-progress',
      contentType: ContentType.image,
      referralSource: ReferralSource.organicFeed,
      totalImages: 4,
    );
    tracker.trackContentProgress('image-progress', currentImageIndex: 2);
    tracker.trackContentEnter(
      'image-zero',
      contentType: ContentType.image,
      referralSource: ReferralSource.organicFeed,
      totalImages: 4,
    );
    tracker.trackContentEnter(
      'image-dwell',
      contentType: ContentType.image,
      referralSource: ReferralSource.organicFeed,
      totalImages: 1,
    );
    tracker.trackContentEnter(
      'video-short',
      contentType: ContentType.video,
      referralSource: ReferralSource.organicFeed,
      totalDurationMs: 8000,
    );
    tracker.trackContentProgress('video-short', playPositionMs: 4000);
    tracker.trackContentEnter(
      'video-normal',
      contentType: ContentType.video,
      referralSource: ReferralSource.organicFeed,
      totalDurationMs: 20000,
    );
    tracker.trackContentProgress('video-normal', playPositionMs: 12000);
    tracker.trackContentEnter(
      'video-idle',
      contentType: ContentType.video,
      referralSource: ReferralSource.organicFeed,
      totalDurationMs: 10000,
    );

    // ContentEngagementTracker 以真实 wall-clock 会话时长拒绝不足 1 秒的 dwell。
    // 六个 session 共用一次等待，避免把 UI 测试运行速度当作覆盖率来源。
    await Future<void>.delayed(const Duration(milliseconds: 3100));
    await Future.wait(<Future<void>>[
      tracker.trackContentExit('image-progress', emitDwell: false),
      tracker.trackContentExit('image-zero', emitDwell: false),
      tracker.trackContentExit('image-dwell', emitDwell: false),
      tracker.trackContentExit('video-short', emitDwell: false),
      tracker.trackContentExit('video-normal', emitDwell: false),
      tracker.trackContentExit('video-idle', emitDwell: false),
    ]);

    final depthByContent = <String, BehaviorEvent>{
      for (final event in reporter.recorded)
        if (event.action == BehaviorEventType.contentDepth)
          event.contentId: event,
    };

    expect(depthByContent.keys, <String>{
      'image-progress',
      'image-zero',
      'image-dwell',
      'video-short',
      'video-normal',
      'video-idle',
    });
    expect(depthByContent['image-progress']?.consumedRatio, 0.5);
    expect(depthByContent['image-progress']?.engagementDepth, 2);
    expect(depthByContent['image-progress']?.totalUnits, 4);
    expect(depthByContent['image-zero']?.consumedRatio, 0);
    expect(depthByContent['image-zero']?.engagementDepth, 0);
    expect(depthByContent['image-dwell']?.consumedRatio, -1);
    expect(depthByContent['image-dwell']?.engagementDepth, 1);
    expect(depthByContent['image-dwell']?.totalUnits, 1);
    expect(depthByContent['video-short']?.consumedRatio, closeTo(0.65, 0.001));
    expect(depthByContent['video-short']?.engagementDepth, 3);
    expect(depthByContent['video-short']?.totalUnits, 8);
    expect(depthByContent['video-normal']?.consumedRatio, 0.6);
    expect(depthByContent['video-normal']?.engagementDepth, 3);
    expect(depthByContent['video-normal']?.totalUnits, 20);
    expect(depthByContent['video-idle']?.consumedRatio, 0);
    expect(depthByContent['video-idle']?.engagementDepth, 0);
    expect(depthByContent['video-idle']?.totalUnits, 10);
  });
}
