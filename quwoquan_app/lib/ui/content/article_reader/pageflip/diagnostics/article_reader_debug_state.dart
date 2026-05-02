import 'package:flutter/widgets.dart';

@immutable
class BackwardDebugState {
  const BackwardDebugState({
    this.coveredPageIndex,
    this.leafRectoPageIndex,
    this.leafVersoPageIndex,
    this.phase,
    this.mainline,
    this.foldX,
    this.pageEdgeX,
    this.currentResidualBounds,
    this.backVertexCount,
    this.frontVertexCount,
    this.edgeEnteredPage,
    this.backPolygonPoints,
    this.frontPolygonPoints,
    this.currentPolygonPoints,
  });

  final int? coveredPageIndex;
  final int? leafRectoPageIndex;
  final int? leafVersoPageIndex;
  final String? phase;
  final String? mainline;
  final double? foldX;
  final double? pageEdgeX;
  final Rect? currentResidualBounds;
  final int? backVertexCount;
  final int? frontVertexCount;
  final bool? edgeEnteredPage;
  final String? backPolygonPoints;
  final String? frontPolygonPoints;
  final String? currentPolygonPoints;
}

@immutable
class ArticleReaderPipelineDebugState {
  const ArticleReaderPipelineDebugState({
    required this.pipelineName,
    required this.renderBranchName,
    this.backward,
  });

  final String pipelineName;
  final String renderBranchName;
  final BackwardDebugState? backward;
}
