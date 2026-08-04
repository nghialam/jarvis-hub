#!/usr/bin/env python3
import sqlite3, random
from datetime import date, timedelta

import os


DB = os.path.join(os.path.dirname(__file__), '..', 'knowledge', 'jarvis.db')


def get_conn():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def create_schema(conn):
    q = "DROP TABLE IF EXISTS alerts; "
    q += "CREATE TABLE alerts (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER DEFAULT 1, ticker TEXT CHECK(ticker IN ('a','b')), threshold FLOAT, active INTEGER DEFAULT 1); "
    q += "DROP TABLE IF EXISTS research_reports; "
    q += "CREATE TABLE research_reports (id INTEGER PRIMARY KEY AUTOINCREMENT, broker TEXT, title TEXT, market_outlook INTEGER, index_target FLOAT, key_tickers TEXT, summary TEXT, downloaded INTEGER DEFAULT 0, published_at DATE); "
    q += "DROP TABLE IF EXISTS daily_ohlcv; "
    q += "CREATE TABLE daily_ohlcv (id INTEGER PRIMARY KEY AUTOINCREMENT, ticker TEXT NOT NULL, date DATE NOT NULL, low FLOAT, high FLOAT, open FLOAT, close FLOAT, volume FLOAT, value FLOAT, UNIQUE(ticker,date)); "
    q += "DROP TABLE IF EXISTS news_articles; "
    q += "CREATE TABLE news_articles (id INTEGER PRIMARY KEY AUTOINCREMENT, headline TEXT NOT NULL, source TEXT, category TEXT, sentiment TEXT, relevance_score INTEGER, published_at DATE, lang CHAR DEFAULT 'en'); "
    q += "DROP TABLE IF EXISTS entity_mentions; "
    q += "CREATE TABLE entity_mentions (id INTEGER PRIMARY KEY AUTOINCREMENT, article_id INTEGER, ticker TEXT, company_name TEXT, mention_type TEXT); "
    q += "DROP TABLE IF EXISTS market_quotes; "
    q += "CREATE TABLE market_quotes (id INTEGER PRIMARY KEY AUTOINCREMENT, ticker TEXT UNIQUE NOT NULL, name TEXT NOT NULL, exchange CHAR DEFAULT 'HOSE', price FLOAT, pe_ratio FLOAT, pb_ratio FLOAT, mkt_cap FLOAT, sector TEXT, updated_at DATE);"
    conn.executescript(q.rstrip())
    conn.commit()


def seed_stocks(conn):
    tkr_list = [
        ("MBB","Vinhcombank","HOSE"),("ACB", "Asian Comm Bank", "HOSE"),
        ("VPB", "VN Bank Profit", "HOSE"), ("STB", "Sacombank", "HOSE"),
        ("TCM", "Techcom Sec", "HNX"), ("VHM", "Vinhomes", "HOSE"),
        ("PAC", "Paradise Corp", "HOSE"), ("GVC", "GeoVina Complex", "HNX"),
        ("VIC", "Vingroup", "HOSE"), ("MSN", "Masan Group", "HOSE"),
        ("FPT", "FPT Corp", "HOSE"), ("GVR", "Gia Van Auto", "HOSE"),
        ("HAA", "Hai Phong Auto", "HNX"), ("PVS", "Petrolimex", "HOSE"),
        ("PLX", "Viettel Petrovin", "HNX"), ("NVL", "Petec Oil", "HOSE"),
        ("PVF", "Finance Corp", "HOSE"), ("STG", "VN Seafood", "HNX"),
        ("DGC", "Duc Phu Invest", "HOSE"), ("VNM", "Vietnamese Foods", "HOSE"),
        ("PTC", "Viettel Post", "HNX"), ("FIT", "Future Tech VN", "HOSE"),
        ("GMD", "GameDev VN", "HNX"), ("RE3", "Red River Bev", "HOSE"),
        ("NWP", "Novaland", "HOSE"), ("OHC", "Oho Corp", "HOSE"),
        ("SAB", "Sabeco", "HNX"), ("VPY", "Vinhomes Prop Co.", "UPCoM"),
        ("HMX", "Hemex Pharma", "HOSE")]
    conn.execute("DELETE FROM market_quotes")
    now = date.today().isoformat()
    for tkr, nm, ex in tkr_list:
        px = round(random.randint(15000, 130000) * (1 + random.uniform(-0.04, 0.05)), -2)
        conn.execute("INSERT INTO market_quotes(ticker,"
                        "name,exchange,price,pe_ratio,pb_ratio,mkt_cap,"
                        "sector,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                        (tkr,nm,ex,px,12.5,2.3, random.randint(20,150),
                         "Banking", now))
    conn.commit()
    return len(tkr_list)


