#!/usr/bin/python
#License#
#bitHopper by Colin Rice is licensed under a Creative Commons
# Attribution-NonCommercial-ShareAlike 3.0 Unported License.
#Based on a work at github.com.

import time
import random
import math

from twisted.internet.task import LoopingCall

class Scheduler(object):
    def __init__(self,bitHopper):
        self.bh = bitHopper
        self.initData()

    def initData(self,):
        if self.bh.options.threshold:
            self.difficultyThreshold = self.bh.options.threshold
        else:
            self.difficultyThreshold = 0.435
        self.valid_roles = ['mine','mine_nmc','mine_deepbit','mine_slush','mine_ixc','mine_i0c']
        return

    @classmethod
    def server_update(self,):
        return

    @classmethod
    def select_best_server(self,):
        return

    def select_charity_server(self):
        server_name = None
        most_shares = self.bh.difficulty.get_difficulty() * 2
        for server in self.bh.pool.get_servers():
            info = self.bh.pool.get_entry(server)
            if info['role'] != 'mine_charity':
                continue
            if info['shares'] > most_shares and info['lag'] == False:
                server_name = server
                most_shares = info['shares']
                self.bh.log_dbg('select_charity_server: ' + str(server), cat='scheduler-default')

        return server_name

    def select_latehop_server(self):
        server_name = None
        max_share_count = 1
        for server in self.bh.pool.get_servers():
            info = self.bh.pool.get_entry(server)
            if info['api_lag'] or info['lag']:
                continue
            if info['role'] != 'backup_latehop':
                continue
            if info['shares'] > max_share_count:
                server_name = server
                max_share_count = info['shares']
                #self.bh.log_dbg('select_latehop_server: ' + str(server), cat='scheduler-default')

        return server_name   

    def server_to_btc_shares(self,server):
        difficulty = self.bh.difficulty.get_difficulty()
        nmc_difficulty = self.bh.difficulty.get_nmc_difficulty()
        ixc_difficulty = self.bh.difficulty.get_ixc_difficulty()
        i0c_difficulty = self.bh.difficulty.get_i0c_difficulty()
        info = self.bh.pool.get_entry(server)
        if info['role'] in ['mine', 'mine_deepbit']:
            shares = info['shares']
        elif info['role'] == 'mine_slush':
            shares = info['shares'] * self.difficultyThreshold /  0.10
        elif info['role'] == 'mine_nmc':
            shares = info['shares']*difficulty / nmc_difficulty
        elif info['role'] == 'mine_ixc':
            shares = info['shares']*difficulty / ixc_difficulty
        elif info['role'] == 'mine_i0c':
            shares = info['shares']*difficulty / i0c_difficulty
        else:
            shares = difficulty
        # apply penalty
        if 'penalty' in info:
            shares = shares * float(info['penalty'])
        return shares, info

    def select_backup_server(self,):
        #self.bh.log_dbg('select_backup_server', cat='scheduler-default')
        server_name = self.select_latehop_server()
        reject_rate = 1      

        difficulty = self.bh.difficulty.get_difficulty()
        nmc_difficulty = self.bh.difficulty.get_nmc_difficulty()

        if server_name == None:
            for server in self.bh.pool.get_servers():
                info = self.bh.pool.get_entry(server)
                if info['role'] not in ['backup', 'backup_latehop']:
                    continue
                if info['lag']:
                    continue
                shares = info['user_shares']+1
                rr_server = float(info['rejects'])/shares
                if 'penalty' in info:
                    rr_server += float(info['penalty'])/100
                if rr_server < reject_rate:
                    server_name = server
                    self.bh.log_dbg('select_backup_server: ' + str(server), cat='select_backup_server')
                    reject_rate = rr_server

        if server_name == None:
            #self.bh.log_dbg('Try another backup' + str(server), cat='scheduler-default')
            min_shares = 10**10
            for server in self.bh.pool.get_servers():
                shares,info = self.server_to_btc_shares(server)
                if info['role'] not in self.valid_roles:
                    continue
                if shares < min_shares and not info['lag']:
                    min_shares = shares
                    #self.bh.log_dbg('Selecting pool ' + str(server) + ' with shares ' + str(shares), cat='select_backup_server')
                    server_name = server
          
        if server_name == None:
            #self.bh.log_dbg('Try another backup pt2' + str(server), cat='scheduler-default')
            for server in self.bh.pool.get_servers():
                info = self.bh.pool.get_entry(server)
                if info['role'] != 'backup':
                    continue
                server_name = server
                break

        return server_name

    def update_api_server(self,server):
        return

