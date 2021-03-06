# OURO-LIB:  Common functions used across the Ouro project
# Written by Dave Andrus on May 2, 2020
# Copyright 2020 Agile Data Guru
# https://github.com/AgileDataGuru/Ouro

# Required modules
import os                               # for operating system specific functions
import logging                          # for application logging
import json                             # for manipulating array data
import pandas as pd                     # in-memory database capabilities
import talib as ta                      # lib to calcualted technical indicators
from azure.cosmos import exceptions, CosmosClient, PartitionKey
import alpaca_trade_api as tradeapi     # required for interaction with Alpaca
from datetime import datetime
from datetime import timedelta
import time
from dateutil.parser import parse
import pyodbc

def sqldbconn (dsn='ouro_dsn', usr='unknown', pwd='unknown'):
    # connect to a SQL server DSN
    sqluser = sqlpwd=os.environ.get("OURO_SQL_USER", usr)
    sqlpwd=os.environ.get("OURO_SQL_PWD", pwd)
    pyodbc.autocommit = True
    try:
        sqlsvr = pyodbc.connect('DSN=Ouro;UID=' + sqluser + ';PWD=' + sqlpwd, autocommit=True)
        return sqlsvr
    except:
        return None

def sqldbcursor (dsn='ouro_dsn', usr='unknown', pwd='unknown'):
    # connect to a SQL server DSN
    sqluser = sqlpwd=os.environ.get("OURO_SQL_USER", usr)
    sqlpwd=os.environ.get("OURO_SQL_PWD", pwd)
    pyodbc.autocommit = True
    try:
        sqlsvr = pyodbc.connect('DSN=Ouro;UID=' + sqluser + ';PWD=' + sqlpwd, autocommit=True)
        return sqlsvr.cursor()
    except:
        return None

def qrysqldb(csr, query):
    # Execute a query against a connection to a SQL database
    try:
        ds = csr.execute(query)
        return ds
    except Exception as ex:
        print(query)
        print(ex)
        return None

def cosdb (db, ctr, prtn):
    # Connect to a CosmosDB database and container

    # Setup Logging
    logging.basicConfig(level=os.environ.get("LOGLEVEL", "INFO"))

    # Initialize the Cosmos client
    endpoint = os.environ.get("OURO_DOCUMENTS_ENDPOINT", "SET OURO_DOCUMENTS_ENDPOINT IN ENVIRONMENT")
    key = os.environ.get("OURO_DOCUMENTS_KEY", "SET OURO_DOCUMENTS_KEY IN ENVIRONMENT")
    client = CosmosClient(endpoint, key)
    database = client.create_database_if_not_exists(id=db)

    # Connect to the daily_indicators container
    try:
        container = database.create_container_if_not_exists(
            id=ctr,
            partition_key=PartitionKey(path=prtn),
            offer_throughput=400
        )
        logging.info('Azure-Cosmos client initialized; connected to ' + db + '.' + ctr + ' at ' + endpoint)
        return container
    except Exception as ex:
        logging.critical('Unable to create connection to ' + db + '.' + ctr + ' at ' + endpoint)
        logging.critical(ex)
        quit(-1)

def qrycosdb(ctr, query):
    # Execute a query against a connection to a CosmosDB container
    try:
        ds = list(ctr.query_items(
            query=query,
            enable_cross_partition_query=True
        ))
        logging.debug('Running query:  ' + query)
        return ds
    except Exception as ex:
        logging.debug('Query did not return results:  ' + query)
        logging.debug(ex)
        return None

