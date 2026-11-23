"""Daily all-NSE-equity swing scanner: Upstox prices, fundamentals and news."""
import logging, math, os, re
from datetime import date, timedelta
import numpy as np
import pandas as pd
from exporters import export_json
from telegram_alerts import send_telegram_document, send_telegram_message
from upstox_client import UpstoxClient

OUT="data"
CANDLE_LIMIT=int(os.getenv("MAX_CANDLE_CANDIDATES","350"))
RESEARCH_LIMIT=int(os.getenv("MAX_FUNDAMENTAL_CANDIDATES","25"))
TURNOVER_MIN=float(os.getenv("MIN_DAILY_TURNOVER_CRORE","3"))
MIN_SCORE=float(os.getenv("MIN_FINAL_SCORE","62"))
os.makedirs(OUT,exist_ok=True)
logging.basicConfig(level=logging.INFO,format="%(asctime)s | %(levelname)s | %(message)s")

def num(x):
    if isinstance(x,(int,float)) and not isinstance(x,bool):
        return float(x) if math.isfinite(float(x)) else None
    if isinstance(x,str):
        try: return float(x.replace(",","").replace("%","").strip())
        except ValueError: return None
    return None

def norm(x): return re.sub(r"[^a-z0-9]+","_",str(x).lower()).strip("_")

def metric(obj,labels):
    labels=[norm(x) for x in labels]; found=[]
    def walk(x):
        if isinstance(x,dict):
            for k,v in x.items():
                nk=norm(k)
                if any(a in nk for a in labels):
                    if isinstance(v,dict):
                        for vk in ("value","current","ratio","amount","latest","percentage","percent"):
                            z=num(v.get(vk))
                            if z is not None: found.append(z)
                    else:
                        z=num(v)
                        if z is not None: found.append(z)
                walk(v)
        elif isinstance(x,list):
            for row in x:
                if isinstance(row,dict):
                    label=norm(row.get("name") or row.get("ratio_name") or row.get("metric") or row.get("key") or "")
                    if any(a in label for a in labels):
                        for vk in ("value","current","ratio","amount","latest","percentage","percent"):
                            z=num(row.get(vk))
                            if z is not None: found.append(z)
                walk(row)
    walk(obj)
    return found[0] if found else None

def growth(obj,terms):
    terms=[norm(x) for x in terms]; found=[]
    def walk(x,ctx=""):
        if isinstance(x,dict):
            for k,v in x.items():
                nk=norm(k); full=ctx+"_"+nk
                if any(t in full for t in terms) and any(t in nk for t in ("growth","change","yoy","percentage","percent")):
                    if isinstance(v,dict):
                        for vk in ("value","percentage","percent","growth","change"):
                            z=num(v.get(vk))
                            if z is not None: found.append(z)
                    else:
                        z=num(v)
                        if z is not None: found.append(z)
                walk(v,full)
        elif isinstance(x,list):
            for v in x: walk(v,ctx)
    walk(obj)
    return found[0] if found else None

