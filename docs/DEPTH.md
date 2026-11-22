# 深度登记 公交刷卡换乘优惠与日封顶回算

规模：中型。使用者：公交清分中心复核员。核心规则：换乘按上次有效付费行程的时间窗计算，优惠与日封顶按确定顺序裁决并保留分币守恒。

## 功能模块

| 模块 | 使用者动作 | 入口 | 核心文件 | 测试 |
|---|---|---|---|---|
| M1 刷卡采信 | 查看并运行刷卡采信 | `/api/taps` | `app/modules/m1_taps/rules.py` | `tests/test_m1.py` |
| M2 线路换乘 | 查看并运行线路换乘 | `/api/routes` | `app/modules/m2_routes/rules.py` | `tests/test_m2.py` |
| M3 票价版本 | 查看并运行票价版本 | `/api/fares` | `app/modules/m3_fares/rules.py` | `tests/test_m3.py` |
| M4 行程配对 | 查看并运行行程配对 | `/api/journeys` | `app/modules/m4_journeys/rules.py` | `tests/test_m4.py` |
| M5 优惠回算 | 查看并运行优惠回算 | `/api/discounts` | `app/modules/m5_discounts/rules.py` | `tests/test_m5.py` |
| M6 清分对账 | 查看并运行清分对账 | `/api/clearing` | `app/modules/m6_clearing/rules.py` | `tests/test_m6.py` |
| M7 日结归档 | 查看并运行日结归档 | `/api/settlement` | `app/modules/m7_settlement/rules.py` | `tests/test_m7.py` |

## 陷阱登记

| TRAP | 现象 | 朴素实现 | 本项目处理 | 处理位置 | 测试 |
|---|---|---|---|---|---|
| TRAP-01 | 旧编码 | 默认解码失败 | 回退GB18030 | `app/modules/m1_taps/rules.py` | `tests/test_m1.py::test_legacy_encoding_real_sample` |
| TRAP-02 | BOM | 首列名多字符 | utf-8-sig | `app/modules/m1_taps/rules.py` | `tests/test_m1.py::test_bom_real_sample` |
| TRAP-03 | 带引号换行 | 拆成两条 | csv逻辑行 | `app/modules/m1_taps/rules.py` | `tests/test_m1.py::test_quoted_newline_is_one_record` |
| TRAP-05 | 列数不匹配 | 静默错列 | 隔离原行 | `app/modules/m1_taps/rules.py` | `tests/test_m1.py::test_bad_columns_real_sample` |
| TRAP-08 | 前导零ID | 编码变形 | 全程字符串 | `app/modules/m1_taps/rules.py` | `tests/test_m1.py::test_identifier_preserved_real_sample` |
| TRAP-14 | 重复键冲突 | 后写覆盖 | 保留首条并隔离冲突行 | `app/modules/m1_taps/rules.py` | `tests/test_m1.py::test_duplicate_conflict_real_sample` |
| TRAP-18 | 空态三态 | 一律成功 | 分别错误码 | `app/modules/m1_taps/rules.py` | `tests/test_m1.py::test_three_empty_states` |
| TRAP-26 | 旧版本提交 | 覆盖新结果 | 版本条件更新 | `app/store.py` | `tests/test_e2e.py::test_stale_review_409` |
| TRAP-06 | 全角数字 | 转换失败 | NFKC与Decimal | `app/values.py` | `tests/test_m3.py::test_thousands_and_fullwidth` |
| TRAP-07 | 金额哨兵 | 零参与扣费 | 空值隔离 | `app/values.py` | `tests/test_m3.py::test_real_sentinel_quarantined` |
| TRAP-11 | 混合偏移 | 落错版本 | UTC归整 | `app/values.py` | `tests/test_m3.py::test_timezone_equal` |
| TRAP-23 | 换乘截止点 | 重复优惠 | 截止点排除 | `app/modules/m5_discounts/rules.py` | `tests/test_m5.py::test_exact_window_excluded` |
| TRAP-25 | 票价重叠 | 随意取版 | 冲突隔离 | `app/modules/m3_fares/rules.py` | `tests/test_m3.py::test_overlap_rejected` |

## 对账规则

输入原始逻辑行=最终采纳来源行+隔离来源行+重复行+空白行+分段表头。派生记录用_sources保存完整来源，因此分组不丢行。业务预期合计与上游申报合计之差等于逐行差异之和。结果按输入摘要、规则版本及参数产生唯一批次，事务写入；同源重跑只复用已有批次。

## 超限批次与卡日归集（2026.11.22-r2）

| TRAP | 现象 | 朴素实现 | 本项目处理 | 处理位置 | 测试 |
|---|---|---|---|---|---|
| TRAP-31 | 月末文件超4MB | 整包拒收 | 分块上传后拼接 | `app/store.py` | `tests/test_m10_api.py::test_chunked_source_is_idempotent_and_single_batch` |
| TRAP-32 | 同卡日跨块 | 按块接续状态，换乘/封顶少算多算 | 先按卡号+业务日归集再算 | `app/modules/m5_discounts/rules.py` | `tests/test_m9_chunking.py::test_card_day_reaggregation_beats_chunk_boundary` |
| TRAP-33 | 同源重试 | 每块都新建批次 | source幂等键+同块sha比对 | `app/store.py` | `tests/test_m10_api.py::test_retry_same_part_updates_without_new_batch` |
| TRAP-34 | 处理中断 | 半成品覆盖旧版 | 算完才 INSERT OR IGNORE | `app/pipeline.py` | `tests/test_m10_api.py::test_failed_finalize_keeps_previous_complete_version` |
| TRAP-35 | 缺逐条去向 | 照常封存 | 去向守恒校验，不完整即拒 | `app/lineage.py` | `tests/test_m10_api.py::test_seal_requires_lineage` |
| TRAP-36 | 上传重试删原块 | 原始刷卡丢失 | 同块冲突保留原块并409 | `app/store.py` | `tests/test_m10_api.py::test_conflicting_part_is_refused_and_original_kept` |
| TRAP-37 | 记录跨块 | 位置无法追溯 | 记录起止行映射到分块区间 | `app/modules/m1_taps/rules.py` | `tests/test_m10_api.py::test_chunked_source_is_idempotent_and_single_batch` |

### 裁决：归集优先于接续

采用「分块只作传输边界；计算前对同一来源重新按卡号+业务日归集，再统一裁决换乘与封顶」。理由是接续方案要求块与卡日严格对齐，而月末超限文件按字节切块必然切在卡日中间，且重试/补块会改变块边界，接续状态一旦错位就会系统性少算换乘或多算封顶，且难以在复核页证明。归集方案把状态边界绑定到业务键而非传输边界，分块顺序、重试与补块都不影响结果，可直接与整包上传结果逐行比对（见测试）。

## 已知不覆盖

分块上传覆盖单文件超4MB的整包场景，但单个来源总量仍限64MB、256块；更大规模需先按业务键拆分来源。不模拟生产支付与外部回调。人工复核只变更批次状态，不改写原始记录；原始分块与来源摘要保留，不随批次清理。