class OldDefaultScheduler(Scheduler):

    def select_best_server(self,):
        #self.bh.log_dbg('select_best_server', cat='scheduler-default')
        server_name = None
        difficulty = self.bh.difficulty.get_difficulty()
        nmc_difficulty = self.bh.difficulty.get_nmc_difficulty()
        min_shares = difficulty * self.difficultyThreshold

        #self.bh.log_dbg('min-shares: ' + str(min_shares), cat='scheduler-default')  
        for server in self.bh.pool.get_servers():
            shares,info = self.server_to_btc_shares(server)
            if info['api_lag'] or info['lag']:
                continue
            if info['role'] not in self.valid_roles:
                continue
            if shares< min_shares:
                min_shares = shares
                #self.bh.log_dbg('Selecting pool ' + str(server) + ' with shares ' + str(info['shares']), cat='scheduler-default')
                server_name = server
         
        if server_name == None:
            server_name = self.select_charity_server()

        if server_name == None:     
            return self.select_backup_server()
        else: 
            return server_name   
   
    def select_latehop_server(self):
      server_name = None
      max_share_count = 1
      for server in self.bh.pool.get_servers():
         info = self.bh.pool.get_entry(server)
         if info['api_lag'] or info['lag']:
            continue
         if info['role'] != 'backup_latehop':
            continue
         if info['shares'] > max_share_count:
            server_name = server
            max_share_count = info['shares']
            self.bh.log_dbg('select_latehop_server: ' + str(server), cat='scheduler-default')

      return server_name   

    def server_update(self,):
      current = self.bh.pool.get_current()
      shares,info = self.server_to_btc_shares(current)
      difficulty = self.bh.difficulty.get_difficulty()

      if info['role'] not in self.valid_roles:
         return True
    
      if info['api_lag'] or info['lag']:
         return True

      if shares > (difficulty * self.difficultyThreshold):
         return True

      min_shares = info['shares']

      for server in self.bh.pool.servers:
         pool = self.bh.pool.get_entry(server)
         if pool['shares'] < min_shares:
            min_shares = pool['shares']

      if min_shares < info['shares']*.90:
        return True       

      return False

class RoundTimeScheduler(Scheduler):
   def select_best_server(self,):
      return
   def select_backup_server(self,):
      return


class RoundTimeDynamicPenaltyScheduler(Scheduler):
   def select_best_server(self,):
      return
   def select_backup_server(self,):
      return


