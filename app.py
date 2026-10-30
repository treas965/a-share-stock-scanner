import json
from pathlib import Path
import pandas as pd
import streamlit as st
st.set_page_config(page_title='A股四日形态雷达',layout='wide')
st.title('A股四日形态雷达 · 免费行情版')
st.caption('数据源：BaoStock历史日线。收盘候选名单不等于次日开盘确认；9:29实时集合竞价暂未接入。')
root=Path(__file__).parent/'results'; status=root/'status.json'; candidates=root/'candidates.csv'
if not status.exists():
 st.warning('尚无后台扫描记录。请在GitHub Actions手动运行 close 模式。')
else:
 s=json.loads(status.read_text(encoding='utf-8'))
 st.write(f"最近扫描：{s.get('run_time_bjt','未知')} ｜ 状态：{s.get('status','未知')} ｜ 已检查：{s.get('checked',0)} ｜ 数据错误：{s.get('errors',0)}")
 if s.get('status')!='success': st.error('数据未完整验证：请查看GitHub Actions日志。不能将结果视为全市场完整筛选。')
 if s.get('error'): st.code(s['error'])
 if candidates.exists():
  df=pd.read_csv(candidates,dtype={'代码':str})
  st.metric('候选股票数（仅收盘形态）',len(df))
  st.dataframe(df,use_container_width=True,hide_index=True)
  st.download_button('下载CSV',candidates.read_bytes(),'candidates.csv','text/csv')
 else: st.info('尚无候选名单文件。')
st.info('策略参数：横盘15日、振幅≤16%、横盘量比≤0.85、首日量≥前5日均量3倍、次日实体≥4%且不缩量、第三日量≤次日70%并守住MA25。')