def seed_news(conn):
    news = [
        "VN-Index tang mang dau phien giao dich",
        "MBB va VPB dan hayd dong tien mua rung quy mo lon",
        "Fed giu nguyen lai suat USD tiep tuc yeu di",
        "NNVV tiep tuc noi long chin sach ho tang truong",
        "SSI Research tang target VN-Index len 1380 diem Q3/2026",
        "Gia vang the gioi lap dinh $2,900/oz",
        "GVC cong bao tai chinh Q2/2026 loi nhuan tang 15%",
        "VN-Index vut dinh lich su 1,300 diem voi khop luong ca ky",
        "SSI va HCM dong lot tang target chi so len 1,400 dim",
        "NNVV tiep tuc noi long chin sach ho tang truong kinh te"]
    conn.execute("DELETE FROM news_articles")
    cur = conn.cursor()
    for i, hl in enumerate(news):
        pub = (date.today() - timedelta(days=random.randint(1,30))).isoformat()
        sen    = random.choice(["Bullish", "Neutral"])
        rs     = random.randint(2, 5)
        cur.execute("INSERT INTO news_articles(id, headline,"
                         "source, category, sentiment, relevance_score"
                         ", published_at) VALUES(?,?,?,?,?,?,?)",
                         (i+1, hl[:200], "VNews", "VN Market", sen, rs, pub))
    conn.commit()
    return len(news)


def seed_ohlcv(conn):
    conn.execute("DELETE FROM daily_ohlcv")
    bp_map = [("MBB", 48500), ("ACB", 32100)]
    td = date.today()
    total = 0
    for tkr, bpl in bp_map:
        p = bpl
        for off in range(1, 6):
            d = td - timedelta(days=off)
            chg = random.uniform(-0.04, +0.04)
            cur_ = round(p * (1 + chg), 0)
            opn    = round(cur_ * random.uniform(0.98, 1.02))
            lwr    = round(min(opn, cur_) * 0.98)
            vol     = int(random.randint(500000, 8000000))
            conn.execute("INSERT INTO daily_ohlcv(ticker,"
                              "date,low,open,"
                              "close,volume,value) VALUES(?,?,?,?,?,?,?)",
                             (tkr,d.isoformat(),lwr,opn,cur_,vol,vol*cur_*1e-6))
            total += 1
    conn.commit()
    return total


def seed_reports(conn):
    entries = [
        ("SSI","Weekly Chart Jun 26",0,1380.0,"MBB,ACB,VHM"),
        ("HCM","Macro Economy H2/2026",1,1350.0,"VIC,MSN,GVC"),
        ("VCI", "Real E State Revival",0,None,"PAC,VHM"),
        ("TCBS","Stock Picks Q3 Tech",0,1420.0,"FPT,MSN,MBB")]
    summaries = [
        "VN-Index tiep tuc tang manh trong tuan qua.",
        "Growth remains strong but watch inflation closely.",
        "Real estate sector may face headwinds in Q3 2026.",
        "Top picks include FPT tech rebour and MSN agri stocks."]
    conn.execute("DELETE FROM research_reports")
    new_dt = date.today()
    for j, (br, tle, klt, tgt, ktkrs) in enumerate(entries):
        pub = (new_dt - timedelta(days=random.randint(1,30))).isoformat()
        s    = summaries[j]
        conn.execute("INSERT INTO research_reports(broker,title,"
                         "market_outlook,index_target,key_tickers"
                         ",summary,published_at)"
                        " VALUES(?,?,?,?,?,?,?)",
                        (br, tle[:80], klt, tgt,
                        ktkrs[:50] if ktkrs else None, s, pub))
    conn.commit()
    return conn.execute("SELECT COUNT(*) FROM research_reports").fetchone()[0]


def main():
    print("[HUB2] Starting...")
    conn = get_conn()
    create_schema(conn)
    n_s    = seed_stocks(conn);          print(f"stocks: {n_s}")
    n_n    = seed_news(conn);             print(f"news: {n_n}")
    n_o    = seed_ohlcv(conn);              print(f"ohlcv:   {n_o}")
    n_r    = seed_reports(conn);            print(f"reports:{n_r}")
    for tbl in ["entity_mentions", "alerts"]:
        cnt = conn.execute("SELECT COUNT(*) FROM " + tbl).fetchone()[0]
        print(f"   {tbl}: {cnt}")
    print("[HUB2 DONE!]")


if __name__ == "__main__":
    main()
