import 'package:quwoquan_app/runtime/errors/cloud_transport_failure.dart';

import 'cloud_transport_failure_classifier_stub.dart'
    if (dart.library.io) 'cloud_transport_failure_classifier_io.dart'
    as platform;

CloudTransportFailure? classifyCloudTransportFailure(Object error) {
  return platform.classifyCloudTransportFailure(error);
}