class DefaultScheduler(Scheduler):
   def __init__(self,bitHopper):
      self.bh = bitHopper
      self.bitHopper = self.bh
      self.difficultyThreshold = 0.435
      self.sliceinfo = {}
      self.initData()
      self.lastcalled = time.time()
      call = LoopingCall(self.bh.server_update)
      call.start(10)
   def initData(self,):
      Scheduler.initData(self)
      if self.bh.options.threshold:
         #self.bh.log_msg("Override difficulty threshold to: " + str(self.bh.options.threshold), cat='scheduler-default')
         self.difficultyThreshold = self.bh.options.threshold
      self.reset()

   def reset(self,):
      for server in self.bh.pool.get_servers():
            self.sliceinfo[server] = -1

   def select_best_server(self,):
      #self.bh.log_dbg('select_best_server', cat='scheduler-default')
      server_name = None
      difficulty = self.bh.difficulty.get_difficulty()
      nmc_difficulty = self.bh.difficulty.get_nmc_difficulty()
      min_shares = difficulty * self.difficultyThreshold

      valid_servers = []
      for server in self.bh.pool.get_servers():
         shares,info = self.server_to_btc_shares(server)
         if info['role'] not in self.valid_roles:
            continue

         if shares< min_shares:
            valid_servers.append(server)
         
      for server in valid_servers:
        if server not in self.sliceinfo:
            self.sliceinfo[server] = 0
        if self.sliceinfo[server] == -1:
            self.sliceinfo[server] = 0

      for server in self.sliceinfo:
        if server not in valid_servers:
            self.sliceinfo[server] = -1

      charity_server = self.select_charity_server()
      if valid_servers == [] and charity_server != None: return charity_server

      if valid_servers == []: return self.select_backup_server()
      
      min_slice = self.sliceinfo[valid_servers[0]]
      server = valid_servers[0]
      for pool in valid_servers:
        info = self.bh.pool.servers[pool]
        if info['api_lag'] or info['lag']:
            continue
        if self.sliceinfo[pool] < min_slice:
            min_slice = self.sliceinfo[pool]
            server = pool

      return server

   
   def server_update(self,):
        #self.bitHopper.log_msg(str(self.sliceinfo))
        diff_time = time.time()-self.lastcalled
        self.lastcalled = time.time()
        current = self.sliceinfo[self.bh.pool.get_current()]
        if current == -1:
            return True

        self.sliceinfo[self.bh.pool.get_current()] += diff_time

        if self.bh.pool.servers[self.bh.pool.get_current()]['role'] not in self.valid_roles:
            return True

        valid = []
        for k in self.sliceinfo:
            if self.sliceinfo[k] != -1:
                valid.append(k)

        if len(valid) <=1:
            return True

        for server in valid:
            if current - self.sliceinfo[server] > 30:
                return True

        difficulty = self.bh.difficulty.get_difficulty()
        min_shares = difficulty * self.difficultyThreshold

        shares,info = self.server_to_btc_shares(self.bh.pool.get_current())
        
        if shares > min_shares:
            return True

        return False

