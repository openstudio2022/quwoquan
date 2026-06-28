import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/services/connection/connection_models.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';

/// 同频/广场页面数据 Provider。
///
/// 仅 `ref.watch(connectionRepositoryProvider)` 取数，由 core 的
/// `appDataSourceModeProvider` 透明切换 Mock/Remote；UI 不直接碰数据源模式
/// （守 `verify_ui_app_data_source_mode_ratchet`）。

/// 同频连接中心四 tab 计数摘要。
final connectionHubSummaryProvider = FutureProvider<ConnectionHubSummary>((
  ref,
) {
  return ref.watch(connectionRepositoryProvider).getHubSummary();
});

/// 同趣的人（无地理位置）。
final affinityPeersProvider = FutureProvider<List<PeerConnection>>((ref) {
  return ref.watch(connectionRepositoryProvider).listAffinityPeers();
});

/// 附近同趣的人（带模糊位置）。
final nearbyPeersProvider = FutureProvider<List<PeerConnection>>((ref) {
  return ref.watch(connectionRepositoryProvider).listNearbyPeers();
});

/// 结伴 / 行程机会。
final companionTripsProvider = FutureProvider<List<CompanionTrip>>((ref) {
  return ref.watch(connectionRepositoryProvider).listCompanionTrips();
});

/// 线下局。
final offlineMeetupsProvider = FutureProvider<List<OfflineMeetup>>((ref) {
  return ref.watch(connectionRepositoryProvider).listOfflineMeetups();
});
