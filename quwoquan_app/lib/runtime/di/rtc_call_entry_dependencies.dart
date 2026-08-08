import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/presentation/rtc_call_entry_presenter.dart';

/// Production binding for the RTC-owned call-entry presentation coordinator.
///
/// Cross-object presentation consumes this typed provider; construction of the
/// concrete RTC presenter remains confined to the composition root.
final rtcCallEntryPresenterProvider = Provider<RtcCallEntryPresenter>(
  (ref) => const RtcCallEntryPresenter(),
);
