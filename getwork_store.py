#License#
#bitHopper by Colin Rice is licensed under a Creative Commons
# Attribution-NonCommercial-ShareAlike 3.0 Unported License.
#Based on a work at github.com.

import eventlet
from eventlet.green import threading
from eventlet.green import time

class Getwork_store:
    
    def __init__(self, bitHopper):
        self.data = {}
        self.bitHopper = bitHopper
        self.lock = threading.RLock()
        eventlet.spawn_n(self.prune)

    def add(self, server, merkle_root):
        with self.lock:
            self.data[merkle_root] = [server, time.time()]

    def get_server(self, merkle_root):
        with self.lock:
            if self.data.has_key(merkle_root):
                return self.data[merkle_root][0]
            return None      
    
    def prune(self):
        while True:
            with self.lock:
                for key, work in self.data.items():
                    if work[1] < (time.time() - (60*5)):
                        del self.data[key]
            eventlet.sleep(60)