def calcind(df):
    # Calculate indicators and interpret them into buy or sell signals
    # Note 1:  If the dataframe is not sorted in timeframe order, the results will be worthless
    # Note 2:  The dataframe must have the following OHLCV attributes at a minimum:
    #   {
    #       "o": 100            <-- open value
    #       "h": 150            <-- high value
    #       "l": 90             <-- low value
    #       "c": 110            <-- close value
    #       "v": 3000           <-- volume value
    #   }

    if not df.empty:
        # calculate the technical indicators if there is data to do so
        # Ref:  https://mrjbq7.github.io/ta-lib/func_groups/momentum_indicators.html

        # Momentum indicators
        df['ADX14'] = ta.ADX(df['h'], df['l'], df['c'])
        df['ADXR14'] = ta.ADXR(df['h'], df['l'], df['c'])
        df['APO12'] = ta.APO(df['c'], fastperiod=12, slowperiod=26, matype=0)
        df['AROONUP'], df['AROONDN'] = ta.AROON(df['h'], df['l'], timeperiod=14)
        df['BOP'] = ta.BOP(df['o'], df['h'], df['l'], df['c'])
        df['CCI14'] = ta.CCI(df['h'], df['l'], df['c'], timeperiod=14)
        df['CMO14'] = ta.CMO(df['c'], timeperiod=14)
        df['DX14'] = ta.DX(df['h'], df['l'], df['c'], timeperiod=14)
        df['MACD'], df['MACDSIG'], df['MACDHIST'] = ta.MACD(df['c'], fastperiod=12, slowperiod=26, signalperiod=9)
        df['MFI4'] = ta.MFI(df['h'], df['l'], df['c'], df['v'], timeperiod=14)
        df['MOM10'] = ta.MOM(df['c'], timeperiod=10)
        df['PPO12'] = ta.PPO(df['c'], fastperiod=12, slowperiod=26, matype=0)
        df['ROC10'] = ta.MOM(df['c'], timeperiod=10)
        df['RSI14'] = ta.RSI(df['c'], timeperiod=14)
        df['STOCHK'], df['STOCHD'] = ta.STOCH(df['h'], df['l'], df['c'], fastk_period=5, slowk_period=3, slowk_matype=0, slowd_period=3, slowd_matype=0)
        df['STOCHRSIK'], df['STOCHRSID'] = ta.STOCHRSI(df['c'], timeperiod=14, fastk_period=5, fastd_period=3, fastd_matype=0)
        df['TRIX30'] = ta.TRIX(df['c'], timeperiod=30)
        df['ULTOSC'] = ta.ULTOSC(df['h'], df['l'], df['c'], timeperiod1=7, timeperiod2=14, timeperiod3=28)

        # Moving Average or Overlap functions
        df['BBUPPER'], df['BBMID'], df['BBLOWER'] = ta.BBANDS(df['c'], timeperiod=5, nbdevup=2, nbdevdn=2, matype=0)
        df['EMA14'] = ta.EMA(df['c'], timeperiod=14)
        df['SMA14'] = ta.SMA(df['c'], timeperiod=14)

        # Volume Indicators
        df['AD'] = ta.AD(df['h'], df['l'], df['c'], df['v'])
        df['ADOSC'] = ta.ADOSC(df['h'], df['l'], df['c'], df['v'], fastperiod=3, slowperiod=10)
        df['OBV'] = ta.OBV(df['c'], df['v'])

        # Candlestick Patterns
        df['DJI'] = ta.CDLDOJI (df['o'], df['h'], df['l'], df['c'])
        df['ENG'] = ta.CDLENGULFING (df['o'], df['h'], df['l'], df['c'])
        df['HMR'] = ta.CDLHAMMER (df['o'], df['h'], df['l'], df['c'])
        df['HGM'] = ta.CDLHANGINGMAN (df['o'], df['h'], df['l'], df['c'])
        df['PRC'] = ta.CDLPIERCING (df['o'], df['h'], df['l'], df['c'])
        df['DCC'] = ta.CDLDARKCLOUDCOVER (df['o'], df['h'], df['l'], df['c'], penetration=0)
        df['MSR'] = ta.CDLMORNINGSTAR (df['o'], df['h'], df['l'], df['c'], penetration=0)
        df['ESR'] = ta.CDLEVENINGSTAR (df['o'], df['h'], df['l'], df['c'], penetration=0)
        df['KKR'] = ta.CDLKICKING (df['o'], df['h'], df['l'], df['c'])
        df['SSR'] = ta.CDLSHOOTINGSTAR (df['o'], df['h'], df['l'], df['c'])
        df['IHM'] = ta.CDLINVERTEDHAMMER (df['o'], df['h'], df['l'], df['c'])
        df['TWS'] = ta.CDL3WHITESOLDIERS (df['o'], df['h'], df['l'], df['c'])
        df['TBC'] = ta.CDL3BLACKCROWS (df['o'], df['h'], df['l'], df['c'])
        df['STP'] = ta.CDLSPINNINGTOP (df['o'], df['h'], df['l'], df['c'])

        # ADX Trend Strength
        df['ADXTREND'] = 'Weak'
        df.loc[df['ADX14'] >= 25, 'ADXTREND'] = 'Changing'
        df.loc[df['ADX14'] >= 50, 'ADXTREND'] = 'Strong'
        df.loc[df['ADX14'] >= 75, 'ADXTREND'] = 'Very Strong'

        # ADXR Trend Strength
        df['ADXRTREND'] = 'Weak'
        df.loc[df['ADXR14'] >= 25, 'ADXRTREND'] = 'Changing'
        df.loc[df['ADXR14'] >= 50, 'ADXRTREND'] = 'Strong'
        df.loc[df['ADXR14'] >= 75, 'ADXRTREND'] = 'Very Strong'

        # AROON Oscillator
        df['AROONOSC'] = df['AROONDN'] - df['AROONUP']
        df['AROONVOTE'] = 0
        df.loc[df['AROONOSC'] >= 25, 'AROONVOTE'] = 1    # This threshold is a guess
        df.loc[df['AROONOSC'] <= -25, 'AROONVOTE'] = -1  # This threshold is a guess



        # BOP Signal
        df['BOPVOTE'] = 0
        df.loc[(df['BOP'] >0), 'BOPVOTE'] = 1
        df.loc[(df['BOP'] <0), 'BOPVOTE'] = -1

        # CCI Vote
        df['CCIVOTE'] = 0
        df.loc[df['CCI14'] >= 100, 'CCIVOTE'] = 1
        df.loc[df['CCI14'] <= -100, 'CCIVOTE'] = -1

        # CMO Votes
        df['CMOVOTE'] = 0
        df.loc[df['CMO14'] < -50, 'CMOVOTE'] = 1
        df.loc[df['CMO14'] > 50, 'CMOVOTE'] = -1

        # MACD Vote; based on when the histogram crosses the zero line
        df['MACDVOTE'] = 0
        df.loc[(df['MACDHIST'] > 0) & (df['MACDHIST'].shift(periods=-1) < df['MACDHIST']), 'MACDVOTE'] = 1
        df.loc[(df['MACDHIST'] < 0) & (df['MACDHIST'].shift(periods=-1) > df['MACDHIST']), 'MACDVOTE'] = -1
        df.loc[df['MACDHIST'] == 0, 'MACDVOTE'] = 0

        # MFI Votes
        # Skipping interpretting MFI because it correlates to the direction of price

        # MOM Votes
        # Skipping basic momentum because it's not a good signal for buy or sell

        # PPO Votes; cousin of MACD
        df['PPOVOTE'] = 0
        #df.loc[df['PPO12'] >= 0, 'RSIVOTE'] = 1
        #df.loc[df['PPO12'] <= 0, 'RSIVOTE'] = -1

        # ROC Votes
        # Not using ROC because it's prone to whipsaws near the 0 line; and, this isn't used to trade

        # RSI Votes
        df['RSIVOTE'] = 0
        df.loc[df['RSI14'] >= 70, 'RSIVOTE'] = -1
        df.loc[df['RSI14'] <= 30, 'RSIVOTE'] = 1

        # STOCH Votes
        df['STOCHVOTE'] = 0
        df.loc[(df['STOCHK'] >= 80) & (df['STOCHD'] >= 80), 'STOCHVOTE'] = -1
        df.loc[(df['STOCHK'] <= 20) & (df['STOCHD'] <= 20), 'STOCHVOTE'] = 1

        # STOCHRSI Votes
        df['STOCHRSIVOTE'] = 0
        df.loc[(df['STOCHRSIK'] >= 80) & (df['STOCHRSID'] >= 80), 'STOCHRSIVOTE'] = -1
        df.loc[(df['STOCHRSIK'] <= 20) & (df['STOCHRSID'] <= 20), 'STOCHRSIVOTE'] = 1

        # TRIX Votes
        df['TRIXVOTE'] = 0
        df.loc[df['TRIX30'] > 0, 'TRIXVOTE'] = 1
        df.loc[df['TRIX30'] < 0, 'TRIXVOTE'] = -1

        # ULTOSC Votes
        # I'm skipping this oscillator because the buy/sell conditions are three-pronged and not clear

        # ADOSC Votes
        df['ADOSCVOTE'] = 0
        df.loc[df['ADOSC'] > 0, 'ADOSCVOTE'] = 1
        df.loc[df['ADOSC'] < 0, 'ADOSCVOTE'] = -1

        # Drop rows where there isn't enough information to vote
        # Note 1:  TRIX30 should be cleaned up, but the period is too long and it removes too much data.
        # Note 2:  MACD has a long period as well and will essentially eliminate trading before 10:00 AM
        df.dropna(subset=['AROONUP', 'AROONDN', 'BOP', 'CCI14', 'CMO14', 'MACDHIST', 'PPO12', 'RSI14', 'STOCHK', 'STOCHD', 'STOCHRSIK', 'STOCHRSID', 'ADOSC'], inplace=True)

        for x in df.index:
            #print (df.loc[x, 'STRATEGY_ID'][0])
            a = chr(66 + df.loc[x, 'AROONVOTE'])
            b = chr(66 + df.loc[x, 'BOPVOTE'])
            c = chr(66 + df.loc[x, 'CCIVOTE'])
            d = chr(66 + df.loc[x, 'CMOVOTE'])
            e = chr(66 + df.loc[x, 'MACDVOTE'])
            f = chr(66 + df.loc[x, 'PPOVOTE'])
            g = chr(66 + df.loc[x, 'RSIVOTE'])
            h = chr(66 + df.loc[x, 'STOCHVOTE'])
            i = chr(66 + df.loc[x, 'STOCHRSIVOTE'])
            j = chr(66 + df.loc[x, 'TRIXVOTE'])
            k = chr(66 + df.loc[x, 'ADOSCVOTE'])
            df.loc[x, 'STRATEGY_ID'] = a + b + c + d + e + f + g + h +i + j + k

        return df

