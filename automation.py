"""Free historical daily data via BaoStock. No 09:29 realtime claims."""
import argparse, datetime as dt, json, os, time
from pathlib import Path
from types import SimpleNamespace
import baostock as bs
import pandas as pd
from strategy import evaluate

ROOT=Path(__file__).parent
OUT=ROOT/'results'; OUT.mkdir(exist_ok=True)
FIELDS='date,code,open,high,low,close,volume,pctChg,tradestatus,isST'
ARGS=SimpleNamespace(sideways=15,band=.16,quiet_ratio=.85,volume_multiple=3.0,day2_body=.04,day2_volume=1.0,day3_volume=.70,ma_tolerance=.015)

def records(query):
    if query.error_code!='0': raise RuntimeError(query.error_msg)
    rows=[]
    while query.next(): rows.append(query.get_row_data())
    return pd.DataFrame(rows,columns=query.fields)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--mode',choices=['close','open'],default='close'); ap.add_argument('--limit',type=int,default=0); args=ap.parse_args()
    if args.mode=='open':
        raise SystemExit('9:29集合竞价数据源尚未接入；禁止用历史日线冒充实时开盘价。')
    now=dt.datetime.now(dt.timezone(dt.timedelta(hours=8)))
    status={'run_time_bjt':now.isoformat(),'mode':'close','provider':'BaoStock','status':'running','checked':0,'errors':0,'matches':0}
    (OUT/'status.json').write_text(json.dumps(status,ensure_ascii=False,indent=2),encoding='utf-8')
    login=bs.login()
    if login.error_code!='0': raise RuntimeError('BaoStock登录失败: '+login.error_msg)
    results=[]; errors=[]
    try:
        end=now.date(); start=end-dt.timedelta(days=260)
        stocks=records(bs.query_stock_basic())
        stocks=stocks[(stocks['type']=='1')&(stocks['status']=='1')]
        stocks=stocks[stocks['code'].str.match(r'^(sh\.60[0135]|sz\.(000|001|002|003|300|301))')]
        if args.limit: stocks=stocks.head(args.limit)
        for _,s in stocks.iterrows():
            code=s['code']; rawcode=code.split('.')[1]
            try:
                q=records(bs.query_history_k_data_plus(code,FIELDS,start_date=start.isoformat(),end_date=end.isoformat(),frequency='d',adjustflag='2'))
                if len(q)<ARGS.sideways+35: continue
                q=q[(q['tradestatus']=='1')&(q['isST']!='1')]
                if q.empty: continue
                d=q.rename(columns={'date':'日期','open':'开盘','high':'最高','low':'最低','close':'收盘','volume':'成交量','pctChg':'涨跌幅'})
                # Exclude securities whose listing history is too short.
                if len(d)<60: continue
                hit=evaluate(d,rawcode,s.get('code_name',rawcode),ARGS)
                if hit: results.append(hit)
            except Exception as e: errors.append({'code':code,'error':str(e)})
            status['checked']+=1
            if status['checked']%250==0: print(f"checked={status['checked']} matches={len(results)} errors={len(errors)}",flush=True)
        status.update(status='partial' if errors else 'success',errors=len(errors),matches=len(results),total_universe=len(stocks))
        pd.DataFrame(results,columns=['代码','名称','第三日日期','第三日收盘','MA25','横盘振幅%','横盘量比','首日放量倍数','次日实体%','次日量/首日量','第三日量/次日量','距MA25%']).to_csv(OUT/'candidates.csv',index=False,encoding='utf-8-sig')
        pd.DataFrame(errors,columns=['code','error']).to_csv(OUT/'errors.csv',index=False,encoding='utf-8-sig')
        (OUT/'status.json').write_text(json.dumps(status,ensure_ascii=False,indent=2),encoding='utf-8')
        print(status,flush=True)
        if errors and len(errors)>max(10,len(stocks)*0.1): raise RuntimeError('超过10%股票数据获取失败，结果不完整')
    except Exception as e:
        status.update(status='failed',error=str(e),errors=len(errors))
        (OUT/'status.json').write_text(json.dumps(status,ensure_ascii=False,indent=2),encoding='utf-8')
        raise
    finally: bs.logout()
if __name__=='__main__': main()
