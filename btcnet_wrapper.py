#Copyright (C) 2011,2012 Colin Rice
#This software is licensed under an included MIT license.
#See the file entitled LICENSE
#If you were not provided with a copy of the license please contact: 
# Colin Rice colin@daedrum.net

import sys
import traceback
import logging
import httplib2
import traceback
import os.path

# TODO : These imports should occur within Pull_git. If they're not present,
# fall back to retrieving the zip.
from git import Repo
try:
    from git import GitCommandError
except ImportError:
    # Sometimes (apparently), the exception classes are in a subpackage.
    # One of these should be deprecated, but I haven't figured out which.
    from git.exc import GitCommandError

def Pull_git():
    """
    Tries to load btcnet_info as git repository and download the files
    """
    try:
        logging.info('Trying to load btcnet_info submodule')
        #Try load load btcnet_info as a git repo (Submodule)
        repo = Repo("btcnet_info")
    except GitCommandError:
        # Here we have some sort of error probably an empty directory in a zip download instead of 
        # A git submodule
        logging.info('Making new btcnet_info repo')
        repo = Repo.init("btcnet_info")
        logging.info('Cloning into it')
        repo = repo.clone_from("git://github.com/c00w/btcnet_info.git", 'btcnet_info')
        try:
            #For some reason the above doesn't always set the origin correctly.
            logging.info('Checking if we need to add the origin')
            origin = repo.create_remote('origin', 'git://github.com/c00w/btcnet_info.git')
        except GitCommandError:
            logging.info('We do not need to add the origin')
        
        
    logging.info('Updating btcnet_info')
    #Select the origin
    origin = repo.remotes.origin
    #Update it
    origin.fetch()
    #Pull the master branch
    origin.pull('master')
    logging.info('Done')
    
def Pull_zip():
    logging.info('Downloading zip archive')
    #Get the actual zip file
    headers, content = httplib2.Http(disable_ssl_certificate_validation=True).request('https://github.com/c00w/btcnet_info/zipball/master')
    
    #Proccess the zip file
    from StringIO import StringIO
    from zipfile import ZipFile
    zipfile = ZipFile(StringIO(content))
    
    logging.info('Extracting zip archive')
    for name in zipfile.namelist():
    
        #Put it in btcnet_info
        dest = name.split('/',1)[1]
        dest = os.path.join('btcnet_info',dest)
        destdir = os.path.dirname(dest)
        #Make directory if we need it
        if not os.path.isdir(destdir):
          os.makedirs(destdir)
        #Get the data
        data = zipfile.read(name)
        
        #Write the data to the correct file if we have data (Not a directory)
        if data:
            with open(dest, 'w') as f:
                f.write(data)
            
    with open('.zip', 'w') as f:
        f.write('Switched to zip mode')
    
    logging.info('Done')
    
def Install_btcnet():
    
    if os.path.exists('.zip'):
        try:
            Pull_zip()
        except Exception as error:
            logging.error(traceback.format_exc())
    else:
        try:
            Pull_git()
            import btcnet_info
        except Exception as e:
            logging.error(traceback.format_exc())
            try:
                Pull_zip()
            except Exception as error:
                logging.error(traceback.format_exc())

# other modules should use:
#   from bcnet_wrapper import btcnet_info
# to import btcnet_nifo into their namespace, automatically downloading and
# installing the module if necessary
try:
    # If we already have the module, we're done!  This will probably only work
    # if the CWD is the parent of the btcnet_info submodule.
    import btcnet_info
except ImportError:
    # Fall-through to installation attempt
    pass

if 'btcnet_info' not in globals():
    try:
        Install_btcnet()
        import btcnet_info
    except Exception:
        logging.error(traceback.format_exc())
        logging.error('Could not install btcnet_info, please report logs online plus python version' )
        sys.exit(2)
        btcnet_info = None