def InitSignal(tickers, families):
    # initialize a matrix of tickers x signal families
    sigarray = {}
    for t in tickers:
        sigarray[t] = {f:0 for f in families}
    return sigarray

def IsOpen():
    # check if the market is open
    alpaca = tradeapi.REST()
    clock = alpaca.get_clock()
    return clock.is_open

def IsEOD(minutes=75):
    # check if we're at the end of the day
    alpaca = tradeapi.REST()
    clock = alpaca.get_clock()
    delta = clock.next_close - clock.timestamp
    if int(delta.total_seconds()/60) <= minutes:
        return True
    else:
        return False

def roundTime(dt=None):
    # round the seconds off the time so we can time things to the beginning of the minute
    if dt == None : dt = datetime.now()
    format_str = '%Y-%m-%d %H:%M'
    return datetime.strptime(datetime.strftime(dt, format_str), format_str)

def WaitForMinute():
    # Wait until the beginning of the next minute.
    waituntil = roundTime() + timedelta(minutes=1)
    waittime = waituntil - datetime.now()
    logging.debug ('Waiting for ' + str(waittime.seconds) + ' seconds for before checking the next trade.')
    time.sleep(waittime.seconds + 1) # Adding one second to eliminate ms variances

def GetAccount():
    # Get Alpaca account details
    # Note:  'buying_power' loans / credit are against the trading plan; only use cash
    data = {}
    alpaca = tradeapi.REST()
    account = alpaca.get_account()
    return account