class AltSliceScheduler(Scheduler):
   def __init__(self,bitHopper):
      self.bh = bitHopper
      self.bitHopper = self.bh
      self.difficultyThreshold = 0.435
      self.sliceinfo = {}
      self.name = 'scheduler-altslice'
      self.bh.log_msg('Initializing AltSliceScheduler...', cat=self.name)
      self.bh.log_msg(' - Min Slice Size: ' + str(self.bh.options.altminslicesize), cat=self.name)
      self.bh.log_msg(' - Slice Size: ' + str(self.bh.options.altslicesize), cat=self.name)
      self.initData()
      self.lastcalled = time.time()
      self.target_duration = 0
      self.sbs_count = 0
      self.initDone = False
      
   def initData(self,):
      Scheduler.initData(self)
      self.reset() 

   def reset(self,):
      for server in self.bh.pool.get_servers():
         info = self.bh.pool.get_entry(server)
         info['slice'] = -1
         info['slicedShares'] = 0
         info['init'] = False
      if (self.bh.options.altsliceroundtimebias == True):
         difficulty = self.bh.difficulty.get_difficulty()
         one_ghash = 1000000 * 1000
         target_ghash = one_ghash * int(self.bh.options.altsliceroundtimetarget) * self.difficultyThreshold
         self.bh.log_msg(' - Target Round Time Bias GHash/s: ' + str(float(target_ghash/one_ghash)), cat=self.name)
         self.target_duration = difficulty * (2**32) / target_ghash
         self.bh.log_msg(" - Target duration: " + str(int(self.target_duration)) + "(s) or " + str(int(self.target_duration/60)) + " minutes", cat=self.name)
            
   def select_best_server(self,):
      self.bh.log_trace('select_best_server', cat=self.name)
      server_name = None
      difficulty = self.bh.difficulty.get_difficulty()
      nmc_difficulty = self.bh.difficulty.get_nmc_difficulty()
      min_shares = difficulty * self.difficultyThreshold

      current_server = self.bh.pool.get_current()
      reslice = True
      fullinit = True
      allSlicesDone = True
      
      for server in self.bh.pool.get_servers():
         info = self.bh.pool.get_entry(server)
         if info['slice'] > 0:
            reslice = False
            allSlicesDone = False
         if info['init'] == False and info['role'] in self.valid_roles:
            self.bh.log_trace(server + " not yet initialized", cat=self.name)
            fullinit = False
         shares = info['shares']
         if 'penalty' in info:
            shares = shares * float(info['penalty'])
         # favor slush over other pools if low enough
         if info['role'] in ['mine_slush'] and shares * 4 < min_shares:
            fullinit = True
      
      if self.bh.pool.get_current() == None or allSlicesDone == True:
         reslice = True
      elif self.bh.pool.get_entry(current_server)['lag'] == True:
         reslice = True

      if (fullinit and self.initDone == False) or self.sbs_count > 64: # catch long init
         self.initDone = True
         reslice = True
         
      #self.bh.log_dbg('allSlicesDone: ' + str(allSlicesDone) + ' fullinit: ' + str(fullinit) + ' initDone: ' + str(self.initDone), cat='reslice')
      if (reslice == True):
         self.bh.log_msg('Re-Slicing...', cat=self.name)
         totalshares = 0
         totalweight = 0
         server_shares = {}
         for server in self.bh.pool.get_servers():
            shares,info = self.server_to_btc_shares(server)
            if info['role'] not in self.valid_roles:
               continue
            if info['api_lag'] or info['lag']:
               continue
            if shares < min_shares and shares > 0:               
               totalshares = totalshares + shares           
               info['slicedShares'] = info['shares']
               server_shares[server] = shares
            else:
               self.bh.log_trace(server + ' skipped ')
               continue
            
         # find total weight   
         for server in self.bh.pool.get_servers():
            shares,info = self.server_to_btc_shares(server)
            if info['role'] not in self.valid_roles:
               continue
            if info['api_lag'] or info['lag']:
               continue
            if server not in server_shares: continue
            if server_shares[server] < min_shares and server_shares[server] > 0:
               totalweight += 1/(float(shares)/totalshares)
                  
                  
         # round time biasing
         tb_delta = {}
         tb_log_delta = {}
         pos_weight = {}
         neg_weight = {}
         adj_slice = {}
         # TODO punish duration estimates weighed by temporal duration
         if (self.bh.options.altsliceroundtimebias == True):
            # delta from target
            for server in self.bh.pool.get_servers():              
               info = self.bh.pool.get_entry(server)
               if info['role'] not in ['mine','mine_nmc','mine_slush']: continue
               if info['duration'] <= 0: continue
               if server not in server_shares: continue
               tb_delta[server] = self.target_duration - info['duration'] + 1
               tb_log_delta[server] = math.log(abs(tb_delta[server]))
               self.bh.log_trace('  ' + server + " delta: " + str(tb_delta[server]) + " log_delta: " + str(tb_log_delta[server]), cat=self.name)            

            # pos/neg_total
            pos_total = 0
            neg_total = 0
            for server in self.bh.pool.get_servers():              
               info = self.bh.pool.get_entry(server)
               if info['role'] not in ['mine','mine_nmc','mine_slush']: continue
               if info['duration'] <= 0: continue
               if server not in server_shares: continue
               if tb_delta[server] >= 0: pos_total += tb_log_delta[server]
               if tb_delta[server]  < 0: neg_total += tb_log_delta[server]
            self.bh.log_trace("pos_total: " + str(pos_total) + " / neg_total: " + str(neg_total), cat=self.name)   
            
            # preslice            
            self.bh.options.altslicesize
            for server in self.bh.pool.get_servers():
               if server in tb_delta:
                  info = self.bh.pool.get_entry(server)
                  if info['isDurationEstimated'] == True and info['duration_temporal'] < 300:
                     tb_delta[server] = 0
                  else:
                     if tb_delta[server] >= 0:
                        pos_weight[server] = tb_log_delta[server] / pos_total
                        self.bh.log_trace(server + " pos_weight: " + str(pos_weight[server]), cat=self.name)
                     elif tb_delta[server] < 0:
                        neg_weight[server] = tb_log_delta[server] / neg_total
                        self.bh.log_trace(server + " neg_weight: " + str(neg_weight[server]), cat=self.name)
                                                

         # allocate slices         
         for server in self.bh.pool.get_servers():
            info = self.bh.pool.get_entry(server)
            if info['role'] not in self.valid_roles:
               continue
            if info['shares'] <=0: continue
            if server not in server_shares: continue
            shares = server_shares[server] + 1
            if shares < min_shares and shares > 0:
               weight = 0
               self.bh.log_trace('tb_delta: ' + str(len(tb_delta)) + ' / server_shares: ' + str(len(server_shares)), cat=self.name)
               if (self.bh.options.altsliceroundtimebias == True):
                  if len(tb_delta) == 1 and len(server_shares) == 1:
                     # only 1 server to slice (zzz)
                     if info['duration'] > 0:
                        slice = self.bh.options.altslicesize
                     else:
                        slice = 0
                  else:
                     weight = 1/(float(shares)/totalshares)
                     slice = weight * self.bh.options.altslicesize / totalweight
                     if self.bh.options.altslicejitter != 0:
                        jitter = random.randint(0-self.bh.options.altslicejitter, self.bh.options.altslicejitter)
                        slice += jitter
               else:                  
                  if shares == totalshares:
                     # only 1 server to slice (zzz)
                     slice = self.bh.options.altslicesize
                  else:
                     weight = 1/(float(shares)/totalshares)
                     slice = weight * self.bh.options.altslicesize / totalweight
                     if self.bh.options.altslicejitter != 0:
                        jitter = random.randint(0-self.bh.options.altslicejitter, self.bh.options.altslicejitter)
                        slice += jitter
               info['slice'] = slice
               if self.bh.options.debug:
                  self.bh.log_dbg(server + " sliced to " + "{0:.2f}".format(info['slice']) + '/' + "{0:d}".format(int(self.bh.options.altslicesize)) + '/' + str(shares) + '/' + "{0:.3f}".format(weight) + '/' + "{0:.3f}".format(totalweight) , cat=self.name)
               else:
                  self.bh.log_msg(server + " sliced to " + "{0:.2f}".format(info['slice']), cat=self.name)
               
         # adjust based on round time bias
         if self.bh.options.altsliceroundtimebias == True:
            self.bh.log_dbg('Check if apply Round Time Bias: tb_log_delta: ' + str(len(tb_log_delta)) + ' == servers: ' + str(len(server_shares)), cat=self.name)
         if self.bh.options.altsliceroundtimebias == True and len(tb_log_delta) >= 1:            
            self.bh.log_msg('>>> Apply Round Time Bias === ', cat=self.name)
            ns_total = 0
            adj_factor = self.bh.options.altsliceroundtimemagic
            self.bh.log_trace('     server: ' + server)
            for server in self.bh.pool.get_servers():
               info = self.bh.pool.get_entry(server)
               if server not in tb_log_delta: continue # no servers to adjust
               self.bh.log_trace('     server(tld): ' + server)
               if server in pos_weight:
                  adj_slice[server] = info['slice'] + adj_factor * pos_weight[server]
                  self.bh.log_trace('     server (pos): ' + str(adj_slice[server]))
                  ns_total += adj_slice[server]            
               elif server in neg_weight:                  
                  adj_slice[server] = info['slice'] - adj_factor * neg_weight[server]
                  self.bh.log_trace('     server (neg): ' + str(adj_slice[server]))
                  ns_total += adj_slice[server]
            # re-slice the slices
            ad_totalslice = 0
            for server in self.bh.pool.get_servers():
               info = self.bh.pool.get_entry(server)
               if info['role'] not in ['mine','mine_nmc','mine_slush']:
                  continue
               if info['shares'] <=0: continue
               if server not in server_shares: continue
               shares = server_shares[server] + 1
               if shares < min_shares and shares > 0:
                  if server in adj_slice:
                     ad_totalslice += adj_slice[server]
                  else:
                     ad_totalslice += info['slice']
                     
            for server in self.bh.pool.get_servers():            
               info = self.bh.pool.get_entry(server)
               if info['role'] not in ['mine','mine_nmc','mine_slush']:
                  continue
               if info['shares'] <=0: continue
               if server not in server_shares: continue
               if server not in tb_log_delta: continue # no servers to adjust
               shares = server_shares[server] + 1
               if shares < min_shares and shares > 0:
                  if server in adj_slice:
                     previous = info['slice']
                     info['slice'] = self.bh.options.altslicesize * (adj_slice[server] / ad_totalslice)
                     if self.bh.options.debug:
                        self.bh.log_dbg(server + " _adjusted_ slice to " + "{0:.2f}".format(info['slice']) + '/' + "{0:d}".format(int(self.bh.options.altslicesize)) + '/' + str(shares) + '/' + "{0:.3f}".format(adj_slice[server]) + '/' + "{0:.3f}".format(ad_totalslice) , cat=self.name)
                     else:
                        self.bh.log_msg('  > ' + server + " _adjusted_ slice to " + "{0:.2f}".format(info['slice']) + " from {0:.2f}".format(previous), cat=self.name)
                  else:
                     info['slice'] = self.bh.options.altslicesize * (info['slice'] / ad_totalslice)
                     if self.bh.options.debug:
                        self.bh.log_dbg(server + " sliced to " + "{0:.2f}".format(info['slice']) + '/' + "{0:d}".format(int(self.bh.options.altslicesize)) + '/' + str(shares) + '/na/' + "{0:.3f}".format(ad_totalslice) , cat=self.name)
                     else:
                        self.bh.log_msg(server + " sliced to " + "{0:.2f}".format(info['slice']), cat=self.name)
                                 
         # min share adjustment
         for server in self.bh.pool.get_servers():
            info = self.bh.pool.get_entry(server)
            if info['role'] not in ['mine','mine_nmc','mine_slush']:
               continue
            if info['shares'] <=0: continue
            if server not in server_shares: continue
            if info['slice'] < self.bh.options.altminslicesize:
               info['slice'] = self.bh.options.altminslicesize
               if self.bh.options.debug:
                  self.bh.log_dbg(server + " (min)sliced to " + "{0:.2f}".format(info['slice']) + '/' + "{0:d}".format(int(self.bh.options.altslicesize)) + '/' + str(shares) + '/' + "{0:d}".format(info['duration']), cat=self.name)
               else:
                  self.bh.log_msg(server + " (min)sliced to " + "{0:.2f}".format(info['slice']), cat=self.name)                                           
   
      # Pick server with largest slice first
      max_slice = -1
      for server in self.bh.pool.get_servers():
         info = self.bh.pool.get_entry(server)
         shares = info['shares']
         if 'penalty' in info:
            shares = shares * float(info['penalty'])
         # favor slush over other pools if low enough
         if info['role'] in ['mine_slush'] and shares * 4 < min_shares:
            server_name = server
            continue
         if info['role'] in self.valid_roles and info['slice'] > 0 and not info['lag']:
            if max_slice == -1:
               max_slice = info['slice']
               server_name = server
            if info['slice'] > max_slice:
               max_slice = info['slice']
               server_name = server
   
      if server_name == None: server_name = self.select_charity_server()
               
      #self.bh.log_dbg('server_name: ' + str(server_name), cat=self.name)
      if server_name == None:
         self.bh.log_msg('No servers to slice, picking a backup...')
         server_name = self.select_backup_server()
      return server_name
         

   def server_update(self,):
      #self.bh.log_dbg('server_update', cat='server_update')
      diff_time = time.time()-self.lastcalled
      self.lastcalled = time.time()
      current = self.bh.pool.get_current()
      shares,info = self.server_to_btc_shares(current)
      info['slice'] = info['slice'] - diff_time
      #self.bh.log_dbg(current_server + ' slice ' + str(info['slice']), cat='server_update' )
      if self.initDone == False:
         self.bh.select_best_server()
         return True
      if info['slice'] <= 0: return True
      
      # shares are now less than shares at time of slicing (new block found?)
      if info['slicedShares'] > info['shares']:
         self.bh.log_dbg("slicedShares > shares")
         return True
      
      # double check role
      if info['role'] not in self.valid_roles: return True
      
      # check to see if threshold exceeded
      difficulty = self.bh.difficulty.get_difficulty()
      min_shares = difficulty * self.difficultyThreshold

      if shares > min_shares:
         self.bh.log_dbg("shares > min_shares")
         info['slice'] = -1 # force switch
         return True
      
      return False

   def update_api_server(self,server):
      info = self.bh.pool.get_entry(server)
      if info['role'] in ['info', 'disable'] and info['slice'] > 0:
         info['slice'] = -1
      return

