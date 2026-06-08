# API Specifications (compiled — authoritative)

## Create_Target_API_v10   [stage: target]
当一份生成的 ROI 需要绑定成可被后续步骤（测量、公式）按名引用的可复用 target 时使用；也用于把 Measure_ROI 筛选后的 ROI 派生为新 target。
Endpoint: POST /api/v10/create-target/run
Selector: operation ∈ {bindSegmentRoi, bindMeasureRoi, bindExistingRoi}; sourceType ∈ {segment_roi, measure_roi, existing_roi, target_roi_variant}

### 请求参数
- sessionId (string, required) — 会话 ID。
- workplanId (string, optional) — Workplan ID。
- stepId (string, required) — 当前 Create_Target 步骤 ID。
- operation (string, required, enum: bindSegmentRoi|bindMeasureRoi|bindExistingRoi) — 创建 target 的动作。`bindExistingRoi` 为兼容旧版的通用绑定；推荐新 Workplan 使用 `bindSegmentRoi` 或 `bindMeasure
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

## Formula_API_v10   [stage: calculate]
当需要产出最终报表/答案——对最终 target 的计数、比例、OD/IOD 等计算量或比值——时使用。
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

## Pic_Split_API_v10   [stage: deconvolve]
当分析目标只占复合图中的某个染色或通道，需要先把它从复合图里分离出来再做分割/测量时使用。rgb_split 拆分 RGB 通道；color_deconvolution 做 H&E、DAB 等颜色解卷。
Endpoint: POST /api/v10/pic-split/run
Selector: splitMethod ∈ {rgb_split, color_deconvolution}

### 请求参数
- sessionId (string, required) — 会话 ID。
- inputImage (object, required, FileRefDto) — 输入图片引用。
- inputImage.storedFilename (string, required, Put_File 返回的 storedFilename) — 服务端已存储图片文件名。
- inputImage.originalFilename (string, optional) — 原始文件名，仅用于描述。
- splitMethod (string, required, enum: rgb_split|color_deconvolution) — 拆分方式。
- colorDeconvParams (object, optional, if `splitMethod=color_deconvolution` 时建议提供, 见下表) — 颜色反卷积参数；缺省时使用 H DAB。
- outputOptions (object, optional, 见下表) — 输出控制。

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

## Segment_ROI_API_v10   [stage: segment]
从输入图片生成 ROI（细胞/颗粒等目标的轮廓）。当目标形状需要被分割、计数或后续测量时使用；按形状特性选 cellpose（圆形/核）或 threshold（强度阈值）。
Endpoint: POST /api/v10/segment-roi/run
Selector: segmentationMethod ∈ {threshold, cellpose, weka}; operation ∈ {run_segmentation, postprocess_binary_and_analyze, analyze_particles}

### 通用请求参数
- sessionId (string, required) — 会话 ID。
- workplanId (string, optional) — Workplan ID。
- segmentationMethod (string, required, enum: threshold|cellpose|weka) — 分割方法。
- operation (string, optional, if threshold/cellpose 时是, enum: run_segmentation|postprocess_binary_and_analyze|analyze_particles) — 执行动作。
- inputResources (object, required, 见各分支) — 输入资源引用。
- params (object, required, 见各分支) — 分割参数。

### cellpose: run_segmentation 请求参数
- inputResources.sourceImageResourceUuid (string, required, 图片 storedFilename 或语义引用) — Cellpose 输入图片。
- params.cellposeParams (object, required) — Cellpose 参数。
- params.cellposeParams.model (string, optional, enum: zhijing_if_nuclei) — Cellpose 模型名。
- params.cellposeParams.diameter (number, required, >0) — 细胞/细胞核直径。
- params.cellposeParams.flowThreshold.min (number, required) — flow threshold 扫描下限。
- params.cellposeParams.flowThreshold.max (number, required) — flow threshold 扫描上限。
- params.cellposeParams.cellprobThreshold.min (number, required) — cellprob 扫描下限。
- params.cellposeParams.cellprobThreshold.max (number, required) — cellprob 扫描上限。
- outputOptions.returnRoiZip (boolean, optional, default=True) — 是否返回 ROI zip 引用。

### threshold: analyze_particles 请求参数
- inputResources.binaryImageResourceUuid (string, required, storedFilename) — 二值图资源。
- params.analyzeParticlesParams.sizeMin (number, optional, default=20.0) — 最小面积。
- params.analyzeParticlesParams.sizeMax (number, optional, default=2000.0) — 最大面积。
- params.analyzeParticlesParams.circularityMin (number, optional, default=0.2) — 最小圆度。
- params.analyzeParticlesParams.excludeOnEdges (boolean, optional, default=False) — 是否排除边缘颗粒。
