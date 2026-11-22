from pathlib import Path
import os
ROOT=Path(__file__).resolve().parent.parent
DATA_DIR=Path(os.environ.get("DATA_DIR", "/tmp/transitcap"))
TITLE='公交刷卡换乘优惠与日封顶回算'
SHORT='transitcap'
COLUMNS=['event_id', 'card', 'route', 'event_time', 'result', 'reported', 'note']
MODULES=[('taps', '刷卡采信'), ('routes', '线路换乘'), ('fares', '票价版本'), ('journeys', '行程配对'), ('discounts', '优惠回算'), ('clearing', '清分对账'), ('settlement', '日结归档')]
RULE_VERSION="2026.11.22-r2"
# 单次请求上限（与 Flask MAX_CONTENT_LENGTH 一致）。月末大文件按块上传，单块不得超过此值。
MAX_UPLOAD_BYTES=4*1024*1024
# 同一逻辑来源（可跨多个分块）的总量上限，防止无限拼接占满内存。
MAX_SOURCE_BYTES=64*1024*1024
MAX_PARTS=256