def fundamentals_score(d):
    r,i,c,b=(d.get("ratios",{}),d.get("income",{}),d.get("cash_flow",{}),d.get("balance",{}))
    roce=metric(r,["roce","return_on_capital_employed"])
    roe=metric(r,["roe","return_on_equity"])
    rev=growth(i,["revenue","sales","total_income"])
    profit=growth(i,["net_profit","profit_after_tax","pat"])
    pe=metric(r,["pe_ratio","price_earnings","p_e"])
    sector_pe=metric(r,["sector_pe","sector_price_earnings","benchmark_pe"])
    ocf=metric(c,["operating_cash_flow","cash_from_operating_activities","net_cash_operating"])
    assets=metric(b,["total_assets"]); liabilities=metric(b,["total_liabilities"])
    weighted=total=0.0
    def add(value,weight,good,bad):
        nonlocal weighted,total
        if value is None:return
        total+=weight
        weighted+=weight*(1 if value>=good else max(0,(value-bad)/(good-bad)) if value>bad else 0)
    add(roce,20,18,5); add(roe,12,15,5); add(rev,14,12,-5); add(profit,14,15,-5)
    if ocf is not None: total+=15; weighted+=15 if ocf>0 else 0
    if pe and sector_pe and pe>0 and sector_pe>0:
        ratio=pe/sector_pe; total+=10
        weighted+=10*(1 if ratio<=.85 else .75 if ratio<=1.1 else .4 if ratio<=1.35 else 0)
    debt_ratio=None
    if assets and assets>0 and liabilities is not None:
        debt_ratio=liabilities/assets; total+=15
        weighted+=15*(1 if debt_ratio<=.45 else .7 if debt_ratio<=.65 else .35 if debt_ratio<=.8 else 0)
    return {"fundamental_score":round(weighted/total*100,1) if total else None,
            "fundamental_coverage":round(total/100,2),"ROCE_pct":roce,"ROE_pct":roe,
            "Revenue_growth_pct":rev,"Net_profit_growth_pct":profit,"PE":pe,"Sector_PE":sector_pe,
            "Operating_cash_flow_crore":ocf,"Liabilities_to_assets":round(debt_ratio,3) if debt_ratio is not None else None}

POS=("order win","wins order","contract","profit rises","profit growth","revenue growth","results beat","strong results","capacity expansion","approval","clearance","upgrade","buyback","dividend","debt reduced","stake sale","acquisition","expansion","record order","promoter buying")
NEG=("fraud","investigation","default","downgrade","pledge","pledged","loss widens","profit falls","revenue falls","sebi action","ban","penalty","regulatory action","insolvency","debt stress","resignation","auditor resign","plant shutdown","litigation","accounting issue")

def news_score(articles):
    heads=[]; links=[]; pos=neg=0
    for a in articles or []:
        h=str(a.get("heading") or a.get("title") or ""); s=str(a.get("summary") or "")
        text=(h+" "+s).lower()
        if not text.strip(): continue
        heads.append(h[:240]); links.append(str(a.get("article_link") or ""))
        pos+=sum(w in text for w in POS); neg+=sum(w in text for w in NEG)
    sentiment=0 if pos==neg==0 else (pos-neg)/max(pos+neg,1)
    score=max(0,min(100,50+25*sentiment+min(15,len(heads)*3)))
    return {"news_score":round(score,1),"news_sentiment":round(sentiment,2),
            "news_count_7d":len(heads),"news_headlines":" | ".join(heads[:3]),
            "news_links":" | ".join(x for x in links[:3] if x)}

