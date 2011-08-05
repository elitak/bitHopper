#License#
#bitHopper by Colin Rice is licensed under a Creative Commons Attribution-NonCommercial-ShareAlike 3.0 Unported License.
#Based on a work at github.com.

import json
import socket
import os
import base64
import exceptions
import time
import traceback

from zope.interface import implements

from twisted.web.iweb import IBodyProducer
from twisted.web.http_headers import Headers
from twisted.internet import defer
from twisted.internet.defer import succeed, Deferred
from twisted.internet.protocol import Protocol

i = 1

class StringProducer(object):
    implements(IBodyProducer)

    def __init__(self, body):
        self.body = body
        self.length = len(body)
    def startProducing(self, consumer):
        consumer.write(self.body)
        return succeed(None)

    def pauseProducing(self):
        pass

    def stopProducing(self):
        pass

class WorkProtocol(Protocol):

    def __init__(self, finished):
        self.data = ""
        self.finished = finished
    
    def dataReceived(self, data):
        self.data += data

    def connectionLost(self, reason):
        self.finished.callback(self.data)

def print_error(x):
    print x

@defer.inlineCallbacks
def jsonrpc_lpcall(agent,server, url, lp):
    
    global i
    request = json.dumps({'method':'getwork', 'params':[], 'id':i}, ensure_ascii = True)
    i = i +1
    pool = lp.pool.servers[server]
    header = {'Authorization':["Basic " +base64.b64encode(pool['user']+ ":" + pool['pass'])], 'User-Agent': ['poclbm/20110709'],'Content-Type': ['application/json'] }
    d = agent.request('GET', "http://" + url, Headers(header), None)
    d.addErrback(print_error)
    body = yield d
    if body == None:
        lp.receive(None,server)
        defer.returnValue(None)
    finish = Deferred()
    body.deliverBody(WorkProtocol(finish))
    text = yield finish
    lp.receive(text,server)
    defer.returnValue(None)

@defer.inlineCallbacks
def get(agent,url):
    d = agent.request('GET', url, Headers({'User-Agent':['Mozilla/5.0 (Windows NT 5.1) AppleWebKit/535.1 (KHTML, like Gecko) Chrome/13.0.782.107 Safari/535.1']}),None)
    response = yield d
    finish = Deferred()
    response.deliverBody(WorkProtocol(finish))
    body = yield finish
    defer.returnValue(body)

@defer.inlineCallbacks
def jsonrpc_call(agent, server, data , bitHopper):
    global i
    try:
        request = json.dumps({'method':'getwork', 'params':data, 'id':i}, ensure_ascii = True)
        i = i +1
        
        header = {'Authorization':["Basic " +base64.b64encode(server['user']+ ":" + server['pass'])], 'User-Agent': ['poclbm/20110709'],'Content-Type': ['application/json'] }
        d = agent.request('POST', "http://" + server['mine_address'], Headers(header), StringProducer(request))
        response = yield d
        header = response.headers

        #Check for long polling header
        lp = bitHopper.lp
        if lp.check_lp(server['pool_index']):
            #bitHopper.log_msg('Inside LP check')
            for k,v in header.getAllRawHeaders():
                if k.lower() == 'x-long-polling':
                    lp.set_lp(v[0],server['pool_index'])
                    break

        finish = Deferred()
        response.deliverBody(WorkProtocol(finish))
        body = yield finish
    except Exception, e:
        bitHopper.log_dbg('Caught, jsonrpc_call insides')
        bitHopper.log_dbg(e)
        traceback.print_exc
        defer.returnValue(None)

    try:
        message = json.loads(body)
        value =  message['result']
        defer.returnValue(value)
    except Exception, e:
        bitHopper.log_dbg( "Error in json decoding, Server probably down")
        bitHopper.log_dbg(body)
        defer.returnValue(None)

@defer.inlineCallbacks
def jsonrpc_getwork(agent, server, data, j_id, request, bitHopper):

    i = 0
    work = None
    while work == None:
        i += 1
        if data == [] and i > 1:
            server = bitHopper.get_new_server(server)
        try:
            if i > 4:
                time.sleep(0.1)
            work = yield jsonrpc_call(agent, server,data,bitHopper)
        except Exception, e:
            bitHopper.log_dbg( 'caught, inner jsonrpc_call loop')
            bitHopper.log_dbg(str(e))
            work = None
            continue

    try:
        if str(work) == 'False':
            bitHopper.reject_callback(server['pool_index'], data)
        elif str(work) != 'True':
            merkle_root = work["data"][72:136]
            bitHopper.getwork_store.add(server['pool_index'],merkle_root)
        response = json.dumps({"result":work,'error':None,'id':j_id})
        request.write(response)
        request.finish()
    except Exception, e:
        bitHopper.log_dbg('caught, Final response/writing')
        bitHopper.log_dbg(str(e))
        try:
            request.finish()
        except Exception, e:
            pass
