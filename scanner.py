#!/usr/bin/env python3
"""A股四日形态扫描。pip install akshare pandas numpy requests"""
import argparse
import datetime as dt
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import numpy as np
import pandas as pd
import akshare as ak


def evaluate(df, code, name, args):
    d = df.copy()
    if d.empty or len(d) < args.sideways + 35:
        return None
    d['日期'] = pd.to_datetime(d['日期'])
    for c in ['开盘','收盘','最高','最低','成交量','涨跌幅']:
        d[c] = pd.to_numeric(d[c], errors='coerce')
    d = d.sort_values('日期').dropna(subset=['开盘','收盘','最高','最低','成交量'])
    if len(d) < args.sideways + 35: return None
    d['ma25'] = d['收盘'].rolling(25).mean()
    d['vma5prev'] = d['成交量'].shift(1).rolling(5).mean()
    # 最后一天为第三天，筛选次日（第四天）候选；第四天开盘须次日盘中验证
    a, b, c = d.iloc[-3], d.iloc[-2], d.iloc[-1]
    pre = d.iloc[-3-args.sideways:-3]
    if len(pre) != args.sideways: return None
    # 前期窄幅整理 + 相对低量（不是对主力吸筹的直接证明）
    band = pre['最高'].max()/pre['最低'].min()-1
    pre_v = pre['成交量'].mean()
    prior_v = d.iloc[-3-args.sideways-20:-3-args.sideways]['成交量'].mean()
    if band > args.band or not np.isfinite(prior_v) or pre_v > prior_v*args.quiet_ratio: return None
    # 首日涨停：按板块设置近似涨幅阈值，并要求收盘贴近最高价
    limit = 0.195 if code.startswith(('300','301')) else 0.095
    if a['涨跌幅'] < limit*100 or a['收盘'] < a['最高']*0.997: return None
    if a['成交量'] < args.volume_multiple*a['vma5prev']: return None
    # 第二日大阳：实体幅度与第一日量能比较
    body2 = b['收盘']/b['开盘']-1
    if body2 < args.day2_body or b['成交量'] < a['成交量']*args.day2_volume: return None
    # 第三日缩量、阴线或假阳（涨幅小但实体可阳），且守住MA25
    body3 = c['收盘']/c['开盘']-1
    pseudo_yang = (body3 >= 0 and c['收盘'] <= b['收盘']*1.005)
    if not (body3 < 0 or pseudo_yang): return None
    if c['成交量'] > b['成交量']*args.day3_volume: return None
    if c['收盘'] < c['ma25'] or c['最低'] < c['ma25']*(1-args.ma_tolerance): return None
    return {'代码':code,'名称':name,'第三日日期':c['日期'].strftime('%Y-%m-%d'),
            '第三日收盘':round(c['收盘'],2),'MA25':round(c['ma25'],2),
            '横盘振幅%':round(band*100,2),'横盘量比':round(pre_v/prior_v,2),
            '首日放量倍数':round(a['成交量']/a['vma5prev'],2),
            '次日实体%':round(body2*100,2),'次日量/首日量':round(b['成交量']/a['成交量'],2),
            '第三日量/次日量':round(c['成交量']/b['成交量'],2),
            '距MA25%':round((c['收盘']/c['ma25']-1)*100,2)}


def fetch_one(code, name, args):
    try:
        end = dt.date.today().strftime('%Y%m%d')
        start = (dt.date.today()-dt.timedelta(days=240)).strftime('%Y%m%d')
        df = ak.stock_zh_a_hist(symbol=code,period='daily',start_date=start,end_date=end,adjust='qfq')
        return evaluate(df,code,name,args)
    except Exception as exc:
        return ('ERROR',code,str(exc))


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--sideways',type=int,default=15,help='横盘交易日数')
    p.add_argument('--band',type=float,default=.16,help='横盘最高最低振幅上限')
    p.add_argument('--quiet-ratio',type=float,default=.85,help='横盘均量/此前20日均量上限')
    p.add_argument('--volume-multiple',type=float,default=3.0)
    p.add_argument('--day2-body',type=float,default=.04)
    p.add_argument('--day2-volume',type=float,default=1.0)
    p.add_argument('--day3-volume',type=float,default=.70)
    p.add_argument('--ma-tolerance',type=float,default=.015)
    p.add_argument('--workers',type=int,default=4)
    p.add_argument('--out',default='scan_results.csv')
    args=p.parse_args()
    spot=ak.stock_zh_a_spot_em()
    spot['代码']=spot['代码'].astype(str).str.zfill(6)
    spot=spot[spot['代码'].str.startswith(('000','001','002','003','300','301','600','601','603','605'))]
    spot=spot[~spot['名称'].astype(str).str.contains('ST|退',case=False,regex=True)]
    results=[]; errors=[]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures=[pool.submit(fetch_one,r['代码'],r['名称'],args) for _,r in spot.iterrows()]
        for i,f in enumerate(as_completed(futures),1):
            item=f.result()
            if isinstance(item,tuple): errors.append(item)
            elif item is not None: results.append(item)
            if i%300==0: print(f'已检查 {i}/{len(futures)}，命中 {len(results)}，失败 {len(errors)}')
    out=pd.DataFrame(results)
    if not out.empty: out=out.sort_values(['首日放量倍数','距MA25%'],ascending=[False,True])
    out.to_csv(args.out,index=False,encoding='utf-8-sig')
    print(f'筛选完成：{len(results)}只，失败{len(errors)}只，保存至 {Path(args.out).resolve()}')
    if errors: pd.DataFrame(errors,columns=['状态','代码','错误']).to_csv('scan_errors.csv',index=False,encoding='utf-8-sig')

if __name__=='__main__': main()