def GetOrders(status='open', startdate=None):
    # get orders of the defined type
    alpaca = tradeapi.REST()
    if startdate != None:
        today_str = startdate
    else:
        today_str = datetime.utcnow().strftime('%Y-%m-%d')
    return alpaca.list_orders(status, limit=500, after=today_str)

def GetPositions():
    # get orders of the defined type
    alpaca = tradeapi.REST()
    today_str = datetime.utcnow().strftime('%Y-%m-%d')
    return alpaca.list_positions()

def GetOrderCount():
    # Get the number of position waiting to be sold and pending orders
    heldstocks = len(GetPositions())
    #pendingstocks = len(GetOrders()) # I dont' think this will occur
    return int(int(heldstocks))

def GetLastOpenMarket():
    today = datetime.utcnow()
    startdate = today - timedelta(days=14)
    alpaca = tradeapi.REST()
    cal = alpaca.get_calendar(start=startdate.strftime('%Y-%m-%d'), end=today.strftime('%Y-%m-%d'))
    return cal[-1].date.strftime('%Y-%m-%d')

def GetOHLCV(ticker='CVS', timeframe='1Min', startdate='1971-01-21', enddate='2020-01-21'):
    # Gets single stock data from Alpaca given the specified date

    # Setup logging specifically for getting data
    quorumroot = os.environ.get("OURO_QUORUM", "C:\\TEMP")
    logpath = quorumroot + '\\getohlcv.log'

    # configure logging for this specific process
    logging.basicConfig(
        filename=logpath,
        filemode='a',
        format='%(asctime)s %(name)s %(levelname)s %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        level=os.environ.get("LOGLEVEL", "INFO"))

    logging.info('Getting ' + timeframe + ' for ' + ticker + ' on ' + startdate)

    # Initialize the Alpaca API
    alpaca = tradeapi.REST()

    # Put date strings into usable formats
    if timeframe == '1Min':
        startdate = parse(startdate)
        s = str(startdate.strftime("%Y-%m-%d")) + ' 09:30'
        e = str(startdate.strftime("%Y-%m-%d")) + ' 16:30'
    else:
        startdate = parse(startdate)
        enddate = parse(enddate)
        s = str(startdate.strftime("%Y-%m-%d"))
        e = str(enddate.strftime("%Y-%m-%d"))

    # get the stock data for the current stock
    barset = None
    while barset == None:
        try:
            barset = alpaca.get_barset(ticker, timeframe=timeframe, limit=1000,
                                       start=pd.Timestamp(s, tz='America/New_York').isoformat(),
                                       end=pd.Timestamp(e, tz='America/New_York').isoformat())

        except Exception as ex:
            logging.warning('Could not get barset data; retrying # in 10 seconds', exc_info=True)
            time.sleep(10)

    # Initialize working data structures
    df = {}
    raw = {}

    # Convert barset to usable dataframe
    # Note:  There is typically only one stock in the barset, but I guess there could be more
    for stock in barset.keys():
        bars = barset[stock]

        logging.debug('Converting bar data for ' + stock)
        data = {'ticker': [stock for bar in bars],
                't': [bar.t for bar in bars],
                'h': [bar.h for bar in bars],
                'l': [bar.l for bar in bars],
                'o': [bar.o for bar in bars],
                'c': [bar.c for bar in bars],
                'v': [bar.v for bar in bars]}

        # copy the raw data before doing anything else to it
        raw[stock] = pd.DataFrame(data)

    return raw[stock]

def WriteOHLCV(df=None, timeframe='1Min'):
    # Writes stock data to SQL Server and disk

    # Setup the output file
    quorumroot = os.environ.get("OURO_QUORUM", "C:\\TEMP")
    outpath = quorumroot + '\\ohlcv_' + datetime.now().strftime("%Y%m%d") + '_' + timeframe + '.csv'
    logpath = quorumroot + '\\WriteOHLCV.log'

    # Setup Logging
    logging.basicConfig(
        filename=logpath,
        filemode='a',
        format='%(asctime)s %(name)s %(levelname)s %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        level=os.environ.get("LOGLEVEL", "INFO"))

    # Setup the cursor for SQL Server
    crs = sqldbcursor()

    # set the destination table
    tn = None
    if timeframe == '1Min':
        tn = 'ohlcv_minute'
    else:
        tn = 'ohlcv_day'

    # delete the data from SQL Server
    qry = "DELETE FROM stockdata.." + tn + " WHERE "
    first=True
    for index, row in df.iterrows():
        # Add OR at the end if this isn't the first time in the loop
        if first:
            first = False
        else:
            qry = qry + ' or '

        # use the right keys in the WHERE clause
        if timeframe == '1Min':
            qry = qry + "(ticker = '" + row['ticker'] + "' AND t = '" + str(row['t'].strftime("%Y-%m-%d %H:%M%S")) + "-5:00')"
        else:
            qry = qry + "(ticker = '" + row['ticker'] + "' AND tradedate = '" + str(row['t'].strftime("%Y-%m-%d")) + "')"

    # Execute the delete query
    try:
        crs.execute(qry)
    except Exception as ex:
        logging.error(qry, exc_info=True)

    # Write the data to SQL Server in one transaction
    qry = "INSERT INTO stockdata.." + tn + " (ticker, tradedate, tradedatetime, t, o, h, l, c, v, stage) VALUES "
    first=True
    for index, row in df.iterrows():
    # Write to SQL via INSERT or UPDATE, depending if the row exists or not
        if first:
            first = False
        else:
            qry = qry + ', '

        # Add the value
        qry = qry + "('" + str(row['ticker']) + "'" \
                    ", '" + str(row['t'].strftime("%Y-%m-%d")) + "'" \
                    ", '" + str(row['t'].strftime("%Y-%m-%d %H:%M")) + "'" \
                    ", '" + str(row['t'].strftime("%Y-%m-%d %H:%M%S")) + "-5:00'" \
                    ", '" + str(row['o']) + "'" \
                    ", '" + str(row['h']) + "'" \
                    ", '" + str(row['l']) + "'" \
                    ", '" + str(row['c']) + "'" \
                    ", '" + str(row['v']) + "'" \
                    ", 'Ouro')"

    # Execute the query
    try:
        crs.execute(qry)
    except Exception as ex:
        logging.error(qry, exc_info=True)

    with open (outpath, 'a', newline='\n', encoding='utf-8') as outfile:
        df.to_csv(outfile, header=False, index=False)










