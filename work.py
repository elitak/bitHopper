#License#
#bitHopper by Colin Rice is licensed under a Creative Commons 
# Attribution-NonCommercial-ShareAlike 3.0 Unported License.
#Based on a work at github.com.

import json
import base64
import traceback

import eventlet
httplib2 = eventlet.import_patched('httplib20_7_1')
from eventlet import pools

import webob

class Work():
    def __init__(self, bitHopper):
        self.bitHopper = bitHopper
        self.i = 0
        self.connect_pool = {}
        #pools.Pool(min_size = 2, max_size = 10, create = lambda: httplib2.Http(disable_ssl_certificate_validation=True))

    def get_http(self, address, timeout=30):
        if address not in self.connect_pool:
            self.connect_pool[address] =  pools.Pool(min_size = 0, create = lambda: httplib2.Http(disable_ssl_certificate_validation=True, timeout=timeout))
        return self.connect_pool[address].item()

    def jsonrpc_lpcall(self, server, url, lp):
        try:
            #self.i += 1
            #request = json.dumps({'method':'getwork', 'params':[], 'id':self.i}, ensure_ascii = True)
            pool = self.bitHopper.pool.servers[server]
            header = {'Authorization':"Basic " +base64.b64encode(pool['user']+ ":" + pool['pass']), 'user-agent': 'poclbm/20110709', 'Content-Type': 'application/json' }
            with self.get_http(url, timeout=None) as http:
                try:
                    resp, content = http.request( url, 'GET', headers=header)#, body=request)[1] # Returns response dict and content str
                except Exception, e:
                    self.bitHopper.log_dbg('Error with a jsonrpc_lpcall http request')
                    self.bitHopper.log_dbg(e)
                    content = None
            lp.receive(content, server)
            return None
        except Exception, e:
            self.bitHopper.log_dbg('Error in lpcall work.py')
            self.bitHopper.log_dbg(e)
            lp.receive(None, server)
            return None

    def get(self, url):
        """A utility method for getting webpages"""
        header = {'user-agent':'Mozilla/5.0 (compatible; MSIE 9.0; Windows NT 6.1; WOW64; Trident/5.0)'}
        with self.get_http(url) as http:
            try:
                content = http.request( url, 'GET', headers=header)[1] # Returns response dict and content str
            except Exception, e:
                self.bitHopper.log_dbg('Error with a work.get http request')
                self.bitHopper.log_dbg(e)
                content = ""
                
        return content

    def jsonrpc_call(self, server, data, client_header={}):
        try:
            request = json.dumps({'method':'getwork', 'params':data, 'id':self.i}, ensure_ascii = True)
            self.i += 1
            
            info = self.bitHopper.pool.get_entry(server)
            header = {'Authorization':"Basic " +base64.b64encode(info['user']+ ":" + info['pass'])}
            user_agent = None
            for k,v in client_header:
                if k not in header:
                    header[k] = v
                if k.lower() == 'user-agent':
                    user_agent = k
            if user_agent != 'user-agent' and user_agent != None:
                header['user-agent'] = header[user_agent]
                del header[user_agent]
            
            url = "http://" + info['mine_address']
            with self.get_http(url) as http:
                try:
                    resp, content = http.request( url, 'POST', headers=header, body=request)
                except Exception, e:
                    self.bitHopper.log_dbg('Error with a jsonrpc_call http request')
                    self.bitHopper.log_dbg(e)
                    resp = {}
                    content = ""

            #Check for long polling header
            lp = self.bitHopper.lp
            if lp.check_lp(server):
                #bitHopper.log_msg('Inside LP check')
                for k,v in resp.items():
                    if k.lower() == 'x-long-polling':
                        lp.set_lp(v,server)
                        break
        except Exception, e:
            self.bitHopper.log_dbg('Caught, jsonrpc_call insides')
            self.bitHopper.log_dbg(e)
            #traceback.print_exc()
            return None, None

        try:
            message = json.loads(content)
            value =  message['result']
            return value, resp
        except Exception, e:
            self.bitHopper.log_dbg( "Error in json decoding, Server probably down")
            self.bitHopper.log_dbg(server)
            self.bitHopper.log_dbg(content)
            return None, None

    def jsonrpc_getwork(self, server, data, request, headers={}):
        tries = 0
        work = None
        while work == None:
            if data == [] and tries > 2:
                server = self.bitHopper.get_new_server(server)
            elif tries > 2:
                self.bitHopper.get_new_server(server)
            tries += 1
            try:
                if tries > 4:
                    eventlet.sleep(0.5)
                work, server_headers = self.jsonrpc_call(server, data, headers)
            except Exception, e:
                self.bitHopper.log_dbg( 'caught, inner jsonrpc_call loop')
                self.bitHopper.log_dbg(server)
                self.bitHopper.log_dbg(e)
                work = None
        return work, server_headers

    def handle(self, env, start_request):

        request = webob.Request(env)
        rpc_request = json.loads(request.body)

        client_headers = {}
        for header in env:
            if len(header)> 5 and header[0:5] is 'HTTP_':
                client_headers[header[5:]] = env[header]

        #check if they are sending a valid message
        if rpc_request['method'] != "getwork":
            return

        data = rpc_request['params']
        j_id = rpc_request['id']

        if data != []:
            server = self.bitHopper.getwork_store.get_server(data[0][72:136])
        if data == [] or server == None:
            server = self.bitHopper.pool.get_work_server()

        work, server_headers  = self.jsonrpc_getwork(server, data, request, client_headers)

        to_delete = []
        for header in server_headers:
            if header.lower() not in []: #['x-roll-ntime', 'nonce-range]:
                to_delete.append(header)
        for item in to_delete:
            del server_headers[item]  

        server_headers['X-Long-Polling'] = '/LP'

        start_request('200 OK', server_headers.items())

        response = json.dumps({"result":work, 'error':None, 'id':j_id})        

        #some reject callbacks and merkle root stores
        if str(work) == 'False':
            data = env.get('HTTP_AUTHORIZATION').split(None, 1)[1]
            username, password = data.decode('base64').split(':', 1)
            self.bitHopper.reject_callback(server, data, username, password)
        elif str(work) != 'True':
            merkle_root = work["data"][72:136]
            self.bitHopper.getwork_store.add(server,merkle_root)

        #Fancy display methods
        if self.bitHopper.options.debug:
            self.bitHopper.log_msg('RPC request ' + str(data) + " submitted to " + server)
        elif data == []:
            self.bitHopper.log_msg('RPC request [' + rpc_request['method'] + "] submitted to " + server)
        else:
            self.bitHopper.log_msg('RPC request [' + str(data[0][155:163]) + "] submitted to " + server)

        if data != []:
            data = env.get('HTTP_AUTHORIZATION').split(None, 1)[1]
            username, password = data.decode('base64').split(':', 1)
            self.bitHopper.data_callback(server, data, username,password) #request.remote_password)
        return [response]

    def handle_LP(self, env, start_response):
        start_response('200 OK', [('Content-Type', 'text/json')])
        
        request = webob.Request(env)
        j_id = None
        try:
            rpc_request = json.loads(request.body)
            j_id = rpc_request['id']

        except Exception, e:
            self.bitHopper.log_dbg('Error in json handle_LP')
            self.bitHopper.log_dbg(e)
            if not j_id:
                j_id = 1
        
        value = self.bitHopper.lp_callback.read()

        try:
            data = env.get('HTTP_AUTHORIZATION').split(None, 1)[1]
            username = data.decode('base64').split(':', 1)[0] # Returns ['username', 'password']
        except Exception,e:
            username = ''

        self.bitHopper.log_msg('LP Callback for miner: '+ username)

        response = json.dumps({"result":value, 'error':None, 'id':j_id})

        return [response]
