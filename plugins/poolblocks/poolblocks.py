#License#
# poolblocks.py is created by echiu64 and licensed under a Creative Commons Attribution-NonCommercial-ShareAlike 3.0 Unported License.
# http://creativecommons.org/licenses/by-nc-sa/3.0/
# Based on a work at github.com.
#
# Portions based on blockinfo.py by ryouiki and licensed under a Creative Commons Attribution-NonCommercial-ShareAlike 3.0 Unported License.
#
# TODO
#  If too many None responses for a particular block/hash/txid, we should stop trying
#

import eventlet
from eventlet.green import os, threading, socket
from eventlet import greenpool

import traceback
import random
import time
import sys
import re
import json
import urllib
import urllib2
import operator

from peak.util import plugins
from ConfigParser import RawConfigParser
from cookielib import CookieJar
from util import urlutil

import blockexplorer

class PoolBlocks:
    def __init__(self, bitHopper):
        self.bitHopper = bitHopper
        self.refreshInterval = 300
        self.refreshRandomJitter = 90
        self.execpoolsize = 20
        self.rate_limit = 100
        self.block_retrieve_limit = 25
        self.timeout = 30
        self.blocks = {}
        self.fetch = None
        # TODO blockexplore retry limit / retry delay configuration
        #self.blockexplorerRetryLimit
        #self.blockexplorerRetryDelay
        self.parseConfig()        
        self.threadpool = greenpool.GreenPool(size=8)
        self.execpool = greenpool.GreenPool(size=self.execpoolsize)
        
        hook = plugins.Hook('plugins.lp.announce')
        hook.register(self.lp_announce)
        hookv = plugins.Hook('plugins.poolblocks.verified')
        hookv.register(self.block_verified)
        self.lock = threading.RLock()
        self.log_msg('Startup')
        self.log_msg(' - refreshInterval: ' + str(self.refreshInterval))
        self.log_msg(' - refreshRandomJitter: ' + str(self.refreshRandomJitter))
        self.log_msg(' - execpoolsize: ' + str(self.execpoolsize))
        self.log_msg(' - rate_limit: ' + str(self.rate_limit))
        self.log_msg(' - timeout: ' + str(self.timeout))
        self.log_msg(' - block_retrieve_limit: ' + str(self.block_retrieve_limit))
        self.cleanup()
        eventlet.spawn_n(self.run)
        
    def parseConfig(self):
        self.fetchconfig = RawConfigParser()
        self.fetchconfig.read('poolblock.cfg')
        try:
            self.refreshInterval = self.bitHopper.config.getint('plugin.poolblocks', 'refreshInterval')
            self.refreshRandomJitter = self.bitHopper.config.getint('plugin.poolblocks', 'refreshRandomJitter')
            self.execpoolsize = self.bitHopper.config.getint('plugin.poolblocks', 'execpoolsize')
            self.block_retrieve_limit = self.bitHopper.config.getint('plugin.poolblocks', 'block_retrieve_limit')
            self.rate_limit = self.bitHopper.config.getint('plugin.poolblocks', 'ratelimit')
            if self.bitHopper.config.getboolean('plugin.poolblocks', 'use_ratelimit'):
                self.fetch = urlutil.URLFetchRateLimit(self.bitHopper, self.rate_limit)
        except Exception, e:
            self.log_msg('ERROR parsing config, possible missing section or configuration items: ' + str(e))
            if self.bitHopper.options.debug:
                traceback.print_exc()
                
    def log_msg(self,msg):
        self.bitHopper.log_msg(msg, cat='poolblock')
        
    def log_dbg(self,msg):
        self.bitHopper.log_dbg(msg, cat='poolblock')
        
    def log_trace(self,msg):
        self.bitHopper.log_trace(msg, cat='poolblock')

    def run(self):
        while True:
            try:
                self.fetchBlocks()
                self.execpool.waitall()
                self.threadpool.waitall()
                if self.bitHopper.options.trace:
                    #self.report()
                    pass
                interval = self.refreshInterval
                interval += random.randint(0, self.refreshRandomJitter)
                self.log_dbg('sleep ' + str(interval))
                eventlet.sleep(interval)
            except Exception, e:
                traceback.print_exc()
                eventlet.sleep(30)
    
    def cleanup(self):
        try:
            for file in os.listdir('.'):
                if file.startswith('tmpretrieve'):
                    os.remove(file)
        except Exception, e:
            traceback.print_exc()
    
    def fetchBlocks(self):
        with self.lock:
            self.log_trace('fetchBlocks')
            for pool in self.fetchconfig.sections():
                try:
                    self.log_trace('fetchBlocks: ' + str(pool))
                    url = self.fetchconfig.get(pool, 'url')
                    searchStr = self.fetchconfig.get(pool, 'search')
                    try: mode = self.fetchconfig.get(pool, 'mode')
                    except: mode = 'b'
                    try: type = self.fetchconfig.get(pool, 'type')
                    except: type = None
                    self.execpool.spawn_n(self.fetchBlocksFromPool, pool, url, searchStr, mode, type)
                except Exception, e:
                    if self.bitHopper.options.debug:
                        traceback.print_exc()
                    else:
                        self.log_msg('ERROR fetchBlocks: ' + str(pool))
            
            
    
    def fetchBlocksFromPool(self, pool, url, searchstr, mode='b', type=None):
        self.log_trace('fetchBlockFromPool ' + str(pool) + ' | ' + str(url) + ' | ' + str(searchstr) + ' | ' + str(mode) )
        searchPattern = re.compile(searchstr)
        matchCount = 0
        outputs = None
        
        if type == 'btcmp':
            cj = CookieJar()
            opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cj))
            opener.addheaders = [('User-agent', 'Mozilla/5.0 (compatible; MSIE 9.0; Windows NT 6.1; WOW64; Trident/5.0)'),('Referer', 'http://btcmp.com')]
            response = opener.open(url, None, self.timeout)
            # find session id
            session_id = None
            for cookie in cj:
               if cookie.name == 'session_id':
                  session_id = cookie.value
                  break
            
            values = {'_token': session_id, 'limit':60}
            data = urllib.urlencode(values)
            json_url = self.fetchconfig.get(pool, 'json_url')
            try:
                response = opener.open(json_url, data, self.timeout)
                json_data = response.read()
                data = json.loads(json_data)
            except Exception, e:
                self.log_msg('Error ' + str(pool) + ' : ' + str(e))
                return
            
            count = 0
            for block in data['blockstats']:
                blockNumber = block['blockno']
                blockHash = block['blockhash']
                if blockNumber not in self.blocks:
                    matchCount += 1
                    self.log_trace('['+str(pool)+'] Block ' + str(blockNumber) + ' not found, adding new block')
                    self.blocks[blockNumber] = Block()
                    self.blocks[blockNumber].hash = blockHash
                    self.blocks[blockNumber].owner = pool
                    hook = plugins.Hook('plugins.poolblocks.verified')
                    hook.notify(blockNumber, blockHash, pool)
                elif self.blocks[blockNumber].owner != pool:
                    self.log_trace('['+str(pool)+'] Block ' + str(blockNumber) + ' exists but with different owner: ' + str(self.blocks[blockNumber].owner) )
                    self.blocks[blockNumber].owner = pool
                    matchCount += 1
                    hook = plugins.Hook('plugins.poolblocks.verified')
                    hook.notify(blockNumber, blockHash, pool)
                else:
                    self.log_trace('['+str(pool)+'] Block ' + str(blockNumber) + ' exists same owner')
                count += 1
                if count > self.block_retrieve_limit:
                    break
            self.log_msg('[{0}] parsed {1} blocks, {2} matches'.format(pool, len(data['blockstats']), matchCount) )
            return
                        
        elif type == 'mmf':
            cj = CookieJar()
            opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cj))
            opener.addheaders = [('User-agent', 'Mozilla/5.0 (compatible; MSIE 9.0; Windows NT 6.1; WOW64; Trident/5.0)'),('Referer', 'http://mining.mainframe.nl/news')]
            auth_url = self.fetchconfig.get(pool, 'auth_url')
            username = self.fetchconfig.get(pool, 'user')
            password = self.fetchconfig.get(pool, 'pass')
            values = {'username':username, 'password':password}
            data = urllib.urlencode(values)
            try:
                response = opener.open(auth_url, data, self.timeout)
                eventlet.sleep(2)
                response = opener.open(url, None, self.timeout)
                outputs = searchPattern.findall(response.read())
                if len(outputs) < 5:
                    self.log_msg('mmf is acting up, skip this retrieve')
                    return
                if len(outputs) == 2:
                    self.log_msg('mmf is acting up, got wrong page')
                    return
                if len(outputs) > self.block_retrieve_limit:
                    outputs = outputs[0:self.block_retrieve_limit]
                self.log_trace('mmf: ' +str(outputs))
            except Exception, e:
                self.log_msg('Error ' + str(pool) + ' : ' + str(e))
                return
        
        else:
            try:
                data = None
                if self.fetch != None:
                    data = self.fetch.retrieve(url)
                else:
                    req = urllib2.Request(url)
                    response = urllib2.urlopen(url, None, self.timeout)
                    data = response.read()
                outputs = searchPattern.findall(data)
            except Exception, e:
                self.log_msg('Error ' + str(pool) + ' : ' + str(e))
                if self.bitHopper.options.trace:
                    traceback.print_exc()
                return
            # limit blocks found
            if len(outputs) > self.block_retrieve_limit:
                outputs = outputs[0:self.block_retrieve_limit]
        
        if mode == 'b':
            # pool reports block# solved
            for blockNumber in outputs:
                if blockNumber in self.blocks:
                    if self.blocks[blockNumber].owner != pool:
                        self.log_trace('[' + pool + '] block ' + str(blockNumber) + ' exists, setting owner')
                        self.blocks[blockNumber].owner = pool
                        blockHash = self.blocks[blockNumber].hash
                        if blockHash is None:
                            self.blocks[blockNumber].hash = blockexplorer.getBlockHashByNumber(blockNumber, urlfetch=self.fetch)
                        if blockHash is not None:
                            hook = plugins.Hook('plugins.poolblocks.verified')
                            hook.notify(blockNumber, blockHash, pool)
                        else:
                            self.log_msg('Could not find blockHash for block: ' + str(blockNumber))
                        matchCount += 1
                    else:
                        self.log_trace('[' + pool + '] block ' + str(blockNumber) + ' exists, owner already set to: ' + self.blocks[blockNumber].owner)
                else:
                    self.log_trace('[' + pool + '] block ' + str(blockNumber) + ' does not exist, adding')
                    matchCount += 1
                    self.threadpool.spawn_n(self.fetchBlockFromPool, pool, blockNumber, mode)
                
        elif mode == 'h':
            # pool reports block hash solved
            for blockHash in outputs:                
                found = False
                for blockNumber in self.blocks:
                    if str(blockHash) == self.blocks[blockNumber].hash:
                        if self.blocks[blockNumber].owner != pool:
                            self.log_trace('[' + pool + '] Found hash, setting owner to ' + str(pool))
                            self.blocks[blockNumber].owner = pool
                            hook = plugins.Hook('plugins.poolblocks.verified')
                            hook.notify(blockNumber, blockHash, pool)
                            matchCount += 1
                        else:
                            self.log_trace('[' + pool + '] block ' + str(blockNumber) + ' exists, owner already set to: ' + self.blocks[blockNumber].owner)
                        found = True
                        break
                if not found:
                    matchCount += 1
                    self.log_trace('[' + pool + '] Hash not found, looking up block number')
                    self.threadpool.spawn_n(self.fetchBlockFromPool, pool, blockHash, mode)
                    
        elif mode == 'g':
            # pool uses transaction id
            for txid in outputs:
                found = False
                for blockNumber in self.blocks:
                    if str(txid) == self.blocks[blockNumber].txid:
                        if self.blocks[blockNumber].owner != pool:
                            self.log_trace('[' + pool + '] Found TXID, setting owner to ' + str(pool))
                            self.blocks[blockNumber].owner = pool
                            hook = plugins.Hook('plugins.poolblocks.verified')
                            hook.notify(blockNumber, blockHash, pool)
                            matchCount += 1                                                       
                        else:
                            self.log_trace('[' + pool + '] Found TXID, owner aready set to ' + str(pool))
                        found = True
                        break
                if not found:
                    self.log_trace('[' + pool + '] TXID not found, looking up block number and hash')
                    matchCount += 1
                    self.threadpool.spawn_n(self.fetchBlockFromPool, pool, txid, mode)               
        
        self.log_msg('[{0}] parsed {1} blocks, {2} matches'.format(pool, len(outputs), matchCount) )

    def fetchBlockFromPool(self, pool, blockInfo, mode='b'):
        self.log_trace('fetchBlockFromPool: ' + str(pool) + ' blockInfo ' + str(blockInfo))
        if mode == 'b':
            # block number
            blockNumber = blockInfo
            blockHash = blockexplorer.getBlockHashByNumber(self.bitHopper, blockNumber, urlfetch=self.fetch)
            if blockHash is not None:
                self.blocks[blockNumber] = Block()
                self.blocks[blockNumber].owner = pool
                self.blocks[blockNumber].hash = blockHash
                hook = plugins.Hook('plugins.poolblocks.verified')
                hook.notify(blockNumber, blockHash, pool)
            else:
                self.log_msg('[' + pool + '] ERROR ' + str(blockNumber) + ' and hash ' + str(blockHash))
           
        elif mode == 'h':
            # block hash
            blockHash = blockInfo
            blockNumber = blockexplorer.getBlockNumberByHash(self.bitHopper, blockHash, urlfetch=self.fetch)
            self.log_dbg('[' + pool + '] Block Number ' + str(blockNumber) + ' found for hash ' + blockHash)
            if blockNumber is not None:
                self.log_trace('[' + pool + '] Creating new block: ' + str(blockNumber))
                self.blocks[blockNumber] = Block()
                self.blocks[blockNumber].hash = blockHash
                self.blocks[blockNumber].owner = pool
                hook = plugins.Hook('plugins.poolblocks.verified')
                hook.notify(blockNumber, blockHash, pool)
            else:
                self.log_msg('[' + pool + '] ERROR ' + str(blockNumber) + ' and hash ' + str(blockHash))

        elif mode == 'g':
            # txid
            blockHash, blockNumber = blockexplorer.getBlockHashAndNumberByTxid(self.bitHopper, blockInfo, urlfetch=self.fetch)
            self.log_dbg('[' + pool + '] Block Number ' + str(blockNumber) + ' and hash ' + str(blockHash) + ' found for txid ' + blockInfo)
            if blockNumber is not None and blockHash is not None:
                found = False
                for bNumber in self.blocks:
                    if str(bNumber) == blockNumber:
                        self.log_dbg('['+pool+'] Found block ' + str(bNumber) + ' setting new owner')
                        self.blocks[blockNumber].owner = pool
                        self.blocks[blockNumber].txid = blockInfo
                        found = True
                        hook = plugins.Hook('plugins.poolblocks.verified')
                        hook.notify(blockNumber, blockHash, pool)
                        
                if not found:
                    self.log_trace('[' + pool + '] Creating new block: ' + str(blockNumber))
                    self.blocks[blockNumber] = Block()
                    self.blocks[blockNumber].hash = blockHash
                    self.blocks[blockNumber].owner = pool
                    self.blocks[blockNumber].txid = blockInfo                    
                    hook = plugins.Hook('plugins.poolblocks.verified')
                    hook.notify(blockNumber, blockHash, pool)
            else:
                self.log_msg('[' + pool + '] ERROR ' + str(blockNumber) + ' and hash ' + str(blockHash) + ' for ' + str(blockInfo) )

    def report(self):
        self.log_trace('report()')
        keys = sorted(self.blocks.keys(), key=int)
        count = 0
        for blockNumber in keys:
            block = self.blocks[blockNumber]
            print "Block %6d %12s %64s " % ( int(blockNumber), str(block.owner), str(block.hash) )
        
    def lp_announce(self, lpobj, body, server, blockHash):
        self.log_trace('lp_announce for block ' + str(blockHash))
        return
        # untested
        with self.lock:
            try:
                found = False
                for blockNumber in self.blocks:
                    if str(self.blocks[blockNumber].hash) == blockHash:
                        found = True
                if found == False:
                    self.log_trace('lp_announce: new block ' + str(blockHash))
                    # lookup block number
                    blockNumber = blockexplorer.getBlockNumberByHash(blockHash, urlfetch=self.fetch)
                    if blockNumber != None:
                        self.log_dbg('lp_announce: new block ' + str(blockNumber))
                        self.blocks[blockNumber] = Block()
                        self.blocks[blockNumber].hash = blockHash
                    else:
                        self.log_msg('No block number from blockexplorer for ' + str(blockHash))
            except Exception, e:
                traceback.print_exc()
    
    def block_verified(self, blockNumber, blockHash, pool):
        if blockHash in self.bitHopper.lp.blocks:
            self.log_trace('block exists, add verified owner ' + str(pool) + ' for ' + str(blockHash) )
            self.bitHopper.lp.blocks[blockHash]['_verified'] = pool
    
# class for Block       
class Block:
    def __init__(self):
        self.hash = None
        self.number = None
        self.owner = None
        self.coinbase = None #TBD
        self.txid = None #TBD
    
