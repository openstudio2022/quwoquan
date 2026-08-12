import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

abstract interface class ResearchReleaseReadback {
  Future<ResearchReleaseReadbackView> readCurrentResearchRelease();
}
