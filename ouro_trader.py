# OURO_TRADER:  Buys and sells stocks based on signals from pathfinder
# Written by Dave Andrus on May 17, 2020
# Copyright 2020 Agile Data Guru
# https://github.com/AgileDataGuru/Ouro

# Required modules
import ouro_lib as ol
import json                             # for manipulating array data
import os                               # for basic OS functions
import pandas as pd                     # in-memory database capabilities
import argparse
from progress.bar import Bar
import datetime                         # used for stock timestamps
import alpaca_trade_api as tradeapi     # required for interaction with Alpaca
import csv
import logging
import time

# Get Quorum path from environment
quorumroot = os.environ.get("OURO_QUORUM", "C:\\TEMP")
actionpath = quorumroot + '\\broker-actions.json'
buyskippath = quorumroot + '\\broker-buyskip.json'
statuspath = quorumroot + '\\broker-status.csv'
logpath = quorumroot + '\\trader.log'
installpath = os.environ.get("OURO_INSTALL", "D:\\OneDrive\\Dev\\Python\\Oura")

# Setup Logging
logging.basicConfig(
    filename=logpath,
    filemode='a',
    format='%(asctime)s %(name)s %(levelname)s %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    level=os.environ.get("LOGLEVEL", "INFO"))

logging.info('OURO-TRADER logging enabled.')

# initialize files
try:
    logging.debug('Initializing trader files.')
    with open (statuspath, 'w', newline='\n', encoding='utf-8') as outfile:
        outfile.write('')
    with open (buyskippath, 'w', newline='\n', encoding='utf-8') as outfile:
        outfile.write('')
except Exception:
    logging.error('Could not initialize files', exc_info=True)
    quit()

# setup command line
parser = argparse.ArgumentParser(description="OURO-HISTORY:  Daily stock data ingestion.")
parser.add_argument("--test", action="store_true", default=False, help="Script runs in test mode.  FALSE (Default) = ignore if the market is closed; TRUE = only run while the market is open")
parser.add_argument("--marketopen", action="store_true", default=False, help="Force the market to be open for one execution.  FALSE (Default) = query the actual market; TRUE = set the market as open for one execution for testing purposes.")
cmdline = parser.parse_args()
logging.info('Command line arguement; test mode is ' + str(cmdline.test))

# Initialize the Alpaca API
alpaca = tradeapi.REST()

# Read the buy and sell strategies
strategies = pd.read_csv(installpath + '\\buy_strategies.csv')

# build simple index between family and average return percentage
familyreturns = {}
try:
    logging.debug('Building strategy families and average return percentages')
    for x in strategies['Family'].keys():
        familyreturns[strategies.at[x, 'Family']] = strategies.at[x, 'AvgPctRtn']
except Exception:
    logging.error('Could not build strategies', exc_info=True)


# Set maximum risk ratio to 0.5% of the account
# This ratio cannot be exceeded on a single trade
maxriskratio = .004

# Initialize the stock lists
boughtlist = []
skiplist = []
status = {}
closeprices = {}

# Get the closing prices for all the stocks from yesterday
query = "select ticker, c from stockdata..ohlcv_day o " \
        "where tradedate in (select dateadd(day, -1, max(tradedate)) from stockdata..ohlcv_day)"
crs = ol.sqldbcursor()
crs.execute(query)
for x in crs.fetchall():
    closeprices[x[0]] = x[1]


# Initialize MarketOpen
marketopen = ol.IsOpen()
eod = ol.IsEOD()

# Force the market open if configured to do so
if cmdline.marketopen:
    logging.info ('Forcing market to be open')
    marketopen = True
    eod = False

# Wait for the market to open unless it's a test
while not marketopen and not cmdline.test:
    logging.info('Market is closed; waiting for 1 minute.')
    marketopen = ol.IsOpen()
    ol.WaitForMinute()

# This is to work around an odd problem with Alpaca and the way it reports cash / buying power
account = ol.GetAccount()
cash = (float(account.buying_power) / (float(account.multiplier)))-25001 # minimum amount for day trading
tradecapital = cash / 10

while (marketopen and not eod) or cmdline.test is True:
    marketopen = ol.IsOpen()
    eod = ol.IsEOD()

    # Log info for heartbeat
    logging.info('Checking inbound stock actions.')

    # get ticker actions
    with open(actionpath, 'r', encoding='utf-8') as infile:
        inboundactions = json.load(infile)

    #setup a progress bar
    starttime = datetime.datetime.now().strftime('%H:%M:%S')
    logtime = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    prgbar = Bar('  Stocks ' + starttime + ': ', max=len(inboundactions))

    # Bandwagonning happens where trader gets out of sync with pathfinder
    # and there is an abundance of orders (>10) that need to be bought.
    # This script will submit buy orders faster than they can be executed
    # so they're never seen in order count.  This helps limit the effect
    # of bandwagonning.
    inboundcount = 0
    for stock in inboundactions:
        if stock not in boughtlist and stock not in skiplist:
            inboundcount += 1

    # loop through the inbound stocks
    for stock in inboundactions:
        if inboundcount >= 10:
            # Give the order execution engine time to catch up
            time.sleep(2)
            # Reduce the risk if bandwaggoning is happening
            bandwagondiscount = .3
            logging.debug('Bandwagonning detected; reducing risk and delaying order placement.')
        else:
            # This is normal; risk is not modified
            bandwagondiscount = 1

        if stock not in boughtlist and stock not in skiplist:
            # how much is the stock
            stockprice = float(inboundactions[stock].get('price'))
            recenthigh = float(inboundactions[stock].get('recenthigh'))
            recentlow = float(inboundactions[stock].get('recentlow'))
            yesterdayclose = float(closeprices.get(stock))

            # set max trade risk
            maxriskamt = cash * maxriskratio * bandwagondiscount
            traderiskamt = cash * maxriskratio * bandwagondiscount

            # how much capital should I use on this trade?
            ordercount = ol.GetOrderCount()
            if ordercount < 10:
                # tradecapital = cash / float(10-ordercount)
                logging.debug('Orders are < 10; trade capital set to ' + str(tradecapital))
            else:
                # tradecapital = 0
                logging.debug('Orders count is > 10; trade capital set to 0')

            # how many shares should I buy
            ordershares = int(tradecapital/float(inboundactions[stock].get('price')))

            # reset pricing
            floorprice = 0
            ceilingprice = 0
            buylimit = 0
            traderiskpct = 0
            familyret = 0

            if ordercount < 10:
                # reset the skip reason
                skipreason = 'Unknown'

                # Get the strategy family and estimated return
                family = inboundactions[stock].get('strategyfamily')
                familyret = float(familyreturns[family]) * .8  # It's rare that the average is every filled

                # Set the baseline floor price and percent based on the return rate
                floorpct = familyret * .5
                floorprice = stockprice * (1-floorpct)

                # set the ceiling price for the bracket order
                ceilingprice = stockprice * (1 + float(familyreturns[family]))

                # Adjust prices to recent high/low if we're using oscilators
                if family != 'Candlestick':
                    # Pricing reality check -- are the prices achievable in the recent past?
                    if ceilingprice > recenthigh:
                        ceilingprice = recenthigh - 0.05  # $0.05 under the recent high
                    if floorprice > recentlow:
                        skipreason = 'Proposed stop-loss price already hit today'
                        ordershares = 0

                # Adjust the floor price if there is more risk than reward
                if (stockprice * ordershares * floorpct) > maxriskamt:
                    # Use 40% of the ceiling difference as the new floor amount
                    floorprice = stockprice - ((ceilingprice-stockprice) * .4) # I never want to break even on risk

                # Calculate the amount risked on this trade
                traderiskamt = (stockprice - floorprice) * ordershares
                traderiskpct = (stockprice - floorprice) / stockprice

                # set the buy limit to 5% of the potential profit
                buylimit = ((ceilingprice - stockprice) * .05) + stockprice

                # Calculate the trade return
                traderet = (ceilingprice - buylimit) / buylimit

                # Check if the price change between now and yesterday's close is more than
                # the average for this strategy family.
                if (stockprice - yesterdayclose) / yesterdayclose >= traderet:
                    ordershares = 0
                    skipreason = 'The potential return has already been met today.'

                # Are we planning on making more than we risk?
                if traderet-.005 <= traderiskpct:
                    # This is a bad trade
                    ordershares = 0
                    skipreason = 'Risk outweighs reward'

                # place the order
                if ordershares > 0:
                    try:
                        logging.debug('Placing a bracket order for' + stock)
                        alpaca.submit_order(
                            side='buy',
                            symbol=stock,
                            type='limit',
                            limit_price=buylimit,
                            qty=ordershares,
                            time_in_force='day', # bracket order must be 'day' or 'gtc'
                            order_class='bracket',
                            take_profit={
                                'limit_price': ceilingprice
                            },
                            stop_loss={
                                'stop_price': floorprice
                            }

                        )
                        # Add this to the stocks already bought
                        # Note:  Only add this to the bought list if the placing the order was successful
                        #        This allows the stock to be re-tried if the price falls below the stop
                        #        point before the buy order can be filled.
                        boughtlist.append(stock)
                        status[stock] = {
                            'DateTime': logtime,
                            'Ticker': stock,
                            'Cash': cash,
                            'TradeCapital': tradecapital,
                            'BuyPrice': stockprice,
                            'BuyLimit': buylimit,
                            'MaxRiskAmt': maxriskamt,
                            'TradeRiskAmt': traderiskamt,
                            'TradeRiskPct': traderiskpct,
                            'PortfolioRiskPct': traderiskamt/cash,
                            'FamilyReturnPct': familyret,
                            'TradeReturnPct' : traderet,
                            'OrderShares': ordershares,
                            'RecentHigh': recenthigh,
                            'RecentLow':  recentlow,
                            'FloorPrice': floorprice,
                            'CeilingPrice': ceilingprice,
                            'Decision': 'buy',
                            'Reason': family
                        }
                    except Exception as ex:
                        logging.error('Could not submit buy order', exc_info=True)
                        logging.info('Skipping ' + stock + ' because buy order failed.')
                        if stock not in skiplist:
                            # add this to the skip list -- the timing just wasn't right
                            # skiplist.append(stock) -- With buy limits, I don't need to do this.

                            # Annotate what happened
                            status[stock] = {
                                'DateTime': logtime,
                                'Ticker': stock,
                                'Cash': cash,
                                'TradeCapital': tradecapital,
                                'BuyPrice': stockprice,
                                'BuyLimit': buylimit,
                                'MaxRiskAmt': maxriskamt,
                                'TradeRiskAmt': traderiskamt,
                                'TradeRiskPct': traderiskpct,
                                'PortfolioRiskPct': traderiskamt / cash,
                                'FamilyReturnPct': familyret,
                                'TradeReturnPct': traderet,
                                'OrderShares': ordershares,
                                'RecentHigh': recenthigh,
                                'RecentLow': recentlow,
                                'FloorPrice': floorprice,
                                'CeilingPrice': ceilingprice,
                                'Decision': 'skip',
                                'Reason': skipreason + ' - buy order failed; eligible for retry.'
                            }
                else:
                    # define skipping reasons if not previously defined
                    if ordershares == 0 and skipreason == 'Unknown':
                        skipreason = 'Stock is too expensive or unable to buy shares.'
                    if stock in boughtlist and skipreason == 'Unknown':
                        skipreason = 'Stock in bought list.'
                    if ordercount >= 10 and skipreason == 'Unknown':
                        skipreason = 'Too many existing positions'

                    logging.info('Skipping ' + stock)
                    if stock not in skiplist:
                        # add this to the skip list -- the timing just wasn't right
                        skiplist.append(stock)
                        status[stock] = {
                            'DateTime': logtime,
                            'Ticker': stock,
                            'Cash': cash,
                            'TradeCapital': tradecapital,
                            'BuyPrice': stockprice,
                            'BuyLimit': buylimit,
                            'MaxRiskAmt': maxriskamt,
                            'TradeRiskAmt': traderiskamt,
                            'TradeRiskPct': traderiskpct,
                            'PortfolioRiskPct': traderiskamt/cash,
                            'FamilyReturnPct': familyret,
                            'TradeReturnPct' : traderet,
                            'OrderShares': ordershares,
                            'RecentHigh': recenthigh,
                            'RecentLow':  recentlow,
                            'FloorPrice': floorprice,
                            'CeilingPrice': ceilingprice,
                            'Decision': 'skip',
                            'Reason': skipreason + '; not eligible for retry.'
                        }
        # Update the order count after submitting the order
        ordercount = ol.GetOrderCount()

        #advance the progress bar
        prgbar.next()

    # finish the progress bar
    prgbar.finish()

    # write the bought and skip lists
    try:
        logging.debug('Writing bought and skip list.')
        with open (buyskippath, 'w', newline='\n', encoding='utf-8') as outfile:
            tmp = {
                'buy': boughtlist,
                'skip': skiplist
            }
            tmp = json.dumps(status, indent=4)
            outfile.write(tmp)
    except Exception:
        try:
            logging.error('Could not write buy and skip list', exc_info=True)
        except:
            print('Could not write to log file')

    # update broker status
    try:
        logging.debug('Writing broker status')
        with open (statuspath, 'w', newline='\n', encoding='utf-8') as outfile:
            fieldnames = ['DateTime', 'Ticker', 'Cash', 'TradeCapital', 'BuyPrice', 'BuyLimit', 'MaxRiskAmt',
                          'TradeRiskAmt', 'TradeRiskPct', 'PortfolioRiskPct', 'RiskPct', 'FamilyReturnPct', 'TradeReturnPct', 'OrderShares', 'RecentHigh',
                          'RecentLow','FloorPrice', 'CeilingPrice', 'Decision', 'Reason']
            writer = csv.DictWriter(outfile, fieldnames=fieldnames)
            # write the header
            writer.writeheader()
            #writer.writerow(['datetime', 'ticker', 'cash', 'TradeRiskAmt', 'TradeCapital', 'OrderShares', 'FloorPrice', 'CeilingPrice', 'Decision'])
            for x in status:
                writer.writerow(status[x])
    except Exception:
        try:
            logging.error('Could not write broker status', exc_info=True)
        except:
            print('Could not to log file.')


    # wait until the next minute before checking again
    ol.WaitForMinute()

# Log the transition to end of day processing
logging.info('Early end-of-day detected; checking for stocks that should be liquidated early.')

# Get stocks that should be sold early
try:
    crs = ol.sqldbcursor()
    query = "select ticker from stockdata..ticker_statistics where sellwhen = 'Early'"
    se = crs.execute(query)
    earlylist = []
    for x in se.fetchall():
        earlylist.append(x[0])
except Exception as ex:
    logging.error('Could not get list of early stocks.', exc_info=True)

logging.info('15-minute end-of-day check:  ' + str(ol.IsEOD(minutes=15)))

# If forcing the market open, simulate the end of day
eod = ol.IsEOD(minutes=15)
if cmdline.marketopen:
    eod = True

# Start wrapping up the day
while (not eod):
    # Check if a stock on an open order is in the early-sell list and cancel it
    for stock in ol.GetOrders():
        if stock.symbol in earlylist:
            try:
                alpaca.cancel_order(stock.id)
                logging.info('Cancelling open orders for ' + stock.symbol + ' early.')
            except Exception as ex:
                logging.error('Could not cancel order', exc_info=True)
    # If a held position is in the early sell list, close it
    for stock in ol.GetPositions():
        if stock.symbol in earlylist:
            try:
                alpaca.close_position(stock.symbol)
                logging.info('Closing open positions for ' + stock.symbol + ' early.')
            except Exception as ex:
                logging.error('Could not close position', exc_info=True)

    # Wait for a minute until we're 15 minutes before the end of the day
    time.sleep(60)

    # If forcing the market open, simulate the end of day
    eod = ol.IsEOD(minutes=15)
    if cmdline.marketopen:
        eod = True
    logging.info('15-minute end-of-day check:  ' + str(eod))


# It's the end of the day; cancel orders and quit
logging.info('End of day reached; liquidating all orders.')
try:
    alpaca.cancel_all_orders()
    alpaca.close_all_positions()
except Exception as ex:
    logging.error('Could not cancel orders and liquidate positions at the end of the day.', exc_info=True)





