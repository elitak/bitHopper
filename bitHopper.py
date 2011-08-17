#!/usr/bin/python
#License#
#bitHopper by Colin Rice is licensed under a Creative Commons
# Attribution-NonCommercial-ShareAlike 3.0 Unported License.
#Based on a work at github.com.

import json
import work
import diff
import stats
import pool
import speed
import database
import scheduler
import website
import getwork_store
import request_store
import data

import sys
import optparse
import time
import lp
import os
import os.path

from twisted.web import server, resource
from twisted.internet import reactor, defer
from twisted.internet.defer import Deferred
from twisted.internet.task import LoopingCall
from twisted.python import log, failure
from scheduler import Scheduler
import twisted.web.client
from lpbot import LpBot

class BitHopper():
    def __init__(self, options):
        """Initializes all of the submodules bitHopper uses"""
        self.options = options
        self.new_server = Deferred()
        self.stats_file = None
        self.lpBot = None
        self.reactor = reactor
        self.difficulty = diff.Difficulty(self)
        self.pool = pool.Pool(self)
        self.db = database.Database(self)
        self.lp = lp.LongPoll(self)
        self.speed = speed.Speed(self)
        self.stats = stats.Statistics(self)
        self.scheduler = scheduler.Scheduler(self)
        self.getwork_store = getwork_store.Getwork_store(self)
        self.request_store = request_store.Request_store(self)
        self.data = data.Data(self)
        self.pool.setup(self)
        self.auth = None
        self.work = work.Work(self)

    def reject_callback(self, server, data, user, password):
        self.data.reject_callback(server,data, user, password)

    def data_callback(self,server,data, user, password):
        self.data.data_callback(server, data, user, password)

    def update_payout(self,server,payout):
        self.db.set_payout(server,float(payout))
        self.pool.servers[server]['payout'] = float(payout)

    def lp_callback(self, work):
        if work == None:
            return
        merkle_root = work['data'][72:136]
        self.getwork_store.add(server,merkle_root)
        reactor.callLater(0,self.new_server.callback,work)
        self.new_server = Deferred()

    def get_json_agent(self):
        return self.json_agent

    def get_lp_agent(self):
        return self.lp_agent

    def get_options(self):
        return self.options

    def log_msg(self, msg, **kwargs):
        if kwargs and kwargs.get('cat'):
            print time.strftime("[%H:%M:%S] ") + '[' + kwargs.get('cat') + '] ' + str(msg)
        elif self.get_options() == None:
            print time.strftime("[%H:%M:%S] ") +str(msg)
            sys.stdout.flush()
        elif self.get_options().debug == True:
            log.msg(msg)
            sys.stdout.flush()
        else: 
            print time.strftime("[%H:%M:%S] ") +str(msg)
            sys.stdout.flush()

    def log_dbg(self, msg, **kwargs):
        if self.get_options().debug == True and kwargs and kwargs.get('cat'):
            log.err('['+kwargs.get('cat')+"] "+msg)
            sys.stderr.flush()
        elif self.get_options() == None:
            log.err(msg)
            sys.stderr.flush()
        elif self.get_options().debug == True:
            log.err(msg)
            sys.stderr.flush()
        return

    def get_server(self, ):
        return self.pool.get_current()

    def select_best_server(self, ):
        server_name = None
        server_name = self.scheduler.select_best_server()
        if server_name == None:
            self.log_msg('FATAL Error, scheduler did not return any pool!')
            os._exit(-1)
            
        if self.pool.get_current() != server_name:
            self.pool.set_current(server_name)
            self.log_msg("Server change to " + str(self.pool.get_current()))

        return

    def get_new_server(self, server):
        self.pool.get_entry(server)['lag'] = True
        self.log_dbg('Lagging. :' + server)
        self.server_update()
        return self.pool.get_current()

    def server_update(self, ):
        if self.scheduler.server_update():
            self.select_best_server()

    @defer.inlineCallbacks
    def delag_server(self ):
        #Delags servers which have been marked as lag.
        #If this function breaks bitHopper dies a long slow death.
        
        self.log_dbg('Running Delager')
        for server in self.pool.get_servers():
            info = self.pool.servers[server]
            if info['lag'] == True:
                data = yield self.work.jsonrpc_call(server,[])
                self.log_dbg('Got' + server + ":" + str(data))
                if data != None:
                    info['lag'] = False
                    self.log_dbg('Delagging')
                else:
                    self.log_dbg('Not delagging')


    def bitHopperLP(self, value, *methodArgs):
        try:
            self.log_msg('LP triggered serving miner')
            request = methodArgs[0]

            if self.request_store.closed(request):
                return value

            #Duplicated from above because its a little less of a hack
            #But apparently people expect well formed json-rpc back but won't actually make the call
            try:
                json_request = request.content.read()
            except Exception,e:
                self.log_dbg( 'reading request content failed')
                json_request = None
                return value
            try:
                rpc_request = json.loads(json_request)
            except Exception, e:
                self.log_dbg('Loading the request failed')
                rpc_request = {'params':[],'id':1}
                return value

            j_id = rpc_request['id']

            response = json.dumps({"result":value,'error':None,'id':j_id})
            if self.request_store.closed(request):
                return value
            request.write(response)
            request.finish()
            return value

        except Exception, e:
            self.log_msg('Error Caught in bitHopperLP')
            self.log_dbg(str(e))
            try:
                request.finish()
            except Exception, e:
                self.log_dbg( "Client already disconnected Urgh.")
        finally:
            return value

