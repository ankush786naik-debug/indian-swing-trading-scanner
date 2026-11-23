"""Upstox Analytics API client; read-only market data endpoints."""
import gzip,json,os,time
from urllib.parse import quote
import requests
BASE="https://api.upstox.com"
MASTER="https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz"
class UpstoxAPIError(RuntimeError): pass
class UpstoxClient:
    def __init__(self):
        self.token=(os.getenv("UPSTOX_ANALYTICS_TOKEN") or os.getenv("UPSTOX_ACCESS_TOKEN") or "").strip()
        if not self.token:raise UpstoxAPIError("Set UPSTOX_ANALYTICS_TOKEN in repository Actions secrets (Upstox Analytics Token).")
        self.session=requests.Session()
        self.session.headers.update({"Accept":"application/json","Authorization":f"Bearer {self.token}","User-Agent":"NSE-Swing-Research/2.0"})
        self.last=0.0
    def get(self,path,params=None,retries=4):
        for attempt in range(retries):
            wait=max(.13-(time.monotonic()-self.last),0)
            if wait:time.sleep(wait)
            try:
                response=self.session.get(BASE+path,params=params,timeout=30);self.last=time.monotonic()
                if response.status_code==429 or response.status_code>=500:
                    if attempt+1<retries:time.sleep(min(2**attempt,12));continue
                response.raise_for_status();payload=response.json()
                if payload.get("status")=="error":raise UpstoxAPIError(str(payload))
                return payload.get("data",payload)
            except requests.RequestException as exc:
                if attempt+1>=retries:raise UpstoxAPIError(f"Upstox request error: {exc}") from exc
                time.sleep(min(2**attempt,12))
        raise UpstoxAPIError(f"Failed after retries: {path}")
    @staticmethod
    def load_nse_equities():
        r=requests.get(MASTER,timeout=45);r.raise_for_status()
        items=json.loads(gzip.decompress(r.content).decode("utf-8"));result=[];seen=set()
        for x in items:
            if x.get("segment")!="NSE_EQ" or x.get("instrument_type")!="EQ":continue
            key=x.get("instrument_key");symbol=x.get("trading_symbol")
            if not key or not symbol or key in seen:continue
            seen.add(key);result.append({"instrument_key":key,"symbol":symbol,"name":x.get("name") or x.get("short_name") or symbol,"isin":x.get("isin") or ""})
        if not result:raise UpstoxAPIError("NSE BOD master contained no NSE_EQ equities.")
        return sorted(result,key=lambda x:x["symbol"])
    def quotes(self,keys):
        result={}
        for i in range(0,len(keys),500):
            data=self.get("/v2/market-quote/quotes",{"instrument_key":",".join(keys[i:i+500])})
            if isinstance(data,dict):result.update(data)
        return result
    def daily_candles(self,key,start,end):
        encoded=quote(key,safe="")
        data=self.get(f"/v3/historical-candle/{encoded}/days/1/{end}/{start}")
        candles=data.get("candles",[]) if isinstance(data,dict) else []
        return [{"date":x[0],"open":x[1],"high":x[2],"low":x[3],"close":x[4],"volume":x[5]} for x in candles if isinstance(x,(list,tuple)) and len(x)>=6]
    def fundamentals(self,isin):
        if not isin:return {}
        data={}
        for key,endpoint in {"ratios":"key-ratios","income":"income-statement","cash_flow":"cash-flow","balance":"balance-sheet"}.items():
            try:data[key]=self.get(f"/v2/fundamentals/{isin}/{endpoint}")
            except UpstoxAPIError as exc:data[key]={"_error":str(exc)}
        return data
    def news(self,keys):
        result={}
        for i in range(0,len(keys),30):
            data=self.get("/v2/news",{"category":"instrument_keys","instrument_keys":",".join(keys[i:i+30]),"page_number":1,"page_size":100})
            if isinstance(data,dict):result.update(data)
        return result
    def close(self):self.session.close()
