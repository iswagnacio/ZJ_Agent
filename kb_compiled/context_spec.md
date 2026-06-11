# API Specifications (compiled — authoritative)

## Create_Target_API_v10   [stage: target]
当一份生成的 ROI 需要绑定成可被后续步骤（测量、公式）按名引用的可复用 target 时使用；也用于把 Measure_ROI 筛选后的 ROI 派生为新 target。
Endpoint: POST /api/v10/create-target/run
Selector: operation ∈ {bindSegmentRoi, bindMeasureRoi, bindExistingRoi}; sourceType ∈ {segment_roi, measure_roi, existing_roi, target_roi_variant}

### 请求参数
- sessionId (string, required) — 会话 ID。
- workplanId (string, optional) — Workplan ID。
- stepId (string, required) — 当前 Create_Target 步骤 ID。
- operation (string, required, enum: bindSegmentRoi|bindMeasureRoi|bindExistingRoi) — 创建 target 的动作。`bindExistingRoi` 为兼容旧版的通用绑定；推荐新 Workplan 使用 `bindSegmentRoi` 或 `bindMeasureRoi`。
- sourceType (string, optional, enum: segment_roi|measure_roi|existing_roi|target_roi_variant) — 来源类型。为空时按 operation 自动推断。
- sourceSegmentStepId (string, optional) — 来源 Segment_ROI 步骤 ID，用于追溯。
- sourceMeasureStepId (string, optional) — 来源 Measure_ROI 步骤 ID，用于追溯。
- sourceRoiResourceUuid (string, required, ROI zip storedFilename、targetName、targetResourceUuid 或自动变体 targetName) — 来源 ROI。
- measureTableResourceUuid (string, optional, Measure_ROI 返回的测量表 storedFilename) — 若来源是 Measure_ROI 生成的新 ROI，建议记录其对应测量表。
- targetName (string, required, 允许字母、数字、点、下划线、短横线) — 要创建/绑定的 target 名称。
- targetShowName (string, optional) — 用户可见名称。为空或不提供时，默认等于 `targetName`。
- segmentRoiParams (object, optional) — 来源 Segment_ROI 的关键参数快照，会持久化到 target binding。
- measureRoiParams (object, optional) — 来源 Measure_ROI 的关键参数快照，会持久化到 target binding。
- roiRenderParams (object, optional, 见下表) — ROI 渲染参数快照，会持久化到 target binding 和 `createTargetParams`。
- variantStrategy (object, optional, 见下表) — Create_Target 自动生成 ROI 变体的策略。
- outputOptions (object, optional, 见下表) — 输出控制。
- roiRenderParams.enabled (boolean, optional, default=True) — 是否启用过 ROI 渲染。Create_Target 只记录，不根据该字段重新渲染。
- roiRenderParams.renderImageResourceUuid (string, optional) — 当时用于 ROI 渲染的底图资源。可以是原图、PicSplit 灰度图、PicSplit 伪彩图或任意 session 中已有图。
- roiRenderParams.renderImageBase64 (string, optional) — 当时用于 ROI 渲染的底图 base64。通常不建议在 target binding 长期保存大体积 base64，推荐保存资源 ID。
- roiRenderParams.renderContour (boolean, optional, default=True) — 是否渲染 ROI 轮廓。
- roiRenderParams.renderMaskOverlay (boolean, optional, default=False) — 是否渲染半透明 ROI 蒙版。
- roiRenderParams.overlayAlpha (number, optional, default=0.35) — 半透明 ROI 蒙版透明度。
- roiRenderParams.contourColor (string, optional, default=#FFFF00) — ROI 轮廓/蒙版颜色。
- roiRenderParams.contourWidthPixels (integer, optional, default=2) — ROI 轮廓粗细，像素单位。
- variantStrategy.boundaryModes (array, optional, enum: in_bound|on_bound) — 自动生成 ROI 变体的边界模式。
- variantStrategy.offsetLevels (array, optional, enum: [-0.2,-0.1,0,0.1,0.2]) — ROI 缩放 offset；>0 放大，<0 缩小。
- outputOptions.generateDefaultRoiVariants (boolean, optional, default=True) — 是否在 Create_Target 成功绑定 target 后自动生成默认 ROI 变体。

## Formula_API_v10   [stage: calculate]
当最终结果是对已测量 target 的计算量或比值（计数、比例、OD/IOD 等），需要把测量值汇总成报表/答案时使用。
Endpoint: POST /api/v10/formula/run

### 请求参数
- sessionId (string, required) — 会话 ID。
- workplanId (string, optional) — Workplan ID。
- stepId (string, optional) — 步骤 ID。
- operation (string, optional) — 公式动作，当前服务主要透传。
- targetName (string, optional) — 目标名，当前服务主要透传。
- formulaPlan (object, optional) — 公式计划，例如 expression、inputTargets、metrics 等。
- reportRequirements (object, optional) — 报告输出要求，例如 format、language、precision 等。
- knownContext (object, optional) — 已知上下文。
- inputResources (object, optional) — 输入资源，当前服务主要透传。
- params (object, optional) — 公式参数，当前服务主要透传。
- outputOptions (object, optional) — 输出控制，当前服务主要透传。

## Get_File_API_v10   [stage: shared]
当需要按 storedFilename 取回服务端已存文件的字节（如结果图、ROI zip）时使用。
Endpoint: POST /api/v10/files/get

### 请求参数
- sessionId (string, required) — 会话 ID。
- storedFilename (string, required, Put_File 返回的 storedFilename) — 要读取的服务端文件名。

## Get_Target_API_v10   [stage: shared]
当需要按 targetName 查询某个已创建 target 的 binding 及其创建时填入的参数（用于追溯或复用）时使用。
Endpoint: GET /api/v10/get-target/run?sessionId=<sessionId>&targetName=<targetName> | POST /api/v10/get-target/run

### GET 请求参数
- sessionId (string, required) — 会话 ID。
- targetName (string, required, targetName 或 targetResourceUuid) — 要查询的 target 名。推荐传 `targetName`；如果传入 `target_<targetName>`，服务会尝试兼容解析。

### POST 请求参数
- sessionId (string, required) — 会话 ID。
- targetName (string, required, targetName 或 targetResourceUuid) — 要查询的 target 名。推荐传 `targetName`；如果传入 `target_<targetName>`，服务会尝试兼容解析。

## Measure_ROI_API_v10   [stage: measure]
当需要逐对象的属性值（面积、平均强度、圆度等），或需要按这些属性筛选对象并生成新 ROI（如筛出 Ki67 阳性细胞）时使用。
Endpoint: POST /api/v10/measure-roi/run
Selector: operation ∈ {measure_existing, measureAndFilterRoi}

### 通用请求参数
- sessionId (string, required) — 会话 ID。
- workplanId (string, optional) — Workplan ID。
- stepId (string, optional) — 当前步骤 ID。
- targetName (string, optional, if `measureAndFilterRoi` 时建议提供) — 用于生成筛选后 ROI 文件名，例如 `ki67_positive_dapi_roi_filtered.zip`。
- operation (string, required, enum: measure_existing|measureAndFilterRoi) — 测量动作。
- inputResources (object, required, 见下表) — 输入资源。
- params (object, optional, 见下表) — 测量与筛选参数。
- filterRules (object, optional, 兼容字段) — 顶层筛选规则。若同时提供 `params.filterRules`，优先使用 `params.filterRules`。
- roiRenderParams (object, optional, 见 ROI 渲染参数表) — ROI 自动渲染参数。
- outputOptions (object, optional, 见下表) — 输出控制。
- inputResources.parentRoiResourceUuid (string, required, ROI zip storedFilename、targetName 或 targetResourceUuid) — 父 ROI 资源或 target 引用。
- inputResources.measureImageResourceUuid (string, required, 图片 storedFilename 或已注册语义引用) — 用于测量强度/面积等指标的图像；若启用 ROI 渲染且未指定底图，默认也用这张图作为渲染底图。
- params.measureFeatures (array, optional, enum: AREA|MEAN|CIRCULARITY|INTEGRATED_DENSITY|MIN|MAX|STD_DEV|AREA|MEAN|CIRCULARITY) — 需要测量的指标。
- params.filterRules (object, optional, if `measureAndFilterRoi` 时可选, 见下表) — 测量后筛选 ROI 的规则。
- params.filterRules.<metric>.min (number, optional) — 指定指标最小值。`metric` 可为 `AREA`、`MEAN`、`CIRCULARITY`、`INTEGRATED_DENSITY`、`MIN`、`MAX`、`STD_DEV`，也兼容 `area`、`mean`、`circularity`、`integratedDensity` 等写法。
- params.filterRules.<metric>.max (number, optional) — 指定指标最大值。
- roiRenderParams.renderImageResourceUuid (string, optional, default=inputResources.measureImageResourceUuid, 图片 storedFilename 或语义引用) — 被渲染的底图。
- roiRenderParams.renderImageBase64 (string, optional, Base64 或 data URL) — 直接传入底图。
- roiRenderParams.enabled (boolean, optional, default=True) — 是否启用 ROI 渲染。
- roiRenderParams.renderContour (boolean, optional, default=True) — 是否绘制 ROI 轮廓。
- roiRenderParams.renderMaskOverlay (boolean, optional, default=False) — 是否绘制半透明 ROI 蒙版。
- roiRenderParams.overlayAlpha (number, optional, default=0.35, 0~1) — 半透明蒙版透明度。
- roiRenderParams.contourColor (string, optional, default=#FFFF00, `#RRGGBB`、`R,G,B`、常见英文色名) — ROI 轮廓与蒙版颜色。
- roiRenderParams.contourWidthPixels (integer, optional, default=2, >=1) — ROI 轮廓粗细，像素单位。
- outputOptions.returnMeasureTable (boolean, optional, default=True) — 是否保存并返回测量表资源。`measureAndFilterRoi` 会返回完整测量表和筛选后测量表。
- outputOptions.returnMeasureRows (boolean, optional, default=True) — 是否在响应中直接返回测量行。
- outputOptions.returnRoiZip (boolean, optional, default=False) — 是否返回原 ROI zip Base64。
- outputOptions.returnFilteredRoiZip (boolean, optional, default=True) — 是否保存并返回筛选后 ROI zip 文件资源。Create_Target.bindMeasureRoi 后续应使用 `filteredRoiResourceUuid`。
- outputOptions.returnFilteredOutRoiZip (boolean, optional, default=False) — 是否保存并返回被筛掉 ROI zip 文件资源。
- outputOptions.returnFilteredRoiBase64 (boolean, optional, default=False) — 是否在响应中返回筛选后 ROI zip Base64。
- outputOptions.returnFilteredOutRoiBase64 (boolean, optional, default=False) — 是否在响应中返回被筛掉 ROI zip Base64。
- outputOptions.returnSummary (boolean, optional, default=True) — 是否返回统计摘要。
- outputOptions.returnRoiRender (boolean, optional, default=False) — 是否启用 ROI 自动渲染。
- outputOptions.returnRenderedImage (boolean, optional, default=False) — ROI 渲染启用兼容开关。
- outputOptions.returnRenderedImageStoredFile (boolean, optional, default=True) — 是否保存并返回带 ROI 的渲染图。
- outputOptions.returnRenderedImageBase64 (boolean, optional, default=False) — 是否返回渲染图 Base64。
- outputOptions.returnRoiMaskStoredFile (boolean, optional, default=True) — 是否保存并返回 ROI Mask 图。
- outputOptions.returnRoiMaskBase64 (boolean, optional, default=False) — 是否返回 ROI Mask Base64。

## Pic_Split_API_v10   [stage: deconvolve]
当分析目标只占复合图中的某个染色或通道，需要先把它从复合图里分离出来再做分割/测量时使用。rgb_split 拆分 RGB 通道；color_deconvolution 做 H&E、DAB 等颜色解卷。
Endpoint: POST /api/v10/pic-split/run
Selector: splitMethod ∈ {rgb_split, color_deconvolution}

### 请求参数
- pseudoColorRgb (string, optional) — 该通道使用的伪彩颜色，格式为 `#RRGGBB`。
- pseudoColorStoredFilename (string, optional) — 伪彩图 PNG 保存后的文件名。
- pseudoColorOriginalFilename (string, optional) — 伪彩图派生原始文件名。
- pseudoColorResourceUuid (string, optional) — 伪彩图资源 ID，通常等于 `pseudoColorStoredFilename`。
- sessionId (string, required) — 会话 ID。
- inputImage (object, required, FileRefDto) — 输入图片引用。
- inputImage.storedFilename (string, required, Put_File 返回的 storedFilename) — 服务端已存储图片文件名。
- inputImage.originalFilename (string, optional) — 原始文件名，仅用于描述。
- splitMethod (string, required, enum: rgb_split|color_deconvolution) — 拆分方式。
- colorDeconvParams (object, optional, if `splitMethod=color_deconvolution` 时建议提供, 见下表) — 颜色反卷积参数；缺省时使用 H DAB。
- outputOptions (object, optional, 见下表) — 输出控制。
- colorDeconvParams.matrix (string, optional, enum: H&E|H&E 2|H DAB|Feulgen Light Green|Giemsa|FastRed FastBlue DAB|Methyl Green DAB|H&E DAB|H AEC|Azan-Mallory|Masson Trichrome|Alcian blue & H|H PAS|Brilliant_Blue|RGB|CMY|custom) — 颜色反卷积矩阵名。`custom` 时必须提供 3 个 stainVectors。
- colorDeconvParams.stainVectors (array<object>, optional, if `matrix=custom` 时是, 长度必须为 3) — 自定义染色向量。
- colorDeconvParams.stainVectors[].r (number, optional, if `matrix=custom` 时是, 0~1 常用) — R 分量。
- colorDeconvParams.stainVectors[].g (number, optional, if `matrix=custom` 时是, 0~1 常用) — G 分量。
- colorDeconvParams.stainVectors[].b (number, optional, if `matrix=custom` 时是, 0~1 常用) — B 分量。
- outputOptions.returnChannelBase64 (boolean, optional, default=True) — 是否返回每个灰度通道图片的 Base64。
- outputOptions.returnChannelStoredFiles (boolean, optional, default=True) — 是否保存灰度通道图片；同时控制伪彩图片是否保存为服务端文件。

## Put_File_API_v10   [stage: shared]
当原始字节（上传的图片、分类器文件等）需要先存到服务端、换取后续 API 可引用的 storedFilename 时使用。
Endpoint: POST /api/v10/files/put

### 请求参数
- sessionId (string, required) — 会话 ID，用于隔离不同会话下的文件存储目录。
- originalFilename (string, required, 合法文件名) — 原始文件名，用于保存元数据和推断文件类型。
- fileBase64 (string, required, Base64 文本) — 文件内容的 Base64 编码，不需要 data URL 前缀。

## ROI_Render_API_v10   [stage: render]
当需要把 ROI 以轮廓或半透明蒙版形式绘制到底图上、单独生成可视化图片（用于审阅或输出）时使用，与分割/测量解耦。
Endpoint: POST /api/v10/roi-render/run

### 请求参数
- sessionId (string, required) — 会话 ID。
- roiResourceUuid (string, required, ROI zip storedFilename、targetName 或 targetResourceUuid) — 要渲染的 ROI zip。
- renderImageResourceUuid (string, optional, 图片 storedFilename 或语义引用) — 被渲染的底图。可以是 PicSplit 产生的灰度图、伪彩图，也可以是 session 中任意已有图片。
- renderImageBase64 (string, optional, Base64 或 data URL) — 直接传入底图图片。若同时提供 `renderImageResourceUuid` 与 `renderImageBase64`，实现可优先使用 base64。
- roiRenderParams (object, optional, 见下表) — ROI 绘制样式参数。
- outputOptions (object, optional, 见下表) — 输出控制。
- roiRenderParams.enabled (boolean, optional, default=True) — 是否启用 ROI 渲染。独立 ROI_Render_API 调用时通常不需要传 false。
- roiRenderParams.renderContour (boolean, optional, default=True) — 是否绘制 ROI 轮廓。
- roiRenderParams.renderMaskOverlay (boolean, optional, default=False) — 是否绘制半透明 ROI 蒙版。
- roiRenderParams.overlayAlpha (number, optional, default=0.35, 0~1) — 半透明蒙版透明度。仅 `renderMaskOverlay=true` 时生效。
- roiRenderParams.contourColor (string, optional, default=#FFFF00, `#RRGGBB`、`R,G,B`、常见英文色名) — ROI 轮廓和蒙版颜色。默认黄色。
- roiRenderParams.renderColor (string, optional, 同上) — `contourColor` 的兼容别名。若同时提供，推荐以 `contourColor` 为准。
- roiRenderParams.color (string, optional, 同上) — 颜色兼容别名。
- roiRenderParams.contourWidthPixels (integer, optional, default=2, >=1) — ROI 轮廓粗细，像素单位。
- outputOptions.returnRenderedImageStoredFile (boolean, optional, default=True) — 是否保存并返回带 ROI 的渲染图。
- outputOptions.returnRenderedImageBase64 (boolean, optional, default=False) — 是否直接返回渲染图 Base64。
- outputOptions.returnRoiMaskStoredFile (boolean, optional, default=True) — 是否保存并返回 ROI Mask 图。
- outputOptions.returnRoiMaskBase64 (boolean, optional, default=False) — 是否直接返回 ROI Mask Base64。

## Segment_ROI_API_v10   [stage: segment]
从输入图片生成 ROI（细胞/颗粒等目标的轮廓）。当目标形状需要被分割、计数或后续测量时使用；按形状特性选 cellpose（圆形/核）或 threshold（强度阈值）。
Endpoint: POST /api/v10/segment-roi/run
Selector: segmentationMethod ∈ {threshold, cellpose, weka}; operation ∈ {run_segmentation, postprocess_binary_and_analyze, analyze_particles}

### 通用请求参数
- sessionId (string, required) — 会话 ID。
- workplanId (string, optional) — Workplan ID。
- stepId (string, optional) — 当前步骤 ID。
- segmentationMethod (string, required, enum: threshold|cellpose|weka) — 分割方法。
- operation (string, optional, if threshold/cellpose 时是, enum: run_segmentation|postprocess_binary_and_analyze|analyze_particles) — 执行动作。
- targetName (string, optional) — 目标名，当前分割服务主要透传。
- inputResources (object, required, 见各分支) — 输入资源引用。
- params (object, required, 见各分支) — 分割参数。
- roiRenderParams (object, optional, 见 ROI 渲染参数表) — ROI 自动渲染参数。
- outputOptions (object, optional, 见各分支) — 输出控制。
- roiRenderParams.renderImageResourceUuid (string, optional, 图片 storedFilename 或语义引用) — 被渲染的底图。
- roiRenderParams.renderImageBase64 (string, optional, Base64 或 data URL) — 直接传入底图。
- roiRenderParams.enabled (boolean, optional, default=True) — 是否启用自动 ROI 渲染。
- roiRenderParams.renderContour (boolean, optional, default=True) — 是否绘制 ROI 轮廓。
- roiRenderParams.renderMaskOverlay (boolean, optional, default=False) — 是否绘制半透明 ROI 蒙版。
- roiRenderParams.overlayAlpha (number, optional, default=0.35, 0~1) — 半透明蒙版透明度。
- roiRenderParams.contourColor (string, optional, default=#FFFF00, `#RRGGBB`、`R,G,B`、常见英文色名) — ROI 轮廓与蒙版颜色。
- roiRenderParams.contourWidthPixels (integer, optional, default=2, >=1) — ROI 轮廓粗细，像素单位。
- outputOptions.returnRoiRender (boolean, optional, default=False) — 是否启用自动 ROI 渲染。
- outputOptions.returnRenderedImage (boolean, optional, default=False) — ROI 渲染启用兼容开关。
- outputOptions.returnRenderedImageStoredFile (boolean, optional, default=True) — 是否保存并返回带 ROI 的渲染图。
- outputOptions.returnRenderedImageBase64 (boolean, optional, default=False) — 是否直接返回渲染图 Base64。
- outputOptions.returnRoiMaskStoredFile (boolean, optional, default=True) — 是否保存并返回 ROI Mask 图。
- outputOptions.returnRoiMaskBase64 (boolean, optional, default=False) — 是否直接返回 ROI Mask Base64。

### threshold: run_segmentation 请求参数
- inputResources.sourceImageResourceUuid (string, required, 图片 storedFilename 或语义引用) — 阈值分割输入灰度/图片资源。
- params.imagePreprocess (object, optional) — 灰度预处理参数。
- params.imagePreprocess.smooth (number, optional, default=0.0) — 平滑次数/强度。
- params.imagePreprocess.sharp (number, optional, default=0.0) — 锐化次数/强度。
- params.imagePreprocess.blur (number, optional, default=0.0) — 高斯模糊 sigma/强度。
- params.imagePreprocess.invert (boolean, optional, default=False) — 是否反相。
- params.thresholdParams.thresholdMin (integer, required, 0~255) — 阈值下限。
- params.thresholdParams.thresholdMax (integer, required, 0~255，且 >= thresholdMin) — 阈值上限。
- outputOptions.returnPreprocessedImage (boolean, optional, default=False) — 是否返回预处理图。
- outputOptions.returnBinaryImage (boolean, optional, default=True) — 是否返回二值图。

### threshold: postprocess_binary_and_analyze / analyze_particles 请求参数
- inputResources.binaryImageResourceUuid (string, required, 二值图 storedFilename 或语义引用) — 二值图输入。
- params.binaryPostprocess (object, optional, if postprocess_binary_and_analyze 时可选) — 二值图后处理。
- params.binaryPostprocess.fillHole (boolean, optional, default=False) — 是否填洞。
- params.binaryPostprocess.watershed (boolean, optional, default=False) — 是否 watershed 分割粘连区域。
- params.analyzeParticlesParams (object, optional) — Analyze Particles 参数；缺省使用默认值。
- params.analyzeParticlesParams.sizeMin (number, optional, default=20.0) — 最小面积。
- params.analyzeParticlesParams.sizeMax (number, optional, default=2000.0) — 最大面积。
- params.analyzeParticlesParams.circularityMin (number, optional, default=0.2) — 最小圆度。
- params.analyzeParticlesParams.circularityMax (number, optional, default=1.0) — 最大圆度。
- params.analyzeParticlesParams.excludeOnEdges (boolean, optional, default=False) — 是否排除边缘颗粒。
- params.analyzeParticlesParams.includeHoles (boolean, optional, default=False) — 是否包含孔洞。
- outputOptions.returnPostprocessedBinary (boolean, optional, default=True) — 是否返回后处理二值图。
- outputOptions.returnRoiZip (boolean, optional, default=True) — 是否返回 ROI zip。

### threshold: postprocess_binary_and_analyze / analyze_particles 请求参数
- inputResources.binaryImageResourceUuid (string, required, 二值图 storedFilename 或语义引用) — 二值图输入。
- params.binaryPostprocess (object, optional, if postprocess_binary_and_analyze 时可选) — 二值图后处理。
- params.binaryPostprocess.fillHole (boolean, optional, default=False) — 是否填洞。
- params.binaryPostprocess.watershed (boolean, optional, default=False) — 是否 watershed 分割粘连区域。
- params.analyzeParticlesParams (object, optional) — Analyze Particles 参数；缺省使用默认值。
- params.analyzeParticlesParams.sizeMin (number, optional, default=20.0) — 最小面积。
- params.analyzeParticlesParams.sizeMax (number, optional, default=2000.0) — 最大面积。
- params.analyzeParticlesParams.circularityMin (number, optional, default=0.2) — 最小圆度。
- params.analyzeParticlesParams.circularityMax (number, optional, default=1.0) — 最大圆度。
- params.analyzeParticlesParams.excludeOnEdges (boolean, optional, default=False) — 是否排除边缘颗粒。
- params.analyzeParticlesParams.includeHoles (boolean, optional, default=False) — 是否包含孔洞。
- outputOptions.returnPostprocessedBinary (boolean, optional, default=True) — 是否返回后处理二值图。
- outputOptions.returnRoiZip (boolean, optional, default=True) — 是否返回 ROI zip。

### cellpose: run_segmentation 请求参数
- inputResources.sourceImageResourceUuid (string, required, 图片 storedFilename 或语义引用) — Cellpose 输入图片。
- params.cellposeParams (object, required) — Cellpose 参数。
- params.cellposeParams.model (string, optional, 例如 `zhijing_if_nuclei`) — Cellpose 模型名。
- params.cellposeParams.diameter (number, required, >0) — 细胞/细胞核直径。
- params.cellposeParams.flowThreshold.min (number, required) — flow threshold 扫描下限。
- params.cellposeParams.flowThreshold.max (number, required) — flow threshold 扫描上限。
- params.cellposeParams.cellprobThreshold.min (number, required) — cellprob threshold 扫描下限。
- params.cellposeParams.cellprobThreshold.max (number, required) — cellprob threshold 扫描上限。
- outputOptions.returnRoiZip (boolean, optional) — 是否返回 ROI zip 引用。

### weka: run_segmentation 请求参数
- inputResources.sourceImageResourceUuid (string, required, 图片 storedFilename 或语义引用) — Weka 输入图片。
- inputResources.classifierResourceUuid (string, required, Weka classifier 文件 storedFilename) — 已训练分类器文件。
- params.wekaParams.returnProbability (boolean, optional, default=False) — 是否返回概率图。
- params.wekaParams.selectedClassIndex (integer, optional, if returnProbability=true 时建议提供, default=1) — 选择概率栈中的类别索引。
- outputOptions.returnResultImage (boolean, optional) — 是否保存结果图。
- outputOptions.returnResultImageBase64 (boolean, optional) — 是否返回结果图 Base64。
