# API Catalog (stage-grouped — Stage-1 selection menu)

## deconvolve
- **Pic_Split_API_v10** — 当分析目标只占复合图中的某个染色或通道，需要先把它从复合图里分离出来再做分割/测量时使用。rgb_split 拆分 RGB 通道；color_deconvolution 做 H&E、DAB 等颜色解卷。  `POST /api/v10/pic-split/run`

## segment
- **Segment_ROI_API_v10** — 从输入图片生成 ROI（细胞/颗粒等目标的轮廓）。当目标形状需要被分割、计数或后续测量时使用；按形状特性选 cellpose（圆形/核）或 threshold（强度阈值）。  `POST /api/v10/segment-roi/run`  · methods: cellpose, threshold, weka

## target
- **Create_Target_API_v10** — 当一份生成的 ROI 需要绑定成可被后续步骤（测量、公式）按名引用的可复用 target 时使用；也用于把 Measure_ROI 筛选后的 ROI 派生为新 target。  `POST /api/v10/create-target/run`

## measure
- **Measure_ROI_API_v10** — 当需要逐对象的属性值（面积、平均强度、圆度等），或需要按这些属性筛选对象并生成新 ROI（如筛出 Ki67 阳性细胞）时使用。  `POST /api/v10/measure-roi/run`

## calculate
- **Formula_API_v10** — 当最终结果是对已测量 target 的计算量或比值（计数、比例、OD/IOD 等），需要把测量值汇总成报表/答案时使用。  `POST /api/v10/formula/run`

## render
- **ROI_Render_API_v10** — 当需要把 ROI 以轮廓或半透明蒙版形式绘制到底图上、单独生成可视化图片（用于审阅或输出）时使用，与分割/测量解耦。  `POST /api/v10/roi-render/run`

## shared / utility
- **Get_File_API_v10** — 当需要按 storedFilename 取回服务端已存文件的字节（如结果图、ROI zip）时使用。  `POST /api/v10/files/get`
- **Get_Target_API_v10** — 当需要按 targetName 查询某个已创建 target 的 binding 及其创建时填入的参数（用于追溯或复用）时使用。  `GET /api/v10/get-target/run?sessionId=<sessionId>&targetName=<targetName>`  · methods: GET, POST
- **Put_File_API_v10** — 当原始字节（上传的图片、分类器文件等）需要先存到服务端、换取后续 API 可引用的 storedFilename 时使用。  `POST /api/v10/files/put`
