import datetime as dt
from concurrent.futures import ThreadPoolExecutor, as_completed
from types import SimpleNamespace
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import akshare as ak
from scanner import evaluate

st.set_page_config(page_title='A股 · 四日形态雷达',page_icon='📈',layout='wide')
st.markdown('''<style>.stApp{background:#0b1220;color:#e6edf7}div[data-testid="stMetric"]{background:#172338;border:1px solid #263a56;border-radius:14px;padding:14px}.block-container{padding-top:2rem}h1,h2,h3{color:#e6edf7}</style>''',unsafe_allow_html=True)
st.title('A股 · 四日形态雷达')
st.caption('横盘缩量 → 三倍量涨停 → 放量大阳 → 缩量守住 MA25 → 次日开盘确认｜研究观察工具，不构成投资建议')

@st.cache_data(ttl=3600,show_spinner=False)
def universe():
    x=ak.stock_zh_a_spot_em()[['代码','名称']].copy()
    x['代码']=x['代码'].astype(str).str.zfill(6)
    x=x[x['代码'].str.startswith(('000','001','002','003','300','301','600','601','603','605'))]
    return x[~x['名称'].astype(str).str.contains('ST|退',case=False,regex=True)].drop_duplicates('代码')

@st.cache_data(ttl=3600,show_spinner=False)
def hist(code):
    today=dt.date.today()
    return ak.stock_zh_a_hist(symbol=code,period='daily',start_date=(today-dt.timedelta(days=280)).strftime('%Y%m%d'),end_date=today.strftime('%Y%m%d'),adjust='qfq')

with st.sidebar:
    st.header('扫描参数')
    sideways=st.slider('前期横盘天数',8,35,15)
    band=st.slider('横盘最大振幅 %',5,30,16)/100
    quiet=st.slider('横盘均量 / 前20日均量上限',0.3,1.5,0.85,0.05)
    multiple=st.slider('首日放量倍数',1.5,6.0,3.0,0.25)
    body=st.slider('次日阳线实体至少 %',1,12,4)/100
    day2v=st.slider('次日成交量 / 首日最低比',0.5,1.5,1.0,0.05)
    day3v=st.slider('第三日成交量 / 次日最高比',0.3,1.0,0.7,0.05)
tolerance = st.slider(

    '第三日最低价跌破MA25容忍 %',

    min_value=0.0,

    max_value=5.0,

    value=1.5,

    step=0.5

) / 100
    workers=st.slider('并发请求数（过高易限流）',1,8,3)
    limit=st.number_input('测试扫描股票数（0=全部）',min_value=0,max_value=6000,value=100,step=100)
    st.caption('首次建议先扫描100只测试数据接口；正式扫描设置为0。')

args=SimpleNamespace(sideways=sideways,band=band,quiet_ratio=quiet,volume_multiple=multiple,day2_body=body,day2_volume=day2v,day3_volume=day3v,ma_tolerance=tolerance)
if 'results' not in st.session_state: st.session_state.results=pd.DataFrame()
if 'errors' not in st.session_state: st.session_state.errors=[]
if st.button('▶ 开始收盘扫描',type='primary',use_container_width=True):
    try:
        pool=universe()
        if limit: pool=pool.head(limit)
        st.info(f'开始检查 {len(pool)} 只股票；全市场扫描可能需要数分钟至更久，取决于行情接口速度和限流情况。')
        bar=st.progress(0); status=st.empty(); found=[]; errors=[]
        def run(row):
            try:
                d=hist(row.代码)
                return evaluate(d,row.代码,row.名称,args),None
            except Exception as e:
                return None,f'{row.代码}: {str(e)[:120]}'
        rows=list(pool.itertuples(index=False))
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures=[ex.submit(run,r) for r in rows]
            for i,f in enumerate(as_completed(futures),1):
                hit,err=f.result()
                if hit: found.append(hit)
                if err: errors.append(err)
                bar.progress(i/len(rows));status.caption(f'已扫描 {i}/{len(rows)}｜命中 {len(found)}｜接口失败 {len(errors)}')
        result=pd.DataFrame(found)
        if not result.empty: result=result.sort_values(['首日放量倍数','距MA25%'],ascending=[False,True])
        st.session_state.results=result;st.session_state.errors=errors
        st.success(f'扫描结束：命中 {len(found)} 只，数据获取失败 {len(errors)} 只。')
    except Exception as e:
        st.error(f'行情接口暂不可用：{e}')

