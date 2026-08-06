/// CircleStats 页面只需要记录当前圈子被访问，不依赖 runtime 存储、同步或去重实现。
typedef CircleStatsVisitRecorder = Future<void> Function(String circleId);
