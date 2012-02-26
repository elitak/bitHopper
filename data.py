#!/usr/bin/python
#Copyright (C) 2011,2012 Colin Rice
#This software is licensed under an included MIT license.
#See the file entitled LICENSE
#If you were not provided with a copy of the license please contact: 
# Colin Rice colin@daedrum.net

import gevent
import threading, time, socket
import logging

# Global timeout for sockets in case something leaks
socket.setdefaulttimeout(900)

class Data():
    def __init__(self,bitHopper):
        self.users = {}
        self.bitHopper = bitHopper
        logging.debug = logging.debug
        self.pool = self.bitHopper.pool
        self.db = self.bitHopper.db
        self.speed = self.bitHopper.speed
        self.difficulty = self.bitHopper.difficulty
        self.lock = threading.RLock()
        try:
            self.user_drop_time = self.bitHopper.config.get('main', 'user_drop_time')
        except:
            self.user_drop_time = 3600
        with self.lock:
            users = self.db.get_users()

            for user in users:
                self.users[user] = {'shares':users[user]['shares'],'rejects':users[user]['rejects'], 'last':0, 'shares_time': [], 'hash_rate': 0}
        gevent.spawn(self.prune)

    def prune(self):
        while True:
            with self.lock:
                for user in self.users:
                    for share_time in self.users[user]['shares_time']:
                        if time.time() - share_time > 60 * 15:
                            if len(self.users[user]['shares_time']) > 1:
                                self.users[user]['shares_time'].remove(share_time)
                    self.users[user]['hash_rate'] = (len(self.users[user]['shares_time']) * 2**32) / (60 * 15 * 1000000)
            gevent.sleep(30)
    
    def get_users(self):
        with self.lock:
            users = {}
            for item in self.users:
                if self.users[item]['shares'] > 0:
                    shares_time = self.users[item]['shares_time']
                    if len(shares_time) > 0 and time.time()-max(shares_time) < int(self.user_drop_time):
                        users[item] = self.users[item]
            return users

    def user_share_add(self,user,password,shares,server):
        with self.lock:
            if user not in self.users:
                self.users[user] = {'shares':0,'rejects':0, 'last':0, 'shares_time': [], 'hash_rate': 0}
            self.users[user]['last'] = int(time.time())
            self.users[user]['shares'] += shares
            self.users[user]['shares_time'].append(int(time.time()))
            self.users[user]['hash_rate'] = (len(self.users[user]['shares_time']) * 2**32) / (60 * 15 * 1000000)

    def user_reject_add(self,user,password,rejects,server):
        with self.lock:
            if user not in self.users:
                self.users[user] = {'shares':0,'rejects':0, 'last':0, 'shares_time': [], 'hash_rate': 0}
            self.users[user]['rejects'] += rejects

    def reject_callback(self,server,data,user,password):
        try:
            self.db.update_rejects(server,1, user, password)
            self.pool.get_servers()[server]['rejects'] += 1
            self.user_reject_add(user, password, 1, server)
        except Exception, e:
            logging.debug('reject_callback_error')
            logging.debug(str(e))
            return

    def data_callback(self,server,data, user, password):
        try:
            if data != []:
                self.speed.add_shares(1)
                self.db.update_shares(server, 1, user, password)
                self.pool.get_servers()[server]['user_shares'] += 1
                self.pool.get_servers()[server]['expected_payout'] += 1.0 / self.difficulty['btc'] * 50.0
                self.user_share_add(user, password, 1, server)

        except Exception, e:
            logging.debug('data_callback_error')
            logging.debug(str(e))
    
