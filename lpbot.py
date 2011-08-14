from irclib import SimpleIRCClient
import time
import random
import re
import thread
import urllib2

class LpBot(SimpleIRCClient):
	def __init__(self):
		SimpleIRCClient.__init__(self)
		self.nick = 'lp' + str(random.randint(1,9999999999))
		self.connection.add_global_handler('disconnect', self._on_disconnect, -10)
		self.chan_list=[]
		self.newblock_re = re.compile('\*\*\* New Block \{(?P<server>.+)\} - (?P<hash>.*)')
		self.hashes = ['']
		self.hashinfo = {}
		self.server=''
		self.current_block=''
		# TODO: Use twisted
		thread.start_new_thread(self.run,())
		thread.start_new_thread(self.ircobj.process_forever,())

	def run(self):
	        while(True):
        	        if self.is_connected():
                	        self.join()
                	else:
                       		print "Connecting..."
                        	self._connect()
                	time.sleep(1)
	
	def _connect(self):
		self.connect('chat.freenode.net', 6667, self.nick)

	def is_connected(self):
		return self.connection.is_connected();

	def _on_disconnect(self, c, e):
		self.chan_list=[]
		self.connection.execute_delayed(30, self._connect)

	def on_pubmsg(self, c, e):
		bl_match = self.newblock_re.match(e.arguments()[0])
		if bl_match != None:
			last_hash = bl_match.group('hash')
			server = bl_match.group('server')
			self.decider(server, last_hash)

	def get_last_block(self):
		return self.hashes[-1]

	def decider(self, server, block):
		last_server = self.server
		last_block = self.get_last_block()
		votes = 0
		total_votes = 0

		if block not in self.hashes:
			### New block I know nothing about
			print "New Block: {" + str(server) + "} - " + block
			self.hashes.append(block)
			if len(self.hashes) > 50:
				del self.hashes[0];
			self.hashinfo[block] = [server]
			# Am I working on this now?
			if self.current_block == block:
				self.server = server
				votes = 1
				total_votes = 1
			else:
				# Info added, I have nothing else to do
				return
		else:
			# Add a vote
			self.hashinfo[block].append(server)
			# Talley the votes based on who we have selected so far
			for v in self.hashinfo[block]:
				if v == self.server:
					votes = votes + 1
				total_votes = total_votes + 1
			
			# If I haven't received the new work yet, I don't want to decide anything, just store it
			if self.current_block != block:
				print "Unknown work - " + block
				return

			print "Total Votes: " + str(total_votes)
			# Enough votes for a quarum?
			if total_votes > 5:
				# Enought compelling evidence to switch?
				# Loop through unique servers for the block
				for test_server in set(self.hashinfo[block]):
					test_votes = 0
					## Talley up the votes for that server
					for test_vote in self.hashinfo[block]:
						test_votes = total_votes + 1
					if test_votes / total_votes > .5:
						self.server = test_server
						votes = test_votes
			else: # Not enough for quarum, select first
				self.server = self.hashinfo[block][0]
				votes = 0
				for vote_server in self.hashinfo[block]:
					if vote_server == self.server:
						votes = votes + 1
		
		if (self.get_last_block() != last_block and self.current_block == block) or self.server != last_server:
			 self.say("Best Guess: {" + self.server + "} with " + str(votes) + " of " + str(total_votes) + " votes - " + self.get_last_block())

		# Cleanup
		# Delete any orbaned blocks out of blockinfo
		for clean_block, clean_val in self.hashinfo.items():
			if clean_block not in self.hashes:
				del self.hashinfo[clean_block]

	def say(self, text):
		self.connection.privmsg("#bithopper-lp", text)			
		
	def announce(self, server, last_hash):
		try:
			if self.current_block != last_hash:
				self.current_block = last_hash
				print "Announcing: *** New Block {" + str(server) + "} - " + last_hash
				self.say("*** New Block {" + str(server) + "} - " + last_hash)
				self.decider(server, last_hash)
		except Exception, e:
			print "********************************"
			print "*****  ERROR IN ANNOUCE  *******"
			print "********************************"
			print e
			traceback.print_exc(file=sys.stdout)

	def join(self):
		if '#bithopper-lp' not in self.chan_list:
	                self.connection.join('#bithopper-lp')
			self.chan_list.append('#bithopper-lp')
		self.ircobj.process_forever()

#class test_eventargs():
#	def __init__(self, message):
#		self.arguments = [message]

#if __name__ == "__main__":
#	bot = LpBot()
#	while not bot.is_connected:
#		thread.sleep(3)
#	
#	print 'Testing me first, everyone agrees'
#	bot.announce('test', '1')
#	bot.on_pubmsg('', test_eventargs('*** New Block {test} - 1'))
#	bot.on_pubmsg('', test_eventargs('*** New Block (test) - 1'))
#	bot.on_pubmsg('', test_eventargs('*** New Block (test) - 1'))
#	bot.on_pubmsg('', test_eventargs('*** New Block (test) - 1'))
#	bot.on_pubmsg('', test_eventargs('*** New Block (test) - 1'))
#
#	print 'Testing someone first, me later with wrong server'


