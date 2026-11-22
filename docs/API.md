# 接口

模块GET使用仓内样例，模块POST可传csv或rows与context，直接计算当前规则。/api/runs使用完整流水线并原子保存。每个阶段返回rows、quarantine、metrics；后续阶段还返回累计隔离。/api/upload接收multipart文件file。/api/runs/<id>/archive只导出一份带清单与证据的CSV。

## 超限分块

- `POST /api/sources/<source>/parts/<n>`：multipart `file` + `parts`（总块数）+ 可选 `params`（JSON）。单块≤4MB，n∈1..parts。返回 `{parts,received,missing,complete,bytes,part_digests}`。
- `GET /api/sources/<source>`：来源收块进度与各块 sha256。
- `POST /api/sources/<source>/finalize`：收齐后拼接、归集、计算并保存批次，返回完整 run。未收齐409 `CHUNK_INCOMPLETE`；块内容冲突409 `SOURCE_CONFLICT`；参数或总数不一致409。
- `GET /api/sources/<source>/runs`：该来源已产生的批次（正常只有一个；同源重试幂等）。

## 结果与证据

- `GET /api/runs`：历史批次，含 `source`。
- `GET /api/runs/<id>`：完整批次，含 `manifest.lineage`（逐条去向是否完整）。
- `GET /api/runs/<id>/settlement`：可发布的卡日结算 CSV，一行一个「卡号+业务日」，列含凭证、换乘依据、封顶依据、处理位置、来源行、分块、应扣实扣差额与合计。
- `GET /api/runs/<id>/archive`：逐条来源证据 CSV；逐条去向不完整时409 `LINEAGE_INCOMPLETE`。
- `POST /api/runs/<id>/review`：需 `version` 与 `decision`；陈旧版本409。

页面：`/` 与 `/discounts` 展示卡日结算；`/batches` 为批次复核页，按来源列出分块收齐情况，并沿超限日批展开每个卡日的凭证、换乘/封顶依据、处理位置与逐事件明细。
