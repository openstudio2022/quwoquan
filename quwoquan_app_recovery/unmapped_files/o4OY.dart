import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/analytics/core/analytics_service.dart';
import 'package:quwoquan_app/features/home/providers/analytics_provider.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

/// 分析仪表板Widget
class AnalyticsDashboard extends ConsumerWidget {
  const AnalyticsDashboard({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final analyticsStats = ref.watch(analyticsStatsProvider);
    final analyticsStatus = ref.watch(analyticsStatusProvider);

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              '分析数据',
              style: Theme.of(context).textTheme.headlineSmall,
            ),
                SizedBox(height: context.safeGetIntraGroupSpacing(SpacingSize.lg)),
            _buildStatusIndicator(context, analyticsStatus),
                SizedBox(height: context.safeGetIntraGroupSpacing(SpacingSize.lg)),
            analyticsStats.when(
              data: (stats) => _buildStatsContent(context, stats),
              loading: () => const CircularProgressIndicator(),
              error: (error, stack) => Text('错误: $error'),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildStatusIndicator(BuildContext context, AnalyticsStatus status) {
    Color statusColor;
    String statusText;

    switch (status) {
      case AnalyticsStatus.enabled:
        statusColor = Colors.green;
        statusText = '已启用';
        break;
      case AnalyticsStatus.disabled:
        statusColor = Colors.grey;
        statusText = '已禁用';
        break;
      case AnalyticsStatus.initializing:
        statusColor = Colors.orange;
        statusText = '初始化中';
        break;
      case AnalyticsStatus.error:
        statusColor = Colors.red;
        statusText = '错误';
        break;
    }

    return Row(
      children: [
        Container(
              width: context.safeGetIntraGroupSpacing(SpacingSize.sm),
              height: context.safeGetIntraGroupSpacing(SpacingSize.sm),
          decoration: BoxDecoration(
            color: statusColor,
            shape: BoxShape.circle,
          ),
        ),
            SizedBox(width: context.safeGetIntraGroupSpacing(SpacingSize.sm)),
        Text('状态: $statusText'),
      ],
    );
  }

  Widget _buildStatsContent(BuildContext context, Map<String, dynamic> stats) {
    return Column(
      children: [
        _buildStatRow(context, '总事件数', stats['total_events']?.toString() ?? '0'),
        _buildStatRow(context, '待上报', stats['pending_events']?.toString() ?? '0'),
        _buildStatRow(context, '已上报', stats['uploaded_events']?.toString() ?? '0'),
        _buildStatRow(context, '存储大小', _formatBytes(stats['storage_size_bytes'] ?? 0)),
      ],
    );
  }

  Widget _buildStatRow(BuildContext context, String label, String value) {
    return Padding(
          padding: EdgeInsets.symmetric(vertical: context.safeGetIntraGroupSpacing(SpacingSize.xs)),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label),
          Text(
            value,
            style: const TextStyle(fontWeight: FontWeight.bold),
          ),
        ],
      ),
    );
  }

  String _formatBytes(int bytes) {
    const int bytesPerKB = 1024;
    const int bytesPerMB = bytesPerKB * bytesPerKB;
    
    if (bytes < bytesPerKB) return '$bytes B';
    if (bytes < bytesPerMB) return '${(bytes / bytesPerKB).toStringAsFixed(1)} KB';
    return '${(bytes / bytesPerMB).toStringAsFixed(1)} MB';
  }
}

/// 分析事件列表Widget
class AnalyticsEventList extends ConsumerWidget {
  const AnalyticsEventList({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Card(
      child: Padding(
            padding: EdgeInsets.all(context.safeGetContainerSpacing(SpacingSize.lg)),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              '最近事件',
              style: Theme.of(context).textTheme.headlineSmall,
            ),
                SizedBox(height: context.safeGetIntraGroupSpacing(SpacingSize.lg)),
            const _EventListContent(),
          ],
        ),
      ),
    );
  }
}

class _EventListContent extends ConsumerStatefulWidget {
  const _EventListContent();

  @override
  ConsumerState<_EventListContent> createState() => _EventListContentState();
}

class _EventListContentState extends ConsumerState<_EventListContent> {
  @override
  Widget build(BuildContext context) {
    return FutureBuilder(
      future: _getRecentEvents(),
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return const CircularProgressIndicator();
        }

        if (snapshot.hasError) {
          return Text('错误: ${snapshot.error}');
        }

        final events = snapshot.data ?? [];
        if (events.isEmpty) {
          return const Text('暂无事件');
        }

        return ListView.builder(
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          itemCount: events.length,
          itemBuilder: (context, index) {
            final event = events[index];
            return _EventListItem(event: event);
          },
        );
      },
    );
  }

  Future<List<Map<String, dynamic>>> _getRecentEvents() async {
    final analyticsService = AnalyticsService();
    final events = await analyticsService.getStoredEvents();
    
    const int maxRecentEvents = 10;
    return events.take(maxRecentEvents).map((event) => {
      'type': event.eventType,
      'name': event.eventName,
      'timestamp': event.timestamp,
      'properties': event.properties,
    }).toList();
  }
}

