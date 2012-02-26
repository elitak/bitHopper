#!/usr/bin/python
#Copyright (C) 2011,2012 Colin Rice
#This software is licensed under an included MIT license.
#See the file entitled LICENSE
#If you were not provided with a copy of the license please contact: 
# Colin Rice colin@daedrum.net


#
# Usage: Add a unique wallet:xxxxx option for each pool to user.cfg
#        this will overwrite any previous manually set payout value

import traceback, logging
from jsonrpc import ServiceProxy

import gevent
import time, threading

class Payouts():
    def __init__(self, bitHopper):
        self.bitHopper = bitHopper
        self.interval = 600
        self.parseConfig()
        self.log_msg("Payouts interval: " + str(self.interval))
        gevent.spawn(self.run)
        self.lock = threading.RLock()
            
    def parseConfig(self):
        try:
            self.interval = self.bitHopper.config.getint('plugin.payouts', 'interval')
            self.rpcuser = self.bitHopper.config.get('plugin.payouts', 'rpcuser')
            self.rpcpass = self.bitHopper.config.get('plugin.payouts', 'rpcpass')
            self.rpchost = self.bitHopper.config.get('plugin.payouts', 'rpchost')
            self.rpcport = self.bitHopper.config.get('plugin.payouts', 'rpcport')
        except:
            traceback.print_exc()
        
    def log_msg(self, msg, **kwargs):
        logging.info(msg)
        
    def log_dbg(self, msg, **kwargs):
        logging.debug(msg)
        
    def run(self):
        access = ServiceProxy('http://' + self.rpcuser + ':' + self.rpcpass + '@' + self.rpchost + ':' + self.rpcport)
        while True:
            for server in self.bitHopper.pool.servers:
                info = self.bitHopper.pool.get_entry(server)

                if info['wallet'] != "":
                    wallet = info['wallet']
                    try:
                        getbalance = float(access.getreceivedbyaddress(wallet))
                        self.log_msg(server + ' ' + str(getbalance) + ' ' + wallet)
                        self.bitHopper.update_payout(server, float(getbalance))
                    except Exception, e:
                        self.log_dbg("Error getting getreceivedbyaddress")
                        self.log_dbg(e)

            gevent.sleep(self.interval)
