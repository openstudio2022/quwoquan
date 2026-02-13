const int kImageEditorToolFilter = 0;
const int kImageEditorToolCrop = 1;
const int kImageEditorToolRotate = 2;
const int kImageEditorToolPro = 3;
const int kImageEditorToolFrame = 4;
const int kImageEditorToolText = 5;
const int kImageEditorToolMosaic = 6;

const int kImageEditorProCategoryOverall = 0;
const int kImageEditorProCategoryLocal = 1;
const int kImageEditorProCategoryHsl = 2;
const int kImageEditorProCategoryCurve = 3;
const int kImageEditorProCategoryWhiteBalance = 4;
const int kImageEditorProCategoryPerspective = 5;
const int kImageEditorProCategoryBwLevels = 6;
const int kImageEditorProCategoryPicker = -1;

// 兼容旧引用（后续统一迁移到 Overall 命名）
const int kImageEditorProCategoryBase = kImageEditorProCategoryOverall;

const List<String> kImageEditorToolTypes = [
  'filter',
  'crop',
  'rotate',
  'proTools',
  'frame',
  'text',
  'mosaic',
];