class _EventListItem extends StatelessWidget {
  final Map<String, dynamic> event;

  const _EventListItem({required this.event});

  @override
  Widget build(BuildContext context) {
    final timestamp = event['timestamp'] as DateTime;
    final eventType = event['type'] as String;
    final eventName = event['name'] as String;

    return ListTile(
      leading: _getEventIcon(eventType),
      title: Text(eventName),
      subtitle: Text(_formatTimestamp(timestamp)),
      trailing: Text(
        _getEventTypeDisplayName(eventType),
        style: Theme.of(context).textTheme.bodySmall,
      ),
      onTap: () => _showEventDetails(context, event),
    );
  }

  Widget _getEventIcon(String eventType) {
    IconData iconData;
    Color iconColor;

    switch (eventType) {
      case 'page_view':
        iconData = Icons.visibility;
        iconColor = Colors.blue;
        break;
      case 'user_action':
        iconData = Icons.touch_app;
        iconColor = Colors.green;
        break;
      case 'error':
        iconData = Icons.error;
        iconColor = Colors.red;
        break;
      case 'performance':
        iconData = Icons.speed;
        iconColor = Colors.orange;
        break;
      default:
        iconData = Icons.analytics;
        iconColor = Colors.grey;
    }

    return Icon(iconData, color: iconColor, size: AppSpacing.iconMedium);
  }

  String _formatTimestamp(DateTime timestamp) {
    final now = DateTime.now();
    final difference = now.difference(timestamp);

    const int oneMinute = 1;
    const int oneHour = 1;
    const int oneDay = 1;

    if (difference.inMinutes < oneMinute) {
      return '刚刚';
    } else if (difference.inHours < oneHour) {
      return '${difference.inMinutes}分钟前';
    } else if (difference.inDays < oneDay) {
      return '${difference.inHours}小时前';
    } else {
      return '${difference.inDays}天前';
    }
  }

  String _getEventTypeDisplayName(String eventType) {
    switch (eventType) {
      case 'page_view':
        return '页面访问';
      case 'user_action':
        return '用户行为';
      case 'error':
        return '错误';
      case 'performance':
        return '性能';
      default:
        return eventType;
    }
  }

  void _showEventDetails(BuildContext context, Map<String, dynamic> event) {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(event['name'] as String),
        content: SingleChildScrollView(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Text('类型: ${event['type']}'),
              Text('时间: ${_formatTimestamp(event['timestamp'] as DateTime)}'),
                SizedBox(height: context.safeGetIntraGroupSpacing(SpacingSize.lg)),
              const Text('属性:'),
                  SizedBox(height: context.safeGetIntraGroupSpacing(SpacingSize.sm)),
              ...((event['properties'] as Map<String, dynamic>).entries.map(
                (entry) => Padding(
                      padding: EdgeInsets.symmetric(vertical: context.safeGetIntraGroupSpacing(SpacingSize.xs) / 2),
                  child: Text('${entry.key}: ${entry.value}'),
                ),
              )),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => context.pop(),
            child: const Text('关闭'),
          ),
        ],
      ),
    );
  }
}

/// 分析控制面板Widget
class AnalyticsControlPanel extends ConsumerWidget {
  const AnalyticsControlPanel({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Card(
      child: Padding(
            padding: EdgeInsets.all(context.safeGetContainerSpacing(SpacingSize.lg)),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              '分析控制',
              style: Theme.of(context).textTheme.headlineSmall,
            ),
                SizedBox(height: context.safeGetIntraGroupSpacing(SpacingSize.lg)),
            _buildControlButtons(context, ref),
          ],
        ),
      ),
    );
  }

  Widget _buildControlButtons(BuildContext context, WidgetRef ref) {
    return Column(
      children: [
        SizedBox(
          width: double.infinity,
          child: ElevatedButton(
            onPressed: () => _uploadEvents(ref),
            child: const Text('上报事件'),
          ),
        ),
                  SizedBox(height: context.safeGetIntraGroupSpacing(SpacingSize.sm)),
        SizedBox(
          width: double.infinity,
          child: ElevatedButton(
            onPressed: () => _clearOldData(ref),
            child: const Text('清理旧数据'),
          ),
        ),
                  SizedBox(height: context.safeGetIntraGroupSpacing(SpacingSize.sm)),
        SizedBox(
          width: double.infinity,
          child: ElevatedButton(
            onPressed: () => _testConnection(ref),
            child: const Text('测试连接'),
          ),
        ),
      ],
    );
  }

  void _uploadEvents(WidgetRef ref) async {
    final analyticsService = AnalyticsService();
    await analyticsService.uploadEvents();
    
    // 刷新统计信息
    ref.invalidate(analyticsStatsProvider);
  }

  void _clearOldData(WidgetRef ref) async {
    final analyticsService = AnalyticsService();
    await analyticsService.cleanup();
    
    // 刷新统计信息
    ref.invalidate(analyticsStatsProvider);
  }

  void _testConnection(WidgetRef ref) async {
    // 这里可以显示连接测试结果
    ScaffoldMessenger.of(ref.context).showSnackBar(
      const SnackBar(content: Text('连接测试功能待实现')),
    );
  }
}

