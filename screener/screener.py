#! /usr/bin/env python3
'''
# Wolfinch Stock Screener
# Desc: Main File implements Screener Entry points
#  Copyright: (c) 2017-2021 Joshith Rayaroth Koderi
#  This file is part of Wolfinch.
# 
#  Wolfinch is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
# 
#  Wolfinch is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
# 
#  You should have received a copy of the GNU General Public License
#  along with Wolfinch.  If not, see <https://www.gnu.org/licenses/>.
'''

import time
import sys
import os
import traceback
import argparse
from decimal import getcontext
import random
# import logging
sys.path.append(os.path.join(os.path.abspath(os.path.dirname(sys.argv[0])), "../pkgs"))

from utils import getLogger, get_product_config, load_config, get_config
# import sims
# import exchanges
import db
from  strategies import Configure
import ui
# from ui import ui_conn_pipe

import nasdaq

# mpl_logger = logging.getLogger('matplotlib')
# mpl_logger.setLevel(logging.WARNING)
log = getLogger('Screener')
log.setLevel(log.INFO)

ticker_import_time = 0
all_tickers = []
YF = None

# global Variables
MAIN_TICK_DELAY = 0.500  # 500 milli


def screener_init():
    global YF
    # seed random
    random.seed()

    # 1. Retrieve states back from Db
#     db.init_order_db(Order)
    register_screeners()
    
    # setup ui if required
    ui.integrated_ui = True
    if ui.integrated_ui:
        log.info("ui init")
        ui.ui_conn_pipe = ui.ui_mp_init(ui.port, ui.screener.ui_main)
        if ui.ui_conn_pipe is None:
            log.critical("unable to setup ui!! ")
            print("unable to setup UI!!")
            sys.exit(1)

def screener_end():
    log.info("Finalizing Screener")

    # stop stats thread
    log.info("waiting to stop stats thread")

    ui.ui_mp_end()
    log.info("all cleanup done.")


def screener_main():
    """
    Main Function for Screener
    """

    integrated_ui = ui.integrated_ui
    ui_conn_pipe = ui.ui_conn_pipe

    sleep_time = MAIN_TICK_DELAY
    while True:
        if integrated_ui == True:
            process_ui_msgs(ui_conn_pipe)        
        cur_time = time.time()
        update_data()
        process_screeners()
        # '''Make sure each iteration take exactly LOOP_DELAY time'''
        sleep_time = (MAIN_TICK_DELAY -(time.time()- cur_time))
#         if sleep_time < 0 :
#             log.critical("******* TIMING SKEWED(%f)******"%(sleep_time))
        sleep_time = 0 if sleep_time < 0 else sleep_time
        time.sleep(sleep_time)
    # end While(true)


g_screeners = []
g_ticker_stats = {}
def register_screeners():
    global g_screeners
    log.debug("registering screeners")
    g_screeners = Configure()
    
def update_data():
    log.debug("updating data")
    sym_list = get_all_tickers()
    for scrn_obj in g_screeners:
        if scrn_obj.interval + scrn_obj.update_time < int(time.time()):
            s_list = sym_list.get(scrn_obj.ticker_kind)
            if not s_list :
                log.critical("unable to find ticker list kind %s"%(scrn_obj.ticker_kind))
                continue
            log.info ("updating screener data - %s"%(scrn_obj.name))                
            if scrn_obj.update(s_list, g_ticker_stats):
                scrn_obj.update_time = int(time.time())
                scrn_obj.updated = True

def process_screeners ():
    log.debug("processing screeners")
    for scrn_obj in g_screeners:
        if scrn_obj.updated :
            log.info ("running screener - %s"%(scrn_obj.name))
            scrn_obj.screen(g_ticker_stats)
            scrn_obj.updated = False
            
def get_all_screener_data():
    #run thru all screeners and collect filtered data
    filtered_list = {}
    for scrn_obj in g_screeners:
        log.debug("get screener data from %s"%(scrn_obj.name))
        filtered_list[scrn_obj.name] = scrn_obj.get_screened()
    return filtered_list
                
def get_all_tickers ():
    global ticker_import_time, all_tickers
    log.debug ("get all tickers")
    if ticker_import_time + 24*3600 < int(time.time()) :
        log.info ("renew tickers list")
#         t_l = nasdaq.get_all_tickers_gt50m()
        t_l = nasdaq.get_all_tickers_megacap()
        if t_l:
            all_tickers = {}
            mcap = []
            for ticker in t_l:
                mcap.append(ticker["symbol"].strip())
                all_tickers["MEGACAP"] = mcap        
            ticker_import_time = int(time.time())
    return all_tickers
    
def process_ui_msgs(ui_conn_pipe):
    try:
        while ui_conn_pipe.poll():
            msg = ui_conn_pipe.recv()
            err = msg.get("error", None)
            if  err is not None:
                log.error("error in the pipe, ui finished: msg:%s" %(err))
                raise Exception("UI error - %s" %(err))
            else:
                log.info ("ui_msg: %s"%(msg))
                msg_type = msg.get("type")
                if msg_type == "GET_SCREENER_DATA":
                    process_get_screener_data(msg)
                else:
                    log.error("Unknown ui msg type: %s", msg_type)
    except Exception as e:
        log.critical("exception %s on ui" %(str(e)))
        raise e
    
def process_get_screener_data(msg):
    log.info("msg %s"%(msg))

    dataSet = get_all_screener_data()
    
    msg["type"] = "GET_SCREENER_DATA_RESP"
    msg["data"] = dataSet #{}
    ui.ui_conn_pipe.send(msg)    

def clean_states():
    ''' 
    clean states
    '''
    log.info("Clearing Db")
    db.clear_db()

def arg_parse():
    '''
    arg parse
    '''
    parser = argparse.ArgumentParser(description='Wolfinch Screener')

    parser.add_argument('--version', action='version', version='%(prog)s 1.0.1')
    parser.add_argument("--clean",
                        help='Clean states,dbs and exit. Clear all the existing states',
                        action='store_true')
    parser.add_argument("--port", help='API Port')
    parser.add_argument("--restart", help='restart from the previous state', action='store_true')

    args = parser.parse_args()

    if args.clean:
        clean_states()
        exit(0)

    if args.port:
        log.debug("port: %s" % (str(args.port)))
        ui.port = args.port
    else:
        pass
#         parser.print_help()
#         exit(1)

    if args.restart:
        log.debug("restart enabled")
        print("Restarting from previous state")
    else:
        log.debug("restart disabled")

######### ******** MAIN ****** #########
if __name__ == '__main__':
    '''
    main entry point
    '''
    arg_parse()
    getcontext().prec = 8  # decimal precision
    print("Starting Wolfinch Screener..")
    try:
        screener_init()
        log.info("Starting Main forever loop")
        print("Starting Main forever loop")            
        screener_main()
    except(KeyboardInterrupt, SystemExit):
        screener_end()
        sys.exit()
    except Exception as e:
        log.critical("Unexpected error: exception: %s" %(traceback.format_exc()))
        print("Unexpected error: exception: %s" %(traceback.format_exc()))
        screener_end()
        raise
#         traceback.print_exc()
#         os.abort()
    # '''Not supposed to reach here'''
    print("\nScreener end")

# EOF