def parse_server_disable(option, opt, value, parser):
    setattr(parser.values, option.dest, value.split(','))

def select_scheduler(option, opt, value, parser):
    pass

bithopper_global = None

def main():
    parser = optparse.OptionParser(description='bitHopper')
    parser.add_option('--noLP', action = 'store_true' ,default=False, help='turns off client side longpolling')
    parser.add_option('--debug', action= 'store_true', default = False, help='Use twisted output')
    parser.add_option('--listschedulers', action='store_true', default = False, help='List alternate schedulers available')
    parser.add_option('--list', action= 'store_true', default = False, help='List servers')
    parser.add_option('--disable', type=str, default = None, action='callback', callback=parse_server_disable, help='Servers to disable. Get name from --list. Servera,Serverb,Serverc')
    parser.add_option('--port', type = int, default=8337, help='Port to listen on')
    parser.add_option('--scheduler', type=str, default=None, help='Select an alternate scheduler')
    parser.add_option('--threshold', type=float, default=None, help='Override difficulty threshold (default 0.43)')
    parser.add_option('--altslicesize', type=int, default=900, help='Override Default AltSliceScheduler Slice Size of 900')
    parser.add_option('--altminslicesize', type=int, default=60, help='Override Default Minimum Pool Slice Size of 60 (AltSliceScheduler only)')
    parser.add_option('--altslicejitter', type=int, default=0, help='Add some random variance to slice size, disabled by default (AltSliceScheduler only)')
    parser.add_option('--startLP', action= 'store_true', default = True, help='Seeds the LP module with known pools. Must use it for LP based hopping with deepbit, True by default')
    parser.add_option('--p2pLP', action='store_true', default=False, help='Starts up an IRC bot to validate LP based hopping.  Must be used with --startLP')
    parser.add_option('--ip', type = str, default='', help='IP to listen on')
    parser.add_option('--auth', type = str, default=None, help='User,Password')
    options, rest = parser.parse_args()
    global bithopper_global
    bithopper_global = BitHopper(options)

    if options.list:
        for k in bithopper_global.pool.get_servers():
            print k
        return

    if options.auth:
        auth = options.auth.split(',')
        bithopper_global.auth = auth
        if len(auth) != 2:
            print 'User,Password. Not whatever you just entered'
            return

    if options.listschedulers:
        schedulers = None
        for s in Scheduler.__subclasses__():
            if schedulers != None: 
                schedulers = schedulers + ", " + s.__name__
            else: 
                schedulers = s.__name__
        print "Available Schedulers: " + schedulers
        return
    
    if options.scheduler:
        bithopper_global.log_msg("Selecting scheduler: " + options.scheduler)
        foundScheduler = False
        for s in Scheduler.__subclasses__():
            if s.__name__ == options.scheduler:
                bithopper_global.scheduler = s(bithopper_global)
                foundScheduler = True
                break
        if foundScheduler == False:            
            bithopper_global.log_msg("Error couldn't find: " + options.scheduler + ". Using default scheduler.")
            bithopper_global.scheduler = scheduler.DefaultScheduler(bithopper_global)
    else:
        bithopper_global.log_msg("Using default scheduler.")
        bithopper_global.scheduler = scheduler.DefaultScheduler(bithopper_global)

    bithopper_global.select_best_server()

    if options.disable != None:
        for k in options.disable:
            if k in bithopper_global.pool.get_servers():
                if bithopper_global.pool.get_servers()[k]['role'] == 'backup':
                    bithopper_global.log_msg("You just disabled the backup pool. I hope you know what you are doing")
                bithopper_global.pool.get_servers()[k]['role'] = 'disable'
            else:
                bithopper_global.log_msg(k + " Not a valid server")

    if options.debug: log.startLogging(sys.stdout)

    if options.startLP:
        bithopper_global.log_msg( 'Starting LP')
        startlp = LoopingCall(bithopper_global.lp.start_lp)
        startlp.start(60*60)

    if options.p2pLP and options.startLP:
        bithopper_global.log_msg('Starting p2p LP')
        bithopper_global.lpBot = LpBot(bithopper_global)

    site = server.Site(website.bitSite(bithopper_global))
    reactor.listenTCP(options.port, site,5, options.ip)
    reactor.callLater(0, bithopper_global.pool.update_api_servers, bithopper_global)
    delag_call = LoopingCall(bithopper_global.delag_server)
    delag_call.start(10)
    reactor.run()
    bithopper_global.db.close()

if __name__ == "__main__":
    main()