res=st.session_state.results; errs=st.session_state.errors
c1,c2,c3=st.columns(3)
c1.metric('当前候选',len(res));c2.metric('数据获取失败',len(errs));c3.metric('形态阶段','第三日收盘')
st.subheader('每日自动扫描结果')
try:
    from pathlib import Path
    saved = Path(__file__).with_name('scan_results.csv')
    if saved.exists():
        cached = pd.read_csv(saved, dtype={'代码': str})
        st.caption(f'云端定时任务最近保存的结果｜文件更新时间：{dt.datetime.fromtimestamp(saved.stat().st_mtime).strftime("%Y-%m-%d %H:%M")}（服务器时间；并非行情时间）')
        if cached.empty:
            st.info('最近一次自动扫描没有命中。')
        else:
            st.dataframe(cached, use_container_width=True, hide_index=True)
            st.download_button('下载每日结果 CSV', cached.to_csv(index=False).encode('utf-8-sig'), file_name='daily_scan.csv')
    else:
        st.caption('尚无自动扫描结果；需要部署并启用 GitHub Actions，首次运行后才会显示。')
except Exception as e:
    st.warning(f'读取自动扫描结果失败：{e}')

st.subheader('候选股票')
if res.empty:
    st.info('暂无结果。点击左侧设置参数后开始扫描。严格形态条件可能导致零命中。')
else:
    st.dataframe(res,use_container_width=True,hide_index=True)
    st.download_button('⬇ 下载筛选结果 CSV',res.to_csv(index=False).encode('utf-8-sig'),file_name=f'四日形态_{dt.date.today()}.csv',mime='text/csv')
    options={f"{r['代码']}  {r['名称']}":r['代码'] for _,r in res.iterrows()}
    choice=st.selectbox('查看候选股票K线',list(options))
    try:
        d=hist(options[choice]).copy();d['日期']=pd.to_datetime(d['日期']);d=d.tail(65)
        for col in ['开盘','最高','最低','收盘','成交量']:d[col]=pd.to_numeric(d[col],errors='coerce')
        d['MA25']=d['收盘'].rolling(25).mean()
        fig=make_subplots(rows=2,cols=1,shared_xaxes=True,vertical_spacing=.04,row_heights=[.73,.27])
        fig.add_trace(go.Candlestick(x=d['日期'],open=d['开盘'],high=d['最高'],low=d['最低'],close=d['收盘'],name='日K',increasing_line_color='#ef5b69',decreasing_line_color='#24ba92'),row=1,col=1)
        fig.add_trace(go.Scatter(x=d['日期'],y=d['MA25'],name='MA25',line=dict(color='#f3b95f',width=2)),row=1,col=1)
        fig.add_trace(go.Bar(x=d['日期'],y=d['成交量'],name='成交量',marker_color=['#ef5b69' if c>=o else '#24ba92' for c,o in zip(d['收盘'],d['开盘'])]),row=2,col=1)
        fig.update_layout(height=630,template='plotly_dark',paper_bgcolor='#0b1220',plot_bgcolor='#101c2d',xaxis_rangeslider_visible=False,margin=dict(l=10,r=10,t=30,b=10))
        st.plotly_chart(fig,use_container_width=True)
    except Exception as e:st.warning(f'图表数据暂不可用：{e}')
if errs:
    with st.expander('查看数据接口失败明细'):
        st.text('\n'.join(errs[:100]))
st.divider()
st.markdown('**第四日确认说明**：本页扫描的是第三日收盘后的候选。第四日必须在真实开盘后获取开盘价，并与当时可计算的25日均线比较；本工具不将第三日结果冒充第四日确认。')
st.caption('涨停判定采用近似涨幅阈值（主板9.5%、创业板19.5%），不适合直接用于ST、特殊交易制度及新股无涨跌幅限制阶段；请人工复核交易所涨停价、复权口径与行情异常。')