def analyze(symbol,candles):
    d=pd.DataFrame(candles)
    if d.empty:return None
    d["date"]=pd.to_datetime(d.date,errors="coerce",utc=True).dt.tz_convert(None)
    for k in ("open","high","low","close","volume"): d[k]=pd.to_numeric(d[k],errors="coerce")
    d=d.dropna(subset=["date","open","high","low","close","volume"]).sort_values("date").drop_duplicates("date").reset_index(drop=True)
    if len(d)<205:return None
    c,h,l,v=d.close,d.high,d.low,d.volume
    for n in (20,50,200): d[f"ema{n}"]=c.ewm(span=n,adjust=False).mean()
    delta=c.diff(); gain=delta.clip(lower=0).ewm(alpha=1/14,min_periods=14,adjust=False).mean()
    loss=-delta.clip(upper=0).ewm(alpha=1/14,min_periods=14,adjust=False).mean()
    d["rsi"]=100-100/(1+gain/loss.replace(0,np.nan))
    d.loc[(loss==0)&(gain>0),"rsi"]=100
    d["macd"]=c.ewm(span=12,adjust=False).mean()-c.ewm(span=26,adjust=False).mean()
    d["macd_signal"]=d.macd.ewm(span=9,adjust=False).mean()
    tr=pd.concat([h-l,(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1)
    d["atr"]=tr.ewm(alpha=1/14,min_periods=14,adjust=False).mean()
    d["volratio"]=v/v.rolling(20).mean().replace(0,np.nan)
    d["support"]=l.shift(1).rolling(20).min(); d["resistance"]=h.shift(1).rolling(20).max()
    weekly=d.set_index("date").resample("W-FRI").close.last().dropna()
    weekly20=weekly.ewm(span=20,adjust=False).mean(); weekly40=weekly.ewm(span=40,adjust=False).mean()
    if d.date.max().weekday()!=4 and len(weekly)>1: weekly,weekly20,weekly40=weekly.iloc[:-1],weekly20.iloc[:-1],weekly40.iloc[:-1]
    x=d.iloc[-1]
    if len(weekly)<40 or pd.isna(x.atr) or x.atr<=0:return None
    wt="BULLISH" if weekly.iloc[-1]>weekly20.iloc[-1]>weekly40.iloc[-1] else "BEARISH" if weekly.iloc[-1]<weekly20.iloc[-1]<weekly40.iloc[-1] else "SIDEWAYS"
    p=float(x.close); atr=float(x.atr); sup=float(x.support) if pd.notna(x.support) else p-2*atr
    rsi=float(x.rsi) if pd.notna(x.rsi) else 50; vr=float(x.volratio) if pd.notna(x.volratio) else 0
    score=0; why=[]
    def award(condition,points,label):
        nonlocal score
        if condition: score+=points; why.append(label)
    award(p>x.ema200,15,"above EMA200"); award(x.ema20>x.ema50,10,"EMA20 > EMA50")
    award(x.ema50>x.ema200,10,"EMA50 > EMA200"); award(wt=="BULLISH",10,"weekly bullish")
    award(45<=rsi<=65,10,"RSI swing zone"); award(x.macd>x.macd_signal,10,"MACD bullish")
    award(abs(p-x.ema20)/p<=.025,10,"near EMA20 pullback")
    award(sup>0 and (p-sup)/p<=.04,10,"near 20-day support")
    award(vr>=1.2,10,"volume confirmation"); award((p-x.ema20)/p<=.06,5,"not extended")
    entry_low=min(p,max(sup+.25*atr,p-.5*atr)); stop=min(sup-.25*atr,p-1.4*atr)
    if stop<=0 or stop>=entry_low:stop=p-1.5*atr
    risk=p-stop; t1=p+2*risk; t2=p+3*risk
    return {"symbol":symbol,"date":str(x.date.date()),"close":round(p,2),"technical_score":min(score,100),
            "weekly_trend":wt,"rsi":round(rsi,1),"volume_ratio":round(vr,2),"support20":round(sup,2),
            "entry_low":round(entry_low,2),"entry_high":round(p,2),"stop_loss":round(stop,2),
            "target_1":round(t1,2),"target_2":round(t2,2),"target_1_return_pct":round((t1/p-1)*100,2),
            "target_2_return_pct":round((t2/p-1)*100,2),"risk_pct":round((p-stop)/p*100,2),
            "technical_reasons":"; ".join(why)}

def main():
    client=UpstoxClient(); failures=[]
    try:
        universe=client.load_nse_equities()
        logging.info("ALL NSE_EQ instruments loaded: %d",len(universe))
        quote_data=client.quotes([x["instrument_key"] for x in universe])
        lookup={x["instrument_key"]:x for x in universe}
        by_symbol={x["symbol"]:x for x in universe}
        liquid=[]
        for key,q in quote_data.items():
            stock=lookup.get(key)
            # Upstox quote response keys are NSE_EQ:SYMBOL, not instrument_key.
            if stock is None:
                quote_symbol=(q.get("symbol") if isinstance(q,dict) else None) or str(key).split(":")[-1]
                stock=by_symbol.get(quote_symbol)
            if not stock or not isinstance(q,dict):continue
            ltp=num(q.get("last_price")); volume=num(q.get("volume"))
            if not ltp or not volume or ltp<=0 or volume<=0:continue
            turnover=ltp*volume/1e7
            if turnover>=TURNOVER_MIN: liquid.append({**stock,"turnover":turnover})
        liquid.sort(key=lambda x:x["turnover"],reverse=True)
        candle_stocks=liquid[:CANDLE_LIMIT]
        logging.info("Quote screen %d stocks; fetching daily candles for dynamic top-liquidity %d",len(liquid),len(candle_stocks))
        end=date.today(); start=end-timedelta(days=420); tech=[]
        for idx,s in enumerate(candle_stocks,1):
            try:
                candles=client.daily_candles(s["instrument_key"],start.isoformat(),end.isoformat())
                row=analyze(s["symbol"],candles)
                if row:row.update({"instrument_key":s["instrument_key"],"isin":s["isin"],"name":s["name"],"turnover_crore":round(s["turnover"],2)});tech.append(row)
            except Exception as e:
                failures.append({"symbol":s["symbol"],"stage":"candles","error":str(e)[:300]})
                logging.warning("Candle failure %s: %s",s["symbol"],str(e)[:180])
            if idx%50==0:logging.info("Candle progress %d/%d; valid=%d",idx,len(candle_stocks),len(tech))
        tech.sort(key=lambda x:(x["technical_score"],x["turnover_crore"]),reverse=True)
        pool=tech[:RESEARCH_LIMIT]; news=client.news([x["instrument_key"] for x in pool]) if pool else {}
        researched=[]
        for s in pool:
            try:
                fscore=fundamentals_score(client.fundamentals(s["isin"]))
                nscore=news_score(news.get(s["instrument_key"],[]) if isinstance(news,dict) else [])
                if fscore["fundamental_score"] is None or fscore["fundamental_coverage"]<.45:continue
                if nscore["news_count_7d"]==0 or nscore["news_sentiment"]<-.25:continue
                combined=.45*s["technical_score"]+.40*fscore["fundamental_score"]+.15*nscore["news_score"]
                researched.append({**s,**fscore,**nscore,"combined_score":round(combined,1)})
            except Exception as e:
                failures.append({"symbol":s["symbol"],"stage":"research","error":str(e)[:300]})
                logging.warning("Research error %s: %s",s["symbol"],str(e)[:180])
        researched.sort(key=lambda x:x["combined_score"],reverse=True)
        top=[x for x in researched if x["combined_score"]>=MIN_SCORE][:5]
        columns=["rank","symbol","name","date","close","entry_low","entry_high","stop_loss","target_1","target_2",
                 "target_1_return_pct","target_2_return_pct","risk_pct","combined_score","technical_score","fundamental_score",
                 "fundamental_coverage","news_score","news_sentiment","news_count_7d","news_headlines","news_links","ROCE_pct",
                 "ROE_pct","Revenue_growth_pct","Net_profit_growth_pct","PE","Sector_PE","Operating_cash_flow_crore",
                 "Liabilities_to_assets","weekly_trend","rsi","volume_ratio","support20","turnover_crore","technical_reasons"]
        rows=[{"rank":i,**{k:s.get(k) for k in columns if k!="rank"}} for i,s in enumerate(top,1)]
        today=date.today().isoformat()
        path=os.path.join(OUT,"top5_swing_stocks.csv")
        pd.DataFrame(rows,columns=columns).to_csv(path,index=False,encoding="utf-8-sig")
        pd.DataFrame(rows,columns=columns).to_csv(os.path.join(OUT,f"top5_swing_stocks_{today}.csv"),index=False,encoding="utf-8-sig")
        export_json({"date":today,"nse_eq_universe":len(universe),"quote_screened":len(liquid),"deep_candle_candidates":len(candle_stocks),
                     "technical_valid":len(tech),"news_fundamental_research":len(pool),"qualified_top5":len(top),"failures":failures},"scan_diagnostics.json")
        caption=(f"📊 NSE TOP-5 SWING RESEARCH | {today}\nNSE EQ universe: {len(universe)} | quote-screened: {len(liquid)}\n"
                 f"Daily candles: {len(candle_stocks)} dynamically selected liquid stocks\nFundamentals + 7-day news: {len(pool)} | Qualified picks: {len(top)}\nNo forced picks. Research only; no orders placed.")
        logging.info(caption);send_telegram_message(caption);send_telegram_document(path,caption)
    finally:client.close()

if __name__=="__main__":main()
