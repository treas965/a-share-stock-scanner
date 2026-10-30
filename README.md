# A股四日形态雷达（免费历史行情版）

这是**完整替换包**。在 GitHub 仓库根目录上传包内文件，保留 `.github/workflows/main.yml` 路径。Streamlit 主文件 `app.py`。

- 使用 BaoStock 免费历史日K线，无需 Tushare Token、无需购买积分。
- GitHub Actions 定时为北京时间工作日 15:40（不保证准时；非交易日暂未做严格交易日历校验）。
- 首次运行可在 Actions -> A-share Free Close Scan -> Run workflow 填 `limit=100` 测试；确认成功后改 `0` 全量。全量首次可能较慢并遇到接口限制。
- 网页只读取 GitHub 仓库中的 `results/` 文件；如果 Streamlit 部署不会及时同步提交，需手动重启应用。
- **不提供9:29集合竞价行情**。当前无法保证免费数据源在9:29提供可信开盘价，故不做虚假确认。
- `strategy.py` 复用旧版筛选算法，首日涨停为近似涨幅判断，非交易所逐价位涨停校验；复权口径会影响识别，需要回测验证。
- `results/status.json` 显示扫描状态，失败不等于0只命中。
- `TUSHARE_TOKEN` 可以继续留在 GitHub Secrets，本版不会读取它。
