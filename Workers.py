#Copyright (C) 2011,2012 Colin Rice
#This software is licensed under an included MIT license.
#See the file entitled LICENSE
#If you were not provided with a copy of the license please contact: 
# Colin Rice colin@daedrum.net

"""
File for adding multiple worker support to pools
"""
import threading, time, ConfigParser, random, gevent, webob, os, json, Queue

class Workers():
    """
    Worker information and management class
    """
    def __init__(self, bitHopper):
        self.pool = bitHopper.pool
        self.workers = {}
        self.worker_locks = {}
        self.lock = threading.Lock()
        self.parser = ConfigParser.RawConfigParser()
        # Override optionxform to avoid downcasing option names (usernames)
        self.parser.optionxform = lambda x: x
        self.queue = Queue.Queue(maxsize=-1)
        
        thread = threading.Thread(target=self.poll_thread)
        thread.daemon = True
        thread.start()
        
        WorkerSite(bitHopper)
        WorkerDataSite(bitHopper)
        
    def _nonblock_lock(self):
        """
        Utility function for doing a non blocking lock on a thread lock.
        """
        while not self.lock.acquire(False):
            gevent.sleep(0)
            
    def _release(self):
        self.lock.release()
        
    def poll_thread(self):
        """
        Thread that checks for new workers and writes them to the file
        """
        self.fd = None
        with self.lock:
            for item in self.pool.get_servers():
                self.workers[item] = []
                self.parser.add_section(item)
            self.parser.read('worker.cfg')

            for item in self.parser.sections():
                self.workers[item] = self.parser.items(item)
                self.worker_locks[item] = {}
                
                for work, passw in self.workers[item]:
                    self.worker_locks[item][(work, passw)] = threading.Semaphore(50)
                
        while True:
            self.queue.get()
            with self.lock:
                if not self.fd:
                    self.fd = open('worker.cfg', 'wb')
                try:
                    self.fd.seek(0)
                    self.parser.write(self.fd)
                except IOError as e:
                    self.fd.close()
                    self.fd = open('worker.cfg', 'wb')
                    self.queue.put(None, False)
                    
    def get_worker(self, pool):
        """
        Returns a random worker from the pool
        """
        self._nonblock_lock()
        if pool in self.workers and self.workers[pool]:
            user, passw = random.choice(self.workers[pool])
            err = None
        else:
            user, passw, err = None, None, "Not in pool"
        self._release()
        return user, passw, err
        
    def get_worker_limited(self, pool):
        """
        This is a rate limited get_worker. It only allows us to have one connection per pool per worker
        """
        while True:
            self._nonblock_lock()
            
            for pool in self.workers:
                for worker_tuple in self.worker_lock[pool]:
                    if self.worker_locks[pool][worker_tuple].acquire(False):
                        return worker_tuple[0], worker_tuple[1], None
                        
            self._release()
            gevent.sleep(0)
            
    def release_worker_limited(self, pool, worker_tuple):
        if pool in self.worker_locks:
            if worker_tuple in self.worker_locks[pool]:
                self.worker_locks[pool][worker_tuple].release()
                        
        
    def add_worker(self, pool, worker, password):
        self._nonblock_lock()
        
        #Update the parser
        if pool not in self.parser.sections():
            self.parser.add_section(pool)
            
        #Update the worker info
        if pool not in self.workers:
            self.workers[pool] = []
            
        #Update the blocking info
        if pool not in self.worker_locks:
            self.worker_locks[pool] = {}
            for item in self.workers[pool]:
                self.worker_locks[pool][item] = threading.Semaphore(50)
                
        self.parser.set(pool, worker, password)
        self.workers[pool].append((worker, password))
        self.worker_locks[pool][(worker, password)] = threading.Semaphore(50)
        
        self._release()
        self.queue.put(None, False)
        
    def remove_worker(self, pool, worker, password):
        if pool not in self.parser.sections():
            return
        self._nonblock_lock()
        self.parser.remove_option(pool, worker)
        if (worker, password) in self.workers[pool]:
            self.workers[pool].remove((worker, password))
        self._release()
        self.queue.put(None)
        
    def get_workers(self):
        return self.workers
        
class WorkerSite():
    def __init__(self, bitHopper):
        self.bitHopper = bitHopper
        self.site_names = ['/worker']
        self.auth = True
        self.bitHopper.website.sites.append(self)
        file_name = 'worker.html'
        try:
            
            # determine if application is a script file or frozen exe
            if hasattr(sys, 'frozen'):
                application_path = os.path.dirname(sys.executable)
            elif __file__:
                application_path = os.path.dirname(__file__)          
            index = os.path.join(application_path, file_name)
        except:
            index = os.path.join(os.curdir, file_name)
        fd = open(index, 'rb')
        self.line_string = fd.read()
        fd.close()
        
    def handle(self, env, start_response):
        start_response('200 OK', [('Content-Type', 'html')])
        
        self.handle_post(webob.Request(env))
        return self.line_string
        
    def handle_post(self, request):
        post = request.POST
            
        for item in ['method','user','pass', 'pool']:
            if item not in post:
                return
        
        if post['method'] == 'remove':
            self.bitHopper.workers.remove_worker(post['pool'],
                            post['user'], post['pass'])
        elif post['method'] == 'add':
            self.bitHopper.workers.add_worker(post['pool'],
                        post['user'], post['pass'])
    
class WorkerDataSite():
    def __init__(self, bitHopper):
        self.bitHopper = bitHopper
        self.site_names = ['/worker_data']
        self.auth = True
        self.bitHopper.website.sites.append(self)
        
    def handle(self, env, start_response):
        start_response('200 OK', [('Content-Type', 'text/json')])
        
        output = self.bitHopper.workers.get_workers()
        return json.dumps(output)
    
