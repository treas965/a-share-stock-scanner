"""Cloud scheduled jobs: close candidates and 09:29 indicative open check.
No claim of guaranteed exchange-grade opening prices. Data failures never mean zero matches.
"""
import argparse
import datetime as dt
import json
import time
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd
import akshare as ak
from scanner import evaluate
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parent
DATA=ROOT/'data'; DATA.mkdir(exist_ok=True)
TZ=ZoneInfo('Asia/Shanghai')
CODES=('000','001','002','003','300','301','600','601','603','605')
ARGS=SimpleNamespace(sideways=15,band=.16,quiet_ratio=.85,volume_multiple=3.0,day2_body=.04,day2_volume=1.0,day3_volume=.70,ma_tolerance=.015)

def universe():
    try:
        x=ak.stock_info_a_code_name()[['code','name']].rename(columns={'code':'代码','name':'名称'})
    except Exception as exc:
        raise RuntimeError(f'股票列表获取失败: {exc}') from exc
    x['代码']=x['代码'].astype(str).str.zfill(6)
    return x[x['代码'].str.startswith(CODES)&~x['名称'].str.contains('ST|退',case=False,na=False)].drop_duplicates('代码')

def fetch_history(code, end):
    start=(end-dt.timedelta(days=300)).strftime('%Y%m%d')
    last=None
    for k in range(2):
        try:
            return ak.stock_zh_a_hist(symbol=code,period='daily',start_date=start,end_date=end.strftime('%Y%m%d'),adjust='qfq')
        except Exception as exc:
            last=exc
            time.sleep(1.5*(k+1))
    raise RuntimeError(str(last))

def close_scan(limit=0):
    now=dt.datetime.now(TZ)
    if now.weekday()>4: print('周末跳过'); return
    stocks=universe()
    if limit: stocks=stocks.head(limit)
    hits=[]; failures=[]; checked=0
    for row in stocks.itertuples(index=False):
        try:
            d=fetch_history(row.代码,now.date())
            if d.empty: raise ValueError('空K线')
            # Ensure last trading day is today. Prevent silently using stale candles.
            if pd.to_datetime(d['日期']).max().date()!=now.date():
                raise ValueError('最新日K非今日，行情可能未更新或休市')
            hit=evaluate(d,row.代码,row.名称,ARGS)
            if hit: hits.append(hit)
            checked+=1
        except Exception as exc:
            failures.append({'代码':row.代码,'错误':str(exc)[:160]})
        if (checked+len(failures))%200==0: print('进度',checked+len(failures),'/',len(stocks),flush=True)
        time.sleep(.12) # conservative pacing; not a guarantee against limits
    meta={'阶段':'第三日收盘候选','运行时间':now.isoformat(),'股票总数':len(stocks),'成功获取':checked,'失败':len(failures),'命中':len(hits),'数据完整':len(failures)==0}
    pd.DataFrame(hits,columns=['代码','名称','第三日日期','第三日收盘','MA25','横盘振幅%','横盘量比','首日放量倍数','次日实体%','次日量/首日量','第三日量/次日量','距MA25%']).to_csv(DATA/'candidates.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(failures,columns=['代码','错误']).to_csv(DATA/'errors.csv',index=False,encoding='utf-8-sig')
    (DATA/'close_status.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf8')
    print(meta)
    if checked==0: raise RuntimeError('所有日K请求失败；请检查数据源，不可视为零命中')

def open_check():
    now=dt.datetime.now(TZ)
    if now.weekday()>4: print('周末跳过'); return
    file=DATA/'candidates.csv'
    if not file.exists(): raise RuntimeError('缺少前一交易日收盘候选文件；请先完成收盘扫描')
    x=pd.read_csv(file,dtype={'代码':str})
    if x.empty: print('候选为空，无需开盘验证'); return
    dates=pd.to_datetime(x['第三日日期']).dt.date
    # Candidate must be from a preceding day, not same-day or ancient.
    if not all((now.date()-day).days in (1,2,3,4) for day in dates):
        raise RuntimeError('候选日期过旧或不合理，拒绝验证')
    try:
        spot=ak.stock_zh_a_spot_em()
    except Exception as exc:
        raise RuntimeError(f'09:29快照获取失败，保留旧结果: {exc}') from exc
    spot['代码']=spot['代码'].astype(str).str.zfill(6)
    spot['今开']=pd.to_numeric(spot['今开'],errors='coerce')
    spot['最新价']=pd.to_numeric(spot['最新价'],errors='coerce')
    joined=x.merge(spot[['代码','今开','最新价']],on='代码',how='left')
    joined['MA25']=pd.to_numeric(joined['MA25'],errors='coerce')
    # MA25 for current day: replace oldest of prior 25 closes, NOT simply compare against prior MA25.
    # We cannot recompute precisely from candidate row alone. Mark as provisional only.
    joined['初步高于昨日MA25']=joined['今开']>=joined['MA25']
    joined['状态']=joined.apply(lambda r:'待行情核实' if pd.isna(r['今开']) or r['今开']<=0 else ('初步符合（非最终确认）' if r['初步高于昨日MA25'] else '未通过初步比较'),axis=1)
    joined['快照获取时间']=now.isoformat()
    joined.to_csv(DATA/'opening_check.csv',index=False,encoding='utf-8-sig')
    print('完成初步验证',len(joined),'只；行情快照非交易所认证开盘价，非最终MA25确认')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['close','open']);p.add_argument('--limit',type=int,default=0);a=p.parse_args()
    close_scan(a.limit) if a.mode=='close' else open_check()
